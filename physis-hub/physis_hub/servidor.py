"""Servidor HTTP do hub (biblioteca padrao).

Rotas que o Receptor V6 ja usa (sem mudar o firmware):
  POST /api/gateway/webhook      text/plain, uma linha V6 por linha -> 200
Rotas para dispositivos Wi-Fi via ESP (Caixinha e afins):
  POST /api/v6/linha             mesmo corpo; a resposta traz os comandos pendentes do no
Rotas das telas:
  GET  /api/painel               estado completo para a interface
  GET  /api/serie?ativo=&grandeza=
  GET  /api/leituras?limite=&no=   historico das leituras (tela Registros e download)
  GET  /api/saude                contadores, descartes, cadeia do registro
  POST /api/comando              {"comando":"CMD:03:LIM1:35"} ou a linha crua
  GET  /api/clima                previsão de cada fonte guardada no hub, placar de acertos e previsão combinada
  POST /api/clima/local          {"lat","lon","municipio","uf","ibge"} — também grava no receptor (PHYSIS_RX_URL)
  POST /api/clima/atualizar      consulta todas as fontes agora
  GET  /                         web/painel.html

Variaveis de ambiente:
  PHYSIS_MQTT_BROKER/_PORTA/_USUARIO/_SENHA/_TLS/_NOS  ponte MQTT da Caixinha IoT (ver docs/MQTT.md)
  PHYSIS_PORTA (8700)  PHYSIS_BANCO (physis-hub.db)  PHYSIS_ORG  PHYSIS_LUGAR
  PHYSIS_RX_URL        ex.: http://192.168.4.1 — liga o envio de comandos e a consulta ao receptor
  PHYSIS_TOKEN         se definido, exigido em X-Physis-Token nas rotas das telas que alteram estado (comparação em
                       tempo constante); também vale como chave única antiga dos aparelhos. Prefira as chaves por dispositivo.
  Segurança na internet (docs/SEGURANCA.md, physis_hub/seguranca.py):
  PHYSIS_ENDERECO (0.0.0.0)  PHYSIS_PROXY_CONFIAVEL  PHYSIS_HTTPS  PHYSIS_EXPOSTO  PHYSIS_ACEITAR_SEM_CHAVE
  PHYSIS_PRIMEIRA_CONTA_EXTERNA  PHYSIS_LIMITE_{PUBLICO,ARQUIVO,ENTRAR,DISPOSITIVO}  PHYSIS_RETENCAO_DIAS_*
  PHYSIS_CSRF_ESTRITO  PHYSIS_ORIGENS  PHYSIS_SESSAO_OCIOSA_MIN  PHYSIS_SESSAO_DIAS  PHYSIS_REAUT_MIN
  PHYSIS_CONFIRMAR_EMAIL  PHYSIS_TERMOS_VERSAO  PHYSIS_CONSENTIMENTO_ESTRITO  PHYSIS_SEGURANCA_CONTATO
  PHYSIS_SIMULAR       ex.: "6,1,3,1" (solo,zona,coleira,comedouro) — gera dados sem hardware
"""
from __future__ import annotations

import json
import os
import sys
import threading
import traceback
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import re

from . import clima as clima_mod
from . import saude as saude_mod
from . import mqtt as mqtt_mod
from . import gis as gis_mod
from . import zonas as zonas_mod
from . import vento as vento_mod
from . import residuos_gis as residuos_mod
from . import aprendizado as aprendizado_mod
from . import robos as robos_mod
from . import alertas_clima as alertas_mod
from . import app_pwa
from . import correio
from . import editais as editais_mod
from . import seguranca as seg
from . import perfil_cliente
from .hub import Hub
from .protocolo import para_int, validar_telemetria
from .simulador import Simulador

CORPO_MAX = 64 * 1024
# Ao recusar um corpo grande, o servidor ainda le e descarta ate este tanto antes de fechar.
# Sem isso, o Windows (e as vezes o Linux) corta a conexao com RST e quem enviou nunca ve o 413.
# O teto e o tempo limite impedem que alguem prenda o servidor mandando um corpo sem fim.
DRENAR_MAX = 24 * 1024 * 1024
DRENAR_SEGUNDOS = 5
WEB = Path(__file__).resolve().parent.parent / "web"
DWG_MAX = 50 * 1024 * 1024


def converter_dwg(dados: bytes, programa: str | None = None, tempo: float = 120.0) -> dict:
    """DWG -> DXF com o LibreDWG (dwg2dxf, código aberto). Sem o programa no servidor, avisa e pede DXF."""
    import shutil
    import subprocess
    import tempfile
    exe = programa or os.environ.get("PHYSIS_DWG2DXF") or shutil.which("dwg2dxf")
    if not exe:
        return {"ok": False, "codigo": 501, "erro": "o conversor de DWG (LibreDWG, dwg2dxf) ainda não está instalado no servidor; exporte em DXF pelo programa de desenho"}
    if not dados.startswith(b"AC10"):
        return {"ok": False, "codigo": 400, "erro": "o arquivo não parece ser um DWG"}
    with tempfile.TemporaryDirectory() as d:
        ent, sai = Path(d) / "entrada.dwg", Path(d) / "saida.dxf"
        ent.write_bytes(dados)
        try:
            p = subprocess.run([exe, "-y", "-o", str(sai), str(ent)], capture_output=True, timeout=tempo)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "codigo": 500, "erro": f"a conversão não terminou: {exc}"}
        if not sai.is_file() or sai.stat().st_size == 0:
            msg = (p.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-1:] or ["sem detalhe"]
            return {"ok": False, "codigo": 422, "erro": "o conversor não conseguiu ler este DWG (" + msg[0][:160] + "); exporte em DXF"}
        return {"ok": True, "dxf": sai.read_bytes()}


# mapas de fundo das regiões dos clientes (PMTiles do OpenStreetMap); PHYSIS_MAPAS troca a pasta
def PASTA_MAPAS() -> Path:
    return Path(os.environ.get("PHYSIS_MAPAS") or (WEB.parent / "mapas"))


# bibliotecas grandes que o servidor entrega em /vendor/ (as pequenas vão embutidas nos programas)
VENDOR_TIPOS = {"maplibre-gl.js": "text/javascript; charset=utf-8", "maplibre-gl.css": "text/css; charset=utf-8",
                "pmtiles.js": "text/javascript; charset=utf-8", "web-ifc-api-iife.js": "text/javascript; charset=utf-8",
                "web-ifc.wasm": "application/wasm", "three.min.js": "text/javascript; charset=utf-8"}
INSTANCIA = Path(__file__).resolve().parent.parent / "instancia.json"


def arquivo_instancia() -> Path:
    """instancia.json desta instalação. PHYSIS_INSTANCIA troca o arquivo: assim o servidor da Physis e o do
    Instituto Physis rodam do mesmo código na mesma máquina, cada um com a sua configuração (docs/INSTITUTO.md)."""
    return Path(os.environ.get("PHYSIS_INSTANCIA") or INSTANCIA)


def ler_instancia() -> dict:
    """Configuracao da instalacao montada na compra: modulos, se exige login, licenca."""
    try:
        return json.loads(arquivo_instancia().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def banco_da_instancia(inst: dict) -> str:
    """Arquivo do banco: PHYSIS_BANCO; senão o "banco" do instancia.json (relativo à pasta dele); senão physis-hub.db."""
    if os.environ.get("PHYSIS_BANCO"):
        return os.environ["PHYSIS_BANCO"]
    nome = str(inst.get("banco") or "").strip()
    if nome and re.fullmatch(r"[A-Za-z0-9._-]{1,80}\.db", nome):
        return str(arquivo_instancia().resolve().parent / nome)
    return "physis-hub.db"


def marca_da_instancia(inst: dict) -> dict:
    """Marca da instalação para as telas: nome, texto do logo e cores (só as da docs/PALETA.md, conferidas na montagem)."""
    m = inst.get("marca") if isinstance(inst.get("marca"), dict) else {}
    cores = m.get("cores") if isinstance(m.get("cores"), dict) else {}
    return {"nome": str(m.get("nome") or inst.get("nome") or "")[:120], "logo_texto": str(m.get("logo_texto") or "")[:60],
            "cores": {str(k)[:30]: str(v)[:9] for k, v in cores.items() if re.fullmatch(r"#[0-9A-Fa-f]{6}", str(v))}}


def cliente_receptor(base: str, timeout: float = 4.0):
    """Funcao que entrega um comando ao receptor (`POST /api/comando`)."""
    def enviar(linha: str):
        dados = json.dumps({"comando": linha}).encode()
        req = urllib.request.Request(base.rstrip("/") + "/api/comando", data=dados,
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                corpo = json.loads(r.read().decode() or "{}")
                return bool(corpo.get("ok")), f"fila do receptor: {corpo.get('fila', '?')}"
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return False, f"receptor inacessivel: {exc}"
    return enviar


def consultar_receptor(hub: Hub, base: str, parar: threading.Event, intervalo: float = 3.0):
    """Consulta `GET /api/leituras?desde=<cursor>` — segundo caminho, alem do envio."""
    cursor = 0
    while not parar.is_set():
        try:
            with urllib.request.urlopen(f"{base.rstrip('/')}/api/leituras?desde={cursor}", timeout=4) as r:
                dados = json.loads(r.read().decode())
            linhas = dados.get("leituras", [])
            if linhas:
                hub.receber_lote("\n".join(linhas), origem="receptor-consulta")
            cursor = int(dados.get("cursor", cursor))
        except (urllib.error.URLError, OSError, ValueError):
            pass
        parar.wait(intervalo)


def simular(hub: Hub, sim: Simulador, parar: threading.Event, intervalo: float = 2.0):
    while not parar.is_set():
        linhas = sim.passo(hub.comandos_pendentes())
        hub.receber_lote("\n".join(linhas), origem="simulador")
        parar.wait(intervalo)


def origem_chamadas(valor: str | None) -> str | None:
    """Origem do servidor de chamadas (Jitsi) da Physis, ou None se ausente ou invalida.

    So aceita https://host[:porta], sem caminho, consulta nem caractere que quebre a politica
    de seguranca. Qualquer outra coisa e recusada: a politica continua fechada."""
    if not valor:
        return None
    v = valor.strip().rstrip("/")
    if any(c in v for c in " ;,'\"\t\r\n"):
        return None
    u = urlparse(v)
    if u.scheme != "https" or not u.hostname or u.path or u.query or u.fragment or u.username or u.password:
        return None
    return f"https://{u.netloc}"


def politica(chamadas: str | None = None) -> str:
    """Content-Security-Policy. Sem servidor de chamadas, nada de fora do proprio servidor e carregado.
    Com ele, so aquela origem entra: script da API, quadro da chamada e a ligacao (https e wss)."""
    o = origem_chamadas(chamadas)
    s = f" {o}" if o else ""
    w = f" {o} wss://{o[len('https://'):]}" if o else ""
    # 'wasm-unsafe-eval': deixa rodar o leitor BIM (web-ifc, WebAssembly) servido pelo próprio servidor;
    # worker-src blob:: o mapa (MapLibre) desenha num worker criado na própria página. Nada de fora entra.
    return ("default-src 'self'; script-src 'self' 'unsafe-inline'" + s + " 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; "
            "worker-src 'self' blob:; "
            "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' blob:" + w + "; frame-src 'self' blob: data:" + s + "; "
            "media-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'")


def fabricante(instancia: dict):
    """Função que monta o pacote de um cliente, ou None se este servidor não tem o montador.

    Procura montar.py ao lado de physis_hub/ e os programas da Physis em programas/ (pacote do
    servidor) ou nas pastas do repositório. Os pacotes vão para PHYSIS_ENTREGAS (padrão: entregas/)."""
    raiz = WEB.parent
    if not (raiz / "montar.py").exists():
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location("physis_montar", raiz / "montar.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    def achar(*nomes):
        for n in nomes:
            for p in (raiz / "programas" / n, raiz.parent / "sistema" / n, raiz.parent / "modulos" / "planejador" / n):
                if p.exists():
                    return p
        return None
    sk, sup = achar("SustainKit_Definitivo.html"), achar("physis-scada-demo.html")
    saida = Path(os.environ.get("PHYSIS_ENTREGAS") or (raiz / "entregas"))
    def fabricar(org: str, modulos: list[str], nome: str, cursos: list | None = None) -> Path:
        saida.mkdir(parents=True, exist_ok=True)
        return mod.montar(org, "lugar01", modulos, saida, sk, instancia.get("licenca") or mod.LICENCA_PADRAO, sup, None, None, False, nome, cursos)
    return fabricar


PAGINA_ATIVAR = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ativar a plataforma · Physis</title><style>
body{margin:0;background:#F4F6F1;color:#1C2B21;font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif}
main{max-width:560px;margin:0 auto;padding:32px 16px}h1{font:500 1.9em Fraunces,Georgia,serif;color:#33512F;margin:0 0 8px}
.cartao{background:#fff;border:1px solid #C9D2C4;border-radius:12px;padding:18px;margin-top:16px}
label{display:block;font-weight:600;margin-bottom:4px}input{font:inherit;font-size:1.15em;letter-spacing:.08em;width:100%;box-sizing:border-box;min-height:48px;padding:6px 12px;border:1px solid #8A9284;border-radius:8px;text-transform:uppercase}
button{font:inherit;font-weight:600;min-height:48px;padding:0 20px;margin-top:12px;border-radius:8px;border:1px solid #33512F;background:#33512F;color:#fff;cursor:pointer}
:focus-visible{outline:3px solid #33512F;outline-offset:2px}#msg{min-height:1.5em;font-weight:600;margin-top:12px}.t2{color:#4A4F44}
</style></head><body><main><h1>Ativar a sua plataforma</h1>
<p class="t2">Instalação <strong>__NUMERO__</strong>. Digite o código de ativação que chegou no seu e-mail.</p>
<div class="cartao"><label for="codigo">Código de ativação</label><input id="codigo" autocomplete="one-time-code" placeholder="XXXX-XXXX-XXXX" aria-describedby="msg">
<button type="button" id="ok">Ativar e baixar a plataforma</button><p id="msg" role="status" aria-live="polite"></p></div>
<p class="t2">Depois de baixar: descompacte, rode <code>python3 -m physis_hub.servidor</code> e abra o endereço indicado no arquivo LEIA-ME. No primeiro acesso, crie o seu usuário e senha.</p>
</main><script>
var n="__NUMERO__",b=document.getElementById("ok"),m=document.getElementById("msg"),c=document.getElementById("codigo");
function dizer(t,e){m.textContent=t;m.style.color=e?"#7A2214":"#1F4A1C";}
c.addEventListener("keydown",function(e){if(e.key==="Enter")b.click();});
b.onclick=function(){var v=c.value.trim();if(!v){dizer("Digite o código.",true);c.focus();return;}b.disabled=true;dizer("Conferindo…",false);
fetch("/api/ativar/"+encodeURIComponent(n),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({codigo:v})}).then(function(r){
var t=r.headers.get("Content-Type")||"";if(r.ok&&t.indexOf("zip")>=0)return r.blob().then(function(z){var u=URL.createObjectURL(z),a=document.createElement("a");a.href=u;a.download="physis-"+n+".zip";document.body.appendChild(a);a.click();a.remove();setTimeout(function(){URL.revokeObjectURL(u);},4000);dizer("Código conferido. O download da sua plataforma começou.",false);});
return r.json().then(function(j){dizer(j.ok?"Código conferido. A equipe Physis envia a plataforma montada para você em breve.":(j.erro==="muitas tentativas; espere alguns minutos"?"Muitas tentativas. Espere alguns minutos e tente de novo.":"Instalação ou código não conferem. Confira o e-mail."),!j.ok);});
}).catch(function(){dizer("Sem resposta do servidor. Tente de novo.",true);}).then(function(){b.disabled=false;});};
</script></body></html>"""


PAGINA_ENTRAR = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Entrar · Gestão Physis</title><style>
body{margin:0;background:#F4F6F1;color:#1C2B21;font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif}
main{max-width:460px;margin:0 auto;padding:40px 16px}h1{font:500 1.9em Fraunces,Georgia,serif;color:#33512F;margin:0 0 6px}
.cartao{background:#fff;border:1px solid #C9D2C4;border-radius:12px;padding:18px;margin-top:14px;display:grid;gap:10px}
label{font-weight:600}input{font:inherit;width:100%;box-sizing:border-box;min-height:46px;padding:6px 12px;border:1px solid #8A9284;border-radius:8px}
button{font:inherit;font-weight:600;min-height:46px;padding:0 20px;border-radius:8px;border:1px solid #33512F;background:#33512F;color:#fff;cursor:pointer}
:focus-visible{outline:3px solid #33512F;outline-offset:2px}#msg{min-height:1.5em;font-weight:600;margin:0}.t2{color:#4A4F44;margin:0}
</style></head><body><main><h1>Gestão Physis</h1><p class="t2" id="sub">Entre com o seu e-mail da Physis e a sua senha.</p>
<div class="cartao"><div id="caixa-nome" hidden><label for="nome">Seu nome</label><input id="nome" autocomplete="name"></div>
<div><label for="usuario">E-mail</label><input id="usuario" type="email" autocomplete="username" inputmode="email"></div>
<div><label for="senha">Senha</label><input id="senha" type="password" autocomplete="current-password"></div>
<div id="caixa-codigo" hidden><label for="codigo">Código do aplicativo autenticador</label><input id="codigo" autocomplete="one-time-code" inputmode="numeric" aria-describedby="dica-codigo">
<p class="t2" id="dica-codigo">6 números do aplicativo, ou um dos códigos de recuperação.</p></div>
<div id="caixa-termos" hidden><label style="font-weight:400;display:flex;gap:8px;align-items:flex-start"><input type="checkbox" id="termos" style="width:auto;min-height:0;margin-top:5px"> <span id="termos-txt"></span></label></div>
<button type="button" id="ok">Entrar</button><p id="msg" role="status" aria-live="polite"></p></div>
<p class="t2" style="margin-top:12px"><a href="/conta/esqueci">Esqueci a senha</a></p></main><script>
var criar=false,versao=null,b=document.getElementById("ok"),m=document.getElementById("msg");
function dizer(t,e){m.textContent=t;m.style.color=e?"#7A2214":"#1F4A1C";}
fetch("/api/instancia",{cache:"no-store"}).then(function(r){return r.json();}).then(function(j){versao=(j&&j.termos_versao)||null;if(j&&j.tem_conta===false){criar=true;document.getElementById("caixa-nome").hidden=false;
document.getElementById("sub").textContent="Primeira entrada neste servidor: quem criar esta conta passa a ser da direção (administradora). Use uma senha de pelo menos 12 caracteres.";document.getElementById("senha").autocomplete="new-password";b.textContent="Criar conta e entrar";
if(versao){document.getElementById("termos-txt").textContent="Li e aceito os Termos de uso e a Política de privacidade da Physis (versão "+versao+").";document.getElementById("caixa-termos").hidden=false;}}});
["usuario","senha","nome","codigo"].forEach(function(i){document.getElementById(i).addEventListener("keydown",function(e){if(e.key==="Enter")b.click();});});
b.onclick=function(){var u=document.getElementById("usuario").value.trim(),s=document.getElementById("senha").value,n=document.getElementById("nome").value.trim(),cx=document.getElementById("caixa-codigo");
if(!u||!s){dizer("Informe o e-mail e a senha.",true);return;}var corpo={nome:n||u,usuario:u,senha:s};
if(!cx.hidden){corpo.codigo=document.getElementById("codigo").value.trim();if(!corpo.codigo){dizer("Digite o código do aplicativo.",true);document.getElementById("codigo").focus();return;}}
if(criar&&versao){if(!document.getElementById("termos").checked){dizer("Para criar a conta, marque que leu e aceita os termos.",true);document.getElementById("termos").focus();return;}corpo.consentimento={versao:versao,aceito:true};}
b.disabled=true;dizer("Conferindo…",false);
fetch(criar?"/api/conta/criar":"/api/conta/entrar",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(corpo)})
.then(function(r){return r.json();}).then(function(j){if(j.ok){dizer("Entrando…",false);location.reload();}
else if(j.precisa_2fa&&cx.hidden){cx.hidden=false;document.getElementById("codigo").focus();dizer("Esta conta usa verificação em duas etapas. Digite o código do aplicativo.",false);b.disabled=false;}
else{dizer(j.erro||"E-mail ou senha não conferem.",true);b.disabled=false;}})
.catch(function(){dizer("Sem resposta do servidor.",true);b.disabled=false;});};
</script></body></html>"""


# Páginas dos fluxos de conta, servidas pelo próprio servidor (as telas só precisam pôr os links):
#   /conta/esqueci  /conta/nova-senha#t=…  /conta/confirmar#t=…  /conta/convite#t=…
# O código vem depois de "#": o navegador não o envia ao servidor nem a proxies; a página o tira da barra de endereço.
PAGINA_CONTA = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Conta · Physis</title><style>
body{margin:0;background:#F4F6F1;color:#1C2B21;font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif}
main{max-width:480px;margin:0 auto;padding:40px 16px}h1{font:500 1.9em Fraunces,Georgia,serif;color:#33512F;margin:0 0 6px}
.cartao{background:#fff;border:1px solid #C9D2C4;border-radius:12px;padding:18px;margin-top:14px;display:grid;gap:10px}
label{font-weight:600}input{font:inherit;width:100%;box-sizing:border-box;min-height:46px;padding:6px 12px;border:1px solid #8A9284;border-radius:8px}
input[type=checkbox]{width:auto;min-height:0;margin-top:5px}.linha{display:flex;gap:8px;align-items:flex-start;font-weight:400}
button{font:inherit;font-weight:600;min-height:46px;padding:0 20px;border-radius:8px;border:1px solid #33512F;background:#33512F;color:#fff;cursor:pointer}
:focus-visible{outline:3px solid #33512F;outline-offset:2px}#msg{min-height:1.5em;font-weight:600;margin:0}.t2{color:#4A4F44;margin:0}a{color:#33512F}
</style></head><body><main><h1 id="tit">Conta Physis</h1><p class="t2" id="sub"></p>
<form class="cartao" id="f" novalidate>
<div id="c-email" hidden><label for="email">E-mail</label><input id="email" type="email" autocomplete="username" inputmode="email"></div>
<div id="c-token" hidden><label for="token">Código que chegou no e-mail</label><input id="token" autocomplete="one-time-code"></div>
<div id="c-nome" hidden><label for="nome">Seu nome</label><input id="nome" autocomplete="name"></div>
<div id="c-senha" hidden><label for="senha">Senha nova</label><input id="senha" type="password" autocomplete="new-password" aria-describedby="dica">
<p class="t2" id="dica">Pelo menos 12 caracteres. Uma frase com palavras suas é o melhor; não precisa de símbolos.</p></div>
<div id="c-senha2" hidden><label for="senha2">Repita a senha nova</label><input id="senha2" type="password" autocomplete="new-password"></div>
<div id="c-termos" hidden><label class="linha"><input type="checkbox" id="termos"> <span id="termos-txt"></span></label></div>
<button type="submit" id="ok">Continuar</button><p id="msg" role="status" aria-live="polite"></p></form>
<p class="t2" style="margin-top:12px"><a href="/gestao">Ir para a entrada</a></p></main><script>
var modo=location.pathname.replace(/\/+$/,"").split("/").pop(),versao=null;
var tk=(location.hash.match(/[#&]t=([A-Za-z0-9_-]+)/)||[])[1]||"";
if(tk&&history.replaceState)history.replaceState(null,"",location.pathname);
function $(i){return document.getElementById(i);}
function mostrar(){for(var i=0;i<arguments.length;i++)$("c-"+arguments[i]).hidden=false;}
function dizer(t,e){$("msg").textContent=t||"";$("msg").style.color=e?"#7A2214":"#1F4A1C";}
function falha(){dizer("Sem resposta do servidor. Tente de novo.",true);$("ok").disabled=false;}
function post(rota,corpo){return fetch(rota,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(corpo)}).then(function(r){return r.json();});}
function codigo(){return tk||$("token").value.trim();}
function ver(){if(!codigo()){dizer("Cole o código do e-mail.",true);$("token").focus();return;}
post("/api/conta/convite/ver",{token:codigo()}).then(function(j){if(!j.ok){dizer(j.erro,true);return;}tk=codigo();$("c-token").hidden=true;
$("sub").textContent="Convite para "+j.email+" ("+({administrador:"direção",operador:"equipe",cliente:"cliente"}[j.papel]||j.papel)+") em "+j.org+". Escolha o seu nome e a sua senha.";
$("nome").value=j.nome||"";mostrar("nome","senha","senha2");versao=j.termos_versao||null;
if(versao){$("termos-txt").textContent="Li e aceito os Termos de uso e a Política de privacidade da Physis (versão "+versao+").";mostrar("termos");}
$("ok").textContent="Criar a minha conta";modo="convite2";dizer("",false);$("nome").focus();}).catch(falha);}
function enviar(){var b=$("ok");
if(modo==="esqueci"){var em=$("email").value.trim();if(!em){dizer("Digite o e-mail.",true);$("email").focus();return;}b.disabled=true;
post("/api/conta/esqueci",{usuario:em}).then(function(j){dizer(j.mensagem||j.erro,!j.ok);b.disabled=false;}).catch(falha);return;}
if(modo==="confirmar"){if(!codigo()){dizer("Cole o código do e-mail.",true);$("token").focus();return;}
post("/api/conta/confirmar",{token:codigo()}).then(function(j){dizer(j.ok?"E-mail confirmado. Já pode entrar na plataforma.":j.erro,!j.ok);}).catch(falha);return;}
if(modo==="convite"){ver();return;}
var s=$("senha").value;if(s.length<12){dizer("A senha precisa de pelo menos 12 caracteres.",true);$("senha").focus();return;}
if(s!==$("senha2").value){dizer("As duas senhas não são iguais.",true);$("senha2").focus();return;}
if(modo==="nova-senha"){if(!codigo()){dizer("Cole o código do e-mail.",true);$("token").focus();return;}b.disabled=true;
post("/api/conta/nova-senha",{token:codigo(),senha:s}).then(function(j){if(j.ok){dizer("Senha nova gravada. Indo para a entrada…",false);setTimeout(function(){location.href="/gestao";},1500);}else{dizer(j.erro,true);b.disabled=false;}}).catch(falha);return;}
if(modo==="convite2"){var n=$("nome").value.trim();if(!n){dizer("Digite o seu nome.",true);$("nome").focus();return;}
if(versao&&!$("termos").checked){dizer("Para criar a conta, marque que leu e aceita os termos.",true);$("termos").focus();return;}
var corpo={token:tk,nome:n,senha:s};if(versao)corpo.consentimento={versao:versao,aceito:true};b.disabled=true;
post("/api/conta/convite/aceitar",corpo).then(function(j){if(j.ok){dizer("Conta criada. Entrando…",false);setTimeout(function(){location.href=j.papel==="cliente"?"/":"/gestao";},800);}else{dizer(j.erro,true);b.disabled=false;}}).catch(falha);}}
var T={esqueci:["Esqueci a senha","Digite o e-mail da sua conta. Se ele tiver conta, chega um link para criar uma senha nova."],
"nova-senha":["Senha nova","Escolha a senha nova. Ao gravar, todas as sessões abertas da conta são encerradas."],
confirmar:["Confirmar o e-mail","Confirme que este e-mail é seu."],convite:["Aceitar o convite","Conferindo o convite…"]};
var t=T[modo]||T.esqueci;if(!T[modo])modo="esqueci";$("tit").textContent=t[0];$("sub").textContent=t[1];document.title=t[0]+" · Physis";
$("f").addEventListener("submit",function(e){e.preventDefault();enviar();});
if(modo==="esqueci")mostrar("email");
else if(modo==="nova-senha"){if(!tk)mostrar("token");mostrar("senha","senha2");$("ok").textContent="Gravar a senha nova";}
else if(modo==="confirmar"){if(!tk)mostrar("token");else enviar();}
else if(modo==="convite"){if(!tk){mostrar("token");$("ok").textContent="Conferir o convite";$("sub").textContent="Cole o código que chegou no e-mail do convite.";}else ver();}
</script></body></html>"""


def criar_manipulador(hub: Hub, token: str | None, instancia: dict | None = None, clima=None, irradiacao=None):
    instancia = instancia if instancia is not None else ler_instancia()
    if irradiacao is None:
        irradiacao = gis_mod.Irradiacao(hub)
    saude = saude_mod.Saude(hub)
    # MED/PUL pelo receptor, pelo /api/v6/linha e pelo MQTT: o hub entrega à Saúde antes do adaptador genérico
    # (protocolo.TIPOS_SAUDE; PHYSIS_SAUDE_V6=0 desliga). Avisos novos (dose esquecida, crise) saem pela fila de e-mail.
    def receptor_saude(linha: str, origem: str) -> dict:
        r = saude.registrar_evento(linha, origem=origem)
        for aid in r.get("alertas", []):
            threading.Thread(target=correio.enviar_fila, args=(hub, f"saude-{aid}"), daemon=True).start()
        return r
    if getattr(hub, "saude_receptor", None) is None:
        hub.saude_receptor = receptor_saude
    if clima is None:
        rx = os.environ.get("PHYSIS_RX_URL")
        clima = clima_mod.Clima(hub, receptor_url=rx, enviar_local=clima_mod.receptor_local(rx) if rx else None)
    exige_login = bool(instancia.get("login"))
    csp = politica(os.environ.get("PHYSIS_CHAMADAS") or instancia.get("chamadas"))
    csp_planejador = csp.replace("'wasm-unsafe-eval'", "'wasm-unsafe-eval' 'unsafe-eval'", 1)
    fabricar = fabricante(instancia)
    url_publica = (os.environ.get("PHYSIS_URL_PUBLICA") or instancia.get("url_publica") or "").rstrip("/")
    # Editais e eventos (editais.py): listas públicas buscadas pelo servidor, com cache em arquivo
    pasta_editais = Path(os.environ.get("PHYSIS_EDITAIS_PASTA") or (Path(banco_da_instancia(instancia)).resolve().parent / "editais"))
    editais_col = editais_mod.Coletor(pasta_editais, tipo="edital")
    eventos_col = editais_mod.Coletor(pasta_editais, tipo="evento")
    # Aprendizado local (sem internet), robôs com regras (+ IA local opcional) e alertas de clima por e-mail/WhatsApp
    aprendizado = aprendizado_mod.Aprendizado(hub)
    robos = robos_mod.criar_robos({"hub": hub, "editais": editais_col,
                                   "suporte_email": os.environ.get("PHYSIS_SUPORTE_EMAIL") or instancia.get("suporte_email") or ""})
    alertas = alertas_mod.AlertasClima(hub, aprendizado=aprendizado)
    # ── Segurança (seguranca.py; docs/SEGURANCA.md) ──
    proxies = seg.proxies_confiaveis()                  # PHYSIS_PROXY_CONFIAVEL: só deles vale X-Forwarded-*
    limites = seg.Limites()                             # PHYSIS_LIMITE_*: balde de fichas por IP
    chamadas_origem = origem_chamadas(os.environ.get("PHYSIS_CHAMADAS") or instancia.get("chamadas"))
    sem_chave = os.environ.get("PHYSIS_ACEITAR_SEM_CHAVE", "").strip()   # "1" aceita, "0" recusa, vazio: só rede local
    SEM_PAPEL = {"ok": False, "erro": "o seu papel não permite esta ação"}
    termos = seg.termos_versao()                        # versão dos Termos/Política (sistema/physis-juridico.js)
    # rotas da própria conta que funcionam sem token CSRF (ainda não há sessão) e mesmo com o consentimento pendente
    SEM_CSRF = ("/api/conta/entrar", "/api/conta/criar", "/api/conta/esqueci", "/api/conta/nova-senha", "/api/conta/confirmar",
                "/api/conta/convite/ver", "/api/conta/convite/aceitar")
    class Manipulador(BaseHTTPRequestHandler):
        # Cabecalhos de seguranca em toda resposta. As telas usam script e estilo dentro da pagina,
        # por isso 'unsafe-inline'; de fora do proprio servidor, so o servidor de chamadas da Physis, se configurado.
        def end_headers(self):
            # O Planejador (e só ele) precisa de 'unsafe-eval': o leitor BIM web-ifc monta funções ao rodar.
            # A liberação vale só para essa página; o resto da plataforma continua sem eval.
            eh_planejador = urlparse(getattr(self, "path", "") or "").path in ("/planejador", "/planejador/")
            self.send_header("Content-Security-Policy", csp_planejador if eh_planejador else csp)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            # Permissions-Policy, COOP, CORP, X-Frame-Options e, só por HTTPS, HSTS (seguranca.cabecalhos_extra)
            for k, v in seg.cabecalhos_extra(self._https(), chamadas_origem):
                self.send_header(k, v)
            super().end_headers()

        server_version = "PhysisHub/0.1"
        sys_version = ""                     # não anuncia a versão do Python no cabeçalho Server

        def log_message(self, *a):          # silencioso; a saude fica em /api/saude
            pass

        def handle_one_request(self):
            self._corpo_lido = False          # cada pedido começa sem corpo lido
            self._respondeu = False
            try:
                super().handle_one_request()
            except (ConnectionError, TimeoutError):
                self.close_connection = True          # quem chamou foi embora
            except Exception:
                # o rastro do erro vai só para o console do servidor; quem chamou recebe "erro interno", nunca o rastro
                traceback.print_exc(file=sys.stderr)
                self.close_connection = True
                if not self._respondeu:
                    try:
                        self._json(500, {"ok": False, "erro": "erro interno"})
                    except Exception:
                        pass

        def send_response(self, *a, **k):
            self._respondeu = True
            super().send_response(*a, **k)

        # ── Segurança: IP de verdade, HTTPS, rede local, papéis, limites e chaves dos aparelhos ──
        def _ip(self) -> str:
            return seg.ip_do_cliente(self.client_address[0], getattr(self, "headers", None) or {}, proxies)

        def _https(self) -> bool:
            return seg.eh_https(self.client_address[0], getattr(self, "headers", None) or {}, proxies)

        def _local(self) -> bool:
            return seg.eh_rede_local(self._ip())

        def _precisa_sessao(self) -> bool:
            """Com login na instalação, sempre; sem login, só quem chama de fora da rede local."""
            return exige_login or not self._local()

        def _cookie(self, valor: str, idade: int) -> str:
            return (f"physis_sessao={valor}; Path=/; Max-Age={idade}; HttpOnly; SameSite=Strict"
                    + ("; Secure" if self._https() else ""))

        def _exigir(self, minimo: str) -> dict | None:
            """Conta da sessão com pelo menos o papel pedido; senão responde 401 (sem sessão) ou 403 e devolve None.
            Com PHYSIS_CONSENTIMENTO_ESTRITO=1, sem o aceite da versão atual dos termos também 403 ({"consentimento": true})."""
            q = self._quem()
            if not q:
                self._json(401, {"ok": False, "erro": "entre com usuario e senha", "login": True})
                return None
            if seg.consentimento_estrito() and seg.consentimento_pendente(q):
                self._json(403, {"ok": False, "consentimento": True, "versao": termos,
                                 "erro": "Leia e aceite a versão atual dos Termos de uso e da Política de privacidade."})
                return None
            if not seg.pode(q, minimo):
                self._json(403, dict(SEM_PAPEL, confirmar_email=True) if q.get("confirmado") is False else SEM_PAPEL)
                return None
            return q

        def _sensivel(self, q: dict) -> bool:
            """Ações sensíveis pedem a senha de novo se o último login/reautenticação passou de PHYSIS_REAUT_MIN."""
            if seg.reauth_recente(hub, q):
                return True
            self._json(403, {"ok": False, "reautenticar": True, "erro": "Confirme a sua senha para continuar."})
            return False

        def _csrf_barrado(self) -> bool:
            """POST/PUT/DELETE: (1) Origin/Referer de outro site com sessão (ou nas rotas de conta) = 403;
            (2) com sessão, X-Physis-CSRF errado = 403; ausente = 403 só com PHYSIS_CSRF_ESTRITO=1."""
            caminho = urlparse(self.path).path
            tk = self._token_sessao()
            if seg.origem_confere(self.headers, url_publica) is False and (tk or caminho.startswith("/api/conta/")):
                return self._negar_csrf("origem de outro site")
            if tk and caminho not in SEM_CSRF:
                h = self.headers.get("X-Physis-CSRF")
                if (h is not None or seg.csrf_estrito()) and not seg.iguais(h, seg.csrf_de(hub, tk)):
                    return self._negar_csrf("token CSRF ausente ou errado")
            return False

        def _negar_csrf(self, motivo: str) -> bool:
            seg.acesso_registrar(hub, "", self._ip(), "csrf recusado", cadeia=False)
            self._json(403, {"ok": False, "csrf": True, "erro": "pedido recusado: " + motivo + "; recarregue a página"})
            return True

        def _ler(self, corpo, esquema: str, estrito: bool = True) -> dict | None:
            """JSON do corpo validado (seguranca.carregar_json + ESQUEMAS). None = já respondeu 400."""
            try:
                d = seg.carregar_json(corpo or "{}")
            except ValueError:
                self._json(400, {"ok": False, "erro": "json invalido"})
                return None
            erro = seg.validar(d, seg.ESQUEMAS[esquema], estrito)
            if erro:
                self._json(400, {"ok": False, "erro": erro})
                return None
            return d

        def _mandar(self, ref: str | None) -> None:
            if ref:
                threading.Thread(target=correio.enviar_fila, args=(hub, ref), daemon=True).start()

        def _pagina(self, html: str) -> None:
            pagina = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(pagina)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(pagina)

        def _limitado(self, categoria: str) -> bool:
            """True (e já respondeu 429 com Retry-After, depois de ler o corpo) quando este IP passou do limite."""
            espera = limites.tentar(categoria, self._ip())
            if espera <= 0:
                return False
            n = max(1, int(espera + 0.999))
            self._recusar(429, {"ok": False, "erro": f"muitos pedidos; tente de novo em {n} s", "espera": n}, {"Retry-After": str(n)})
            return True

        def _dispositivo(self, saude_linha: bool = False) -> tuple[bool, int | None]:
            """Quem entrega linhas de aparelho. (True, nó ou None) se pode; (False, None) e já respondeu 401.
            Aceita: a chave do dispositivo (Authorization: Bearer / X-Physis-Chave); o PHYSIS_TOKEN antigo
            (X-Physis-Token); sem chave, conforme PHYSIS_ACEITAR_SEM_CHAVE (vazio = só da rede local)."""
            ch = seg.chave_do_pedido(self.headers)
            if ch:
                c = seg.chave_conferir(hub, ch)
                if c:
                    return True, c["no"]
                self._json(401, {"ok": False, "erro": "chave do dispositivo inválida ou revogada"})
                return False, None
            if token is not None and seg.iguais(self.headers.get("X-Physis-Token"), token):
                return True, None
            if saude_linha and token is not None:          # como antes: com PHYSIS_TOKEN definido, a Saúde exige token ou chave
                self._json(401, {"ok": False, "erro": "token ausente ou invalido"})
                return False, None
            if sem_chave == "1" or (sem_chave != "0" and self._local()):
                return True, None
            self._json(401, {"ok": False, "erro": "chave do dispositivo ausente"})
            return False, None

        def _drenar_pendente(self) -> None:
            """Lê o corpo que ninguém leu antes de responder com erro. Sem isso, um 401/403/404 a um POST
            com corpo fecha a conexão com bytes não lidos e o Windows corta com RST: quem enviou não vê a resposta."""
            if getattr(self, "_corpo_lido", True):
                return
            self._corpo_lido = True
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return
            if 0 < n <= CORPO_MAX:
                try:
                    self.rfile.read(n)
                except OSError:
                    pass

        def _json(self, codigo: int, obj, cabecalhos: dict | None = None) -> None:
            if codigo >= 400:
                # corpo grande ainda não lido (ex.: 403 a um anexo de 20 MB): responde e drena com tempo limite
                try:
                    grande = not getattr(self, "_corpo_lido", True) and int(self.headers.get("Content-Length") or 0) > CORPO_MAX
                except ValueError:
                    grande = False
                if grande:
                    return self._recusar(codigo, obj, cabecalhos)
                self._drenar_pendente()
            corpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (cabecalhos or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(corpo)

        def _json_cookie(self, codigo: int, obj, cookie: str) -> None:
            corpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Set-Cookie", cookie)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(corpo)

        def _recusar_corpo(self, erro: str) -> None:
            """Responde 413 e fecha sem cortar a conexao na cara de quem enviou."""
            self._recusar(413, {"ok": False, "erro": erro})

        def _recusar(self, codigo: int, obj: dict, cabecalhos: dict | None = None) -> None:
            """Responde um erro (413, 429) a um pedido cujo corpo ainda não foi lido: responde, depois lê e
            descarta o corpo (até DRENAR_MAX, com tempo limite) e fecha, sem RST no Windows."""
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = 0
            if getattr(self, "_corpo_lido", False):
                n = 0
            self._corpo_lido = True
            self.close_connection = True
            corpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (cabecalhos or {}).items():
                self.send_header(k, v)
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(corpo)
            try:
                self.wfile.flush()
                self.connection.settimeout(DRENAR_SEGUNDOS)
                restam = min(max(n, 0), DRENAR_MAX)
                while restam > 0:
                    pedaco = self.rfile.read(min(65536, restam))
                    if not pedaco:
                        break
                    restam -= len(pedaco)
            except OSError:
                pass

        def _corpo(self) -> str | None:
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return None
            if n < 0 or n > CORPO_MAX:
                return None
            self._corpo_lido = True
            return self.rfile.read(n).decode("utf-8", errors="replace")

        def _corpo_grande(self, limite: int) -> bytes | None:
            """Corpo maior que o normal (dados e arquivos da Gestão). None = ausente ou acima do limite."""
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return None
            if n <= 0 or n > limite:
                return None
            self._corpo_lido = True
            return self.rfile.read(n)

        def _sessao_ou_401(self) -> dict | None:
            q = self._quem()
            if not q:
                self._json(401, {"ok": False, "erro": "entre com usuario e senha", "login": True})
            return q

        def _autorizado(self) -> bool:
            return token is None or seg.iguais(self.headers.get("X-Physis-Token"), token)

        def _token_sessao(self) -> str | None:
            for parte in (self.headers.get("Cookie") or "").split(";"):
                k, _, v = parte.strip().partition("=")
                if k == "physis_sessao":
                    return v
            return None

        def _quem(self) -> dict | None:
            return hub.sessao(self._token_sessao())

        def _barrado(self) -> bool:
            """True (e ja respondeu 401) quando a instalacao exige login (ou quem chama esta fora da rede local) e nao ha sessao."""
            if not self._precisa_sessao() or self._quem():
                return False
            self._json(401, {"ok": False, "erro": "entre com usuario e senha", "login": True})
            return True

        def _estado_instancia(self) -> dict:
            q = self._quem()
            return {"org": hub.org, "lugar": hub.lugar, "modulos": instancia.get("modulos"),
                    "exige_login": exige_login, "tem_conta": hub.tem_conta(), "autenticado": bool(q),
                    "nome": q["nome"] if q else None, "papel": q["papel"] if q else None,
                    "licenca": instancia.get("licenca"), "sustainkit": (WEB / "sustainkit.html").exists(),
                    "supervisao": (WEB / "supervisao.html").exists(), "gestao": (WEB / "gestao.html").exists(),
                    "planejador": (WEB / "planejador.html").exists(), "pesquisa": bool(instancia.get("pesquisa")),
                    "nome_cliente": instancia.get("nome"),
                    # instalação "physis" (padrão) ou "instituto" (Instituto Physis: outra marca, outro banco, outro catálogo)
                    "instalacao": instancia.get("instalacao") or "physis", "marca": marca_da_instancia(instancia),
                    "cursos": [c for c in (instancia.get("cursos") or []) if isinstance(c, dict)] if q else [],
                    "senha_min": hub.SENHA_MIN,
                    # segurança: token CSRF da sessão (mandar em X-Physis-CSRF), termos, e-mail, 2FA
                    "csrf": seg.csrf_de(hub, self._token_sessao()) if q else None,
                    "termos_versao": termos, "consentimento_pendente": seg.consentimento_pendente(q) if q else False,
                    "email_confirmado": q.get("confirmado") if q else None, "dois_fatores": q.get("dois_fatores") if q else None,
                    "recuperar_senha": True, "reautenticar_min": int(seg.reauth_janela_s() // 60)}

        def _rotas_conta(self, caminho: str):
            """Fluxos de conta. Devolve False se a rota não é daqui (o do_POST segue procurando)."""
            ip = self._ip()
            publicas = {"/api/conta/esqueci": "esqueci", "/api/conta/nova-senha": "nova_senha", "/api/conta/confirmar": "token",
                        "/api/conta/convite/ver": "token", "/api/conta/convite/aceitar": "convite_aceitar"}
            if caminho in publicas:
                if self._limitado("entrar"):
                    return None
                d = self._ler(self._corpo(), publicas[caminho])
                if d is None:
                    return None
                if caminho == "/api/conta/esqueci":
                    r, ref = seg.senha_esqueci(hub, d["usuario"], url_publica, ip)
                    self._mandar(ref)
                    return self._json(200, r)
                if caminho == "/api/conta/nova-senha":
                    r = seg.senha_redefinir(hub, d["token"], d["senha"], ip)
                    return self._json(200 if r["ok"] else 400, r)
                if caminho == "/api/conta/confirmar":
                    r = seg.confirmar(hub, d["token"])
                    return self._json(200 if r["ok"] else 400, r)
                if caminho == "/api/conta/convite/ver":
                    r = seg.convite_ver(hub, d["token"])
                    return self._json(200 if r["ok"] else 404, r)
                r = seg.convite_aceitar(hub, d["token"], d.get("nome") or "", d["senha"], d, ip)
                if not r["ok"]:
                    return self._json(400, r)
                e = hub.entrar(r["usuario"], d["senha"], ip, self.headers.get("User-Agent") or "")
                seg.acesso_registrar(hub, r["usuario"], ip, "entrou")
                tk = e.pop("token")
                e["csrf"] = seg.csrf_de(hub, tk)
                return self._json_cookie(200, e, self._cookie(tk, hub.SESSAO_S))
            privadas = {"/api/conta/confirmar/reenviar": "vazio", "/api/conta/consentimento": "consentimento",
                        "/api/conta/reautenticar": "reautenticar", "/api/conta/2fa/iniciar": "vazio",
                        "/api/conta/2fa/ativar": "codigo", "/api/conta/2fa/desativar": "codigo", "/api/convites": "convite"}
            revogar = caminho.startswith("/api/convites/") and caminho.endswith("/revogar")
            if caminho not in privadas and not revogar:
                return False
            if caminho == "/api/conta/reautenticar" and self._limitado("entrar"):
                return None
            q = self._quem()
            if not q:
                return self._json(401, {"ok": False, "erro": "entre com usuario e senha", "login": True})
            if caminho.startswith("/api/convites"):
                if not seg.pode(q, seg.DIRECAO):
                    return self._json(403, SEM_PAPEL)
                if revogar:
                    ok = seg.convite_revogar(hub, caminho.split("/")[-2], q["usuario"])
                    return self._json(200 if ok else 404, {"ok": ok})
            d = self._ler(self._corpo(), privadas[caminho])
            if d is None:
                return None
            if caminho == "/api/convites":
                if seg.normalizar_papel(d.get("papel")) == seg.DIRECAO and not self._sensivel(q):
                    return None
                r = seg.convite_criar(hub, d["email"], d.get("papel") or seg.EQUIPE, d.get("pessoa") or "", d.get("nome") or "",
                                      q["usuario"], url_publica)
                if r["ok"]:
                    self._mandar(r.pop("ref"))
                    r["email_enviado"] = correio.configurado()
                return self._json(200 if r["ok"] else 400, r)
            if caminho == "/api/conta/confirmar/reenviar":
                ref = seg.confirmar_enviar(hub, q["id"], url_publica)
                self._mandar(ref)
                return self._json(200, {"ok": True, "enviado": bool(ref)})
            if caminho == "/api/conta/consentimento":
                if d["aceito"] and not d.get("versao"):
                    return self._json(400, {"ok": False, "erro": "falta o campo versao"})
                r = seg.consentimento_registrar(hub, q["id"], q["usuario"], d.get("versao") or q.get("consentimento") or "", d["aceito"], ip)
                return self._json(200 if r["ok"] else 409, r)
            if caminho == "/api/conta/reautenticar":
                r = seg.reautenticar(hub, self._token_sessao(), q, d["senha"], d.get("codigo") or "")
                return self._json(200 if r["ok"] else r.pop("codigo", 403), r)
            if caminho == "/api/conta/2fa/iniciar":
                if not self._sensivel(q):
                    return None
                r = seg.totp_iniciar(hub, q["id"], q["usuario"])
                return self._json(200 if r["ok"] else 400, r)
            if caminho == "/api/conta/2fa/ativar":
                r = seg.totp_ativar(hub, q["id"], q["usuario"], d["codigo"])
                return self._json(200 if r["ok"] else 400, r)
            if not self._sensivel(q):           # /api/conta/2fa/desativar
                return None
            r = seg.totp_desativar(hub, q["id"], q["usuario"], d["codigo"])
            return self._json(200 if r["ok"] else 400, r)

        def do_HEAD(self):
            # só o mapa da região responde a HEAD (o Planejador pergunta se o arquivo existe antes de usar)
            u = urlparse(self.path)
            if u.path.startswith("/mapas/"):
                return self._mapa(u.path, so_cabecalho=True)
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _mapa(self, caminho: str, so_cabecalho: bool = False) -> None:
            """Mapa de fundo da região (PMTiles do OpenStreetMap) guardado no servidor, entregue por partes
            (Range), como o leitor de PMTiles pede. Nome restrito: só [a-z0-9-].pmtiles dentro da pasta de mapas."""
            if self._barrado():
                return
            nome = caminho[len("/mapas/"):]
            arq = PASTA_MAPAS() / nome
            if not re.fullmatch(r"[a-z0-9-]{1,40}\.pmtiles", nome) or not arq.is_file():
                if so_cabecalho:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                return self._json(404, {"ok": False, "erro": "mapa da região não instalado"})
            total = arq.stat().st_size
            ini, fim, parcial = 0, total - 1, False
            m = re.fullmatch(r"bytes=(\d*)-(\d*)", (self.headers.get("Range") or "").strip())
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    ini = int(m.group(1)); fim = min(int(m.group(2)) if m.group(2) else total - 1, total - 1)
                else:
                    ini = max(0, total - int(m.group(2)))
                if ini > fim or ini >= total:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{total}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                parcial = True
            n = fim - ini + 1
            self.send_response(206 if parcial else 200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(n))
            if parcial:
                self.send_header("Content-Range", f"bytes {ini}-{fim}/{total}")
            self.send_header("Cache-Control", "private, max-age=86400")
            self.end_headers()
            if so_cabecalho:
                return
            with open(arq, "rb") as f:
                f.seek(ini)
                restam = n
                while restam > 0:
                    pedaco = f.read(min(1 << 20, restam))
                    if not pedaco:
                        break
                    self.wfile.write(pedaco)
                    restam -= len(pedaco)

        def _arquivo(self, arq: Path, tipo: str) -> None:
            dados = arq.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path == "/api/instancia":
                return self._json(200, self._estado_instancia())
            if u.path in ("/conta/esqueci", "/conta/nova-senha", "/conta/confirmar", "/conta/convite"):
                return self._pagina(PAGINA_CONTA)
            if u.path in ("/.well-known/security.txt", "/security.txt"):
                txt = seg.security_txt(os.environ.get("PHYSIS_SEGURANCA_CONTATO") or os.environ.get("PHYSIS_SUPORTE_EMAIL")
                                       or instancia.get("suporte_email") or "", url_publica, time.time()).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(txt)))
                self.end_headers()
                self.wfile.write(txt)
                return
            if u.path == "/api/convites":
                if not self._exigir(seg.DIRECAO):
                    return
                return self._json(200, {"ok": True, "convites": seg.convite_listar(hub)})
            # ── Editais (só quem tem acesso) e eventos (equipe com sessão): editais.rota decide ──
            if u.path.startswith(("/api/editais", "/api/eventos")):
                q = self._quem()
                if q and not seg.pode(q, seg.EQUIPE):          # conta de cliente não vê a área interna
                    return self._json(403, SEM_PAPEL)
                r = editais_mod.rota("GET", u.path, q, None, editais_col, eventos_col, hub, correio)
                if r:
                    return self._json(*r)
            if u.path.startswith("/api/central/compra/"):
                # publico de proposito: a loja so pergunta se a propria compra ja foi aprovada
                est = hub.central_estado("compra", u.path.rsplit("/", 1)[-1])
                return self._json(200 if est else 404, {"ok": bool(est), "estado": est})
            if u.path == "/api/loja/catalogo":
                # publico: so o que foi revisado e posto no ar pela equipe
                return self._json(200, hub.loja_catalogo(interno=False))
            if u.path == "/api/loja/catalogo/interno":
                if not self._exigir(seg.EQUIPE):
                    return
                return self._json(200, hub.loja_catalogo(interno=True))
            # ── Consultoria ── página pública e textos editáveis do site (leitura pública, como a loja)
            if u.path in ("/consultoria", "/consultoria/"):
                if not (WEB / "consultoria.html").exists():
                    return self._json(404, {"ok": False, "erro": "consultoria.html ausente"})
                return self._arquivo(WEB / "consultoria.html", "text/html; charset=utf-8")
            if u.path.startswith("/api/site/textos/"):
                r = hub.site_textos(u.path[len("/api/site/textos/"):])
                return self._json(200 if r["ok"] else 404, r)
            # ── fim Consultoria ──
            if u.path.startswith("/ativar/"):
                numero = u.path.rstrip("/").rsplit("/", 1)[-1]
                if not re.fullmatch(r"PH-\d{4,6}", numero):
                    return self._json(404, {"ok": False, "erro": "rota desconhecida"})
                pagina = PAGINA_ATIVAR.replace("__NUMERO__", numero).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(pagina)))
                self.end_headers()
                self.wfile.write(pagina)
                return
            # ── LGPD art. 18: o que o servidor guarda sobre quem está na sessão (seguranca.meus_dados) ──
            if u.path == "/api/conta/meus-dados":
                q = self._sessao_ou_401()
                if not q:
                    return
                return self._json(200, seg.meus_dados(hub, q))
            # ── Chaves dos dispositivos: só a direção lista (a chave em si nunca volta, só o resumo fica guardado) ──
            if u.path == "/api/dispositivos/chaves":
                if not self._exigir(seg.DIRECAO):
                    return
                return self._json(200, {"ok": True, "chaves": seg.chave_listar(hub)})
            if u.path == "/api/gestao/estado":
                q = self._exigir(seg.EQUIPE)
                if not q:
                    return
                try:
                    desde = float((q2 := parse_qs(u.query)).get("desde", ["0"])[0])
                except ValueError:
                    desde = 0.0
                return self._json(200, {"ok": True, "agora": time.time(), "conta": {k: q[k] for k in ("nome", "usuario", "papel", "pessoa")},
                                        "itens": hub.gestao_ler(desde)})
            # ── Plataforma do cliente: dados que antes ficavam só no navegador (perfil_cliente.py) ──
            if u.path == "/api/cliente/estado" or u.path.startswith("/api/cliente/estado/") or u.path == "/api/cliente/perfil":
                qc = self._exigir(seg.CLIENTE)          # sempre com sessão, mesmo em instalação sem login
                if not qc:
                    return
                if u.path == "/api/cliente/perfil":
                    return self._json(200, {"ok": True, "org": hub.org, "aprendido": hub.cliente_aprendido()})
                if u.path == "/api/cliente/estado":
                    try:
                        desde = float(q.get("desde", ["0"])[0])
                    except ValueError:
                        desde = 0.0
                    return self._json(200, {"ok": True, "agora": time.time(), "org": hub.org,
                                            "conta": {k: qc[k] for k in ("nome", "usuario", "papel")},
                                            "chaves": list(perfil_cliente.CHAVES), "prefixos": list(perfil_cliente.PREFIXOS),
                                            "itens": hub.cliente_ler(desde=desde)})
                chave = unquote(u.path[len("/api/cliente/estado/"):])
                if not perfil_cliente.chave_valida(chave):
                    return self._json(400, {"ok": False, "erro": "chave nao permitida"})
                it = hub.cliente_ler(chave=chave).get(chave)
                if not it:
                    return self._json(404, {"ok": False, "chave": chave, "versao": 0, "valor": None}, {"ETag": '"v0"'})
                etag = f'"v{it["versao"]}"'
                if (self.headers.get("If-None-Match") or "").strip() == etag:
                    self.send_response(304)
                    self.send_header("ETag", etag)
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    return
                return self._json(200, {"ok": True, "chave": chave, **it}, {"ETag": etag})
            # ── Central de clientes e caixa de chamados (Gestão interna; dado pessoal: só equipe) ──
            if u.path == "/api/central/clientes":
                if not self._exigir(seg.EQUIPE):
                    return
                return self._json(200, {"ok": True, "clientes": hub.central_clientes()})
            if u.path.startswith("/api/suporte/chamados/"):
                if not self._exigir(seg.EQUIPE):
                    return
                ch = hub.suporte_detalhe(unquote(u.path[len("/api/suporte/chamados/"):]))
                return self._json(200 if ch else 404, {"ok": bool(ch), "chamado": ch})
            if u.path == "/api/suporte/chamados":
                if not self._exigir(seg.EQUIPE):
                    return
                return self._json(200, {"ok": True, "chamados": hub.suporte_listar(None)})
            if u.path.startswith("/api/gestao/arquivo/"):
                if not self._exigir(seg.EQUIPE):
                    return
                arq = hub.gestao_arquivo(u.path.rsplit("/", 1)[-1])
                if not arq:
                    return self._json(404, {"ok": False})
                self.send_response(200)
                self.send_header("Content-Type", arq[1])
                self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(arq[0]))
                self.send_header("Content-Length", str(len(arq[2])))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(arq[2])
                return
            if u.path == "/api/contas":
                q = self._sessao_ou_401()
                if not q:
                    return
                if q["papel"] != "administrador":
                    return self._json(403, {"ok": False, "erro": "so a direcao ve as contas"})
                return self._json(200, {"ok": True, "contas": hub.contas()})
            # ── Saúde (caixinha de remédios e pulseira): dado sensível, sempre com sessão e só de quem foi autorizado ──
            if u.path == "/api/saude/estado":
                q = self._sessao_ou_401()
                if not q:
                    return
                return self._json(200, saude.estado(q["usuario"]))
            if u.path in ("/api/central/emails", "/api/central/instalacoes"):
                if not self._exigir(seg.EQUIPE):
                    return
                if u.path.endswith("emails"):
                    # avisos de saúde (dado sensível, LGPD) vão só para os cuidadores: a fila mostra só quantos são
                    todos = hub.emails()
                    # e-mails de conta (senha nova, confirmação, convite) levam link de uso único: também ficam fora da fila
                    oculto = lambda e: str(e.get("ref") or "").startswith(("saude-", seg.REF_CONTA))
                    saude_n = sum(1 for e in todos if str(e.get("ref") or "").startswith("saude-"))
                    return self._json(200, {"ok": True, "configurado": correio.configurado(), "saude_ocultos": saude_n,
                                            "conta_ocultos": sum(1 for e in todos if str(e.get("ref") or "").startswith(seg.REF_CONTA)),
                                            "emails": [e for e in todos if not oculto(e)]})
                return self._json(200, {"ok": True, "instalacoes": hub.instalacoes()})
            if u.path in ("/demo", "/demo/"):
                # demonstração gratuita: roda inteira no navegador, com dados simulados; não lê nada do servidor
                return self._arquivo(WEB / "painel.html", "text/html; charset=utf-8")
            if u.path in ("/loja/interna", "/loja/interna/"):
                # a pagina em si nao tem dado; os dados internos so vem com sessao
                return self._arquivo(WEB / "painel.html", "text/html; charset=utf-8")
            if u.path.startswith("/api/") and self._barrado():
                return
            if u.path in ("/sustainkit", "/sustainkit/") and (WEB / "sustainkit.html").exists():
                if self._barrado():
                    return
                return self._arquivo(WEB / "sustainkit.html", "text/html; charset=utf-8")
            if u.path in ("/loja", "/loja/"):
                # a loja e publica: quem compra nao tem, nem deve ter, conta na gestao
                return self._arquivo(WEB / "painel.html", "text/html; charset=utf-8")
            if u.path == "/api/central/arquivos":
                # dado pessoal (anexos de quem pediu proposta): sempre com sessão da equipe, com ou sem login na instalação
                if not self._exigir(seg.EQUIPE):
                    return
                return self._json(200, {"ok": True, "arquivos": hub.arquivos_de((parse_qs(u.query).get("pedido") or [""])[0])})
            if u.path.startswith("/api/central/arquivo/"):
                if not self._exigir(seg.EQUIPE):
                    return
                arq = hub.arquivo(u.path.rsplit("/", 1)[-1])
                if not arq:
                    return self._json(404, {"ok": False})
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", "attachment; filename*=UTF-8\'\'" + quote(arq[0]))
                self.send_header("Content-Length", str(len(arq[1])))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(arq[1])
                return
            if u.path == "/api/central/caixa":
                # compras e pedidos trazem nome, e-mail e CPF de quem pagou: sempre com sessão da equipe
                if not self._exigir(seg.EQUIPE):
                    return
                return self._json(200, {"ok": True, "itens": hub.central_listar()})
            if u.path in ("/gestao", "/gestao/") and (WEB / "gestao.html").exists():
                # sem sessão, a página de entrada; a Gestão (e o que ela traz embutido) só depois do login
                if not self._quem():
                    pagina = PAGINA_ENTRAR.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(pagina)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(pagina)
                    return
                return self._arquivo(WEB / "gestao.html", "text/html; charset=utf-8")
            if u.path.startswith("/app/"):
                # app instalável (PWA): manifestos, ícones e service worker. Só os da lista e sem login:
                # o celular precisa deles para instalar antes de qualquer entrada.
                r = app_pwa.resposta(unquote(u.path[len("/app/"):]), WEB)
                if not r:
                    return self._json(404, {"ok": False, "erro": "arquivo desconhecido"})
                corpo, cabecalhos = r
                self.send_response(200)
                for k, v in cabecalhos.items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(corpo)
                return
            if u.path.startswith("/vendor/"):
                # bibliotecas abertas guardadas no próprio sistema (mapa e BIM); só as da lista, nunca um caminho qualquer
                nome = u.path[len("/vendor/"):]
                tipo = VENDOR_TIPOS.get(nome)
                arq = next((p for p in (WEB / "vendor" / nome, WEB.parent.parent / "vendor" / nome) if tipo and p.is_file()), None)
                if not arq:
                    return self._json(404, {"ok": False, "erro": "biblioteca desconhecida"})
                dados = arq.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(dados)))
                self.send_header("Cache-Control", "public, max-age=604800, immutable")
                self.end_headers()
                self.wfile.write(dados)
                return
            if u.path.startswith("/mapas/"):
                return self._mapa(u.path)
            if u.path in ("/planejador", "/planejador/") and (WEB / "planejador.html").exists():
                if self._barrado():
                    return
                return self._arquivo(WEB / "planejador.html", "text/html; charset=utf-8")
            if u.path in ("/supervisao", "/supervisao/") and (WEB / "supervisao.html").exists():
                if self._barrado():
                    return
                return self._arquivo(WEB / "supervisao.html", "text/html; charset=utf-8")
            if u.path == "/api/painel":
                return self._json(200, hub.painel())
            if u.path == "/api/clima":
                # previsão das fontes guardadas no hub (a tela nunca chama a internet)
                return self._json(200, clima.estado())
            if u.path == "/api/suporte":
                # os contatos da Physis são públicos; os chamados (com contato de quem abriu) só com sessão:
                # a equipe vê todos, o cliente só os que ele abriu
                q = self._quem()
                contatos = {"whatsapp": re.sub(r"\D", "", os.environ.get("PHYSIS_SUPORTE_WHATSAPP") or instancia.get("suporte_whatsapp") or ""),
                            "email": os.environ.get("PHYSIS_SUPORTE_EMAIL") or instancia.get("suporte_email") or ""}
                if not q:
                    return self._json(200, {"ok": True, "chamados": [], "login": True, **contatos})
                return self._json(200, {"ok": True, "chamados": hub.suporte_listar(None if seg.pode(q, seg.EQUIPE) else q["usuario"]), **contatos})
            if u.path in ("/api/gis/relevo", "/api/gis/solo", "/api/gis/rio"):
                # relevo (curvas de nível e declividade), solo e rio (enchente) do lugar, guardados no hub
                try:
                    lat, lon = float(q.get("lat", [""])[0]), float(q.get("lon", [""])[0])
                except ValueError:
                    return self._json(400, {"ok": False, "erro": "lat e lon são obrigatórios"})
                if not (-35.0 <= lat <= 6.0 and -75.0 <= lon <= -28.0):
                    return self._json(400, {"ok": False, "erro": "coordenadas fora do Brasil"})
                extra = gis_mod.GisExtra(irradiacao)
                return self._json(200, getattr(extra, u.path.rsplit("/", 1)[-1])(lat, lon))
            if u.path in ("/api/gis/irradiacao", "/api/gis/clima"):
                # base GIS de clima do lugar (ponto + grade da região), buscada uma vez e guardada no hub
                try:
                    lat, lon = float(q.get("lat", [""])[0]), float(q.get("lon", [""])[0])
                except ValueError:
                    return self._json(400, {"ok": False, "erro": "lat e lon são obrigatórios"})
                r = irradiacao.consultar(lat, lon, q.get("camada", ["irradiacao"])[0] if u.path.endswith("clima") else "irradiacao")
                return self._json(200 if r["ok"] or not r.get("erro") else 400, r)
            if u.path in ("/api/gis/zonas", "/api/gis/solo-grade", "/api/gis/vento", "/api/gis/residuos"):
                # zonas do lugar (IBGE + Köppen), mapa de solo da região, vento em altura e destinos de resíduos:
                # buscados uma vez e guardados no hub
                try:
                    lat, lon = float(q.get("lat", [""])[0]), float(q.get("lon", [""])[0])
                except ValueError:
                    return self._json(400, {"ok": False, "erro": "lat e lon são obrigatórios"})
                if not (-35.0 <= lat <= 6.0 and -75.0 <= lon <= -28.0):
                    return self._json(400, {"ok": False, "erro": "coordenadas fora do Brasil"})
                if u.path.endswith("zonas"):
                    r = zonas_mod.Zonas(irradiacao).consultar(lat, lon)
                elif u.path.endswith("solo-grade"):
                    r = gis_mod.GisExtra(irradiacao).solo_grade(lat, lon, q.get("prop", ["phh2o"])[0], q.get("prof", ["0-5cm"])[0])
                elif u.path.endswith("vento"):
                    r = vento_mod.Vento(irradiacao).consultar(lat, lon)
                else:
                    try:
                        raio = float(q.get("raio", [str(residuos_mod.RAIO_PADRAO)])[0])
                    except ValueError:
                        return self._json(400, {"ok": False, "erro": "raio precisa ser número"})
                    r = residuos_mod.ResiduosGis(irradiacao).consultar(lat, lon, raio)
                return self._json(200 if r.get("ok") or not r.get("erro") else 400, r)
            # ── Aprendizado (modelos do próprio hub, sem internet) ──
            if u.path.startswith("/api/aprendizado/"):
                if self._barrado():
                    return
                qual = u.path.rsplit("/", 1)[-1]
                fn = {"estado": aprendizado.estado, "anomalias": aprendizado.anomalias, "previsao-chuva": aprendizado.previsao_chuva,
                      "consumo": aprendizado.consumo, "irrigacao": aprendizado.irrigacao}.get(qual)
                if fn:
                    return self._json(200, fn())
            if u.path == "/api/robos":
                if not self._exigir(seg.CLIENTE):
                    return
                return self._json(200, {"ok": True, "robos": robos_mod.listar(robos)})
            if u.path in ("/api/alertas/assinaturas", "/api/alertas/historico"):
                qs = self._sessao_ou_401()
                if not qs:
                    return
                quem = None if seg.pode(qs, seg.DIRECAO) else qs["usuario"]          # a direção vê todas
                if u.path.endswith("/historico"):
                    return self._json(200, {"ok": True, "historico": alertas.historico(quem=quem)})
                return self._json(200, {"ok": True, "assinaturas": alertas.assinaturas(quem),
                                        "regras": {k: v[0] for k, v in alertas_mod.REGRAS.items()},
                                        "atividades": list(alertas_mod.ATIVIDADES), "finalidade": alertas_mod.FINALIDADE,
                                        # aprendidas da descrição do negócio: valem quando a assinatura não escolhe nenhuma
                                        "atividades_perfil": alertas.atividades_do_perfil(),
                                        "whatsapp": bool(alertas.whatsapp), "agora": alertas.alertas_agora()})
            if u.path == "/api/saude":
                integra, n = hub.verificar_cadeia()
                p = hub.painel()["saude"]
                p["registro"] = {"integro": integra, "entradas": n}
                return self._json(200, p)
            if u.path == "/api/leituras":
                try:
                    lim = int(q.get("limite", ["1000"])[0]); no = q.get("no", [""])[0]
                    return self._json(200, hub.leituras(lim, int(no) if no else None))
                except ValueError:
                    return self._json(400, {"ok": False, "erro": "limite ou no invalido"})
            if u.path == "/api/serie":
                return self._json(200, hub.serie(q.get("ativo", [""])[0], q.get("grandeza", [""])[0]))
            if u.path in ("/", "/painel.html"):
                arq = WEB / "painel.html"
                if not arq.exists():
                    return self._json(404, {"ok": False, "erro": "painel.html ausente"})
                dados = arq.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)
                return
            self._json(404, {"ok": False, "erro": "rota desconhecida"})

        def do_PUT(self):
            u = urlparse(self.path)
            if self._csrf_barrado():
                return
            if u.path.startswith("/api/gestao/arquivo/"):
                q = self._exigir(seg.EQUIPE)
                if not q:
                    return
                dados = self._corpo_grande(hub.GESTAO_ARQ_MAX)
                if dados is None:
                    return self._recusar_corpo("arquivo vazio ou maior que 20 MB")
                nome = unquote(self.headers.get("X-Nome") or "arquivo")
                r = hub.gestao_arquivo_por(u.path.rsplit("/", 1)[-1], nome, self.headers.get("Content-Type") or "", dados, q["usuario"])
                return self._json(200 if r["ok"] else 400, r)
            if u.path.startswith("/api/cliente/estado/"):
                return self._gravar_cliente(unquote(u.path[len("/api/cliente/estado/"):]))
            self._json(404, {"ok": False, "erro": "rota desconhecida"})

        def _gravar_cliente(self, chave: str) -> None:
            """PUT /api/cliente/estado/<chave> {"valor": texto, "versao": n} (ou cabeçalho If-Match: "v<n>").
            200 + ETag; 409 (conflito) com o valor, a versão e quem gravou; 413 grande demais; 400 chave fora da lista."""
            bruto = self._corpo_grande(perfil_cliente.VALOR_MAX + 4096)
            if bruto is None:
                return self._recusar_corpo("dados ausentes ou maiores que 2 MB")
            q = self._exigir(seg.CLIENTE)
            if not q:
                return
            if not perfil_cliente.chave_valida(chave):
                return self._json(400, {"ok": False, "erro": "chave nao permitida"})
            try:
                d = seg.carregar_json(bruto)
            except (ValueError, UnicodeDecodeError):
                return self._json(400, {"ok": False, "erro": "json invalido"})
            if not isinstance(d, dict) or not isinstance(d.get("valor"), str) or set(d) - {"valor", "versao"}:
                return self._json(400, {"ok": False, "erro": "envie {valor: texto, versao: número}"})
            versao = d.get("versao")
            if versao is None:
                m = re.fullmatch(r'(?:W/)?"?v(\d{1,12})"?', (self.headers.get("If-Match") or "").strip())
                versao = int(m.group(1)) if m else 0
            if not isinstance(versao, int) or isinstance(versao, bool) or versao < 0:
                return self._json(400, {"ok": False, "erro": "versao invalida"})
            r = hub.cliente_gravar(chave, d["valor"], versao, q["usuario"])
            if r.get("conflito"):
                return self._json(409, r, {"ETag": f'"v{r["versao"]}"'})
            if not r["ok"]:
                return self._json(413 if r.get("grande") else 400, r)
            return self._json(200, r, {"ETag": f'"v{r["versao"]}"'})

        def do_DELETE(self):
            u = urlparse(self.path)
            if self._csrf_barrado():
                return
            if u.path.startswith("/api/gestao/arquivo/"):
                q = self._exigir(seg.EQUIPE)
                if not q:
                    return
                return self._json(200, {"ok": hub.gestao_arquivo_apagar(u.path.rsplit("/", 1)[-1], q["usuario"])})
            self._json(404, {"ok": False, "erro": "rota desconhecida"})

        def do_POST(self):
            u = urlparse(self.path)
            if self._csrf_barrado():
                return
            # ── Editais, eventos e e-mail escrito na Gestão (vai para a fila email_saida que já existe) ──
            if u.path.startswith(("/api/editais", "/api/eventos")) or u.path == "/api/gestao/correio":
                q = self._quem()
                if q and not seg.pode(q, seg.EQUIPE):
                    return self._json(403, SEM_PAPEL)
                if q and u.path.endswith("/fontes") and not seg.pode(q, seg.DIRECAO):   # configurar as fontes: só a direção
                    return self._json(403, SEM_PAPEL)
                r = editais_mod.rota("POST", u.path, q, self._corpo(), editais_col, eventos_col, hub, correio)
                if r:
                    return self._json(*r)
            # ── Suporte ao cliente: chamado + e-mail para a Physis (e-mail e WhatsApp vêm da configuração) ──
            if u.path == "/api/suporte":
                q = self._quem()
                if self._precisa_sessao() and not q:
                    return self._json(401, {"ok": False, "erro": "entre com usuario e senha", "login": True})
                if not q and self._limitado("publico"):
                    return
                d = self._ler(self._corpo(), "suporte", estrito=False)
                if d is None:
                    return
                para = os.environ.get("PHYSIS_SUPORTE_EMAIL") or instancia.get("suporte_email") or ""
                r = hub.suporte_abrir(d if isinstance(d, dict) else {}, (q or {}).get("nome", ""), para, (q or {}).get("usuario", ""))
                if r.get("ok"):
                    threading.Thread(target=correio.enviar_fila, args=(hub, r["numero"]), daemon=True).start()
                return self._json(200 if r["ok"] else 400, r)
            # ── Caixa de chamados (equipe): situação, responsável, nota interna e resposta por e-mail ao cliente ──
            if u.path.startswith("/api/suporte/chamados/"):
                q = self._exigir(seg.EQUIPE)
                if not q:
                    return
                d = self._ler(self._corpo(), "chamado")
                if d is None:
                    return
                r = hub.suporte_atualizar(unquote(u.path[len("/api/suporte/chamados/"):]), d, q["usuario"])
                if r.get("ref"):
                    self._mandar(r["ref"])
                    r["email"] = "enviando" if correio.configurado() else "pendente"
                return self._json(200 if r["ok"] else r.pop("codigo", 400), r)
            # ── DWG para DXF (Planejador): conversor aberto LibreDWG (dwg2dxf) instalado no servidor ──
            if u.path == "/api/converter/dwg":
                q = self._quem()
                if self._precisa_sessao() and not q:
                    return self._json(401, {"ok": False, "erro": "entre com usuario e senha", "login": True})
                if not exige_login and not self._autorizado():
                    return self._json(401, {"ok": False, "erro": "token ausente ou invalido"})
                dados = self._corpo_grande(DWG_MAX)
                if dados is None:
                    return self._recusar_corpo("arquivo DWG vazio ou maior que 50 MB")
                r = converter_dwg(dados)
                if not r["ok"]:
                    return self._json(r["codigo"], {"ok": False, "erro": r["erro"]})
                self.send_response(200)
                self.send_header("Content-Type", "application/dxf")
                self.send_header("Content-Length", str(len(r["dxf"])))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(r["dxf"])
                return
            # ── Localização do lugar e previsão do tempo ──
            if u.path in ("/api/clima/local", "/api/clima/atualizar"):
                q = self._quem()
                if self._precisa_sessao() and not q:
                    return self._json(401, {"ok": False, "erro": "entre com usuario e senha", "login": True})
                if not exige_login and not self._autorizado():
                    return self._json(401, {"ok": False, "erro": "token ausente ou invalido"})
                if u.path.endswith("/atualizar"):
                    return self._json(200, {"ok": True, "consultas": clima.consultar_tudo(), "estado": clima.estado()})
                try:
                    d = seg.carregar_json(self._corpo() or "{}")
                except ValueError:
                    return self._json(400, {"ok": False, "erro": "json invalido"})
                r = clima.definir_local(d if isinstance(d, dict) else {}, (q or {}).get("usuario", ""))
                return self._json(200 if r["ok"] else 400, r)
            # ── Saúde: linhas dos aparelhos (MED/PUL, a homologar) e ações da tela ──
            if u.path == "/api/saude/linha":
                corpo = self._corpo()
                if corpo is None:
                    return self._recusar_corpo("corpo invalido ou grande demais")
                if self._limitado("dispositivo"):
                    return
                ok, no = self._dispositivo(saude_linha=True)
                if not ok:
                    return
                corpo, _ = seg.filtrar_do_no(corpo, no)
                res = [saude.registrar_evento(l, origem="aparelho") for l in corpo.split("\n") if l.strip()]
                for aid in {a for r in res for a in r.get("alertas", [])}:
                    threading.Thread(target=correio.enviar_fila, args=(hub, f"saude-{aid}"), daemon=True).start()
                return self._json(200, {"ok": True, "aceitas": sum(1 for r in res if r.get("ok") and not r.get("duplicada")),
                                        "linhas": [{"ok": r.get("ok"), "motivo": r.get("motivo", "")} for r in res]})
            if u.path.startswith("/api/saude/"):
                q = self._sessao_ou_401()
                if not q:
                    return
                try:
                    d = seg.carregar_json(self._corpo() or "{}")
                except ValueError:
                    return self._json(400, {"ok": False, "erro": "json invalido"})
                r = saude.executar(u.path[len("/api/saude/"):], d if isinstance(d, dict) else {}, q["usuario"])
                return self._json(200 if r.get("ok") else r.pop("codigo", 400), r)
            # ── Gestão no servidor: dados, contas e senha (sempre com sessão) ──
            if u.path.startswith("/api/gestao/estado/"):
                q = self._exigir(seg.EQUIPE)
                if not q:
                    return
                bruto = self._corpo_grande(hub.GESTAO_VALOR_MAX + 4096)
                if bruto is None:
                    return self._recusar_corpo("dados ausentes ou grandes demais")
                try:
                    d = seg.carregar_json(bruto)
                except ValueError:
                    return self._json(400, {"ok": False, "erro": "json invalido"})
                if not isinstance(d, dict) or not isinstance(d.get("versao") or 0, int) or isinstance(d.get("versao"), bool):
                    return self._json(400, {"ok": False, "erro": "json invalido"})
                r = hub.gestao_gravar(unquote(u.path[len("/api/gestao/estado/"):]), d.get("valor"), d.get("versao") or 0, q["usuario"])
                return self._json(409 if r.get("conflito") else (200 if r["ok"] else 400), r)
            if u.path in ("/api/contas", "/api/conta/senha") or (u.path.startswith("/api/contas/") and u.path.count("/") == 3):
                q = self._sessao_ou_401()
                if not q:
                    return
                esq = "senha" if u.path == "/api/conta/senha" else ("contas" if u.path == "/api/contas" else "conta_alterar")
                d = self._ler(self._corpo(), esq, estrito=False)
                if d is None:
                    return
                if u.path != "/api/conta/senha" and not seg.pode(q, seg.DIRECAO):
                    return self._json(403, SEM_PAPEL)
                # dar papel de direção, mudar papel, desativar ou trocar a senha de outra pessoa: pede a senha de novo
                if u.path != "/api/conta/senha" and (seg.normalizar_papel(d.get("papel")) == seg.DIRECAO or
                                                     (u.path != "/api/contas" and (d.get("papel") is not None or d.get("ativa") is False
                                                                                   or d.get("senha") is not None))):
                    if not self._sensivel(q):
                        return
                if u.path == "/api/conta/senha":
                    r = hub.trocar_senha(q["id"], str(d.get("atual", "")), str(d.get("nova", "")))
                    if r["ok"]:
                        seg.evento_seguranca(hub, "senha trocada", q["usuario"], ip=self._ip())
                elif u.path == "/api/contas":
                    r = hub.criar_conta(str(d.get("nome", "")), str(d.get("usuario", "")), str(d.get("senha", "")), q["id"],
                                        str(d.get("pessoa") or ""), str(d.get("papel") or "operador"))
                    if r["ok"] and r.get("id"):
                        self._mandar(seg.confirmar_enviar(hub, r["id"], url_publica))
                else:
                    alvo = unquote(u.path.rsplit("/", 1)[-1])
                    r = hub.alterar_conta(q["id"], alvo, senha=d.get("senha") if isinstance(d.get("senha"), str) else None,
                                          ativa=d.get("ativa") if isinstance(d.get("ativa"), bool) else None,
                                          papel=d.get("papel") if isinstance(d.get("papel"), str) else None,
                                          pessoa=d.get("pessoa") if isinstance(d.get("pessoa"), str) else None)
                return self._json(200 if r["ok"] else 400, r)
            # ── Fluxos de conta (seguranca.py): esqueci a senha, confirmar e-mail, convite, consentimento, 2FA ──
            if u.path.startswith("/api/conta/") or u.path.startswith("/api/convites"):
                r = self._rotas_conta(u.path)
                if r is not False:
                    return
            # ── Consultoria ── gravar textos do site: sempre com sessão, mesmo em instalação sem login
            if u.path.startswith("/api/site/textos/"):
                # lê o corpo antes de responder, mesmo sem sessão: no Windows, fechar com bytes
                # não lidos corta a conexão (RST) e quem enviou não vê o 401
                bruto = self._corpo_grande(1024 * 1024)
                if bruto is None:
                    return self._recusar_corpo("textos ausentes ou maiores que 1 MB")
                q = self._exigir(seg.DIRECAO)          # textos do site público: só a direção
                if not q:
                    return
                try:
                    d = seg.carregar_json(bruto)
                except ValueError:
                    return self._json(400, {"ok": False, "erro": "json invalido"})
                if isinstance(d, dict) and isinstance(d.get("textos"), dict) and len(d) == 1:
                    d = d["textos"]          # aceita {"textos": {...}} ou {chave: texto}
                r = hub.site_gravar(u.path[len("/api/site/textos/"):], d, q["usuario"])
                return self._json(200 if r["ok"] else 400, r)
            # ── fim Consultoria ──
            if u.path == "/api/central/arquivo":
                # arquivo de apoio do pedido: corpo binario, ate 20 MB; publico como o proprio pedido (com limite por IP)
                if self._limitado("arquivo"):
                    return
                q = parse_qs(u.query)
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    n = -1
                if n <= 0 or n > hub.ARQUIVO_MAX:
                    return self._recusar_corpo("arquivo vazio ou maior que 20 MB")
                self._corpo_lido = True
                r = hub.arquivo_por((q.get("pedido") or [""])[0], (q.get("nome") or [""])[0], self.rfile.read(n))
                return self._json(200 if r["ok"] else 400, r)
            corpo = self._corpo()
            if corpo is None:
                return self._recusar_corpo("corpo invalido ou grande demais")
            # ── Aprendizado, robôs e alertas de clima ──
            if u.path == "/api/aprendizado/treinar":
                if not self._exigir(seg.DIRECAO):
                    return
                return self._json(200, aprendizado.treinar())
            if u.path.startswith("/api/robos/"):
                qs = self._sessao_ou_401()
                if not qs:
                    return
                try:
                    d = seg.carregar_json(corpo or "{}")
                except ValueError:
                    return self._json(400, {"ok": False, "erro": "json invalido"})
                d = d if isinstance(d, dict) else {}
                d["_quem"] = qs["usuario"]                  # quem abre o chamado do suporte (vem da sessão, nunca do corpo)
                cod, r = robos_mod.atender(u.path.rsplit("/", 1)[-1], d, robos)
                return self._json(cod, r)
            if u.path == "/api/alertas/assinaturas":
                qs = self._sessao_ou_401()
                if not qs:
                    return
                try:
                    d = seg.carregar_json(corpo or "{}")
                except ValueError:
                    return self._json(400, {"ok": False, "erro": "json invalido"})
                if not isinstance(d, dict):
                    return self._json(400, {"ok": False, "erro": "json invalido"})
                admin = seg.pode(qs, seg.DIRECAO)
                if d.get("acao") == "sair":
                    r = alertas.sair(int(d.get("id") or 0), qs["usuario"], admin=admin)
                else:
                    d.pop("_admin", None)
                    if admin:
                        d["_admin"] = True
                    r = alertas.assinar(d, qs["usuario"])
                return self._json(r.pop("codigo", 200 if r["ok"] else 400), r)
            if u.path == "/api/gis/residuos/importar":
                if not self._exigir(seg.EQUIPE):
                    return
                try:
                    pts = (residuos_mod.importar_geojson(seg.carregar_json(corpo)) if corpo.lstrip().startswith("{")
                           else residuos_mod.importar_csv(corpo))
                except ValueError as exc:
                    return self._json(400, {"ok": False, "erro": str(exc)})
                return self._json(200, residuos_mod.ResiduosGis(irradiacao).importar(pts))
            # Entrega dos aparelhos: chave por dispositivo (Authorization: Bearer / X-Physis-Chave). Sem chave,
            # só da rede local (o receptor V6 atual ainda não manda chave) ou com PHYSIS_ACEITAR_SEM_CHAVE=1.
            recusadas = 0
            if u.path in ("/api/gateway/webhook", "/api/hardware/gateway", "/api/v6/linha"):
                if self._limitado("dispositivo"):
                    return
                ok, no = self._dispositivo()
                if not ok:
                    return
                corpo, recusadas = seg.filtrar_do_no(corpo, no)
            if u.path in ("/api/gateway/webhook", "/api/hardware/gateway"):
                r = hub.receber_lote(corpo, origem="receptor")
                if recusadas:
                    r["recusadas_outro_no"] = recusadas
                return self._json(200, r)
            if u.path == "/api/v6/linha":
                r = hub.receber_lote(corpo, origem="esp-wifi")
                if recusadas:
                    r["recusadas_outro_no"] = recusadas
                # comandos pendentes do(s) no(s) que acabaram de falar
                pend: list[str] = []
                for bruta in corpo.split("\n"):
                    ok, _, campos = validar_telemetria(bruta)
                    if ok:
                        pend += hub.comandos_pendentes(para_int(campos["ID"], -1))
                r["comandos"] = pend
                return self._json(200, r)
            if u.path in ("/api/central/compra", "/api/central/pedido"):
                # a loja entrega aqui; nao exige login porque quem compra nao tem conta na gestao (limite por IP)
                if self._limitado("publico"):
                    return
                tipo = u.path.rsplit("/", 1)[-1]
                try:
                    d = seg.carregar_json(corpo or "{}")
                except ValueError:
                    return self._json(400, {"ok": False, "erro": "json invalido"})
                if len(corpo or "") > 64_000 or d.get("_formato") != f"physis-{tipo}/1" or not isinstance(d.get("numero"), str):
                    return self._json(400, {"ok": False, "erro": "registro invalido"})
                r = hub.central_por(tipo, d["numero"], d)
                return self._json(200 if r["ok"] else 400, r)
            if u.path == "/api/central/alocacao":
                # interno: a direcao define os consultores e cada consultor aceita a sua parte
                if not self._exigir(seg.EQUIPE):
                    return
                try:
                    d = seg.carregar_json(corpo or "{}")
                except ValueError:
                    return self._json(400, {"ok": False, "erro": "json invalido"})
                if len(corpo or "") > 64_000 or d.get("_formato") != "physis-alocacao/1" or not isinstance(d.get("id"), str):
                    return self._json(400, {"ok": False, "erro": "registro invalido"})
                r = hub.central_gravar("alocacao", d["id"], d)
                return self._json(200 if r["ok"] else 400, r)
            if u.path.startswith("/api/central/compra/") and u.path.endswith("/aprovar"):
                q = self._exigir(seg.DIRECAO)          # aprovar dispara a montagem e o código: só a direção
                if not q or not self._sensivel(q):     # e com a senha confirmada há pouco
                    return
                numero = u.path.split("/")[-2]
                ok = hub.central_marcar("compra", numero, "aprovado", q["usuario"] if q else "")
                if not ok:
                    return self._json(404, {"ok": False})
                # montagem automática: número, plataforma, código e e-mail de acesso
                base = url_publica or (("https" if self._https() else "http") + "://" + (self.headers.get("Host") or "localhost"))
                inst = hub.instalar_compra(numero, base, fabricar, q["usuario"] if q else "")
                if inst.get("ok") and not inst.get("repetido") and correio.configurado():
                    threading.Thread(target=correio.enviar_fila, args=(hub, inst["numero"]), daemon=True).start()
                    inst["email"] = "enviando"
                return self._json(200, {"ok": True, "instalacao": inst})
            if u.path.startswith("/api/ativar/"):
                # o cliente digita o código do e-mail; certo -> baixa a plataforma montada para ele
                if self._limitado("entrar"):
                    return
                try:
                    d = seg.carregar_json(corpo or "{}")
                except ValueError:
                    return self._json(400, {"ok": False, "erro": "json invalido"})
                r = hub.ativar(u.path.rsplit("/", 1)[-1], str(d.get("codigo", "")) if isinstance(d, dict) else "")
                if not r["ok"]:
                    return self._json(429 if r.get("espera") else 403, r)
                pac = Path(r["pacote"]) if r.get("pacote") else None
                if pac and pac.is_file():
                    dados = pac.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/zip")
                    self.send_header("Content-Disposition", "attachment; filename=\"physis-" + r["numero"] + ".zip\"")
                    self.send_header("Content-Length", str(len(dados)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(dados)
                    return
                return self._json(200, {"ok": True, "pacote": False, "numero": r["numero"]})
            if u.path.startswith("/api/central/emails/"):
                # a equipe marca como enviado à mão, ou manda tentar de novo pelo servidor de e-mail
                if not self._exigir(seg.EQUIPE):
                    return
                partes = u.path.split("/")
                if len(partes) != 6 or not partes[4].isdigit() or partes[5] not in ("enviado", "enviar"):
                    return self._json(404, {"ok": False, "erro": "rota desconhecida"})
                if partes[5] == "enviado":
                    return self._json(200, {"ok": hub.email_marcar(int(partes[4]), "enviado_a_mao")})
                e = [x for x in hub.emails() if x["id"] == int(partes[4])]
                if not e:
                    return self._json(404, {"ok": False})
                ok, erro = correio.enviar(e[0]["para"], e[0]["assunto"], e[0]["corpo"])
                hub.email_marcar(e[0]["id"], "enviado" if ok else "falhou", erro)
                return self._json(200 if ok else 502, {"ok": ok, "erro": erro})
            if u.path in ("/api/conta/criar", "/api/conta/entrar", "/api/conta/sair"):
                if u.path != "/api/conta/sair" and self._limitado("entrar"):     # por IP, além do limite por usuário do hub
                    return
                if u.path == "/api/conta/sair":
                    d = {}
                else:
                    d = self._ler(corpo, "criar" if u.path.endswith("criar") else "entrar", estrito=False)
                    if d is None:
                        return
                if u.path == "/api/conta/sair":
                    q = self._quem()
                    hub.sair(self._token_sessao())
                    if q:
                        seg.acesso_registrar(hub, q["usuario"], self._ip(), "saiu")
                    return self._json_cookie(200, {"ok": True}, self._cookie("", 0))
                if u.path == "/api/conta/criar":
                    q = self._quem()
                    # a primeira conta vira a direção: de fora da rede local, só com PHYSIS_PRIMEIRA_CONTA_EXTERNA=1
                    if not hub.tem_conta() and not self._local() and os.environ.get("PHYSIS_PRIMEIRA_CONTA_EXTERNA") != "1":
                        return self._json(403, {"ok": False, "erro": "a primeira conta só pode ser criada da rede local do servidor"})
                    r = hub.criar_conta(str(d.get("nome", "")), str(d.get("usuario", "")), str(d.get("senha", "")), q["id"] if q else None)
                    if not r["ok"]:
                        return self._json(400, r)
                    aceito, versao = seg._consentimento_do_corpo(d)
                    if aceito and r.get("id"):
                        seg.consentimento_registrar(hub, r["id"], str(d.get("usuario", "")).strip().lower(), versao, True, self._ip())
                    if not r.get("primeira"):
                        self._mandar(seg.confirmar_enviar(hub, r["id"], url_publica))
                        return self._json(200, r)
                r = hub.entrar(str(d.get("usuario", "")), str(d.get("senha", "")), self._ip(), self.headers.get("User-Agent") or "",
                               d.get("codigo") if isinstance(d.get("codigo"), str) else None)
                if not r.get("precisa_2fa"):
                    seg.acesso_registrar(hub, str(d.get("usuario", "")).strip().lower(), self._ip(),
                                         "entrou" if r["ok"] else ("bloqueado" if r.get("espera") else "senha errada"))
                if not r["ok"]:
                    return self._json(429 if r.get("espera") else 401, r)
                tk = r.pop("token")
                r["csrf"] = seg.csrf_de(hub, tk)
                return self._json_cookie(200, r, self._cookie(tk, hub.SESSAO_S))
            # ── LGPD art. 18, VI: a pessoa apaga a própria conta (confirma com a senha); ver seguranca.apagar_titular ──
            if u.path == "/api/conta/apagar":
                if self._limitado("entrar"):
                    return
                q = self._sessao_ou_401()
                if not q:
                    return
                d = self._ler(corpo, "apagar")
                if d is None:
                    return
                if q.get("dois_fatores") and not seg.segundo_fator(hub, q["id"], str(d.get("codigo") or ""), q["usuario"]):
                    return self._json(403, {"ok": False, "precisa_2fa": True, "erro": "Digite o código do aplicativo autenticador."})
                r = seg.apagar_titular(hub, q, str(d.get("senha", "")))
                if not r["ok"]:
                    return self._json(r.pop("codigo", 400), r)
                return self._json_cookie(200, r, self._cookie("", 0))
            # ── Chaves dos dispositivos (só a direção): criar devolve a chave UMA vez; revogar vale na hora ──
            if u.path == "/api/dispositivos/chaves" or (u.path.startswith("/api/dispositivos/chaves/") and u.path.endswith("/revogar")):
                q = self._exigir(seg.DIRECAO)
                if not q:
                    return
                if u.path.endswith("/revogar"):
                    ok = seg.chave_revogar(hub, u.path.split("/")[-2], q["usuario"])
                    return self._json(200 if ok else 404, {"ok": ok})
                d = self._ler(corpo, "chave")
                if d is None or not self._sensivel(q):
                    return
                r = seg.chave_criar(hub, d.get("no"), str(d.get("rotulo", "")), q["usuario"])
                return self._json(200 if r["ok"] else 400, r)
            if u.path.startswith("/api/loja/item/"):
                # catálogo da loja: sempre exige sessão da equipe, mesmo em instalação sem login; publicar, só a direção
                q = self._exigir(seg.EQUIPE)
                if not q:
                    return
                partes = u.path.split("/")          # ['', 'api', 'loja', 'item', <id>, (acao)]
                if len(partes) not in (5, 6):
                    return self._json(404, {"ok": False, "erro": "rota desconhecida"})
                try:
                    d = seg.carregar_json(corpo or "{}")
                except ValueError:
                    return self._json(400, {"ok": False, "erro": "json invalido"})
                if not isinstance(d, dict):
                    return self._json(400, {"ok": False, "erro": "json invalido"})
                ident, acao = partes[4], (partes[5] if len(partes) == 6 else "")
                if acao == "":
                    r = hub.loja_gravar(ident, d, q["usuario"])
                elif acao == "revisar":
                    r = hub.loja_revisar(ident, q["usuario"], bool(d.get("revisado", True)))
                elif acao == "publicar":
                    if not seg.pode(q, seg.DIRECAO):
                        return self._json(403, SEM_PAPEL)
                    r = hub.loja_publicar(ident, q["usuario"], bool(d.get("publico", True)))
                else:
                    return self._json(404, {"ok": False, "erro": "rota desconhecida"})
                return self._json(200 if r["ok"] else 400, r)
            if u.path == "/api/comando":
                if self._barrado():
                    return
                if not self._autorizado():
                    return self._json(401, {"ok": False, "erro": "token ausente ou invalido"})
                linha = corpo.strip()
                if linha.startswith("{"):
                    try:
                        c = seg.carregar_json(linha)
                        linha = str(c.get("comando", "")) if isinstance(c, dict) else ""
                        if len(linha) > 200:
                            return self._json(400, {"ok": False, "erro": "comando longo demais"})
                    except ValueError:
                        return self._json(400, {"ok": False, "erro": "json invalido"})
                r = hub.comandar(linha)
                return self._json(200 if r["ok"] else 400, r)
            self._json(404, {"ok": False, "erro": "rota desconhecida"})

    return Manipulador


def iniciar(hub: Hub, porta: int = 8700, token: str | None = None, endereco: str = "0.0.0.0", instancia: dict | None = None,
            clima=None, irradiacao=None):
    srv = ThreadingHTTPServer((endereco, porta), criar_manipulador(hub, token, instancia, clima, irradiacao))
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main() -> None:
    porta = int(os.environ.get("PHYSIS_PORTA", "8700"))
    rx = os.environ.get("PHYSIS_RX_URL")
    inst = ler_instancia()
    hub = Hub(banco_da_instancia(inst),
              org=os.environ.get("PHYSIS_ORG", inst.get("org", "org-teste")),
              lugar=os.environ.get("PHYSIS_LUGAR", inst.get("lugar", "lugar01")),
              enviar_comando=cliente_receptor(rx) if rx else None)
    parar = threading.Event()
    if rx:
        threading.Thread(target=consultar_receptor, args=(hub, rx, parar), daemon=True).start()
    sim = os.environ.get("PHYSIS_SIMULAR")
    if sim:
        a, b, c, d = (int(x) for x in sim.split(","))
        threading.Thread(target=simular, args=(hub, Simulador(a, b, c, d), parar), daemon=True).start()
    clima = clima_mod.Clima(hub, receptor_url=rx, enviar_local=clima_mod.receptor_local(rx) if rx else None)
    if os.environ.get("PHYSIS_CLIMA", "1") != "0":     # PHYSIS_CLIMA=0 desliga as consultas (sem internet de propósito)
        threading.Thread(target=clima_mod.rodar, args=(clima, parar), daemon=True).start()
    cfg_mqtt = mqtt_mod.config_de(ler_instancia())       # Caixinha Physis IoT (ESPHome) pelo broker MQTT
    if cfg_mqtt:
        threading.Thread(target=mqtt_mod.rodar, args=(hub, cfg_mqtt, parar), daemon=True).start()
    apr_fundo = aprendizado_mod.Aprendizado(hub)         # treina ao ligar (se o último tem mais de 1 dia) e às 3 h
    threading.Thread(target=aprendizado_mod.rodar, args=(apr_fundo, parar), daemon=True).start()
    alertas_fundo = alertas_mod.AlertasClima(hub, aprendizado=apr_fundo)   # alertas de clima a cada 15 min
    threading.Thread(target=alertas_mod.rodar, args=(alertas_fundo, parar),
                     kwargs={"enviar": lambda: alertas_mod.enviar_emails(hub, correio.enviar_fila)}, daemon=True).start()
    saude_fundo = saude_mod.Saude(hub)          # doses esquecidas e avisos aos cuidadores, mesmo sem a tela aberta
    threading.Thread(target=saude_mod.rodar, args=(saude_fundo, parar),
                     kwargs={"enviar": lambda: saude_mod.enviar_avisos(hub, correio.enviar_fila)}, daemon=True).start()
    # retenção (LGPD/Marco Civil): sessões vencidas, acessos com mais de 6 meses, e-mails não enviados... (PHYSIS_RETENCAO_DIAS_*)
    threading.Thread(target=seg.rodar_retencao, args=(hub, parar), daemon=True).start()
    endereco = os.environ.get("PHYSIS_ENDERECO") or "0.0.0.0"
    srv = iniciar(hub, porta, os.environ.get("PHYSIS_TOKEN"), endereco=endereco, clima=clima)
    print(f"Physis Hub em http://{endereco}:{porta}  receptor={rx or 'nao configurado'}  simulador={sim or 'desligado'}")
    if not inst.get("login"):
        print("Aviso: instalação sem login. Telemetria aberta só para a rede local; de fora, tudo pede sessão (docs/SEGURANCA.md).")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        parar.set()
        srv.shutdown()
        hub.fechar()


if __name__ == "__main__":
    main()
