/* physis-nativo.js — primeira coisa que roda no app Physis (Capacitor). Posto no <head> por scripts/preparar_www.py.
 *
 * 1. Marca o app: window.PHYSIS_NATIVO = true (a plataforma pode esconder "Instalar app" e mostrar o Bluetooth).
 * 2. Sem servidor escolhido ou sem consentimento: vai para primeiro-uso.html.
 * 3. Pedidos da plataforma para "api/…" ou "/api/…" vão para o servidor escolhido (o do cliente ou o da Physis).
 *    Com CapacitorHttp ligado (capacitor.config.json), o pedido sai pelo lado nativo: sem CORS, com o cookie
 *    da sessão guardado pelo próprio app (CapacitorCookies), sem cabeçalho Origin.
 * 4. Liga a PhysisBLE ao mesmo servidor.
 * Nenhum endereço fixo aqui: o único servidor é o que a pessoa digitou no primeiro uso.
 */
(function () {
"use strict";
window.PHYSIS_NATIVO = true;

const CH_HUB = "physis-nativo-hub", CH_CONS = "physis-nativo-consentimento";
const VERSAO_TERMO = "1";        // provisória: texto a revisar pelo jurídico (ver docs/APP_NATIVO.md)
const C = window.Capacitor, P = C && C.Plugins ? C.Plugins : {};

function ler(k) { try { return localStorage.getItem(k) || ""; } catch (e) { return ""; } }
function gravar(k, v) {
  try { if (v) localStorage.setItem(k, v); else localStorage.removeItem(k); } catch (e) { /* sem armazenamento */ }
  if (P.Preferences) (v ? P.Preferences.set({ key: k, value: v }) : P.Preferences.remove({ key: k })).catch(() => {});
}

const hub = ler(CH_HUB).replace(/\/+$/, "");
const consentido = (() => { try { return JSON.parse(ler(CH_CONS) || "{}").versao === VERSAO_TERMO; } catch (e) { return false; } })();
const naPrimeira = /primeiro-uso\.html$/.test(location.pathname);

if ((!hub || !consentido) && !naPrimeira) {
  // o localStorage pode ter sido limpo; o Preferences (nativo) guarda uma cópia
  if (!hub && P.Preferences) {
    Promise.all([P.Preferences.get({ key: CH_HUB }), P.Preferences.get({ key: CH_CONS })]).then(([h, c]) => {
      if (h && h.value && c && c.value) {
        try { localStorage.setItem(CH_HUB, h.value); localStorage.setItem(CH_CONS, c.value); } catch (e) { /* segue */ }
        location.reload();
      } else location.replace("primeiro-uso.html");
    }, () => location.replace("primeiro-uso.html"));
  } else location.replace("primeiro-uso.html");
}

/* ── Pedidos da plataforma vão para o servidor escolhido ── */
function paraHub(url) {
  if (!hub) return null;
  let u;
  try { u = new URL(String(url), location.href); } catch (e) { return null; }
  if (u.origin !== location.origin || !u.pathname.startsWith("/api/")) return null;
  return hub + u.pathname + u.search;
}
if (window.fetch) {
  const original = window.fetch.bind(window);
  window.fetch = function (entrada, op) {
    if (entrada instanceof Request) {
      const novo = paraHub(entrada.url);
      return original(novo ? new Request(novo, entrada) : entrada, op);
    }
    const novo = paraHub(entrada);
    return original(novo || entrada, op);
  };
}
if (window.XMLHttpRequest) {
  const abrir = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (metodo, url) {
    const args = Array.prototype.slice.call(arguments);
    const novo = paraHub(url);
    if (novo) args[1] = novo;
    return abrir.apply(this, args);
  };
}

/* ── Monitoramento contínuo da pulseira (Android): serviço em primeiro plano com notificação clara ── */
async function monitorar(ligar) {
  const F = P.ForegroundService;
  if (!F) return false;                                // iPhone: o modo "bluetooth-central" do sistema faz esse papel
  if (!ligar) { await F.stopForegroundService(); return true; }
  if (F.requestPermissions) await F.requestPermissions().catch(() => {});
  await F.startForegroundService({
    id: 4701, smallIcon: "ic_stat_physis",
    title: "Physis: pulseira conectada",
    body: "Recebendo os alertas da pulseira por Bluetooth. Toque para abrir; para parar, desconecte a pulseira no app."
  });
  return true;
}

window.PhysisNativo = Object.freeze({
  hub: () => hub,
  versaoTermo: VERSAO_TERMO,
  monitorar,
  trocarServidor() { gravar(CH_HUB, ""); location.replace("primeiro-uso.html"); },
  esquecer() {                                          // "sair e apagar deste celular"
    gravar(CH_HUB, ""); gravar(CH_CONS, "");
    try { indexedDB.deleteDatabase("physis-ble"); } catch (e) { /* segue */ }
    location.replace("primeiro-uso.html");
  },
  _gravar: gravar, _CH_HUB: CH_HUB, _CH_CONS: CH_CONS
});

document.addEventListener("DOMContentLoaded", () => {
  if (window.PhysisBLE && hub) window.PhysisBLE.configurar({ hub }).catch(() => {});
});
})();
