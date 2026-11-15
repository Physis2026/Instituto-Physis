#!/usr/bin/env python3
"""Gera sistema/physis-juridico.js a partir das minutas jurídicas (09_Minutas_Juridicas.md).

Leva para as telas: Termos de uso (A), Política de privacidade (B), Licença (C.4) e o canal de
acessibilidade (D.1). Tira as "Notas para a assessoria" (são internas). Os dados da empresa
continuam como marcadores [ENTRE COLCHETES] até a formatação para emissão (decisão de 14/11).

  python ferramentas/gerar_juridico.py "<caminho>/09_Minutas_Juridicas.md"
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "sistema" / "physis-juridico.js"


def secao(md: str, ini: str, fim: str | None) -> str:
    i = md.index(ini)
    j = md.index(fim, i + len(ini)) if fim else len(md)
    return md[i + len(ini):j]


def limpar(txt: str) -> str:
    txt = re.sub(r"\s*\*\(Nota para a assessoria:[^)]*\)\*", "", txt)
    linhas = [l for l in txt.splitlines() if not re.match(r"^>\s*\*?\*?Nota para a assessoria", l.strip(), re.I)]
    return "\n".join(linhas)


def blocos(txt: str) -> list[dict]:
    """Divide em subtítulos ### e parágrafos/listas/tabelas (markdown simples)."""
    out, atual = [], None
    for l in limpar(txt).splitlines():
        s = l.strip()
        s = re.sub(r"^>\s?", "", s)
        if s.startswith("### "):
            atual = {"t": s[4:].strip(), "p": []}
            out.append(atual)
            continue
        if not s or s == "---":
            continue
        if atual is None:
            atual = {"t": "", "p": []}
            out.append(atual)
        atual["p"].append(s)
    return out


def main() -> None:
    doc = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "OneDrive - Physis Engineering" / "Documents" / "Sistema Physis" / "09_Minutas_Juridicas.md"
    md = doc.read_text(encoding="utf-8")
    versao = (re.search(r"Data:\s*([0-9/]+)", md) or [None, ""])[1]
    dados = {
        "versao": versao, "situacao": "Minuta em revisão jurídica",
        "termos": {"titulo": "Termos de uso", "blocos": blocos(secao(md, "## A. Termos de uso da plataforma e da loja", "## B."))},
        "privacidade": {"titulo": "Política de privacidade (LGPD)", "blocos": blocos(secao(md, "## B. Política de privacidade (LGPD — Lei 13.709/2018)", "## C."))},
        "licenca": {"titulo": "Licença Physis de uso e adaptação", "blocos": blocos(secao(md, "### C.4 Texto da licença (minuta curta)", "## D."))},
        "acessibilidade": {"titulo": "Encontrou alguma barreira? Conte para nós", "blocos": blocos(secao(md, "### D.1 Texto para a plataforma e o site (minuta)", "### D.2"))},
    }
    for k in ("licenca", "acessibilidade"):      # o primeiro parágrafo repete o título
        b = dados[k]["blocos"]
        if b and b[0]["p"] and b[0]["p"][0].startswith("**"):
            b[0]["p"] = b[0]["p"][1:]
    js = ("/* Gerado por ferramentas/gerar_juridico.py a partir de 09_Minutas_Juridicas.md. Não editar à mão.\n"
          "   Textos jurídicos das telas (MINUTA, em revisão jurídica). Marcadores [ENTRE COLCHETES] = dado a definir. */\n"
          "window.PHYSIS_JURIDICO = " + json.dumps(dados, ensure_ascii=False, indent=1) + ";\n")
    SAIDA.write_text(js, encoding="utf-8", newline="\n")
    print(f"gerado: {SAIDA.relative_to(RAIZ)} ({len(js) // 1024} kB, versão {versao})")


if __name__ == "__main__":
    main()
