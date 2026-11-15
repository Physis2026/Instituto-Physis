#!/usr/bin/env bash
# Restaura uma cópia feita por backup.sh.
#
#   sudo ./restaurar.sh --arquivo /media/physis-backup/diarias/physis-pi-20261115-023000.tar.gz.age \
#                       --chave-age /caminho/physis-backup.chave
#   sudo ./restaurar.sh --arquivo ...tar.gz.enc            # openssl: usa OPENSSL_SENHA_ARQUIVO do backup.env
#   sudo ./restaurar.sh --arquivo ... --so-conferir        # só decifra e confere, não troca nada
#
# O banco atual NÃO é apagado: vira physis-hub.db.antes-restauro-<data> na mesma pasta.
set -euo pipefail
umask 077

ARQ=""; CHAVE=""; SO_CONFERIR=""; CONFIG=/etc/physis/backup.env
while [[ $# -gt 0 ]]; do
  case "$1" in
    --arquivo) ARQ="$2"; shift 2 ;;
    --chave-age) CHAVE="$2"; shift 2 ;;
    --config) CONFIG="$2"; shift 2 ;;
    --so-conferir) SO_CONFERIR=1; shift ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "opção desconhecida: $1" >&2; exit 2 ;;
  esac
done
falha() { echo "[restaurar] FALHOU: $*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || falha "rode com sudo"
[[ -f "$ARQ" ]] || falha "use --arquivo <cópia>"
[[ -f "$CONFIG" ]] && source "$CONFIG"

if [[ -f "$ARQ.sha256" ]]; then
  ( cd "$(dirname "$ARQ")" && sha256sum -c --status "$(basename "$ARQ").sha256" ) || falha "SHA-256 não confere: arquivo corrompido"
fi

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
case "$ARQ" in
  *.age) [[ -f "$CHAVE" ]] || falha "cópia age: informe --chave-age (a chave PRIVADA, guardada fora do aparelho)"
         age -d -i "$CHAVE" -o "$TMP/c.tar.gz" "$ARQ" ;;
  *.enc) [[ -r "${OPENSSL_SENHA_ARQUIVO:-}" ]] || falha "defina OPENSSL_SENHA_ARQUIVO em $CONFIG"
         openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass "file:$OPENSSL_SENHA_ARQUIVO" -in "$ARQ" -out "$TMP/c.tar.gz" ;;
  *) falha "extensão desconhecida (esperado .age ou .enc)" ;;
esac
tar -C "$TMP" -xzf "$TMP/c.tar.gz"
NOVO="$(find "$TMP" -mindepth 2 -maxdepth 2 -name physis-hub.db -print -quit)"
[[ -n "$NOVO" ]] || falha "a cópia não tem physis-hub.db"
python3 - "$NOVO" <<'PY'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
r = c.execute("PRAGMA integrity_check").fetchone()[0]
n = c.execute("SELECT count(*) FROM registro").fetchone()[0]
c.close()
print(f"[restaurar] integrity_check={r}  entradas no registro={n}")
sys.exit(0 if r == "ok" else 1)
PY
[[ -n "$SO_CONFERIR" ]] && { echo "[restaurar] cópia boa (nada foi trocado)"; exit 0; }

BANCO="$(grep -E '^PHYSIS_BANCO=' /etc/physis/physis.env | cut -d= -f2-)"
BANCO="${BANCO:-/var/lib/physis/physis-hub.db}"
QUANDO="$(date +%Y%m%d-%H%M%S)"
systemctl stop physis-hub.service
for ext in "" -wal -shm; do
  [[ -f "$BANCO$ext" ]] && mv "$BANCO$ext" "$BANCO.antes-restauro-$QUANDO$ext"
done
install -m 0640 -o physis -g physis "$NOVO" "$BANCO"
PASTA="$(dirname "$NOVO")"
if [[ -f "$PASTA/instancia.json" ]]; then
  echo "[restaurar] instancia.json da cópia em /opt/physis/atual/instancia.json.da-copia (compare antes de trocar)"
  install -m 0640 -o root -g physis "$PASTA/instancia.json" /opt/physis/atual/instancia.json.da-copia
fi
systemctl start physis-hub.service
sleep 3
/opt/physis/implantacao/verificar.sh || falha "o hub subiu com problemas; o banco anterior está em $BANCO.antes-restauro-$QUANDO"
echo "[restaurar] ok. Banco anterior guardado em $BANCO.antes-restauro-$QUANDO"
