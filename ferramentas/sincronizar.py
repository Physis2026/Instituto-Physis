#!/usr/bin/env python3
"""Mantém as cópias embutidas iguais ao original. Rode depois de mudar um original.

    python ferramentas/sincronizar.py            # aplica
    python ferramentas/sincronizar.py --conferir # só confere (para testes e CI); sai com erro se houver diferença

Por que existe: os programas da Physis são arquivos HTML únicos, que funcionam sem internet.
Por isso o exportador de documentos (sistema/physis-exportar.js) vai copiado dentro de cada um,
e alguns programas vão embutidos em base64 dentro da plataforma (physis-hub/web/painel.html).
Copiar à mão gera versões diferentes; este script faz a cópia sempre igual ao original.

O que faz:
1. Troca o bloco do exportador em cada HTML pelo conteúdo de sistema/physis-exportar.js.
2. Corrige textos pedidos pela Physis nos programas (ex.: o SCADA não se chama mais
   "fazenda net zero").
3. Refaz as cópias em base64 (PROGRAMAS) dentro da plataforma com o mesmo tratamento.
"""
from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ORIGEM = RAIZ / "sistema" / "physis-exportar.js"
INICIO = "/* physis-exportar.js v"
FIM = '})(typeof window !== "undefined" ? window : this);'
ALVOS = [
    RAIZ / "physis-hub" / "docs" / "physis-exportar.js",
    RAIZ / "sistema" / "gestao-interna-physis.html",
    RAIZ / "sistema" / "physis-scada-demo.html",
    RAIZ / "sistema" / "physis-tela-cliente.html",
    RAIZ / "physis-hub" / "web" / "painel.html",
]
PLATAFORMA = RAIZ / "physis-hub" / "web" / "painel.html"
# Textos que a Physis pediu para mudar (14/11/2026): o SCADA é da organização do cliente, não de uma "fazenda net zero".
TROCAS = [
    ("Physis · SCADA · fazenda net zero", "Physis · SCADA"),
    ("SCADA · fazenda net zero", "SCADA"),
    ("SCADA · net zero farm", "SCADA"),
    ("Fazenda simulada · o dado não é real", "Simulação · o dado não é real"),
    ("Simulated farm · the data is not real", "Simulation · the data is not real"),
]


def trocar_exportar(texto: str, novo: str) -> str:
    i = texto.find(INICIO)
    if i < 0:
        return texto
    j = texto.find(FIM, i)
    if j < 0:
        raise SystemExit("bloco do exportador sem fim reconhecível")
    return texto[:i] + novo + texto[j + len(FIM):]


def tratar(texto: str, novo: str) -> str:
    texto = trocar_exportar(texto, novo)
    for a, b in TROCAS:
        texto = texto.replace(a, b)
    return texto


def tratar_programas(html: str, novo: str) -> str:
    m = re.search(r"const PROGRAMAS = \{(.*?)\};\n", html, re.S)
    if not m:
        return html
    def um(mm: re.Match) -> str:
        bruto = base64.b64decode(mm.group(2)).decode("utf-8")
        return f'{mm.group(1)}:"' + base64.b64encode(tratar(bruto, novo).encode("utf-8")).decode("ascii") + '"'
    corpo = re.sub(r'(\w+):"([A-Za-z0-9+/=]+)"', um, m.group(1))
    return html[:m.start(1)] + corpo + html[m.end(1):]


def main() -> int:
    conferir = "--conferir" in sys.argv
    novo = ORIGEM.read_text(encoding="utf-8").replace("\r\n", "\n").rstrip("\n")
    if not novo.startswith(INICIO) or not novo.endswith(FIM):
        raise SystemExit("o original do exportador precisa começar e terminar com as marcas conhecidas")
    diferentes = []
    for arq in ALVOS:
        antes = arq.read_text(encoding="utf-8")
        depois = tratar(antes, novo) if arq.suffix == ".html" else novo + "\n"
        if arq == PLATAFORMA:
            depois = tratar_programas(depois, novo)
        if depois != antes:
            diferentes.append(arq.relative_to(RAIZ))
            if not conferir:
                arq.write_text(depois, encoding="utf-8", newline="\n")
    for d in diferentes:
        print(("diferente: " if conferir else "atualizado: ") + str(d))
    if not diferentes:
        print("tudo igual ao original")
    return 1 if (conferir and diferentes) else 0


if __name__ == "__main__":
    raise SystemExit(main())
