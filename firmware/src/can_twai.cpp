#include "can_twai.h"

#include <driver/twai.h>

#include <cstring>

namespace can_twai {

// PINOS: valores provisórios (os mesmos do exemplo oficial do ESP-IDF, fora
// dos pinos de boot/strapping). Confirmar contra a fiação real do
// SN65HVD230 quando o hardware chegar -- só estas duas linhas mudam.
constexpr gpio_num_t kTxPin = GPIO_NUM_21;  // -> pino D (TXD) do transceiver
constexpr gpio_num_t kRxPin = GPIO_NUM_22;  // <- pino R (RXD) do transceiver

bool begin() {
  // MODO NORMAL (e não LISTEN_ONLY) de propósito: o SCOPE.md registra que
  // nada mais usa o CAN2 do carro, então o ESP32 pode ser o único receptor.
  // Sem ninguém dando ACK, o PDM veria erro em todo quadro e ficaria
  // retransmitindo. No modo normal o controlador só dá ACK -- este firmware
  // nunca chama twai_transmit(), então não escreve nada no barramento.
  // A confirmar no carro/bancada quando houver hardware.
  twai_general_config_t general = TWAI_GENERAL_CONFIG_DEFAULT(kTxPin, kRxPin, TWAI_MODE_NORMAL);
  const twai_timing_config_t timing = TWAI_TIMING_CONFIG_500KBITS();
  // Aceita tudo: quem descarta o que não é da tabela é o parser.
  const twai_filter_config_t filter = TWAI_FILTER_CONFIG_ACCEPT_ALL();

  if (twai_driver_install(&general, &timing, &filter) != ESP_OK) {
    return false;
  }
  return twai_start() == ESP_OK;
}

bool receive(can_parser::CanFrame &out) {
  twai_message_t message;
  // Timeout 0: não bloqueia o loop() se a fila estiver vazia.
  while (twai_receive(&message, 0) == ESP_OK) {
    if (message.rtr) {
      continue;  // quadro de requisição remota: sem dados, não interessa
    }
    out.id = message.identifier;
    out.dlc = message.data_length_code;
    out.extended = message.extd;
    std::memcpy(out.data, message.data, sizeof(out.data));
    return true;
  }
  return false;
}

}  // namespace can_twai
