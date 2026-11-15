#!/usr/bin/env bash
# Instala o Physis Hub num Raspberry Pi ou mini PC (Debian 12 / Raspberry Pi OS bookworm ou mais novo).
#
# Pode rodar quantas vezes quiser (idempotente): o que já existe é conferido, não refeito.
# Segredos são gerados aqui (python3 -m secrets) e gravados só em arquivos 0600/0640; nunca aparecem na tela.
#
#   sudo ./instalar.sh                                   # pergunta o que é opcional
#   sudo ./instalar.sh --sim                             # sem perguntas: só o hub, sem opcionais
#   sudo ./instalar.sh --pacote physis-fazenda.zip --mosquitto --mqtt-no irrigacao-zona1 \
#                      --caddy lan --ufw --rede 192.168.0.0/24
#   sudo ./instalar.sh --caddy dominio --dominio hub.exemplo.com.br --email ti@exemplo.com.br --ufw
#
# Opções:
#   --pacote DIR|ZIP   pacote montado (montar.py). Padrão: a pasta acima desta (ou ../physis-hub no repositório)
#   --porta N          porta do hub (padrão 8700)
#   --mosquitto        instala o broker MQTT da Caixinha (usuário e senha, ACL por nó)
#   --mqtt-no NOME     cria o usuário MQTT de um nó ESPHome (repita para vários). Padrão: irrigacao-zona1
#   --caddy lan        HTTPS na rede local com certificado próprio (CA local do Caddy)
#   --caddy dominio    HTTPS com Let's Encrypt (precisa --dominio e as portas 80/443 chegando ao aparelho)
#   --dominio NOME     nome público (modo dominio) ou nome/IP da rede local (modo lan; padrão: o IP do aparelho)
#   --email EMAIL      e-mail para o Let's Encrypt (modo dominio)
#   --ufw              liga o firewall (só SSH, hub, MQTT e HTTPS, e só da rede local quando faz sentido)
#   --rede CIDR        rede local (padrão: detectada, ex. 192.168.0.0/24)
#   --sim              não pergunta nada (o que não veio por opção fica desligado)
set -euo pipefail
umask 027

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ=/opt/physis
DADOS=/var/lib/physis
ETC=/etc/physis
ENVF="$ETC/physis.env"
BACKUPS=/var/backups/physis
USUARIO=physis

PACOTE=""; PORTA=8700; MOSQ=""; CADDY=""; DOMINIO=""; EMAIL=""; UFW=""; REDE=""; SIM=""
NOS=()

msg()  { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
aviso(){ printf '\033[1;33m[aviso]\033[0m %s\n' "$*" >&2; }
erro() { printf '\033[1;31m[erro]\033[0m %s\n' "$*" >&2; exit 1; }
pergunta() {  # pergunta "texto" -> 0 sim / 1 não (com --sim ou sem terminal: não)
  [[ -n "$SIM" || ! -t 0 ]] && return 1
  local r; read -r -p "$1 [s/N] " r || return 1
  [[ "$r" =~ ^[sSyY] ]]
}
segredo() { python3 -c 'import secrets; print(secrets.token_urlsafe(32))'; }
# garante KEY=valor no physis.env sem trocar o que já existe (idempotente) e sem mostrar o valor
garantir_var() {
  local k="$1" v="$2"
  grep -qE "^${k}=" "$ENVF" 2>/dev/null || printf '%s=%s\n' "$k" "$v" >> "$ENVF"
}
trocar_var() {  # força um valor (só para itens não secretos, como o endereço de escuta)
  local k="$1" v="$2"
  if grep -qE "^${k}=" "$ENVF"; then sed -i "s|^${k}=.*|${k}=${v}|" "$ENVF"; else printf '%s=%s\n' "$k" "$v" >> "$ENVF"; fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pacote) PACOTE="$2"; shift 2 ;;
    --porta) PORTA="$2"; shift 2 ;;
    --mosquitto) MOSQ=1; shift ;;
    --mqtt-no) NOS+=("$2"); shift 2 ;;
    --caddy) CADDY="$2"; shift 2 ;;
    --dominio) DOMINIO="$2"; shift 2 ;;
    --email) EMAIL="$2"; shift 2 ;;
    --ufw) UFW=1; shift ;;
    --rede) REDE="$2"; shift 2 ;;
    --sim) SIM=1; shift ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) erro "opção desconhecida: $1 (veja --help)" ;;
  esac
done

[[ $EUID -eq 0 ]] || erro "rode com sudo"
[[ "$PORTA" =~ ^[0-9]{2,5}$ ]] || erro "--porta inválida"
[[ -z "$CADDY" || "$CADDY" == lan || "$CADDY" == dominio ]] || erro "--caddy aceita lan ou dominio"
for n in "${NOS[@]:-}"; do [[ -z "$n" || "$n" =~ ^[a-z0-9][a-z0-9_-]{0,62}$ ]] || erro "nome de nó MQTT inválido: $n"; done

# ── 1. Python 3.10 ou mais novo ─────────────────────────────────────────────────────────────────
command -v python3 >/dev/null || erro "python3 não encontrado (sudo apt install python3)"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
  || erro "precisa de Python 3.10 ou mais novo; este tem $(python3 -V 2>&1)"
python3 -c 'import sqlite3, ssl' || erro "o Python deste sistema não tem sqlite3/ssl"
msg "Python: $(python3 -V 2>&1)"

# ── 2. Pacote ───────────────────────────────────────────────────────────────────────────────────
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
if [[ -z "$PACOTE" ]]; then
  if [[ -f "$AQUI/../physis_hub/servidor.py" ]]; then PACOTE="$AQUI/.."
  elif [[ -f "$AQUI/../physis-hub/physis_hub/servidor.py" ]]; then PACOTE="$AQUI/../physis-hub"
  else erro "não achei o pacote; use --pacote <pasta ou .zip>"; fi
fi
if [[ -f "$PACOTE" && "$PACOTE" == *.zip ]]; then
  python3 -m zipfile -e "$PACOTE" "$TMP/zip"
  PACOTE="$(dirname "$(find "$TMP/zip" -path '*/physis_hub/servidor.py' -print -quit)")/.."
fi
[[ -f "$PACOTE/physis_hub/servidor.py" ]] || erro "pacote sem physis_hub/servidor.py: $PACOTE"
PACOTE="$(cd "$PACOTE" && pwd)"
msg "Pacote: $PACOTE"

# ── 3. Usuário e pastas ─────────────────────────────────────────────────────────────────────────
if ! id -u "$USUARIO" >/dev/null 2>&1; then
  useradd --system --home-dir "$DADOS" --no-create-home --shell /usr/sbin/nologin "$USUARIO"
  msg "Usuário de sistema '$USUARIO' criado"
fi
install -d -m 0755 -o root -g root "$RAIZ" "$RAIZ/versoes"
install -d -m 0750 -o "$USUARIO" -g "$USUARIO" "$DADOS" "$DADOS/mapas" "$DADOS/entregas" "$DADOS/editais"
install -d -m 0750 -o root -g "$USUARIO" "$ETC"
install -d -m 0700 -o root -g root "$BACKUPS"

# ── 4. Código: /opt/physis/versoes/<data> e o atalho /opt/physis/atual (troca e volta em atualizar.sh) ──
if [[ -L "$RAIZ/atual" ]] && diff -rq --exclude=__pycache__ --exclude=instancia.json \
      "$PACOTE/physis_hub" "$RAIZ/atual/physis_hub" >/dev/null 2>&1; then
  msg "Código já instalado e igual: $(readlink -f "$RAIZ/atual")"
else
  VER="$RAIZ/versoes/$(date +%Y%m%d-%H%M%S)"
  mkdir -p "$VER"
  for item in physis_hub web tests docs instancia.json LICENSE LEIA-ME.md montar.py programas; do
    [[ -e "$PACOTE/$item" ]] && cp -a "$PACOTE/$item" "$VER/"
  done
  # instancia.json local (nós MQTT, ajustes de campo) vale mais que o do pacote
  if [[ -L "$RAIZ/atual" && -f "$RAIZ/atual/instancia.json" ]]; then
    [[ -f "$VER/instancia.json" ]] && mv "$VER/instancia.json" "$VER/instancia.json.do-pacote"
    cp -a "$RAIZ/atual/instancia.json" "$VER/instancia.json"
  fi
  chown -R root:root "$VER"; chmod -R u=rwX,go=rX "$VER"
  [[ -f "$VER/instancia.json" ]] && { chgrp "$USUARIO" "$VER/instancia.json"; chmod 0640 "$VER/instancia.json"; }
  ln -sfn "$VER" "$RAIZ/atual"
  msg "Código instalado em $VER"
fi
# os próprios scripts de implantação ficam junto (o timer de cópia usa /opt/physis/implantacao/backup.sh)
install -d -m 0755 "$RAIZ/implantacao"
if [[ "$AQUI" != "$(cd "$RAIZ/implantacao" && pwd)" ]]; then
  for f in backup.sh restaurar.sh atualizar.sh verificar.sh instalar.sh; do install -m 0755 "$AQUI/$f" "$RAIZ/implantacao/$f"; done
  cp -a "$AQUI/systemd" "$AQUI/caddy" "$AQUI/mosquitto" "$AQUI/backup.env.exemplo" "$AQUI/physis.env.exemplo" "$RAIZ/implantacao/"
fi

# ── 5. Arquivo de ambiente (segredos só aqui; 0640 root:physis) ────────────────────────────────
if [[ ! -f "$ENVF" ]]; then
  ( umask 077; : > "$ENVF" )
  printf '# Physis Hub — gerado por instalar.sh em %s. Não versionar. Ver docs/SEGURANCA.md.\n' "$(date -Iseconds)" >> "$ENVF"
  msg "Criado $ENVF"
fi
chown root:"$USUARIO" "$ENVF"; chmod 0640 "$ENVF"
garantir_var PHYSIS_BANCO "$DADOS/physis-hub.db"
garantir_var PHYSIS_PORTA "$PORTA"
garantir_var PHYSIS_ENDERECO "0.0.0.0"
garantir_var PHYSIS_MAPAS "$DADOS/mapas"
garantir_var PHYSIS_ENTREGAS "$DADOS/entregas"
garantir_var PHYSIS_EDITAIS_PASTA "$DADOS/editais"
garantir_var PYTHONDONTWRITEBYTECODE 1

# ── 6. Rede local ────────────────────────────────────────────────────────────────────────────────
if [[ -z "$REDE" ]]; then
  REDE="$(ip -o -f inet addr show scope global 2>/dev/null | awk '{print $4; exit}' \
          | python3 -c 'import ipaddress,sys; l=sys.stdin.read().strip(); print(ipaddress.ip_interface(l).network if l else "")')"
fi
IP_LOCAL="$(ip -o -f inet addr show scope global 2>/dev/null | awk '{split($4,a,"/"); print a[1]; exit}')"
[[ -n "$REDE" ]] && msg "Rede local: $REDE" || aviso "rede local não detectada; use --rede"

# ── 7. Mosquitto (opcional) ─────────────────────────────────────────────────────────────────────
if [[ -z "$MOSQ" ]] && pergunta "Instalar o broker MQTT (Mosquitto) para a Caixinha Physis IoT?"; then MOSQ=1; fi
if [[ -n "$MOSQ" ]]; then
  [[ ${#NOS[@]} -gt 0 ]] || NOS=(irrigacao-zona1)
  command -v mosquitto >/dev/null || { apt-get update -qq; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq mosquitto mosquitto-clients; }
  install -d -m 0750 -o root -g mosquitto /etc/mosquitto/physis
  install -m 0644 "$AQUI/mosquitto/physis.conf" /etc/mosquitto/conf.d/physis.conf
  install -m 0640 -o mosquitto -g mosquitto "$AQUI/mosquitto/acl.exemplo" /etc/mosquitto/physis/acl
  PW=/etc/mosquitto/physis/senhas
  [[ -f "$PW" ]] || { ( umask 077; : > "$PW" ); chown mosquitto:mosquitto "$PW"; }
  install -d -m 0700 "$ETC/mqtt"
  # usuário do hub: a senha vai só para o physis.env (PHYSIS_MQTT_SENHA)
  if ! grep -q '^PHYSIS_MQTT_SENHA=' "$ENVF"; then
    S="$(segredo)"; garantir_var PHYSIS_MQTT_SENHA "$S"
    mosquitto_passwd -b "$PW" physis-hub "$S" >/dev/null; unset S
  fi
  garantir_var PHYSIS_MQTT_BROKER 127.0.0.1
  garantir_var PHYSIS_MQTT_PORTA 1883
  garantir_var PHYSIS_MQTT_USUARIO physis-hub
  # um usuário por nó, com o mesmo nome do nó ESPHome: a ACL (pattern %u/#) só deixa cada nó no próprio tópico
  for n in "${NOS[@]}"; do
    if [[ ! -f "$ETC/mqtt/$n.senha" ]]; then
      ( umask 077; segredo > "$ETC/mqtt/$n.senha" )
      mosquitto_passwd -b "$PW" "$n" "$(cat "$ETC/mqtt/$n.senha")" >/dev/null
      msg "Usuário MQTT '$n' criado; senha em $ETC/mqtt/$n.senha (copie para o secrets.yaml do ESPHome)"
    fi
  done
  chmod 0640 "$PW"; chown mosquitto:mosquitto "$PW"
  systemctl enable --now mosquitto >/dev/null
  systemctl restart mosquitto
  grep -q '^PHYSIS_MQTT_NOS=' "$ENVF" || aviso "cadastre os nós em instancia.json (\"mqtt\".\"nos\") ou PHYSIS_MQTT_NOS — docs/MQTT.md"
fi

# ── 8. Caddy com TLS (opcional) ──────────────────────────────────────────────────────────────────
if [[ -z "$CADDY" ]] && pergunta "Instalar HTTPS (Caddy) na rede local?"; then CADDY=lan; fi
if [[ -n "$CADDY" ]]; then
  command -v caddy >/dev/null || { apt-get update -qq; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq caddy; }
  if [[ "$CADDY" == dominio ]]; then
    [[ -n "$DOMINIO" && -n "$EMAIL" ]] || erro "--caddy dominio precisa de --dominio e --email"
    sed -e "s|__DOMINIO__|$DOMINIO|g" -e "s|__EMAIL__|$EMAIL|g" -e "s|__PORTA__|$PORTA|g" \
        "$AQUI/caddy/Caddyfile.dominio" > /etc/caddy/Caddyfile
    # na internet: o hub só escuta em 127.0.0.1, ninguém conta como rede local, aparelhos com chave
    trocar_var PHYSIS_ENDERECO 127.0.0.1
    garantir_var PHYSIS_EXPOSTO 1
    garantir_var PHYSIS_URL_PUBLICA "https://$DOMINIO"
    garantir_var PHYSIS_ACEITAR_SEM_CHAVE 0
  else
    NOME="${DOMINIO:-$IP_LOCAL}"; [[ -n "$NOME" ]] || erro "não achei o IP; use --dominio <nome ou IP da rede local>"
    sed -e "s|__NOME__|$NOME|g" -e "s|__PORTA__|$PORTA|g" "$AQUI/caddy/Caddyfile.lan" > /etc/caddy/Caddyfile
    # na rede local o receptor V6 continua entregando em http://<pi>:8700 (o firewall limita à rede local);
    # pessoas entram por https (PHYSIS_HTTPS=1 deixa o cookie de sessão sempre Secure).
  fi
  garantir_var PHYSIS_PROXY_CONFIAVEL "127.0.0.1,::1"
  garantir_var PHYSIS_HTTPS 1
  chmod 0644 /etc/caddy/Caddyfile
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
  systemctl enable --now caddy >/dev/null; systemctl reload caddy || systemctl restart caddy
  [[ "$CADDY" == lan ]] && msg "CA local do Caddy: instale /var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt nos celulares/computadores (docs/IMPLANTACAO.md)"
fi

# ── 9. Serviço systemd + cópia diária ───────────────────────────────────────────────────────────
install -m 0644 "$AQUI/systemd/physis-hub.service" /etc/systemd/system/physis-hub.service
install -m 0644 "$AQUI/systemd/physis-backup.service" /etc/systemd/system/physis-backup.service
install -m 0644 "$AQUI/systemd/physis-backup.timer" /etc/systemd/system/physis-backup.timer
systemctl daemon-reload
systemctl enable physis-hub.service >/dev/null
systemctl restart physis-hub.service
[[ -f "$ETC/backup.env" ]] && systemctl enable --now physis-backup.timer >/dev/null \
  || aviso "cópia diária: crie $ETC/backup.env (modelo em docs/IMPLANTACAO.md) e rode: systemctl enable --now physis-backup.timer"

# ── 10. Firewall (opcional) ─────────────────────────────────────────────────────────────────────
if [[ -z "$UFW" ]] && pergunta "Ligar o firewall (ufw)?"; then UFW=1; fi
if [[ -n "$UFW" ]]; then
  command -v ufw >/dev/null || { apt-get update -qq; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ufw; }
  DE="${REDE:-any}"
  ufw default deny incoming >/dev/null
  ufw default allow outgoing >/dev/null
  ufw allow from "$DE" to any port 22 proto tcp comment 'SSH (rede local)' >/dev/null
  if [[ "$CADDY" == dominio ]]; then
    ufw allow 80/tcp comment 'HTTP->HTTPS / ACME' >/dev/null
    ufw allow 443/tcp comment 'HTTPS' >/dev/null
  else
    ufw allow from "$DE" to any port "$PORTA" proto tcp comment 'Physis Hub (rede local)' >/dev/null
    [[ -n "$CADDY" ]] && { ufw allow from "$DE" to any port 443 proto tcp comment 'HTTPS (rede local)' >/dev/null;
                           ufw allow from "$DE" to any port 80 proto tcp comment 'HTTP->HTTPS (rede local)' >/dev/null; }
  fi
  [[ -n "$MOSQ" ]] && ufw allow from "$DE" to any port 1883 proto tcp comment 'MQTT Caixinha (rede local)' >/dev/null
  ufw --force enable >/dev/null
  msg "Firewall ligado (rede: $DE)"
fi

# ── 11. Conferência ──────────────────────────────────────────────────────────────────────────────
sleep 3
"$RAIZ/implantacao/verificar.sh" || aviso "verificar.sh apontou pendências (acima)"
msg "Pronto. Abra http://${IP_LOCAL:-<ip>}:$PORTA/ (ou https://${DOMINIO:-$IP_LOCAL}/ com Caddy) e crie a primeira conta pela rede local."
