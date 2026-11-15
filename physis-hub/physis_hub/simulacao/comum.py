"""Peças comuns das simulações da Fase 1 (espelho de sistema/physis-simulacao.js, parte "comum").

- resultado(): o envelope que TODO resultado carrega (método, hipóteses, premissas usadas, malha, limites de
  validade e o aviso de que é pré-dimensionamento para revisão do engenheiro; nada aprova projeto sozinho);
- premissa(): lê sistema/physis-simulacao-premissas.json (e, como reserva, sistema/physis-premissas.json);
- material(): lê sistema/physis-materiais.json (propriedades térmicas e densidade; nada inventado);
- Rng: gerador mulberry32 (inteiros de 32 bits), igual no Python e no navegador, para o Monte Carlo e o
  recozimento simulado darem o MESMO sorteio nos dois lados com a mesma semente;
- resolver(): eliminação de Gauss com pivoteamento parcial (sistemas pequenos, densos).
Só biblioteca padrão. Caminhos com pathlib (o servidor de produção é Linux).
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
SISTEMA = RAIZ / "sistema"
ARQ_PREMISSAS = SISTEMA / "physis-simulacao-premissas.json"
ARQ_PREMISSAS_GERAIS = SISTEMA / "physis-premissas.json"
ARQ_MATERIAIS = SISTEMA / "physis-materiais.json"

AVISO = ("Pré-dimensionamento para revisão do engenheiro responsável. Não aprova projeto, não substitui "
         "norma nem ensaio. Premissas marcadas 'conferir' precisam ser conferidas antes de uso em proposta.")
MARCADOR = "[MARCADOR]"


class FaltaDado(ValueError):
    """Falta um dado que a base não tem (vira [MARCADOR]; a conta não inventa)."""


@lru_cache(maxsize=4)
def _ler(caminho: str) -> dict:
    p = Path(caminho)
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _por_id(caminho: Path) -> dict:
    return {p["id"]: p for p in (_ler(str(caminho)).get("premissas") or [])}


def premissa_info(pid: str) -> dict | None:
    return _por_id(ARQ_PREMISSAS).get(pid) or _por_id(ARQ_PREMISSAS_GERAIS).get(pid)


def premissa(pid: str, padrao=None):
    p = premissa_info(pid)
    return padrao if p is None else p.get("valor_padrao")


def usada(pid: str, valor=None) -> dict:
    """Linha da lista 'premissas usadas' do resultado."""
    p = premissa_info(pid) or {}
    return {"id": pid, "valor": p.get("valor_padrao") if valor is None else valor,
            "status": p.get("status", "conferir" if p else "ausente"), "fonte": p.get("fonte", MARCADOR)}


def base_materiais() -> dict:
    return _ler(str(ARQ_MATERIAIS))


def material(mid: str) -> dict:
    for m in base_materiais().get("materiais") or []:
        if m.get("id") == mid:
            return m
    raise FaltaDado(f"{MARCADOR} material '{mid}' não está na base sistema/physis-materiais.json")


def composicao(cid: str) -> dict:
    for c in base_materiais().get("composicoes") or []:
        if c.get("id") == cid:
            return c
    raise FaltaDado(f"{MARCADOR} composição '{cid}' não está na base")


def resultado(metodo: str, hipoteses: list, premissas: list, malha, limites: str, dados: dict,
              avisos: list | None = None) -> dict:
    r = {"metodo": metodo, "hipoteses": list(hipoteses), "premissas_usadas": list(premissas), "malha": malha,
         "limites_validade": limites, "aviso": AVISO, "fase": 1, "avisos": list(avisos or [])}
    r.update(dados)
    return r


# ── gerador pseudoaleatório igual nos dois lados (mulberry32) ──
M32 = 0xFFFFFFFF


def _imul(a: int, b: int) -> int:
    return (a * b) & M32


class Rng:
    """mulberry32: mesma sequência que SIMULACAO.Rng no navegador (semente inteira)."""

    def __init__(self, semente: int = 42):
        self.a = int(semente) & M32

    def __call__(self) -> float:
        self.a = (self.a + 0x6D2B79F5) & M32
        a = self.a
        t = _imul(a ^ (a >> 15), 1 | a)
        t = ((t + _imul(t ^ (t >> 7), 61 | t)) & M32) ^ t
        return ((t ^ (t >> 14)) & M32) / 4294967296.0

    def normal(self) -> float:
        """Box-Muller (usa dois sorteios; sem guardar o segundo, igual no JS)."""
        u1 = self()
        u2 = self()
        if u1 <= 0.0:
            u1 = 1e-300
        return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


# ── álgebra linear pequena ──
def resolver(A: list, b: list) -> list:
    """Gauss com pivoteamento parcial. A (n×n) e b são copiados. Levanta FaltaDado se singular."""
    n = len(b)
    M = [list(A[i]) + [b[i]] for i in range(n)]
    for c in range(n):
        p = c
        mx = abs(M[c][c])
        for r in range(c + 1, n):
            if abs(M[r][c]) > mx:
                mx, p = abs(M[r][c]), r
        if mx < 1e-300:
            raise FaltaDado("sistema singular: faltam apoios (estrutura instável) ou há nó solto")
        if p != c:
            M[c], M[p] = M[p], M[c]
        piv = M[c][c]
        for r in range(c + 1, n):
            f = M[r][c] / piv
            if f != 0.0:
                Mr, Mc = M[r], M[c]
                for k in range(c, n + 1):
                    Mr[k] -= f * Mc[k]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = M[i][n]
        for k in range(i + 1, n):
            s -= M[i][k] * x[k]
        x[i] = s / M[i][i]
    return x


def tridiagonal(a: list, b: list, c: list, d: list) -> list:
    """Algoritmo de Thomas: a = subdiagonal (a[0] ignorado), b = diagonal, c = superdiagonal (c[-1] ignorado)."""
    n = len(d)
    cp, dp = [0.0] * n, [0.0] * n
    cp[0] = c[0] / b[0] if n > 1 else 0.0
    dp[0] = d[0] / b[0]
    for i in range(1, n):
        m = b[i] - a[i] * cp[i - 1]
        cp[i] = c[i] / m if i < n - 1 else 0.0
        dp[i] = (d[i] - a[i] * dp[i - 1]) / m
    x = [0.0] * n
    x[-1] = dp[-1]
    for i in range(n - 2, -1, -1):
        x[i] = dp[i] - cp[i] * x[i + 1]
    return x


def percentil(ordenados: list, p: float) -> float:
    """Percentil com interpolação linear (tipo 7), p de 0 a 100; lista já ordenada."""
    n = len(ordenados)
    if n == 0:
        return float("nan")
    h = (n - 1) * p / 100.0
    i = int(math.floor(h))
    if i >= n - 1:
        return ordenados[-1]
    return ordenados[i] + (h - i) * (ordenados[i + 1] - ordenados[i])
