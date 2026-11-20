/* physis-3d.js — aba Physis 3D da plataforma: peças para impressão 3D com plástico reciclado. EM DESENVOLVIMENTO.
   Contrato com a plataforma: define telaPhysis3D() (HTML da aba inteira, com um único título h1),
   window.PHYSIS3D = { contas puras, testáveis } e window.PHYSIS3D_I18N (português → inglês, para juntar ao I18N)
   com window.PHYSIS3D_I18N_RX (frases com números).
   Módulo EM DESENVOLVIMENTO: a tela mostra o selo "Em desenvolvimento" até a plataforma marcar window.PHYSIS3D_PRONTO = true.
   Espelho de physis-hub/physis_hub/impressao3d.py: leitura de STL/OBJ/3MF, medidas, fatiamento plano e estimativas
   (mesmas fórmulas; teste em tests/test_impressao3d.py e no navegador em ferramentas/testes-navegador/teste-physis-3d.html).
   Visualizador em WebGL escrito à mão (sem biblioteca de terceiros, sem internet). 3MF: ZIP lido com um descompactador
   (inflate) próprio e escrito sem compressão. Os endereços "http://schemas..." abaixo são NOMES do formato 3MF/OPC
   (namespaces XML exigidos pela norma), não são acessados.
   Perfis de material: premissas "conferir" de sistema/physis-3d-premissas.json, embutidas como
   <script type="application/json" id="base-3d-premissas"> (ou em window.PhysisCalc.PREMISSAS, quando a proposta entrar em physis-premissas.json).
   Servidor (modo hub): GET/POST api/3d/... (biblioteca, memorial, fórum, avisos aprendidos e fatiador em contêiner).
   Globais usadas se existirem: esc, n2, el, ui, desenhar. Estado leve em localStorage "physis-3d"; a malha fica na memória. */
(function () {
"use strict";
const CHAVE = "physis-3d";
const NS_3MF = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02";
const NS_CT = "http://schemas.openxmlformats.org/package/2006/content-types", NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships";
const REL_3D = "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel";
const UNIDADES_3MF = { micron:0.001, millimeter:1, centimeter:10, inch:25.4, foot:304.8, meter:1000 };
const MM_POR_POL = 25.4, TRIANGULOS_MAX = 3000000, DESCOMPACTADO_MAX = 200 * 1024 * 1024;
const CONFIG_PADRAO = { altura_camada:0.2, largura_linha:0.45, paredes:2, preenchimento:0.2, camadas_topo:4, camadas_fundo:4,
  vel_parede:40, vel_preench:60, fator_deslocamento:1.15, troca_camada_s:2, diametro_filamento:1.75, bico_c:null, mesa_c:null, bico_mm:0.4 };
/* cópia de reserva das premissas (as mesmas de sistema/physis-3d-premissas.json; o teste confere) — todas "conferir" */
const MATERIAIS_RESERVA = {
  rpetg: { nome:"rPET / PETG reciclado", densidade_g_cm3:1.27, bico_c:240, bico_faixa_c:[230, 250], mesa_c:75, mesa_faixa_c:[70, 85], contracao_pct:0.4, contracao_faixa_pct:[0.2, 0.6], diametro_mm:1.75 },
  rpp: { nome:"rPP (polipropileno reciclado)", densidade_g_cm3:0.9, bico_c:230, bico_faixa_c:[210, 250], mesa_c:90, mesa_faixa_c:[80, 100], contracao_pct:1.8, contracao_faixa_pct:[1.0, 2.5], diametro_mm:1.75 },
  rhdpe: { nome:"rHDPE (PEAD reciclado)", densidade_g_cm3:0.95, bico_c:240, bico_faixa_c:[220, 260], mesa_c:100, mesa_faixa_c:[90, 110], contracao_pct:2.5, contracao_faixa_pct:[1.5, 4.0], diametro_mm:1.75 },
  rabs: { nome:"rABS (ABS reciclado)", densidade_g_cm3:1.04, bico_c:240, bico_faixa_c:[230, 255], mesa_c:100, mesa_faixa_c:[95, 110], contracao_pct:0.6, contracao_faixa_pct:[0.4, 0.8], diametro_mm:1.75 },
  rpla: { nome:"PLA reciclado", densidade_g_cm3:1.24, bico_c:205, bico_faixa_c:[190, 220], mesa_c:60, mesa_faixa_c:[50, 65], contracao_pct:0.3, contracao_faixa_pct:[0.2, 0.5], diametro_mm:1.75 } };
const CORES_MATERIAL = { rpetg:"#8FB183", rpp:"#D9D3C2", rhdpe:"#E9E6DB", rabs:"#4A5A47", rpla:"#7FA874" };
const LICENCAS = { "CC-BY-4.0":"Creative Commons Atribuição 4.0", "CC-BY-SA-4.0":"Creative Commons Atribuição-CompartilhaIgual 4.0", "CC0-1.0":"Creative Commons Zero 1.0 (domínio público)",
  "CERN-OHL-S-2.0":"CERN Open Hardware Licence 2.0, fortemente recíproca", "CERN-OHL-W-2.0":"CERN Open Hardware Licence 2.0, fracamente recíproca", "CERN-OHL-P-2.0":"CERN Open Hardware Licence 2.0, permissiva" };
const PROBLEMAS = { empenamento:"Empenamento (warping)", adesao:"Pouca adesão à mesa", fios:"Fios (stringing)", delaminacao:"Separação de camadas", subextrusao:"Subextrusão",
  sobreextrusao:"Sobre-extrusão", balanco:"Balanço ou ponte caiu", dimensional:"Medida fora (contração)", entupimento:"Bico entupido", bolhas:"Bolhas ou umidade no filamento", outro:"Outro problema" };
const RESULTADOS = { ok:"Deu certo", parcial:"Serviu com defeito", falha:"Falhou" };

/* ════════ utilidades (com reserva quando a plataforma não as tem) ════════ */
const E = s => typeof esc === "function" ? esc(s) : String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));
const N = (v, c) => v == null || !isFinite(v) ? "—" : (typeof n2 === "function" ? n2(v, c) : Number(v).toLocaleString("pt-BR", { minimumFractionDigits:c, maximumFractionDigits:c }));
const U = () => (typeof ui !== "undefined" && ui) ? ui : (window.__p3dUi = window.__p3dUi || {});
const pega = id => typeof el === "function" ? el(id) : document.getElementById(id);
const redesenhar = () => { if (typeof desenhar === "function") desenhar(false); else if (typeof window.__p3dDesenhar === "function") window.__p3dDesenhar(); };
function num(v){ if (v == null) return null; if (typeof v === "number") return isFinite(v) ? v : null; let s = String(v).trim().replace(/\s/g, ""); if (!s) return null;
  if (s.indexOf(",") >= 0) s = s.replace(/\./g, "").replace(",", "."); const x = Number(s); return isFinite(x) ? x : null; }
function tx(s){ try { if (!/^en/i.test(document.documentElement.lang || "")) return s; const D = window.PHYSIS3D_I18N || {}, k = String(s).replace(/\s+/g, " ").trim(); if (Object.prototype.hasOwnProperty.call(D, k)) return D[k];
  for (const [a, r] of (window.PHYSIS3D_I18N_RX || [])){ const m = k.match(new RegExp(a)); if (m) return r.replace(/\$(\d)/g, (_, i) => m[+i] == null ? "" : m[+i]); } } catch (e){} return s; }
const emHub = () => { const u = U(); return u.modo === "hub" || (typeof location !== "undefined" && /^https?:$/.test(location.protocol) && !u.modo); };
function lerPref(){ let o = null; try { o = JSON.parse(localStorage.getItem(CHAVE) || "null"); } catch (e){} o = o && typeof o === "object" ? o : {};
  o.cfg = Object.assign({}, o.cfg || {}); return o; }
function gravarPref(o){ try { localStorage.setItem(CHAVE, JSON.stringify(o)); } catch (e){} }

/* ════════ perfis de material (premissas "conferir") ════════ */
function materiais(){ const out = {};
  const somar = base => { (base && Array.isArray(base.premissas) ? base.premissas : []).forEach(p => { if (p && /^impressao3d\.material\./.test(p.id) && p.valor_padrao){ const k = p.id.split(".").pop(); if (!out[k]) out[k] = Object.assign({}, p.valor_padrao, { id:p.id, status:p.status || "", fonte:p.fonte || "" }); } }); };
  somar((window.PhysisCalc || {}).PREMISSAS);       /* quando a proposta entrar em physis-premissas.json (vem por physis-calc-comum.js) */
  try { const s = typeof document !== "undefined" && document.getElementById("base-3d-premissas"); if (s) somar(JSON.parse(s.textContent)); } catch (e){}
  somar(window.PHYSIS_3D_PREMISSAS);
  Object.keys(MATERIAIS_RESERVA).forEach(k => { if (!out[k]) out[k] = Object.assign({}, MATERIAIS_RESERVA[k], { id:"impressao3d.material." + k, status:"conferir", fonte:"[CONFERIR] cópia de reserva da tela (sistema/physis-3d-premissas.json)" }); });
  return out; }

/* ════════ leitura de malhas: tudo vira Float32Array com 9 números por triângulo (mm) ════════ */
function lerSTL(buf){ const dv = new DataView(buf);
  if (buf.byteLength >= 84){ const n = dv.getUint32(80, true);
    if (buf.byteLength === 84 + 50 * n){ if (n > TRIANGULOS_MAX) throw new Error("malha grande demais"); const T = new Float32Array(9 * n);
      for (let i = 0; i < n; i++){ const o = 84 + 50 * i + 12; for (let k = 0; k < 9; k++) T[9 * i + k] = dv.getFloat32(o + 4 * k, true); } return T; } }
  const txt = new TextDecoder("utf-8").decode(new Uint8Array(buf));
  if (!/^\s*solid/.test(txt) || txt.indexOf("facet") < 0) throw new Error("STL não reconhecido");
  const vs = []; const rx = /vertex\s+(\S+)\s+(\S+)\s+(\S+)/g; let m;
  while ((m = rx.exec(txt))){ const a = +m[1], b = +m[2], c = +m[3]; if (!isFinite(a) || !isFinite(b) || !isFinite(c)) throw new Error("número inválido no STL"); vs.push(a, b, c); }
  if (!vs.length || vs.length % 9) throw new Error("STL de texto incompleto"); return new Float32Array(vs); }
function lerOBJ(txt){ const v = [], out = [];
  String(txt).split(/\r?\n/).forEach(l => { const p = l.trim().split(/\s+/); if (p[0] === "v" && p.length >= 4) v.push([+p[1], +p[2], +p[3]]);
    else if (p[0] === "f" && p.length >= 4){ const idx = p.slice(1).map(t => { const k = parseInt(t.split("/")[0], 10); return k > 0 ? k - 1 : v.length + k; });
      for (let j = 1; j < idx.length - 1; j++) [idx[0], idx[j], idx[j + 1]].forEach(i => { const q = v[i]; if (!q) throw new Error("OBJ com índice fora"); out.push(q[0], q[1], q[2]); }); } });
  if (!out.length) throw new Error("OBJ sem faces"); return new Float32Array(out); }

/* inflate (RFC 1951), escrito à mão: blocos guardados, Huffman fixo e dinâmico */
const LBASE = [3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227,258], LEXT = [0,0,0,0,0,0,0,0,1,1,1,1,2,2,2,2,3,3,3,3,4,4,4,4,5,5,5,5,0];
const DBASE = [1,2,3,4,5,7,9,13,17,25,33,49,65,97,129,193,257,385,513,769,1025,1537,2049,3073,4097,6145,8193,12289,16385,24577], DEXT = [0,0,0,0,1,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9,10,10,11,11,12,12,13,13];
const ORDEM_CL = [16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15];
function inflar(d, tamanho){ let pos = 0, bit = 0, n = 0, out = new Uint8Array(Math.max(1024, tamanho || d.length * 4));
  const ler = k => { let v = 0; for (let i = 0; i < k; i++){ if (pos >= d.length) throw new Error("deflate truncado"); v |= ((d[pos] >> bit) & 1) << i; if (++bit === 8){ bit = 0; pos++; } } return v; };
  const caber = k => { if (n + k <= out.length) return; let m = out.length * 2; while (m < n + k) m *= 2; if (m > DESCOMPACTADO_MAX * 2) throw new Error("arquivo grande demais"); const o = new Uint8Array(m); o.set(out.subarray(0, n)); out = o; };
  const tabela = comps => { const cont = new Uint16Array(16), offs = new Uint16Array(16), simb = new Uint16Array(comps.length); comps.forEach(c => cont[c]++); cont[0] = 0;
    for (let i = 1; i < 16; i++) offs[i] = offs[i - 1] + cont[i - 1]; comps.forEach((c, s) => { if (c) simb[offs[c]++] = s; }); return { cont, simb }; };
  const decod = t => { let cod = 0, prim = 0, ind = 0; for (let len = 1; len < 16; len++){ cod |= ler(1); const c = t.cont[len]; if (cod - c < prim) return t.simb[ind + cod - prim]; ind += c; prim += c; prim <<= 1; cod <<= 1; } throw new Error("código Huffman inválido"); };
  let fixaL = null, fixaD = null, fim = 0;
  while (!fim){ fim = ler(1); const tipo = ler(2);
    if (tipo === 0){ if (bit){ bit = 0; pos++; } const len = d[pos] | (d[pos + 1] << 8); pos += 4; if (pos + len > d.length) throw new Error("deflate truncado"); caber(len); out.set(d.subarray(pos, pos + len), n); n += len; pos += len; continue; }
    let tl, td;
    if (tipo === 1){ if (!fixaL){ const c = []; for (let i = 0; i < 288; i++) c.push(i < 144 ? 8 : i < 256 ? 9 : i < 280 ? 7 : 8); fixaL = tabela(c); fixaD = tabela(new Array(30).fill(5)); } tl = fixaL; td = fixaD; }
    else if (tipo === 2){ const hl = ler(5) + 257, hd = ler(5) + 1, hc = ler(4) + 4, cl = new Array(19).fill(0); for (let i = 0; i < hc; i++) cl[ORDEM_CL[i]] = ler(3);
      const tc = tabela(cl), comps = []; while (comps.length < hl + hd){ const s = decod(tc);
        if (s < 16) comps.push(s); else if (s === 16){ if (!comps.length) throw new Error("deflate inválido"); const p = comps[comps.length - 1]; for (let r = 3 + ler(2); r > 0; r--) comps.push(p); }
        else if (s === 17){ for (let r = 3 + ler(3); r > 0; r--) comps.push(0); } else { for (let r = 11 + ler(7); r > 0; r--) comps.push(0); } }
      tl = tabela(comps.slice(0, hl)); td = tabela(comps.slice(hl, hl + hd)); }
    else throw new Error("bloco deflate inválido");
    for (;;){ const s = decod(tl); if (s < 256){ caber(1); out[n++] = s; continue; } if (s === 256) break;
      const li = s - 257; if (li >= 29) throw new Error("deflate inválido"); const len = LBASE[li] + ler(LEXT[li]); const di = decod(td); if (di >= 30) throw new Error("deflate inválido");
      const dist = DBASE[di] + ler(DEXT[di]); if (dist > n) throw new Error("distância inválida"); caber(len); for (let i = 0; i < len; i++, n++) out[n] = out[n - dist]; } }
  return out.subarray(0, n); }

/* ZIP: leitura (guardado ou deflate) e escrita (só guardado, com CRC-32) */
function lerZip(buf){ const b = new Uint8Array(buf), dv = new DataView(buf); let e = -1;
  for (let i = b.length - 22; i >= Math.max(0, b.length - 65557); i--) if (dv.getUint32(i, true) === 0x06054b50){ e = i; break; }
  if (e < 0) throw new Error("3MF não é um ZIP"); const qtd = dv.getUint16(e + 10, true); let p = dv.getUint32(e + 16, true); const out = {};
  for (let k = 0; k < qtd; k++){ if (dv.getUint32(p, true) !== 0x02014b50) throw new Error("ZIP corrompido");
    const metodo = dv.getUint16(p + 10, true), comp = dv.getUint32(p + 20, true), tam = dv.getUint32(p + 24, true), nl = dv.getUint16(p + 28, true), xl = dv.getUint16(p + 30, true), cl = dv.getUint16(p + 32, true), loc = dv.getUint32(p + 42, true);
    const nome = new TextDecoder("utf-8").decode(b.subarray(p + 46, p + 46 + nl)); p += 46 + nl + xl + cl;
    out[nome] = { metodo, comp, tam, ini: loc + 30 + dv.getUint16(loc + 26, true) + dv.getUint16(loc + 28, true) }; }
  return { nomes: Object.keys(out), ler: nome => { const x = out[nome]; if (!x) return null; if (x.tam > DESCOMPACTADO_MAX) throw new Error("3MF grande demais"); const dados = b.subarray(x.ini, x.ini + x.comp);
    if (x.metodo === 0) return dados; if (x.metodo === 8) return inflar(dados, x.tam); throw new Error("compressão do ZIP não suportada"); } }; }
const CRC = (() => { const t = new Uint32Array(256); for (let i = 0; i < 256; i++){ let c = i; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[i] = c >>> 0; } return t; })();
function crc32(b){ let c = 0xFFFFFFFF; for (let i = 0; i < b.length; i++) c = CRC[(c ^ b[i]) & 255] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; }
function escreverZip(arqs){ const enc = new TextEncoder(), partes = [], centrais = []; let off = 0;
  arqs.forEach(([nome, dados]) => { const nb = enc.encode(nome), d = typeof dados === "string" ? enc.encode(dados) : dados, crc = crc32(d);
    const h = new DataView(new ArrayBuffer(30)); h.setUint32(0, 0x04034b50, true); h.setUint16(4, 20, true); h.setUint32(14, crc, true); h.setUint32(18, d.length, true); h.setUint32(22, d.length, true); h.setUint16(26, nb.length, true);
    const c = new DataView(new ArrayBuffer(46)); c.setUint32(0, 0x02014b50, true); c.setUint16(4, 20, true); c.setUint16(6, 20, true); c.setUint32(16, crc, true); c.setUint32(20, d.length, true); c.setUint32(24, d.length, true); c.setUint16(28, nb.length, true); c.setUint32(42, off, true);
    partes.push(new Uint8Array(h.buffer), nb, d); centrais.push(new Uint8Array(c.buffer), nb); off += 30 + nb.length + d.length; });
  const tamC = centrais.reduce((s, x) => s + x.length, 0), f = new DataView(new ArrayBuffer(22)); f.setUint32(0, 0x06054b50, true); f.setUint16(8, arqs.length, true); f.setUint16(10, arqs.length, true); f.setUint32(12, tamC, true); f.setUint32(16, off, true);
  return new Blob(partes.concat(centrais, [new Uint8Array(f.buffer)]), { type:"model/3mf" }); }

function matriz3mf(t){ if (!t) return null; const m = t.trim().split(/\s+/).map(Number); return m.length === 12 && m.every(isFinite) ? m : null; }
function aplicar(m, x, y, z){ return m ? [m[0] * x + m[3] * y + m[6] * z + m[9], m[1] * x + m[4] * y + m[7] * z + m[10], m[2] * x + m[5] * y + m[8] * z + m[11]] : [x, y, z]; }
function compor(a, b){ if (!a) return b; if (!b) return a; const M = m => [[m[0], m[3], m[6], m[9]], [m[1], m[4], m[7], m[10]], [m[2], m[5], m[8], m[11]], [0, 0, 0, 1]], A = M(a), B = M(b), C = [];
  for (let i = 0; i < 4; i++){ C.push([]); for (let j = 0; j < 4; j++){ let s = 0; for (let k = 0; k < 4; k++) s += A[i][k] * B[k][j]; C[i].push(s); } }
  return [C[0][0], C[1][0], C[2][0], C[0][1], C[1][1], C[2][1], C[0][2], C[1][2], C[2][2], C[0][3], C[1][3], C[2][3]]; }
function ler3MF(buf){ const z = lerZip(buf), modelo = z.nomes.find(n => n.toLowerCase() === "3d/3dmodel.model") || z.nomes.find(n => /\.model$/i.test(n));
  if (!modelo) throw new Error("3MF sem modelo"); const xml = new TextDecoder("utf-8").decode(z.ler(modelo)); if (/<!DOCTYPE/i.test(xml.slice(0, 2048))) throw new Error("3MF recusado");
  const doc = new DOMParser().parseFromString(xml, "application/xml"); if (doc.getElementsByTagName("parsererror").length) throw new Error("XML do 3MF inválido");
  const raiz = doc.documentElement, escala = UNIDADES_3MF[raiz.getAttribute("unit") || "millimeter"] || 1, objetos = {};
  const filhos = (e, nome) => Array.from(e.getElementsByTagNameNS(NS_3MF, nome));
  filhos(raiz, "object").forEach(o => { const ma = filhos(o, "mesh")[0], co = filhos(o, "components")[0];
    if (ma){ const vs = filhos(ma, "vertex").map(v => [+v.getAttribute("x"), +v.getAttribute("y"), +v.getAttribute("z")]); objetos[o.getAttribute("id")] = { vs, ts: filhos(ma, "triangle").map(t => [+t.getAttribute("v1"), +t.getAttribute("v2"), +t.getAttribute("v3")]) }; }
    else if (co) objetos[o.getAttribute("id")] = { comps: filhos(co, "component").map(c => [c.getAttribute("objectid"), matriz3mf(c.getAttribute("transform"))]) }; });
  const out = [];
  const emitir = (id, m, prof) => { const o = objetos[id]; if (!o || prof > 16) return; if (o.comps){ o.comps.forEach(([c, cm]) => emitir(c, compor(m, cm), prof + 1)); return; }
    o.ts.forEach(t => t.forEach(i => { const v = o.vs[i]; if (!v) throw new Error("3MF com índice fora"); const p = aplicar(m, v[0], v[1], v[2]); out.push(p[0] * escala, p[1] * escala, p[2] * escala); })); if (out.length > 9 * TRIANGULOS_MAX) throw new Error("malha grande demais"); };
  const itens = filhos(raiz, "item"); if (itens.length) itens.forEach(it => emitir(it.getAttribute("objectid"), matriz3mf(it.getAttribute("transform")), 0)); else Object.keys(objetos).forEach(k => emitir(k, null, 0));
  if (!out.length) throw new Error("3MF sem triângulos"); return new Float32Array(out); }
function formatoDe(nome){ const ext = String(nome || "").split(".").pop().toLowerCase(); if (["stl", "obj", "3mf"].indexOf(ext) < 0) throw new Error("formato aceito: STL, OBJ ou 3MF"); return ext; }
function lerMalha(buf, nome){ const f = formatoDe(nome); return f === "stl" ? lerSTL(buf) : f === "obj" ? lerOBJ(new TextDecoder("utf-8").decode(new Uint8Array(buf))) : ler3MF(buf); }

/* ════════ escrita ════════ */
function normal(T, i){ const ax = T[i + 3] - T[i], ay = T[i + 4] - T[i + 1], az = T[i + 5] - T[i + 2], bx = T[i + 6] - T[i], by = T[i + 7] - T[i + 1], bz = T[i + 8] - T[i + 2];
  return [ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx]; }
function escreverSTL(T, nome){ const n = T.length / 9, b = new ArrayBuffer(84 + 50 * n), dv = new DataView(b), cab = String(nome || "physis3d").slice(0, 80);
  for (let i = 0; i < cab.length; i++) dv.setUint8(i, cab.charCodeAt(i) & 127); dv.setUint32(80, n, true);
  for (let t = 0; t < n; t++){ const o = 84 + 50 * t, nn = normal(T, 9 * t), m = Math.hypot(nn[0], nn[1], nn[2]) || 1; for (let k = 0; k < 3; k++) dv.setFloat32(o + 4 * k, nn[k] / m, true); for (let k = 0; k < 9; k++) dv.setFloat32(o + 12 + 4 * k, T[9 * t + k], true); }
  return b; }
function escrever3MF(T){ const vs = [], idx = new Map(), ts = []; const chave = i => T[i].toFixed(5) + "," + T[i + 1].toFixed(5) + "," + T[i + 2].toFixed(5);
  for (let i = 0; i < T.length; i += 9){ const t = []; for (let k = 0; k < 3; k++){ const c = chave(i + 3 * k); let j = idx.get(c); if (j == null){ j = vs.length; idx.set(c, j); vs.push(`<vertex x="${T[i + 3 * k]}" y="${T[i + 3 * k + 1]}" z="${T[i + 3 * k + 2]}"/>`); } t.push(j); }
    if (t[0] !== t[1] && t[1] !== t[2] && t[0] !== t[2]) ts.push(`<triangle v1="${t[0]}" v2="${t[1]}" v3="${t[2]}"/>`); }
  const modelo = `<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="pt-BR" xmlns="${NS_3MF}"><metadata name="Application">Physis 3D</metadata><resources><object id="1" type="model"><mesh><vertices>${vs.join("")}</vertices><triangles>${ts.join("")}</triangles></mesh></object></resources><build><item objectid="1"/></build></model>`;
  return escreverZip([["[Content_Types].xml", `<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="${NS_CT}"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>`],
    ["_rels/.rels", `<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="${NS_REL}"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="${REL_3D}"/></Relationships>`], ["3D/3dmodel.model", modelo]]); }

/* ════════ medidas (as mesmas do impressao3d.py) ════════ */
function caixa(T){ const mn = [Infinity, Infinity, Infinity], mx = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < T.length; i += 3) for (let k = 0; k < 3; k++){ const v = T[i + k]; if (v < mn[k]) mn[k] = v; if (v > mx[k]) mx[k] = v; }
  return { min: mn, max: mx, tamanho: [mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]] }; }
function arestas(T, passo){ passo = passo || 1e-4; const uso = new Map(), sentido = new Map(); let deg = 0;
  const k = i => Math.round(T[i] / passo) + "," + Math.round(T[i + 1] / passo) + "," + Math.round(T[i + 2] / passo);
  for (let i = 0; i < T.length; i += 9){ const c = [k(i), k(i + 3), k(i + 6)]; if (c[0] === c[1] || c[1] === c[2] || c[0] === c[2]){ deg++; continue; }
    for (let j = 0; j < 3; j++){ const a = c[j], b = c[(j + 1) % 3], e = a < b ? a + "|" + b : b + "|" + a, s = a + ">" + b; uso.set(e, (uso.get(e) || 0) + 1); sentido.set(s, (sentido.get(s) || 0) + 1); } }
  let ab = 0, nm = 0, tr = 0; uso.forEach(n => { if (n === 1) ab++; else if (n > 2) nm++; }); sentido.forEach(n => { if (n > 1) tr++; });
  return { arestas: uso.size, abertas: ab, nao_manifold: nm, orientacao_trocada: tr, degeneradas: deg, fechada: ab === 0 && nm === 0 && tr === 0 }; }
function medir(T, limite){ limite = limite == null ? 45 : limite; if (!T || !T.length) throw new Error("malha vazia");
  const cx = caixa(T), zmin = cx.min[2], seno = Math.sin(limite * Math.PI / 180); let vol = 0, area = 0, ab = 0, fb = 0, faces = [];
  for (let i = 0; i < T.length; i += 9){ const ax = T[i], ay = T[i + 1], az = T[i + 2], bx = T[i + 3], by = T[i + 4], bz = T[i + 5], cx_ = T[i + 6], cy = T[i + 7], cz = T[i + 8];
    vol += (ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx_) + az * (bx * cy - by * cx_)) / 6;
    const n = normal(T, i), m = Math.hypot(n[0], n[1], n[2]); if (!(m > 0)){ faces.push(0); continue; } area += m / 2;
    const bal = -n[2] / m > seno && Math.max(az, bz, cz) > zmin + 0.01; if (bal){ ab += m / 2; fb++; } faces.push(bal ? 1 : 0); }
  return { caixa_min: cx.min, caixa_max: cx.max, tamanho: cx.tamanho, volume_mm3: Math.abs(vol), volume_sinal: vol >= 0 ? 1 : -1, area_mm2: area, triangulos: T.length / 9,
    balanco_limite_graus: limite, balanco_faces: fb, balanco_area_mm2: ab, balanco_fracao: area ? ab / area : 0, arestas: arestas(T), faces_balanco: faces }; }

/* ════════ fatiamento plano e estimativas (espelho do impressao3d.py) ════════ */
function corte(T, i, zc){ const pts = [];
  for (let k = 0; k < 3; k++){ const a = i + 3 * k, b = i + 3 * ((k + 1) % 3); let za = T[a + 2] - zc, zb = T[b + 2] - zc; if (za === 0) za = 1e-12; if (zb === 0) zb = 1e-12;
    if ((za < 0) !== (zb < 0)){ const s = za / (za - zb); pts.push([T[a] + s * (T[b] - T[a]), T[a + 1] + s * (T[b + 1] - T[a + 1])]); } }
  if (pts.length !== 2) return null; const n = normal(T, i), dx = pts[1][0] - pts[0][0], dy = pts[1][1] - pts[0][1];
  if (dy * n[0] - dx * n[1] < 0) pts.reverse(); return pts; }
function ordenarZ(T){ const n = T.length / 9, ix = new Array(n), zl = new Float64Array(n), zh = new Float64Array(n);
  for (let t = 0; t < n; t++){ const i = 9 * t; ix[t] = t; zl[t] = Math.min(T[i + 2], T[i + 5], T[i + 8]); zh[t] = Math.max(T[i + 2], T[i + 5], T[i + 8]); }
  ix.sort((a, b) => zl[a] - zl[b]); return { ix, zl, zh }; }
function fatiar(T, altura){ altura = +altura; if (!T || !T.length || !(altura > 0)) return [];
  const o = ordenarZ(T), cx = caixa(T), zmin = cx.min[2], n = Math.max(0, Math.floor((cx.max[2] - zmin) / altura + 1e-9)), camadas = []; let ativo = [], j = 0;
  for (let c = 0; c < n; c++){ const zc = zmin + (c + 0.5) * altura;
    while (j < o.ix.length && o.zl[o.ix[j]] <= zc) ativo.push(o.ix[j++]); ativo = ativo.filter(t => o.zh[t] >= zc);
    let per = 0, ar = 0; for (const t of ativo){ const s = corte(T, 9 * t, zc); if (!s) continue; per += Math.hypot(s[1][0] - s[0][0], s[1][1] - s[0][1]); ar += s[0][0] * s[1][1] - s[1][0] * s[0][1]; }
    camadas.push({ i: c, z: zc, perimetro_mm: per, area_mm2: ar / 2 }); }
  return camadas; }
function segmentosEm(T, zc){ const out = []; for (let i = 0; i < T.length; i += 9){ const zl = Math.min(T[i + 2], T[i + 5], T[i + 8]), zh = Math.max(T[i + 2], T[i + 5], T[i + 8]); if (zl > zc || zh < zc) continue; const s = corte(T, i, zc); if (s) out.push(s); } return out; }
function config(c){ const o = Object.assign({}, CONFIG_PADRAO); Object.keys(c || {}).forEach(k => { if (k in o){ const v = num(c[k]); if (v != null) o[k] = v; } }); return o; }
function estimar(camadas, cfg, densidade){ const c = config(cfg), h = c.altura_camada, w = c.largura_linha, np = Math.trunc(c.paredes), total = camadas.length; let parede = 0, preench = 0;
  camadas.forEach((cm, k) => { const solida = k < c.camadas_fundo || k >= total - c.camadas_topo, per = cm.perimetro_mm, area = Math.max(0, cm.area_mm2), dentro = Math.max(0, area - per * np * w);
    parede += np * per; preench += dentro / w * (solida ? 1 : c.preenchimento); });
  const vol = (parede + preench) * w * h, secao = Math.PI * Math.pow(c.diametro_filamento / 2, 2), tempo_s = (parede / c.vel_parede + preench / c.vel_preench) * c.fator_deslocamento + total * c.troca_camada_s;
  return { camadas: total, caminho_parede_mm: parede, caminho_preench_mm: preench, volume_extrudado_mm3: vol, filamento_m: vol / secao / 1000, massa_g: vol / 1000 * densidade, tempo_h: tempo_s / 3600, config: c }; }

/* ════════ edições: escala, giro, espelho, pôr na mesa, corte plano ════════ */
function escalar(T, sx, sy, sz){ const R = new Float32Array(T); for (let i = 0; i < R.length; i += 3){ R[i] *= sx; R[i + 1] *= sy; R[i + 2] *= sz; } return (sx * sy * sz < 0) ? inverter(R) : R; }
function inverter(T){ for (let i = 0; i < T.length; i += 9) for (let k = 0; k < 3; k++){ const a = T[i + 3 + k]; T[i + 3 + k] = T[i + 6 + k]; T[i + 6 + k] = a; } return T; }
function girar(T, eixo, graus){ const r = graus * Math.PI / 180, c = Math.cos(r), s = Math.sin(r), R = new Float32Array(T), [a, b] = eixo === "x" ? [1, 2] : eixo === "y" ? [2, 0] : [0, 1];
  for (let i = 0; i < R.length; i += 3){ const p = R[i + a], q = R[i + b]; R[i + a] = c * p - s * q; R[i + b] = s * p + c * q; } return R; }
const espelhar = (T, eixo) => escalar(T, eixo === "x" ? -1 : 1, eixo === "y" ? -1 : 1, eixo === "z" ? -1 : 1);
function naMesa(T){ const cx = caixa(T), dx = -(cx.min[0] + cx.max[0]) / 2, dy = -(cx.min[1] + cx.max[1]) / 2, dz = -cx.min[2], R = new Float32Array(T);
  for (let i = 0; i < R.length; i += 3){ R[i] += dx; R[i + 1] += dy; R[i + 2] += dz; } return R; }
/* corte: mantém a parte de baixo (ou de cima) do plano z e fecha a face do corte com triangulação por orelhas.
   Limite (fase 1): furos no plano do corte não são respeitados pela tampa — a conferência de arestas avisa. */
function cortar(T, z0, manter){ const cima = manter === "cima", out = [];
  const lado = v => cima ? v - z0 : z0 - v;                /* >= 0: fica */
  const corta = (p, q) => { const dp = lado(p[2]), dq = lado(q[2]), s = dp / (dp - dq); return [p[0] + s * (q[0] - p[0]), p[1] + s * (q[1] - p[1]), z0]; };
  for (let i = 0; i < T.length; i += 9){ const v = [0, 1, 2].map(k => [T[i + 3 * k], T[i + 3 * k + 1], T[i + 3 * k + 2]]), d = v.map(p => lado(p[2]));
    const fica = d.map(x => x >= 0), qtd = fica.filter(Boolean).length; if (qtd === 3){ v.forEach(p => out.push(p[0], p[1], p[2])); continue; } if (qtd === 0) continue;
    const poli = []; for (let k = 0; k < 3; k++){ const p = v[k], q = v[(k + 1) % 3]; if (fica[k]) poli.push(p); if (fica[k] !== fica[(k + 1) % 3]) poli.push(corta(p, q)); }
    for (let k = 1; k < poli.length - 1; k++) [poli[0], poli[k], poli[k + 1]].forEach(p => out.push(p[0], p[1], p[2])); }
  const corpo = new Float32Array(out), tampa = tampar(T, z0, cima); const R = new Float32Array(corpo.length + tampa.length); R.set(corpo); R.set(tampa, corpo.length); return R; }
function lacos(segs){ const k = p => Math.round(p[0] * 1e4) + "," + Math.round(p[1] * 1e4), ini = new Map(); segs.forEach((s, i) => { const c = k(s[0]); if (!ini.has(c)) ini.set(c, []); ini.get(c).push(i); });
  const usado = new Uint8Array(segs.length), out = [];
  for (let i = 0; i < segs.length; i++){ if (usado[i]) continue; const laco = []; let j = i, guarda = 0;
    while (j != null && !usado[j] && guarda++ < segs.length + 1){ usado[j] = 1; laco.push(segs[j][0]); const prox = (ini.get(k(segs[j][1])) || []).find(x => !usado[x]); j = prox == null ? null : prox; }
    if (laco.length >= 3) out.push(laco); } return out; }
const areaPoli = P => { let a = 0; for (let i = 0; i < P.length; i++){ const p = P[i], q = P[(i + 1) % P.length]; a += p[0] * q[1] - q[0] * p[1]; } return a / 2; };
function orelhas(P){ const idx = P.map((_, i) => i), out = []; let guarda = 0;
  const dentro = (p, a, b, c) => { const s = (u, v, w) => (v[0] - u[0]) * (w[1] - u[1]) - (v[1] - u[1]) * (w[0] - u[0]); return s(a, b, p) >= 0 && s(b, c, p) >= 0 && s(c, a, p) >= 0; };
  while (idx.length > 3 && guarda++ < 10 * P.length){ let achou = false;
    for (let i = 0; i < idx.length; i++){ const ia = idx[(i + idx.length - 1) % idx.length], ib = idx[i], ic = idx[(i + 1) % idx.length], a = P[ia], b = P[ib], c = P[ic];
      if ((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) <= 0) continue;
      if (idx.some(j => j !== ia && j !== ib && j !== ic && dentro(P[j], a, b, c))) continue; out.push([a, b, c]); idx.splice(i, 1); achou = true; break; }
    if (!achou) break; }
  if (idx.length === 3) out.push([P[idx[0]], P[idx[1]], P[idx[2]]]); return out; }
function tampar(T, z0, cima){ const segs = segmentosEm(T, z0), out = [];
  lacos(segs).forEach(L => { if (areaPoli(L) <= 0) return;                  /* contorno de fora (anti-horário); furo fica sem tampa */
    orelhas(L).forEach(t => { const tri = cima ? [t[0], t[2], t[1]] : t; tri.forEach(p => out.push(p[0], p[1], z0)); }); });
  return new Float32Array(out); }

/* ════════ WebGL: visualizador escrito à mão (órbita, aproximação, teclado) ════════ */
const M4 = { mul(a, b){ const o = new Float32Array(16); for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++){ let s = 0; for (let k = 0; k < 4; k++) s += a[k * 4 + j] * b[i * 4 + k]; o[i * 4 + j] = s; } return o; },
  persp(f, asp, n, l){ const t = 1 / Math.tan(f / 2), o = new Float32Array(16); o[0] = t / asp; o[5] = t; o[10] = (l + n) / (n - l); o[11] = -1; o[14] = 2 * l * n / (n - l); return o; },
  olhar(e, c, up){ const z = norm([e[0] - c[0], e[1] - c[1], e[2] - c[2]]), x = norm(cruz(up, z)), y = cruz(z, x);
    return new Float32Array([x[0], y[0], z[0], 0, x[1], y[1], z[1], 0, x[2], y[2], z[2], 0, -dot(x, e), -dot(y, e), -dot(z, e), 1]); } };
const cruz = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]], dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const norm = a => { const m = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / m, a[1] / m, a[2] / m]; };
const VS = "attribute vec3 p;attribute vec3 n;attribute float b;uniform mat4 mvp;varying vec3 vn;varying float vz;varying float vb;void main(){vn=n;vz=p.z;vb=b;gl_Position=mvp*vec4(p,1.0);}";
const FS = "precision mediump float;varying vec3 vn;varying float vz;varying float vb;uniform vec3 cor;uniform float h;uniform float listras;uniform float bal;uniform vec3 corBal;" +
  "void main(){vec3 n=normalize(vn);float l=0.35+0.55*max(dot(n,normalize(vec3(0.4,-0.5,0.8))),0.0)+0.2*max(dot(n,normalize(vec3(-0.6,0.7,0.3))),0.0);vec3 c=cor;" +
  "if(bal>0.5&&vb>0.5)c=corBal;if(listras>0.5&&h>0.0){float f=abs(fract(vz/h)-0.5)*2.0;l*=1.0-0.28*pow(f,6.0);}gl_FragColor=vec4(c*l,1.0);}";
const VS_L = "attribute vec3 p;uniform mat4 mvp;void main(){gl_Position=mvp*vec4(p,1.0);}", FS_L = "precision mediump float;uniform vec3 cor;void main(){gl_FragColor=vec4(cor,1.0);}";
const hexRgb = h => { const m = /^#?([0-9a-f]{6})$/i.exec(String(h || "")); const v = m ? parseInt(m[1], 16) : 0x7FA874; return [(v >> 16 & 255) / 255, (v >> 8 & 255) / 255, (v & 255) / 255]; };
function programa(gl, vs, fs){ const sh = (t, s) => { const x = gl.createShader(t); gl.shaderSource(x, s); gl.compileShader(x); if (!gl.getShaderParameter(x, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(x)); return x; };
  const p = gl.createProgram(); gl.attachShader(p, sh(gl.VERTEX_SHADER, vs)); gl.attachShader(p, sh(gl.FRAGMENT_SHADER, fs)); gl.linkProgram(p); return p; }
function escuro(){ try { const t = document.documentElement.getAttribute("data-tema"); if (t === "escuro") return true; if (t === "claro") return false; return window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches; } catch (e){ return false; } }
function montarVista(){ const cv = pega("p3d-vista"), st = U().p3d; if (!cv || !st || !st.T) return; if (cv.__p3d && cv.__p3d.T === st.T && cv.__p3d.versao === st.versao){ cv.__p3d.desenhar(); return; }
  let gl = null; try { gl = cv.getContext("webgl", { preserveDrawingBuffer: true, antialias: true }); } catch (e){}
  if (!gl){ const a = pega("p3d-sem-webgl"); if (a) a.hidden = false; return; }
  const T = st.T, n = T.length / 9, pos = new Float32Array(T.length), nor = new Float32Array(T.length), bal = new Float32Array(3 * n), fb = (st.med && st.med.faces_balanco) || [];
  pos.set(T); for (let t = 0; t < n; t++){ const m = normal(T, 9 * t), q = Math.hypot(m[0], m[1], m[2]) || 1; for (let k = 0; k < 3; k++){ nor[9 * t + 3 * k] = m[0] / q; nor[9 * t + 3 * k + 1] = m[1] / q; nor[9 * t + 3 * k + 2] = m[2] / q; bal[3 * t + k] = fb[t] || 0; } }
  const P = programa(gl, VS, FS), L = programa(gl, VS_L, FS_L), buf = (d) => { const b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, d, gl.STATIC_DRAW); return b; };
  const bp = buf(pos), bn = buf(nor), bb = buf(bal), grade = []; const lado = 110; for (let x = -lado; x <= lado; x += 10) grade.push(x, -lado, 0, x, lado, 0, -lado, x, 0, lado, x, 0); const bg = buf(new Float32Array(grade));
  const cx = caixa(T), alvo = [(cx.min[0] + cx.max[0]) / 2, (cx.min[1] + cx.max[1]) / 2, (cx.min[2] + cx.max[2]) / 2], raio = Math.max(10, Math.hypot(cx.tamanho[0], cx.tamanho[1], cx.tamanho[2]) / 2);
  const cam = st.cam = st.cam && st.cam.versao === st.versao ? st.cam : { gx: -0.6, gy: 0.5, dist: raio * 3.2, versao: st.versao };
  function desenhar(){ const w = cv.clientWidth || 640, h = cv.clientHeight || 420, dpr = Math.min(2, window.devicePixelRatio || 1); if (cv.width !== Math.round(w * dpr)){ cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
    gl.viewport(0, 0, cv.width, cv.height); const esc_ = escuro(), fundo = esc_ ? hexRgb("#1C2B21") : hexRgb("#F4F6F1"); gl.clearColor(fundo[0], fundo[1], fundo[2], 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT); gl.enable(gl.DEPTH_TEST);
    const olho = [alvo[0] + cam.dist * Math.cos(cam.gy) * Math.cos(cam.gx), alvo[1] + cam.dist * Math.cos(cam.gy) * Math.sin(cam.gx), alvo[2] + cam.dist * Math.sin(cam.gy)];
    const mvp = M4.mul(M4.persp(0.8, cv.width / cv.height, Math.max(0.1, cam.dist / 100), cam.dist * 20 + lado * 4), M4.olhar(olho, alvo, [0, 0, 1]));
    gl.useProgram(L); gl.uniformMatrix4fv(gl.getUniformLocation(L, "mvp"), false, mvp); gl.uniform3fv(gl.getUniformLocation(L, "cor"), hexRgb(esc_ ? "#4A5A47" : "#C9D2C4"));
    const pl = gl.getAttribLocation(L, "p"); gl.bindBuffer(gl.ARRAY_BUFFER, bg); gl.enableVertexAttribArray(pl); gl.vertexAttribPointer(pl, 3, gl.FLOAT, false, 0, 0); gl.drawArrays(gl.LINES, 0, grade.length / 3);
    gl.useProgram(P); const pref = lerPref(), mat = pref.material || "rpla";
    gl.uniformMatrix4fv(gl.getUniformLocation(P, "mvp"), false, mvp); gl.uniform3fv(gl.getUniformLocation(P, "cor"), hexRgb(pref.cor || CORES_MATERIAL[mat]));
    gl.uniform1f(gl.getUniformLocation(P, "h"), config(pref.cfg).altura_camada); gl.uniform1f(gl.getUniformLocation(P, "listras"), pref.listras === false ? 0 : 1);
    gl.uniform1f(gl.getUniformLocation(P, "bal"), pref.mostrarBalanco ? 1 : 0); gl.uniform3fv(gl.getUniformLocation(P, "corBal"), hexRgb("#A63A28"));
    [["p", bp, 3], ["n", bn, 3], ["b", bb, 1]].forEach(([nome, b, k]) => { const a = gl.getAttribLocation(P, nome); if (a < 0) return; gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.enableVertexAttribArray(a); gl.vertexAttribPointer(a, k, gl.FLOAT, false, 0, 0); });
    gl.drawArrays(gl.TRIANGLES, 0, 3 * n); }
  cv.__p3d = { T, versao: st.versao, desenhar };
  let arr = null; cv.onpointerdown = e => { arr = [e.clientX, e.clientY]; try { cv.setPointerCapture(e.pointerId); } catch (x){} };
  cv.onpointermove = e => { if (!arr) return; cam.gx -= (e.clientX - arr[0]) * 0.01; cam.gy = Math.max(-1.5, Math.min(1.5, cam.gy + (e.clientY - arr[1]) * 0.01)); arr = [e.clientX, e.clientY]; desenhar(); };
  cv.onpointerup = cv.onpointercancel = () => { arr = null; };
  cv.onwheel = e => { e.preventDefault(); cam.dist = Math.max(raio * 0.5, Math.min(raio * 40, cam.dist * (e.deltaY > 0 ? 1.1 : 0.9))); desenhar(); };
  cv.onkeydown = e => { const k = e.key; let ok = true;
    if (k === "ArrowLeft") cam.gx += 0.1; else if (k === "ArrowRight") cam.gx -= 0.1; else if (k === "ArrowUp") cam.gy = Math.min(1.5, cam.gy + 0.1); else if (k === "ArrowDown") cam.gy = Math.max(-1.5, cam.gy - 0.1);
    else if (k === "+" || k === "=") cam.dist = Math.max(raio * 0.5, cam.dist * 0.9); else if (k === "-" || k === "_") cam.dist = Math.min(raio * 40, cam.dist * 1.1); else if (k === "0"){ cam.gx = -0.6; cam.gy = 0.5; cam.dist = raio * 3.2; } else ok = false;
    if (ok){ e.preventDefault(); desenhar(); } };
  desenhar(); }
function desenharCamada(){ const cv = pega("p3d-camada"), st = U().p3d; if (!cv || !st || !st.T || !st.cam_ || !st.camadas) return; const c = st.camadas[st.camada || 0]; if (!c) return;
  const g = cv.getContext("2d"), w = cv.width, h = cv.height, cx = caixa(st.T), s = Math.min(w / (cx.tamanho[0] || 1), h / (cx.tamanho[1] || 1)) * 0.9, ox = (w - cx.tamanho[0] * s) / 2, oy = (h - cx.tamanho[1] * s) / 2;
  const esc_ = escuro(); g.fillStyle = esc_ ? "#1C2B21" : "#FFFFFF"; g.fillRect(0, 0, w, h); g.strokeStyle = esc_ ? "#8FB183" : "#33512F"; g.lineWidth = 2; g.beginPath();
  segmentosEm(st.T, c.z).forEach(sg => { g.moveTo(ox + (sg[0][0] - cx.min[0]) * s, h - oy - (sg[0][1] - cx.min[1]) * s); g.lineTo(ox + (sg[1][0] - cx.min[0]) * s, h - oy - (sg[1][1] - cx.min[1]) * s); }); g.stroke(); }
function posDesenho(){ setTimeout(() => { try { montarVista(); desenharCamada(); } catch (e){ const a = pega("p3d-sem-webgl"); if (a){ a.hidden = false; a.textContent = tx("O visualizador 3D não abriu neste navegador: use a tabela de medidas.") ; } } }, 0); }

/* ════════ servidor (modo hub) ════════ */
let csrf = null;
async function api(metodo, url, corpo){ const op = { credentials:"same-origin", cache:"no-store" };
  if (metodo === "POST"){ if (csrf == null){ try { const i = await fetch("/api/instancia", op).then(r => r.json()); csrf = i.csrf || ""; U().p3dPapel = i.papel || null; } catch (e){ csrf = ""; } }
    op.method = "POST"; op.headers = { "Content-Type":"application/json" }; if (csrf) op.headers["X-Physis-CSRF"] = csrf; op.body = JSON.stringify(corpo || {}); }
  let r, j = {}; try { r = await fetch(url, op); try { j = await r.json(); } catch (e){} } catch (e){ return { ok:false, erro:"sem ligação com o computador central" }; }
  if (r && !r.ok && j.ok == null) j.ok = false; return j; }
const b64 = buf => { const b = new Uint8Array(buf); let s = ""; for (let i = 0; i < b.length; i += 32768) s += String.fromCharCode.apply(null, b.subarray(i, i + 32768)); return btoa(s); };
function baixar(nome, dados, tipo){ try { const b = dados instanceof Blob ? dados : new Blob([dados], { type: tipo || "application/octet-stream" }), a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = nome; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 800); } catch (e){} }

/* ════════ tela ════════ */
const SUBS = [["modelo", "Modelo"], ["fatiar", "Fatiamento"], ["biblioteca", "Biblioteca"], ["forum", "Fórum"], ["metodo", "Método e licenças"]];
const campoN = (k, rot, val, ph, ajuda) => `<div><label for="p3d-c-${k}">${rot}</label><input id="p3d-c-${k}" type="text" inputmode="decimal" data-p3d-cfg="${k}" value="${E(val == null ? "" : val)}" placeholder="${E(ph == null ? "" : ph)}" style="width:100%"${ajuda ? ` aria-describedby="p3d-c-${k}-a"` : ""}>${ajuda ? `<span id="p3d-c-${k}-a" class="t2 pq">${ajuda}</span>` : ""}</div>`;
const un = () => lerPref().unidade === "in" ? "in" : "mm";
const L = mm => un() === "in" ? mm / MM_POR_POL : mm;
function selMaterial(id, atual, M){ return `<select id="${id}" data-p3d-pref="material" style="width:100%">${Object.keys(M).map(k => `<option value="${k}" ${k === atual ? "selected" : ""}>${E(M[k].nome || k)}</option>`).join("")}</select>`; }
function tabelaMedidas(st, M, mat){ const m = st.med, a = m.arestas, u = un(), d = M[mat] || {}, massa = m.volume_mm3 / 1000 * (d.densidade_g_cm3 || 0);
  const linhas = [["Tamanho (X × Y × Z)", m.tamanho.map(v => N(L(v), u === "in" ? 3 : 1)).join(" × ") + " " + u], ["Volume da peça maciça", N(m.volume_mm3 / 1000, 2) + " cm³"],
    ["Área da superfície", N(m.area_mm2 / 100, 1) + " cm²"], ["Massa se fosse maciça (" + (d.nome || mat) + ")", N(massa, 1) + " g"],
    ["Área em balanço (acima de " + N(m.balanco_limite_graus, 0) + "°)", N(100 * m.balanco_fracao, 1) + " % (" + m.balanco_faces + " faces)"], ["Triângulos", N(m.triangulos, 0)],
    ["Arestas abertas", N(a.abertas, 0)], ["Arestas com 3 faces ou mais", N(a.nao_manifold, 0)], ["Faces com o lado trocado", N(a.orientacao_trocada, 0)], ["Triângulos degenerados", N(a.degeneradas, 0)]];
  const sit = a.fechada && m.volume_sinal > 0 ? `<div class="faixa ok" role="status">${tx("Malha fechada: pronta para fatiar.")}</div>` : `<div class="faixa at" role="status">${tx("Malha com problema: o fatiador pode errar. Conserte no programa de desenho (ou numa ferramenta aberta de reparo) antes de imprimir.")}</div>`;
  return `${sit}<div class="rolagem"><table id="p3d-medidas"><caption>Medidas da peça</caption><tbody>${linhas.map(l => `<tr><th scope="row">${E(l[0])}</th><td>${E(l[1])}</td></tr>`).join("")}</tbody></table></div>`; }
function parteModelo(st, P, M){ const mat = P.material || "rpla", cor = P.cor || CORES_MATERIAL[mat] || "#7FA874";
  const imp = `<section class="cartao" aria-labelledby="h-p3d-imp"><h2 id="h-p3d-imp">Abrir a peça</h2><div class="precos">
    <div><label for="p3d-arquivo">Arquivo STL, OBJ ou 3MF</label><input id="p3d-arquivo" type="file" accept=".stl,.obj,.3mf" data-p3d-acao="abrir" style="width:100%"></div>
    <div><label for="p3d-un-arq">Unidade do arquivo</label><select id="p3d-un-arq" data-p3d-pref="unidadeArquivo" style="width:100%"><option value="mm" ${P.unidadeArquivo !== "in" ? "selected" : ""}>milímetros</option><option value="in" ${P.unidadeArquivo === "in" ? "selected" : ""}>polegadas</option></select></div>
    <div><label for="p3d-material">Material</label>${selMaterial("p3d-material", mat, M)}</div>
    <div><label for="p3d-cor">Cor do filamento</label><input id="p3d-cor" type="color" data-p3d-pref="cor" value="${E(cor)}" style="width:100%;min-height:44px"></div>
    <div><label for="p3d-un">Mostrar medidas em</label><select id="p3d-un" data-p3d-pref="unidade" style="width:100%"><option value="mm" ${un() === "mm" ? "selected" : ""}>mm</option><option value="in" ${un() === "in" ? "selected" : ""}>polegadas</option></select></div></div>
    <p class="t2 pq" role="status" id="p3d-msg">${E(st.msg || "")}</p></section>`;
  if (!st.T) return imp + `<p class="t2">Abra um arquivo para ver a peça, medir, editar e fatiar. O arquivo fica só neste computador até você enviar à biblioteca.</p>`;
  const vista = `<section class="cartao" aria-labelledby="h-p3d-vista"><h2 id="h-p3d-vista">Como a peça vai ficar</h2>
    <canvas id="p3d-vista" tabindex="0" role="img" aria-label="Vista 3D da peça. Setas giram, mais e menos aproximam, zero volta ao começo." aria-describedby="p3d-ajuda p3d-medidas" style="width:100%;height:420px;display:block;border:1px solid var(--linha,#C9D2C4);border-radius:8px"></canvas>
    <p id="p3d-sem-webgl" class="faixa at" hidden>Este navegador não abriu o WebGL: a vista 3D não aparece, mas as medidas abaixo valem.</p>
    <p id="p3d-ajuda" class="t2 pq">Arraste para girar e use a roda para aproximar; no teclado, clique na vista e use as setas, + e − e 0. As linhas horizontais mostram as camadas na altura escolhida no Fatiamento. Prévia simulada: a foto real de cada revisão vai na Biblioteca.</p>
    <div class="chips"><label><input type="checkbox" data-p3d-pref="listras" ${P.listras === false ? "" : "checked"}> Linhas de camada</label><label><input type="checkbox" data-p3d-pref="mostrarBalanco" ${P.mostrarBalanco ? "checked" : ""}> Mostrar balanço (vermelho)</label>
    <button type="button" data-p3d-acao="foto-tela" id="p3d-b-foto">Guardar a imagem na tela</button></div>
    ${st.img ? `<figure style="margin:8px 0 0"><img src="${st.img}" alt="Imagem da vista 3D da peça (${E(st.nome || "")})" style="max-width:100%;border-radius:8px"><figcaption class="t2 pq">Imagem guardada para o “Baixar esta tela”.</figcaption></figure>` : ""}</section>`;
  const ed = `<section class="cartao" aria-labelledby="h-p3d-ed"><h2 id="h-p3d-ed">Ajustar antes de fatiar</h2><div class="precos">
    <div><label for="p3d-escala">Escala (%)</label><input id="p3d-escala" type="text" inputmode="decimal" value="100" style="width:100%"></div>
    <div><label for="p3d-graus">Girar (graus)</label><input id="p3d-graus" type="text" inputmode="decimal" value="90" style="width:100%"></div>
    <div><label for="p3d-zcorte">Altura do corte (mm, a partir da mesa)</label><input id="p3d-zcorte" type="text" inputmode="decimal" value="${E(N(st.med.tamanho[2] / 2, 1))}" style="width:100%"></div></div>
    <div class="chips" role="group" aria-label="Edições"><button type="button" data-p3d-acao="escala">Aplicar escala</button>
    <button type="button" data-p3d-acao="girar" data-p3d-eixo="x">Girar em X</button><button type="button" data-p3d-acao="girar" data-p3d-eixo="y">Girar em Y</button><button type="button" data-p3d-acao="girar" data-p3d-eixo="z">Girar em Z</button>
    <button type="button" data-p3d-acao="espelhar" data-p3d-eixo="x">Espelhar X</button><button type="button" data-p3d-acao="espelhar" data-p3d-eixo="y">Espelhar Y</button><button type="button" data-p3d-acao="espelhar" data-p3d-eixo="z">Espelhar Z</button>
    <button type="button" data-p3d-acao="mesa">Pôr na mesa</button><button type="button" data-p3d-acao="cortar" data-p3d-lado="baixo">Cortar e ficar com a parte de baixo</button><button type="button" data-p3d-acao="cortar" data-p3d-lado="cima">Cortar e ficar com a parte de cima</button>
    <button type="button" data-p3d-acao="desfazer" ${st.pilha && st.pilha.length ? "" : "disabled"}>Desfazer</button><button type="button" data-p3d-acao="original">Voltar ao original</button></div>
    <p class="t2 pq">Corte plano simples: a face do corte é fechada pelo contorno de fora; furos que passam pelo corte ficam tampados (a conferência de arestas avisa).</p></section>`;
  const med = `<section class="cartao" aria-labelledby="h-p3d-med"><h2 id="h-p3d-med">Medidas: ${E(st.nome || "")}</h2>${tabelaMedidas(st, M, mat)}
    <div class="chips"><button type="button" data-p3d-acao="baixar-original">Baixar o arquivo original</button><button type="button" data-p3d-acao="baixar-stl">Baixar STL (editado)</button><button type="button" data-p3d-acao="baixar-3mf">Baixar 3MF (editado)</button></div></section>`;
  return imp + vista + ed + med; }
function parteFatiar(st, P, M){ const mat = P.material || "rpla", d = M[mat] || {}, c = config(P.cfg);
  const cfg = `<section class="cartao" aria-labelledby="h-p3d-cfg"><h2 id="h-p3d-cfg">Configuração de impressão</h2><p class="t2 pq">Material: ${E(d.nome || mat)} — bico ${N(d.bico_c, 0)} °C (${N((d.bico_faixa_c || [])[0], 0)} a ${N((d.bico_faixa_c || [])[1], 0)}), mesa ${N(d.mesa_c, 0)} °C, densidade ${N(d.densidade_g_cm3, 2)} g/cm³, contração ${N(d.contracao_pct, 1)} %. <span class="selo at">conferir</span> ${E(d.fonte || "")}</p><div class="precos">
    ${campoN("altura_camada", "Altura da camada (mm)", P.cfg.altura_camada, "0,2")}${campoN("largura_linha", "Largura da linha (mm)", P.cfg.largura_linha, "0,45")}${campoN("paredes", "Paredes", P.cfg.paredes, "2")}
    ${campoN("preenchimento", "Preenchimento (0 a 1)", P.cfg.preenchimento, "0,2")}${campoN("camadas_topo", "Camadas sólidas no topo", P.cfg.camadas_topo, "4")}${campoN("camadas_fundo", "Camadas sólidas no fundo", P.cfg.camadas_fundo, "4")}
    ${campoN("vel_parede", "Velocidade nas paredes (mm/s)", P.cfg.vel_parede, "40")}${campoN("vel_preench", "Velocidade no preenchimento (mm/s)", P.cfg.vel_preench, "60")}${campoN("diametro_filamento", "Diâmetro do filamento (mm)", P.cfg.diametro_filamento, N(d.diametro_mm || 1.75, 2))}
    ${campoN("bico_c", "Bico (°C)", P.cfg.bico_c, N(d.bico_c, 0))}${campoN("mesa_c", "Mesa (°C)", P.cfg.mesa_c, N(d.mesa_c, 0))}</div>
    <p class="t2 pq">Valores de partida editáveis, não são dados do material: ajuste à sua impressora.</p>
    <button type="button" data-p3d-acao="fatiar" id="p3d-b-fatiar" ${st.T ? "" : "disabled"}>Fatiar aqui</button>${st.T ? "" : ` <span class="t2">Abra uma peça em Modelo.</span>`}</section>`;
  let res = "";
  if (st.T && st.camadas && st.cam_){ const e = estimar(st.camadas, c, d.densidade_g_cm3 || 1), k = Math.min(st.camada || 0, st.camadas.length - 1), cm = st.camadas[k] || {};
    const h = Math.floor(e.tempo_h), mi = Math.round((e.tempo_h - h) * 60);
    res = `<div class="grade"><section class="cartao" aria-labelledby="h-p3d-e1"><h3 id="h-p3d-e1" class="t3">Camadas</h3><span class="numero">${N(e.camadas, 0)}</span><span class="t2">de ${N(c.altura_camada, 2)} mm</span></section>
      <section class="cartao" aria-labelledby="h-p3d-e2"><h3 id="h-p3d-e2" class="t3">Filamento</h3><span class="numero">${N(e.filamento_m, 1)}</span><span class="t2">m · ${N(e.massa_g, 1)} g</span></section>
      <section class="cartao" aria-labelledby="h-p3d-e3"><h3 id="h-p3d-e3" class="t3">Tempo</h3><span class="numero">${h} h ${mi} min</span><span class="t2">estimativa de pré-projeto</span></section></div>
      <section class="cartao" aria-labelledby="h-p3d-cam"><h2 id="h-p3d-cam">Camada por camada</h2><div class="precos"><div><label for="p3d-camada-n">Camada (1 a ${st.camadas.length})</label><input id="p3d-camada-n" type="range" min="1" max="${st.camadas.length}" value="${k + 1}" data-p3d-acao="camada" style="width:100%"></div></div>
      <canvas id="p3d-camada" width="480" height="320" role="img" aria-label="Contorno da camada ${k + 1}" aria-describedby="p3d-camada-txt" style="max-width:100%;border:1px solid var(--linha,#C9D2C4);border-radius:8px"></canvas>
      <p id="p3d-camada-txt" role="status">Camada ${k + 1} de ${st.camadas.length}: altura ${N(cm.z, 2)} mm, contorno ${N(cm.perimetro_mm, 1)} mm, área ${N(cm.area_mm2, 1)} mm².</p>
      <details><summary>Ver os números de todas as camadas</summary><div class="rolagem"><table><caption>Contorno e área por camada</caption><thead><tr><th scope="col">Camada</th><th scope="col">Altura (mm)</th><th scope="col">Contorno (mm)</th><th scope="col">Área (mm²)</th></tr></thead><tbody>
      ${st.camadas.filter((_, i) => st.camadas.length <= 200 || i % Math.ceil(st.camadas.length / 200) === 0).map(x => `<tr><th scope="row">${x.i + 1}</th><td>${N(x.z, 2)}</td><td>${N(x.perimetro_mm, 1)}</td><td>${N(x.area_mm2, 1)}</td></tr>`).join("")}</tbody></table></div></details>
      <p class="t2 pq">Conta: paredes = n × contorno; preenchimento = (área − contorno × n × largura) ÷ largura × fração (100 % nas ${N(c.camadas_fundo, 0)} primeiras e ${N(c.camadas_topo, 0)} últimas camadas); volume = caminho × largura × altura; filamento = volume ÷ seção do fio; massa = volume × densidade; tempo = caminho ÷ velocidade × ${N(c.fator_deslocamento, 2)} + ${N(c.troca_camada_s, 0)} s por camada. O fatiador de verdade dá o número final.</p></section>`; }
  const av = `<section class="cartao" aria-labelledby="h-p3d-av"><h2 id="h-p3d-av">Avisos da biblioteca</h2><p class="t2">O que outras impressões parecidas tiveram de mudar (aprendido com as revisões registradas pelos participantes).</p>
    <button type="button" data-p3d-acao="avisos" ${st.T && emHub() ? "" : "disabled"}>Ver avisos</button>${emHub() ? "" : ` <span class="t2">Precisa do computador central.</span>`}
    ${st.avisos ? `<div role="status"><p>${E(tx(st.avisos.texto || st.avisos.erro || ""))}</p>${(st.avisos.avisos || []).length ? `<ul>${st.avisos.avisos.map(a => `<li>${E(a.texto)} <span class="t2 pq">(probabilidade estimada ${N(100 * a.probabilidade, 0)} %)</span></li>`).join("")}</ul>` : ""}</div>` : ""}</section>`;
  const ex = `<section class="cartao" aria-labelledby="h-p3d-ex"><h2 id="h-p3d-ex">Levar para a impressora</h2><div class="chips"><button type="button" data-p3d-acao="baixar-stl" ${st.T ? "" : "disabled"}>Baixar STL</button><button type="button" data-p3d-acao="baixar-3mf" ${st.T ? "" : "disabled"}>Baixar 3MF</button>
    <button type="button" data-p3d-acao="gcode" ${st.T && emHub() ? "" : "disabled"}>Gerar G-code no servidor</button></div><p class="t2 pq" role="status">${E(st.gmsg || (emHub() ? "" : "Sem o computador central: baixe a malha e fatie num fatiador aberto (PrusaSlicer, Cura ou OrcaSlicer)."))}</p></section>`;
  return cfg + res + av + ex; }
function parteBiblioteca(st, P){ if (!emHub()) return `<div class="faixa in" role="note">A biblioteca dos participantes fica no computador central: entre pela plataforma ligada a ele.</div>`;
  const b = st.bib; if (!b) { carregar("bib"); return `<p class="t2" role="status">Carregando a biblioteca…</p>`; }
  if (b.erro) return `<div class="faixa al" role="alert">${E(b.erro)}</div>`;
  const pa = b.participante;
  const adesao = pa && !pa.removido ? `<p class="t2">Você publica como <strong>${E(pa.nome_publico)}</strong>. <button type="button" class="link" data-p3d-acao="sair-lgpd">Tirar o meu nome (LGPD)</button></p>`
    : `<section class="cartao" aria-labelledby="h-p3d-lgpd"><h2 id="h-p3d-lgpd">Participar da biblioteca</h2><p class="t2">${E(b.finalidade || "")}</p><div class="precos"><div><label for="p3d-nome-pub">Nome público (pode ser apelido)</label><input id="p3d-nome-pub" type="text" style="width:100%"></div></div>
      <label><input type="checkbox" id="p3d-lgpd"> Aceito mostrar este nome nas peças e mensagens que eu publicar.</label> <button type="button" data-p3d-acao="aderir">Participar</button></section>`;
  const busca = `<div class="precos"><div><label for="p3d-busca">Procurar peças</label><input id="p3d-busca" type="search" data-p3d-acao="busca" value="${E(st.busca || "")}" style="width:100%"></div></div>`;
  const lista = (b.pecas || []).length ? `<div class="rolagem"><table><caption>Peças da biblioteca</caption><thead><tr><th scope="col">Peça</th><th scope="col">Material</th><th scope="col">Autoria</th><th scope="col">Licença</th><th scope="col">Revisões</th><th scope="col">Situação</th></tr></thead><tbody>
    ${b.pecas.map(p => `<tr><th scope="row"><button type="button" class="link" data-p3d-acao="abrir-peca" data-p3d-id="${p.id}">${E(p.nome)}</button></th><td>${E((b.materiais || {})[p.material] || p.material || "—")}</td><td>${E(p.autor_nome)}</td><td>${E(p.licenca || "—")}</td><td>${p.revisoes} (${p.ok} ok, ${p.falhas} falhas)</td><td>${p.estado === "publicada" ? "publicada" : "rascunho"}${p.curada ? ' <span class="selo ok">curada pela Physis</span>' : ""}${p.oculta ? ' <span class="selo al">oculta</span>' : ""}</td></tr>`).join("")}</tbody></table></div>` : `<p class="t2">Nenhuma peça ainda.</p>`;
  const nova = `<section class="cartao" aria-labelledby="h-p3d-nova"><h2 id="h-p3d-nova">Nova peça</h2><div class="precos"><div><label for="p3d-n-nome">Nome</label><input id="p3d-n-nome" type="text" style="width:100%"></div><div><label for="p3d-n-desc">Para que serve</label><input id="p3d-n-desc" type="text" style="width:100%"></div></div>
    <button type="button" data-p3d-acao="nova-peca">Criar (rascunho)</button></section>`;
  return adesao + busca + lista + (st.peca ? partePeca(st, P, b) : "") + nova + `<p class="t2 pq" role="status">${E(st.bmsg || "")}</p>`; }
function partePeca(st, P, b){ const x = st.peca; if (x.erro) return `<div class="faixa al" role="alert">${E(x.erro)}</div>`; const p = x.peca, eq = /administrador|operador/.test(U().p3dPapel || "");
  const revs = x.revisoes.map(v => `<tr><th scope="row">${v.numero}</th><td>${E(v.nota || "—")}</td><td>${E(RESULTADOS[v.resultado] || "não registrado")}${v.problemas.length ? ": " + E(v.problemas.map(k => PROBLEMAS[k] || k).join(", ")) : ""}</td>
    <td><a href="api/3d/arquivo/${v.arquivo_sha256}" download>${E(v.arquivo_nome)}</a></td><td>${v.fotos.map(f => `<a href="api/3d/arquivo/${f.sha256}"><img src="api/3d/arquivo/${f.sha256}" alt="${E(f.legenda || "Foto da revisão " + v.numero)}" style="max-width:96px;max-height:72px"></a>`).join(" ")}</td><td><code title="${E(v.resumo)}">${E(v.resumo.slice(0, 12))}…</code> ${v.confere ? "confere" : "NÃO CONFERE"}</td></tr>`).join("");
  const minha = p.minha ? `<div class="precos"><div><label for="p3d-r-nota">O que mudou nesta revisão</label><input id="p3d-r-nota" type="text" style="width:100%"></div></div><button type="button" data-p3d-acao="revisao" ${st.T ? "" : "disabled"}>Enviar a peça aberta como nova revisão</button>
    <div class="precos"><div><label for="p3d-res-n">Revisão</label><input id="p3d-res-n" type="text" inputmode="numeric" value="${x.revisoes.length || ""}" style="width:100%"></div><div><label for="p3d-res">Resultado da impressão</label><select id="p3d-res" style="width:100%">${Object.keys(RESULTADOS).map(k => `<option value="${k}">${E(RESULTADOS[k])}</option>`).join("")}</select></div>
    <div><label for="p3d-res-nota">Observação</label><input id="p3d-res-nota" type="text" style="width:100%"></div></div><fieldset><legend>Problemas encontrados</legend>${Object.keys(PROBLEMAS).map(k => `<label style="display:inline-flex;gap:4px;margin-right:12px"><input type="checkbox" data-p3d-prob="${k}"> ${E(PROBLEMAS[k])}</label>`).join("")}</fieldset>
    <button type="button" data-p3d-acao="resultado">Registrar o resultado</button>
    <div class="precos"><div><label for="p3d-foto">Foto real da peça impressa (JPEG ou PNG)</label><input id="p3d-foto" type="file" accept="image/jpeg,image/png" style="width:100%"></div><div><label for="p3d-foto-leg">Legenda</label><input id="p3d-foto-leg" type="text" style="width:100%"></div></div><button type="button" data-p3d-acao="foto">Enviar a foto da revisão</button>
    ${p.estado !== "publicada" ? `<div class="precos"><div><label for="p3d-lic">Licença aberta</label><select id="p3d-lic" style="width:100%">${Object.keys(LICENCAS).map(k => `<option value="${k}">${E(k + " — " + LICENCAS[k])}</option>`).join("")}</select></div></div>
    <label><input type="checkbox" id="p3d-pub-ok"> Publico esta peça sob a licença escolhida, com o meu nome público.</label> <button type="button" data-p3d-acao="publicar">Publicar</button>` : ""}` : `<button type="button" data-p3d-acao="derivar">Melhorar esta peça (cria uma derivada sua)</button>`;
  const equipe = eq ? `<div class="chips"><button type="button" data-p3d-acao="curar">${p.curada ? "Tirar a curadoria" : "Marcar como curada"}</button><button type="button" data-p3d-acao="moderar">${p.oculta ? "Mostrar de novo" : "Ocultar (moderação)"}</button></div>` : "";
  return `<section class="cartao" aria-labelledby="h-p3d-peca"><h2 id="h-p3d-peca">${E(p.nome)}</h2><p class="t2">${E(p.descricao || "")} · ${E(p.autor_nome)} · ${E(p.licenca ? p.licenca + " (" + p.licenca_nome + ")" : "rascunho, ainda sem licença")}${p.origem ? " · derivada da peça " + p.origem : ""}</p>
    <div class="rolagem"><table><caption>Revisões e memorial</caption><thead><tr><th scope="col">Revisão</th><th scope="col">O que mudou</th><th scope="col">Resultado</th><th scope="col">Arquivo</th><th scope="col">Fotos</th><th scope="col">Integridade</th></tr></thead><tbody>${revs}</tbody></table></div>
    <div class="chips"><button type="button" data-p3d-acao="memorial">Ver o memorial</button><button type="button" data-p3d-acao="forum-peca">Fórum desta peça</button></div>
    ${st.memorial ? `<pre style="white-space:pre-wrap">${E(st.memorial)}</pre><button type="button" data-p3d-acao="baixar-memorial">Baixar o memorial (.md)</button>` : ""}${minha}${equipe}</section>`; }
function parteForum(st){ if (!emHub()) return `<div class="faixa in" role="note">O fórum fica no computador central.</div>`;
  const f = st.forum; if (!f){ carregar("forum"); return `<p class="t2" role="status">Carregando o fórum…</p>`; }
  const top = (f.topicos || []).map(t => `<li><button type="button" class="link" data-p3d-acao="topico" data-p3d-id="${t.id}">${E(t.titulo)}</button> <span class="t2 pq">${E(t.autor_nome)} · ${t.mensagens} mensagens</span></li>`).join("");
  const aberto = st.topico ? `<section class="cartao" aria-labelledby="h-p3d-top"><h2 id="h-p3d-top">${E(st.topico.topico ? st.topico.topico.titulo : "")}</h2>${(st.topico.mensagens || []).map(m => `<article class="cartao"><p class="t2 pq">${E(m.autor_nome)}${m.oculta ? ' <span class="selo al">retirada</span>' : ""}</p><p style="white-space:pre-wrap">${E(m.texto)}</p>${/administrador|operador/.test(U().p3dPapel || "") ? `<button type="button" data-p3d-acao="moderar-msg" data-p3d-id="${m.id}">${m.oculta ? "Mostrar de novo" : "Retirar"}</button>` : ""}</article>`).join("")}
    <div><label for="p3d-resp">Responder</label><textarea id="p3d-resp" rows="3" style="width:100%"></textarea></div><button type="button" data-p3d-acao="responder">Enviar</button></section>` : "";
  return `<p class="t2">${st.forumPeca ? "Tópicos da peça aberta na Biblioteca." : "Tópicos gerais. Para falar de uma peça, abra a peça na Biblioteca e use “Fórum desta peça”."} ${st.forumPeca ? `<button type="button" class="link" data-p3d-acao="forum-geral">Ver os gerais</button>` : ""}</p><ul>${top || "<li>Nenhum tópico ainda.</li>"}</ul>${aberto}
    <section class="cartao" aria-labelledby="h-p3d-novo"><h2 id="h-p3d-novo">Novo tópico</h2><div class="precos"><div><label for="p3d-t-tit">Título</label><input id="p3d-t-tit" type="text" style="width:100%"></div></div><div><label for="p3d-t-txt">Mensagem</label><textarea id="p3d-t-txt" rows="3" style="width:100%"></textarea></div><button type="button" data-p3d-acao="novo-topico">Abrir o tópico</button></section><p class="t2 pq" role="status">${E(st.fmsg || "")}</p>`; }
function parteMetodo(){ return `<section class="cartao" aria-labelledby="h-p3d-met"><h2 id="h-p3d-met">Método e licenças</h2><ul>
  <li><strong>Leitura:</strong> STL (texto e binário), OBJ e 3MF lidos por código próprio; o 3MF é um ZIP, aberto com um descompactador escrito aqui. O arquivo original fica guardado como veio.</li>
  <li><strong>Medidas:</strong> volume pela soma dos tetraedros de cada triângulo com a origem; área pela soma dos triângulos; balanço = faces viradas para baixo mais deitadas que o limite (45° da vertical, padrão), fora da mesa; conferência de arestas (cada aresta tem de ter exatamente duas faces, em sentidos opostos).</li>
  <li><strong>Fatiamento da tela:</strong> planos no meio de cada camada; cada triângulo cortado dá um segmento orientado pela face, e a área sai pela fórmula de Gauss sem montar os contornos. Estimativa de pré-projeto; o G-code de verdade vem do fatiador aberto do servidor (PrusaSlicer, AGPL-3.0, num contêiner separado).</li>
  <li><strong>Materiais reciclados:</strong> densidade, temperaturas e contração são premissas "conferir" (valores típicos do polímero virgem). Troque pelos do fornecedor ou pelo ensaio da oficina.</li>
  <li><strong>Avisos aprendidos:</strong> classificador de Bayes ingênuo, treinado nas revisões com resultado (material, camada, balanço, parede, tamanho e temperatura do bico). Com poucos dados, a tela diz que são poucos.</li>
  <li><strong>Licenças:</strong> este código é da Physis, aberto; o visualizador é WebGL escrito à mão (sem biblioteca de terceiros). Cada peça publicada leva a licença aberta escolhida pelo autor (CC BY 4.0, CC BY-SA 4.0, CC0 1.0, CERN-OHL-S/W/P 2.0). Formatos: 3MF (especificação aberta do 3MF Consortium) e STL.</li>
  <li><strong>Fase 2:</strong> simulações (escoamento, calor, pressão, compressão, impacto, tração, flambagem) com resolvedores clássicos abertos como referência (CalculiX, FEniCS, OpenFOAM) e a trilha de programação quântica (Qiskit, PennyLane), que só entra no Planejador depois de validada contra os clássicos. Veja physis-hub/docs/PHYSIS_3D.md.</li></ul></section>`; }
function telaPhysis3D(){ const u = U(), st = u.p3d = u.p3d || {}, P = lerPref(), M = materiais(), sub = SUBS.some(s => s[0] === u.p3dSub) ? u.p3dSub : "modelo";
  const chips = `<div class="chips" role="group" aria-label="Partes do Physis 3D">${SUBS.map(([k, n]) => `<button type="button" id="p3d-sub-${k}" data-p3d-sub="${k}" aria-pressed="${k === sub}">${n}</button>`).join("")}</div>`;
  const dev = window.PHYSIS3D_PRONTO === true ? "" : `<p><span class="selo at">Em desenvolvimento</span> <span class="t2 pq">Módulo em construção, só na instalação de pesquisa: use para estudo e confira tudo antes de imprimir uma peça para alguém.</span></p>`;
  const corpo = sub === "fatiar" ? parteFatiar(st, P, M) : sub === "biblioteca" ? parteBiblioteca(st, P) : sub === "forum" ? parteForum(st) : sub === "metodo" ? parteMetodo() : parteModelo(st, P, M);
  posDesenho();
  return `<h1>Physis 3D</h1>${dev}<p class="t2 apoio">Peças para impressão 3D com plástico reciclado: abrir, medir, ajustar, fatiar e ver como vai ficar; biblioteca aberta com memorial de cada peça e fórum.</p>${chips}<div id="p3d-corpo">${corpo}</div>`; }

/* ════════ ações ════════ */
function trocarMalha(st, T, msg){ st.pilha = (st.pilha || []).concat([st.T]).slice(-10); st.T = T; st.med = medir(T); st.versao = (st.versao || 0) + 1; st.camadas = null; st.cam_ = false; st.img = null; st.avisos = null; st.msg = msg || ""; }
async function abrirArquivo(f){ const u = U(), st = u.p3d = u.p3d || {}; st.msg = "Lendo…"; redesenhar();
  try { const buf = await f.arrayBuffer(); let T = lerMalha(buf, f.name); if (lerPref().unidadeArquivo === "in") T = escalar(T, MM_POR_POL, MM_POR_POL, MM_POR_POL);
    st.original = { nome: f.name, dados: buf }; st.nome = f.name; st.pilha = []; st.T = null; trocarMalha(st, T, ""); st.pilha = []; st.T0 = T;
    st.msg = `${f.name}: ${N(st.med.triangulos, 0)} triângulos.`; } catch (e){ st.msg = "Não consegui ler o arquivo: " + (e && e.message || e); }
  redesenhar(); const x = pega("p3d-arquivo"); if (x) x.focus(); }
function camposMarcados(sel){ return Array.from(document.querySelectorAll(sel)).filter(x => x.checked).map(x => x.dataset.p3dProb); }
async function carregar(o){ const u = U(), st = u.p3d = u.p3d || {}; if (st["c_" + o]) return; st["c_" + o] = true;
  try { if (o === "bib"){ const [l, pa] = await Promise.all([api("GET", "api/3d/pecas?busca=" + encodeURIComponent(st.busca || "")), api("GET", "api/3d/participante")]);
      if (csrf == null) await api("GET", "/api/instancia").then(i => { csrf = i.csrf || ""; u.p3dPapel = i.papel || null; });
      st.bib = l.ok ? Object.assign(l, { participante: pa.participante, finalidade: pa.finalidade }) : { erro: l.erro || "biblioteca indisponível" }; }
    if (o === "forum"){ const r = await api("GET", "api/3d/forum" + (st.forumPeca ? "?peca=" + st.forumPeca : "")); st.forum = r.ok ? r : { topicos: [], erro: r.erro }; } }
  finally { st["c_" + o] = false; } redesenhar(); }
async function abrirPeca(id){ const st = U().p3d; st.memorial = null; st.peca = await api("GET", "api/3d/pecas/" + id); if (!st.peca.ok) st.peca = { erro: st.peca.erro || "peça não encontrada" }; redesenhar(); }
async function acao(b){ const u = U(), st = u.p3d = u.p3d || {}, a = b.dataset.p3dAcao, P = lerPref(), foco = b.id;
  const refoco = () => { if (foco){ const x = pega(foco); if (x) x.focus(); } };
  if (a === "desfazer" && st.pilha && st.pilha.length){ const T = st.pilha.pop(); st.T = T; st.med = medir(T); st.versao = (st.versao || 0) + 1; st.camadas = null; st.cam_ = false; redesenhar(); return; }
  if (a === "original" && st.T0){ trocarMalha(st, st.T0, "De volta ao original."); redesenhar(); return; }
  if (st.T && ["escala", "girar", "espelhar", "mesa", "cortar"].indexOf(a) >= 0){
    if (a === "escala"){ const s = num((pega("p3d-escala") || {}).value); if (!(s > 0)) return; trocarMalha(st, escalar(st.T, s / 100, s / 100, s / 100), `Escala de ${N(s, 1)} %.`); }
    if (a === "girar"){ const g = num((pega("p3d-graus") || {}).value) || 0; trocarMalha(st, girar(st.T, b.dataset.p3dEixo, g), `Girada ${N(g, 0)}° em ${b.dataset.p3dEixo.toUpperCase()}.`); }
    if (a === "espelhar") trocarMalha(st, espelhar(st.T, b.dataset.p3dEixo), `Espelhada em ${b.dataset.p3dEixo.toUpperCase()}.`);
    if (a === "mesa") trocarMalha(st, naMesa(st.T), "Na mesa: base em z = 0 e centro no meio.");
    if (a === "cortar"){ const z = num((pega("p3d-zcorte") || {}).value); if (z == null) return; const z0 = caixa(st.T).min[2] + z, R = cortar(st.T, z0, b.dataset.p3dLado);
      if (!R.length){ st.msg = "O corte não deixou nada: confira a altura."; redesenhar(); return; } trocarMalha(st, R, "Cortada."); }
    redesenhar(); return; }
  if (a === "foto-tela"){ const cv = pega("p3d-vista"); try { if (cv && cv.__p3d) cv.__p3d.desenhar(); st.img = cv ? cv.toDataURL("image/png") : null; } catch (e){ st.img = null; } redesenhar(); refoco(); return; }
  if (a === "baixar-original" && st.original){ baixar(st.original.nome, st.original.dados); return; }
  const base = String(st.nome || "peca").replace(/\.[^.]+$/, "");
  if (a === "baixar-stl" && st.T){ baixar(base + "-physis3d.stl", escreverSTL(st.T, "Physis 3D " + base), "model/stl"); return; }
  if (a === "baixar-3mf" && st.T){ baixar(base + "-physis3d.3mf", escrever3MF(st.T)); return; }
  if (a === "fatiar" && st.T){ st.camadas = fatiar(st.T, config(P.cfg).altura_camada); st.cam_ = true; st.camada = 0; redesenhar(); refoco(); return; }
  if (a === "avisos" && st.T){ const c = config(P.cfg); st.avisos = await api("POST", "api/3d/avisos", { material: P.material || "rpla", config: c, balanco_fracao: st.med.balanco_fracao, tamanho_mm: Math.max.apply(null, st.med.tamanho) }); redesenhar(); refoco(); return; }
  if (a === "gcode" && st.T){ st.gmsg = "Fatiando no servidor…"; redesenhar(); const r = await api("POST", "api/3d/fatiar", { stl_b64: b64(escreverSTL(st.T)), config: config(P.cfg), material: P.material || "rpla" });
    if (r.ok && r.gcode){ baixar(base + ".gcode", r.gcode, "text/x.gcode"); const e = r.estimativa || {}; st.gmsg = `G-code pronto (${r.fatiador || "fatiador do servidor"}): ${e.tempo_s ? N(e.tempo_s / 3600, 1) + " h" : "tempo não informado"}, ${e.filamento_g ? N(e.filamento_g, 1) + " g" : ""}.`; }
    else st.gmsg = r.erro || "fatiador indisponível: baixe a malha e fatie num fatiador aberto."; redesenhar(); return; }
  /* biblioteca e fórum */
  const recarregar = async () => { st.bib = null; if (st.peca && st.peca.peca) await abrirPeca(st.peca.peca.id); redesenhar(); };
  if (a === "aderir"){ const r = await api("POST", "api/3d/participante", { nome_publico: (pega("p3d-nome-pub") || {}).value, consentimento: !!(pega("p3d-lgpd") || {}).checked }); st.bmsg = r.ok ? "Pronto: você participa da biblioteca." : r.erro; return recarregar(); }
  if (a === "sair-lgpd"){ if (typeof confirm === "function" && !confirm(tx("Tirar o seu nome público de tudo? As peças publicadas seguem sob a licença, sem o seu nome."))) return; const r = await api("POST", "api/3d/participante/remover", {}); st.bmsg = r.ok ? "Nome removido." : r.erro; return recarregar(); }
  if (a === "nova-peca"){ const r = await api("POST", "api/3d/pecas", { nome: (pega("p3d-n-nome") || {}).value, descricao: (pega("p3d-n-desc") || {}).value, material: P.material || "" }); st.bmsg = r.ok ? "Peça criada como rascunho." : r.erro; if (r.ok) await abrirPeca(r.id); return recarregar(); }
  if (a === "abrir-peca"){ await abrirPeca(b.dataset.p3dId); return; }
  const pid = st.peca && st.peca.peca ? st.peca.peca.id : null;
  if (a === "memorial" && pid){ const r = await api("GET", "api/3d/pecas/" + pid + "/memorial"); st.memorial = r.ok ? r.texto : r.erro; redesenhar(); return; }
  if (a === "baixar-memorial" && st.memorial){ baixar("memorial-peca-" + pid + ".md", st.memorial, "text/markdown"); return; }
  if (a === "revisao" && pid && st.T){ st.bmsg = "Enviando…"; redesenhar(); const r = await api("POST", "api/3d/pecas/" + pid + "/revisao", { arquivo_b64: b64(escreverSTL(st.T)), arquivo_nome: base + ".stl", nota: (pega("p3d-r-nota") || {}).value, material: P.material || "", config: config(P.cfg) });
    st.bmsg = r.ok ? `Revisão ${r.numero} guardada (integridade ${String(r.resumo).slice(0, 12)}…).` : r.erro; return recarregar(); }
  if (a === "resultado" && pid){ const r = await api("POST", "api/3d/pecas/" + pid + "/resultado", { numero: num((pega("p3d-res-n") || {}).value), resultado: (pega("p3d-res") || {}).value, problemas: camposMarcados("[data-p3d-prob]"), resultado_nota: (pega("p3d-res-nota") || {}).value });
    st.bmsg = r.ok ? "Resultado registrado." : r.erro; return recarregar(); }
  if (a === "foto" && pid){ const f = (pega("p3d-foto") || {}).files; if (!f || !f[0]) return; const r = await api("POST", "api/3d/pecas/" + pid + "/foto", { numero: num((pega("p3d-res-n") || {}).value), foto_b64: b64(await f[0].arrayBuffer()), legenda: (pega("p3d-foto-leg") || {}).value });
    st.bmsg = r.ok ? "Foto guardada." : r.erro; return recarregar(); }
  if (a === "publicar" && pid){ const r = await api("POST", "api/3d/pecas/" + pid + "/publicar", { licenca: (pega("p3d-lic") || {}).value, consentimento: !!(pega("p3d-pub-ok") || {}).checked }); st.bmsg = r.ok ? "Peça publicada." : r.erro; return recarregar(); }
  if (a === "derivar" && pid){ const r = await api("POST", "api/3d/pecas/" + pid + "/derivar", {}); st.bmsg = r.ok ? "Derivada criada: agora a peça é sua para melhorar." : r.erro; if (r.ok) await abrirPeca(r.id); return recarregar(); }
  if (a === "curar" && pid){ const r = await api("POST", "api/3d/pecas/" + pid + "/curar", { curada: !st.peca.peca.curada }); st.bmsg = r.ok ? "Curadoria atualizada." : r.erro; return recarregar(); }
  if (a === "moderar" && pid){ const oc = !st.peca.peca.oculta, mot = oc && typeof prompt === "function" ? prompt(tx("Motivo da moderação")) : ""; if (oc && !mot) return; const r = await api("POST", "api/3d/pecas/" + pid + "/moderar", { oculta: oc, motivo: mot }); st.bmsg = r.ok ? "Moderação registrada." : r.erro; return recarregar(); }
  if (a === "forum-peca" && pid){ st.forumPeca = pid; st.forum = null; st.topico = null; u.p3dSub = "forum"; redesenhar(); return; }
  if (a === "forum-geral"){ st.forumPeca = null; st.forum = null; st.topico = null; redesenhar(); return; }
  if (a === "topico"){ st.topico = await api("GET", "api/3d/forum/" + b.dataset.p3dId); redesenhar(); return; }
  if (a === "novo-topico"){ const r = await api("POST", "api/3d/forum", { peca: st.forumPeca || null, titulo: (pega("p3d-t-tit") || {}).value, texto: (pega("p3d-t-txt") || {}).value }); st.fmsg = r.ok ? "Tópico aberto." : r.erro; st.forum = null; if (r.ok) st.topico = await api("GET", "api/3d/forum/" + r.id); redesenhar(); return; }
  if (a === "responder" && st.topico && st.topico.topico){ const r = await api("POST", "api/3d/forum/" + st.topico.topico.id, { texto: (pega("p3d-resp") || {}).value }); st.fmsg = r.ok ? "" : r.erro; st.topico = await api("GET", "api/3d/forum/" + st.topico.topico.id); redesenhar(); return; }
  if (a === "moderar-msg"){ const m = (st.topico.mensagens || []).find(x => String(x.id) === b.dataset.p3dId), oc = !(m && m.oculta), mot = oc && typeof prompt === "function" ? prompt(tx("Motivo da moderação")) : ""; if (oc && !mot) return;
    await api("POST", "api/3d/forum/mensagem/" + b.dataset.p3dId + "/moderar", { oculta: oc, motivo: mot }); st.topico = await api("GET", "api/3d/forum/" + st.topico.topico.id); redesenhar(); } }
if (typeof document !== "undefined" && !window.__p3dEventos){ window.__p3dEventos = true;
  document.addEventListener("change", ev => { const t = ev.target; if (!t || !t.dataset) return; const st = U().p3d = U().p3d || {};
    if (t.dataset.p3dAcao === "abrir" && t.files && t.files[0]){ abrirArquivo(t.files[0]); return; }
    if (t.dataset.p3dAcao === "busca"){ st.busca = t.value; st.bib = null; redesenhar(); const x = pega(t.id); if (x) x.focus(); return; }
    if (t.dataset.p3dAcao === "camada"){ st.camada = Math.max(0, (+t.value || 1) - 1); redesenhar(); const x = pega(t.id); if (x) x.focus(); return; }
    if (t.dataset.p3dPref){ const P = lerPref(), k = t.dataset.p3dPref; P[k] = t.type === "checkbox" ? t.checked : t.value; if (k === "material") P.cor = CORES_MATERIAL[t.value] || P.cor; gravarPref(P);
      const cv = pega("p3d-vista"); if (cv) cv.__p3d = null; redesenhar(); const x = pega(t.id); if (x) x.focus(); return; }
    if (t.dataset.p3dCfg){ const P = lerPref(); P.cfg[t.dataset.p3dCfg] = t.value; gravarPref(P); if (st.cam_ && t.dataset.p3dCfg === "altura_camada"){ st.cam_ = false; st.camadas = null; } redesenhar(); const x = pega(t.id); if (x) x.focus(); } });
  document.addEventListener("input", ev => { const t = ev.target; if (t && t.dataset && t.dataset.p3dAcao === "camada"){ const st = U().p3d; st.camada = Math.max(0, (+t.value || 1) - 1); desenharCamada();
    const c = st.camadas[st.camada], p = pega("p3d-camada-txt"); if (c && p) p.textContent = tx(`Camada ${st.camada + 1} de ${st.camadas.length}: altura ${N(c.z, 2)} mm, contorno ${N(c.perimetro_mm, 1)} mm, área ${N(c.area_mm2, 1)} mm².`); } });
  document.addEventListener("click", ev => { const b = ev.target && ev.target.closest ? ev.target.closest("button") : null; if (!b || !b.dataset) return;
    if (b.dataset.p3dSub){ U().p3dSub = b.dataset.p3dSub; redesenhar(); const x = pega("p3d-sub-" + b.dataset.p3dSub); if (x) x.focus(); return; }
    if (b.dataset.p3dAcao) acao(b); }); }

/* ════════ autoteste (o mesmo cubo do tests/test_impressao3d.py; rodado em ferramentas/testes-navegador/teste-physis-3d.html) ════════ */
function cubo(L){ L = L || 20; const v = []; for (let z = 0; z < 2; z++) for (let y = 0; y < 2; y++) for (let x = 0; x < 2; x++) v.push([x * L, y * L, z * L]);
  const f = [[0, 2, 3], [0, 3, 1], [4, 5, 7], [4, 7, 6], [0, 1, 5], [0, 5, 4], [2, 6, 7], [2, 7, 3], [0, 4, 6], [0, 6, 2], [1, 3, 7], [1, 7, 5]], out = [];
  f.forEach(t => t.forEach(i => out.push(v[i][0], v[i][1], v[i][2]))); return new Float32Array(out); }
function autoteste(){ const r = [], ok = (nome, cond, info) => r.push({ nome, ok: !!cond, info: info == null ? "" : String(info) }), perto = (a, b, t) => Math.abs(a - b) <= (t || 1e-6) * Math.max(1, Math.abs(b));
  const T = cubo(20), m = medir(T); ok("volume do cubo 20 mm = 8000 mm³", perto(m.volume_mm3, 8000), m.volume_mm3); ok("área = 2400 mm²", perto(m.area_mm2, 2400), m.area_mm2); ok("cubo fechado", m.arestas.fechada && m.volume_sinal === 1);
  ok("sem balanço (fundo na mesa)", m.balanco_fracao === 0);
  const c = fatiar(T, 0.2); ok("100 camadas de 0,2 mm", c.length === 100, c.length); ok("contorno 80 mm por camada", c.every(x => perto(x.perimetro_mm, 80, 1e-4)), c[0] && c[0].perimetro_mm); ok("área 400 mm² por camada", c.every(x => perto(x.area_mm2, 400, 1e-4)), c[0] && c[0].area_mm2);
  const e = estimar(c, null, 1.24); ok("paredes: 2 × 80 × 100 = 16000 mm", perto(e.caminho_parede_mm, 16000, 1e-4), e.caminho_parede_mm); ok("preenchimento igual ao Python", perto(e.caminho_preench_mm, 19242.666666666664, 1e-6), e.caminho_preench_mm);
  ok("massa igual ao Python (g)", perto(e.massa_g, 3.9330816, 1e-6), e.massa_g); ok("tempo igual ao Python (h)", perto(e.tempo_h, 0.2857827160493827, 1e-6), e.tempo_h);
  const stl = lerSTL(escreverSTL(T)); ok("STL binário ida e volta", perto(medir(stl).volume_mm3, 8000));
  let txt = "solid c\n"; for (let i = 0; i < T.length; i += 9) txt += ` facet normal 0 0 0\n  outer loop\n   vertex ${T[i]} ${T[i + 1]} ${T[i + 2]}\n   vertex ${T[i + 3]} ${T[i + 4]} ${T[i + 5]}\n   vertex ${T[i + 6]} ${T[i + 7]} ${T[i + 8]}\n  endloop\n endfacet\n`; txt += "endsolid c\n";
  ok("STL de texto", perto(medir(lerSTL(new TextEncoder().encode(txt).buffer)).volume_mm3, 8000));
  ok("OBJ", perto(medir(lerOBJ("v 0 0 0\nv 20 0 0\nv 0 20 0\nv 20 20 0\nv 0 0 20\nv 20 0 20\nv 0 20 20\nv 20 20 20\nf 1 3 4 2\nf 5 6 8 7\nf 1 2 6 5\nf 3 7 8 4\nf 1 5 7 3\nf 2 4 8 6\n")).volume_mm3, 8000));
  return { r, T }; }
async function autoteste3MF(){ const T = cubo(20), z = escrever3MF(T), buf = await z.arrayBuffer(), m = medir(ler3MF(buf)), r = [{ nome: "3MF escrito e lido (sem compressão)", ok: Math.abs(m.volume_mm3 - 8000) < 1e-3, info: m.volume_mm3 }];
  if (typeof CompressionStream === "function"){ /* confere o inflate próprio com um deflate do navegador */
    const dados = new TextEncoder().encode("Physis 3D ".repeat(500) + "fim"), cs = new Blob([dados]).stream().pipeThrough(new CompressionStream("deflate-raw")), comp = new Uint8Array(await new Response(cs).arrayBuffer()), volta = inflar(comp);
    r.push({ nome: "inflate próprio = deflate do navegador", ok: volta.length === dados.length && volta.every((x, i) => x === dados[i]), info: comp.length + " → " + volta.length }); }
  const cortado = cortar(T, 10, "baixo"), mc = medir(cortado); r.push({ nome: "corte a 10 mm: metade do volume e fechado", ok: Math.abs(mc.volume_mm3 - 4000) < 1e-2 && mc.arestas.fechada, info: mc.volume_mm3 + " " + JSON.stringify(mc.arestas) });
  const g = medir(girar(T, "x", 90)); r.push({ nome: "giro mantém o volume", ok: Math.abs(g.volume_mm3 - 8000) < 1e-2 && g.volume_sinal === 1, info: g.volume_mm3 });
  const es = medir(espelhar(T, "x")); r.push({ nome: "espelho mantém as faces para fora", ok: es.volume_sinal === 1 && es.arestas.fechada, info: es.volume_sinal });
  return r; }

window.PHYSIS3D = { estado:"dev", versao:"physis-3d-0.1", CONFIG_PADRAO, MATERIAIS_RESERVA, LICENCAS, PROBLEMAS, RESULTADOS, materiais, lerSTL, lerOBJ, ler3MF, lerMalha, lerZip, inflar, crc32,
  escreverSTL, escrever3MF, caixa, medir, arestas, fatiar, segmentosEm, estimar, config, escalar, girar, espelhar, naMesa, cortar, cubo, autoteste, autoteste3MF };
window.telaPhysis3D = telaPhysis3D;   /* global: a plataforma chama telaPhysis3D() na hora de desenhar */

/* ════════ Inglês (o integrador junta ao I18N da plataforma) ════════ */
window.PHYSIS3D_I18N = {
  "Physis 3D": "Physis 3D",
  "Em desenvolvimento": "In development",
  "Módulo em construção, só na instalação de pesquisa: use para estudo e confira tudo antes de imprimir uma peça para alguém.": "Module under construction, research installation only: use it for study and check everything before printing a part for someone.",
  "Peças para impressão 3D com plástico reciclado: abrir, medir, ajustar, fatiar e ver como vai ficar; biblioteca aberta com memorial de cada peça e fórum.": "3D-printed parts from recycled plastic: open, measure, adjust, slice and preview; open library with a development record for every part, and a forum.",
  "Partes do Physis 3D": "Physis 3D sections",
  "Modelo": "Model", "Fatiamento": "Slicing", "Biblioteca": "Library", "Fórum": "Forum", "Método e licenças": "Method and licences",
  "Abrir a peça": "Open the part", "Arquivo STL, OBJ ou 3MF": "STL, OBJ or 3MF file", "Unidade do arquivo": "File unit", "milímetros": "millimetres", "polegadas": "inches",
  "Material": "Material", "Cor do filamento": "Filament colour", "Mostrar medidas em": "Show measurements in",
  "Abra um arquivo para ver a peça, medir, editar e fatiar. O arquivo fica só neste computador até você enviar à biblioteca.": "Open a file to view, measure, edit and slice the part. The file stays on this computer until you send it to the library.",
  "Como a peça vai ficar": "How the part will look",
  "Este navegador não abriu o WebGL: a vista 3D não aparece, mas as medidas abaixo valem.": "This browser could not start WebGL: the 3D view is not shown, but the measurements below are valid.",
  "O visualizador 3D não abriu neste navegador: use a tabela de medidas.": "The 3D viewer did not open in this browser: use the measurements table.",
  "Arraste para girar e use a roda para aproximar; no teclado, clique na vista e use as setas, + e − e 0. As linhas horizontais mostram as camadas na altura escolhida no Fatiamento. Prévia simulada: a foto real de cada revisão vai na Biblioteca.": "Drag to rotate and use the wheel to zoom; with the keyboard, focus the view and use the arrows, + and − and 0. The horizontal lines show the layers at the height chosen in Slicing. Simulated preview: the real photo of each revision goes to the Library.",
  "Linhas de camada": "Layer lines", "Mostrar balanço (vermelho)": "Show overhangs (red)", "Guardar a imagem na tela": "Keep the image on the screen",
  "Imagem guardada para o “Baixar esta tela”.": "Image kept for “Download this screen”.",
  "Ajustar antes de fatiar": "Adjust before slicing", "Escala (%)": "Scale (%)", "Girar (graus)": "Rotate (degrees)", "Altura do corte (mm, a partir da mesa)": "Cut height (mm, from the bed)",
  "Edições": "Edits", "Aplicar escala": "Apply scale", "Girar em X": "Rotate about X", "Girar em Y": "Rotate about Y", "Girar em Z": "Rotate about Z",
  "Espelhar X": "Mirror X", "Espelhar Y": "Mirror Y", "Espelhar Z": "Mirror Z", "Pôr na mesa": "Place on bed",
  "Cortar e ficar com a parte de baixo": "Cut and keep the lower part", "Cortar e ficar com a parte de cima": "Cut and keep the upper part", "Desfazer": "Undo", "Voltar ao original": "Back to the original",
  "Corte plano simples: a face do corte é fechada pelo contorno de fora; furos que passam pelo corte ficam tampados (a conferência de arestas avisa).": "Simple planar cut: the cut face is closed along the outer outline; holes crossing the cut get covered (the edge check warns).",
  "Medidas da peça": "Part measurements", "Volume da peça maciça": "Volume of the solid part", "Área da superfície": "Surface area", "Triângulos": "Triangles",
  "Arestas abertas": "Open edges", "Arestas com 3 faces ou mais": "Edges with 3 or more faces", "Faces com o lado trocado": "Faces with flipped orientation", "Triângulos degenerados": "Degenerate triangles",
  "Tamanho (X × Y × Z)": "Size (X × Y × Z)",
  "Malha fechada: pronta para fatiar.": "Closed mesh: ready to slice.",
  "Malha com problema: o fatiador pode errar. Conserte no programa de desenho (ou numa ferramenta aberta de reparo) antes de imprimir.": "Mesh has problems: the slicer may fail. Repair it in the design program (or in an open repair tool) before printing.",
  "Baixar o arquivo original": "Download the original file", "Baixar STL (editado)": "Download STL (edited)", "Baixar 3MF (editado)": "Download 3MF (edited)",
  "Configuração de impressão": "Print settings", "Altura da camada (mm)": "Layer height (mm)", "Largura da linha (mm)": "Line width (mm)", "Paredes": "Walls",
  "Preenchimento (0 a 1)": "Infill (0 to 1)", "Camadas sólidas no topo": "Solid top layers", "Camadas sólidas no fundo": "Solid bottom layers",
  "Velocidade nas paredes (mm/s)": "Wall speed (mm/s)", "Velocidade no preenchimento (mm/s)": "Infill speed (mm/s)", "Diâmetro do filamento (mm)": "Filament diameter (mm)",
  "Bico (°C)": "Nozzle (°C)", "Mesa (°C)": "Bed (°C)", "Valores de partida editáveis, não são dados do material: ajuste à sua impressora.": "Editable starting values, not material data: adjust them to your printer.",
  "Fatiar aqui": "Slice here", "Abra uma peça em Modelo.": "Open a part in Model.", "Camadas": "Layers", "Filamento": "Filament", "Tempo": "Time", "estimativa de pré-projeto": "pre-design estimate",
  "Camada por camada": "Layer by layer", "Ver os números de todas as camadas": "See the numbers for every layer", "Contorno e área por camada": "Outline and area per layer",
  "Camada": "Layer", "Altura (mm)": "Height (mm)", "Contorno (mm)": "Outline (mm)", "Área (mm²)": "Area (mm²)",
  "Avisos da biblioteca": "Library warnings", "O que outras impressões parecidas tiveram de mudar (aprendido com as revisões registradas pelos participantes).": "What similar prints had to change (learned from the revisions recorded by participants).",
  "Ver avisos": "See warnings", "Precisa do computador central.": "Needs the central computer.",
  "Levar para a impressora": "Take it to the printer", "Baixar STL": "Download STL", "Baixar 3MF": "Download 3MF", "Gerar G-code no servidor": "Generate G-code on the server",
  "Sem o computador central: baixe a malha e fatie num fatiador aberto (PrusaSlicer, Cura ou OrcaSlicer).": "Without the central computer: download the mesh and slice it in an open slicer (PrusaSlicer, Cura or OrcaSlicer).",
  "A biblioteca dos participantes fica no computador central: entre pela plataforma ligada a ele.": "The participants' library lives on the central computer: sign in through the platform connected to it.",
  "Carregando a biblioteca…": "Loading the library…", "Participar da biblioteca": "Join the library", "Nome público (pode ser apelido)": "Public name (can be a nickname)",
  "Aceito mostrar este nome nas peças e mensagens que eu publicar.": "I agree to show this name on the parts and messages I publish.", "Participar": "Join",
  "Tirar o meu nome (LGPD)": "Remove my name (LGPD)", "Procurar peças": "Search parts", "Peças da biblioteca": "Library parts", "Peça": "Part", "Autoria": "Author", "Licença": "Licence",
  "Revisões": "Revisions", "Situação": "Status", "Nenhuma peça ainda.": "No parts yet.", "Nova peça": "New part", "Nome": "Name", "Para que serve": "What it is for", "Criar (rascunho)": "Create (draft)",
  "Revisões e memorial": "Revisions and development record", "Revisão": "Revision", "O que mudou": "What changed", "Resultado": "Result", "Arquivo": "File", "Fotos": "Photos", "Integridade": "Integrity",
  "Ver o memorial": "See the development record", "Fórum desta peça": "Forum for this part", "Baixar o memorial (.md)": "Download the development record (.md)",
  "O que mudou nesta revisão": "What changed in this revision", "Enviar a peça aberta como nova revisão": "Send the open part as a new revision", "Resultado da impressão": "Print result",
  "Observação": "Note", "Problemas encontrados": "Problems found", "Registrar o resultado": "Record the result", "Foto real da peça impressa (JPEG ou PNG)": "Real photo of the printed part (JPEG or PNG)",
  "Legenda": "Caption", "Enviar a foto da revisão": "Send the revision photo", "Licença aberta": "Open licence", "Publico esta peça sob a licença escolhida, com o meu nome público.": "I publish this part under the chosen licence, with my public name.",
  "Publicar": "Publish", "Melhorar esta peça (cria uma derivada sua)": "Improve this part (creates your own derivative)", "Marcar como curada": "Mark as curated", "Tirar a curadoria": "Remove curation",
  "Ocultar (moderação)": "Hide (moderation)", "Mostrar de novo": "Show again", "Retirar": "Remove", "curada pela Physis": "curated by Physis", "oculta": "hidden", "retirada": "removed",
  "O fórum fica no computador central.": "The forum lives on the central computer.", "Carregando o fórum…": "Loading the forum…", "Responder": "Reply", "Enviar": "Send",
  "Novo tópico": "New topic", "Título": "Title", "Mensagem": "Message", "Abrir o tópico": "Open the topic", "Ver os gerais": "See the general ones", "Nenhum tópico ainda.": "No topics yet.",
  "Tópicos da peça aberta na Biblioteca.": "Topics for the part open in the Library.",
  "Tópicos gerais. Para falar de uma peça, abra a peça na Biblioteca e use “Fórum desta peça”.": "General topics. To talk about a part, open it in the Library and use “Forum for this part”.",
  "Deu certo": "Worked", "Serviu com defeito": "Usable with defects", "Falhou": "Failed",
  "Empenamento (warping)": "Warping", "Pouca adesão à mesa": "Poor bed adhesion", "Fios (stringing)": "Stringing", "Separação de camadas": "Layer separation", "Subextrusão": "Under-extrusion",
  "Sobre-extrusão": "Over-extrusion", "Balanço ou ponte caiu": "Overhang or bridge sagged", "Medida fora (contração)": "Dimension off (shrinkage)", "Bico entupido": "Clogged nozzle",
  "Bolhas ou umidade no filamento": "Bubbles or moisture in the filament", "Outro problema": "Other problem",
  "Motivo da moderação": "Reason for moderation", "Tirar o seu nome público de tudo? As peças publicadas seguem sob a licença, sem o seu nome.": "Remove your public name from everything? Published parts remain under their licence, without your name.",
  "conferir": "to be checked", "Lendo…": "Reading…", "Cortada.": "Cut.", "De volta ao original.": "Back to the original.", "Na mesa: base em z = 0 e centro no meio.": "On the bed: base at z = 0 and centred.",
  "O corte não deixou nada: confira a altura.": "The cut left nothing: check the height.", "Peça criada como rascunho.": "Part created as a draft.", "Resultado registrado.": "Result recorded.",
  "Foto guardada.": "Photo saved.", "Peça publicada.": "Part published.", "Curadoria atualizada.": "Curation updated.", "Moderação registrada.": "Moderation recorded.", "Tópico aberto.": "Topic opened.",
  "Pronto: você participa da biblioteca.": "Done: you are part of the library.", "Nome removido.": "Name removed.", "Enviando…": "Sending…", "Fatiando no servidor…": "Slicing on the server…",
  "Derivada criada: agora a peça é sua para melhorar.": "Derivative created: the part is now yours to improve.",
  "Ainda há poucos dados": "There is little data yet"
};
window.PHYSIS3D_I18N_RX = [
  ["^Camada (\\d+) de (\\d+): altura ([\\d.,]+) mm, contorno ([\\d.,]+) mm, área ([\\d.,]+) mm²\\.$", "Layer $1 of $2: height $3 mm, outline $4 mm, area $5 mm²."],
  ["^Camada \\(1 a (\\d+)\\)$", "Layer (1 to $1)"],
  ["^Contorno da camada (\\d+)$", "Outline of layer $1"],
  ["^Medidas: (.+)$", "Measurements: $1"],
  ["^de ([\\d.,]+) mm$", "of $1 mm"],
  ["^m · ([\\d.,]+) g$", "m · $1 g"],
  ["^Massa se fosse maciça \\((.+)\\)$", "Mass if solid ($1)"],
  ["^Área em balanço \\(acima de ([\\d.,]+)°\\)$", "Overhang area (above $1°)"],
  ["^([\\d.,]+) % \\(([\\d.,]+) faces\\)$", "$1 % ($2 faces)"],
  ["^(.+): ([\\d.,]+) triângulos\\.$", "$1: $2 triangles."],
  ["^Escala de ([\\d.,]+) %\\.$", "Scale of $1 %."],
  ["^Girada (-?[\\d.,]+)° em ([XYZ])\\.$", "Rotated $1° about $2."],
  ["^Espelhada em ([XYZ])\\.$", "Mirrored in $1."],
  ["^Revisão (\\d+) guardada \\(integridade (\\w+)…\\)\\.$", "Revision $1 saved (integrity $2…)."],
  ["^Em (\\d+) impressões parecidas, (\\d+) tiveram (.+)\\.$", "In $1 similar prints, $2 had $3."],
  ["^\\(probabilidade estimada ([\\d.,]+) %\\)$", "(estimated probability $1 %)"],
  ["^Não consegui ler o arquivo: (.+)$", "Could not read the file: $1"]
];
})();
