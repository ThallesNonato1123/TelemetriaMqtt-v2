import threading
import time

import paho.mqtt.client as mqtt

from conftest import TEST_USERS
from ingestion.ingest import make_on_message
from mock_publisher.publisher import MQTT_TOPIC, publish_snapshot

# Automatiza a validação manual que foi refeita à mão pelo menos 3 vezes
# durante os checkpoints 3 e 4 (mock publisher -> broker real -> ingestão):
# sobe o Mosquitto efêmero real (mesma fixture usada nos testes de ACL),
# publica de verdade usando o código de produção do mock_publisher, e
# confirma que o make_on_message de produção da ingestão recebe e
# transforma a mensagem corretamente -- sem reimplementar nenhum dos dois
# lados, só trocando o writer final por uma lista (o InfluxDB real só
# existe a partir do checkpoint 5).


def _client(username: str) -> mqtt.Client:
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        protocol=mqtt.MQTTv5,
    )
    client.username_pw_set(username, TEST_USERS[username])
    return client


def _connect_and_wait(client: mqtt.Client, port: int, timeout: float = 5.0) -> None:
    connected = threading.Event()
    client.on_connect = lambda c, u, flags, rc, props: connected.set()
    client.connect(port=port, host="127.0.0.1")
    client.loop_start()
    if not connected.wait(timeout):
        raise TimeoutError("client não conectou a tempo")


def test_mock_publisher_message_reaches_ingestion_correctly_transformed(mosquitto_broker):
    port = mosquitto_broker
    received_points = []

    subscriber = _client("telemetria_reader")
    subscriber.on_message = make_on_message(writer=received_points.append)
    _connect_and_wait(subscriber, port)
    subscriber.subscribe(MQTT_TOPIC, qos=1)
    time.sleep(0.3)

    publisher = _client("esp32_telemetria")
    _connect_and_wait(publisher, port)
    # publish_snapshot não devolve o MQTTMessageInfo (ver publisher.py), só
    # dispara o publish -- por isso a espera abaixo, não um wait_for_publish.
    publish_snapshot(publisher, t=1.234, dry_run=False)

    time.sleep(1)
    publisher.loop_stop()
    publisher.disconnect()
    subscriber.loop_stop()
    subscriber.disconnect()

    assert len(received_points) == 1
    point = received_points[0]
    assert point.measurement == "telemetry"
    # device_ts_ms preserva o "ts" original do publisher (t=1.234s -> 1234ms);
    # time_ns é o horário de chegada real, tem que ser bem maior que isso.
    assert point.fields["device_ts_ms"] == 1234
    assert point.time_ns > 1_000_000_000_000_000_000
    assert 800.0 <= point.fields["rpm"] <= 8000.0
    assert point.fields["bombaInput"] in (0, 1)


def test_multiple_snapshots_all_reach_ingestion_in_order(mosquitto_broker):
    port = mosquitto_broker
    received_points = []

    subscriber = _client("telemetria_reader")
    subscriber.on_message = make_on_message(writer=received_points.append)
    _connect_and_wait(subscriber, port)
    subscriber.subscribe(MQTT_TOPIC, qos=1)
    time.sleep(0.3)

    publisher = _client("esp32_telemetria")
    _connect_and_wait(publisher, port)
    for t in (0.0, 0.05, 0.10):
        publish_snapshot(publisher, t=t, dry_run=False)
        time.sleep(0.05)

    time.sleep(1)
    publisher.loop_stop()
    publisher.disconnect()
    subscriber.loop_stop()
    subscriber.disconnect()

    assert len(received_points) == 3
    device_ts_values = [p.fields["device_ts_ms"] for p in received_points]
    assert device_ts_values == [0, 50, 100]
