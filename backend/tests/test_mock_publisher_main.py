from unittest.mock import MagicMock, patch

from mock_publisher.__main__ import build_client, parse_args


def test_parse_args_defaults():
    args = parse_args([])
    assert args.dry_run is False
    assert args.host == "localhost"
    assert args.port == 8883
    assert args.no_tls is False
    assert args.duration is None


def test_parse_args_no_tls_flag():
    args = parse_args(["--no-tls"])
    assert args.no_tls is True


def test_build_client_returns_none_in_dry_run():
    # Modo --dry-run não pode abrir nenhuma conexão de rede.
    args = parse_args(["--dry-run"])
    assert build_client(args) is None


@patch("mock_publisher.__main__.mqtt.Client")
def test_build_client_enables_tls_by_default(mock_client_cls):
    # Teste de regressão: no checkpoint 3, esse era o comportamento (TLS
    # sempre ligado) que quebrava contra o broker de dev sem TLS. O bug em
    # si já foi corrigido (via --no-tls); este teste existe pra garantir
    # que o comportamento padrão -- TLS ligado quando --no-tls não é
    # passado -- nunca regride silenciosamente.
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    args = parse_args(["--host", "broker.exemplo.com"])

    build_client(args)

    mock_client.tls_set.assert_called_once()


@patch("mock_publisher.__main__.mqtt.Client")
def test_build_client_skips_tls_with_no_tls_flag(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    args = parse_args(["--no-tls"])

    build_client(args)

    mock_client.tls_set.assert_not_called()


@patch("mock_publisher.__main__.mqtt.Client")
def test_build_client_sets_credentials_when_username_given(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    args = parse_args(["--no-tls", "--username", "esp32_telemetria", "--password", "abc123"])

    build_client(args)

    mock_client.username_pw_set.assert_called_once_with("esp32_telemetria", "abc123")


@patch("mock_publisher.__main__.mqtt.Client")
def test_build_client_skips_credentials_when_no_username(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    args = parse_args(["--no-tls"])

    build_client(args)

    mock_client.username_pw_set.assert_not_called()


@patch("mock_publisher.__main__.mqtt.Client")
def test_build_client_connects_to_configured_host_and_port(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    args = parse_args(["--no-tls", "--host", "192.168.1.50", "--port", "1883"])

    build_client(args)

    mock_client.connect.assert_called_once_with("192.168.1.50", 1883)
    mock_client.loop_start.assert_called_once()
