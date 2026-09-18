#!/usr/bin/env python3
"""
Gera infra/grafana/dashboards/ao-vivo.json -- o dashboard do caminho ao
vivo (Grafana Live + plugin grafana-mqtt-datasource), sem passar pelo
InfluxDB. Reaproveita os agrupamentos/unidades do dashboard histórico
(PANELS em generate_dashboard.py), então os dois ficam sempre iguais.

Uso: python3 generate_live_dashboard.py > dashboards/ao-vivo.json
"""
import json

from generate_dashboard import PANELS

MQTT_TOPIC = "telemetria/esp32/data"
DATASOURCE = {"type": "grafana-mqtt-datasource", "uid": "mqtt-live"}

# O plugin agrupa as mensagens recebidas num frame a cada "intervalo" e só
# então empurra pro navegador -- esse intervalo é o piso da latência. Vem do
# "Min interval" do painel. 200ms = 5 atualizações/s (o dispositivo publica
# a 20Hz, então ~4 amostras por frame): dentro do "centenas de ms" do
# SCOPE.md sem inundar o navegador. Um valor maior que isso só piora a
# latência; menor, só aumenta a carga.
LIVE_INTERVAL = "200ms"


def make_panel(panel_id: int, x: int, y: int, spec: dict) -> dict:
    return {
        "id": panel_id,
        "gridPos": {"h": 8, "w": 12, "x": x, "y": y},
        "type": "timeseries",
        "title": spec["title"],
        "datasource": DATASOURCE,
        "interval": LIVE_INTERVAL,
        "fieldConfig": {"defaults": {"unit": spec["unit"]}, "overrides": []},
        "options": {
            "legend": {"displayMode": "list", "placement": "bottom"},
            "tooltip": {"mode": "multi"},
        },
        # O plugin devolve UM frame com todos os campos do JSON (ts, rpm,
        # engineTemp, ...); cada painel fica só com os do seu grupo.
        "transformations": [
            {
                "id": "filterFieldsByName",
                "options": {"include": {"names": ["Time", *spec["fields"]]}},
            }
        ],
        "targets": [
            {
                "datasource": DATASOURCE,
                "refId": "A",
                "topic": MQTT_TOPIC,
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
        "uid": "telemetria-ao-vivo",
        "title": "Telemetria — Ao vivo",
        "timezone": "browser",
        "schemaVersion": 39,
        "version": 1,
        "refresh": "",
        # Janela rolante: os painéis mantêm só o último minuto em memória
        # (o plugin não guarda histórico -- pra isso é o dashboard histórico).
        "time": {"from": "now-1m", "to": "now"},
        "timepicker": {"hidden": True},
        "liveNow": True,
        "panels": panels,
    }
    print(json.dumps(dashboard, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
