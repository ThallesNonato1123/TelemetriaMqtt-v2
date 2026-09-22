#pragma once

#include "can_parser.h"

// Leitura do barramento CAN pelo controlador TWAI do ESP32 (via transceiver
// SN65HVD230). Só compila no alvo esp32dev -- depende do driver do ESP-IDF e
// não é testável sem hardware; a lógica que importa (decodificação) mora em
// lib/can_parser e é coberta pelos testes nativos.
namespace can_twai {

// Instala e inicia o driver a 500 kbps (velocidade do CAN2 do PDM, SCOPE.md).
// Devolve false se o driver não subir.
bool begin();

// Pega um quadro da fila de recepção, sem bloquear. Devolve false se não há
// nenhum quadro de dados pendente.
bool receive(can_parser::CanFrame &out);

}  // namespace can_twai
