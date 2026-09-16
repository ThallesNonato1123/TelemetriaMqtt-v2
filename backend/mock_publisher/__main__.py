import argparse
import time

import paho.mqtt.client as mqtt

from mock_publisher.publisher import MQTT_TOPIC, publish_snapshot

PUBLISH_HZ = 20


def main():
    parser = argparse.ArgumentParser(description="Mock ESP32 telemetry publisher")
    parser.add_argument("--dry-run", action="store_true", help="print JSON instead of publishing to MQTT")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8883)
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--duration", type=float, default=None, help="segundos rodando (padrão: para sempre)")
    args = parser.parse_args()

    client = None
    if not args.dry_run:
        client = mqtt.Client()
        if args.username:
            client.username_pw_set(args.username, args.password)
        client.tls_set()
        client.connect(args.host, args.port)
        client.loop_start()

    destination = "(dry-run)" if args.dry_run else f"-> {args.host}:{args.port}"
    print(f"Publicando no tópico '{MQTT_TOPIC}' a {PUBLISH_HZ}Hz {destination}")

    start = time.monotonic()
    tick = 1.0 / PUBLISH_HZ
    try:
        while True:
            t = time.monotonic() - start
            if args.duration is not None and t > args.duration:
                break
            publish_snapshot(client, t, dry_run=args.dry_run)
            time.sleep(tick)
    except KeyboardInterrupt:
        pass
    finally:
        if client:
            client.loop_stop()
            client.disconnect()


if __name__ == "__main__":
    main()
