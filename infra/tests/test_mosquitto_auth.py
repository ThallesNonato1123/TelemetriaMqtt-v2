import threading

import paho.mqtt.client as mqtt

from conftest import TEST_USERS


def _attempt_connect(client: mqtt.Client, port: int, timeout: float = 5.0):
    # Diferente de _connect_and_wait (test_mosquitto_acl.py), aqui o objetivo
    # é justamente observar uma REJEIÇÃO -- então não levantamos erro se a
    # conexão falhar; só se on_connect nunca disparar (timeout de rede real,
    # o que indicaria um problema diferente do que estamos testando aqui).
    result = {}
    fired = threading.Event()

    def on_connect(c, userdata, flags, reason_code, properties):
        result["reason_code"] = reason_code
        fired.set()

    client.on_connect = on_connect
    client.connect(port=port, host="127.0.0.1")
    client.loop_start()
    if not fired.wait(timeout):
        raise TimeoutError("on_connect não disparou a tempo")
    client.loop_stop()
    return result["reason_code"]


def _client() -> mqtt.Client:
    return mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        protocol=mqtt.MQTTv5,
    )


def test_correct_credentials_are_accepted(mosquitto_broker):
    # Baseline positivo: garante que os testes de rejeição abaixo não
    # passariam trivialmente só porque toda conexão falha (ex: broker fora
    # do ar) -- prova que existe pelo menos um caminho de sucesso real.
    client = _client()
    client.username_pw_set("esp32_telemetria", TEST_USERS["esp32_telemetria"])

    reason_code = _attempt_connect(client, mosquitto_broker)

    assert reason_code.value == 0


def test_wrong_password_is_rejected(mosquitto_broker):
    # allow_anonymous false + password_file (mosquitto.conf) -- usuário
    # válido, senha errada, tem que ser recusado. Essa é a propriedade que
    # motivou o checkpoint inteiro (evitar repetir o vazamento do TCC
    # antigo) e não tinha nenhum teste cobrindo ela até agora.
    client = _client()
    client.username_pw_set("esp32_telemetria", "senha-errada-de-proposito")

    reason_code = _attempt_connect(client, mosquitto_broker)

    assert reason_code.value >= 128


def test_unknown_username_is_rejected(mosquitto_broker):
    client = _client()
    client.username_pw_set("usuario_que_nao_existe", "qualquer-coisa")

    reason_code = _attempt_connect(client, mosquitto_broker)

    assert reason_code.value >= 128


def test_anonymous_connection_is_rejected(mosquitto_broker):
    # Sem username_pw_set nenhum -- é o comportamento padrão do Mosquitto
    # (allow_anonymous true) que mosquitto.conf desativa explicitamente.
    client = _client()

    reason_code = _attempt_connect(client, mosquitto_broker)

    assert reason_code.value >= 128
