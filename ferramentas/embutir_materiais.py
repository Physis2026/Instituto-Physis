#!/usr/bin/env python3
"""Coloca a base de materiais (sistema/physis-materiais.json) dentro do SustainKit e do Planejador.

Por quê: os dois programas também abrem sozinhos (arquivo, pacote, demo), sem a plataforma.
Dentro da plataforma eles leem a base do documento pai (<script id="base-materiais"> do painel);
fora dela, leem esta cópia embutida. Rodar de novo troca o bloco; não duplica.

    python ferramentas/embutir_materiais.py             # aplica
    python ferramentas/embutir_materiais.py --conferir  # só confere; sai com erro se alguma cópia estiver diferente
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BASE = RAIZ / "sistema" / "physis-materiais.json"
ALVOS = [RAIZ / "sistema" / "SustainKit_Definitivo.html",
         RAIZ / "modulos" / "planejador" / "planejador-physis.html"]
IDENT = "base-materiais"


def bloco() -> str:
    dados = json.loads(BASE.read_text(encoding="utf-8"))           # confere que é JSON válido
    texto = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return f'<script type="application/json" id="{IDENT}">{texto}</script>'


def embutir(html: str) -> str:
    novo = bloco()
    padrao = re.compile(rf'<script type="application/json" id="{IDENT}">.*?</script>', re.S)
    if padrao.search(html):
        return padrao.sub(lambda _m: novo, html, count=1)
    m = re.search(r"</head>\s*<body", html)                         # o </head> de verdade (não um texto dentro de biblioteca)
    if not m:
        raise SystemExit("não achei o </head> seguido de <body>")
    return html[:m.start()] + novo + "\n" + html[m.start():]


def main() -> int:
    conferir = "--conferir" in sys.argv
    diferentes = []
    for alvo in ALVOS:
        antes = alvo.read_text(encoding="utf-8")
        depois = embutir(antes)
        if depois != antes:
            diferentes.append(alvo.relative_to(RAIZ))
            if not conferir:
                alvo.write_text(depois, encoding="utf-8", newline="")
    for d in diferentes:
        print(("diferente: " if conferir else "atualizado: ") + str(d))
    if not diferentes:
        print("base de materiais igual nas cópias")
    return 1 if (conferir and diferentes) else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
