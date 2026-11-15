/* physis-parceiros.js — Marketplace de serviços: "Profissionais parceiros" na loja e curadoria na Gestão.
   Servidor: physis-hub/physis_hub/parceiros.py (rotas /api/parceiros*). Sem internet: só o próprio hub.
   Contrato:
     PARCEIROS.montarLoja(elemento)       vitrine pública (por especialidade e região), pedido de orçamento
                                          (vira pedido na Central) e "Quero ser parceiro" (candidatura com consentimento)
     PARCEIROS.montarCuradoria(elemento)  tela interna da Gestão: lista, pendências, documentos com validade,
                                          avaliações; aprovar/suspender só para a direção (o servidor também confere)
     PARCEIROS.cpfValido(v), PARCEIROS.cnpjValido(v)  mesma conta do parceiros.py
   Não usa h1 (a tela que hospeda já tem o seu título). Dados pessoais: a loja nunca recebe CPF/CNPJ, contato
   nem número de registro do parceiro; o contato de quem pede orçamento só vai com o consentimento marcado. */
(function (global) {
"use strict";

const ESPECIALIDADES = { solar:"Energia solar", avac:"AVAC (ar-condicionado e ventilação)", hidraulica:"Hidráulica", eletrica:"Elétrica", sbn:"SbN e paisagismo", automacao:"Automação" };
const TIPOS_DOC = { art_modelo:"ART/RRT modelo", seguro:"Seguro de responsabilidade civil", nr10:"Certificado NR-10", nr35:"Certificado NR-35", certificado:"Outro certificado", outro:"Outro documento" };
const STATUS = { em_analise:"Em análise", aprovado:"Aprovado", suspenso:"Suspenso" };
const UFS = "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split(" ");

const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));
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
const opcoes = (obj, sel, vazio) => (vazio ? `<option value="">${esc(vazio)}</option>` : "") + Object.keys(obj).map(k => `<option value="${k}"${k === sel ? " selected" : ""}>${esc(obj[k])}</option>`).join("");
const opUF = (sel, vazio) => (vazio ? `<option value="">${esc(vazio)}</option>` : "") + UFS.map(u => `<option${u === sel ? " selected" : ""}>${u}</option>`).join("");
const campo = (id, rot, attrs) => `<div><label for="${id}">${esc(rot)}</label><input id="${id}" ${attrs || 'type="text"'} style="width:100%"></div>`;
let seq = 0;

/* ══ Loja: vitrine, pedido de orçamento e candidatura ══ */
function montarLoja(el){
  const id = "pl" + (++seq), st = { filtro:{ servico:"", uf:"", municipio:"" }, lista:null, erro:"", pedir:null, msg:"", candidatar:false };
  async function buscar(){
    const f = st.filtro, q = new URLSearchParams(); Object.keys(f).forEach(k => f[k] && q.set(k, f[k]));
    try { st.lista = (await api("/api/parceiros?" + q.toString())).parceiros; st.erro = ""; } catch (e){ st.lista = []; st.erro = "Não foi possível carregar os profissionais agora."; }
    desenhar();
  }
  function cartao(p){
    return `<li class="cartao"><h3 class="t3">${esc(p.nome)}</h3>
      <p>${p.especialidades.map(e => `<span class="selo in">${esc(e.nome)}</span>`).join(" ")}</p>
      ${p.descricao ? `<p class="pq">${esc(p.descricao)}</p>` : ""}
      <p class="t2 pq">Atende: ${esc(p.regioes.map(r => r.municipio ? r.municipio + "/" + r.uf : r.uf + " (estado todo)").join(", "))}</p>
      <p class="pq">${p.registro ? `Registro ${esc(p.registro)}${p.registro_conferido ? " conferido pela Physis" : ""}` : ""}${p.documentos_em_dia.length ? ` · Documentos em dia: ${esc(p.documentos_em_dia.join(", "))}` : ""}</p>
      <p class="pq">${p.nota != null ? `Nota ${String(p.nota).replace(".", ",")} de 5 (${p.avaliacoes} avaliação${p.avaliacoes > 1 ? "ões" : ""})` : "Ainda sem avaliações"}</p>
      <button type="button" data-pl-pedir="${p.id}">Pedir orçamento</button></li>`;
  }
  function formPedido(){
    const p = (st.lista || []).find(x => x.id === st.pedir); if (!p) return "";
    const f = st.filtro, serv = f.servico || (p.especialidades[0] || {}).id;
    return `<form class="cartao" data-pl-form="pedido" aria-labelledby="${id}-hp" style="display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(200px,1fr))">
      <h3 id="${id}-hp" class="t3" style="grid-column:1/-1">Pedir orçamento a ${esc(p.nome)}</h3>
      <div><label for="${id}-ps">Serviço</label><select id="${id}-ps" name="servico" style="width:100%">${opcoes(Object.fromEntries(p.especialidades.map(e => [e.id, e.nome])), serv)}</select></div>
      ${campo(id + "-pm", "Município do serviço", `type="text" name="municipio" required value="${esc(f.municipio)}" autocomplete="address-level2"`)}
      <div><label for="${id}-pu">UF</label><select id="${id}-pu" name="uf" required style="width:100%">${opUF(f.uf, "Escolha")}</select></div>
      ${campo(id + "-pn", "Seu nome", 'type="text" name="nome" required autocomplete="name" maxlength="120"')}
      ${campo(id + "-pe", "E-mail", 'type="email" name="email" autocomplete="email"')}
      ${campo(id + "-pt", "Telefone com DDD", 'type="tel" name="telefone" autocomplete="tel"')}
      <div style="grid-column:1/-1"><label for="${id}-pd">O que precisa</label><textarea id="${id}-pd" name="descricao" required minlength="10" maxlength="2000" style="width:100%"></textarea></div>
      <p class="t2 pq" style="grid-column:1/-1">Informe e-mail ou telefone (um dos dois basta). O pedido passa pela Central da Physis.</p>
      <label style="grid-column:1/-1;font-weight:400;display:flex;gap:8px;align-items:flex-start"><input type="checkbox" name="consentimento" required> Autorizo enviar meu nome e contato ao profissional escolhido, só para este orçamento (LGPD).</label>
      <div style="grid-column:1/-1;display:flex;gap:8px;flex-wrap:wrap"><button type="submit">Enviar pedido</button><button type="button" data-pl-cancelar="1">Cancelar</button></div></form>`;
  }
  function formCandidato(){
    return `<form class="cartao" data-pl-form="candidato" aria-labelledby="${id}-hc" style="display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(200px,1fr))">
      <h3 id="${id}-hc" class="t3" style="grid-column:1/-1">Quero ser parceiro</h3>
      <div><label for="${id}-ct">Tipo</label><select id="${id}-ct" name="tipo" style="width:100%"><option value="pj">Empresa (CNPJ)</option><option value="pf">Pessoa física (CPF)</option></select></div>
      ${campo(id + "-cd", "CPF ou CNPJ", 'type="text" name="documento" required inputmode="numeric"')}
      ${campo(id + "-cn", "Razão social ou nome", 'type="text" name="nome" required maxlength="160"')}
      ${campo(id + "-cp", "Nome na vitrine", 'type="text" name="nome_publico" maxlength="120"')}
      <div><label for="${id}-cc">Conselho</label><select id="${id}-cc" name="conselho" style="width:100%"><option>CREA</option><option>CAU</option><option>CFT</option></select></div>
      ${campo(id + "-cr", "Número do registro", 'type="text" name="registro" required maxlength="30"')}
      <div><label for="${id}-cu">UF do registro</label><select id="${id}-cu" name="registro_uf" required style="width:100%">${opUF("", "Escolha")}</select></div>
      ${campo(id + "-ce", "E-mail", 'type="email" name="email" autocomplete="email"')}
      ${campo(id + "-cf", "Telefone com DDD", 'type="tel" name="telefone" autocomplete="tel"')}
      <fieldset style="grid-column:1/-1"><legend>Especialidades</legend>${Object.keys(ESPECIALIDADES).map(k => `<label style="font-weight:400;display:inline-flex;gap:6px;margin:4px 14px 4px 0"><input type="checkbox" name="esp" value="${k}"> ${esc(ESPECIALIDADES[k])}</label>`).join("")}</fieldset>
      <div style="grid-column:1/-1"><label for="${id}-cg">Regiões atendidas (uma por linha: UF, ou município/UF)</label><textarea id="${id}-cg" name="regioes" required placeholder="RJ&#10;Petrópolis/RJ" style="width:100%"></textarea></div>
      <div style="grid-column:1/-1"><label for="${id}-cx">Sobre o seu trabalho</label><textarea id="${id}-cx" name="descricao" maxlength="1000" style="width:100%"></textarea></div>
      <label style="grid-column:1/-1;font-weight:400;display:flex;gap:8px;align-items:flex-start"><input type="checkbox" name="consentimento" required> Autorizo a Physis a usar estes dados para conferir meu registro e documentos, mostrar meu perfil público (nome, especialidades, regiões e nota) e me encaminhar pedidos de orçamento. Posso pedir a exclusão quando quiser (LGPD).</label>
      <p class="t2 pq" style="grid-column:1/-1">Depois do envio, a equipe pede os documentos (ART/RRT modelo, seguro e, conforme o serviço, NR-10 e NR-35). Só aparece na loja depois da aprovação.</p>
      <div style="grid-column:1/-1;display:flex;gap:8px;flex-wrap:wrap"><button type="submit">Enviar candidatura</button><button type="button" data-pl-cancelar="1">Cancelar</button></div></form>`;
  }
  function desenhar(){
    const f = st.filtro;
    el.innerHTML = `<section aria-labelledby="${id}-h"><h2 id="${id}-h">Profissionais parceiros</h2>
      <p class="t2">Instaladores e projetistas independentes, com registro profissional e documentos conferidos pela Physis. O serviço e a ART são do profissional.</p>
      <form data-pl-form="filtro" style="display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));align-items:end">
        <div><label for="${id}-fs">Serviço</label><select id="${id}-fs" name="servico" style="width:100%">${opcoes(ESPECIALIDADES, f.servico, "Todos")}</select></div>
        <div><label for="${id}-fu">UF</label><select id="${id}-fu" name="uf" style="width:100%">${opUF(f.uf, "Todas")}</select></div>
        ${campo(id + "-fm", "Município", `type="text" name="municipio" value="${esc(f.municipio)}" autocomplete="address-level2"`)}
        <div><button type="submit">Buscar</button></div></form>
      <div role="status" aria-live="polite">${st.msg ? `<p class="pq"><strong>${esc(st.msg)}</strong></p>` : ""}${st.erro ? `<p class="pq">${esc(st.erro)}</p>` : ""}</div>
      ${st.pedir ? formPedido() : ""}${st.candidatar ? formCandidato() : ""}
      ${st.lista == null ? `<p class="t2">Carregando…</p>` : st.lista.length ? `<ul style="list-style:none;padding:0;display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(260px,1fr))">${st.lista.map(cartao).join("")}</ul>` : `<p class="t2">Nenhum profissional aprovado para este filtro ainda.</p>`}
      ${st.candidatar ? "" : `<p><button type="button" data-pl-candidatar="1">Quero ser parceiro</button></p>`}</section>`;
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
  desenhar(); buscar();
}

/* ══ Gestão: curadoria ══ */
function montarCuradoria(el){
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
      <td><span class="selo ${sel}">${esc(STATUS[p.status])}</span>${p.status_motivo ? `<br><span class="t2 pq">${esc(p.status_motivo)}</span>` : ""}</td>
      <td>${esc(p.especialidades.map(e => ESPECIALIDADES[e] || e).join(", "))}</td>
      <td>${p.conselho ? esc(p.conselho + " " + p.registro + "/" + p.registro_uf) : "—"}<br><span class="t2 pq">${p.registro_conferido ? "conferido" : "não conferido"}</span></td>
      <td>${p.documentos.length}${venc ? ` <span class="selo al">${venc} vencido${venc > 1 ? "s" : ""}</span>` : ""}</td>
      <td>${p.pendencias.length ? `<ul class="pq">${p.pendencias.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : `<span class="selo ok">nenhuma</span>`}</td>
      <td>${p.nota != null ? String(p.nota).replace(".", ",") + " (" + p.avaliacoes + ")" : "—"}</td>
      <td><button type="button" data-pc-abrir="${p.id}" aria-expanded="${!!st.aberto[p.id]}" aria-label="Detalhes de ${esc(p.nome_publico)}">Detalhes</button></td></tr>
      ${st.aberto[p.id] ? `<tr><td colspan="8">${detalhe(p)}</td></tr>` : ""}`;
  }
  function detalhe(p){
    const docs = p.documentos.length ? `<ul>${p.documentos.map(x => `<li>${esc(x.tipo_nome)}${x.descricao ? " · " + esc(x.descricao) : ""} · ${x.validade ? "validade " + esc(x.validade) : "sem validade"} ${x.vencido ? '<span class="selo al">vencido</span>' : ""} <button type="button" data-pc-rmdoc="${x.id}" data-pc-id="${p.id}" aria-label="Remover ${esc(x.tipo_nome)}">Remover</button></li>`).join("")}</ul>` : `<p class="t2">Nenhum documento.</p>`;
    const com = p.comentarios.length ? `<ul>${p.comentarios.map(c => `<li>${c.nota}/5 · pedido ${esc(c.pedido)}${c.comentario ? ": " + esc(c.comentario) : ""}</li>`).join("")}</ul>` : `<p class="t2">Sem avaliações.</p>`;
    const cur = `<form data-pc-form="curar" data-pc-id="${p.id}" style="display:grid;gap:8px;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));align-items:end">
        <div><label for="${id}-s${p.id}">Curadoria</label><select id="${id}-s${p.id}" name="status" style="width:100%"${direcao() ? "" : " disabled"}>${opcoes(STATUS, p.status)}</select></div>
        <div><label for="${id}-m${p.id}">Motivo (obrigatório para suspender)</label><input id="${id}-m${p.id}" name="motivo" type="text" maxlength="300" style="width:100%"${direcao() ? "" : " disabled"}></div>
        <div><button type="submit"${direcao() ? "" : ' disabled aria-describedby="' + id + '-sod"'}>Gravar curadoria</button></div></form>
      ${direcao() ? "" : `<p id="${id}-sod" class="t2 pq">Só a direção muda a curadoria.</p>`}`;
    const doc = `<form data-pc-form="doc" data-pc-id="${p.id}" style="display:grid;gap:8px;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));align-items:end">
        <div><label for="${id}-t${p.id}">Documento</label><select id="${id}-t${p.id}" name="tipo" style="width:100%">${opcoes(TIPOS_DOC, "art_modelo")}</select></div>
        <div><label for="${id}-v${p.id}">Validade</label><input id="${id}-v${p.id}" name="validade" type="date" style="width:100%"></div>
        <div><label for="${id}-d${p.id}">Descrição</label><input id="${id}-d${p.id}" name="descricao" type="text" maxlength="200" style="width:100%"></div>
        <div><button type="submit">Registrar documento</button></div></form>`;
    return `<div style="display:grid;gap:12px">
      <p class="pq">Contato (uso interno): ${esc(p.email || "—")} · ${esc(p.telefone || "—")} · consentimento em ${new Date(p.consentimento * 1000).toLocaleDateString("pt-BR")} (termo ${esc(p.versao_termo)})</p>
      <p>Atende: ${esc(p.regioes.map(r => r.municipio ? r.municipio + "/" + r.uf : r.uf).join(", "))}</p>
      <div><button type="button" data-pc-conferir="${p.id}">Registro conferido no site do conselho</button></div>
      ${cur}<h3>Documentos</h3>${docs}${doc}<h3>Avaliações</h3>${com}
      ${direcao() ? `<div><button type="button" data-pc-apagar="${p.id}">Apagar cadastro (pedido de exclusão, LGPD)</button></div>` : ""}</div>`;
  }
  function desenhar(){
    const d = st.dados;
    el.innerHTML = `<section aria-labelledby="${id}-h"><h2 id="${id}-h">Parceiros: curadoria</h2>
      <p class="t2">Requisitos para aprovar: registro conferido; ART/RRT modelo e seguro para todos; NR-10 para solar, elétrica, automação e AVAC; NR-35 para solar. Documento vencido tira o parceiro da loja até ser atualizado.</p>
      <div role="status" aria-live="polite">${st.msg ? `<p class="pq"><strong>${esc(st.msg)}</strong></p>` : ""}</div>
      ${!d ? (st.erro ? "" : `<p class="t2">Carregando…</p>`) : d.parceiros.length ? `<div class="rolagem"><table><caption class="so-leitor">Parceiros cadastrados</caption><thead><tr><th scope="col">Parceiro</th><th scope="col">Situação</th><th scope="col">Especialidades</th><th scope="col">Registro</th><th scope="col">Documentos</th><th scope="col">Pendências</th><th scope="col">Nota</th><th scope="col"><span class="so-leitor">Ações</span></th></tr></thead><tbody>${d.parceiros.map(linha).join("")}</tbody></table></div>` : `<p class="t2">Nenhum parceiro cadastrado. As candidaturas chegam pela loja ("Quero ser parceiro").</p>`}</section>`;
  }
  async function agir(fn, ok){ try { await fn(); st.msg = ok; st.erro = false; } catch (e){ st.msg = "Erro: " + e.message; st.erro = true; } await carregar(); }
  el.addEventListener("click", async ev => { const b = ev.target.closest("button"); if (!b) return;
    if (b.dataset.pcAbrir){ st.aberto[b.dataset.pcAbrir] = !st.aberto[b.dataset.pcAbrir]; desenhar(); }
    else if (b.dataset.pcConferir) await agir(() => api(`/api/parceiros/${b.dataset.pcConferir}/conferir`, {}), "Registro marcado como conferido.");
    else if (b.dataset.pcRmdoc) await agir(() => api(`/api/parceiros/${b.dataset.pcId}/documento/remover`, { id:Number(b.dataset.pcRmdoc) }), "Documento removido.");
    else if (b.dataset.pcApagar && global.confirm("Apagar o cadastro, os documentos e as avaliações deste parceiro? Não dá para desfazer."))
      await agir(() => api(`/api/parceiros/${b.dataset.pcApagar}/apagar`, {}), "Cadastro apagado."); });
  el.addEventListener("submit", async ev => { const f = ev.target; if (!f.dataset || !f.dataset.pcForm) return; ev.preventDefault();
    const v = n => (f.elements[n] && f.elements[n].value || "").trim(), pid = f.dataset.pcId;
    if (f.dataset.pcForm === "curar") await agir(() => api(`/api/parceiros/${pid}/curadoria`, { status:v("status"), motivo:v("motivo") }), "Curadoria gravada.");
    else await agir(() => api(`/api/parceiros/${pid}/documento`, { tipo:v("tipo"), validade:v("validade"), descricao:v("descricao") }), "Documento registrado."); });
  desenhar(); carregar();
}

global.PARCEIROS = { ESPECIALIDADES, TIPOS_DOC, STATUS, cpfValido, cnpjValido, montarLoja, montarCuradoria };
})(typeof window !== "undefined" ? window : globalThis);
