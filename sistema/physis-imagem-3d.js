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
  lista.push({ id: "cubo-calibracao-20mm", nome: "Cubo de calibração de 20 mm",
    medidas: "Cubo maciço de 20 × 20 × 20 mm.",
    observar: "Meça X, Y e Z com paquímetro: o esperado é 20,0 mm. A diferença mostra contração do material ou fluxo de extrusão; olhe também a primeira camada e os cantos.",
    T: P && P.cubo ? P.cubo(20) : (() => { const o = []; caixa(o, 0, 0, 0, 20, 20, 20); return new Float32Array(o); })() });
  { const o = []; caixa(o, 0, 0, 0, 60, 20, 2);
    [30, 45, 60].forEach((ang, k) => { const x = 4 + 19 * k, h = 15, w = 5, t = Math.tan(ang * Math.PI / 180);
      prismaXZ(o, [[x, 2], [x + w, 2], [x + w + h * t * 0.5, 2 + h * 0.5], [x, 2 + h * 0.5]], 5, 15); });
    lista.push({ id: "teste-balanco-30-45-60", nome: "Teste de balanço (30°, 45° e 60°)",
      medidas: BLOCOS + "Base de 60 × 20 × 2 mm com três rampas de 7,5 mm de altura, 10 mm de profundidade e a face de baixo inclinada a 30°, 45° e 60° da vertical.",
      observar: "Veja a partir de qual ângulo a face de baixo fica áspera, com fios soltos ou caída. O Physis 3D marca em vermelho o balanço acima de 45° (opção da vista).",
      T: new Float32Array(o) }); }
  { const o = []; caixa(o, 0, 0, 0, 90, 10, 2); let x = 0;
    const vaos = [10, 20, 30]; caixa(o, x, 0, 2, 5, 10, 10);
    vaos.forEach(v => { x += 5 + v; caixa(o, x, 0, 2, 5, 10, 10); });
    caixa(o, 0, 0, 12, x + 5, 10, 1.5);
    lista.push({ id: "teste-ponte-10-20-30mm", nome: "Teste de ponte (vãos de 10, 20 e 30 mm)",
      medidas: BLOCOS + "Base de 90 × 10 × 2 mm, quatro pilares de 5 × 10 × 10 mm e uma laje de 1,5 mm por cima, com vãos livres de 10, 20 e 30 mm.",
      observar: "Veja quanto a face de baixo da laje cede no meio de cada vão e se os fios ficam esticados ou soltos.",
      T: new Float32Array(o) }); }
  { const o = []; caixa(o, 0, 0, 0, 50, 20, 1.5);
    [0.4, 0.8, 1.2, 1.6, 2.0].forEach((e, k) => caixa(o, 4 + 9.5 * k, 2.5, 1.5, e, 15, 10));
    lista.push({ id: "teste-espessura-parede", nome: "Teste de espessura de parede (0,4 a 2,0 mm)",
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
  return r;
}

window.PhysisImagem3D = { mascara, contornos, svg, dxf, relevo, campoDeAlturas, testes, autoteste, versao: "physis-imagem-3d-0.1" };
})();
