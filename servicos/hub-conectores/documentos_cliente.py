"""Cliente do hub para o serviço de documentos (LibreOffice PDF/A + veraPDF). Opcional: o hub funciona sem ele.

Para colocar em physis_hub/ quando a equipe decidir ligar. Uso sugerido em documentos.converter_pdfa:
sem `soffice` local e com PHYSIS_DOC_URL definida, chamar `pdfa_converter(...)`; depois `pdfa_validar(pdf)` para
mostrar "PDF/A-2b conferido pelo veraPDF" (ou as regras que falharam) na tela.

Variáveis: PHYSIS_DOC_URL (compose: http://documentos:8720), PHYSIS_DOC_CHAVE, PHYSIS_DOC_TEMPO (s, padrão 120).
Só destino da rede local/interna (mesma regra de robos.destino_local), salvo PHYSIS_DOC_EXTERNO=1.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("physis.documentos")
MAX_RESPOSTA = 60 * 1024 * 1024


def _local(url: str) -> bool:
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return host == "localhost" or "." not in host or host.endswith((".local", ".lan", ".internal", ".localhost"))


def doc_url() -> str:
    url = (os.environ.get("PHYSIS_DOC_URL") or "").strip().rstrip("/")
    if url and (not url.startswith(("http://", "https://")) or (not _local(url) and os.environ.get("PHYSIS_DOC_EXTERNO") != "1")):
        log.warning("PHYSIS_DOC_URL fora da rede local: ignorada")
        return ""
    return url


def _pedir(caminho: str, corpo: bytes | None, tipo: str, tempo: float):
    """(status, cabeçalhos, bytes) ou None se o serviço está ausente/fora do ar."""
    url = doc_url()
    if not url:
        return None
    req = urllib.request.Request(url + caminho, data=corpo, method="POST" if corpo is not None else "GET",
                                 headers={"Content-Type": tipo, "User-Agent": "PhysisHub/1.0"})
    chave = os.environ.get("PHYSIS_DOC_CHAVE")
    if chave:
        req.add_header("Authorization", f"Bearer {chave}")
    try:
        with urllib.request.urlopen(req, timeout=tempo) as r:
            return r.status, dict(r.headers), r.read(MAX_RESPOSTA)
    except urllib.error.HTTPError as e:
        if e.code in (400, 413, 422):
            return e.code, dict(e.headers), e.read(65536)
        log.info("documentos %s: HTTP %s", caminho, e.code)
        return None
    except (urllib.error.URLError, OSError) as exc:
        log.info("documentos %s: %s", caminho, type(exc).__name__)
        return None


def _tempo() -> float:
    return float(os.environ.get("PHYSIS_DOC_TEMPO") or 120)


def doc_saude(tempo: float = 2.0) -> dict | None:
    r = _pedir("/saude", None, "application/json", tempo)
    try:
        return json.loads(r[2]) if r and r[0] == 200 else None
    except ValueError:
        return None


def pdfa_converter(odf: bytes, extensao: str = "odt", validar: bool = True) -> dict | None:
    """{"ok": True, "pdf": bytes, "pdfa": "conforme"|"nao-conforme"|"nao-validado"} | {"ok": False, "erro"} | None."""
    r = _pedir(f"/pdfa/converter?extensao={extensao}" + ("&validar=1" if validar else ""), odf,
               "application/vnd.oasis.opendocument.text" if extensao == "odt" else "application/vnd.oasis.opendocument.spreadsheet",
               _tempo())
    if r is None:
        return None
    st, cab, corpo = r
    if st == 200 and corpo.startswith(b"%PDF-"):
        return {"ok": True, "pdf": corpo, "pdfa": cab.get("X-Physis-PDFA", "nao-validado")}
    try:
        return {"ok": False, "erro": json.loads(corpo).get("erro", f"HTTP {st}")}
    except ValueError:
        return {"ok": False, "erro": f"HTTP {st}"}


def pdfa_validar(pdf: bytes, perfil: str = "2b") -> dict | None:
    """Resumo do veraPDF: {"ok", "compliant", "perfil", "regras_falhas", "falhas": [...]} ou None."""
    r = _pedir(f"/pdfa/validar?perfil={perfil}", pdf, "application/pdf", _tempo())
    if r is None:
        return None
    try:
        return json.loads(r[2])
    except ValueError:
        return None
