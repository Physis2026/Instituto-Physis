"""Otimização em QUBO — trilha quântica pedida (espelho de SIMULACAO.qubo em sistema/physis-simulacao.js).

QUBO = minimizar E(x) = offset + Σ hᵢ·xᵢ + Σ_{i<j} wᵢⱼ·xᵢ·xⱼ com xᵢ ∈ {0, 1}.
Problemas pequenos formulados aqui: escolha de posições de placas sob sombra (paineis), caminho de tubo numa grade
(rota) e topologia grossa de uma peça 2D (topologia, heurística sobre a energia de deformação do CST).
Solução AGORA, clássica e só com biblioteca padrão: exato por enumeração em código de Gray (até 24 variáveis) e
recozimento simulado (gerador mulberry32, igual no navegador). exportar() grava o JSON "physis-qubo/1" que o
adaptador simulacao/conteiner/qubo_qiskit.py lê DENTRO de um contêiner Linux (só lá importa qiskit; o hub nunca).

Aviso: solução quântica é pesquisa (P&D). Em simulador cabem ~20 a 30 variáveis, que o clássico resolve na hora.
Ela precisa dar o MESMO ótimo do clássico e nunca entra em relatório nem certificação.
"""
from __future__ import annotations

import heapq
import math

from .comum import FaltaDado, Rng, premissa, resultado, usada

AVISO_QUANTICO = ("Trilha de pesquisa: solução quântica (QAOA/QUBO) é P&D, cabe ~20–30 variáveis em simulador e "
                  "precisa reproduzir o ótimo clássico. Nunca usar em relatório nem certificação.")
LIMITE_EXATO = 24


def novo(n: int, nomes: list | None = None) -> dict:
    return {"n": n, "nomes": nomes or [f"x{i}" for i in range(n)], "linear": [0.0] * n, "quad": {}, "offset": 0.0}


def soma(Q: dict, i: int, j: int, w: float) -> None:
    if i == j:
        Q["linear"][i] += w
        return
    a, b = (i, j) if i < j else (j, i)
    k = f"{a},{b}"
    Q["quad"][k] = Q["quad"].get(k, 0.0) + w


def lista_quad(Q: dict) -> list:
    out = []
    for k, w in Q["quad"].items():
        a, b = k.split(",")
        out.append([int(a), int(b), w])
    out.sort(key=lambda t: (t[0], t[1]))
    return out


def energia(Q: dict, x: list) -> float:
    e = Q["offset"]
    for i in range(Q["n"]):
        if x[i]:
            e += Q["linear"][i]
    for i, j, w in lista_quad(Q):
        if x[i] and x[j]:
            e += w
    return e


def _viz(Q):
    nb = [[] for _ in range(Q["n"])]
    for i, j, w in lista_quad(Q):
        nb[i].append((j, w))
        nb[j].append((i, w))
    return nb


def exato(Q: dict) -> dict:
    n = Q["n"]
    if n > LIMITE_EXATO:
        raise FaltaDado(f"{n} variáveis: acima de {LIMITE_EXATO} use o recozimento")
    nb = _viz(Q)
    h = Q["linear"]
    x = [0] * n
    e = Q["offset"]
    best, bx = e, x[:]
    for g in range(1, 1 << n):
        i = (g & -g).bit_length() - 1
        d = h[i]
        for j, w in nb[i]:
            if x[j]:
                d += w
        if x[i]:
            e -= d
            x[i] = 0
        else:
            e += d
            x[i] = 1
        if e < best - 1e-9:
            best, bx = e, x[:]
    return {"x": bx, "energia": energia(Q, bx), "metodo": "exato (enumeração em código de Gray)", "avaliados": 1 << n}


def recozimento(Q: dict, semente: int | None = None, varreduras: int | None = None, t0: float | None = None,
                t1: float | None = None) -> dict:
    n = Q["n"]
    semente = premissa("sim.mc.semente", 42) if semente is None else semente
    varreduras = int(varreduras or premissa("sim.qubo.varreduras", 400))
    nb = _viz(Q)
    h = Q["linear"]
    escala = max([abs(v) for v in h] + [abs(w) for _, _, w in lista_quad(Q)] + [1e-9])
    t0 = 2.0 * escala if t0 is None else t0
    t1 = 1e-3 * escala if t1 is None else t1
    rng = Rng(semente)
    x = [1 if rng() < 0.5 else 0 for _ in range(n)]
    e = energia(Q, x)
    best, bx = e, x[:]
    for s in range(varreduras):
        T = t0 * (t1 / t0) ** (s / max(1, varreduras - 1))
        for i in range(n):
            d = h[i]
            for j, w in nb[i]:
                if x[j]:
                    d += w
            dE = -d if x[i] else d
            if dE <= 0 or rng() < math.exp(-dE / T):
                x[i] = 0 if x[i] else 1
                e += dE
                if e < best - 1e-9:
                    best, bx = e, x[:]
    return {"x": bx, "energia": energia(Q, bx), "metodo": f"recozimento simulado ({varreduras} varreduras, semente {semente})"}


def resolver(Q: dict, semente: int | None = None) -> dict:
    return exato(Q) if Q["n"] <= min(LIMITE_EXATO, premissa("sim.qubo.limite_exato", 20)) else recozimento(Q, semente)


def _pen(base: float) -> float:
    return premissa("sim.qubo.penalidade_fator", 1.5) * base


# ── problemas ──
def paineis(p: dict) -> dict:
    """p: ganho [kWh/ano de cada posição já com a sombra do entorno], sombra [[i, j, perda kWh]] (sombreamento
    mútuo de duas posições usadas juntas), k (quantas placas). min −Σg·x + Σs·xᵢxⱼ + P·(Σx − k)²."""
    g = [float(v) for v in p["ganho"]]
    n, k = len(g), int(p["k"])
    som = p.get("sombra") or []
    P = p.get("penalidade") or _pen(max(g) + sum(abs(s[2]) for s in som))
    Q = novo(n, [f"posicao_{i}" for i in range(n)])
    for i in range(n):
        soma(Q, i, i, -g[i] + P - 2 * P * k)
    for i in range(n):
        for j in range(i + 1, n):
            soma(Q, i, j, 2 * P)
    for i, j, s in som:
        soma(Q, int(i), int(j), float(s))
    Q["offset"] = P * k * k
    sol = resolver(Q, p.get("semente"))
    esc = [i for i in range(n) if sol["x"][i]]
    kwh = sum(g[i] for i in esc) - sum(s for i, j, s in som if sol["x"][int(i)] and sol["x"][int(j)])
    return _res("Escolha de posições de placas sob sombra (QUBO)", Q, sol, P,
                {"escolhidas": esc, "kwh_ano": kwh, "k": k, "atende_k": len(esc) == k},
                "Sombra mútua entra só aos pares; a geração de cada posição vem do estudo solar (aba Energia solar).")


def rota(p: dict) -> dict:
    """p: nx, ny (nós), custo {"a,b": c} ou custo_padrao (por aresta, ex.: metros × R$/m), bloqueados [nós],
    origem, destino (índices de nó = linha·nx + coluna). Variáveis: uma por aresta + uma auxiliar por nó interno.
    Restrições como penalidade: grau 1 na origem e no destino; grau 0 ou 2 nos outros (ciclos soltos custam > 0)."""
    nx, ny = int(p["nx"]), int(p["ny"])
    blq = set(p.get("bloqueados") or [])
    cp = float(p.get("custo_padrao", 1.0))
    ct = p.get("custo") or {}
    arestas = []
    for v in range(nx * ny):
        i, j = divmod(v, nx)
        for a, b in ((i, j + 1), (i + 1, j)):
            if a < ny and b < nx:
                u = a * nx + b
                if v not in blq and u not in blq:
                    arestas.append((v, u, float(ct.get(f"{v},{u}", ct.get(f"{u},{v}", cp)))))
    o, d = int(p["origem"]), int(p["destino"])
    internos = [v for v in range(nx * ny) if v not in blq and v not in (o, d)]
    ne = len(arestas)
    nomes = [f"aresta_{a}_{b}" for a, b, _ in arestas] + [f"aux_{v}" for v in internos]
    Q = novo(ne + len(internos), nomes)
    P = p.get("penalidade") or _pen(sum(c for _, _, c in arestas))
    for e, (_, _, c) in enumerate(arestas):
        soma(Q, e, e, c)
    inc = {v: [e for e, (a, b, _) in enumerate(arestas) if v in (a, b)] for v in range(nx * ny)}
    for v in (o, d):
        for e in inc[v]:
            soma(Q, e, e, -P)
        for x1 in range(len(inc[v])):
            for x2 in range(x1 + 1, len(inc[v])):
                soma(Q, inc[v][x1], inc[v][x2], 2 * P)
        Q["offset"] += P
    for k, v in enumerate(internos):
        y = ne + k
        for e in inc[v]:
            soma(Q, e, e, P)
            soma(Q, e, y, -4 * P)
        for x1 in range(len(inc[v])):
            for x2 in range(x1 + 1, len(inc[v])):
                soma(Q, inc[v][x1], inc[v][x2], 2 * P)
        soma(Q, y, y, 4 * P)
    sol = resolver(Q, p.get("semente"))
    usadas = [arestas[e] for e in range(ne) if sol["x"][e]]
    custo = sum(c for _, _, c in usadas)
    ref = _dijkstra(nx * ny, arestas, o, d)
    return _res("Caminho de tubo numa grade (QUBO com restrição de grau)", Q, sol, P,
                {"arestas": [[a, b] for a, b, _ in usadas], "custo": custo, "custo_dijkstra": ref,
                 "igual_ao_classico": ref is not None and abs(custo - ref) < 1e-9},
                "Grade grossa; desníveis, diâmetro e perda de carga são das abas Água/Turbinas/AVAC (redes existentes).")


def _dijkstra(n, arestas, o, d):
    adj = [[] for _ in range(n)]
    for a, b, c in arestas:
        adj[a].append((b, c))
        adj[b].append((a, c))
    dist = [math.inf] * n
    dist[o] = 0.0
    fila = [(0.0, o)]
    while fila:
        dv, v = heapq.heappop(fila)
        if dv > dist[v]:
            continue
        for u, c in adj[v]:
            if dv + c < dist[u]:
                dist[u] = dv + c
                heapq.heappush(fila, (dist[u], u))
    return None if dist[d] == math.inf else dist[d]


def topologia(p: dict) -> dict:
    """p: nx, ny, energia [por célula ativa, da análise CST com a peça cheia], mascara (0/1), fixas [células que
    ficam: apoio e carga], fracao (parte das células que fica), suavidade β (premissa).
    min −Σ (eᵢ/e_max)·xᵢ + β·Σ_vizinhos (xᵢ − xⱼ)² + P·(Σx − V)²; fixas com prêmio grande para ficar."""
    nx, ny = int(p["nx"]), int(p["ny"])
    M = p.get("mascara") or [1] * (nx * ny)
    cel = [s for s in range(nx * ny) if M[s]]
    en = p["energia"]
    emax = max(en[s] for s in cel) or 1.0
    beta = float(p.get("suavidade", premissa("sim.qubo.suavidade", 0.2)))
    V = int(round(float(p["fracao"]) * len(cel)))
    P = p.get("penalidade") or _pen(1.0 + 4 * beta)
    idx = {s: k for k, s in enumerate(cel)}
    Q = novo(len(cel), [f"celula_{s}" for s in cel])
    for s in cel:
        soma(Q, idx[s], idx[s], -en[s] / emax + P - 2 * P * V)
    for a in range(len(cel)):
        for b in range(a + 1, len(cel)):
            soma(Q, a, b, 2 * P)
    for s in cel:
        i, j = divmod(s, nx)
        for u in ((i * nx + j + 1) if j + 1 < nx else None, ((i + 1) * nx + j) if i + 1 < ny else None):
            if u is not None and u in idx:
                soma(Q, idx[s], idx[s], beta)
                soma(Q, idx[u], idx[u], beta)
                soma(Q, idx[s], idx[u], -2 * beta)
    for s in p.get("fixas") or []:
        if s in idx:
            soma(Q, idx[s], idx[s], -2 * P * len(cel))
    Q["offset"] = P * V * V
    sol = resolver(Q, p.get("semente"))
    nova = [0] * (nx * ny)
    for s in cel:
        nova[s] = sol["x"][idx[s]]
    return _res("Topologia grossa de peça 2D (QUBO heurístico sobre a energia de deformação)", Q, sol, P,
                {"mascara": nova, "celulas": sum(nova), "alvo": V},
                "Heurística de um passo, não é otimização topológica completa (SIMP). Reanalise a peça nova no CST.")


def _res(metodo, Q, sol, P, dados, limites):
    d = {"qubo": {"n": Q["n"], "variaveis": Q["nomes"]}, "Q": Q, "solucao": sol, "penalidade": P,
         "aviso_quantico": AVISO_QUANTICO}
    d.update(dados)
    return resultado(metodo + " — resolvido no clássico", ["restrições como penalidade quadrática",
                                                          "penalidade grande o bastante para não violar"],
                     [usada("sim.qubo.penalidade_fator"), usada("sim.qubo.limite_exato")],
                     {"variaveis": Q["n"], "termos_quadraticos": len(Q["quad"])}, limites, d)


def exportar(Q: dict, problema: str, classico: dict | None = None) -> dict:
    """JSON 'physis-qubo/1' para o adaptador (Qiskit/PennyLane no contêiner). Ising com xᵢ = (1 − sᵢ)/2."""
    quad = lista_quad(Q)
    hs = [-Q["linear"][i] / 2 for i in range(Q["n"])]
    for i, j, w in quad:
        hs[i] -= w / 4
        hs[j] -= w / 4
    off = Q["offset"] + sum(Q["linear"]) / 2 + sum(w for _, _, w in quad) / 4
    return {"formato": "physis-qubo/1", "problema": problema, "n": Q["n"], "nomes": Q["nomes"],
            "linear": Q["linear"], "quadratico": quad, "offset": Q["offset"],
            "ising": {"convencao": "x = (1 - s)/2, s em {-1, +1}", "h": hs, "J": [[i, j, w / 4] for i, j, w in quad], "offset": off},
            "solucao_classica": classico, "aviso": AVISO_QUANTICO}
