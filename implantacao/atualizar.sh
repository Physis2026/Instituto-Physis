#!/usr/bin/env bash
# Atualiza o Physis Hub em campo: pacote novo + o MESMO banco. Volta sozinho se algo der errado.
#
#   sudo /opt/physis/implantacao/atualizar.sh --pacote physis-fazenda-x.zip
#   sudo ./atualizar.sh --pacote /caminho/physis-fazenda-x [--testes-completos] [--instancia-nova]
#
# Passos: confere o pacote → testa o código novo (antes de parar nada) → para o serviço → cópia de segurança
# (cifrada, se backup.env existir, e sempre uma cópia local rápida) → troca o atalho /opt/physis/atual →
# sobe (o hub migra o banco sozinho ao abrir) → confere /api/saude e a cadeia do registro → se falhar,
# devolve o banco e o código anteriores.
set -euo pipefail
umask 027

RAIZ=/opt/physis
PACOTE=""; COMPLETO=""; INST_NOVA=""; ESPERA=60
# subconjunto rápido (o Pi leva minutos com todos). Módulos ausentes no pacote são pulados.
SMOKE=(test_protocolo test_seguranca test_sem_internet test_mqtt test_bases)
while [[ $# -gt 0 ]]; do
  case "$1" in
    --pacote) PACOTE="$2"; shift 2 ;;
    --testes-completos) COMPLETO=1; shift ;;
    --instancia-nova) INST_NOVA=1; shift ;;
    --espera) ESPERA="$2"; shift 2 ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) echo "opção desconhecida: $1" >&2; exit 2 ;;
  esac
done
msg() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
falha() { printf '\033[1;31m[atualizar] %s\033[0m\n' "$*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || falha "rode com sudo"
[[ -n "$PACOTE" ]] || falha "use --pacote <pasta ou .zip>"
[[ -L "$RAIZ/atual" ]] || falha "não há instalação em $RAIZ/atual (use instalar.sh)"
ANTERIOR="$(readlink -f "$RAIZ/atual")"

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
if [[ -f "$PACOTE" && "$PACOTE" == *.zip ]]; then
  python3 -m zipfile -e "$PACOTE" "$TMP/zip"
  PACOTE="$(dirname "$(find "$TMP/zip" -path '*/physis_hub/servidor.py' -print -quit)")/.."
fi
[[ -f "$PACOTE/physis_hub/servidor.py" ]] || falha "pacote sem physis_hub/servidor.py"

# 1. copia a versão nova ao lado (a anterior fica intacta)
VER="$RAIZ/versoes/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$VER"
for item in physis_hub web tests docs instancia.json LICENSE LEIA-ME.md montar.py programas; do
  [[ -e "$PACOTE/$item" ]] && cp -a "$PACOTE/$item" "$VER/"
done
if [[ -z "$INST_NOVA" && -f "$ANTERIOR/instancia.json" ]]; then
  [[ -f "$VER/instancia.json" ]] && mv "$VER/instancia.json" "$VER/instancia.json.do-pacote"
  cp -a "$ANTERIOR/instancia.json" "$VER/instancia.json"
fi
chown -R root:root "$VER"; chmod -R u=rwX,go=rX "$VER"
[[ -f "$VER/instancia.json" ]] && { chgrp physis "$VER/instancia.json"; chmod 0640 "$VER/instancia.json"; }

# 2. testes do código novo, como o usuário physis, em pasta temporária (nunca no banco de verdade)
msg "Testando a versão nova"
chmod 0755 "$TMP"
TESTES=()
if [[ -n "$COMPLETO" ]]; then
  CMD=(python3 -m unittest discover -s tests)
else
  for t in "${SMOKE[@]}"; do [[ -f "$VER/tests/$t.py" ]] && TESTES+=("tests.$t"); done
  CMD=(python3 -m unittest "${TESTES[@]}")
fi
if [[ -d "$VER/tests" && ( -n "$COMPLETO" || ${#TESTES[@]} -gt 0 ) ]]; then
  ( cd "$VER" && runuser -u physis -- env -i PATH=/usr/bin:/bin HOME="$TMP" TMPDIR="$TMP" PYTHONDONTWRITEBYTECODE=1 \
      PHYSIS_CLIMA=0 "${CMD[@]}" ) || { rm -rf "$VER"; falha "testes da versão nova falharam; nada foi trocado"; }
else
  echo "[atualizar] aviso: pacote sem testes; seguindo só com a conferência depois de subir" >&2
fi

# 3. para, copia o banco (cópia local rápida para voltar + a cifrada do backup.sh)
BANCO="$(grep -E '^PHYSIS_BANCO=' /etc/physis/physis.env | cut -d= -f2-)"; BANCO="${BANCO:-/var/lib/physis/physis-hub.db}"
PORTA="$(grep -E '^PHYSIS_PORTA=' /etc/physis/physis.env | cut -d= -f2-)"; PORTA="${PORTA:-8700}"
msg "Parando o serviço"
systemctl stop physis-hub.service
PRE="$BANCO.pre-atualizacao"
runuser -u physis -- python3 - "$BANCO" "$PRE" <<'PY'
import sqlite3, sys
s = sqlite3.connect(sys.argv[1]); d = sqlite3.connect(sys.argv[2])
with d:
    s.backup(d)
d.close(); s.close()
PY
if [[ -f /etc/physis/backup.env ]]; then
  "$RAIZ/implantacao/backup.sh" --rotulo pre-atualizacao || echo "[atualizar] aviso: cópia cifrada falhou; a local está em $PRE" >&2
fi

voltar() {
  echo "[atualizar] VOLTANDO para $ANTERIOR: $*" >&2
  systemctl stop physis-hub.service || true
  ln -sfn "$ANTERIOR" "$RAIZ/atual"
  for ext in -wal -shm; do rm -f "$BANCO$ext"; done
  install -m 0640 -o physis -g physis "$PRE" "$BANCO"
  systemctl start physis-hub.service
  falha "atualização desfeita (versão nova guardada em $VER para análise)"
}

# 4. troca o código e sobe (a migração do banco roda ao abrir)
ln -sfn "$VER" "$RAIZ/atual"
msg "Subindo $VER"
systemctl start physis-hub.service || voltar "o serviço não subiu"

# 5. confere: serviço ativo, porta respondendo e cadeia do registro íntegra
OK=""
for _ in $(seq 1 "$ESPERA"); do
  sleep 1
  systemctl is-active --quiet physis-hub.service || continue
  if python3 - "$PORTA" <<'PY'
import json, sys, urllib.error, urllib.request
porta = sys.argv[1]
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/instancia", timeout=3) as r:
        if r.status != 200:
            sys.exit(1)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/saude", timeout=5) as r:
            s = json.loads(r.read())
        sys.exit(0 if s.get("registro", {}).get("integro") else 2)
    except urllib.error.HTTPError as e:
        sys.exit(0 if e.code in (401, 403) else 1)   # instalação exposta: /api/saude pede sessão
except Exception:
    sys.exit(1)
PY
  then OK=1; break; fi
done
[[ -n "$OK" ]] || voltar "o hub não respondeu bem em ${ESPERA}s (ver: journalctl -u physis-hub -n 100)"

# 6. guarda as 3 versões mais novas
ls -1dt "$RAIZ"/versoes/*/ | tail -n +4 | while read -r v; do
  [[ "$(readlink -f "$v")" == "$(readlink -f "$RAIZ/atual")" ]] || rm -rf -- "$v"
done
msg "Atualizado: $ANTERIOR -> $VER. Cópia local do banco anterior: $PRE"
"$RAIZ/implantacao/verificar.sh" || true
