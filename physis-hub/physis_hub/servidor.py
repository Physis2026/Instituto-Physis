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
  PHYSIS_PORTA (8700)  PHYSIS_BANCO (physis-hub.db)  PHYSIS_ORG  PHYSIS_LUGAR
  PHYSIS_RX_URL        ex.: http://192.168.4.1 — liga o envio de comandos e a consulta ao receptor
  PHYSIS_TOKEN         se definido, exigido em X-Physis-Token nas rotas das telas que alteram estado
  PHYSIS_SIMULAR       ex.: "6,1,3,1" (solo,zona,coleira,comedouro) — gera dados sem hardware
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import re

from . import clima as clima_mod
from . import saude as saude_mod
from . import gis as gis_mod
from . import app_pwa
from . import correio
from . import editais as editais_mod
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


def ler_instancia() -> dict:
    """Configuracao da instalacao montada na compra: modulos, se exige login, licenca."""
    try:
        return json.loads(INSTANCIA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


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
<button type="button" id="ok">Entrar</button><p id="msg" role="status" aria-live="polite"></p></div>
<p class="t2" style="margin-top:12px">Esqueceu a senha? Peça à direção da Physis para criar uma nova.</p></main><script>
var criar=false,b=document.getElementById("ok"),m=document.getElementById("msg");
function dizer(t,e){m.textContent=t;m.style.color=e?"#7A2214":"#1F4A1C";}
fetch("/api/instancia",{cache:"no-store"}).then(function(r){return r.json();}).then(function(j){if(j&&j.tem_conta===false){criar=true;document.getElementById("caixa-nome").hidden=false;
document.getElementById("sub").textContent="Primeira entrada neste servidor: quem criar esta conta passa a ser da direção (administradora).";document.getElementById("senha").autocomplete="new-password";b.textContent="Criar conta e entrar";}});
["usuario","senha","nome"].forEach(function(i){document.getElementById(i).addEventListener("keydown",function(e){if(e.key==="Enter")b.click();});});
b.onclick=function(){var u=document.getElementById("usuario").value.trim(),s=document.getElementById("senha").value,n=document.getElementById("nome").value.trim();
if(!u||!s){dizer("Informe o e-mail e a senha.",true);return;}b.disabled=true;dizer("Conferindo…",false);
fetch(criar?"/api/conta/criar":"/api/conta/entrar",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({nome:n||u,usuario:u,senha:s})})
.then(function(r){return r.json();}).then(function(j){if(j.ok){dizer("Entrando…",false);location.reload();}else{dizer(j.erro||"E-mail ou senha não conferem.",true);b.disabled=false;}})
.catch(function(){dizer("Sem resposta do servidor.",true);b.disabled=false;});};
</script></body></html>"""


def criar_manipulador(hub: Hub, token: str | None, instancia: dict | None = None, clima=None, irradiacao=None):
    instancia = instancia if instancia is not None else ler_instancia()
    if irradiacao is None:
        irradiacao = gis_mod.Irradiacao(hub)
    saude = saude_mod.Saude(hub)
    if clima is None:
        rx = os.environ.get("PHYSIS_RX_URL")
        clima = clima_mod.Clima(hub, receptor_url=rx, enviar_local=clima_mod.receptor_local(rx) if rx else None)
    exige_login = bool(instancia.get("login"))
    csp = politica(os.environ.get("PHYSIS_CHAMADAS") or instancia.get("chamadas"))
    csp_planejador = csp.replace("'wasm-unsafe-eval'", "'wasm-unsafe-eval' 'unsafe-eval'", 1)
    fabricar = fabricante(instancia)
    url_publica = (os.environ.get("PHYSIS_URL_PUBLICA") or instancia.get("url_publica") or "").rstrip("/")
    # Editais e eventos (editais.py): listas públicas buscadas pelo servidor, com cache em arquivo
    pasta_editais = Path(os.environ.get("PHYSIS_EDITAIS_PASTA") or (Path(os.environ.get("PHYSIS_BANCO", "physis-hub.db")).resolve().parent / "editais"))
    editais_col = editais_mod.Coletor(pasta_editais, tipo="edital")
    eventos_col = editais_mod.Coletor(pasta_editais, tipo="evento")
    class Manipulador(BaseHTTPRequestHandler):
        # Cabecalhos de seguranca em toda resposta. As telas usam script e estilo dentro da pagina,
        # por isso 'unsafe-inline'; de fora do proprio servidor, so o servidor de chamadas da Physis, se configurado.
        def end_headers(self):
            # O Planejador (e só ele) precisa de 'unsafe-eval': o leitor BIM web-ifc monta funções ao rodar.
            # A liberação vale só para essa página; o resto da plataforma continua sem eval.
            eh_planejador = urlparse(self.path).path in ("/planejador", "/planejador/")
            self.send_header("Content-Security-Policy", csp_planejador if eh_planejador else csp)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            super().end_headers()

        server_version = "PhysisHub/0.1"

        def log_message(self, *a):          # silencioso; a saude fica em /api/saude
            pass

        def handle_one_request(self):
            self._corpo_lido = False          # cada pedido começa sem corpo lido
            super().handle_one_request()

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

        def _json(self, codigo: int, obj) -> None:
            if codigo >= 400:
                self._drenar_pendente()
            corpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
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
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = 0
            self._corpo_lido = True
            self.close_connection = True
            corpo = json.dumps({"ok": False, "erro": erro}, ensure_ascii=False).encode("utf-8")
            self.send_response(413)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
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
            return token is None or self.headers.get("X-Physis-Token") == token

        def _token_sessao(self) -> str | None:
            for parte in (self.headers.get("Cookie") or "").split(";"):
                k, _, v = parte.strip().partition("=")
                if k == "physis_sessao":
                    return v
            return None

        def _quem(self) -> dict | None:
            return hub.sessao(self._token_sessao())

        def _barrado(self) -> bool:
            """True (e ja respondeu 401) quando a instalacao exige login e nao ha sessao."""
            if not exige_login or self._quem():
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
                    "cursos": [c for c in (instancia.get("cursos") or []) if isinstance(c, dict)] if q else [],
                    "senha_min": hub.SENHA_MIN}

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
            # ── Editais (só quem tem acesso) e eventos (equipe com sessão): editais.rota decide ──
            if u.path.startswith(("/api/editais", "/api/eventos")):
                r = editais_mod.rota("GET", u.path, self._quem(), None, editais_col, eventos_col, hub, correio)
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
                if not self._quem():
                    return self._json(401, {"ok": False, "erro": "entre com usuario e senha", "login": True})
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
            if u.path == "/api/gestao/estado":
                q = self._sessao_ou_401()
                if not q:
                    return
                try:
                    desde = float((q2 := parse_qs(u.query)).get("desde", ["0"])[0])
                except ValueError:
                    desde = 0.0
                return self._json(200, {"ok": True, "agora": time.time(), "conta": {k: q[k] for k in ("nome", "usuario", "papel", "pessoa")},
                                        "itens": hub.gestao_ler(desde)})
            if u.path.startswith("/api/gestao/arquivo/"):
                if not self._sessao_ou_401():
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
                if not self._quem():
                    return self._json(401, {"ok": False, "erro": "entre com usuario e senha", "login": True})
                if u.path.endswith("emails"):
                    # avisos de saúde (dado sensível, LGPD) vão só para os cuidadores: a fila mostra só quantos são
                    todos = hub.emails()
                    saude_n = sum(1 for e in todos if str(e.get("ref") or "").startswith("saude-"))
                    return self._json(200, {"ok": True, "configurado": correio.configurado(), "saude_ocultos": saude_n,
                                            "emails": [e for e in todos if not str(e.get("ref") or "").startswith("saude-")]})
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
                return self._json(200, {"ok": True, "arquivos": hub.arquivos_de((parse_qs(u.query).get("pedido") or [""])[0])})
            if u.path.startswith("/api/central/arquivo/"):
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
                return self._json(200, {"ok": True, "chamados": hub.suporte_listar(),
                                        "whatsapp": re.sub(r"\D", "", os.environ.get("PHYSIS_SUPORTE_WHATSAPP") or instancia.get("suporte_whatsapp") or ""),
                                        "email": os.environ.get("PHYSIS_SUPORTE_EMAIL") or instancia.get("suporte_email") or ""})
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
            if u.path.startswith("/api/gestao/arquivo/"):
                q = self._sessao_ou_401()
                if not q:
                    return
                dados = self._corpo_grande(hub.GESTAO_ARQ_MAX)
                if dados is None:
                    return self._recusar_corpo("arquivo vazio ou maior que 20 MB")
                nome = unquote(self.headers.get("X-Nome") or "arquivo")
                r = hub.gestao_arquivo_por(u.path.rsplit("/", 1)[-1], nome, self.headers.get("Content-Type") or "", dados, q["usuario"])
                return self._json(200 if r["ok"] else 400, r)
            self._json(404, {"ok": False, "erro": "rota desconhecida"})

        def do_DELETE(self):
            u = urlparse(self.path)
            if u.path.startswith("/api/gestao/arquivo/"):
                q = self._sessao_ou_401()
                if not q:
                    return
                return self._json(200, {"ok": hub.gestao_arquivo_apagar(u.path.rsplit("/", 1)[-1], q["usuario"])})
            self._json(404, {"ok": False, "erro": "rota desconhecida"})

        def do_POST(self):
            u = urlparse(self.path)
            # ── Editais, eventos e e-mail escrito na Gestão (vai para a fila email_saida que já existe) ──
            if u.path.startswith(("/api/editais", "/api/eventos")) or u.path == "/api/gestao/correio":
                r = editais_mod.rota("POST", u.path, self._quem(), self._corpo(), editais_col, eventos_col, hub, correio)
                if r:
                    return self._json(*r)
            # ── Suporte ao cliente: chamado + e-mail para a Physis (e-mail e WhatsApp vêm da configuração) ──
            if u.path == "/api/suporte":
                q = self._quem()
                if exige_login and not q:
                    return self._json(401, {"ok": False, "erro": "entre com usuario e senha", "login": True})
                try:
                    d = json.loads(self._corpo() or "{}")
                except ValueError:
                    return self._json(400, {"ok": False, "erro": "json invalido"})
                para = os.environ.get("PHYSIS_SUPORTE_EMAIL") or instancia.get("suporte_email") or ""
                r = hub.suporte_abrir(d if isinstance(d, dict) else {}, (q or {}).get("nome", ""), para)
                if r.get("ok"):
                    threading.Thread(target=correio.enviar_fila, args=(hub, r["numero"]), daemon=True).start()
                return self._json(200 if r["ok"] else 400, r)
            # ── DWG para DXF (Planejador): conversor aberto LibreDWG (dwg2dxf) instalado no servidor ──
            if u.path == "/api/converter/dwg":
                q = self._quem()
                if exige_login and not q:
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
                if exige_login and not q:
                    return self._json(401, {"ok": False, "erro": "entre com usuario e senha", "login": True})
                if not exige_login and not self._autorizado():
                    return self._json(401, {"ok": False, "erro": "token ausente ou invalido"})
                if u.path.endswith("/atualizar"):
                    return self._json(200, {"ok": True, "consultas": clima.consultar_tudo(), "estado": clima.estado()})
                try:
                    d = json.loads(self._corpo() or "{}")
                except ValueError:
                    return self._json(400, {"ok": False, "erro": "json invalido"})
                r = clima.definir_local(d if isinstance(d, dict) else {}, (q or {}).get("usuario", ""))
                return self._json(200 if r["ok"] else 400, r)
            # ── Saúde: linhas dos aparelhos (MED/PUL, a homologar) e ações da tela ──
            if u.path == "/api/saude/linha":
                if not self._autorizado():
                    return self._json(401, {"ok": False, "erro": "token ausente ou invalido"})
                corpo = self._corpo()
                if corpo is None:
                    return self._recusar_corpo("corpo invalido ou grande demais")
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
                    d = json.loads(self._corpo() or "{}")
                except ValueError:
                    return self._json(400, {"ok": False, "erro": "json invalido"})
                r = saude.executar(u.path[len("/api/saude/"):], d if isinstance(d, dict) else {}, q["usuario"])
                return self._json(200 if r.get("ok") else r.pop("codigo", 400), r)
            # ── Gestão no servidor: dados, contas e senha (sempre com sessão) ──
            if u.path.startswith("/api/gestao/estado/"):
                q = self._sessao_ou_401()
                if not q:
                    return
                bruto = self._corpo_grande(hub.GESTAO_VALOR_MAX + 4096)
                if bruto is None:
                    return self._recusar_corpo("dados ausentes ou grandes demais")
                try:
                    d = json.loads(bruto.decode("utf-8"))
                except ValueError:
                    return self._json(400, {"ok": False, "erro": "json invalido"})
                r = hub.gestao_gravar(unquote(u.path[len("/api/gestao/estado/"):]), d.get("valor"), d.get("versao") or 0, q["usuario"])
                return self._json(409 if r.get("conflito") else (200 if r["ok"] else 400), r)
            if u.path in ("/api/contas", "/api/conta/senha") or (u.path.startswith("/api/contas/") and u.path.count("/") == 3):
                q = self._sessao_ou_401()
                if not q:
                    return
                try:
                    d = json.loads(self._corpo() or "{}")
                except ValueError:
                    return self._json(400, {"ok": False, "erro": "json invalido"})
                if u.path == "/api/conta/senha":
                    r = hub.trocar_senha(q["id"], str(d.get("atual", "")), str(d.get("nova", "")))
                elif u.path == "/api/contas":
                    r = hub.criar_conta(str(d.get("nome", "")), str(d.get("usuario", "")), str(d.get("senha", "")), q["id"],
                                        str(d.get("pessoa", "")), str(d.get("papel", "operador")))
                else:
                    alvo = unquote(u.path.rsplit("/", 1)[-1])
                    r = hub.alterar_conta(q["id"], alvo, senha=d.get("senha") if isinstance(d.get("senha"), str) else None,
                                          ativa=d.get("ativa") if isinstance(d.get("ativa"), bool) else None,
                                          papel=d.get("papel") if isinstance(d.get("papel"), str) else None,
                                          pessoa=d.get("pessoa") if isinstance(d.get("pessoa"), str) else None)
                return self._json(200 if r["ok"] else 400, r)
            # ── Consultoria ── gravar textos do site: sempre com sessão, mesmo em instalação sem login
            if u.path.startswith("/api/site/textos/"):
                # lê o corpo antes de responder, mesmo sem sessão: no Windows, fechar com bytes
                # não lidos corta a conexão (RST) e quem enviou não vê o 401
                bruto = self._corpo_grande(1024 * 1024)
                if bruto is None:
                    return self._recusar_corpo("textos ausentes ou maiores que 1 MB")
                q = self._quem()
                if not q:
                    return self._json(401, {"ok": False, "erro": "entre com usuario e senha", "login": True})
                try:
                    d = json.loads(bruto.decode("utf-8"))
                except ValueError:
                    return self._json(400, {"ok": False, "erro": "json invalido"})
                if isinstance(d, dict) and isinstance(d.get("textos"), dict) and len(d) == 1:
                    d = d["textos"]          # aceita {"textos": {...}} ou {chave: texto}
                r = hub.site_gravar(u.path[len("/api/site/textos/"):], d, q["usuario"])
                return self._json(200 if r["ok"] else 400, r)
            # ── fim Consultoria ──
            if u.path == "/api/central/arquivo":
                # arquivo de apoio do pedido: corpo binario, ate 20 MB; publico como o proprio pedido
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
            # Entrega do receptor: o firmware atual nao manda token; fica aberta
            # na rede local ate a F0 (memo, secao 6).
            if u.path in ("/api/gateway/webhook", "/api/hardware/gateway"):
                return self._json(200, hub.receber_lote(corpo, origem="receptor"))
            if u.path == "/api/v6/linha":
                r = hub.receber_lote(corpo, origem="esp-wifi")
                # comandos pendentes do(s) no(s) que acabaram de falar
                pend: list[str] = []
                for bruta in corpo.split("\n"):
                    ok, _, campos = validar_telemetria(bruta)
                    if ok:
                        pend += hub.comandos_pendentes(para_int(campos["ID"], -1))
                r["comandos"] = pend
                return self._json(200, r)
            if u.path in ("/api/central/compra", "/api/central/pedido"):
                # a loja entrega aqui; nao exige login porque quem compra nao tem conta na gestao
                tipo = u.path.rsplit("/", 1)[-1]
                try:
                    d = json.loads(corpo or "{}")
                except ValueError:
                    return self._json(400, {"ok": False, "erro": "json invalido"})
                if len(corpo or "") > 64_000 or d.get("_formato") != f"physis-{tipo}/1" or not isinstance(d.get("numero"), str):
                    return self._json(400, {"ok": False, "erro": "registro invalido"})
                r = hub.central_por(tipo, d["numero"], d)
                return self._json(200 if r["ok"] else 400, r)
            if u.path == "/api/central/alocacao":
                # interno: a direcao define os consultores e cada consultor aceita a sua parte
                if self._barrado():
                    return
                try:
                    d = json.loads(corpo or "{}")
                except ValueError:
                    return self._json(400, {"ok": False, "erro": "json invalido"})
                if len(corpo or "") > 64_000 or d.get("_formato") != "physis-alocacao/1" or not isinstance(d.get("id"), str):
                    return self._json(400, {"ok": False, "erro": "registro invalido"})
                r = hub.central_gravar("alocacao", d["id"], d)
                return self._json(200 if r["ok"] else 400, r)
            if u.path.startswith("/api/central/compra/") and u.path.endswith("/aprovar"):
                q = self._quem()          # aprovar dispara a montagem e o código: sempre com sessão
                if not q:
                    return self._json(401, {"ok": False, "erro": "entre com usuario e senha", "login": True})
                numero = u.path.split("/")[-2]
                ok = hub.central_marcar("compra", numero, "aprovado", q["usuario"] if q else "")
                if not ok:
                    return self._json(404, {"ok": False})
                # montagem automática: número, plataforma, código e e-mail de acesso
                base = url_publica or (("https" if self.headers.get("X-Forwarded-Proto") == "https" else "http") + "://" + (self.headers.get("Host") or "localhost"))
                inst = hub.instalar_compra(numero, base, fabricar, q["usuario"] if q else "")
                if inst.get("ok") and not inst.get("repetido") and correio.configurado():
                    threading.Thread(target=correio.enviar_fila, args=(hub, inst["numero"]), daemon=True).start()
                    inst["email"] = "enviando"
                return self._json(200, {"ok": True, "instalacao": inst})
            if u.path.startswith("/api/ativar/"):
                # o cliente digita o código do e-mail; certo -> baixa a plataforma montada para ele
                try:
                    d = json.loads(corpo or "{}")
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
                q = self._quem()
                if not q:
                    return self._json(401, {"ok": False, "erro": "entre com usuario e senha", "login": True})
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
                try:
                    d = json.loads(corpo or "{}")
                except ValueError:
                    return self._json(400, {"ok": False, "erro": "json invalido"})
                if u.path == "/api/conta/sair":
                    hub.sair(self._token_sessao())
                    return self._json_cookie(200, {"ok": True}, "physis_sessao=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict")
                if u.path == "/api/conta/criar":
                    q = self._quem()
                    r = hub.criar_conta(str(d.get("nome", "")), str(d.get("usuario", "")), str(d.get("senha", "")), q["id"] if q else None)
                    if not r["ok"]:
                        return self._json(400, r)
                    if not r.get("primeira"):
                        return self._json(200, r)
                r = hub.entrar(str(d.get("usuario", "")), str(d.get("senha", "")))
                if not r["ok"]:
                    return self._json(429 if r.get("espera") else 401, r)
                tk = r.pop("token")
                return self._json_cookie(200, r, f"physis_sessao={tk}; Path=/; Max-Age={hub.SESSAO_S}; HttpOnly; SameSite=Strict")
            if u.path.startswith("/api/loja/item/"):
                # catálogo da loja: sempre exige sessão, mesmo em instalação sem login
                q = self._quem()
                if not q:
                    return self._json(401, {"ok": False, "erro": "entre com usuario e senha", "login": True})
                partes = u.path.split("/")          # ['', 'api', 'loja', 'item', <id>, (acao)]
                if len(partes) not in (5, 6):
                    return self._json(404, {"ok": False, "erro": "rota desconhecida"})
                try:
                    d = json.loads(corpo or "{}")
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
                        linha = str(json.loads(linha).get("comando", ""))
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
    hub = Hub(os.environ.get("PHYSIS_BANCO", "physis-hub.db"),
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
    saude_fundo = saude_mod.Saude(hub)          # doses esquecidas e avisos aos cuidadores, mesmo sem a tela aberta
    threading.Thread(target=saude_mod.rodar, args=(saude_fundo, parar),
                     kwargs={"enviar": lambda: saude_mod.enviar_avisos(hub, correio.enviar_fila)}, daemon=True).start()
    srv = iniciar(hub, porta, os.environ.get("PHYSIS_TOKEN"), clima=clima)
    print(f"Physis Hub em http://0.0.0.0:{porta}  receptor={rx or 'nao configurado'}  simulador={sim or 'desligado'}")
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
