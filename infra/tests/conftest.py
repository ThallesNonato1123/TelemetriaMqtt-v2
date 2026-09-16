import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

CONFIG_SRC = Path(__file__).parent.parent / "mosquitto" / "config"
ENV_PATH = Path(__file__).parent.parent / ".env"

INFLUXDB_TEST_ORG = "test-org"
INFLUXDB_TEST_BUCKET = "test-bucket"
INFLUXDB_TEST_TOKEN = "test-token-not-a-real-secret"  # nosec: só usado em container efêmero de teste

# Usuários de TESTE, descartáveis — não são as credenciais reais de produção.
# Os nomes de usuário batem com os definidos em infra/mosquitto/config/acl.conf,
# porque o que queremos testar são as regras de ACL de verdade.
TEST_USERS = {
    "esp32_telemetria": "test-publisher-pw",
    "telemetria_reader": "test-reader-pw",
}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            try:
                s.connect(("127.0.0.1", port))
                return
            except OSError:
                time.sleep(0.2)
    raise TimeoutError(f"mosquitto não respondeu na porta {port} em {timeout}s")


@pytest.fixture(scope="module")
def mosquitto_broker():
    """
    Sobe um Mosquitto efêmero usando o mosquitto.conf/acl.conf REAIS do
    projeto (infra/mosquitto/config) — só o passwd é descartável (usuários
    de teste). Assim testamos as regras de ACL de produção de verdade, sem
    depender de segredos reais nem deixar sujeira no ambiente.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="mosquitto-test-"))
    config_dir = tmp_dir / "config"
    shutil.copytree(CONFIG_SRC, config_dir)

    passwd_path = config_dir / "passwd"
    passwd_path.touch()
    for username, password in TEST_USERS.items():
        subprocess.run(
            [
                "docker", "run", "--rm",
                "-v", f"{config_dir}:/mosquitto/config",
                "eclipse-mosquitto:2",
                "mosquitto_passwd", "-b", "/mosquitto/config/passwd",
                username, password,
            ],
            check=True, capture_output=True,
        )

    port = _free_port()
    container_name = f"telemetria-mosquitto-test-{port}"
    subprocess.run(
        [
            "docker", "run", "-d", "--rm", "--name", container_name,
            "-p", f"{port}:1883",
            "-v", f"{config_dir}:/mosquitto/config:ro",
            "eclipse-mosquitto:2",
        ],
        check=True, capture_output=True,
    )
    try:
        _wait_for_port(port)
        yield port
    finally:
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def ensure_env_file():
    """
    Garante que infra/.env existe antes de qualquer teste rodar -- o
    docker-compose.yml exige INFLUXDB_INIT_PASSWORD/ADMIN_TOKEN (checkpoint
    5) e GRAFANA_ADMIN_PASSWORD (checkpoint 6). Nunca sobrescreve um .env
    real que o dev já tenha configurado (mesma lógica de preservação usada
    pro passwd do Mosquitto em test_docker_compose.py).
    """
    if not ENV_PATH.exists():
        ENV_PATH.write_text(
            "INFLUXDB_INIT_USERNAME=admin\n"
            f"INFLUXDB_INIT_PASSWORD={secrets.token_urlsafe(16)}\n"
            "INFLUXDB_INIT_ORG=fsae\n"
            "INFLUXDB_INIT_BUCKET=telemetria\n"
            f"INFLUXDB_INIT_ADMIN_TOKEN={secrets.token_hex(32)}\n"
            "GRAFANA_ADMIN_USER=admin\n"
            f"GRAFANA_ADMIN_PASSWORD={secrets.token_urlsafe(16)}\n"
        )
    yield


def _wait_for_influxdb_health(port: int, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{port}/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.5)
    raise TimeoutError(f"influxdb não respondeu em {url} em {timeout}s")


@pytest.fixture(scope="module")
def influxdb_instance():
    """
    Sobe um InfluxDB 2.x efêmero real, com org/bucket/token de teste
    (descartáveis, não credenciais reais) -- valida de verdade a suposição
    de InfluxDB 2.x feita no checkpoint 4 (test_influx_writer.py usava um
    client mockado, já que o banco não existia ainda).
    """
    port = _free_port()
    container_name = f"telemetria-influxdb-test-{port}"
    subprocess.run(
        [
            "docker", "run", "-d", "--rm", "--name", container_name,
            "-p", f"{port}:8086",
            "-e", "DOCKER_INFLUXDB_INIT_MODE=setup",
            "-e", "DOCKER_INFLUXDB_INIT_USERNAME=test-admin",
            "-e", "DOCKER_INFLUXDB_INIT_PASSWORD=test-password-1234",
            "-e", f"DOCKER_INFLUXDB_INIT_ORG={INFLUXDB_TEST_ORG}",
            "-e", f"DOCKER_INFLUXDB_INIT_BUCKET={INFLUXDB_TEST_BUCKET}",
            "-e", f"DOCKER_INFLUXDB_INIT_ADMIN_TOKEN={INFLUXDB_TEST_TOKEN}",
            "influxdb:2",
        ],
        check=True, capture_output=True,
    )
    try:
        _wait_for_influxdb_health(port)
        yield {
            "url": f"http://127.0.0.1:{port}",
            "org": INFLUXDB_TEST_ORG,
            "bucket": INFLUXDB_TEST_BUCKET,
            "token": INFLUXDB_TEST_TOKEN,
        }
    finally:
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
