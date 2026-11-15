/* physis-servidor-verde.js — Servidor verde: dimensionamento de servidores com pouca pegada, por projeto
   (Casa Physis, clientes e terceiros). Espelho das contas em physis_hub/servidor_verde.py (testes de mesa).
   Contrato com a plataforma: define telaServidorVerde() (HTML da aba inteira, com um único título h1),
   window.SERVIDOR_VERDE = { dimensionar, vramGb, ..., PERFIS, ler, gravar } e window.SERVIDOR_VERDE_I18N (português → inglês)
   com window.SERVIDOR_VERDE_I18N_RX (frases com números); os dois vão copiados em sistema/physis-i18n-modulos.json.
   Módulo EM DESENVOLVIMENTO: a tela mostra o selo "Em desenvolvimento" até a plataforma marcar window.SERVIDOR_VERDE_PRONTO = true.
   Catálogo de módulos (hardware e programas): sistema/physis-servidor-catalogo.json, embutido como
   <script type="application/json" id="base-servidor-catalogo"> (ou window.PHYSIS_SERVIDOR_CATALOGO).
   Estado em localStorage "physis-servidor-verde" = { v:1, atual, projetos:[{ id, nome, perfil, p:{...} }] }
   (a ponte do cliente leva ao servidor quando a chave estiver na lista de perfil_cliente.py).
   Usa, se existirem: esc, n2, el, ui, desenhar, window.PhysisCarbono (fator da rede), analiseInvest, window.CARGA_TERMICA,
   GET api/gis/irradiacao (sol do lugar do projeto) e GET /api/servidor/pegada (medição real da Casa Physis).
   Cores e fundo só pelas classes da plataforma (claro e escuro). Sem recursos externos. Normas citadas pelo nome. */
(function () {
"use strict";
const CHAVE = "physis-servidor-verde";
const SUBS = [["selecao","Seleção de módulos"],["cargas","Cargas de trabalho"],["computacao","Computação"],["armazenamento","Armazenamento e cópias"],["rede","Rede"],["energia","Energia"],["termico","Térmico e ambiente"],["carbono","Carbono e custos"],["resultado","Resultado"]];

/* ════════ utilitários ════════ */
const E = s => typeof esc === "function" ? esc(s) : String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;" }[c]));
const N = (v, c) => v == null || !isFinite(v) ? "—" : (typeof n2 === "function" ? n2(v, c) : Number(v).toLocaleString("pt-BR", { minimumFractionDigits:c, maximumFractionDigits:c }));
const UI = () => typeof ui !== "undefined" && ui ? ui : (window.__svUi = window.__svUi || {});
const pegar = id => typeof el === "function" ? el(id) : document.getElementById(id);
function num(v){ if (v == null) return null; if (typeof v === "number") return isFinite(v) ? v : null; let s = String(v).trim().replace(/\s/g, ""); if (!s) return null;
  if (s.indexOf(",") >= 0) s = s.replace(/\./g, "").replace(",", "."); else if (/^-?\d{1,3}(\.\d{3})+$/.test(s)) s = s.replace(/\./g, "");
  const x = Number(s); return isFinite(x) ? x : null; }
const n = (v, pad) => { const x = num(v); return x == null ? (pad == null ? 0 : pad) : x; };
const clone = o => JSON.parse(JSON.stringify(o));
const MARC = "[MARCADOR]";
const temServidorWeb = () => { try { return /^https?:$/.test(location.protocol); } catch (e){ return false; } };

/* ════════ contas (mesmas de physis_hub/servidor_verde.py) ════════ */
const BTU_POR_W = 3.412, BTU_POR_TR = 12000, H_MES = 730;
const EF_80PLUS = { sem:0.80, bronze:0.85, prata:0.88, ouro:0.90, platina:0.92, titanio:0.94 };
const DOD = { lifepo4:0.90, chumbo:0.50 };
const RAID_UTIL = { nenhum:() => 1, raid1:() => 0.5, raid10:() => 0.5, raid5:d => d >= 3 ? (d - 1) / d : 0.5, raid6:d => d >= 4 ? (d - 2) / d : 0.5 };
/* classes de máquina: mesmo bloco "servidor" de sistema/physis-fatores-emissao.json (pegada_servidor.PADRAO) */
const CLASSES_PAD = { rpi4:{ nome:"Raspberry Pi 4 (com fonte e cartão)", w_ocioso:3, w_carga:7, kgco2e_fabricacao:15, vida_anos:5 }, rpi5:{ nome:"Raspberry Pi 5 (com fonte, ventoinha e SSD)", w_ocioso:3.5, w_carga:10, kgco2e_fabricacao:20, vida_anos:5 },
  mini_pc:{ nome:"Mini PC (tipo NUC)", w_ocioso:8, w_carga:45, kgco2e_fabricacao:120, vida_anos:5 }, workstation:{ nome:"Workstation ou desktop (placa ATX, sem placa de vídeo)", w_ocioso:40, w_carga:200, kgco2e_fabricacao:350, vida_anos:5 }, servidor_x86:{ nome:"Servidor x86 de rack ou torre (2 processadores)", w_ocioso:110, w_carga:330, kgco2e_fabricacao:1300, vida_anos:5 },
  servidor_gpu:{ nome:"Servidor com GPU para IA", w_ocioso:150, w_carga:650, kgco2e_fabricacao:1300, vida_anos:4 } };
function baseFatores(){ try { const s = document.getElementById("base-fatores-emissao"); if (s) return JSON.parse(s.textContent); } catch (e){} return window.PHYSIS_FATORES_EMISSAO || null; }
function baseServidor(){ const F = baseFatores(); return F && F.servidor && F.servidor.classes ? F.servidor : { classes:CLASSES_PAD, gpu_placa:{ kgco2e_fabricacao:150, vida_anos:4 } }; }

const vramGb = (paramsB, bits, sobra) => paramsB * bits / 8 * (sobra == null ? 1.2 : sobra);
const vramTreinoGb = (paramsB, bits, modo) => modo === "completo" ? paramsB * 16 * 1.2 : vramGb(paramsB, bits) * 1.5;
const gpusNecessarias = (vram, porGpu, folga) => vram <= 0 || porGpu <= 0 ? 0 : Math.ceil(vram * (1 + (folga || 0) / 100) / porGpu - 1e-9);
const tokSEstimado = paramsB => paramsB > 0 ? 280 / paramsB : 0;
function classeRecomendada(nuc, ram, ia, tb){ if (ia) return "servidor_gpu"; if (nuc <= 4 && ram <= 8 && (tb || 0) <= 1) return "rpi5"; if (nuc <= 8 && ram <= 64) return "mini_pc"; return "servidor_x86"; }
function computacao(p){ const us = n(p.usuarios_sim), bi = n(p.bi_usuarios), cam = n(p.geo_camadas), calcNuc = n(p.calc_rodadas_dia) * n(p.calc_min_rodada) / 1440 * n(p.calc_nucleos_rodada, 1), req = n(p.req_min);
  const nuc = 2 + us / 25 + bi / 5 + (cam ? 1 + cam / 20 : 0) + req / 600 + calcNuc * 4 + n(p.docs_dia) / 500;
  let ram = 2 + us * 0.05 + bi * 0.5 + (cam ? 2 : 0) + n(p.sensores) * 0.002 + (n(p.calc_rodadas_dia) ? 1 : 0) * 2;
  const ia = !!p.ia_ativa, params = n(p.ia_params_b), bits = n(p.ia_bits, 4);
  const vRun = ia ? vramGb(params, bits) * Math.max(1, Math.ceil(n(p.ia_usuarios_sim, 1) / 4)) : 0, vTrn = ia && n(p.treino_h_mes) ? vramTreinoGb(params, bits, p.treino_modo || "qlora") : 0, vNeed = Math.max(vRun, vTrn);
  const folga = n(p.folga_pct, 30), tokS = n(p.ia_tok_s) || tokSEstimado(params), hIa = (ia && tokS ? n(p.ia_tokens_dia) / tokS / 3600 : 0) + n(p.treino_h_mes) / 30;
  if (ia) ram += params * bits / 8;
  const gq = Math.trunc(n(p.gpu_qtd)), gv = n(p.gpu_vram_gb), aq = Math.trunc(n(p.gpu_alt_qtd)), av = n(p.gpu_alt_vram_gb), precisa = vNeed * (1 + folga / 100);
  const r = { nucleos: Math.ceil(nuc * (1 + folga / 100)), ram_gb: Math.ceil(ram * (1 + folga / 100)), vram_rodar_gb:vRun, vram_treino_gb:vTrn, vram_precisa_gb:precisa,
    gpus_precisa: ia ? gpusNecessarias(vNeed, gv || 8, folga) : 0, vram_atual_gb: gq * gv, atende_atual: ia ? gq * gv >= precisa : true, vram_alt_gb: aq * av, atende_alt: ia && aq ? aq * av >= precisa : null, tok_s:tokS, h_ia_dia:hIa };
  r.classe = classeRecomendada(r.nucleos, r.ram_gb, ia); return r; }
const bancoGb = (sens, lmin, bytes, anos) => sens * lmin * 525600 * bytes * anos / 1e9;
const discoBrutoGb = (util, raid, discos) => util / (RAID_UTIL[raid] || RAID_UTIL.raid1)(Math.max(1, discos));
const tempoRestauroH = (gb, mbps) => mbps > 0 ? gb * 8000 / mbps / 3600 : Infinity;
function armazenamento(p){ const anos = n(p.retencao_anos, 1), db = bancoGb(n(p.sensores), n(p.leituras_min), n(p.bytes_leitura, 200), anos) * Math.max(1, n(p.instalacoes, 1)), arq = n(p.arquivos_gb_ano) * anos, tiles = n(p.geo_tiles_gb);
  const mod = n(p.modelos_gb) || (p.ia_ativa ? n(p.ia_params_b) * n(p.ia_bits, 4) / 8 * 3 : 0), util = (db + arq + tiles + mod + 32) * (1 + n(p.folga_pct, 30) / 100), snap = util * n(p.snapshots_pct, 20) / 100;
  const bruto = discoBrutoGb(util + snap, p.raid || "raid1", Math.trunc(n(p.discos, 2))), backup = (db + arq + tiles + mod) * (1 + n(p.backup_versoes, 7) * n(p.mudanca_dia_pct, 2) / 100);
  return { banco_gb:db, arquivos_gb:arq, tiles_gb:tiles, modelos_gb:mod, util_gb:util, snapshots_gb:snap, bruto_gb:bruto, backup_fora_gb:backup, copias:3, restauro_h: tempoRestauroH(backup, n(p.backup_mbps, 50)) }; }
function rede(p, arm){ const us = n(p.usuarios_remotos) * n(p.kbps_usuario, 500) / 1000, sync = n(p.sync_mb_dia) * 8 / 86400, bkDia = arm.backup_fora_gb * n(p.mudanca_dia_pct, 2) / 100, jan = n(p.janela_backup_h, 6), bk = jan ? bkDia * 8000 / (jan * 3600) : 0;
  return { subida_mbps:(us + sync + bk) * 1.5, descida_mbps:(us * 0.5 + sync) * 1.5 + 5, backup_dia_gb:bkDia, latencia_ok: n(p.latencia_ms, 40) <= 100 }; }
function wComponente(c, cicloIa){ const q = n(c.qtd, 1), wo = n(c.w_ocioso), wc = n(c.w_carga); let ci = num(c.ciclo); if (ci == null) ci = c.tipo === "gpu" && cicloIa != null ? cicloIa : 0.3; ci = Math.max(0, Math.min(1, ci)); return [q * (wo + (wc - wo) * ci), q * wc, q * wo]; }
function eficienciaCurva(curva, fr){ const pts = Object.keys(curva || {}).filter(k => k[0] !== "_" && typeof curva[k] === "number").map(k => [Number(k) / 100, curva[k]]).sort((a, b) => a[0] - b[0]); if (!pts.length) return 0.9;
  if (fr <= pts[0][0]) return pts[0][1]; for (let i = 1; i < pts.length; i++) if (fr <= pts[i][0]) return pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * (fr - pts[i - 1][0]) / (pts[i][0] - pts[i - 1][0]); return pts[pts.length - 1][1]; }
function energia(p, comp, fonteW, curva){ const cicloIa = Math.min(1, comp.h_ia_dia / 24), brutas = (p.componentes || []).map(c => [c].concat(wComponente(c, cicloIa)));
  const dcMed = brutas.filter(b => b[0].fonte !== false).reduce((s, b) => s + b[1], 0), ef = fonteW && curva ? eficienciaCurva(curva, dcMed / fonteW) : (EF_80PLUS[p.fonte_80plus || "ouro"] || 0.9); let med = 0, pico = 0; const linhas = [];
  brutas.forEach(([c, wm, wp]) => { const k = c.fonte !== false ? 1 / ef : 1; linhas.push({ nome:c.nome || "", w_medio:wm * k, w_pico:wp * k }); med += wm * k; pico += wp * k; });
  return { w_medio:med, w_pico:pico, kwh_dia:med * 24 / 1000, kwh_mes:med * H_MES / 1000, eficiencia_fonte:ef, linhas, ciclo_ia:cicloIa, dc_medio:dcMed }; }
/* ════════ catálogo de módulos (mesmas regras de servidor_verde.totais / compat) ════════ */
const CATS_POTENCIA = ["plataforma","cpu","ram","gpu","armazenamento","raid","rede"];
function catalogo(){ if (catalogo.c) return catalogo.c; let c = null; try { const s = document.getElementById("base-servidor-catalogo"); if (s) c = JSON.parse(s.textContent); } catch (e){} if (!c && window.PHYSIS_SERVIDOR_CATALOGO) c = window.PHYSIS_SERVIDOR_CATALOGO; if (c) catalogo.c = c; return c; }
const itensDe = C => { const I = {}; (C.hardware || []).concat(C.software || []).forEach(x => { I[x.id] = x; }); return I; };
function selecaoDoPerfil(C, perfil){ const pf = C && C.perfis && C.perfis[perfil] || {}; return { hardware: Object.assign({}, pf.hardware || {}), software: (pf.software || []).slice(), modelo: Object.assign({}, pf.modelo || {}) }; }
function totais(sel, C){ const I = itensDe(C), hw = Object.keys(sel.hardware || {}).filter(k => I[k] && Math.trunc(n(sel.hardware[k])) > 0).map(k => [I[k], Math.trunc(n(sel.hardware[k]))]), sw = (sel.software || []).filter(k => I[k]).map(k => I[k]);
  const soma = (cats, campo) => hw.filter(([x]) => cats.indexOf(x.cat) >= 0).reduce((s, [x, q]) => s + (x[campo] || 0) * q, 0), plats = hw.filter(([x]) => x.cat === "plataforma"), um = cat => (hw.find(([x]) => x.cat === cat) || [null])[0];
  const fonte = um("fonte"), ups = um("nobreak"), refr = hw.filter(([x]) => x.cat === "refrigeracao").map(([x]) => x), ti = hw.filter(([x]) => CATS_POTENCIA.indexOf(x.cat) >= 0);
  const w = (campo, comFonte) => ti.filter(([x]) => (x.fonte !== false) === comFonte).reduce((s, [x, q]) => s + x[campo] * q, 0), motores = sw.filter(x => x.motor_ia), m = sel.modelo || {};
  return { nucleos: soma(["plataforma","cpu"], "nucleos"), threads: soma(["plataforma","cpu"], "threads"), ram_gb: soma(["plataforma"], "ram_gb") + soma(["ram"], "gb"), ram_max_gb: soma(["plataforma"], "ram_max_gb"), ram_modulos_gb: soma(["ram"], "gb"),
    vram_gb: soma(["gpu"], "vram_gb"), gpus: hw.filter(([x]) => x.cat === "gpu").reduce((s, [, q]) => s + q, 0), disco_tb: soma(["armazenamento"], "tb"), pcie_x16: soma(["plataforma"], "pcie_x16"), pcie_slots: soma(["plataforma"], "pcie_slots"), pcie_usado: soma(["gpu","raid"], "pcie"),
    x86: plats.some(([x]) => x.arch === "x86_64"), arm: plats.some(([x]) => x.arch === "arm64"), plataformas: plats.length, w_ocioso_dc: w("w_ocioso", true), w_pico_dc: w("w_carga", true), w_ocioso_ac: w("w_ocioso", false), w_pico_ac: w("w_carga", false),
    fonte_w: fonte ? fonte.w : 0, fonte_classe: fonte ? fonte.classe80 : null, ups_va: ups ? ups.va : 0, ups_w: ups ? ups.w : 0, ups_wh: ups ? ups.bateria_wh : 0, ups_quimica: ups ? ups.quimica : null, ups_proprio_w: ups ? ups.w_ocioso : 0,
    refrig_cop: Math.max.apply(null, refr.map(x => x.cop || 0).concat([0])), free_cooling: refr.some(x => x.id === "vent_forcada"),
    sw_nucleos: sw.reduce((s, x) => s + (x.nucleos || 0), 0), sw_ram_gb: sw.reduce((s, x) => s + (x.ram_gb || 0), 0) + soma(["raid"], "ram_gb"), sw_disco_gb: sw.reduce((s, x) => s + (x.disco_gb || 0), 0),
    motores_ia: motores.map(x => x.id), vram_modelo_gb: motores.length && n(m.params_b) ? vramGb(n(m.params_b), n(m.bits, 4)) : 0 }; }
function componentesDaSelecao(sel, C){ const I = itensDe(C); return Object.keys(sel.hardware || {}).filter(k => I[k] && CATS_POTENCIA.indexOf(I[k].cat) >= 0 && Math.trunc(n(sel.hardware[k]))).map(k => { const x = I[k], tipo = { gpu:"gpu", armazenamento:"disco", rede:"rede" }[x.cat] || "cpu";
  return { nome:x.nome, tipo, qtd:Math.trunc(n(sel.hardware[k])), w_ocioso:x.w_ocioso, w_carga:x.w_carga, ciclo: tipo === "gpu" ? "" : tipo === "rede" ? 0.5 : 0.3, fonte: x.fonte !== false, id:k }; }); }
const g = v => N(v, Number.isInteger(v) ? 0 : 1);
function compat(sel, C, armBrutoGb, ef){ ef = ef || 0.9; const I = itensDe(C), T = totais(sel, C), hw = Object.keys(sel.hardware || {}).filter(k => I[k] && Math.trunc(n(sel.hardware[k])) > 0), sw = (sel.software || []).filter(k => I[k]), plats = hw.map(k => I[k]).filter(x => x.cat === "plataforma"), r = [];
  const ck = (id, ok, nivel, msg) => r.push({ id, ok:!!ok, nivel, msg });
  ck("plataforma", plats.length, "erro", "Escolha ao menos uma plataforma (a máquina).");
  ck("so", sw.some(k => I[k].cat === "so"), "aviso", "Escolha o sistema operacional.");
  const cpus = hw.map(k => I[k]).filter(x => x.cat === "cpu");
  plats.filter(x => x.encaixe === "desktop" || x.encaixe === "servidor").forEach(x => ck("cpu_" + x.id, cpus.some(c => c.encaixe === x.encaixe), "erro", `${x.nome}: falta o processador do encaixe '${x.encaixe}'.`));
  cpus.forEach(c => ck("encaixe_" + c.id, plats.some(x => x.encaixe === c.encaixe), "erro", `${c.nome} não encaixa em nenhuma plataforma escolhida.`));
  hw.map(k => I[k]).filter(x => x.cat === "ram").forEach(x => { ck("ram_fmt_" + x.id, plats.some(p => p.ram_formato === x.formato), "erro", `${x.nome}: nenhuma plataforma usa esse formato de memória.`); if (plats.some(p => p.ram_ecc) && !x.ecc) ck("ecc_" + x.id, false, "aviso", `${x.nome}: servidor pede memória ECC.`); });
  if (T.ram_max_gb) ck("ram_max", T.ram_modulos_gb <= T.ram_max_gb, "erro", `Memória (${g(T.ram_modulos_gb)} GB) acima do máximo das plataformas (${g(T.ram_max_gb)} GB).`);
  if (T.gpus){ ck("gpu_encaixe", T.pcie_x16 > 0, "erro", "Placa de vídeo pede encaixe PCIe x16: Raspberry Pi e mini PC não recebem placa."); if (T.pcie_x16) ck("pcie_x16", T.gpus <= T.pcie_x16, "erro", `${T.gpus} placas de vídeo para ${T.pcie_x16} encaixes x16.`); }
  ck("pcie", T.pcie_usado <= T.pcie_slots || !T.pcie_usado, "erro", `Placas PCIe (${T.pcie_usado}) acima dos encaixes (${T.pcie_slots}).`);
  sw.forEach(k => { const x = I[k], rq = x.requer || {}; if (rq.x86) ck("x86_" + k, T.x86, "erro", `${x.nome} precisa de processador x86 (não roda no Raspberry Pi).`); if (rq.arm) ck("arm_" + k, T.arm, "erro", `${x.nome} é só para Raspberry Pi.`); if (rq.gpu) ck("gpu_" + k, T.gpus > 0, "erro", `${x.nome} precisa de placa de vídeo.`);
    (x.deps || []).forEach(d => ck("dep_" + k + "_" + d, sw.indexOf(d) >= 0, "erro", `${x.nome} precisa de ${I[d] ? I[d].nome : d}.`)); });
  const ramIa = T.vram_modelo_gb && T.vram_gb < T.vram_modelo_gb ? T.vram_modelo_gb : 0;
  ck("ram", T.ram_gb >= T.sw_ram_gb + ramIa, "erro", `Memória ${g(T.ram_gb)} GB para ${N(T.sw_ram_gb + ramIa, 1)} GB pedidos pelos programas${ramIa ? " e pelo modelo (sem placa suficiente)" : ""}.`);
  ck("nucleos", T.threads >= T.sw_nucleos, "aviso", `${g(T.threads)} threads para ${N(T.sw_nucleos, 1)} núcleos pedidos pelos programas.`);
  if (T.vram_modelo_gb){ const obrig = T.motores_ia.some(k => I[k].gpu === "obrigatoria"); ck("vram", T.vram_gb >= T.vram_modelo_gb, obrig ? "erro" : "aviso", `Modelo pede ${N(T.vram_modelo_gb, 1)} GB de vídeo; a seleção tem ${g(T.vram_gb)} GB${obrig ? "" : " (sem isso, roda na memória, bem mais devagar)"}.`); }
  if (T.w_pico_dc){ if (T.fonte_w) ck("fonte", T.fonte_w >= T.w_pico_dc * 1.3, "erro", `Fonte de ${g(T.fonte_w)} W para pico de ${N(T.w_pico_dc, 0)} W (pede 30% de folga: ${N(T.w_pico_dc * 1.3, 0)} W).`); else if (plats.some(x => x.fonte !== false)) ck("fonte", false, "aviso", "Escolha a fonte do servidor."); }
  const picoAc = T.w_pico_dc / ef + T.w_pico_ac; if (T.ups_w) ck("nobreak", T.ups_w >= picoAc, "erro", `Nobreak de ${g(T.ups_w)} W para pico de ${N(picoAc, 0)} W.`);
  if (armBrutoGb != null) ck("disco", T.disco_tb * 1000 >= armBrutoGb + T.sw_disco_gb, "erro", `Discos com ${g(T.disco_tb)} TB para ${N((armBrutoGb + T.sw_disco_gb) / 1000, 2)} TB pedidos (dados, cópias locais e programas).`);
  return r; }
function kgFabricacaoSelecao(sel, C, S){ const I = itensDe(C); let kg = 0, t = 0; Object.keys(sel.hardware || {}).forEach(k => { const x = I[k], q = Math.trunc(n(sel.hardware[k])); if (!x || !q) return;
  if (x.cat === "plataforma"){ const cl = S.classes[x.classe] || S.classes.mini_pc; kg += cl.kgco2e_fabricacao * q; t += cl.kgco2e_fabricacao * q / 1000 / cl.vida_anos; }
  else if (x.cat === "gpu"){ const gp = S.gpu_placa; kg += gp.kgco2e_fabricacao * q; t += gp.kgco2e_fabricacao * q / 1000 / (gp.vida_anos || 4); } }); return [kg, t]; }
function nobreak(wPico, wMedio, autMin, bateria, tensao, fp, folga, efInv){ fp = fp || 0.9; folga = folga == null ? 0.25 : folga; efInv = efInv || 0.9; const wh = wMedio * autMin / 60 / ((DOD[bateria] || 0.9) * efInv);
  return { va: wPico / fp * (1 + folga), w: wPico * (1 + folga), bateria_wh:wh, bateria_ah: tensao ? wh / tensao : 0 }; }
function solar(kwhDia, hsp, pr, fracao, wMedio, horasNoite, diasNub, bateria, ef){ pr = pr || 0.75; ef = ef || 0.9; const kwp = hsp > 0 && pr > 0 ? kwhDia * fracao / (hsp * pr) : 0;
  return { kwp, bateria_kwh: (wMedio * horasNoite / 1000 + kwhDia * diasNub) * fracao / ((DOD[bateria] || 0.9) * ef), ger_dia_kwh: kwp * hsp * pr }; }
const btuH = w => w * BTU_POR_W, trDe = w => btuH(w) / BTU_POR_TR;
const pueDe = (ti, resf, perdas, ilum) => ti > 0 ? (ti + resf + (perdas || 0) + (ilum || 0)) / ti : 0;
function termico(p, en){ const calor = en.w_medio, cop = n(p.cop, 3) || 3, resf = p.free_cooling ? 0 : calor / cop, perdas = calor * n(p.perdas_ups_pct, 5) / 100;
  return { calor_w:calor, btu_h:btuH(en.w_pico), tr:trDe(en.w_pico), resfriamento_w:resf, pue:pueDe(calor, resf, perdas, n(p.iluminacao_w)), temp_min:18, temp_max:27 }; }
function dimensionar(p, fatorRede, hsp, S, sel, C){ S = S || baseServidor(); const usaSel = !!(sel && C && Object.keys(sel.hardware || {}).length && p.usar_selecao !== false), T = usaSel ? totais(sel, C) : null;
  if (usaSel){ p = Object.assign({}, p, { componentes: componentesDaSelecao(sel, C) }); if (T.ups_wh) p.ups_bateria = T.ups_quimica || p.ups_bateria; if (T.refrig_cop) p.cop = T.refrig_cop; if (T.free_cooling && !T.refrig_cop) p.free_cooling = true; }
  const comp = computacao(p); if (usaSel){ comp.ram_software_gb = T.sw_ram_gb; comp.ram_gb = Math.max(comp.ram_gb, Math.ceil(T.sw_ram_gb * (1 + n(p.folga_pct, 30) / 100))); }
  const arm = armazenamento(p); comp.classe = classeRecomendada(comp.nucleos, comp.ram_gb, !!p.ia_ativa, arm.bruto_gb / 1000);
  const curvas = (C && C.eficiencia_80plus) || {}, net = rede(p, arm), en = energia(p, comp, T ? T.fonte_w : 0, T && T.fonte_classe ? curvas[T.fonte_classe] : null), ter = termico(p, en), ups = nobreak(en.w_pico, en.w_medio, n(p.ups_autonomia_min, 30), p.ups_bateria || "lifepo4", n(p.ups_tensao, 24));
  if (T && T.ups_wh) ups.autonomia_min_selecao = en.w_medio ? T.ups_wh * (DOD[T.ups_quimica || "chumbo"] || 0.5) * 0.9 / en.w_medio * 60 : 0;
  const h = n(p.hsp) || hsp || 0, modo = p.solar_modo || "dedicado", fr = modo === "nenhum" ? 0 : n(p.solar_fracao, 100) / 100;
  const sol = solar(en.kwh_dia, h, n(p.pr, 0.75), fr, en.w_medio, n(p.horas_noite, 14), n(p.dias_nublados, 0), p.ups_bateria || "lifepo4");
  const f = n(p.fator_rede) || fatorRede || 0.0289, kwhAnoInst = en.kwh_dia * 365 * ter.pue, redeKwh = kwhAnoInst * (h > 0 ? 1 - fr : 1);
  const cl = S.classes[comp.classe] || S.classes.mini_pc; let kgFab = cl.kgco2e_fabricacao + (p.ia_ativa ? Math.max(comp.gpus_precisa, Math.trunc(n(p.gpu_qtd))) * S.gpu_placa.kgco2e_fabricacao : 0), tFab = kgFab / 1000 / cl.vida_anos;
  if (usaSel){ const kt = kgFabricacaoSelecao(sel, C, S); kgFab = kt[0]; tFab = kt[1]; }
  const fDc = n(p.fator_dc, f), pueDc = n(p.pue_dc, 1.5), tarifa = n(p.tarifa), capex = n(p.custo_kwp) ? sol.kwp * n(p.custo_kwp) + sol.bateria_kwh * n(p.custo_bat_kwh) : null, econ = tarifa ? (kwhAnoInst - redeKwh) * tarifa : null;
  const carb = { fator:f, kwh_ano:kwhAnoInst, kwh_rede_ano:redeKwh, t_operacao:redeKwh / 1000 * f, t_sem_solar:kwhAnoInst / 1000 * f, kg_fabricacao:kgFab, t_fabricacao_ano:tFab,
    t_datacenter: en.kwh_dia * 365 * pueDc / 1000 * fDc, custo_mes: tarifa ? redeKwh / 12 * tarifa : null, capex_solar:capex, economia_ano:econ, payback_anos: capex && econ ? capex / econ : null };
  const r = { computacao:comp, armazenamento:arm, rede:net, energia:en, nobreak:ups, solar:sol, termico:ter, carbono:carb };
  if (usaSel) r.selecao = { totais:T, compat: compat(sel, C, arm.bruto_gb, en.eficiencia_fonte) }; return r; }

/* ════════ perfis de partida (todos "verificar") ════════ */
const COMP = {
  rpi:{ nome:"Raspberry Pi 5 com SSD", tipo:"cpu", qtd:1, w_ocioso:3.5, w_carga:10, ciclo:0.2, fonte:false },
  mini:{ nome:"Mini PC (processador, memória, SSD)", tipo:"cpu", qtd:1, w_ocioso:8, w_carga:45, ciclo:0.3, fonte:false },
  base_ia:{ nome:"Servidor de IA: placa-mãe, processador e memória", tipo:"cpu", qtd:1, w_ocioso:45, w_carga:150, ciclo:0.3, fonte:true },
  gpu8:{ nome:"Placa de vídeo 8 GB", tipo:"gpu", qtd:2, w_ocioso:12, w_carga:130, ciclo:"", fonte:true },
  nvme:{ nome:"SSD NVMe", tipo:"disco", qtd:2, w_ocioso:1, w_carga:5, ciclo:0.3, fonte:true },
  hdd:{ nome:"Disco rígido 3,5\"", tipo:"disco", qtd:4, w_ocioso:5, w_carga:8, ciclo:0.3, fonte:true },
  x86:{ nome:"Servidor x86 (2 processadores, memória)", tipo:"cpu", qtd:1, w_ocioso:110, w_carga:330, ciclo:0.4, fonte:true },
  sw:{ nome:"Switch de rede", tipo:"rede", qtd:1, w_ocioso:5, w_carga:8, ciclo:0.5, fonte:false },
  rot:{ nome:"Roteador", tipo:"rede", qtd:1, w_ocioso:8, w_carga:12, ciclo:0.5, fonte:false } };
const BASE_P = { nome_local:"", lat:"", lon:"", hsp:"", hsp_base:"critico", fator_rede:"", fator_ano:"", tarifa:"",
  instalacoes:1, usuarios_sim:5, sensores:20, leituras_min:1, retencao_anos:5, req_min:30, bi_usuarios:0, geo_camadas:0, geo_tiles_gb:0, calc_rodadas_dia:0, calc_min_rodada:10, calc_nucleos_rodada:2, docs_dia:10,
  usar_selecao:true, ia_ativa:false, ia_params_b:7, ia_bits:4, ia_tokens_dia:0, ia_usuarios_sim:1, ia_tok_s:"", treino_h_mes:0, treino_modo:"qlora",
  gpu_qtd:0, gpu_vram_gb:8, gpu_alt_qtd:"", gpu_alt_vram_gb:"", folga_pct:30,
  bytes_leitura:200, arquivos_gb_ano:10, modelos_gb:"", raid:"raid1", discos:2, snapshots_pct:20, backup_versoes:7, mudanca_dia_pct:2, backup_mbps:50, janela_backup_h:6,
  usuarios_remotos:2, kbps_usuario:500, sync_mb_dia:100, latencia_ms:40, vpn:true, link_reserva:"4g",
  componentes:[], fonte_80plus:"ouro", ups_autonomia_min:30, ups_bateria:"lifepo4", ups_tensao:24, solar_modo:"dedicado", solar_fracao:100, pr:0.75, horas_noite:14, dias_nublados:1, agendar_ia_solar:true,
  cop:3, free_cooling:false, perdas_ups_pct:5, iluminacao_w:0, rack_u:"", ruido_ok:true, poeira:"filtro",
  fator_dc:"", pue_dc:1.5, custo_kwp:"", custo_bat_kwh:"", custo_hw:"", anos_analise:10, ligar_pegada:false };
const PERFIS = {
  casa_physis:{ nome:"Casa Physis (hub + IA 2×8 GB)", nota:"Hub da plataforma e servidor de IA local com 2 placas de 8 GB; alternativa em estudo pela equipe: 4 placas de 16 GB. Todos os números: verificar.",
    p:{ usuarios_sim:8, sensores:60, leituras_min:1, retencao_anos:10, req_min:60, bi_usuarios:2, geo_camadas:10, geo_tiles_gb:20, calc_rodadas_dia:6, calc_min_rodada:10, docs_dia:30,
      ia_ativa:true, ia_params_b:7, ia_bits:4, ia_tokens_dia:300000, ia_usuarios_sim:3, treino_h_mes:20, gpu_qtd:2, gpu_vram_gb:8, gpu_alt_qtd:4, gpu_alt_vram_gb:16, arquivos_gb_ano:30, usuarios_remotos:5,
      componentes:[COMP.rpi, COMP.base_ia, COMP.gpu8, COMP.nvme, COMP.sw, COMP.rot], ligar_pegada:true } },
  pequena:{ nome:"Pequena empresa / fazenda (Raspberry Pi ou mini PC)", nota:"Monitoramento, plataforma e documentos para poucos usuários.", p:{ usuarios_sim:3, sensores:30, componentes:[COMP.rpi, COMP.rot], raid:"nenhum", discos:1, ups_autonomia_min:120 } },
  escritorio:{ nome:"Escritório com BI e mapas", nota:"Painéis de BI e servidor de mapas para a equipe.", p:{ usuarios_sim:15, bi_usuarios:8, geo_camadas:30, geo_tiles_gb:50, calc_rodadas_dia:10, arquivos_gb_ano:80, usuarios_remotos:10, componentes:[COMP.mini, Object.assign({}, COMP.hdd, { qtd:2 }), COMP.sw, COMP.rot] } },
  ia:{ nome:"Servidor de IA (GPU)", nota:"Modelo de linguagem local para vários usuários.", p:{ ia_ativa:true, ia_params_b:13, ia_bits:4, ia_tokens_dia:1000000, ia_usuarios_sim:8, treino_h_mes:40, gpu_qtd:2, gpu_vram_gb:16, componentes:[COMP.base_ia, Object.assign({}, COMP.gpu8, { nome:"Placa de vídeo 16 GB", w_ocioso:15, w_carga:200 }), COMP.nvme, COMP.sw] } },
  datacenter:{ nome:"Datacenter/colocation", nota:"Máquina em datacenter: sem solar no lugar; use o PUE e o fator da rede do contrato.", p:{ usuarios_sim:50, sensores:500, instalacoes:10, bi_usuarios:10, geo_camadas:20, geo_tiles_gb:100, usuarios_remotos:50, solar_modo:"nenhum", pue_dc:1.5, raid:"raid10", discos:4, componentes:[COMP.x86, Object.assign({}, COMP.nvme, { qtd:4 })] } },
  personalizado:{ nome:"Personalizado", nota:"Comece do zero e preencha tudo.", p:{ componentes:[] } } };
function novoProjeto(perfil, nome){ const pf = PERFIS[perfil] || PERFIS.personalizado; return { id:"sv" + Date.now().toString(36) + Math.floor(Math.random() * 1e4), nome: nome || pf.nome, perfil, criado:new Date().toISOString().slice(0, 10), p: Object.assign(clone(BASE_P), clone(pf.p)), sel: catalogo() ? selecaoDoPerfil(catalogo(), perfil) : { hardware:{}, software:[], modelo:{} } }; }

/* ════════ estado salvo ════════ */
function ler(){ let e = null; try { e = JSON.parse(localStorage.getItem(CHAVE) || "null"); } catch (x){} if (!e || !Array.isArray(e.projetos)) e = { v:1, atual:null, projetos:[] };
  if (!e.projetos.length){ const p = novoProjeto("casa_physis"); e.projetos.push(p); e.atual = p.id; }
  e.projetos.forEach(x => { x.p = Object.assign(clone(BASE_P), x.p || {}); if (!x.sel || typeof x.sel !== "object") x.sel = catalogo() ? selecaoDoPerfil(catalogo(), x.perfil) : { hardware:{}, software:[], modelo:{} }; x.sel.hardware = x.sel.hardware || {}; x.sel.software = x.sel.software || []; x.sel.modelo = x.sel.modelo || {}; }); if (!e.projetos.some(x => x.id === e.atual)) e.atual = e.projetos[0].id; return e; }
function gravar(e){ e.v = 1; try { localStorage.setItem(CHAVE, JSON.stringify(e)); } catch (x){} }
const atual = e => e.projetos.find(x => x.id === e.atual) || e.projetos[0];

/* ════════ dados do lugar e do servidor ════════ */
const EXT = { sol:{}, pegada:null, pegadaQuando:0, pedindo:{} };
function fatorDoProjeto(p){ const m = num(p.fator_rede); if (m != null && m >= 0) return [m, "digitado no projeto"]; const F = baseFatores();
  if (F && F.rede){ const A = F.rede.anual, k = A[p.fator_ano] ? p.fator_ano : F.rede.padrao; return [A[k].valor, A[k].rotulo]; } return [0.0289, "padrão da plataforma"]; }
function solDoProjeto(p){ const h = num(p.hsp); if (h) return [h, "digitado no projeto"]; const la = num(p.lat), lo = num(p.lon); if (la == null || lo == null) return [0, "falta o lugar (latitude e longitude) ou as horas de sol"];
  const k = la.toFixed(2) + "," + lo.toFixed(2), r = EXT.sol[k];
  if (!r && temServidorWeb() && !EXT.pedindo[k]){ EXT.pedindo[k] = true; fetch(`api/gis/irradiacao?lat=${la}&lon=${lo}`, { cache:"no-store", credentials:"same-origin" }).then(x => x.json()).then(j => { EXT.sol[k] = j; redesenhar(); }).catch(() => { EXT.sol[k] = { ok:false }; }); }
  const m = r && r.ponto && r.ponto.meses; if (!m || !m.length) return [0, temServidorWeb() ? "buscando o sol do lugar (NASA POWER, no servidor)…" : "digite as horas de sol pleno (sem servidor)"];
  return p.hsp_base === "media" ? [m.reduce((s, x) => s + x, 0) / m.length, "média anual do lugar (NASA POWER)"] : [Math.min.apply(null, m), "mês com menos sol do lugar (NASA POWER)"]; }
function pegadaReal(){ if (!temServidorWeb() || EXT.pedindo.pegada || (EXT.pegada && Date.now() - EXT.pegadaQuando < 300000)) return EXT.pegada;
  EXT.pedindo.pegada = true; fetch("/api/servidor/pegada", { credentials:"same-origin", cache:"no-store" }).then(r => r.json()).then(j => { EXT.pedindo.pegada = false; EXT.pegadaQuando = Date.now(); EXT.pegada = j && j.ok ? j : { ok:false }; redesenhar(); }).catch(() => { EXT.pedindo.pegada = false; EXT.pegadaQuando = Date.now(); EXT.pegada = { ok:false }; });
  return EXT.pegada; }

/* ════════ peças de tela ════════ */
const idDe = k => "sv-" + String(k).replace(/[^a-zA-Z0-9]+/g, "-");
function campo(p, k, rot, aj, ph){ const id = idDe(k); return `<div><label for="${id}">${rot}</label><input id="${id}" type="text" inputmode="decimal" data-sv-campo="${E(k)}" value="${E(p[k] == null ? "" : p[k])}" placeholder="${E(ph || "")}" style="width:100%"${aj ? ` aria-describedby="${id}-a"` : ""}>${aj ? `<span id="${id}-a" class="t2 pq">${aj}</span>` : ""}</div>`; }
function texto(p, k, rot){ const id = idDe(k); return `<div><label for="${id}">${rot}</label><input id="${id}" type="text" data-sv-campo="${E(k)}" value="${E(p[k] == null ? "" : p[k])}" style="width:100%"></div>`; }
function escolha(p, k, rot, ops){ const id = idDe(k), v = String(p[k] == null ? "" : p[k]); return `<div><label for="${id}">${rot}</label><select id="${id}" data-sv-campo="${E(k)}" style="width:100%">${ops.map(([a, b]) => `<option value="${E(a)}" ${v === String(a) ? "selected" : ""}>${E(b)}</option>`).join("")}</select></div>`; }
function marca(p, k, rot){ const id = idDe(k); return `<div><label for="${id}" style="display:flex;gap:8px;align-items:center;min-height:44px"><input id="${id}" type="checkbox" data-sv-campo="${E(k)}" ${p[k] ? "checked" : ""}> ${rot}</label></div>`; }
const cartao = (id, tit, numero, un, extra) => `<section class="cartao" aria-labelledby="h-${id}"><h3 id="h-${id}" class="t3">${tit}</h3><span class="numero">${numero}</span> <span class="t2">${un}</span>${extra || ""}</section>`;
const tabela = (cap, cab, linhas) => `<div class="rolagem"><table><caption class="so-leitor">${E(cap)}</caption><thead><tr>${cab.map(h => `<th scope="col">${h}</th>`).join("")}</tr></thead><tbody>${linhas.join("")}</tbody></table></div>`;
const verificar = t => `<span class="selo at">verificar</span> <span class="t2 pq">${t}</span>`;
const secao = (id, tit, corpo) => `<section class="cartao" aria-labelledby="h-${id}"><h2 id="h-${id}">${tit}</h2>${corpo}</section>`;
const R$ = v => v == null ? MARC : "R$ " + N(v, 2);

/* ════════ subabas ════════ */
const CATS_HW = [["plataforma","Plataforma"],["cpu","Processador"],["ram","Memória"],["gpu","Placa de vídeo"],["armazenamento","Armazenamento"],["raid","RAID"],["fonte","Fonte de alimentação"],["rede","Rede"],["nobreak","Nobreak"],["solar","Solar"],["refrigeracao","Refrigeração"],["rack","Rack e gabinete"]];
const CATS_SW = [["so","Sistema operacional"],["conteineres","Contêineres"],["physis","Physis"],["banco","Banco de dados"],["ia","IA local"],["bi","BI"],["gis","Mapas"],["calculo","Motores de cálculo"],["documentos","Documentos"],["iot","IoT"],["proxy","Proxy e HTTPS"],["vpn","VPN"],["backup","Cópias"],["monitoramento","Monitoramento"],["seguranca","Segurança"],["colaboracao","Colaboração"]];
function specHw(x){ return [x.arch ? (x.arch === "arm64" ? "ARM" : "x86") : "", x.nucleos ? x.nucleos + "/" + (x.threads || x.nucleos) + " núcleos/threads" : "", x.ram_gb ? x.ram_gb + " GB" : "", x.gb ? x.gb + " GB" + (x.ecc ? " ECC" : "") : "", x.vram_gb ? x.vram_gb + " GB de vídeo · " + x.tflops_fp16 + " TFLOPS FP16 · " + x.conectores : "", x.pcie_x16 != null && x.cat === "plataforma" ? x.pcie_x16 + " encaixes x16" : "", x.tb ? x.tb + " TB" + (x.tbw ? " · " + x.tbw + " TBW" : "") : "", x.cat === "fonte" ? x.w + " W · " + x.classe80 : "", x.va ? x.va + " VA / " + x.w + " W · " + x.bateria_wh + " Wh " + x.quimica + " · " + x.tipo : "", x.capacidade_btu ? x.capacidade_btu + " BTU/h, COP " + N(x.cop, 1) : "", (x.w_ocioso || x.w_carga) && x.cat !== "nobreak" ? N(x.w_ocioso, 1) + " a " + N(x.w_carga, 0) + " W" : "", x.ref_equipamentos ? "base de equipamentos" : ""].filter(Boolean).join(" · "); }
function abaSelecao(p, R, prj){ const C = catalogo(), u = UI();
  if (!C) return `<p class="faixa al" role="alert">O catálogo de módulos não foi carregado. Embuta sistema/physis-servidor-catalogo.json no painel (id base-servidor-catalogo).</p>`;
  const sel = prj.sel, filtro = u.svFiltro || "", busca = String(u.svBusca || "").toLowerCase(), I = itensDe(C), passa = x => (!filtro || x.cat === filtro) && (!busca || (x.nome + " " + x.id + " " + (x.licenca || "")).toLowerCase().indexOf(busca) >= 0);
  const filtros = `<div class="precos"><div><label for="sv-filtro">Mostrar</label><select id="sv-filtro" data-sv-acao="filtro" style="width:100%"><option value="">Todas as categorias</option>${CATS_HW.concat(CATS_SW).map(([k, t]) => `<option value="${k}" ${filtro === k ? "selected" : ""}>${E(t)}</option>`).join("")}</select></div>
    <div><label for="sv-busca">Procurar</label><input id="sv-busca" type="search" data-sv-acao="busca" value="${E(u.svBusca || "")}" style="width:100%"></div>${marca(p, "usar_selecao", "Usar a seleção nas contas (energia, nobreak, térmico, carbono)")}</div>
    <div class="chips"><button type="button" id="sv-sel-perfil" data-sv-acao="sel-perfil">Aplicar a seleção do perfil “${E((PERFIS[prj.perfil] || {}).nome || "")}”</button><button type="button" id="sv-sel-limpar" data-sv-acao="sel-limpar">Limpar a seleção</button></div>`;
  const hw = CATS_HW.map(([cat, tit]) => { const its = (C.hardware || []).filter(x => x.cat === cat && passa(x)); if (!its.length) return "";
    return `<h3 class="t3">${E(tit)}</h3>${tabela(tit, ["Módulo", "Especificação", "Quantidade"], its.map(x => { const id = idDe("hw-" + x.id); return `<tr><th scope="row" style="font-weight:500">${E(x.nome)}${x.verificar ? ' <span class="selo at">verificar</span>' : ""}</th><td class="t2 pq">${E(specHw(x))}${x.nota ? "<br>" + E(x.nota) : ""}</td><td><label class="so-leitor" for="${id}">Quantidade de ${E(x.nome)}</label><input id="${id}" type="number" min="0" step="1" data-sv-hw="${E(x.id)}" value="${E(sel.hardware[x.id] || 0)}" style="width:80px"></td></tr>`; }))}`; }).join("");
  const sw = CATS_SW.map(([cat, tit]) => { const its = (C.software || []).filter(x => x.cat === cat && passa(x)); if (!its.length) return "";
    return `<fieldset><legend class="t3">${E(tit)}</legend>${its.map(x => { const id = idDe("sw-" + x.id); return `<div><label for="${id}" style="display:flex;gap:8px;align-items:flex-start;min-height:44px"><input id="${id}" type="checkbox" data-sv-sw="${E(x.id)}" ${sel.software.indexOf(x.id) >= 0 ? "checked" : ""}> <span>${E(x.nome)} <span class="t2 pq">· ${E(x.licenca)} · ${N(x.nucleos, 1)} núcleo, ${N(x.ram_gb, 1)} GB, ${N(x.disco_gb, 0)} GB de disco${x.deps && x.deps.length ? " · precisa de " + E(x.deps.map(d => (I[d] || { nome:d }).nome).join(", ")) : ""}${x.requer && x.requer.x86 ? " · só x86" : ""}${x.requer && x.requer.gpu ? " · precisa de placa de vídeo" : ""}</span></span></label></div>`; }).join("")}</fieldset>`; }).join("");
  const M = C.modelos || { tamanhos_b:[], bits:[] }, m = sel.modelo || {};
  const modelo = `<div class="precos"><div><label for="sv-mod-params">Modelo aberto (tamanho)</label><select id="sv-mod-params" data-sv-modelo="params_b" style="width:100%"><option value="">Sem modelo</option>${M.tamanhos_b.map(t => `<option value="${t}" ${String(m.params_b) === String(t) ? "selected" : ""}>${t}B</option>`).join("")}</select></div>
    <div><label for="sv-mod-bits">Quantização</label><select id="sv-mod-bits" data-sv-modelo="bits" style="width:100%">${M.bits.map(b => `<option value="${b}" ${String(m.bits || 4) === String(b) ? "selected" : ""}>${b} bits</option>`).join("")}</select></div></div><p class="t2 pq">${E(M.nota || "")}</p>`;
  const S = R.selecao, T = S ? S.totais : (Object.keys(sel.hardware).length ? totais(sel, C) : null), lista = S ? S.compat : [], erros = lista.filter(c => !c.ok && c.nivel === "erro"), avisos = lista.filter(c => !c.ok && c.nivel !== "erro");
  const conf = `<div role="status" aria-live="polite">${!S ? `<p class="t2">${p.usar_selecao === false ? "A seleção está desligada: as contas usam os componentes da aba Energia." : "Escolha os módulos para conferir."}</p>` : erros.length || avisos.length ? `<ul>${erros.map(c => `<li><span class="selo al">erro</span> ${E(c.msg)}</li>`).join("")}${avisos.map(c => `<li><span class="selo at">aviso</span> ${E(c.msg)}</li>`).join("")}</ul>` : `<p><span class="selo ok">tudo compatível</span> ${lista.length} conferências passaram.</p>`}</div>`;
  const tot = T ? `<div class="grade">${cartao("sv-t-cpu", "Processamento", N(T.nucleos, 0) + " / " + N(T.threads, 0), "núcleos / threads", `<span class="t2 pq">programas pedem ${N(T.sw_nucleos, 1)}</span>`)}${cartao("sv-t-ram", "Memória", N(T.ram_gb, 0), "GB", `<span class="t2 pq">programas pedem ${N(T.sw_ram_gb, 1)} GB</span>`)}${cartao("sv-t-vram", "Vídeo", N(T.vram_gb, 0), "GB", `<span class="t2 pq">${N(T.gpus, 0)} placas · modelo pede ${N(T.vram_modelo_gb, 1)} GB</span>`)}${cartao("sv-t-disco", "Disco", N(T.disco_tb, 1), "TB")}${cartao("sv-t-w", "Potência", N(R.energia.w_medio, 0), "W médios na tomada", `<span class="t2 pq">parado ${N(T.w_ocioso_dc + T.w_ocioso_ac, 0)} W · pico ${N(R.energia.w_pico, 0)} W · fonte com ${N(R.energia.eficiencia_fonte * 100, 0)}%</span>`)}</div>` : "";
  return `<p class="t2 apoio">Primeiro passo do projeto: escolha a máquina, as peças e os programas. As somas e as conferências alimentam todas as outras subabas e a lista de materiais.</p>
    ${secao("sv-conf", "Conferências", conf + tot)}${secao("sv-fil", "Filtros", filtros)}${secao("sv-hw", "Hardware", hw || '<p class="t2">Nada com esse filtro.</p>')}${secao("sv-swp", "Programas abertos", sw || '<p class="t2">Nada com esse filtro.</p>')}${secao("sv-mod", "Modelo de IA", modelo)}
    <p class="t2 pq">${verificar("especificações por classe, faixas públicas típicas; custos ficam " + MARC + " até o orçamento")}</p>`; }
function abaCargas(p){ return `<p class="t2 apoio">O que o servidor precisa fazer. Tudo o resto (máquina, disco, energia) sai daqui.</p>
  ${secao("sv-pl", "Plataforma e dados", `<div class="precos">${campo(p, "instalacoes", "Instalações ou clientes hospedados")}${campo(p, "usuarios_sim", "Usuários ao mesmo tempo")}${campo(p, "req_min", "Pedidos por minuto (Gestão e plataforma)")}${campo(p, "sensores", "Sensores (nós V6 e MQTT)")}${campo(p, "leituras_min", "Leituras por minuto de cada sensor")}${campo(p, "retencao_anos", "Guardar os dados por quantos anos")}${campo(p, "docs_dia", "Documentos e PDF/A por dia")}</div>`)}
  ${secao("sv-bi", "Painéis, mapas e cálculos", `<div class="precos">${campo(p, "bi_usuarios", "Usuários de BI (Superset)")}${campo(p, "geo_camadas", "Camadas no servidor de mapas (GeoServer)")}${campo(p, "geo_tiles_gb", "Mapas em blocos (PMTiles), GB")}${campo(p, "calc_rodadas_dia", "Rodadas de cálculo por dia (EnergyPlus, pvlib, SWMM)")}${campo(p, "calc_min_rodada", "Minutos por rodada")}${campo(p, "calc_nucleos_rodada", "Núcleos por rodada")}</div>`)}
  ${secao("sv-ia", "IA local", `${marca(p, "ia_ativa", "Rodar modelo de IA no próprio servidor")}<div class="precos">${escolha(p, "ia_params_b", "Tamanho do modelo", [["3","3 bilhões de parâmetros (3B)"],["7","7B"],["8","8B"],["13","13B"],["14","14B"],["32","32B"],["70","70B"]])}${escolha(p, "ia_bits", "Quantização", [["4","4 bits"],["8","8 bits"],["16","16 bits (sem quantizar)"]])}${campo(p, "ia_tokens_dia", "Tokens por dia")}${campo(p, "ia_usuarios_sim", "Usuários da IA ao mesmo tempo")}${campo(p, "ia_tok_s", "Tokens por segundo (vazio = estimativa)")}${campo(p, "treino_h_mes", "Horas de treino ou ajuste fino por mês")}${escolha(p, "treino_modo", "Tipo de ajuste fino", [["qlora","QLoRA/LoRA (leve)"],["completo","Completo (pesado)"]])}</div>`)}`; }
function abaComputacao(p, R){ const C = R.computacao, S = baseServidor(), tiers = [["rpi5","Raspberry Pi 5: cliente pequeno, até 4 núcleos e 8 GB"],["mini_pc","Mini PC: até 8 núcleos e 64 GB"],["servidor_x86","Servidor x86: acima disso"],["servidor_gpu","Servidor com GPU: IA local"]];
  return `<p class="t2 apoio">Processador, memória e placas de vídeo com folga para crescer.</p>
  ${secao("sv-cp", "Folga e placas de vídeo", `<div class="precos">${campo(p, "folga_pct", "Folga para crescer (%)")}${campo(p, "gpu_qtd", "Placas de vídeo que existem ou estão previstas")}${campo(p, "gpu_vram_gb", "Memória de cada placa (GB)")}${campo(p, "gpu_alt_qtd", "Alternativa: quantas placas")}${campo(p, "gpu_alt_vram_gb", "Alternativa: GB de cada placa")}</div>`)}
  <div class="grade">${cartao("sv-nuc", "Núcleos", N(C.nucleos, 0), "núcleos (threads)")}${cartao("sv-ram", "Memória", N(C.ram_gb, 0), "GB")}${cartao("sv-vram", "Memória de vídeo", N(C.vram_precisa_gb, 1), "GB", `<span class="t2 pq">rodar ${N(C.vram_rodar_gb, 1)} · treinar ${N(C.vram_treino_gb, 1)}</span>`)}${cartao("sv-gpu", "Placas necessárias", N(C.gpus_precisa, 0), "de " + N(n(p.gpu_vram_gb) || 8, 0) + " GB")}</div>
  ${p.ia_ativa ? tabela("Configurações de placas de vídeo", ["Configuração", "Memória de vídeo", "Atende?"], [`<tr><th scope="row">Atual: ${N(n(p.gpu_qtd), 0)} × ${N(n(p.gpu_vram_gb), 0)} GB</th><td>${N(C.vram_atual_gb, 0)} GB</td><td>${C.atende_atual ? '<span class="selo ok">sim</span>' : '<span class="selo al">não</span>'}</td></tr>`].concat(C.atende_alt == null ? [] : [`<tr><th scope="row">Alternativa: ${N(n(p.gpu_alt_qtd), 0)} × ${N(n(p.gpu_alt_vram_gb), 0)} GB</th><td>${N(C.vram_alt_gb, 0)} GB</td><td>${C.atende_alt ? '<span class="selo ok">sim</span>' : '<span class="selo al">não</span>'}</td></tr>`])) : ""}
  <p class="t2 pq">Regra prática da memória de vídeo: bilhões de parâmetros × bytes por parâmetro (4 bits = 0,5 byte) × 1,2. Ajuste fino leve (QLoRA) pede cerca de 1,5 vez isso; completo, 16 bytes por parâmetro. A IA ocupa a placa cerca de ${N(C.h_ia_dia, 1)} h por dia (${N(C.tok_s, 0)} tokens/s). ${verificar("regras práticas Physis; confirmar com teste do modelo escolhido")}</p>
  ${secao("sv-tier", "Configuração recomendada", `<ul>${tiers.map(([k, t]) => `<li>${k === C.classe ? "<strong>" + E(t) + " ← recomendada</strong>" : E(t)}</li>`).join("")}</ul><p class="t2 pq">${E((S.classes[C.classe] || {}).nome || "")}</p>`)}`; }
function abaArmazenamento(p, R){ const A = R.armazenamento;
  return `<p class="t2 apoio">Quanto disco, como espelhar e onde guardar as cópias (regra 3-2-1: 3 cópias, 2 mídias, 1 fora do lugar, criptografada).</p>
  ${secao("sv-ar", "Dados e discos", `<div class="precos">${campo(p, "bytes_leitura", "Bytes por leitura guardada (com índice)")}${campo(p, "arquivos_gb_ano", "Arquivos e anexos por ano (GB)")}${campo(p, "modelos_gb", "Modelos de IA (GB, vazio = estimativa)")}${escolha(p, "raid", "Espelhamento (RAID)", [["nenhum","Sem RAID"],["raid1","RAID 1 (espelho)"],["raid5","RAID 5"],["raid6","RAID 6"],["raid10","RAID 10"]])}${campo(p, "discos", "Quantos discos")}${campo(p, "snapshots_pct", "Espaço para fotos do disco (snapshots, %)")}${campo(p, "backup_versoes", "Versões guardadas fora")}${campo(p, "mudanca_dia_pct", "Dados que mudam por dia (%)")}${campo(p, "backup_mbps", "Velocidade para restaurar (Mbps)")}</div>`)}
  ${tabela("Armazenamento", ["Item", "GB"], [["Leituras dos sensores", A.banco_gb], ["Arquivos e anexos", A.arquivos_gb], ["Mapas (PMTiles)", A.tiles_gb], ["Modelos de IA", A.modelos_gb], ["Útil com folga (com sistema)", A.util_gb], ["Fotos do disco", A.snapshots_gb], ["Disco bruto com RAID", A.bruto_gb], ["Cópia criptografada fora do lugar", A.backup_fora_gb]].map(([a, b]) => `<tr><th scope="row">${a}</th><td>${N(b, 1)}</td></tr>`))}
  <p class="t2 pq">Restaurar tudo da cópia de fora leva cerca de ${N(A.restauro_h, 1)} h. Teste a restauração a cada 6 meses.</p>`; }
function abaRede(p, R){ const Q = R.rede;
  return `<p class="t2 apoio">Internet que o servidor precisa para os usuários de fora, a sincronia e as cópias.</p>
  ${secao("sv-rd", "Uso da internet", `<div class="precos">${campo(p, "usuarios_remotos", "Usuários de fora ao mesmo tempo")}${campo(p, "kbps_usuario", "kbit/s por usuário")}${campo(p, "sync_mb_dia", "Sincronia com outros servidores (MB por dia)")}${campo(p, "janela_backup_h", "Horas da noite para a cópia")}${campo(p, "latencia_ms", "Latência medida (ms)")}${marca(p, "vpn", "Acesso pela VPN (sem portas abertas)")}${escolha(p, "link_reserva", "Link reserva", [["nenhum","Nenhum"],["4g","4G/5G"],["fibra2","Segunda fibra"],["satelite","Satélite"]])}</div>`)}
  <div class="grade">${cartao("sv-up", "Subida", N(Q.subida_mbps, 1), "Mbps")}${cartao("sv-dn", "Descida", N(Q.descida_mbps, 1), "Mbps")}${cartao("sv-bk", "Cópia por dia", N(Q.backup_dia_gb, 2), "GB")}</div>
  <p class="t2 pq">${Q.latencia_ok ? "Latência boa para uso interativo." : "Latência alta: telas lentas para quem está fora; avalie servidor mais perto dos usuários."} ${p.link_reserva === "nenhum" ? "Sem link reserva: o lugar fica sem acesso remoto se a internet cair (o hub continua coletando)." : ""}</p>`; }
function abaEnergia(p, R){ const En = R.energia, U = R.nobreak, So = R.solar, sol = solDoProjeto(p), comps = p.componentes || [];
  const linhas = comps.map((c, i) => { const f = (k, rot, w) => { const id = idDe("c" + i + k); return `<td><label class="so-leitor" for="${id}">${rot} (linha ${i + 1})</label><input id="${id}" type="text" ${w ? 'inputmode="decimal"' : ""} data-sv-comp="${i}.${k}" value="${E(c[k] == null ? "" : c[k])}" style="width:100%;min-width:${w ? 64 : 160}px"></td>`; };
    const tid = idDe("c" + i + "tipo"), fid = idDe("c" + i + "fonte");
    return `<tr>${f("nome", "Componente")}<td><label class="so-leitor" for="${tid}">Tipo (linha ${i + 1})</label><select id="${tid}" data-sv-comp="${i}.tipo">${[["cpu","Processador e placa"],["gpu","Placa de vídeo"],["disco","Disco"],["rede","Rede"],["outro","Outro"]].map(([a, b]) => `<option value="${a}" ${c.tipo === a ? "selected" : ""}>${b}</option>`).join("")}</select></td>${f("qtd", "Quantidade", 1)}${f("w_ocioso", "W parado", 1)}${f("w_carga", "W em carga", 1)}${f("ciclo", "Tempo em carga (0 a 1)", 1)}<td><label class="so-leitor" for="${fid}">Passa pela fonte do servidor (linha ${i + 1})</label><input id="${fid}" type="checkbox" data-sv-comp="${i}.fonte" ${c.fonte !== false ? "checked" : ""}></td><td>${N((En.linhas[i] || {}).w_medio, 1)}</td><td><button type="button" id="${idDe("c" + i + "x")}" data-sv-acao="comp-del" data-sv-i="${i}" aria-label="Remover ${E(c.nome || "componente " + (i + 1))}">Remover</button></td></tr>`; });
  const usaSel = !!R.selecao;
  return `<p class="t2 apoio">Potência de cada peça, energia do mês, nobreak e energia solar.</p>
  ${usaSel ? `<p class="faixa in" role="note">As contas usam as peças da Seleção de módulos (${En.linhas.length} linhas, fonte com ${N(En.eficiencia_fonte * 100, 0)}% de eficiência na carga média). A lista abaixo só vale com a seleção desligada.</p>` : ""}
  ${secao("sv-cm", usaSel ? "Componentes (lista manual, sem uso agora)" : "Componentes", `${comps.length ? tabela("Componentes do servidor", ["Componente", "Tipo", "Qtd.", "W parado", "W em carga", "Tempo em carga", "Fonte de alimentação", "W médio", '<span class="so-leitor">Ações</span>'], linhas) : '<p class="t2">Nenhum componente ainda.</p>'}
    <button type="button" id="sv-comp-add" data-sv-acao="comp-add">Acrescentar componente</button><p class="t2 pq">Tempo em carga vazio na placa de vídeo = calculado pela IA (${N(En.ciclo_ia * 100, 0)}% do dia). ${verificar("potências de ficha técnica; meça na tomada quando puder")}</p>
    <div class="precos">${escolha(p, "fonte_80plus", "Eficiência da fonte (80 PLUS)", [["sem","Sem selo (80%)"],["bronze","Bronze (85%)"],["prata","Prata (88%)"],["ouro","Ouro (90%)"],["platina","Platina (92%)"],["titanio","Titânio (94%)"]])}</div>`)}
  <div class="grade">${cartao("sv-wm", "Potência média", N(En.w_medio, 0), "W", `<span class="t2 pq">pico ${N(En.w_pico, 0)} W</span>`)}${cartao("sv-kd", "Energia", N(En.kwh_dia, 2), "kWh por dia")}${cartao("sv-km", "Energia", N(En.kwh_mes, 1), "kWh por mês")}</div>
  ${secao("sv-ups", "Nobreak", `<div class="precos">${campo(p, "ups_autonomia_min", "Autonomia (minutos)")}${escolha(p, "ups_bateria", "Bateria", [["lifepo4","Lítio (LiFePO4)"],["chumbo","Chumbo-ácido"]])}${escolha(p, "ups_tensao", "Tensão do banco (V)", [["12","12 V"],["24","24 V"],["48","48 V"]])}</div>
    <p>Nobreak de ${N(U.va, 0)} VA (${N(U.w, 0)} W) e banco de ${N(U.bateria_wh, 0)} Wh (${N(U.bateria_ah, 0)} Ah em ${N(n(p.ups_tensao, 24), 0)} V).</p>${U.autonomia_min_selecao != null ? `<p>Nobreak escolhido na seleção: cerca de ${N(U.autonomia_min_selecao, 0)} minutos de autonomia na potência média.</p>` : ""}<p class="t2 pq">Lítio usa 90% da carga e dura mais ciclos; chumbo usa 50%, é mais barato e mais pesado.</p>`)}
  ${secao("sv-sol", "Energia solar", `<div class="precos">${escolha(p, "solar_modo", "Energia solar", [["dedicado","Sistema só para o servidor"],["compartilhado","Parte do sistema do lugar"],["nenhum","Sem solar"]])}${campo(p, "solar_fracao", "Parte da energia do servidor coberta (%)")}${campo(p, "hsp", "Horas de sol pleno (kWh/m²·dia), vazio = do lugar")}${escolha(p, "hsp_base", "Sol do lugar", [["critico","Mês com menos sol (seguro)"],["media","Média do ano"]])}${campo(p, "pr", "Desempenho do sistema (PR)")}${campo(p, "horas_noite", "Horas sem sol por dia")}${campo(p, "dias_nublados", "Dias nublados de autonomia")}${marca(p, "agendar_ia_solar", "Agendar treinos de IA nas horas de sol")}</div>
    <p>${p.solar_modo === "nenhum" ? "Sem energia solar." : `${N(So.kwp, 2)} kWp de painéis e ${N(So.bateria_kwh, 1)} kWh de bateria útil.`} <span class="t2 pq">Sol: ${N(sol[0], 2)} kWh/m²·dia (${E(sol[1])}).</span></p>
    ${window.SOLAR ? `<p class="t2 pq">No modo compartilhado, some ${N(R.energia.kwh_dia * 365, 0)} kWh por ano ao consumo da aba Energia solar.</p>` : ""}`)}`; }
function abaTermico(p, R){ const T = R.termico;
  return `<p class="t2 apoio">Todo watt do servidor vira calor na sala.</p>
  ${secao("sv-tm", "Sala do servidor", `<div class="precos">${campo(p, "cop", "Eficiência do ar-condicionado (COP)")}${marca(p, "free_cooling", "Ventilação com ar de fora (free cooling), sem ar-condicionado")}${campo(p, "perdas_ups_pct", "Perdas do nobreak e da distribuição (%)")}${campo(p, "iluminacao_w", "Iluminação e outros na sala (W)")}${texto(p, "rack_u", "Espaço no rack (U) ou local")}${escolha(p, "poeira", "Poeira", [["filtro","Filtro na entrada de ar"],["limpo","Sala limpa"],["sujo","Ambiente com poeira (fazenda, obra)"]])}${marca(p, "ruido_ok", "Ruído aceitável no lugar")}</div>`)}
  <div class="grade">${cartao("sv-cal", "Calor no pico", N(T.btu_h, 0), "BTU/h", `<span class="t2 pq">${N(T.tr, 3)} TR</span>`)}${cartao("sv-res", "Ar-condicionado", N(T.resfriamento_w, 0), "W elétricos")}${cartao("sv-pue", "PUE", N(T.pue, 2), "energia total ÷ energia de TI")}</div>
  <p class="t2 pq">Faixa de entrada de ar recomendada: ${T.temp_min} a ${T.temp_max} °C, umidade sem condensação (orientações térmicas ASHRAE TC 9.9, classe A1, em palavras próprias). ${window.CARGA_TERMICA ? "Lance o calor do servidor como carga interna na aba Carga térmica." : ""} ${verificar("conferir a classe do equipamento na ficha técnica")}</p>`; }
function abaCarbono(p, R){ const C = R.carbono, f = fatorDoProjeto(p), F = baseFatores(), anos = F && F.rede ? Object.keys(F.rede.anual) : [];
  const inv = C.capex_solar && C.economia_ano && typeof analiseInvest === "function" ? analiseInvest(C.capex_solar, C.economia_ano / 12, n(p.anos_analise, 10), 10, 4) : null;
  return `<p class="t2 apoio">Carbono da operação (energia), da fabricação das máquinas e os custos. Fator da rede do lugar do projeto.</p>
  ${secao("sv-lg", "Lugar do projeto", `<div class="precos">${texto(p, "nome_local", "Lugar")}${campo(p, "lat", "Latitude")}${campo(p, "lon", "Longitude")}${escolha(p, "fator_ano", "Fator da rede (SIN)", [["", "Padrão da plataforma"]].concat(anos.map(k => [k, F.rede.anual[k].rotulo + " · " + N(F.rede.anual[k].valor, 4)])))}${campo(p, "fator_rede", "Ou fator digitado (tCO₂/MWh)")}${campo(p, "tarifa", "Tarifa de energia (R$/kWh)")}</div>${typeof ui !== "undefined" && ui && ui.clima && ui.clima.local ? `<button type="button" id="sv-usar-lugar" data-sv-acao="lugar">Usar o lugar da plataforma</button>` : ""}`)}
  ${secao("sv-cmp", "Comparar com datacenter ou nuvem", `<div class="precos">${campo(p, "fator_dc", "Fator da rede da região do datacenter (tCO₂/MWh)")}${campo(p, "pue_dc", "PUE do datacenter")}${campo(p, "custo_kwp", "Custo do solar (R$/kWp)", "vazio = " + MARC)}${campo(p, "custo_bat_kwh", "Custo da bateria (R$/kWh)", "vazio = " + MARC)}${campo(p, "anos_analise", "Anos da análise")}</div>`)}
  ${tabela("Carbono e custos", ["Item", "Valor"], [["Fator da rede", N(C.fator, 4) + " tCO₂/MWh (" + E(f[1]) + ")"], ["Energia por ano (com PUE)", N(C.kwh_ano, 0) + " kWh"], ["Energia da rede por ano (depois do solar)", N(C.kwh_rede_ano, 0) + " kWh"], ["Operação no lugar", N(C.t_operacao, 3) + " tCO₂e por ano"], ["Operação sem solar", N(C.t_sem_solar, 3) + " tCO₂e por ano"], ["No datacenter", N(C.t_datacenter, 3) + " tCO₂e por ano"], ["Fabricação (escopo 3, cat. 2)", N(C.kg_fabricacao, 0) + " kgCO₂e, " + N(C.t_fabricacao_ano, 3) + " tCO₂e por ano"], ["Energia da rede por mês", R$(C.custo_mes)], ["Investimento no solar e bateria", R$(C.capex_solar)], ["Economia por ano", R$(C.economia_ano)], ["Retorno simples", C.payback_anos != null ? N(C.payback_anos, 1) + " anos" : MARC]].concat(inv && inv.descontado != null ? [["Retorno descontado", N(inv.descontado / 12, 1) + " anos"]] : []).map(([a, b]) => `<tr><th scope="row">${a}</th><td>${b}</td></tr>`))}
  <p class="t2 pq">Mesmas regras da aba Carbono: energia no escopo 2 (máquina própria) e fabricação no escopo 3, categoria 2, dividida pelos anos de uso. ${verificar("carbono de fabricação por classe de máquina, ordem de grandeza")}</p>`; }
function bomSelecao(sel){ const C = catalogo(), I = C ? itensDe(C) : {}; return Object.keys(sel.hardware || {}).filter(k => I[k] && Math.trunc(n(sel.hardware[k]))).map(k => { const x = I[k];
  const esp = [x.nucleos ? x.nucleos + " núcleos" : "", x.gb ? x.gb + " GB" : "", x.vram_gb ? x.vram_gb + " GB de vídeo, " + x.tdp_w + " W" : "", x.tb ? x.tb + " TB" + (x.tbw ? ", " + x.tbw + " TBW" : "") : "", x.w && x.cat === "fonte" ? x.w + " W, " + x.classe80 : "", x.va ? x.va + " VA / " + x.w + " W, " + x.bateria_wh + " Wh" : "", x.capacidade_btu ? x.capacidade_btu + " BTU/h" : "", x.u ? x.u + "U" : ""].filter(Boolean).join(" · ");
  return [x.nome, esp || x.cat, Math.trunc(n(sel.hardware[k])), x.custo]; }); }
function bom(p, R){ const C = R.computacao, A = R.armazenamento, S = baseServidor(), it = [[(S.classes[C.classe] || {}).nome || C.classe, `${C.nucleos} núcleos, ${C.ram_gb} GB de memória`, 1]];
  if (p.ia_ativa) it.push(["Placa de vídeo para IA", N(n(p.gpu_vram_gb) || 8, 0) + " GB cada", Math.max(C.gpus_precisa, Math.trunc(n(p.gpu_qtd)))]);
  it.push(["SSD ou disco", N(A.bruto_gb / Math.max(1, n(p.discos, 2)), 0) + " GB cada, " + (p.raid || "raid1").toUpperCase(), Math.trunc(n(p.discos, 2))], ["Cópia fora do lugar, criptografada", N(A.backup_fora_gb, 0) + " GB", 1], ["Nobreak", N(R.nobreak.va, 0) + " VA, " + N(R.nobreak.bateria_wh, 0) + " Wh", 1]);
  if (p.solar_modo !== "nenhum" && R.solar.kwp) it.push(["Painéis solares e inversor", N(R.solar.kwp, 2) + " kWp", 1], ["Bateria solar", N(R.solar.bateria_kwh, 1) + " kWh úteis", 1]);
  if (p.link_reserva && p.link_reserva !== "nenhum") it.push(["Link reserva", p.link_reserva, 1]);
  return it; }
const PRATICAS = ["Limite de potência (power capping) nas placas de vídeo e no processador", "Suspender ou desligar a placa de vídeo parada", "Agendar treinos e cálculos pesados nas horas de sol", "Fonte 80 PLUS Ouro ou melhor", "SSD em vez de disco rígido", "Virtualização e contêineres: menos máquinas meio paradas", "Hibernar o que não precisa ficar ligado à noite", "Medir na tomada e comparar com o dimensionado", "Usar até o fim da vida útil e reciclar com empresa certificada"];
function abaResultado(p, R, prj){ const pg = p.ligar_pegada ? pegadaReal() : null, med = pg && pg.ok && pg.total ? pg.total.kwh_mes : null, itens = R.selecao ? bomSelecao(prj.sel) : bom(p, R).map(x => x.concat([MARC]));
  return `<p class="t2 apoio">Relatório do dimensionamento para entregar ao cliente: imprima, use “Baixar esta tela” ou exporte o projeto.</p>
  <article class="cartao" aria-labelledby="h-sv-rel"><h2 id="h-sv-rel">Relatório de dimensionamento · ${E(prj.nome)}</h2><p class="t2 pq">Physis · Servidor verde · ${E(new Date().toISOString().slice(0, 10))} · perfil: ${E((PERFIS[prj.perfil] || {}).nome || prj.perfil)}${p.nome_local ? " · " + E(p.nome_local) : ""}</p>
  <div class="grade">${cartao("sv-r1", "Máquina", E(C_NOME(R)), "")}${cartao("sv-r2", "Energia", N(R.energia.kwh_mes, 1), "kWh por mês")}${cartao("sv-r3", "Carbono", N(R.carbono.t_operacao + R.carbono.t_fabricacao_ano, 3), "tCO₂e por ano")}${cartao("sv-r4", "Solar", N(R.solar.kwp, 2), "kWp")}</div>
  <h3 class="t3">Lista de materiais (classes genéricas)</h3>${tabela("Lista de materiais", ["Item", "Especificação", "Qtd.", "Custo"], itens.map(([a, b, q, custo], i) => `<tr><th scope="row">${E(a)}</th><td>${E(b)}</td><td>${N(q, 0)}</td><td>${i === 0 && n(p.custo_hw) ? R$(n(p.custo_hw)) : E(custo || MARC)}</td></tr>`))}${R.selecao ? `<p class="t2 pq">Programas: ${E((prj.sel.software || []).map(k => (itensDe(catalogo())[k] || { nome:k }).nome).join(", "))}.</p>` : ""}
  <div class="precos">${campo(p, "custo_hw", "Custo da máquina principal (R$), se já orçado")}</div>
  <h3 class="t3">Boas práticas</h3><ul>${PRATICAS.map(x => `<li>${E(x)}</li>`).join("")}</ul>
  ${secao("sv-med", "Medição real", `${marca(p, "ligar_pegada", "Comparar com a pegada medida deste servidor (aba Carbono)")}${p.ligar_pegada ? (med != null ? `<p>Dimensionado ${N(R.energia.kwh_mes, 1)} kWh por mês × medido ${N(med, 1)} kWh por mês (${N((R.energia.kwh_mes / med - 1) * 100, 0)}% de diferença).</p>` : `<p class="t2">${temServidorWeb() ? "Sem dado do servidor ainda (precisa de sessão)." : "Abra pelo servidor Physis para comparar."}</p>`) : ""}`)}
  <p class="t2 pq">${verificar("dimensionamento por regras práticas; confirmar com medição e ficha técnica antes da compra. Custos sem orçamento ficam como " + MARC + ".")}</p></article>
  <div class="chips"><button type="button" id="sv-imprimir" data-sv-acao="imprimir">Imprimir</button><button type="button" id="sv-exportar" data-sv-acao="exportar">Exportar projetos (JSON)</button><label for="sv-importar" class="botao">Importar projetos (JSON)</label><input id="sv-importar" type="file" accept="application/json,.json" data-sv-acao="importar"></div>`; }
const C_NOME = R => (baseServidor().classes[R.computacao.classe] || {}).nome || R.computacao.classe;

function metodologia(){ return `<details><summary class="t2">Metodologia e normas</summary><ul>
  <li>Memória de vídeo, núcleos e memória: regras práticas Physis (parâmetros × bytes × 1,2; serviços somados com folga).</li>
  <li>Energia: potência parada e em carga × tempo em carga, dividida pela eficiência da fonte (selos 80 PLUS).</li>
  <li>Solar: energia do dia ÷ (horas de sol pleno × desempenho), com o sol do lugar do projeto (NASA POWER, guardado no servidor).</li>
  <li>Calor: 1 W = 3,412 BTU/h; 12.000 BTU/h = 1 TR. PUE = energia total ÷ energia de TI. Faixa térmica: orientações ASHRAE TC 9.9.</li>
  <li>Carbono: GHG Protocol (escopo 2 e escopo 3, categoria 2), Orientação Setorial de TIC do GHG Protocol e Recomendação ITU-T L.1450; mesmo fator da rede do Carbono.</li>
  <li>Cópias: regra 3-2-1 (três cópias, duas mídias, uma fora do lugar).</li></ul><p class="t2 pq">Resumos com palavras próprias da Physis.</p></details>`; }

/* ════════ tela inteira ════════ */
function tela(){ const e = ler(), prj = atual(e), p = prj.p, u = UI(), sub = SUBS.some(s => s[0] === u.svAba) ? u.svAba : "selecao";
  const [f] = fatorDoProjeto(p), [h] = solDoProjeto(p), R = dimensionar(p, f, h, null, prj.sel, catalogo());
  const barra = `<section class="cartao" aria-labelledby="h-sv-prj"><h2 id="h-sv-prj">Projeto</h2><div class="precos">
    <div><label for="sv-projeto">Projeto aberto</label><select id="sv-projeto" data-sv-acao="abrir" style="width:100%">${e.projetos.map(x => `<option value="${E(x.id)}" ${x.id === prj.id ? "selected" : ""}>${E(x.nome)}</option>`).join("")}</select></div>
    <div><label for="sv-nome">Nome do projeto</label><input id="sv-nome" type="text" data-sv-acao="renomear" value="${E(prj.nome)}" style="width:100%"></div>
    <div><label for="sv-perfil">Perfil para um projeto novo</label><select id="sv-perfil" style="width:100%">${Object.keys(PERFIS).map(k => `<option value="${k}">${E(PERFIS[k].nome)}</option>`).join("")}</select></div></div>
    <div class="chips"><button type="button" id="sv-novo" data-sv-acao="novo">Novo projeto</button><button type="button" id="sv-duplicar" data-sv-acao="duplicar">Duplicar</button><button type="button" id="sv-apagar" data-sv-acao="apagar">Apagar</button></div>
    <p class="t2 pq">${E((PERFIS[prj.perfil] || {}).nota || "")} ${verificar("valores de partida do perfil")}</p></section>`;
  const chips = `<div class="chips" role="group" aria-label="Partes do Servidor verde">${SUBS.map(([k, t]) => `<button type="button" id="sv-aba-${k}" data-sv-aba="${k}" aria-pressed="${k === sub}">${E(t)}</button>`).join("")}</div>`;
  const corpo = { selecao:abaSelecao, cargas:abaCargas, computacao:abaComputacao, armazenamento:abaArmazenamento, rede:abaRede, energia:abaEnergia, termico:abaTermico, carbono:abaCarbono, resultado:abaResultado }[sub](p, R, prj);
  const dev = window.SERVIDOR_VERDE_PRONTO === true ? "" : `<p><span class="selo at">Em desenvolvimento</span> <span class="t2 pq">Módulo em construção: use para estudo e confira tudo antes de entregar.</span></p>`;
  return `<h1>Servidor verde</h1>${dev}<p class="t2 apoio">Dimensione um servidor com pouca pegada para qualquer projeto: máquina, disco, rede, energia com nobreak e solar, calor, carbono e custos.</p>${barra}${chips}${corpo}${metodologia()}`; }

/* ════════ eventos: um ouvinte guardado por tipo ════════ */
const redesenhar = () => { if (typeof desenhar === "function") desenhar(false); };
function refocar(id){ const x = pegar(id); if (x && x.focus) x.focus(); }
function mudar(fn, foco){ const e = ler(); fn(e, atual(e)); gravar(e); redesenhar(); if (foco) refocar(foco); }
function baixar(nome, texto){ try { const b = new Blob([texto], { type:"application/json" }), a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = nome; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500); } catch (x){} }
function importar(texto){ let j; try { j = JSON.parse(texto); } catch (x){ return "arquivo inválido"; } const lista = Array.isArray(j) ? j : j && Array.isArray(j.projetos) ? j.projetos : null; if (!lista) return "sem projetos no arquivo";
  const e = ler(); let k = 0; lista.forEach(x => { if (!x || typeof x !== "object" || typeof x.p !== "object") return; const novo = { id:"sv" + Date.now().toString(36) + (k++), nome:String(x.nome || "Projeto importado").slice(0, 120), perfil: PERFIS[x.perfil] ? x.perfil : "personalizado", criado:String(x.criado || "").slice(0, 10), p: Object.assign(clone(BASE_P), x.p), sel: x.sel && typeof x.sel === "object" ? x.sel : undefined }; e.projetos.push(novo); e.atual = novo.id; });
  gravar(e); return k ? "" : "nenhum projeto válido"; }
if (typeof document !== "undefined" && !window.__svEventos){ window.__svEventos = true;
  document.addEventListener("change", ev => { const t = ev.target; if (!t || !t.dataset) return;
    if (t.dataset.svCampo != null){ const k = t.dataset.svCampo; mudar((e, prj) => { prj.p[k] = t.type === "checkbox" ? t.checked : t.value.trim(); }, t.id); return; }
    if (t.dataset.svComp != null){ const [i, k] = t.dataset.svComp.split("."); mudar((e, prj) => { const c = (prj.p.componentes || [])[+i]; if (c) c[k] = t.type === "checkbox" ? t.checked : t.value.trim(); }, t.id); return; }
    if (t.dataset.svHw != null){ const k = t.dataset.svHw, q = Math.max(0, Math.trunc(n(t.value))); mudar((e, prj) => { if (q) prj.sel.hardware[k] = q; else delete prj.sel.hardware[k]; }, t.id); return; }
    if (t.dataset.svSw != null){ const k = t.dataset.svSw; mudar((e, prj) => { prj.sel.software = prj.sel.software.filter(x => x !== k); if (t.checked) prj.sel.software.push(k); }, t.id); return; }
    if (t.dataset.svModelo != null){ const k = t.dataset.svModelo; mudar((e, prj) => { const v = num(t.value); if (v == null) delete prj.sel.modelo[k]; else prj.sel.modelo[k] = v; }, t.id); return; }
    const a = t.dataset.svAcao;
    if (a === "filtro"){ UI().svFiltro = t.value; redesenhar(); refocar(t.id); return; }
    if (a === "busca"){ UI().svBusca = t.value; redesenhar(); refocar(t.id); return; }
    if (a === "abrir"){ mudar(e => { e.atual = t.value; }, t.id); return; }
    if (a === "renomear"){ mudar((e, prj) => { prj.nome = t.value.trim().slice(0, 120) || prj.nome; }, t.id); return; }
    if (a === "importar" && t.files && t.files[0]){ const r = new FileReader(); r.onload = () => { const erro = importar(String(r.result || "")); redesenhar(); if (erro && typeof alert === "function") alert(erro); }; r.readAsText(t.files[0]); } });
  document.addEventListener("click", ev => { const b = ev.target && ev.target.closest ? ev.target.closest("button") : null; if (!b || !b.dataset) return;
    if (b.dataset.svAba){ UI().svAba = b.dataset.svAba; redesenhar(); refocar("sv-aba-" + b.dataset.svAba); return; }
    const a = b.dataset.svAcao; if (!a) return;
    if (a === "novo"){ const s = pegar("sv-perfil"), pf = s ? s.value : "personalizado"; mudar(e => { const x = novoProjeto(pf); e.projetos.push(x); e.atual = x.id; }, "sv-nome"); return; }
    if (a === "duplicar"){ mudar((e, prj) => { const x = clone(prj); x.id = "sv" + Date.now().toString(36); x.nome = prj.nome + " (cópia)"; e.projetos.push(x); e.atual = x.id; }, "sv-nome"); return; }
    if (a === "apagar"){ const e0 = ler(), prj0 = atual(e0); if (typeof confirm === "function" && !confirm("Apagar o projeto “" + prj0.nome + "”? Não dá para desfazer (exporte antes, se quiser guardar).")) return;
      mudar(e => { e.projetos = e.projetos.filter(x => x.id !== prj0.id); if (!e.projetos.length){ const x = novoProjeto("personalizado"); e.projetos.push(x); } e.atual = e.projetos[0].id; }, "sv-projeto"); return; }
    if (a === "sel-perfil"){ mudar((e, prj) => { if (catalogo()) prj.sel = selecaoDoPerfil(catalogo(), prj.perfil); }, b.id); return; }
    if (a === "sel-limpar"){ mudar((e, prj) => { prj.sel = { hardware:{}, software:[], modelo:{} }; }, b.id); return; }
    if (a === "comp-add"){ mudar((e, prj) => { (prj.p.componentes = prj.p.componentes || []).push({ nome:"", tipo:"outro", qtd:1, w_ocioso:"", w_carga:"", ciclo:"", fonte:true }); }, idDe("c" + ((atual(ler()).p.componentes || []).length) + "nome")); return; }
    if (a === "comp-del"){ const i = +b.dataset.svI; mudar((e, prj) => { prj.p.componentes.splice(i, 1); }, "sv-comp-add"); return; }
    if (a === "lugar"){ mudar((e, prj) => { const L = ui.clima.local; prj.p.lat = String(L.lat); prj.p.lon = String(L.lon); if (L.nome) prj.p.nome_local = L.nome; }, "sv-usar-lugar"); return; }
    if (a === "imprimir"){ if (typeof print === "function") print(); return; }
    if (a === "exportar"){ const e = ler(); baixar("servidor-verde-projetos.json", JSON.stringify({ v:1, exportado:new Date().toISOString(), projetos:e.projetos }, null, 2)); } }); }

window.SERVIDOR_VERDE = { estado:"dev", catalogo, totais, compat, componentesDaSelecao, kgFabricacaoSelecao, eficienciaCurva, selecaoDoPerfil, tela, dimensionar, computacao, armazenamento, rede, energia, nobreak, solar, termico, vramGb, vramTreinoGb, gpusNecessarias, bancoGb, discoBrutoGb, tempoRestauroH, btuH, trDe, pueDe, classeRecomendada, PERFIS, BASE_P, ler, gravar, novoProjeto, importar, versao:"servidor-verde-1" };
window.telaServidorVerde = tela;
window.SERVIDOR_VERDE_I18N = {
  "Servidor verde": "Green server",
  "Cargas de trabalho": "Workloads",
  "Computação": "Computing",
  "Armazenamento e cópias": "Storage and backups",
  "Rede": "Network",
  "Energia": "Energy",
  "Térmico e ambiente": "Thermal and environment",
  "Carbono e custos": "Carbon and costs",
  "Resultado": "Result",
  "Seleção de módulos": "Module selection",
  "Em desenvolvimento": "In development",
  "Conferências": "Checks",
  "Filtros": "Filters",
  "Hardware": "Hardware",
  "Programas abertos": "Open-source software",
  "Modelo de IA": "AI model",
  "tudo compatível": "all compatible",
  "Usar a seleção nas contas (energia, nobreak, térmico, carbono)": "Use the selection in the calculations (energy, UPS, thermal, carbon)",
  "Limpar a seleção": "Clear selection",
  "Procurar": "Search",
  "Mostrar": "Show",
  "Todas as categorias": "All categories",
  "Projeto": "Project",
  "Projeto aberto": "Open project",
  "Nome do projeto": "Project name",
  "Perfil para um projeto novo": "Profile for a new project",
  "Novo projeto": "New project",
  "Duplicar": "Duplicate",
  "Apagar": "Delete",
  "Casa Physis (hub + IA 2×8 GB)": "Casa Physis (hub + AI 2×8 GB)",
  "Pequena empresa / fazenda (Raspberry Pi ou mini PC)": "Small business / farm (Raspberry Pi or mini PC)",
  "Escritório com BI e mapas": "Office with BI and maps",
  "Servidor de IA (GPU)": "AI server (GPU)",
  "Datacenter/colocation": "Datacenter/colocation",
  "Personalizado": "Custom",
  "Plataforma e dados": "Platform and data",
  "Painéis, mapas e cálculos": "Dashboards, maps and calculations",
  "IA local": "Local AI",
  "Núcleos": "Cores",
  "Memória": "Memory",
  "Memória de vídeo": "Video memory",
  "Placas necessárias": "Cards needed",
  "Configuração recomendada": "Recommended configuration",
  "Dados e discos": "Data and disks",
  "Uso da internet": "Internet use",
  "Subida": "Upload",
  "Descida": "Download",
  "Componentes": "Components",
  "Potência média": "Average power",
  "Nobreak": "UPS",
  "Energia solar": "Solar energy",
  "Sala do servidor": "Server room",
  "Calor no pico": "Peak heat",
  "Ar-condicionado": "Air conditioning",
  "Lugar do projeto": "Project site",
  "Comparar com datacenter ou nuvem": "Compare with datacenter or cloud",
  "Lista de materiais (classes genéricas)": "Bill of materials (generic classes)",
  "Boas práticas": "Good practices",
  "Medição real": "Real measurement",
  "Imprimir": "Print",
  "Exportar projetos (JSON)": "Export projects (JSON)",
  "Importar projetos (JSON)": "Import projects (JSON)",
  "Metodologia e normas": "Methodology and standards",
  "Módulo em construção: use para estudo e confira tudo antes de entregar.": "Module under construction: use it for study and check everything before delivery.",
  "Dimensione um servidor com pouca pegada para qualquer projeto: máquina, disco, rede, energia com nobreak e solar, calor, carbono e custos.": "Size a low-footprint server for any project: machine, storage, network, power with UPS and solar, heat, carbon and costs.",
  "Partes do Servidor verde": "Green server sections",
  "valores de partida do perfil": "profile starting values",
  "Hub da plataforma e servidor de IA local com 2 placas de 8 GB; alternativa em estudo pela equipe: 4 placas de 16 GB. Todos os números: verificar.": "Platform hub and local AI server with 2 × 8 GB GPUs; alternative under study by the team: 4 × 16 GB GPUs. All figures: to be verified.",
  "Monitoramento, plataforma e documentos para poucos usuários.": "Monitoring, platform and documents for a few users.",
  "Painéis de BI e servidor de mapas para a equipe.": "BI dashboards and map server for the team.",
  "Modelo de linguagem local para vários usuários.": "Local language model for several users.",
  "Máquina em datacenter: sem solar no lugar; use o PUE e o fator da rede do contrato.": "Machine in a datacenter: no on-site solar; use the PUE and grid emission factor from the contract.",
  "Comece do zero e preencha tudo.": "Start from scratch and fill in everything.",
  "Projeto importado": "Imported project",
  "Primeiro passo do projeto: escolha a máquina, as peças e os programas. As somas e as conferências alimentam todas as outras subabas e a lista de materiais.": "First step of the project: choose the machine, the parts and the software. The totals and checks feed all the other subtabs and the bill of materials.",
  "O catálogo de módulos não foi carregado. Embuta sistema/physis-servidor-catalogo.json no painel (id base-servidor-catalogo).": "The module catalogue was not loaded. Embed sistema/physis-servidor-catalogo.json in the platform (id base-servidor-catalogo).",
  "A seleção está desligada: as contas usam os componentes da aba Energia.": "The selection is off: the calculations use the components from the Energy tab.",
  "Escolha os módulos para conferir.": "Choose the modules to check.",
  "Processamento": "Processing",
  "núcleos / threads": "cores / threads",
  "Vídeo": "VRAM",
  "Disco": "Disk",
  "Potência": "Power",
  "W médios na tomada": "average W at the outlet",
  "Plataforma": "Platform",
  "Processador": "Processor",
  "Placa de vídeo": "GPU",
  "Armazenamento": "Storage",
  "Fonte de alimentação": "Power supply",
  "Refrigeração": "Refrigeration",
  "Rack e gabinete": "Rack and enclosure",
  "Sistema operacional": "Operating system",
  "Contêineres": "Containers",
  "Banco de dados": "Database",
  "Mapas": "Maps",
  "Motores de cálculo": "Calculation engines",
  "Proxy e HTTPS": "Proxy and HTTPS",
  "Cópias": "Backups",
  "Segurança": "Security",
  "Colaboração": "Collaboration",
  "Especificação": "Specification",
  "Modelo aberto (tamanho)": "Open model (size)",
  "Sem modelo": "No model",
  "Quantização": "Quantization",
  "Modelos abertos por tamanho; memória de vídeo = bilhões de parâmetros × bits ÷ 8 × 1,2 (regra prática). Sem placa, o motor roda na memória do sistema, bem mais devagar.": "Open models by size; VRAM = billions of parameters × bits ÷ 8 × 1.2 (rule of thumb). Without a GPU, the engine runs in system memory, much more slowly.",
  "especificações por classe, faixas públicas típicas; custos ficam [MARCADOR] até o orçamento": "specifications by class, typical public ranges; costs stay [MARCADOR] until quoted",
  "Nada com esse filtro.": "Nothing matches this filter.",
  "só x86": "x86 only",
  "precisa de placa de vídeo": "needs a GPU",
  "sem custo de licença": "no license cost",
  "base de equipamentos": "equipment database",
  "ouro": "gold",
  "platina": "platinum",
  "titanio": "titanium",
  "prata": "silver",
  "interativo": "line-interactive",
  "chumbo": "lead-acid",
  "lifepo4": "LiFePO4",
  "1 × 8 pinos": "1 × 8-pin",
  "1 × 6 pinos": "1 × 6-pin",
  "1 × 16 pinos": "1 × 16-pin",
  "1 × 8 pinos ou 1 × 16 pinos": "1 × 8-pin or 1 × 16-pin",
  "1 × 16 pinos ou 2 × 8 pinos": "1 × 16-pin or 2 × 8-pin",
  "1 × 16 pinos ou 3 × 8 pinos": "1 × 16-pin or 3 × 8-pin",
  "1 × 16 pinos ou 1 × 8 pinos CPU": "1 × 16-pin or 1 × 8-pin CPU",
  "Raspberry Pi 5, 8 GB (com SSD no HAT M.2)": "Raspberry Pi 5, 8 GB (with SSD on an M.2 HAT)",
  "Mini PC com processador de 4 núcleos econômico (classe N100)": "Mini PC with a low-power 4-core processor (N100 class)",
  "Mini PC com processador de 8 núcleos econômico (classe N305)": "Mini PC with a low-power 8-core processor (N305 class)",
  "Mini PC Ryzen 7 (8 núcleos, 16 threads)": "Mini PC Ryzen 7 (8 cores, 16 threads)",
  "Workstation de mesa (placa-mãe ATX, Ryzen ou Intel)": "Desktop workstation (ATX motherboard, Ryzen or Intel)",
  "Servidor 1U de entrada (Xeon E ou EPYC 4004)": "Entry-level 1U server (Xeon E or EPYC 4004)",
  "Servidor 2U de 2 processadores (Xeon Silver ou EPYC 9004)": "2U dual-processor server (Xeon Silver or EPYC 9004)",
  "Servidor 4U para placas de vídeo (até 4 placas duplas)": "4U GPU server (up to 4 dual-slot cards)",
  "Ryzen 7 de mesa (8 núcleos, 16 threads, 65 W)": "Desktop Ryzen 7 (8 cores, 16 threads, 65 W)",
  "Ryzen 9 de mesa (16 núcleos, 32 threads, 170 W)": "Desktop Ryzen 9 (16 cores, 32 threads, 170 W)",
  "Core i5 de mesa (14 núcleos híbridos, 20 threads, 65 W base)": "Desktop Core i5 (14 hybrid cores, 20 threads, 65 W base)",
  "Xeon E de entrada (8 núcleos, 16 threads, 95 W)": "Entry-level Xeon E (8 cores, 16 threads, 95 W)",
  "EPYC 4004 (16 núcleos, 32 threads, até 170 W)": "EPYC 4004 (16 cores, 32 threads, up to 170 W)",
  "Xeon Silver (20 núcleos, 40 threads, 165 W)": "Xeon Silver (20 cores, 40 threads, 165 W)",
  "EPYC 9004 (16 núcleos, 32 threads, 200 W)": "EPYC 9004 (16 cores, 32 threads, 200 W)",
  "Memória SO-DIMM 16 GB": "SO-DIMM memory 16 GB",
  "Memória DIMM DDR5 16 GB": "DDR5 DIMM memory 16 GB",
  "Memória DIMM DDR5 32 GB": "DDR5 DIMM memory 32 GB",
  "Memória DDR5 ECC RDIMM 32 GB": "DDR5 ECC RDIMM memory 32 GB",
  "Memória DDR5 ECC RDIMM 64 GB": "DDR5 ECC RDIMM memory 64 GB",
  "Placa de vídeo de consumo 8 GB": "Consumer GPU 8 GB",
  "Placa de vídeo de consumo 12 GB": "Consumer GPU 12 GB",
  "Placa de vídeo de consumo 16 GB": "Consumer GPU 16 GB",
  "Placa de vídeo de consumo 24 GB": "Consumer GPU 24 GB",
  "Placa de vídeo profissional 16 GB (1 slot)": "Professional GPU 16 GB (single slot)",
  "Placa de vídeo profissional 20 GB (1 slot)": "Professional GPU 20 GB (single slot)",
  "Placa de vídeo profissional 48 GB": "Professional GPU 48 GB",
  "Disco rígido 3,5\" 4 TB (para cópias e arquivos frios)": "3.5\" hard disk 4 TB (for backups and cold files)",
  "Disco rígido 3,5\" 8 TB (para cópias e arquivos frios)": "3.5\" hard disk 8 TB (for backups and cold files)",
  "ZFS (espelho ou RAIDZ, por programa)": "ZFS (mirror or RAIDZ, software)",
  "RAID por programa do Linux (mdadm)": "Linux software RAID (mdadm)",
  "Controladora HBA SAS/SATA (8 portas)": "SAS/SATA HBA controller (8 ports)",
  "Fonte 450 W 80 PLUS Ouro": "450 W 80 PLUS Gold power supply",
  "Fonte 750 W 80 PLUS Ouro": "750 W 80 PLUS Gold power supply",
  "Fonte 1.000 W 80 PLUS Platina": "1,000 W 80 PLUS Platinum power supply",
  "Fonte 1.200 W 80 PLUS Platina": "1,200 W 80 PLUS Platinum power supply",
  "Fonte 1.600 W 80 PLUS Titânio": "1,600 W 80 PLUS Titanium power supply",
  "Par de fontes redundantes de servidor 800 W Platina": "Pair of redundant 800 W Platinum server power supplies",
  "Switch gigabit 8 portas": "Gigabit switch, 8 ports",
  "Switch gigabit 8 portas com PoE (sem as cargas PoE)": "Gigabit PoE switch, 8 ports (PoE loads not included)",
  "Roteador com 4G/5G de reserva": "Router with 4G/5G backup",
  "Ponto de acesso Wi-Fi 6": "Wi-Fi 6 access point",
  "Nobreak interativo 1.000 VA / 600 W, chumbo": "Line-interactive UPS 1,000 VA / 600 W, lead-acid",
  "Nobreak online (dupla conversão) 1.500 VA / 1.350 W, chumbo": "Online UPS (double conversion) 1,500 VA / 1,350 W, lead-acid",
  "Nobreak interativo 1.500 VA / 1.000 W, lítio (LiFePO4)": "Line-interactive UPS 1,500 VA / 1,000 W, lithium (LiFePO4)",
  "Painéis, inversor e bateria da base de equipamentos": "Panels, inverter and battery from the equipment database",
  "Ventilação forçada do rack ou da sala (exaustores com filtro)": "Forced ventilation of the rack or room (filtered exhaust fans)",
  "Ar-condicionado split inverter 9.000 BTU/h (sala pequena)": "Inverter split air conditioner 9,000 BTU/h (small room)",
  "Rack de parede 12U com porta e filtro": "12U wall-mount rack with door and filter",
  "Rack de piso 42U": "42U floor-standing rack",
  "Gabinete torre (sem rack)": "Tower case (no rack)",
  "potência da placa-mãe, chipset e ventoinhas; o processador, a memória e as placas entram à parte": "power of the motherboard, chipset and fans; processor, memory and cards are counted separately",
  "no mini PC a potência já está na da plataforma (fonte própria)": "on the mini PC this power is already in the platform figure (own power supply)",
  "disco rígido não tem TBW; carga de trabalho típica de 180 a 550 TB por ano": "hard disks have no TBW rating; typical workload of 180 to 550 TB per year",
  "memória extra para o cache; ECC recomendada": "extra memory for the cache; ECC recommended",
  "a perda da dupla conversão (cerca de 5 a 10%) aparece aqui como potência própria": "the double-conversion loss (about 5 to 10%) appears here as the unit's own power draw",
  "o tamanho (kWp e kWh) sai da subaba Energia; a escolha do modelo é feita na aba Energia solar": "the size (kWp and kWh) comes from the Energy subtab; the model is chosen in the Solar energy tab",
  "só serve se o ar de fora fica abaixo de 27 °C na maior parte do ano": "only works if outdoor air stays below 27 °C for most of the year",
  "a potência do ar entra pelo calor do servidor ÷ COP (subaba Térmico); lance o calor também na aba Carga térmica": "the air conditioner power comes from the server heat ÷ COP (Thermal subtab); also enter the heat in the Thermal load tab",
  "Python 3.10 sem dependências; o banco dos sensores entra no armazenamento": "Python 3.10 with no dependencies; the sensor database is counted in storage",
  "Ubuntu LTS (servidor)": "Ubuntu LTS (server)",
  "Proxmox VE (virtualização)": "Proxmox VE (virtualization)",
  "Raspberry Pi OS (64 bits)": "Raspberry Pi OS (64-bit)",
  "Physis Hub (este sistema)": "Physis Hub (this system)",
  "PostGIS (mapas no PostgreSQL)": "PostGIS (maps in PostgreSQL)",
  "TimescaleDB (séries no PostgreSQL)": "TimescaleDB (time series in PostgreSQL)",
  "PMTiles (mapas em um arquivo)": "PMTiles (maps in a single file)",
  "LibreOffice (sem tela, para ODT e PDF)": "LibreOffice (headless, for ODT and PDF)",
  "veraPDF (conferir PDF/A)": "veraPDF (PDF/A validation)",
  "Caddy (HTTPS automático)": "Caddy (automatic HTTPS)",
  "restic (cópias criptografadas)": "restic (encrypted backups)",
  "BorgBackup (cópias criptografadas)": "BorgBackup (encrypted backups)",
  "Netdata (agente)": "Netdata (agent)",
  "CrowdSec (agente)": "CrowdSec (agent)",
  "Forgejo (repositórios de código)": "Forgejo (code repositories)",
  "Jitsi Meet (videochamadas, até cerca de 20 pessoas)": "Jitsi Meet (video calls, up to about 20 people)",
  "DFSG (GPL-2.0 e outras livres)": "DFSG (GPL-2.0 and other free licenses)",
  "GPL-2.0 e outras livres": "GPL-2.0 and other free licenses",
  "Domínio público": "Public domain",
  "Apache-2.0 (núcleo) e Timescale License (recursos comunitários)": "Apache-2.0 (core) and Timescale License (community features)",
  "MIT ou Apache-2.0": "MIT or Apache-2.0",
  "BSD-3-Clause (licença própria do EnergyPlus)": "BSD-3-Clause (EnergyPlus's own license)",
  "GPL-3.0-or-later ou MPL-2.0": "GPL-3.0-or-later or MPL-2.0",
  "EPL-2.0 ou EDL-1.0": "EPL-2.0 or EDL-1.0",
  "Apache-2.0 e AGPL-3.0": "Apache-2.0 and AGPL-3.0",
  "O que o servidor precisa fazer. Tudo o resto (máquina, disco, energia) sai daqui.": "What the server needs to do. Everything else (machine, disk, energy) follows from this.",
  "Instalações ou clientes hospedados": "Sites or hosted clients",
  "Usuários ao mesmo tempo": "Concurrent users",
  "Pedidos por minuto (Gestão e plataforma)": "Requests per minute (Management and platform)",
  "Sensores (nós V6 e MQTT)": "Sensors (V6 and MQTT nodes)",
  "Leituras por minuto de cada sensor": "Readings per minute per sensor",
  "Guardar os dados por quantos anos": "Data retention (years)",
  "Documentos e PDF/A por dia": "Documents and PDF/A per day",
  "Usuários de BI (Superset)": "BI users (Superset)",
  "Camadas no servidor de mapas (GeoServer)": "Layers on the map server (GeoServer)",
  "Mapas em blocos (PMTiles), GB": "Tiled maps (PMTiles), GB",
  "Rodadas de cálculo por dia (EnergyPlus, pvlib, SWMM)": "Calculation runs per day (EnergyPlus, pvlib, SWMM)",
  "Minutos por rodada": "Minutes per run",
  "Núcleos por rodada": "Cores per run",
  "Rodar modelo de IA no próprio servidor": "Run the AI model on the server itself",
  "Tamanho do modelo": "Model size",
  "3 bilhões de parâmetros (3B)": "3 billion parameters (3B)",
  "16 bits (sem quantizar)": "16 bits (not quantized)",
  "Tokens por dia": "Tokens per day",
  "Usuários da IA ao mesmo tempo": "Concurrent AI users",
  "Tokens por segundo (vazio = estimativa)": "Tokens per second (blank = estimate)",
  "Horas de treino ou ajuste fino por mês": "Training or fine-tuning hours per month",
  "Tipo de ajuste fino": "Fine-tuning type",
  "QLoRA/LoRA (leve)": "QLoRA/LoRA (light)",
  "Completo (pesado)": "Full (heavy)",
  "Processador, memória e placas de vídeo com folga para crescer.": "Processor, memory and GPUs with headroom for growth.",
  "Folga e placas de vídeo": "Headroom and GPUs",
  "Folga para crescer (%)": "Growth headroom (%)",
  "Placas de vídeo que existem ou estão previstas": "GPUs installed or planned",
  "Memória de cada placa (GB)": "Memory per GPU (GB)",
  "Alternativa: quantas placas": "Alternative: number of GPUs",
  "Alternativa: GB de cada placa": "Alternative: GB per GPU",
  "núcleos (threads)": "cores (threads)",
  "Configurações de placas de vídeo": "GPU configurations",
  "Configuração": "Settings",
  "Atende?": "Sufficient?",
  "regras práticas Physis; confirmar com teste do modelo escolhido": "Physis rules of thumb; confirm by testing the chosen model",
  "Raspberry Pi 5: cliente pequeno, até 4 núcleos e 8 GB": "Raspberry Pi 5: small client, up to 4 cores and 8 GB",
  "Mini PC: até 8 núcleos e 64 GB": "Mini PC: up to 8 cores and 64 GB",
  "Servidor x86: acima disso": "x86 server: above that",
  "Servidor com GPU: IA local": "GPU server: local AI",
  "Raspberry Pi 4 (com fonte e cartão)": "Raspberry Pi 4 (with power supply and card)",
  "Raspberry Pi 5 (com fonte, ventoinha e SSD)": "Raspberry Pi 5 (with power supply, fan and SSD)",
  "Mini PC (tipo NUC)": "Mini PC (NUC type)",
  "Workstation ou desktop (placa ATX, sem placa de vídeo)": "Workstation or desktop (ATX board, no GPU)",
  "Servidor x86 de rack ou torre (2 processadores)": "x86 rack or tower server (2 processors)",
  "Servidor com GPU para IA (1 placa incluída na potência)": "GPU server for AI (1 card included in the power)",
  "Servidor com GPU para IA": "GPU server for AI",
  "Quanto disco, como espelhar e onde guardar as cópias (regra 3-2-1: 3 cópias, 2 mídias, 1 fora do lugar, criptografada).": "How much disk, how to mirror it and where to keep the backups (3-2-1 rule: 3 copies, 2 media, 1 off-site, encrypted).",
  "Bytes por leitura guardada (com índice)": "Bytes per stored reading (with index)",
  "Arquivos e anexos por ano (GB)": "Files and attachments per year (GB)",
  "Modelos de IA (GB, vazio = estimativa)": "AI models (GB, blank = estimate)",
  "Espelhamento (RAID)": "Mirroring (RAID)",
  "Sem RAID": "No RAID",
  "RAID 1 (espelho)": "RAID 1 (mirror)",
  "Quantos discos": "Number of disks",
  "Espaço para fotos do disco (snapshots, %)": "Space for disk snapshots (%)",
  "Versões guardadas fora": "Off-site versions kept",
  "Dados que mudam por dia (%)": "Data changed per day (%)",
  "Velocidade para restaurar (Mbps)": "Restore speed (Mbps)",
  "Leituras dos sensores": "Sensor readings",
  "Arquivos e anexos": "Files and attachments",
  "Mapas (PMTiles)": "Maps (PMTiles)",
  "Modelos de IA": "AI models",
  "Útil com folga (com sistema)": "Usable with headroom (incl. system)",
  "Fotos do disco": "Disk snapshots",
  "Disco bruto com RAID": "Raw disk with RAID",
  "Cópia criptografada fora do lugar": "Encrypted off-site backup",
  "Internet que o servidor precisa para os usuários de fora, a sincronia e as cópias.": "Internet bandwidth the server needs for remote users, synchronization and backups.",
  "Usuários de fora ao mesmo tempo": "Concurrent remote users",
  "kbit/s por usuário": "kbit/s per user",
  "Sincronia com outros servidores (MB por dia)": "Sync with other servers (MB per day)",
  "Horas da noite para a cópia": "Night-time backup window (hours)",
  "Latência medida (ms)": "Measured latency (ms)",
  "Acesso pela VPN (sem portas abertas)": "Access through VPN (no open ports)",
  "Link reserva": "Backup link",
  "Segunda fibra": "Second fiber",
  "Satélite": "Satellite",
  "Cópia por dia": "Backup per day",
  "Latência boa para uso interativo.": "Latency good for interactive use.",
  "Latência alta: telas lentas para quem está fora; avalie servidor mais perto dos usuários.": "High latency: slow screens for remote users; consider a server closer to the users.",
  "Latência boa para uso interativo. Sem link reserva: o lugar fica sem acesso remoto se a internet cair (o hub continua coletando).": "Latency good for interactive use. No backup link: the site loses remote access if the internet goes down (the hub keeps collecting).",
  "Latência alta: telas lentas para quem está fora; avalie servidor mais perto dos usuários. Sem link reserva: o lugar fica sem acesso remoto se a internet cair (o hub continua coletando).": "High latency: slow screens for remote users; consider a server closer to the users. No backup link: the site loses remote access if the internet goes down (the hub keeps collecting).",
  "fibra2": "second fiber",
  "satelite": "satellite",
  "4g": "4G/5G",
  "Potência de cada peça, energia do mês, nobreak e energia solar.": "Power of each part, monthly energy, UPS and solar energy.",
  "Componentes (lista manual, sem uso agora)": "Components (manual list, not in use now)",
  "Componentes do servidor": "Server components",
  "Qtd.": "Qty",
  "W parado": "Idle W",
  "W em carga": "Load W",
  "Tempo em carga": "Time under load",
  "Tempo em carga (0 a 1)": "Time under load (0 to 1)",
  "Passa pela fonte do servidor": "Goes through the server power supply",
  "W médio": "mean W",
  "Processador e placa": "Processor and board",
  "Nenhum componente ainda.": "No components yet.",
  "Acrescentar componente": "Add component",
  "potências de ficha técnica; meça na tomada quando puder": "datasheet power figures; measure at the outlet when you can",
  "Eficiência da fonte (80 PLUS)": "Power supply efficiency (80 PLUS)",
  "Sem selo (80%)": "No rating (80%)",
  "Prata (88%)": "Silver (88%)",
  "Ouro (90%)": "Gold (90%)",
  "Platina (92%)": "Platinum (92%)",
  "Titânio (94%)": "Titanium (94%)",
  "kWh por dia": "kWh per day",
  "kWh por mês": "kWh per month",
  "Autonomia (minutos)": "Runtime (minutes)",
  "Lítio (LiFePO4)": "Lithium (LiFePO4)",
  "Chumbo-ácido": "Lead-acid",
  "Tensão do banco (V)": "Battery bank voltage (V)",
  "Lítio usa 90% da carga e dura mais ciclos; chumbo usa 50%, é mais barato e mais pesado.": "Lithium uses 90% of its charge and lasts more cycles; lead-acid uses 50%, is cheaper and heavier.",
  "Sistema só para o servidor": "System dedicated to the server",
  "Parte do sistema do lugar": "Part of the site system",
  "Sem solar": "No solar",
  "Parte da energia do servidor coberta (%)": "Share of the server energy covered (%)",
  "Horas de sol pleno (kWh/m²·dia), vazio = do lugar": "Peak sun hours (kWh/m²·day), blank = from the site",
  "Sol do lugar": "Site sunlight",
  "Mês com menos sol (seguro)": "Month with least sun (conservative)",
  "Média do ano": "Annual average",
  "Desempenho do sistema (PR)": "System performance ratio (PR)",
  "Horas sem sol por dia": "Hours without sun per day",
  "Dias nublados de autonomia": "Cloudy days of autonomy",
  "Agendar treinos de IA nas horas de sol": "Schedule AI training during sun hours",
  "Sem energia solar.": "No solar energy.",
  "digitado no projeto": "typed in the project",
  "padrão da plataforma": "platform default",
  "falta o lugar (latitude e longitude) ou as horas de sol": "site (latitude and longitude) or sun hours missing",
  "buscando o sol do lugar (NASA POWER, no servidor)…": "fetching the site sunshine (NASA POWER, on the server)…",
  "digite as horas de sol pleno (sem servidor)": "type the peak sun hours (no server)",
  "média anual do lugar (NASA POWER)": "annual average for the site (NASA POWER)",
  "mês com menos sol do lugar (NASA POWER)": "month with least sun at the site (NASA POWER)",
  "Todo watt do servidor vira calor na sala.": "Every watt the server draws becomes heat in the room.",
  "Eficiência do ar-condicionado (COP)": "Air conditioner efficiency (COP)",
  "Ventilação com ar de fora (free cooling), sem ar-condicionado": "Ventilation with outdoor air (free cooling), no air conditioning",
  "Perdas do nobreak e da distribuição (%)": "UPS and distribution losses (%)",
  "Iluminação e outros na sala (W)": "Lighting and other loads in the room (W)",
  "Espaço no rack (U) ou local": "Rack space (U) or location",
  "Poeira": "Dust",
  "Filtro na entrada de ar": "Filter on the air inlet",
  "Sala limpa": "Clean room",
  "Ambiente com poeira (fazenda, obra)": "Dusty environment (farm, construction site)",
  "Ruído aceitável no lugar": "Noise acceptable on site",
  "W elétricos": "electrical W",
  "energia total ÷ energia de TI": "total energy ÷ IT energy",
  "conferir a classe do equipamento na ficha técnica": "check the equipment class on the datasheet",
  "Carbono da operação (energia), da fabricação das máquinas e os custos. Fator da rede do lugar do projeto.": "Carbon from operation (energy) and from manufacturing the machines, plus costs. Grid emission factor of the project site.",
  "Fator da rede (SIN)": "Grid emission factor (SIN)",
  "Padrão da plataforma": "Platform default",
  "Ou fator digitado (tCO₂/MWh)": "Or typed factor (tCO₂/MWh)",
  "Tarifa de energia (R$/kWh)": "Energy tariff (R$/kWh)",
  "Usar o lugar da plataforma": "Use the platform site",
  "Fator da rede da região do datacenter (tCO₂/MWh)": "Grid emission factor of the datacenter region (tCO₂/MWh)",
  "PUE do datacenter": "Datacenter PUE",
  "Custo do solar (R$/kWp)": "Solar cost (R$/kWp)",
  "Custo da bateria (R$/kWh)": "Battery cost (R$/kWh)",
  "vazio = [MARCADOR]": "blank = [MARCADOR]",
  "Anos da análise": "Analysis period (years)",
  "Fator da rede": "Grid emission factor",
  "Energia por ano (com PUE)": "Energy per year (with PUE)",
  "Energia da rede por ano (depois do solar)": "Grid energy per year (after solar)",
  "Operação no lugar": "On-site operation",
  "Operação sem solar": "Operation without solar",
  "No datacenter": "In a datacenter",
  "Fabricação (escopo 3, cat. 2)": "Manufacturing (scope 3, cat. 2)",
  "Energia da rede por mês": "Grid energy per month",
  "Investimento no solar e bateria": "Solar and battery investment",
  "Economia por ano": "Savings per year",
  "Retorno simples": "Simple payback",
  "Retorno descontado": "Discounted payback",
  "Mesmas regras da aba Carbono: energia no escopo 2 (máquina própria) e fabricação no escopo 3, categoria 2, dividida pelos anos de uso.": "Same rules as the Carbon tab: energy in scope 2 (own machine) and manufacturing in scope 3, category 2, spread over the years of use.",
  "carbono de fabricação por classe de máquina, ordem de grandeza": "manufacturing carbon by machine class, order of magnitude",
  "Padrão da plataforma (núcleo physis/1)": "Platform default (physis/1 core)",
  "Média anual 2019": "2019 annual average",
  "Média anual 2020": "2020 annual average",
  "Média anual 2021 (crise hídrica)": "2021 annual average (water crisis)",
  "Média anual 2022": "2022 annual average",
  "Média anual 2023": "2023 annual average",
  "Relatório do dimensionamento para entregar ao cliente: imprima, use “Baixar esta tela” ou exporte o projeto.": "Sizing report to hand to the client: print it, use “Download this screen” or export the project.",
  "Relatório de dimensionamento": "Sizing report",
  "Máquina": "Machine",
  "Lista de materiais": "Bill of materials",
  "Custo": "Cost",
  "Custo da máquina principal (R$), se já orçado": "Cost of the main machine (R$), if already quoted",
  "Limite de potência (power capping) nas placas de vídeo e no processador": "Power capping on the GPUs and the processor",
  "Suspender ou desligar a placa de vídeo parada": "Suspend or power off idle GPUs",
  "Agendar treinos e cálculos pesados nas horas de sol": "Schedule training and heavy calculations during sun hours",
  "Fonte 80 PLUS Ouro ou melhor": "80 PLUS Gold power supply or better",
  "SSD em vez de disco rígido": "SSD instead of hard disk",
  "Virtualização e contêineres: menos máquinas meio paradas": "Virtualization and containers: fewer half-idle machines",
  "Hibernar o que não precisa ficar ligado à noite": "Hibernate what does not need to run at night",
  "Medir na tomada e comparar com o dimensionado": "Measure at the outlet and compare with the sizing",
  "Usar até o fim da vida útil e reciclar com empresa certificada": "Use until end of life and recycle with a certified company",
  "Comparar com a pegada medida deste servidor (aba Carbono)": "Compare with the measured footprint of this server (Carbon tab)",
  "Sem dado do servidor ainda (precisa de sessão).": "No data from the server yet (requires a session).",
  "Abra pelo servidor Physis para comparar.": "Open through the Physis server to compare.",
  "dimensionamento por regras práticas; confirmar com medição e ficha técnica antes da compra. Custos sem orçamento ficam como [MARCADOR].": "sizing by rules of thumb; confirm with measurements and datasheets before purchase. Costs without a quote stay as [MARCADOR].",
  "Placa de vídeo para IA": "GPU for AI",
  "SSD ou disco": "SSD or disk",
  "Cópia fora do lugar, criptografada": "Off-site backup, encrypted",
  "Painéis solares e inversor": "Solar panels and inverter",
  "Bateria solar": "Solar battery",
  "plataforma": "platform",
  "rede": "network",
  "refrigeracao": "cooling",
  "armazenamento": "storage",
  "Memória de vídeo, núcleos e memória: regras práticas Physis (parâmetros × bytes × 1,2; serviços somados com folga).": "VRAM, cores and memory: Physis rules of thumb (parameters × bytes × 1.2; services added up with headroom).",
  "Energia: potência parada e em carga × tempo em carga, dividida pela eficiência da fonte (selos 80 PLUS).": "Energy: idle and load power × time under load, divided by the power supply efficiency (80 PLUS ratings).",
  "Solar: energia do dia ÷ (horas de sol pleno × desempenho), com o sol do lugar do projeto (NASA POWER, guardado no servidor).": "Solar: daily energy ÷ (peak sun hours × performance ratio), using the sunshine of the project site (NASA POWER, stored on the server).",
  "Calor: 1 W = 3,412 BTU/h; 12.000 BTU/h = 1 TR. PUE = energia total ÷ energia de TI. Faixa térmica: orientações ASHRAE TC 9.9.": "Heat: 1 W = 3.412 BTU/h; 12,000 BTU/h = 1 TR. PUE = total energy ÷ IT energy. Thermal range: ASHRAE TC 9.9 guidelines.",
  "Carbono: GHG Protocol (escopo 2 e escopo 3, categoria 2), Orientação Setorial de TIC do GHG Protocol e Recomendação ITU-T L.1450; mesmo fator da rede do Carbono.": "Carbon: GHG Protocol (scope 2 and scope 3, category 2), GHG Protocol ICT Sector Guidance and ITU-T Recommendation L.1450; same grid factor as the Carbon tab.",
  "Cópias: regra 3-2-1 (três cópias, duas mídias, uma fora do lugar).": "Backups: 3-2-1 rule (three copies, two media, one off-site).",
  "Resumos com palavras próprias da Physis.": "Summaries in Physis's own words.",
  "Escolha ao menos uma plataforma (a máquina).": "Choose at least one platform (the machine).",
  "Escolha o sistema operacional.": "Choose the operating system.",
  "Placa de vídeo pede encaixe PCIe x16: Raspberry Pi e mini PC não recebem placa.": "A GPU needs a PCIe x16 slot: Raspberry Pi and mini PC cannot take one.",
  "Escolha a fonte do servidor.": "Choose the server power supply.",
  "Debian 12": "Debian 12",
  "Docker Engine": "Docker Engine",
  "Podman": "Podman",
  "SQLite": "SQLite",
  "PostgreSQL": "PostgreSQL",
  "InfluxDB 3 Core": "InfluxDB 3 Core",
  "Ollama": "Ollama",
  "vLLM": "vLLM",
  "llama.cpp": "llama.cpp",
  "Apache Superset": "Apache Superset",
  "Metabase": "Metabase",
  "GeoServer": "GeoServer",
  "QGIS Server": "QGIS Server",
  "EnergyPlus": "EnergyPlus",
  "pvlib python": "pvlib python",
  "windpowerlib": "windpowerlib",
  "EPANET": "EPANET",
  "SWMM": "SWMM",
  "Eclipse Mosquitto (MQTT)": "Eclipse Mosquitto (MQTT)",
  "Node-RED": "Node-RED",
  "nginx": "nginx",
  "WireGuard": "WireGuard",
  "Prometheus + Grafana": "Prometheus + Grafana",
  "fail2ban": "fail2ban",
  "Documentos": "Documents",
  "Monitoramento": "Monitoring",
  "Nenhum": "None",
  "LibreOffice (sem tela": "LibreOffice (headless",
  "para ODT e PDF)": "for ODT and PDF)"
};
/* regras com números (o painel lê a cópia em sistema/physis-i18n-modulos.json) */
window.SERVIDOR_VERDE_I18N_RX = [
  ["^(\\d+) conferências passaram\\.$", "$1 checks passed."],
  ["^programas pedem ([\\d.,]+)$", "software needs $1"],
  ["^programas pedem ([\\d.,]+) GB$", "software needs $1 GB"],
  ["^(\\d+) placas$", "$1 cards"],
  ["^modelo pede ([\\d.,]+) GB$", "model needs $1 GB"],
  ["^parado ([\\d.,]+) W$", "idle $1 W"],
  ["^pico ([\\d.,]+) W$", "peak $1 W"],
  ["^fonte com ([\\d.,]+)%$", "power supply at $1%"],
  ["^(\\d+)/(\\d+) núcleos/threads$", "$1/$2 cores/threads"],
  ["^(\\d+) encaixes x16$", "$1 x16 slots"],
  ["^([\\d.,]+) a ([\\d.,]+) W$", "$1 to $2 W"],
  ["^([\\d.,]+) GB de vídeo$", "$1 GB VRAM"],
  ["^([\\d.,]+) a ([\\d.,]+) TFLOPS FP16$", "$1 to $2 TFLOPS FP16"],
  ["^([\\d.,]+) Wh (chumbo|lifepo4)$", "$1 Wh $2"],
  ["^Quantidade de (.+)$", "Quantity of $1"],
  ["^Aplicar a seleção do perfil “(.+)”$", "Apply the selection from the “$1” profile"],
  ["^([\\d.,]+) núcleo, ([\\d.,]+) GB, ([\\d.,]+) GB de disco$", "$1 core, $2 GB RAM, $3 GB disk"],
  ["^precisa de (.+)$", "needs $1"],
  ["^rodar ([\\d.,]+) · treinar ([\\d.,]+)$", "run $1 · train $2"],
  ["^de ([\\d.,]+) GB$", "of $1 GB"],
  ["^Atual: ([\\d.,]+ × [\\d.,]+ GB)$", "Current: $1"],
  ["^Alternativa: ([\\d.,]+ × [\\d.,]+ GB)$", "Alternative: $1"],
  ["^Regra prática da memória de vídeo: bilhões de parâmetros × bytes por parâmetro \\(4 bits = 0,5 byte\\) × 1,2\\. Ajuste fino leve \\(QLoRA\\) pede cerca de 1,5 vez isso; completo, 16 bytes por parâmetro\\. A IA ocupa a placa cerca de ([\\d.,]+) h por dia \\(([\\d.,]+) tokens/s\\)\\.$", "VRAM rule of thumb: billions of parameters × bytes per parameter (4 bits = 0.5 byte) × 1.2. Light fine-tuning (QLoRA) needs about 1.5 times that; full fine-tuning, 16 bytes per parameter. The AI keeps the GPU busy about $1 h per day ($2 tokens/s)."],
  ["^(.+) ← recomendada$", "$1 ← recommended"],
  ["^Restaurar tudo da cópia de fora leva cerca de (.+) h\\. Teste a restauração a cada 6 meses\\.$", "Restoring everything from the off-site backup takes about $1 h. Test the restore every 6 months."],
  ["^As contas usam as peças da Seleção de módulos \\((\\d+) linhas, fonte com ([\\d.,]+)% de eficiência na carga média\\)\\. A lista abaixo só vale com a seleção desligada\\.$", "The calculations use the parts from the Module selection ($1 rows, power supply at $2% efficiency at average load). The list below only applies with the selection turned off."],
  ["^Tempo em carga vazio na placa de vídeo = calculado pela IA \\(([\\d.,]+)% do dia\\)\\.$", "Blank time under load on the GPU = calculated from the AI use ($1% of the day)."],
  ["^Nobreak de ([\\d.,]+) VA \\(([\\d.,]+) W\\) e banco de ([\\d.,]+) Wh \\(([\\d.,]+) Ah em ([\\d.,]+) V\\)\\.$", "UPS of $1 VA ($2 W) and a $3 Wh battery bank ($4 Ah at $5 V)."],
  ["^Nobreak escolhido na seleção: cerca de ([\\d.,]+) minutos de autonomia na potência média\\.$", "UPS chosen in the selection: about $1 minutes of runtime at average power."],
  ["^([\\d.,]+) kWp de painéis e ([\\d.,]+) kWh de bateria útil\\.$", "$1 kWp of panels and $2 kWh of usable battery."],
  ["^Sol: ([\\d.,]+|—) kWh/m²·dia \\((.+)\\)\\.$", "Sun: $1 kWh/m²·day ($2)."],
  ["^No modo compartilhado, some ([\\d.,]+) kWh por ano ao consumo da aba Energia solar\\.$", "In shared mode, add $1 kWh per year to the consumption in the Solar energy tab."],
  ["^Faixa de entrada de ar recomendada: ([\\d.,]+) a ([\\d.,]+) °C, umidade sem condensação \\(orientações térmicas ASHRAE TC 9\\.9, classe A1, em palavras próprias\\)\\. Lance o calor do servidor como carga interna na aba Carga térmica\\.$", "Recommended air inlet range: $1 to $2 °C, non-condensing humidity (ASHRAE TC 9.9 thermal guidelines, class A1, in our own words). Enter the server heat as an internal load in the Thermal load tab."],
  ["^Faixa de entrada de ar recomendada: ([\\d.,]+) a ([\\d.,]+) °C, umidade sem condensação \\(orientações térmicas ASHRAE TC 9\\.9, classe A1, em palavras próprias\\)\\.$", "Recommended air inlet range: $1 to $2 °C, non-condensing humidity (ASHRAE TC 9.9 thermal guidelines, class A1, in our own words)."],
  ["^([\\d.,]+) tCO₂/MWh \\((.+)\\)$", "$1 tCO₂/MWh ($2)"],
  ["^([\\d.,−-]+) tCO₂e por ano$", "$1 tCO₂e per year"],
  ["^([\\d.,]+) kgCO₂e, ([\\d.,]+) tCO₂e por ano$", "$1 kgCO₂e, $2 tCO₂e per year"],
  ["^perfil: (.+)$", "profile: $1"],
  ["^([\\d.,]+) núcleos$", "$1 cores"],
  ["^([\\d.,]+) GB de vídeo, ([\\d.,]+) W$", "$1 GB VRAM, $2 W"],
  ["^([\\d.,]+) W, (ouro|platina|titanio|prata|bronze)$", "$1 W, $2"],
  ["^([\\d.,]+) núcleos, ([\\d.,]+) GB de memória$", "$1 cores, $2 GB of memory"],
  ["^([\\d.,]+) GB cada$", "$1 GB each"],
  ["^([\\d.,]+) GB cada, (.+)$", "$1 GB each, $2"],
  ["^([\\d.,]+) kWh úteis$", "$1 kWh usable"],
  ["^Programas: (.+)\\.$", "Software: $1."],
  ["^Dimensionado ([\\d.,]+) kWh por mês × medido ([\\d.,]+) kWh por mês \\(([−-]?[\\d.,]+)% de diferença\\)\\.$", "Sized $1 kWh per month × measured $2 kWh per month ($3% difference)."],
  ["^componente (\\d+)$", "component $1"],
  ["^(.+): falta o processador do encaixe '(.+)'\\.$", "$1: missing processor for socket '$2'."],
  ["^(.+) não encaixa em nenhuma plataforma escolhida\\.$", "$1 does not fit any chosen platform."],
  ["^(.+): nenhuma plataforma usa esse formato de memória\\.$", "$1: no chosen platform uses this memory form factor."],
  ["^(.+): servidor pede memória ECC\\.$", "$1: the server requires ECC memory."],
  ["^Memória \\(([\\d.,]+) GB\\) acima do máximo das plataformas \\(([\\d.,]+) GB\\)\\.$", "Memory ($1 GB) above the platforms' maximum ($2 GB)."],
  ["^(\\d+) placas de vídeo para (\\d+) encaixes x16\\.$", "$1 GPUs for $2 x16 slots."],
  ["^Placas PCIe \\((\\d+)\\) acima dos encaixes \\((\\d+)\\)\\.$", "PCIe cards ($1) exceed the slots ($2)."],
  ["^(.+) precisa de processador x86 \\(não roda no Raspberry Pi\\)\\.$", "$1 needs an x86 processor (does not run on the Raspberry Pi)."],
  ["^(.+) é só para Raspberry Pi\\.$", "$1 is for Raspberry Pi only."],
  ["^(.+) precisa de placa de vídeo\\.$", "$1 needs a GPU."],
  ["^(.+) precisa de (.+)\\.$", "$1 needs $2."],
  ["^Memória ([\\d.,]+) GB para ([\\d.,]+) GB pedidos pelos programas e pelo modelo \\(sem placa suficiente\\)\\.$", "Memory $1 GB for $2 GB required by the software and the model (not enough GPU)."],
  ["^Memória ([\\d.,]+) GB para ([\\d.,]+) GB pedidos pelos programas\\.$", "Memory $1 GB for $2 GB required by the software."],
  ["^([\\d.,]+) threads para ([\\d.,]+) núcleos pedidos pelos programas\\.$", "$1 threads for $2 cores required by the software."],
  ["^Modelo pede ([\\d.,]+) GB de vídeo; a seleção tem ([\\d.,]+) GB \\(sem isso, roda na memória, bem mais devagar\\)\\.$", "Model needs $1 GB of VRAM; the selection has $2 GB (without it, it runs in system memory, much more slowly)."],
  ["^Modelo pede ([\\d.,]+) GB de vídeo; a seleção tem ([\\d.,]+) GB\\.$", "Model needs $1 GB of VRAM; the selection has $2 GB."],
  ["^Fonte de ([\\d.,]+) W para pico de ([\\d.,]+) W \\(pede 30% de folga: ([\\d.,]+) W\\)\\.$", "$1 W power supply for a $2 W peak (needs 30% headroom: $3 W)."],
  ["^Nobreak de ([\\d.,]+) W para pico de ([\\d.,]+) W\\.$", "$1 W UPS for a $2 W peak."],
  ["^Discos com ([\\d.,]+) TB para ([\\d.,]+) TB pedidos \\(dados, cópias locais e programas\\)\\.$", "Disks with $1 TB for $2 TB required (data, local copies and software)."],
  ["^rodar ([\\d.,]+)$", "run $1"],
  ["^treinar ([\\d.,]+)$", "train $1"]
];
})();
