/* physis-ponte-cliente.js · 15/11/2026 · ORIGINAL ÚNICO: vai embutido na plataforma do cliente (web/painel.html).
 *
 * Ponte entre a plataforma do cliente e o servidor (Physis Hub), no molde da gestao-ponte.js da Gestão.
 * Antes, o perfil e os dados de cada módulo ficavam só neste navegador (localStorage); trocar de computador
 * ou limpar o navegador apagava tudo. Agora:
 *  1. Ao abrir (ANTES do aplicativo), busca no servidor os dados da organização (GET /api/cliente/estado) e
 *     grava no navegador, para a tela já abrir atualizada.
 *  2. Cada gravação da tela numa chave da lista também sobe para o servidor (PUT /api/cliente/estado/<chave>),
 *     com a versão em que se baseou.
 *  3. Se outra pessoa gravou antes (409), vale a mudança MAIS NOVA (a última a ser feita) e a pessoa é avisada.
 *  4. Sem ligação, as mudanças ficam numa fila neste navegador e sobem quando a ligação volta.
 *
 * Sem servidor (arquivo aberto do disco), sem sessão, ou na loja/demonstração: não faz nada; tudo continua
 * só no navegador, como antes. Chaves que vão para o servidor: as da lista abaixo (a mesma do servidor,
 * physis_hub/perfil_cliente.py). As de controle desta ponte começam com "physis-ponte-cliente:".
 *
 * Uso na tela:  PHYSIS_PONTE_CLIENTE.aoAvisar(function (a) { ... a.texto, a.recarregar ... });
 *               PHYSIS_PONTE_CLIENTE.ativa  (true = ligada ao servidor)
 */
(function (g) {
  "use strict";
  /* as seis últimas: qualidade da água (15/11/2026), as mesmas CHAVES_AGUA de perfil_cliente.py */
  var CHAVES = ["physis-perfil", "physis-gestao-cliente", "physis-carbono", "physis-residuos-plano", "physis-cert-gap",
                "physis-sbn", "physis.terreno.v1", "physis-servidor-verde",
                "physis-ph-leituras", "physis-ph-calibracoes", "physis-ph-laboratorio", "physis-agua-limites", "physis-agua-laudos", "physis-agua-config"];
  var PREFIXOS = ["physis-calc-", "physis-curso-"];
  var SUFIXO = /^[A-Za-z0-9_.:-]{1,60}$/;
  var PRE = "physis-ponte-cliente:";
  var NOMES = { "physis-perfil": "perfil", "physis-gestao-cliente": "gestão", "physis-carbono": "inventário de carbono",
                "physis-residuos-plano": "plano de resíduos", "physis-cert-gap": "certificações", "physis-sbn": "soluções baseadas na natureza",
                "physis.terreno.v1": "terreno", "physis-servidor-verde": "projetos de servidor verde",
                "physis-ph-leituras": "leituras de água", "physis-ph-calibracoes": "calibrações de pH", "physis-ph-laboratorio": "análises de laboratório",
                "physis-agua-limites": "limites da água", "physis-agua-laudos": "laudos da água", "physis-agua-config": "configuração da água" };
  function rastreada(k) {
    k = String(k == null ? "" : k);
    if (CHAVES.indexOf(k) >= 0) return true;
    for (var i = 0; i < PREFIXOS.length; i++) if (k.indexOf(PREFIXOS[i]) === 0 && SUFIXO.test(k.slice(PREFIXOS[i].length))) return true;
    return false;
  }
  function nome(k) { return NOMES[k] || (k.indexOf("physis-curso-") === 0 ? "curso" : k.indexOf("physis-calc-") === 0 ? "calculadora" : k); }

  var P = g.PHYSIS_PONTE_CLIENTE = { ativa: false, rastreada: rastreada, sujas: {}, erro: null };
  var ls; try { ls = g.localStorage; } catch (e) { P.erro = "sem armazenamento"; return; }
  if (!ls) { P.erro = "sem armazenamento"; return; }
  var setRaw = Storage.prototype.setItem;
  function ler(k) { try { return ls.getItem(k); } catch (e) { return null; } }
  function gravar(k, v) { try { setRaw.call(ls, k, v); return true; } catch (e) { return false; } }
  function lerJ(k, padrao) { try { var v = JSON.parse(ler(PRE + k) || "null"); return v == null ? padrao : v; } catch (e) { return padrao; } }
  function gravarJ(k, v) { gravar(PRE + k, JSON.stringify(v)); }
  // a "base" (último valor combinado com o servidor) é guardada só como resumo: o navegador tem pouco espaço
  function resumo(t) { if (t == null) return null; var h = 2166136261; for (var i = 0; i < t.length; i++) { h ^= t.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; } return t.length + ":" + h.toString(36); }

  if (!/^https?:$/.test(location.protocol)) { P.erro = "sem servidor"; return; }
  if (/^\/(demo|loja|consultoria|gestao|conta|ativar)(\/|$)/.test(location.pathname)) { P.erro = "fora da plataforma"; return; }

  function xhrSinc(metodo, url) {
    var x = new XMLHttpRequest();
    try { x.open(metodo, url, false); x.setRequestHeader("Accept", "application/json"); x.send(); } catch (e) { return { st: 0, j: null }; }
    var j = null; try { j = JSON.parse(x.responseText); } catch (e) {}
    return { st: x.status, j: j };
  }
  var inst = xhrSinc("GET", "/api/instancia");
  if (inst.st !== 200 || !inst.j) { P.erro = "sem servidor"; return; }
  if (!inst.j.autenticado) { P.erro = "sem sessão"; return; }      // sem conta: continua só no navegador
  P.csrf = inst.j.csrf || null;
  var est = xhrSinc("GET", "/api/cliente/estado");
  if (est.st !== 200 || !est.j || !est.j.itens) { P.erro = "servidor sem dados do cliente (" + est.st + ")"; return; }

  var versoes = lerJ("versoes", {}), bases = lerJ("bases", {}), quando = lerJ("quando", {});
  lerJ("fila", []).forEach(function (k) { if (rastreada(k)) P.sujas[k] = true; });   // o que ficou sem subir da última vez
  var avisos = [];
  function salvarMeta() { gravarJ("versoes", versoes); gravarJ("bases", bases); gravarJ("quando", quando); gravarJ("fila", Object.keys(P.sujas)); }
  var it = est.j.itens;
  P.ativa = true; P.org = est.j.org; P.conta = est.j.conta || {}; P.desde = est.j.agora || 0;

  /* ───────── ao abrir: junta o servidor com este navegador ───────── */
  Object.keys(it).forEach(function (k) {
    if (!rastreada(k)) return;
    var s = it[k], l = ler(k);
    var mudouAqui = l !== null && l !== s.valor && resumo(l) !== bases[k];
    if (!mudouAqui) { if (l !== s.valor) gravar(k, s.valor); delete P.sujas[k]; }
    else if ((quando[k] || 0) > (s.atualizado || 0) * 1000) { P.sujas[k] = true; }          // a daqui é mais nova: sobe
    else { gravar(k, s.valor); delete P.sujas[k]; avisos.push("Havia uma versão mais nova (" + nome(k) + ", de " + (s.por || "outra pessoa") + "); ela substituiu a deste navegador."); }
    bases[k] = resumo(s.valor); versoes[k] = s.versao;
  });
  for (var i = 0; i < ls.length; i++) { var k0 = ls.key(i); if (rastreada(k0) && !(k0 in it)) { P.sujas[k0] = true; if (!quando[k0]) quando[k0] = Date.now(); } }
  salvarMeta();

  /* ───────── durante o uso ───────── */
  var timers = {}, avisoCb = null, offlineAvisado = false;
  function avisar(t, recarregar) { P.ultimoAviso = { texto: t, recarregar: !!recarregar }; if (avisoCb) { try { avisoCb(P.ultimoAviso); } catch (e) {} } }
  P.aoAvisar = function (cb) { avisoCb = cb; if (P.ultimoAviso) cb(P.ultimoAviso); };
  if (avisos.length) avisar(avisos.join(" "), false);

  function renovarCsrf() { var r = xhrSinc("GET", "/api/instancia"); if (r.st === 200 && r.j) P.csrf = r.j.csrf || null; }
  function cabecalhos() { var h = { "Content-Type": "application/json" }; if (P.csrf) h["X-Physis-CSRF"] = P.csrf; return h; }

  function enviar(k, tentativa, manter) {
    tentativa = tentativa || 0;
    var valor = ler(k);
    if (valor === null) { delete P.sujas[k]; salvarMeta(); return Promise.resolve(); }
    return fetch("/api/cliente/estado/" + encodeURIComponent(k), { method: "PUT", headers: cabecalhos(), keepalive: !!manter && valor.length < 60000,
                                                                     body: JSON.stringify({ valor: valor, versao: versoes[k] || 0 }) })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { return { st: r.status, j: j }; }); })
      .then(function (o) {
        offlineAvisado = false;
        if (o.st === 200) { versoes[k] = o.j.versao; bases[k] = resumo(valor); if (ler(k) === valor) delete P.sujas[k]; salvarMeta(); return; }
        if (o.st === 409 && tentativa < 3) {
          // outra pessoa gravou antes: vale a mudança mais nova
          versoes[k] = o.j.versao; bases[k] = resumo(o.j.valor);
          if ((quando[k] || Date.now()) >= (o.j.atualizado || 0) * 1000) {
            salvarMeta();
            avisar("A sua mudança (" + nome(k) + ") substituiu uma gravada antes por " + (o.j.por || "outra pessoa") + ".", false);
            return enviar(k, tentativa + 1);
          }
          if (o.j.valor != null) gravar(k, o.j.valor);
          delete P.sujas[k]; salvarMeta();
          return avisar("Havia uma versão mais nova (" + nome(k) + ", de " + (o.j.por || "outra pessoa") + "). Recarregue para ver.", true);
        }
        if (o.st === 403 && o.j && o.j.csrf && tentativa < 1) { renovarCsrf(); return enviar(k, tentativa + 1); }
        if (o.st === 401) return avisar("A sessão terminou. Entre de novo para continuar salvando no servidor; até lá, fica neste navegador.", true);
        if (o.st === 413 || o.st === 400) { delete P.sujas[k]; salvarMeta();
          return avisar("Não foi possível guardar no servidor (" + nome(k) + "): " + ((o.j && o.j.erro) || o.st) + ". O dado continua neste navegador.", false); }
        avisar("Não foi possível salvar no servidor agora (" + o.st + "). Tentamos de novo em seguida.", false);
      })
      .catch(function () {
        P.sujas[k] = true; salvarMeta();
        if (!offlineAvisado) { offlineAvisado = true; avisar("Sem ligação com o servidor. As mudanças ficam neste navegador e sobem quando a ligação voltar.", false); }
      });
  }
  P.agendar = function (k) {
    P.sujas[k] = true; salvarMeta();
    clearTimeout(timers[k]); timers[k] = setTimeout(function () { delete timers[k]; enviar(k); }, 800);
  };
  P.enviarFila = function () { Object.keys(P.sujas).forEach(function (k) { if (!timers[k]) enviar(k); }); };
  P.buscar = function () {
    return fetch("/api/cliente/estado?desde=" + encodeURIComponent(P.desde), { cache: "no-store" })
      .then(function (r) { if (r.status === 401) { avisar("A sessão terminou. Entre de novo.", true); return null; } return r.ok ? r.json() : null; })
      .then(function (j) {
        if (!j || !j.itens) return;
        P.desde = j.agora || P.desde; var quem = {}, mudou = 0;
        Object.keys(j.itens).forEach(function (k) {
          var s = j.itens[k]; if (!rastreada(k) || s.versao <= (versoes[k] || 0)) return;
          if (P.sujas[k]) return;                                      // mudança daqui a caminho: a gravação resolve
          if (ler(k) !== s.valor) { gravar(k, s.valor); mudou++; quem[s.por || "outra pessoa"] = true; }
          bases[k] = resumo(s.valor); versoes[k] = s.versao;
        });
        salvarMeta();
        if (mudou) avisar("Há novidades de " + Object.keys(quem).join(", ") + ". Recarregue para ver.", true);
        P.enviarFila();
      })
      .catch(function () {});
  };

  // toda gravação da tela numa chave da lista também vai para o servidor
  Storage.prototype.setItem = function (k, v) {
    setRaw.call(this, k, v);
    if (this === ls && rastreada(k)) { quando[k] = Date.now(); P.agendar(k); }
  };
  Object.keys(P.sujas).forEach(function (k) { P.agendar(k); });
  setInterval(function () { if (!document.hidden) P.buscar(); }, 30000);
  g.addEventListener("online", function () { P.enviarFila(); });
  // ao sair da página: o que ainda estava esperando os 800 ms sobe já (keepalive)
  g.addEventListener("pagehide", function () {
    Object.keys(timers).forEach(function (k) { clearTimeout(timers[k]); delete timers[k]; enviar(k, 0, true); });
  });
})(window);
