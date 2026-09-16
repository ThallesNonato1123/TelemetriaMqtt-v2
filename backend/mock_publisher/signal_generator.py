import math

# Espelha a tabela de payloads do SCOPE.md (seção "Fonte dos dados: PDM").
# freq_hz é a frequência de amostragem do sinal real (por payload CAN);
# period_s é só o período da oscilação sintética, não tem relação com o CAN.
SIGNAL_SPECS = {
    "rpm": {"freq_hz": 20, "kind": "analog", "range": (800.0, 8000.0), "period_s": 6.0},
    "throttlePosition": {"freq_hz": 20, "kind": "analog", "range": (0.0, 100.0), "period_s": 4.0},
    "lambda": {"freq_hz": 20, "kind": "analog", "range": (0.8, 1.2), "period_s": 5.0},
    "map": {"freq_hz": 20, "kind": "analog", "range": (20.0, 100.0), "period_s": 4.5},

    "gpsSpeed": {"freq_hz": 10, "kind": "analog", "range": (0.0, 180.0), "period_s": 20.0},
    "shifterCurrent": {"freq_hz": 10, "kind": "analog", "range": (0.0, 5.0), "period_s": 3.0},
    "bicosD1Current": {"freq_hz": 10, "kind": "analog", "range": (0.0, 12.0), "period_s": 5.0},
    "bicosD2Current": {"freq_hz": 10, "kind": "analog", "range": (0.0, 12.0), "period_s": 5.2},
    "bobinasCurrent": {"freq_hz": 10, "kind": "analog", "range": (0.0, 8.0), "period_s": 4.8},
    "poTotCurrent": {"freq_hz": 10, "kind": "analog", "range": (0.0, 40.0), "period_s": 6.0},
    "poTotCrntAll": {"freq_hz": 10, "kind": "analog", "range": (0.0, 60.0), "period_s": 6.5},
    "partidaCurrent": {"freq_hz": 10, "kind": "analog", "range": (0.0, 80.0), "period_s": 15.0},
    "extBattery": {"freq_hz": 10, "kind": "analog", "range": (11.5, 14.6), "period_s": 10.0},

    "ventoinhaCurrent": {"freq_hz": 5, "kind": "analog", "range": (0.0, 10.0), "period_s": 8.0},
    "bombaCurrent": {"freq_hz": 5, "kind": "analog", "range": (0.0, 6.0), "period_s": 8.0},

    "engineTemp": {"freq_hz": 2, "kind": "analog", "range": (70.0, 110.0), "period_s": 30.0},
    "airTemp": {"freq_hz": 2, "kind": "analog", "range": (15.0, 45.0), "period_s": 45.0},
    "brakeLightCurrent": {"freq_hz": 2, "kind": "analog", "range": (0.0, 2.0), "period_s": 3.0},
    "bombaInput": {"freq_hz": 2, "kind": "binary", "range": (0, 1), "period_s": 4.0},
    "giratoriaInput": {"freq_hz": 2, "kind": "binary", "range": (0, 1), "period_s": 6.0},
}


def _snap_to_interval(t: float, freq_hz: float) -> float:
    interval = 1.0 / freq_hz
    return math.floor(t / interval) * interval


def _sine_value(sampled_t: float, low: float, high: float, period_s: float) -> float:
    mid = (low + high) / 2
    amplitude = (high - low) / 2
    return mid + amplitude * math.sin(2 * math.pi * sampled_t / period_s)


def _square_value(sampled_t: float, period_s: float) -> int:
    return int(sampled_t // (period_s / 2)) % 2


def snapshot(t: float) -> dict:
    result = {"ts": int(round(t * 1000))}
    for name, spec in SIGNAL_SPECS.items():
        sampled_t = _snap_to_interval(t, spec["freq_hz"])
        if spec["kind"] == "binary":
            result[name] = _square_value(sampled_t, spec["period_s"])
        else:
            low, high = spec["range"]
            result[name] = round(_sine_value(sampled_t, low, high, spec["period_s"]), 2)
    return result
