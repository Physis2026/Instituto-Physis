/* physis-parceiros.js — Marketplace de serviços: "Profissionais parceiros" na loja e curadoria na Gestão.
   Servidor: physis-hub/physis_hub/parceiros.py (rotas /api/parceiros*). Sem internet: só o próprio hub.
   Contrato:
     PARCEIROS.montarLoja(elemento, op)      vitrine pública (por especialidade e região), pedido de orçamento
                                             (vira pedido na Central) e "Quero ser parceiro" (candidatura com consentimento)
     PARCEIROS.montarCuradoria(elemento, op) tela interna da Gestão: lista, pendências, documentos com validade,
                                             avaliações; aprovar/suspender só para a direção (o servidor também confere)
       op (opcional) = { idioma: function () { return "pt" | "en"; } }; sem ele, vale o lang do <html>
       (a plataforma e a Gestão mudam o lang ao trocar o idioma; a tela se redesenha sozinha quando ele muda).
     PARCEIROS.cpfValido(v), PARCEIROS.cnpjValido(v)  mesma conta do parceiros.py
     PARCEIROS.I18N = { "texto em português": "English" }, PARCEIROS.I18N_RX = [[padrão, inglês]], PARCEIROS.t(s)
       (como PhysisConta: o texto da tela nasce em português e passa por t(); as mensagens do servidor também).
   Não usa h1 (a tela que hospeda já tem o seu título). Dados pessoais: a loja nunca recebe CPF/CNPJ, contato
   nem número de registro do parceiro; o contato de quem pede orçamento só vai com o consentimento marcado. */
(function (global) {
"use strict";

const ESPECIALIDADES = { solar:"Energia solar", avac:"AVAC (ar-condicionado e ventilação)", hidraulica:"Hidráulica", eletrica:"Elétrica", sbn:"SbN e paisagismo", automacao:"Automação" };
const TIPOS_DOC = { art_modelo:"ART/RRT modelo", seguro:"Seguro de responsabilidade civil", nr10:"Certificado NR-10", nr35:"Certificado NR-35", certificado:"Outro certificado", outro:"Outro documento" };
const STATUS = { em_analise:"Em análise", aprovado:"Aprovado", suspenso:"Suspenso" };
const UFS = "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split(" ");

/* ══ Inglês (texto em português → inglês; mensagens do parceiros.py inclusive) ══ */
const PAR_I18N = /*I18N*/{
  "Energia solar": "Solar energy",
  "AVAC (ar-condicionado e ventilação)": "HVAC (air conditioning and ventilation)",
  "Hidráulica": "Plumbing",
  "Elétrica": "Electrical",
  "SbN e paisagismo": "NbS and landscaping",
  "Automação": "Automation",
  "ART/RRT modelo": "ART/RRT template",
  "Seguro de responsabilidade civil": "Civil liability insurance",
  "Certificado NR-10": "NR-10 certificate",
  "Certificado NR-35": "NR-35 certificate",
  "Outro certificado": "Other certificate",
  "Outro documento": "Other document",
  "Em análise": "Under review",
  "Aprovado": "Approved",
  "Suspenso": "Suspended",
  "Não foi possível carregar os profissionais agora.": "Could not load the professionals right now.",
  "Ainda sem avaliações": "No reviews yet",
  "Pedir orçamento": "Request a quote",
  "Serviço": "Service",
  "Município do serviço": "Municipality of the service",
  "UF": "State",
  "Escolha": "Choose",
  "Seu nome": "Your name",
  "E-mail": "E-mail",
  "Telefone com DDD": "Phone with area code",
  "O que precisa": "What you need",
  "Informe e-mail ou telefone (um dos dois basta). O pedido passa pela Central da Physis.": "Give an e-mail or a phone number (either one is enough). The request goes through the Physis Central.",
  "Autorizo enviar meu nome e contato ao profissional escolhido, só para este orçamento (LGPD).": "I authorize sending my name and contact details to the chosen professional, for this quote only (LGPD).",
  "Enviar pedido": "Send request",
  "Cancelar": "Cancel",
  "Quero ser parceiro": "I want to become a partner",
  "Tipo": "Type",
  "Empresa (CNPJ)": "Company (CNPJ)",
  "Pessoa física (CPF)": "Individual (CPF)",
  "CPF ou CNPJ": "CPF or CNPJ",
  "Razão social ou nome": "Company name or full name",
  "Nome na vitrine": "Name shown in the showcase",
  "Conselho": "Professional council",
  "Número do registro": "Registration number",
  "UF do registro": "Registration state",
  "Especialidades": "Specialties",
  "Regiões atendidas (uma por linha: UF, ou município/UF)": "Regions served (one per line: state, or municipality/state)",
  "Sobre o seu trabalho": "About your work",
  "Autorizo a Physis a usar estes dados para conferir meu registro e documentos, mostrar meu perfil público (nome, especialidades, regiões e nota) e me encaminhar pedidos de orçamento. Posso pedir a exclusão quando quiser (LGPD).": "I authorize Physis to use this data to check my registration and documents, show my public profile (name, specialties, regions and rating) and forward quote requests to me. I can request deletion at any time (LGPD).",
  "Depois do envio, a equipe pede os documentos (ART/RRT modelo, seguro e, conforme o serviço, NR-10 e NR-35). Só aparece na loja depois da aprovação.": "After submission, the team asks for the documents (ART/RRT template, insurance and, depending on the service, NR-10 and NR-35). Your profile only appears in the store after approval.",
  "Enviar candidatura": "Submit application",
  "Profissionais parceiros": "Partner professionals",
  "Instaladores e projetistas independentes, com registro profissional e documentos conferidos pela Physis. O serviço e a ART são do profissional.": "Independent installers and designers, with professional registration and documents checked by Physis. The service and the ART are the professional's responsibility.",
  "Todos": "All",
  "Todas": "All",
  "Município": "Municipality",
  "Buscar": "Search",
  "Carregando…": "Loading…",
  "Nenhum profissional aprovado para este filtro ainda.": "No approved professional for this filter yet.",
  "informe e-mail ou telefone": "give an e-mail or a phone number",
  "CPF inválido": "Invalid CPF",
  "CNPJ inválido": "Invalid CNPJ",
  "Candidatura recebida. A equipe da Physis entra em contato para conferir os documentos.": "Application received. The Physis team will contact you to check the documents.",
  "Entre com uma conta da equipe para ver a curadoria.": "Sign in with a team account to see the curation.",
  "Não foi possível carregar os parceiros.": "Could not load the partners.",
  "conferido": "checked",
  "não conferido": "not checked",
  "nenhuma": "none",
  "Detalhes": "Details",
  "vencido": "expired",
  "ausente": "missing",
  "sem validade": "no expiry date",
  "Nenhum documento.": "No documents.",
  "Sem avaliações.": "No reviews.",
  "Curadoria": "Curation",
  "Motivo (obrigatório para suspender)": "Reason (required to suspend)",
  "Gravar curadoria": "Save curation",
  "Só a direção muda a curadoria.": "Only management can change the curation.",
  "Documento": "Document",
  "Validade": "Expiry date",
  "Descrição": "Description",
  "Registrar documento": "Record document",
  "Registro conferido no site do conselho": "Registration checked on the council website",
  "Documentos": "Documents",
  "Avaliações": "Reviews",
  "Apagar cadastro (pedido de exclusão, LGPD)": "Delete registration (deletion request, LGPD)",
  "Parceiros: curadoria": "Partners: curation",
  "Requisitos para aprovar: registro conferido; ART/RRT modelo e seguro para todos; NR-10 para solar, elétrica, automação e AVAC; NR-35 para solar. Documento vencido tira o parceiro da loja até ser atualizado.": "Requirements for approval: registration checked; ART/RRT template and insurance for everyone; NR-10 for solar, electrical, automation and HVAC; NR-35 for solar. An expired document removes the partner from the store until it is updated.",
  "Parceiros cadastrados": "Registered partners",
  "Parceiro": "Partner",
  "Situação": "Status",
  "Registro": "Registration",
  "Pendências": "Pending items",
  "Nota": "Rating",
  "Ações": "Actions",
  "Nenhum parceiro cadastrado. As candidaturas chegam pela loja (\"Quero ser parceiro\").": "No partners registered. Applications come in through the store (\"I want to become a partner\").",
  "Registro marcado como conferido.": "Registration marked as checked.",
  "Documento removido.": "Document removed.",
  "Cadastro apagado.": "Registration deleted.",
  "Curadoria gravada.": "Curation saved.",
  "Documento registrado.": "Document recorded.",
  "Apagar o cadastro, os documentos e as avaliações deste parceiro? Não dá para desfazer.": "Delete this partner's registration, documents and reviews? This cannot be undone.",
  "Remover": "Remove",
  "Contato (uso interno)": "Contact (internal use)",
  "consentimento em": "consent on",
  "termo": "terms version",
  "pedido": "request",
  "registro no CREA, CAU ou CFT": "registration with CREA, CAU or CFT",
  "registro profissional conferido pela equipe": "professional registration checked by the team",
  "informe de 1 a 60 regiões atendidas (UF ou município/UF)": "enter 1 to 60 regions served (state or municipality/state)",
  "código IBGE do município tem 7 dígitos": "the municipality IBGE code has 7 digits",
  "json invalido": "invalid JSON",
  "tipo: pf (pessoa física) ou pj (empresa)": "type: pf (individual) or pj (company)",
  "razão social ou nome obrigatório (até 160 letras)": "company name or full name required (up to 160 characters)",
  "registro profissional: conselho (CREA, CAU ou CFT), número e UF": "professional registration: council (CREA, CAU or CFT), number and state",
  "e-mail inválido": "invalid e-mail",
  "telefone com DDD": "phone with area code",
  "informe e-mail ou telefone para a Physis falar com você": "give an e-mail or a phone number so Physis can contact you",
  "é preciso aceitar o uso dos dados para o cadastro (LGPD)": "you must accept the use of the data for the registration (LGPD)",
  "já existe um cadastro com este CPF/CNPJ; fale com a Physis": "a registration with this CPF/CNPJ already exists; contact Physis",
  "parceiro desconhecido": "unknown partner",
  "CPF/CNPJ já cadastrado em outro parceiro": "CPF/CNPJ already registered to another partner",
  "validade no formato AAAA-MM-DD": "expiry date in YYYY-MM-DD format",
  "este documento precisa de validade": "this document needs an expiry date",
  "arquivo da Gestão não encontrado": "Management file not found",
  "só a direção muda a curadoria": "only management can change the curation",
  "diga o motivo da suspensão": "state the reason for the suspension",
  "nota de 1 a 5": "rating from 1 to 5",
  "pedido não encontrado para este parceiro": "request not found for this partner",
  "só depois do serviço concluído": "only after the service is completed",
  "só quem pediu o serviço avalia": "only the person who requested the service can rate it",
  "este pedido já foi avaliado": "this request has already been rated",
  "é preciso aceitar o envio do seu contato ao profissional": "you must accept sending your contact details to the professional",
  "escolha o profissional": "choose the professional",
  "escolha o serviço": "choose the service",
  "informe o município e a UF do serviço": "enter the municipality and state of the service",
  "nome e um contato (e-mail ou telefone com DDD) para o orçamento": "name and one contact (e-mail or phone with area code) for the quote",
  "descreva o serviço em poucas palavras": "describe the service in a few words",
  "este profissional não atende este serviço nesta região agora": "this professional does not currently offer this service in this region",
  "o seu papel não permite esta ação": "your role does not allow this action"
};
const PAR_I18N_RX = /*I18N_RX*/[
  ["^Atende: ([A-Z]{2}) \\(estado todo\\)$", "Serves: $1 (whole state)"],
  ["^Atende: (.+)$", "Serves: $1"],
  ["^([A-Z]{2}) \\(estado todo\\)$", "$1 (whole state)"],
  ["^Registro ((?:CREA|CAU|CFT)\\b.*?) conferido pela Physis · Documentos em dia: (.+)$", "Registration $1 checked by Physis · Documents up to date: $2"],
  ["^Registro ((?:CREA|CAU|CFT)\\b.*?) · Documentos em dia: (.+)$", "Registration $1 · Documents up to date: $2"],
  ["^Registro ((?:CREA|CAU|CFT)\\b.*) conferido pela Physis$", "Registration $1 checked by Physis"],
  ["^· Documentos em dia: (.+)$", "· Documents up to date: $1"],
  ["^Registro ((?:CREA|CAU|CFT)\\b.*)$", "Registration $1"],
  ["^Nota ([\\d.,−-]+) de 5 \\(1 avaliação\\)$", "Rating $1 out of 5 (1 review)"],
  ["^Nota ([\\d.,−-]+) de 5 \\((\\d+) avalia(?:ção|ções|çãoões)\\)$", "Rating $1 out of 5 ($2 reviews)"],
  ["^Pedir orçamento a (.+)$", "Request a quote from $1"],
  ["^Pedido (\\S+) enviado\\. A Physis encaminha ao profissional e acompanha pela Central\\.$", "Request $1 sent. Physis forwards it to the professional and follows it up through the Central."],
  ["^Não foi enviado: (.+)$", "Not sent: $1"],
  ["^Erro: (.+)$", "Error: $1"],
  ["^Remover (.+)$", "Remove $1"],
  ["^Detalhes de (.+)$", "Details of $1"],
  ["^(\\d+) vencidos?$", "$1 expired"],
  ["^(.+) (vencido|ausente)$", "$1 $2"],
  ["^validade (\\d{4}-\\d{2}-\\d{2})$", "expires $1"],
  ["^falta para aprovar: (.+)$", "missing for approval: $1"],
  ["^UF inválida: (.+)$", "invalid state: $1"],
  ["^especialidades: (.+)$", "specialties: $1"],
  ["^tipo de documento: (.+)$", "document type: $1"],
  ["^status: (.+)$", "status: $1"]
];
let opIdioma = null;
function en(){ try { if (opIdioma) return opIdioma() === "en"; return /^en/i.test((global.document && global.document.documentElement.lang) || ""); } catch (e){ return false; } }
/* t(s): par exato; senão a primeira regra que casa (cada pedaço $n também passa por t); senão lista "a, b" com todos os pares */
function t(s){ const k = String(s == null ? "" : s).replace(/\s+/g, " ").trim(); if (!k || !en()) return s;
  let v = Object.prototype.hasOwnProperty.call(PAR_I18N, k) ? PAR_I18N[k] : null;
  if (v == null) for (const [a, r] of PAR_I18N_RX){ const m = k.match(new RegExp(a)); if (m){ v = r.replace(/\$(\d)/g, (_, i) => { const g = m[+i]; return g == null ? "" : g.length < k.length ? t(g) : g; }); break; } }
  if (v == null && k.indexOf(", ") > 0){ const ps = k.split(", ").map(x => Object.prototype.hasOwnProperty.call(PAR_I18N, x) ? PAR_I18N[x] : null); if (ps.every(x => x != null)) v = ps.join(", "); }
  return v == null ? s : v; }
/* telas montadas: redesenha quando o lang do <html> muda (troca de idioma na plataforma ou na Gestão) */
const vivos = new Set();
function aoMudarIdioma(el, fn){ vivos.add([el, fn]);
  if (aoMudarIdioma.obs || typeof MutationObserver === "undefined" || !global.document) return;
  let ultimo = global.document.documentElement.lang;
  aoMudarIdioma.obs = new MutationObserver(() => { const l = global.document.documentElement.lang; if (l === ultimo) return; ultimo = l;
    vivos.forEach(x => { if (!x[0].isConnected) { vivos.delete(x); return; } try { x[1](); } catch (e){} }); });
  aoMudarIdioma.obs.observe(global.document.documentElement, { attributes:true, attributeFilter:["lang"] }); }

const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));
const et = s => esc(t(s));
const dig = v => String(v == null ? "" : v).replace(/\D/g, "");
function cpfValido(v){ const d = dig(v); if (d.length !== 11 || /^(\d)\1+$/.test(d)) return false;
  for (const n of [9, 10]){ let s = 0; for (let i = 0; i < n; i++) s += +d[i] * (n + 1 - i); if ((s * 10 % 11) % 10 !== +d[n]) return false; } return true; }
function cnpjValido(v){ const d = dig(v); if (d.length !== 14 || /^(\d)\1+$/.test(d)) return false;
  const P = [[12, [5,4,3,2,9,8,7,6,5,4,3,2]], [13, [6,5,4,3,2,9,8,7,6,5,4,3,2]]];
  for (const [n, p] of P){ let s = 0; for (let i = 0; i < n; i++) s += +d[i] * p[i]; const r = s % 11; if ((r < 2 ? 0 : 11 - r) !== +d[n]) return false; } return true; }

let csrf = null;
async function api(url, corpo){
  const op = { credentials:"same-origin" };
  if (corpo !== undefined){
    if (csrf == null){ try { csrf = (await fetch("/api/instancia", op).then(r => r.json())).csrf || ""; } catch (e){ csrf = ""; } }
    op.method = "POST"; op.headers = { "Content-Type":"application/json" }; if (csrf) op.headers["X-Physis-CSRF"] = csrf; op.body = JSON.stringify(corpo);
  }
  const r = await fetch(url, op); let j = {}; try { j = await r.json(); } catch (e){}
  if (!r.ok || j.ok === false){ const e = new Error(j.erro || ("HTTP " + r.status)); e.dados = j; e.codigo = r.status; throw e; }
  return j;
}
const opcoes = (obj, sel, vazio) => (vazio ? `<option value="">${et(vazio)}</option>` : "") + Object.keys(obj).map(k => `<option value="${k}"${k === sel ? " selected" : ""}>${et(obj[k])}</option>`).join("");
const opUF = (sel, vazio) => (vazio ? `<option value="">${et(vazio)}</option>` : "") + UFS.map(u => `<option${u === sel ? " selected" : ""}>${u}</option>`).join("");
const campo = (id, rot, attrs) => `<div><label for="${id}">${et(rot)}</label><input id="${id}" ${attrs || 'type="text"'} style="width:100%"></div>`;
const regiao = (r, todo) => r.municipio ? r.municipio + "/" + r.uf : todo ? t(r.uf + " (estado todo)") : r.uf;
let seq = 0;

/* ══ Loja: vitrine, pedido de orçamento e candidatura ══ */
function montarLoja(el, op){
  if (op && typeof op.idioma === "function") opIdioma = op.idioma;
  const id = "pl" + (++seq), st = { filtro:{ servico:"", uf:"", municipio:"" }, lista:null, erro:"", pedir:null, msg:"", candidatar:false };
  async function buscar(){
    const f = st.filtro, q = new URLSearchParams(); Object.keys(f).forEach(k => f[k] && q.set(k, f[k]));
    try { st.lista = (await api("/api/parceiros?" + q.toString())).parceiros; st.erro = ""; } catch (e){ st.lista = []; st.erro = "Não foi possível carregar os profissionais agora."; }
    desenhar();
  }
  function cartao(p){
    const registro = (p.registro ? `Registro ${p.registro}${p.registro_conferido ? " conferido pela Physis" : ""}` : "") + (p.documentos_em_dia.length ? ` · Documentos em dia: ${p.documentos_em_dia.join(", ")}` : "");
    return `<li class="cartao"><h3 class="t3">${esc(p.nome)}</h3>
      <p>${p.especialidades.map(e => `<span class="selo in">${et(e.nome)}</span>`).join(" ")}</p>
      ${p.descricao ? `<p class="pq">${esc(p.descricao)}</p>` : ""}
      <p class="t2 pq">${et("Atende: " + p.regioes.map(r => regiao(r, true)).join(", "))}</p>
      <p class="pq">${registro ? et(registro) : ""}</p>
      <p class="pq">${p.nota != null ? et(`Nota ${String(p.nota).replace(".", ",")} de 5 (${p.avaliacoes} ${p.avaliacoes > 1 ? "avaliações" : "avaliação"})`) : et("Ainda sem avaliações")}</p>
      <button type="button" data-pl-pedir="${p.id}">${et("Pedir orçamento")}</button></li>`;
  }
  function formPedido(){
    const p = (st.lista || []).find(x => x.id === st.pedir); if (!p) return "";
    const f = st.filtro, serv = f.servico || (p.especialidades[0] || {}).id;
    return `<form class="cartao" data-pl-form="pedido" aria-labelledby="${id}-hp" style="display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(200px,1fr))">
      <h3 id="${id}-hp" class="t3" style="grid-column:1/-1">${et("Pedir orçamento a " + p.nome)}</h3>
      <div><label for="${id}-ps">${et("Serviço")}</label><select id="${id}-ps" name="servico" style="width:100%">${opcoes(Object.fromEntries(p.especialidades.map(e => [e.id, e.nome])), serv)}</select></div>
      ${campo(id + "-pm", "Município do serviço", `type="text" name="municipio" required value="${esc(f.municipio)}" autocomplete="address-level2"`)}
      <div><label for="${id}-pu">${et("UF")}</label><select id="${id}-pu" name="uf" required style="width:100%">${opUF(f.uf, "Escolha")}</select></div>
      ${campo(id + "-pn", "Seu nome", 'type="text" name="nome" required autocomplete="name" maxlength="120"')}
      ${campo(id + "-pe", "E-mail", 'type="email" name="email" autocomplete="email"')}
      ${campo(id + "-pt", "Telefone com DDD", 'type="tel" name="telefone" autocomplete="tel"')}
      <div style="grid-column:1/-1"><label for="${id}-pd">${et("O que precisa")}</label><textarea id="${id}-pd" name="descricao" required minlength="10" maxlength="2000" style="width:100%"></textarea></div>
      <p class="t2 pq" style="grid-column:1/-1">${et("Informe e-mail ou telefone (um dos dois basta). O pedido passa pela Central da Physis.")}</p>
      <label style="grid-column:1/-1;font-weight:400;display:flex;gap:8px;align-items:flex-start"><input type="checkbox" name="consentimento" required> ${et("Autorizo enviar meu nome e contato ao profissional escolhido, só para este orçamento (LGPD).")}</label>
      <div style="grid-column:1/-1;display:flex;gap:8px;flex-wrap:wrap"><button type="submit">${et("Enviar pedido")}</button><button type="button" data-pl-cancelar="1">${et("Cancelar")}</button></div></form>`;
  }
  function formCandidato(){
    return `<form class="cartao" data-pl-form="candidato" aria-labelledby="${id}-hc" style="display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(200px,1fr))">
      <h3 id="${id}-hc" class="t3" style="grid-column:1/-1">${et("Quero ser parceiro")}</h3>
      <div><label for="${id}-ct">${et("Tipo")}</label><select id="${id}-ct" name="tipo" style="width:100%"><option value="pj">${et("Empresa (CNPJ)")}</option><option value="pf">${et("Pessoa física (CPF)")}</option></select></div>
      ${campo(id + "-cd", "CPF ou CNPJ", 'type="text" name="documento" required inputmode="numeric"')}
      ${campo(id + "-cn", "Razão social ou nome", 'type="text" name="nome" required maxlength="160"')}
      ${campo(id + "-cp", "Nome na vitrine", 'type="text" name="nome_publico" maxlength="120"')}
      <div><label for="${id}-cc">${et("Conselho")}</label><select id="${id}-cc" name="conselho" style="width:100%"><option>CREA</option><option>CAU</option><option>CFT</option></select></div>
      ${campo(id + "-cr", "Número do registro", 'type="text" name="registro" required maxlength="30"')}
      <div><label for="${id}-cu">${et("UF do registro")}</label><select id="${id}-cu" name="registro_uf" required style="width:100%">${opUF("", "Escolha")}</select></div>
      ${campo(id + "-ce", "E-mail", 'type="email" name="email" autocomplete="email"')}
      ${campo(id + "-cf", "Telefone com DDD", 'type="tel" name="telefone" autocomplete="tel"')}
      <fieldset style="grid-column:1/-1"><legend>${et("Especialidades")}</legend>${Object.keys(ESPECIALIDADES).map(k => `<label style="font-weight:400;display:inline-flex;gap:6px;margin:4px 14px 4px 0"><input type="checkbox" name="esp" value="${k}"> ${et(ESPECIALIDADES[k])}</label>`).join("")}</fieldset>
      <div style="grid-column:1/-1"><label for="${id}-cg">${et("Regiões atendidas (uma por linha: UF, ou município/UF)")}</label><textarea id="${id}-cg" name="regioes" required placeholder="RJ&#10;Petrópolis/RJ" style="width:100%"></textarea></div>
      <div style="grid-column:1/-1"><label for="${id}-cx">${et("Sobre o seu trabalho")}</label><textarea id="${id}-cx" name="descricao" maxlength="1000" style="width:100%"></textarea></div>
      <label style="grid-column:1/-1;font-weight:400;display:flex;gap:8px;align-items:flex-start"><input type="checkbox" name="consentimento" required> ${et("Autorizo a Physis a usar estes dados para conferir meu registro e documentos, mostrar meu perfil público (nome, especialidades, regiões e nota) e me encaminhar pedidos de orçamento. Posso pedir a exclusão quando quiser (LGPD).")}</label>
      <p class="t2 pq" style="grid-column:1/-1">${et("Depois do envio, a equipe pede os documentos (ART/RRT modelo, seguro e, conforme o serviço, NR-10 e NR-35). Só aparece na loja depois da aprovação.")}</p>
      <div style="grid-column:1/-1;display:flex;gap:8px;flex-wrap:wrap"><button type="submit">${et("Enviar candidatura")}</button><button type="button" data-pl-cancelar="1">${et("Cancelar")}</button></div></form>`;
  }
  function desenhar(){
    const f = st.filtro;
    el.innerHTML = `<section aria-labelledby="${id}-h"><h2 id="${id}-h">${et("Profissionais parceiros")}</h2>
      <p class="t2">${et("Instaladores e projetistas independentes, com registro profissional e documentos conferidos pela Physis. O serviço e a ART são do profissional.")}</p>
      <form data-pl-form="filtro" style="display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));align-items:end">
        <div><label for="${id}-fs">${et("Serviço")}</label><select id="${id}-fs" name="servico" style="width:100%">${opcoes(ESPECIALIDADES, f.servico, "Todos")}</select></div>
        <div><label for="${id}-fu">${et("UF")}</label><select id="${id}-fu" name="uf" style="width:100%">${opUF(f.uf, "Todas")}</select></div>
        ${campo(id + "-fm", "Município", `type="text" name="municipio" value="${esc(f.municipio)}" autocomplete="address-level2"`)}
        <div><button type="submit">${et("Buscar")}</button></div></form>
      <div role="status" aria-live="polite">${st.msg ? `<p class="pq"><strong>${et(st.msg)}</strong></p>` : ""}${st.erro ? `<p class="pq">${et(st.erro)}</p>` : ""}</div>
      ${st.pedir ? formPedido() : ""}${st.candidatar ? formCandidato() : ""}
      ${st.lista == null ? `<p class="t2">${et("Carregando…")}</p>` : st.lista.length ? `<ul style="list-style:none;padding:0;display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(260px,1fr))">${st.lista.map(cartao).join("")}</ul>` : `<p class="t2">${et("Nenhum profissional aprovado para este filtro ainda.")}</p>`}
      ${st.candidatar ? "" : `<p><button type="button" data-pl-candidatar="1">${et("Quero ser parceiro")}</button></p>`}</section>`;
  }
  el.addEventListener("click", ev => { const b = ev.target.closest("button"); if (!b) return;
    if (b.dataset.plPedir){ st.pedir = Number(b.dataset.plPedir); st.candidatar = false; st.msg = ""; desenhar(); const n = el.querySelector("[data-pl-form=pedido] select, [data-pl-form=pedido] input"); if (n) n.focus(); }
    else if (b.dataset.plCandidatar){ st.candidatar = true; st.pedir = null; st.msg = ""; desenhar(); const n = el.querySelector("[data-pl-form=candidato] select"); if (n) n.focus(); }
    else if (b.dataset.plCancelar){ st.pedir = null; st.candidatar = false; desenhar(); } });
  el.addEventListener("submit", async ev => { const fm = ev.target; if (!fm.dataset || !fm.dataset.plForm) return; ev.preventDefault();
    const v = n => (fm.elements[n] && fm.elements[n].value || "").trim();
    if (fm.dataset.plForm === "filtro"){ st.filtro = { servico:v("servico"), uf:v("uf"), municipio:v("municipio") }; st.lista = null; desenhar(); return buscar(); }
    const b = fm.querySelector("button[type=submit]"); b.disabled = true;
    try {
      if (fm.dataset.plForm === "pedido"){
        if (!v("email") && !v("telefone")) throw new Error("informe e-mail ou telefone");
        const r = await api("/api/parceiros/orcamento", { parceiro: st.pedir, servico:v("servico"), municipio:v("municipio"), uf:v("uf"), nome:v("nome"), email:v("email"), telefone:v("telefone"), descricao:v("descricao"), consentimento: fm.elements.consentimento.checked });
        st.pedir = null; st.msg = "Pedido " + r.numero + " enviado. A Physis encaminha ao profissional e acompanha pela Central.";
      } else {
        const tipo = v("tipo"), doc = v("documento");
        if (tipo === "pf" ? !cpfValido(doc) : !cnpjValido(doc)) throw new Error(tipo === "pf" ? "CPF inválido" : "CNPJ inválido");
        const regioes = v("regioes").split("\n").map(x => x.trim()).filter(Boolean).map(x => { const [a, b2] = x.split("/").map(s => s.trim()); return b2 ? { municipio:a, uf:b2.toUpperCase() } : { uf:a.toUpperCase() }; });
        const esp = Array.from(fm.querySelectorAll("input[name=esp]:checked")).map(x => x.value);
        await api("/api/parceiros/cadastro", { tipo, documento:doc, nome:v("nome"), nome_publico:v("nome_publico"), conselho:v("conselho"), registro:v("registro"), registro_uf:v("registro_uf"), email:v("email"), telefone:v("telefone"), especialidades:esp, regioes, descricao:v("descricao"), consentimento: fm.elements.consentimento.checked });
        st.candidatar = false; st.msg = "Candidatura recebida. A equipe da Physis entra em contato para conferir os documentos.";
      }
    } catch (e){ st.msg = "Não foi enviado: " + e.message; }
    b.disabled = false; desenhar(); el.querySelector("[role=status]").scrollIntoView({ block:"nearest" }); });
  aoMudarIdioma(el, desenhar);
  desenhar(); buscar();
}

/* ══ Gestão: curadoria ══ */
function montarCuradoria(el, op){
  if (op && typeof op.idioma === "function") opIdioma = op.idioma;
  const id = "pc" + (++seq), st = { dados:null, papel:null, msg:"", erro:false, aberto:{} };
  async function carregar(){
    try { const i = await fetch("/api/instancia", { credentials:"same-origin" }).then(r => r.json()).catch(() => ({})); st.papel = i.papel || null; csrf = i.csrf || csrf;
      st.dados = await api("/api/parceiros/interno"); }
    catch (e){ st.msg = e.codigo === 401 || e.codigo === 403 ? "Entre com uma conta da equipe para ver a curadoria." : "Não foi possível carregar os parceiros."; st.erro = true; }
    desenhar();
  }
  const direcao = () => st.papel === "administrador";
  function linha(p){
    const venc = p.documentos.filter(x => x.vencido).length, sel = p.status === "aprovado" ? "ok" : p.status === "suspenso" ? "al" : "at";
    return `<tr><th scope="row">${esc(p.nome_publico)}<br><span class="t2 pq">${esc(p.nome)} · ${esc(p.documento)}</span></th>
      <td><span class="selo ${sel}">${et(STATUS[p.status])}</span>${p.status_motivo ? `<br><span class="t2 pq">${esc(p.status_motivo)}</span>` : ""}</td>
      <td>${esc(p.especialidades.map(e => t(ESPECIALIDADES[e] || e)).join(", "))}</td>
      <td>${p.conselho ? esc(p.conselho + " " + p.registro + "/" + p.registro_uf) : "—"}<br><span class="t2 pq">${et(p.registro_conferido ? "conferido" : "não conferido")}</span></td>
      <td>${p.documentos.length}${venc ? ` <span class="selo al">${et(venc + " vencido" + (venc > 1 ? "s" : ""))}</span>` : ""}</td>
      <td>${p.pendencias.length ? `<ul class="pq">${p.pendencias.map(x => `<li>${et(x)}</li>`).join("")}</ul>` : `<span class="selo ok">${et("nenhuma")}</span>`}</td>
      <td>${p.nota != null ? String(p.nota).replace(".", ",") + " (" + p.avaliacoes + ")" : "—"}</td>
      <td><button type="button" data-pc-abrir="${p.id}" aria-expanded="${!!st.aberto[p.id]}" aria-label="${et("Detalhes de " + p.nome_publico)}">${et("Detalhes")}</button></td></tr>
      ${st.aberto[p.id] ? `<tr><td colspan="8">${detalhe(p)}</td></tr>` : ""}`;
  }
  function detalhe(p){
    const docs = p.documentos.length ? `<ul>${p.documentos.map(x => `<li>${et(x.tipo_nome)}${x.descricao ? " · " + esc(x.descricao) : ""} · ${x.validade ? et("validade " + x.validade) : et("sem validade")} ${x.vencido ? `<span class="selo al">${et("vencido")}</span>` : ""} <button type="button" data-pc-rmdoc="${x.id}" data-pc-id="${p.id}" aria-label="${et("Remover " + x.tipo_nome)}">${et("Remover")}</button></li>`).join("")}</ul>` : `<p class="t2">${et("Nenhum documento.")}</p>`;
    const com = p.comentarios.length ? `<ul>${p.comentarios.map(c => `<li>${c.nota}/5 · ${et("pedido")} ${esc(c.pedido)}${c.comentario ? ": " + esc(c.comentario) : ""}</li>`).join("")}</ul>` : `<p class="t2">${et("Sem avaliações.")}</p>`;
    const cur = `<form data-pc-form="curar" data-pc-id="${p.id}" style="display:grid;gap:8px;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));align-items:end">
        <div><label for="${id}-s${p.id}">${et("Curadoria")}</label><select id="${id}-s${p.id}" name="status" style="width:100%"${direcao() ? "" : " disabled"}>${opcoes(STATUS, p.status)}</select></div>
        <div><label for="${id}-m${p.id}">${et("Motivo (obrigatório para suspender)")}</label><input id="${id}-m${p.id}" name="motivo" type="text" maxlength="300" style="width:100%"${direcao() ? "" : " disabled"}></div>
        <div><button type="submit"${direcao() ? "" : ' disabled aria-describedby="' + id + '-sod"'}>${et("Gravar curadoria")}</button></div></form>
      ${direcao() ? "" : `<p id="${id}-sod" class="t2 pq">${et("Só a direção muda a curadoria.")}</p>`}`;
    const doc = `<form data-pc-form="doc" data-pc-id="${p.id}" style="display:grid;gap:8px;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));align-items:end">
        <div><label for="${id}-t${p.id}">${et("Documento")}</label><select id="${id}-t${p.id}" name="tipo" style="width:100%">${opcoes(TIPOS_DOC, "art_modelo")}</select></div>
        <div><label for="${id}-v${p.id}">${et("Validade")}</label><input id="${id}-v${p.id}" name="validade" type="date" style="width:100%"></div>
        <div><label for="${id}-d${p.id}">${et("Descrição")}</label><input id="${id}-d${p.id}" name="descricao" type="text" maxlength="200" style="width:100%"></div>
        <div><button type="submit">${et("Registrar documento")}</button></div></form>`;
    return `<div style="display:grid;gap:12px">
      <p class="pq">${esc(t("Contato (uso interno)") + ": " + (p.email || "—") + " · " + (p.telefone || "—") + " · " + t("consentimento em") + " " + new Date(p.consentimento * 1000).toLocaleDateString("pt-BR") + " (" + t("termo") + " " + p.versao_termo + ")")}</p>
      <p>${et("Atende: " + p.regioes.map(r => regiao(r, false)).join(", "))}</p>
      <div><button type="button" data-pc-conferir="${p.id}">${et("Registro conferido no site do conselho")}</button></div>
      ${cur}<h3>${et("Documentos")}</h3>${docs}${doc}<h3>${et("Avaliações")}</h3>${com}
      ${direcao() ? `<div><button type="button" data-pc-apagar="${p.id}">${et("Apagar cadastro (pedido de exclusão, LGPD)")}</button></div>` : ""}</div>`;
  }
  function desenhar(){
    const d = st.dados;
    el.innerHTML = `<section aria-labelledby="${id}-h"><h2 id="${id}-h">${et("Parceiros: curadoria")}</h2>
      <p class="t2">${et("Requisitos para aprovar: registro conferido; ART/RRT modelo e seguro para todos; NR-10 para solar, elétrica, automação e AVAC; NR-35 para solar. Documento vencido tira o parceiro da loja até ser atualizado.")}</p>
      <div role="status" aria-live="polite">${st.msg ? `<p class="pq"><strong>${et(st.msg)}</strong></p>` : ""}</div>
      ${!d ? (st.erro ? "" : `<p class="t2">${et("Carregando…")}</p>`) : d.parceiros.length ? `<div class="rolagem"><table><caption class="so-leitor">${et("Parceiros cadastrados")}</caption><thead><tr><th scope="col">${et("Parceiro")}</th><th scope="col">${et("Situação")}</th><th scope="col">${et("Especialidades")}</th><th scope="col">${et("Registro")}</th><th scope="col">${et("Documentos")}</th><th scope="col">${et("Pendências")}</th><th scope="col">${et("Nota")}</th><th scope="col"><span class="so-leitor">${et("Ações")}</span></th></tr></thead><tbody>${d.parceiros.map(linha).join("")}</tbody></table></div>` : `<p class="t2">${et('Nenhum parceiro cadastrado. As candidaturas chegam pela loja ("Quero ser parceiro").')}</p>`}</section>`;
  }
  async function agir(fn, ok){ try { await fn(); st.msg = ok; st.erro = false; } catch (e){ st.msg = "Erro: " + e.message; st.erro = true; } await carregar(); }
  el.addEventListener("click", async ev => { const b = ev.target.closest("button"); if (!b) return;
    if (b.dataset.pcAbrir){ st.aberto[b.dataset.pcAbrir] = !st.aberto[b.dataset.pcAbrir]; desenhar(); }
    else if (b.dataset.pcConferir) await agir(() => api(`/api/parceiros/${b.dataset.pcConferir}/conferir`, {}), "Registro marcado como conferido.");
    else if (b.dataset.pcRmdoc) await agir(() => api(`/api/parceiros/${b.dataset.pcId}/documento/remover`, { id:Number(b.dataset.pcRmdoc) }), "Documento removido.");
    else if (b.dataset.pcApagar && global.confirm(t("Apagar o cadastro, os documentos e as avaliações deste parceiro? Não dá para desfazer.")))
      await agir(() => api(`/api/parceiros/${b.dataset.pcApagar}/apagar`, {}), "Cadastro apagado."); });
  el.addEventListener("submit", async ev => { const f = ev.target; if (!f.dataset || !f.dataset.pcForm) return; ev.preventDefault();
    const v = n => (f.elements[n] && f.elements[n].value || "").trim(), pid = f.dataset.pcId;
    if (f.dataset.pcForm === "curar") await agir(() => api(`/api/parceiros/${pid}/curadoria`, { status:v("status"), motivo:v("motivo") }), "Curadoria gravada.");
    else await agir(() => api(`/api/parceiros/${pid}/documento`, { tipo:v("tipo"), validade:v("validade"), descricao:v("descricao") }), "Documento registrado."); });
  aoMudarIdioma(el, desenhar);
  desenhar(); carregar();
}

global.PARCEIROS = { ESPECIALIDADES, TIPOS_DOC, STATUS, cpfValido, cnpjValido, montarLoja, montarCuradoria, I18N: PAR_I18N, I18N_RX: PAR_I18N_RX, t };
})(typeof window !== "undefined" ? window : globalThis);
