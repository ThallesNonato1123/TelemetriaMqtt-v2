import json
import logging
import time

from ingestion.transform import to_point

logger = logging.getLogger(__name__)


def make_on_message(writer, clock=time.time_ns):
    """
    Constroi o callback on_message do paho-mqtt. `writer` recebe um
    InfluxPoint por mensagem valida; `clock` retorna o horario de chegada
    em nanossegundos (injetavel pra testes -- por padrao, time.time_ns).

    Mensagens invalidas (JSON corrompido ou payload incompleto) sao
    descartadas e logadas, sem derrubar o restante do processo.
    """

    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload)
            point = to_point(payload, received_at_ns=clock())
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("mensagem descartada: %s", exc)
            return
        writer(point)

    return on_message
