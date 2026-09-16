# CLAUDE.md

Instruções de trabalho para este repositório. Ver `SCOPE.md` para as decisões técnicas (arquitetura, protocolo CAN, hardware, infra) — este arquivo é só sobre *como* trabalhamos, não *o quê*.

## Metodologia

- **TDD obrigatório**: para cada checkpoint, escrever os testes antes ou junto da implementação. Nenhum checkpoint é considerado fechado com testes falhando. Isso existe para manter cada etapa pequena e verificável, evitando que o código cresça sem controle.
- **Testes são intocáveis depois de escritos**: nunca apagar ou modificar um teste já existente para fazê-lo passar, nem para "simplificar". Se um teste está falhando, o problema é a implementação — conserte a implementação, não o teste. Se um requisito genuinamente mudou e um teste ficou obsoleto, pare e pergunte ao usuário antes de tocar nele; não decida isso sozinho. Adicionar novos testes é sempre permitido.
- **Toda decisão de tecnologia registrada no SCOPE.md**: qualquer escolha de linguagem, framework, biblioteca, serviço ou ferramenta feita durante um checkpoint (ex: PlatformIO, Python, pytest, Mosquitto) precisa ser adicionada à seção "Stack tecnológico" do `SCOPE.md` antes de considerar o checkpoint fechado — mesmo que pareça óbvia ou incidental no momento.
- **Quem escreve o código**: Claude escreve toda a implementação. O usuário revisa — não espere que ele escreva trechos de código.
- **Revisão por checkpoint**: parar ao final de cada checkpoint (ver lista abaixo) e aguardar aprovação explícita antes de seguir para o próximo. Não emendar múltiplos checkpoints em uma sequência sem parar.
- **Forma de revisão**: o usuário revisa tanto lendo o código/diff quanto rodando/testando na própria máquina. Ao final de cada checkpoint, resumir o que foi feito, como rodar os testes, e como testar manualmente (se aplicável).

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

## Referências

- Decisões técnicas e arquitetura: `SCOPE.md`
- Protocolo CAN (IDs, frequências, byte layout): seção "Plano de payloads" do `SCOPE.md`
- Projeto antigo (histórico, não reaproveitar código): `~/Desktop/TelemetriaMqtt`
