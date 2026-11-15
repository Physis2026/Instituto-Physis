/* physis-relatorio-esg.js — Relatório ESG e taxonomia, para bancos e investidores.
   Estrutura da metodologia IGEA (Physis): identificação e limites do relato → linha de base e qualidade dos dados →
   indicadores (ambiental, social, governança) → maturidade da gestão (13 elementos, escala 1 a 5) → medidas e
   investimento → prontidão para financiamento → conclusões. Acrescenta o alinhamento com a Taxonomia Sustentável
   Brasileira e a correspondência com GRI, IFRS S1/S2 e CBPS 01/02 (só os códigos).
   Contrato com a plataforma: relatorioEsgDados() junta os dados guardados neste aparelho (localStorage e leitores
   dos outros módulos); relatorioEsgHtml(dados) devolve o HTML (títulos a partir de h2, para caber dentro de uma aba);
   telaRelatorioEsg() = relatorioEsgHtml(relatorioEsgDados()). O “Baixar esta tela” da plataforma exporta o HTML.
   Lacunas de dados aparecem escritas, nunca escondidas. Normas citadas pelo nome; textos com palavras próprias. */
(function () {
"use strict";
const E = s => typeof esc === "function" ? esc(s) : String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;" }[c]));
const N = (v, c) => typeof n2 === "function" ? n2(v, c) : Number(v).toLocaleString("pt-BR", { minimumFractionDigits:c, maximumFractionDigits:c });
const T = v => v == null || !isFinite(v) ? null : N(v, Math.abs(v) < 100 ? 2 : 1);
const num = v => { if (v == null) return null; if (typeof v === "number") return isFinite(v) ? v : null; let s = String(v).trim(); if (!s) return null; if (s.indexOf(",") >= 0) s = s.replace(/\./g, "").replace(",", "."); else if (/^-?\d{1,3}(\.\d{3})+$/.test(s)) s = s.replace(/\./g, ""); const x = Number(s); return isFinite(x) ? x : null; };
const vazio = () => typeof ui !== "undefined" && ui && ui.vazia;
const lerLS = (k, pad) => { if (vazio()) return pad; try { const v = JSON.parse(localStorage.getItem(k) || "null"); return v == null ? pad : v; } catch (e){ return pad; } };
const tenta = (f, pad) => { try { const v = f(); return v == null ? pad : v; } catch (e){ return pad; } };

/* 13 elementos da maturidade da gestão (metodologia IGEA, Physis); ids iguais aos da base de certificações */
const IGEA = [["igea_01","Contexto e partes interessadas"],["igea_02","Liderança e compromisso da direção"],["igea_03","Política documentada e comunicada"],["igea_04","Papéis, responsabilidades e autoridade"],["igea_05","Revisão sistemática dos usos e consumos"],["igea_06","Linha de base e indicadores de desempenho"],["igea_07","Objetivos e metas"],["igea_08","Competência e conscientização da equipe"],["igea_09","Planejamento e controle operacional"],["igea_10","Projeto e compras com critério de eficiência"],["igea_11","Monitoramento, medição e análise"],["igea_12","Análise crítica pela direção"],["igea_13","Não conformidade e ação corretiva"]];
const NIVEL = { 1:"inicial", 2:"em desenvolvimento", 3:"definido", 4:"gerenciado", 5:"otimizado" };
const G_SIS = [["ambiental","Gestão ambiental","ISO 14001"],["energia","Gestão de energia","ISO 50001"],["seguranca","Segurança do trabalho","ISO 45001"],["netzero","Net zero","inventário e metas"]];

/* ════════ junta os dados ════════ */
function relatorioEsgDados(){ const d = { data: new Date().toISOString().slice(0, 10) };
  const p = tenta(() => typeof perfilLer === "function" ? perfilLer() : Object.assign({ c:{}, historico:[] }, lerLS("physis-perfil", {})), { c:{}, historico:[] }), pc = p.c || {};
  d.org = { nome: pc.razao_social || pc.nome_fantasia || pc.nome || "", lugar: pc.unidade_nome || "", municipio: pc.municipio || "", setor: pc.setor || pc.cnae || "", colaboradores: num(pc.colaboradores), area_m2: num(pc.area_construida), area_ha: num(pc.area_total_ha), nivel: p.nivel || "" };
  const hist = (p.historico || []).filter(x => x.mes).sort((a, b) => a.mes.localeCompare(b.mes)), uk = hist.filter(x => num(x.kwh) != null).slice(-12), ua = hist.filter(x => num(x.m3) != null).slice(-12);
  d.energia = { kwh: uk.length ? uk.reduce((s, x) => s + num(x.kwh), 0) * 12 / uk.length : null, meses: uk.length, ate: uk.length ? uk[uk.length - 1].mes : "" };
  d.agua = { m3: ua.length ? ua.reduce((s, x) => s + num(x.m3), 0) * 12 / ua.length : null, meses: ua.length };
  const so = tenta(() => typeof calcLer === "function" ? calcLer("solar") : lerLS("physis-calc-solar", {}), {}); d.energia.solar_kwh = tenta(() => typeof solarCalc === "function" && num(so.consumo) > 0 ? solarCalc().ger : null, null);
  d.carbono = tenta(() => window.PhysisCarbono ? window.PhysisCarbono.resumo() : null, null);
  if (!d.carbono){ const c = lerLS("physis-carbono", null); if (c) d.carbono = { antigo:true, kwh: num(c.kwh), solar_kwh: num(c.solar_kwh) }; }
  const rc = tenta(() => typeof rcLer === "function" ? rcLer() : lerLS("physis-residuos-plano", []), []);
  if (Array.isArray(rc) && rc.length){ const s = tenta(() => typeof rcResumo === "function" ? rcResumo(rc) : null, null); d.residuos = { tipos: rc.length, kg_mes: s ? s.tot : null, desvio: s ? s.pct : null, mtr: s ? s.mtr.length : null }; } else d.residuos = null;
  const sbn = tenta(() => typeof sbnLer === "function" ? sbnLer() : lerLS("physis-sbn", { plano:[] }), { plano:[] }), plantas = typeof SBN !== "undefined" && SBN && SBN.plantas ? SBN.plantas : [];
  const plano = sbn.plano || []; d.sbn = plano.length ? { mudas: plano.reduce((s, x) => s + (num(x.qtd) || 0), 0), especies: new Set(plano.map(x => x.n)).size, nativas: plantas.length ? new Set(plano.filter(x => { const q = plantas.find(y => String(y.n) === String(x.n)); return q && String(q.nativa_br) === "True"; }).map(x => x.n)).size : null } : null;
  const g = tenta(() => typeof gLer === "function" ? gLer() : Object.assign({ atividades:[], compras:[], manutencao:[], producao:[], fatores:[], sistemas:{}, indicadores:[] }, lerLS("physis-gestao-cliente", {})), { atividades:[], compras:[], sistemas:{} });
  const hoje = d.data; d.gestao = { acoes: (g.atividades || []).length, feitas: (g.atividades || []).filter(a => a.sit === "Feito").length, vencidas: (g.atividades || []).filter(a => a.sit !== "Feito" && a.prazo && a.prazo < hoje).length,
    sistemas: G_SIS.map(([id, nome, ref]) => { const o = (g.sistemas || {})[id] || {}, feitos = Object.keys(o).filter(k => (o[k] || {}).sit === "Feito").length; return { id, nome, ref, feitos, total:10, comEvid: Object.keys(o).filter(k => (o[k] || {}).ev).length }; }),
    indicadores: (g.indicadores || []).length, swot: (g.fatores || []).length, producao: (g.producao || []).length,
    investimentos: (g.compras || []).filter(x => x.cat === "Investimento").map(x => ({ item: x.item, valor: num(x.valor), ganho: num(x.ganho), vida: num(x.vida), sit: x.sit })) };
  const seg = ((g.sistemas || {}).seguranca) || {}; d.social = { seguranca_feitos: Object.keys(seg).filter(k => (seg[k] || {}).sit === "Feito").length, colaboradores: d.org.colaboradores };
  const cursos = []; tenta(() => { if (vazio()) return; for (let i = 0; i < localStorage.length; i++){ const k = localStorage.key(i); if (k && k.indexOf("physis-curso-") === 0){ const v = JSON.parse(localStorage.getItem(k) || "null"); if (v && v.concluido) cursos.push(k.slice(13)); } } }, null); d.social.cursos = cursos;
  const cert = tenta(() => typeof certLer === "function" ? certLer() : Object.assign({ sel:[], r:{} }, lerLS("physis-cert-gap", {})), { sel:[], r:{} });
  d.igea = IGEA.map(([id, nome]) => { const st = ((cert.r || {})[id] || {}).st || ""; return { id, nome, nivel: /^m[1-5]$/.test(st) ? +st[1] : null, na: st === "na", ev: ((cert.r || {})[id] || {}).ev || "" }; });
  d.certs = tenta(() => (typeof CERTS !== "undefined" && typeof certAvalia === "function") ? CERTS.filter(x => (cert.sel || []).indexOf(x.id) >= 0).map(x => { const a = certAvalia(x, cert); return { id:x.id, nome:x.nome, pct:a.pct, n:a.n, obrigPend:a.obrigPend }; }) : (cert.sel || []).map(id => ({ id, nome:id, pct:null, n:0 })), []);
  return d; }

/* ════════ peças ════════ */
let LAC = [];
const falta = (txt, onde) => { if (!LAC.some(x => x[0] === txt)) LAC.push([txt, onde]); return `<span class="selo al">sem dado</span> <span class="t2 pq">${E(onde)}</span>`; };
const val = (v, un, txt, onde) => v == null ? falta(txt, onde) : E(v) + (un ? " " + E(un) : "");
const tab = (cap, cab, linhas) => `<div class="rolagem"><table><caption>${E(cap)}</caption><thead><tr>${cab.map(h => `<th scope="col">${E(h)}</th>`).join("")}</tr></thead><tbody>${linhas.join("")}</tbody></table></div>`;
const tr = (cels) => `<tr><th scope="row" style="font-weight:500">${cels[0]}</th>${cels.slice(1).map(c => `<td>${c}</td>`).join("")}</tr>`;
const sec = (id, tit, corpo) => `<section class="cartao esg-sec" aria-labelledby="esg-${id}"><h3 id="esg-${id}">${tit}</h3>${corpo}</section>`;
const verif = `<span class="selo at">verificar</span>`;

/* ════════ relatório ════════ */
function relatorioEsgHtml(d){ d = d || relatorioEsgDados(); LAC = [];
  const o = d.org || {}, cb = d.carbono && !d.carbono.antigo ? d.carbono : null, en = d.energia || {}, ag = d.agua || {}, rs = d.residuos, sb = d.sbn, ge = d.gestao || { sistemas:[], investimentos:[] }, so = d.social || {};
  const ig = (d.igea || []).filter(x => x.nivel != null), igMedia = ig.length ? ig.reduce((s, x) => s + x.nivel, 0) / ig.length : null;
  const intE = en.kwh != null && o.area_m2 ? en.kwh / o.area_m2 : null;

  const capa = `<header class="esg-capa"><p class="t2" style="letter-spacing:.08em;text-transform:uppercase;margin:0">Physis · Relatório ESG</p>
    <h2 id="esg-titulo" style="margin:.2em 0">Relatório ESG ${o.nome ? "· " + E(o.nome) : ""}</h2>
    <p class="t2">${o.lugar ? E(o.lugar) + " · " : ""}${o.municipio ? E(o.municipio) + " · " : ""}emitido em ${E(String(d.data).split("-").reverse().join("/"))} · estrutura da metodologia IGEA (Physis)</p>
    <p class="t2 pq">Preparado pela plataforma Physis com os dados registrados pela própria organização. Relatório de apoio à decisão: não é auditado nem verificado por terceira parte, salvo indicação em contrário. Uso restrito aos destinatários.</p></header>`;

  /* 1. resumo executivo */
  const resumo = sec("resumo", "1. Resumo executivo", tab("Principais números", ["Indicador", "Valor atual", "Referência ou meta"], [
    tr(["Emissões totais (escopos 1, 2 e 3)", cb ? val(T(cb.total), "tCO₂e/ano") : falta("Inventário de carbono", "aba Carbono"), cb && cb.metas ? "meta: −" + E(N(cb.metas.pct, 1)) + "% da base por ano; net zero em " + E(cb.metas.net_zero || "—") : "—"]),
    tr(["Escopos 1 e 2 (operação)", cb ? val(T(cb.e1 + cb.e2_loc), "tCO₂e/ano") : falta("Escopos 1 e 2", "aba Carbono"), cb ? "SBCE: " + E({ voluntario:"abaixo de 10 mil t", relato:"relato obrigatório", obrigacao:"relato e conciliação" }[cb.sbce] || "—") : "—"]),
    tr(["Eletricidade", val(en.kwh != null ? N(en.kwh, 0) : null, "kWh/ano", "Consumo de eletricidade", "contas de luz no Início"), intE != null ? E(N(intE, 1)) + " kWh/m²·ano" : "—"]),
    tr(["Água", val(ag.m3 != null ? N(ag.m3, 0) : null, "m³/ano", "Consumo de água", "contas de água no Início"), "—"]),
    tr(["Resíduos desviados do aterro", rs && rs.desvio != null ? E(Math.round(rs.desvio * 100)) + "%" : falta("Desvio de resíduos", "Economia circular"), "meta de referência: 90% (lixo zero)"]),
    tr(["Maturidade da gestão (1 a 5)", igMedia != null ? E(N(igMedia, 1)) + " · " + E(NIVEL[Math.round(igMedia)]) : falta("Maturidade da gestão", "Certificações → ISO 50001 → maturidade (IGEA)"), ig.length + " de 13 elementos avaliados"])]));

  /* 2. limites do relato e qualidade dos dados */
  const qual = [["Contas de luz", en.meses, 12], ["Contas de água", ag.meses, 12]].map(([n, m, a]) => tr([E(n), m ? m + " de " + a + " meses" : falta(n, "Início → contas"), m >= a ? '<span class="selo ok">completo</span>' : m ? '<span class="selo at">parcial</span>' : "—"]));
  const limites = sec("limites", "2. Limites do relato e qualidade dos dados", `<p>Fronteira: controle operacional da unidade ${o.lugar ? "“" + E(o.lugar) + "”" : "cadastrada"}${o.area_m2 ? ", " + E(N(o.area_m2, 0)) + " m² construídos" : ""}${o.area_ha ? ", " + E(N(o.area_ha, 1)) + " ha" : ""}. Período: últimos 12 meses com dados${cb && cb.ano ? "; inventário de carbono do ano " + E(cb.ano) : ""}.</p>
    ${tab("Completude dos dados de base", ["Dado", "Cobertura", "Situação"], qual.concat([tr(["Inventário de carbono", cb ? E(cb.linhas) + " fontes lançadas" : falta("Inventário", "aba Carbono"), cb && cb.medido != null ? "medido: " + E(Math.round(cb.medido * 100)) + "% · incerteza ±" + E(cb.incerteza != null ? Math.round(cb.incerteza * 100) : "—") + "%" : "—"])]))}`);

  /* 3. ambiental */
  const carbTab = cb ? tab("Emissões por escopo", ["Escopo", "tCO₂e por ano", "Observação"], [
      tr(["Escopo 1 · diretas", E(T(cb.e1)), "combustíveis, refrigeração, processos, agropecuária"]), tr(["Escopo 2 · localização", E(T(cb.e2_loc)), "fator do SIN: " + E(N(cb.fator_rede, 4)) + " tCO₂/MWh"]), tr(["Escopo 2 · escolha de compra", E(T(cb.e2_mkt)), "I-REC e contratos"]),
      tr(["Escopo 3 · cadeia de valor", E(T(cb.e3)), "categorias " + E((cb.cats3 || []).join(", ") || "—")]), tr(["CO₂ biogênico (à parte)", E(T(cb.bio_t)), "não soma ao total"]), tr(["Remoções (à parte)", E(T(cb.remocoes_t)), "restauração e reflorestamento"]), tr(["Evitadas (à parte)", E(T(cb.evitadas_t)), "solar, biogás, reciclagem"])])
    + tab("Emissões por gás", ["Gás", "tCO₂e por ano"], [["CO₂","CO2"],["CH₄","CH4"],["N₂O","N2O"],["HFCs","HFC"],["SF₆","SF6"]].map(([n, k]) => tr([n, E(T((cb.por_gas || {})[k] || 0))]))) + `<p class="t2 pq">GWP ${E(cb.gwp)}; GHG Protocol (abordagem do Programa Brasileiro GHG Protocol). Intensidade: ${cb.int_m2 != null ? E(N(cb.int_m2, 1)) + " kgCO₂e/m²·ano" : "sem área"}${cb.int_prod != null ? "; " + E(N(cb.int_prod, 3)) + " kgCO₂e por " + E(cb.producao_un) : ""}.</p>`
    : `<p>${falta("Inventário de emissões por escopo", "aba Carbono")}</p>`;
  const amb = sec("amb", "3. Ambiental", `
    <h4>3.1 Energia</h4><p>Eletricidade: ${val(en.kwh != null ? N(en.kwh, 0) : null, "kWh por ano", "Eletricidade", "contas de luz no Início")}${intE != null ? " · " + E(N(intE, 1)) + " kWh/m²·ano" : ""}. Geração solar: ${en.solar_kwh ? E(N(en.solar_kwh, 0)) + " kWh por ano (estimativa da aba Energia solar)" : "não dimensionada"}.</p>
    <h4>3.2 Água</h4><p>Consumo: ${val(ag.m3 != null ? N(ag.m3, 0) : null, "m³ por ano", "Água", "contas de água no Início")}.</p>
    <h4>3.3 Resíduos</h4><p>${rs ? E(rs.tipos) + " tipos de resíduo com rota definida; " + (rs.kg_mes != null ? E(N(rs.kg_mes * 12 / 1000, 1)) + " t por ano; " : "") + (rs.desvio != null ? E(Math.round(rs.desvio * 100)) + "% desviado do aterro; " : "") + (rs.mtr != null ? E(rs.mtr) + " fluxos exigem MTR." : "") : falta("Plano de resíduos", "Economia circular")}</p>
    <h4>3.4 Carbono por escopo</h4>${carbTab}
    <h4>3.5 Biodiversidade e soluções baseadas na natureza</h4><p>${sb ? E(N(sb.mudas, 0)) + " mudas de " + E(sb.especies) + " espécies no plano" + (sb.nativas != null ? " (" + E(sb.nativas) + " nativas do Brasil)" : "") + (cb && cb.remocoes_t ? "; remoção estimada de " + E(T(cb.remocoes_t)) + " tCO₂ por ano." : ".") : falta("Plano de plantio e restauração", "SbN e viveiro")}</p>`);

  /* 4. social */
  const segSis = (ge.sistemas || []).find(x => x.id === "seguranca"), i45 = (d.certs || []).find(x => x.id === "iso45001");
  const soc = sec("soc", "4. Social", tab("Indicadores sociais", ["Tema", "Situação", "Fonte"], [
      tr(["Segurança do trabalho (rotina de gestão)", segSis ? E(segSis.feitos) + " de 10 itens feitos" : falta("Itens de segurança do trabalho", "Gestão → Sistemas de gestão"), "Gestão"]),
      tr(["Segurança do trabalho (ISO 45001)", i45 && i45.pct != null ? E(Math.round(i45.pct * 100)) + "% dos critérios avaliados" : falta("Gap da ISO 45001", "Certificações"), "Certificações"]),
      tr(["Acidentes e taxa de frequência", falta("Registro de acidentes e horas trabalhadas", "a registrar (fase 2)"), "—"]),
      tr(["Capacitação", so.cursos && so.cursos.length ? E(so.cursos.length) + " cursos concluídos neste aparelho (" + E(so.cursos.join(", ")) + ")" : falta("Cursos concluídos e horas de treinamento", "Cursos"), "Cursos"]),
      tr(["Acessibilidade do lugar (ABNT NBR 9050)", falta("Diagnóstico de acessibilidade", "a avaliar (fase 2)"), "—"]),
      tr(["Pessoas", val(so.colaboradores != null ? N(so.colaboradores, 0) : null, "colaboradores", "Número de colaboradores", "Início"), "Início"]),
      tr(["Diversidade (gênero, raça, PcD)", falta("Composição da equipe", "a registrar (fase 2)"), "—"])]));

  /* 5. governança */
  const igTab = tab("Maturidade da gestão por elemento (escala 1 a 5)", ["Elemento", "Nível", "Evidência"], (d.igea || IGEA.map(([id, nome]) => ({ id, nome }))).map(x => tr([E(x.nome), x.na ? "não se aplica" : x.nivel != null ? E(x.nivel) + " · " + E(NIVEL[x.nivel]) : '<span class="selo al">não avaliado</span>', E(x.ev || "—")])));
  const certTab = (d.certs || []).length ? tab("Certificações e sistemas de gestão escolhidos", ["Certificação", "Atendimento", "Obrigatórios pendentes"], d.certs.map(x => tr([E(x.nome), x.pct != null ? E(Math.round(x.pct * 100)) + "% (" + E(x.n) + " critérios avaliados)" : "não avaliado", E(x.obrigPend != null ? x.obrigPend : "—")]))) : `<p>${falta("Gap analysis de certificações", "Certificações")}</p>`;
  const sisTab = tab("Sistemas de gestão na rotina", ["Sistema", "Itens feitos", "Com evidência"], (ge.sistemas || []).map(x => tr([E(x.nome) + " · apoio à " + E(x.ref), E(x.feitos) + " de 10", E(x.comEvid)])));
  const gov = sec("gov", "5. Governança", `<h4>5.1 Maturidade da gestão (metodologia IGEA, Physis)</h4><p>Média: ${igMedia != null ? "<strong>" + E(N(igMedia, 1)) + "</strong> (" + E(NIVEL[Math.round(igMedia)]) + "), " + ig.length + " de 13 elementos" : falta("Avaliação de maturidade", "Certificações → ISO 50001 → maturidade (IGEA)")}. Escala: 1 inicial, 2 em desenvolvimento, 3 definido, 4 gerenciado, 5 otimizado.</p>${igTab}
    <h4>5.2 Certificações</h4>${certTab}<h4>5.3 Políticas e sistemas de gestão</h4>${sisTab}
    <h4>5.4 Plano de ação e indicadores</h4><p>${ge.acoes ? E(ge.feitas) + " de " + E(ge.acoes) + " ações concluídas; " + E(ge.vencidas) + " com prazo vencido. " : falta("Plano de ação", "Gestão → Plano de ação") + " "}${ge.indicadores ? E(ge.indicadores) + " indicadores próprios acompanhados. " : ""}${ge.swot ? E(ge.swot) + " fatores internos e externos registrados." : ""}</p>
    <h4>5.5 Clima e mercado regulado</h4><p>${cb ? "Enquadramento no SBCE (Lei 15.042/2024): " + E({ voluntario:"abaixo do limite de relato", relato:"obrigado a monitorar e relatar", obrigacao:"obrigado a relatar e conciliar" }[cb.sbce]) + ". Itens de preparação feitos: " + E(Object.keys(cb.sbce_check || {}).filter(k => cb.sbce_check[k]).length) + " de 7. " + verif : falta("Enquadramento no SBCE", "Carbono → SBCE e créditos")}</p>`);

  /* 6. medidas, investimento e prontidão para financiamento */
  const inv = (ge.investimentos || []).filter(x => x.valor);
  const invTab = inv.length ? tab("Investimentos registrados", ["Item", "Investimento", "Ganho por mês", "Vida útil", "Retorno simples", "Situação"], inv.map(x => tr([E(x.item || "—"), "R$ " + E(N(x.valor, 2)), x.ganho ? "R$ " + E(N(x.ganho, 2)) : "—", x.vida ? E(N(x.vida, 0)) + " anos" : "—", x.ganho ? E(N(x.valor / x.ganho, 1)) + " meses" : "—", E(x.sit || "—")]))) : `<p>${falta("Medidas com investimento e economia", "Gestão → Compras e investimentos (tipo Investimento)")}</p>`;
  const pront = [["Medição e verificação da economia (IPMVP citado)", false], ["Estrutura do financiamento (prazo, carência, reserva)", false], ["Riscos com plano de resposta", ge.swot > 0], ["Análise de crédito do tomador", false], ["Incerteza da economia quantificada (cenário conservador)", !!(cb && cb.incerteza != null)], ["Benefícios além da energia quantificados", false], ["Premissas de tarifa, inflação e câmbio", inv.some(x => x.vida)]];
  const fin = sec("fin", "6. Medidas, investimento e prontidão para financiamento", `${invTab}${cb && cb.metas ? `<p>Redução cadastrada no Carbono: ${E(T(cb.metas.medidas_t) || "0")} tCO₂e por ano.</p>` : ""}
    ${tab("Lista de prontidão para financiamento", ["Requisito", "Situação"], pront.map(([n, ok]) => tr([E(n), ok ? '<span class="selo ok">há indício nos dados</span>' : '<span class="selo at">a preparar</span>'])))}
    <p class="t2 pq">Prontidão: ${pront.filter(x => x[1]).length} de ${pront.length}. Bancos costumam pedir 80% ou mais, com auditoria de grau de investimento.</p>`);

  /* 7. Taxonomia Sustentável Brasileira */
  const temSolar = !!(en.solar_kwh || (cb && cb.evitadas && cb.evitadas.solar)), temRest = !!(sb || (cb && cb.remocoes_t)), temOrg = !!(rs && cb && cb.evitadas && cb.evitadas.biogas) || !!rs;
  const indicio = (tem, txt) => tem ? `<span class="selo ok">indício</span> ${E(txt)}` : '<span class="selo in">sem indício nos dados</span>';
  const tax = sec("tax", "7. Alinhamento com a Taxonomia Sustentável Brasileira", `<p>A Taxonomia Sustentável Brasileira (Ministério da Fazenda, Plano de Transformação Ecológica) classifica atividades econômicas que contribuem para objetivos climáticos, ambientais e sociais. Para uma atividade ser considerada alinhada, ela precisa: (1) dar contribuição substancial a pelo menos um objetivo, pelos critérios técnicos do setor; (2) não causar dano significativo aos demais objetivos; e (3) cumprir salvaguardas mínimas sociais e de governança. ${verif} critérios técnicos, limites e calendário de adoção conforme os cadernos publicados.</p>
    ${tab("Atividades com possível alinhamento", ["Atividade (setor)", "Critério em resumo (palavras próprias)", "Situação neste lugar"], [
      tr(["Geração de eletricidade solar (eletricidade e gás)", "Geração renovável com emissão de ciclo de vida baixa; avaliar destino dos módulos no fim de vida.", indicio(temSolar, "sistema solar dimensionado ou informado")]),
      tr(["Eficiência energética em edificações (construção)", "Redução comprovada de consumo frente à linha de base, com medição.", indicio(!!(cb && cb.metas && cb.metas.medidas_t), "medidas de redução cadastradas")]),
      tr(["Restauração de vegetação nativa (agropecuária e floresta)", "Espécies nativas, plano de manejo e monitoramento; sem substituir vegetação nativa existente.", indicio(temRest, "plano SbN ou área em restauração")]),
      tr(["Compostagem e biodigestão de orgânicos (água, esgoto e resíduos)", "Tratamento que evita aterro e controla emissões de metano.", indicio(temOrg, "rotas de tratamento na Economia circular")]),
      tr(["Agropecuária de baixa emissão (agropecuária)", "Práticas como recuperação de pastagem e integração lavoura-pecuária-floresta, com inventário.", indicio(!!(cb && cb.por_grupo && cb.por_grupo.agropecuaria), "rebanho ou adubação no inventário")]),
      tr(["Salvaguardas mínimas", "Direitos trabalhistas e humanos, integridade e conformidade legal.", (ge.sistemas || []).some(x => x.id === "seguranca" && x.feitos >= 5) ? '<span class="selo ok">indício</span> rotina de segurança do trabalho' : '<span class="selo at">a comprovar</span>'])])}
    <p class="t2 pq">Indício não é alinhamento: a confirmação exige comparar cada atividade com os critérios técnicos do caderno do setor e reunir as evidências.</p>`);

  /* 8. correspondência de códigos */
  const ref = [
    ["Consumo de energia", "302-1", "S2 · 32", "02 · 32", en.kwh != null],
    ["Intensidade energética", "302-3", "S2 · 32", "02 · 32", intE != null],
    ["Redução do consumo de energia", "302-4", "S2 · 33–36", "02 · 33–36", !!(cb && cb.metas && cb.metas.medidas_t)],
    ["Retirada e consumo de água", "303-3; 303-5", "—", "—", ag.m3 != null],
    ["Habitats protegidos ou restaurados", "304-3", "—", "—", !!sb],
    ["Emissões diretas (escopo 1)", "305-1", "S2 · 29(a)(i)", "02 · 29(a)(i)", !!cb],
    ["Emissões de energia comprada (escopo 2)", "305-2", "S2 · 29(a)(i), 29(a)(v)", "02 · 29(a)(i), 29(a)(v)", !!cb],
    ["Outras emissões indiretas (escopo 3)", "305-3", "S2 · 29(a)(i), 29(a)(vi)", "02 · 29(a)(i), 29(a)(vi)", !!(cb && cb.e3)],
    ["Intensidade de emissões", "305-4", "S2 · 32", "02 · 32", !!(cb && (cb.int_m2 != null || cb.int_prod != null))],
    ["Redução de emissões e metas", "305-5", "S2 · 33–36", "02 · 33–36", !!(cb && cb.metas)],
    ["Resíduos gerados, desviados e destinados", "306-3; 306-4; 306-5", "—", "—", !!rs],
    ["Sistema de gestão de saúde e segurança", "403-1", "—", "—", !!(segSis && segSis.feitos)],
    ["Treinamento em saúde e segurança", "403-5", "—", "—", false],
    ["Acidentes de trabalho", "403-9", "—", "—", false],
    ["Horas de capacitação", "404-1", "—", "—", false],
    ["Diversidade na equipe", "405-1", "—", "—", false],
    ["Governança e responsabilidades", "2-9; 2-12", "S1 · 26–27; S2 · 5–7", "01 · 26–27; 02 · 5–7", ig.length > 0],
    ["Políticas e compromissos", "2-23; 2-24", "S1 · 26–27", "01 · 26–27", (ge.sistemas || []).some(x => x.feitos > 0)],
    ["Estratégia, riscos e oportunidades do clima", "201-2", "S2 · 8–23; 24–26", "02 · 8–23; 24–26", ge.swot > 0],
    ["Conformidade com leis e regulamentos", "2-27", "S1 · 45–53", "01 · 45–53", false]];
  const cods = sec("cods", "8. Correspondência com GRI, IFRS S1/S2 e CBPS", `${tab("Indicadores e códigos de referência", ["Indicador", "GRI", "IFRS", "CBPS", "Neste relatório"], ref.map(([n, g, i, c, ok]) => tr([E(n), E(g), E(i), E(c), ok ? '<span class="selo ok">com dado</span>' : '<span class="selo al">lacuna</span>'])))}
    <p class="t2 pq">Só os códigos: GRI (Normas GRI, série 300 ambiental, 400 social e 2 conteúdos gerais); IFRS S1 e S2 (ISSB, números dos parágrafos); CBPS 01 e 02 (Comitê Brasileiro de Pronunciamentos de Sustentabilidade, adotados pela CVM, Resolução 193/2023). ${verif} numeração na versão vigente de cada norma.</p>`);

  /* 9. lacunas e 10. nota metodológica (montadas no fim, com a lista de lacunas completa) */
  const lac = sec("lac", "9. Lacunas de dados", LAC.length ? `<p>${LAC.length} dados ainda faltam para um relatório completo:</p><ul>${LAC.map(([t, o]) => `<li><strong>${E(t)}</strong> — onde preencher: ${E(o)}</li>`).join("")}</ul>` : `<p><span class="selo ok">Sem lacunas</span> nos dados que este relatório usa.</p>`);
  const nota = sec("nota", "10. Nota metodológica", `<ul><li>Estrutura da metodologia IGEA (Physis): limites e linha de base, indicadores, maturidade da gestão em 13 elementos (escala 1 a 5), medidas e investimento, prontidão para financiamento e conclusões.</li>
    <li>Emissões pelo GHG Protocol (padrão corporativo, orientação do escopo 2 e padrão do escopo 3), com a abordagem do Programa Brasileiro GHG Protocol e a ISO 14064-1:2018; fatores com fonte e ano na base da Physis, os marcados “verificar” a conferir antes de relato oficial.</li>
    <li>Remoções, emissões evitadas e CO₂ biogênico informados à parte, sem abater o total.</li>
    <li>Dados registrados pela organização na plataforma; não houve verificação independente. Valores anuais estimados a partir de até 12 meses de dados.</li></ul>`);
  const estilo = `<style>.esg-rel h3{margin-top:0}.esg-rel caption{text-align:left;font-weight:600;padding:4px 0}@media print{.esg-rel .esg-sec{break-inside:avoid-page}.esg-rel .esg-capa{border-bottom:2px solid currentColor;margin-bottom:12px}.esg-rel .selo{border:1px solid currentColor}}</style>`;
  return `${estilo}<article class="esg-rel" aria-labelledby="esg-titulo">${capa}${resumo}${limites}${amb}${soc}${gov}${fin}${tax}${cods}${lac}${nota}
    <p class="t2 pq">Para levar em Word, PDF ou Excel, use “Baixar esta tela”.</p></article>`; }

const telaRelatorioEsg = () => relatorioEsgHtml(relatorioEsgDados());
window.relatorioEsgDados = relatorioEsgDados;
window.relatorioEsgHtml = relatorioEsgHtml;
window.telaRelatorioEsg = telaRelatorioEsg;
})();
