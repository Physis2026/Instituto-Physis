/* physis-saude.js — aba Saúde: caixinha de remédios e pulseira de alerta.
 *
 * telaSaude() devolve o HTML da aba (um <h1>Saúde</h1> e cinco partes).
 * Na plataforma (ui.modo === "hub") tudo vem do computador central: GET api/saude/estado e POST api/saude/<ação>.
 * Fora dela, uma demonstração com dados de exemplo guardados só neste navegador (localStorage).
 * Usa do painel, na hora da chamada: esc, n2, numBr, brl, el, desenhar(false), ui.
 * Eventos só por atributos data-saude-… (registrados uma vez: window.__saudeEventos).
 * window.SAUDE traz as contas puras: adesao(doses), proximas(horarios, agora), ocorrencias, estadoDose.
 *
 * Dados de saúde são sensíveis (LGPD): na plataforma, só aparecem as pessoas que o usuário foi autorizado a ver,
 * e nada é guardado sem consentimento registrado com data e hora.
 */
(function () {
"use strict";

const CHAVE = "physis-saude-demo-v1";
const ANTES_MIN = 30, TOL_PADRAO = 60, MAX_CMP = 8;
const DIAS = [["1", "seg"], ["2", "ter"], ["3", "qua"], ["4", "qui"], ["5", "sex"], ["6", "sáb"], ["7", "dom"]];
const SUBS = [["hoje", "Hoje"], ["horarios", "Horários e remédios"], ["historico", "Histórico e adesão"],
  ["pulseira", "Pulseira e alertas"], ["pessoas", "Pessoas e consentimento"]];
const SITUACAO = { tomado: ["ok", "Tomado"], atrasado: ["at", "Tomado com atraso"], esquecido: ["al", "Não tomado"],
  pendente: ["at", "Na hora: falta confirmar"], esperando: ["in", "Ainda não é a hora"] };
const EVENTO = { TOMADO: "Tomou", ATRASO: "Tomou com atraso", ESQUECEU: "Não tomou" };
const ORIGEM = { aparelho: "caixinha", tela: "confirmado na tela", hub: "aviso automático", demo: "exemplo" };
const MOV = ["parado", "andando", "correndo"];
const FINALIDADE = "Acompanhar os horários dos remédios e os alertas da pulseira, e avisar os cuidadores autorizados. " +
  "Os dados ficam no computador central do lugar e só são vistos pelas pessoas autorizadas. " +
  "O consentimento pode ser retirado a qualquer momento, e os dados podem ser apagados.";

/* ════════ Contas puras (as mesmas regras de physis_hub/saude.py; tempos em segundos) ════════ */
const pad = n => (n < 10 ? "0" : "") + n;
const diaDe = s => { const d = new Date(s * 1000); return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); };
const segundos = x => { const v = x instanceof Date ? x.getTime() : Number(x); return v > 1e11 ? v / 1000 : v; };   // aceita Date, ms ou s
const meiaNoite = s => { const d = new Date(s * 1000); d.setHours(0, 0, 0, 0); return d.getTime() / 1000; };

function ocorrencias(horarios, ini, fim) {
  ini = segundos(ini); fim = segundos(fim);
  const out = [];
  (horarios || []).forEach(h => {
    const tol = (Number(h.tolerancia) || TOL_PADRAO) * 60, hm = String(h.hora || "00:00").split(":").map(Number);
    const d = new Date((ini - 86400) * 1000); d.setHours(0, 0, 0, 0);
    const limite = (fim + 86400) * 1000;
    for (; d.getTime() <= limite; d.setDate(d.getDate() + 1)) {
      if (String(h.dias || "").indexOf(String(d.getDay() || 7)) < 0) continue;
      const p = new Date(d.getFullYear(), d.getMonth(), d.getDate(), hm[0], hm[1]).getTime() / 1000;
      if (p < ini || p >= fim || (h.criado && p + tol <= h.criado) || (h.removido && p >= h.removido)) continue;
      out.push({ horario: h.id, cmp: h.cmp, hora: h.hora, remedio: h.remedio || "", dose: h.dose || "", dia: diaDe(p),
        previsto: p, inicio: p - ANTES_MIN * 60, fim: p + tol });
    }
  });
  return out.sort((a, b) => a.previsto - b.previsto || a.cmp - b.cmp);
}

function estadoDose(oc, eventos, agora) {
  agora = segundos(agora);
  const ev = eventos || [], tomou = ev.filter(e => e.evento === "TOMADO").map(e => e.quando);
  if (tomou.some(q => q <= oc.fim)) return "tomado";
  if (tomou.length || ev.some(e => e.evento === "ATRASO")) return "atrasado";
  if (ev.some(e => e.evento === "ESQUECEU") || agora >= oc.fim) return "esquecido";
  return agora >= oc.previsto ? "pendente" : "esperando";
}

/* adesao([{estado:"tomado"}, "esquecido", …]) → {total, tomadas, atrasadas, esquecidas, taxa, taxa_no_horario} */
function adesao(doses) {
  const est = (doses || []).map(d => typeof d === "string" ? d : d && d.estado);
  const t = est.filter(e => e === "tomado").length, a = est.filter(e => e === "atrasado").length, e = est.filter(x => x === "esquecido").length;
  const total = t + a + e, r3 = x => Math.round(x * 1000) / 1000;
  return { total, tomadas: t, atrasadas: a, esquecidas: e, taxa: total ? r3((t + a) / total) : null, taxa_no_horario: total ? r3(t / total) : null };
}

/* proximas(horarios, agora[, doses]) → doses na hora (pendente) ou nas próximas 24 h (esperando).
   doses (opcional): [{horario, dia, evento, quando}] para tirar as que já foram tomadas. */
function proximas(horarios, agora, doses) {
  agora = segundos(agora == null ? Date.now() : agora);
  const mapa = agruparEventos(doses);
  return ocorrencias(horarios, agora - 6 * 3600, agora + 24 * 3600)
    .map(o => Object.assign(o, { estado: estadoDose(o, mapa[o.horario + "|" + o.dia], agora) }))
    .filter(o => o.estado === "pendente" || o.estado === "esperando");
}

function agruparEventos(doses) {
  const m = {};
  (doses || []).forEach(d => { if (d.horario != null) (m[d.horario + "|" + d.dia] = m[d.horario + "|" + d.dia] || []).push(d); });
  return m;
}

window.SAUDE = { adesao, proximas, ocorrencias, estadoDose };

/* ════════ Demonstração (dados de exemplo só neste navegador) ════════ */
let memoria = null;
function lerDemo() {
  if (memoria) return memoria;
  try { const j = JSON.parse(localStorage.getItem(CHAVE) || "null"); if (j && j.v === 1) return (memoria = j); } catch (e) { /* sem armazenamento */ }
  memoria = semente(); gravarDemo(); return memoria;
}
function gravarDemo() { try { localStorage.setItem(CHAVE, JSON.stringify(memoria)); } catch (e) { /* fica só na memória */ } }

function semente() {
  const agora = Date.now() / 1000, criado = meiaNoite(agora) - 14 * 86400, hoje = new Date();
  const db = { v: 1, seq: 100, pessoas: [] };
  const maria = { id: 1, nome: "Dona Maria (exemplo)", nascimento: "1948-05-10", menor: false, responsavel: "",
    consentimento: { quem: "Dona Maria (exemplo)", papel: "titular", versao: "1", dado: criado, revogado: null, registrado_por: "você" },
    acesso: ["você (demonstração)"], contatos: [{ id: 1, nome: "Joana (filha)", email: "joana@exemplo.com", telefone: "", alerta: true }],
    dispositivos: [{ no: 31, tipo: "MED", apelido: "Caixinha da cozinha", visto: agora - 240, bat: 3.92 }],
    horarios: [
      { id: 1, cmp: 1, hora: "08:00", dias: "1234567", remedio: "Losartana 50 mg", dose: "1 comprimido", tolerancia: 60, criado },
      { id: 2, cmp: 2, hora: "12:00", dias: "1234567", remedio: "Metformina 500 mg", dose: "1 comprimido", tolerancia: 60, criado },
      { id: 3, cmp: 3, hora: "18:00", dias: "1234567", remedio: "Losartana 50 mg", dose: "1 comprimido", tolerancia: 60, criado },
      { id: 4, cmp: 4, hora: "22:00", dias: "135", remedio: "Vitamina D", dose: "1 cápsula", tolerancia: 60, criado }],
    doses: [], alertas: [], posicao: null };
  ocorrencias(maria.horarios, criado, agora).forEach(o => {
    if (o.previsto > agora - 15 * 60) return;
    const k = (Math.floor(o.previsto / 86400) * 7 + o.cmp * 3) % 20;
    if (k < 15) maria.doses.push({ horario: o.horario, dia: o.dia, cmp: o.cmp, evento: "TOMADO", quando: o.previsto + k * 60, origem: "demo" });
    else if (k < 18 && o.fim + 900 < agora) maria.doses.push({ horario: o.horario, dia: o.dia, cmp: o.cmp, evento: "TOMADO", quando: o.fim + 900, origem: "demo" });
  });
  const pedro = { id: 2, nome: "Pedro (exemplo)", nascimento: (hoje.getFullYear() - 10) + "-03-15", menor: true, responsavel: "Carla (mãe)",
    consentimento: { quem: "Carla (mãe)", papel: "responsavel", versao: "1", dado: criado, revogado: null, registrado_por: "você" },
    acesso: ["você (demonstração)"], contatos: [{ id: 2, nome: "Carla (mãe)", email: "carla@exemplo.com", telefone: "", alerta: true }],
    dispositivos: [{ no: 51, tipo: "PUL", apelido: "Pulseira azul", visto: agora - 60, bat: 3.85 }],
    horarios: [], doses: [], alertas: [],
    posicao: { lat: -22.5051, lon: -43.1784, gps: true, crise: false, bpm: 92, mov: 1, bat: 3.85, quando: agora - 60,
      ultimo_gps: { lat: -22.5051, lon: -43.1784, quando: agora - 60 } } };
  db.pessoas.push(maria, pedro);
  return db;
}

function verificarDemo(db, agora) {
  let mudou = false;
  db.pessoas.forEach(p => {
    if (!ativo(p)) return;
    const mapa = agruparEventos(p.doses);
    ocorrencias(p.horarios, agora - 29 * 3600, agora).forEach(o => {
      if (o.fim > agora || o.fim <= agora - 24 * 3600) return;
      const ev = mapa[o.horario + "|" + o.dia];
      if (estadoDose(o, ev, agora) !== "esquecido") return;
      if (!ev) { p.doses.push({ horario: o.horario, dia: o.dia, cmp: o.cmp, evento: "ESQUECEU", quando: o.fim, origem: "hub" }); mudou = true; }
      if (novoAlerta(db, p, "dose_esquecida", `A dose das ${o.hora} de ${fmtDia(o.dia)} (compartimento ${o.cmp}) de ${p.nome} não foi confirmada.`, "dose:" + o.horario + ":" + o.dia, agora)) mudou = true;
    });
  });
  if (mudou && db === memoria) gravarDemo();
  return mudou;
}
function novoAlerta(db, p, tipo, mensagem, ref, agora, lat, lon) {
  if (p.alertas.some(a => a.ref === ref)) return null;
  const a = { id: ++db.seq, tipo, mensagem, ref, criado: agora, atualizado: agora, lat: lat == null ? null : lat, lon: lon == null ? null : lon, visto: null, visto_por: "" };
  p.alertas.push(a); return a;
}
const ativo = p => !!(p.consentimento && !p.consentimento.revogado);

/* Monta o mesmo formato que o computador central devolve em GET api/saude/estado. */
function visaoDemo(db, agora) {
  verificarDemo(db, agora);
  const pessoas = db.pessoas.map(p => {
    const base = { id: p.id, nome: p.nome, nascimento: p.nascimento, menor: p.menor, responsavel: p.responsavel,
      consentimento: p.consentimento ? Object.assign({ ativo: ativo(p) }, p.consentimento) : null, acesso: p.acesso.slice(), ativo: ativo(p) };
    if (!base.ativo) return base;
    const mapa = agruparEventos(p.doses);
    const doses = (ini, fim) => ocorrencias(p.horarios, ini, fim).map(o => Object.assign(o, { estado: estadoDose(o, mapa[o.horario + "|" + o.dia], agora) }));
    const resumo = n => {
      const ini = meiaNoite(agora) - (n - 1) * 86400, lista = doses(ini, agora + 1).filter(o => ["tomado", "atrasado", "esquecido"].includes(o.estado));
      const r = adesao(lista); r.dias = n; r.por_dia = [];
      for (let i = 0; i < n; i++) { const dia = diaDe(ini + i * 86400 + 7200), s = adesao(lista.filter(o => o.dia === dia)); s.dia = dia; r.por_dia.push(s); }
      return r;
    };
    const hor = {}; p.horarios.forEach(h => { hor[h.id] = h; });
    return Object.assign(base, {
      contatos: p.contatos.slice(), dispositivos: p.dispositivos.slice(),
      horarios: p.horarios.filter(h => !h.removido).sort((a, b) => a.hora < b.hora ? -1 : a.hora > b.hora ? 1 : a.cmp - b.cmp),
      hoje: doses(meiaNoite(agora), meiaNoite(agora) + 86400), proximas: proximas(p.horarios, agora, p.doses),
      adesao: { semana: resumo(7), mes: resumo(30) }, posicao: p.posicao,
      alertas: p.alertas.slice().sort((a, b) => b.id - a.id).slice(0, 30),
      eventos: p.doses.filter(d => d.quando >= agora - 30 * 86400).sort((a, b) => b.quando - a.quando).slice(0, 100)
        .map(d => ({ quando: d.quando, dia: d.dia, cmp: d.cmp, evento: d.evento, origem: d.origem,
          hora: hor[d.horario] ? hor[d.horario].hora : null, remedio: hor[d.horario] ? hor[d.horario].remedio : null })) });
  });
  const alertas = [];
  db.pessoas.forEach(p => { if (ativo(p)) p.alertas.filter(a => !a.visto).forEach(a => alertas.push(Object.assign({ pessoa: p.id, nome: p.nome }, a))); });
  alertas.sort((a, b) => (b.tipo === "crise") - (a.tipo === "crise") || b.id - a.id);
  return { ok: true, agora, pessoas, alertas, finalidade: FINALIDADE, versao_termo: "1", max_cmp: MAX_CMP, tolerancia_padrao: TOL_PADRAO, demo: true };
}

function idadeDe(nasc, agora) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(nasc || ""); if (!m) return null;
  const h = new Date(agora * 1000); let i = h.getFullYear() - Number(m[1]);
  if (h.getMonth() + 1 < Number(m[2]) || (h.getMonth() + 1 === Number(m[2]) && h.getDate() < Number(m[3]))) i--;
  return i;
}
const inteiro = v => { const n = typeof v === "number" ? v : numBr(String(v == null ? "" : v)); return n != null && isFinite(n) && Math.round(n) === n ? n : null; };

/* As ações da demonstração seguem as mesmas regras do computador central (versão curta). */
function acaoDemo(acao, d) {
  const db = lerDemo(), agora = Date.now() / 1000, p = db.pessoas.find(x => x.id === Number(d.pessoa));
  const pronto = r => { gravarDemo(); return Object.assign({ ok: true }, r || {}); }, erro = e => ({ ok: false, erro: e });
  if (acao === "restaurar_demo") { memoria = semente(); gravarDemo(); return { ok: true, pessoa: 1 }; }
  if (acao === "pessoa") {
    const nome = String(d.nome || "").trim(); if (!nome) return erro("Informe o nome da pessoa.");
    const idade = d.nascimento ? idadeDe(d.nascimento, agora) : null;
    if (d.nascimento && (idade == null || idade < 0 || idade > 130)) return erro("Data de nascimento inválida.");
    const menor = idade != null ? idade < 18 : !!d.menor, resp = String(d.responsavel || "").trim(), c = d.consentimento || {};
    if (c.aceito !== true) return erro("Sem o consentimento marcado, nada é guardado.");
    const papel = menor ? "responsavel" : (c.papel || "titular");
    if (papel === "responsavel" && !resp) return erro(menor ? "Para menor de 18 anos, informe o responsável legal." : "Informe o nome do responsável legal.");
    const nova = { id: ++db.seq, nome, nascimento: d.nascimento || "", menor, responsavel: resp,
      consentimento: { quem: String(c.quem || "").trim() || (papel === "responsavel" ? resp : nome), papel, versao: "1", dado: agora, revogado: null, registrado_por: "você" },
      acesso: ["você (demonstração)"], contatos: [], dispositivos: [], horarios: [], doses: [], alertas: [], posicao: null };
    db.pessoas.push(nova); return pronto({ pessoa: nova.id });
  }
  if (!p) return erro("Escolha uma pessoa.");
  const exigeAtivo = () => ativo(p) ? null : erro("O consentimento foi retirado. Registre um novo para continuar.");
  let e;
  switch (acao) {
    case "consentimento": {
      const c = d.consentimento || {}; if (c.aceito !== true) return erro("Sem o consentimento marcado, nada é guardado.");
      const papel = p.menor ? "responsavel" : (c.papel || "titular");
      if (papel === "responsavel" && !p.responsavel) return erro("Informe o nome do responsável legal.");
      p.consentimento = { quem: String(c.quem || "").trim() || (papel === "responsavel" ? p.responsavel : p.nome), papel, versao: "1", dado: agora, revogado: null, registrado_por: "você" };
      return pronto();
    }
    case "revogar": if (p.consentimento) p.consentimento.revogado = agora; return pronto();
    case "apagar": db.pessoas = db.pessoas.filter(x => x !== p); return pronto();
    case "acesso_dar": { const u = String(d.usuario || "").trim().toLowerCase(); if (!u) return erro("Informe o usuário.");
      if (p.acesso.indexOf(u) < 0) p.acesso.push(u); return pronto(); }
    case "acesso_tirar": if (p.acesso.length <= 1) return erro("Precisa ficar pelo menos uma pessoa autorizada.");
      p.acesso = p.acesso.filter(u => u !== d.usuario); return pronto();
    case "contato": { if ((e = exigeAtivo())) return e;
      const nome = String(d.nome || "").trim(), email = String(d.email || "").trim().toLowerCase(), tel = String(d.telefone || "").trim();
      if (!nome) return erro("Informe o nome do cuidador.");
      if (email && !/^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$/.test(email)) return erro("E-mail inválido.");
      if (!email && !tel) return erro("Informe um e-mail ou telefone.");
      p.contatos.push({ id: ++db.seq, nome, email, telefone: tel, alerta: d.alerta !== false }); return pronto(); }
    case "contato_tirar": p.contatos = p.contatos.filter(c => c.id !== Number(d.id)); return pronto();
    case "horario": { if ((e = exigeAtivo())) return e;
      const cmp = inteiro(d.cmp); if (cmp == null || cmp < 1 || cmp > MAX_CMP) return erro("Compartimento de 1 a " + MAX_CMP + ".");
      let hora = String(d.hora || "").trim(); if (/^\d:\d\d$/.test(hora)) hora = "0" + hora;
      if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(hora)) return erro("Hora no formato 08:00.");
      const dias = (d.dias || []).filter(x => /^[1-7]$/.test(x)).sort().join(""); if (!dias) return erro("Escolha pelo menos um dia da semana.");
      const tol = d.tolerancia === "" || d.tolerancia == null ? TOL_PADRAO : inteiro(d.tolerancia);
      if (tol == null || tol < 5 || tol > 240) return erro("Tolerância de 5 a 240 minutos.");
      if (p.horarios.some(h => !h.removido && h.cmp === cmp && h.hora === hora)) return erro("Este compartimento já tem esse horário.");
      p.horarios.push({ id: ++db.seq, cmp, hora, dias, remedio: String(d.remedio || "").trim(), dose: String(d.dose || "").trim(), tolerancia: tol, criado: agora });
      return pronto(); }
    case "horario_tirar": p.horarios.forEach(h => { if (h.id === Number(d.id) && !h.removido) h.removido = agora; }); return pronto();
    case "dispositivo": { if ((e = exigeAtivo())) return e;
      const no = inteiro(d.no), tipo = String(d.tipo || "").toUpperCase();
      if (no == null || no < 1 || no > 99) return erro("Número do aparelho (ID) de 1 a 99.");
      if (tipo !== "MED" && tipo !== "PUL") return erro("Escolha o tipo do aparelho.");
      if (db.pessoas.some(x => x.dispositivos.some(a => a.no === no))) return erro("Este número de aparelho já está em uso.");
      p.dispositivos.push({ no, tipo, apelido: String(d.apelido || "").trim(), visto: null, bat: null }); return pronto(); }
    case "dispositivo_tirar": p.dispositivos = p.dispositivos.filter(a => a.no !== Number(d.no)); return pronto();
    case "dose": { if ((e = exigeAtivo())) return e;
      const h = p.horarios.find(x => x.id === Number(d.horario)); if (!h) return erro("Horário não encontrado.");
      p.doses.push({ horario: h.id, dia: d.dia, cmp: h.cmp, evento: "TOMADO", quando: agora, origem: "tela" }); return pronto(); }
    case "alerta_visto": p.alertas.forEach(a => { if (a.id === Number(d.id) && !a.visto) { a.visto = agora; a.visto_por = "você"; } }); return pronto();
    case "simular_crise": case "simular_calma": { if ((e = exigeAtivo())) return e;
      const crise = acao === "simular_crise", pos = p.posicao || { lat: -22.5051, lon: -43.1784, gps: true, mov: 0, bat: 3.8 };
      p.posicao = Object.assign({}, pos, { crise, bpm: crise ? 131 : 88, mov: crise ? 2 : 0, quando: agora, gps: true,
        lat: pos.lat + (crise ? 0.0007 : 0), lon: pos.lon + (crise ? 0.0004 : 0) });
      p.posicao.ultimo_gps = { lat: p.posicao.lat, lon: p.posicao.lon, quando: agora };
      if (crise) {
        const aberto = p.alertas.find(a => a.tipo === "crise" && !a.visto && a.atualizado >= agora - 900);
        if (aberto) { aberto.atualizado = agora; aberto.lat = p.posicao.lat; aberto.lon = p.posicao.lon; }
        else novoAlerta(db, p, "crise", `Possível crise de ${p.nome} às ${fmtHora(agora)}. Último local (GPS): ${p.posicao.lat.toFixed(5)}, ${p.posicao.lon.toFixed(5)}.`,
          "crise:" + p.id + ":" + Math.round(agora), agora, p.posicao.lat, p.posicao.lon);
      }
      return pronto(); }
  }
  return erro("Ação desconhecida.");
}

/* ════════ Conversa com o computador central ════════ */
function estadoAtual() {
  if (ui.modo !== "hub") return visaoDemo(lerDemo(), Date.now() / 1000);
  if (!ui.saudeCarregando && Date.now() - (ui.saudeEm || 0) > 30000) carregar();
  return ui.saude || null;
}

async function carregar() {
  ui.saudeCarregando = true;
  try {
    const r = await fetch("api/saude/estado", { cache: "no-store" });
    if (r.status === 401) { ui.saude = null; ui.saudeErro = "Entre com seu usuário e senha para ver os dados de saúde."; }
    else if (!r.ok) ui.saudeErro = "O computador central não respondeu à parte de Saúde (ela pode ainda não estar instalada).";
    else { ui.saude = await r.json(); ui.saudeErro = ""; }
  } catch (e) { ui.saudeErro = "Sem resposta do computador central. Mostrando os últimos dados recebidos."; }
  ui.saudeEm = Date.now(); ui.saudeCarregando = false;
  desenhar(false);
}

async function executar(acao, dados, foco) {
  let r;
  if (ui.modo === "hub") {
    try {
      const resp = await fetch("api/saude/" + acao, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados) });
      r = await resp.json();
    } catch (e) { r = { ok: false, erro: "Sem resposta do computador central." }; }
  } else r = acaoDemo(acao, dados);
  ui.saudeMsg = r.ok ? (MSG_OK[acao] || "Feito.") : (r.erro || "Não deu certo.");
  ui.saudeMsgErro = !r.ok;
  if (r.ok) {
    if (r.pessoa) ui.saudePessoa = r.pessoa;
    if (acao === "apagar") ui.saudePessoa = null;
    if (ui.saudeRasc && FORM_DE[acao]) delete ui.saudeRasc[FORM_DE[acao]];
  }
  if (ui.modo === "hub" && r.ok) { await carregar(); } else desenhar(false);
  const alvo = foco && el(foco) ? foco : "saude-msg"; const f = el(alvo); if (f) f.focus();
  return r;
}
const MSG_OK = { pessoa: "Pessoa cadastrada, com o consentimento registrado.", consentimento: "Consentimento registrado.",
  revogar: "Consentimento retirado. Os aparelhos desta pessoa deixam de ser lidos e ninguém é avisado.",
  apagar: "Todos os dados da pessoa foram apagados.", acesso_dar: "Autorização dada.", acesso_tirar: "Autorização retirada.",
  contato: "Cuidador incluído.", contato_tirar: "Cuidador retirado.", horario: "Horário incluído.", horario_tirar: "Horário retirado.",
  dispositivo: "Aparelho ligado à pessoa.", dispositivo_tirar: "Aparelho desligado da pessoa.", dose: "Dose confirmada.",
  alerta_visto: "Aviso marcado como visto.", restaurar_demo: "O exemplo recomeçou.", simular_crise: "Crise simulada: veja o aviso.",
  simular_calma: "A pulseira voltou ao normal." };
const FORM_DE = { pessoa: "pessoa", consentimento: "consentimento", acesso_dar: "acesso", contato: "contato", horario: "horario", dispositivo: "dispositivo" };

/* ════════ Pedaços de tela ════════ */
const fmtHora = s => s ? new Date(s * 1000).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : "—";
const fmtDataHora = s => s ? new Date(s * 1000).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—";
const fmtDia = d => d ? d.slice(8, 10) + "/" + d.slice(5, 7) : "—";
const pct = x => x == null ? "—" : n2(x * 100, 0) + "%";
const selo = estado => { const s = SITUACAO[estado] || ["in", estado]; return `<span class="selo ${s[0]}">${esc(s[1])}</span>`; };
const diasTexto = d => d === "1234567" ? "todos os dias" : DIAS.filter(x => String(d).indexOf(x[0]) >= 0).map(x => x[1]).join(", ");
const rasc = (form, nome, padrao) => { const r = ui.saudeRasc && ui.saudeRasc[form]; return r && r[nome] != null ? r[nome] : padrao; };
const botao = (acao, texto, extra, rotulo, id) => `<button type="button" ${id ? `id="${id}"` : ""} data-saude-acao="${acao}" ${extra || ""}${rotulo ? ` aria-label="${esc(rotulo)}"` : ""}>${esc(texto)}</button>`;

function campo(form, nome, rotulo, tipo, extra, ajuda) {
  const id = `saude-${form}-${nome}`;
  return `<div><label for="${id}">${esc(rotulo)}</label><br><input id="${id}" name="${nome}" type="${tipo || "text"}" value="${esc(rasc(form, nome, ""))}" ${extra || ""}${ajuda ? ` aria-describedby="${id}-a"` : ""}>${ajuda ? `<br><span id="${id}-a" class="t2 pq">${esc(ajuda)}</span>` : ""}</div>`;
}
function marcar(form, nome, rotulo, padrao) {
  const id = `saude-${form}-${nome}`, v = rasc(form, nome, padrao);
  return `<div><input id="${id}" name="${nome}" type="checkbox" ${v ? "checked" : ""}> <label for="${id}">${esc(rotulo)}</label></div>`;
}
function escolha(form, nome, rotulo, ops, padrao) {
  const id = `saude-${form}-${nome}`, v = rasc(form, nome, padrao);
  return `<div><label for="${id}">${esc(rotulo)}</label><br><select id="${id}" name="${nome}">${ops.map(o => `<option value="${esc(o[0])}" ${o[0] === v ? "selected" : ""}>${esc(o[1])}</option>`).join("")}</select></div>`;
}

function avisos(S, P) {
  const crises = S.alertas.filter(a => a.tipo === "crise");
  let h = "";
  if (crises.length) h += `<div class="faixa al" role="alert" data-anuncio="Alerta de crise"><strong>Alerta da pulseira.</strong> ${crises.map(a =>
    `${esc(a.mensagem)} <span class="t2">(atualizado às ${fmtHora(a.atualizado)})</span> ${botao("alerta_visto", "Estou cuidando", `data-saude-id="${a.id}" data-saude-de="${a.pessoa}"`, "Marcar o alerta de " + a.nome + " como visto")}`).join("<br>")}</div>`;
  const outros = P && P.ativo ? S.alertas.filter(a => a.tipo !== "crise" && a.pessoa === P.id) : [];
  h += `<div aria-live="polite">${outros.length ? `<div class="faixa at"><strong>${outros.length === 1 ? "1 aviso" : outros.length + " avisos"} sem resposta.</strong><ul>${outros.map(a =>
    `<li>${esc(a.mensagem)} ${botao("alerta_visto", "Ciente", `data-saude-id="${a.id}" data-saude-de="${a.pessoa}"`, "Marcar como visto: " + a.mensagem)}</li>`).join("")}</ul></div>` : ""}</div>`;
  return h;
}

function parteHoje(S, P) {
  const prox = P.proximas[0];
  const ad = P.adesao.semana;
  let h = `<div class="grade">
    <section class="cartao" aria-labelledby="saude-h-prox"><h2 id="saude-h-prox" class="t3">Próxima dose</h2>${prox
      ? `<p class="numero">${esc(prox.hora)}</p><p>${prox.dia !== diaDe(S.agora) ? "Amanhã · " : ""}Compartimento ${prox.cmp}${prox.remedio ? " · " + esc(prox.remedio) : ""}${prox.dose ? " · " + esc(prox.dose) : ""}</p><p>${selo(prox.estado)}</p>`
      : `<p class="t2">Nenhuma dose marcada nas próximas 24 horas.</p>`}</section>
    <section class="cartao" aria-labelledby="saude-h-ad"><h2 id="saude-h-ad" class="t3">Remédios tomados nos últimos 7 dias</h2>
      <p class="numero">${pct(ad.taxa)}</p><p class="t2">${ad.total ? `${ad.tomadas + ad.atrasadas} de ${ad.total} doses (${ad.atrasadas} com atraso).` : "Ainda sem doses para contar."}</p></section>
  </div>`;
  if (!P.horarios.length) return h + `<p class="t2">Nenhum horário marcado ainda. Use “Horários e remédios” para cadastrar.</p>`;
  h += `<div class="rolagem"><table><caption>Doses de hoje, ${fmtDia(diaDe(S.agora))}</caption>
    <thead><tr><th scope="col">Hora</th><th scope="col">Compartimento</th><th scope="col">Remédio</th><th scope="col">Situação</th><th scope="col">Ação</th></tr></thead><tbody>${
    P.hoje.map(o => `<tr><td>${esc(o.hora)}</td><td>${o.cmp}</td><td>${esc(o.remedio || "—")}${o.dose ? ` <span class="t2">(${esc(o.dose)})</span>` : ""}</td><td>${selo(o.estado)}</td><td>${
      o.estado === "pendente" || o.estado === "esquecido" ? botao("dose", "Marcar como tomado", `data-saude-horario="${o.horario}" data-saude-dia="${o.dia}"`, `Marcar como tomada a dose das ${o.hora}`, `saude-dose-${o.horario}`) : ""}</td></tr>`).join("")
    || `<tr><td colspan="5">Sem doses marcadas para hoje.</td></tr>`}</tbody></table></div>
    <p class="t2 pq">“Marcar como tomado” serve para quando a caixinha está sem rede ou o remédio foi dado à mão. Fica anotado quem confirmou.</p>`;
  return h;
}

function parteHorarios(S, P) {
  const lista = P.horarios;
  let h = `<div class="rolagem"><table><caption>Horários marcados (${lista.length})</caption>
    <thead><tr><th scope="col">Hora</th><th scope="col">Compartimento</th><th scope="col">Dias</th><th scope="col">Remédio</th><th scope="col">Dose</th><th scope="col">Tolerância</th><th scope="col">Ação</th></tr></thead><tbody>${
    lista.map(x => `<tr><td>${esc(x.hora)}</td><td>${x.cmp}</td><td>${esc(diasTexto(x.dias))}</td><td>${esc(x.remedio || "—")}</td><td>${esc(x.dose || "—")}</td><td>${x.tolerancia} min</td><td>${
      botao("horario_tirar", "Retirar", `data-saude-id="${x.id}"`, `Retirar o horário das ${x.hora}, compartimento ${x.cmp}`)}</td></tr>`).join("")
    || `<tr><td colspan="7">Nenhum horário ainda.</td></tr>`}</tbody></table></div>`;
  const diasSel = rasc("horario", "dias", ["1", "2", "3", "4", "5", "6", "7"]);
  h += `<form class="cartao" data-saude-form="horario" aria-labelledby="saude-h-novohor"><h2 id="saude-h-novohor" class="t3">Novo horário</h2>
    <div class="precos">${campo("horario", "cmp", `Compartimento (1 a ${S.max_cmp || MAX_CMP})`, "text", 'inputmode="numeric" required')}
    ${campo("horario", "hora", "Hora", "time", "required")}
    ${campo("horario", "remedio", "Remédio", "text", 'maxlength="80"')}
    ${campo("horario", "dose", "Quanto tomar", "text", 'maxlength="40" placeholder="1 comprimido"')}
    ${campo("horario", "tolerancia", "Tolerância (minutos)", "text", `inputmode="numeric" placeholder="${S.tolerancia_padrao || TOL_PADRAO}"`, "Tempo para confirmar antes de contar como não tomado.")}</div>
    <fieldset><legend>Dias da semana</legend><div class="chips">${DIAS.map(([k, n]) =>
      `<span><input type="checkbox" id="saude-horario-dia${k}" name="dias" value="${k}" ${diasSel.indexOf(k) >= 0 ? "checked" : ""}> <label for="saude-horario-dia${k}">${n}</label></span>`).join(" ")}</div></fieldset>
    <p><button type="submit" id="saude-horario-enviar">Incluir horário</button></p></form>
    <p class="t2 pq">A caixinha de hoje tem 4 compartimentos e toca às 08, 12 e 18 h; a versão com Wi-Fi vai receber estes horários do computador central.</p>`;
  return h;
}

function parteHistorico(S, P) {
  const s = P.adesao.semana, m = P.adesao.mes;
  let h = `<div class="grade">
    <section class="cartao"><h2 class="t3">Últimos 7 dias</h2><p class="numero">${pct(s.taxa)}</p><p class="t2">${s.tomadas + s.atrasadas} de ${s.total} doses tomadas.</p></section>
    <section class="cartao"><h2 class="t3">Últimos 30 dias</h2><p class="numero">${pct(m.taxa)}</p><p class="t2">${m.tomadas + m.atrasadas} de ${m.total} doses tomadas.</p></section>
    <section class="cartao"><h2 class="t3">No horário certo (30 dias)</h2><p class="numero">${pct(m.taxa_no_horario)}</p><p class="t2">${m.atrasadas} com atraso e ${m.esquecidas} não tomadas.</p></section>
  </div>
  <p class="t2 pq">Adesão é a parte das doses marcadas que foi tomada. Doses que ainda estão no horário não entram na conta.</p>`;
  const dias = m.por_dia.filter(d => d.total).reverse();
  h += `<div class="rolagem"><table><caption>Adesão por dia (30 dias)</caption>
    <thead><tr><th scope="col">Dia</th><th scope="col">Doses</th><th scope="col">Tomadas</th><th scope="col">Com atraso</th><th scope="col">Não tomadas</th><th scope="col">Adesão</th></tr></thead><tbody>${
    dias.map(d => `<tr><td>${fmtDia(d.dia)}</td><td>${d.total}</td><td>${d.tomadas}</td><td>${d.atrasadas}</td><td>${d.esquecidas}</td><td><meter min="0" max="100" value="${Math.round((d.taxa || 0) * 100)}" aria-hidden="true"></meter> ${pct(d.taxa)}</td></tr>`).join("")
    || `<tr><td colspan="6">Ainda sem doses para contar.</td></tr>`}</tbody></table></div>`;
  h += `<div class="rolagem"><table><caption>O que aconteceu (últimos registros)</caption>
    <thead><tr><th scope="col">Quando</th><th scope="col">Dose das</th><th scope="col">Compartimento</th><th scope="col">Remédio</th><th scope="col">O que houve</th><th scope="col">Quem avisou</th></tr></thead><tbody>${
    P.eventos.slice(0, 50).map(e => `<tr><td>${fmtDataHora(e.quando)}</td><td>${e.hora ? esc(e.hora) + " de " + fmtDia(e.dia) : "fora do horário"}</td><td>${e.cmp}</td><td>${esc(e.remedio || "—")}</td><td>${
      `<span class="selo ${e.evento === "TOMADO" ? "ok" : e.evento === "ATRASO" ? "at" : "al"}">${esc(EVENTO[e.evento] || e.evento)}</span>`}</td><td>${esc(ORIGEM[e.origem] || e.origem)}</td></tr>`).join("")
    || `<tr><td colspan="6">Nada registrado nos últimos 30 dias.</td></tr>`}</tbody></table></div>`;
  return h;
}

function partePulseira(S, P) {
  const tem = P.dispositivos.some(d => d.tipo === "PUL"), pos = P.posicao;
  let h = "";
  if (!tem) h += `<p class="faixa in">Nenhuma pulseira ligada a ${esc(P.nome)}. Em “Pessoas e consentimento”, ligue o aparelho pelo número (ID) dele.</p>`;
  if (pos) {
    h += `<div class="grade">
      <section class="cartao" aria-labelledby="saude-h-pul"><h2 id="saude-h-pul" class="t3">Agora</h2>
        <p>${pos.crise ? '<span class="selo al">Possível crise</span>' : '<span class="selo ok">Sem sinal de crise</span>'}</p>
        <p class="t2">Última notícia da pulseira: ${fmtDataHora(pos.quando)}</p></section>
      <section class="cartao"><h2 class="t3">Onde está</h2>${pos.gps
        ? `<p>Latitude ${n2(pos.lat, 5)}<br>Longitude ${n2(pos.lon, 5)}</p>`
        : `<p>Sem posição do GPS agora.${pos.ultimo_gps ? `<br><span class="t2">Última posição: ${n2(pos.ultimo_gps.lat, 5)}, ${n2(pos.ultimo_gps.lon, 5)} às ${fmtHora(pos.ultimo_gps.quando)}</span>` : ""}</p>`}</section>
      <section class="cartao"><h2 class="t3">Corpo e bateria</h2><p>Batimentos: ${pos.bpm != null ? n2(pos.bpm, 0) + " por minuto" : "sem leitura"}<br>
        Movimento: ${pos.mov != null ? esc(MOV[pos.mov] || "—") : "sem leitura"}<br>Bateria: ${pos.bat != null ? n2(pos.bat, 2) + " V" : "sem leitura"}</p></section>
    </div>`;
  } else if (tem) h += `<p class="t2">A pulseira ainda não mandou nenhuma notícia.</p>`;
  if (S.demo && tem) h += `<p>${botao("simular_crise", "Simular crise (exemplo)", "", "", "saude-sim-crise")} ${botao("simular_calma", "Simular volta ao normal (exemplo)", "", "", "saude-sim-calma")}</p>`;
  h += `<div class="rolagem"><table><caption>Avisos de ${esc(P.nome)} (os 30 mais recentes)</caption>
    <thead><tr><th scope="col">Quando</th><th scope="col">Tipo</th><th scope="col">Mensagem</th><th scope="col">Visto</th></tr></thead><tbody>${
    P.alertas.map(a => `<tr><td>${fmtDataHora(a.criado)}</td><td>${a.tipo === "crise" ? '<span class="selo al">Crise</span>' : a.tipo === "bateria" ? '<span class="selo in">Bateria</span>' : '<span class="selo at">Dose</span>'}</td><td>${esc(a.mensagem)}</td><td>${
      a.visto ? fmtDataHora(a.visto) + (a.visto_por ? " · " + esc(a.visto_por) : "") : botao("alerta_visto", "Ciente", `data-saude-id="${a.id}"`, "Marcar como visto: " + a.mensagem)}</td></tr>`).join("")
    || `<tr><td colspan="4">Nenhum aviso.</td></tr>`}</tbody></table></div>
    <p class="t2 pq">Os cuidadores com e-mail recebem cada aviso na hora. O local da pulseira é guardado por 30 dias e depois apagado.</p>`;
  return h;
}

function formConsentimento(form, S, menor) {
  return `<fieldset><legend>Consentimento (LGPD)</legend>
    <p class="t2" id="saude-${form}-fin">${esc(S.finalidade || FINALIDADE)}</p>
    ${menor === true ? `<p class="t2">Para menor de 18 anos, quem consente é o responsável legal.</p>` : escolha(form, "papel", "Quem dá o consentimento", [["titular", "A própria pessoa"], ["responsavel", "O responsável legal"]], "titular")}
    ${campo(form, "quem", "Nome de quem consente", "text", 'maxlength="80"', "Se ficar em branco, vale o nome da pessoa ou do responsável.")}
    ${marcar(form, "aceito", "Li a finalidade acima e concordo que estes dados de saúde sejam guardados e usados para isso.", false)}
  </fieldset>`;
}

function partePessoas(S, P) {
  let h = `<div class="rolagem"><table><caption>Pessoas acompanhadas que você pode ver (${S.pessoas.length})</caption>
    <thead><tr><th scope="col">Nome</th><th scope="col">Idade</th><th scope="col">Consentimento</th><th scope="col">Dado por</th><th scope="col">Quando</th></tr></thead><tbody>${
    S.pessoas.map(p => { const c = p.consentimento || {}, i = idadeDe(p.nascimento, S.agora);
      return `<tr><td>${esc(p.nome)}</td><td>${i != null ? i + " anos" : "—"}${p.menor ? ' <span class="selo in">menor</span>' : ""}</td><td>${p.ativo ? '<span class="selo ok">Válido</span>' : '<span class="selo al">Retirado</span>'}</td><td>${esc(c.quem || "—")}${c.papel === "responsavel" ? " (responsável)" : ""}</td><td>${fmtDataHora(p.ativo ? c.dado : c.revogado)}</td></tr>`; }).join("")
    || `<tr><td colspan="5">Ninguém cadastrado ainda (ou você ainda não foi autorizado a ver alguém).</td></tr>`}</tbody></table></div>`;

  if (P) {
    const c = P.consentimento || {};
    h += `<section class="cartao" aria-labelledby="saude-h-cons"><h2 id="saude-h-cons" class="t3">Consentimento de ${esc(P.nome)}</h2>
      <p>${P.ativo ? `<span class="selo ok">Válido</span> Dado por ${esc(c.quem)}${c.papel === "responsavel" ? " (responsável legal)" : ""} em ${fmtDataHora(c.dado)}, termo versão ${esc(c.versao || "1")}.`
        : `<span class="selo al">Retirado</span> em ${fmtDataHora(c.revogado)}. Nada novo é guardado e ninguém é avisado.`}</p>
      ${P.menor ? `<p class="t2">Menor de idade. Responsável legal: ${esc(P.responsavel || "—")}.</p>` : ""}
      ${P.ativo ? `<p>${botao("revogar", "Retirar o consentimento", "", "Retirar o consentimento de " + P.nome, "saude-revogar")}</p>`
        : `<form data-saude-form="consentimento" aria-label="Registrar novo consentimento">${formConsentimento("consentimento", S, P.menor)}<p><button type="submit" id="saude-consentimento-enviar">Registrar novo consentimento</button></p></form>`}
      <p>${botao("apagar", "Apagar todos os dados desta pessoa", "", "Apagar todos os dados de " + P.nome, "saude-apagar")}</p>
      <p class="t2 pq">Apagar remove horários, histórico, local da pulseira, avisos, cuidadores e o próprio cadastro. Não dá para desfazer.</p></section>`;
    if (P.ativo) {
      h += `<section class="cartao" aria-labelledby="saude-h-acesso"><h2 id="saude-h-acesso" class="t3">Quem pode ver os dados de ${esc(P.nome)}</h2>
        <ul>${P.acesso.map(u => `<li>${esc(u)} ${P.acesso.length > 1 ? botao("acesso_tirar", "Tirar", `data-saude-usuario="${esc(u)}"`, "Tirar a autorização de " + u) : ""}</li>`).join("")}</ul>
        <form data-saude-form="acesso" aria-label="Autorizar outra pessoa"><div class="precos">${campo("acesso", "usuario", ui.modo === "hub" ? "Usuário da plataforma a autorizar" : "Usuário a autorizar", "text", 'autocomplete="off" required')}</div>
        <p><button type="submit" id="saude-acesso-enviar">Autorizar</button></p></form>
        <p class="t2 pq">Só a pessoa (ou o responsável) decide quem vê. Nem a administração da plataforma vê sem autorização.</p></section>`;
      h += `<section class="cartao" aria-labelledby="saude-h-cont"><h2 id="saude-h-cont" class="t3">Cuidadores que recebem avisos</h2>
        <ul>${P.contatos.map(x => `<li>${esc(x.nome)}${x.email ? " · " + esc(x.email) : ""}${x.telefone ? " · " + esc(x.telefone) : ""} ${x.alerta ? '<span class="selo ok">recebe avisos</span>' : '<span class="selo in">sem avisos</span>'} ${
          botao("contato_tirar", "Retirar", `data-saude-id="${x.id}"`, "Retirar o cuidador " + x.nome)}</li>`).join("") || "<li>Nenhum cuidador cadastrado.</li>"}</ul>
        <form data-saude-form="contato" aria-label="Novo cuidador"><div class="precos">${campo("contato", "nome", "Nome", "text", 'maxlength="80" required')}
          ${campo("contato", "email", "E-mail", "email", 'maxlength="120"')}${campo("contato", "telefone", "Telefone", "tel", 'maxlength="30"')}</div>
          ${marcar("contato", "alerta", "Recebe os avisos por e-mail", true)}
          <p><button type="submit" id="saude-contato-enviar">Incluir cuidador</button></p></form></section>`;
      h += `<section class="cartao" aria-labelledby="saude-h-apar"><h2 id="saude-h-apar" class="t3">Aparelhos de ${esc(P.nome)}</h2>
        <ul>${P.dispositivos.map(a => `<li>${a.tipo === "MED" ? "Caixinha de remédios" : "Pulseira"} nº ${a.no}${a.apelido ? " · " + esc(a.apelido) : ""} · ${a.visto ? "última notícia " + fmtDataHora(a.visto) : "ainda sem notícia"}${a.bat != null ? " · bateria " + n2(a.bat, 2) + " V" : ""} ${
          botao("dispositivo_tirar", "Desligar", `data-saude-no="${a.no}"`, "Desligar o aparelho número " + a.no)}</li>`).join("") || "<li>Nenhum aparelho ligado.</li>"}</ul>
        <form data-saude-form="dispositivo" aria-label="Ligar aparelho"><div class="precos">${campo("dispositivo", "no", "Número do aparelho (ID, 1 a 99)", "text", 'inputmode="numeric" required')}
          ${escolha("dispositivo", "tipo", "Tipo", [["MED", "Caixinha de remédios"], ["PUL", "Pulseira"]], "MED")}${campo("dispositivo", "apelido", "Apelido", "text", 'maxlength="40" placeholder="Caixinha da cozinha"')}</div>
          <p><button type="submit" id="saude-dispositivo-enviar">Ligar aparelho</button></p></form></section>`;
    }
  }
  const nasc = rasc("pessoa", "nascimento", ""), idade = nasc ? idadeDe(nasc, S.agora) : null;
  h += `<form class="cartao" data-saude-form="pessoa" aria-labelledby="saude-h-nova"><h2 id="saude-h-nova" class="t3">Cadastrar pessoa acompanhada</h2>
    <div class="precos">${campo("pessoa", "nome", "Nome", "text", 'maxlength="80" required')}
    ${campo("pessoa", "nascimento", "Data de nascimento", "date", "", "Com a data, o sistema sabe se é menor de idade.")}
    ${campo("pessoa", "responsavel", "Responsável legal (obrigatório para menor)", "text", 'maxlength="80"')}</div>
    ${idade != null && idade < 18 ? `<p class="faixa in">Menor de 18 anos: o consentimento é do responsável legal.</p>` : ""}
    ${formConsentimento("pessoa", S, idade != null && idade < 18)}
    <p><button type="submit" id="saude-pessoa-enviar">Cadastrar com consentimento</button></p></form>`;
  return h;
}

/* ════════ A aba ════════ */
window.telaSaude = function telaSaude() {
  const S = estadoAtual(), sub = ui.saudeSub || "hoje";
  let h = `<h1>Saúde</h1><p class="t2">Caixinha de remédios e pulseira de alerta. Funcionam juntas ou separadas.</p>`;
  if (ui.modo !== "hub") h += `<p class="faixa in">Demonstração: as pessoas abaixo são de exemplo e tudo fica só neste navegador. ${botao("restaurar_demo", "Recomeçar o exemplo", "", "", "saude-restaurar")}</p>`;
  h += `<p id="saude-msg" tabindex="-1" role="status" aria-live="polite" class="${ui.saudeMsg ? (ui.saudeMsgErro ? "faixa al" : "faixa ok") : "so-leitor"}">${esc(ui.saudeMsg || "")}</p>`;
  if (!S) return h + (ui.saudeErro ? `<p class="faixa al" role="alert">${esc(ui.saudeErro)}</p>` : `<p aria-live="polite">Carregando…</p>`);
  if (ui.saudeErro) h += `<p class="faixa at">${esc(ui.saudeErro)}</p>`;
  const P = S.pessoas.find(p => p.id === ui.saudePessoa) || S.pessoas[0] || null;
  h += avisos(S, P);
  if (S.pessoas.length > 1) h += `<div class="chips" role="group" aria-label="Pessoa acompanhada">${S.pessoas.map(p =>
    `<button type="button" id="saude-p-${p.id}" data-saude-pessoa="${p.id}" aria-pressed="${!!P && p.id === P.id}">${esc(p.nome)}</button>`).join("")}</div>`;
  else if (P) h += `<p>Pessoa acompanhada: <strong>${esc(P.nome)}</strong></p>`;
  h += `<div class="chips" role="group" aria-label="Partes da Saúde">${SUBS.map(([k, n]) =>
    `<button type="button" id="saude-sub-${k}" data-saude-sub="${k}" aria-pressed="${k === sub}">${esc(n)}</button>`).join("")}</div>`;
  const titulo = (SUBS.find(s => s[0] === sub) || SUBS[0])[1];
  h += `<h2 class="so-leitor">${esc(titulo)}</h2>`;
  if (sub === "pessoas") return h + partePessoas(S, P);
  if (!P) return h + `<p class="faixa in">Ninguém para mostrar. ${botao("ir_pessoas", "Cadastrar uma pessoa", "", "", "saude-ir-pessoas")}</p>`;
  if (!P.ativo) return h + `<p class="faixa al">O consentimento de ${esc(P.nome)} foi retirado: os dados de saúde não são mostrados. ${botao("ir_pessoas", "Ver o consentimento", "", "", "saude-ir-pessoas")}</p>`;
  if (sub === "horarios") return h + parteHorarios(S, P);
  if (sub === "historico") return h + parteHistorico(S, P);
  if (sub === "pulseira") return h + partePulseira(S, P);
  return h + parteHoje(S, P);
};

/* ════════ Eventos (atributos data-saude-…) ════════ */
function lerForm(f) {
  const fd = new FormData(f), o = {};
  fd.forEach((v, k) => { if (k === "dias") (o.dias = o.dias || []).push(String(v)); else o[k] = String(v); });
  f.querySelectorAll('input[type="checkbox"]').forEach(c => { if (c.name !== "dias") o[c.name] = c.checked; });
  if (!o.dias && f.querySelector('input[name="dias"]')) o.dias = [];
  return o;
}

if (typeof document !== "undefined" && !window.__saudeEventos) {
  window.__saudeEventos = true;
  const guardarRascunho = ev => {
    const t = ev.target, f = t && t.form;
    if (!f || !f.dataset || !f.dataset.saudeForm) return;
    ui.saudeRasc = ui.saudeRasc || {};
    ui.saudeRasc[f.dataset.saudeForm] = lerForm(f);
    if (f.dataset.saudeForm === "pessoa" && t.name === "nascimento" && ev.type === "change") { const id = t.id; desenhar(false); const x = el(id); if (x) x.focus(); }
  };
  document.addEventListener("input", guardarRascunho);
  document.addEventListener("change", guardarRascunho);
  document.addEventListener("submit", ev => {
    const f = ev.target;
    if (!f || !f.dataset || !f.dataset.saudeForm) return;
    ev.preventDefault();
    const tipo = f.dataset.saudeForm, d = lerForm(f);
    ui.saudeRasc = ui.saudeRasc || {}; ui.saudeRasc[tipo] = d;
    const sel = () => { const S = ui.modo === "hub" ? ui.saude : visaoDemo(lerDemo(), Date.now() / 1000); const P = S && (S.pessoas.find(p => p.id === ui.saudePessoa) || S.pessoas[0]); return P ? P.id : null; };
    const consent = { aceito: d.aceito === true, papel: d.papel || "titular", quem: d.quem || "" };
    let acao = tipo, dados;
    if (tipo === "pessoa") dados = { nome: d.nome, nascimento: d.nascimento, responsavel: d.responsavel, consentimento: consent };
    else if (tipo === "consentimento") dados = { pessoa: sel(), consentimento: consent };
    else if (tipo === "acesso") { acao = "acesso_dar"; dados = { pessoa: sel(), usuario: d.usuario }; }
    else if (tipo === "contato") dados = { pessoa: sel(), nome: d.nome, email: d.email, telefone: d.telefone, alerta: d.alerta === true };
    else if (tipo === "horario") dados = { pessoa: sel(), cmp: numBr(d.cmp), hora: d.hora, dias: d.dias, remedio: d.remedio, dose: d.dose,
      tolerancia: String(d.tolerancia || "").trim() === "" ? "" : numBr(d.tolerancia) };
    else if (tipo === "dispositivo") dados = { pessoa: sel(), no: numBr(d.no), tipo: d.tipo, apelido: d.apelido };
    else return;
    executar(acao, dados, `saude-${tipo}-enviar`);
  });
  document.addEventListener("click", ev => {
    const b = ev.target && ev.target.closest ? ev.target.closest("button") : null;
    if (!b || !b.dataset) return;
    if (b.dataset.saudeSub) { ui.saudeSub = b.dataset.saudeSub; ui.saudeMsg = ""; desenhar(false); const x = el("saude-sub-" + b.dataset.saudeSub); if (x) x.focus(); return; }
    if (b.dataset.saudePessoa) { ui.saudePessoa = Number(b.dataset.saudePessoa); ui.saudeMsg = ""; desenhar(false); const x = el("saude-p-" + b.dataset.saudePessoa); if (x) x.focus(); return; }
    const acao = b.dataset.saudeAcao;
    if (!acao) return;
    if (acao === "ir_pessoas") { ui.saudeSub = "pessoas"; desenhar(false); const x = el("saude-sub-pessoas"); if (x) x.focus(); return; }
    const S = ui.modo === "hub" ? ui.saude : visaoDemo(lerDemo(), Date.now() / 1000);
    const P = S && (S.pessoas.find(p => p.id === ui.saudePessoa) || S.pessoas[0]);
    const dados = { pessoa: b.dataset.saudeDe ? Number(b.dataset.saudeDe) : (P ? P.id : null) };
    if (b.dataset.saudeId) dados.id = Number(b.dataset.saudeId);
    if (b.dataset.saudeNo) dados.no = Number(b.dataset.saudeNo);
    if (b.dataset.saudeUsuario) dados.usuario = b.dataset.saudeUsuario;
    if (b.dataset.saudeHorario) { dados.horario = Number(b.dataset.saudeHorario); dados.dia = b.dataset.saudeDia; }
    const nome = P ? P.nome : "esta pessoa";
    if (acao === "apagar" && !window.confirm(`Apagar TODOS os dados de ${nome}? Não dá para desfazer.`)) return;
    if (acao === "revogar" && !window.confirm(`Retirar o consentimento de ${nome}? Os aparelhos deixam de ser lidos e ninguém mais é avisado.`)) return;
    if (acao === "restaurar_demo" && !window.confirm("Apagar o que você mudou e voltar ao exemplo inicial?")) return;
    executar(acao, dados);
  });
}
})();
