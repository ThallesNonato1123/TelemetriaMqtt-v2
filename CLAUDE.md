# CLAUDE.md

Instruções de trabalho para este repositório. Ver `SCOPE.md` para as decisões técnicas (arquitetura, protocolo CAN, hardware, infra) — este arquivo é só sobre *como* trabalhamos, não *o quê*.

## Metodologia

- **TDD obrigatório**: para cada checkpoint, escrever os testes antes ou junto da implementação. Nenhum checkpoint é considerado fechado com testes falhando. Isso existe para manter cada etapa pequena e verificável, evitando que o código cresça sem controle.
- **Testes são intocáveis depois de escritos**: nunca apagar ou modificar um teste já existente para fazê-lo passar, nem para "simplificar". Se um teste está falhando, o problema é a implementação — conserte a implementação, não o teste. Se um requisito genuinamente mudou e um teste ficou obsoleto, pare e pergunte ao usuário antes de tocar nele; não decida isso sozinho. Adicionar novos testes é sempre permitido.
- **Toda decisão de tecnologia registrada no SCOPE.md**: qualquer escolha de linguagem, framework, biblioteca, serviço ou ferramenta feita durante um checkpoint (ex: PlatformIO, Python, pytest, Mosquitto) precisa ser adicionada à seção "Stack tecnológico" do `SCOPE.md` antes de considerar o checkpoint fechado — mesmo que pareça óbvia ou incidental no momento.
- **Quem escreve o código**: Claude escreve toda a implementação. O usuário revisa — não espere que ele escreva trechos de código.
- **Revisão por checkpoint**: parar ao final de cada checkpoint (ver lista abaixo) e aguardar aprovação explícita antes de seguir para o próximo. Não emendar múltiplos checkpoints em uma sequência sem parar.
- **Forma de revisão**: o usuário revisa tanto lendo o código/diff quanto rodando/testando na própria máquina. Ao final de cada checkpoint, resumir o que foi feito, como rodar os testes, e como testar manualmente (se aplicável).
- **Tag por checkpoint fechado**: ao fechar um checkpoint (e o usuário aprovar o commit), criar uma tag semântica (`vX.Y.0`) apontando pro commit que fecha aquele checkpoint, e dar `git push` (branch + tags) pro remote. Ver seção "Small releases e CI" do `SCOPE.md` pro esquema completo.
- **CI roda sozinho**: todo push aciona o GitHub Actions (`.github/workflows/ci.yml`), rodando as 3 suítes de teste. Não é preciso rodar tudo manualmente antes de cada push só por precaução — mas ainda assim rode localmente durante o desenvolvimento, o CI é uma segunda rede de proteção, não a primeira.

## Comandos

Repo tem três áreas independentes, cada uma com seu próprio ambiente de teste.

### `backend/` — mock publisher + ingestão (Python)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # primeira vez
pip install -r requirements.txt
pytest                                               # todos os testes (mock publisher + ingestão)
pytest tests/test_signal_generator.py -k nome_do_teste  # um teste específico
python -m mock_publisher --dry-run                   # roda o publisher sem broker (imprime no terminal)
python -m ingestion --dry-run                         # roda a ingestão sem broker/InfluxDB (imprime no terminal)
```

### `infra/` — testes de ACL do Mosquitto (Python + Docker)

```bash
cd infra
pip install -r requirements-test.txt
pytest                                        # sobe um Mosquitto efêmero (Docker) com o acl.conf real e testa as regras
docker compose up -d                          # broker local persistente (porta 1883, sem TLS)
./mosquitto/generate_passwd.sh <username>     # cria/atualiza infra/mosquitto/config/passwd (gitignored, pede senha interativamente)
```

Os testes de ACL exigem Docker rodando (sobem containers `eclipse-mosquitto:2` de verdade, não mockam o broker).

### `firmware/` — ESP32 (PlatformIO)

```bash
cd firmware
pio run -e esp32dev     # compila para o ESP32 (upload requer hardware conectado)
pio test -e native       # testes unitários (Unity) sem hardware
```

## Checkpoints (ordem de desenvolvimento)

1. Scaffolding do repo — estrutura de pastas, PlatformIO, `.gitignore`, `secrets.h.example`
2. Script mock de publicação MQTT (simula o ESP32, sem hardware — ver seção "Simulador de desenvolvimento" no SCOPE.md)
3. `docker-compose` local + configuração do broker Mosquitto (credenciais/ACL por dispositivo; sem TLS em dev local — ver seção "Docker" no SCOPE.md)
4. Script de ingestão (MQTT → InfluxDB)
5. Schema/setup do InfluxDB
6. Dashboards Grafana — caminho histórico (datasource InfluxDB)
7. Dashboard Grafana — caminho ao vivo (Grafana Live + plugin MQTT)
8. Firmware — parser CAN (TWAI + tabela de payloads do SCOPE.md)
9. Firmware — integração MQTT/WiFi/TLS
10. Traefik + Let's Encrypt (DuckDNS) + deploy na VPS
11. Validação de integração ponta a ponta

Cada item da lista é um checkpoint independente: implementar, testar, resumir, parar para revisão.

## Documentação detalhada por checkpoint

Quando o usuário pedir uma explicação mais aprofundada de um checkpoint (ex: em PDF), o material vai em `docs/checkpoint-NN-nome-curto.tex` (+ `.pdf` compilado), versionado junto com o resto do projeto — não solto fora do repositório. `SCOPE.md`/`CLAUDE.md` continuam sendo a referência rápida; os documentos em `docs/` são para leitura aprofundada sob demanda, não mantidos automaticamente a cada checkpoint.

## Referências

- Decisões técnicas e arquitetura: `SCOPE.md`
- Protocolo CAN (IDs, frequências, byte layout): seção "Plano de payloads" do `SCOPE.md`
- Documentação aprofundada por checkpoint (sob demanda): `docs/`
- Projeto antigo (histórico, não reaproveitar código): `~/Desktop/TelemetriaMqtt`
