from dataclasses import dataclass
from typing import Any

MEASUREMENT = "telemetry"

# Espelha a tabela de payloads do SCOPE.md (mesmos 20 sinais do mock_publisher).
NUMERIC_FIELDS = [
    "rpm", "throttlePosition", "lambda", "map",
    "gpsSpeed", "shifterCurrent", "bicosD1Current", "bicosD2Current",
    "bobinasCurrent", "poTotCurrent", "poTotCrntAll", "partidaCurrent",
    "extBattery",
    "ventoinhaCurrent", "bombaCurrent",
    "engineTemp", "airTemp",
    "brakeLightCurrent", "bombaInput", "giratoriaInput",
]


@dataclass
class InfluxPoint:
    measurement: str
    fields: dict[str, Any]
    time_ns: int


def to_point(payload: dict, received_at_ns: int) -> InfluxPoint:
    missing = [name for name in NUMERIC_FIELDS if name not in payload]
    if missing:
        raise ValueError(f"payload sem os campos: {', '.join(missing)}")

    fields: dict[str, Any] = {name: payload[name] for name in NUMERIC_FIELDS}
    # "ts" do payload e relativo ao boot do dispositivo, nao e hora real --
    # guardado como campo de referencia, nao como o timestamp do ponto.
    fields["device_ts_ms"] = payload.get("ts")

    return InfluxPoint(measurement=MEASUREMENT, fields=fields, time_ns=received_at_ns)
