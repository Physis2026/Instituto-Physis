"""Monta physis-hub/web/inovastem-lab.html: o Laboratório online da InovaSTEM (/laboratorio), com a Simulação (Fase 1)
e o Physis 3D rodando no navegador, sem conta e sem internet (D94; pedido da direção de 20/11/2026: "deve ser funcional
online antes de ser liberado ao público").

A página é um arquivo único, como as outras telas do sistema. Ela leva CÓPIAS IGUAIS de:
  sistema/physis-turbinas.js, sistema/simulacao-exemplos/casos.js, sistema/physis-simulacao.js, sistema/physis-3d.js,
  sistema/physis-3d-premissas.json e sistema/physis-preferencias.js
e o cabeçalho, os logos e os estilos de physis-hub/web/inovastem.html (Guia de Identidade de 19/11/2026).
Os motores não mudam (regra 2): só a APARÊNCIA do que eles desenham é trocada para as cores do guia na hora de mostrar
(sem azul; roxo só na Delas). Teste: physis-hub/tests/test_inovastem.py (cópias iguais aos originais).

Uso (depois de mudar qualquer um dos arquivos acima):
    python ferramentas/montar_lab_inovastem.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SIS = RAIZ / "sistema"
WEB = RAIZ / "physis-hub" / "web"
SAIDA = WEB / "inovastem-lab.html"

# blocos copiados sem mudar nada: (id do <script>, arquivo)
BLOCOS = [("lab-turbinas", SIS / "physis-turbinas.js"), ("lab-casos", SIS / "simulacao-exemplos" / "casos.js"),
          ("lab-simulacao", SIS / "physis-simulacao.js"), ("lab-3d", SIS / "physis-3d.js")]

# troca de cor só na tela (aparência): azuis → sequência creme→verde profundo do guia; vermelho e ocre → laranjas do guia
CORES = {"#DBE7F1": "#F4F1EA", "#B8D0E0": "#D9D3C2", "#7FA9C4": "#8A9284", "#546A7B": "#4A5A47", "#3D6E8F": "#4A5A47",
         "#2C5A6E": "#0B3D2E", "#1C3550": "#1B1F23", "#7A2214": "#C2410C", "#A63A28": "#C2410C", "#A85432": "#C2410C",
         "#C9A227": "#F97316", "#C08A1E": "#C2410C"}


def ler(p: Path) -> str:
    return p.read_text(encoding="utf-8").replace("\r\n", "\n")


def montar() -> str:
    site = ler(WEB / "inovastem.html")
    estilo = re.search(r"<style>\n(.*?)</style>", site, re.S).group(1)
    logo = re.search(r'(<h1 class="logo">.*?</h1>)', site, re.S).group(1)
    pref = ler(SIS / "physis-preferencias.js")
    prem3d = json.dumps(json.loads(ler(SIS / "physis-3d-premissas.json")), ensure_ascii=False)
    blocos = "\n".join(f'<script id="{i}">\n{ler(a)}</script>' for i, a in BLOCOS)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>InovaSTEM · Laboratório</title>
<meta name="description" content="Laboratório online da InovaSTEM: simulações leves (calor, estrutura, ventilação, terreno, incerteza, biogás e trilha QUBO) e Physis 3D, no navegador. Versão beta.">
<!-- GERADO por ferramentas/montar_lab_inovastem.py. Não edite aqui: edite os originais e rode o gerador. -->
<script>(function(){{var r=document.documentElement,t=null,p=null;try{{p=JSON.parse(localStorage.getItem("physis-pref")||"null");t=p&&p.tema||localStorage.getItem("physis-pref-tema");}}catch(e){{}}if(t!=="claro"&&t!=="escuro"){{try{{t=matchMedia("(prefers-color-scheme: dark)").matches?"escuro":"claro";}}catch(e){{t="claro";}}}}r.setAttribute("data-tema",t);}})();</script>
<style>
{estilo}/* Laboratório: classes que os motores usam (cartao, faixa in/al/at, t2), nas cores do guia */
.faixa.in{{background:var(--suave);color:var(--texto)}}
.faixa.al{{background:var(--al-f);color:var(--al-t)}}
.faixa.at{{background:var(--at-f);color:var(--at-t)}}
#lab button:not(.botao),#lab input[type=file]{{font:700 1rem/1.2 var(--fonte);min-height:44px;padding:6px 14px;border-radius:8px;border:2px solid var(--sec);background:transparent;color:var(--sec);cursor:pointer}}
#lab figure{{margin:10px 0;max-width:100%;overflow-x:auto}}
#lab svg{{max-width:100%;height:auto}}
#lab canvas{{max-width:100%}}
#lab textarea{{font-family:ui-monospace,Consolas,monospace;font-size:.9rem}}
.lab-abas{{list-style:none;display:flex;flex-wrap:wrap;gap:8px;padding:0;margin:16px 0}}
</style>
<script type="application/json" id="base-3d-premissas">{prem3d}</script>
</head>
<body>
<a class="pular" href="#conteudo">Pular para o conteúdo</a>
<div class="endosso"><div class="in"><span>uma iniciativa</span> <span class="marca-physis">Physis</span></div></div>
<header>
  <div class="in">
    <div class="ferramentas" id="pp-lugar" data-physis-preferencias="lugar"></div>
    <div class="cabeca">
      {logo.replace('href="#inicio"', 'href="/"')}
      <nav class="abas" aria-label="Seções do site"><ul>
        <li><a href="/#delas" class="delas">InovaSTEM Delas</a></li><li><a href="/#desafios">Desafios e projetos</a></li>
        <li><a href="/#forum">Fórum</a></li><li><a href="/#modelagem" aria-current="page">Modelagem online</a></li>
        <li><a href="/#hackathon">Hackathon</a></li><li><a href="/#materiais">Materiais</a></li></ul></nav>
      <a class="botao" href="/#participar">Inscreva-se</a>
    </div>
    <p class="sub">Laboratório online · roda no seu navegador, sem conta <span class="beta">versão beta</span></p>
  </div>
</header>
<main id="conteudo" class="in" tabindex="-1">
  <ul class="lab-abas" aria-label="Ferramentas do laboratório">
    <li><a class="botao" id="lab-a-sim" href="#simulacao">Simulação</a></li>
    <li><a class="botao sec" id="lab-a-3d" href="#3d">Physis 3D</a></li>
    <li><a class="botao sec" href="/planejador">GIS e BIM (Planejador)</a></li>
  </ul>
  <p class="faixa" role="note">Em desenvolvimento (Fase 1). Pré-dimensionamento para aprender e testar ideias: não aprova projeto, não substitui norma nem ensaio. Os exemplos usam dados fictícios. Nada do que você abre aqui sai do seu computador.</p>
  <div id="lab"></div>
</main>
<footer><div class="in"><p><strong>InovaSTEM · uma iniciativa PHYSIS</strong> · Physis Engineering · CNPJ [MARCADOR] · Petrópolis (RJ) · Contato: [MARCADOR]</p>
  <p>Versão beta: termos e aviso de privacidade em revisão jurídica.</p>
  <ul><li><a href="/#termos">Termos de uso (beta)</a></li><li><a href="/#privacidade">Privacidade (beta)</a></li><li><a href="/acessibilidade">Acessibilidade</a></li></ul></div></footer>
<script>const ui = {{}};</script>
{blocos}
<script id="lab-inovastem">
"use strict";
/* Casca do Laboratório: escolhe a ferramenta, desenha e troca as cores da tela para as do guia (aparência apenas). */
const CORES = {json.dumps(CORES)};
let abaLab = "simulacao";
function recolorir(h) {{ return h.replace(/#[0-9A-Fa-f]{{6}}\\b/g, c => CORES[c.toUpperCase()] || c); }}
function desenhar() {{
  const alvo = document.getElementById("lab");
  let h = abaLab === "3d" ? telaPhysis3D() : telaSimulacao();
  h = h.replace(/<h1(\\s[^>]*)?>/g, "<h2$1>").replace(/<\\/h1>/g, "</h2>");      // um título só por tela: o logo
  alvo.innerHTML = recolorir(h);
  document.getElementById("lab-a-sim").className = "botao" + (abaLab === "simulacao" ? "" : " sec");
  document.getElementById("lab-a-3d").className = "botao" + (abaLab === "3d" ? "" : " sec");
  document.getElementById("lab-a-sim").setAttribute("aria-current", abaLab === "simulacao" ? "page" : "false");
  document.getElementById("lab-a-3d").setAttribute("aria-current", abaLab === "3d" ? "page" : "false");
}}
window.__p3dDesenhar = desenhar;
function irLab() {{ abaLab = location.hash === "#3d" ? "3d" : "simulacao"; desenhar(); }}
window.addEventListener("hashchange", irLab);
irLab();
</script>
<script id="physis-preferencias">
{pref}</script>
<script id="pp-site">
PxPref.iniciar({{ lugar:"#pp-lugar", conteudo:"#conteudo", tela:"lab-inovastem", aoMudar: () => desenhar() }});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    SAIDA.write_text(montar(), encoding="utf-8", newline="\n")
    print(f"{SAIDA.relative_to(RAIZ)}: {SAIDA.stat().st_size // 1024} kB")
