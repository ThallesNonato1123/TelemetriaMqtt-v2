import json

from mock_publisher.signal_generator import snapshot

MQTT_TOPIC = "telemetria/esp32/data"


def publish_snapshot(client, t: float, dry_run: bool = False, sink=print) -> None:
    payload = json.dumps(snapshot(t))
    if dry_run:
        sink(payload)
    else:
        client.publish(MQTT_TOPIC, payload)
