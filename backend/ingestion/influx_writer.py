from influxdb_client import Point, WritePrecision

from ingestion.transform import InfluxPoint


def make_influx_writer(write_api, bucket: str, org: str):
    """
    Constroi a funcao "writer" que make_on_message (ingest.py) espera:
    recebe um InfluxPoint (nosso tipo interno, sem dependencia do SDK) e
    grava via write_api.write(...) do client oficial influxdb-client.
    """

    def write(point: InfluxPoint) -> None:
        influx_point = Point(point.measurement).time(point.time_ns, WritePrecision.NS)
        for name, value in point.fields.items():
            if value is not None:
                influx_point = influx_point.field(name, value)
        write_api.write(bucket=bucket, org=org, record=influx_point)

    return write
