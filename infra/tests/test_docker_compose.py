import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS

from ingestion.influx_writer import make_influx_writer
from ingestion.transform import InfluxPoint

INFRA_DIR = Path(__file__).parent.parent
PASSWD_PATH = INFRA_DIR / "mosquitto" / "config" / "passwd"
GENERATE_SCRIPT = INFRA_DIR / "mosquitto" / "generate_passwd.sh"
ENV_PATH = INFRA_DIR / ".env"


def _read_env_file() -> dict:
    env = {}
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key] = value
    return env

# Os testes de test_mosquitto_acl.py/test_mosquitto_auth.py sobem containers
# efêmeros via "docker run" direto, com config copiada pra um diretório
# temporário -- isso nunca exercitou o docker-compose.yml real em si (nomes
# de serviço, mapeamento de porta, volumes, restart policy). Esse arquivo
# testa o docker-compose.yml tal como ele é, não uma cópia dele.


def _wait_for_port(port: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            try:
                s.connect(("127.0.0.1", port))
                return
            except OSError:
                time.sleep(0.3)
    raise TimeoutError(f"mosquitto (docker compose) não respondeu na porta {port} em {timeout}s")


def _compose_service_is_running(service: str = "mosquitto") -> bool:
    result = subprocess.run(
        ["docker", "compose", "ps", "-q", service],
        cwd=INFRA_DIR, capture_output=True, text=True,
    )
    return bool(result.stdout.strip())


def _wait_for_http_ok(url: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.5)
    raise TimeoutError(f"{url} não respondeu 200 em {timeout}s")


def test_docker_compose_config_is_syntactically_valid():
    # "docker compose config" resolve e valida o arquivo sem subir nada --
    # pega erro de YAML/schema antes de qualquer teste mais pesado.
    result = subprocess.run(
        ["docker", "compose", "config"],
        cwd=INFRA_DIR, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_docker_compose_up_starts_a_working_broker():
    # Preserva um passwd real que o dev já tenha configurado -- só gera um
    # temporário se não existir nenhum, e só remove no final se fomos nós
    # que criamos. Mesma lógica pro container: se já tiver rodando (dev
    # com o stack de pé), não paramos no final -- não é responsabilidade
    # do teste derrubar o ambiente de trabalho de outra pessoa.
    passwd_existed = PASSWD_PATH.exists()
    was_already_running = _compose_service_is_running()

    if not passwd_existed:
        result = subprocess.run(
            ["bash", str(GENERATE_SCRIPT), "esp32_telemetria"],
            input="senha-smoke-test-temporaria\n",
            text=True, capture_output=True,
        )
        assert result.returncode == 0, result.stderr

    try:
        up = subprocess.run(
            ["docker", "compose", "up", "-d"],
            cwd=INFRA_DIR, capture_output=True, text=True,
        )
        assert up.returncode == 0, up.stderr

        _wait_for_port(1883)

        # Só confirma que o serviço definido no compose (nome do container,
        # porta mapeada) está de pé e aceitando conexão TCP -- a lógica de
        # auth/ACL em si já é validada nos outros arquivos de teste, contra
        # a mesma config, só que subida via "docker run" direto.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(3)
            s.connect(("127.0.0.1", 1883))

        ps = subprocess.run(
            ["docker", "compose", "ps", "--format", "{{.Name}}"],
            cwd=INFRA_DIR, capture_output=True, text=True,
        )
        assert "telemetria-mosquitto" in ps.stdout
    finally:
        if not was_already_running:
            subprocess.run(["docker", "compose", "down"], cwd=INFRA_DIR, capture_output=True)
        if not passwd_existed:
            PASSWD_PATH.unlink(missing_ok=True)


def test_docker_compose_up_starts_a_working_influxdb():
    # infra/.env já existe a essa altura (fixture autouse ensure_env_file
    # em conftest.py garante isso antes de qualquer teste rodar) -- não
    # precisa bootstrapar nada aqui, só subir e checar.
    was_already_running = _compose_service_is_running("influxdb")

    try:
        up = subprocess.run(
            ["docker", "compose", "up", "-d", "influxdb"],
            cwd=INFRA_DIR, capture_output=True, text=True,
        )
        assert up.returncode == 0, up.stderr

        _wait_for_http_ok("http://127.0.0.1:8086/health")

        ps = subprocess.run(
            ["docker", "compose", "ps", "--format", "{{.Name}}"],
            cwd=INFRA_DIR, capture_output=True, text=True,
        )
        assert "telemetria-influxdb" in ps.stdout
    finally:
        if not was_already_running:
            subprocess.run(["docker", "compose", "stop", "influxdb"], cwd=INFRA_DIR, capture_output=True)
            subprocess.run(["docker", "compose", "rm", "-f", "influxdb"], cwd=INFRA_DIR, capture_output=True)


def _grafana_api_get(path: str, password: str) -> dict:
    import base64

    req = urllib.request.Request(f"http://127.0.0.1:3000{path}")
    creds = base64.b64encode(b"admin:" + password.encode()).decode()
    req.add_header("Authorization", f"Basic {creds}")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def test_docker_compose_up_starts_a_working_grafana():
    # grafana depende do influxdb (depends_on no compose) pra provisionar o
    # datasource com sucesso -- sobe os dois.
    influxdb_was_running = _compose_service_is_running("influxdb")
    grafana_was_running = _compose_service_is_running("grafana")

    try:
        up = subprocess.run(
            ["docker", "compose", "up", "-d", "influxdb", "grafana"],
            cwd=INFRA_DIR, capture_output=True, text=True,
        )
        assert up.returncode == 0, up.stderr

        _wait_for_http_ok("http://127.0.0.1:3000/api/health")

        env = _read_env_file()
        datasources = _grafana_api_get("/api/datasources", env["GRAFANA_ADMIN_PASSWORD"])
        assert len(datasources) == 2
        assert datasources[0]["type"] == "influxdb"
        assert datasources[0]["jsonData"]["organization"] == env["INFLUXDB_INIT_ORG"]
        assert datasources[0]["jsonData"]["defaultBucket"] == env["INFLUXDB_INIT_BUCKET"]

        dashboards = _grafana_api_get("/api/search?query=", env["GRAFANA_ADMIN_PASSWORD"])
        assert any(d["uid"] == "telemetria-historico" for d in dashboards)

        dashboard = _grafana_api_get(
            "/api/dashboards/uid/telemetria-historico", env["GRAFANA_ADMIN_PASSWORD"],
        )
        assert len(dashboard["dashboard"]["panels"]) == 7
    finally:
        if not grafana_was_running:
            subprocess.run(["docker", "compose", "stop", "grafana"], cwd=INFRA_DIR, capture_output=True)
            subprocess.run(["docker", "compose", "rm", "-f", "grafana"], cwd=INFRA_DIR, capture_output=True)
        if not influxdb_was_running:
            subprocess.run(["docker", "compose", "stop", "influxdb"], cwd=INFRA_DIR, capture_output=True)
            subprocess.run(["docker", "compose", "rm", "-f", "influxdb"], cwd=INFRA_DIR, capture_output=True)


def test_grafana_queries_real_data_through_provisioned_datasource():
    # A validação mais forte: escreve um ponto real no InfluxDB (via
    # make_influx_writer de produção) e consulta de volta através da
    # própria API do Grafana (/api/ds/query, o mesmo caminho que os
    # painéis do dashboard usam) -- não direto no InfluxDB. Confirma que
    # datasource + rede entre os containers do compose funcionam de
    # ponta a ponta, não só que a configuração "parece certa".
    influxdb_was_running = _compose_service_is_running("influxdb")
    grafana_was_running = _compose_service_is_running("grafana")

    try:
        up = subprocess.run(
            ["docker", "compose", "up", "-d", "influxdb", "grafana"],
            cwd=INFRA_DIR, capture_output=True, text=True,
        )
        assert up.returncode == 0, up.stderr
        _wait_for_http_ok("http://127.0.0.1:8086/health")
        _wait_for_http_ok("http://127.0.0.1:3000/api/health")

        env = _read_env_file()

        with InfluxDBClient(
            url="http://127.0.0.1:8086", token=env["INFLUXDB_INIT_ADMIN_TOKEN"], org=env["INFLUXDB_INIT_ORG"],
        ) as influx_client:
            write_api = influx_client.write_api(write_options=SYNCHRONOUS)
            writer = make_influx_writer(write_api, bucket=env["INFLUXDB_INIT_BUCKET"], org=env["INFLUXDB_INIT_ORG"])
            writer(InfluxPoint(measurement="telemetry", fields={"rpm": 5555.0}, time_ns=time.time_ns()))

        body = json.dumps({
            "queries": [{
                "refId": "A",
                "datasource": {"type": "influxdb", "uid": "influxdb-main"},
                "query": (
                    'from(bucket: "telemetria") |> range(start: -5m) '
                    '|> filter(fn: (r) => r._measurement == "telemetry") '
                    '|> filter(fn: (r) => r._field == "rpm")'
                ),
            }],
        }).encode()

        import base64
        req = urllib.request.Request("http://127.0.0.1:3000/api/ds/query", data=body, method="POST")
        creds = base64.b64encode(b"admin:" + env["GRAFANA_ADMIN_PASSWORD"].encode()).decode()
        req.add_header("Authorization", f"Basic {creds}")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())

        values = result["results"]["A"]["frames"][0]["data"]["values"][1]
        assert 5555.0 in values
    finally:
        if not grafana_was_running:
            subprocess.run(["docker", "compose", "stop", "grafana"], cwd=INFRA_DIR, capture_output=True)
            subprocess.run(["docker", "compose", "rm", "-f", "grafana"], cwd=INFRA_DIR, capture_output=True)
        if not influxdb_was_running:
            subprocess.run(["docker", "compose", "stop", "influxdb"], cwd=INFRA_DIR, capture_output=True)
            subprocess.run(["docker", "compose", "rm", "-f", "influxdb"], cwd=INFRA_DIR, capture_output=True)
