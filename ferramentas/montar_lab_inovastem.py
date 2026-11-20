"""Monta physis-hub/web/inovastem-lab.html: a Modelagem 3D (Physis 3D) da InovaSTEM, servida em /laboratorio, rodando no
navegador, sem internet (D94; estrutura aprovada pela dona em 20/11/2026, com os acréscimos do mesmo dia).

A Modelagem 3D é a bancada de desenvolvimento da InovaSTEM, aberta a qualquer assunto. O Planejador é outra ferramenta
(relacionada, mas separada; dona, 20/11/2026) e não aparece no site da InovaSTEM.
Oito subabas, nesta ordem (hash da página), que leem e gravam um PROJETO COMUM (JSON "inovastem-projeto/1" no navegador,
com Exportar/Importar arquivo; seções lugar, edificacao, pecas, resultados, arquivos e passos). Fluxo visível no topo:
Enviar arquivo → Lugar/Edificação (se for território ou edificação) → Peças 3D → Simulação → Fila de impressão → Galeria.
  #arquivo      Enviar arquivo: qualquer arquivo; imagem e SVG viram CAD 2D (SVG, DXF) e 3D (STL, 3MF) ajustáveis,
                por sistema/physis-imagem-3d.js; malhas vão direto para Peças 3D; PDF: pede a imagem da página
  #lugar        Lugar (GIS): importa o lugar no contrato physis-geometria-lugar/1 (Mapeamento)
  #edificacao   Edificação (BIM): leva o resumo do IFC (leitor ifc.py do servidor, ou o JSON do resumo)
  #pecas        Peças 3D: a tela telaPhysis3D() do motor sistema/physis-3d.js (sem mudar função nem conta)
  #simulacao    Simulação: um bloco por fenômeno, rodando os exemplos pelo motor window.SIMULACAO (rodarCaso, desenhoCaso)
  #escaneamento Escaneamento: modelos do CrealityScan em STL ou OBJ, abertos em Peças 3D (sem limpeza de malha)
  #fila         Fila de impressão: rotas /api/inovastem/impressao* (physis_hub/inovastem.py), com conta
  #galeria      Galeria: peças publicadas (/api/publico/3d/pecas), só licenças abertas
(#3d, o endereço antigo, abre Peças 3D.)

A página é um arquivo único, como as outras telas do sistema. Ela leva CÓPIAS IGUAIS de:
  sistema/physis-turbinas.js, sistema/simulacao-exemplos/casos.js, sistema/physis-simulacao.js, sistema/physis-3d.js,
  sistema/physis-imagem-3d.js (imagem → CAD 2D e 3D; peças de teste de impressão), sistema/physis-3d-premissas.json e
  sistema/physis-preferencias.js
e o cabeçalho, os logos e os estilos de physis-hub/web/inovastem.html (Guia de Identidade de 19/11/2026).
Os motores não mudam (regra 2): só a APARÊNCIA do que eles desenham é trocada para as cores do guia na hora de mostrar
(sem azul; roxo só na Delas). A casca (subabas, projeto comum, blocos da simulação, fila e galeria) fica AQUI, em CASCA_CSS
e CASCA_JS. Teste: physis-hub/tests/test_inovastem.py (cópias iguais aos originais, 7 subabas, gerador em dia).

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
          ("lab-simulacao", SIS / "physis-simulacao.js"), ("lab-3d", SIS / "physis-3d.js"),
          ("lab-imagem3d", SIS / "physis-imagem-3d.js")]

# troca de cor só na tela (aparência): azuis → sequência creme→verde profundo do guia; vermelho e ocre → laranjas do guia
CORES = {"#DBE7F1": "#F4F1EA", "#B8D0E0": "#D9D3C2", "#7FA9C4": "#8A9284", "#546A7B": "#4A5A47", "#3D6E8F": "#4A5A47",
         "#2C5A6E": "#0B3D2E", "#1C3550": "#1B1F23", "#7A2214": "#C2410C", "#A63A28": "#C2410C", "#A85432": "#C2410C",
         "#C9A227": "#F97316", "#C08A1E": "#C2410C"}

# as subabas aprovadas (20/11/2026; "Enviar arquivo" acrescentada no mesmo dia como a primeira do fluxo): (hash, nome)
SUBABAS = [("arquivo", "Enviar arquivo"), ("lugar", "Lugar (GIS)"), ("edificacao", "Edificação (BIM)"), ("pecas", "Peças 3D"), ("simulacao", "Simulação"),
           ("escaneamento", "Escaneamento"), ("fila", "Fila de impressão"), ("galeria", "Galeria")]
ESQUEMA_PROJETO = "inovastem-projeto/1"

CASCA_CSS = """/* Modelagem 3D (casca do laboratório): classes que os motores usam (cartao, faixa in/al/at, t2), nas cores do guia */
.faixa.in{background:var(--suave);color:var(--texto)}
.faixa.al{background:var(--al-f);color:var(--al-t)}
.faixa.at{background:var(--at-f);color:var(--at-t)}
#lab button:not(.botao),#lab input[type=file],.lab-projeto input[type=file]{font:700 1rem/1.2 var(--fonte);min-height:44px;padding:6px 14px;border-radius:8px;border:2px solid var(--sec);background:transparent;color:var(--sec);cursor:pointer;max-width:100%}
#lab figure{margin:10px 0;max-width:100%;overflow-x:auto}
#lab svg{max-width:100%;height:auto}
#lab canvas{max-width:100%}
#lab textarea{font-family:ui-monospace,Consolas,monospace;font-size:.9rem}
#lab pre{white-space:pre-wrap;overflow-wrap:anywhere}
#lab code,.lab-projeto code{overflow-wrap:anywhere}
.lab-intro{margin:16px 0 0}
.lab-abas{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0;padding:0}
.lab-abas [role=tab]{display:inline-flex;align-items:center;min-height:44px;padding:6px 14px;border-radius:8px;border:2px solid var(--sec);color:var(--sec);background:transparent;text-decoration:none;font:700 1rem/1.2 var(--fonte)}
.lab-abas [role=tab][aria-selected=true]{background:var(--acao);border-color:var(--acao);color:var(--sobre-acao)}
.lab-projeto{border:1px solid var(--linha);border-left:6px solid var(--semente);border-radius:12px;background:var(--sup);padding:10px 14px;margin:12px 0}
.lab-projeto p{margin:0}
.lab-projeto ul{list-style:none;padding:0;margin:8px 0 0;display:grid;gap:4px 16px;grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}
.lab-projeto label{margin-top:0}
.lab-arq{display:flex;flex-direction:column;gap:4px;max-width:100%}
#lab:focus-visible{outline:3px solid var(--link);outline-offset:4px}
#lab .cartao{margin:14px 0}
#lab .cartao h3{font:700 1.15rem/1.3 var(--fonte)}
dl.lab-ficha{display:grid;grid-template-columns:minmax(0,11em) minmax(0,1fr);gap:6px 14px;margin:8px 0}
dl.lab-ficha dt{font-weight:700}
dl.lab-ficha dd{margin:0}
@media (max-width:560px){dl.lab-ficha{grid-template-columns:minmax(0,1fr)}dl.lab-ficha dd{margin-bottom:6px}}
.lab-indice{list-style:none;display:flex;flex-wrap:wrap;gap:6px;padding:0;margin:10px 0}
.lab-res{margin-top:10px}
.lab-fluxo{list-style:none;padding:0;margin:10px 0 0;display:grid;gap:4px 14px;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));border-top:1px solid var(--linha);padding-top:8px}
.lab-fluxo li{display:flex;flex-wrap:wrap;align-items:center;gap:2px 6px}
.lab-fluxo a{display:inline-flex;align-items:center;min-height:44px;font-weight:700}
.lab-fluxo a[aria-current=step]{text-decoration-thickness:3px;text-decoration-color:var(--semente)}
.lab-fluxo .lab-feito{flex-basis:100%;margin-top:-8px}
#lab h4{font:700 1.02rem/1.3 var(--fonte);margin:0 0 4px}
#lab input[type=file]{width:100%}
#lab summary{padding:9px 0;cursor:pointer}
#lab .rolagem table{overflow-wrap:normal}
#lab .rolagem td .botao{white-space:nowrap}
.lab-fen{scroll-margin-top:12px}
"""

CASCA_JS = r""""use strict";
/* Casca da Modelagem 3D (Physis 3D): 8 subabas em fluxo, projeto comum (inovastem-projeto/1), enviar arquivo, blocos da
   simulação por fenômeno, fila de impressão e galeria. Gerada por ferramentas/montar_lab_inovastem.py. Os motores (SIMULACAO, telaPhysis3D) não
   mudam: a casca só chama as funções deles e troca as cores do desenho para as do guia (aparência apenas). */
const CORES = __CORES__;
const SUBABAS = __SUBABAS__;
const ANTIGAS = { "3d": "pecas" };                          // endereço antigo do Physis 3D
const ESQ_PROJETO = "__ESQ_PROJETO__", ESQ_LUGAR = "physis-geometria-lugar/1", CHAVE_PROJ = "inovastem-projeto";
const ARQ_MAX = 20 * 1024 * 1024;                           // o mesmo limite dos arquivos do Mapeamento (20 MB)
const ESTADOS = { pendente:"Pendente", aprovada:"Aprovada", imprimindo:"Imprimindo", pronta:"Pronta", recusada:"Recusada" };
const PASSO_ROTULO = { aprovada:"Aprovar", recusada:"Recusar", imprimindo:"Começar a imprimir", pronta:"Marcar como pronta" };
let abaLab = "arquivo", desenhado = false, proj = null, inst = null;
const lab = { proj: null, limpar: false, lugar: null, ed: null, peca: null, sim: {}, fila: null, filaMsg: null, gal: null, arq: null, arqMsg: null, testes: null };

const escL = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));
const nf = (v, c) => (typeof v === "number" && isFinite(v)) ? v.toLocaleString("pt-BR", { minimumFractionDigits: c, maximumFractionDigits: c }) : "—";
const quando = iso => { try { const d = new Date(typeof iso === "number" ? iso * 1000 : iso); return isNaN(d) ? String(iso || "") : d.toLocaleString("pt-BR"); } catch (e) { return String(iso || ""); } };
const agora = () => new Date().toISOString();
const msgHtml = (id, m) => `<p class="msg${m && m.erro ? " erro" : ""}" role="status" id="${id}">${escL(m ? m.texto : "")}</p>`;
const tabela = (cap, linhas) => `<div class="rolagem"><table><caption>${escL(cap)}</caption><tbody>${linhas.map(l => `<tr><th scope="row">${escL(l[0])}</th><td>${l[1]}</td></tr>`).join("")}</tbody></table></div>`;
function recolorir(h) { return h.replace(/#[0-9A-Fa-f]{6}\b/g, c => CORES[c.toUpperCase()] || c); }

/* ════════ projeto comum (inovastem-projeto/1): no navegador, com try/catch, e em arquivo ════════ */
function projetoVazio() { const t = agora(); return { esquema: ESQ_PROJETO, criado: t, atualizado: t, lugar: null, edificacao: null, pecas: [], resultados: [], arquivos: [], passos: [] }; }
function lugarValido(g) {
  if (!g || typeof g !== "object" || g.esquema !== ESQ_LUGAR) return false;
  const t = g.terreno;
  if (t != null && (typeof t !== "object" || !Number.isInteger(t.nx) || !Number.isInteger(t.ny) || t.nx < 1 || t.ny < 1
      || !(typeof t.cs === "number" && t.cs > 0) || !Array.isArray(t.Z) || t.Z.length !== t.nx * t.ny)) return false;
  return ["edificacoes", "superficies", "elementos_bim"].every(k => g[k] == null || Array.isArray(g[k]));
}
function resumoIfcValido(r) { return !!(r && typeof r === "object" && typeof r.esquema === "string" && r.elementos_por_tipo && typeof r.elementos_por_tipo === "object"); }
function projetoValido(o) {
  if (!o || typeof o !== "object" || o.esquema !== ESQ_PROJETO) return null;
  const p = projetoVazio();
  if (typeof o.criado === "string") p.criado = o.criado.slice(0, 40);
  if (typeof o.atualizado === "string") p.atualizado = o.atualizado.slice(0, 40);
  if (o.lugar && typeof o.lugar === "object" && lugarValido(o.lugar.dados)) p.lugar = o.lugar;
  if (o.edificacao && typeof o.edificacao === "object" && resumoIfcValido(o.edificacao.resumo)) p.edificacao = o.edificacao;
  p.pecas = Array.isArray(o.pecas) ? o.pecas.filter(x => x && typeof x === "object").slice(0, 200) : [];
  p.resultados = Array.isArray(o.resultados) ? o.resultados.filter(x => x && typeof x === "object").slice(0, 200) : [];
  p.arquivos = Array.isArray(o.arquivos) ? o.arquivos.filter(x => x && typeof x === "object").slice(-200) : [];
  p.passos = Array.isArray(o.passos) ? o.passos.filter(x => x && typeof x === "object" && typeof x.passo === "string").slice(-200) : [];
  return p;
}
function lerProjeto() { try { return projetoValido(JSON.parse(localStorage.getItem(CHAVE_PROJ) || "null")) || projetoVazio(); } catch (e) { return projetoVazio(); } }
function gravarProjeto(texto, naBarra) {          // a mensagem vai para a barra só nas ações do projeto (ou se falhar)
  proj.atualizado = agora();
  let ok = false;
  try { localStorage.setItem(CHAVE_PROJ, JSON.stringify(proj)); ok = true; } catch (e) {}
  lab.proj = ok ? (naBarra ? { texto } : null) : { texto: texto + " Atenção: não deu para guardar neste navegador (espaço cheio ou navegação privada). Exporte o arquivo do projeto para não perder.", erro: true };
  return ok;
}
function baixar(nome, texto, tipo) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([texto], { type: tipo }));
  a.download = nome; document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}
async function lerArquivoJson(f) {
  if (!f) throw new Error("Escolha um arquivo.");
  if (f.size > ARQ_MAX) throw new Error("Arquivo grande demais (máximo 20 MB).");
  try { return JSON.parse(await f.text()); } catch (e) { throw new Error("O arquivo não é um JSON válido."); }
}
const deOnde = x => x ? `de: ${escL(x.origem)}${x.arquivo ? " (" + escL(x.arquivo) + ")" : ""}, ${escL(quando(x.importado_em))}` : "";
function resumoLugarCurto(g) {
  const t = g.terreno;
  const n = (a, um, varios) => { const k = (a || []).length; return k + " " + (k === 1 ? um : varios); };
  return (t ? `terreno ${t.nx} × ${t.ny}` : "sem terreno") + ` · ${n(g.edificacoes, "edificação", "edificações")} · ${n(g.superficies, "superfície", "superfícies")}`;
}
function barraProjeto() {
  const L = proj.lugar, Ed = proj.edificacao, vazio = '<span class="t2">vazio</span>', fen = {};
  proj.resultados.forEach(r => { const k = r.fenomeno_nome || r.fenomeno || "?"; fen[k] = (fen[k] || 0) + 1; });
  return `<p><strong>Projeto comum</strong> <span class="t2 pq">(<code>${ESQ_PROJETO}</code>, guardado neste navegador · atualizado em ${escL(quando(proj.atualizado))})</span></p>
    <ul><li><strong>Arquivos:</strong> ${proj.arquivos.length ? proj.arquivos.length + " · último: " + escL(proj.arquivos[proj.arquivos.length - 1].nome) : vazio}</li>
      <li><strong>Lugar:</strong> ${L ? escL(resumoLugarCurto(L.dados)) + " · " + deOnde(L) : vazio}</li>
      <li><strong>Edificação:</strong> ${Ed ? escL((Ed.resumo.elementos != null ? Ed.resumo.elementos + " elementos" : "resumo IFC") + " · " + (Ed.resumo.esquema || "")) + " · " + deOnde(Ed) : vazio}</li>
      <li><strong>Peças:</strong> ${proj.pecas.length ? proj.pecas.length + " · de: Peças 3D (Physis 3D)" : vazio}</li>
      <li><strong>Resultados:</strong> ${proj.resultados.length ? proj.resultados.length + " · de: Simulação (" + Object.keys(fen).map(k => escL(k) + " " + fen[k]).join(", ") + ")" : vazio}</li></ul>
    <div class="acoes"><button class="botao sec" type="button" id="proj-exportar" data-lab="proj-exportar">Exportar o projeto (.json)</button>
      <span class="lab-arq"><label for="proj-importar">Importar um projeto (.json)</label><input id="proj-importar" type="file" accept=".json,application/json" data-lab-arq="projeto"></span>
      <button class="botao sec" type="button" id="proj-limpar" data-lab="proj-limpar">${lab.limpar ? "Confirmar: apagar o projeto deste navegador" : "Começar outro projeto"}</button></div>
    ${msgHtml("proj-msg", lab.proj)}${fluxoHtml()}`;
}

/* ════════ servidor da InovaSTEM (mesma origem; nada de fora) ════════ */
async function getJ(url) {
  try { const r = await fetch(url, { credentials: "same-origin", cache: "no-store" }); let j = {}; try { j = await r.json(); } catch (e) {}
    if (j.ok == null) j.ok = r.ok; j._status = r.status; return j; } catch (e) { return { ok: false, erro: "Sem ligação com o servidor da InovaSTEM." }; }
}
async function instancia(renovar) { if (!inst || renovar) { const j = await getJ("/api/instancia"); inst = j && j.org !== undefined ? j : null; } return inst; }
async function postJ(url, corpo) {
  const i = await instancia(), op = { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) };
  if (i && i.csrf) op.headers["X-Physis-CSRF"] = i.csrf;
  try { const r = await fetch(url, op); let j = {}; try { j = await r.json(); } catch (e) {} if (j.ok == null) j.ok = r.ok; return j; }
  catch (e) { return { ok: false, erro: "Sem ligação com o servidor da InovaSTEM." }; }
}
const ehEquipe = i => !!(i && (i.papel === "operador" || i.papel === "administrador"));

/* ════════ fluxo e passos do projeto ════════ */
const FLUXO = [["arquivo", "Enviar arquivo", ["arquivo"], ""], ["lugar", "Lugar ou Edificação", ["lugar", "edificacao"], "se for território ou edificação"],
  ["pecas", "Peças 3D", ["pecas"], ""], ["simulacao", "Simulação", ["simulacao"], ""], ["fila", "Fila de impressão", ["fila"], ""], ["galeria", "Galeria", ["galeria"], ""]];
function registrarPasso(passo, detalhe) { proj.passos.push({ passo, detalhe: String(detalhe || "").slice(0, 200), quando: agora() }); if (proj.passos.length > 200) proj.passos.splice(0, proj.passos.length - 200); }
function ultimoPasso(nomes) { for (let i = proj.passos.length - 1; i >= 0; i--) if (nomes.indexOf(proj.passos[i].passo) >= 0) return proj.passos[i]; return null; }
function fluxoHtml() {
  return `<nav aria-label="Fluxo da Modelagem 3D"><ol class="lab-fluxo">${FLUXO.map(([k, nome, nomes, quandoUsar], i) => {
    const u = ultimoPasso(nomes), atual = nomes.indexOf(abaLab) >= 0;
    const links = k === "lugar" ? `<a href="#lugar"${abaLab === "lugar" ? ' aria-current="step"' : ""}>Lugar</a> ou <a href="#edificacao"${abaLab === "edificacao" ? ' aria-current="step"' : ""}>Edificação</a>`
      : `<a href="#${k}"${atual ? ' aria-current="step"' : ""}>${escL(nome)}</a>`;
    return `<li${atual ? ' class="atual"' : ""}><span class="lab-n">${i + 1}.</span> ${links}${quandoUsar ? ` <span class="t2 pq">(${escL(quandoUsar)})</span>` : ""}
      <span class="t2 pq lab-feito">${u ? "✓ " + escL(quando(u.quando)) + (u.detalhe ? ": " + escL(u.detalhe) : "") : "ainda não"}</span></li>`; }).join("")}</ol></nav>`;
}

/* ════════ 0. Enviar arquivo (sistema/physis-imagem-3d.js + motor PHYSIS3D, sem mudar) ════════ */
const RX_IMG = /\.(png|jpe?g|webp)$/i, RX_MALHA = /\.(stl|obj|3mf)$/i, RX_SVG = /\.svg$/i, RX_PDF = /\.pdf$/i;
const PAR_PADRAO = { limiar: 128, inverter: false, res: 100, largura: 60, altura: 3, base: 1 };     // pontos de partida da tela, ajustáveis
const SVG_FORMAS = ["path", "rect", "circle", "ellipse", "polygon", "polyline", "line"];
const SVG_ATRIBUTOS = ["d", "x", "y", "width", "height", "rx", "ry", "cx", "cy", "r", "points", "x1", "y1", "x2", "y2", "transform", "stroke-width", "fill-rule"];
const numL = (v, d) => { const x = Number(String(v == null ? "" : v).trim().replace(",", ".")); return isFinite(x) ? x : d; };
function tipoDe(f) {
  const n = f.name || "", t = f.type || "";
  return RX_MALHA.test(n) ? "malha" : (RX_SVG.test(n) || t === "image/svg+xml") ? "svg" : (RX_PDF.test(n) || t === "application/pdf") ? "pdf"
    : (RX_IMG.test(n) || /^image\/(png|jpeg|webp)$/.test(t)) ? "imagem" : "outro";
}
/* SVG: só as formas geométricas e os atributos de geometria (nada de script, link, estilo ou evento), refeitas aqui */
function svgLimpo(texto) {
  const doc = new DOMParser().parseFromString(texto, "image/svg+xml"), raiz = doc.documentElement;
  if (!raiz || raiz.nodeName.toLowerCase() !== "svg" || doc.getElementsByTagName("parsererror").length) throw new Error("O SVG não pôde ser lido.");
  let vb = (raiz.getAttribute("viewBox") || "").trim().split(/[\s,]+/).map(Number);
  if (vb.length !== 4 || vb.some(v => !isFinite(v)) || !(vb[2] > 0 && vb[3] > 0)) vb = [0, 0, numL(raiz.getAttribute("width"), 0), numL(raiz.getAttribute("height"), 0)];
  if (!(vb[2] > 0 && vb[3] > 0)) throw new Error("O SVG não tem viewBox nem largura e altura em números.");
  const partes = [];
  SVG_FORMAS.forEach(tag => Array.from(raiz.getElementsByTagName(tag)).forEach(el => {
    const at = SVG_ATRIBUTOS.filter(a => el.hasAttribute(a)).map(a => `${a}="${escL(el.getAttribute(a))}"`).join(" ");
    partes.push(`<${tag} ${at}/>`);
  }));
  if (!partes.length) throw new Error("O SVG não tem formas (caminhos, retângulos, círculos, polígonos ou linhas).");
  return { vb, formas: partes.join(""), n: partes.length };
}
const svgDe = (s, w, h, cor) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${s.vb.join(" ")}" width="${w}" height="${h}"><g fill="${cor}" stroke="${cor}">${s.formas}</g></svg>`;
/* caminhos do SVG direto para o CAD 2D: amostrados pelo próprio navegador (getPointAtLength), em mm, y para cima */
function lacosDoSvg(s, largura) {
  const caixa = document.createElement("div");
  caixa.setAttribute("aria-hidden", "true");
  caixa.style.cssText = "position:fixed;left:-20000px;top:0;visibility:hidden;pointer-events:none";
  caixa.innerHTML = svgDe(s, s.vb[2], s.vb[3], "none");
  document.body.appendChild(caixa);
  const lacos = [], esc_ = largura / s.vb[2], alt = s.vb[3];
  try {
    const raiz = caixa.firstChild, inv = raiz.getScreenCTM().inverse();
    raiz.querySelectorAll(SVG_FORMAS.join(",")).forEach(el => {
      if (typeof el.getTotalLength !== "function") return;
      const L = el.getTotalLength(); if (!(L > 0)) return;
      const n = Math.max(8, Math.min(2000, Math.ceil(L / (Math.hypot(s.vb[2], s.vb[3]) / 600)))), passo = L / n, m = inv.multiply(el.getScreenCTM());
      let atual = [], ant = null;
      for (let k = 0; k <= n; k++) {
        const p = el.getPointAtLength(Math.min(L, k * passo)).matrixTransform(m), q = [(p.x - s.vb[0]) * esc_, (alt - (p.y - s.vb[1])) * esc_];
        if (ant && Math.hypot(q[0] - ant[0], q[1] - ant[1]) > 3 * passo * esc_ + 1e-9) { if (atual.length >= 2) lacos.push(atual); atual = []; }
        atual.push(q); ant = q;
      }
      if (atual.length >= 2) lacos.push(atual);
    });
  } finally { caixa.remove(); }
  return lacos;
}
async function imagemDe(f, fonte) {
  if (fonte === "svg") {
    const s = svgLimpo(await f.text()), lado = 1000, w = s.vb[2] >= s.vb[3] ? lado : Math.max(1, Math.round(lado * s.vb[2] / s.vb[3])), h = s.vb[3] > s.vb[2] ? lado : Math.max(1, Math.round(lado * s.vb[3] / s.vb[2]));
    const url = URL.createObjectURL(new Blob([svgDe(s, w, h, "black")], { type: "image/svg+xml" })), im = new Image();
    try { im.src = url; await im.decode(); } finally { setTimeout(() => URL.revokeObjectURL(url), 1000); }
    return { img: im, w, h, svg: s };
  }
  if (typeof createImageBitmap === "function") { const b = await createImageBitmap(f); return { img: b, w: b.width, h: b.height }; }
  const url = URL.createObjectURL(f), im = new Image();
  try { im.src = url; await im.decode(); } finally { setTimeout(() => URL.revokeObjectURL(url), 1000); }
  return { img: im, w: im.naturalWidth, h: im.naturalHeight };
}
function processarArquivo() {
  const a = lab.arq; if (!a || !a.img) return;
  const p = a.par, I = window.PhysisImagem3D;
  a.r = null;
  try {
    if (!I || !window.PHYSIS3D) throw new Error("Os módulos de imagem e do Physis 3D não carregaram.");
    const asp = a.w / a.h, nx = asp >= 1 ? p.res : Math.max(2, Math.round(p.res * asp)), ny = asp >= 1 ? Math.max(2, Math.round(p.res / asp)) : p.res;
    const cv = document.createElement("canvas"); cv.width = nx; cv.height = ny;
    const cx = cv.getContext("2d"); cx.clearRect(0, 0, nx, ny); cx.drawImage(a.img, 0, 0, nx, ny);
    const M = I.mascara(cx.getImageData(0, 0, nx, ny).data, nx, ny, p.limiar, p.inverter), cel = p.largura / nx;
    const lacos = a.svg ? lacosDoSvg(a.svg, p.largura) : I.contornos(M, nx, ny, cel, 0.5);
    const T = I.relevo(M, nx, ny, cel, p.altura, p.base);
    a.r = { nx, ny, cel, lacos, T, med: PHYSIS3D.medir(T), larg: nx * cel, alt: ny * cel, celulas: M.reduce((s, v) => s + v, 0) };
  } catch (e) { a.r = { erro: String(e && e.message || e) }; }
}
async function receberArquivo(f) {
  if (!f) return { texto: "Escolha um arquivo.", erro: true };
  if (f.size > ARQ_MAX) return { texto: "Arquivo grande demais (máximo 20 MB).", erro: true };
  const fonte = tipoDe(f), base = (f.name || "arquivo").replace(/\.[^.]+$/, "");
  lab.arq = { nome: f.name, base, tipo: f.type || "", tamanho: f.size, fonte, arquivo: f, par: Object.assign({}, PAR_PADRAO), r: null };
  proj.arquivos.push({ nome: String(f.name).slice(0, 160), tipo: String(f.type || "").slice(0, 80), tamanho: f.size, fonte, recebido_em: agora() });
  if (proj.arquivos.length > 200) proj.arquivos.splice(0, proj.arquivos.length - 200);
  registrarPasso("arquivo", f.name);
  gravarProjeto("Arquivo registrado no projeto.");
  if (fonte === "imagem" || fonte === "svg") {
    try { Object.assign(lab.arq, await imagemDe(f, fonte)); } catch (e) { lab.arq.r = { erro: "Não deu para ler: " + (e && e.message || e) }; return { texto: "Não deu para ler o arquivo.", erro: true }; }
    processarArquivo();
    return { texto: fonte === "svg" ? "SVG lido: os caminhos vão direto para o CAD 2D; o 3D sai das formas preenchidas." : "Imagem lida: ajuste o limiar e as medidas e confira a prévia." };
  }
  return { texto: fonte === "malha" ? "Malha recebida: abra em Peças 3D." : fonte === "pdf" ? "PDF recebido: veja abaixo o que fazer." : "Arquivo registrado no projeto." };
}
function lerParametros() {
  const a = lab.arq, v = id => (document.getElementById(id) || {}).value, lim = (x, a_, b) => Math.max(a_, Math.min(b, x));
  a.par = { limiar: lim(Math.round(numL(v("ar-limiar"), a.par.limiar)), 0, 255), inverter: !!(document.getElementById("ar-inverter") || {}).checked,
    res: lim(Math.round(numL(v("ar-res"), a.par.res)), 10, 250), largura: lim(numL(v("ar-largura"), a.par.largura), 1, 1000),
    altura: lim(numL(v("ar-altura"), a.par.altura), 0, 500), base: lim(numL(v("ar-base"), a.par.base), 0, 100) };
}
function previa2d(r) {
  const d = r.lacos.map(l => "M" + l.map(p => (+p[0]).toFixed(3) + " " + (r.alt - p[1]).toFixed(3)).join(" L") + (l.length > 2 ? " Z" : "")).join(" ");
  return `<figure><svg viewBox="0 0 ${r.larg.toFixed(3)} ${r.alt.toFixed(3)}" role="img" aria-label="Prévia do CAD 2D: ${r.lacos.length} contornos em ${nf(r.larg, 1)} × ${nf(r.alt, 1)} mm" style="width:100%;max-width:520px;height:auto;border:1px solid var(--linha);border-radius:8px;background:var(--sup);color:var(--texto)">
    <path d="${d}" fill="currentColor" fill-opacity="0.25" fill-rule="evenodd" stroke="currentColor" stroke-width="${(r.larg / 300).toFixed(3)}"/></svg>
    <figcaption class="t2 pq">Prévia do CAD 2D: ${r.lacos.length} contornos; ${nf(r.larg, 1)} × ${nf(r.alt, 1)} mm.</figcaption></figure>`;
}
function telaArquivo() {
  const a = lab.arq, f = (n, rot, val, dica) => `<div><label for="ar-${n}">${rot}</label><input id="ar-${n}" type="text" inputmode="decimal" value="${escL(val)}" data-lab-par="1"${dica ? ` aria-describedby="ar-${n}-d"` : ""}>${dica ? `<p class="t2 pq" id="ar-${n}-d">${dica}</p>` : ""}</div>`;
  let h = `<h2>Enviar arquivo</h2>
  <section class="cartao" aria-labelledby="ar-o-h"><h3 id="ar-o-h">O primeiro passo do fluxo</h3>
    <p>Envie qualquer arquivo, de qualquer assunto. Imagem (PNG, JPG ou WebP) e SVG viram CAD 2D (contorno vetorizado, em SVG e DXF) e um modelo 3D (extrusão do contorno), que você ajusta antes de mandar para Peças 3D e para a impressão. Malhas STL, OBJ e 3MF vão direto para Peças 3D. O arquivo é lido no seu navegador e não sai do seu computador; o projeto comum guarda só o nome, o tipo e o tamanho.</p>
    <label for="ar-arq">Arquivo</label><input id="ar-arq" type="file" data-lab-arq="enviar">
    ${msgHtml("ar-msg", lab.arqMsg)}</section>`;
  if (!a) return h + cartaoTestes();
  if (a.fonte === "malha") return h + `<section class="cartao" aria-labelledby="ar-m-h"><h3 id="ar-m-h">Malha: ${escL(a.nome)}</h3><p>STL, OBJ e 3MF são lidos pelo Physis 3D.</p>
    <div class="acoes"><button class="botao" type="button" id="ar-abrir-malha" data-lab="arq-malha">Abrir em Peças 3D</button></div></section>`;
  if (a.fonte === "pdf") return h + `<section class="cartao" aria-labelledby="ar-p-h"><h3 id="ar-p-h">PDF: ${escL(a.nome)}</h3>
    <p class="faixa" role="note">Sem uma biblioteca de fora, o navegador não consegue ler o desenho de dentro de um PDF aqui. Exporte a página como imagem (PNG ou JPG) ou como SVG e envie de novo. A leitura direta de PDF fica como próxima etapa [MARCADOR: decidir a leitura de PDF].</p>
    <p class="t2">O PDF ficou registrado no projeto (nome, tipo e tamanho).</p></section>`;
  if (a.fonte === "outro") return h + `<section class="cartao" aria-labelledby="ar-x-h"><h3 id="ar-x-h">${escL(a.nome)}</h3>
    <p>Este tipo de arquivo ficou registrado no projeto, mas ainda não é transformado aqui. Para virar CAD 2D e 3D, envie uma imagem (PNG, JPG, WebP), um SVG ou uma malha (STL, OBJ, 3MF).</p></section>`;
  const p = a.par, r = a.r || {};
  h += `<section class="cartao" aria-labelledby="ar-e-h"><h3 id="ar-e-h">Ajustar: ${escL(a.nome)}</h3>
    <form id="ar-form" novalidate><div class="campos">
      ${f("limiar", "Limiar (0 a 255)", p.limiar, "Abaixo do limiar, o pixel escuro vira material.")}
      ${f("res", "Resolução (células na maior medida, 10 a 250)", p.res, "Mais células: mais detalhe e mais triângulos.")}
      ${f("largura", "Largura final (mm)", nf(p.largura, 1), "")}
      ${f("altura", "Altura do relevo (mm)", nf(p.altura, 1), "")}
      ${f("base", "Espessura da base (mm; 0 = sem base)", nf(p.base, 1), "")}</div>
      <label class="opcao"><input type="checkbox" id="ar-inverter" data-lab-par="1"${p.inverter ? " checked" : ""}> Inverter (o claro vira material)</label>
      <div class="acoes"><button class="botao sec" type="submit" id="ar-atualizar">Atualizar a prévia</button></div></form>
    ${a.svg ? '<p class="t2 pq">SVG: o CAD 2D usa os caminhos do arquivo direto (a resolução e o limiar só mudam o 3D).</p>' : ""}</section>`;
  if (r.erro) return h + `<p class="faixa erro" role="alert">${escL(r.erro)}</p>`;
  if (!r.T) return h;
  const m = r.med;
  h += `<section class="cartao" aria-labelledby="ar-r-h"><h3 id="ar-r-h">CAD 2D e modelo 3D</h3>${previa2d(r)}
    ${tabela("Modelo 3D (extrusão do contorno)", [["Tamanho", m.tamanho.map(v => nf(v, 1)).join(" × ") + " mm"], ["Volume", nf(m.volume_mm3 / 1000, 2) + " cm³"],
      ["Triângulos", nf(m.triangulos, 0)], ["Células de material", nf(r.celulas, 0) + " de " + nf(r.nx * r.ny, 0) + " (" + r.nx + " × " + r.ny + ", " + nf(r.cel, 3) + " mm cada)"],
      ["Malha", m.arestas && m.arestas.fechada ? "fechada" : "com arestas abertas ou não manifold (confira em Peças 3D)"]])}
    <p class="t2">A vista 3D é a do Physis 3D: "Enviar para Peças 3D" abre o modelo lá. Para mudar, volte aqui, ajuste e envie de novo.</p>
    <div class="acoes"><button class="botao" type="button" id="ar-enviar" data-lab="arq-enviar">Enviar para Peças 3D / impressão</button>
      <button class="botao sec" type="button" id="ar-svg" data-lab="arq-svg">Baixar SVG</button><button class="botao sec" type="button" id="ar-dxf" data-lab="arq-dxf">Baixar DXF</button>
      <button class="botao sec" type="button" id="ar-stl" data-lab="arq-stl">Baixar STL</button><button class="botao sec" type="button" id="ar-3mf" data-lab="arq-3mf">Baixar 3MF</button></div></section>`;
  return h;
}
/* entrega um arquivo ao Physis 3D pela própria tela dele (campo de abrir), sem mudar o motor */
function abrirEmPecas(f, rotulo) {
  if (typeof ui !== "undefined") ui.p3dSub = "modelo";
  abaLab = "pecas";
  try { history.pushState(null, "", "#pecas"); } catch (e) {}
  desenhar();
  const x = document.getElementById("p3d-arquivo");
  if (!x || typeof DataTransfer === "undefined") { lab.peca = { texto: "Escolha o arquivo no campo do Physis 3D abaixo (" + f.name + ").", erro: true }; desenhar(); return; }
  const dt = new DataTransfer(); dt.items.add(f); x.files = dt.files;
  x.dispatchEvent(new Event("change", { bubbles: true }));
  registrarPasso("pecas", (rotulo || "aberto em Peças 3D") + ": " + f.name);
  gravarProjeto("Peça aberta em Peças 3D.");
  lab.peca = { texto: f.name + " aberto no Physis 3D. Confira as medidas e guarde no projeto." };
  focar("tab-pecas");
}
function testesProntos() { if (!lab.testes && window.PhysisImagem3D) lab.testes = PhysisImagem3D.testes(); return lab.testes || []; }
function cartaoTestes() {
  const ts = testesProntos();
  return `<section class="cartao" aria-labelledby="tp-h"><h3 id="tp-h">Arquivos de teste para impressão</h3>
    <p>Gerados aqui mesmo, pelo motor do Physis 3D (sem conta e sem nada copiado de terceiros). Baixe em STL ou abra em Peças 3D.</p>
    ${ts.map(t => `<div class="item"><h4 id="tp-${t.id}-h">${escL(t.nome)}</h4><p>${escL(t.medidas)}</p><p class="t2"><strong>O que observar:</strong> ${escL(t.observar)}</p>
      <div class="acoes"><button class="botao sec" type="button" id="tp-${t.id}-b" data-lab="teste-baixar" data-id="${t.id}" aria-describedby="tp-${t.id}-h">Baixar STL</button>
        <button class="botao sec" type="button" id="tp-${t.id}-a" data-lab="teste-abrir" data-id="${t.id}" aria-describedby="tp-${t.id}-h">Abrir em Peças 3D</button></div></div>`).join("")}</section>`;
}

/* ════════ 1. Lugar (GIS) ════════ */
function importarLugar(g, origem, arquivo) {
  if (!lugarValido(g)) return { texto: "Este arquivo não segue o contrato physis-geometria-lugar/1 (esquema, terreno em grade com nx × ny cotas Z, listas de edificações, superfícies e elementos BIM).", erro: true };
  proj.lugar = { origem, arquivo: arquivo || "", importado_em: agora(), dados: g };
  registrarPasso("lugar", arquivo || origem);
  gravarProjeto("Lugar guardado no projeto.");
  return { texto: "Lugar guardado no projeto." };
}
function tabelaLugar(L) {
  const g = L.dados, t = g.terreno, o = g.origem || {};
  let zmin = null, zmax = null;
  if (t) t.Z.forEach(z => { if (typeof z === "number" && isFinite(z)) { zmin = zmin == null ? z : Math.min(zmin, z); zmax = zmax == null ? z : Math.max(zmax, z); } });
  const linhas = [["Contrato", `<code>${escL(g.esquema)}</code>`],
    ["Origem (latitude, longitude)", typeof o.lat === "number" && typeof o.lon === "number" ? nf(o.lat, 5) + ", " + nf(o.lon, 5) : "não informada no arquivo"],
    ["Terreno", t ? `${t.nx} × ${t.ny} células de ${nf(t.cs, 2)} m · cotas de ${nf(zmin, 1)} a ${nf(zmax, 1)} m` : "sem terreno no arquivo"],
    ["Edificações", String((g.edificacoes || []).length)], ["Superfícies (orientação e irradiação)", String((g.superficies || []).length)],
    ["Elementos BIM com materiais", String((g.elementos_bim || []).length)]];
  if (typeof g.fonte === "string") linhas.push(["Fonte", escL(g.fonte)]);
  if (typeof g.atualizado === "string") linhas.push(["Gerado em", escL(quando(g.atualizado))]);
  linhas.push(["Levado ao projeto", deOnde(L)]);
  return tabela("Resumo do lugar (só o que está no arquivo)", linhas);
}
function telaLugar() {
  const L = proj.lugar;
  return `<h2>Lugar (GIS)</h2>
  <section class="cartao" aria-labelledby="lg-o-h"><h3 id="lg-o-h">O que é</h3>
    <p>O lugar é o terreno do projeto e o que está em volta: relevo em grade, edificações e superfícies com a orientação e o sol que recebem. Ele vem do Mapeamento da plataforma ou de arquivo; aqui ele entra no projeto comum para as outras subabas lerem (a Simulação usa o terreno no bloco Terreno e água).</p></section>
  <section class="cartao" aria-labelledby="lg-i-h"><h3 id="lg-i-h">Levar o lugar para o projeto</h3>
    <p>O arquivo do lugar segue o contrato <code>physis-geometria-lugar/1</code> (docs/MAPEAMENTO.md): terreno em grade (x para o leste, y para o norte, cotas Z), caixas das edificações, superfícies com orientação e irradiação e os materiais dos elementos BIM. Só dados: nenhuma conta é feita aqui.</p>
    <label for="lg-arq">Arquivo do lugar (.json)</label><input id="lg-arq" type="file" accept=".json,application/json" data-lab-arq="lugar">
    <div class="acoes"><button class="botao sec" type="button" id="lg-nav" data-lab="lugar-navegador">Ler o lugar que o Mapeamento gravou neste navegador</button></div>
    <p class="t2 pq">O Mapeamento da plataforma grava este contrato no navegador quando você envia o sol nas superfícies para a Solar e o AVAC; se você usou o Mapeamento neste mesmo endereço e navegador, o botão acima lê o lugar..</p>
    ${msgHtml("lg-msg", lab.lugar)}</section>
  ${L ? `<section class="cartao" aria-labelledby="lg-r-h"><h3 id="lg-r-h">Lugar no projeto</h3>${tabelaLugar(L)}
    <div class="acoes"><button class="botao sec" type="button" id="lg-tirar" data-lab="lugar-tirar">Tirar o lugar do projeto</button></div></section>` : ""}`;
}

/* ════════ 2. Edificação (BIM) ════════ */
function importarIfc(r, origem, arquivo) {
  if (!resumoIfcValido(r)) return { texto: "Este arquivo não é o resumo do leitor IFC (falta o esquema ou os elementos por tipo).", erro: true };
  proj.edificacao = { origem, arquivo: arquivo || "", importado_em: agora(), resumo: r };
  registrarPasso("edificacao", arquivo || origem);
  gravarProjeto("Resumo da edificação guardado no projeto.");
  return { texto: "Resumo da edificação guardado no projeto." };
}
async function lerIfcServidor() {
  const inp = document.getElementById("ed-ifc"), f = inp && inp.files && inp.files[0];
  if (!f) return { texto: "Escolha um arquivo .ifc primeiro.", erro: true };
  if (f.size > ARQ_MAX) return { texto: "Arquivo grande demais (máximo 20 MB).", erro: true };
  const i = await instancia(true);
  if (!i || !i.autenticado) return { texto: "Para ler o IFC no servidor, entre com a sua conta (Participar, no site). Sem conta, use o caminho 2: o resumo em JSON.", erro: true };
  let j = {};
  try { const r = await fetch("/api/mapeamento/ifc/ler", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/octet-stream", "X-Physis-CSRF": i.csrf || "" }, body: await f.arrayBuffer() });
    try { j = await r.json(); } catch (e) {} } catch (e) { return { texto: "Sem ligação com o servidor da InovaSTEM.", erro: true }; }
  if (!j.ok) return { texto: j.erro || "O servidor não leu o arquivo.", erro: true };
  return importarIfc(j.resumo, "leitor IFC do servidor", f.name);
}
function tabelaIfc(Ed) {
  const r = Ed.resumo, nomes = a => Array.isArray(a) && a.length ? a.map(x => escL(x && x.nome != null ? x.nome : "(sem nome)")).join(", ") : "nenhum no arquivo";
  const linhas = [["Esquema", escL(r.esquema)]];
  if (r.projeto != null) linhas.push(["Projeto", escL(r.projeto)]);
  if (typeof r.entidades === "number") linhas.push(["Entidades no arquivo", nf(r.entidades, 0)]);
  if (r.terrenos) linhas.push(["Terrenos", nomes(r.terrenos)]);
  if (r.edificacoes) linhas.push(["Edificações", nomes(r.edificacoes)]);
  if (Array.isArray(r.pavimentos)) linhas.push(["Pavimentos", r.pavimentos.length ? r.pavimentos.map(p => escL(p.nome) + (typeof p.elevacao_m === "number" ? " (" + nf(p.elevacao_m, 2) + " m)" : "")).join(", ") : "nenhum no arquivo"]);
  if (typeof r.elementos === "number") linhas.push(["Elementos", nf(r.elementos, 0)]);
  if (r.caixa && Array.isArray(r.caixa.min) && Array.isArray(r.caixa.max)) linhas.push(["Caixa envolvente", r.caixa.min.map(v => nf(v, 2)).join("; ") + " até " + r.caixa.max.map(v => nf(v, 2)).join("; ") + " " + escL(r.caixa.unidade || "")]);
  linhas.push(["Levado ao projeto", deOnde(Ed)]);
  const tipos = Object.keys(r.elementos_por_tipo);
  return (r.aviso ? `<p class="faixa" role="note">${escL(r.aviso)}</p>` : "") + tabela("Resumo da edificação (só o que está no arquivo)", linhas)
    + (tipos.length ? `<div class="rolagem"><table><caption>Elementos por tipo IFC</caption><thead><tr><th scope="col">Tipo</th><th scope="col">Quantidade</th></tr></thead><tbody>${tipos.map(k => `<tr><th scope="row">${escL(k)}</th><td>${escL(r.elementos_por_tipo[k])}</td></tr>`).join("")}</tbody></table></div>` : "");
}
function telaEdificacao() {
  const Ed = proj.edificacao;
  return `<h2>Edificação (BIM)</h2>
  <section class="cartao" aria-labelledby="ed-o-h"><h3 id="ed-o-h">O que é</h3>
    <p>A edificação vem de um modelo BIM aberto (IFC). Aqui entra só o resumo do modelo: esquema, projeto, terrenos, edificações, pavimentos e elementos por tipo (leitor básico, sem geometria).</p></section>
  <section class="cartao" aria-labelledby="ed-1-h"><h3 id="ed-1-h">Caminho 1: ler o IFC no servidor (com conta)</h3>
    <p>O arquivo vai só para o servidor da InovaSTEM, que devolve o resumo (leitor <code>ifc.py</code>) e não guarda o arquivo.</p>
    <label for="ed-ifc">Arquivo IFC (.ifc, texto STEP)</label><input id="ed-ifc" type="file" accept=".ifc">
    <div class="acoes"><button class="botao" type="button" id="ed-ler" data-lab="ed-ler">Ler o resumo e guardar no projeto</button></div></section>
  <section class="cartao" aria-labelledby="ed-2-h"><h3 id="ed-2-h">Caminho 2: importar o resumo em JSON (sem conta)</h3>
    <p>O mesmo resumo que o leitor IFC devolve, guardado em arquivo (por exemplo, o resumo do pacote de exemplo do Mapeamento).</p>
    <label for="ed-json">Resumo do IFC (.json)</label><input id="ed-json" type="file" accept=".json,application/json" data-lab-arq="ifc-resumo"></section>
  ${msgHtml("ed-msg", lab.ed)}
  ${Ed ? `<section class="cartao" aria-labelledby="ed-r-h"><h3 id="ed-r-h">Edificação no projeto</h3>${tabelaIfc(Ed)}
    <div class="acoes"><button class="botao sec" type="button" id="ed-tirar" data-lab="ed-tirar">Tirar a edificação do projeto</button></div></section>` : ""}`;
}

/* ════════ 3. Peças 3D (motor sistema/physis-3d.js, sem mudar) ════════ */
function telaPecas() {
  const st = (typeof ui !== "undefined" && ui.p3d) || {}, m = st.med, pode = !!(st.T && m);
  const linhas = proj.pecas.map((p, i) => `<tr><th scope="row">${escL(p.nome)}</th><td>${Array.isArray(p.tamanho_mm) ? p.tamanho_mm.map(v => nf(v, 1)).join(" × ") + " mm" : "—"}</td>
      <td>${nf(p.volume_mm3 / 1000, 2)} cm³</td><td>${p.biblioteca_id ? "peça " + escL(p.biblioteca_id) : "—"}</td><td>${escL(quando(p.guardado_em))}</td>
      <td><button class="botao sec" type="button" id="pc-tirar-${i}" data-lab="peca-tirar" data-i="${i}" aria-label="Tirar ${escL(p.nome)} do projeto">Tirar</button></td></tr>`).join("");
  return `<h2>Peças 3D</h2>
  <section class="cartao" aria-labelledby="pc-h"><h3 id="pc-h">Peças no projeto</h3>
    <p class="t2">Abra a peça no Physis 3D logo abaixo (STL, OBJ ou 3MF). Depois guarde as medidas dela no projeto comum. O arquivo fica no seu computador; para a galeria e a fila de impressão, envie a peça à Biblioteca (com conta).</p>
    <div class="acoes"><button class="botao" type="button" id="pc-guardar" data-lab="peca-guardar"${pode ? "" : ' disabled aria-describedby="pc-guardar-dica"'}>Guardar a peça aberta no projeto</button></div>
    ${pode ? "" : '<p class="t2 pq" id="pc-guardar-dica">Abra um arquivo de peça primeiro.</p>'}
    ${msgHtml("pc-msg", lab.peca)}
    ${proj.pecas.length ? `<div class="rolagem"><table><caption>Peças guardadas no projeto</caption><thead><tr><th scope="col">Peça</th><th scope="col">Tamanho</th><th scope="col">Volume</th><th scope="col">Biblioteca</th><th scope="col">Guardada em</th><th scope="col">Ação</th></tr></thead><tbody>${linhas}</tbody></table></div>` : ""}</section>
  ${telaPhysis3D()}
  ${cartaoTestes()}`;
}
function guardarPeca() {
  const st = (typeof ui !== "undefined" && ui.p3d) || {}, m = st.med;
  if (!st.T || !m) return { texto: "Abra um arquivo de peça primeiro.", erro: true };
  const bib = st.peca && st.peca.ok && st.peca.peca ? st.peca.peca.id : null;
  proj.pecas.push({ nome: String(st.nome || "peça"), origem: "Physis 3D (arquivo aberto neste navegador)", tamanho_mm: (m.tamanho || []).slice(0, 3),
    volume_mm3: m.volume_mm3, area_mm2: m.area_mm2, triangulos: m.triangulos, biblioteca_id: bib, guardado_em: agora() });
  registrarPasso("pecas", "guardada: " + String(st.nome || "peça"));
  gravarProjeto("Peça guardada no projeto.");
  return { texto: "Peça guardada no projeto: " + String(st.nome || "peça") + "." };
}

/* ════════ 4. Simulação: um bloco por fenômeno (motor window.SIMULACAO, sem mudar contas) ════════ */
const FEN = [
  { id: "calor", nome: "Calor", prefixos: ["termica."],
    faz: "Transmitância (U) de parede ou cobertura, a parede ao longo do dia (atraso térmico e amortecimento) e o corte 2D (ponte térmica, corte de peça impressa).",
    entra: "Camadas ou composição da base de materiais, resistências superficiais de premissa, temperaturas e sol ao longo do dia; no corte 2D, a máscara do corte.",
    sai: "U, capacidade térmica e carbono por m²; atraso e amortecimento; campo de temperatura e fluxos de calor.",
    limites: "Condução em 1D ou 2D com propriedades da base de materiais; convecção e radiação por coeficientes de premissa. Cada resultado traz o limite do motor." },
  { id: "estrutura", nome: "Estrutura", prefixos: ["estrutura."],
    faz: "Treliça e pórtico 2D e 3D, flambagem de Euler, verificação de tensão e chapa 2D com triângulos (peças impressas).",
    entra: "Nós, barras, apoios, cargas nos nós, carga distribuída e peso próprio; seção e material (módulo E; resistência fy de ensaio, sem ela vira [MARCADOR]).",
    sai: "Deslocamentos, reações, esforços (normal, cortante, momento, torção), tensões e a verificação de cada elemento.",
    limites: "Estrutura linear (pequenos deslocamentos, material elástico). Vento só pela pressão dinâmica, com coeficientes digitados [CONFERIR NA NORMA]." },
  { id: "ventilacao", nome: "Ventilação e vento", prefixos: ["fluidos."],
    faz: "Ventilação natural (chaminé e vento), escoamento do ar num corte (Lattice-Boltzmann D2Q9, qualitativo) e energia de turbina pela série de vento.",
    entra: "Aberturas, alturas e temperaturas; grade e obstáculo do corte; série de vento e curva da turbina.",
    sai: "Vazão e trocas de ar por hora; campo de velocidade qualitativo; energia pela série e pela Weibull ajustada.",
    limites: "Coeficientes de descarga e de pressão de premissa. O escoamento LBM é qualitativo (Fase 1): mostra esteira e aceleração, nunca número de projeto." },
  { id: "terreno", nome: "Terreno e água", prefixos: ["terreno."],
    faz: "Declividade e aspecto, caminho da água (D8) e acumulação, enxurrada de um evento (SCS-CN), perda de solo (USLE) e visada.",
    entra: "Grade de cotas (a do exemplo ou o terreno do lugar do projeto, contrato physis-geometria-lugar/1); chuva e CN por uso do solo; R, K, C e P digitados na USLE.",
    sai: "Acumulação de fluxo, volume de enxurrada acumulado, perda de solo por célula e células visíveis.",
    limites: "Evento isolado e bacias pequenas no SCS-CN (sem vazão de pico nem hidrograma); fatores da USLE digitados. Cada resultado traz o limite do motor." },
  { id: "incerteza", nome: "Incerteza", prefixos: ["incerteza."],
    faz: "Monte Carlo: sorteia as entradas (normal, uniforme, triangular, lognormal) e mostra a média e os percentis do resultado.",
    entra: "Cada entrada com a sua distribuição; o modelo (carbono, solar, payback ou biogás); número de sorteios e semente.",
    sai: "Média e percentis (faixa) do resultado do modelo.",
    limites: "A faixa vale para as distribuições digitadas; o gerador tem semente fixa para repetir o resultado." },
  { id: "biogas", nome: "Biogás", prefixos: ["biogas."],
    faz: "Produção de biogás por substrato, com cinética de primeira ordem dependente da temperatura e tempo de retenção.",
    entra: "Substratos e quantidades, volume ou tempo de retenção, regime de temperatura e a temperatura mensal do local (sem local, a conta para: nunca usa um padrão).",
    sai: "Biogás e metano por dia e por mês, volume, carga orgânica, energia, GLP equivalente, gerador (P, Q, S e fator de potência), CO₂e evitado, digestato e avisos.",
    limites: "Propriedades dos substratos de premissa \"conferir\"; substrato sem valor vira [MARCADOR]. Cada resultado traz o limite do motor." },
  { id: "qubo", nome: "Otimização QUBO", prefixos: ["qubo."],
    faz: "Problemas pequenos escritos como QUBO: placas sob sombra, caminho de tubo na grade e topologia grossa de peça 2D, resolvidos agora no clássico.",
    entra: "Posições, sombras, grade e custos do problema; penalidade de premissa.",
    sai: "A solução clássica (exata até 20 variáveis ou recozimento simulado) e a energia do QUBO.",
    limites: "A trilha quântica é pesquisa (P&D): precisa dar o mesmo ótimo do clássico e nunca entra em relatório nem certificação." }];
const TERRENO_DO_LUGAR = ["terreno.escoamento", "terreno.usle", "terreno.declividade_aspecto"];   // casos que só pedem a grade
function casosDe(f) {
  const cs = ((window.SIMULACAO_CASOS || {}).casos || []).filter(c => f.prefixos.some(p => String(c.solver).indexOf(p) === 0));
  return cs.filter(c => c.exemplo).concat(cs.filter(c => !c.exemplo));
}
function estSim(f) {
  const cs = casosDe(f), st = lab.sim[f.id] = lab.sim[f.id] || { caso: null, entrada: null, res: null, c2: null, msg: null, usarLugar: false, aberta: false };
  const c = cs.filter(x => x.id === st.caso)[0] || cs[0];
  if (c && (st.caso !== c.id || st.entrada == null)) { st.caso = c.id; st.entrada = JSON.stringify(c.entrada, null, 1); st.res = null; st.c2 = null; }
  return { st, c, cs };
}
function rodarFen(f) {
  const { st, c } = estSim(f);
  if (!c) return;
  const ta = document.getElementById("sim-ent-" + f.id);
  if (ta) { st.entrada = ta.value; const det = ta.closest("details"); st.aberta = !!(det && det.open); }
  st.res = null; st.c2 = null; st.doLugar = false;
  if (!window.SIMULACAO) { st.msg = { texto: "O motor da simulação não carregou.", erro: true }; return; }
  let e;
  try { e = JSON.parse(st.entrada); } catch (x) { st.msg = { texto: "Entrada inválida (JSON): " + x.message, erro: true }; st.aberta = true; return; }
  if (st.usarLugar && TERRENO_DO_LUGAR.indexOf(c.solver) >= 0) {
    if (!(proj.lugar && proj.lugar.dados.terreno)) { st.msg = { texto: "O projeto não tem terreno: importe o lugar na subaba Lugar (GIS).", erro: true }; return; }
    try { e = Object.assign({}, e, { grade: SIMULACAO.terreno.gradeDaGeometria(proj.lugar.dados) }); st.doLugar = true; }
    catch (x) { st.msg = { texto: String(x && x.message || x), erro: true }; return; }
  }
  const c2 = Object.assign({}, c, { entrada: e });
  try { st.res = SIMULACAO.rodarCaso(c2); st.c2 = c2; st.msg = { texto: "Pronto: " + c.nome + (st.doLugar ? " (terreno do lugar do projeto)" : "") + "." }; }
  catch (x) { st.msg = { texto: (x && x.faltaDado ? "" : "Não deu para rodar: ") + (x && x.message || x), erro: true }; }
}
function escalares(r) {
  const o = {}, n = v => typeof v === "number" && isFinite(v);
  Object.keys(r).forEach(k => {
    const v = r[k];
    if (["metodo", "limites_validade", "aviso", "fase"].indexOf(k) >= 0) return;
    if (n(v) || typeof v === "boolean") o[k] = v;
    else if (typeof v === "string" && v.length <= 200) o[k] = v;
    else if (v && typeof v === "object" && !Array.isArray(v)) { const ks = Object.keys(v); if (ks.length && ks.length <= 20 && ks.every(x => n(v[x]) || typeof v[x] === "string" && v[x].length <= 80)) o[k] = v; }
  });
  return o;
}
function guardarResultado(f) {
  const { st, c } = estSim(f);
  if (!st.res || !st.c2) return { texto: "Rode o exemplo antes de guardar.", erro: true };
  const original = JSON.stringify(c.entrada, null, 1), mudou = st.entrada !== original;
  const r = { fenomeno: f.id, fenomeno_nome: f.nome, caso: c.id, nome: c.nome, solver: c.solver, exemplo_dados_ficticios: !!c.exemplo,
    entrada_mudada: mudou, terreno_do_lugar: !!st.doLugar, metodo: st.res.metodo || "", limites_validade: st.res.limites_validade || "",
    aviso: st.res.aviso || "", avisos: (st.res.avisos || []).slice(0, 20), valores: escalares(st.res), guardado_em: agora() };
  if (mudou && st.entrada.length <= 20000) r.entrada = st.entrada;
  proj.resultados.push(r);
  registrarPasso("simulacao", f.nome + ": " + c.nome);
  gravarProjeto("Resultado guardado no projeto.");
  return { texto: "Resultado guardado no projeto: " + c.nome + "." };
}
function envelope(r) {
  if (!r) return "";
  const prem = (r.premissas_usadas || []).map(p => `<li><code>${escL(p.id)}</code> (${escL(p.status)})</li>`).join("");
  return `<details><summary>Método, hipóteses e premissas</summary>${r.metodo ? `<p><strong>Método:</strong> ${escL(r.metodo)}</p>` : ""}
      ${r.malha != null ? `<p><strong>Malha ou grade:</strong> ${escL(JSON.stringify(r.malha))}</p>` : ""}
      ${(r.hipoteses || []).length ? `<ul class="lista">${r.hipoteses.map(h => `<li>${escL(h)}</li>`).join("")}</ul>` : ""}
      ${prem ? `<p><strong>Premissas usadas:</strong></p><ul class="lista">${prem}</ul>` : ""}</details>
    ${r.limites_validade ? `<p><strong>Limites de validade (do motor):</strong> ${escL(r.limites_validade)}</p>` : ""}
    ${(r.avisos || []).length ? `<div class="faixa at" role="note"><ul class="lista">${r.avisos.map(a => `<li>${escL(a)}</li>`).join("")}</ul></div>` : ""}
    ${r.aviso ? `<p class="faixa in" role="note">${escL(r.aviso)}</p>` : ""}`;
}
function blocoFen(f, n) {
  const { st, c, cs } = estSim(f);
  if (!c) return `<section class="cartao lab-fen" id="fen-${f.id}" tabindex="-1" aria-labelledby="fen-${f.id}-h"><h3 id="fen-${f.id}-h">${n}. ${escL(f.nome)}</h3><p class="faixa in" role="note">Exemplos não carregados.</p></section>`;
  const temLugar = f.id === "terreno", pode = TERRENO_DO_LUGAR.indexOf(c.solver) >= 0, terr = !!(proj.lugar && proj.lugar.dados.terreno);
  let res = "";
  if (st.res && st.c2) { try { res = SIMULACAO.desenhoCaso(st.c2, st.res, "sim-fig-" + f.id); } catch (x) { res = ""; } res += envelope(st.res); }
  return `<section class="cartao lab-fen" id="fen-${f.id}" tabindex="-1" aria-labelledby="fen-${f.id}-h"><h3 id="fen-${f.id}-h">${n}. ${escL(f.nome)}</h3>
    <dl class="lab-ficha"><dt>O que faz</dt><dd>${escL(f.faz)}</dd><dt>Entradas</dt><dd>${escL(f.entra)}</dd><dt>O que sai</dt><dd>${escL(f.sai)}</dd><dt>Limites de validade</dt><dd>${escL(f.limites)}</dd></dl>
    <label for="sim-sel-${f.id}">Exemplo deste fenômeno</label>
    <select id="sim-sel-${f.id}" data-lab-sel="${f.id}">${cs.map(x => `<option value="${escL(x.id)}"${x.id === c.id ? " selected" : ""}>${escL(x.nome)}${x.exemplo ? "" : " (teste de conferência)"}</option>`).join("")}</select>
    <p class="t2 pq">${escL(c.descricao || "")} ${c.exemplo ? (/fictíci/i.test(c.descricao || "") ? "" : "Exemplo com dados fictícios.") : "Teste de conferência: o resultado é conhecido (conta analítica)."}</p>
    ${temLugar ? `<label class="opcao"><input type="checkbox" id="sim-lugar-${f.id}" data-lab-chk="${f.id}"${st.usarLugar ? " checked" : ""}${terr && pode ? "" : " disabled"}> Usar o terreno do lugar do projeto</label>
      <p class="t2 pq">${terr ? (pode ? "O terreno do lugar troca a grade do exemplo." : "Este exemplo pede mais que a grade (usos do solo ou ponto de visada): use D8, USLE ou declividade.") : "O projeto ainda não tem terreno (subaba Lugar)."}</p>` : ""}
    <details${st.aberta ? " open" : ""}><summary>Entrada (JSON): mude e rode de novo</summary><label for="sim-ent-${f.id}">Entrada do exemplo</label>
      <textarea id="sim-ent-${f.id}" rows="8" style="width:100%" spellcheck="false">${escL(st.entrada)}</textarea></details>
    <div class="acoes"><button class="botao" type="button" id="sim-rodar-${f.id}" data-lab="sim-rodar" data-fen="${f.id}">Rodar ${escL(f.nome.toLowerCase())}</button>
      <button class="botao sec" type="button" id="sim-repor-${f.id}" data-lab="sim-repor" data-fen="${f.id}">Voltar ao exemplo</button>
      <button class="botao sec" type="button" id="sim-guardar-${f.id}" data-lab="sim-guardar" data-fen="${f.id}"${st.res ? "" : ' disabled aria-describedby="sim-dica-' + f.id + '"'}>Guardar no projeto</button></div>
    ${st.res ? "" : `<p class="t2 pq" id="sim-dica-${f.id}">Rode o exemplo para poder guardar o resultado.</p>`}
    ${msgHtml("sim-msg-" + f.id, st.msg)}
    <div class="lab-res">${res}</div></section>`;
}
function telaSimulacaoBlocos() {
  const guardados = proj.resultados.map((r, i) => `<tr><th scope="row">${escL(r.nome)}</th><td>${escL(r.fenomeno_nome)}</td><td>${r.exemplo_dados_ficticios ? "exemplo (dados fictícios)" : "teste de conferência"}${r.entrada_mudada ? ", entrada mudada" : ""}${r.terreno_do_lugar ? ", terreno do lugar" : ""}</td>
      <td>${escL(quando(r.guardado_em))}</td><td><button class="botao sec" type="button" id="res-tirar-${i}" data-lab="res-tirar" data-i="${i}" aria-label="Tirar ${escL(r.nome)} do projeto">Tirar</button></td></tr>`).join("");
  return `<h2>Simulação</h2>
  <p>Contas leves da Fase 1 que rodam aqui mesmo, sem internet, pelo motor da simulação (o mesmo do servidor, com paridade conferida). Um bloco por fenômeno: o que faz, o que entra, o que sai, os limites de validade e os exemplos daquele fenômeno.</p>
  <p class="faixa" role="note">Pré-dimensionamento para aprender e testar ideias, para revisão do engenheiro: não aprova projeto, não substitui norma nem ensaio.</p>
  <ul class="lab-indice" aria-label="Ir para o bloco do fenômeno">${FEN.map((f, i) => `<li><button class="botao sec" type="button" id="sim-ir-${f.id}" data-lab="sim-ir" data-fen="${f.id}">${i + 1}. ${escL(f.nome)}</button></li>`).join("")}</ul>
  ${FEN.map((f, i) => blocoFen(f, i + 1)).join("")}
  <section class="cartao" aria-labelledby="sim-proj-h"><h3 id="sim-proj-h">Resultados guardados no projeto</h3>
    ${proj.resultados.length ? `<div class="rolagem"><table><caption>Resultados no projeto comum</caption><thead><tr><th scope="col">Caso</th><th scope="col">Fenômeno</th><th scope="col">Origem</th><th scope="col">Guardado em</th><th scope="col">Ação</th></tr></thead><tbody>${guardados}</tbody></table></div>` : '<p class="t2">Nenhum resultado guardado ainda.</p>'}</section>`;
}

/* ════════ 5. Escaneamento (CrealityScan) ════════ */
function telaEscaneamento() {
  return `<h2>Escaneamento</h2>
  <section class="cartao" aria-labelledby="es-h"><h3 id="es-h">Modelos do CrealityScan</h3>
    <p>O escaneamento é feito no CrealityScan, fora do navegador. Hoje o Physis 3D lê STL, OBJ e 3MF: exporte o modelo escaneado em <strong>STL</strong> ou <strong>OBJ</strong> e abra o arquivo em Peças 3D.</p>
    <ol class="lista"><li>No CrealityScan, exporte o modelo em STL ou OBJ [CONFERIR o nome da opção de exportar na versão instalada].</li>
      <li>Abra a subaba Peças 3D e escolha o arquivo. Confira a unidade (milímetros ou polegadas) e o tamanho nas medidas.</li>
      <li>Veja as arestas abertas e as faces com o lado trocado nas medidas: a malha de um escaneamento costuma precisar de acerto antes de imprimir.</li>
      <li>Guarde a peça no projeto e, com conta, envie à Biblioteca para a galeria ou a fila de impressão.</li></ol>
    <p class="faixa" role="note">Esta subaba não faz fotogrametria nem limpeza de malha: o escopo da limpeza é uma pergunta aberta da direção [MARCADOR].</p>
    <div class="acoes"><a class="botao" href="#pecas">Abrir Peças 3D</a></div></section>`;
}

/* ════════ 6. Fila de impressão (physis_hub/inovastem.py: /api/inovastem/impressao*) ════════ */
async function carregarFila() {
  lab.fila = { carregando: true };
  const i = await instancia(true), f = { inst: i, minhas: null, equipe: null, pecas: null };
  if (i && i.autenticado) {
    f.minhas = await getJ("/api/inovastem/impressao/minhas");
    f.pecas = await getJ("/api/3d/pecas");
    if (ehEquipe(i)) f.equipe = await getJ("/api/inovastem/impressao/fila");
  }
  lab.fila = f;
}
const nomeMat = k => { try { const M = window.PHYSIS3D && PHYSIS3D.materiais ? PHYSIS3D.materiais() : {}; return (M[k] && M[k].nome) || k; } catch (e) { return k; } };
function telaFila() {
  const f = lab.fila, situacao = x => escL(ESTADOS[x.estado] || x.estado) + (x.motivo ? " · motivo: " + escL(x.motivo) : "");
  let h = `<h2>Fila de impressão</h2>
  <section class="cartao" aria-labelledby="fi-o-h"><h3 id="fi-o-h">Como funciona</h3>
    <ol class="lista"><li>Com a sua conta, escolha uma peça da Biblioteca do Physis 3D (sua ou publicada) que já tenha arquivo, o material e uma observação.</li>
      <li>A equipe aprova ou recusa (sempre com motivo) e muda a situação: pendente, aprovada, imprimindo, pronta.</li>
      <li>Na oficina, a equipe baixa o arquivo da peça e abre <strong>no próprio computador</strong>, no CrealityPrint ou no HALOT.</li></ol>
    <p class="faixa" role="note">Nada é instalado nem chamado pelo navegador: o arquivo só é baixado; quem abre o CrealityPrint ou o HALOT é a pessoa, no computador dela.</p>
    <p class="t2 pq">Impressoras da oficina: [MARCADOR: modelos exatos das impressoras]. Materiais: os perfis de plástico reciclado do Physis 3D (valores "conferir").</p></section>`;
  if (!f || f.carregando) return h + '<p class="t2" role="status">Carregando…</p>';
  if (!f.inst) return h + '<p class="faixa erro" role="alert">Sem ligação com o servidor da InovaSTEM.</p>';
  if (!f.inst.autenticado) return h + `<section class="cartao" aria-labelledby="fi-c-h"><h3 id="fi-c-h">Entre com a sua conta</h3><p>Para pedir impressão, entre com a sua conta ou crie uma em Participar.</p>
    <div class="acoes"><a class="botao" href="/#participar">Entrar ou criar conta</a><button class="botao sec" type="button" id="fi-recarregar" data-lab="fila-recarregar">Já entrei: atualizar</button></div></section>`;
  const pecas = f.pecas && f.pecas.ok ? (f.pecas.pecas || []).filter(p => p.revisoes > 0) : null, mats = (f.minhas && f.minhas.materiais) || [];
  h += `<section class="cartao" aria-labelledby="fi-p-h"><h3 id="fi-p-h">Pedir impressão</h3><form id="fila-form" novalidate>
    ${pecas ? (pecas.length ? `<label for="fi-peca">Peça (id da Biblioteca do Physis 3D)</label><select id="fi-peca" required>${pecas.map(p => `<option value="${+p.id}">Peça ${+p.id}: ${escL(p.nome)}${p.minha ? " (minha)" : ""}</option>`).join("")}</select>`
        : '<p class="t2">Nenhuma peça com arquivo ainda. Em Peças 3D → Biblioteca, crie a peça e envie uma revisão com o arquivo.</p>')
      : `<label for="fi-peca">Número da peça na Biblioteca do Physis 3D</label><input id="fi-peca" type="text" inputmode="numeric" required>`}
    <label for="fi-mat">Material</label><select id="fi-mat"><option value="">A equipe escolhe</option>${mats.map(m => `<option value="${escL(m)}">${escL(nomeMat(m))}</option>`).join("")}</select>
    <label for="fi-obs">Observação (opcional)</label><textarea id="fi-obs" maxlength="1000" rows="3"></textarea>
    <div class="acoes"><button class="botao" type="submit" id="fi-enviar"${pecas && !pecas.length ? " disabled" : ""}>Pedir impressão</button></div></form>
    ${msgHtml("fi-msg", lab.filaMsg)}</section>`;
  const minhas = f.minhas && f.minhas.ok ? f.minhas.itens : [];
  h += `<section class="cartao" aria-labelledby="fi-m-h"><h3 id="fi-m-h">Meus pedidos</h3>${minhas.length ? `<div class="rolagem"><table><caption>Meus pedidos de impressão</caption><thead><tr><th scope="col">Pedido</th><th scope="col">Peça</th><th scope="col">Material</th><th scope="col">Situação</th><th scope="col">Pedido em</th></tr></thead><tbody>
    ${minhas.map(x => `<tr><th scope="row">${+x.id}</th><td>${escL(x.peca_nome || "peça " + x.peca)} (revisão ${+x.revisao})</td><td>${escL(x.material ? nomeMat(x.material) : "a equipe escolhe")}</td><td>${situacao(x)}</td><td>${escL(quando(x.criado))}</td></tr>`).join("")}</tbody></table></div>`
    : '<p class="t2">Você ainda não pediu impressão.</p>'}<div class="acoes"><button class="botao sec" type="button" id="fi-recarregar" data-lab="fila-recarregar">Atualizar</button></div></section>`;
  if (f.equipe) {
    const it = f.equipe.ok ? f.equipe.itens : [];
    h += `<section class="cartao" aria-labelledby="fi-e-h"><h3 id="fi-e-h">Fila da equipe</h3>${f.equipe.ok ? "" : `<p class="faixa erro" role="alert">${escL(f.equipe.erro || "Não deu para ler a fila.")}</p>`}
      ${it.length ? it.map(x => `<div class="item"><h4 id="fe-h-${+x.id}">Pedido ${+x.id}: ${escL(x.peca_nome || "peça " + x.peca)} (revisão ${+x.revisao})</h4>
        <p>${escL(x.nome_publico || "")} · ${escL(x.material ? nomeMat(x.material) : "a equipe escolhe o material")} · situação: <strong>${situacao(x)}</strong> · ${escL(quando(x.criado))}</p>
        ${x.observacao ? `<p class="t2">Observação: ${escL(x.observacao)}</p>` : ""}
        <div class="acoes"><a class="botao sec" href="${escL(x.arquivo_url)}" download aria-describedby="fe-h-${+x.id}">Baixar o arquivo (${escL(x.arquivo_nome)})</a>
          ${x.proximos.map(e => `<button class="botao${e === "recusada" ? " sec" : ""}" type="button" id="fe-${+x.id}-${e}" data-lab="fila-estado" data-id="${+x.id}" data-estado="${e}" aria-describedby="fe-h-${+x.id}">${escL(PASSO_ROTULO[e] || e)}</button>`).join("")}</div>
        ${x.proximos.indexOf("recusada") >= 0 ? `<label for="fe-mot-${+x.id}">Motivo da recusa (pedido ${+x.id})</label><input id="fe-mot-${+x.id}" type="text" maxlength="400">` : ""}</div>`).join("")
        : '<p class="t2">Nenhum pedido na fila.</p>'}</section>`;
  }
  return h;
}

/* ════════ 7. Galeria (peças publicadas, só licenças abertas) ════════ */
async function carregarGaleria() { lab.gal = { carregando: true }; const j = await getJ("/api/publico/3d/pecas"); lab.gal = { j, abertas: {} }; }
function telaGaleria() {
  const g = lab.gal;
  let h = `<h2>Galeria</h2>
  <section class="cartao" aria-labelledby="ga-o-h"><h3 id="ga-o-h">Peças da comunidade</h3>
    <p>Peças publicadas na Biblioteca do Physis 3D, cada uma com a licença escolhida por quem fez e o memorial de desenvolvimento (o que se tentou, o que deu errado e o que mudou).</p>
    <p><strong>Só licenças abertas.</strong> "Todos os direitos reservados" não entra na galeria.${g && g.j && g.j.licencas ? " Licenças aceitas: " + Object.keys(g.j.licencas).map(k => escL(g.j.licencas[k]) + " (" + escL(k) + ")").join("; ") + "." : ""}</p>
    <p>Para enviar: com a sua conta, em Peças 3D → Biblioteca, crie a peça, envie o arquivo e publique com uma licença aberta. Tudo passa pela moderação da equipe antes de aparecer.</p>
    <div class="acoes"><a class="botao sec" href="#pecas">Enviar uma peça (Peças 3D)</a></div></section>`;
  if (!g || g.carregando) return h + '<p class="t2" role="status">Carregando…</p>';
  if (!g.j.ok) return h + '<p class="faixa erro" role="alert">Não deu para ler a galeria agora.</p>';
  const lic = g.j.licencas || {}, pecas = (g.j.pecas || []).filter(p => Object.prototype.hasOwnProperty.call(lic, p.licenca));
  if (!pecas.length) return h + '<p class="t2">Nenhuma peça publicada ainda.</p>';
  return h + pecas.map(p => {
    const ab = g.abertas[p.id];
    const arqs = ab ? (ab.ok ? `<ul class="lista">${(ab.revisoes || []).map(r => `<li>Revisão ${+r.numero}: <a href="/api/publico/3d/arquivo/${escL(r.arquivo_sha256)}" download>baixar ${escL(r.arquivo_nome)}</a>${r.resultado ? " · resultado: " + escL(r.resultado) : ""}</li>`).join("")}</ul>` : `<p class="msg erro">${escL(ab.erro || "Não deu para abrir a peça.")}</p>`) : "";
    return `<section class="cartao" aria-labelledby="ga-${+p.id}-h"><h3 id="ga-${+p.id}-h">${escL(p.nome)}</h3>
      <p class="t2 pq">${escL(p.autor_nome)} · licença: ${escL(p.licenca_nome || p.licenca)} (${escL(p.licenca)}) · ${+p.revisoes} revisões${p.curada ? " · curada pela equipe" : ""}</p>
      ${p.descricao ? `<p>${escL(p.descricao)}</p>` : ""}
      <div class="acoes"><button class="botao sec" type="button" id="ga-ver-${+p.id}" data-lab="gal-ver" data-id="${+p.id}" aria-describedby="ga-${+p.id}-h" aria-expanded="${ab ? "true" : "false"}">Arquivos</button>
        <a class="botao sec" href="/api/publico/3d/pecas/${+p.id}/memorial" aria-describedby="ga-${+p.id}-h">Memorial</a></div>${arqs}</section>`;
  }).join("");
}

/* ════════ desenho, subabas e eventos ════════ */
const TELAS = { arquivo: telaArquivo, lugar: telaLugar, edificacao: telaEdificacao, pecas: telaPecas, simulacao: telaSimulacaoBlocos, escaneamento: telaEscaneamento, fila: telaFila, galeria: telaGaleria };
function desenhar() {
  const alvo = document.getElementById("lab");
  let h = (TELAS[abaLab] || telaArquivo)();
  h = h.replace(/<h1(\s[^>]*)?>/g, "<h2$1>").replace(/<\/h1>/g, "</h2>");      // um título só por tela: o logo
  alvo.innerHTML = recolorir(h);
  alvo.setAttribute("aria-labelledby", "tab-" + abaLab);
  document.getElementById("lab-proj").innerHTML = barraProjeto();
  SUBABAS.forEach(([k]) => { const t = document.getElementById("tab-" + k), sim = k === abaLab; t.setAttribute("aria-selected", String(sim)); t.tabIndex = sim ? 0 : -1; });
  document.title = "InovaSTEM · Modelagem 3D · " + (SUBABAS.filter(s => s[0] === abaLab)[0] || ["", ""])[1];
  desenhado = true;
}
window.__p3dDesenhar = desenhar;
function focar(id) { const e = id && document.getElementById(id); if (e && !e.disabled) e.focus(); else document.getElementById("lab").focus(); }
function aoEntrar() {
  if (abaLab === "fila") carregarFila().then(() => { if (abaLab === "fila") desenhar(); });
  if (abaLab === "galeria" && (!lab.gal || !lab.gal.j || !lab.gal.j.ok)) carregarGaleria().then(() => { if (abaLab === "galeria") desenhar(); });
}
function irLab() {
  const h = decodeURIComponent(location.hash.replace(/^#/, "")), alvo = ANTIGAS[h] || h;
  if (SUBABAS.some(s => s[0] === alvo)) {
    abaLab = alvo;
    if (ANTIGAS[h]) { try { history.replaceState(null, "", "#" + alvo); } catch (e) {} }
  } else if (desenhado) return;                    // "#conteudo" e outras âncoras: a subaba fica
  else abaLab = "arquivo";
  aoEntrar(); desenhar();
}
document.getElementById("lab-abas").addEventListener("keydown", ev => {
  const i = SUBABAS.findIndex(s => s[0] === abaLab), n = SUBABAS.length;
  const novo = ev.key === "ArrowRight" ? (i + 1) % n : ev.key === "ArrowLeft" ? (i - 1 + n) % n : ev.key === "Home" ? 0 : ev.key === "End" ? n - 1 : ev.key === " " ? i : null;
  if (novo == null) return;
  ev.preventDefault();
  const k = SUBABAS[novo][0];
  if (location.hash !== "#" + k) location.hash = "#" + k;
  focar("tab-" + k);
});
async function acao(a, b) {
  const fen = FEN.filter(f => f.id === b.getAttribute("data-fen"))[0];
  if (a === "proj-exportar") { baixar("inovastem-projeto-" + agora().slice(0, 10) + ".json", JSON.stringify(proj, null, 1), "application/json"); lab.proj = { texto: "Arquivo do projeto baixado." }; return; }
  if (a === "proj-limpar") {
    if (!lab.limpar) { lab.limpar = true; lab.proj = { texto: "Clique de novo para confirmar: o projeto deste navegador será apagado (exporte antes, se quiser guardar)." }; return; }
    lab.limpar = false; proj = projetoVazio(); gravarProjeto("Projeto novo começado.", true); return;
  }
  lab.limpar = false;
  if (a === "lugar-navegador") { let g = null; try { g = JSON.parse(localStorage.getItem("physis-geometria-lugar") || "null"); } catch (e) {}
    lab.lugar = g ? importarLugar(g, "Mapeamento (gravado neste navegador)", "") : { texto: "Nenhum lugar gravado pelo Mapeamento neste navegador.", erro: true }; return; }
  if (a === "lugar-tirar") { proj.lugar = null; gravarProjeto("Lugar tirado do projeto."); lab.lugar = { texto: "Lugar tirado do projeto." }; return; }
  if (a === "ed-ler") { lab.ed = { texto: "Lendo…" }; lab.ed = await lerIfcServidor(); return; }
  if (a === "ed-tirar") { proj.edificacao = null; gravarProjeto("Edificação tirada do projeto."); lab.ed = { texto: "Edificação tirada do projeto." }; return; }
  if (a === "peca-guardar") { lab.peca = guardarPeca(); return; }
  if (a === "peca-tirar") { proj.pecas.splice(+b.getAttribute("data-i"), 1); gravarProjeto("Peça tirada do projeto."); lab.peca = { texto: "Peça tirada do projeto." }; return; }
  if (a === "res-tirar") { proj.resultados.splice(+b.getAttribute("data-i"), 1); gravarProjeto("Resultado tirado do projeto."); return; }
  if (a === "sim-rodar" && fen) { rodarFen(fen); return; }
  if (a === "sim-repor" && fen) { const st = estSim(fen).st; st.entrada = null; st.res = null; st.c2 = null; st.aberta = false; st.msg = { texto: "Entrada do exemplo de volta." }; return; }
  if (a === "sim-guardar" && fen) { estSim(fen).st.msg = guardarResultado(fen); return; }
  if (a === "fila-recarregar") { await carregarFila(); return; }
  if (a === "fila-estado") {
    const id = +b.getAttribute("data-id"), estado = b.getAttribute("data-estado"), mot = document.getElementById("fe-mot-" + id);
    const r = await postJ("/api/inovastem/impressao/estado", { id, estado, motivo: mot ? mot.value : "" });
    lab.filaMsg = r.ok ? { texto: "Pedido " + id + ": " + (ESTADOS[r.estado] || r.estado) + "." } : { texto: r.erro || "Não deu para mudar a situação.", erro: true };
    await carregarFila(); return;
  }
  if (a === "gal-ver") { const id = +b.getAttribute("data-id"); if (lab.gal.abertas[id]) { delete lab.gal.abertas[id]; return; }
    const j = lab.gal.abertas[id] = await getJ("/api/publico/3d/pecas/" + id);
    if (j.ok && j.peca) { registrarPasso("galeria", "consultou: " + j.peca.nome); gravarProjeto("Consulta registrada no projeto."); } return; }
  if (a === "arq-malha" && lab.arq && lab.arq.arquivo) { abrirEmPecas(lab.arq.arquivo, "malha enviada"); return "fica"; }
  if (/^arq-(svg|dxf|stl|3mf|enviar)$/.test(a) && lab.arq && lab.arq.r && lab.arq.r.T) {
    const r = lab.arq.r, nome = lab.arq.base;
    if (a === "arq-svg") baixar(nome + "-cad.svg", PhysisImagem3D.svg(r.lacos, r.larg, r.alt), "image/svg+xml");
    if (a === "arq-dxf") baixar(nome + "-cad.dxf", PhysisImagem3D.dxf(r.lacos), "application/dxf");
    if (a === "arq-stl") baixar(nome + ".stl", PHYSIS3D.escreverSTL(r.T, nome), "model/stl");
    if (a === "arq-3mf") baixar(nome + ".3mf", PHYSIS3D.escrever3MF(r.T), "model/3mf");
    if (a === "arq-enviar") { abrirEmPecas(new File([PHYSIS3D.escreverSTL(r.T, nome)], nome + ".stl", { type: "model/stl" }), "modelo da imagem"); return "fica"; }
    lab.arqMsg = { texto: "Arquivo baixado." }; return;
  }
  if (a === "teste-baixar" || a === "teste-abrir") { const tp = testesProntos().filter(x => x.id === b.getAttribute("data-id"))[0]; if (!tp) return;
    if (a === "teste-baixar") { baixar(tp.id + ".stl", PHYSIS3D.escreverSTL(tp.T, tp.id), "model/stl"); return; }
    abrirEmPecas(new File([PHYSIS3D.escreverSTL(tp.T, tp.id)], tp.id + ".stl", { type: "model/stl" }), "peça de teste"); return "fica"; }
}
document.addEventListener("click", ev => {
  const b = ev.target && ev.target.closest ? ev.target.closest("[data-lab]") : null;
  if (!b || b.disabled) return;
  const a = b.getAttribute("data-lab");
  if (a === "sim-ir") { const s = document.getElementById("fen-" + b.getAttribute("data-fen")); if (s) { s.scrollIntoView(); s.focus(); } return; }
  const id = b.id;
  acao(a, b).then(fica => { if (fica === "fica") return; desenhar(); focar(id); });
});
document.addEventListener("change", async ev => {
  const t = ev.target;
  if (!t || !t.getAttribute) return;
  const sel = t.getAttribute("data-lab-sel"), chk = t.getAttribute("data-lab-chk"), arq = t.getAttribute("data-lab-arq");
  if (sel) { const st = estSim(FEN.filter(f => f.id === sel)[0]).st; st.caso = t.value; st.entrada = null; st.res = null; st.c2 = null; st.msg = null; desenhar(); focar(t.id); return; }
  if (chk) { estSim(FEN.filter(f => f.id === chk)[0]).st.usarLugar = t.checked; desenhar(); focar(t.id); return; }
  if (t.getAttribute("data-lab-par") && lab.arq) { lerParametros(); processarArquivo(); desenhar(); focar(t.id); return; }
  if (!arq) return;
  const f = t.files && t.files[0], id = t.id;
  if (arq === "enviar") { lab.arqMsg = { texto: "Lendo…" }; lab.arqMsg = await receberArquivo(f); desenhar(); focar(id); return; }
  let m;
  try {
    const o = await lerArquivoJson(f);
    if (arq === "projeto") { const p = projetoValido(o); if (!p) throw new Error("Este arquivo não é um projeto " + ESQ_PROJETO + ".");
      proj = p; gravarProjeto("Projeto importado: " + f.name + ".", true); lab.limpar = false; }
    else if (arq === "lugar") { m = importarLugar(o, "arquivo", f.name); lab.lugar = m; }
    else if (arq === "ifc-resumo") { m = importarIfc(o, "arquivo do resumo IFC", f.name); lab.ed = m; }
  } catch (e) {
    m = { texto: String(e && e.message || e), erro: true };
    if (arq === "projeto") lab.proj = m; else if (arq === "lugar") lab.lugar = m; else lab.ed = m;
  }
  desenhar(); focar(id);
});
document.addEventListener("submit", async ev => {
  if (ev.target && ev.target.id === "ar-form") { ev.preventDefault(); if (lab.arq) { lerParametros(); processarArquivo(); desenhar(); focar("ar-atualizar"); } return; }
  if (!ev.target || ev.target.id !== "fila-form") return;
  ev.preventDefault();
  const v = id => (document.getElementById(id) || {}).value || "";
  const peca = parseInt(v("fi-peca"), 10);
  if (!(peca > 0)) { lab.filaMsg = { texto: "Escolha a peça.", erro: true }; desenhar(); focar("fi-peca"); return; }
  const r = await postJ("/api/inovastem/impressao", { peca, material: v("fi-mat"), observacao: v("fi-obs") });
  lab.filaMsg = r.ok ? { texto: "Pedido " + r.id + " enviado: pendente, esperando a equipe." } : { texto: r.erro || "Não deu para pedir agora.", erro: true };
  if (r.ok) { registrarPasso("fila", "pedido " + r.id + " (peça " + peca + ")"); gravarProjeto("Pedido registrado no projeto."); }
  await carregarFila(); desenhar(); focar(r.ok ? "fi-msg" : "fi-peca");
});
proj = lerProjeto();
window.addEventListener("hashchange", irLab);
irLab();
"""


def ler(p: Path) -> str:
    return p.read_text(encoding="utf-8").replace("\r\n", "\n")


def montar() -> str:
    site = ler(WEB / "inovastem.html")
    estilo = re.search(r"<style>\n(.*?)</style>", site, re.S).group(1)
    logo = re.search(r'(<h1 class="logo">.*?</h1>)', site, re.S).group(1)
    pref = ler(SIS / "physis-preferencias.js")
    prem3d = json.dumps(json.loads(ler(SIS / "physis-3d-premissas.json")), ensure_ascii=False)
    blocos = "\n".join(f'<script id="{i}">\n{ler(a)}</script>' for i, a in BLOCOS)
    casca = (CASCA_JS.replace("__CORES__", json.dumps(CORES)).replace("__ESQ_PROJETO__", ESQUEMA_PROJETO)
             .replace("__SUBABAS__", json.dumps([list(s) for s in SUBABAS], ensure_ascii=False)))
    abas = "\n    ".join(f'<a role="tab" id="tab-{k}" href="#{k}" aria-controls="lab" aria-selected="{"true" if i == 0 else "false"}" '
                         f'tabindex="{0 if i == 0 else -1}">{i + 1}. {n}</a>' for i, (k, n) in enumerate(SUBABAS))
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>InovaSTEM · Modelagem 3D</title>
<meta name="description" content="Modelagem 3D (Physis 3D) da InovaSTEM, aberta a qualquer assunto: enviar arquivo (imagem para CAD 2D e 3D), lugar (GIS), edificação (BIM), peças 3D, simulação por fenômeno, escaneamento, fila de impressão e galeria, com um projeto comum, no navegador. Versão beta.">
<!-- GERADO por ferramentas/montar_lab_inovastem.py. Não edite aqui: edite os originais e rode o gerador. -->
<script>(function(){{var r=document.documentElement,t=null,p=null;try{{p=JSON.parse(localStorage.getItem("physis-pref")||"null");t=p&&p.tema||localStorage.getItem("physis-pref-tema");}}catch(e){{}}if(t!=="claro"&&t!=="escuro"){{try{{t=matchMedia("(prefers-color-scheme: dark)").matches?"escuro":"claro";}}catch(e){{t="claro";}}}}r.setAttribute("data-tema",t);}})();</script>
<style>
{estilo}{CASCA_CSS}</style>
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
        <li><a href="/#forum">Fórum</a></li><li><a href="/#modelagem" aria-current="page">Modelagem 3D</a></li>
        <li><a href="/#hackathon">Hackathon</a></li><li><a href="/#materiais">Materiais</a></li></ul></nav>
      <a class="botao" href="/#participar">Inscreva-se</a>
    </div>
    <p class="sub">Modelagem 3D (Physis 3D) · roda no seu navegador <span class="beta">versão beta</span></p>
  </div>
</header>
<main id="conteudo" class="in" tabindex="-1">
  <h2 class="lab-intro">Modelagem 3D (Physis 3D)</h2>
  <p>A bancada de desenvolvimento da InovaSTEM, aberta a modelagens de qualquer assunto: oito subabas que leem e gravam um projeto comum, num fluxo do arquivo até a galeria.</p>
  <section class="lab-projeto" id="lab-proj" aria-label="Projeto comum"></section>
  <div class="lab-abas" id="lab-abas" role="tablist" aria-label="Subabas da Modelagem 3D">
    {abas}
  </div>
  <p class="faixa" role="note">Em desenvolvimento (Fase 1). Pré-dimensionamento para aprender e testar ideias: não aprova projeto, não substitui norma nem ensaio. Os exemplos usam dados fictícios. O que você abre ou envia aqui fica no seu computador; só vai para o servidor da InovaSTEM quando você pede (ler um IFC, pedir impressão, enviar peça à Biblioteca).</p>
  <div id="lab" role="tabpanel" tabindex="0" aria-labelledby="tab-arquivo"></div>
</main>
<footer><div class="in"><p><strong>InovaSTEM · uma iniciativa PHYSIS</strong> · Physis Engineering · CNPJ [MARCADOR] · Petrópolis (RJ) · Contato: [MARCADOR]</p>
  <p>Versão beta: termos e aviso de privacidade em revisão jurídica.</p>
  <ul><li><a href="/#termos">Termos de uso (beta)</a></li><li><a href="/#privacidade">Privacidade (beta)</a></li><li><a href="/acessibilidade">Acessibilidade</a></li></ul></div></footer>
<script>const ui = {{}};</script>
{blocos}
<script id="lab-inovastem">
{casca}</script>
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
