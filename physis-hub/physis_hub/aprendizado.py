"""Aprendizado de máquina leve, no próprio hub, sem internet e sem bibliotecas de fora.

Por que assim: o hub roda num Raspberry Pi ou num computador simples do cliente, muitas vezes sem
internet. Então os modelos são pequenos, feitos só com a biblioteca padrão do Python, treinados com os
dados que o próprio hub guarda no SQLite, retreinados uma vez por dia e sempre explicáveis em português.

Quatro modelos:
  chuva      Regressão logística (gradiente descendente com L2) que estima a chance de chover ≥ 1 mm
             amanhã a partir do que cada fonte disse (Open-Meteo, INMET, receptor), do mês (seno e
             cosseno) e da chuva medida nos dias anteriores (CEMADEN ou pluviômetro Physis). Com poucos
             dias de histórico, usa o placar de acertos que já existe em clima.py.
  anomalias  Para cada sensor (ativo + grandeza): z robusto (mediana e MAD), sensor travado (o mesmo
             valor por muitas leituras), salto impossível (variação rápida demais) e tendência da
             bateria (regressão linear → dias até a bateria baixa).
  consumo    Regressão linear do consumo diário (energia, água) com o mês, o fim de semana, a
             temperatura e a produção/ocupação (quando houver) → esperado × real; desperdício quando o
             real passa do esperado + 2 desvios.
  irrigacao  Velocidade com que o solo seca (regressão da umidade por hora desde a última rega) + chance
             de chuva do modelo de chuva → quando irrigar, explicado em português simples.

Cada modelo tem: dados_<m>(db, ...) que lê o banco, treinar_<m>(amostras, agora) → modelo (dicionário
que vira JSON), prever_<m>(modelo, x) e explicar_<m>(modelo) → texto. As funções de treino e previsão
são puras (sem banco, sem relógio do sistema, sem sorteio): o mesmo dado dá sempre o mesmo resultado.

Os modelos ficam na tabela `modelo` (nome, versao, treinado_em, n_amostras, metricas, parametros);
cada treino grava uma versão nova e a tela mostra a última.
"""
from __future__ import annotations

import json
import math
import re
import threading
import time
from datetime import datetime, timedelta

from . import clima as clima_mod

FUSO = clima_mod.FUSO
CHUVA_MM = clima_mod.CHUVA_MM

ESQUEMA = """
CREATE TABLE IF NOT EXISTS modelo (
  nome TEXT NOT NULL, versao INTEGER NOT NULL, treinado_em REAL NOT NULL, n_amostras INTEGER NOT NULL,
  metricas TEXT NOT NULL, parametros TEXT NOT NULL, PRIMARY KEY (nome, versao));
"""
VERSOES_GUARDADAS = 30          # por modelo; as mais antigas são apagadas


# ══ Matemática básica (lista de listas; nada de numpy) ═════════════════════════════════════════════
def media(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def desvio(xs: list[float], ddof: int = 0) -> float:
    n = len(xs)
    if n - ddof <= 0:
        return 0.0
    m = media(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - ddof))


def mediana(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    if not n:
        return 0.0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def mad(xs: list[float], med: float | None = None) -> float:
    """Desvio absoluto mediano: a "régua" robusta (um valor maluco não estraga a régua)."""
    m = mediana(xs) if med is None else med
    return mediana([abs(x - m) for x in xs])


def sigmoide(z: float) -> float:
    z = max(-35.0, min(35.0, z))
    return 1.0 / (1.0 + math.exp(-z))


def resolver(a: list[list[float]], b: list[float]) -> list[float]:
    """Sistema linear por eliminação de Gauss com pivô parcial."""
    n = len(b)
    m = [list(a[i]) + [b[i]] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[p][c]) < 1e-12:
            continue
        m[c], m[p] = m[p], m[c]
        for r in range(n):
            if r != c and m[r][c]:
                f = m[r][c] / m[c][c]
                for k in range(c, n + 1):
                    m[r][k] -= f * m[c][k]
    return [m[i][n] / m[i][i] if abs(m[i][i]) > 1e-12 else 0.0 for i in range(n)]


def regressao(x: list[list[float]], y: list[float], l2: float = 1e-6) -> list[float]:
    """Mínimos quadrados com uma pitada de L2 (ridge). A 1ª coluna de x deve ser a constante 1 (não é penalizada)."""
    p = len(x[0])
    xtx = [[sum(r[i] * r[j] for r in x) + (l2 if i == j and i > 0 else 0.0) for j in range(p)] for i in range(p)]
    xty = [sum(r[i] * yy for r, yy in zip(x, y)) for i in range(p)]
    return resolver(xtx, xty)


def reta(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """(inclinação, intercepto, r²) da reta y = a·x + b."""
    n = len(xs)
    if n < 2:
        return 0.0, (ys[0] if ys else 0.0), 0.0
    mx, my = media(xs), media(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return 0.0, my, 0.0
    a = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    b = my - a * mx
    sst = sum((y - my) ** 2 for y in ys)
    sse = sum((y - (a * x + b)) ** 2 for x, y in zip(xs, ys))
    return a, b, (1 - sse / sst) if sst > 0 else 0.0


def logistica(x: list[list[float]], y: list[int], l2: float = 0.01, passo: float = 0.3,
              iteracoes: int = 2000) -> list[float]:
    """Regressão logística por gradiente descendente (lote inteiro, começa do zero: determinística).
    A 1ª coluna de x é a constante 1 e não é penalizada."""
    n, p = len(x), len(x[0])
    w = [0.0] * p
    for _ in range(iteracoes):
        g = [0.0] * p
        for r, yy in zip(x, y):
            e = sigmoide(sum(wi * xi for wi, xi in zip(w, r))) - yy
            for j in range(p):
                g[j] += e * r[j]
        for j in range(p):
            w[j] -= passo * (g[j] / n + (l2 * w[j] if j > 0 else 0.0))
    return w


def padronizar(linhas: list[list[float]]) -> tuple[list[float], list[float]]:
    p = len(linhas[0]) if linhas else 0
    mu = [media([r[j] for r in linhas]) for j in range(p)]
    sd = [desvio([r[j] for r in linhas]) or 1.0 for j in range(p)]
    return mu, sd


def aplicar_padrao(r: list[float], mu: list[float], sd: list[float]) -> list[float]:
    return [1.0] + [(v - m) / s for v, m, s in zip(r, mu, sd)]


def brier(ps: list[float], ys: list[int]) -> float | None:
    return round(sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ys), 4) if ys else None


def calibracao(ps: list[float], ys: list[int], faixas: int = 5) -> list[dict]:
    """Tabela de calibração: em cada faixa de chance prevista, quantas vezes choveu de fato."""
    out = []
    for i in range(faixas):
        lo, hi = i / faixas, (i + 1) / faixas
        sel = [(p, y) for p, y in zip(ps, ys) if lo <= p < hi or (i == faixas - 1 and p == 1.0)]
        if sel:
            out.append({"faixa": f"{int(lo * 100)}–{int(hi * 100)}%", "n": len(sel),
                        "prevista": round(media([p for p, _ in sel]), 3), "observada": round(media([y for _, y in sel]), 3)})
    return out


def _dia(t: float) -> str:
    return datetime.fromtimestamp(t, FUSO).strftime("%Y-%m-%d")


def _somar_dias(dia: str, n: int) -> str:
    return (datetime.strptime(dia, "%Y-%m-%d") + timedelta(days=n)).strftime("%Y-%m-%d")


def _mes(dia: str) -> int:
    return int(dia[5:7])


def _r(v, n: int = 3):
    return None if v is None else round(v, n)


def _modelo(nome: str, agora: float, n: int, metricas: dict, parametros: dict) -> dict:
    return {"nome": nome, "versao": 0, "treinado_em": agora, "n_amostras": n, "metricas": metricas, "parametros": parametros}


# ══ (a) Chuva de amanhã ══════════════════════════════════════════════════════════════════════════
FONTES_PREV = ("openmeteo", "inmet", "receptor")
VARIAVEIS_CHUVA = ("openmeteo_diz", "inmet_diz", "receptor_diz", "openmeteo_mm", "mes_seno", "mes_cosseno",
                   "chuva_anteontem", "chuva_3_dias")
NOMES_VARIAVEIS = {"openmeteo_diz": "o que o Open-Meteo previu", "inmet_diz": "o que o INMET previu",
                   "receptor_diz": "o que o receptor previu", "openmeteo_mm": "os milímetros previstos pelo Open-Meteo",
                   "mes_seno": "a época do ano", "mes_cosseno": "a época do ano",
                   "chuva_anteontem": "a chuva medida no dia anterior à previsão",
                   "chuva_3_dias": "a chuva medida nos 3 dias anteriores"}
MIN_AMOSTRAS_CHUVA = 30


def observados(db) -> dict[str, float]:
    """Chuva medida por dia; o pluviômetro Physis do lugar vale mais que o CEMADEN."""
    obs: dict[str, float] = {}
    for dia, origem, mm in db.execute("SELECT dia, origem, mm FROM clima_observado ORDER BY dia"):
        if dia not in obs or origem == "physis":
            obs[dia] = float(mm)
    return obs


def _recente(obs: dict[str, float], dia: str) -> tuple[float | None, float | None]:
    """Chuva já conhecida quando a previsão para `dia` foi feita (na véspera): anteontem e os 3 dias até lá."""
    d2 = obs.get(_somar_dias(dia, -2))
    tres = [obs[d] for d in (_somar_dias(dia, -k) for k in (2, 3, 4)) if d in obs]
    return d2, (sum(tres) if tres else None)


def dados_chuva(db) -> list[dict]:
    """Uma amostra por dia que tem chuva medida e pelo menos uma aposta de fonte."""
    obs = observados(db)
    apostas: dict[str, dict] = {}
    for fonte, dia, chove, mm in db.execute("SELECT fonte, dia, chove, mm FROM clima_aposta ORDER BY dia"):
        apostas.setdefault(dia, {})[fonte] = {"chove": int(chove), "mm": mm}
    out = []
    for dia in sorted(apostas):
        if dia not in obs:
            continue
        antes, tres = _recente(obs, dia)
        out.append({"dia": dia, "fontes": apostas[dia], "chuva_anteontem_mm": antes, "chuva_3d_mm": tres,
                    "mm": obs[dia], "y": int(obs[dia] >= CHUVA_MM)})
    return out


def vetor_chuva(x: dict) -> list[float]:
    """Transforma a entrada em números. Fonte que disse "chove" = +1, "não chove" = -1, sem previsão = 0."""
    f = x.get("fontes") or {}
    v = []
    for nome in FONTES_PREV:
        d = f.get(nome)
        v.append(0.0 if d is None or d.get("chove") is None else (1.0 if d.get("chove") else -1.0))
    om = (f.get("openmeteo") or {}).get("mm")
    v.append(math.log1p(max(0.0, float(om))) if om is not None else 0.0)
    mes = x.get("mes") or _mes(x["dia"])
    v += [math.sin(2 * math.pi * (mes - 1) / 12), math.cos(2 * math.pi * (mes - 1) / 12)]
    v.append(math.log1p(max(0.0, x.get("chuva_anteontem_mm") or 0.0)))
    v.append(math.log1p(max(0.0, x.get("chuva_3d_mm") or 0.0)))
    return v


def placar_de(amostras: list[dict]) -> dict:
    p: dict[str, dict] = {}
    for a in amostras:
        for fonte, d in (a.get("fontes") or {}).items():
            q = p.setdefault(fonte, {"dias": 0, "acertos": 0})
            q["dias"] += 1
            q["acertos"] += int(bool(d.get("chove")) == bool(a["y"]))
    return p


def prob_placar(placar: dict, fontes: dict) -> float:
    """A mesma conta de clima.Clima.combinada: média dos votos pesada pelo acerto (Laplace)."""
    soma = peso = 0.0
    for fonte, d in (fontes or {}).items():
        if fonte not in FONTES_PREV or d.get("chove") is None:
            continue
        q = placar.get(fonte, {"dias": 0, "acertos": 0})
        w = (q["acertos"] + 1) / (q["dias"] + 2)
        soma += w * (1.0 if d.get("chove") else 0.0)
        peso += w
    return soma / peso if peso else 0.5


def _ajustar_chuva(amostras: list[dict]) -> dict:
    linhas = [vetor_chuva(a) for a in amostras]
    mu, sd = padronizar(linhas)
    w = logistica([aplicar_padrao(r, mu, sd) for r in linhas], [a["y"] for a in amostras])
    return {"pesos": w, "media": mu, "desvio": sd}


def _p_logistica(par: dict, x: dict) -> float:
    r = aplicar_padrao(vetor_chuva(x), par["media"], par["desvio"])
    return sigmoide(sum(a * b for a, b in zip(par["pesos"], r)))


def treinar_chuva(amostras: list[dict], agora: float, minimo: int = MIN_AMOSTRAS_CHUVA) -> dict:
    amostras = sorted(amostras, key=lambda a: a["dia"])
    n = len(amostras)
    placar = placar_de(amostras)
    if n < minimo:
        ps = [prob_placar(placar, a["fontes"]) for a in amostras]
        return _modelo("chuva", agora, n, {"modo": "placar", "brier_placar": brier(ps, [a["y"] for a in amostras]),
                                          "aviso": f"só {n} dias com chuva medida; o modelo próprio começa com {minimo}"},
                       {"modo": "placar", "placar": placar, "minimo": minimo})
    # avaliação honesta: treina nos 70% mais antigos e mede nos 30% mais novos (ordem do tempo)
    k = max(1, int(n * 0.7))
    treino, teste = amostras[:k], amostras[k:]
    par = _ajustar_chuva(treino)
    ys = [a["y"] for a in teste]
    p_mod = [_p_logistica(par, a) for a in teste]
    pl_treino = placar_de(treino)
    p_pl = [prob_placar(pl_treino, a["fontes"]) for a in teste]
    por_fonte = {}
    for f in FONTES_PREV:
        ps = [(1.0 if a["fontes"][f]["chove"] else 0.0) if f in a["fontes"] else 0.5 for a in teste]
        if any(f in a["fontes"] for a in teste):
            por_fonte[f] = brier(ps, ys)
    acerto = media([float((p >= 0.5) == bool(y)) for p, y in zip(p_mod, ys)])
    metricas = {"modo": "logistica", "n_treino": len(treino), "n_teste": len(teste),
                "brier_modelo": brier(p_mod, ys), "brier_placar": brier(p_pl, ys), "brier_fontes": por_fonte,
                "brier_sempre_media": brier([media([a["y"] for a in treino])] * len(ys), ys),
                "acerto_modelo": round(acerto, 3), "calibracao": calibracao(p_mod, ys),
                "taxa_chuva": round(media([a["y"] for a in amostras]), 3)}
    final = _ajustar_chuva(amostras)            # o modelo que vai para uso aprende com tudo
    final.update({"modo": "logistica", "variaveis": list(VARIAVEIS_CHUVA), "placar": placar, "minimo": minimo})
    return _modelo("chuva", agora, n, metricas, final)


def prever_chuva(modelo: dict, x: dict) -> dict:
    par = modelo["parametros"]
    if par.get("modo") != "logistica":
        p = prob_placar(par.get("placar") or {}, x.get("fontes") or {})
        return {"prob": round(p, 3), "chove": p >= 0.5, "modo": "placar", "fontes": sorted((x.get("fontes") or {}).keys())}
    r = aplicar_padrao(vetor_chuva(x), par["media"], par["desvio"])
    p = sigmoide(sum(a * b for a, b in zip(par["pesos"], r)))
    contrib = sorted(((nome, par["pesos"][i + 1] * r[i + 1]) for i, nome in enumerate(VARIAVEIS_CHUVA)),
                     key=lambda t: -abs(t[1]))
    return {"prob": round(p, 3), "chove": p >= 0.5, "modo": "logistica",
            "placar_prob": round(prob_placar(par.get("placar") or {}, x.get("fontes") or {}), 3),
            "contribuicoes": [{"variavel": nome, "texto": NOMES_VARIAVEIS[nome], "efeito": round(c, 3)} for nome, c in contrib[:4]]}


def explicar_chuva(modelo: dict) -> str:
    m, par = modelo["metricas"], modelo["parametros"]
    if par.get("modo") != "logistica":
        return (f"Ainda há poucos dias com chuva medida ({modelo['n_amostras']}). Por enquanto a chance de chuva é a "
                f"média do que cada fonte disse, com mais peso para a fonte que mais acertou aqui. O modelo próprio "
                f"começa com {par.get('minimo', MIN_AMOSTRAS_CHUVA)} dias.")
    w = par["pesos"][1:]
    ordem = sorted(range(len(w)), key=lambda i: -abs(w[i]))[:3]
    pesa = ", ".join(NOMES_VARIAVEIS[VARIAVEIS_CHUVA[i]] for i in ordem)
    bm, bp = m.get("brier_modelo"), m.get("brier_placar")
    comp = ""
    if bm is not None and bp is not None:
        comp = (" Nos dias de teste ele errou menos que o placar das fontes" if bm < bp else
                " Nos dias de teste ele ainda não superou o placar das fontes; a tela mostra os dois") + f" (Brier {bm} × {bp}; quanto menor, melhor)."
    return (f"Aprendeu com {modelo['n_amostras']} dias deste lugar em que a chuva foi medida. O que mais pesa: {pesa}."
            f"{comp} Acertou {round(100 * (m.get('acerto_modelo') or 0))}% dos dias de teste.")


def entrada_chuva_amanha(db, agora: float) -> dict:
    """Monta a entrada do modelo com o que o hub tem guardado agora (sem chamar a internet)."""
    amanha = _somar_dias(_dia(agora), 1)
    fontes = {}
    for fonte, dados in db.execute("SELECT fonte, dados FROM clima_fonte WHERE consultado > 0"):
        try:
            d = json.loads(dados or "{}")
        except ValueError:
            continue
        if fonte == "receptor" and "chuva" in d:
            fontes["receptor"] = {"chove": int(bool(d.get("chuva"))), "mm": None}
        for dd in d.get("dias") or []:
            if dd.get("dia") == amanha and fonte in FONTES_PREV:
                fontes[fonte] = {"chove": int(bool(dd.get("chove"))), "mm": dd.get("mm")}
    antes, tres = _recente(observados(db), amanha)
    return {"dia": amanha, "fontes": fontes, "chuva_anteontem_mm": antes, "chuva_3d_mm": tres}


# ══ (b) Anomalias nos sensores ═══════════════════════════════════════════════════════════════════
GRANDEZAS_CONTINUAS = ("umidade_solo", "temperatura", "umidade", "bateria", "rssi", "snr", "nivel", "energia",
                       "tensao", "corrente", "vazao", "pressao", "fp")
# variação máxima por minuto que um sensor real consegue ter (acima disso é defeito, fio solto ou ruído)
SALTO_POR_MIN = {"umidade_solo": 10.0, "temperatura": 2.0, "umidade": 10.0, "bateria": 0.05, "nivel": 10.0,
                 "tensao": 40.0, "pressao": 3.0}
INTERVALO_PADRAO_S = 300        # sem relógio no nó, supõe uma leitura a cada 5 min
Z_LIMITE = 3.5
K_TRAVADO = 24
JANELA = 288                    # ~1 dia com leitura a cada 5 min
BAT_BAIXA_V = 3.5
BAT_AVISO_DIAS = 14


def dados_anomalias(db, janela: int = JANELA) -> dict[str, list[tuple[int, float]]]:
    out: dict[str, list[tuple[int, float]]] = {}
    marcas = ",".join("?" * len(GRANDEZAS_CONTINUAS))
    pares = db.execute(f"SELECT DISTINCT ativo, grandeza FROM medicao WHERE grandeza IN ({marcas})", GRANDEZAS_CONTINUAS).fetchall()
    for ativo, grandeza in pares:
        linhas = db.execute("SELECT ts, valor FROM medicao WHERE ativo=? AND grandeza=? ORDER BY seq DESC LIMIT ?",
                            (ativo, grandeza, janela)).fetchall()
        out[f"{ativo}|{grandeza}"] = [(int(t), float(v)) for t, v in reversed(linhas)]
    return out


def _z(valor: float, med: float, m: float, base: list[float]) -> float | None:
    if m > 0:
        return 0.6745 * (valor - med) / m
    dm = media([abs(x - med) for x in base])
    return (valor - med) / (1.2533 * dm) if dm > 0 else None


def checar_ponto(grandeza: str, base: list[float], anterior: tuple[int, float] | None, ponto: tuple[int, float],
                 ultimos: list[float]) -> list[dict]:
    """Motivos para estranhar um ponto, comparado à janela `base` (que não inclui o ponto)."""
    ts, v = ponto
    motivos = []
    if len(base) >= 10:
        med = mediana(base)
        z = _z(v, med, mad(base, med), base)
        if z is not None and abs(z) > Z_LIMITE:
            motivos.append({"tipo": "fora_do_normal", "z": round(z, 2),
                            "texto": f"valor {v:g} longe do normal recente (mediana {med:g}; z robusto {z:.1f})"})
    if anterior is not None and grandeza in SALTO_POR_MIN:
        t0, v0 = anterior
        dt_min = (ts - t0) / 60.0 if ts > 0 and t0 > 0 and ts > t0 else INTERVALO_PADRAO_S / 60.0
        dt_min = max(1.0, dt_min)
        taxa = abs(v - v0) / dt_min
        if taxa > SALTO_POR_MIN[grandeza]:
            motivos.append({"tipo": "salto_impossivel", "taxa_por_min": round(taxa, 3),
                            "texto": f"pulou de {v0:g} para {v:g} em {dt_min:.0f} min (limite físico {SALTO_POR_MIN[grandeza]:g} por minuto)"})
    if len(ultimos) >= K_TRAVADO and max(ultimos) == min(ultimos):
        motivos.append({"tipo": "travado", "texto": f"o mesmo valor ({v:g}) nas últimas {len(ultimos)} leituras: sensor travado ou desligado"})
    return motivos


def tendencia_bateria(pontos: list[tuple[int, float]], agora: float, baixa: float = BAT_BAIXA_V) -> dict | None:
    """Regressão da tensão pelo tempo (últimos 7 dias) → quantos dias até a bateria baixa."""
    p = [(t, v) for t, v in pontos if t > 0 and agora - t <= 7 * 86400]
    if len(p) < 6 or p[-1][0] - p[0][0] < 6 * 3600:
        return None
    xs = [(t - agora) / 86400.0 for t, _ in p]
    a, b, r2 = reta(xs, [v for _, v in p])
    v_agora = b
    if v_agora <= baixa:
        dias = 0.0
    elif a < -0.001:
        dias = (baixa - v_agora) / a
    else:
        dias = None
    return {"v_por_dia": round(a, 4), "v_agora": round(v_agora, 3), "r2": round(r2, 3), "dias_ate_baixa": _r(dias, 1)}


def treinar_anomalias(series: dict[str, list[tuple[int, float]]], agora: float) -> dict:
    par, n, bat, alertas = {}, 0, {}, 0
    for chave, pontos in series.items():
        if len(pontos) < 3:
            continue
        ativo, grandeza = chave.split("|", 1)
        vals = [v for _, v in pontos]
        med = mediana(vals)
        par[chave] = {"mediana": med, "mad": mad(vals, med), "n": len(vals), "ultimos": vals[-K_TRAVADO:],
                      "ultimo": list(pontos[-1]), "base": vals[-60:]}
        n += len(vals)
        if grandeza == "bateria":
            t = tendencia_bateria(pontos, agora)
            if t:
                bat[ativo] = t
                alertas += int(t["dias_ate_baixa"] is not None and t["dias_ate_baixa"] <= BAT_AVISO_DIAS)
    return _modelo("anomalias", agora, n, {"series": len(par), "baterias": len(bat), "baterias_em_aviso": alertas},
                   {"series": par, "baterias": bat, "z_limite": Z_LIMITE, "k_travado": K_TRAVADO, "salto_por_min": SALTO_POR_MIN})


def prever_anomalia(modelo: dict, x: dict) -> dict:
    """x = {"ativo", "grandeza", "valor", "ts"}: este valor novo é estranho para este sensor?"""
    chave = f"{x['ativo']}|{x['grandeza']}"
    s = modelo["parametros"]["series"].get(chave)
    if not s:
        return {"anomalo": False, "motivos": [], "aviso": "sensor sem histórico"}
    ultimos = (s["ultimos"] + [float(x["valor"])])[-K_TRAVADO:]
    motivos = checar_ponto(x["grandeza"], s["base"], tuple(s["ultimo"]), (int(x.get("ts") or 0), float(x["valor"])), ultimos)
    return {"anomalo": bool(motivos), "motivos": motivos}


def detectar_anomalias(series: dict[str, list[tuple[int, float]]], agora: float) -> list[dict]:
    """O que está estranho agora: confere a última leitura de cada sensor e a tendência das baterias."""
    out = []
    for chave, pontos in sorted(series.items()):
        if len(pontos) < 2:
            continue
        ativo, grandeza = chave.split("|", 1)
        base = [v for _, v in pontos[:-1]]
        motivos = checar_ponto(grandeza, base, pontos[-2], pontos[-1], [v for _, v in pontos[-K_TRAVADO:]])
        for m in motivos:
            out.append({"ativo": ativo, "grandeza": grandeza, "valor": pontos[-1][1], "ts": pontos[-1][0],
                        "nivel": "alarme" if m["tipo"] in ("travado", "salto_impossivel") else "atencao", **m})
        if grandeza == "bateria":
            t = tendencia_bateria(pontos, agora)
            if t and t["dias_ate_baixa"] is not None and t["dias_ate_baixa"] <= BAT_AVISO_DIAS:
                out.append({"ativo": ativo, "grandeza": grandeza, "valor": pontos[-1][1], "ts": pontos[-1][0],
                            "nivel": "atencao" if t["dias_ate_baixa"] > 3 else "alarme", "tipo": "bateria_acabando", **t,
                            "texto": f"a bateria cai {abs(t['v_por_dia']):.3f} V por dia: chega a {BAT_BAIXA_V} V em cerca de "
                                     f"{t['dias_ate_baixa']:.0f} dia(s)"})
    return out


def explicar_anomalias(modelo: dict) -> str:
    m = modelo["metricas"]
    return (f"Acompanha {m['series']} sensores. Para cada um, guarda o valor típico (mediana) e a variação típica (MAD) "
            f"das últimas leituras. Estranha um valor quando ele fica a mais de {Z_LIMITE} 'réguas' do típico, quando "
            f"o sensor repete o mesmo número {K_TRAVADO} vezes seguidas (travado) ou quando muda mais rápido do que a "
            f"física permite. Nas baterias, uma reta da tensão pelo tempo estima em quantos dias ela fica baixa "
            f"({m['baterias_em_aviso']} de {m['baterias']} em aviso).")


# ══ (c) Consumo esperado (energia e água) ═══════════════════════════════════════════════════════
GRANDEZAS_CONSUMO = {"energia": ("kWh/dia", "energia"), "vazao": ("m³/dia", "água")}
MIN_DIAS_CONSUMO = 14


def _producao_gestao(db) -> dict[str, float]:
    """Produção ou ocupação por dia, se a Gestão guardar (melhor esforço: listas com data e quantidade)."""
    out: dict[str, float] = {}
    try:
        linhas = db.execute("SELECT chave, valor FROM gestao_estado WHERE chave LIKE '%produc%' OR chave LIKE '%ocupac%'").fetchall()
    except Exception:       # noqa: BLE001 — tabela da gestão pode não existir neste banco
        return out
    for _, valor in linhas:
        try:
            lista = json.loads(valor)
        except ValueError:
            continue
        for it in lista if isinstance(lista, list) else []:
            if not isinstance(it, dict):
                continue
            dia = str(it.get("dia") or it.get("data") or "")[:10]
            q = next((it[k] for k in ("quantidade", "qtd", "valor", "ocupacao", "hospedes") if isinstance(it.get(k), (int, float))), None)
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", dia) and q is not None:
                out[dia] = out.get(dia, 0.0) + float(q)
    return out


def dados_consumo(db) -> dict[str, list[dict]]:
    """Consumo diário por medidor: média da potência (ou vazão) no dia × 24 h."""
    temp: dict[str, list[float]] = {}
    for ts, v in db.execute("SELECT ts, valor FROM medicao WHERE grandeza='temperatura' AND ativo LIKE '%-ar' AND ts > 0"):
        temp.setdefault(_dia(ts), []).append(v)
    tmed = {d: media(v) for d, v in temp.items()}
    prod = _producao_gestao(db)
    out: dict[str, list[dict]] = {}
    for grandeza in GRANDEZAS_CONSUMO:
        por: dict[tuple[str, str], list[float]] = {}
        for ativo, ts, v in db.execute("SELECT ativo, ts, valor FROM medicao WHERE grandeza=? AND ts > 0", (grandeza,)):
            por.setdefault((ativo, _dia(ts)), []).append(v)
        for (ativo, dia), vals in sorted(por.items()):
            out.setdefault(f"{ativo}|{grandeza}", []).append(
                {"dia": dia, "valor": media(vals) * 24.0, "leituras": len(vals), "temp": tmed.get(dia), "producao": prod.get(dia)})
    return out


def _vetor_consumo(x: dict, usa_temp: bool, usa_prod: bool, temp_media: float, prod_media: float) -> list[float]:
    d = datetime.strptime(x["dia"], "%Y-%m-%d")
    m = d.month
    v = [math.sin(2 * math.pi * (m - 1) / 12), math.cos(2 * math.pi * (m - 1) / 12), 1.0 if d.weekday() >= 5 else 0.0]
    if usa_temp:
        v.append(x["temp"] if x.get("temp") is not None else temp_media)
    if usa_prod:
        v.append(x["producao"] if x.get("producao") is not None else prod_media)
    return v


def treinar_consumo(amostras: list[dict], agora: float, nome: str = "consumo", minimo: int = MIN_DIAS_CONSUMO) -> dict:
    amostras = sorted(amostras, key=lambda a: a["dia"])
    n = len(amostras)
    if n < minimo:
        vals = [a["valor"] for a in amostras]
        return _modelo(nome, agora, n, {"modo": "media", "aviso": f"só {n} dias; a regressão começa com {minimo}"},
                       {"modo": "media", "media": media(vals), "sigma": desvio(vals, 1) if n > 1 else 0.0})
    com_t = [a["temp"] for a in amostras if a.get("temp") is not None]
    com_p = [a["producao"] for a in amostras if a.get("producao") is not None]
    usa_t, usa_p = len(com_t) >= 0.8 * n, len(com_p) >= 0.8 * n
    tm, pm = media(com_t), media(com_p)
    linhas = [_vetor_consumo(a, usa_t, usa_p, tm, pm) for a in amostras]
    mu, sd = padronizar(linhas)
    xs = [aplicar_padrao(r, mu, sd) for r in linhas]
    ys = [a["valor"] for a in amostras]
    w = regressao(xs, ys, l2=1e-3)
    prev = [sum(a * b for a, b in zip(w, r)) for r in xs]
    res = [y - p for y, p in zip(ys, prev)]
    p_ = len(w)
    sigma = math.sqrt(sum(r * r for r in res) / max(1, n - p_))
    my = media(ys)
    sst = sum((y - my) ** 2 for y in ys)
    r2 = 1 - sum(r * r for r in res) / sst if sst > 0 else 0.0
    variaveis = ["mes_seno", "mes_cosseno", "fim_de_semana"] + (["temperatura"] if usa_t else []) + (["producao"] if usa_p else [])
    return _modelo(nome, agora, n, {"modo": "regressao", "r2": round(r2, 3), "sigma": round(sigma, 3),
                                    "erro_medio": round(media([abs(r) for r in res]), 3), "media": round(my, 3)},
                   {"modo": "regressao", "pesos": w, "media_x": mu, "desvio_x": sd, "sigma": sigma, "variaveis": variaveis,
                    "usa_temp": usa_t, "usa_prod": usa_p, "temp_media": tm, "prod_media": pm})


def prever_consumo(modelo: dict, x: dict) -> dict:
    """x = {"dia", "temp"?, "producao"?, "real"?} → esperado, faixa normal e se houve desperdício."""
    par = modelo["parametros"]
    if par["modo"] == "media":
        esp, s = par["media"], par["sigma"]
    else:
        r = aplicar_padrao(_vetor_consumo(x, par["usa_temp"], par["usa_prod"], par["temp_media"], par["prod_media"]),
                           par["media_x"], par["desvio_x"])
        esp, s = sum(a * b for a, b in zip(par["pesos"], r)), par["sigma"]
    out = {"dia": x.get("dia"), "esperado": round(max(0.0, esp), 3), "faixa": [round(max(0.0, esp - 2 * s), 3), round(esp + 2 * s, 3)]}
    if x.get("real") is not None:
        real = float(x["real"])
        out.update({"real": round(real, 3), "diferenca": round(real - esp, 3),
                    "desperdicio": s > 0 and real > esp + 2 * s})
    return out


def explicar_consumo(modelo: dict) -> str:
    par, m = modelo["parametros"], modelo["metricas"]
    if par["modo"] == "media":
        return f"Com {modelo['n_amostras']} dias, o esperado é a média simples. A regressão começa com {MIN_DIAS_CONSUMO} dias."
    extra = [t for t, ok in (("a temperatura do dia", par["usa_temp"]), ("a produção/ocupação da Gestão", par["usa_prod"])) if ok]
    return (f"Aprendeu com {modelo['n_amostras']} dias o consumo normal levando em conta o mês, o fim de semana"
            f"{(' e ' + ' e '.join(extra)) if extra else ''}. Explica {round(100 * max(0, m['r2']))}% da variação; "
            f"o erro típico é {m['sigma']:.2f}. Um dia acima do esperado + 2 erros típicos é marcado como possível desperdício.")


# ══ (d) Irrigação ═══════════════════════════════════════════════════════════════════════════════
LIMITE_PADRAO = 30.0
SUBIDA_REGA = 3.0           # subida de umidade maior que isso = rega ou chuva (começa um trecho novo de secagem)


def dados_irrigacao(db, agora: float, horas: int = 72) -> dict[str, list[tuple[int, float]]]:
    desde = int(agora - horas * 3600)
    todos: dict[str, list[tuple[int, float]]] = {}
    for ativo, ts, v in db.execute("SELECT ativo, ts, valor FROM medicao WHERE grandeza='umidade_solo' AND ts >= ? ORDER BY seq", (desde,)):
        todos.setdefault(ativo, []).append((int(ts), float(v)))
    base = {a for a in todos if not a.endswith(("-a", "-b"))}
    out = {a: p for a, p in todos.items() if a in base}
    for a, p in todos.items():            # ZONA não tem média: vale cada zona
        if a.endswith(("-a", "-b")) and a[:-2] not in base:
            out[a] = p
    return out


def trecho_secagem(pontos: list[tuple[int, float]]) -> list[tuple[int, float]]:
    """Do fim para trás, até a última subida (rega ou chuva)."""
    i = len(pontos) - 1
    while i > 0 and pontos[i][1] - pontos[i - 1][1] <= SUBIDA_REGA:
        i -= 1
    return pontos[i:]


def treinar_irrigacao(pontos: list[tuple[int, float]], agora: float, nome: str = "irrigacao") -> dict:
    tr = [(t, v) for t, v in trecho_secagem(sorted(pontos)) if t > 0]
    if len(tr) < 4 or tr[-1][0] - tr[0][0] < 3600:
        return _modelo(nome, agora, len(tr), {"modo": "sem_dado"}, {"modo": "sem_dado", "taxa_h": None})
    xs = [(t - tr[0][0]) / 3600.0 for t, _ in tr]
    a, b, r2 = reta(xs, [v for _, v in tr])
    return _modelo(nome, agora, len(tr), {"modo": "reta", "r2": round(r2, 3), "horas": round(xs[-1], 1)},
                   {"modo": "reta", "taxa_h": round(-a, 4), "umidade_agora": round(a * xs[-1] + b, 2), "ts_ultimo": tr[-1][0]})


def prever_irrigacao(modelo: dict, x: dict) -> dict:
    """x = {"umidade", "limite", "prob_chuva", "agora"} → quando irrigar e por quê."""
    par = modelo["parametros"]
    u = x.get("umidade", par.get("umidade_agora"))
    lim = float(x.get("limite") or LIMITE_PADRAO)
    p = x.get("prob_chuva")
    agora = float(x.get("agora") or 0)
    chance = f"{round(100 * p)}%" if p is not None else "desconhecida"
    if u is None or par["modo"] == "sem_dado":
        return {"acao": "sem_dado", "texto": "Ainda não há leituras suficientes de umidade do solo (precisa de pelo menos 1 hora de secagem)."}
    taxa = par["taxa_h"] or 0.0
    if u <= lim:
        if p is not None and p >= 0.7:
            return {"acao": "aguardar_chuva", "horas_ate_limite": 0,
                    "texto": f"O solo chegou ao limite ({u:.0f}% ≤ {lim:.0f}%), mas a chance de chover amanhã é {chance}. "
                             "Se a planta aguenta algumas horas, vale esperar a chuva; se as folhas murcharem, irrigue."}
        return {"acao": "irrigar_agora", "horas_ate_limite": 0,
                "texto": f"Irrigue agora: a umidade está em {u:.0f}%, no limite de {lim:.0f}% ou abaixo, e a chance de chuva amanhã é {chance}."}
    if taxa <= 0.05:
        return {"acao": "nao_precisa", "horas_ate_limite": None,
                "texto": f"O solo está em {u:.0f}% e quase não está secando agora. Não precisa irrigar por enquanto."}
    horas = (u - lim) / taxa
    quando = agora + horas * 3600 if agora else None
    hora_txt = datetime.fromtimestamp(quando, FUSO).strftime("%d/%m às %H:%M") if quando else f"daqui a {horas:.0f} h"
    base = f"O solo perde cerca de {taxa:.1f} ponto(s) de umidade por hora e está em {u:.0f}%. Chega ao limite de {lim:.0f}% por volta de {hora_txt}."
    if p is not None and p >= 0.6 and horas >= 12:
        return {"acao": "aguardar_chuva", "horas_ate_limite": round(horas, 1), "quando": quando,
                "texto": base + f" Como a chance de chuva amanhã é {chance}, a sugestão é não irrigar antes e conferir de novo depois da chuva."}
    return {"acao": "agendar", "horas_ate_limite": round(horas, 1), "quando": quando,
            "texto": base + f" Programe a próxima rega para perto desse horário (chance de chuva amanhã: {chance})."}


def explicar_irrigacao(modelo: dict) -> str:
    par = modelo["parametros"]
    if par["modo"] == "sem_dado":
        return "Sem leituras suficientes desde a última rega para medir a velocidade de secagem do solo."
    return (f"Desde a última rega ou chuva, o solo perde {par['taxa_h']:.2f} ponto(s) de umidade por hora "
            f"(reta ajustada a {modelo['n_amostras']} leituras, r² {modelo['metricas']['r2']}). Com isso e a chance de chuva, "
            "o sistema calcula quando a umidade chega ao limite da válvula.")


# ══ Guardar e ler modelos ═══════════════════════════════════════════════════════════════════════
def salvar(db, modelo: dict) -> dict:
    r = db.execute("SELECT COALESCE(MAX(versao), 0) FROM modelo WHERE nome=?", (modelo["nome"],)).fetchone()
    modelo = dict(modelo, versao=int(r[0]) + 1)
    db.execute("INSERT INTO modelo(nome,versao,treinado_em,n_amostras,metricas,parametros) VALUES(?,?,?,?,?,?)",
               (modelo["nome"], modelo["versao"], modelo["treinado_em"], modelo["n_amostras"],
                json.dumps(modelo["metricas"], ensure_ascii=False), json.dumps(modelo["parametros"], ensure_ascii=False)))
    db.execute("DELETE FROM modelo WHERE nome=? AND versao <= ?", (modelo["nome"], modelo["versao"] - VERSOES_GUARDADAS))
    return modelo


def carregar(db, nome: str) -> dict | None:
    r = db.execute("SELECT nome,versao,treinado_em,n_amostras,metricas,parametros FROM modelo WHERE nome=? "
                   "ORDER BY versao DESC LIMIT 1", (nome,)).fetchone()
    if not r:
        return None
    return {"nome": r[0], "versao": r[1], "treinado_em": r[2], "n_amostras": r[3],
            "metricas": json.loads(r[4]), "parametros": json.loads(r[5])}


EXPLICAR = {"chuva": explicar_chuva, "anomalias": explicar_anomalias}


def explicar(modelo: dict) -> str:
    nome = modelo["nome"]
    if nome.startswith("consumo"):
        return explicar_consumo(modelo)
    if nome.startswith("irrigacao"):
        return explicar_irrigacao(modelo)
    return EXPLICAR[nome](modelo) if nome in EXPLICAR else ""


# ══ O que o servidor usa ════════════════════════════════════════════════════════════════════════
class Aprendizado:
    """Liga os modelos ao banco do hub. Todos os acessos ao banco passam pela trava do hub."""

    def __init__(self, hub, relogio=None):
        self.hub = hub
        self.relogio = relogio or hub.relogio
        with hub._trava:
            hub._db.executescript(clima_mod.ESQUEMA + ESQUEMA)   # tabelas do clima podem ainda não existir
            hub._db.commit()

    @property
    def _db(self):
        return self.hub._db

    def treinar(self) -> dict:
        agora = self.relogio()
        feitos = []
        with self.hub._trava:
            feitos.append(salvar(self._db, treinar_chuva(dados_chuva(self._db), agora)))
            feitos.append(salvar(self._db, treinar_anomalias(dados_anomalias(self._db), agora)))
            for chave, amostras in dados_consumo(self._db).items():
                feitos.append(salvar(self._db, treinar_consumo(amostras, agora, nome=f"consumo:{chave}")))
            for ativo, pontos in dados_irrigacao(self._db, agora).items():
                feitos.append(salvar(self._db, treinar_irrigacao(pontos, agora, nome=f"irrigacao:{ativo}")))
            self._db.commit()
        try:
            self.hub.registrar("aprendizado", "hub", {"o_que": "modelos treinados", "modelos": [m["nome"] for m in feitos]})
            with self.hub._trava:
                self.hub._db.commit()
        except Exception:       # noqa: BLE001 — o registro é bom de ter, não pode impedir o treino
            pass
        return {"ok": True, "treinado_em": agora,
                "modelos": [{"nome": m["nome"], "versao": m["versao"], "n_amostras": m["n_amostras"], "metricas": m["metricas"]} for m in feitos]}

    def _ultimos(self) -> list[dict]:
        with self.hub._trava:
            nomes = [r[0] for r in self._db.execute("SELECT DISTINCT nome FROM modelo ORDER BY nome")]
            return [carregar(self._db, n) for n in nomes]

    def estado(self) -> dict:
        ms = self._ultimos()
        return {"ok": True, "agora": self.relogio(),
                "modelos": [{"nome": m["nome"], "versao": m["versao"], "treinado_em": m["treinado_em"], "n_amostras": m["n_amostras"],
                             "metricas": m["metricas"], "explicacao": explicar(m)} for m in ms]}

    def previsao_chuva(self) -> dict:
        agora = self.relogio()
        with self.hub._trava:
            m = carregar(self._db, "chuva") or treinar_chuva(dados_chuva(self._db), agora)
            x = entrada_chuva_amanha(self._db, agora)
        if not x["fontes"]:
            return {"ok": True, "dia": x["dia"], "prob": None, "texto": "Nenhuma fonte de previsão guardada para amanhã.",
                    "modelo": {"modo": m["parametros"].get("modo"), "versao": m["versao"]}}
        p = prever_chuva(m, x)
        return {"ok": True, "dia": x["dia"], **p, "entrada": x, "explicacao": explicar_chuva(m),
                "metricas": m["metricas"], "modelo": {"versao": m["versao"], "treinado_em": m["treinado_em"]}}

    def anomalias(self) -> dict:
        agora = self.relogio()
        with self.hub._trava:
            series = dados_anomalias(self._db)
        lista = detectar_anomalias(series, agora)
        return {"ok": True, "agora": agora, "sensores": len(series), "anomalias": lista}

    def consumo(self, dias: int = 7) -> dict:
        agora = self.relogio()
        with self.hub._trava:
            dados = dados_consumo(self._db)
            modelos = {k: carregar(self._db, f"consumo:{k}") for k in dados}
        out = []
        for chave, amostras in sorted(dados.items()):
            m = modelos.get(chave) or treinar_consumo(amostras, agora, nome=f"consumo:{chave}")
            ativo, grandeza = chave.split("|", 1)
            dias_prev = [prever_consumo(m, dict(a, real=a["valor"])) for a in sorted(amostras, key=lambda a: a["dia"])[-dias:]]
            out.append({"ativo": ativo, "grandeza": grandeza, "unidade": GRANDEZAS_CONSUMO[grandeza][0], "dias": dias_prev,
                        "desperdicio": [d["dia"] for d in dias_prev if d.get("desperdicio")], "explicacao": explicar_consumo(m)})
        return {"ok": True, "medidores": out}

    def irrigacao(self) -> dict:
        agora = self.relogio()
        prev = self.previsao_chuva()
        with self.hub._trava:
            dados = dados_irrigacao(self._db, agora)
        out = []
        for ativo, pontos in sorted(dados.items()):
            m = treinar_irrigacao(pontos, agora, nome=f"irrigacao:{ativo}")
            mno = re.search(r"-no(\d+)", ativo)
            no = self.hub.nos.get(int(mno.group(1))) if mno else None
            lim = (no or {}).get("lim2" if ativo.endswith("-b") else "lim1") or LIMITE_PADRAO
            rec = prever_irrigacao(m, {"limite": lim, "prob_chuva": prev.get("prob"), "agora": agora})
            out.append({"ativo": ativo, "limite": lim, **rec, "explicacao": explicar_irrigacao(m)})
        return {"ok": True, "prob_chuva": prev.get("prob"), "recomendacoes": out}


def rodar(apr: Aprendizado, parar: threading.Event, hora: int = 3, passo: float = 600.0) -> None:
    """Treina ao ligar (se o último treino tem mais de 1 dia) e depois todo dia a partir de `hora` (3 h da manhã)."""
    while not parar.is_set():
        try:
            if precisa_treinar(apr, hora):
                apr.treinar()
        except Exception:       # noqa: BLE001 — treino com defeito não derruba o hub
            pass
        parar.wait(passo)


def precisa_treinar(apr: Aprendizado, hora: int = 3) -> bool:
    agora = apr.relogio()
    with apr.hub._trava:
        r = apr._db.execute("SELECT MAX(treinado_em) FROM modelo").fetchone()
    ultimo = (r[0] if r else None) or 0
    if not ultimo or agora - ultimo > 86400:
        return True
    return datetime.fromtimestamp(agora, FUSO).hour >= hora and _dia(ultimo) != _dia(agora)
