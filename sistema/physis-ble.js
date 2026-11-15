/* physis-ble.js — Bluetooth (BLE) da Saúde: caixinha de remédios (MED) e pulseira (PUL).
 *
 * Uma só biblioteca para a plataforma, no app nativo (Capacitor) e no navegador (PWA):
 *   1. app Physis (Android/iOS): plugin @capacitor-community/bluetooth-le, quando
 *      window.Capacitor.isNativePlatform() é verdadeiro;
 *   2. navegador com Web Bluetooth (Chrome/Edge no Android, Windows, macOS, Linux, ChromeOS; só em HTTPS
 *      ou localhost, e só com a tela aberta);
 *   3. nenhum dos dois (iPhone no Safari, Firefox): disponivel() diz por que e o que fazer.
 *
 * API (window.PhysisBLE):
 *   disponivel()                 -> Promise<{ok, backend: "nativo"|"web"|"nenhum", motivo, texto}>
 *   configurar({hub, chaves, idioma, enviar})
 *                                hub: endereço do computador central ("" = o mesmo do site);
 *                                chaves: {"31": "phk_…", "*": "phk_…"} (chave por aparelho; "*" = chave de receptor)
 *   procurar({tipo: "med"|"pul"}) -> Promise<{id, nome, tipo}> (abre a lista do sistema; a pessoa escolhe)
 *   conectar(id)                 -> Promise<{id, nome, tipo}> (pareia se preciso, acerta o relógio, assina as linhas)
 *   inscrever(cb)                -> função para cancelar; cb({tipo: "linha"|"bateria"|"estado"|"envio"|"erro", …})
 *   escrever(cmd[, id])          -> Promise; cmd no formato V6 "CMD:<nn>:<AÇÃO>[:<ARG>]"
 *   desconectar([id])            -> Promise
 *   pendentes()                  -> Promise<número de linhas na fila>
 *   enviarPendentes()            -> Promise<{enviadas, restam}>
 *   texto(chave[, idioma])       -> frase pronta para a tela (pt/en), para leitores de tela também
 *   UUID                         -> as UUIDs do perfil GATT (firmware/saude/BLE_PERFIL.md)
 *
 * O que chega do aparelho já é a linha V6 (MED/PUL, ver physis_hub/saude.py), em pedaços de até 240 bytes
 * terminados por "\n". Aqui a linha é remontada, conferida, recebe TS do celular quando o aparelho não tem
 * relógio, vai para a fila (IndexedDB, cifrada com AES-GCM) e é enviada para POST /api/saude/linha com o
 * cabeçalho X-Physis-Chave. Sem rede, fica na fila e é reenviada depois (com espera crescente e ao voltar a rede).
 *
 * LGPD (dado de saúde é sensível): a fila guarda só a linha (sem nome de pessoa); cada sessão de aparelho
 * usa uma chave AES-GCM derivada (HKDF) de uma chave-mestra não exportável; linhas PUL (com local) com mais
 * de 30 dias são apagadas sem envio; nada vai para outro endereço que não o hub configurado.
 * Sem endereço externo, sem eval: a biblioteca não carrega nada de fora.
 */
(function () {
"use strict";

const VERSAO = "0.1.0";

/* ════════ Perfil GATT (o mesmo de firmware/saude/BLE_PERFIL.md; teste confere) ════════ */
const UUID = Object.freeze({
  SERVICO_MED: "461d76e3-6508-4db6-9886-05374c5fbb50",   // caixinha de remédios
  SERVICO_PUL: "e970dc7d-400e-4b4e-924c-948d2198e81b",   // pulseira
  LINHA:       "bbca3cf4-40e0-4103-9420-7c1f5f693fd4",   // notify: linha V6 em pedaços, termina em "\n"
  COMANDO:     "529cbb10-062f-4ca8-aa64-cca0c1307234",   // write (com resposta, cifrado e autenticado)
  BATERIA:     "0000180f-0000-1000-8000-00805f9b34fb",   // Battery Service (padrão)
  NIVEL_BATERIA: "00002a19-0000-1000-8000-00805f9b34fb",
  INFO:        "0000180a-0000-1000-8000-00805f9b34fb"    // Device Information (padrão)
});
const PREFIXO_NOME = { med: "Physis-MED", pul: "Physis-PUL" };
const SERVICO = { med: UUID.SERVICO_MED, pul: UUID.SERVICO_PUL };

/* ════════ Regras da linha (espelho de physis_hub/protocolo.py e saude.py) ════════ */
const LINHA_MAX = 240, TOTAL_NOS = 99, BUFFER_MAX = 1024;
const EPOCH_MIN = 1700000000, EPOCH_MAX = 4102444800;
const ACOES = ["SYNC", "PING", "HOR", "HORAPAGA", "TOL", "LIMBPM"];
const FILA_MAX = 5000, RETENCAO_PUL_S = 30 * 86400, ESPERA_MAX_MS = 5 * 60 * 1000;

/* ════════ Textos (pt/en) ════════ */
const TEXTOS = {
  pt: {
    nativo: "Bluetooth pronto (app Physis).",
    web: "Bluetooth pronto (navegador). Mantenha esta tela aberta enquanto o aparelho estiver ligado.",
    nenhum: "Este aparelho ou navegador não fala Bluetooth com a caixinha nem com a pulseira. No Android, use o Chrome ou o app Physis; no iPhone, instale o app Physis.",
    inseguro: "O Bluetooth do navegador só funciona em endereço seguro (https). Peça à Physis o endereço com https ou use o app Physis.",
    desligado: "O Bluetooth do celular está desligado. Ligue-o e tente de novo.",
    procurando: "Procurando aparelhos Physis por perto…",
    cancelado: "Nenhum aparelho escolhido.",
    conectando: "Conectando ao aparelho…",
    pareando: "Confirme o código de 6 números que aparece no aparelho (ou no QR da etiqueta).",
    conectado: "Aparelho conectado.",
    desconectado: "Aparelho desconectado.",
    reconectando: "Conexão perdida. Tentando de novo…",
    linha: "Registro recebido do aparelho.",
    linha_recusada: "O aparelho mandou um registro que não foi entendido. Ele foi descartado.",
    enviado: "Registros enviados ao computador central.",
    fila: "Sem conexão com o computador central. Os registros ficam guardados neste celular, cifrados, e serão enviados depois.",
    chave_invalida: "O computador central recusou a chave deste aparelho. Peça uma chave nova a quem administra o sistema.",
    sem_cifra: "Este navegador não permite guardar os registros com segurança. Eles só ficam na memória até serem enviados.",
    comando_invalido: "Comando fora do formato CMD:<nn>:<AÇÃO>[:<ARG>].",
    sem_aparelho: "Nenhum aparelho conectado.",
    bateria: "Bateria do aparelho"
  },
  en: {
    nativo: "Bluetooth ready (Physis app).",
    web: "Bluetooth ready (browser). Keep this screen open while the device is in use.",
    nenhum: "This phone or browser cannot talk Bluetooth to the pill box or the wristband. On Android, use Chrome or the Physis app; on iPhone, install the Physis app.",
    inseguro: "Browser Bluetooth only works on a secure (https) address. Ask Physis for the https address or use the Physis app.",
    desligado: "Bluetooth is turned off on this phone. Turn it on and try again.",
    procurando: "Looking for nearby Physis devices…",
    cancelado: "No device chosen.",
    conectando: "Connecting to the device…",
    pareando: "Confirm the 6-digit code shown on the device (or on the label QR).",
    conectado: "Device connected.",
    desconectado: "Device disconnected.",
    reconectando: "Connection lost. Trying again…",
    linha: "Record received from the device.",
    linha_recusada: "The device sent a record that could not be read. It was discarded.",
    enviado: "Records sent to the central computer.",
    fila: "No connection to the central computer. Records are kept on this phone, encrypted, and will be sent later.",
    chave_invalida: "The central computer refused this device's key. Ask your system administrator for a new key.",
    sem_cifra: "This browser cannot store records securely. They stay in memory only until sent.",
    comando_invalido: "Command not in the CMD:<nn>:<ACTION>[:<ARG>] format.",
    sem_aparelho: "No device connected.",
    bateria: "Device battery"
  }
};

const cfg = { hub: "", chaves: {}, idioma: (navigator.language || "pt").toLowerCase().startsWith("en") ? "en" : "pt", enviar: true };
const ouvintes = new Set();
const aparelhos = new Map();      // id -> {id, nome, tipo, no, buffer, sessao, ligado, querLigado, web?: BluetoothDevice}
let ultimo = null;

function texto(chave, idioma) {
  const t = TEXTOS[idioma || cfg.idioma] || TEXTOS.pt;
  return t[chave] || TEXTOS.pt[chave] || chave;
}
function avisar(ev) {
  ouvintes.forEach(cb => { try { cb(ev); } catch (e) { /* um ouvinte com erro não para os outros */ } });
}
function erro(chave, extra) {
  const e = new Error(texto(chave));
  e.codigo = chave;
  if (extra) e.causa = extra;
  return e;
}

/* ════════ Bytes ════════ */
const cod = new TextEncoder(), dec = new TextDecoder("utf-8");
function paraBytes(v) {
  if (v instanceof DataView) return new Uint8Array(v.buffer, v.byteOffset, v.byteLength);
  if (v instanceof ArrayBuffer) return new Uint8Array(v);
  if (ArrayBuffer.isView(v)) return new Uint8Array(v.buffer, v.byteOffset, v.byteLength);
  if (typeof v === "string") {                              // o plugin nativo entrega hexadecimal ("6a 7b …")
    const h = v.replace(/[^0-9a-fA-F]/g, "");
    const out = new Uint8Array(h.length >> 1);
    for (let i = 0; i < out.length; i++) out[i] = parseInt(h.substr(i * 2, 2), 16);
    return out;
  }
  return new Uint8Array(0);
}
function paraHex(u8) {
  return Array.from(u8, b => (b < 16 ? "0" : "") + b.toString(16)).join(" ");
}
function b64(u8) { let s = ""; u8.forEach(b => { s += String.fromCharCode(b); }); return btoa(s); }
function aleatorio(n) { const a = new Uint8Array(n); crypto.getRandomValues(a); return a; }
const agora = () => Math.floor(Date.now() / 1000);

/* ════════ Linha V6: remontar, conferir, completar ════════ */
function campos(linha) {
  const c = {};
  linha.split(",").forEach(par => {
    const i = par.indexOf(":");
    if (i <= 0) return;
    const k = par.slice(0, i).trim().toUpperCase();
    if (!(k in c)) c[k] = par.slice(i + 1).trim();       // primeira chave vence, como no protocolo.py
  });
  return c;
}

/* Devolve {ok, motivo, linha, no, tipo}. Não muda o sentido da linha: só limpa e, sem relógio, põe o TS do celular. */
function conferirLinha(bruta, tipoEsperado) {
  let linha = String(bruta || "").replace(/[\u0000-\u001f\u007f]/g, "").trim();
  if (!linha) return { ok: false, motivo: "vazia" };
  if (linha.startsWith("CMD:")) return { ok: false, motivo: "comando" };
  if (linha.startsWith("BCN:")) return { ok: false, motivo: "beacon" };
  const c = campos(linha);
  const no = /^\d{1,2}$/.test(c.ID || "") ? Number(c.ID) : -1;
  if (!(no >= 1 && no <= TOTAL_NOS)) return { ok: false, motivo: "id_fora" };
  const tipo = (c.TIPO || "").toUpperCase();
  if (tipo !== "MED" && tipo !== "PUL") return { ok: false, motivo: "tipo_desconhecido" };
  if (tipoEsperado && tipo !== tipoEsperado.toUpperCase()) return { ok: false, motivo: "tipo_trocado" };
  const ts = /^\d+$/.test(c.TS || "") ? Number(c.TS) : 0;
  if (!(ts >= EPOCH_MIN && ts <= EPOCH_MAX)) {
    // aparelho sem relógio: a linha vai para a fila e pode chegar horas depois; o TS do celular guarda a hora certa
    linha = linha.split(",").filter(p => p.split(":")[0].trim().toUpperCase() !== "TS").join(",") + ",TS:" + agora();
  }
  if (linha.length > LINHA_MAX) return { ok: false, motivo: "longa" };
  return { ok: true, motivo: "", linha, no, tipo, ts: ts >= EPOCH_MIN && ts <= EPOCH_MAX ? ts : agora() };
}

function receberPedaco(ap, valor) {
  if (!ap.dec) ap.dec = new TextDecoder("utf-8");             // um decodificador por aparelho: pedaço pode cortar um caractere
  ap.buffer += ap.dec.decode(paraBytes(valor), { stream: true });
  if (ap.buffer.length > BUFFER_MAX) { ap.buffer = ""; avisar({ tipo: "erro", aparelho: ap.id, codigo: "linha_recusada", texto: texto("linha_recusada") }); return; }
  let i;
  while ((i = ap.buffer.indexOf("\n")) >= 0) {
    const bruta = ap.buffer.slice(0, i);
    ap.buffer = ap.buffer.slice(i + 1);
    if (!bruta.trim()) continue;
    const r = conferirLinha(bruta, ap.tipo);
    if (!r.ok) { avisar({ tipo: "erro", aparelho: ap.id, codigo: "linha_recusada", motivo: r.motivo, texto: texto("linha_recusada") }); continue; }
    if (ap.no && ap.no !== r.no) { avisar({ tipo: "erro", aparelho: ap.id, codigo: "linha_recusada", motivo: "id_trocado", texto: texto("linha_recusada") }); continue; }
    ap.no = r.no;
    avisar({ tipo: "linha", aparelho: ap.id, no: r.no, tipoLinha: r.tipo, linha: r.linha, texto: texto("linha") });
    enfileirar(ap, r).then(() => agendarEnvio(0)).catch(e => avisar({ tipo: "erro", codigo: "fila", texto: String(e && e.message || e) }));
  }
}

/* ════════ Fila cifrada (IndexedDB + WebCrypto) ════════
 * Chave-mestra HKDF gerada uma vez, guardada no IndexedDB como CryptoKey NÃO exportável (o JavaScript não
 * consegue ler os bytes dela). Para cada sessão de aparelho (cada conexão) sorteia-se um sal; a chave AES-GCM
 * de 256 bits daquela sessão é derivada (HKDF-SHA-256, info = "physis-ble|<sessão>"). Cada linha tem IV próprio.
 * Limite honesto: protege contra cópia dos arquivos do navegador/app, não contra quem já controla o celular
 * desbloqueado com o app aberto. No Android e no iOS a cifra do próprio sistema (FBE/Data Protection) soma-se a esta. */
const BANCO = "physis-ble", VBANCO = 1;
let bancoP = null, mestraP = null;
const memoria = [];               // sem IndexedDB/WebCrypto: fila só na memória (some ao fechar)
const chavesSessao = new Map();
const temCifra = () => !!(window.crypto && crypto.subtle && window.indexedDB && window.isSecureContext !== false);

function banco() {
  if (!bancoP) bancoP = new Promise((ok, falha) => {
    const p = indexedDB.open(BANCO, VBANCO);
    p.onupgradeneeded = () => {
      const db = p.result;
      if (!db.objectStoreNames.contains("fila")) db.createObjectStore("fila", { keyPath: "n", autoIncrement: true });
      if (!db.objectStoreNames.contains("meta")) db.createObjectStore("meta");
    };
    p.onsuccess = () => ok(p.result);
    p.onerror = () => falha(p.error);
  });
  return bancoP;
}
function tx(loja, modo, fazer) {
  return banco().then(db => new Promise((ok, falha) => {
    const t = db.transaction(loja, modo), s = t.objectStore(loja);
    let res;
    const r = fazer(s);
    if (r) r.onsuccess = () => { res = r.result; };
    t.oncomplete = () => ok(res);
    t.onerror = () => falha(t.error);
    t.onabort = () => falha(t.error);
  }));
}
function mestra() {
  if (!mestraP) mestraP = tx("meta", "readonly", s => s.get("mestra")).then(k => {
    if (k) return k;
    const bruta = aleatorio(32);
    return crypto.subtle.importKey("raw", bruta, "HKDF", false, ["deriveKey"]).then(nova => {
      bruta.fill(0);
      return tx("meta", "readwrite", s => s.put(nova, "mestra")).then(() => nova);
    });
  });
  return mestraP;
}
function chaveDaSessao(sessao, sal) {
  const id = sessao + "|" + b64(sal);
  if (!chavesSessao.has(id)) {
    chavesSessao.set(id, mestra().then(m => crypto.subtle.deriveKey(
      { name: "HKDF", hash: "SHA-256", salt: sal, info: cod.encode("physis-ble|" + sessao) },
      m, { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"])));
  }
  return chavesSessao.get(id);
}
function cifrar(sessao, sal, texto_) {
  const iv = aleatorio(12);
  return chaveDaSessao(sessao, sal).then(k => crypto.subtle.encrypt({ name: "AES-GCM", iv, additionalData: cod.encode(sessao) }, k, cod.encode(texto_)))
    .then(dados => ({ iv, dados }));
}
function decifrar(reg) {
  return chaveDaSessao(reg.sessao, reg.sal)
    .then(k => crypto.subtle.decrypt({ name: "AES-GCM", iv: reg.iv, additionalData: cod.encode(reg.sessao) }, k, reg.dados))
    .then(b => dec.decode(b));
}

function novaSessao(ap) {
  ap.sessao = b64(aleatorio(12));
  ap.sal = aleatorio(16);
}

function enfileirar(ap, r) {
  const hub = cfg.hub;
  if (!temCifra()) {
    if (memoria.length >= FILA_MAX) memoria.shift();
    memoria.push({ no: r.no, tipo: r.tipo, ts: r.ts, hub, linha: r.linha });
    return Promise.resolve();
  }
  if (!ap.sessao) novaSessao(ap);
  return cifrar(ap.sessao, ap.sal, r.linha).then(({ iv, dados }) =>
    tx("fila", "readwrite", s => s.add({ no: r.no, tipo: r.tipo, ts: r.ts, hub, sessao: ap.sessao, sal: ap.sal, iv, dados, quando: agora() })))
    .then(() => contar()).then(n => { if (n > FILA_MAX) return apagarMaisAntigas(n - FILA_MAX); });
}
function contar() {
  return temCifra() ? tx("fila", "readonly", s => s.count()) : Promise.resolve(memoria.length);
}
function apagarMaisAntigas(n) {
  return tx("fila", "readwrite", s => {
    const c = s.openCursor();
    c.onsuccess = () => { const cur = c.result; if (cur && n-- > 0) { cur.delete(); cur.continue(); } };
  });
}
function lerFila() {
  if (!temCifra()) return Promise.resolve(memoria.map((m, i) => Object.assign({ n: "m" + i }, m)));
  return tx("fila", "readonly", s => s.getAll()).then(regs => Promise.all((regs || []).map(reg =>
    decifrar(reg).then(linha => ({ n: reg.n, no: reg.no, tipo: reg.tipo, ts: reg.ts, hub: reg.hub, linha }),
      () => ({ n: reg.n, perdida: true })))));          // chave-mestra apagada (dados do app limpos): não dá para ler
}
function apagar(ns) {
  if (!ns.length) return Promise.resolve();
  if (!temCifra()) {
    const fora = new Set(ns);
    for (let i = memoria.length - 1; i >= 0; i--) if (fora.has("m" + i)) memoria.splice(i, 1);
    return Promise.resolve();
  }
  return tx("fila", "readwrite", s => { ns.forEach(n => s.delete(n)); });
}

/* Chaves dos aparelhos: também cifradas no IndexedDB (sessão fixa "chaves"), para reenviar depois de reabrir o app. */
const SAL_CHAVES_ID = "sal-chaves";
function guardarChaves() {
  if (!temCifra()) return Promise.resolve();
  return tx("meta", "readonly", s => s.get(SAL_CHAVES_ID)).then(sal => {
    sal = sal || aleatorio(16);
    return cifrar("chaves", sal, JSON.stringify(cfg.chaves)).then(({ iv, dados }) =>
      tx("meta", "readwrite", s => { s.put(sal, SAL_CHAVES_ID); s.put({ sessao: "chaves", sal, iv, dados }, "chaves"); }));
  });
}
function lerChaves() {
  if (!temCifra()) return Promise.resolve();
  return tx("meta", "readonly", s => s.get("chaves")).then(reg => {
    if (!reg) return;
    return decifrar(reg).then(t => { const c = JSON.parse(t); if (c && typeof c === "object") cfg.chaves = Object.assign(c, cfg.chaves); }, () => {});
  }).catch(() => {});
}

/* ════════ Envio ao hub ════════ */
let espera = 0, timer = null, enviando = null;
function urlHub(hub, caminho) {
  if (!hub) return caminho;                                   // mesmo endereço do site
  const u = new URL(caminho.replace(/^\//, ""), hub.replace(/\/?$/, "/"));
  if (u.protocol !== "https:" && u.hostname !== "localhost" && u.hostname !== "127.0.0.1") throw erro("inseguro");
  return u.toString();
}
function agendarEnvio(ms) {
  if (!cfg.enviar) return;
  clearTimeout(timer);
  timer = setTimeout(() => { enviarPendentes().catch(() => {}); }, ms);
}
function enviarPendentes() {
  if (enviando) return enviando;
  enviando = lerFila().then(regs => {
    const limite = agora() - RETENCAO_PUL_S;
    const velhas = regs.filter(r => r.perdida || (r.tipo === "PUL" && r.ts < limite)).map(r => r.n);
    const vivas = regs.filter(r => !r.perdida && !(r.tipo === "PUL" && r.ts < limite));
    const grupos = new Map();                                  // um pedido por (hub, nó): a chave pode ser por nó
    vivas.forEach(r => { const k = r.hub + "|" + r.no; if (!grupos.has(k)) grupos.set(k, []); grupos.get(k).push(r); });
    let enviadas = 0, falhou = false;
    const passos = Array.from(grupos.values()).map(g => () => {
      const chave = cfg.chaves[String(g[0].no)] || cfg.chaves["*"] || "";
      const cab = { "Content-Type": "text/plain; charset=utf-8" };
      if (chave) cab["X-Physis-Chave"] = chave;
      return fetch(urlHub(g[0].hub, "/api/saude/linha"), {
        method: "POST", headers: cab, body: g.map(r => r.linha).join("\n"),
        credentials: "omit", cache: "no-store", referrerPolicy: "no-referrer"
      }).then(resp => {
        if (resp.status === 401) { avisar({ tipo: "erro", codigo: "chave_invalida", no: g[0].no, texto: texto("chave_invalida") }); falhou = true; return; }
        if (!resp.ok) { falhou = true; return; }
        enviadas += g.length;
        return apagar(g.map(r => r.n));
      }, () => { falhou = true; });
    });
    return passos.reduce((p, f) => p.then(f), apagar(velhas)).then(() => contar()).then(restam => {
      if (enviadas) avisar({ tipo: "envio", enviadas, restam, texto: texto("enviado") });
      if (restam && falhou) {
        espera = Math.min(ESPERA_MAX_MS, espera ? espera * 2 : 5000);
        avisar({ tipo: "envio", enviadas: 0, restam, texto: texto("fila") });
        agendarEnvio(espera);
      } else if (!falhou) espera = 0;
      return { enviadas, restam };
    });
  }).finally(() => { enviando = null; });
  return enviando;
}
window.addEventListener("online", () => { espera = 0; agendarEnvio(500); });

/* ════════ Backends ════════ */
function capacitor() {
  const C = window.Capacitor;
  return C && typeof C.isNativePlatform === "function" && C.isNativePlatform() && C.Plugins && C.Plugins.BluetoothLe ? C.Plugins.BluetoothLe : null;
}

const nativo = {
  iniciado: null,
  iniciar(p) {
    if (!this.iniciado) this.iniciado = p.initialize({ androidNeverForLocation: true });
    return this.iniciado;
  },
  async disponivel(p) {
    await this.iniciar(p);
    const r = await p.isEnabled().catch(() => ({ value: true }));
    return r && r.value === false ? { ok: false, motivo: "desligado" } : { ok: true, motivo: "" };
  },
  async procurar(p, tipo) {
    await this.iniciar(p);
    const d = await p.requestDevice({ services: [SERVICO[tipo]], namePrefix: PREFIXO_NOME[tipo], optionalServices: [UUID.BATERIA, UUID.INFO] });
    return { id: d.deviceId, nome: d.name || PREFIXO_NOME[tipo] };
  },
  async conectar(p, ap) {
    await this.iniciar(p);
    if (ap.ouvintes) ap.ouvintes.forEach(h => h && h.remove && h.remove());
    ap.ouvintes = [];
    ap.ouvintes.push(await p.addListener("disconnected|" + ap.id, () => caiu(ap)));
    await p.connect({ deviceId: ap.id, timeout: 15000 });
    if (typeof p.isBonded === "function" && typeof p.createBond === "function") {   // só Android; no iOS o sistema pareia sozinho
      const b = await p.isBonded({ deviceId: ap.id }).catch(() => ({ value: true }));
      if (!b.value) { avisar({ tipo: "estado", aparelho: ap.id, estado: "pareando", texto: texto("pareando") }); await p.createBond({ deviceId: ap.id }); }
    }
    const svc = SERVICO[ap.tipo];
    ap.ouvintes.push(await p.addListener("notification|" + ap.id + "|" + svc + "|" + UUID.LINHA, r => receberPedaco(ap, r && r.value)));
    await p.startNotifications({ deviceId: ap.id, service: svc, characteristic: UUID.LINHA });
    try {
      const nv = await p.read({ deviceId: ap.id, service: UUID.BATERIA, characteristic: UUID.NIVEL_BATERIA });
      bateria(ap, nv && nv.value);
      ap.ouvintes.push(await p.addListener("notification|" + ap.id + "|" + UUID.BATERIA + "|" + UUID.NIVEL_BATERIA, r => bateria(ap, r && r.value)));
      await p.startNotifications({ deviceId: ap.id, service: UUID.BATERIA, characteristic: UUID.NIVEL_BATERIA });
    } catch (e) { /* bateria é opcional */ }
  },
  escrever(p, ap, bytes) {
    return p.write({ deviceId: ap.id, service: SERVICO[ap.tipo], characteristic: UUID.COMANDO, value: paraHex(bytes) });
  },
  async desconectar(p, ap) {
    try { await p.stopNotifications({ deviceId: ap.id, service: SERVICO[ap.tipo], characteristic: UUID.LINHA }); } catch (e) { /* já caiu */ }
    await p.disconnect({ deviceId: ap.id });
    (ap.ouvintes || []).forEach(h => h && h.remove && h.remove());
    ap.ouvintes = [];
  }
};

const web = {
  async disponivel() {
    if (!window.isSecureContext) return { ok: false, motivo: "inseguro" };
    const ok = await navigator.bluetooth.getAvailability().catch(() => true);
    return ok ? { ok: true, motivo: "" } : { ok: false, motivo: "desligado" };
  },
  async procurar(_, tipo) {
    const d = await navigator.bluetooth.requestDevice({
      filters: [{ services: [SERVICO[tipo]] }, { namePrefix: PREFIXO_NOME[tipo] }],
      optionalServices: [SERVICO[tipo], UUID.BATERIA, UUID.INFO]
    });
    return { id: d.id, nome: d.name || PREFIXO_NOME[tipo], web: d };
  },
  async conectar(_, ap) {
    if (!ap.web && navigator.bluetooth.getDevices) ap.web = (await navigator.bluetooth.getDevices()).find(d => d.id === ap.id);
    if (!ap.web) throw erro("sem_aparelho");
    if (!ap.webCaiu) { ap.webCaiu = () => caiu(ap); ap.web.addEventListener("gattserverdisconnected", ap.webCaiu); }
    const gatt = await ap.web.gatt.connect();
    const svc = await gatt.getPrimaryService(SERVICO[ap.tipo]);
    ap.carLinha = await svc.getCharacteristic(UUID.LINHA);
    ap.carComando = await svc.getCharacteristic(UUID.COMANDO);
    if (!ap.webLinha) { ap.webLinha = e => receberPedaco(ap, e.target.value); ap.carLinha.addEventListener("characteristicvaluechanged", ap.webLinha); }
    await ap.carLinha.startNotifications();       // característica cifrada: o sistema pede o pareamento aqui
    try {
      const b = await (await gatt.getPrimaryService(UUID.BATERIA)).getCharacteristic(UUID.NIVEL_BATERIA);
      bateria(ap, await b.readValue());
      b.addEventListener("characteristicvaluechanged", e => bateria(ap, e.target.value));
      await b.startNotifications();
    } catch (e) { /* bateria é opcional */ }
  },
  escrever(_, ap, bytes) {
    if (!ap.carComando) throw erro("sem_aparelho");
    return ap.carComando.writeValueWithResponse ? ap.carComando.writeValueWithResponse(bytes) : ap.carComando.writeValue(bytes);
  },
  async desconectar(_, ap) {
    try { if (ap.carLinha) await ap.carLinha.stopNotifications(); } catch (e) { /* já caiu */ }
    if (ap.web && ap.web.gatt.connected) ap.web.gatt.disconnect();
  }
};

function backend() {
  const p = capacitor();
  if (p) return { nome: "nativo", impl: nativo, plugin: p };
  if (navigator.bluetooth && typeof navigator.bluetooth.requestDevice === "function") return { nome: "web", impl: web, plugin: null };
  return { nome: "nenhum", impl: null, plugin: null };
}

function bateria(ap, valor) {
  const b = paraBytes(valor);
  if (!b.length) return;
  ap.bateria = Math.min(100, b[0]);
  avisar({ tipo: "bateria", aparelho: ap.id, pct: ap.bateria, texto: texto("bateria") + ": " + ap.bateria + "%" });
}

function caiu(ap) {
  if (!ap.ligado) return;
  ap.ligado = false;
  ap.buffer = "";
  avisar({ tipo: "estado", aparelho: ap.id, estado: "desconectado", texto: texto("desconectado") });
  if (!ap.querLigado) return;
  // pulseira: monitoramento contínuo — tenta de novo com espera crescente (até 2 min) enquanto a pessoa não desligar
  ap.tentativa = (ap.tentativa || 0) + 1;
  const ms = Math.min(120000, 2000 * Math.pow(2, ap.tentativa - 1));
  avisar({ tipo: "estado", aparelho: ap.id, estado: "reconectando", texto: texto("reconectando") });
  setTimeout(() => { if (ap.querLigado && !ap.ligado) conectar(ap.id).catch(() => caiu(Object.assign(ap, { ligado: true }))); }, ms);
}

/* ════════ API ════════ */
async function disponivel() {
  const b = backend();
  if (!b.impl) return { ok: false, backend: "nenhum", motivo: "nenhum", texto: texto("nenhum") };
  try {
    const r = await b.impl.disponivel(b.plugin);
    return { ok: r.ok, backend: b.nome, motivo: r.motivo, texto: texto(r.ok ? b.nome : r.motivo) };
  } catch (e) {
    return { ok: false, backend: b.nome, motivo: "nenhum", texto: texto("nenhum") };
  }
}

function configurar(op) {
  op = op || {};
  if (typeof op.hub === "string") {
    if (op.hub) urlHub(op.hub, "/");                        // recusa http fora da própria máquina
    cfg.hub = op.hub.replace(/\/+$/, "");
  }
  if (op.idioma === "pt" || op.idioma === "en") cfg.idioma = op.idioma;
  if (typeof op.enviar === "boolean") cfg.enviar = op.enviar;
  let p = Promise.resolve();
  if (op.chaves && typeof op.chaves === "object") {
    Object.keys(op.chaves).forEach(k => { const v = op.chaves[k]; if (v) cfg.chaves[String(k)] = String(v); else delete cfg.chaves[String(k)]; });
    p = guardarChaves();
  }
  return p.then(() => ({ hub: cfg.hub, idioma: cfg.idioma, aparelhosComChave: Object.keys(cfg.chaves) }));
}

async function procurar(op) {
  const tipo = String((op && op.tipo) || "").toLowerCase();
  if (!SERVICO[tipo]) throw new TypeError('tipo: "med" (caixinha) ou "pul" (pulseira)');
  const b = backend();
  if (!b.impl) throw erro("nenhum");
  avisar({ tipo: "estado", estado: "procurando", texto: texto("procurando") });
  let d;
  try { d = await b.impl.procurar(b.plugin, tipo); }
  catch (e) { const c = erro("cancelado", e); avisar({ tipo: "estado", estado: "cancelado", texto: c.message }); throw c; }
  const ap = aparelhos.get(d.id) || { id: d.id, buffer: "", ligado: false };
  Object.assign(ap, { nome: d.nome, tipo, web: d.web || ap.web });
  aparelhos.set(d.id, ap);
  return { id: ap.id, nome: ap.nome, tipo };
}

async function conectar(id) {
  const ap = aparelhos.get(id);
  if (!ap) throw erro("sem_aparelho");
  const b = backend();
  if (!b.impl) throw erro("nenhum");
  ap.querLigado = true;
  avisar({ tipo: "estado", aparelho: id, estado: "conectando", texto: texto("conectando") });
  await b.impl.conectar(b.plugin, ap);
  ap.ligado = true;
  ap.tentativa = 0;
  ap.buffer = "";
  novaSessao(ap);
  ultimo = id;
  avisar({ tipo: "estado", aparelho: id, estado: "conectado", texto: texto("conectado") });
  try { await escrever("CMD:00:SYNC:" + agora(), id); } catch (e) { /* aparelho antigo sem SYNC: segue */ }
  agendarEnvio(0);
  return { id, nome: ap.nome, tipo: ap.tipo };
}

function inscrever(cb) {
  if (typeof cb !== "function") throw new TypeError("inscrever(cb): cb tem de ser função");
  ouvintes.add(cb);
  return () => ouvintes.delete(cb);
}

const RE_CMD = /^CMD:(\d{2}):([A-Z]+)(?::([0-9A-Za-z./-]{1,64}))?$/;
function conferirComando(cmd) {
  const m = RE_CMD.exec(String(cmd || "").trim());
  if (!m || ACOES.indexOf(m[2]) < 0) return null;
  if (m[2] === "SYNC") { const t = Number(m[3]); if (!(t >= EPOCH_MIN && t <= EPOCH_MAX)) return null; }
  if (m[2] === "PING" && m[3]) return null;
  if (m[2] === "HOR" && !/^[1-8]\/([01]\d|2[0-3])[0-5]\d\/[1-7]{1,7}$/.test(m[3] || "")) return null;
  if (m[2] === "HORAPAGA" && !/^([1-8]|0)$/.test(m[3] || "")) return null;
  if ((m[2] === "TOL" || m[2] === "LIMBPM") && !/^\d{1,3}$/.test(m[3] || "")) return null;
  return m[0];
}

async function escrever(cmd, id) {
  const c = conferirComando(cmd);
  if (!c) throw erro("comando_invalido");
  const ap = aparelhos.get(id || ultimo);
  if (!ap || !ap.ligado) throw erro("sem_aparelho");
  const b = backend();
  if (!b.impl) throw erro("nenhum");
  await b.impl.escrever(b.plugin, ap, cod.encode(c + "\n"));
}

async function desconectar(id) {
  const lista = id ? [aparelhos.get(id)].filter(Boolean) : Array.from(aparelhos.values());
  const b = backend();
  for (const ap of lista) {
    ap.querLigado = false;
    if (b.impl && ap.ligado) { try { await b.impl.desconectar(b.plugin, ap); } catch (e) { /* já caiu */ } }
    ap.ligado = false;
    avisar({ tipo: "estado", aparelho: ap.id, estado: "desconectado", texto: texto("desconectado") });
  }
}

const pronto = temCifra() ? lerChaves() : Promise.resolve();
pronto.then(() => agendarEnvio(1500));

window.PhysisBLE = Object.freeze({
  VERSAO, UUID, PREFIXO_NOME, ACOES: ACOES.slice(), TEXTOS,
  disponivel, configurar, procurar, conectar, inscrever, escrever, desconectar,
  pendentes: () => pronto.then(contar), enviarPendentes, texto,
  backend: () => backend().nome, conferirLinha, conferirComando
});
})();
