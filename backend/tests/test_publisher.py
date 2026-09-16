import json
from unittest.mock import MagicMock

from mock_publisher.publisher import MQTT_TOPIC, publish_snapshot

# Usamos MagicMock no lugar de um client MQTT real (paho.mqtt.client.Client)
# de propósito: nesse checkpoint ainda não existe broker (isso é o checkpoint 3),
# então testamos só a nossa lógica de "como chamamos o client", sem depender de
# rede nem de infraestrutura externa pra rodar o teste.


def test_publish_snapshot_calls_client_publish_with_correct_topic():
    # Garante que publish_snapshot manda pro tópico certo (telemetria/esp32/data)
    # e chama client.publish exatamente uma vez por snapshot — não duas, não zero.
    client = MagicMock()
    publish_snapshot(client, t=0.0)
    assert client.publish.call_count == 1
    called_topic = client.publish.call_args[0][0]
    assert called_topic == MQTT_TOPIC


def test_publish_snapshot_payload_is_valid_json_with_expected_keys():
    # O payload publicado precisa ser uma string JSON válida (não um dict cru,
    # que o paho não aceita) e o "ts" precisa bater com o t passado (2.5s -> 2500ms).
    # Isso pega erros de serialização antes de irem pro broker de verdade.
    client = MagicMock()
    publish_snapshot(client, t=2.5)
    payload_str = client.publish.call_args[0][1]
    payload = json.loads(payload_str)
    assert "rpm" in payload
    assert "ts" in payload
    assert payload["ts"] == 2500


def test_publish_snapshot_dry_run_does_not_touch_client():
    # Modo dry-run (usado pra você rodar o script sem broker nenhum) tem que
    # desviar completamente do client MQTT — se ele chamasse client.publish
    # por engano, o script quebraria assim que alguém rodasse --dry-run sem
    # ter um broker configurado. "sink" é o destino alternativo (aqui, uma
    # lista; no CLI real, é a função print).
    client = MagicMock()
    output = []
    publish_snapshot(client, t=0.0, dry_run=True, sink=output.append)
    client.publish.assert_not_called()
    assert len(output) == 1
    payload = json.loads(output[0])
    assert "rpm" in payload
