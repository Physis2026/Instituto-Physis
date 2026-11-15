/* primeiro-uso.js — tela de primeiro uso do app Physis: servidor, consentimento; a entrada (login) é a da plataforma. */
(function () {
"use strict";
const $ = id => document.getElementById(id);
const N = window.PhysisNativo;
let hubOk = "";

function dizer(el, txt, tipo) { el.textContent = txt; el.className = "msg " + (tipo || ""); }

function normalizar(txt) {
  let t = String(txt || "").trim();
  if (!t) return null;
  if (!/^[a-z]+:/i.test(t)) t = "https://" + t;        // a pessoa digitou só o nome
  let u;
  try { u = new URL(t); } catch (e) { return null; }
  if (u.protocol !== "https:") return null;                      // app sem tráfego aberto (cleartext desligado)
  return u.origin;
}

$("versao-termo").textContent = N ? N.versaoTermo : "1";

$("conferir").addEventListener("click", async () => {
  const msg = $("msg-servidor");
  const hub = normalizar($("servidor").value);
  if (!hub) { dizer(msg, "Endereço inválido. Ele precisa começar com https://.", "erro"); $("servidor").focus(); return; }
  dizer(msg, "Conferindo…");
  $("conferir").disabled = true;
  try {
    const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), 10000);
    const r = await fetch(hub + "/api/instancia", { cache: "no-store", credentials: "omit", signal: ctl.signal });
    clearTimeout(t);
    const j = await r.json();
    if (!j || typeof j !== "object" || !("org" in j)) throw new Error("não é um servidor Physis");
    hubOk = hub;
    const nome = j.nome_cliente || j.org || "";
    dizer(msg, "Servidor Physis encontrado" + (nome ? ": " + nome : "") + ". Confira se é o do seu lugar.", "ok");
    $("parte-consentimento").hidden = false;
    $("link-privacidade").href = hub + "/";                       // [MARCADOR] rota da política quando existir
    $("aceito").focus();
  } catch (e) {
    hubOk = "";
    dizer(msg, "Não foi possível falar com esse endereço. Confira o endereço e a internet e tente de novo.", "erro");
  } finally {
    $("conferir").disabled = false;
  }
});
$("servidor").addEventListener("keydown", e => { if (e.key === "Enter") $("conferir").click(); });
$("aceito").addEventListener("change", () => { $("comecar").disabled = !$("aceito").checked; });

$("comecar").addEventListener("click", async () => {
  if (!hubOk || !$("aceito").checked) return;
  const cons = { versao: N ? N.versaoTermo : "1", aceito: true, quando: Math.floor(Date.now() / 1000),
    bluetooth: $("usar-ble").checked, avisos: $("usar-avisos").checked };
  if (cons.avisos && window.Capacitor && window.Capacitor.Plugins.LocalNotifications) {
    try { await window.Capacitor.Plugins.LocalNotifications.requestPermissions(); } catch (e) { /* a pessoa pode negar */ }
  }
  if (N) { N._gravar(N._CH_HUB, hubOk); N._gravar(N._CH_CONS, JSON.stringify(cons)); }
  dizer($("msg-consentimento"), "Tudo pronto. Abrindo a plataforma…", "ok");
  location.replace("index.html");
});
})();
