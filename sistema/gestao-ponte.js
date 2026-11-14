/* gestao-ponte.js · 14/11/2026 · ORIGINAL ÚNICO: vai embutido na Gestão Physis (sincronizar.py).
 *
 * Ponte entre a Gestão Physis e o servidor da Physis (Hub). Roda ANTES do aplicativo:
 *  1. Busca no servidor os dados da Gestão (atividades, painel administrativo, reuniões, documentos...).
 *  2. Junta com o que houver neste navegador (por exemplo, o que a pessoa fez antes de existir o servidor)
 *     e grava no navegador, para o aplicativo já abrir atualizado.
 *  3. Depois, a casca envia cada mudança ao servidor e busca as mudanças das outras pessoas.
 *
 * Aberta como arquivo (sem servidor), não faz nada: tudo continua no navegador, como antes.
 *
 * Junção de mudanças (juntar3): compara a última versão combinada com o servidor (base), a deste navegador
 * (local) e a do servidor. Registros com "id" são juntados um a um: novo de um lado entra, apagado de um
 * lado sai, alterado nos dois tem os campos juntados. No mesmo campo alterado dos dois lados, vale o local.
 */
(function (g) {
  "use strict";
  var LOCAIS = /^gestao-physis:(ultima-copia|melhorias-oferecidas|melhorias-2026-11-14)$/;   // só deste aparelho
  var rastreada = function (k) { return /^gestao-physis:/.test(k) && !LOCAIS.test(k); };
  var setRaw = Storage.prototype.setItem.bind(localStorage);
  function ler(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function gravar(k, v) { try { setRaw(k, v); return true; } catch (e) { return false; } }
  function meta() { try { return JSON.parse(ler("physis-ponte:versoes") || "{}"); } catch (e) { return {}; } }

  function idDe(x) { return x && typeof x === "object" && !Array.isArray(x) ? (x.id != null ? "id:" + x.id : x.numero != null ? "n:" + x.numero : x.chave != null ? "c:" + x.chave : null) : null; }
  function igual(a, b) { return JSON.stringify(a) === JSON.stringify(b); }
  function juntar3(B, L, S) {
    if (igual(L, S) || igual(L, B)) return S;
    if (igual(S, B)) return L;
    if (Array.isArray(L) && Array.isArray(S)) {
      var comId = function (a) { return a.every(function (x) { return idDe(x) !== null; }); };
      if (comId(L) && comId(S) && (!Array.isArray(B) || comId(B))) {
        var mapa = function (a) { var m = {}; (a || []).forEach(function (x) { m[idDe(x)] = x; }); return m; };
        var mb = mapa(Array.isArray(B) ? B : []), ml = mapa(L), out = [], vistos = {};
        S.forEach(function (x) { var k = idDe(x); vistos[k] = true;
          if (!(k in ml)) { if (!(k in mb)) out.push(x); return; }          // novo no servidor entra; apagado aqui sai
          out.push(juntar3(mb[k], ml[k], x)); });
        L.forEach(function (x) { var k = idDe(x); if (!vistos[k] && !(k in mb)) out.push(x); });   // novo aqui entra; apagado no servidor sai
        return out;
      }
      return L;
    }
    if (L && S && typeof L === "object" && typeof S === "object" && !Array.isArray(L) && !Array.isArray(S)) {
      var b = B && typeof B === "object" && !Array.isArray(B) ? B : {}, o = {}, ks = {};
      Object.keys(S).concat(Object.keys(L)).forEach(function (k) { ks[k] = true; });
      Object.keys(ks).forEach(function (k) { var inL = k in L, inS = k in S, inB = k in b;
        if (inL && inS) o[k] = juntar3(b[k], L[k], S[k]);
        else if (inL) { if (!inB || !igual(L[k], b[k])) o[k] = L[k]; }
        else if (inS) { if (!inB || !igual(S[k], b[k])) o[k] = S[k]; } });
      return o;
    }
    return L;
  }
  function parse(t) { if (t == null) return undefined; try { return JSON.parse(t); } catch (e) { return t; } }
  function juntarTexto(b, l, s) {
    var B = parse(b), L = parse(l), S = parse(s);
    if (typeof L === "string" || typeof S === "string") return l != null && l !== b ? l : s;
    return JSON.stringify(juntar3(B, L, S));
  }

  var P = g.PHYSIS_PONTE = { ativa: false, rastreada: rastreada, juntar3: juntar3, juntarTexto: juntarTexto, setRaw: setRaw, sujas: {}, mudou: false };
  if (!/^https?:$/.test(location.protocol)) return;
  var x = new XMLHttpRequest();
  try { x.open("GET", "/api/gestao/estado", false); x.send(); } catch (e) { P.erro = "sem servidor"; return; }
  if (x.status === 401) { location.reload(); return; }           // a página de entrada aparece
  if (x.status !== 200) { P.erro = "servidor sem Gestão (" + x.status + ")"; return; }
  var j; try { j = JSON.parse(x.responseText); } catch (e) { P.erro = "resposta inválida"; return; }
  var it = j.itens || {}, m = meta();
  P.ativa = true; P.conta = j.conta || {}; P.desde = j.agora || 0;
  // o que o servidor tem
  Object.keys(it).forEach(function (k) { if (!rastreada(k)) return;
    var s = it[k], l = ler(k), b = ler("physis-ponte:base:" + k), v = m[k] || 0;
    if (l === null || l === b || l === s.valor || (v === s.versao && l === b)) { gravar(k, s.valor); }
    else { var junto = juntarTexto(b, l, s.valor); gravar(k, junto); if (junto !== s.valor) P.sujas[k] = true; }
    gravar("physis-ponte:base:" + k, s.valor); m[k] = s.versao; });
  // o que só este navegador tem (por exemplo, dados de antes do servidor): sobe para o servidor
  for (var i = 0; i < localStorage.length; i++) { var k = localStorage.key(i); if (rastreada(k) && !(k in it)) P.sujas[k] = true; }
  gravar("physis-ponte:versoes", JSON.stringify(m));

  /* ───────── durante o uso ───────── */
  var timers = {}, avisoCb = null;
  function avisar(t, recarregar) { P.ultimoAviso = { texto: t, recarregar: !!recarregar }; if (avisoCb) avisoCb(P.ultimoAviso); }
  P.aoAvisar = function (cb) { avisoCb = cb; if (P.ultimoAviso) cb(P.ultimoAviso); };
  function enviar(k, tentativa) {
    var mm = meta(), valor = ler(k); if (valor === null) return;
    fetch("/api/gestao/estado/" + encodeURIComponent(k), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ valor: valor, versao: mm[k] || 0 }) })
      .then(function (r) { return r.json().then(function (j) { return { st: r.status, j: j }; }); })
      .then(function (o) {
        var m2 = meta();
        if (o.st === 200) { m2[k] = o.j.versao; gravar("physis-ponte:versoes", JSON.stringify(m2)); gravar("physis-ponte:base:" + k, valor); delete P.sujas[k]; return; }
        if (o.st === 409 && (tentativa || 0) < 4) {
          // outra pessoa gravou antes: junta as duas versões e tenta de novo
          var junto = juntarTexto(ler("physis-ponte:base:" + k), ler(k), o.j.valor);
          if (junto !== ler(k)) { gravar(k, junto); avisar("Juntamos mudanças de " + (o.j.por || "outra pessoa") + ". Recarregue para ver tudo atualizado.", true); }
          m2[k] = o.j.versao; gravar("physis-ponte:versoes", JSON.stringify(m2)); gravar("physis-ponte:base:" + k, o.j.valor);
          return enviar(k, (tentativa || 0) + 1);
        }
        if (o.st === 401) return avisar("A sessão terminou. Entre de novo para continuar salvando no servidor.", true);
        avisar("Não foi possível salvar no servidor: " + ((o.j && o.j.erro) || o.st) + ". O dado continua neste navegador.", false);
      })
      .catch(function () { P.sujas[k] = true; avisar("Sem ligação com o servidor. As mudanças ficam neste navegador e sobem quando a ligação voltar.", false); });
  }
  P.agendar = function (k) { P.sujas[k] = true; clearTimeout(timers[k]); timers[k] = setTimeout(function () { delete timers[k]; enviar(k); }, 800); };
  P.buscar = function () {
    return fetch("/api/gestao/estado?desde=" + encodeURIComponent(P.desde), { cache: "no-store" }).then(function (r) { if (r.status === 401) { avisar("A sessão terminou. Entre de novo.", true); return null; } return r.json(); })
      .then(function (j2) { if (!j2 || !j2.itens) return; P.desde = j2.agora || P.desde; var mm = meta(), quem = {}, mudou = 0;
        Object.keys(j2.itens).forEach(function (k) { var s = j2.itens[k]; if (!rastreada(k) || s.versao <= (mm[k] || 0)) return;
          if (P.sujas[k]) return;                                       // mudança local a caminho: a gravação junta
          if (ler(k) !== s.valor) { gravar(k, s.valor); mudou++; quem[s.por] = true; }
          gravar("physis-ponte:base:" + k, s.valor); mm[k] = s.versao; });
        gravar("physis-ponte:versoes", JSON.stringify(mm));
        if (mudou) avisar("Há novidades de " + Object.keys(quem).join(", ") + ". Recarregue para ver.", true);
        Object.keys(P.sujas).forEach(function (k) { if (!timers[k]) P.agendar(k); }); })
      .catch(function () {});
  };
  P.iniciarUso = function () {
    if (!P.ativa || P.emUso) return; P.emUso = true;
    // toda gravação da Gestão neste navegador também vai para o servidor
    var orig = Storage.prototype.setItem;
    Storage.prototype.setItem = function (k, v) { orig.call(this, k, v); if (this === localStorage && rastreada(k)) P.agendar(k); };
    Object.keys(P.sujas).forEach(function (k) { P.agendar(k); });
    setInterval(function () { if (!document.hidden) P.buscar(); }, 15000);
    window.addEventListener("online", function () { Object.keys(P.sujas).forEach(function (k) { P.agendar(k); }); });
  };
  /* arquivos (anexos, comprovantes, gravações): também no servidor */
  P.subirArquivo = function (id, f) {
    return fetch("/api/gestao/arquivo/" + encodeURIComponent(id), { method: "PUT", headers: { "Content-Type": (f && f.type) || "application/octet-stream", "X-Nome": encodeURIComponent((f && f.name) || "arquivo") }, body: f })
      .then(function (r) { if (!r.ok) avisar("Um arquivo não subiu para o servidor; ele continua neste navegador.", false); return r.ok; }).catch(function () { return false; });
  };
  P.baixarArquivo = function (id) {
    return fetch("/api/gestao/arquivo/" + encodeURIComponent(id), { cache: "no-store" }).then(function (r) { if (!r.ok) return null;
      var nome = decodeURIComponent(((r.headers.get("Content-Disposition") || "").split("''")[1] || "arquivo"));
      return r.blob().then(function (b) { try { return new File([b], nome, { type: b.type }); } catch (e) { return b; } }); }).catch(function () { return null; });
  };
  P.apagarArquivo = function (id) { return fetch("/api/gestao/arquivo/" + encodeURIComponent(id), { method: "DELETE" }).catch(function () {}); };
})(window);
