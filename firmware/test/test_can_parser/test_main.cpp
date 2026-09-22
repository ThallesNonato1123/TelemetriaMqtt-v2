#include <unity.h>

#include <cstdint>
#include <cstring>
#include <initializer_list>

#include "can_parser.h"

// Checkpoint 8: parser dos quadros CAN do PDM32. Os bytes esperados abaixo
// vêm da tabela "Plano de payloads" do SCOPE.md (IDs, DLC, layout, little
// endian) e foram calculados de forma independente do parser (struct.pack
// do Python), então os testes não repetem a lógica que verificam.

using namespace can_parser;

void setUp(void) {}
void tearDown(void) {}

static CanFrame make_frame(uint32_t id, uint8_t dlc, std::initializer_list<uint8_t> bytes,
                           bool extended = false) {
  CanFrame frame{};
  frame.id = id;
  frame.dlc = dlc;
  frame.extended = extended;
  uint8_t i = 0;
  for (uint8_t b : bytes) {
    frame.data[i++] = b;
  }
  return frame;
}

// Sem padding: dá pra comparar dois Telemetry byte a byte (memcmp) pra provar
// "não foi alterado".
static_assert(sizeof(Telemetry) == 18 * sizeof(float) + 2 * sizeof(uint16_t),
              "Telemetry não pode ter padding (os testes comparam com memcmp)");

static Telemetry sentinel_telemetry() {
  Telemetry t{};
  t.rpm = 42.0f;
  t.engineTemp = 42.0f;
  t.bombaInput = 42;
  return t;
}

static void assert_unchanged(const Telemetry &before, const Telemetry &after) {
  TEST_ASSERT_EQUAL_MEMORY(&before, &after, sizeof(Telemetry));
}

// ---------------------------------------------------------------- estado inicial

void test_telemetry_starts_zeroed(void) {
  Telemetry t{};
  Telemetry zero;
  std::memset(&zero, 0, sizeof(zero));
  assert_unchanged(zero, t);
}

// ---------------------------------------------------------------- um teste por payload

void test_0x100_decodes_rpm_and_throttle(void) {
  Telemetry t{};
  CanFrame f = make_frame(0x100, 8, {0x00, 0x50, 0x9A, 0x44, 0x00, 0x80, 0xAE, 0x42});
  TEST_ASSERT_TRUE(parse_frame(f, t));
  TEST_ASSERT_EQUAL_FLOAT(1234.5f, t.rpm);
  TEST_ASSERT_EQUAL_FLOAT(87.25f, t.throttlePosition);
}

void test_0x101_decodes_lambda_and_map(void) {
  Telemetry t{};
  CanFrame f = make_frame(0x101, 8, {0x00, 0x00, 0x7C, 0x3F, 0x00, 0x00, 0x36, 0x42});
  TEST_ASSERT_TRUE(parse_frame(f, t));
  TEST_ASSERT_EQUAL_FLOAT(0.984375f, t.lambda);
  TEST_ASSERT_EQUAL_FLOAT(45.5f, t.map);
}

void test_0x110_decodes_gps_speed_and_shifter_current(void) {
  Telemetry t{};
  CanFrame f = make_frame(0x110, 8, {0x00, 0x80, 0xE1, 0x42, 0x00, 0x00, 0x20, 0x40});
  TEST_ASSERT_TRUE(parse_frame(f, t));
  TEST_ASSERT_EQUAL_FLOAT(112.75f, t.gpsSpeed);
  TEST_ASSERT_EQUAL_FLOAT(2.5f, t.shifterCurrent);
}

void test_0x111_decodes_both_bicos_currents(void) {
  Telemetry t{};
  CanFrame f = make_frame(0x111, 8, {0x00, 0x00, 0xC4, 0x40, 0x00, 0x00, 0xBC, 0x40});
  TEST_ASSERT_TRUE(parse_frame(f, t));
  TEST_ASSERT_EQUAL_FLOAT(6.125f, t.bicosD1Current);
  TEST_ASSERT_EQUAL_FLOAT(5.875f, t.bicosD2Current);
}

void test_0x112_decodes_bobinas_and_po_tot_current(void) {
  Telemetry t{};
  CanFrame f = make_frame(0x112, 8, {0x00, 0x00, 0x90, 0x40, 0x00, 0x00, 0xAA, 0x41});
  TEST_ASSERT_TRUE(parse_frame(f, t));
  TEST_ASSERT_EQUAL_FLOAT(4.5f, t.bobinasCurrent);
  TEST_ASSERT_EQUAL_FLOAT(21.25f, t.poTotCurrent);
}

void test_0x113_decodes_po_tot_crnt_all_and_partida_current(void) {
  Telemetry t{};
  CanFrame f = make_frame(0x113, 8, {0x00, 0x00, 0x06, 0x42, 0x00, 0x00, 0x80, 0x42});
  TEST_ASSERT_TRUE(parse_frame(f, t));
  TEST_ASSERT_EQUAL_FLOAT(33.5f, t.poTotCrntAll);
  TEST_ASSERT_EQUAL_FLOAT(64.0f, t.partidaCurrent);
}

void test_0x114_decodes_ext_battery_from_a_4_byte_frame(void) {
  Telemetry t{};
  CanFrame f = make_frame(0x114, 4, {0x00, 0x00, 0x5C, 0x41});
  TEST_ASSERT_TRUE(parse_frame(f, t));
  TEST_ASSERT_EQUAL_FLOAT(13.75f, t.extBattery);
}

void test_0x120_decodes_ventoinha_and_bomba_current(void) {
  Telemetry t{};
  CanFrame f = make_frame(0x120, 8, {0x00, 0x00, 0xF0, 0x40, 0x00, 0x00, 0x50, 0x40});
  TEST_ASSERT_TRUE(parse_frame(f, t));
  TEST_ASSERT_EQUAL_FLOAT(7.5f, t.ventoinhaCurrent);
  TEST_ASSERT_EQUAL_FLOAT(3.25f, t.bombaCurrent);
}

void test_0x130_decodes_engine_and_air_temp_including_negative(void) {
  Telemetry t{};
  CanFrame f = make_frame(0x130, 8, {0x00, 0x00, 0xBF, 0x42, 0x00, 0x00, 0x44, 0xC1});
  TEST_ASSERT_TRUE(parse_frame(f, t));
  TEST_ASSERT_EQUAL_FLOAT(95.5f, t.engineTemp);
  TEST_ASSERT_EQUAL_FLOAT(-12.25f, t.airTemp);
}

void test_0x131_decodes_brake_light_current_and_two_uint16_inputs(void) {
  Telemetry t{};
  // brakeLightCurrent (float, bytes 0-3) + bombaInput (uint16, bytes 4-5) +
  // giratoriaInput (uint16, bytes 6-7). Os inputs são uint16, não float.
  CanFrame f = make_frame(0x131, 8, {0x00, 0x00, 0xC0, 0x3F, 0x01, 0x00, 0x00, 0x00});
  TEST_ASSERT_TRUE(parse_frame(f, t));
  TEST_ASSERT_EQUAL_FLOAT(1.5f, t.brakeLightCurrent);
  TEST_ASSERT_EQUAL_UINT16(1, t.bombaInput);
  TEST_ASSERT_EQUAL_UINT16(0, t.giratoriaInput);
}

void test_uint16_inputs_are_little_endian(void) {
  Telemetry t{};
  // 0x0100 = 256 em little endian (byte baixo primeiro); 0xABCD = CD AB. Os
  // inputs reais só valem 0/1, mas esse caso prova a ordem dos bytes, que um
  // 0/1 sozinho não distingue.
  CanFrame f = make_frame(0x131, 8, {0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0xCD, 0xAB});
  TEST_ASSERT_TRUE(parse_frame(f, t));
  TEST_ASSERT_EQUAL_UINT16(256, t.bombaInput);
  TEST_ASSERT_EQUAL_UINT16(0xABCD, t.giratoriaInput);
}

// ---------------------------------------------------------------- composição

void test_a_frame_only_updates_its_own_fields(void) {
  Telemetry t{};
  t.lambda = 1.0f;
  t.airTemp = 20.0f;
  CanFrame f = make_frame(0x100, 8, {0x00, 0x50, 0x9A, 0x44, 0x00, 0x80, 0xAE, 0x42});
  TEST_ASSERT_TRUE(parse_frame(f, t));
  TEST_ASSERT_EQUAL_FLOAT(1.0f, t.lambda);
  TEST_ASSERT_EQUAL_FLOAT(20.0f, t.airTemp);
}

void test_all_ten_payloads_together_fill_all_twenty_signals(void) {
  Telemetry t{};
  const CanFrame frames[] = {
      make_frame(0x100, 8, {0x00, 0x50, 0x9A, 0x44, 0x00, 0x80, 0xAE, 0x42}),
      make_frame(0x101, 8, {0x00, 0x00, 0x7C, 0x3F, 0x00, 0x00, 0x36, 0x42}),
      make_frame(0x110, 8, {0x00, 0x80, 0xE1, 0x42, 0x00, 0x00, 0x20, 0x40}),
      make_frame(0x111, 8, {0x00, 0x00, 0xC4, 0x40, 0x00, 0x00, 0xBC, 0x40}),
      make_frame(0x112, 8, {0x00, 0x00, 0x90, 0x40, 0x00, 0x00, 0xAA, 0x41}),
      make_frame(0x113, 8, {0x00, 0x00, 0x06, 0x42, 0x00, 0x00, 0x80, 0x42}),
      make_frame(0x114, 4, {0x00, 0x00, 0x5C, 0x41}),
      make_frame(0x120, 8, {0x00, 0x00, 0xF0, 0x40, 0x00, 0x00, 0x50, 0x40}),
      make_frame(0x130, 8, {0x00, 0x00, 0xBF, 0x42, 0x00, 0x00, 0x44, 0xC1}),
      make_frame(0x131, 8, {0x00, 0x00, 0xC0, 0x3F, 0x01, 0x00, 0x01, 0x00}),
  };
  for (const CanFrame &f : frames) {
    TEST_ASSERT_TRUE(parse_frame(f, t));
  }
  TEST_ASSERT_EQUAL_FLOAT(1234.5f, t.rpm);
  TEST_ASSERT_EQUAL_FLOAT(87.25f, t.throttlePosition);
  TEST_ASSERT_EQUAL_FLOAT(0.984375f, t.lambda);
  TEST_ASSERT_EQUAL_FLOAT(45.5f, t.map);
  TEST_ASSERT_EQUAL_FLOAT(112.75f, t.gpsSpeed);
  TEST_ASSERT_EQUAL_FLOAT(2.5f, t.shifterCurrent);
  TEST_ASSERT_EQUAL_FLOAT(6.125f, t.bicosD1Current);
  TEST_ASSERT_EQUAL_FLOAT(5.875f, t.bicosD2Current);
  TEST_ASSERT_EQUAL_FLOAT(4.5f, t.bobinasCurrent);
  TEST_ASSERT_EQUAL_FLOAT(21.25f, t.poTotCurrent);
  TEST_ASSERT_EQUAL_FLOAT(33.5f, t.poTotCrntAll);
  TEST_ASSERT_EQUAL_FLOAT(64.0f, t.partidaCurrent);
  TEST_ASSERT_EQUAL_FLOAT(13.75f, t.extBattery);
  TEST_ASSERT_EQUAL_FLOAT(7.5f, t.ventoinhaCurrent);
  TEST_ASSERT_EQUAL_FLOAT(3.25f, t.bombaCurrent);
  TEST_ASSERT_EQUAL_FLOAT(95.5f, t.engineTemp);
  TEST_ASSERT_EQUAL_FLOAT(-12.25f, t.airTemp);
  TEST_ASSERT_EQUAL_FLOAT(1.5f, t.brakeLightCurrent);
  TEST_ASSERT_EQUAL_UINT16(1, t.bombaInput);
  TEST_ASSERT_EQUAL_UINT16(1, t.giratoriaInput);
}

void test_a_later_frame_overwrites_the_previous_value(void) {
  Telemetry t{};
  CanFrame first = make_frame(0x100, 8, {0x00, 0x50, 0x9A, 0x44, 0x00, 0x00, 0x00, 0x00});
  CanFrame second = make_frame(0x100, 8, {0x00, 0x00, 0x80, 0x42, 0x00, 0x00, 0x00, 0x00});  // rpm=64.0
  TEST_ASSERT_TRUE(parse_frame(first, t));
  TEST_ASSERT_TRUE(parse_frame(second, t));
  TEST_ASSERT_EQUAL_FLOAT(64.0f, t.rpm);
}

// ---------------------------------------------------------------- entradas inválidas

void test_unknown_id_is_rejected_and_leaves_telemetry_untouched(void) {
  const uint32_t unknown_ids[] = {0x000, 0x0FF, 0x102, 0x115, 0x121, 0x132, 0x200, 0x7FF};
  for (uint32_t id : unknown_ids) {
    Telemetry t = sentinel_telemetry();
    const Telemetry before = t;
    CanFrame f = make_frame(id, 8, {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF});
    TEST_ASSERT_FALSE_MESSAGE(parse_frame(f, t), "ID fora da tabela deveria ser rejeitado");
    assert_unchanged(before, t);
  }
}

void test_frame_shorter_than_the_contract_dlc_is_rejected_and_untouched(void) {
  struct Case {
    uint32_t id;
    uint8_t required_dlc;
  };
  const Case cases[] = {{0x100, 8}, {0x101, 8}, {0x110, 8}, {0x111, 8}, {0x112, 8},
                        {0x113, 8}, {0x114, 4}, {0x120, 8}, {0x130, 8}, {0x131, 8}};
  for (const Case &c : cases) {
    Telemetry t = sentinel_telemetry();
    const Telemetry before = t;
    CanFrame f = make_frame(c.id, static_cast<uint8_t>(c.required_dlc - 1),
                            {0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88});
    TEST_ASSERT_FALSE_MESSAGE(parse_frame(f, t), "DLC menor que o contrato deveria ser rejeitado");
    assert_unchanged(before, t);
  }
}

void test_dlc_zero_is_rejected(void) {
  Telemetry t = sentinel_telemetry();
  const Telemetry before = t;
  TEST_ASSERT_FALSE(parse_frame(make_frame(0x100, 0, {}), t));
  assert_unchanged(before, t);
}

void test_dlc_larger_than_the_contract_is_accepted_and_extra_bytes_ignored(void) {
  // 0x114 tem DLC 4 no contrato. Se alguém configurar 8 no Race Studio, os
  // 4 bytes do float continuam no mesmo lugar: aceita e ignora o resto.
  Telemetry t{};
  CanFrame f = make_frame(0x114, 8, {0x00, 0x00, 0x5C, 0x41, 0xFF, 0xFF, 0xFF, 0xFF});
  TEST_ASSERT_TRUE(parse_frame(f, t));
  TEST_ASSERT_EQUAL_FLOAT(13.75f, t.extBattery);
}

void test_extended_29_bit_frame_with_a_known_id_is_rejected(void) {
  // O PDM foi configurado com IDs de 11 bits. Um quadro estendido com o
  // mesmo número (0x100) é outro endereço, de outro dispositivo.
  Telemetry t = sentinel_telemetry();
  const Telemetry before = t;
  CanFrame f = make_frame(0x100, 8, {0x00, 0x50, 0x9A, 0x44, 0x00, 0x80, 0xAE, 0x42}, /*extended=*/true);
  TEST_ASSERT_FALSE(parse_frame(f, t));
  assert_unchanged(before, t);
}

int main(int argc, char **argv) {
  UNITY_BEGIN();
  RUN_TEST(test_telemetry_starts_zeroed);
  RUN_TEST(test_0x100_decodes_rpm_and_throttle);
  RUN_TEST(test_0x101_decodes_lambda_and_map);
  RUN_TEST(test_0x110_decodes_gps_speed_and_shifter_current);
  RUN_TEST(test_0x111_decodes_both_bicos_currents);
  RUN_TEST(test_0x112_decodes_bobinas_and_po_tot_current);
  RUN_TEST(test_0x113_decodes_po_tot_crnt_all_and_partida_current);
  RUN_TEST(test_0x114_decodes_ext_battery_from_a_4_byte_frame);
  RUN_TEST(test_0x120_decodes_ventoinha_and_bomba_current);
  RUN_TEST(test_0x130_decodes_engine_and_air_temp_including_negative);
  RUN_TEST(test_0x131_decodes_brake_light_current_and_two_uint16_inputs);
  RUN_TEST(test_uint16_inputs_are_little_endian);
  RUN_TEST(test_a_frame_only_updates_its_own_fields);
  RUN_TEST(test_all_ten_payloads_together_fill_all_twenty_signals);
  RUN_TEST(test_a_later_frame_overwrites_the_previous_value);
  RUN_TEST(test_unknown_id_is_rejected_and_leaves_telemetry_untouched);
  RUN_TEST(test_frame_shorter_than_the_contract_dlc_is_rejected_and_untouched);
  RUN_TEST(test_dlc_zero_is_rejected);
  RUN_TEST(test_dlc_larger_than_the_contract_is_accepted_and_extra_bytes_ignored);
  RUN_TEST(test_extended_29_bit_frame_with_a_known_id_is_rejected);
  return UNITY_END();
}
