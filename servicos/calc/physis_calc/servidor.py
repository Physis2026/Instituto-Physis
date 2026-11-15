"""Servidor HTTP local dos motores de cálculo (só biblioteca padrão; os motores importam as bibliotecas na hora).

    GET  /saude                     {"ok": true, "motores": {"pv": true, ...}}
    POST /pv | /eolica | /termica | /rede-agua | /drenagem      corpo JSON (veja cada módulo)
         ?somente_entrada=1 (termica, rede-agua, drenagem): devolve só o IDF/INP montado, sem rodar o motor

Variáveis: PHYSIS_CALC_PORTA (8710), PHYSIS_CALC_ENDERECO (0.0.0.0 no contêiner, rede interna),
PHYSIS_CALC_CHAVE (se definida, exige "Authorization: Bearer <chave>"), PHYSIS_CALC_SIMULTANEOS (2),
PHYSIS_CALC_TEMPO (s, EnergyPlus), PHYSIS_CALC_EPW (pasta dos arquivos .epw).
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import __version__, drenagem, eolica, pv, rede_agua, termica
from .comum import EntradaInvalida, MotorIndisponivel, tem_modulo

log = logging.getLogger("physis_calc")
MAX_CORPO = 4 * 1024 * 1024


def motores() -> dict:
    return {"pv": tem_modulo("pvlib"), "eolica": tem_modulo("windpowerlib"),
            "termica": termica.energyplus() is not None, "rede-agua": tem_modulo("wntr"), "drenagem": tem_modulo("pyswmm")}


def rotear(rota: str, corpo: dict, somente_entrada: bool) -> dict:
    if rota == "/pv":
        return pv.calcular(corpo)
    if rota == "/eolica":
        return eolica.calcular(corpo)
    if rota == "/termica":
        return termica.calcular(corpo, somente_idf=somente_entrada)
    if rota == "/rede-agua":
        return rede_agua.calcular(corpo, somente_inp=somente_entrada)
    if rota == "/drenagem":
        return drenagem.calcular(corpo, somente_inp=somente_entrada)
    raise KeyError(rota)


def criar_manipulador(chave: str | None, vagas: threading.Semaphore):
    class Manipulador(BaseHTTPRequestHandler):
        server_version = "PhysisCalc"
        sys_version = ""

        def log_message(self, fmt, *args):
            log.info("%s %s", self.address_string(), fmt % args)

        def _json(self, codigo: int, dados: dict):
            b = json.dumps(dados, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(b)

        def _autorizado(self) -> bool:
            if not chave:
                return True
            dado = self.headers.get("Authorization", "")
            return dado.startswith("Bearer ") and hmac.compare_digest(dado[7:].encode(), chave.encode())

        def do_GET(self):
            if urlparse(self.path).path == "/saude":
                return self._json(200, {"ok": True, "versao": __version__, "motores": motores()})
            self._json(404, {"ok": False, "erro": "rota desconhecida"})

        def do_POST(self):
            u = urlparse(self.path)
            if not self._autorizado():
                return self._json(401, {"ok": False, "erro": "chave inválida"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = -1
            if n <= 0 or n > MAX_CORPO:
                return self._json(413 if n > MAX_CORPO else 400, {"ok": False, "erro": "corpo ausente ou grande demais"})
            try:
                corpo = json.loads(self.rfile.read(n), parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
                if not isinstance(corpo, dict):
                    raise ValueError("objeto")
            except ValueError:
                return self._json(400, {"ok": False, "erro": "JSON inválido"})
            somente = parse_qs(u.query).get("somente_entrada", ["0"])[0] == "1"
            if not vagas.acquire(timeout=1):
                return self._json(429, {"ok": False, "erro": "motores ocupados; tente de novo"})
            try:
                return self._json(200, rotear(u.path, corpo, somente))
            except KeyError:
                return self._json(404, {"ok": False, "erro": "rota desconhecida"})
            except EntradaInvalida as exc:
                return self._json(400, {"ok": False, "erro": str(exc)})
            except MotorIndisponivel as exc:
                return self._json(503, {"ok": False, "erro": str(exc)})
            except Exception:  # noqa: BLE001 — rastro só no registro do serviço
                log.error("erro em %s\n%s", u.path, traceback.format_exc())
                return self._json(500, {"ok": False, "erro": "erro interno"})
            finally:
                vagas.release()

    return Manipulador


def iniciar(porta: int = 8710, endereco: str = "127.0.0.1", chave: str | None = None, simultaneos: int = 2):
    srv = ThreadingHTTPServer((endereco, porta), criar_manipulador(chave, threading.Semaphore(simultaneos)))
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    porta = int(os.environ.get("PHYSIS_CALC_PORTA", "8710"))
    endereco = os.environ.get("PHYSIS_CALC_ENDERECO", "127.0.0.1")
    srv = iniciar(porta, endereco, os.environ.get("PHYSIS_CALC_CHAVE") or None,
                  int(os.environ.get("PHYSIS_CALC_SIMULTANEOS", "2")))
    log.info("Physis Calc %s em %s:%d  motores=%s", __version__, endereco, porta, motores())
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
