"""API local de documentos (só biblioteca padrão; chama os programas soffice e verapdf).

    GET  /saude                              {"ok": true, "soffice": bool, "verapdf": bool}
    POST /pdfa/converter?extensao=odt|ods[&validar=1]
         corpo = bytes do ODT/ODS  ->  application/pdf (PDF/A-2b). Com validar=1, cabeçalho
         X-Physis-PDFA: conforme | nao-conforme | nao-validado
    POST /pdfa/validar[?perfil=2b]
         corpo = bytes do PDF  ->  {"ok", "compliant", "perfil", "regras_ok", "regras_falhas", "falhas": [...]}

Variáveis: PHYSIS_DOC_PORTA (8720), PHYSIS_DOC_ENDERECO (127.0.0.1; 0.0.0.0 no contêiner, rede interna),
PHYSIS_DOC_CHAVE (se definida, exige "Authorization: Bearer"), PHYSIS_SOFFICE, PHYSIS_VERAPDF, PHYSIS_DOC_TEMPO (s).
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__

log = logging.getLogger("physis_doc")
MAX_CORPO = 50 * 1024 * 1024
# mesmo filtro de physis_hub/documentos.py (PDF/A-2 = SelectPdfVersion 2, PDF marcado)
PDFA_FILTRO = 'pdf:writer_pdf_Export:{"SelectPdfVersion":{"type":"long","value":"2"},"UseTaggedPDF":{"type":"boolean","value":"true"}}'
PERFIS = {"1a", "1b", "2a", "2b", "2u", "3a", "3b", "3u", "4", "4e", "4f", "ua1"}


class Falha(Exception):
    def __init__(self, codigo: int, erro: str):
        super().__init__(erro)
        self.codigo, self.erro = codigo, erro


def soffice() -> str | None:
    return os.environ.get("PHYSIS_SOFFICE") or shutil.which("soffice") or shutil.which("libreoffice")


def verapdf() -> str | None:
    return os.environ.get("PHYSIS_VERAPDF") or shutil.which("verapdf")


def _tempo() -> float:
    return float(os.environ.get("PHYSIS_DOC_TEMPO", "120"))


def converter(odf: bytes, extensao: str = "odt") -> bytes:
    if extensao not in ("odt", "ods"):
        raise Falha(400, "extensao deve ser odt ou ods")
    if not odf.startswith(b"PK\x03\x04"):
        raise Falha(400, "o arquivo não é um ODT/ODS")
    exe = soffice()
    if not exe:
        raise Falha(503, "LibreOffice (soffice) não instalado")
    with tempfile.TemporaryDirectory(prefix="pdfa-") as d:
        ent = Path(d) / f"documento.{extensao}"
        ent.write_bytes(odf)
        filtro = PDFA_FILTRO.replace("writer_pdf_Export", "calc_pdf_Export") if extensao == "ods" else PDFA_FILTRO
        cmd = [exe, f"-env:UserInstallation={(Path(d) / 'perfil').as_uri()}", "--headless", "--norestore",
               "--convert-to", filtro, "--outdir", d, str(ent)]
        try:
            subprocess.run(cmd, capture_output=True, timeout=_tempo(), check=False)
        except subprocess.TimeoutExpired:
            raise Falha(504, "a conversão passou do tempo") from None
        sai = Path(d) / "documento.pdf"
        if not sai.is_file() or sai.stat().st_size == 0:
            raise Falha(422, "o LibreOffice não gerou o PDF")
        return sai.read_bytes()


def resumo_verapdf(xml_texto: str, perfil_pedido: str = "2b") -> dict:
    """Resumo do relatório XML (MRR) do veraPDF: conformidade, perfil e regras que falharam."""
    try:
        raiz = ET.fromstring(xml_texto)
    except ET.ParseError:
        raise Falha(500, "relatório do veraPDF ilegível") from None
    rel = next((e for e in raiz.iter() if e.tag.endswith("validationReport")), None)
    if rel is None:
        erro = next((e.text for e in raiz.iter() if e.tag.endswith("exceptionMessage") and e.text), None)
        return {"ok": False, "erro": "o veraPDF não validou o arquivo" + (f": {erro[:200]}" if erro else "")}
    det = next((e for e in rel.iter() if e.tag.endswith("details")), None)
    falhas = []
    for r in rel.iter():
        if r.tag.endswith("rule") and r.get("status") == "failed":
            desc = next((x.text for x in r if x.tag.endswith("description")), "") or ""
            falhas.append({"especificacao": r.get("specification", ""), "clausula": r.get("clause", ""),
                           "teste": r.get("testNumber", ""), "ocorrencias": int(r.get("failedChecks", "0") or 0),
                           "descricao": desc.strip()[:300]})
    nome = rel.get("profileName", "")
    return {"ok": True, "compliant": rel.get("isCompliant") == "true",
            "perfil": nome.replace(" validation profile", "") or f"PDF/A-{perfil_pedido.upper()}",
            "regras_ok": int(det.get("passedRules", "0")) if det is not None else None,
            "regras_falhas": int(det.get("failedRules", "0")) if det is not None else len(falhas),
            "falhas": falhas[:50]}


def validar(pdf: bytes, perfil: str = "2b") -> dict:
    if perfil not in PERFIS:
        raise Falha(400, "perfil inválido")
    if not pdf.startswith(b"%PDF-"):
        raise Falha(400, "o arquivo não é um PDF")
    exe = verapdf()
    if not exe:
        raise Falha(503, "veraPDF não instalado")
    with tempfile.TemporaryDirectory(prefix="vera-") as d:
        arq = Path(d) / "documento.pdf"
        arq.write_bytes(pdf)
        try:
            p = subprocess.run([exe, "--flavour", perfil, "--format", "mrr", "--maxfailuresdisplayed", "5", str(arq)],
                               capture_output=True, text=True, timeout=_tempo(), check=False)
        except subprocess.TimeoutExpired:
            raise Falha(504, "a validação passou do tempo") from None
    return resumo_verapdf(p.stdout, perfil)


def criar_manipulador(chave: str | None, vagas: threading.Semaphore):
    class Manipulador(BaseHTTPRequestHandler):
        server_version = "PhysisDoc"
        sys_version = ""

        def log_message(self, fmt, *args):
            log.info("%s %s", self.address_string(), fmt % args)

        def _enviar(self, codigo: int, corpo: bytes, tipo: str, extra: dict | None = None):
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(corpo)

        def _json(self, codigo: int, dados: dict):
            self._enviar(codigo, json.dumps(dados, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):
            if urlparse(self.path).path == "/saude":
                return self._json(200, {"ok": True, "versao": __version__, "soffice": soffice() is not None,
                                        "verapdf": verapdf() is not None})
            self._json(404, {"ok": False, "erro": "rota desconhecida"})

        def do_POST(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if chave:
                dado = self.headers.get("Authorization", "")
                if not (dado.startswith("Bearer ") and hmac.compare_digest(dado[7:].encode(), chave.encode())):
                    return self._json(401, {"ok": False, "erro": "chave inválida"})
            if u.path not in ("/pdfa/converter", "/pdfa/validar"):
                return self._json(404, {"ok": False, "erro": "rota desconhecida"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = -1
            if n <= 0 or n > MAX_CORPO:
                return self._json(413 if n > MAX_CORPO else 400, {"ok": False, "erro": "corpo ausente ou grande demais"})
            corpo = self.rfile.read(n)
            if not vagas.acquire(timeout=2):
                return self._json(429, {"ok": False, "erro": "ocupado; tente de novo"})
            try:
                if u.path == "/pdfa/validar":
                    return self._json(200, validar(corpo, q.get("perfil", "2b")))
                pdf = converter(corpo, q.get("extensao", "odt"))
                extra = {"Content-Disposition": 'attachment; filename="documento.pdf"'}
                if q.get("validar") == "1":
                    try:
                        r = validar(pdf, "2b")
                        extra["X-Physis-PDFA"] = "conforme" if r.get("compliant") else "nao-conforme"
                    except Falha:
                        extra["X-Physis-PDFA"] = "nao-validado"
                return self._enviar(200, pdf, "application/pdf", extra)
            except Falha as f:
                return self._json(f.codigo, {"ok": False, "erro": f.erro})
            except Exception:  # noqa: BLE001
                log.exception("erro em %s", u.path)
                return self._json(500, {"ok": False, "erro": "erro interno"})
            finally:
                vagas.release()

    return Manipulador


def iniciar(porta: int = 8720, endereco: str = "127.0.0.1", chave: str | None = None, simultaneos: int = 2):
    srv = ThreadingHTTPServer((endereco, porta), criar_manipulador(chave, threading.Semaphore(simultaneos)))
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    srv = iniciar(int(os.environ.get("PHYSIS_DOC_PORTA", "8720")), os.environ.get("PHYSIS_DOC_ENDERECO", "127.0.0.1"),
                  os.environ.get("PHYSIS_DOC_CHAVE") or None, int(os.environ.get("PHYSIS_DOC_SIMULTANEOS", "2")))
    log.info("Physis Doc %s  soffice=%s verapdf=%s", __version__, soffice(), verapdf())
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
