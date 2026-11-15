#!/usr/bin/env bash
# Cópia de segurança do Physis Hub: banco copiado COM o servidor ligado (API de backup do SQLite),
# conferido (integrity_check), empacotado com instancia.json, cifrado (age ou openssl) e girado 7/4/12.
# Opcional: espelha por rsync/SSH para o servidor da Physis.
#
#   sudo /opt/physis/implantacao/backup.sh                       # a diária (o timer chama assim)
#   sudo /opt/physis/implantacao/backup.sh --rotulo pre-atualizacao   # avulsa, fora do giro
#   sudo ./backup.sh --config /etc/physis/backup.env --banco /var/lib/physis/physis-hub.db
#
# Configuração: /etc/physis/backup.env (modelo: backup.env.exemplo). Restauração: restaurar.sh.
set -euo pipefail
umask 077

CONFIG=/etc/physis/backup.env
BANCO=""
ROTULO=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) CONFIG="$2"; shift 2 ;;
    --banco) BANCO="$2"; shift 2 ;;
    --rotulo) ROTULO="$2"; shift 2 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "opção desconhecida: $1" >&2; exit 2 ;;
  esac
done

log() { printf '%s backup: %s\n' "$(date -Iseconds)" "$*"; }
falha() { log "FALHOU: $*" >&2; exit 1; }

[[ -f "$CONFIG" ]] || falha "sem $CONFIG (modelo em implantacao/backup.env.exemplo)"
# shellcheck disable=SC1090
source "$CONFIG"
DESTINO="${DESTINO:?defina DESTINO em $CONFIG}"
CIFRA="${CIFRA:-age}"
MANTER_DIARIAS="${MANTER_DIARIAS:-7}"; MANTER_SEMANAIS="${MANTER_SEMANAIS:-4}"; MANTER_MENSAIS="${MANTER_MENSAIS:-12}"
if [[ -z "$BANCO" ]]; then
  BANCO="$(grep -E '^PHYSIS_BANCO=' /etc/physis/physis.env 2>/dev/null | cut -d= -f2- || true)"
  BANCO="${BANCO:-/var/lib/physis/physis-hub.db}"
fi
[[ -f "$BANCO" ]] || falha "banco não encontrado: $BANCO"
[[ "$ROTULO" =~ ^[a-z0-9-]*$ ]] || falha "--rotulo só com letras minúsculas, números e hífen"

if [[ "${DESTINO_EXIGE_MONTAGEM:-0}" == 1 ]]; then
  mountpoint -q "$DESTINO" || falha "$DESTINO não está montado (pendrive ausente?)"
fi
mkdir -p "$DESTINO/diarias" "$DESTINO/semanais" "$DESTINO/mensais" "$DESTINO/avulsas"

case "$CIFRA" in
  age) command -v age >/dev/null || falha "age não instalado (sudo apt install age)"
       [[ "${AGE_DESTINATARIO:-}" == age1* ]] || falha "AGE_DESTINATARIO (chave pública age1...) não definido" ;;
  openssl) command -v openssl >/dev/null || falha "openssl não instalado"
       [[ -r "${OPENSSL_SENHA_ARQUIVO:-}" ]] || falha "OPENSSL_SENHA_ARQUIVO ilegível" ;;
  *) falha "CIFRA deve ser age ou openssl" ;;
esac

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
QUANDO="$(date +%Y%m%d-%H%M%S)"
NOME="physis-$(hostname -s)-$QUANDO${ROTULO:+-$ROTULO}"
mkdir "$TMP/$NOME"

# 1. cópia online e consistente (o hub usa WAL; .backup lê um instantâneo sem parar o serviço).
#    Roda como o dono do banco: se o root abrisse o banco parado, os arquivos -wal/-shm nasceriam do root
#    e o hub não conseguiria mais gravar.
COMO=()
if [[ $EUID -eq 0 ]]; then
  DONO="$(stat -c %U "$BANCO")"
  if [[ "$DONO" != root ]]; then
    COMO=(runuser -u "$DONO" --)
    chmod 0711 "$TMP"; chown "$DONO" "$TMP/$NOME"
  fi
fi
if command -v sqlite3 >/dev/null; then
  ${COMO[@]+"${COMO[@]}"} sqlite3 "$BANCO" ".timeout 30000" ".backup '$TMP/$NOME/physis-hub.db'"
else
  ${COMO[@]+"${COMO[@]}"} python3 - "$BANCO" "$TMP/$NOME/physis-hub.db" <<'PY'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1], timeout=30)
dst = sqlite3.connect(sys.argv[2])
with dst:
    src.backup(dst, pages=1024)
dst.close(); src.close()
PY
fi
python3 - "$TMP/$NOME/physis-hub.db" <<'PY'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
r = c.execute("PRAGMA integrity_check").fetchone()[0]
c.execute("PRAGMA journal_mode=DELETE")
c.close()
if r != "ok":
    sys.exit("integrity_check: " + r)
PY

# 2. junto: a configuração da instalação (sem os segredos do physis.env)
PASTA_COD="$(readlink -f /opt/physis/atual 2>/dev/null || true)"
[[ -n "$PASTA_COD" && -f "$PASTA_COD/instancia.json" ]] && cp "$PASTA_COD/instancia.json" "$TMP/$NOME/"
DIR_BANCO="$(dirname "$BANCO")"
[[ -d "$DIR_BANCO/editais" ]] && cp -a "$DIR_BANCO/editais" "$TMP/$NOME/"
( cd "$TMP/$NOME" && sha256sum -- * > SHA256SUMS 2>/dev/null || true )

# 3. empacota e cifra (o arquivo em claro nunca sai de $TMP, que é 0700 e apagado no fim)
tar -C "$TMP" -czf "$TMP/$NOME.tar.gz" "$NOME"
if [[ "$CIFRA" == age ]]; then
  SAIDA="$NOME.tar.gz.age"
  age -r "$AGE_DESTINATARIO" -o "$TMP/$SAIDA" "$TMP/$NOME.tar.gz"
else
  SAIDA="$NOME.tar.gz.enc"
  openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt -pass "file:$OPENSSL_SENHA_ARQUIVO" \
    -in "$TMP/$NOME.tar.gz" -out "$TMP/$SAIDA"
fi
( cd "$TMP" && sha256sum "$SAIDA" > "$SAIDA.sha256" )

# 4. guarda e gira 7 diárias / 4 semanais / 12 mensais
if [[ -n "$ROTULO" ]]; then
  ALVO="$DESTINO/avulsas"
else
  ALVO="$DESTINO/diarias"
fi
cp "$TMP/$SAIDA" "$TMP/$SAIDA.sha256" "$ALVO/"
if [[ -z "$ROTULO" ]]; then
  [[ "$(date +%u)" == 7 ]] && cp "$TMP/$SAIDA" "$TMP/$SAIDA.sha256" "$DESTINO/semanais/"
  [[ "$(date +%d)" == 01 ]] && cp "$TMP/$SAIDA" "$TMP/$SAIDA.sha256" "$DESTINO/mensais/"
fi
girar() {  # girar <pasta> <quantas manter>
  local p="$1" n="$2"
  ls -1t "$p"/physis-*.tar.gz.* 2>/dev/null | grep -v '\.sha256$' | tail -n +"$((n + 1))" | while read -r f; do
    rm -f -- "$f" "$f.sha256"
  done
}
girar "$DESTINO/diarias" "$MANTER_DIARIAS"
girar "$DESTINO/semanais" "$MANTER_SEMANAIS"
girar "$DESTINO/mensais" "$MANTER_MENSAIS"
girar "$DESTINO/avulsas" 5
sync

# 5. espelho remoto (opcional)
if [[ -n "${RSYNC_DESTINO:-}" ]]; then
  rsync -a --delete --timeout=120 \
    -e "ssh -i ${RSYNC_CHAVE_SSH:-/etc/physis/backup_ed25519} -o BatchMode=yes -o StrictHostKeyChecking=yes" \
    "$DESTINO/" "$RSYNC_DESTINO/" || falha "rsync para $RSYNC_DESTINO"
  log "espelhado em $RSYNC_DESTINO"
fi

# 6. marca para o verificar.sh
install -d -m 0755 /var/backups/physis
printf '{"quando": %s, "arquivo": "%s", "destino": "%s"}\n' "$(date +%s)" "$SAIDA" "$ALVO" > /var/backups/physis/ultimo.json
chmod 0644 /var/backups/physis/ultimo.json
log "ok: $ALVO/$SAIDA ($(du -h "$ALVO/$SAIDA" | cut -f1))"
