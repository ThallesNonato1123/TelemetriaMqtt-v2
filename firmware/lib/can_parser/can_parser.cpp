#include "can_parser.h"

#include <cstring>

namespace can_parser {

namespace {

// Little endian em todos os payloads (SCOPE.md). Os bytes são montados na mão
// em vez de fazer um cast do ponteiro: fica correto em qualquer endianness do
// processador e sem problema de alinhamento.
uint16_t read_u16_le(const uint8_t *p) {
  return static_cast<uint16_t>(p[0] | (p[1] << 8));
}

float read_f32_le(const uint8_t *p) {
  const uint32_t bits = static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) |
                        (static_cast<uint32_t>(p[2]) << 16) | (static_cast<uint32_t>(p[3]) << 24);
  float value;
  std::memcpy(&value, &bits, sizeof(value));
  return value;
}

// DLC mínimo de cada payload (coluna "DLC" da tabela do SCOPE.md); 0 = ID
// que não está na tabela.
uint8_t required_dlc(uint32_t id) {
  switch (id) {
    case 0x100:
    case 0x101:
    case 0x110:
    case 0x111:
    case 0x112:
    case 0x113:
    case 0x120:
    case 0x130:
    case 0x131:
      return 8;
    case 0x114:
      return 4;
    default:
      return 0;
  }
}

}  // namespace

bool parse_frame(const CanFrame &frame, Telemetry &out) {
  if (frame.extended) {
    return false;
  }
  const uint8_t needed = required_dlc(frame.id);
  if (needed == 0 || frame.dlc < needed) {
    return false;
  }

  // Daqui pra baixo o quadro já foi validado por inteiro: nenhum ramo devolve
  // false depois de escrever em `out`.
  const uint8_t *d = frame.data;
  switch (frame.id) {
    case 0x100:
      out.rpm = read_f32_le(d);
      out.throttlePosition = read_f32_le(d + 4);
      break;
    case 0x101:
      out.lambda = read_f32_le(d);
      out.map = read_f32_le(d + 4);
      break;
    case 0x110:
      out.gpsSpeed = read_f32_le(d);
      out.shifterCurrent = read_f32_le(d + 4);
      break;
    case 0x111:
      out.bicosD1Current = read_f32_le(d);
      out.bicosD2Current = read_f32_le(d + 4);
      break;
    case 0x112:
      out.bobinasCurrent = read_f32_le(d);
      out.poTotCurrent = read_f32_le(d + 4);
      break;
    case 0x113:
      out.poTotCrntAll = read_f32_le(d);
      out.partidaCurrent = read_f32_le(d + 4);
      break;
    case 0x114:
      out.extBattery = read_f32_le(d);
      break;
    case 0x120:
      out.ventoinhaCurrent = read_f32_le(d);
      out.bombaCurrent = read_f32_le(d + 4);
      break;
    case 0x130:
      out.engineTemp = read_f32_le(d);
      out.airTemp = read_f32_le(d + 4);
      break;
    case 0x131:
      out.brakeLightCurrent = read_f32_le(d);
      out.bombaInput = read_u16_le(d + 4);
      out.giratoriaInput = read_u16_le(d + 6);
      break;
  }
  return true;
}

}  // namespace can_parser
