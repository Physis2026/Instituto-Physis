/* Service worker do Sistema Physis (plataforma do cliente e Gestão).
 *
 * Servido em /app/sw.js com o cabeçalho Service-Worker-Allowed: / (cuida do site inteiro).
 * O servidor troca __VERSAO__ pela impressão digital das telas (physis_hub/app_pwa.py):
 * mudou uma tela, muda este arquivo, o celular instala a versão nova e apaga os caches velhos.
 *
 * Regras:
 *  - casca do app (/, /painel.html, /planejador/, /vendor/*, /app/*): funciona sem internet;
 *  - /gestao/: tenta a rede primeiro (a resposta depende da sessão) e só cai no cache sem rede;
 *  - /api/*: rede primeiro. Só GET /api/clima e GET /api/gis/* ficam guardados para ver sem rede.
 *    Nenhuma outra resposta da API (dados pessoais, sessão, gestão) é guardada;
 *  - POST/PUT/DELETE, outra origem, pedidos com Range (/mapas/*) e respostas "no-store": nunca no cache.
 */
"use strict";

var VERSAO = "__VERSAO__";
var CASCA = "physis-casca-" + VERSAO;
var DADOS = "physis-dados-" + VERSAO;
var PREFIXO = "physis-";
var MAX_DADOS = 80;

// guardado na instalação; obrigatórios (sem eles o app não abre sem rede)
var ESSENCIAIS = [
  "/",
  "/app/manifest-plataforma.webmanifest",
  "/app/icone-192.png",
  "/app/icone-512.png"
];
// guardados se existirem nesta instalação (nem todo servidor tem Gestão ou Planejador)
var OPCIONAIS = [
  "/app/manifest-gestao.webmanifest",
  "/app/icone-maskable-512.png",
  "/gestao/",
  "/planejador/",
  "/vendor/maplibre-gl.js",
  "/vendor/maplibre-gl.css",
  "/vendor/pmtiles.js"
];
// /vendor/three.min.js, /vendor/web-ifc-api-iife.js e /vendor/web-ifc.wasm (BIM, pesados)
// entram no cache na primeira vez que o Planejador os usa.

var TELAS_CASCA = ["/", "/painel.html", "/planejador/"];
var APELIDOS = { "/painel.html": "/", "/planejador": "/planejador/", "/gestao": "/gestao/",
                 "/demo": "/", "/demo/": "/", "/loja": "/", "/loja/": "/" };

// casca: só 200 da própria origem e sem "no-store" (a página de entrar da Gestão vem com no-store)
function podeGuardar(resp) {
  if (!resp || !resp.ok || resp.status !== 200 || resp.type !== "basic") return false;
  var cc = (resp.headers.get("Cache-Control") || "").toLowerCase();
  return cc.indexOf("no-store") < 0 && cc.indexOf("private") < 0;
}

// dados de clima e GIS: toda resposta da API vem com no-store (para cache HTTP e proxies);
// estas duas, e só estas, o app guarda de propósito para ver sem rede. Só JSON 200 da própria origem.
function podeGuardarDados(resp) {
  return !!resp && resp.status === 200 && resp.type === "basic" &&
    (resp.headers.get("Content-Type") || "").indexOf("application/json") >= 0;
}

function ehHtml(resp) {
  return (resp.headers.get("Content-Type") || "").indexOf("text/html") >= 0;
}

function guardar(cache, chave, resp) {
  return caches.open(cache).then(function (c) { return c.put(chave, resp); });
}

// resposta que ninguém vai ler: descartar o corpo. Corpo não lido segura a conexão aberta, e com
// ~6 conexões por endereço o navegador para de buscar (a instalação ficava travada assim).
function descartar(resp) {
  try { if (resp && resp.body && !resp.bodyUsed) resp.body.cancel().catch(function () {}); } catch (e) {}
}

function guardarSeExistir(c, url) {
  return fetch(url, { credentials: "same-origin", cache: "no-cache" }).then(function (r) {
    // /gestao/ sem sessão devolve a página de entrar com no-store: não é guardada
    if (podeGuardar(r)) return c.put(url, r);
    descartar(r);
  }).catch(function () {});
}

// um pedido de cada vez: a instalação não disputa conexões com a tela que está abrindo
function emSequencia(lista, fazer) {
  return lista.reduce(function (p, u) { return p.then(function () { return fazer(u); }); }, Promise.resolve());
}

self.addEventListener("install", function (ev) {
  ev.waitUntil(caches.open(CASCA).then(function (c) {
    return emSequencia(ESSENCIAIS, function (u) {
      return fetch(u, { credentials: "same-origin", cache: "no-cache" }).then(function (r) {
        if (!r.ok) { descartar(r); throw new Error("falhou " + u); }
        return c.put(u, r);
      });
    }).then(function () {
      return emSequencia(OPCIONAIS, function (u) { return guardarSeExistir(c, u); });
    });
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (ev) {
  ev.waitUntil(caches.keys().then(function (nomes) {
    return Promise.all(nomes.filter(function (n) {
      return n.indexOf(PREFIXO) === 0 && n !== CASCA && n !== DADOS;
    }).map(function (n) { return caches.delete(n); }));
  }).then(function () { return self.clients.claim(); }));
});

// a tela pode pedir para apagar o que é da sessão (ao sair da conta):
// navigator.serviceWorker.controller.postMessage({ tipo: "sair" })
self.addEventListener("message", function (ev) {
  var d = ev.data || {};
  if (d.tipo === "sair") {
    ev.waitUntil(Promise.all([
      caches.delete(DADOS),
      caches.open(CASCA).then(function (c) { return c.delete("/gestao/"); })
    ]));
  } else if (d.tipo === "atualizar") {
    self.skipWaiting();
  }
});

function limitar(nome, max) {
  return caches.open(nome).then(function (c) {
    return c.keys().then(function (k) {
      if (k.length <= max) return;
      return Promise.all(k.slice(0, k.length - max).map(function (r) { return c.delete(r); }));
    });
  });
}

// casca: responde do cache na hora e atualiza por trás (na próxima abertura já vem a nova)
function cascaPrimeiro(ev, chave) {
  var daRede = fetch(ev.request).then(function (r) {
    if (podeGuardar(r) && (ehHtml(r) || chave.indexOf("/app/") === 0 || chave.indexOf("/vendor/") === 0)) {
      var copia = r.clone();
      ev.waitUntil(guardar(CASCA, chave, copia));
    }
    return r;
  });
  return caches.match(chave, { cacheName: CASCA }).then(function (salvo) {
    if (salvo) {
      // a resposta da rede só serve para atualizar o cache: o corpo dela é descartado
      ev.waitUntil(daRede.then(descartar, function () {}));
      return salvo;
    }
    return daRede.catch(function () { return paginaSemRede(); });
  });
}

// rede primeiro; sem rede, o que estiver guardado
function redePrimeiro(ev, chave, cache) {
  return fetch(ev.request).then(function (r) {
    if (cache === DADOS ? podeGuardarDados(r) : (podeGuardar(r) && ehHtml(r))) {
      var copia = r.clone();
      ev.waitUntil(guardar(cache, chave, copia).then(function () {
        return cache === DADOS ? limitar(DADOS, MAX_DADOS) : null;
      }));
    }
    return r;
  }).catch(function () {
    return caches.match(chave, { cacheName: cache }).then(function (salvo) {
      if (salvo) return salvo;
      if (ev.request.mode === "navigate") return paginaSemRede();
      return new Response(JSON.stringify({ ok: false, erro: "sem conexão", offline: true }), {
        status: 503, headers: { "Content-Type": "application/json; charset=utf-8" }
      });
    });
  });
}

function paginaSemRede() {
  return caches.match("/", { cacheName: CASCA }).then(function (r) {
    return r || new Response(
      "<!doctype html><html lang=\"pt-BR\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">" +
      "<title>Sem conexão · Physis</title><body style=\"font:16px system-ui,sans-serif;background:#F4F6F1;color:#1C2B21;padding:24px\">" +
      "<h1 style=\"color:#33512F\">Sem conexão</h1><p>Não foi possível falar com o servidor Physis. Confira a internet e tente de novo.</p></body></html>",
      { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } });
  });
}

self.addEventListener("fetch", function (ev) {
  var req = ev.request;
  if (req.method !== "GET") return;                 // POST e afins: nunca no cache
  if (req.headers.has("range")) return;             // mapas PMTiles (206) ficam com o navegador
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return;  // servidor de chamadas e qualquer outra origem: direto
  var p = url.pathname;

  if (p.indexOf("/api/") === 0) {
    if (p === "/api/clima" || p.indexOf("/api/gis/") === 0) {
      ev.respondWith(redePrimeiro(ev, p + url.search, DADOS));
    }
    return;                                         // resto da API: direto, sem guardar nada
  }
  if (p.indexOf("/mapas/") === 0) return;

  var chave = APELIDOS[p] || p;
  if (chave === "/gestao/") {
    ev.respondWith(redePrimeiro(ev, chave, CASCA));
    return;
  }
  if (TELAS_CASCA.indexOf(chave) >= 0 || p.indexOf("/vendor/") === 0 || p.indexOf("/app/") === 0) {
    if (p === "/app/sw.js") return;
    ev.respondWith(cascaPrimeiro(ev, chave));
    return;
  }
  if (req.mode === "navigate") {
    // outra página do site sem rede: abre o painel guardado
    ev.respondWith(fetch(req).catch(function () { return paginaSemRede(); }));
  }
});
