import shutil
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt
import pytest

SCRIPT = Path(__file__).parent.parent / "mosquitto" / "generate_passwd.sh"
CONFIG_SRC = Path(__file__).parent.parent / "mosquitto" / "config"


def _run_script(config_dir: Path, username: str, password: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), username],
        input=f"{password}\n",
        text=True,
        capture_output=True,
        env={"MOSQUITTO_CONFIG_DIR": str(config_dir), "PATH": "/usr/bin:/bin:/usr/local/bin"},
    )


@pytest.fixture
def tmp_config_dir():
    with tempfile.TemporaryDirectory(prefix="mosquitto-passwd-test-") as d:
        # tempfile cria o diretório como 0700 (só o dono acessa) -- quando
        # esse diretório é montado num container (teste de conectividade
        # real, abaixo), o usuário "mosquitto" de dentro do container não
        # consegue nem atravessar o diretório, e o Mosquitto morre na
        # subida. 0755 deixa qualquer usuário ler/atravessar, sem afetar
        # os testes que só leem o passwd pelo lado do host.
        Path(d).chmod(0o755)
        yield Path(d)


def test_creates_passwd_file_if_missing(tmp_config_dir):
    passwd_path = tmp_config_dir / "passwd"
    assert not passwd_path.exists()

    result = _run_script(tmp_config_dir, "esp32_telemetria", "senha123")

    assert result.returncode == 0, result.stderr
    assert passwd_path.exists()


def test_adds_entry_for_the_given_username(tmp_config_dir):
    _run_script(tmp_config_dir, "esp32_telemetria", "senha123")

    content = (tmp_config_dir / "passwd").read_text()
    assert content.startswith("esp32_telemetria:")


def test_adding_a_second_user_preserves_the_first(tmp_config_dir):
    # mosquitto_passwd sem -c faz append/update -- se isso quebrar (ex: -c
    # sendo usado por engano), o segundo usuário sobrescreveria o arquivo
    # inteiro e o primeiro desapareceria.
    _run_script(tmp_config_dir, "esp32_telemetria", "senha123")
    _run_script(tmp_config_dir, "telemetria_reader", "outrasenha")

    content = (tmp_config_dir / "passwd").read_text()
    usernames = {line.split(":")[0] for line in content.strip().splitlines()}
    assert usernames == {"esp32_telemetria", "telemetria_reader"}


def test_rerunning_for_the_same_user_updates_not_duplicates(tmp_config_dir):
    _run_script(tmp_config_dir, "esp32_telemetria", "senha-antiga")
    _run_script(tmp_config_dir, "esp32_telemetria", "senha-nova")

    content = (tmp_config_dir / "passwd").read_text()
    lines = [line for line in content.strip().splitlines() if line.startswith("esp32_telemetria:")]
    assert len(lines) == 1


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


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_generated_credentials_actually_authenticate_against_mosquitto(tmp_config_dir):
    # Confirmação de ponta a ponta: a senha gerada pelo script tem que ser
    # a mesma que um Mosquitto de verdade aceita -- não só "o arquivo tem
    # um formato parecido com certo". Gera a senha ANTES de subir o
    # container (o Mosquitto só lê o passwd na inicialização).
    shutil.copy(CONFIG_SRC / "mosquitto.conf", tmp_config_dir / "mosquitto.conf")
    shutil.copy(CONFIG_SRC / "acl.conf", tmp_config_dir / "acl.conf")
    _run_script(tmp_config_dir, "esp32_telemetria", "senha-gerada-pelo-script")

    port = _free_port()
    container_name = f"telemetria-mosquitto-genpasswd-test-{port}"
    subprocess.run(
        [
            "docker", "run", "-d", "--rm", "--name", container_name,
            "-p", f"{port}:1883",
            "-v", f"{tmp_config_dir}:/mosquitto/config:ro",
            "eclipse-mosquitto:2",
        ],
        check=True, capture_output=True,
    )
    try:
        _wait_for_port(port)

        client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
        client.username_pw_set("esp32_telemetria", "senha-gerada-pelo-script")
        fired = threading.Event()
        result = {}

        def on_connect(c, u, flags, reason_code, props):
            result["reason_code"] = reason_code
            fired.set()

        client.on_connect = on_connect
        client.connect(port=port, host="127.0.0.1")
        client.loop_start()
        assert fired.wait(5), "on_connect não disparou a tempo"
        client.loop_stop()

        assert result["reason_code"].value == 0
    finally:
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
