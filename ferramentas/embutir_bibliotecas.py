#!/usr/bin/env python3
"""Coloca dentro do Planejador as bibliotecas e fontes que ele buscava na internet.

Por quê: a plataforma bloqueia tudo o que vem de fora (proteção contra roubo de dados) e o
sistema precisa rodar sem internet no servidor do cliente. Então o leitor de PDF (pdf.js),
o leitor/gravador de .zip/.docx (JSZip) e as fontes (Lexend, Atkinson Hyperlegible) passam a
viajar dentro do próprio arquivo HTML.

As cópias ficam em vendor/ (com a conferência de integridade em vendor/LEIA-ME.md).
Rodar de novo é seguro: os blocos marcados com id="vend-..." são trocados, não duplicados.

    python ferramentas/embutir_bibliotecas.py
"""
from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
VENDOR = RAIZ / "vendor"
ALVOS = [RAIZ / "modulos" / "planejador" / "planejador-physis.html"]

FONTES = [("Lexend", w, f"lexend-latin-{w}-normal.woff2") for w in (300, 400, 500, 600)] + \
         [("Atkinson Hyperlegible", w, f"atkinson-hyperlegible-latin-{w}-normal.woff2") for w in (400, 700)]
SCRIPTS = [("vend-jszip", "jszip.min.js"), ("vend-pdf", "pdf.min.js"), ("vend-pdfworker", "pdf.worker.min.js")]

# o que o Planejador tinha antes (endereços de fora)
EXTERNO_FONTES = re.compile(r'<link rel="preconnect" href="https://fonts\.googleapis\.com">'
                            r'<link href="https://fonts\.googleapis\.com/css2\?[^"]*" rel="stylesheet">')
EXTERNO_SCRIPTS = re.compile(r'<script src="https://cdnjs\.cloudflare\.com/ajax/libs/jszip/[^"]+"></script>'
                             r'<script src="https://cdnjs\.cloudflare\.com/ajax/libs/pdf\.js/[^"]+/pdf\.min\.js"></script>'
                             r'<script src="https://cdnjs\.cloudflare\.com/ajax/libs/pdf\.js/[^"]+/pdf\.worker\.min\.js"></script>')
BLOCO_FONTES = re.compile(r'<style id="vend-fontes">.*?</style>', re.S)


def bloco_fontes() -> str:
    regras = []
    for familia, peso, arq in FONTES:
        b64 = base64.b64encode((VENDOR / "fontes" / arq).read_bytes()).decode()
        regras.append(f"@font-face{{font-family:'{familia}';font-style:normal;font-weight:{peso};font-display:swap;"
                      f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}")
    return '<style id="vend-fontes">' + "".join(regras) + "</style>"


def bloco_script(ident: str, arq: str) -> str:
    texto = (VENDOR / arq).read_text(encoding="utf-8")
    if re.search(r"(?i)</script", texto):
        raise SystemExit(f"{arq} contém '</script' e não pode ir embutido")
    return f'<script id="{ident}">{texto}</script>'


def embutir(html: str) -> str:
    fontes = bloco_fontes()
    if BLOCO_FONTES.search(html):
        html = BLOCO_FONTES.sub(lambda _: fontes, html, count=1)
    elif EXTERNO_FONTES.search(html):
        html = EXTERNO_FONTES.sub(lambda _: fontes, html, count=1)
    else:
        raise SystemExit("não achei onde ficam as fontes")
    novos = "".join(bloco_script(i, a) for i, a in SCRIPTS)
    ja = re.compile("".join(rf'<script id="{i}">.*?</script>' for i, _ in SCRIPTS), re.S)
    if ja.search(html):
        html = ja.sub(lambda _: novos, html, count=1)
    elif EXTERNO_SCRIPTS.search(html):
        html = EXTERNO_SCRIPTS.sub(lambda _: novos, html, count=1)
    else:
        raise SystemExit("não achei onde ficam as bibliotecas")
    return html


def main() -> None:
    for alvo in ALVOS:
        antes = alvo.read_text(encoding="utf-8")
        depois = embutir(antes)
        if re.search(r"https://(cdnjs|fonts\.googleapis|fonts\.gstatic|cdn\.jsdelivr|unpkg)", depois):
            raise SystemExit(f"{alvo.name}: ainda busca algo na internet")
        if depois != antes:
            alvo.write_text(depois, encoding="utf-8", newline="")
        print(f"{alvo.relative_to(RAIZ)}: {len(antes) // 1024} kB -> {len(depois) // 1024} kB")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
