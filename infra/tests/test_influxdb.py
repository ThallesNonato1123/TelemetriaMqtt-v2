from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS

from ingestion.influx_writer import make_influx_writer
from ingestion.transform import InfluxPoint

# Valida de verdade a suposição de InfluxDB 2.x feita no checkpoint 4:
# lá, test_influx_writer.py usava um write_api MOCKADO, porque o banco
# ainda não existia. Aqui, o mesmo make_influx_writer (código de
# produção) escreve num InfluxDB real, e consultamos de volta pra
# confirmar que o dado chega íntegro -- não só "o SDK foi chamado certo".


def _client(instance) -> InfluxDBClient:
    return InfluxDBClient(url=instance["url"], token=instance["token"], org=instance["org"])


def test_point_written_via_production_writer_is_queryable(influxdb_instance):
    with _client(influxdb_instance) as client:
        write_api = client.write_api(write_options=SYNCHRONOUS)
        writer = make_influx_writer(write_api, bucket=influxdb_instance["bucket"], org=influxdb_instance["org"])

        point = InfluxPoint(
            measurement="telemetry",
            fields={"rpm": 4200.0, "device_ts_ms": 777},
            time_ns=1_700_000_000_000_000_000,
        )
        writer(point)

        query_api = client.query_api()
        flux = f'''
        from(bucket: "{influxdb_instance["bucket"]}")
          |> range(start: 2023-01-01T00:00:00Z)
          |> filter(fn: (r) => r._measurement == "telemetry")
          |> filter(fn: (r) => r._field == "rpm")
        '''
        tables = query_api.query(flux, org=influxdb_instance["org"])

        values = [record.get_value() for table in tables for record in table.records]
        assert values == [4200.0]


def test_multiple_fields_of_same_point_are_all_queryable(influxdb_instance):
    with _client(influxdb_instance) as client:
        write_api = client.write_api(write_options=SYNCHRONOUS)
        writer = make_influx_writer(write_api, bucket=influxdb_instance["bucket"], org=influxdb_instance["org"])

        point = InfluxPoint(
            measurement="telemetry",
            fields={"engineTemp": 91.5, "airTemp": 28.3, "device_ts_ms": 888},
            time_ns=1_700_000_001_000_000_000,
        )
        writer(point)

        query_api = client.query_api()
        # Filtra pelos nomes de campo, que são exclusivos deste teste dentro
        # do bucket efêmero compartilhado (fixture module-scoped) -- mais
        # simples e robusto do que tentar acertar o RFC3339 exato
        # correspondente ao time_ns usado (esse foi o erro real encontrado
        # rodando o teste pela primeira vez: a data no filtro estava errada,
        # não o código de produção).
        flux = f'''
        from(bucket: "{influxdb_instance["bucket"]}")
          |> range(start: 2023-01-01T00:00:00Z)
          |> filter(fn: (r) => r._measurement == "telemetry")
          |> filter(fn: (r) => r._field == "engineTemp" or r._field == "airTemp")
        '''
        tables = query_api.query(flux, org=influxdb_instance["org"])

        by_field = {record.get_field(): record.get_value() for table in tables for record in table.records}
        assert by_field == {"engineTemp": 91.5, "airTemp": 28.3}
