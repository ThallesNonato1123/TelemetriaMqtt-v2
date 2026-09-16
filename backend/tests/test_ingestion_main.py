from unittest.mock import MagicMock, patch

from ingestion.__main__ import build_mqtt_client, build_writer, parse_args


def test_parse_args_defaults():
    args = parse_args([])
    assert args.dry_run is False
    assert args.host == "localhost"
    assert args.port == 8883
    assert args.no_tls is False
    assert args.influx_url == "http://localhost:8086"
    assert args.influx_org == "fsae"
    assert args.influx_bucket == "telemetria"


def test_build_writer_returns_dry_run_writer_in_dry_run(capsys):
    args = parse_args(["--dry-run"])

    writer = build_writer(args)

    from ingestion.transform import InfluxPoint
    writer(InfluxPoint(measurement="telemetry", fields={"rpm": 1.0}, time_ns=1))
    captured = capsys.readouterr()
    assert "[dry-run]" in captured.out


@patch("influxdb_client.InfluxDBClient")
def test_build_writer_builds_real_influx_client_when_not_dry_run(mock_influx_cls):
    # influxdb-client só existe de verdade a partir do checkpoint 5 -- aqui
    # confirmamos só que a wiring (URL/org/bucket/token repassados pro SDK)
    # está correta, sem precisar de um InfluxDB rodando.
    mock_client = MagicMock()
    mock_influx_cls.return_value = mock_client
    args = parse_args([
        "--influx-url", "http://influx.exemplo.com:8086",
        "--influx-token", "tok123",
        "--influx-org", "fsae-equipe",
        "--influx-bucket", "telemetria-2026",
    ])

    build_writer(args)

    mock_influx_cls.assert_called_once_with(
        url="http://influx.exemplo.com:8086", token="tok123", org="fsae-equipe",
    )
    mock_client.write_api.assert_called_once()


@patch("ingestion.__main__.mqtt.Client")
def test_build_mqtt_client_enables_tls_by_default(mock_client_cls):
    # Teste de regressão, espelhando o mesmo bug já corrigido no
    # mock_publisher (checkpoint 3): TLS precisa ficar ligado por padrão.
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    args = parse_args(["--host", "broker.exemplo.com"])

    build_mqtt_client(args, on_message=lambda *a: None)

    mock_client.tls_set.assert_called_once()


@patch("ingestion.__main__.mqtt.Client")
def test_build_mqtt_client_skips_tls_with_no_tls_flag(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    args = parse_args(["--no-tls"])

    build_mqtt_client(args, on_message=lambda *a: None)

    mock_client.tls_set.assert_not_called()


@patch("ingestion.__main__.mqtt.Client")
def test_build_mqtt_client_sets_credentials_when_username_given(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    args = parse_args(["--no-tls", "--username", "telemetria_reader", "--password", "abc123"])

    build_mqtt_client(args, on_message=lambda *a: None)

    mock_client.username_pw_set.assert_called_once_with("telemetria_reader", "abc123")


@patch("ingestion.__main__.mqtt.Client")
def test_build_mqtt_client_subscribes_to_telemetry_topic(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    args = parse_args(["--no-tls"])

    build_mqtt_client(args, on_message=lambda *a: None)

    mock_client.subscribe.assert_called_once_with("telemetria/esp32/data", qos=1)


@patch("ingestion.__main__.mqtt.Client")
def test_build_mqtt_client_wires_on_message_callback(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    args = parse_args(["--no-tls"])
    sentinel_callback = lambda *a: None

    build_mqtt_client(args, on_message=sentinel_callback)

    assert mock_client.on_message is sentinel_callback
