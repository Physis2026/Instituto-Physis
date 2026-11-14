"""Gestão do eletrodo de pH (projeto P6, Qualidade da água).

Portado de `docs/originais/ph_electrode_original.py`, enviado pela Physis em 13/11/2026,
para Python puro: o hub não usa numpy nem pandas. As constantes são as do original.

CORREÇÕES feitas na portabilidade (o original fica guardado sem alteração):

1. Vida útil. O original calculava a margem como o quanto o slope JÁ PASSOU do limite
   (max(0, |slope-100| - 5)); para um eletrodo bom isso dá zero e a resposta era "0 dias
   restantes". Aqui a margem é o quanto FALTA para o limite (5 - |slope-100|).
2. Última calibração reprovada. O original ignorava a calibração reprovada e respondia com
   a anterior, mostrando "atenção" para um eletrodo que acabou de falhar. Aqui a saúde
   responde "calibracao_reprovada".
3. Tempo de resposta com pH descendo. O original devolvia 0 s para qualquer queda de pH.
   Aqui a comparação vale nos dois sentidos.
4. Unidade do drift. O original chamava de "mV por dia" um valor calculado em pontos
   percentuais do slope por dia. Aqui o nome diz o que é; o limite numérico é o do original.

PERGUNTAS EM ABERTO para a equipe técnica (nada foi mudado nestes pontos):

a. Na nota de saúde, a penalidade de slope só começa fora da faixa 95 a 105 %, mas fora
   dela a calibração já é reprovada. Do jeito que está, essa penalidade nunca acontece.
b. Os limites de drift (0,5 e 0,3) foram escritos para mV por dia. Valem para % por dia?
c. DAYS_REPLACE_WARN e DAYS_REPLACE_ALERT (180 e 365 dias) não são usados: falta a data de
   instalação do eletrodo.
d. A compensação por temperatura é linear (0,003 pH por °C). Confirmar se é a desejada.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import mean, pstdev, variance

IDEAL_SLOPE_MV_PER_PH = -59.16
TEMP_COEF_PH_PER_C = 0.003
SLOPE_OK = (95.0, 105.0)
OFFSET_OK_MV = 30.0
DRIFT_MAX_SLOPE_PCT_POR_DIA = 0.5      # no original: DRIFT_MAX_MV_PER_DAY
DRIFT_MAX_OFFSET_MV_POR_DIA = 0.3
RESPONSE_TIME_MAX_S = 90
DAYS_CAL_WARN = 14
DAYS_CAL_ALERT = 30
DAYS_REPLACE_WARN = 180
DAYS_REPLACE_ALERT = 365


@dataclass
class Calibracao:
    data: datetime
    ponto: str
    slope_pct: float
    offset_mv: float
    buffer_ph: list = field(default_factory=list)
    temp_c: float = 25.0
    tecnico: str = ""
    observacao: str = ""

    def valida(self) -> bool:
        return SLOPE_OK[0] <= self.slope_pct <= SLOPE_OK[1] and abs(self.offset_mv) <= OFFSET_OK_MV


def compensar_temperatura(ph_raw: float, temp_c: float, temp_ref_c: float = 25.0) -> float:
    return ph_raw + TEMP_COEF_PH_PER_C * (temp_ref_c - temp_c)


class EletrodoPH:
    def __init__(self, ponto: str, calibracoes: list):
        if not calibracoes:
            raise ValueError(f"Sem calibrações para {ponto}")
        self.ponto = ponto
        self.calibracoes = sorted(calibracoes, key=lambda c: c.data)

    def _ate(self, ref):
        return [c for c in self.calibracoes if c.data <= ref]

    def ultima_calibracao(self, ref=None):
        validas = [c for c in self._ate(ref or datetime.now()) if c.valida()]
        return validas[-1] if validas else None

    def dias_desde_calibracao(self, ref=None):
        ref = ref or datetime.now()
        c = self.ultima_calibracao(ref)
        return (ref - c.data).days if c else None

    def drift(self):
        out = []
        for a, b in zip(self.calibracoes, self.calibracoes[1:]):
            dias = (b.data - a.data).total_seconds() / 86400
            if dias <= 0:
                continue
            out.append({"de": a.data.isoformat(), "para": b.data.isoformat(), "dias": dias,
                        "slope_pct_por_dia": (b.slope_pct - a.slope_pct) / dias,
                        "offset_mv_por_dia": (b.offset_mv - a.offset_mv) / dias})
        return out

    def drift_excede_limite(self) -> bool:
        return any(abs(x["slope_pct_por_dia"]) > DRIFT_MAX_SLOPE_PCT_POR_DIA
                   or abs(x["offset_mv_por_dia"]) > DRIFT_MAX_OFFSET_MV_POR_DIA for x in self.drift())

    def saude(self, ref=None) -> dict:
        ref = ref or datetime.now()
        feitas = self._ate(ref)
        if not feitas:
            return {"ponto": self.ponto, "score": 0, "status": "sem_calibracao"}
        ultima = feitas[-1]
        if not ultima.valida():          # correção 2
            return {"ponto": self.ponto, "score": 0, "status": "calibracao_reprovada",
                    "dias_desde_calibracao": (ref - ultima.data).days,
                    "slope_pct": ultima.slope_pct, "offset_mv": ultima.offset_mv}
        c = ultima
        score = 100.0
        score -= min(30, max(0, abs(c.slope_pct - 100) - 5) * 3)      # pergunta em aberto (a)
        score -= min(25, max(0, abs(c.offset_mv) - 10) * 2)
        dias = (ref - c.data).days
        score -= min(25, max(0, dias - DAYS_CAL_WARN) * 1.5)
        if self.drift_excede_limite():
            score -= 10
        score = max(0.0, min(100.0, score))
        status = "saudavel" if score > 80 else "atencao" if score > 50 else "substituir"
        return {"ponto": self.ponto, "score": round(score, 1), "status": status,
                "dias_desde_calibracao": dias, "slope_pct": c.slope_pct, "offset_mv": c.offset_mv}

    def vida_util_estimada(self, ref=None):
        c = self.ultima_calibracao(ref or datetime.now())
        if not c:
            return None
        d = self.drift()
        if not d:
            return {"dias_restantes": None, "motivo": "sem_historico_drift"}
        taxa = mean(abs(x["slope_pct_por_dia"]) for x in d)
        if taxa <= 0.01:
            return {"dias_restantes": None, "motivo": "drift_desprezivel"}
        margem = max(0.0, 5 - abs(c.slope_pct - 100))                # correção 1
        return {"dias_restantes": int(margem / taxa), "taxa_drift_pct_dia": round(taxa, 4)}


def comparar_com_laboratorio(leituras, coletas, tol_ph: float = 0.15, janela=timedelta(hours=2)):
    """leituras: [(quando, ph_comp)]; coletas: [(quando, ph_lab)]. Usa a leitura mais próxima de cada coleta."""
    out = []
    for quando, ph_lab in sorted(coletas):
        perto = min(leituras, key=lambda l: abs(l[0] - quando), default=None)
        if perto is None or abs(perto[0] - quando) > janela:
            out.append({"quando": quando, "ph_lab": ph_lab, "ph_comp": None, "residual": None, "alerta_bias": False})
            continue
        r = perto[1] - ph_lab
        out.append({"quando": quando, "ph_lab": ph_lab, "ph_comp": perto[1], "residual": r, "alerta_bias": abs(r) > tol_ph})
    return out


def tempo_resposta(leituras, t0, ph_antes, limiar: float = 0.63, janela_min: float = 5):
    """Tempo até a leitura atingir 63 % da mudança depois de t0. leituras: [(quando, ph_comp)]."""
    d = sorted(l for l in leituras if l[0] >= t0)
    if not d:
        return None
    fim = [l for l in d if l[0] <= t0 + timedelta(minutes=janela_min)] or d
    delta = fim[-1][1] - ph_antes
    if abs(delta) < 0.05:
        return {"t0": t0.isoformat(), "tempo_s": None, "motivo": "mudanca_insuficiente"}
    alvo = ph_antes + limiar * delta
    for quando, v in d:
        if (v >= alvo) if delta > 0 else (v <= alvo):                # correção 3
            t = (quando - t0).total_seconds()
            return {"t0": t0.isoformat(), "tempo_s": t, "limite_s": RESPONSE_TIME_MAX_S, "ok": t <= RESPONSE_TIME_MAX_S}
    return {"t0": t0.isoformat(), "tempo_s": None, "motivo": "nao_atingiu_63pct"}


def validar_redundancia_pre_pos(pares, tol_ph: float = 0.10):
    """pares: [(quando, ph_pre, ph_pos, valvula_adubo_aberta)]. Com a válvula fechada, pré e pós devem coincidir."""
    return [{"quando": q, "delta_ph": abs(pos - pre), "alerta_redundancia": abs(pos - pre) > tol_ph}
            for q, pre, pos, aberta in pares if not aberta]


def _janela(leituras, i, largura):
    fim = leituras[i][0]
    return [v for q, v in leituras[: i + 1] if fim - q <= largura]


def detectar_travamento(leituras, janela_h: float = 3, var_min: float = 1e-4, minimo: int = 10):
    """Leitura que não varia: variância abaixo do mínimo numa janela de tempo."""
    d, out = sorted(leituras), []
    for i, (q, v) in enumerate(d):
        j = _janela(d, i, timedelta(hours=janela_h))
        var = variance(j) if len(j) >= minimo else None
        out.append({"quando": q, "ph_comp": v, "variancia_janela": var, "alerta_travamento": var is not None and var < var_min})
    return out


def diagnosticar_ruido(leituras, janela_min: float = 5, limiar_std: float = 0.3, minimo: int = 5):
    """Ruído elétrico ou de aterramento: desvio padrão alto numa janela curta."""
    d, out = sorted(leituras), []
    for i, (q, v) in enumerate(d):
        j = _janela(d, i, timedelta(minutes=janela_min))
        dp = pstdev(j) if len(j) >= minimo else None
        out.append({"quando": q, "ph_comp": v, "ph_std": dp, "alerta_ruido": dp is not None and dp > limiar_std})
    return out


def relatorio_eletrodos(eletrodos: dict, ref=None):
    ref = ref or datetime.now()
    linhas = []
    for ponto, el in eletrodos.items():
        s = el.saude(ref)
        v = el.vida_util_estimada(ref)
        s["dias_restantes_estimado"] = v["dias_restantes"] if v else None
        linhas.append(s)
    return linhas
