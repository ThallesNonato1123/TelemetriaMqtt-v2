import socket
import subprocess
import time
from pathlib import Path

INFRA_DIR = Path(__file__).parent.parent
PASSWD_PATH = INFRA_DIR / "mosquitto" / "config" / "passwd"
GENERATE_SCRIPT = INFRA_DIR / "mosquitto" / "generate_passwd.sh"

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


def _compose_service_is_running() -> bool:
    result = subprocess.run(
        ["docker", "compose", "ps", "-q", "mosquitto"],
        cwd=INFRA_DIR, capture_output=True, text=True,
    )
    return bool(result.stdout.strip())


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
