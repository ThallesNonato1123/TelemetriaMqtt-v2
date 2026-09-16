import pytest

from ingestion.transform import MEASUREMENT, NUMERIC_FIELDS, to_point

VALID_PAYLOAD = {
    "ts": 1234,
    "rpm": 4400.0, "throttlePosition": 50.0, "lambda": 1.0, "map": 60.0,
    "gpsSpeed": 90.0, "shifterCurrent": 2.5, "bicosD1Current": 6.0,
    "bicosD2Current": 6.0, "bobinasCurrent": 4.0, "poTotCurrent": 20.0,
    "poTotCrntAll": 30.0, "partidaCurrent": 40.0, "extBattery": 13.05,
    "ventoinhaCurrent": 5.0, "bombaCurrent": 3.0, "engineTemp": 90.0,
    "airTemp": 30.0, "brakeLightCurrent": 1.0, "bombaInput": 0,
    "giratoriaInput": 0,
}


def test_to_point_maps_all_20_numeric_fields():
    # Todo sinal declarado em NUMERIC_FIELDS precisa virar um campo do ponto
    # gravado no Influx -- nenhum sinal pode ser silenciosamente esquecido.
    point = to_point(VALID_PAYLOAD, received_at_ns=1_000_000_000)
    for name in NUMERIC_FIELDS:
        assert point.fields[name] == VALID_PAYLOAD[name]


def test_to_point_uses_measurement_name():
    point = to_point(VALID_PAYLOAD, received_at_ns=1_000_000_000)
    assert point.measurement == MEASUREMENT


def test_to_point_uses_received_at_as_time_not_device_ts():
    # O "ts" do payload e relativo ao boot do dispositivo (millis() no ESP32
    # real, tempo desde o start no mock) -- NAO e hora real, entao nao pode
    # virar o timestamp do banco. O timestamp do ponto tem que ser o horario
    # de chegada da mensagem no servico de ingestao (relogio da VPS).
    point = to_point(VALID_PAYLOAD, received_at_ns=9_999_999_999)
    assert point.time_ns == 9_999_999_999


def test_to_point_keeps_device_ts_as_a_reference_field():
    # O "ts" original nao vira o timestamp do banco, mas nao pode ser jogado
    # fora -- serve pra depurar latencia/jitter depois. Guardado com um nome
    # diferente (device_ts_ms) pra nao confundir com o timestamp real do ponto.
    point = to_point(VALID_PAYLOAD, received_at_ns=1_000_000_000)
    assert point.fields["device_ts_ms"] == 1234


def test_to_point_raises_on_missing_field():
    # Uma mensagem incompleta (ex: firmware com bug, ou corrupcao na rede)
    # tem que ser rejeitada explicitamente, nao gravada parcialmente no banco
    # como se fosse um dado valido.
    incomplete = dict(VALID_PAYLOAD)
    del incomplete["rpm"]

    with pytest.raises(ValueError, match="rpm"):
        to_point(incomplete, received_at_ns=1_000_000_000)
