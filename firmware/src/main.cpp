#include <Arduino.h>

#include "can_parser.h"
#include "can_twai.h"

// Checkpoint 8: lê o CAN, decodifica e imprime um resumo na serial.
// WiFi/MQTT/TLS entram no checkpoint 9 -- por enquanto a serial é só pra
// conferir na bancada que os quadros do PDM estão chegando e sendo entendidos.

static can_parser::Telemetry telemetry{};
static uint32_t frames_ok = 0;
static uint32_t frames_ignored = 0;
static uint32_t last_report_ms = 0;

void setup() {
  Serial.begin(115200);
  Serial.println("TelemetriaMqtt v2 - firmware");
  if (!can_twai::begin()) {
    Serial.println("TWAI: falha ao iniciar o driver CAN");
  }
}

void loop() {
  can_parser::CanFrame frame;
  while (can_twai::receive(frame)) {
    if (can_parser::parse_frame(frame, telemetry)) {
      frames_ok++;
    } else {
      frames_ignored++;
    }
  }

  const uint32_t now = millis();
  if (now - last_report_ms >= 1000) {
    last_report_ms = now;
    Serial.printf("CAN ok=%lu ignorados=%lu | rpm=%.0f engineTemp=%.1f extBattery=%.2f\n",
                  static_cast<unsigned long>(frames_ok), static_cast<unsigned long>(frames_ignored),
                  telemetry.rpm, telemetry.engineTemp, telemetry.extBattery);
  }
}
