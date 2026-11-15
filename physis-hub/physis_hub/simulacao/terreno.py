"""Terreno e hidrologia na grade do terreno, Fase 1 (espelho de SIMULACAO.terreno em sistema/physis-simulacao.js).

Grade: {nx, ny, dx, dy (m), z [ny·nx], linha 0 = norte (topo)}; None = sem dado. A grade do Mapeamento
(mapeamento.ler_asc_janela: {nx, ny, cs, valores, lat0}, em graus) entra por grade_do_mapeamento().
- declividade_aspecto: método de Horn (3×3); aspecto em graus a partir do norte, sentido horário.
- d8: direção de escoamento para o vizinho de maior queda/distância; células sem saída = −1 (depressão ou borda).
- acumulacao: células a montante (incluindo a própria), em ordem decrescente de cota.
- scs_cn: escoamento superficial (mm) pelo método do número de curva (CN por uso do solo = premissa).
- usle: perda de solo A = R·K·LS·C·P; fatores sem valor viram [MARCADOR] (nada inventado).
- visada: o que se vê de um ponto (linha de visada sobre a grade).
Usos: Mapeamento (relevo), Resiliência (encosta, enxurrada), Água (onde captar), SbN (onde plantar, valas de
infiltração em nível): veja docs/SIMULACAO.md.
"""
from __future__ import annotations

import math

from .comum import FaltaDado, MARCADOR, premissa, resultado, usada

# vizinhos D8: (di, dj) na ordem L, SE, S, SO, O, NO, N, NE (i cresce para o sul)
VIZ = ((0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1))


def grade_do_mapeamento(j: dict) -> dict:
    """Converte a grade em graus do Mapeamento para metros na latitude do lote (mesma regra de declividade_raster)."""
    lat_m = j["lat0"] - j["ny"] * j["cs"] / 2
    return {"nx": j["nx"], "ny": j["ny"], "dx": j["cs"] * 111320 * math.cos(math.radians(lat_m)), "dy": j["cs"] * 110540,
            "z": list(j["valores"])}


def grade_da_geometria(geo: dict) -> dict:
    """Terreno do contrato physis-geometria-lugar/1 (mapeamento.geometria_para_simulacao / painel
    geometriaParaSimulacao, chave physis-geometria-lugar): Z[j·nx + i] com j do sul para o norte → linha 0 = norte."""
    t = (geo or {}).get("terreno")
    if not t:
        raise FaltaDado("geometria do lugar sem terreno (desenhe ou importe o relevo no Mapeamento)")
    nx, ny = int(t["nx"]), int(t["ny"])
    Z = t["Z"]
    return {"nx": nx, "ny": ny, "dx": float(t["cs"]), "dy": float(t["cs"]),
            "z": [Z[(ny - 1 - i) * nx + j] for i in range(ny) for j in range(nx)]}


def _z(g, i, j):
    if 0 <= i < g["ny"] and 0 <= j < g["nx"]:
        return g["z"][i * g["nx"] + j]
    return None


def declividade_aspecto(g: dict) -> dict:
    nx, ny, dx, dy = g["nx"], g["ny"], float(g["dx"]), float(g["dy"])
    dec, asp = [None] * (nx * ny), [None] * (nx * ny)
    for i in range(ny):
        for j in range(nx):
            z0 = _z(g, i, j)
            if z0 is None:
                continue
            w = [[_z(g, i + a, j + b) for b in (-1, 0, 1)] for a in (-1, 0, 1)]
            for a in range(3):                  # borda ou sem dado: repete a própria célula
                for b in range(3):
                    if w[a][b] is None:
                        w[a][b] = z0
            dzdx = ((w[0][2] + 2 * w[1][2] + w[2][2]) - (w[0][0] + 2 * w[1][0] + w[2][0])) / (8 * dx)
            dzdy = ((w[0][0] + 2 * w[0][1] + w[0][2]) - (w[2][0] + 2 * w[2][1] + w[2][2])) / (8 * dy)   # norte − sul
            s = math.hypot(dzdx, dzdy)
            dec[i * nx + j] = math.degrees(math.atan(s))
            # aspecto = para onde a encosta desce (azimute do gradiente descendente)
            asp[i * nx + j] = None if s == 0 else (math.degrees(math.atan2(-dzdx, -dzdy)) + 360) % 360
    val = [d for d in dec if d is not None]
    return resultado("Declividade e aspecto pelo método de Horn (janela 3×3)",
                     ["grade regular", "borda: repete a célula central"], [],
                     {"nx": nx, "ny": ny, "dx": dx, "dy": dy},
                     "Resolução da grade limita: modelo de 30 m não vê taludes de casa. Declividade em graus (45° = 100 %).",
                     {"declividade_graus": dec, "aspecto_graus": asp,
                      "declividade_media": sum(val) / len(val) if val else None})


def d8(g: dict) -> list:
    nx, ny, dx, dy = g["nx"], g["ny"], float(g["dx"]), float(g["dy"])
    dirs = [-1] * (nx * ny)
    for i in range(ny):
        for j in range(nx):
            z0 = _z(g, i, j)
            if z0 is None:
                continue
            best, bk = 0.0, -1
            for k, (a, b) in enumerate(VIZ):
                z1 = _z(g, i + a, j + b)
                if z1 is None:
                    continue
                dist = math.hypot(a * dy, b * dx)
                q = (z0 - z1) / dist
                if q > best:
                    best, bk = q, k
            dirs[i * nx + j] = bk
    return dirs


def acumulacao(g: dict, dirs: list | None = None, peso: list | None = None) -> list:
    """Soma a montante (peso por célula; padrão 1) seguindo o D8. Ordem: cota decrescente, empate pelo índice."""
    nx, ny = g["nx"], g["ny"]
    dirs = d8(g) if dirs is None else dirs
    N = nx * ny
    acc = [0.0 if g["z"][s] is None else (1.0 if peso is None else float(peso[s] or 0.0)) for s in range(N)]
    ordem = sorted((s for s in range(N) if g["z"][s] is not None), key=lambda s: (-g["z"][s], s))
    for s in ordem:
        k = dirs[s]
        if k >= 0:
            i, j = divmod(s, nx)
            a, b = VIZ[k]
            acc[(i + a) * nx + j + b] += acc[s]
    return acc


def escoamento(g: dict) -> dict:
    dirs = d8(g)
    acc = acumulacao(g, dirs)
    area = float(g["dx"]) * float(g["dy"])
    return resultado("Direção de escoamento D8 (maior queda) e acumulação de fluxo",
                     ["água segue o vizinho mais baixo (um só caminho)", "depressões não são preenchidas"], [],
                     {"nx": g["nx"], "ny": g["ny"]},
                     "D8 concentra o fluxo em linhas; em encosta lisa ele exagera canais. Depressões (−1) param o fluxo: "
                     "confira no campo se são reais (lagoa, bacia) ou erro do modelo de elevação.",
                     {"direcoes": dirs, "acumulacao": acc, "area_contribuicao_m2": [a * area for a in acc],
                      "sumidouros": sum(1 for s, d in enumerate(dirs) if d < 0 and g["z"][s] is not None)})


def scs_cn(chuva_mm: float, cn: float, ia_razao: float | None = None) -> float:
    """Q (mm) = (P − Ia)²/(P − Ia + S), com S = 25400/CN − 254 e Ia = razão·S; zero se P ≤ Ia."""
    ia_razao = premissa("sim.hidro.ia_razao", 0.2) if ia_razao is None else ia_razao
    if not (0 < cn <= 100):
        raise ValueError("CN entre 0 e 100")
    s = 25400.0 / cn - 254.0
    ia = ia_razao * s
    return 0.0 if chuva_mm <= ia else (chuva_mm - ia) ** 2 / (chuva_mm - ia + s)


def cn_de(uso: str, grupo: str) -> float:
    tab = premissa("sim.hidro.cn_por_uso") or {}
    v = (tab.get(uso) or {}).get(grupo)
    if v is None:
        raise FaltaDado(f"{MARCADOR} CN do uso '{uso}' no grupo hidrológico '{grupo}'")
    return float(v)


def escoamento_scs(g: dict, chuva_mm: float, usos: list | str, grupo: list | str) -> dict:
    """CN por célula (uso e grupo hidrológico A–D, lista por célula ou um só), lâmina por célula e volume
    acumulado a montante (m³) seguindo o D8: onde a enxurrada se junta (vala, bacia, jardim de chuva)."""
    N = g["nx"] * g["ny"]
    us = [usos] * N if isinstance(usos, str) else usos
    gs = [grupo] * N if isinstance(grupo, str) else grupo
    area = float(g["dx"]) * float(g["dy"])
    cn = [None if g["z"][s] is None else cn_de(us[s], gs[s]) for s in range(N)]
    q = [0.0 if c is None else scs_cn(chuva_mm, c) for c in cn]
    vol = acumulacao(g, None, [x * area / 1000 for x in q])
    tot = sum(x * area / 1000 for x in q)
    return resultado("Escoamento superficial pelo número de curva (SCS-CN, USDA NRCS) e soma a montante pelo D8",
                     ["chuva uniforme no evento", "condição de umidade antecedente média (II)",
                      "sem infiltração ao longo do caminho"],
                     [usada("sim.hidro.cn_por_uso"), usada("sim.hidro.ia_razao")],
                     {"nx": g["nx"], "ny": g["ny"]},
                     "Evento isolado, bacias pequenas. Não dá vazão de pico nem hidrograma; para drenagem urbana use "
                     "o método da norma/prefeitura.",
                     {"cn": cn, "lamina_mm": q, "volume_acumulado_m3": vol, "volume_total_m3": tot,
                      "chuva_mm": chuva_mm})


def usle(g: dict, R=None, K=None, C=None, P=None, comprimento_m: float | None = None) -> dict:
    """A (t/ha·ano) = R·K·LS·C·P por célula. LS de Wischmeier & Smith com λ = comprimento de rampa (padrão:
    lado da célula × √acumulação) e declividade de Horn; coeficientes na premissa sim.erosao.ls."""
    falt = [n for n, v in (("R", R), ("K", K), ("C", C), ("P", P)) if v is None]
    if falt:
        raise FaltaDado(f"{MARCADOR} fatores {', '.join(falt)} da USLE (digite do estudo do lugar)")
    ls = premissa("sim.erosao.ls") or {}
    N = g["nx"] * g["ny"]
    dec = declividade_aspecto(g)["declividade_graus"]
    acc = acumulacao(g)
    lado = math.sqrt(float(g["dx"]) * float(g["dy"]))
    out, lsv = [None] * N, [None] * N

    def val(x, s):
        return x[s] if isinstance(x, list) else x
    for s in range(N):
        if dec[s] is None:
            continue
        th = math.radians(dec[s])
        pct = math.tan(th) * 100
        m = 0.5 if pct >= 5 else 0.4 if pct >= 3.5 else 0.3 if pct >= 1 else 0.2
        lam = comprimento_m if comprimento_m else lado * math.sqrt(acc[s])
        L = (lam / ls["lambda_ref"]) ** m
        S = ls["a"] * math.sin(th) ** 2 + ls["b"] * math.sin(th) + ls["c"]
        lsv[s] = L * S
        out[s] = val(R, s) * val(K, s) * lsv[s] * val(C, s) * val(P, s)
    v = [x for x in out if x is not None]
    return resultado("USLE: A = R·K·LS·C·P (Wischmeier & Smith), LS pela declividade e comprimento de rampa",
                     ["perda média anual", "erosão laminar e em sulcos (não voçoroca)"],
                     [usada("sim.erosao.ls"), {"id": "usle.fatores", "valor": {"R": R if not isinstance(R, list) else "grade",
                      "K": K if not isinstance(K, list) else "grade", "C": C if not isinstance(C, list) else "grade",
                      "P": P if not isinstance(P, list) else "grade"}, "status": "digitado", "fonte": "estudo do lugar"}],
                     {"nx": g["nx"], "ny": g["ny"]},
                     "Ordem de grandeza para comparar cenários (com e sem cobertura, curva de nível). Não prevê "
                     "deslizamento: risco de encosta é a aba Resiliência e a Defesa Civil.",
                     {"perda_t_ha_ano": out, "ls": lsv, "media": sum(v) / len(v) if v else None,
                      "maxima": max(v) if v else None})


def visada(g: dict, obs_i: int, obs_j: int, altura_obs: float = 1.6, altura_alvo: float = 0.0) -> dict:
    """Célula visível quando nenhuma célula no caminho (amostrado a cada meia célula, vizinho mais próximo)
    tem ângulo de elevação maior que o do alvo."""
    nx, ny, dx, dy = g["nx"], g["ny"], float(g["dx"]), float(g["dy"])
    z0 = _z(g, obs_i, obs_j)
    if z0 is None:
        raise FaltaDado("observador fora da grade ou sem cota")
    h0 = z0 + altura_obs
    vis = [0] * (nx * ny)
    for i in range(ny):
        for j in range(nx):
            zt = _z(g, i, j)
            if zt is None:
                continue
            if i == obs_i and j == obs_j:
                vis[i * nx + j] = 1
                continue
            di, dj = i - obs_i, j - obs_j
            dist = math.hypot(di * dy, dj * dx)
            alvo = (zt + altura_alvo - h0) / dist
            n = int(math.ceil(2 * max(abs(di), abs(dj))))
            ok = True
            for k in range(1, n):
                f = k / n
                ii, jj = int(math.floor(obs_i + f * di + 0.5)), int(math.floor(obs_j + f * dj + 0.5))
                if (ii == i and jj == j) or (ii == obs_i and jj == obs_j):
                    continue
                zc = _z(g, ii, jj)
                if zc is None:
                    continue
                if (zc - h0) / (f * dist) > alvo:
                    ok = False
                    break
            vis[i * nx + j] = 1 if ok else 0
    return resultado("Visada simples (linha de visada sobre a grade, sem curvatura da Terra)",
                     ["terreno nu (sem árvores nem prédios)", "vizinho mais próximo ao longo do raio"], [],
                     {"nx": nx, "ny": ny}, "Só relevo; vegetação e construções mudam tudo. Distâncias de poucos km.",
                     {"visivel": vis, "fracao_visivel": sum(vis) / max(1, sum(1 for x in g["z"] if x is not None))})
