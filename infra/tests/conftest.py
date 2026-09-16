import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

CONFIG_SRC = Path(__file__).parent.parent / "mosquitto" / "config"

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
