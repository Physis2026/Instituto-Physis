#!/usr/bin/env python3
"""Gera as demonstrações públicas (demos/*.html) a partir dos programas de verdade. Rode depois de mudar um original.

    python demos/gerar_demos.py             # gera
    python demos/gerar_demos.py --conferir  # só confere (testes): sai com erro se alguma demo estiver velha

Por que existe: as demos são o que o site mostra. Copiadas à mão, ficam velhas (era o caso até 15/11/2026).
Aqui cada demo é o arquivo original com poucos ajustes conferidos (se o original mudar e um ajuste não couber
mais, o script para com erro em vez de gerar uma demo quebrada).

| Demo                          | Original                                   | O que muda                                              |
|-------------------------------|--------------------------------------------|---------------------------------------------------------|
| physis-demo-cliente.html      | physis-hub/web/painel.html                 | modo demonstração ligado; módulos vendáveis; dados simulados |
| physis-demo-gestao.html       | physis-hub/web/painel.html                 | a mesma, abrindo na aba Gestão (mantém o endereço antigo) |
| physis-demo-scada.html        | sistema/physis-scada-demo.html             | ligações entre as demos                                 |
| physis-demo-planejador.html   | modulos/planejador/planejador-physis.html  | aviso de demonstração                                   |
| physis-demo-sustainkit.html   | sistema/SustainKit_Definitivo.html         | abre no Modo Apresentação, com "Dados de exemplo"       |

Todas recebem uma faixa "Demonstração · dados simulados" com as ligações entre as demos.
Animais e saúde (e turbinas, AVAC) não aparecem no site por enquanto: só os módulos vendáveis.
A Gestão interna da Physis (sistema/gestao-interna-physis.html) NÃO vira demo pública: tem dados internos da equipe.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DEMOS = RAIZ / "demos"
PAINEL = RAIZ / "physis-hub" / "web" / "painel.html"
SCADA = RAIZ / "sistema" / "physis-scada-demo.html"
PLANEJADOR = RAIZ / "modulos" / "planejador" / "planejador-physis.html"
SUSTAINKIT = RAIZ / "sistema" / "SustainKit_Definitivo.html"

# Módulos vendáveis no site (pedido de 15/11/2026): planejamento, solar, água, monitoramento (com a Caixinha IoT),
# SustainKit, SCADA, gestão e certificação. SbN, economia circular, carbono e resiliência entram como partes do
# planejamento/SustainKit. Fora: animais, saúde, turbinas, AVAC.
MODULOS_DEMO = ["planejador", "sustainkit", "solar", "agua", "monitoramento", "zonas", "supervisao", "gestao",
                "certificacoes", "sbn", "circular", "carbono", "resiliencia"]
MARCA = '<meta name="physis-demo-gerado" content="demos/gerar_demos.py">'

LIGACOES = [("physis-demo-cliente.html", "Plataforma", "Platform"), ("physis-demo-planejador.html", "Planejador", "Planner"),
            ("physis-demo-sustainkit.html", "SustainKit", "SustainKit"),
            ("physis-demo-scada.html", "SCADA", "SCADA"), ("physis-demo-gestao.html", "Gestão", "Management")]


def faixa(atual: str) -> str:
    """Faixa fixa no topo: diz que é demonstração com dados simulados e liga as demos. Segue o idioma da página (lang)."""
    links = "".join(
        f'<a href="{arq}"{" aria-current=\"page\"" if arq == atual else ""} data-pt="{pt}" data-en="{en}">{pt}</a>'
        for arq, pt, en in LIGACOES)
    return f"""<div id="physis-demo-faixa" role="note" data-pp-manter translate="no">
<strong data-pt="Demonstração · dados simulados" data-en="Demo · simulated data">Demonstração · dados simulados</strong>
<span data-pt="Nenhum equipamento está ligado e nada é guardado no sistema da Physis." data-en="No equipment is connected and nothing is saved in the Physis system.">Nenhum equipamento está ligado e nada é guardado no sistema da Physis.</span>
<nav aria-label="Demonstrações Physis" data-pt-rot="Demonstrações Physis" data-en-rot="Physis demos">{links}</nav>
</div>
<style id="physis-demo-estilo">
#physis-demo-faixa{{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;padding:8px 16px;background:#F6EAD0;color:#5C3F00;border-bottom:1px solid #B9A97F;font:14px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif}}
#physis-demo-faixa nav{{display:flex;flex-wrap:wrap;gap:6px;margin-left:auto}}
#physis-demo-faixa a{{color:#5C3F00;font-weight:600;padding:6px 10px;border-radius:6px;min-height:36px;display:inline-flex;align-items:center}}
#physis-demo-faixa a[aria-current=page]{{background:#5C3F00;color:#FFFFFF;text-decoration:none}}
#physis-demo-faixa a:focus-visible{{outline:3px solid #1C3550;outline-offset:2px}}
html[data-tema=escuro] #physis-demo-faixa{{background:#33372E;color:#E5D5AE;border-color:#4A5A47}}
html[data-tema=escuro] #physis-demo-faixa a{{color:#E5D5AE}}
html[data-tema=escuro] #physis-demo-faixa a[aria-current=page]{{background:#E5D5AE;color:#14180F}}
</style>
<script id="physis-demo-idioma">
(function(){{ var r = document.documentElement, f = document.getElementById("physis-demo-faixa");
  function por(){{ var en = /^en/i.test(r.getAttribute("lang") || ""); f.querySelectorAll("[data-pt]").forEach(function(e){{ e.textContent = e.getAttribute(en ? "data-en" : "data-pt"); }});
    var n = f.querySelector("nav"); n.setAttribute("aria-label", n.getAttribute(en ? "data-en-rot" : "data-pt-rot")); }}
  por(); if (window.MutationObserver) new MutationObserver(por).observe(r, {{ attributes: true, attributeFilter: ["lang"] }}); }})();
</script>
"""


def troca(texto: str, de: str, para: str, nome: str, n: int = 1) -> str:
    achou = texto.count(de)
    if achou != n:
        raise SystemExit(f"{nome}: o ajuste não cabe mais no original (esperava {n}, achou {achou}): {de[:90]!r}")
    return texto.replace(de, para)


def marcar(texto: str, nome: str, atual: str) -> str:
    i, h = texto.find("<head>"), texto.find("</head>")
    if i < 0 or h < 0 or i > h:
        raise SystemExit(f"{nome}: sem <head>…</head>")
    texto = texto[:i + 6] + "\n" + MARCA + texto[i + 6:]
    m = re.compile(r"<body[^>]*>").search(texto, texto.find("</head>"))   # o <body> de verdade, depois do </head>
    if not m:
        raise SystemExit(f"{nome}: sem <body>")
    return texto[:m.end()] + "\n" + faixa(atual) + texto[m.end():]


def plataforma(aba_inicial: str, atual: str) -> str:
    t = PAINEL.read_text(encoding="utf-8")
    nome = atual
    # 1. modo demonstração ligado em qualquer endereço (o original só liga em /demo/)
    t = troca(t, "demo: /^\\/demo\\/?$/.test(location.pathname)", "demo: true", nome)
    # 2. sem service worker (a demo é arquivo solto no site)
    t = troca(t, '!location.pathname.startsWith("/demo")', "false", nome)
    # 3. módulos vendáveis, com dados simulados (campo e Caixinha IoT)
    t = troca(t, 'abrirPlataformaCliente(["monitoramento","agua","zonas"], { campo:6, zonas:1, col:0, com:0 }, false);',
              "abrirPlataformaCliente(" + str(MODULOS_DEMO).replace("'", '"').replace(" ", "") + ", { campo:6, zonas:1, col:0, com:0 }, false);", nome)
    # 4. aba inicial (o endereço #aba continua valendo)
    t = troca(t, 'ui.inst.demo = true; } ui.aba = "resumo"; desenhar(false);',
              'ui.inst.demo = true; } ui.aba = TELAS[location.hash.slice(1)] ? location.hash.slice(1) : "' + aba_inicial + '"; desenhar(false);', nome)
    # 5. o Planejador abre a demo dele (no servidor, abriria /planejador/)
    t = troca(t, '${doServidor ? `src="${rota}"` : ""}',
              '${doServidor ? `src="${rota}"` : id === "planejador" ? `src="physis-demo-planejador.html"` : ""}', nome)
    return marcar(t, nome, atual)


def scada() -> str:
    t = SCADA.read_text(encoding="utf-8")
    nome = "physis-demo-scada.html"
    t = troca(t, 'href="physis-tela-cliente.html"', 'href="physis-demo-cliente.html"', nome)
    t = troca(t, 'href="physis-scada-demo.html"', 'href="physis-demo-scada.html"', nome)
    t = troca(t, 'href="gestao-physis.html"', 'href="physis-demo-gestao.html"', nome)
    return marcar(t, nome, nome)


def planejador() -> str:
    t = PLANEJADOR.read_text(encoding="utf-8")
    return marcar(t, "physis-demo-planejador.html", "physis-demo-planejador.html")


def sustainkit() -> str:
    """O SustainKit da demo abre no Modo Apresentação, com dados de exemplo marcados (o modo só existe na demo)."""
    t = SUSTAINKIT.read_text(encoding="utf-8")
    nome = "physis-demo-sustainkit.html"
    t = troca(t, '<html lang="pt-BR">', '<html lang="pt-BR" data-physis-demo="sustainkit">', nome)
    troca(t, "function iniciarDemo(){", "function iniciarDemo(){", nome)        # confere que o original ainda tem a demo
    return marcar(t, nome, nome)


def gerar() -> dict[str, str]:
    return {
        "physis-demo-sustainkit.html": sustainkit(),
        "physis-demo-cliente.html": plataforma("resumo", "physis-demo-cliente.html"),
        "physis-demo-gestao.html": plataforma("gestao", "physis-demo-gestao.html"),
        "physis-demo-scada.html": scada(),
        "physis-demo-planejador.html": planejador(),
    }


def main() -> int:
    conferir = "--conferir" in sys.argv
    velhas = []
    for nome, novo in gerar().items():
        arq = DEMOS / nome
        antes = arq.read_text(encoding="utf-8") if arq.exists() else None
        if antes != novo:
            velhas.append(nome)
            if not conferir:
                arq.write_bytes(novo.encode("utf-8"))
    for v in velhas:
        print(("velha: " if conferir else "gerada: ") + v)
    if not velhas:
        print("demos iguais aos originais")
    return 1 if (conferir and velhas) else 0


if __name__ == "__main__":
    raise SystemExit(main())
