/* physis-evidencias.js — Certificação assistida: evidências automáticas para cada critério da aba Certificações.
   Mapa (dados): sistema/physis-evidencias.json, embutido na plataforma como <script type="application/json"
   id="base-evidencias"> (ferramentas/embutir_bases.py) ou posto em window.EVIDENCIAS_MAPA.
   Base de critérios: CERTS da plataforma (ou <script id="base-certificacoes">).
   Contrato com a plataforma:
     evidenciasPara(certId, dados?) -> { ok, cert, criterios: { id: { status, evidencias:[{status, valor, fonte, data, tela}], sugestao } }, resumo }
         status: "atendido" | "parcial" | "sem_evidencia"; sem 'dados', lê o que a plataforma guarda (coletar()).
     telaEvidencias(certId) -> HTML da parte "Evidências automáticas" (sem h1; vai dentro de Certificações).
     window.EVIDENCIAS = { FONTES, num, norm, palavrasDaEvidencia, avaliarCriterio, coletar, carregarServidor, ... }
   Espelho em Python: physis-hub/physis_hub/evidencias.py (regra 4: mudou aqui, muda lá; test_evidencias.py).
   Esgoto e biogás: ebAtual() da plataforma (ou as chaves physis-calc-esgoto e physis-calc-biogas); materiais: physis-calc-materiais
   com a avaliação da NBR 15575 lida da base embutida base-materiais (sistema/physis-materiais.json).
   Globais da plataforma usadas se existirem: perfilLer, calcLer, carbLer, rcLer, rcResumo, sbnLer, phLer, gLer, ebAtual,
   CERTS, esc, irPara, desenhar, ui. Sem internet: só /api/evidencias/* do próprio hub, quando houver servidor. */
(function (global) {
"use strict";

const ORDEM = { sem_evidencia:0, parcial:1, atendido:2 };
const NOME_STATUS = { atendido:"Atendido", parcial:"Parcial", sem_evidencia:"Sem evidência" };
const CHAVE_ANEXOS = "physis-evidencias-anexos";

/* ── utilidades (iguais no Python) ── */
function num(v){
  if (v == null || typeof v === "boolean") return null;
  if (typeof v === "number") return isFinite(v) ? v : null;
  let s = String(v).trim(); if (!s) return null;
  if (s.indexOf(",") >= 0) s = s.replace(/\./g, "").replace(",", ".");
  if (!/^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/.test(s)) return null;
  const x = Number(s); return isFinite(x) ? x : null;
}
const norm = s => String(s == null ? "" : s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim().replace(/ +/g, " ");
function palavrasDaEvidencia(texto){
  const t = String(texto == null ? "" : texto).replace(/\b[A-Z]{2,4}-[A-Z]{2,4}-\d+\b/g, " "), out = [];
  t.split(/[;,/+()]| e | ou /).forEach(p => { const n = norm(p); if (n.length >= 8 && out.indexOf(n) < 0) out.push(n); });
  return out;
}
const R = (status, valor, data) => ({ status, valor, data: data || null });
const pct = x => Math.floor(x * 100 + 0.5);
const virg = s => s.replace(".", ",");
const fmtG = x => String(Number(x));
const fix = (x, c) => (Math.floor(x * Math.pow(10, c) + 0.5) / Math.pow(10, c)).toFixed(c);    /* arredonda como o Python (espelho) */
function meses(d, campo){ return ((d.perfil || {}).historico || []).filter(x => x && typeof x === "object" && num(x[campo]) != null).sort((a, b) => String(a.mes || "").localeCompare(String(b.mes || ""))); }

/* ── fontes: uma função por fonte (espelho de FONTES em evidencias.py) ── */
const FONTES = {
  agua_contas(d, p){ const h = meses(d, "m3"); if (!h.length) return null;
    return R(h.length >= (p.min_meses || 12) ? "atendido" : "parcial", `${h.length} meses de consumo de água nas contas`, h[h.length - 1].mes); },
  energia_hist(d, p){ const h = meses(d, "kwh"); if (!h.length) return null;
    return R(h.length >= (p.min_meses || 12) ? "atendido" : "parcial", `${h.length} meses de consumo de energia nas contas`, h[h.length - 1].mes); },
  medidor(d, p){ const g = p.grandeza || "agua", m = ((d.servidor || {}).medidores || {})[g] || {}, dias = Math.trunc(num(m.dias) || 0); if (!dias) return null;
    const nome = { agua:"água", energia:"energia", nivel:"nível" }[g] || g;
    return R(dias >= (p.min_dias || 30) ? "atendido" : "parcial", `${dias} dias de ${nome} medidos pelo hub`, m.ultimo); },
  agua_cisterna(d, p){ const m = ((d.servidor || {}).medidores || {}).nivel || {}, dias = Math.trunc(num(m.dias) || 0), vol = num(((d.calc || {}).agua || {}).cisterna_m3);
    if (dias >= (p.min_dias || 30)) return R("atendido", `Cisterna em operação: ${dias} dias de nível medido pelo hub`, m.ultimo);
    if (vol && vol > 0) return R("parcial", virg(`Cisterna dimensionada: ${fmtG(vol)} m³ (falta medição de operação)`));
    if (dias) return R("parcial", `${dias} dias de nível medido pelo hub`, m.ultimo);
    return null; },
  solar(d, p){ const c = d.carbono || {}, s = (d.calc || {}).solar || {}, g = num(c.solar_kwh), cons = num(c.kwh);
    if (g && g > 0){ const cob = cons != null && g + cons > 0 ? g / (g + cons) : null, min = p.min_cobertura;
      const st = min != null && cob != null ? (cob >= min ? "atendido" : "parcial") : "atendido";
      return R(st, `Geração solar de ${fix(g, 0)} kWh/ano` + (cob != null ? ` (${pct(cob)}% do consumo)` : "")); }
    if ((num(s.kwp) || 0) > 0 || (num(s.consumo) || 0) > 0) return R("parcial", "Sistema solar dimensionado na aba Energia solar (falta a geração medida)");
    return null; },
  enpi(d, p){ const mods = ((d.servidor || {}).modelos_consumo || []).filter(m => String(m.nome || "").indexOf("energia") >= 0);
    if (mods.length){ const m = mods.reduce((a, b) => (num(b.n_amostras) || 0) > (num(a.n_amostras) || 0) ? b : a);
      return R("atendido", `Linha de base de energia ajustada por clima e produção (modelo do hub, ${Math.trunc(num(m.n_amostras) || 0)} dias)`, m.treinado_em); }
    const h = meses(d, "kwh"); if (h.length < 12) return null;
    const area = num(((d.perfil || {}).c || {}).area_construida), soma = h.slice(-12).reduce((s, x) => s + num(x.kwh), 0);
    if (area && area > 0) return R("parcial", virg(`Indicador: ${fix(soma / area, 1)} kWh/m² por ano (12 meses de contas)`), h[h.length - 1].mes);
    return R("parcial", "12 meses de contas de luz; falta a área construída para normalizar o indicador", h[h.length - 1].mes); },
  residuos_desvio(d, p){ const r = d.residuos || {}, x = num(r.pct);
    if (x == null) return num(r.n) ? R("parcial", `${Math.trunc(num(r.n) || 0)} resíduos no plano; falta a quantidade para o desvio`) : null;
    const meta = p.meta != null ? p.meta : 0.5;
    return R(x >= meta ? "atendido" : "parcial", `${pct(x)}% desviado do aterro (meta ${pct(meta)}%)`, r.data); },
  residuos_plano(d, p){ const r = d.residuos || {}, n = Math.trunc(num(r.n) || 0), com = Math.trunc(num(r.com_rota) || 0); if (!n) return null;
    return R(com >= n ? "atendido" : "parcial", `${com} de ${n} resíduos com rota definida`, r.data); },
  carbono_inventario(d, p){ const c = d.carbono || {}, e2 = num(c.kwh) != null, e1 = ["diesel", "glp", "gn"].some(k => num(c[k]) != null);
    if (!e1 && !e2) return null;
    return R(e1 && e2 ? "atendido" : "parcial", e1 && e2 ? "Inventário com escopos 1 e 2" : e2 ? "Inventário só com escopo 2 (eletricidade)" : "Inventário só com escopo 1 (combustíveis)"); },
  sbn_plano(d, p){ const pl = ((d.sbn || {}).plano || []).filter(x => x && typeof x === "object"); if (!pl.length) return null;
    return R(pl.length >= (p.min_especies || 1) ? "atendido" : "parcial", `${pl.length} espécies no plano de plantio`); },
  acessibilidade(d, p){ if (!d.pref || typeof d.pref !== "object" || Array.isArray(d.pref)) return null;
    return R("parcial", "Plataforma com recursos de acessibilidade digital (LBI 13.146/2015, art. 63); a acessibilidade do espaço (NBR 9050) pede evidência própria"); },
  calibracao(d, p){ const cal = (d.calibracoes || []).filter(c => c && typeof c === "object" && c.data), sens = (d.servidor || {}).sensores || [];
    if (!cal.length && !sens.length) return null;
    if (!cal.length) return R("parcial", `${sens.length} sensores no hub, sem registro de calibração`);
    const hoje = d.hoje || "", ult = {};
    cal.forEach(c => { const k = String(c.ponto || "?"); if (!ult[k] || String(c.data) > String(ult[k].data)) ult[k] = c; });
    const ks = Object.keys(ult), venc = ks.filter(k => ult[k].validade && String(ult[k].validade) < hoje), semVal = ks.filter(k => !ult[k].validade);
    const data = ks.map(k => String(ult[k].data)).sort().pop(), txt = `${ks.length} pontos com calibração registrada`;
    if (venc.length) return R("parcial", txt + `; ${venc.length} vencida(s)`, data);
    if (semVal.length) return R("parcial", txt + "; validade não informada em " + semVal.length, data);
    return R("atendido", txt + ", todas na validade", data); },
  documentos(d, p, crit){ let pal = (p.palavras || []).map(norm).filter(Boolean);
    if (p.da_evidencia) pal = pal.concat(palavrasDaEvidencia((crit || {}).evidencia));
    if (!pal.length) return null;
    const arqs = ((d.servidor || {}).arquivos || []).concat(d.arquivos || []).slice().sort((a, b) => String(b.data || "").localeCompare(String(a.data || "")));
    for (const a of arqs){ const n = norm(a.nome); if (pal.some(w => n.indexOf(w) >= 0)) return R("atendido", "Documento: " + String(a.nome).slice(0, 120), a.data); }
    return null; },
  perfil(d){ const pf = d.perfil || {}; return pf.tipo && pf.nivel ? R("parcial", "Início preenchido (perfil e lugar)") : null; },
  riscos(d){ const ri = (d.calc || {}).riscos || {}; return Object.keys(ri).some(k => (num(ri[k]) || 0) > 0) ? R("parcial", "Matriz de riscos preenchida na Resiliência climática") : null; },
  risco_municipal(d){ const r = (d.municipio || (d.servidor || {}).municipio || {}).risco_lugar;
    if (["baixo", "medio", "alto", "muito_alto"].indexOf(r) < 0) return null;
    const nome = { baixo:"baixo (R1)", medio:"médio (R2)", alto:"alto (R3)", muito_alto:"muito alto (R4)" }[r], st = { baixo:"atendido", medio:"parcial" }[r] || "sem_evidencia";
    return R(st, `Bairro do lugar com risco ${nome} no painel municipal` + (r === "baixo" ? "" : ": pede laudo e consulta à Defesa Civil")); },
  custos(d){ const inv = ((d.gestao || {}).compras || []).filter(c => c && c.cat === "Investimento");
    if (inv.length) return R("parcial", `${inv.length} investimento(s) com retorno em Gestão → Compras e investimentos`);
    if (num(((d.calc || {}).solar || {}).custo_kwp)) return R("parcial", "Custo e retorno do sistema solar calculados");
    return null; },
  /* Economia circular · Esgoto e biogás (Planejador, SustainKit ou estimativa da plataforma): projeto, ainda sem medição */
  agua_reuso(d){ const e = d.esgoto || {}, r = num(e.reuso_m3_dia); if (!(r > 0)) return null; const f = String(e.fonte || "");
    return R("parcial", "Reúso de efluente tratado planejado: " + virg(fix(r, 2)) + " m³/dia" + (f ? " (" + f + ")" : ""), e.atualizado); },
  biogas(d){ const b = d.biogas || {}, g = num(b.biogas_m3_dia); if (!(g > 0)) return null; const v = num(b.biodigestor_m3), f = String(b.fonte || "");
    return R("parcial", "Biodigestor dimensionado: " + virg(fix(g, 2)) + " m³/dia de biogás" + (v ? ", " + virg(fix(v, 1)) + " m³" : "") + (f ? " (" + f + ")" : ""), b.atualizado); },
  /* materiais da obra (chave physis-calc-materiais): carbono incorporado ou, com modo "envoltoria", NBR 15575 (procedimento simplificado) */
  materiais(d, p){ const m = d.materiais || {}, comps = (m.composicoes || []).filter(c => c && typeof c === "object"); if (!comps.length) return null;
    if (p.modo === "envoltoria"){ const av = comps.filter(c => ["atende", "parcial", "nao"].indexOf(c.nbr15575) >= 0); if (!av.length) return null;
      const ok = av.filter(c => c.nbr15575 === "atende").length;
      return R(ok === av.length ? "atendido" : "parcial", `${ok} de ${av.length} composições atendem à NBR 15575 (procedimento simplificado` + (m.zona ? ", zona " + m.zona : "") + ")", m.atualizado); }
    const com = comps.filter(c => num(c.kgco2e_m2) != null && (num(c.area_m2) || 0) > 0);
    if (!com.length) return R("parcial", `${comps.length} composições escolhidas, sem carbono incorporado por m²`, m.atualizado);
    const t = com.reduce((s, c) => s + num(c.area_m2) * num(c.kgco2e_m2), 0) / 1000;
    return R("parcial", "Carbono incorporado das composições: " + virg(fix(t, 1)) + ` tCO₂e (${com.length} de ${comps.length} com valor por m²)`, m.atualizado); }
};

/* ── mapa e base de critérios ── */
let mapaCache = null;
function mapa(){
  if (mapaCache) return mapaCache;
  if (global.EVIDENCIAS_MAPA) return (mapaCache = global.EVIDENCIAS_MAPA);
  try { const n = global.document && global.document.getElementById("base-evidencias"); if (n) mapaCache = JSON.parse(n.textContent); } catch (e){}
  return mapaCache;
}
function certs(){
  if (typeof CERTS !== "undefined" && Array.isArray(CERTS)) return CERTS;     /* eslint-disable-line no-undef */
  try { const n = global.document && global.document.getElementById("base-certificacoes"); if (n) return JSON.parse(n.textContent).certificacoes || []; } catch (e){}
  return [];
}

/* ── motor ── */
function regrasDoCriterio(crit, m){
  let regras = ((m.por_criterio || {})[crit.id] || []).slice();
  if (!regras.length && crit.auto) regras = ((m.por_auto || {})[crit.auto] || []).slice();
  return regras.concat(m.regra_geral || []);
}
function anexosDe(d, id){
  const hoje = d.hoje || "";
  return ((d.servidor || {}).anexos || []).concat(d.anexos || []).filter(a => a && a.criterio === id).map(a => {
    const venc = !!a.validade && String(a.validade) < hoje;
    return { status: venc ? "parcial" : "atendido", fonte:"anexo", tela:"certificacoes", data: a.data || null,
      valor: String(a.nome || "Evidência").slice(0, 160) + (venc ? " (vencida em " + a.validade + ")" : "") + (a.responsavel ? " · " + String(a.responsavel).slice(0, 80) : "") }; });
}
function avaliarCriterio(crit, d, m){
  m = m || mapa() || {}; const fontes = m.fontes || {}, evid = [];
  regrasDoCriterio(crit, m).forEach(regra => { const fn = FONTES[regra.fonte]; if (!fn) return; let r = fn(d, regra, crit); if (!r) return;
    if (regra.teto in ORDEM && ORDEM[r.status] > ORDEM[regra.teto]) r = Object.assign({}, r, { status: regra.teto });
    evid.push(Object.assign({}, r, { fonte: regra.fonte, tela: (fontes[regra.fonte] || {}).tela || null })); });
  const todas = evid.concat(anexosDe(d, crit.id)), vistos = {}, unicos = todas.filter(e => { const k = e.fonte + "|" + e.valor; if (vistos[k]) return false; vistos[k] = 1; return true; });
  unicos.sort((a, b) => ORDEM[b.status] - ORDEM[a.status]);
  const status = unicos.length ? unicos[0].status : "sem_evidencia";
  return { criterio: crit.id, status, evidencias: unicos, sugestao: { atendido:"atende", parcial:"parcial" }[status] || null };
}
function evidenciasPara(certId, dados){
  const m = mapa(); if (!m) return { ok:false, erro:"mapa de evidências não embutido (base-evidencias)" };
  const cert = certs().find(c => c.id === certId); if (!cert) return { ok:false, erro:"certificação desconhecida" };
  const d = dados || coletar(), res = {}, resumo = { atendido:0, parcial:0, sem_evidencia:0, total:0 };
  cert.grupos.forEach(g => g.criterios.forEach(k => { const r = avaliarCriterio(k, d, m); res[k.id] = r; resumo[r.status]++; resumo.total++; }));
  return { ok:true, cert: certId, criterios: res, resumo };
}

/* ── o que a plataforma guarda (localStorage) + o que veio do servidor ── */
function lerJSON(k, padrao){ try { const v = JSON.parse(global.localStorage.getItem(k) || "null"); return v == null ? padrao : v; } catch (e){ return padrao; } }
/* funções da plataforma: algumas são "const" (não ficam em window), então cada uma é lida pelo nome, uma a uma
   (a política de segurança da plataforma não permite avaliar texto como código) */
/* eslint-disable no-undef */
const PLAT = {
  perfilLer: () => typeof perfilLer === "function" ? perfilLer : null, calcLer: () => typeof calcLer === "function" ? calcLer : null,
  carbLer: () => typeof carbLer === "function" ? carbLer : null, rcLer: () => typeof rcLer === "function" ? rcLer : null,
  rcResumo: () => typeof rcResumo === "function" ? rcResumo : null, sbnLer: () => typeof sbnLer === "function" ? sbnLer : null,
  phLer: () => typeof phLer === "function" ? phLer : null, gLer: () => typeof gLer === "function" ? gLer : null,
  irPara: () => typeof irPara === "function" ? irPara : null, desenhar: () => typeof desenhar === "function" ? desenhar : null,
  ebAtual: () => typeof ebAtual === "function" ? ebAtual : null };
/* eslint-enable no-undef */
const fn = nome => { try { return (PLAT[nome] && PLAT[nome]()) || (typeof global[nome] === "function" ? global[nome] : null); } catch (e){ return null; } };
function hojeLocal(){ const d = new Date(), z = n => String(n).padStart(2, "0"); return d.getFullYear() + "-" + z(d.getMonth() + 1) + "-" + z(d.getDate()); }
/* composições escolhidas + avaliação da NBR 15575 (procedimento simplificado) da base de materiais embutida (base-materiais),
   pela zona bioclimática do registro: "atende" (todas as absortâncias), "parcial" (só algumas) ou "nao" */
function materiaisAvaliados(m){ m = m && typeof m === "object" ? m : {}; const comps = Array.isArray(m.composicoes) ? m.composicoes : []; let base = {};
  try { const n = global.document && global.document.getElementById("base-materiais"); if (n) (JSON.parse(n.textContent).composicoes || []).forEach(c => { base[c.id] = c; }); } catch (e){}
  const zona = String(m.zona == null ? "" : m.zona).replace(/\D/g, "");
  return Object.assign({}, m, { composicoes: comps.filter(c => c && typeof c === "object").map(c => { const b = base[c.id], av = b && b.avaliacao && b.avaliacao.nbr15575_simplificado ? b.avaliacao.nbr15575_simplificado[zona] : null;
    const vs = av ? Object.keys(av).map(k => av[k]).filter(x => typeof x === "boolean") : [];
    return Object.assign({}, c, { nbr15575: c.nbr15575 || (vs.length ? (vs.every(Boolean) ? "atende" : vs.some(Boolean) ? "parcial" : "nao") : null) }); }) }); }
function coletar(){
  const ebAtual = fn("ebAtual"); let eb = null; try { eb = ebAtual ? ebAtual() : null; } catch (e){}
  const perfilLer = fn("perfilLer"), calcLer = fn("calcLer"), carbLer = fn("carbLer"), rcLer = fn("rcLer"), rcResumo = fn("rcResumo"), sbnLer = fn("sbnLer"), phLer = fn("phLer"), gLer = fn("gLer");
  const calc = k => calcLer ? calcLer(k) : lerJSON("physis-calc-" + k, {});
  const lista = rcLer ? rcLer() : lerJSON("physis-residuos-plano", []), res = Array.isArray(lista) ? lista : [];
  let p = null; if (rcResumo && res.length){ try { p = rcResumo(res).pct; } catch (e){} }
  const cal = (phLer ? phLer() : lerJSON("physis-ph-calibracoes", [])) || [];
  return { hoje: hojeLocal(),
    perfil: perfilLer ? perfilLer() : lerJSON("physis-perfil", {}),
    calc: { solar: calc("solar"), riscos: calc("riscos"), agua: calc("agua") },
    esgoto: eb ? (eb.esgoto || {}) : calc("esgoto"), biogas: eb ? (eb.biogas || {}) : calc("biogas"), materiais: materiaisAvaliados(calc("materiais")),
    carbono: carbLer ? carbLer() : lerJSON("physis-carbono", {}),
    residuos: { n: res.length, com_rota: res.filter(r => r && r.rota).length, pct: p },
    sbn: sbnLer ? sbnLer() : lerJSON("physis-sbn", {}),
    pref: lerJSON("physis-pref", null),
    calibracoes: (Array.isArray(cal) ? cal : []).map(c => ({ ponto: c.ponto, data: c.data, validade: c.validade || null })),
    gestao: gLer ? gLer() : lerJSON("physis-gestao-cliente", {}),
    anexos: lerJSON(CHAVE_ANEXOS, []),
    arquivos: [],
    servidor: servidor || {} };
}

/* ── servidor (opcional): medidores, sensores, modelos, arquivos da Gestão e anexos ── */
let servidor = null, pedido = null, csrf = null;
const temServidor = () => !!(global.location && /^https?:$/.test(global.location.protocol));
function carregarServidor(forcar){
  if (!temServidor() || (pedido && !forcar)) return pedido || Promise.resolve(null);
  pedido = fetch("/api/evidencias/dados", { credentials:"same-origin" }).then(r => r.ok ? r.json() : null).then(j => { servidor = j && j.ok ? j.dados : null; redesenhar(); return servidor; }).catch(() => null);
  return pedido;
}
async function postar(url, corpo){
  if (!temServidor()) return null;
  if (csrf == null){ try { csrf = (await fetch("/api/instancia", { credentials:"same-origin" }).then(r => r.json())).csrf || ""; } catch (e){ csrf = ""; } }
  const h = { "Content-Type":"application/json" }; if (csrf) h["X-Physis-CSRF"] = csrf;
  const r = await fetch(url, { method:"POST", headers:h, body: JSON.stringify(corpo), credentials:"same-origin" });
  return r.ok ? r.json() : null;
}

/* ── tela ── */
const escH = s => (typeof esc === "function" ? esc : (x => String(x == null ? "" : x).replace(/[&<>"']/g, c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]))))(s);   /* eslint-disable-line no-undef */
const SELO = { atendido:"ok", parcial:"at", sem_evidencia:"" };
let aberto = {}, msgTela = "";
function telaEvidencias(certId){
  if (temServidor() && !pedido) carregarServidor();
  const r = evidenciasPara(certId), m = mapa() || {}, fontes = m.fontes || {}, id = String(certId).replace(/[^\w-]/g, "_");
  if (!r.ok) return `<section class="cartao" id="evid-${id}"><h2>Evidências automáticas</h2><p class="t2">${escH(r.erro)}</p></section>`;
  const cert = certs().find(c => c.id === certId), crits = []; cert.grupos.forEach(g => g.criterios.forEach(k => crits.push(k)));
  const linhas = crits.map(k => { const e = r.criterios[k.id], top = e.evidencias[0], mais = e.evidencias.slice(1);
    return `<tr><th scope="row">${escH(k.texto)}</th><td><span class="selo ${SELO[e.status]}">${NOME_STATUS[e.status]}</span></td>
      <td>${top ? escH(top.valor) : '<span class="t2">—</span>'}${mais.length ? `<details><summary>Mais ${mais.length}</summary><ul>${mais.map(x => `<li>${escH(x.valor)} <span class="t2 pq">(${escH((fontes[x.fonte] || {}).nome || x.fonte)})</span></li>`).join("")}</ul></details>` : ""}</td>
      <td>${top ? escH((fontes[top.fonte] || {}).nome || top.fonte) : ""}</td><td>${top && top.data ? escH(top.data) : ""}</td>
      <td>${top && top.tela && top.tela !== "certificacoes" ? `<button type="button" data-ev-ir="${escH(top.tela)}" aria-label="Abrir ${escH((fontes[top.fonte] || {}).nome || top.fonte)} (${escH(k.id)})">Abrir</button>` : ""}</td></tr>`; }).join("");
  const anex = (servidor && servidor.anexos || []).filter(a => a.cert === certId).map(a => Object.assign({ servidor:true }, a)).concat(lerJSON(CHAVE_ANEXOS, []).filter(a => a.cert === certId));
  const opcoes = crits.map(k => `<option value="${escH(k.id)}">${escH(k.texto.slice(0, 90))}</option>`).join("");
  const form = `<form data-ev-form="${escH(certId)}" class="pq" style="display:grid;gap:8px;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));margin-top:8px">
      <div style="grid-column:1/-1"><label for="ev-c-${id}">Critério</label><select id="ev-c-${id}" name="criterio" required style="width:100%">${opcoes}</select></div>
      <div><label for="ev-n-${id}">Nome do documento</label><input id="ev-n-${id}" name="nome" type="text" maxlength="160" required style="width:100%"></div>
      <div><label for="ev-d-${id}">Data</label><input id="ev-d-${id}" name="data" type="date" required value="${hojeLocal()}" style="width:100%"></div>
      <div><label for="ev-v-${id}">Validade (se houver)</label><input id="ev-v-${id}" name="validade" type="date" style="width:100%"></div>
      <div><label for="ev-r-${id}">Responsável</label><input id="ev-r-${id}" name="responsavel" type="text" maxlength="80" style="width:100%"></div>
      <div style="grid-column:1/-1"><label for="ev-o-${id}">Observação</label><input id="ev-o-${id}" name="obs" type="text" maxlength="500" style="width:100%"></div>
      <div><button type="submit">Anexar evidência</button></div></form>
    <p class="t2 pq">Guarda só os dados do documento (nome, data, validade e responsável). O arquivo fica na Gestão ou com o responsável; não ponha dado pessoal de terceiros na observação.</p>`;
  const lista = anex.length ? `<ul>${anex.map((a, i) => `<li>${escH(a.nome)} · ${escH(a.data)}${a.validade ? " · validade " + escH(a.validade) : ""} <span class="t2 pq">(${escH(a.criterio)}${a.servidor ? ", no servidor" : ", neste aparelho"})</span> <button type="button" data-ev-remover="${a.servidor ? "s" + a.id : "l" + i}" data-ev-cert="${escH(certId)}" aria-label="Remover ${escH(a.nome)}">Remover</button></li>`).join("")}</ul>` : `<p class="t2">Nenhuma evidência anexada.</p>`;
  const s = r.resumo;
  return `<section class="cartao" id="evid-${id}" aria-labelledby="h-evid-${id}"><h2 id="h-evid-${id}">Evidências automáticas</h2>
    <p><span class="selo ok">${s.atendido} atendidos</span> <span class="selo at">${s.parcial} parciais</span> <span class="selo">${s.sem_evidencia} sem evidência</span> <span class="t2">de ${s.total} critérios</span></p>
    <p class="t2 pq">O sistema procura evidência no que já está guardado (contas, medidores, planos, inventários, documentos). É apoio à auditoria: confira cada item; a decisão final é da certificadora.${temServidor() ? (servidor ? "" : " Dados do servidor ainda não carregados.") : " Sem servidor: só os dados deste aparelho."}</p>
    ${msgTela ? `<p role="status" class="pq">${escH(msgTela)}</p>` : ""}
    <div class="rolagem"><table><caption class="so-leitor">Evidências por critério de ${escH(cert.nome)}</caption><thead><tr><th scope="col">Critério</th><th scope="col">Situação</th><th scope="col">Evidência</th><th scope="col">Fonte</th><th scope="col">Data</th><th scope="col">Conferir</th></tr></thead><tbody>${linhas}</tbody></table></div>
    <p><button type="button" data-ev-exportar="${escH(certId)}">Exportar evidências (CSV)</button></p>
    <details ${aberto[certId] ? "open" : ""} data-ev-det="${escH(certId)}"><summary>Anexar evidência</summary>${form}<h3 class="t3">Evidências anexadas</h3>${lista}</details></section>`;
}
function redesenhar(){
  const des = fn("desenhar");
  if (des){ try { des(false); return; } catch (e){} }
  if (!global.document) return;
  global.document.querySelectorAll("section[id^='evid-']").forEach(n => { const c = n.querySelector("[data-ev-exportar]"); if (c) n.outerHTML = telaEvidencias(c.dataset.evExportar); });
}
function csvDe(certId){
  const r = evidenciasPara(certId), m = mapa() || {}, cert = certs().find(c => c.id === certId), q = v => '"' + String(v == null ? "" : v).replace(/"/g, '""') + '"', L = [["criterio", "texto", "situacao", "evidencia", "fonte", "data"].join(";")];
  cert.grupos.forEach(g => g.criterios.forEach(k => { const e = r.criterios[k.id]; (e.evidencias.length ? e.evidencias : [{}]).forEach(x => L.push([k.id, k.texto, NOME_STATUS[e.status], x.valor || "", ((m.fontes || {})[x.fonte] || {}).nome || x.fonte || "", x.data || ""].map(q).join(";"))); }));
  return "﻿" + L.join("\r\n");
}
if (global.document){
  global.document.addEventListener("click", async ev => {
    const b = ev.target.closest && ev.target.closest("button"); if (!b) return;
    if (b.dataset.evIr){ const ir = fn("irPara"); if (ir) ir(b.dataset.evIr); else global.location.hash = b.dataset.evIr; }
    else if (b.dataset.evExportar){ const a = global.document.createElement("a"); a.href = URL.createObjectURL(new Blob([csvDe(b.dataset.evExportar)], { type:"text/csv;charset=utf-8" })); a.download = "evidencias-" + b.dataset.evExportar + ".csv"; global.document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000); }
    else if (b.dataset.evRemover){ const v = b.dataset.evRemover, cert = b.dataset.evCert; aberto[cert] = true;
      if (v[0] === "s"){ const r = await postar("/api/evidencias/anexo/remover", { id: Number(v.slice(1)) }); msgTela = r && r.ok ? "Evidência removida." : "Não foi possível remover no servidor."; await carregarServidor(true); }
      else { const l = lerJSON(CHAVE_ANEXOS, []), meus = l.filter(a => a.cert === cert), alvo = meus[Number(v.slice(1))]; try { global.localStorage.setItem(CHAVE_ANEXOS, JSON.stringify(l.filter(a => a !== alvo && JSON.stringify(a) !== JSON.stringify(alvo)))); } catch (e){} msgTela = "Evidência removida."; }
      redesenhar(); }
  });
  global.document.addEventListener("toggle", ev => { const d = ev.target; if (d && d.dataset && d.dataset.evDet) aberto[d.dataset.evDet] = d.open; }, true);
  global.document.addEventListener("submit", async ev => {
    const f = ev.target; if (!f.dataset || !f.dataset.evForm) return; ev.preventDefault();
    const cert = f.dataset.evForm, v = n => (f.elements[n] && f.elements[n].value || "").trim();
    const a = { cert, criterio: v("criterio"), nome: v("nome"), data: v("data"), validade: v("validade"), responsavel: v("responsavel"), obs: v("obs") };
    if (!a.nome || !/^\d{4}-\d{2}-\d{2}$/.test(a.data)){ msgTela = "Informe o nome do documento e a data."; redesenhar(); return; }
    aberto[cert] = true;
    const r = temServidor() ? await postar("/api/evidencias/anexo", a).catch(() => null) : null;
    if (r && r.ok){ msgTela = "Evidência anexada no servidor."; await carregarServidor(true); }
    else { const l = lerJSON(CHAVE_ANEXOS, []); l.push(a); try { global.localStorage.setItem(CHAVE_ANEXOS, JSON.stringify(l)); } catch (e){} msgTela = "Evidência anexada neste aparelho."; }
    redesenhar();
  });
}

global.EVIDENCIAS = { FONTES, ORDEM, NOME_STATUS, num, norm, palavrasDaEvidencia, regrasDoCriterio, avaliarCriterio, evidenciasPara, coletar, carregarServidor, csvDe, mapa };
global.evidenciasPara = evidenciasPara;
global.telaEvidencias = telaEvidencias;
})(typeof window !== "undefined" ? window : globalThis);
