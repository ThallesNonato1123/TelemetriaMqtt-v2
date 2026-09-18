import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import paho.mqtt.client as mqtt
import pytest
from websockets.sync.client import connect as ws_connect

from conftest import TEST_USERS
from mock_publisher.publisher import MQTT_TOPIC, publish_snapshot
from mock_publisher.signal_generator import SIGNAL_SPECS
from test_docker_compose import (
    _compose_service_is_running,
    _grafana_api_get,
    _read_env_file,
    _wait_for_http_ok,
    _wait_for_port,
)

# Checkpoint 7: caminho ao vivo (Mosquitto -> plugin grafana-mqtt-datasource
# -> Grafana Live). Tudo aqui roda contra o docker-compose.yml REAL (mesmo
# Grafana, mesmos arquivos de provisioning) -- só o Mosquitto troca o passwd
# por um descartável (ver fixture live_stack), pra não depender nem mexer no
# passwd real do dev.

INFRA_DIR = Path(__file__).parent.parent
MOSQUITTO_CONFIG_DIR = INFRA_DIR / "mosquitto" / "config"
DASHBOARDS_DIR = INFRA_DIR / "grafana" / "dashboards"

GRAFANA_URL = "http://127.0.0.1:3000"
GRAFANA_WS_URL = "ws://127.0.0.1:3000/api/live/ws"
MQTT_DATASOURCE_UID = "mqtt-live"
LIVE_DASHBOARD_UID = "telemetria-ao-vivo"
# Namespace do Grafana 13 pra org 1 -- é o prefixo que o frontend usa nos
# canais Live (config.bootData.settings.namespace). Projeto de org única.
GRAFANA_NAMESPACE = "default"
# "Soft real-time (centenas de ms)" do SCOPE.md: o plugin agrupa mensagens
# num frame a cada `interval`, então esse intervalo é o piso da latência.
MAX_LIVE_INTERVAL_MS = 500


def test_live_dashboard_generator_output_matches_committed_file():
    # Mesma ideia do dashboard histórico (SCOPE.md, checkpoint 6): o JSON
    # é gerado por script, então o arquivo versionado não pode divergir do
    # que o gerador produz hoje -- senão alguém editou um dos dois à mão.
    result = subprocess.run(
        ["python3", str(INFRA_DIR / "grafana" / "generate_live_dashboard.py")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    committed = (DASHBOARDS_DIR / "ao-vivo.json").read_text()
    assert json.loads(result.stdout) == json.loads(committed)


def _build_test_mosquitto_config(tmp_dir: Path) -> Path:
    """
    Copia mosquitto.conf/acl.conf REAIS pra um diretório temporário e cria
    lá um passwd descartável com os dois usuários de teste (mesma técnica
    de conftest.mosquitto_broker). Devolve o diretório de config.
    """
    config_dir = tmp_dir / "config"
    shutil.copytree(MOSQUITTO_CONFIG_DIR, config_dir, ignore=shutil.ignore_patterns("passwd"))
    (config_dir / "passwd").touch()
    for username, password in TEST_USERS.items():
        subprocess.run(
            [
                "docker", "run", "--rm",
                "-v", f"{config_dir}:/mosquitto/config",
                "eclipse-mosquitto:2",
                "mosquitto_passwd", "-b", "/mosquitto/config/passwd", username, password,
            ],
            check=True, capture_output=True,
        )
    return config_dir


@pytest.fixture(scope="module")
def live_stack():
    """
    Sobe mosquitto + influxdb + grafana do docker-compose.yml real. Um
    arquivo de override troca só o diretório de config do Mosquitto (passwd
    descartável com as credenciais de teste), e MQTT_READER_PASSWORD vai
    por variável de ambiente do processo (que tem precedência sobre o
    infra/.env) -- assim o Grafana autentica com a senha de teste, e o
    passwd/.env reais do dev ficam intocados.

    Se a stack já estava de pé antes do teste, é recriada com o override e,
    no final, restaurada com a configuração normal; o que estava parado
    volta a ficar parado.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="grafana-live-test-"))
    config_dir = _build_test_mosquitto_config(tmp_dir)

    override = tmp_dir / "override.yml"
    override.write_text(
        "services:\n"
        "  mosquitto:\n"
        "    volumes:\n"
        f"      - {config_dir}:/mosquitto/config:ro\n"
        "      - mosquitto-data:/mosquitto/data\n"
    )

    services = ("mosquitto", "influxdb", "grafana")
    was_running = {s: _compose_service_is_running(s) for s in services}
    base_cmd = ["docker", "compose", "--project-directory", str(INFRA_DIR)]
    test_env = {**os.environ, "MQTT_READER_PASSWORD": TEST_USERS["telemetria_reader"]}

    try:
        up = subprocess.run(
            [*base_cmd, "-f", str(INFRA_DIR / "docker-compose.yml"), "-f", str(override),
             "up", "-d", *services],
            capture_output=True, text=True, env=test_env,
        )
        assert up.returncode == 0, up.stderr

        _wait_for_port(1883, timeout=30)
        # Primeira subida baixa o plugin do grafana.com antes de o Grafana
        # ficar saudável (GF_PLUGINS_PREINSTALL_SYNC), então timeout folgado.
        _wait_for_http_ok(f"{GRAFANA_URL}/api/health", timeout=120)

        yield {"admin_password": _read_env_file()["GRAFANA_ADMIN_PASSWORD"]}
    finally:
        for service in services:
            if not was_running[service]:
                subprocess.run([*base_cmd, "stop", service], capture_output=True)
                subprocess.run([*base_cmd, "rm", "-f", service], capture_output=True)
        restore = [s for s in services if was_running[s]]
        if restore:
            subprocess.run([*base_cmd, "up", "-d", *restore], capture_output=True)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _basic_auth_header(password: str) -> str:
    return "Basic " + base64.b64encode(b"admin:" + password.encode()).decode()


def _grafana_api_post(path: str, password: str, payload: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"{GRAFANA_URL}{path}",
        data=json.dumps(payload).encode() if payload is not None else b"",
        method="POST",
    )
    req.add_header("Authorization", _basic_auth_header(password))
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _topic_to_live_path(topic: str) -> str:
    # O plugin exige o tópico em base64 URL-safe sem padding (restrição de
    # caracteres dos canais do Grafana Live) -- o frontend do plugin faz
    # isso em applyTemplateVariables.
    return base64.urlsafe_b64encode(topic.encode()).decode().rstrip("=")


def _interval_ms(interval: str) -> int:
    match = re.fullmatch(r"(\d+)ms", interval)
    assert match, f"intervalo '{interval}' deveria estar em ms (ex: 200ms)"
    return int(match.group(1))


def test_mqtt_plugin_is_installed_with_valid_signature(live_stack):
    plugin = _grafana_api_get("/api/plugins/grafana-mqtt-datasource/settings", live_stack["admin_password"])
    assert plugin["signature"] == "valid"
    assert plugin["type"] == "datasource"


def test_mqtt_datasource_is_provisioned(live_stack):
    datasources = _grafana_api_get("/api/datasources", live_stack["admin_password"])
    by_uid = {d["uid"]: d for d in datasources}

    mqtt_ds = by_uid.get(MQTT_DATASOURCE_UID)
    assert mqtt_ds is not None, f"datasource '{MQTT_DATASOURCE_UID}' não provisionado: {list(by_uid)}"
    assert mqtt_ds["type"] == "grafana-mqtt-datasource"
    assert mqtt_ds["jsonData"]["uri"] == "tcp://mosquitto:1883"
    # Usuário read-only da ACL (acl.conf) -- o Grafana nunca publica.
    assert mqtt_ds["jsonData"]["username"] == "telemetria_reader"
    # secureJsonFields só vem no endpoint de um datasource individual, não
    # na listagem.
    single = _grafana_api_get(f"/api/datasources/uid/{MQTT_DATASOURCE_UID}", live_stack["admin_password"])
    assert single["secureJsonFields"].get("password") is True

    # O InfluxDB (caminho histórico) continua sendo o datasource padrão.
    assert by_uid["influxdb-main"]["isDefault"] is True
    assert mqtt_ds["isDefault"] is False


def test_mqtt_datasource_health_check_authenticates_against_real_broker(live_stack):
    # O health check do plugin abre uma conexão MQTT de verdade com as
    # credenciais provisionadas -- valida rede entre containers, passwd e
    # a variável MQTT_READER_PASSWORD de ponta a ponta.
    result = _grafana_api_post(
        f"/api/datasources/uid/{MQTT_DATASOURCE_UID}/health", live_stack["admin_password"],
    )
    assert result["status"] == "OK", result


def test_live_dashboard_is_provisioned_with_one_streaming_panel_per_group(live_stack):
    dashboards = _grafana_api_get("/api/search?query=", live_stack["admin_password"])
    assert any(d["uid"] == LIVE_DASHBOARD_UID for d in dashboards)

    dashboard = _grafana_api_get(
        f"/api/dashboards/uid/{LIVE_DASHBOARD_UID}", live_stack["admin_password"],
    )["dashboard"]
    panels = dashboard["panels"]
    assert len(panels) == 7  # mesmos 7 agrupamentos do dashboard histórico

    plotted_signals = set()
    for panel in panels:
        assert panel["type"] == "timeseries"
        assert panel["datasource"]["uid"] == MQTT_DATASOURCE_UID

        (target,) = panel["targets"]
        assert target["topic"] == MQTT_TOPIC

        # O plugin devolve um frame com TODOS os campos do JSON; cada painel
        # filtra só os do seu grupo (+ o campo de tempo).
        (filter_transform,) = [t for t in panel["transformations"] if t["id"] == "filterFieldsByName"]
        names = set(filter_transform["options"]["include"]["names"])
        assert "Time" in names
        plotted_signals |= names - {"Time"}

        assert _interval_ms(panel["interval"]) <= MAX_LIVE_INTERVAL_MS

    assert plotted_signals == set(SIGNAL_SPECS)


def _pushed_frame(raw: str) -> dict | None:
    """
    Extrai {campo: [valores]} de uma mensagem de push do Grafana Live
    (protocolo Centrifuge/JSON), ou None se a mensagem não for um push de
    dados (ack de subscribe, ping etc.).
    """
    message = json.loads(raw)
    data = message.get("push", {}).get("pub", {}).get("data")
    if not data or "schema" not in data:
        return None
    names = [f["name"] for f in data["schema"]["fields"]]
    values = data.get("data", {}).get("values", [])
    if not values or len(values) != len(names):
        return None
    return dict(zip(names, values))


def test_mock_publisher_message_reaches_grafana_live_websocket(live_stack):
    # A validação mais forte do checkpoint: o código de produção do mock
    # publisher publica no broker real; o plugin real (dentro do Grafana
    # real) assina o tópico; e um cliente WebSocket -- o mesmo caminho que
    # o navegador usa nos painéis -- recebe os valores pelo Grafana Live.
    password = live_stack["admin_password"]
    dashboard = _grafana_api_get(f"/api/dashboards/uid/{LIVE_DASHBOARD_UID}", password)["dashboard"]
    panel = dashboard["panels"][0]

    # Reproduz a query que o frontend faz pro painel: o backend do plugin
    # responde com o nome do canal Live a assinar (meta.channel).
    query_result = _grafana_api_post("/api/ds/query", password, {
        "queries": [{
            "refId": "A",
            "datasource": {"type": "grafana-mqtt-datasource", "uid": MQTT_DATASOURCE_UID},
            "topic": _topic_to_live_path(panel["targets"][0]["topic"]),
            "streamingKey": f"{MQTT_DATASOURCE_UID}/pytest/{GRAFANA_NAMESPACE}",
            "intervalMs": _interval_ms(panel["interval"]),
            "maxDataPoints": 800,
        }],
        "from": "now-1m",
        "to": "now",
    })
    channel = query_result["results"]["A"]["frames"][0]["schema"]["meta"]["channel"]

    publisher = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5,
    )
    publisher.username_pw_set("esp32_telemetria", TEST_USERS["esp32_telemetria"])
    publisher.connect("127.0.0.1", 1883)
    publisher.loop_start()

    published_ts = set()
    received = None
    try:
        with ws_connect(
            GRAFANA_WS_URL, additional_headers={"Authorization": _basic_auth_header(password)},
        ) as ws:
            ws.send(json.dumps({"id": 1, "connect": {"name": "pytest"}}))
            assert "connect" in json.loads(ws.recv(timeout=5))
            ws.send(json.dumps({"id": 2, "subscribe": {"channel": f"{GRAFANA_NAMESPACE}/{channel}"}}))

            # O plugin só assina o tópico no broker depois que o stream
            # começa; publicar em loop a 20Hz (como o dispositivo real) em
            # vez de uma vez só evita depender do timing dessa assinatura.
            t = 0.0
            deadline = time.monotonic() + 20
            while received is None and time.monotonic() < deadline:
                publish_snapshot(publisher, t=t, dry_run=False)
                published_ts.add(int(round(t * 1000)))
                t += 0.05
                try:
                    raw = ws.recv(timeout=0.05)
                except TimeoutError:
                    continue
                frame = _pushed_frame(raw)
                if frame and frame.get("rpm"):
                    received = frame
    finally:
        publisher.loop_stop()
        publisher.disconnect()

    assert received is not None, "nenhum dado chegou pelo Grafana Live em 20s"
    assert set(SIGNAL_SPECS) | {"Time", "ts"} <= set(received)
    assert all(800.0 <= rpm <= 8000.0 for rpm in received["rpm"])
    assert set(received["ts"]) <= published_ts
