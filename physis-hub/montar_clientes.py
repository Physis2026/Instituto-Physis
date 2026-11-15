#!/usr/bin/env python3
"""Monta a plataforma de cada cliente a partir de clientes/clientes.json.

    python montar_clientes.py --saida <pasta>

O código é um só (este repositório). Cada cliente é só uma ficha: organização, módulos e,
para a Casa Physis, o modo de pesquisa. Os programas da Physis (SustainKit, SCADA e
Planejador) vêm das pastas do repositório.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from montar import montar

RAIZ = Path(__file__).resolve().parent.parent
FICHAS = RAIZ / "clientes" / "clientes.json"
PROGRAMAS = {
    "sustainkit": RAIZ / "sistema" / "SustainKit_Definitivo.html",
    "supervisao": RAIZ / "sistema" / "physis-scada-demo.html",
    "planejador": RAIZ / "modulos" / "planejador" / "planejador-physis.html",
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--saida", type=Path, required=True)
    ap.add_argument("--so", default="", help="montar só esta organização")
    a = ap.parse_args()
    a.saida.mkdir(parents=True, exist_ok=True)
    base = json.loads(FICHAS.read_text(encoding="utf-8"))
    fichas, suporte = base["clientes"], base.get("suporte")
    for f in fichas:
        if a.so and f["org"] != a.so:
            continue
        gestao = RAIZ / "sistema" / "gestao-interna-physis.html" if f.get("gestao_interna") else None
        pacote = montar(f["org"], f.get("lugar", "lugar01"), f["modulos"], a.saida, PROGRAMAS["sustainkit"],
                        "[LICENÇA A DEFINIR PELA PHYSIS]", PROGRAMAS["supervisao"], gestao, PROGRAMAS["planejador"],
                        bool(f.get("pesquisa")), f.get("nome", ""), None, suporte)
        print(f"{f['nome']}: {pacote.name} ({pacote.stat().st_size // 1024} kB) · módulos: {', '.join(f['modulos'])}"
              + (" · pesquisa" if f.get("pesquisa") else ""))


if __name__ == "__main__":
    main()
