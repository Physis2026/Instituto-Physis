/* physis-modelagem.js — vista 3D e modelagem direta no navegador (Modelos BIM e Montagens da Modelagem 3D da InovaSTEM).
   Pedido da dona (20 e 21/11/2026): abrir IFC com geometria, modelar peças e montagens com ferramentas no estilo do
   SketchUp (selecionar, mover, girar, escalar, empurrar/puxar, linha, retângulo, círculo, medir/cota, desfazer/refazer),
   tudo com formatos abertos (SVG, DXF, STL, 3MF, IFC e o JSON do projeto). Sem internet e sem biblioteca de licença fechada:
     three.js 0.160 (MIT) e web-ifc 0.0.66 (MPL-2.0), entregues pelo próprio servidor em /vendor/ (vendor/LEIA-ME.md),
     carregados só quando a subaba abre; a geometria e as contas de malha vêm de sistema/physis-imagem-3d.js e do motor
     do Physis 3D (PHYSIS3D.medir, escreverSTL, escrever3MF), sem mudar nenhuma função nem conta deles.
   Contrato:
     PhysisModelagem.carregar(["three", "webifc"]) → Promise (põe os scripts de /vendor/ na página uma vez)
     PhysisModelagem.lerIfc(ArrayBuffer) → Promise<{ objetos, resumo }>  (geometria em mm, z para cima)
     PhysisModelagem.editor(opcoes) → editor com objetos, ferramenta, seleção, histórico e a vista 3D (anexar(div))
   Unidades: milímetros. O web-ifc entrega a geometria em metros (y para cima): aqui vira mm com z para cima. */
(function () {
"use strict";
const I = () => window.PhysisImagem3D;
const carregados = {};
function carregarScript(src) {
  if (carregados[src]) return carregados[src];
  return (carregados[src] = new Promise((ok, falha) => {
    const s = document.createElement("script"); s.src = src; s.async = true;
    s.onload = () => ok(); s.onerror = () => { delete carregados[src]; falha(new Error("não carregou " + src)); };
    document.head.appendChild(s);
  }));
}
const VENDOR = { three: "/vendor/three.min.js", webifc: "/vendor/web-ifc-api-iife.js" };
function carregar(quais) { return Promise.all((quais || []).map(q => carregarScript(VENDOR[q]))); }

/* ════════ IFC com geometria (web-ifc) ════════ */
let apiIfc = null;
async function lerIfc(buf) {
  await carregar(["webifc"]);
  if (!apiIfc) { apiIfc = new window.WebIFC.IfcAPI(); apiIfc.SetWasmPath("/vendor/", true); await apiIfc.Init(undefined, true); }
  const api = apiIfc, W = window.WebIFC, id = api.OpenModel(new Uint8Array(buf), { COORDINATE_TO_ORIGIN: true });
  if (id < 0) throw new Error("o web-ifc não abriu o arquivo");
  try {
    const porEl = new Map();
    api.StreamAllMeshes(id, mesh => {
      const eid = mesh.expressID, lista = porEl.get(eid) || [], n = mesh.geometries.size();
      for (let i = 0; i < n; i++) {
        const pg = mesh.geometries.get(i), g = api.GetGeometry(id, pg.geometryExpressID);
        const v = api.GetVertexArray(g.GetVertexData(), g.GetVertexDataSize()), ix = api.GetIndexArray(g.GetIndexData(), g.GetIndexDataSize()), m = pg.flatTransformation;
        const T = new Float32Array(ix.length * 3);
        for (let k = 0; k < ix.length; k++) {
          const o = ix[k] * 6, x = v[o], y = v[o + 1], z = v[o + 2];
          const X = m[0] * x + m[4] * y + m[8] * z + m[12], Y = m[1] * x + m[5] * y + m[9] * z + m[13], Z = m[2] * x + m[6] * y + m[10] * z + m[14];
          T[3 * k] = X * 1000; T[3 * k + 1] = -Z * 1000; T[3 * k + 2] = Y * 1000;     // metros, y para cima → mm, z para cima
        }
        lista.push(T);
        if (g.delete) g.delete();
      }
      porEl.set(eid, lista);
    });
    const pav = new Map(), pavs = [], contidos = [];
    const rels = api.GetLineIDsWithType(id, W.IFCRELCONTAINEDINSPATIALSTRUCTURE);
    for (let i = 0; i < rels.size(); i++) {
      const r = api.GetLine(id, rels.get(i)), est = r.RelatingStructure && api.GetLine(id, r.RelatingStructure.value);
      const nome = est && est.Name ? est.Name.value : ""; if (nome && pavs.indexOf(nome) < 0) pavs.push(nome);
      (r.RelatedElements || []).forEach(e => { pav.set(e.value, nome); contidos.push(e.value); });
    }
    const objetos = [], porTipo = {};
    porEl.forEach((lista, eid) => {
      const T = I().juntar(lista); if (!T.length) return;
      let tipo = "IFC"; try { tipo = api.GetNameFromTypeCode(api.GetLineType(id, eid)) || tipo; } catch (e) {}
      let nome = ""; try { const l = api.GetLine(id, eid); nome = l && l.Name && l.Name.value ? String(l.Name.value) : ""; } catch (e) {}
      porTipo[tipo] = (porTipo[tipo] || 0) + 1;
      objetos.push({ tipo: "malha", origem: "ifc", ifcId: eid, ifcTipo: tipo, nome: nome || tipo + " " + eid, pavimento: pav.get(eid) || "", T });
    });
    // elementos do modelo sem geometria de corpo que o web-ifc gere (por exemplo, só IfcBoundingBox): entram na árvore, sem malha
    let semGeo = 0;
    contidos.forEach(eid => { if (porEl.has(eid)) return;
      let tipo = "IFC"; try { tipo = api.GetNameFromTypeCode(api.GetLineType(id, eid)) || tipo; } catch (e) {}
      let nome = ""; try { const l = api.GetLine(id, eid); nome = l && l.Name && l.Name.value ? String(l.Name.value) : ""; } catch (e) {}
      porTipo[tipo] = (porTipo[tipo] || 0) + 1; semGeo++;
      objetos.push({ tipo: "info", origem: "ifc", ifcId: eid, ifcTipo: tipo, nome: nome || tipo + " " + eid, pavimento: pav.get(eid) || "", semGeometria: true }); });
    let esquema = "IFC"; try { esquema = api.GetModelSchema(id) || esquema; } catch (e) {}
    return { objetos, resumo: { esquema, elementos: objetos.length, com_geometria: objetos.length - semGeo, sem_geometria: semGeo, elementos_por_tipo: porTipo,
      pavimentos: pavs.map(n => ({ nome: n })), leitor: "web-ifc 0.0.66 no navegador" } };
  } finally { api.CloseModel(id); }
}

/* ════════ vista 3D (three.js), com girar e aproximar pelo mouse e pelo teclado ════════ */
function corCss(nome, padrao) { try { const v = getComputedStyle(document.documentElement).getPropertyValue(nome).trim(); return v || padrao; } catch (e) { return padrao; } }
function Vista(opcoes) {
  const T3 = window.THREE, cv = document.createElement("canvas");
  cv.tabIndex = 0; cv.className = "lab-vista"; cv.setAttribute("role", "img");
  const r = new T3.WebGLRenderer({ canvas: cv, antialias: true, preserveDrawingBuffer: true });
  const cena = new T3.Scene(), cam = new T3.PerspectiveCamera(40, 1, 1, 1e7), grupo = new T3.Group(), temp = new T3.Group();
  cam.up.set(0, 0, 1); cena.add(grupo); cena.add(temp);
  cena.add(new T3.HemisphereLight(0xffffff, 0x444444, 1.1)); const sol = new T3.DirectionalLight(0xffffff, 0.9); sol.position.set(1, -2, 3); cena.add(sol);
  const v = { cv, r, cena, cam, grupo, temp, alvo: new T3.Vector3(), dist: 200, teta: -Math.PI / 4, fi: Math.PI / 3.2, malhas: new Map(), grade: null, opcoes: opcoes || {} };
  v.posicionar = () => { const s = Math.sin(v.fi); cam.position.set(v.alvo.x + v.dist * s * Math.cos(v.teta), v.alvo.y + v.dist * s * Math.sin(v.teta), v.alvo.z + v.dist * Math.cos(v.fi)); cam.lookAt(v.alvo); };
  v.tamanho = () => { const w = Math.max(200, cv.parentElement ? cv.parentElement.clientWidth : 600), h = Math.round(Math.min(520, Math.max(240, w * 0.62)));
    r.setPixelRatio(Math.min(2, window.devicePixelRatio || 1)); r.setSize(w, h, true); cam.aspect = w / h; cam.updateProjectionMatrix(); };
  v.desenhar = () => { const f = corCss("--sup", "#FFFFFF"); try { r.setClearColor(new T3.Color(f)); } catch (e) {} v.posicionar(); r.render(cena, cam); };
  v.enquadrar = (cx) => { if (!cx) return; const c = [0, 1, 2].map(k => (cx.min[k] + cx.max[k]) / 2), d = Math.max(cx.max[0] - cx.min[0], cx.max[1] - cx.min[1], cx.max[2] - cx.min[2], 10);
    v.alvo.set(c[0], c[1], c[2]); v.dist = d * 2.2; cam.far = d * 200; cam.near = Math.max(0.05, d / 2000); cam.updateProjectionMatrix(); v.desenhar(); };
  v.malha = (id, T, cor, sel) => {
    let m = v.malhas.get(id);
    if (!m || m.userData.T !== T) {
      if (m) { grupo.remove(m); m.geometry.dispose(); }
      const g = new T3.BufferGeometry(); g.setAttribute("position", new T3.BufferAttribute(T, 3)); g.computeVertexNormals();
      m = new T3.Mesh(g, new T3.MeshLambertMaterial({ color: 0xffffff, side: T3.DoubleSide })); m.userData = { id, T }; v.malhas.set(id, m); grupo.add(m);
    }
    m.material.color.set(cor || "#D9D3C2"); m.material.emissive.set(sel ? corCss("--semente", "#F97316") : "#000000"); m.material.emissiveIntensity = sel ? 0.45 : 0;
    m.visible = true; return m;
  };
  v.limparMalhas = (manter) => { v.malhas.forEach((m, id) => { if (!manter.has(id)) { grupo.remove(m); m.geometry.dispose(); m.material.dispose(); v.malhas.delete(id); } }); };
  v.linhas = (lista) => { while (temp.children.length) { const c = temp.children.pop(); c.geometry && c.geometry.dispose(); }
    lista.forEach(l => { const g = new T3.BufferGeometry().setFromPoints(l.pts.map(p => new T3.Vector3(p[0], p[1], p[2] || 0.05)));
      temp.add(new (l.fechada ? T3.LineLoop : T3.Line)(g, new T3.LineBasicMaterial({ color: l.cor || corCss("--texto", "#1B1F23") }))); }); };
  v.gradeChao = (tam) => { if (v.grade) cena.remove(v.grade); const passo = Math.pow(10, Math.floor(Math.log10(Math.max(10, tam / 10))));
    const n = Math.max(2, Math.min(200, Math.ceil(tam / passo) * 2)); v.grade = new T3.GridHelper(n * passo, n, corCss("--borda-campo", "#8A9284"), corCss("--linha", "#D9D3C2"));
    v.grade.rotation.x = Math.PI / 2; cena.add(v.grade); v.passoGrade = passo; };
  /* raio do ponteiro: objeto tocado e ponto no chão (z = 0) */
  const ray = new T3.Raycaster(), ndc = new T3.Vector2();
  v.raio = (ev) => { const b = cv.getBoundingClientRect(); ndc.set(((ev.clientX - b.left) / b.width) * 2 - 1, -((ev.clientY - b.top) / b.height) * 2 + 1); ray.setFromCamera(ndc, cam);
    const hit = ray.intersectObjects(grupo.children.filter(m => m.visible), false)[0];
    const o = ray.ray.origin, d = ray.ray.direction, t = Math.abs(d.z) > 1e-9 ? -o.z / d.z : null, chao = t != null && t > 0 ? [o.x + t * d.x, o.y + t * d.y, 0] : null;
    return { id: hit ? hit.object.userData.id : null, ponto: hit ? [hit.point.x, hit.point.y, hit.point.z] : null, chao }; };
  v.orbitar = (dx, dy) => { v.teta -= dx * 0.01; v.fi = Math.max(0.05, Math.min(Math.PI - 0.05, v.fi - dy * 0.01)); v.desenhar(); };
  v.aproximar = (f) => { v.dist = Math.max(1, v.dist * f); v.desenhar(); };
  v.imagem = () => { v.desenhar(); try { return cv.toDataURL("image/png"); } catch (e) { return ""; } };
  window.addEventListener("resize", () => { if (cv.isConnected) { v.tamanho(); v.desenhar(); } });
  return v;
}

/* ════════ editor: objetos, ferramentas, histórico ════════ */
const FERRAMENTAS = ["selecionar", "mover", "girar", "escalar", "puxar", "linha", "retangulo", "circulo", "medir"];
let nId = 1;
function editor(opcoes) {
  opcoes = opcoes || {};
  const E = { objetos: [], sel: null, ferramenta: "selecionar", passo: 1, alturaNova: opcoes.alturaNova || 10, esboco: [], hist: [], futuro: [], vista: null,
    ferramentas: opcoes.ferramentas || FERRAMENTAS, aoMudar: opcoes.aoMudar || (() => {}), aoMedir: opcoes.aoMedir || (() => {}), mensagem: "" };
  const cores = I().CORES_PECA;
  const instante = () => E.objetos.map(o => Object.assign({}, o, { pos: o.pos.slice(), rot: o.rot.slice(), lacos: o.lacos ? o.lacos.map(l => l.map(p => p.slice())) : null }));
  E.guardar = () => { E.hist.push(instante()); if (E.hist.length > 60) E.hist.shift(); E.futuro = []; };
  E.desfazer = () => { if (!E.hist.length) return false; E.futuro.push(instante()); E.objetos = E.hist.pop(); if (!E.obj(E.sel)) E.sel = null; E.atualizar(); E.aoMudar("desfazer"); return true; };
  E.refazer = () => { if (!E.futuro.length) return false; E.hist.push(instante()); E.objetos = E.futuro.pop(); if (!E.obj(E.sel)) E.sel = null; E.atualizar(); E.aoMudar("refazer"); return true; };
  E.obj = id => E.objetos.find(o => o.id === id) || null;
  /* geometria local do objeto (antes da posição, do giro e da escala) */
  E.local = o => { if (o.tipo === "perfil") { if (!o._T || o._chave !== JSON.stringify([o.lacos, o.altura])) { o._T = I().extrudar(o.lacos, o.altura); o._chave = JSON.stringify([o.lacos, o.altura]); } return o._T; }
    return o.T || null; };
  E.pivo = o => { const T = E.local(o); if (!T) return [0, 0, 0]; const c = I().caixaDe(T); return [(c.min[0] + c.max[0]) / 2, (c.min[1] + c.max[1]) / 2, c.min[2]]; };
  E.mundo = o => { const T = E.local(o); if (!T) return null; if (!o._piv) o._piv = E.pivo(o); return I().transformar(T, o.pos, o.rot, o.esc, o._piv); };
  E.solidos = (ids) => E.objetos.filter(o => o.visivel !== false && (o.tipo === "perfil" || o.tipo === "malha") && (!ids || ids.indexOf(o.id) >= 0));
  E.conjunto = (ids) => I().juntar(E.solidos(ids).map(E.mundo).filter(Boolean));
  E.adicionar = (o, semHist) => { if (!semHist) E.guardar();
    const n = Object.assign({ id: "o" + (nId++), nome: "Objeto", tipo: "malha", pos: [0, 0, 0], rot: [0, 0, 0], esc: 1, cor: cores[E.objetos.length % cores.length][3], visivel: true }, o);
    E.objetos.push(n); E.sel = n.id; E.atualizar(); E.aoMudar("adicionar"); return n; };
  E.apagar = id => { const o = E.obj(id); if (!o) return; E.guardar(); E.objetos = E.objetos.filter(x => x.id !== id); if (E.sel === id) E.sel = null; E.atualizar(); E.aoMudar("apagar"); };
  E.alterar = (id, campos, semHist) => { const o = E.obj(id); if (!o) return; if (!semHist) E.guardar(); Object.assign(o, campos);
    if ("lacos" in campos || "altura" in campos) { o._piv = null; o._T = null; } E.atualizar(); E.aoMudar("alterar"); };
  E.selecionar = id => { E.sel = E.obj(id) ? id : null; E.atualizar(); E.aoMudar("selecionar"); };
  E.limpar = () => { E.guardar(); E.objetos = []; E.sel = null; E.esboco = []; E.atualizar(); E.aoMudar("limpar"); };
  E.caixa = () => { const T = E.conjunto(); return T.length ? I().caixaDe(T) : null; };
  /* vista: um canvas só, que muda de lugar quando a tela é redesenhada (nada se perde) */
  E.anexar = (alvo) => {
    if (!alvo || !window.THREE) return false;
    if (!E.vista) { E.vista = Vista(); ligarPonteiro(E); }
    alvo.appendChild(E.vista.cv); E.vista.tamanho(); E.atualizar(); if (!E._enq) { E._enq = true; E.enquadrar(); } return true;
  };
  E.enquadrar = () => { if (!E.vista) return; const c = E.caixa(); E.vista.gradeChao(c ? Math.max(c.max[0] - c.min[0], c.max[1] - c.min[1], 100) * 1.5 : 200);
    E.vista.enquadrar(c || { min: [-50, -50, 0], max: [50, 50, 20] }); };
  E.atualizar = () => { const v = E.vista; if (!v) return; const ids = new Set();
    E.objetos.forEach(o => { if (o.visivel === false || !(o.tipo === "perfil" || o.tipo === "malha")) return; const T = E.mundo(o); if (!T) return; ids.add(o.id); v.malha(o.id, T, o.cor, o.id === E.sel); });
    v.limparMalhas(ids);
    const ls = [];
    E.objetos.forEach(o => { if (o.visivel === false) return;
      if (o.tipo === "linha") ls.push({ pts: o.pts, fechada: false }); if (o.tipo === "cota") ls.push({ pts: o.pts, fechada: false, cor: corCss("--sobrancelha", "#C2410C") }); });
    if (E.esboco.length) ls.push({ pts: E.esboco.concat(E._cursor ? [E._cursor] : []), fechada: false, cor: corCss("--semente", "#F97316") });
    v.linhas(ls);
    v.cv.setAttribute("aria-label", (opcoes.rotulo || "Vista 3D") + ": " + E.objetos.length + " · " + (E.sel ? (E.obj(E.sel) || {}).nome : ""));
    v.desenhar(); };
  E.encaixar = p => p ? [Math.round(p[0] / E.passo) * E.passo, Math.round(p[1] / E.passo) * E.passo, 0] : null;
  /* teclado na vista: setas giram a câmera; com Shift, movem o selecionado (ferramenta mover); +, − e 0; Ctrl+Z/Y; Delete; Esc */
  E.tecla = (ev) => {
    const o = E.obj(E.sel), k = ev.key, passo = ev.altKey ? 10 * E.passo : E.passo;
    if ((ev.ctrlKey || ev.metaKey) && (k === "z" || k === "Z")) { ev.preventDefault(); if (ev.shiftKey) E.refazer(); else E.desfazer(); return; }
    if ((ev.ctrlKey || ev.metaKey) && (k === "y" || k === "Y")) { ev.preventDefault(); E.refazer(); return; }
    if (k === "Escape") { E.esboco = []; E._cursor = null; E.atualizar(); E.aoMudar("esc"); return; }
    if (k === "Enter" && E.esboco.length >= 2) { ev.preventDefault(); fecharLinha(E, false); return; }
    if ((k === "Delete" || k === "Backspace") && o) { ev.preventDefault(); E.apagar(o.id); return; }
    const d = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, 1], ArrowDown: [0, -1] }[k];
    if (d && ev.shiftKey && o) { ev.preventDefault();
      if (E.ferramenta === "girar") E.alterar(o.id, { rot: [o.rot[0], o.rot[1], o.rot[2] + d[0] * 15 + d[1] * 15] });
      else if (E.ferramenta === "escalar") E.alterar(o.id, { esc: Math.max(0.01, o.esc * (d[0] + d[1] > 0 ? 1.1 : 1 / 1.1)) });
      else if (E.ferramenta === "puxar" && o.tipo === "perfil") E.alterar(o.id, { altura: Math.max(E.passo, o.altura + (d[0] + d[1]) * passo) });
      else E.alterar(o.id, { pos: [o.pos[0] + d[0] * passo, o.pos[1] + d[1] * passo, o.pos[2]] });
      return; }
    if (d && E.vista) { ev.preventDefault(); E.vista.orbitar(-d[0] * 20, d[1] * 20); return; }
    if ((k === "+" || k === "=") && E.vista) { ev.preventDefault(); E.vista.aproximar(0.85); return; }
    if (k === "-" && E.vista) { ev.preventDefault(); E.vista.aproximar(1 / 0.85); return; }
    if (k === "0" && E.vista) { ev.preventDefault(); E.enquadrar(); return; }
  };
  E.dxfTexto = () => {   // contornos (no chão, já com posição, giro em z e escala), linhas e cotas
    const L = [];
    E.objetos.filter(o => o.visivel !== false).forEach(o => {
      if (o.tipo === "perfil") { if (!o._piv) o._piv = E.pivo(o);
        o.lacos.forEach(l => { const T = new Float32Array(l.length * 3); l.forEach((p, i) => { T[3 * i] = p[0]; T[3 * i + 1] = p[1]; });
          const W = I().transformar(T, o.pos, [0, 0, o.rot[2]], o.esc, o._piv), pts = []; for (let i = 0; i < W.length; i += 3) pts.push([W[i], W[i + 1]]); L.push({ pts, fechada: true }); }); }
      if (o.tipo === "linha" || o.tipo === "cota") L.push({ pts: o.pts.map(p => [p[0], p[1]]), fechada: false, cota: o.tipo === "cota" ? o.medida : null });
    });
    const out = ["0", "SECTION", "2", "HEADER", "9", "$ACADVER", "1", "AC1009", "9", "$INSUNITS", "70", "4", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"], n = x => (Math.round(x * 1e4) / 1e4).toString();
    L.forEach(l => { out.push("0", "POLYLINE", "8", l.cota != null ? "COTAS" : "CONTORNO", "66", "1", "70", l.fechada ? "1" : "0");
      l.pts.forEach(p => out.push("0", "VERTEX", "8", l.cota != null ? "COTAS" : "CONTORNO", "10", n(p[0]), "20", n(p[1]), "30", "0")); out.push("0", "SEQEND");
      if (l.cota != null) { const a = l.pts[0], b = l.pts[l.pts.length - 1]; out.push("0", "TEXT", "8", "COTAS", "10", n((a[0] + b[0]) / 2), "20", n((a[1] + b[1]) / 2), "30", "0", "40", n(Math.max(1, l.cota / 20)), "1", n(l.cota) + " mm"); } });
    out.push("0", "ENDSEC", "0", "EOF"); return out.join("\r\n") + "\r\n"; };
  E.svgTexto = () => {   // vista de cima, em mm
    const T = E.conjunto(), c = T.length ? I().caixaDe(T) : { min: [0, 0, 0], max: [100, 100, 0] }, w = c.max[0] - c.min[0] || 1, h = c.max[1] - c.min[1] || 1, cam = [];
    E.objetos.filter(o => o.visivel !== false && o.tipo === "perfil").forEach(o => { if (!o._piv) o._piv = E.pivo(o);
      const partes = o.lacos.map(l => { const t = new Float32Array(l.length * 3); l.forEach((p, i) => { t[3 * i] = p[0]; t[3 * i + 1] = p[1]; });
        const W = I().transformar(t, o.pos, [0, 0, o.rot[2]], o.esc, o._piv), pts = []; for (let i = 0; i < W.length; i += 3) pts.push((W[i] - c.min[0]).toFixed(3) + " " + (c.max[1] - W[i + 1]).toFixed(3)); return "M" + pts.join(" L") + " Z"; });
      cam.push(`<path d="${partes.join(" ")}" fill="none" stroke="#1B1F23" stroke-width="${(w / 400).toFixed(3)}" fill-rule="evenodd"/>`); });
    E.objetos.filter(o => o.visivel !== false && (o.tipo === "linha" || o.tipo === "cota")).forEach(o =>
      cam.push(`<polyline points="${o.pts.map(p => (p[0] - c.min[0]).toFixed(3) + "," + (c.max[1] - p[1]).toFixed(3)).join(" ")}" fill="none" stroke="${o.tipo === "cota" ? "#C2410C" : "#1B1F23"}" stroke-width="${(w / 400).toFixed(3)}"/>`));
    return `<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" width="${w.toFixed(3)}mm" height="${h.toFixed(3)}mm" viewBox="0 0 ${w.toFixed(3)} ${h.toFixed(3)}">${cam.join("")}</svg>\n`; };
  /* JSON do projeto: o que dá para refazer (formas, linhas, cotas, posições); malhas do IFC e de arquivo ficam de fora */
  E.json = () => E.objetos.map(o => { const b = { nome: o.nome, tipo: o.tipo, origem: o.origem || "", pos: o.pos, rot: o.rot, esc: o.esc, cor: o.cor, visivel: o.visivel !== false };
    if (o.tipo === "perfil") Object.assign(b, { lacos: o.lacos, altura: o.altura, forma: o.forma || null });
    if (o.tipo === "linha" || o.tipo === "cota") Object.assign(b, { pts: o.pts, medida: o.medida });
    if (o.tipo === "malha") Object.assign(b, { ifcTipo: o.ifcTipo || "", ifcId: o.ifcId || null, pavimento: o.pavimento || "", sem_geometria_no_json: true });
    return b; });
  E.deJson = (lista) => { (lista || []).forEach(b => { if (!b || typeof b !== "object") return;
    if (b.tipo === "perfil" && Array.isArray(b.lacos)) E.adicionar({ nome: String(b.nome || "Forma"), tipo: "perfil", lacos: b.lacos, altura: +b.altura || E.alturaNova, forma: b.forma || null,
      pos: (b.pos || [0, 0, 0]).slice(0, 3), rot: (b.rot || [0, 0, 0]).slice(0, 3), esc: +b.esc || 1, cor: b.cor, origem: b.origem || "" }, true);
    if ((b.tipo === "linha" || b.tipo === "cota") && Array.isArray(b.pts)) E.adicionar({ nome: String(b.nome || b.tipo), tipo: b.tipo, pts: b.pts, medida: b.medida }, true); }); E.sel = null; E.atualizar(); };
  return E;
}
function fecharLinha(E, fechada) {
  const pts = E.esboco.filter((p, i, l) => !i || Math.hypot(p[0] - l[i - 1][0], p[1] - l[i - 1][1]) > 1e-9); E.esboco = []; E._cursor = null;
  if (fechada && pts.length >= 3) E.adicionar({ nome: "Forma desenhada", tipo: "perfil", forma: { tipo: "linha" }, lacos: [pts.map(p => [p[0], p[1]])], altura: E.alturaNova, origem: "desenho" });
  else if (pts.length >= 2) E.adicionar({ nome: "Linha", tipo: "linha", pts: pts.map(p => [p[0], p[1], 0]), origem: "desenho" });
  else { E.atualizar(); E.aoMudar("esboco"); }
}
function ligarPonteiro(E) {
  const cv = E.vista.cv; let arr = null;
  cv.addEventListener("contextmenu", ev => ev.preventDefault());
  cv.addEventListener("wheel", ev => { ev.preventDefault(); E.vista.aproximar(ev.deltaY > 0 ? 1.12 : 1 / 1.12); }, { passive: false });
  cv.addEventListener("keydown", ev => E.tecla(ev));
  cv.addEventListener("pointerdown", ev => {
    cv.focus(); const R = E.vista.raio(ev), f = E.ferramenta, o = E.obj(R.id) || null, ch = E.encaixar(R.chao);
    arr = { x: ev.clientX, y: ev.clientY, orbita: ev.button === 2 || ev.button === 1, f, alvo: null, ch0: ch, moveu: false };
    if (arr.orbita) return;
    if (["linha", "retangulo", "circulo", "medir"].indexOf(f) >= 0) {
      if (!ch) return;
      E.esboco.push(ch);
      if (f === "linha" && E.esboco.length >= 3 && Math.hypot(ch[0] - E.esboco[0][0], ch[1] - E.esboco[0][1]) <= Math.max(E.passo * 1.5, E.vista.dist / 150)) { E.esboco.pop(); fecharLinha(E, true); }
      else if (f === "retangulo" && E.esboco.length === 2) { const [a, b] = E.esboco; E.esboco = []; const w = Math.abs(b[0] - a[0]), d = Math.abs(b[1] - a[1]);
        if (w > 0 && d > 0) E.adicionar({ nome: "Retângulo " + w + " × " + d, tipo: "perfil", forma: { tipo: "retangulo", w, d }, lacos: [[[Math.min(a[0], b[0]), Math.min(a[1], b[1])], [Math.max(a[0], b[0]), Math.min(a[1], b[1])], [Math.max(a[0], b[0]), Math.max(a[1], b[1])], [Math.min(a[0], b[0]), Math.max(a[1], b[1])]]], altura: E.alturaNova, origem: "desenho" }); }
      else if (f === "circulo" && E.esboco.length === 2) { const [a, b] = E.esboco; E.esboco = []; const rr = Math.hypot(b[0] - a[0], b[1] - a[1]);
        if (rr > 0) E.adicionar({ nome: "Círculo Ø" + (Math.round(2 * rr * 100) / 100), tipo: "perfil", forma: { tipo: "circulo", d: 2 * rr }, lacos: [I().PRIM.circulo(2 * rr, 48)[0].map(p => [p[0] + a[0], p[1] + a[1]])], altura: E.alturaNova, origem: "desenho" }); }
      else if (f === "medir" && E.esboco.length === 2) { const [a, b] = E.esboco; E.esboco = []; const m = Math.round(Math.hypot(b[0] - a[0], b[1] - a[1]) * 1000) / 1000;
        E.aoMedir(m); E.adicionar({ nome: "Cota " + m + " mm", tipo: "cota", pts: [a, b], medida: m, origem: "medida" }); }
      else { E.atualizar(); E.aoMudar("esboco"); }
      return;
    }
    if (o) { if (E.sel !== o.id) E.selecionar(o.id); if (f !== "selecionar") { E.guardar(); arr.alvo = o; arr.inicio = { pos: o.pos.slice(), rot: o.rot.slice(), esc: o.esc, altura: o.altura }; } }
    else if (f === "selecionar" && E.sel) { arr.limparSel = true; }
    if (!arr.alvo) arr.orbita = true;
    cv.setPointerCapture && cv.setPointerCapture(ev.pointerId);
  });
  cv.addEventListener("pointermove", ev => {
    if (!arr) { if (E.esboco.length) { const R = E.vista.raio(ev); E._cursor = E.encaixar(R.chao); E.atualizar(); } return; }
    const dx = ev.clientX - arr.x, dy = ev.clientY - arr.y; if (Math.abs(dx) + Math.abs(dy) > 3) arr.moveu = true;
    if (arr.orbita) { E.vista.orbitar(ev.movementX || 0, ev.movementY || 0); return; }
    const o = arr.alvo, i = arr.inicio; if (!o) return;
    if (arr.f === "mover") { const ch = E.encaixar(E.vista.raio(ev).chao); if (ch && arr.ch0) { o.pos = [i.pos[0] + ch[0] - arr.ch0[0], i.pos[1] + ch[1] - arr.ch0[1], i.pos[2]]; } }
    else if (arr.f === "girar") o.rot = [i.rot[0], i.rot[1], Math.round(i.rot[2] + dx * 0.5)];
    else if (arr.f === "escalar") o.esc = Math.max(0.01, Math.round(i.esc * Math.exp(-dy * 0.01) * 1000) / 1000);
    else if (arr.f === "puxar" && o.tipo === "perfil") { o.altura = Math.max(E.passo, Math.round((i.altura - dy * E.vista.dist / 600) / E.passo) * E.passo); o._T = null; o._piv = null; }
    E.atualizar();
  });
  cv.addEventListener("pointerup", ev => {
    const a = arr; arr = null; if (!a) return;
    if (a.alvo) { if (!a.moveu) E.hist.pop(); E.atualizar(); E.aoMudar(a.f); }
    else if (a.limparSel && !a.moveu) E.selecionar(null);
  });
  cv.addEventListener("dblclick", ev => { if (E.ferramenta === "linha" && E.esboco.length >= 2) { ev.preventDefault(); fecharLinha(E, false); } });
}

window.PhysisModelagem = { carregar, lerIfc, editor, Vista, FERRAMENTAS, versao: "physis-modelagem-0.1" };
})();
