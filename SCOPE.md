# Escopo — Telemetria Arduino/ESP32 + MQTT (v2)

Reformulação do sistema de telemetria do TCC (equipe FSAE, mesmo carro), reconstruído do zero a partir de `~/Desktop/TelemetriaMqtt-v2`. O repositório antigo (`~/Desktop/TelemetriaMqtt`) permanece intacto como referência histórica, não será reaproveitado como base de código.

## Objetivo

Capturar sinais do barramento CAN do carro (RPM, temperaturas, correntes de PDM, etc.), publicá-los via MQTT e disponibilizá-los em dois caminhos: visualização ao vivo (pit/box, baixa latência) e armazenamento histórico (análise pós-treino/corrida).

## Arquitetura

```
[Carro: PDM32 → CAN2, 500kbps, payloads 0x100-0x131 (ver tabela abaixo)]
          │
          ▼
   [ESP32 + SN65HVD230] ──WiFi/MQTT (TLS)──► [Traefik] ──► [Mosquitto]
          ▲                                     │         (containers Docker
          │ (em desenvolvimento, sem hardware:   │          na VPS, TLS via
          │  script mock no PC publica direto    │          Let's Encrypt +
          │  no broker, mesmo tópico/JSON que     │          DuckDNS)
          │  o ESP32 vai usar)                   │
                                                  │                 │
                                    ┌─────────────┴──────┬──────────┘
                                    ▼                    ▼
                     [Grafana Live + plugin MQTT]  [Script de ingestão própria]
                     painel "ao vivo", soft real-time              │
                     (centenas de ms, sem polling)                 ▼
                                                              [InfluxDB]
                                                                     │
                                                                     ▼
                                                     [Grafana: dashboards históricos]
```

Todos os serviços de backend (Traefik, Mosquitto, InfluxDB, Grafana, script de ingestão) rodam como containers Docker via `docker-compose`, tanto em desenvolvimento local (sem TLS, rede isolada) quanto na VPS (com TLS real via Traefik + Let's Encrypt).

Dois caminhos deliberadamente separados: o painel ao vivo não depende do InfluxDB (elimina o limite de refresh de ~5s do polling), e o caminho histórico fica isolado para análise pós-evento.

## Stack tecnológico

Todas as escolhas de tecnologia feitas até agora, num lugar só (ver `CLAUDE.md` para a regra de manter isso atualizado):

| Camada | Escolha |
|---|---|
| Firmware | PlatformIO — env `esp32dev` (Arduino framework, board ESP32 DevKit) pra produção; env `native` (Unity) pra testes unitários sem hardware |
| Scripts de backend | Python 3, `pytest` (testes), `paho-mqtt` (cliente MQTT) — decidido no checkpoint 2 (mock publisher), confirmado pro script de ingestão no checkpoint 4 |
| Broker MQTT | Mosquitto, self-hosted, TLS + ACL por dispositivo |
| Armazenamento | InfluxDB **2.x** (confirmado no checkpoint 5, container Docker) — client oficial `influxdb-client` (Python) no script de ingestão |
| Visualização | Grafana — datasource InfluxDB (caminho histórico) + plugin `grafana-mqtt-datasource` (open source) via Grafana Live (caminho ao vivo) |
| Infra / VPS | Oracle Cloud Free Tier (plano B: Hetzner CX ou Contabo) |
| Orquestração | Docker + docker-compose — todos os serviços de backend containerizados (Mosquitto, InfluxDB, Grafana, script de ingestão), tanto em dev local quanto na VPS |
| Reverse proxy / TLS | Traefik — gerencia Let's Encrypt automaticamente pra Mosquitto + Grafana na VPS. Sem TLS em dev local (rede Docker isolada, não exposta à internet) |
| Domínio | DuckDNS (gratuito) — necessário pro desafio ACME do Let's Encrypt |
| Hardware | ESP32 DevKit V1 (WROOM-32) + transceiver CAN SN65HVD230 |
| Controle de versão | git + GitHub, repositório **público**: https://github.com/ThallesNonato1123/TelemetriaMqtt-v2 |
| CI | GitHub Actions (`.github/workflows/ci.yml`) — roda as 3 suítes de teste (firmware nativo, backend, infra com Docker) a cada push/PR |
| Releases | Tag semântica por checkpoint fechado (`v0.1.0`, `v0.2.0`, ...) — ver seção "Small releases" abaixo |

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

Pra desenvolver e testar o pipeline de backend (broker → ingestão → InfluxDB → Grafana, incluindo o painel ao vivo) antes de ter o ESP32/transceiver em mãos ou acesso ao carro, um **script mock em Python rodando no PC** (`backend/mock_publisher/`) finge ser o dispositivo real:

- Publica no tópico MQTT **`telemetria/esp32/data`**, uma mensagem JSON combinada (todos os 20 sinais + `ts` em ms) por tick, a **20Hz** (a frequência mais rápida da tabela). Esse será o mesmo contrato do firmware do ESP32 em produção.
- Sinais de frequência mais lenta (10/5/2 Hz) repetem o último valor amostrado dentro da própria mensagem, em vez de interpolar — reproduz fielmente como o dado real vai se comportar (lógica em `signal_generator.py`, coberta por testes `pytest`).
- Não envolve CAN bus físico, transceiver ou segundo microcontrolador — só testa a camada lógica (MQTT + backend), não a camada elétrica do CAN.
- Rodar: `cd backend && source .venv/bin/activate && python -m mock_publisher --dry-run` (imprime no terminal) ou sem `--dry-run` + `--host/--port/--username/--password` uma vez que o broker (checkpoint 3) existir.

**Fora de escopo por enquanto**: validar a camada física do CAN (ESP32 + transceiver recebendo quadros CAN reais ou simulados via bus físico) fica pra quando tivermos o hardware e/ou acesso ao carro — não é bloqueio para começar o desenvolvimento do backend.

## Backend / Infra (VPS)

- **VPS**: começar em Oracle Cloud Free Tier (4 vCPU ARM / 24GB RAM, custo zero); plano B pago (Hetzner CX ou Contabo, ~$5-7/mês) se o free tier se mostrar instável ou a instância for reclamada por ociosidade.
- **Broker MQTT**: Mosquitto, container Docker, com credenciais/ACL por dispositivo (o ESP32 só publica no seu próprio tópico, sem acesso admin ao broker).
- **Ingestão histórica**: script próprio em Python (`backend/ingestion/`, checkpoint 4), assina o broker como `telemetria_reader` e grava no InfluxDB via `influxdb-client` — versionado junto com o resto do código, não Node-RED.
- **Armazenamento**: InfluxDB, container Docker.

### Script de ingestão (checkpoint 4)

- **Medição (measurement)**: `telemetry`, um ponto por mensagem MQTT recebida, com os 20 sinais como campos (fields).
- **Timestamp do ponto**: horário de **recebimento** da mensagem (relógio da própria VPS/container de ingestão), não o `ts` do payload — esse último é relativo ao boot do dispositivo (`millis()` no ESP32 real, tempo desde o início no mock), nunca hora real, então não serve como timestamp absoluto de série temporal. O `ts` original é preservado como campo de referência (`device_ts_ms`), útil pra depurar latência/jitter depois.
- **Mensagens inválidas** (JSON corrompido ou payload com campo faltando) são descartadas e logadas, sem derrubar o processo — nunca gravadas parcialmente no banco.
- **Rodar**: `cd backend && source .venv/bin/activate && python -m ingestion --dry-run` (imprime em vez de gravar) ou sem `--dry-run` + `--influx-url/--influx-token/--influx-org/--influx-bucket` contra o InfluxDB real (ver seção seguinte).
- **Visualização**:
  - Ao vivo: Grafana (container Docker) + plugin `grafana-mqtt-datasource` (open source, sem custo) via Grafana Live, assinando o tópico MQTT diretamente.
  - Histórico: Grafana com datasource InfluxDB, dashboards de análise pós-evento.

### InfluxDB (checkpoint 5)

- **Versão**: InfluxDB 2.x confirmado (container `influxdb:2` no `docker-compose.yml`, mesmo padrão do Mosquitto) — a suposição do checkpoint 4 (terminologia de "bucket" nos slides do TCC antigo) se confirmou na prática.
- **Setup inicial**: feito automaticamente pela própria imagem oficial na primeira subida (`DOCKER_INFLUXDB_INIT_MODE=setup`), lendo usuário/senha/org/bucket/token de variáveis de ambiente vindas de `infra/.env` (gitignored, nunca versionado — mesmo tratamento do `passwd` do Mosquitto). Template em `infra/.env.example`.
- **Organização**: `fsae`. **Bucket**: `telemetria`. **Retenção**: infinita (sem `DOCKER_INFLUXDB_INIT_RETENTION`) — decisão consciente, já que o objetivo declarado é comparar treinos e estudar tendências ao longo de uma temporada inteira, não só o evento mais recente.
- **Measurement**: `telemetry` (definido em `backend/ingestion/transform.py`, checkpoint 4) — um ponto por mensagem MQTT recebida, os 20 sinais como campos, `device_ts_ms` como campo de referência do timestamp original do dispositivo.
- **Validação real**: os testes do checkpoint 4 (`test_influx_writer.py`) usavam um `write_api` mockado, já que o banco não existia. Neste checkpoint, o mesmo código de produção (`make_influx_writer`) escreve e é lido de volta de um InfluxDB real (containers efêmeros nos testes automatizados, e o `docker-compose.yml` real na validação manual) — a suposição de design do checkpoint 4 está confirmada de ponta a ponta, não só no papel.

### Docker (decisão via grill-me, ver stack tecnológico acima)

- **Escopo**: todos os serviços de backend containerizados (Mosquitto, InfluxDB, Grafana, script de ingestão) — nenhum instalado nativamente no SO da VPS. Justificativa: reprodutibilidade entre dev local e VPS, todas as imagens oficiais suportam ARM64 (confirmado, sem bloqueio pra Oracle Cloud), e não há motivo técnico pra deixar parte nativo/parte container.
- **Ambiente local**: `docker-compose` roda a mesma stack no PC pra desenvolvimento/teste dos checkpoints 3, 5, 6 e 7 (Mosquitto, InfluxDB, Grafana) sem precisar tocar na VPS a cada mudança. Sem TLS localmente (rede Docker isolada, não exposta à internet) — só a VPS usa TLS real.
- **TLS/certificado na VPS**: **Traefik** como reverse proxy único na frente de Mosquitto e Grafana, renovando Let's Encrypt automaticamente pros dois (roteamento TCP pro MQTT, HTTP pro Grafana) — menos manutenção do que um certbot standalone com script de renovação próprio.
- **Domínio**: **DuckDNS** (gratuito) apontando pra VPS, necessário porque Let's Encrypt não funciona só com IP.

## Segurança

**Postura**: mínimo essencial, sem over-engineering — dado o uso (telemetria de carro de competição, não um sistema crítico com dados sensíveis de terceiros), não vamos investir em hardening além do básico abaixo.

- Nenhuma credencial em arquivo versionado (firmware ou infra) — `infra/mosquitto/config/passwd` é gitignored, gerado localmente via `infra/mosquitto/generate_passwd.sh` (usa o binário `mosquitto_passwd` dentro do container oficial, sem precisar instalar Mosquitto no host).
- **Usuários MQTT** (definidos em `infra/mosquitto/config/acl.conf`, checkpoint 3): `esp32_telemetria` (write-only em `telemetria/esp32/data` — usado pelo firmware real e pelo mock publisher) e `telemetria_reader` (read-only no mesmo tópico — usado pelo script de ingestão e pelo Grafana Live). Nenhum dos dois tem acesso admin ao broker.
- **Nota de comportamento do Mosquitto** (confirmada rodando testes de integração reais): a ACL de leitura é aplicada na hora de *entregar* a mensagem, não na hora do SUBACK — um cliente sem permissão de leitura consegue assinar um tópico sem erro, mas nunca recebe nada publicado nele. Isso é esperado, não um bug.
- TLS real (Let's Encrypt via Traefik) no broker e no Grafana — só na VPS; ambiente de desenvolvimento local roda sem TLS (rede Docker isolada, não exposta à internet).
- **Pendência do projeto antigo**: repositório `TelemetriaMqtt` é público no GitHub e tem a senha do WiFi e credenciais do broker MQTT (HiveMQ Cloud) expostas em texto plano no histórico de commits. Recomendado trocar essas credenciais assim que possível, independente do novo projeto.
- **Varredura pré-publicação**: antes de tornar este repositório público, foi feita uma busca em todo o histórico de commits por credenciais/segredos acidentalmente commitados. Encontradas apenas senhas de desenvolvimento descartáveis (usadas em exemplos de comando na documentação dos checkpoints 3 e 4) — sem risco real (broker só em `127.0.0.1`, nunca exposto), mas substituídas por um placeholder genérico por higiene antes do primeiro push.

## Small releases e CI

- **Repositório**: público no GitHub, https://github.com/ThallesNonato1123/TelemetriaMqtt-v2 (decisão explícita — diferente da hospedagem só local usada durante boa parte do desenvolvimento inicial).
- **Releases**: uma tag semântica por checkpoint fechado (`v0.1.0` = checkpoint 1, `v0.2.0` = checkpoint 2, etc.), apontando pro commit que fecha aquele checkpoint (incluindo eventuais correções/decisões diretamente ligadas a ele). Tags criadas retroativamente para os checkpoints 1-4 ao adotar esse esquema; daqui pra frente, uma tag nova a cada checkpoint fechado.
- **CI**: GitHub Actions (`.github/workflows/ci.yml`), 3 jobs paralelos (um por suíte de teste — firmware nativo, backend, infra com Docker), rodando a cada push e pull request. Os runners `ubuntu-latest` já vêm com Docker disponível, então os testes de ACL/autenticação do Mosquitto (que sobem containers efêmeros) rodam sem configuração extra.

## Fora de escopo por enquanto

- Reaproveitamento de código do repositório antigo.
- Confirmação final da linguagem do script de ingestão (Python é o padrão de fato após o checkpoint 2, mas só fecha de verdade no checkpoint 4).
- Metodologia de desenvolvimento — definida em `CLAUDE.md` (checkpoints, TDD, forma de revisão), não neste documento.
