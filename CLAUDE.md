# CLAUDE.md

Instruções de trabalho para este repositório. Ver `SCOPE.md` para as decisões técnicas (arquitetura, protocolo CAN, hardware, infra) — este arquivo é só sobre *como* trabalhamos, não *o quê*.

## Metodologia

- **TDD obrigatório**: para cada checkpoint, escrever os testes antes ou junto da implementação. Nenhum checkpoint é considerado fechado com testes falhando. Isso existe para manter cada etapa pequena e verificável, evitando que o código cresça sem controle.
- **Quem escreve o código**: Claude escreve toda a implementação. O usuário revisa — não espere que ele escreva trechos de código.
- **Revisão por checkpoint**: parar ao final de cada checkpoint (ver lista abaixo) e aguardar aprovação explícita antes de seguir para o próximo. Não emendar múltiplos checkpoints em uma sequência sem parar.
- **Forma de revisão**: o usuário revisa tanto lendo o código/diff quanto rodando/testando na própria máquina. Ao final de cada checkpoint, resumir o que foi feito, como rodar os testes, e como testar manualmente (se aplicável).

## Checkpoints (ordem de desenvolvimento)

1. Scaffolding do repo — estrutura de pastas, PlatformIO, `.gitignore`, `secrets.h.example`
2. Script mock de publicação MQTT (simula o ESP32, sem hardware — ver seção "Simulador de desenvolvimento" no SCOPE.md)
3. Configuração do broker Mosquitto (TLS, credenciais/ACL por dispositivo)
4. Script de ingestão (MQTT → InfluxDB)
5. Schema/setup do InfluxDB
6. Dashboards Grafana — caminho histórico (datasource InfluxDB)
7. Dashboard Grafana — caminho ao vivo (Grafana Live + plugin MQTT)
8. Firmware — parser CAN (TWAI + tabela de payloads do SCOPE.md)
9. Firmware — integração MQTT/WiFi/TLS
10. Validação de integração ponta a ponta

Cada item da lista é um checkpoint independente: implementar, testar, resumir, parar para revisão.

## Referências

- Decisões técnicas e arquitetura: `SCOPE.md`
- Protocolo CAN (IDs, frequências, byte layout): seção "Plano de payloads" do `SCOPE.md`
- Projeto antigo (histórico, não reaproveitar código): `~/Desktop/TelemetriaMqtt`
