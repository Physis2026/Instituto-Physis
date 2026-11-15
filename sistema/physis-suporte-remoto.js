/* physis-suporte-remoto.js — "Permitir suporte": acesso remoto da equipe Physis com prazo (15/11/2026).
   Parte da área de conta e segurança da plataforma (só para a direção da instalação). Conversa com o servidor:
     GET  /api/suporte-remoto            → { concessoes, eventos, vpn_configurada, duracoes }
     POST /api/suporte-remoto/conceder   { duracao: "2h"|"8h"|"1d"|"3d", nota, so_ver } → { codigo_acesso (uma vez), concessao }
     POST /api/suporte-remoto/revogar    { id }
   A confirmação de senha (reautenticação) é a de physis-conta.js: o servidor responde {reautenticar:true} e a ponte pede a senha.
   Contrato: window.PhysisSuporteRemoto = { tela(opcoes) → HTML, ligar(raiz, opcoes) }. opcoes.idioma() → "pt"|"en";
   opcoes.pedir(rota, corpo) → Promise<json> (a da plataforma, com CSRF); sem ela, fetch simples.
   Acessível (rótulos, aria-live, foco devolvido), português e inglês, tema claro e escuro e conforto pelas classes da plataforma
   (cartao, selo, faixa, t2): o módulo não define cores próprias. Sem endereço de internet. */
(function (g) {
  "use strict";
  var T = {
    pt: { tit: "Permitir suporte", intro: "Libera, por um prazo, o acesso da equipe Physis a esta instalação para ajudar você. Só funciona pela VPN da Physis e só com o código que aparece aqui.",
      lgpd: "LGPD: durante o prazo, o suporte vê o que a equipe desta instalação vê (telas, leituras, registros e configurações) e, sem \"só ver\", pode mudar configurações. Nenhum dado é copiado para a Physis por este recurso. Tudo o que o suporte fizer fica registrado abaixo.",
      prazo: "Prazo", h2: "2 horas", h8: "8 horas", d1: "1 dia", d3: "3 dias", nota: "Nota para a equipe (opcional)", sover: "Só ver (o suporte não muda nada)",
      liberar: "Permitir suporte", semVpn: "A VPN de suporte ainda não foi configurada neste servidor (PHYSIS_SUPORTE_REDES): o código não funcionará até lá.",
      semContas: "Nenhuma conta da equipe Physis está autorizada neste servidor (PHYSIS_SUPORTE_CONTAS vazio): ninguém consegue entrar com o código até a Physis configurar as contas (previsto para a fase 2).",
      codigo: "Código de acesso (aparece só agora; passe só à equipe Physis):", conc: "Acessos liberados", evt: "O que o suporte fez",
      colPrazo: "Válido até", colPor: "Liberado por", colSit: "Situação", colAcao: "Ação", revogar: "Revogar", valendo: "valendo", vencida: "vencida", revogada: "revogada",
      colQuando: "Quando", colTipo: "Evento", colQuem: "Quem", colIp: "Endereço (VPN)", colDet: "Detalhe", nada: "Nenhum acesso liberado ainda.", erro: "Não foi possível: ",
      sim: "sim", tipos: { concedido: "liberado", entrou: "entrou", uso: "usou", recusado: "recusado", revogado: "revogado", expirou: "venceu", saiu: "saiu" } },
    en: { tit: "Allow support", intro: "Grants the Physis team access to this installation for a limited time, to help you. It only works through the Physis VPN and only with the code shown here.",
      lgpd: "LGPD: during the period, support sees what this installation's team sees (screens, readings, records and settings) and, without \"view only\", can change settings. No data is copied to Physis by this feature. Everything support does is listed below.",
      prazo: "Period", h2: "2 hours", h8: "8 hours", d1: "1 day", d3: "3 days", nota: "Note for the team (optional)", sover: "View only (support changes nothing)",
      liberar: "Allow support", semVpn: "The support VPN is not configured on this server yet (PHYSIS_SUPORTE_REDES): the code will not work until then.",
      semContas: "No Physis team account is authorised on this server (PHYSIS_SUPORTE_CONTAS is empty): no one can sign in with the code until Physis configures the accounts (planned for phase 2).",
      codigo: "Access code (shown only now; give it only to the Physis team):", conc: "Granted access", evt: "What support did",
      colPrazo: "Valid until", colPor: "Granted by", colSit: "Status", colAcao: "Action", revogar: "Revoke", valendo: "active", vencida: "expired", revogada: "revoked",
      colQuando: "When", colTipo: "Event", colQuem: "Who", colIp: "Address (VPN)", colDet: "Detail", nada: "No access granted yet.", erro: "Could not: ",
      sim: "yes", tipos: { concedido: "granted", entrou: "signed in", uso: "used", recusado: "refused", revogado: "revoked", expirou: "expired", saiu: "signed out" } }
  };
  var est = { dados: null, codigo: "", msg: "", erro: false };
  var E = function (s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
  function L(op) { var i = op && op.idioma ? op.idioma() : (g.document.documentElement.lang || "pt"); return /^en/i.test(i) ? T.en : T.pt; }
  function quando(ts, op) { try { return new Date(ts * 1000).toLocaleString(L(op) === T.en ? "en-GB" : "pt-BR", { dateStyle: "short", timeStyle: "short" }); } catch (e) { return ""; } }
  function pedir(op, rota, corpo) {
    if (op && typeof op.pedir === "function") return op.pedir(rota, corpo);
    return g.fetch(rota, corpo ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo), credentials: "same-origin" } : { credentials: "same-origin", cache: "no-store" })
      .then(function (r) { return r.json(); });
  }
  function tela(op) {
    var t = L(op), d = est.dados || {}, conc = d.concessoes || [], ev = d.eventos || [];
    var linhasC = conc.map(function (c) { return "<tr><th scope='row'>" + E(quando(c.expira, op)) + "</th><td>" + E(c.por) + "</td><td><span class='selo " + (c.situacao === "valendo" ? "ok" : "in") + "'>" + E(t[c.situacao] || c.situacao) + "</span>" + (c.so_ver ? " · " + E(t.sover.split(" (")[0]) : "") + "</td><td>"
      + (c.situacao === "valendo" ? "<button type='button' data-sr-revogar='" + E(c.id) + "' id='sr-rev-" + E(c.id) + "'>" + E(t.revogar) + "</button>" : "—") + "</td></tr>"; }).join("");
    var linhasE = ev.slice(0, 100).map(function (x) { return "<tr><th scope='row'>" + E(quando(x.quando, op)) + "</th><td>" + E(t.tipos[x.tipo] || x.tipo) + "</td><td>" + E(x.quem) + "</td><td>" + E(x.ip || "—") + "</td><td>" + E(x.detalhe) + "</td></tr>"; }).join("");
    return "<section class='cartao' aria-labelledby='sr-h'><h2 id='sr-h'>" + E(t.tit) + "</h2><p class='t2'>" + E(t.intro) + "</p>"
      + "<p class='faixa at' role='note'>" + E(t.lgpd) + "</p>"
      + (d.vpn_configurada === false ? "<p class='faixa in' role='note'>" + E(t.semVpn) + "</p>" : "")
      + (d.contas_configuradas === false ? "<p class='faixa in' role='note'>" + E(t.semContas) + "</p>" : "")
      + "<div class='precos'><div><label for='sr-prazo'>" + E(t.prazo) + "</label><select id='sr-prazo' style='width:100%'><option value='2h'>" + E(t.h2) + "</option><option value='8h'>" + E(t.h8) + "</option><option value='1d'>" + E(t.d1) + "</option><option value='3d'>" + E(t.d3) + "</option></select></div>"
      + "<div><label for='sr-nota'>" + E(t.nota) + "</label><input id='sr-nota' type='text' maxlength='300' style='width:100%'></div>"
      + "<div><label class='opc'><input type='checkbox' id='sr-sover'> <span>" + E(t.sover) + "</span></label></div>"
      + "<div style='align-self:end'><button type='button' id='sr-liberar' class='principal'>" + E(t.liberar) + "</button></div></div>"
      + "<p id='sr-msg' tabindex='-1' role='status' aria-live='polite' class='" + (est.erro ? "faixa al" : "t2") + "'>" + E(est.msg) + "</p>"
      + (est.codigo ? "<p class='faixa ok' role='alert'>" + E(t.codigo) + " <strong id='sr-codigo' tabindex='-1' style='font-family:ui-monospace,Consolas,monospace;font-size:1.2em'>" + E(est.codigo) + "</strong></p>" : "")
      + "<h3 class='t3'>" + E(t.conc) + "</h3>" + (linhasC ? "<div class='rolagem'><table><caption>" + E(t.conc) + "</caption><thead><tr><th scope='col'>" + E(t.colPrazo) + "</th><th scope='col'>" + E(t.colPor) + "</th><th scope='col'>" + E(t.colSit) + "</th><th scope='col'>" + E(t.colAcao) + "</th></tr></thead><tbody>" + linhasC + "</tbody></table></div>" : "<p class='t2'>" + E(t.nada) + "</p>")
      + (linhasE ? "<h3 class='t3'>" + E(t.evt) + "</h3><div class='rolagem'><table><caption>" + E(t.evt) + "</caption><thead><tr><th scope='col'>" + E(t.colQuando) + "</th><th scope='col'>" + E(t.colTipo) + "</th><th scope='col'>" + E(t.colQuem) + "</th><th scope='col'>" + E(t.colIp) + "</th><th scope='col'>" + E(t.colDet) + "</th></tr></thead><tbody>" + linhasE + "</tbody></table></div>" : "")
      + "</section>";
  }
  function ligar(raiz, op) {
    if (!raiz || raiz.__srLigado) return; raiz.__srLigado = true;
    var pintar = function (foco) { raiz.innerHTML = tela(op); var f = foco && g.document.getElementById(foco); if (f) f.focus(); };
    var carregar = function (foco) { pedir(op, "/api/suporte-remoto").then(function (j) { if (j && j.ok) est.dados = j; else { est.erro = true; est.msg = L(op).erro + ((j && j.erro) || ""); } pintar(foco); }).catch(function () { pintar(foco); }); };
    raiz.addEventListener("click", function (ev) {
      var b = ev.target.closest ? ev.target.closest("button") : null; if (!b) return; var t = L(op);
      if (b.id === "sr-liberar") {
        b.disabled = true;
        pedir(op, "/api/suporte-remoto/conceder", { duracao: g.document.getElementById("sr-prazo").value, nota: g.document.getElementById("sr-nota").value, so_ver: g.document.getElementById("sr-sover").checked })
          .then(function (j) { est.erro = !(j && j.ok); est.codigo = j && j.ok ? j.codigo_acesso : ""; est.msg = j && j.ok ? (j.aviso || "") : t.erro + ((j && j.erro) || ""); carregar(est.codigo ? "sr-codigo" : "sr-msg"); })
          .catch(function () { b.disabled = false; });
      } else if (b.hasAttribute("data-sr-revogar")) {
        pedir(op, "/api/suporte-remoto/revogar", { id: b.getAttribute("data-sr-revogar") })
          .then(function (j) { est.erro = !(j && j.ok); est.codigo = ""; est.msg = j && j.ok ? t.revogada : t.erro + ((j && j.erro) || ""); carregar("sr-msg"); });
      }
    });
    pintar(); carregar();
  }
  g.PhysisSuporteRemoto = { tela: tela, ligar: ligar, textos: T };
})(typeof window !== "undefined" ? window : this);
