"""Gera sistema/loja-catalogo-inicial.json: o catálogo com que um site Physis novo abre a loja (pedido de 15/11/2026:
"para as lojas as opções de compra não estão aparecendo").

Tirado dos dados da própria plataforma (web/painel.html): os itens à venda (LOJA_VENDA) que estão "em funcionamento"
no catálogo CAT, mais um item por certificação (sistema/physis-certificacoes.json). Item em desenvolvimento, em
simulação ou buscando parceria NUNCA entra. Preços: os decididos pela direção (PRECOS abaixo); o resto "sob consulta"
(preço vazio). Os níveis das certificações (N1 a N4) e os seus preços ficam na tabela niveis_loja da base de
certificações: o cartão da loja mostra os quatro.

O servidor publica este arquivo sozinho quando o catálogo publicado está vazio (Hub.loja_semear_inicial), registrado
como "catálogo inicial da instalação"; a equipe continua editando, revisando e publicando de novo.

    python ferramentas/gerar_loja_catalogo.py            # grava
    python ferramentas/gerar_loja_catalogo.py --conferir # só confere (código 1 se o arquivo estiver diferente)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PAINEL = RAIZ / "physis-hub" / "web" / "painel.html"
CERT = RAIZ / "sistema" / "physis-certificacoes.json"
SAIDA = RAIZ / "sistema" / "loja-catalogo-inicial.json"
# preços decididos pela direção (15/11/2026); o que não está aqui fica "sob consulta"
PRECOS = {"solar": 300, "consultoria-pers": 5000}
PRECO_CERT_N1 = 750


def _campo(txt: str, k: str):
    m = re.search(r'\b' + k + r':"((?:[^"\\]|\\.)*)"', txt)
    return m.group(1).replace('\\"', '"') if m else None


def item_do_cat(html: str, ident: str) -> dict | None:
    """O literal do item no CAT: { id:"x", ... } ou Object.assign(P("x","nome","sub"), { ... })."""
    m = re.search(r'\{ id:"' + re.escape(ident) + r'",(.*?)\}(?:,|\s*\n)', html)
    if m:
        t = m.group(1)
        return {"nome": _campo(t, "nome"), "cod": _campo(t, "cod"), "sub": _campo(t, "sub"), "st": _campo(t, "st"), "link": _campo(t, "link")}
    m = re.search(r'Object\.assign\(P\("' + re.escape(ident) + r'","((?:[^"\\]|\\.)*)","((?:[^"\\]|\\.)*)"\), \{(.*?)\}\)', html)
    if m:
        t = m.group(3)
        return {"nome": m.group(1), "cod": _campo(t, "cod") or ident, "sub": m.group(2), "st": _campo(t, "st") or "dev", "link": _campo(t, "link")}
    return None


def gerar() -> dict:
    html = PAINEL.read_text(encoding="utf-8")
    venda = re.findall(r'"([^"]+)"', re.search(r"const LOJA_VENDA = new Set\(\[([^\]]*)\]", html).group(1))
    cat_de = dict(re.findall(r'"?([\w-]+)"?:"(\w+)"', re.search(r"const CAT_DE = \{(.*?)\};", html).group(1)))
    itens, fora = {}, {}
    for ident in venda:
        c = item_do_cat(html, ident)
        if not c:
            fora[ident] = "não está no catálogo CAT"
            continue
        if c["st"] != "func":                       # em desenvolvimento, simulação ou parceria: nunca no catálogo inicial
            fora[ident] = "situação " + str(c["st"])
            continue
        it = {"st": "func", "preco": PRECOS.get(ident), "categ": cat_de.get(ident, ""), "nome": c["nome"] or ident, "cod": (c["cod"] or "")[:20].strip(), "sub": (c["sub"] or "")[:400]}
        if c.get("link", "") and str(c["link"]).startswith("https://"):
            it["link"] = c["link"]
        itens[ident] = it
    base = json.loads(CERT.read_text(encoding="utf-8"))
    niveis = base.get("niveis_loja", {}).get("niveis", [])
    for c in base["certificacoes"]:
        itens["cert-" + c["id"]] = {"st": "func", "preco": PRECO_CERT_N1, "categ": "cert", "nome": c["nome"][:120], "cod": "Certificação",
                                    "sub": ("Módulo de certificação para " + c["nome"] + ", em quatro níveis (escolha abaixo).")[:400]}
    return {"_formato": "physis-loja-catalogo/1",
            "_leia": "Catálogo inicial da loja de um site Physis novo. Gerado por ferramentas/gerar_loja_catalogo.py a partir de "
                     "web/painel.html (LOJA_VENDA e CAT) e de sistema/physis-certificacoes.json. Só itens em funcionamento; preço "
                     "vazio = sob consulta. O servidor publica sozinho quando o catálogo publicado está vazio.",
            "precos_niveis_certificacao": [{"n": n["n"], "nome": n["nome"], "preco": n["preco"], "a_partir_de": n.get("apartir", False)} for n in niveis],
            "itens": itens, "fora": fora}


def main(argv: list[str]) -> int:
    d = gerar()
    texto = json.dumps(d, ensure_ascii=False, indent=2) + "\n"
    if "--conferir" in argv:
        igual = SAIDA.is_file() and SAIDA.read_text(encoding="utf-8") == texto
        print("igual" if igual else "diferente: rode python ferramentas/gerar_loja_catalogo.py")
        return 0 if igual else 1
    SAIDA.write_text(texto, encoding="utf-8", newline="\n")
    print(f"gravado: {SAIDA} ({len(d['itens'])} itens; fora: {', '.join(sorted(d['fora'])) or 'nenhum'})")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main(sys.argv[1:]))
