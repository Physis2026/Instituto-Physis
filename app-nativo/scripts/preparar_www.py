"""Monta app-nativo/www/ (o que o Capacitor embute no app) a partir da plataforma pronta.

Uso (de dentro de app-nativo/):
    python scripts/preparar_www.py                                   # da physis-hub/web do repositório
    python scripts/preparar_www.py --origem ../pacotes/x.zip         # de um pacote do montar.py (.zip ou pasta)
    python scripts/preparar_www.py --hub https://hub.cliente.example # fixa o servidor na CSP (app de um cliente só)

O que faz:
1. Copia a plataforma do cliente: painel.html vira index.html; as outras telas, vendor/ e app/ (sem o sw.js:
   no app o service worker não é preciso, os arquivos já estão no celular). A Gestão (gestao.html) nunca entra:
   plataforma e Gestão não se misturam.
2. Copia www-extra/ (physis-nativo.js, primeiro-uso.html/.js) e sistema/physis-ble.js.
3. No <head> de index.html e primeiro-uso.html: a política de conteúdo (CSP) do app e os scripts do app.
   O physis-nativo.js põe window.PHYSIS_NATIVO = true antes de qualquer outro script.
   A CSP aceita as origens do Capacitor (Android https://localhost, iOS capacitor://localhost) e, para os
   pedidos ao servidor, só https (ou só o --hub dado).
Só biblioteca padrão do Python.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent.parent          # app-nativo/
RAIZ = AQUI.parent                                      # repositório
ORIGEM_PADRAO = RAIZ / "physis-hub" / "web"
BLE = RAIZ / "sistema" / "physis-ble.js"
EXTRA = AQUI / "www-extra"

FORA = {"gestao.html"}                                   # nunca no app do cliente
FORA_APP = {"sw.js"}
SCRIPTS = ("physis-nativo.js", "physis-ble.js")
ORIGENS_APP = "capacitor://localhost https://localhost"


def politica(hub: str | None = None) -> str:
    """CSP do app. Igual à do servidor (servidor.politica) no que importa, mais as origens do Capacitor."""
    destino = hub.rstrip("/") if hub else "https:"
    return ("default-src 'self' " + ORIGENS_APP + "; "
            "script-src 'self' " + ORIGENS_APP + " 'unsafe-inline' 'wasm-unsafe-eval'; "
            "style-src 'self' " + ORIGENS_APP + " 'unsafe-inline'; "
            "img-src 'self' " + ORIGENS_APP + " data: blob:; font-src 'self' " + ORIGENS_APP + " data:; "
            "connect-src 'self' " + ORIGENS_APP + " blob: " + destino + "; "
            "worker-src 'self' blob:; frame-src 'self' " + ORIGENS_APP + " blob: data:; media-src 'self' blob:; "
            "object-src 'none'; base-uri 'self'; form-action 'self'")


def injetar(html: str, csp: str, scripts: tuple[str, ...]) -> str:
    """Põe (ou troca) a meta CSP e os scripts logo depois de <head> (e do <meta charset>, se vier logo em seguida)."""
    html = re.sub(r'\s*<meta[^>]+http-equiv=["\']Content-Security-Policy["\'][^>]*>', "", html, flags=re.I)
    for s in scripts:
        html = re.sub(r'\s*<script src="' + re.escape(s) + r'"></script>', "", html)
    bloco = ('\n<meta http-equiv="Content-Security-Policy" content="' + csp + '">'
             + "".join(f'\n<script src="{s}"></script>' for s in scripts))
    m = re.search(r"<head[^>]*>(\s*<meta charset=[^>]*>)?", html, flags=re.I)
    if not m:
        raise ValueError("HTML sem <head>")
    return html[:m.end()] + bloco + html[m.end():]


def achar_web(origem: Path, temp: Path) -> Path:
    """Pasta que tem o painel.html: a própria, <pacote>/web ou dentro de um .zip do montar.py."""
    if origem.is_file() and origem.suffix.lower() == ".zip":
        with zipfile.ZipFile(origem) as z:
            for nome in z.namelist():                    # recusa caminhos que saem da pasta temporária
                if nome.startswith(("/", "\\")) or ".." in Path(nome).parts:
                    raise ValueError(f"caminho suspeito no zip: {nome}")
            z.extractall(temp)
        origem = temp
    candidatos = [origem] + sorted(p.parent for p in origem.rglob("painel.html"))
    for c in candidatos:
        if (c / "painel.html").is_file():
            return c
    raise FileNotFoundError(f"painel.html não encontrado em {origem}")


def preparar(origem: Path = ORIGEM_PADRAO, destino: Path = AQUI / "www", hub: str | None = None,
             ble: Path = BLE, extra: Path = EXTRA) -> dict:
    destino = destino.resolve()
    if destino.exists():
        if destino.parent != AQUI.resolve() and "www" not in destino.name:
            raise ValueError(f"não apago {destino}: o destino tem de ser uma pasta www")
        shutil.rmtree(destino)
    destino.mkdir(parents=True)
    with tempfile.TemporaryDirectory() as t:
        web = achar_web(Path(origem), Path(t))
        for p in sorted(web.iterdir()):
            if p.is_file() and p.suffix.lower() == ".html" and p.name not in FORA:
                shutil.copy2(p, destino / ("index.html" if p.name == "painel.html" else p.name))
            elif p.is_dir() and p.name == "vendor":
                shutil.copytree(p, destino / "vendor")
            elif p.is_dir() and p.name == "app":
                shutil.copytree(p, destino / "app", ignore=lambda _d, nomes: [n for n in nomes if n in FORA_APP])
    for p in sorted(Path(extra).iterdir()):
        if p.is_file():
            shutil.copy2(p, destino / p.name)
    shutil.copy2(ble, destino / "physis-ble.js")

    csp = politica(hub)
    for nome, scripts in (("index.html", SCRIPTS), ("primeiro-uso.html", ("physis-nativo.js",))):
        p = destino / nome
        p.write_text(injetar(p.read_text(encoding="utf-8"), csp, scripts), encoding="utf-8", newline="\n")

    arquivos = sorted(str(p.relative_to(destino)).replace("\\", "/") for p in destino.rglob("*") if p.is_file())
    info = {"gerado": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "origem": str(origem), "hub_fixo": hub or "",
            "arquivos": len(arquivos),
            "impressao": hashlib.sha256("".join(arquivos).encode() + (destino / "index.html").read_bytes()).hexdigest()[:16]}
    (destino / "nativo-versao.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return info


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--origem", type=Path, default=ORIGEM_PADRAO, help="pasta web/, pasta do pacote ou .zip do montar.py")
    ap.add_argument("--destino", type=Path, default=AQUI / "www")
    ap.add_argument("--hub", default=None, help="https://… : só este servidor entra na CSP (opcional)")
    a = ap.parse_args(argv)
    if a.hub and not a.hub.startswith("https://"):
        ap.error("--hub tem de começar com https://")
    info = preparar(a.origem, a.destino, a.hub)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
