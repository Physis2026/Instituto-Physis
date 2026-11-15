#!/usr/bin/env bash
# Saúde da instalação: serviço, porta, /api/saude (cadeia do registro íntegra), disco, idade da última cópia,
# broker MQTT, Caddy, relógio e (no Raspberry Pi) energia. Sai com 1 se houver FALHA.
#
#   sudo /opt/physis/implantacao/verificar.sh
#   /opt/physis/implantacao/verificar.sh --max-horas-backup 26
set -euo pipefail

ENVF=/etc/physis/physis.env
MAX_H=26
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENVF="$2"; shift 2 ;;
    --max-horas-backup) MAX_H="$2"; shift 2 ;;
    -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
    *) echo "opção desconhecida: $1" >&2; exit 2 ;;
  esac
done

FALHAS=0
ok()    { printf '  [ OK  ] %s\n' "$*"; }
aviso() { printf '  [AVISO] %s\n' "$*"; }
falha() { printf '  [FALHA] %s\n' "$*"; FALHAS=$((FALHAS + 1)); }
var() { [[ -r "$ENVF" ]] && grep -E "^$1=" "$ENVF" | tail -n1 | cut -d= -f2- || true; }

PORTA="$(var PHYSIS_PORTA)"; PORTA="${PORTA:-8700}"
BANCO="$(var PHYSIS_BANCO)"; BANCO="${BANCO:-/var/lib/physis/physis-hub.db}"
echo "Physis Hub — verificação ($(hostname) $(date '+%d/%m/%Y %H:%M'))"

# 1. serviço
if systemctl is-active --quiet physis-hub.service; then ok "serviço physis-hub ativo"
else falha "serviço physis-hub parado (journalctl -u physis-hub -n 50)"; fi

# 2 e 3. porta e /api/saude
R="$(python3 - "$PORTA" <<'PY' || true
import json, socket, sys, urllib.error, urllib.request
porta = int(sys.argv[1])
try:
    socket.create_connection(("127.0.0.1", porta), timeout=3).close()
except OSError:
    print("porta-fechada"); sys.exit()
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/saude", timeout=5) as r:
        s = json.loads(r.read())
    reg = s.get("registro") or {}
    print(("integro" if reg.get("integro") else "quebrado") + f" {reg.get('entradas', '?')}")
except urllib.error.HTTPError as e:
    print(f"http-{e.code}")
except Exception as e:
    print("erro-" + type(e).__name__)
PY
)"
case "$R" in
  porta-fechada) falha "porta $PORTA não responde" ;;
  integro*)  ok "porta $PORTA respondendo"; ok "cadeia do registro íntegra (${R#integro } entradas)" ;;
  quebrado*) ok "porta $PORTA respondendo"; falha "cadeia do registro QUEBRADA — não apague nada; avise a Physis" ;;
  http-401|http-403) ok "porta $PORTA respondendo"; aviso "/api/saude pede sessão (instalação exposta); confira a cadeia pela Gestão" ;;
  *) falha "/api/saude: $R" ;;
esac

# 4. disco
if [[ -e "$(dirname "$BANCO")" ]]; then
  USO="$(df -P "$(dirname "$BANCO")" | awk 'NR==2 {gsub("%","",$5); print $5}')"
  TAM="$(du -h "$BANCO" 2>/dev/null | cut -f1 || echo '?')"
  if   (( USO >= 95 )); then falha "disco ${USO}% cheio (banco: $TAM)"
  elif (( USO >= 85 )); then aviso "disco ${USO}% cheio (banco: $TAM)"
  else ok "disco ${USO}% usado (banco: $TAM)"; fi
else
  falha "pasta do banco não existe: $(dirname "$BANCO")"
fi

# 5. última cópia de segurança
if [[ -f /var/backups/physis/ultimo.json ]]; then
  H="$(python3 -c 'import json,sys,time; print(int((time.time()-json.load(open(sys.argv[1]))["quando"])//3600))' /var/backups/physis/ultimo.json)"
  if (( H > MAX_H )); then falha "última cópia de segurança há ${H} h (máximo ${MAX_H} h)"
  else ok "última cópia de segurança há ${H} h"; fi
elif [[ -f /etc/physis/backup.env ]]; then
  falha "cópia configurada mas nunca feita (systemctl status physis-backup.timer)"
else
  aviso "cópia de segurança não configurada (/etc/physis/backup.env)"
fi

# 6. MQTT (se instalado)
if systemctl list-unit-files mosquitto.service >/dev/null 2>&1 && command -v mosquitto >/dev/null; then
  if systemctl is-active --quiet mosquitto && python3 -c 'import socket; socket.create_connection(("127.0.0.1",1883),3).close()' 2>/dev/null
  then ok "broker MQTT (Mosquitto) ativo na 1883"
  else falha "broker MQTT parado ou sem a porta 1883"; fi
fi

# 7. Caddy (se instalado)
if command -v caddy >/dev/null; then
  if systemctl is-active --quiet caddy; then ok "Caddy (HTTPS) ativo"; else falha "Caddy parado"; fi
fi

# 8. relógio (o Pi não tem relógio com bateria: hora errada = registro e alertas com hora errada)
if command -v timedatectl >/dev/null; then
  if [[ "$(timedatectl show -p NTPSynchronized --value 2>/dev/null)" == yes ]]; then ok "relógio sincronizado"
  else aviso "relógio NÃO sincronizado (sem internet? considere um módulo RTC)"; fi
fi

# 9. energia no Raspberry Pi (subtensão corrompe cartão SD)
if command -v vcgencmd >/dev/null; then
  T="$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2 || true)"
  if [[ "$T" == 0x0 ]]; then ok "energia do Pi sem subtensão"
  else aviso "energia do Pi: get_throttled=$T (fonte fraca ou cabo ruim; use a fonte oficial e nobreak)"; fi
fi

if (( FALHAS > 0 )); then echo "Resultado: $FALHAS falha(s)."; exit 1; fi
echo "Resultado: tudo certo."
