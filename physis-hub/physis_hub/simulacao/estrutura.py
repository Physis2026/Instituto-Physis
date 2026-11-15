"""Estrutura linear (FEA), Fase 1 (espelho de SIMULACAO.estrutura em sistema/physis-simulacao.js).

- portico: treliça e pórtico 2D (3 GL por nó) e 3D (6 GL por nó), elementos de barra (só axial) e de viga de
  Euler-Bernoulli; apoios, cargas nos nós, carga distribuída no elemento e peso próprio. Resultados: deslocamentos,
  reações, esforços (normal, cortante, momento, torção) e tensão normal máxima (N/A + M·c/I).
- euler: carga crítica de flambagem π²EI/(K·L)², K da premissa sim.estrutura.k_flambagem.
- verificar: tensão contra a admissível (fy/FS) e compressão contra a flambagem/FS; sem valor de material, [MARCADOR].
- cst: estado plano de tensões com triângulos de deformação constante (CST), e malha_de_mascara para cortes de peças.
- carga_vento: método da pressão dinâmica (ABNT NBR 6123 nomeada; os fatores são digitados [CONFERIR NA NORMA]).
- empuxo_rotor: força no topo da torre da turbina pela teoria do disco atuador.
Sistemas resolvidos por eliminação de Gauss em banda (matriz de rigidez simétrica positiva definida após os apoios).
"""
from __future__ import annotations

import math

from .comum import FaltaDado, MARCADOR, premissa, resultado, usada

G_PADRAO = 9.81


# ── seções ──
def secao(s: dict) -> dict:
    """{tipo: retangulo, b, h} | {tipo: circular, d} | {tipo: tubo, d, t} | {A, Iz, Iy?, J?, cy?, cz?} (em m)."""
    t = s.get("tipo")
    if t == "retangulo":
        b, h = float(s["b"]), float(s["h"])
        a, c = max(b, h), min(b, h)
        j = a * c ** 3 * (1 / 3 - 0.21 * (c / a) * (1 - c ** 4 / (12 * a ** 4)))
        return {"A": b * h, "Iz": b * h ** 3 / 12, "Iy": h * b ** 3 / 12, "J": j, "cy": h / 2, "cz": b / 2}
    if t == "circular":
        d = float(s["d"])
        i = math.pi * d ** 4 / 64
        return {"A": math.pi * d * d / 4, "Iz": i, "Iy": i, "J": 2 * i, "cy": d / 2, "cz": d / 2}
    if t == "tubo":
        d, e = float(s["d"]), float(s["t"])
        di = d - 2 * e
        i = math.pi * (d ** 4 - di ** 4) / 64
        return {"A": math.pi * (d * d - di * di) / 4, "Iz": i, "Iy": i, "J": 2 * i, "cy": d / 2, "cz": d / 2}
    out = {"A": float(s["A"]), "Iz": float(s.get("Iz", s.get("I", 0.0)))}
    out["Iy"] = float(s.get("Iy", out["Iz"]))
    out["J"] = float(s.get("J", out["Iz"] + out["Iy"]))
    out["cy"] = float(s.get("cy", s.get("c", 0.0)))
    out["cz"] = float(s.get("cz", out["cy"]))
    return out


def material_estrutural(mid: str | None) -> dict:
    tab = premissa("sim.estrutura.materiais") or {}
    return dict(tab.get(mid) or {}) if mid else {}


# ── solver em banda ──
def resolver_banda(A: list, b: list) -> list:
    """Gauss sem pivoteamento só dentro da banda (A simétrica positiva definida). A e b são alterados."""
    n = len(b)
    bw = 0
    for i in range(n):
        row = A[i]
        for j in range(n - 1, i, -1):
            if row[j] != 0.0:
                if j - i > bw:
                    bw = j - i
                break
    for c in range(n):
        piv = A[c][c]
        if abs(piv) < 1e-300 or piv != piv:
            raise FaltaDado("estrutura instável: faltam apoios ou ligações (pivô nulo)")
        fim = min(n, c + bw + 1)
        Ac = A[c]
        for r in range(c + 1, fim):
            Ar = A[r]
            f = Ar[c] / piv
            if f != 0.0:
                for k in range(c, fim):
                    Ar[k] -= f * Ac[k]
                b[r] -= f * b[c]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = b[i]
        Ai = A[i]
        for k in range(i + 1, min(n, i + bw + 1)):
            s -= Ai[k] * x[k]
        x[i] = s / Ai[i]
    return x


# ── pórtico / treliça ──
def _rot(dim, xi, xj, ref):
    d = [xj[k] - xi[k] for k in range(dim)]
    L = math.sqrt(sum(v * v for v in d))
    if L <= 0:
        raise FaltaDado("elemento de comprimento zero")
    if dim == 2:
        c, s = d[0] / L, d[1] / L
        return L, [[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]]
    ex = [v / L for v in d]
    v = list(ref) if ref else [0.0, 0.0, 1.0]
    dot = sum(v[k] * ex[k] for k in range(3))
    yv = [v[k] - dot * ex[k] for k in range(3)]
    ny = math.sqrt(sum(a * a for a in yv))
    if ny < 1e-9:
        v = [0.0, 1.0, 0.0]
        dot = sum(v[k] * ex[k] for k in range(3))
        yv = [v[k] - dot * ex[k] for k in range(3)]
        ny = math.sqrt(sum(a * a for a in yv))
    ey = [a / ny for a in yv]
    ez = [ex[1] * ey[2] - ex[2] * ey[1], ex[2] * ey[0] - ex[0] * ey[2], ex[0] * ey[1] - ex[1] * ey[0]]
    return L, [ex, ey, ez]


def _k_local(dim, tipo, E, G, sc, L):
    n = 6 if dim == 2 else 12
    k = [[0.0] * n for _ in range(n)]
    nd = n // 2

    def put(i, j, v):
        k[i][j] += v
        if i != j:
            k[j][i] += v
    ea = E * sc["A"] / L
    put(0, 0, ea); put(0, nd, -ea); put(nd, nd, ea)
    if tipo == "barra":
        return k
    if dim == 2:
        ei = E * sc["Iz"]
        put(1, 1, 12 * ei / L ** 3); put(1, 2, 6 * ei / L ** 2); put(1, 4, -12 * ei / L ** 3); put(1, 5, 6 * ei / L ** 2)
        put(2, 2, 4 * ei / L); put(2, 4, -6 * ei / L ** 2); put(2, 5, 2 * ei / L)
        put(4, 4, 12 * ei / L ** 3); put(4, 5, -6 * ei / L ** 2); put(5, 5, 4 * ei / L)
        return k
    gj = G * sc["J"] / L
    put(3, 3, gj); put(3, 9, -gj); put(9, 9, gj)
    ez = E * sc["Iz"]
    put(1, 1, 12 * ez / L ** 3); put(1, 5, 6 * ez / L ** 2); put(1, 7, -12 * ez / L ** 3); put(1, 11, 6 * ez / L ** 2)
    put(5, 5, 4 * ez / L); put(5, 7, -6 * ez / L ** 2); put(5, 11, 2 * ez / L)
    put(7, 7, 12 * ez / L ** 3); put(7, 11, -6 * ez / L ** 2); put(11, 11, 4 * ez / L)
    ey = E * sc["Iy"]
    put(2, 2, 12 * ey / L ** 3); put(2, 4, -6 * ey / L ** 2); put(2, 8, -12 * ey / L ** 3); put(2, 10, -6 * ey / L ** 2)
    put(4, 4, 4 * ey / L); put(4, 8, 6 * ey / L ** 2); put(4, 10, 2 * ey / L)
    put(8, 8, 12 * ey / L ** 3); put(8, 10, 6 * ey / L ** 2); put(10, 10, 4 * ey / L)
    return k


def _f_fixo(dim, tipo, q, L):
    """Forças de engastamento perfeito (no elemento, eixos locais) para carga uniforme q = [qx, qy(, qz)] por metro."""
    qx, qy = q[0], q[1]
    qz = q[2] if dim == 3 else 0.0
    if dim == 2:
        if tipo == "barra":
            return [qx * L / 2, qy * L / 2, 0.0, qx * L / 2, qy * L / 2, 0.0]
        return [qx * L / 2, qy * L / 2, qy * L * L / 12, qx * L / 2, qy * L / 2, -qy * L * L / 12]
    if tipo == "barra":
        return [qx * L / 2, qy * L / 2, qz * L / 2, 0, 0, 0, qx * L / 2, qy * L / 2, qz * L / 2, 0, 0, 0]
    return [qx * L / 2, qy * L / 2, qz * L / 2, 0.0, -qz * L * L / 12, qy * L * L / 12,
            qx * L / 2, qy * L / 2, qz * L / 2, 0.0, qz * L * L / 12, -qy * L * L / 12]


def _T(R, nd):
    """Matriz de transformação (blocos 3×3 de R na diagonal)."""
    n = nd * 2
    T = [[0.0] * n for _ in range(n)]
    for b in range(n // 3):
        for i in range(3):
            for j in range(3):
                T[3 * b + i][3 * b + j] = R[i][j]
    return T


def portico(p: dict) -> dict:
    """p: dim (2|3); nos [[x, y(, z)]] (m); elementos [{i, j, tipo 'viga'|'barra', E (Pa), G?, secao{…},
    q [qx, qy(, qz)] local (N/m), ref [vx, vy, vz] (3D), material (id de sim.estrutura.materiais)}];
    apoios [{no, restr [0/1 por GL]}]; cargas [{no, F [..] global (N, N·m)}];
    peso_proprio {rho (kg/m³) ou do material, g} (gravidade em −y no 2D e −z no 3D)."""
    dim = int(p.get("dim", 2))
    nd = 3 if dim == 2 else 6
    nos = p["nos"]
    nn = len(nos)
    ng = nn * nd
    K = [[0.0] * ng for _ in range(ng)]
    F = [0.0] * ng
    for c in p.get("cargas") or []:
        for k, v in enumerate(c["F"]):
            F[c["no"] * nd + k] += float(v)
    els = []
    pp = p.get("peso_proprio")
    for e in p["elementos"]:
        mat = material_estrutural(e.get("material"))
        E = e.get("E", mat.get("E_Pa"))
        if E is None:
            raise FaltaDado(f"{MARCADOR} módulo de elasticidade E do elemento {e['i']}-{e['j']} (material '{e.get('material')}')")
        E = float(E)
        G = float(e.get("G", mat.get("G_Pa") or E / 2.6))
        sc = secao(e["secao"])
        tipo = e.get("tipo", "viga")
        L, R = _rot(dim, nos[e["i"]], nos[e["j"]], e.get("ref"))
        kl = _k_local(dim, tipo, E, G, sc, L)
        q = list(e.get("q") or [0.0] * (dim if dim == 3 else 2))
        while len(q) < (3 if dim == 3 else 2):
            q.append(0.0)
        if pp:
            rho = pp.get("rho", mat.get("densidade"))
            if rho is None:
                raise FaltaDado(f"{MARCADOR} densidade para o peso próprio")
            w = float(rho) * float(pp.get("g", G_PADRAO)) * sc["A"]
            gvec = [0.0, -w] if dim == 2 else [0.0, 0.0, -w]
            for a in range(len(q)):
                q[a] += sum(R[a][b] * gvec[b] for b in range(dim))
        ff = _f_fixo(dim, tipo, q, L)
        T = _T(R, nd)
        dofs = [e["i"] * nd + k for k in range(nd)] + [e["j"] * nd + k for k in range(nd)]
        n = 2 * nd
        # Kg = Tᵀ·k·T ; Fg = Tᵀ·ff
        kT = [[sum(kl[i][m] * T[m][j] for m in range(n)) for j in range(n)] for i in range(n)]
        for i in range(n):
            Fi = 0.0
            for m in range(n):
                Fi += T[m][i] * ff[m]
            F[dofs[i]] += Fi
            for j in range(n):
                s = 0.0
                for m in range(n):
                    s += T[m][i] * kT[m][j]
                K[dofs[i]][dofs[j]] += s
        els.append({"e": e, "L": L, "R": R, "T": T, "k": kl, "ff": ff, "q": q, "sc": sc, "E": E, "tipo": tipo, "dofs": dofs, "mat": mat})
    restr = [False] * ng
    for a in p.get("apoios") or []:
        for k, v in enumerate(a["restr"]):
            if v:
                restr[a["no"] * nd + k] = True
    auto = []
    for d in range(ng):
        if not restr[d] and K[d][d] == 0.0:
            restr[d] = True
            auto.append(d)
    livres = [d for d in range(ng) if not restr[d]]
    idx = {d: i for i, d in enumerate(livres)}
    Kr = [[K[a][b] for b in livres] for a in livres]
    Fr = [F[a] for a in livres]
    ur = resolver_banda(Kr, Fr) if livres else []
    u = [0.0] * ng
    for d, i in idx.items():
        u[d] = ur[i]
    reac = []
    for d in range(ng):
        if restr[d] and d not in auto:
            reac.append({"no": d // nd, "gl": d % nd, "valor": sum(K[d][m] * u[m] for m in range(ng)) - F[d]})
    res_el = []
    for el in els:
        n = 2 * nd
        ug = [u[d] for d in el["dofs"]]
        ul = [sum(el["T"][i][m] * ug[m] for m in range(n)) for i in range(n)]
        f = [sum(el["k"][i][m] * ul[m] for m in range(n)) - el["ff"][i] for i in range(n)]
        L, q, sc = el["L"], el["q"], el["sc"]
        pts = []
        for s in range(11):
            x = L * s / 10
            N = -f[0] - q[0] * x
            if dim == 2:
                Mz = -f[2] + f[1] * x + q[1] * x * x / 2 if el["tipo"] != "barra" else 0.0
                pts.append({"x": x, "N": N, "V": f[1] + q[1] * x, "M": Mz})
            else:
                if el["tipo"] != "barra":
                    Mz = -f[5] + f[1] * x + q[1] * x * x / 2
                    My = -f[4] - f[2] * x - q[2] * x * x / 2
                else:
                    Mz = My = 0.0
                pts.append({"x": x, "N": N, "Vy": f[1] + q[1] * x, "Vz": f[2] + q[2] * x, "T": -f[3], "My": My, "Mz": Mz})
        if dim == 2:
            sig = max(abs(t["N"]) / sc["A"] + (abs(t["M"]) * sc["cy"] / sc["Iz"] if sc["Iz"] else 0.0) for t in pts)
            mmax = max(abs(t["M"]) for t in pts)
        else:
            sig = max(abs(t["N"]) / sc["A"] + (abs(t["Mz"]) * sc["cy"] / sc["Iz"] if sc["Iz"] else 0.0)
                      + (abs(t["My"]) * sc["cz"] / sc["Iy"] if sc["Iy"] else 0.0) for t in pts)
            mmax = max(math.hypot(t["My"], t["Mz"]) for t in pts)
        res_el.append({"i": el["e"]["i"], "j": el["e"]["j"], "tipo": el["tipo"], "L": L, "N": -f[0], "N_j": f[nd],
                       "M_max": mmax, "sigma_max": sig, "f_local": f, "diagrama": pts, "material": el["e"].get("material"),
                       "E": el["E"], "I_min": min(sc["Iz"], sc["Iy"]) if dim == 3 else sc["Iz"], "A": sc["A"]})
    avisos = []
    if auto:
        avisos.append(f"{len(auto)} giros sem rigidez (nós só de barras) foram travados automaticamente")
    desl = [u[i * nd:(i + 1) * nd] for i in range(nn)]
    dmax = max((math.sqrt(sum(d[k] ** 2 for k in range(dim))) for d in desl), default=0.0)
    return resultado(
        f"Elementos finitos lineares, {'pórtico' if any(e['tipo'] != 'barra' for e in els) else 'treliça'} {dim}D (barra axial + viga de Euler-Bernoulli)",
        ["material elástico linear", "pequenos deslocamentos (1ª ordem)", "seções planas permanecem planas",
         "ligações ideais (rótula ou engaste)", "sem cisalhamento na flexão (Euler-Bernoulli)"],
        [usada("sim.estrutura.materiais")] if any(e["mat"] for e in els) else [],
        {"nos": nn, "elementos": len(els), "graus_de_liberdade": ng, "livres": len(livres)},
        "Primeira ordem: não pega efeito P-Δ, flambagem local, ligações semirrígidas nem fadiga. Bambu e madeira "
        "variam muito por peça: use valores de ensaio. Confira a combinação de ações na norma do material.",
        {"deslocamentos": desl, "desl_max": dmax, "reacoes": reac, "elementos": res_el}, avisos)


def euler(E: float, I: float, L: float, apoio: str = "biapoiada", K: float | None = None) -> dict:
    kt = premissa("sim.estrutura.k_flambagem") or {}
    if K is None:
        K = kt.get(apoio)
    if K is None:
        raise FaltaDado(f"{MARCADOR} coeficiente K de flambagem para '{apoio}'")
    pcr = math.pi ** 2 * E * I / (K * L) ** 2
    return resultado("Flambagem elástica de Euler: Pcr = π²·E·I/(K·L)²", ["barra reta ideal, carga centrada", "regime elástico"],
                     [usada("sim.estrutura.k_flambagem", K)], None,
                     "Só barras esbeltas (flambagem elástica); barras curtas falham por esmagamento antes. "
                     "Imperfeições reduzem a carga real: a norma do material dá a curva de projeto.",
                     {"pcr": pcr, "K": K, "apoio": apoio})


def verificar(res: dict, apoio_flambagem: str = "biapoiada") -> dict:
    """Utilização de cada elemento: σ_max ÷ (fy/FS) e, em compressão, |N| ÷ (Pcr/FS_flambagem)."""
    fs = premissa("sim.estrutura.fs_tensao")
    fsb = premissa("sim.estrutura.fs_flambagem")
    linhas = []
    for e in res["elementos"]:
        mat = material_estrutural(e.get("material"))
        fy = mat.get("fy_Pa")
        lin = {"i": e["i"], "j": e["j"], "material": e.get("material"), "sigma_max": e["sigma_max"]}
        if fy is None or fs is None:
            lin["tensao"] = f"{MARCADOR} tensão admissível (fy do material ou FS)"
            lin["util_tensao"] = None
        else:
            lin["util_tensao"] = e["sigma_max"] / (fy / fs)
        N = min(e["N"], e["N_j"])
        if N < 0 and e["I_min"] > 0 and fsb is not None:
            pcr = euler(e["E"], e["I_min"], e["L"], apoio_flambagem)["pcr"]
            lin["pcr"] = pcr
            lin["util_flambagem"] = -N / (pcr / fsb)
        lin["ok"] = all(v is not None and v <= 1.0 for v in (lin.get("util_tensao"), lin.get("util_flambagem", 0.0)))
        linhas.append(lin)
    return resultado("Verificação por tensões admissíveis (σ ≤ fy/FS) e flambagem de Euler (|N| ≤ Pcr/FS)",
                     ["cargas características (sem majorar)", "comprimento de flambagem = comprimento do elemento × K"],
                     [usada("sim.estrutura.fs_tensao"), usada("sim.estrutura.fs_flambagem"), usada("sim.estrutura.materiais")],
                     None, "Triagem. O dimensionamento final segue a norma do material (aço, madeira, bambu, alumínio).",
                     {"linhas": linhas, "todos_ok": all(l["ok"] for l in linhas)})


# ── cargas de vento e de rotor ──
def carga_vento(area: float, cf: float | None = None, v0: float | None = None, s1: float | None = None,
                s2: float | None = None, s3: float | None = None) -> dict:
    """Método da pressão dinâmica (ABNT NBR 6123, nomeada; fatores [CONFERIR NA NORMA]): Vk = V0·S1·S2·S3;
    q = coef·Vk² (Pa); F = Cf·q·A. Fatores ausentes viram [MARCADOR]."""
    pv = premissa("sim.vento.pressao_dinamica") or {}
    v = {"v0": v0 if v0 is not None else pv.get("v0"), "s1": s1 if s1 is not None else pv.get("s1"),
         "s2": s2 if s2 is not None else pv.get("s2"), "s3": s3 if s3 is not None else pv.get("s3"),
         "cf": cf if cf is not None else pv.get("cf"), "coef": pv.get("coef_q")}
    faltam = [k for k, x in v.items() if x is None]
    if faltam:
        raise FaltaDado(f"{MARCADOR} {', '.join(faltam)} (pressão de vento: digite da norma, [CONFERIR NA NORMA])")
    vk = v["v0"] * v["s1"] * v["s2"] * v["s3"]
    q = v["coef"] * vk * vk
    return resultado("Pressão dinâmica do vento (método da ABNT NBR 6123, nomeado; valores digitados [CONFERIR NA NORMA])",
                     ["vento estático equivalente", "coeficiente de força único para a peça"],
                     [usada("sim.vento.pressao_dinamica", v)], None,
                     "Sem efeitos dinâmicos (vórtices, ressonância). Fatores S1, S2, S3 e Cf vêm da norma.",
                     {"vk": vk, "q_pa": q, "forca_n": v["cf"] * q * area})


def empuxo_rotor(diametro: float, v: float, rho: float = 1.225, ct: float | None = None) -> dict:
    ct = premissa("sim.turbinas.ct_empuxo") if ct is None else ct
    if ct is None:
        raise FaltaDado(f"{MARCADOR} coeficiente de empuxo C_T")
    a = math.pi * diametro ** 2 / 4
    return resultado("Teoria do disco atuador: F = ½·ρ·A·v²·C_T", ["rotor como disco", "vento uniforme"],
                     [usada("sim.turbinas.ct_empuxo", ct)], None,
                     "Para a velocidade de sobrevivência use a força com o rotor parado e o arrasto da torre (fabricante).",
                     {"forca_n": 0.5 * rho * a * v * v * ct, "area": a})


# ── CST (estado plano de tensões) ──
def malha_de_mascara(mascara: list, nx: int, ny: int, dx: float, dy: float, x0: float = 0.0, y0: float = 0.0) -> dict:
    """Cada célula ativa vira 2 triângulos (diagonal de baixo-esquerda para cima-direita). Linha 0 = topo."""
    ids = {}
    nos = []

    def no(i, j):          # canto (linha i de cantos, coluna j), i = 0 no topo
        k = (i, j)
        if k not in ids:
            ids[k] = len(nos)
            nos.append([x0 + j * dx, y0 + (ny - i) * dy])
        return ids[k]
    tris = []
    for i in range(ny):
        for j in range(nx):
            if mascara[i * nx + j]:
                a, b, c, d = no(i + 1, j), no(i + 1, j + 1), no(i, j + 1), no(i, j)
                tris.append([a, b, c])
                tris.append([a, c, d])
    return {"nos": nos, "tris": tris, "id_canto": {f"{i},{j}": v for (i, j), v in ids.items()}}


def cst(p: dict) -> dict:
    """p: nos [[x, y]], tris [[a, b, c]] (anti-horário), E (Pa), nu, t (m); apoios [{no, restr [ux, uy]}];
    cargas [{no, F [fx, fy]}]; material (id) opcional para E."""
    mat = material_estrutural(p.get("material"))
    E = p.get("E", mat.get("E_Pa"))
    nu = p.get("nu", mat.get("nu"))
    if E is None or nu is None:
        raise FaltaDado(f"{MARCADOR} E e ν do material da peça (ensaio da oficina)")
    E, nu, t = float(E), float(nu), float(p["t"])
    nos, tris = p["nos"], p["tris"]
    ng = 2 * len(nos)
    K = [[0.0] * ng for _ in range(ng)]
    F = [0.0] * ng
    c0 = E / (1 - nu * nu)
    D = [[c0, c0 * nu, 0.0], [c0 * nu, c0, 0.0], [0.0, 0.0, c0 * (1 - nu) / 2]]
    Bs = []
    for tr in tris:
        (x1, y1), (x2, y2), (x3, y3) = (nos[k] for k in tr)
        A2 = (x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1)
        if A2 <= 0:
            raise FaltaDado("triângulo com área nula ou no sentido horário")
        B = [[(y2 - y3) / A2, 0.0, (y3 - y1) / A2, 0.0, (y1 - y2) / A2, 0.0],
             [0.0, (x3 - x2) / A2, 0.0, (x1 - x3) / A2, 0.0, (x2 - x1) / A2],
             [(x3 - x2) / A2, (y2 - y3) / A2, (x1 - x3) / A2, (y3 - y1) / A2, (x2 - x1) / A2, (y1 - y2) / A2]]
        DB = [[sum(D[i][m] * B[m][j] for m in range(3)) for j in range(6)] for i in range(3)]
        dofs = [2 * tr[0], 2 * tr[0] + 1, 2 * tr[1], 2 * tr[1] + 1, 2 * tr[2], 2 * tr[2] + 1]
        f = t * A2 / 2
        for i in range(6):
            for j in range(6):
                K[dofs[i]][dofs[j]] += f * (B[0][i] * DB[0][j] + B[1][i] * DB[1][j] + B[2][i] * DB[2][j])
        Bs.append((B, dofs, A2 / 2))
    for c in p.get("cargas") or []:
        F[2 * c["no"]] += float(c["F"][0])
        F[2 * c["no"] + 1] += float(c["F"][1])
    restr = [False] * ng
    for a in p.get("apoios") or []:
        for k, v in enumerate(a["restr"]):
            if v:
                restr[2 * a["no"] + k] = True
    livres = [d for d in range(ng) if not restr[d]]
    ur = resolver_banda([[K[a][b] for b in livres] for a in livres], [F[a] for a in livres])
    u = [0.0] * ng
    for i, d in enumerate(livres):
        u[d] = ur[i]
    tens = []
    for B, dofs, area in Bs:
        ue = [u[d] for d in dofs]
        eps = [sum(B[i][j] * ue[j] for j in range(6)) for i in range(3)]
        s = [sum(D[i][m] * eps[m] for m in range(3)) for i in range(3)]
        vm = math.sqrt(s[0] ** 2 - s[0] * s[1] + s[1] ** 2 + 3 * s[2] ** 2)
        en = 0.5 * t * area * sum(s[i] * eps[i] for i in range(3))
        tens.append({"sx": s[0], "sy": s[1], "txy": s[2], "von_mises": vm, "energia": en, "area": area})
    reac = [{"no": d // 2, "gl": d % 2, "valor": sum(K[d][m] * u[m] for m in range(ng)) - F[d]} for d in range(ng) if restr[d]]
    desl = [[u[2 * i], u[2 * i + 1]] for i in range(len(nos))]
    return resultado("Elementos finitos 2D, estado plano de tensões, triângulo de deformação constante (CST)",
                     ["material elástico linear e isótropo", "pequenas deformações", "espessura constante t"],
                     [usada("sim.estrutura.materiais")] if mat else [],
                     {"nos": len(nos), "triangulos": len(tris), "graus_de_liberdade": ng},
                     "CST é rígido demais em flexão com poucos elementos na altura: refine e compare. Peça impressa é "
                     "anisotrópica (camadas): E e resistência entre camadas são menores [CONFERIR com ensaio].",
                     {"deslocamentos": desl, "tensoes": tens, "reacoes": reac,
                      "von_mises_max": max((x["von_mises"] for x in tens), default=0.0),
                      "desl_max": max((math.hypot(*d) for d in desl), default=0.0)})
