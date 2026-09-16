#!/usr/bin/env python3
"""
Gera infra/grafana/dashboards/historico.json a partir de uma lista
declarativa de painéis -- mais fácil de manter e revisar do que editar o
JSON do dashboard à mão (schema do Grafana é grande e repetitivo).

Uso: python3 generate_dashboard.py > dashboards/historico.json
"""
import json

BUCKET = "telemetria"
MEASUREMENT = "telemetry"
DATASOURCE = {"type": "influxdb", "uid": "influxdb-main"}

# Espelha a tabela de payloads do SCOPE.md -- os mesmos 20 sinais do
# mock_publisher/firmware, agrupados por categoria pra não precisar de
# 20 painéis separados.
PANELS = [
    {"title": "RPM", "fields": ["rpm"], "unit": "none"},
    {"title": "Acelerador / Lambda / MAP", "fields": ["throttlePosition", "lambda", "map"], "unit": "none"},
    {"title": "Temperaturas (°C)", "fields": ["engineTemp", "airTemp"], "unit": "celsius"},
    {
        "title": "Correntes (A)",
        "fields": [
            "ventoinhaCurrent", "bombaCurrent", "bicosD1Current", "bicosD2Current",
            "bobinasCurrent", "partidaCurrent", "poTotCurrent", "poTotCrntAll",
            "brakeLightCurrent", "shifterCurrent",
        ],
        "unit": "amp",
    },
    {"title": "Velocidade GPS (km/h)", "fields": ["gpsSpeed"], "unit": "velocitykmh"},
    {"title": "Tensão da bateria (V)", "fields": ["extBattery"], "unit": "volt"},
    {"title": "Estados digitais", "fields": ["bombaInput", "giratoriaInput"], "unit": "none"},
]


def flux_query(fields: list[str]) -> str:
    field_filter = " or ".join(f'r._field == "{f}"' for f in fields)
    return (
        f'from(bucket: "{BUCKET}")\n'
        f"  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n"
        f'  |> filter(fn: (r) => r._measurement == "{MEASUREMENT}")\n'
        f"  |> filter(fn: (r) => {field_filter})"
    )


def make_panel(panel_id: int, x: int, y: int, spec: dict) -> dict:
    return {
        "id": panel_id,
        "gridPos": {"h": 8, "w": 12, "x": x, "y": y},
        "type": "timeseries",
        "title": spec["title"],
        "datasource": DATASOURCE,
        "fieldConfig": {"defaults": {"unit": spec["unit"]}, "overrides": []},
        "options": {
            "legend": {"displayMode": "list", "placement": "bottom"},
            "tooltip": {"mode": "multi"},
        },
        "targets": [
            {
                "datasource": DATASOURCE,
                "query": flux_query(spec["fields"]),
                "refId": "A",
            }
        ],
    }


def main() -> None:
    panels = []
    for i, spec in enumerate(PANELS):
        x = 12 * (i % 2)
        y = 8 * (i // 2)
        panels.append(make_panel(panel_id=i + 1, x=x, y=y, spec=spec))

    dashboard = {
        "uid": "telemetria-historico",
        "title": "Telemetria — Histórico",
        "timezone": "browser",
        "schemaVersion": 39,
        "version": 1,
        "refresh": "",
        "time": {"from": "now-1h", "to": "now"},
        "panels": panels,
    }
    print(json.dumps(dashboard, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
