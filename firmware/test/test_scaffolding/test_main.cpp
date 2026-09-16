#include <unity.h>

// Prova de que o harness de testes nativo (sem hardware) está funcionando.
// Passa a valer pra lógica de verdade a partir do checkpoint 8 (parser CAN).
void test_native_test_harness_runs(void) {
  TEST_ASSERT_EQUAL(4, 2 + 2);
}

int main(int argc, char **argv) {
  UNITY_BEGIN();
  RUN_TEST(test_native_test_harness_runs);
  return UNITY_END();
}
