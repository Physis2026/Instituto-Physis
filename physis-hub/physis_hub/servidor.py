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
from urllib.parse import parse_qs, quote, urlparse

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
    return ("default-src 'self'; script-src 'self' 'unsafe-inline'" + s + "; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'" + w + "; frame-src 'self' blob: data:" + s + "; "
            "media-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'")


def criar_manipulador(hub: Hub, token: str | None, instancia: dict | None = None):
    instancia = instancia if instancia is not None else ler_instancia()
    exige_login = bool(instancia.get("login"))
    csp = politica(os.environ.get("PHYSIS_CHAMADAS") or instancia.get("chamadas"))
    class Manipulador(BaseHTTPRequestHandler):
        # Cabecalhos de seguranca em toda resposta. As telas usam script e estilo dentro da pagina,
        # por isso 'unsafe-inline'; de fora do proprio servidor, so o servidor de chamadas da Physis, se configurado.
        def end_headers(self):
            self.send_header("Content-Security-Policy", csp)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            super().end_headers()

        server_version = "PhysisHub/0.1"

        def log_message(self, *a):          # silencioso; a saude fica em /api/saude
            pass

        def _json(self, codigo: int, obj) -> None:
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
            return self.rfile.read(n).decode("utf-8", errors="replace")

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
                    "senha_min": hub.SENHA_MIN}

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
                if self._barrado():
                    return
                return self._arquivo(WEB / "gestao.html", "text/html; charset=utf-8")
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

        def do_POST(self):
            u = urlparse(self.path)
            if u.path == "/api/central/arquivo":
                # arquivo de apoio do pedido: corpo binario, ate 20 MB; publico como o proprio pedido
                q = parse_qs(u.query)
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    n = -1
                if n <= 0 or n > hub.ARQUIVO_MAX:
                    return self._recusar_corpo("arquivo vazio ou maior que 20 MB")
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
                if self._barrado():
                    return
                q = self._quem()
                ok = hub.central_marcar("compra", u.path.split("/")[-2], "aprovado", q["usuario"] if q else "")
                return self._json(200 if ok else 404, {"ok": ok})
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


def iniciar(hub: Hub, porta: int = 8700, token: str | None = None, endereco: str = "0.0.0.0", instancia: dict | None = None):
    srv = ThreadingHTTPServer((endereco, porta), criar_manipulador(hub, token, instancia))
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
    srv = iniciar(hub, porta, os.environ.get("PHYSIS_TOKEN"))
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
