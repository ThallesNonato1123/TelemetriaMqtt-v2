# Escopo — Telemetria Arduino/ESP32 + MQTT (v2)

Reformulação do sistema de telemetria do TCC (equipe FSAE, mesmo carro), reconstruído do zero a partir de `~/Desktop/TelemetriaMqtt-v2`. O repositório antigo (`~/Desktop/TelemetriaMqtt`) permanece intacto como referência histórica, não será reaproveitado como base de código.

## Objetivo

Capturar sinais do barramento CAN do carro (RPM, temperaturas, correntes de PDM, etc.), publicá-los via MQTT e disponibilizá-los em dois caminhos: visualização ao vivo (pit/box, baixa latência) e armazenamento histórico (análise pós-treino/corrida).

## Arquitetura

```
[Carro: PDM32 → CAN2, 500kbps, payloads 0x100-0x131 (ver tabela abaixo)]
          │
          ▼
   [ESP32 + SN65HVD230] ──WiFi/MQTT (TLS)──► [Mosquitto na VPS]
          ▲
          │ (em desenvolvimento, sem hardware: script mock no PC publica
          │  direto no broker, mesmo tópico/JSON que o ESP32 vai usar)
                                                     │
                                    ┌────────────────┴────────────────┐
                                    ▼                                 ▼
                     [Grafana Live + plugin MQTT]        [Script de ingestão própria]
                     painel "ao vivo", soft real-time              │
                     (centenas de ms, sem polling)                 ▼
                                                              [InfluxDB]
                                                                     │
                                                                     ▼
                                                     [Grafana: dashboards históricos]
```

Dois caminhos deliberadamente separados: o painel ao vivo não depende do InfluxDB (elimina o limite de refresh de ~5s do polling), e o caminho histórico fica isolado para análise pós-evento.

## Fonte dos dados: PDM (CAN Output)

O carro usa um **AIM PDM32** (Power Distribution Module) como origem dos quadros CAN. Conforme a seção 22 ("CAN Output configuration", p. 56) do [manual oficial do PDM32](https://www.aim-sportline.com/download/doc/eng/pdm32-pdm08/PDM32_user_guide_eng.pdf):

- O PDM transmite um stream CAN configurável, em **CAN1 e/ou CAN2** (duas saídas físicas independentes), montado como um ou mais **"payloads"** — cada payload é um quadro CAN configurado individualmente no software do PDM (Race Studio).
- Por payload, configura-se no Race Studio:
  - **ID CAN** (hex): endereçamento de 11 bits (normal) ou 29 bits (estendido)
  - **DLC**: de 1 a 8 bytes
  - **Byte order**: Little Endian (processadores Intel-compatíveis) ou Big Endian (Motorola)
  - **Frequência de amostragem**: 1, 2, 5, 10 ou 20 Hz — configurada por payload, não por canal individual
  - **Quais canais vão em quais bytes** do payload — definido manualmente na interface do Race Studio, não é um layout fixo de fábrica
- Após configurar os payloads, é preciso **"Save"** e depois **"Transmit"** no Race Studio para gravar a configuração no PDM32 físico.
- Pinout físico dos conectores CAN1/CAN2 está no Apêndice A do manual (só diagrama, sem texto extraível) — conferir fisicamente no chicote/PDM na hora da fiação com o transceiver SN65HVD230.

### Decisões confirmadas

- **Saída física**: CAN2 (confirmado — a equipe/carro não tem nada mais usando o CAN2 hoje, está livre pra essa telemetria).
- **Velocidade do barramento**: 500kbps (mesmo valor do projeto antigo, sem restrição herdada de outro dispositivo no CAN2).
- **Byte order**: Little Endian em todos os payloads (compatível nativo com o ESP32, sem conversão no firmware).

### Digital Inputs do PDM (bombaInput, giratoriaInput)

Conforme seções 6.2 e 11.4 do manual ("Digital Inputs"), um input digital do PDM sempre carrega um valor numérico pequeno:
- **Momentary**: ativo (1) só enquanto o botão/chave está fechado, inativo (0) quando solto.
- **Toggle**: alterna 0↔1 a cada acionamento.
- **Multistable**: cicla de 0 a N a cada acionamento (N configurável), depois volta a 0.

Confirmado com a equipe: `bombaInput` e `giratoriaInput` são Momentary/Toggle — valor sempre **0 ou 1**. Por isso são tratados como `uint16` no payload (não `float`), tanto no PDM quanto no parser do ESP32 — mais correto que usar float pra um valor que nunca é fracionário, e consistente com o que o firmware antigo já fazia.

### Plano de payloads (CAN2, a configurar no Race Studio)

20 sinais do projeto antigo, reagrupados por frequência de acordo com a velocidade de mudança de cada sinal (sinais de dinâmica rápida do motor em 20Hz, correntes de eventos rápidos + GPS em 10Hz, cargas de relé em 5Hz, térmico/estados em 2Hz). Utilização de barramento estimada: ~99 msgs/s no pior caso, <3% de um barramento a 500kbps — folga confortável para ajustar frequências depois se necessário.

| ID (hex) | Freq | DLC | Byte 0-3 | Byte 4-5 | Byte 6-7 |
|---|---|---|---|---|---|
| 0x100 | 20 Hz | 8 | rpm (float) | throttlePosition (float, byte 4-7) | |
| 0x101 | 20 Hz | 8 | lambda (float) | map (float, byte 4-7) | |
| 0x110 | 10 Hz | 8 | gpsSpeed (float) | shifterCurrent (float, byte 4-7) | |
| 0x111 | 10 Hz | 8 | bicosD1Current (float) | bicosD2Current (float, byte 4-7) | |
| 0x112 | 10 Hz | 8 | bobinasCurrent (float) | poTotCurrent (float, byte 4-7) | |
| 0x113 | 10 Hz | 8 | poTotCrntAll (float) | partidaCurrent (float, byte 4-7) | |
| 0x114 | 10 Hz | 4 | extBattery (float) | — | — |
| 0x120 | 5 Hz | 8 | ventoinhaCurrent (float) | bombaCurrent (float, byte 4-7) | |
| 0x130 | 2 Hz | 8 | engineTemp (float) | airTemp (float, byte 4-7) | |
| 0x131 | 2 Hz | 8 | brakeLightCurrent (float) | bombaInput (uint16) | giratoriaInput (uint16) |

Essa tabela é o contrato entre a configuração do Race Studio e o parser do firmware do ESP32 — qualquer mudança de um lado precisa ser refletida no outro.

**Pendência**: nenhuma decisão de protocolo em aberto. Falta apenas a configuração física no Race Studio (você) e a implementação do parser correspondente no firmware (próxima etapa).

## Hardware

- **ESP32 DevKit V1** (WROOM-32) — único microcontrolador, substitui a dupla Arduino Uno + MCP2515 + ESP32 do projeto antigo. TWAI (CAN controller) embutido.
- **Transceiver SN65HVD230** (3.3V, compatível nativamente com os GPIOs do ESP32, sem level shifter) — necessário porque o ESP32 não tem transceiver CAN embutido, só o controlador.

Referências de compra (Mercado Livre, entrega Brasil):
- ESP32 DevKit V1: https://www.mercadolivre.com.br/esp32-doit-devkit-com-esp32-wroom-32/p/MLB28251016
- SN65HVD230: https://produto.mercadolivre.com.br/MLB-2791779546-modulo-rede-can-bus-sn65hvd230-para-arduino-esp8266-esp32-_JM

## Firmware

- **Tooling**: PlatformIO (não Arduino IDE).
- **Credenciais**: `secrets.h` no `.gitignore` desde o primeiro commit, com `secrets.h.example` versionado como template. Nunca hardcoded em arquivo rastreado pelo git.
- **TLS**: certificado real (Let's Encrypt) no broker, sem `setInsecure()`.

## Simulador de desenvolvimento (mock, sem hardware)

Pra desenvolver e testar o pipeline de backend (broker → ingestão → InfluxDB → Grafana, incluindo o painel ao vivo) antes de ter o ESP32/transceiver em mãos ou acesso ao carro, um **script mock rodando no PC** finge ser o dispositivo real:

- Publica diretamente no broker MQTT (mesmo tópico e mesmo schema de JSON que o firmware do ESP32 vai usar em produção).
- Gera valores sintéticos para as 20 variáveis da tabela de payloads, respeitando as frequências definidas por sinal (20/10/5/2 Hz).
- Não envolve CAN bus físico, transceiver ou segundo microcontrolador — só testa a camada lógica (MQTT + backend), não a camada elétrica do CAN.
- Linguagem a definir (provavelmente a mesma do script de ingestão, pra reaproveitar o schema/tipos).

**Fora de escopo por enquanto**: validar a camada física do CAN (ESP32 + transceiver recebendo quadros CAN reais ou simulados via bus físico) fica pra quando tivermos o hardware e/ou acesso ao carro — não é bloqueio para começar o desenvolvimento do backend.

## Backend / Infra (VPS)

- **VPS**: começar em Oracle Cloud Free Tier (4 vCPU ARM / 24GB RAM, custo zero); plano B pago (Hetzner CX ou Contabo, ~$5-7/mês) se o free tier se mostrar instável ou a instância for reclamada por ociosidade.
- **Broker MQTT**: Mosquitto self-hosted na VPS, com TLS e credenciais/ACL por dispositivo (o ESP32 só publica no seu próprio tópico, sem acesso admin ao broker).
- **Ingestão histórica**: script próprio (Python ou Node.js, a definir), assina o broker e grava no InfluxDB — versionado junto com o resto do código, não Node-RED.
- **Armazenamento**: InfluxDB (mantido do projeto antigo).
- **Visualização**:
  - Ao vivo: Grafana + plugin `grafana-mqtt-datasource` (open source, sem custo) via Grafana Live, assinando o tópico MQTT diretamente.
  - Histórico: Grafana com datasource InfluxDB, dashboards de análise pós-evento.

## Segurança

- Nenhuma credencial em arquivo versionado (firmware ou infra).
- Credenciais MQTT únicas por dispositivo, com ACL restrita por tópico.
- TLS real (Let's Encrypt) no broker.
- **Pendência do projeto antigo**: repositório `TelemetriaMqtt` é público no GitHub e tem a senha do WiFi e credenciais do broker MQTT (HiveMQ Cloud) expostas em texto plano no histórico de commits. Recomendado trocar essas credenciais assim que possível, independente do novo projeto.

## Fora de escopo por enquanto

- Reaproveitamento de código do repositório antigo.
- Definição de qual linguagem exata para o script de ingestão (Python vs Node.js) — a decidir na etapa de implementação.
- Metodologia de desenvolvimento — definida em `CLAUDE.md` (checkpoints, TDD, forma de revisão), não neste documento.
