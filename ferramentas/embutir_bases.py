#!/usr/bin/env python3
"""Coloca dentro da plataforma (painel.html) as bases de dados que ela usa sem servidor.

Por quê: a plataforma também funciona aberta como arquivo e na demonstração, sem servidor.
Então a base de certificações (sistema/physis-certificacoes.json) viaja dentro do HTML, num
bloco <script type="application/json" id="base-...">. Rodar de novo troca o bloco; não duplica.

    python ferramentas/embutir_bases.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PAINEL = RAIZ / "physis-hub" / "web" / "painel.html"
BASES = {"base-certificacoes": RAIZ / "sistema" / "physis-certificacoes.json", "base-plantas": RAIZ / "sistema" / "physis-plantas.json"}
# módulos de cálculo em arquivo próprio (testados à parte), embutidos como <script> no <head>
MODULOS = {"mod-avac": RAIZ / "sistema" / "physis-avac.js", "mod-saude": RAIZ / "sistema" / "physis-saude.js",
           "mod-juridico": RAIZ / "sistema" / "physis-juridico.js"}


def bloco(ident: str, arq: Path) -> str:
    dados = json.loads(arq.read_text(encoding="utf-8"))            # confere que é JSON válido
    texto = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return f'<script type="application/json" id="{ident}">{texto}</script>'


def embutir(html: str) -> str:
    for ident, arq in BASES.items():
        if not arq.is_file():
            continue
        novo = bloco(ident, arq)
        padrao = re.compile(rf'<script type="application/json" id="{ident}">.*?</script>\n?', re.S)
        # sempre no <head>: o código da página lê a base assim que carrega, então ela tem de vir antes
        html = padrao.sub("", html)
        html = html.replace("</head>", novo + "\n</head>", 1)
    for ident, arq in MODULOS.items():
        if not arq.is_file():
            continue
        codigo = arq.read_text(encoding="utf-8")
        if re.search(r"(?i)</script", codigo):
            raise SystemExit(f"{arq.name} contém '</script' e não pode ir embutido")
        novo = f'<script id="{ident}">{codigo}</script>'
        padrao = re.compile(rf'<script id="{ident}">.*?</script>\n?', re.S)
        html = padrao.sub("", html)
        html = html.replace("</head>", novo + "\n</head>", 1)
    return html


def main() -> None:
    antes = PAINEL.read_text(encoding="utf-8")
    depois = embutir(antes)
    if depois != antes:
        PAINEL.write_text(depois, encoding="utf-8", newline="")
    print("bases embutidas:", ", ".join(k for k, v in BASES.items() if v.is_file()) or "nenhuma")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
