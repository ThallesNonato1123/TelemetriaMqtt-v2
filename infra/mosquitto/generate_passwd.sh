#!/usr/bin/env bash
# Cria/atualiza infra/mosquitto/config/passwd usando o binário mosquitto_passwd
# dentro do container oficial — não precisa instalar mosquitto localmente.
#
# Uso: ./generate_passwd.sh <username>
# (pede a senha interativamente, não fica no histórico do shell)
set -euo pipefail

USERNAME="${1:?uso: generate_passwd.sh <username>}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# MOSQUITTO_CONFIG_DIR permite apontar pra um diretório alternativo (usado
# pelos testes, pra não arriscar sujar infra/mosquitto/config/passwd de
# verdade) -- uso normal não define essa variável, então o comportamento
# de sempre (config/ ao lado do script) não muda.
CONFIG_DIR="${MOSQUITTO_CONFIG_DIR:-$DIR/config}"

mkdir -p "$CONFIG_DIR"
touch "$CONFIG_DIR/passwd"

read -rsp "Senha para '$USERNAME': " PASSWORD
echo

docker run --rm \
  -v "$CONFIG_DIR:/mosquitto/config" \
  eclipse-mosquitto:2 \
  mosquitto_passwd -b /mosquitto/config/passwd "$USERNAME" "$PASSWORD"

echo "Usuário '$USERNAME' adicionado/atualizado em $CONFIG_DIR/passwd"
