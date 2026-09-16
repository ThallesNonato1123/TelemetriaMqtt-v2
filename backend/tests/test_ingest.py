import json

from ingestion.ingest import make_on_message

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


class _FakeMqttMessage:
    def __init__(self, payload_bytes: bytes):
        self.payload = payload_bytes


def test_on_message_parses_valid_payload_and_calls_writer():
    # on_message e o callback real que o paho-mqtt chama a cada mensagem --
    # testamos aqui sem precisar de um client MQTT nem de um broker de
    # verdade: só simulamos o objeto "msg" que o paho passaria.
    written = []
    on_message = make_on_message(writer=written.append, clock=lambda: 42)

    on_message(None, None, _FakeMqttMessage(json.dumps(VALID_PAYLOAD).encode()))

    assert len(written) == 1
    assert written[0].fields["rpm"] == 4400.0
    assert written[0].time_ns == 42


def test_on_message_ignores_invalid_json():
    # Uma mensagem corrompida/malformada não pode derrubar o serviço de
    # ingestão inteiro -- só essa mensagem é descartada, o writer nunca é
    # chamado para ela.
    written = []
    on_message = make_on_message(writer=written.append, clock=lambda: 42)

    on_message(None, None, _FakeMqttMessage(b"isso nao e json"))

    assert written == []


def test_on_message_ignores_payload_missing_fields():
    # Mesma lógica de test_to_point_raises_on_missing_field, mas checando
    # que o callback (a camada de integração) trata esse erro sem propagar
    # a exceção e sem escrever nada no banco.
    incomplete = dict(VALID_PAYLOAD)
    del incomplete["engineTemp"]
    written = []
    on_message = make_on_message(writer=written.append, clock=lambda: 42)

    on_message(None, None, _FakeMqttMessage(json.dumps(incomplete).encode()))

    assert written == []
