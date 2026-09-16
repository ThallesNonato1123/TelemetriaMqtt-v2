import argparse
import logging

import paho.mqtt.client as mqtt

from ingestion.ingest import make_on_message

TOPIC = "telemetria/esp32/data"


def _dry_run_writer(point) -> None:
    print(f"[dry-run] {point.measurement} {point.fields} t={point.time_ns}")


def _make_real_influx_writer(args):
    # Import local: influxdb-client só é necessário quando de fato vamos
    # gravar num banco de verdade (checkpoint 5 valida isso contra uma
    # instância real). Em --dry-run, essa dependência nem precisa resolver.
    from influxdb_client import InfluxDBClient
    from influxdb_client.client.write_api import SYNCHRONOUS

    from ingestion.influx_writer import make_influx_writer

    client = InfluxDBClient(url=args.influx_url, token=args.influx_token, org=args.influx_org)
    write_api = client.write_api(write_options=SYNCHRONOUS)
    return make_influx_writer(write_api, bucket=args.influx_bucket, org=args.influx_org)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Serviço de ingestão MQTT -> InfluxDB")
    parser.add_argument("--dry-run", action="store_true", help="imprime em vez de gravar no InfluxDB")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8883)
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--no-tls", action="store_true", help="desliga TLS (broker de dev local não usa TLS)")
    parser.add_argument("--influx-url", default="http://localhost:8086")
    parser.add_argument("--influx-token")
    parser.add_argument("--influx-org", default="fsae")
    parser.add_argument("--influx-bucket", default="telemetria")
    return parser.parse_args(argv)


def build_writer(args):
    """
    Retorna o writer que grava (ou imprime, em --dry-run) cada InfluxPoint.
    Extraído do main() pra ser testável sem depender de um InfluxDB real.
    """
    if args.dry_run:
        return _dry_run_writer
    return _make_real_influx_writer(args)


def build_mqtt_client(args, on_message):
    """
    Constroi, autentica e conecta o client MQTT, já assinando o tópico de
    telemetria. Extraído do main() pra ser testável sem broker real -- os
    testes substituem mqtt.Client por um mock antes de chamar isso.
    """
    client = mqtt.Client()
    if args.username:
        client.username_pw_set(args.username, args.password)
    if not args.no_tls:
        client.tls_set()
    client.on_message = on_message
    client.connect(args.host, args.port)
    client.subscribe(TOPIC, qos=1)
    return client


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    args = parse_args()
    writer = build_writer(args)
    on_message = make_on_message(writer=writer)
    client = build_mqtt_client(args, on_message)

    destination = "(dry-run)" if args.dry_run else args.influx_url
    print(f"Assinando '{TOPIC}' em {args.host}:{args.port}, gravando em {destination}")

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        pass
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
