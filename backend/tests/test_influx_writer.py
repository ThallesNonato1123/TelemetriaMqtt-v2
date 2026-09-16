from unittest.mock import MagicMock

from ingestion.influx_writer import make_influx_writer
from ingestion.transform import InfluxPoint

# Usamos MagicMock no lugar de um InfluxDBClient real de propósito: o
# InfluxDB só entra no ar no checkpoint 5 (ainda não existe infra pra
# testar contra um banco de verdade). Testamos aqui só a nossa lógica de
# "como construímos e enviamos o Point pro write_api do SDK oficial".


def test_writer_calls_write_api_with_correct_bucket_and_org():
    write_api = MagicMock()
    write = make_influx_writer(write_api, bucket="telemetria", org="fsae")

    write(InfluxPoint(measurement="telemetry", fields={"rpm": 4400.0}, time_ns=123))

    assert write_api.write.call_count == 1
    _, kwargs = write_api.write.call_args
    assert kwargs["bucket"] == "telemetria"
    assert kwargs["org"] == "fsae"


def test_writer_builds_point_with_measurement_fields_and_time():
    write_api = MagicMock()
    write = make_influx_writer(write_api, bucket="telemetria", org="fsae")

    write(InfluxPoint(
        measurement="telemetry",
        fields={"rpm": 4400.0, "bombaInput": 0},
        time_ns=123456789,
    ))

    _, kwargs = write_api.write.call_args
    line = kwargs["record"].to_line_protocol()
    assert line.startswith("telemetry ")
    assert "rpm=4400" in line
    assert "bombaInput=0i" in line  # inteiro -> sufixo "i" no line protocol
    assert line.endswith("123456789")


def test_writer_skips_none_fields():
    # device_ts_ms pode ser None se o payload nao tiver "ts" -- nao faz
    # sentido gravar um campo None no Influx (o SDK nem aceita).
    write_api = MagicMock()
    write = make_influx_writer(write_api, bucket="telemetria", org="fsae")

    write(InfluxPoint(
        measurement="telemetry",
        fields={"rpm": 4400.0, "device_ts_ms": None},
        time_ns=123,
    ))

    _, kwargs = write_api.write.call_args
    line = kwargs["record"].to_line_protocol()
    assert "device_ts_ms" not in line
