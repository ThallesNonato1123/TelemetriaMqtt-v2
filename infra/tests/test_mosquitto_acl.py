import threading
import time

import paho.mqtt.client as mqtt

from conftest import TEST_USERS

TOPIC = "telemetria/esp32/data"


def _make_client(username: str) -> mqtt.Client:
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        protocol=mqtt.MQTTv5,
    )
    client.username_pw_set(username, TEST_USERS[username])
    return client


def _connect_and_wait(client: mqtt.Client, port: int, timeout: float = 5.0) -> None:
    # client.connect() é assíncrono (só enfileira o CONNECT); publicar ou
    # assinar antes do CONNACK chegar derruba com "not currently connected".
    # Espera o on_connect real disparar em vez de confiar num sleep chutado.
    connected = threading.Event()
    client.on_connect = lambda c, u, flags, rc, props: connected.set()
    client.connect(port=port, host="127.0.0.1")
    client.loop_start()
    if not connected.wait(timeout):
        raise TimeoutError("client não conectou a tempo")


def test_esp32_user_can_publish_to_its_topic(mosquitto_broker):
    # esp32_telemetria tem "topic write" no acl.conf -> publicar tem que
    # ser aceito. No MQTTv5, reason codes < 128 são sucesso (0 = "Success",
    # mas o Mosquitto também pode devolver 0x10 "No matching subscribers"
    # quando não há ninguém inscrito no momento — ainda é sucesso do ponto
    # de vista da ACL, só não tem quem receber). >= 128 é que indica recusa
    # (ex: 135 "Not authorized").
    port = mosquitto_broker
    result = {}

    client = _make_client("esp32_telemetria")
    client.on_publish = lambda c, u, mid, rc, props: result.update(reason_code=rc)
    _connect_and_wait(client, port)
    info = client.publish(TOPIC, b'{"rpm": 1000}', qos=1)
    info.wait_for_publish(timeout=5)
    time.sleep(0.3)
    client.loop_stop()
    client.disconnect()

    assert result["reason_code"].value < 128


def test_esp32_user_subscribes_but_never_receives_without_read_access(mosquitto_broker):
    # esp32_telemetria só tem "write" no acl.conf, não "read". O Mosquitto
    # aceita o SUBACK mesmo assim (confirmado rodando o teste — ele não
    # rejeita a assinatura em si), mas a ACL de leitura é aplicada na hora
    # de ENTREGAR a mensagem: mesmo publicando no próprio tópico que
    # assinou, esse usuário nunca deve receber nada de volta.
    port = mosquitto_broker
    received = []

    subscriber = _make_client("esp32_telemetria")
    subscriber.on_message = lambda c, u, msg: received.append(msg.payload)
    _connect_and_wait(subscriber, port)
    subscriber.subscribe(TOPIC, qos=1)
    time.sleep(0.3)

    publisher = _make_client("esp32_telemetria")
    _connect_and_wait(publisher, port)
    info = publisher.publish(TOPIC, b'{"rpm": 1}', qos=1)
    info.wait_for_publish(timeout=5)

    time.sleep(1)
    subscriber.loop_stop()
    subscriber.disconnect()
    publisher.loop_stop()
    publisher.disconnect()

    assert received == []


def test_reader_can_subscribe_and_receive(mosquitto_broker):
    # telemetria_reader tem "topic read" -> deve receber o que o publisher
    # (esp32_telemetria) manda no tópico compartilhado.
    port = mosquitto_broker
    received = []

    reader = _make_client("telemetria_reader")
    reader.on_message = lambda c, u, msg: received.append(msg.payload)
    _connect_and_wait(reader, port)
    reader.subscribe(TOPIC, qos=1)
    time.sleep(0.3)

    publisher = _make_client("esp32_telemetria")
    _connect_and_wait(publisher, port)
    info = publisher.publish(TOPIC, b'{"rpm": 4200}', qos=1)
    info.wait_for_publish(timeout=5)

    time.sleep(1)
    publisher.loop_stop()
    publisher.disconnect()
    reader.loop_stop()
    reader.disconnect()

    assert received == [b'{"rpm": 4200}']


def test_reader_cannot_publish(mosquitto_broker):
    # telemetria_reader só tem "read" no acl.conf, não "write" -> publicar
    # deve ser negado. Reason code >= 128 (ex: 135 "Not authorized") no
    # PUBACK, diferente do >= 0x10 "No matching subscribers" que ainda é
    # sucesso (ver comentário em test_esp32_user_can_publish_to_its_topic).
    port = mosquitto_broker
    result = {}

    client = _make_client("telemetria_reader")
    client.on_publish = lambda c, u, mid, rc, props: result.update(reason_code=rc)
    _connect_and_wait(client, port)
    info = client.publish(TOPIC, b"x", qos=1)
    info.wait_for_publish(timeout=5)
    time.sleep(0.3)
    client.loop_stop()
    client.disconnect()

    assert result["reason_code"].value >= 128
