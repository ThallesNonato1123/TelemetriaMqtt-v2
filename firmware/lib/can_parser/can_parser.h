#pragma once

#include <cstdint>

// Parser dos quadros CAN do PDM32 (CAN2, 500 kbps). Implementa a tabela
// "Plano de payloads" do SCOPE.md: qualquer mudança lá (IDs, DLC, layout dos
// bytes) precisa ser refletida aqui, e vice-versa.
//
// Sem dependência de Arduino/ESP-IDF de propósito: roda igual no PC (testes
// nativos com Unity) e no ESP32. A leitura do barramento em si (driver TWAI)
// fica em src/, só no alvo de hardware.

namespace can_parser {

// Um quadro CAN clássico, já tirado do driver.
struct CanFrame {
  uint32_t id;
  uint8_t dlc;
  bool extended;  // true = ID de 29 bits; o PDM usa só 11 bits
  uint8_t data[8];
};

// Últimos valores conhecidos dos 20 sinais. Os nomes são exatamente as chaves
// do JSON publicado no MQTT (mesmo contrato do mock_publisher), então o
// checkpoint 9 pode serializar direto daqui.
//
// Sem padding de propósito (18 floats + 2 uint16): os testes comparam duas
// instâncias byte a byte pra provar que um quadro inválido não altera nada.
struct Telemetry {
  // 0x100, 0x101 -- 20 Hz
  float rpm;
  float throttlePosition;
  float lambda;
  float map;
  // 0x110..0x114 -- 10 Hz
  float gpsSpeed;
  float shifterCurrent;
  float bicosD1Current;
  float bicosD2Current;
  float bobinasCurrent;
  float poTotCurrent;
  float poTotCrntAll;
  float partidaCurrent;
  float extBattery;
  // 0x120 -- 5 Hz
  float ventoinhaCurrent;
  float bombaCurrent;
  // 0x130, 0x131 -- 2 Hz
  float engineTemp;
  float airTemp;
  float brakeLightCurrent;
  // uint16, não float: valem sempre 0 ou 1 (Momentary/Toggle; ver SCOPE.md)
  uint16_t bombaInput;
  uint16_t giratoriaInput;
};

// Decodifica `frame` e atualiza só os campos do payload correspondente em
// `out`. Devolve true se o quadro foi reconhecido e decodificado.
//
// Devolve false, sem alterar `out`, quando o quadro:
//   - é estendido (29 bits) -- o PDM foi configurado com IDs de 11 bits;
//   - tem um ID fora da tabela;
//   - tem DLC menor que o do contrato (não há bytes suficientes pra ler).
// DLC maior que o do contrato é aceito e os bytes extras são ignorados.
bool parse_frame(const CanFrame &frame, Telemetry &out);

}  // namespace can_parser
