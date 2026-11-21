/* physis-imagem-3d.js — da imagem (ou do SVG) para o CAD 2D e o modelo 3D, no navegador, sem internet e sem biblioteca de
   terceiros. Pedido da dona (20/11/2026, Modelagem 3D da InovaSTEM, subaba "Enviar arquivo").
   Contrato:
     window.PhysisImagem3D = {
       mascara(rgba, nx, ny, limiar, inverter)  → Uint8Array nx·ny (1 = material): escuro vira material; transparente = fundo
       contornos(M, nx, ny, celula_mm, tolerancia_celulas) → [[ [x,y], ... ], ...] laços fechados em mm (y para cima),
                                                  pelas bordas das células e simplificados (Douglas-Peucker)
       svg(lacos, largura_mm, altura_mm) / dxf(lacos) → texto do CAD 2D (SVG em mm; DXF R12 com POLYLINE fechadas)
       relevo(M, nx, ny, celula_mm, altura_mm, base_mm) → Float32Array no formato do Physis 3D (9 números por triângulo):
                                                  extrusão das células de material, com base opcional por baixo de tudo
       testes() → peças de teste de impressão geradas aqui (cubo de calibração, balanço, ponte, espessura de parede),
                  cada uma com { id, nome, medidas, observar, T }
       autoteste() → [{ nome, ok, info }]
     }
   Os arquivos STL e 3MF são escritos pelas funções do motor do Physis 3D (window.PHYSIS3D.escreverSTL / escrever3MF);
   este módulo não muda nenhuma função nem conta do motor. Medidas de conferência: PHYSIS3D.medir. */
(function () {
"use strict";

/* ════════ imagem → máscara ════════ */
function mascara(rgba, nx, ny, limiar, inverter) {
  const M = new Uint8Array(nx * ny), L = limiar == null ? 128 : +limiar;
  for (let k = 0; k < nx * ny; k++) {
    const r = rgba[4 * k], g = rgba[4 * k + 1], b = rgba[4 * k + 2], a = rgba[4 * k + 3] / 255;
    const lum = 255 - a * (255 - (0.2126 * r + 0.7152 * g + 0.0722 * b));       // transparente conta como branco
    const escuro = lum < L;
    M[k] = (inverter ? !escuro : escuro) ? 1 : 0;
  }
  return M;
}

/* ════════ máscara → contornos (bordas das células, encadeadas e simplificadas) ════════ */
function dp(pts, tol) {                     // Douglas-Peucker num trecho aberto
  if (pts.length < 3) return pts.slice();
  const a = pts[0], b = pts[pts.length - 1], dx = b[0] - a[0], dy = b[1] - a[1], n = Math.hypot(dx, dy) || 1;
  let im = 0, dm = -1;
  for (let i = 1; i < pts.length - 1; i++) {
    const d = Math.abs(dy * (pts[i][0] - a[0]) - dx * (pts[i][1] - a[1])) / n;
    if (d > dm) { dm = d; im = i; }
  }
  if (dm <= tol) return [a, b];
  const e = dp(pts.slice(0, im + 1), tol), f = dp(pts.slice(im), tol);
  return e.slice(0, -1).concat(f);
}
function simplificarLaco(l, tol) {
  if (l.length < 4 || !(tol > 0)) return l;
  let im = 0, dm = -1;                      // corta o laço no ponto mais longe do primeiro
  for (let i = 1; i < l.length; i++) { const d = Math.hypot(l[i][0] - l[0][0], l[i][1] - l[0][1]); if (d > dm) { dm = d; im = i; } }
  const s = dp(l.slice(0, im + 1), tol).slice(0, -1).concat(dp(l.slice(im).concat([l[0]]), tol).slice(0, -1));
  // o corte pode cair no meio de um lado: tira os pontos que ficaram alinhados com os vizinhos (laço fechado)
  let mudou = true;
  while (mudou && s.length > 3) {
    mudou = false;
    for (let i = 0; i < s.length && s.length > 3; i++) {
      const a = s[(i + s.length - 1) % s.length], b = s[i], c = s[(i + 1) % s.length], dx = c[0] - a[0], dy = c[1] - a[1];
      if (Math.abs(dy * (b[0] - a[0]) - dx * (b[1] - a[1])) / (Math.hypot(dx, dy) || 1) <= tol) { s.splice(i, 1); mudou = true; i--; }
    }
  }
  return s.length >= 3 ? s : l;
}
function contornos(M, nx, ny, cel, tol) {
  cel = cel || 1;
  const on = (i, j) => i >= 0 && j >= 0 && i < nx && j < ny && M[j * nx + i] === 1;
  const prox = new Map(), chave = (x, y) => x + "," + y;
  const add = (x0, y0, x1, y1) => { const k = chave(x0, y0); (prox.get(k) || prox.set(k, []).get(k)).push([x1, y1]); };
  // grade de vértices: x = i, y = ny − j (y para cima); arestas com o material à esquerda
  for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
    if (!on(i, j)) continue;
    const xa = i, xb = i + 1, ya = ny - j - 1, yb = ny - j;
    if (!on(i, j + 1)) add(xa, ya, xb, ya);           // embaixo, para a direita
    if (!on(i + 1, j)) add(xb, ya, xb, yb);           // à direita, para cima
    if (!on(i, j - 1)) add(xb, yb, xa, yb);           // em cima, para a esquerda
    if (!on(i - 1, j)) add(xa, yb, xa, ya);           // à esquerda, para baixo
  }
  const lacos = [];
  for (const [k0] of prox) {
    while ((prox.get(k0) || []).length) {
      const l = []; let k = k0, guarda = 0;
      do {
        const lista = prox.get(k), p = lista.pop(); const xy = k.split(",").map(Number);
        l.push(xy); k = chave(p[0], p[1]);
        if (++guarda > 4 * nx * ny + 8) break;
      } while (k !== k0 && (prox.get(k) || []).length);
      if (l.length >= 3) lacos.push(simplificarLaco(l, tol == null ? 0.5 : tol).map(p => [p[0] * cel, p[1] * cel]));
    }
  }
  return lacos;
}

/* ════════ CAD 2D: SVG e DXF ════════ */
const n4 = v => (Math.round(v * 1e4) / 1e4).toString();
function svg(lacos, largura, altura) {
  const d = lacos.map(l => "M" + l.map(p => n4(p[0]) + " " + n4(altura - p[1])).join(" L") + " Z").join(" ");
  return `<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" width="${n4(largura)}mm" height="${n4(altura)}mm" viewBox="0 0 ${n4(largura)} ${n4(altura)}">`
    + `<path d="${d}" fill="#000000" fill-rule="evenodd"/></svg>\n`;
}
function dxf(lacos) {
  const L = ["0", "SECTION", "2", "HEADER", "9", "$ACADVER", "1", "AC1009", "9", "$INSUNITS", "70", "4", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"];
  lacos.forEach(l => {
    L.push("0", "POLYLINE", "8", "CONTORNO", "66", "1", "70", "1");
    l.forEach(p => L.push("0", "VERTEX", "8", "CONTORNO", "10", n4(p[0]), "20", n4(p[1]), "30", "0"));
    L.push("0", "SEQEND", "8", "CONTORNO");
  });
  L.push("0", "ENDSEC", "0", "EOF");
  return L.join("\r\n") + "\r\n";
}

/* ════════ 3D: faces com a normal pedida (a ordem dos vértices é acertada pela normal) ════════ */
function quad(out, p0, p1, p2, p3, n) {
  const ux = p1[0] - p0[0], uy = p1[1] - p0[1], uz = p1[2] - p0[2], vx = p2[0] - p0[0], vy = p2[1] - p0[1], vz = p2[2] - p0[2];
  const c = [uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx];
  const pts = c[0] * n[0] + c[1] * n[1] + c[2] * n[2] >= 0 ? [p0, p1, p2, p3] : [p3, p2, p1, p0];
  out.push(...pts[0], ...pts[1], ...pts[2], ...pts[0], ...pts[2], ...pts[3]);
}
/* campo de alturas (h por célula, 0 = vazio) → malha fechada */
function campoDeAlturas(H, nx, ny, cel) {
  const out = [], h = (i, j) => (i >= 0 && j >= 0 && i < nx && j < ny) ? H[j * nx + i] : 0;
  // as paredes são cortadas em todos os níveis que existem, para as arestas verticais coincidirem (malha fechada)
  const niveis = Array.from(new Set([0].concat(Array.from(H)))).sort((a, b) => a - b);
  for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
    const z = h(i, j); if (!(z > 0)) continue;
    const x0 = i * cel, x1 = x0 + cel, y0 = (ny - j - 1) * cel, y1 = y0 + cel;
    quad(out, [x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z], [0, 0, 1]);
    quad(out, [x0, y0, 0], [x1, y0, 0], [x1, y1, 0], [x0, y1, 0], [0, 0, -1]);
    const lado = (zv, a, b, n) => { for (let k = 0; k < niveis.length - 1; k++) { const za = niveis[k], zb = niveis[k + 1];
      if (za >= zv && zb <= z) quad(out, [a[0], a[1], za], [b[0], b[1], za], [b[0], b[1], zb], [a[0], a[1], zb], n); } };
    lado(h(i + 1, j), [x1, y0], [x1, y1], [1, 0, 0]);
    lado(h(i - 1, j), [x0, y1], [x0, y0], [-1, 0, 0]);
    lado(h(i, j - 1), [x1, y1], [x0, y1], [0, 1, 0]);       // célula de cima na imagem = +y
    lado(h(i, j + 1), [x0, y0], [x1, y0], [0, -1, 0]);
  }
  return new Float32Array(out);
}
function relevo(M, nx, ny, cel, altura, base) {
  altura = +altura || 0; base = +base || 0;
  if (!(cel > 0) || !(altura > 0 || base > 0)) throw new Error("altura e base não podem ser as duas zero");
  const H = new Float32Array(nx * ny);
  let algum = false;
  for (let k = 0; k < nx * ny; k++) { H[k] = (M[k] ? altura : 0) + base; if (H[k] > 0) algum = true; }
  if (!algum) throw new Error("nenhuma célula de material: ajuste o limiar ou inverta");
  return campoDeAlturas(H, nx, ny, cel);
}

/* ════════ foto: escala de cinza, suavização, limiar automático (Otsu), ruído e fundo ════════ */
function cinza(rgba, n) {
  const g = new Float32Array(n);
  for (let k = 0; k < n; k++) { const a = rgba[4 * k + 3] / 255; g[k] = 255 - a * (255 - (0.2126 * rgba[4 * k] + 0.7152 * rgba[4 * k + 1] + 0.0722 * rgba[4 * k + 2])); }
  return g;
}
/* média em caixa separável, aplicada 3 vezes (aproxima uma gaussiana); raio em células */
function suavizar(g, nx, ny, raio) {
  raio = Math.max(0, Math.round(raio || 0));
  if (!raio) return Float32Array.from(g);
  let a = Float32Array.from(g), b = new Float32Array(g.length);
  for (let it = 0; it < 3; it++) {
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      let s = 0, c = 0; for (let d = -raio; d <= raio; d++) { const x = i + d; if (x >= 0 && x < nx) { s += a[j * nx + x]; c++; } } b[j * nx + i] = s / c; }
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      let s = 0, c = 0; for (let d = -raio; d <= raio; d++) { const y = j + d; if (y >= 0 && y < ny) { s += b[y * nx + i]; c++; } } a[j * nx + i] = s / c; }
  }
  return a;
}
/* limiar de Otsu (1979): o que separa melhor os dois grupos do histograma de 256 tons */
function otsu(g) {
  const h = new Float64Array(256); for (let k = 0; k < g.length; k++) h[Math.max(0, Math.min(255, Math.round(g[k])))]++;
  const n = g.length; let soma = 0; for (let i = 0; i < 256; i++) soma += i * h[i];
  let sB = 0, wB = 0, melhor = 0, lim = 128;
  for (let t = 0; t < 256; t++) {
    wB += h[t]; if (!wB) continue; const wF = n - wB; if (!wF) break;
    sB += t * h[t]; const mB = sB / wB, mF = (soma - sB) / wF, v = wB * wF * (mB - mF) * (mB - mF);
    if (v > melhor) { melhor = v; lim = t + 0.5; }
  }
  return lim;
}
/* componentes ligadas (vizinhança de 4) do valor v; devolve rótulos, tamanhos e se tocam a borda */
function componentes(M, nx, ny, v) {
  const rot = new Int32Array(nx * ny).fill(-1), tam = [], borda = [], pilha = [];
  for (let k = 0; k < nx * ny; k++) {
    if (M[k] !== v || rot[k] >= 0) continue;
    const c = tam.length; tam.push(0); borda.push(false); rot[k] = c; pilha.push(k);
    while (pilha.length) {
      const q = pilha.pop(), i = q % nx, j = (q - i) / nx; tam[c]++;
      if (i === 0 || j === 0 || i === nx - 1 || j === ny - 1) borda[c] = true;
      const viz = [i > 0 ? q - 1 : -1, i < nx - 1 ? q + 1 : -1, j > 0 ? q - nx : -1, j < ny - 1 ? q + nx : -1];
      for (const w of viz) if (w >= 0 && M[w] === v && rot[w] < 0) { rot[w] = c; pilha.push(w); }
    }
  }
  return { rot, tam, borda };
}
/* ruído: tira as manchas de material menores que areaMin células e tapa os furinhos menores que areaMin;
   fundo: tira o material que toca a borda da foto (o fundo escuro em volta da peça); maior: fica só a maior peça */
function limpar(M, nx, ny, op) {
  op = op || {}; const R = Uint8Array.from(M), am = Math.max(0, Math.round(op.areaMin || 0));
  if (op.fundo) { const c = componentes(R, nx, ny, 1); for (let k = 0; k < R.length; k++) if (R[k] && c.borda[c.rot[k]]) R[k] = 0; }
  if (am > 0) {
    let c = componentes(R, nx, ny, 1); for (let k = 0; k < R.length; k++) if (R[k] && c.tam[c.rot[k]] < am) R[k] = 0;
    c = componentes(R, nx, ny, 0); for (let k = 0; k < R.length; k++) if (!R[k] && !c.borda[c.rot[k]] && c.tam[c.rot[k]] < am) R[k] = 1;
  }
  if (op.maior) { const c = componentes(R, nx, ny, 1); let mx = -1, im = -1; c.tam.forEach((t, i) => { if (t > mx) { mx = t; im = i; } });
    for (let k = 0; k < R.length; k++) if (R[k] && c.rot[k] !== im) R[k] = 0; }
  return R;
}
/* tudo junto: foto (RGBA) → máscara pronta; op = { limiar (null = Otsu), inverter, suavizar, areaMin, fundo, maior } */
function processarFoto(rgba, nx, ny, op) {
  op = op || {};
  const g = suavizar(cinza(rgba, nx * ny), nx, ny, op.suavizar || 0), auto = otsu(g);
  const L = op.limiar == null || op.limiar === "" ? auto : +op.limiar, M = new Uint8Array(nx * ny);
  for (let k = 0; k < nx * ny; k++) { const escuro = g[k] < L; M[k] = (op.inverter ? !escuro : escuro) ? 1 : 0; }
  return { M: limpar(M, nx, ny, op), limiar: L, otsu: auto, cinza: g };
}

/* ════════ polígonos: extrusão com furos (recorte de orelhas, com ponte para cada furo) ════════ */
const area2 = l => { let a = 0; for (let i = 0; i < l.length; i++) { const p = l[i], q = l[(i + 1) % l.length]; a += p[0] * q[1] - q[0] * p[1]; } return a / 2; };
function dentro(p, l) { let c = false; for (let i = 0, j = l.length - 1; i < l.length; j = i++) { const a = l[i], b = l[j];
  if ((a[1] > p[1]) !== (b[1] > p[1]) && p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]) c = !c; } return c; }
function cruza(a, b, c, d) {
  const o = (p, q, r) => (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]);
  const d1 = o(c, d, a), d2 = o(c, d, b), d3 = o(a, b, c), d4 = o(a, b, d);
  return ((d1 > 1e-12 && d2 < -1e-12) || (d1 < -1e-12 && d2 > 1e-12)) && ((d3 > 1e-12 && d4 < -1e-12) || (d3 < -1e-12 && d4 > 1e-12));
}
function limparLaco(l) { const o = []; l.forEach(p => { const u = o[o.length - 1]; if (!u || Math.hypot(u[0] - p[0], u[1] - p[1]) > 1e-9) o.push([+p[0], +p[1]]); });
  while (o.length > 2 && Math.hypot(o[0][0] - o[o.length - 1][0], o[0][1] - o[o.length - 1][1]) <= 1e-9) o.pop(); return o; }
/* agrupa laços em peças: cada contorno de fora (sentido anti-horário) com os furos dentro dele (horário) */
function agrupar(lacos) {
  const ls = lacos.map(limparLaco).filter(l => l.length >= 3 && Math.abs(area2(l)) > 1e-9);
  const prof = ls.map((l, i) => ls.reduce((n, m, j) => n + (j !== i && dentro(l[0], m) ? 1 : 0), 0));
  const fora = [];
  ls.forEach((l, i) => { if (prof[i] % 2 === 0) fora.push({ i, l: area2(l) < 0 ? l.slice().reverse() : l, furos: [] }); });
  ls.forEach((l, i) => { if (prof[i] % 2 === 1) {
    let dono = null; fora.forEach(f => { if (dentro(l[0], f.l) && prof[f.i] === prof[i] - 1 && (!dono || Math.abs(area2(f.l)) < Math.abs(area2(dono.l)))) dono = f; });
    if (dono) dono.furos.push(area2(l) > 0 ? l.slice().reverse() : l); } });
  return fora;
}
function costurar(fora, furos) {
  let pol = fora.slice();
  furos.slice().sort((a, b) => Math.max(...b.map(p => p[0])) - Math.max(...a.map(p => p[0]))).forEach(h => {
    let im = 0; h.forEach((p, i) => { if (p[0] > h[im][0]) im = i; });
    const M = h[im], todos = [pol].concat(furos);
    const cand = pol.map((p, i) => [Math.hypot(p[0] - M[0], p[1] - M[1]), i]).sort((a, b) => a[0] - b[0]);
    let iv = cand[0][1];
    for (const [, i] of cand) {
      const V = pol[i]; let livre = true;
      for (const l of todos) { for (let k = 0; k < l.length && livre; k++) { if (cruza(M, V, l[k], l[(k + 1) % l.length])) livre = false; } if (!livre) break; }
      if (livre) { iv = i; break; }
    }
    const volta = h.slice(im).concat(h.slice(0, im + 1));
    pol = pol.slice(0, iv + 1).concat(volta, [pol[iv]], pol.slice(iv + 1));
  });
  return pol;
}
function orelhas(pol) {
  const idx = pol.map((_, i) => i), tris = [], P = pol, conv = (a, b, c) => (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) > 1e-12;
  const dentroTri = (p, a, b, c) => { const s = (x, y, z) => (y[0] - x[0]) * (z[1] - x[1]) - (y[1] - x[1]) * (z[0] - x[0]);
    return s(a, b, p) >= -1e-12 && s(b, c, p) >= -1e-12 && s(c, a, p) >= -1e-12; };
  let guarda = 0;
  while (idx.length > 3 && guarda++ < 100000) {
    let achou = false;
    for (let k = 0; k < idx.length; k++) {
      const ia = idx[(k + idx.length - 1) % idx.length], ib = idx[k], ic = idx[(k + 1) % idx.length], a = P[ia], b = P[ib], c = P[ic];
      if (!conv(a, b, c)) continue;
      let vazio = true;
      for (const j of idx) { if (j === ia || j === ib || j === ic) continue; const p = P[j];
        if ((p[0] === a[0] && p[1] === a[1]) || (p[0] === b[0] && p[1] === b[1]) || (p[0] === c[0] && p[1] === c[1])) continue;
        if (dentroTri(p, a, b, c)) { vazio = false; break; } }
      if (vazio) { tris.push([a, b, c]); idx.splice(k, 1); achou = true; break; }
    }
    if (!achou) { const ia = idx[0], ib = idx[1], ic = idx[2]; tris.push([P[ia], P[ib], P[ic]]); idx.splice(1, 1); }   // laço ruim: segue sem travar
  }
  if (idx.length === 3) tris.push([P[idx[0]], P[idx[1]], P[idx[2]]]);
  return tris;
}
/* laços fechados (mm; furos pela paridade) → sólido de altura h (z de 0 a h), no formato do Physis 3D */
function extrudar(lacos, h) {
  h = +h; if (!(h > 0)) throw new Error("a altura da extrusão precisa ser maior que zero");
  const out = [];
  agrupar(lacos).forEach(g => {
    orelhas(costurar(g.l, g.furos)).forEach(([a, b, c]) => { out.push(a[0], a[1], h, b[0], b[1], h, c[0], c[1], h, a[0], a[1], 0, c[0], c[1], 0, b[0], b[1], 0); });
    [g.l].concat(g.furos).forEach(l => l.forEach((p, i) => { const q = l[(i + 1) % l.length], n = [q[1] - p[1], -(q[0] - p[0]), 0];
      quad(out, [p[0], p[1], 0], [q[0], q[1], 0], [q[0], q[1], h], [p[0], p[1], h], n); }));
  });
  if (!out.length) throw new Error("nenhum contorno fechado para extrudar");
  return new Float32Array(out);
}
/* formas paramétricas (mm), centradas na origem */
const PRIM = {
  retangulo: (w, d) => [[[-w / 2, -d / 2], [w / 2, -d / 2], [w / 2, d / 2], [-w / 2, d / 2]]],
  circulo: (diam, n) => { n = Math.max(8, Math.round(n || 48)); const r = diam / 2, l = []; for (let i = 0; i < n; i++) { const a = 2 * Math.PI * i / n; l.push([r * Math.cos(a), r * Math.sin(a)]); } return [l]; },
  chapaComFuro: (w, d, furo) => { if (!(furo > 0 && furo < Math.min(w, d))) throw new Error("o furo precisa ser menor que a chapa"); return PRIM.retangulo(w, d).concat([PRIM.circulo(furo, 48)[0].reverse()]); },
  perfil: (tipo, a, b, e) => { if (!(e > 0 && e < Math.min(a, b))) throw new Error("a espessura precisa ser menor que as abas");
    if (tipo === "L") return [[[0, 0], [a, 0], [a, e], [e, e], [e, b], [0, b]]];
    if (tipo === "U") return [[[0, 0], [a, 0], [a, b], [a - e, b], [a - e, e], [e, e], [e, b], [0, b]]];
    if (tipo === "T") return [[[0, b - e], [(a - e) / 2, b - e], [(a - e) / 2, 0], [(a + e) / 2, 0], [(a + e) / 2, b - e], [a, b - e], [a, b], [0, b]]];
    throw new Error("perfil: L, U ou T"); }
};

/* ════════ DXF 2D: LINE, LWPOLYLINE, POLYLINE, CIRCLE e ARC → laços fechados e linhas abertas (mm) ════════ */
function lerDxf(texto) {
  const L = String(texto).replace(/\r/g, "").split("\n"), pares = [];
  for (let i = 0; i + 1 < L.length; i += 2) pares.push([parseInt(L[i], 10), L[i + 1].trim()]);
  const ents = []; let sec = "", e = null;
  pares.forEach(([c, v]) => {
    if (c === 0) { if (e) ents.push(e); e = null;
      if (v === "SECTION" || v === "ENDSEC" || v === "EOF") { sec = v === "SECTION" ? "?" : ""; return; }
      if (sec === "ENTITIES") e = { tipo: v, c: [] }; return; }
    if (c === 2 && sec === "?") { sec = v; return; }
    if (e) e.c.push([c, v]);
  });
  if (e) ents.push(e);
  const g = (en, cod) => { const x = en.c.find(p => p[0] === cod); return x ? parseFloat(x[1]) : 0; };
  const fechados = [], abertos = [], segs = [], avisos = new Set();
  let poli = null;
  ents.forEach(en => {
    if (en.tipo === "LINE") segs.push([[g(en, 10), g(en, 20)], [g(en, 11), g(en, 21)]]);
    else if (en.tipo === "LWPOLYLINE") { const pts = [], fl = g(en, 70); let x = null;
      en.c.forEach(([c, v]) => { if (c === 10) x = parseFloat(v); if (c === 20 && x != null) { pts.push([x, parseFloat(v)]); x = null; } if (c === 42 && parseFloat(v)) avisos.add("arcos dentro de polilinhas (bulge) viram retas"); });
      ((fl & 1) ? fechados : abertos).push(pts); }
    else if (en.tipo === "POLYLINE") poli = { pts: [], fechada: (g(en, 70) & 1) === 1 };
    else if (en.tipo === "VERTEX" && poli) poli.pts.push([g(en, 10), g(en, 20)]);
    else if (en.tipo === "SEQEND" && poli) { (poli.fechada ? fechados : abertos).push(poli.pts); poli = null; }
    else if (en.tipo === "CIRCLE") { const l = PRIM.circulo(2 * g(en, 40), 64)[0].map(p => [p[0] + g(en, 10), p[1] + g(en, 20)]); fechados.push(l); }
    else if (en.tipo === "ARC") { const r = g(en, 40), a0 = g(en, 50) * Math.PI / 180; let a1 = g(en, 51) * Math.PI / 180; if (a1 <= a0) a1 += 2 * Math.PI;
      const n = Math.max(4, Math.ceil((a1 - a0) / (Math.PI / 32))), pts = []; for (let i = 0; i <= n; i++) { const a = a0 + (a1 - a0) * i / n; pts.push([g(en, 10) + r * Math.cos(a), g(en, 20) + r * Math.sin(a)]); }
      segs.push(pts); }
    else if (["TEXT", "MTEXT", "DIMENSION", "HATCH", "INSERT", "SPLINE", "ELLIPSE", "POINT"].indexOf(en.tipo) >= 0) avisos.add(en.tipo + " ainda não é lido (fica de fora)");
  });
  // encadeia linhas e arcos soltos pelos pontos das pontas
  const k = p => Math.round(p[0] * 1e4) + "," + Math.round(p[1] * 1e4), usados = new Set();
  segs.forEach((s0, i0) => {
    if (usados.has(i0)) return; usados.add(i0); let cad = s0.slice(), mudou = true;
    while (mudou) { mudou = false;
      for (let i = 0; i < segs.length; i++) { if (usados.has(i)) continue; const s = segs[i], ini = k(cad[0]), fim = k(cad[cad.length - 1]);
        if (k(s[0]) === fim) cad = cad.concat(s.slice(1)); else if (k(s[s.length - 1]) === fim) cad = cad.concat(s.slice(0, -1).reverse());
        else if (k(s[s.length - 1]) === ini) cad = s.slice(0, -1).concat(cad); else if (k(s[0]) === ini) cad = s.slice(1).reverse().concat(cad); else continue;
        usados.add(i); mudou = true; } }
    if (cad.length > 3 && k(cad[0]) === k(cad[cad.length - 1])) fechados.push(cad.slice(0, -1)); else abertos.push(cad);
  });
  const unid = pares.findIndex(p => p[0] === 9 && p[1] === "$INSUNITS");
  return { lacos: fechados.filter(l => l.length >= 3), linhas: abertos.filter(l => l.length >= 2), avisos: Array.from(avisos),
    unidade: unid >= 0 && pares[unid + 1] ? ({ 1: "polegada", 4: "mm", 5: "cm", 6: "m" }[parseInt(pares[unid + 1][1], 10)] || "") : "" };
}

/* ════════ transformação, caixas e colisão simples ════════ */
function caixaDe(T) { const mn = [Infinity, Infinity, Infinity], mx = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < T.length; i += 3) for (let k = 0; k < 3; k++) { const v = T[i + k]; if (v < mn[k]) mn[k] = v; if (v > mx[k]) mx[k] = v; } return { min: mn, max: mx }; }
/* p' = R(rot em graus, z·y·x) · (p − pivô) · escala + pivô + posição */
function transformar(T, pos, rot, esc, pivo) {
  pos = pos || [0, 0, 0]; rot = rot || [0, 0, 0]; esc = esc == null ? 1 : +esc; pivo = pivo || [0, 0, 0];
  const r = rot.map(g => g * Math.PI / 180), [cx, cy, cz] = r.map(Math.cos), [sx, sy, sz] = r.map(Math.sin);
  const R = [[cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx], [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx], [-sy, cy * sx, cy * cx]];
  const o = new Float32Array(T.length), inv = esc < 0;
  for (let i = 0; i < T.length; i += 3) { const x = (T[i] - pivo[0]) * esc, y = (T[i + 1] - pivo[1]) * esc, z = (T[i + 2] - pivo[2]) * esc;
    for (let k = 0; k < 3; k++) o[i + k] = R[k][0] * x + R[k][1] * y + R[k][2] * z + pivo[k] + pos[k]; }
  if (inv) for (let i = 0; i < o.length; i += 9) for (let k = 0; k < 3; k++) { const t = o[i + 3 + k]; o[i + 3 + k] = o[i + 6 + k]; o[i + 6 + k] = t; }
  return o;
}
function juntar(lista) { let n = 0; lista.forEach(T => n += T.length); const o = new Float32Array(n); let k = 0; lista.forEach(T => { o.set(T, k); k += T.length; }); return o; }
/* pares de itens cujas caixas se cruzam (encostar não conta); itens = [{ nome, T }] */
function colisoes(itens, folga) {
  folga = folga == null ? 0.01 : folga; const cx = itens.map(it => caixaDe(it.T)), out = [];
  for (let a = 0; a < itens.length; a++) for (let b = a + 1; b < itens.length; b++) {
    const A = cx[a], B = cx[b]; let cruzam = true, vol = 1;
    for (let k = 0; k < 3; k++) { const s = Math.min(A.max[k], B.max[k]) - Math.max(A.min[k], B.min[k]); if (s <= folga) { cruzam = false; break; } vol *= s; }
    if (cruzam) out.push({ a, b, volume_mm3: vol });
  }
  return out;
}

/* ════════ 3MF de montagem (um objeto por peça, com cor) e IFC4 do modelo editado ════════ */
let TAB_CRC = null;
function crc32(b) { if (!TAB_CRC) { TAB_CRC = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; TAB_CRC[n] = c >>> 0; } }
  let c = 0xFFFFFFFF; for (let i = 0; i < b.length; i++) c = TAB_CRC[(c ^ b[i]) & 255] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; }
/* ZIP sem compressão (método 0), como o 3MF aceita */
function zipGuardado(arquivos) {
  const enc = new TextEncoder(), partes = [], central = []; let pos = 0;
  arquivos.forEach(([nome, dados]) => {
    const n = enc.encode(nome), d = typeof dados === "string" ? enc.encode(dados) : dados, crc = crc32(d);
    const h = new DataView(new ArrayBuffer(30)); h.setUint32(0, 0x04034b50, true); h.setUint16(4, 20, true); h.setUint32(14, crc, true);
    h.setUint32(18, d.length, true); h.setUint32(22, d.length, true); h.setUint16(26, n.length, true);
    const c = new DataView(new ArrayBuffer(46)); c.setUint32(0, 0x02014b50, true); c.setUint16(4, 20, true); c.setUint16(6, 20, true); c.setUint32(16, crc, true);
    c.setUint32(20, d.length, true); c.setUint32(24, d.length, true); c.setUint16(28, n.length, true); c.setUint32(42, pos, true);
    partes.push(new Uint8Array(h.buffer), n, d); central.push(new Uint8Array(c.buffer), n); pos += 30 + n.length + d.length;
  });
  const tc = central.reduce((s, x) => s + x.length, 0), f = new DataView(new ArrayBuffer(22));
  f.setUint32(0, 0x06054b50, true); f.setUint16(8, arquivos.length, true); f.setUint16(10, arquivos.length, true); f.setUint32(12, tc, true); f.setUint32(16, pos, true);
  const tudo = partes.concat(central, [new Uint8Array(f.buffer)]), out = new Uint8Array(tudo.reduce((s, x) => s + x.length, 0)); let k = 0;
  tudo.forEach(x => { out.set(x, k); k += x.length; }); return out;
}
const xmlEsc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;" }[c]));
const NS3MF = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02";
function escrever3MFMontagem(itens) {
  const cores = itens.map(it => /^#[0-9A-Fa-f]{6}$/.test(it.cor || "") ? it.cor.toUpperCase() : "#D9D3C2");
  let objs = "", build = "";
  itens.forEach((it, o) => {
    const vs = [], idx = new Map(), ts = [], T = it.T, ch = i => T[i].toFixed(4) + "," + T[i + 1].toFixed(4) + "," + T[i + 2].toFixed(4);
    for (let i = 0; i < T.length; i += 9) { const t = [];
      for (let k = 0; k < 3; k++) { const c = ch(i + 3 * k); let j = idx.get(c); if (j == null) { j = vs.length; idx.set(c, j); vs.push(`<vertex x="${T[i + 3 * k]}" y="${T[i + 3 * k + 1]}" z="${T[i + 3 * k + 2]}"/>`); } t.push(j); }
      if (t[0] !== t[1] && t[1] !== t[2] && t[0] !== t[2]) ts.push(`<triangle v1="${t[0]}" v2="${t[1]}" v3="${t[2]}"/>`); }
    objs += `<object id="${o + 2}" type="model" name="${xmlEsc(it.nome)}" pid="1" pindex="${o}"><mesh><vertices>${vs.join("")}</vertices><triangles>${ts.join("")}</triangles></mesh></object>`;
    build += `<item objectid="${o + 2}"/>`;
  });
  const mats = itens.map((it, o) => `<base name="${xmlEsc(it.material || it.nome)}" displaycolor="${cores[o]}"/>`).join("");
  const modelo = `<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="pt-BR" xmlns="${NS3MF}"><metadata name="Application">Physis 3D · montagem</metadata><resources><basematerials id="1">${mats}</basematerials>${objs}</resources><build>${build}</build></model>`;
  return zipGuardado([["[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>'],
    ["_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'],
    ["3D/3dmodel.model", modelo]]);
}
/* IFC4 (texto STEP) do modelo editado: um IfcBuildingElementProxy por objeto, com a malha em IfcTriangulatedFaceSet (mm).
   As propriedades e a estrutura do IFC original não vão junto: é a geometria do que foi modelado aqui. */
function guidIfc() { const A = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$"; let s = A[Math.floor(Math.random() * 4)];
  for (let i = 0; i < 21; i++) s += A[Math.floor(Math.random() * 64)]; return s; }
function escreverIfc(objetos, nomeProjeto) {
  const L = [], add = t => { L.push(t); return "#" + L.length; }, q = s => "'" + String(s == null ? "" : s).replace(/[^\x20-\x7E]/g, "_").replace(/'/g, "''") + "'";
  const pessoa = add("IFCPERSON($,$,'',$,$,$,$,$)"), org = add("IFCORGANIZATION($,'InovaSTEM',$,$,$)"), po = add(`IFCPERSONANDORGANIZATION(${pessoa},${org},$)`);
  const app = add(`IFCAPPLICATION(${org},'0.1','Physis 3D - Modelagem 3D','physis3d')`), dono = add(`IFCOWNERHISTORY(${po},${app},$,.ADDED.,$,$,$,0)`);
  const mm = add("IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.)"), un = add(`IFCUNITASSIGNMENT((${mm}))`);
  const o0 = add("IFCCARTESIANPOINT((0.,0.,0.))"), ax = add(`IFCAXIS2PLACEMENT3D(${o0},$,$)`);
  const ctx = add(`IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.E-05,${ax},$)`), sub = add(`IFCGEOMETRICREPRESENTATIONSUBCONTEXT('Body','Model',*,*,*,*,${ctx},$,.MODEL_VIEW.,$)`);
  const prj = add(`IFCPROJECT('${guidIfc()}',${dono},${q(nomeProjeto || "Modelagem 3D")},$,$,$,$,(${ctx}),${un})`);
  const lp = add(`IFCLOCALPLACEMENT($,${ax})`);
  const site = add(`IFCSITE('${guidIfc()}',${dono},'Terreno',$,$,${lp},$,$,.ELEMENT.,$,$,$,$,$)`);
  const pred = add(`IFCBUILDING('${guidIfc()}',${dono},'Edificacao',$,$,${lp},$,$,.ELEMENT.,$,$,$)`);
  const pav = add(`IFCBUILDINGSTOREY('${guidIfc()}',${dono},'Pavimento',$,$,${lp},$,$,.ELEMENT.,0.)`);
  add(`IFCRELAGGREGATES('${guidIfc()}',${dono},$,$,${prj},(${site}))`); add(`IFCRELAGGREGATES('${guidIfc()}',${dono},$,$,${site},(${pred}))`);
  add(`IFCRELAGGREGATES('${guidIfc()}',${dono},$,$,${pred},(${pav}))`);
  const els = [];
  objetos.forEach(ob => {
    const T = ob.T, vs = [], idx = new Map(), fs = [], ch = i => T[i].toFixed(3) + "," + T[i + 1].toFixed(3) + "," + T[i + 2].toFixed(3);
    for (let i = 0; i < T.length; i += 9) { const t = []; for (let k = 0; k < 3; k++) { const c = ch(i + 3 * k); let j = idx.get(c); if (j == null) { j = vs.length + 1; idx.set(c, j); vs.push("(" + [T[i + 3 * k], T[i + 3 * k + 1], T[i + 3 * k + 2]].map(v => (+v).toFixed(3)).join(",") + ")"); } t.push(j); }
      if (t[0] !== t[1] && t[1] !== t[2] && t[0] !== t[2]) fs.push("(" + t.join(",") + ")"); }
    if (!fs.length) return;
    const pts = add(`IFCCARTESIANPOINTLIST3D((${vs.join(",")}))`), fset = add(`IFCTRIANGULATEDFACESET(${pts},$,.T.,(${fs.join(",")}),$)`);
    const rep = add(`IFCSHAPEREPRESENTATION(${sub},'Body','Tessellation',(${fset}))`), pds = add(`IFCPRODUCTDEFINITIONSHAPE($,$,(${rep}))`);
    const lpe = add(`IFCLOCALPLACEMENT(${lp},${ax})`);
    els.push(add(`IFCBUILDINGELEMENTPROXY('${guidIfc()}',${dono},${q(ob.nome)},${q(ob.descricao || "")},$,${lpe},${pds},$,$)`));
  });
  if (els.length) add(`IFCRELCONTAINEDINSPATIALSTRUCTURE('${guidIfc()}',${dono},$,$,(${els.join(",")}),${pav})`);
  const hoje = new Date().toISOString().slice(0, 19);
  return "ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('ViewDefinition [ReferenceView]'),'2;1');\nFILE_NAME(" + q((nomeProjeto || "modelo") + ".ifc") + ",'" + hoje + "',(''),(''),'Physis 3D','Physis 3D','');\nFILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\n"
    + L.map((t, i) => "#" + (i + 1) + "=" + t + ";").join("\n") + "\nENDSEC;\nEND-ISO-10303-21;\n";
}

/* cores do guia para peças e montagens (nada de azul) */
const CORES_PECA = [["verde", "Verde profundo", "Deep green", "#0B3D2E"], ["laranja", "Laranja", "Orange", "#F97316"], ["terracota", "Terracota", "Terracotta", "#BB6B4A"],
  ["creme", "Creme", "Cream", "#F4F1EA"], ["areia", "Areia", "Sand", "#D9D3C2"], ["carvao", "Carvão", "Charcoal", "#1B1F23"], ["oliva", "Verde-oliva", "Olive green", "#4A5A47"]];

/* ════════ peças de teste de impressão (geradas aqui; nada copiado de terceiros) ════════ */
function caixa(out, x0, y0, z0, dx, dy, dz) {
  const x1 = x0 + dx, y1 = y0 + dy, z1 = z0 + dz;
  quad(out, [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1], [0, 0, 1]);
  quad(out, [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0], [0, 0, -1]);
  quad(out, [x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1], [1, 0, 0]);
  quad(out, [x0, y0, z0], [x0, y1, z0], [x0, y1, z1], [x0, y0, z1], [-1, 0, 0]);
  quad(out, [x0, y1, z0], [x1, y1, z0], [x1, y1, z1], [x0, y1, z1], [0, 1, 0]);
  quad(out, [x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1], [0, -1, 0]);
}
/* prisma de perfil convexo no plano XZ (pontos no sentido anti-horário visto de −Y), estendido de y0 a y1 */
function prismaXZ(out, perfil, y0, y1) {
  const n = perfil.length, cx = perfil.reduce((s, p) => s + p[0], 0) / n, cz = perfil.reduce((s, p) => s + p[1], 0) / n;
  for (let k = 1; k < n - 1; k++) {
    const a = perfil[0], b = perfil[k], c = perfil[k + 1];
    for (const [y, s] of [[y0, -1], [y1, 1]]) {
      const tri = [[a[0], y, a[1]], [b[0], y, b[1]], [c[0], y, c[1]]];
      const u = [tri[1][0] - tri[0][0], 0, tri[1][2] - tri[0][2]], v = [tri[2][0] - tri[0][0], 0, tri[2][2] - tri[0][2]];
      const ny_ = u[2] * v[0] - u[0] * v[2];
      (ny_ * s >= 0 ? tri : tri.reverse()).forEach(p => out.push(...p));
    }
  }
  for (let k = 0; k < n; k++) {
    const a = perfil[k], b = perfil[(k + 1) % n], mx = (a[0] + b[0]) / 2 - cx, mz = (a[1] + b[1]) / 2 - cz;
    const ex = b[0] - a[0], ez = b[1] - a[1];
    let nx_ = ez, nz_ = -ex; if (nx_ * mx + nz_ * mz < 0) { nx_ = -nx_; nz_ = -nz_; }
    quad(out, [a[0], y0, a[1]], [b[0], y0, b[1]], [b[0], y1, b[1]], [a[0], y1, a[1]], [nx_, 0, nz_]);
  }
}
const BLOCOS = "Feita de blocos fechados encostados uns nos outros (o fatiador junta os blocos). ";
function testes() {
  const P = window.PHYSIS3D, lista = [];
  lista.push({ id: "cubo-calibracao-20mm", nome: "Cubo de calibração de 20 mm", en: { nome: "20 mm calibration cube", medidas: "Solid 20 × 20 × 20 mm cube.", observar: "Measure X, Y and Z with calipers: 20.0 mm is expected. The difference shows material shrinkage or extrusion flow; also look at the first layer and the corners." },
    medidas: "Cubo maciço de 20 × 20 × 20 mm.",
    observar: "Meça X, Y e Z com paquímetro: o esperado é 20,0 mm. A diferença mostra contração do material ou fluxo de extrusão; olhe também a primeira camada e os cantos.",
    T: P && P.cubo ? P.cubo(20) : (() => { const o = []; caixa(o, 0, 0, 0, 20, 20, 20); return new Float32Array(o); })() });
  { const o = []; caixa(o, 0, 0, 0, 60, 20, 2);
    [30, 45, 60].forEach((ang, k) => { const x = 4 + 19 * k, h = 15, w = 5, t = Math.tan(ang * Math.PI / 180);
      prismaXZ(o, [[x, 2], [x + w, 2], [x + w + h * t * 0.5, 2 + h * 0.5], [x, 2 + h * 0.5]], 5, 15); });
    lista.push({ id: "teste-balanco-30-45-60", nome: "Teste de balanço (30°, 45° e 60°)", en: { nome: "Overhang test (30°, 45° and 60°)", medidas: "Made of closed blocks touching each other (the slicer joins them). 60 × 20 × 2 mm base with three 7.5 mm tall, 10 mm deep ramps whose underside leans 30°, 45° and 60° from vertical.", observar: "See from which angle the underside gets rough, stringy or drooping. Physis 3D shows overhangs above 45° in red (view option)." },
      medidas: BLOCOS + "Base de 60 × 20 × 2 mm com três rampas de 7,5 mm de altura, 10 mm de profundidade e a face de baixo inclinada a 30°, 45° e 60° da vertical.",
      observar: "Veja a partir de qual ângulo a face de baixo fica áspera, com fios soltos ou caída. O Physis 3D marca em vermelho o balanço acima de 45° (opção da vista).",
      T: new Float32Array(o) }); }
  { const o = []; caixa(o, 0, 0, 0, 90, 10, 2); let x = 0;
    const vaos = [10, 20, 30]; caixa(o, x, 0, 2, 5, 10, 10);
    vaos.forEach(v => { x += 5 + v; caixa(o, x, 0, 2, 5, 10, 10); });
    caixa(o, 0, 0, 12, x + 5, 10, 1.5);
    lista.push({ id: "teste-ponte-10-20-30mm", nome: "Teste de ponte (vãos de 10, 20 e 30 mm)", en: { nome: "Bridging test (10, 20 and 30 mm spans)", medidas: "Made of closed blocks touching each other (the slicer joins them). 90 × 10 × 2 mm base, four 5 × 10 × 10 mm pillars and a 1.5 mm slab on top, with clear spans of 10, 20 and 30 mm.", observar: "See how much the underside of the slab sags in the middle of each span and whether the strands are taut or loose." },
      medidas: BLOCOS + "Base de 90 × 10 × 2 mm, quatro pilares de 5 × 10 × 10 mm e uma laje de 1,5 mm por cima, com vãos livres de 10, 20 e 30 mm.",
      observar: "Veja quanto a face de baixo da laje cede no meio de cada vão e se os fios ficam esticados ou soltos.",
      T: new Float32Array(o) }); }
  { const o = []; caixa(o, 0, 0, 0, 50, 20, 1.5);
    [0.4, 0.8, 1.2, 1.6, 2.0].forEach((e, k) => caixa(o, 4 + 9.5 * k, 2.5, 1.5, e, 15, 10));
    lista.push({ id: "teste-espessura-parede", nome: "Teste de espessura de parede (0,4 a 2,0 mm)", en: { nome: "Wall thickness test (0.4 to 2.0 mm)", medidas: "Made of closed blocks touching each other (the slicer joins them). 50 × 20 × 1.5 mm base with five 15 × 10 mm walls, 0.4, 0.8, 1.2, 1.6 and 2.0 mm thick.", observar: "See which walls come out whole and measure each one. A wall thinner than the nozzle (0.4 mm in the Physis 3D default setup) may disappear in the slicer." },
      medidas: BLOCOS + "Base de 50 × 20 × 1,5 mm com cinco paredes de 15 × 10 mm e espessuras de 0,4, 0,8, 1,2, 1,6 e 2,0 mm.",
      observar: "Veja quais paredes saem inteiras e meça cada uma. Parede mais fina que o bico (0,4 mm na configuração padrão do Physis 3D) pode sumir no fatiador.",
      T: new Float32Array(o) }); }
  return lista;
}

/* ════════ autoteste (no navegador) ════════ */
function autoteste() {
  const r = [], ok = (nome, c, info) => r.push({ nome, ok: !!c, info: info == null ? "" : String(info) }), P = window.PHYSIS3D;
  // quadrado 4 × 4 de material numa imagem 6 × 6
  const nx = 6, ny = 6, rgba = new Uint8ClampedArray(nx * ny * 4).fill(255);
  for (let j = 1; j < 5; j++) for (let i = 1; i < 5; i++) { const k = 4 * (j * nx + i); rgba[k] = rgba[k + 1] = rgba[k + 2] = 0; }
  const M = mascara(rgba, nx, ny, 128, false);
  ok("máscara: 16 células de material", M.reduce((s, v) => s + v, 0) === 16);
  ok("inverter troca material e fundo", mascara(rgba, nx, ny, 128, true).reduce((s, v) => s + v, 0) === 20);
  const L = contornos(M, nx, ny, 2, 0.5);
  ok("contorno do quadrado: 1 laço de 4 cantos", L.length === 1 && L[0].length === 4, JSON.stringify(L));
  ok("contorno em mm (célula de 2 mm: lado 8 mm)", L.length && Math.max(...L[0].map(p => p[0])) - Math.min(...L[0].map(p => p[0])) === 8);
  const furo = M.slice(); furo[2 * nx + 2] = 0;
  ok("furo vira um segundo laço", contornos(furo, nx, ny, 1, 0.5).length === 2);
  ok("DXF com POLYLINE fechada", /POLYLINE[\s\S]*70\r\n1[\s\S]*SEQEND[\s\S]*EOF/.test(dxf(L)));
  ok("SVG com o caminho", svg(L, 12, 12).indexOf('fill-rule="evenodd"') > 0);
  const T = relevo(M, nx, ny, 2, 3, 0);
  if (P && P.medir) {
    const m = P.medir(T);
    ok("relevo: volume 8 × 8 × 3 = 192 mm³", Math.abs(m.volume_mm3 - 192) < 1e-6, m.volume_mm3);
    ok("relevo: malha fechada e orientada", m.arestas && m.arestas.fechada && m.volume_sinal === 1, JSON.stringify(m.arestas));
    const Tb = relevo(M, nx, ny, 2, 3, 1), mb = P.medir(Tb);
    ok("com base de 1 mm: 12 × 12 × 1 + 192 = 336 mm³", Math.abs(mb.volume_mm3 - 336) < 1e-6, mb.volume_mm3);
    ok("com base: malha fechada", mb.arestas && mb.arestas.fechada, JSON.stringify(mb.arestas));
    const deg = M.slice(); deg[1 * nx + 1] = 0; deg[3 * nx + 3] = 0;     // alturas diferentes nas bordas
    const md = P.medir(relevo(deg, nx, ny, 1, 2, 0.5));
    ok("bordas com alturas diferentes: sem aresta aberta", md.arestas.abertas === 0 && md.arestas.orientacao_trocada === 0, JSON.stringify(md.arestas));
    const ts = testes();
    ok("quatro peças de teste", ts.length === 4);
    const vol = { "cubo-calibracao-20mm": 8000, "teste-ponte-10-20-30mm": 90 * 10 * 2 + 4 * 5 * 10 * 10 + 80 * 10 * 1.5,
      "teste-espessura-parede": 50 * 20 * 1.5 + (0.4 + 0.8 + 1.2 + 1.6 + 2.0) * 15 * 10 };
    ts.forEach(t => { const mt = P.medir(t.T);
      ok(t.nome + ": volume positivo" + (vol[t.id] ? " e igual ao desenho" : ""), mt.volume_mm3 > 0 && (vol[t.id] == null || Math.abs(mt.volume_mm3 - vol[t.id]) < 1e-3), mt.volume_mm3);
      ok(t.nome + ": STL escrito pelo motor", P.escreverSTL(t.T, t.id).byteLength === 84 + 50 * t.T.length / 9); });
  } else ok("motor do Physis 3D presente", false);
  // foto: Otsu num histograma de dois tons, ruído e fundo
  const fx = 20, fy = 20, foto = new Uint8ClampedArray(fx * fy * 4).fill(255);
  for (let j = 0; j < fy; j++) for (let i = 0; i < fx; i++) { const k = 4 * (j * fx + i), dentroQ = i >= 5 && i < 15 && j >= 5 && j < 15, borda = i < 2;
    const v = dentroQ || borda ? 40 : 220; foto[k] = foto[k + 1] = foto[k + 2] = v; }
  foto[4 * (1 * fx + 18)] = foto[4 * (1 * fx + 18) + 1] = foto[4 * (1 * fx + 18) + 2] = 30;              // um ponto de ruído
  const pf = processarFoto(foto, fx, fy, { suavizar: 0, areaMin: 3, fundo: true });
  ok("Otsu entre os dois tons", pf.otsu > 40 && pf.otsu < 220, pf.otsu);
  ok("foto: fica só a peça (ruído e fundo da borda tirados)", pf.M.reduce((s, v) => s + v, 0) === 100, pf.M.reduce((s, v) => s + v, 0));
  ok("foto: um contorno da peça", contornos(pf.M, fx, fy, 1, 0.5).length === 1);
  // extrusão com furo: chapa 40 × 30 com furo de 10 mm
  const Tch = extrudar(PRIM.chapaComFuro(40, 30, 10), 5), vch = 40 * 30 * 5 - 5 * 48 / 2 * 25 * Math.sin(2 * Math.PI / 48);
  if (P && P.medir) { const mc = P.medir(Tch);
    ok("chapa com furo: volume da chapa menos o furo", Math.abs(mc.volume_mm3 - vch) < 1e-2, mc.volume_mm3);
    ok("chapa com furo: malha fechada", mc.arestas.fechada && mc.volume_sinal === 1, JSON.stringify(mc.arestas));
    const ml = P.medir(extrudar(PRIM.perfil("L", 30, 20, 3), 50));
    ok("perfil L: volume (30 + 20 − 3) × 3 × 50", Math.abs(ml.volume_mm3 - 47 * 3 * 50) < 1e-2 && ml.arestas.fechada, ml.volume_mm3); }
  const dx = "0\nSECTION\n2\nENTITIES\n0\nLINE\n8\n0\n10\n0\n20\n0\n11\n10\n21\n0\n0\nLINE\n8\n0\n10\n10\n20\n0\n11\n10\n21\n10\n0\nLINE\n8\n0\n10\n10\n20\n10\n11\n0\n21\n10\n0\nLINE\n8\n0\n10\n0\n20\n10\n11\n0\n21\n0\n0\nCIRCLE\n8\n0\n10\n50\n20\n0\n40\n5\n0\nENDSEC\n0\nEOF\n";
  const ld = lerDxf(dx);
  ok("DXF: quatro linhas viram um laço e o círculo outro", ld.lacos.length === 2 && ld.linhas.length === 0, JSON.stringify(ld.lacos.map(l => l.length)));
  ok("DXF de volta: lido pelo próprio leitor", lerDxf(dxf([[[0, 0], [10, 0], [10, 10]]])).lacos.length === 1);
  const c1 = { nome: "a", T: transformar(extrudar(PRIM.retangulo(10, 10), 10), [0, 0, 0]) }, c2 = { nome: "b", T: transformar(c1.T, [5, 0, 0]) }, c3 = { nome: "c", T: transformar(c1.T, [10, 0, 0]) };
  const co = colisoes([c1, c2, c3]);
  ok("colisão por caixas: a×b e b×c se cruzam; a e c só encostam", co.length === 2 && co[0].a === 0 && co[0].b === 1 && co[1].a === 1 && co[1].b === 2, JSON.stringify(co));
  const z3 = escrever3MFMontagem([{ nome: "a", T: c1.T, cor: "#0B3D2E" }, { nome: "b", T: c3.T, cor: "#F97316" }]);
  ok("3MF da montagem é ZIP com duas peças", z3[0] === 0x50 && z3[1] === 0x4B && new TextDecoder().decode(z3).split("<object ").length === 3);
  const ifc = escreverIfc([{ nome: "Caixa", T: c1.T }], "teste");
  ok("IFC4 com IfcTriangulatedFaceSet", /FILE_SCHEMA\(\('IFC4'\)\)/.test(ifc) && ifc.indexOf("IFCTRIANGULATEDFACESET") > 0 && ifc.indexOf("IFCBUILDINGELEMENTPROXY") > 0);
  return r;
}

window.PhysisImagem3D = { mascara, contornos, svg, dxf, relevo, campoDeAlturas, testes, autoteste, cinza, suavizar, otsu, limpar, processarFoto,
  extrudar, PRIM, lerDxf, caixaDe, transformar, juntar, colisoes, escrever3MFMontagem, escreverIfc, CORES_PECA, versao: "physis-imagem-3d-0.2" };
})();
