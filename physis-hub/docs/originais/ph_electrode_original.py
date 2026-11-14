# src/ph_electrode.py
"""
Módulo de gestão do eletrodo de pH.
Cobre: compensação por temperatura, calibração versionada, detecção de drift,
saúde do eletrodo, resposta temporal, validação cruzada com laboratório,
redundância pré/pós-adubação, e manutenção preditiva.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import numpy as np
import pandas as pd


# ---- Constantes físicas e de engenharia
IDEAL_SLOPE_MV_PER_PH = -59.16  # a 25 °C (Nernst)
TEMP_COEF_PH_PER_C = 0.003      # ~0.003 pH/°C para águas de irrigação
SLOPE_OK = (95.0, 105.0)        # % do ideal
OFFSET_OK_MV = 30.0             # ±mV
DRIFT_MAX_MV_PER_DAY = 0.5      # slope drift
DRIFT_MAX_OFFSET_MV_PER_DAY = 0.3
RESPONSE_TIME_MAX_S = 90        # tempo para 63% da mudança
DAYS_CAL_WARN = 14
DAYS_CAL_ALERT = 30
DAYS_REPLACE_WARN = 180
DAYS_REPLACE_ALERT = 365


@dataclass
class Calibracao:
    data: datetime
    ponto: str
    slope_pct: float           # % do ideal
    offset_mv: float
    buffer_ph: list            # [4.01, 7.00, 10.01]
    temp_c: float
    tecnico: str = ""
    observacao: str = ""

    def valida(self) -> bool:
        return (
            SLOPE_OK[0] <= self.slope_pct <= SLOPE_OK[1]
            and abs(self.offset_mv) <= OFFSET_OK_MV
        )


class EletrodoPH:
    def __init__(self, ponto: str, calibracoes: list):
        self.ponto = ponto
        self.calibracoes = sorted(calibracoes, key=lambda c: c.data)
        if not self.calibracoes:
            raise ValueError(f"Sem calibrações para {ponto}")

    # --- 1. Compensação por temperatura
    def compensar_temperatura(self, ph_raw, temp_c, temp_ref_c=25.0):
        return ph_raw + TEMP_COEF_PH_PER_C * (temp_ref_c - temp_c)

    # --- 2. Última calibração válida
    def ultima_calibracao(self, ref=None):
        ref = ref or datetime.now()
        validas = [c for c in self.calibracoes if c.data <= ref and c.valida()]
        return validas[-1] if validas else None

    # --- 3. Idade da calibração
    def dias_desde_calibracao(self, ref=None):
        ref = ref or datetime.now()
        c = self.ultima_calibracao(ref)
        return (ref - c.data).days if c else None

    # --- 4. Drift entre calibrações consecutivas
    def drift(self):
        if len(self.calibracoes) < 2:
            return None
        out = []
        for a, b in zip(self.calibracoes, self.calibracoes[1:]):
            dt = (b.data - a.data).total_seconds() / 86400
            if dt <= 0:
                continue
            out.append({
                "de": a.data.isoformat(),
                "para": b.data.isoformat(),
                "dias": dt,
                "slope_drift_mv_d": (b.slope_pct - a.slope_pct) / dt,
                "offset_drift_mv_d": (b.offset_mv - a.offset_mv) / dt,
            })
        return out

    def drift_excede_limite(self):
        d = self.drift() or []
        return any(
            abs(x["slope_drift_mv_d"]) > DRIFT_MAX_MV_PER_DAY
            or abs(x["offset_drift_mv_d"]) > DRIFT_MAX_OFFSET_MV_PER_DAY
            for x in d
        )

    # --- 5. Score de saúde
    def saude(self, ref=None):
        ref = ref or datetime.now()
        c = self.ultima_calibracao(ref)
        if not c:
            return {"ponto": self.ponto, "score": 0, "status": "sem_calibracao"}
        score = 100.0
        # -slope
        slope_dev = max(0, abs(c.slope_pct - 100) - 5)  # 0 acima da faixa 95-105
        score -= min(30, slope_dev * 3)
        # -offset
        offset_dev = max(0, abs(c.offset_mv) - 10)
        score -= min(25, offset_dev * 2)
        # -idade da calibração
        dias = (ref - c.data).days
        score -= min(25, max(0, dias - DAYS_CAL_WARN) * 1.5)
        # -drift
        if self.drift_excede_limite():
            score -= 10
        score = max(0, min(100, score))
        status = "saudavel" if score > 80 else "atencao" if score > 50 else "substituir"
        return {
            "ponto": self.ponto,
            "score": round(score, 1),
            "status": status,
            "dias_desde_calibracao": dias,
            "slope_pct": c.slope_pct,
            "offset_mv": c.offset_mv,
        }

    # --- 6. Manutenção preditiva
    def vida_util_estimada(self, ref=None):
        ref = ref or datetime.now()
        c = self.ultima_calibracao(ref)
        if not c:
            return None
        d = self.drift()
        if not d:
            return {"dias_restantes": None, "motivo": "sem_historico_drift"}
        # extrapola: usa taxa média de drift de slope
        taxas = [abs(x["slope_drift_mv_d"]) for x in d if x["dias"] > 0]
        if not taxas:
            return None
        taxa_media = np.mean(taxas)
        if taxa_media <= 0.01:
            return {"dias_restantes": None, "motivo": "drift_desprezivel"}
        # distancia ate o limite de 5% do slope ideal
        margem = max(0, abs(c.slope_pct - 100) - 5)
        dias = int(margem / taxa_media) if taxa_media > 0 else None
        return {"dias_restantes": dias, "taxa_drift_pct_dia": round(taxa_media, 4)}


# ---- Validação cruzada com laboratório
def comparar_com_laboratorio(df_sensor, df_lab, ponto, tol_ph=0.15):
    """
    df_sensor: timestamp, ponto, ph_comp
    df_lab: data_coleta, ponto, ph_lab
    Retorna DataFrame com residual ph_sensor - ph_lab.
    """
    lab = df_lab[df_lab["ponto"] == ponto].copy()
    if lab.empty:
        return pd.DataFrame()
    sens = df_sensor[df_sensor["ponto"] == ponto].copy()
    if sens.empty:
        return pd.DataFrame()
    sens = sens.sort_values("timestamp")
    lab = lab.sort_values("data_coleta")

    # pega a leitura mais próxima da coleta
    merged = pd.merge_asof(
        lab.rename(columns={"data_coleta": "timestamp"}),
        sens[["timestamp", "ph_comp"]],
        on="timestamp",
        direction="nearest",
        tolerance=pd.Timedelta("2h"),
    )
    merged["residual"] = merged["ph_comp"] - merged["ph_lab"]
    merged["abs_residual"] = merged["residual"].abs()
    merged["alerta_bias"] = merged["abs_residual"] > tol_ph
    return merged


# ---- Resposta temporal a um degrau (início/fim de adubação)
def tempo_resposta(df, ponto, t0, ph_antes, limiar=0.63, janela_min=5):
    """
    Mede o tempo até a leitura atingir 63% da mudança total após t0.
    df: timestamp, ponto, ph_comp
    """
    d = df[(df["ponto"] == ponto) & (df["timestamp"] >= t0)].copy()
    if d.empty:
        return None
    d = d.sort_values("timestamp")
    ph_final = d["ph_comp"].iloc[min(len(d) - 1, int(janela_min * 12))]  # 5min a 5s
    delta = ph_final - ph_antes
    if abs(delta) < 0.05:
        return {"ponto": ponto, "t0": t0.isoformat(), "tempo_s": None,
                "motivo": "mudanca_insuficiente"}
    alvo = ph_antes + limiar * delta
    atingiu = d[d["ph_comp"].apply(
        lambda v: (v - alvo) * (delta > 0) >= 0
    )]
    if atingiu.empty:
        return {"ponto": ponto, "t0": t0.isoformat(), "tempo_s": None,
                "motivo": "nao_atingiu_63pct"}
    t = (atingiu["timestamp"].iloc[0] - t0).total_seconds()
    return {"ponto": ponto, "t0": t0.isoformat(), "tempo_s": t,
            "limite_s": RESPONSE_TIME_MAX_S,
            "ok": t <= RESPONSE_TIME_MAX_S}


# ---- Redundância pré/pós com válvula fechada
def validar_redundancia_pre_pos(df, tol_ph=0.10):
    """
    Com a válvula de adubação fechada, pré e pós devem convergir.
    Se divergirem consistentemente → um dos eletrodos está com problema.
    df: timestamp, ponto, ph_comp, valvula_adubo_aberta (bool)
    """
    if "valvula_adubo_aberta" not in df.columns:
        return pd.DataFrame()
    fechado = df[~df["valvula_adubo_aberta"]].copy()
    if fechado.empty:
        return pd.DataFrame()
    pivot = fechado.pivot_table(
        index="timestamp", columns="ponto", values="ph_comp", aggfunc="mean"
    )
    pre = [c for c in pivot.columns if "pre" in c.lower()]
    pos = [c for c in pivot.columns if "pos" in c.lower()]
    if not pre or not pos:
        return pd.DataFrame()
    dif = (pivot[pos[0]] - pivot[pre[0]]).abs()
    return pd.DataFrame({
        "timestamp": dif.index,
        "delta_ph": dif.values,
        "alerta_redundancia": dif.values > tol_ph,
    })


# ---- Detecção de leitura travada
def detectar_travamento(df, ponto, janela_h=3, var_min=1e-4):
    d = df[df["ponto"] == ponto].sort_values("timestamp").copy()
    if d.empty:
        return pd.DataFrame()
    var = d["ph_comp"].rolling(f"{janela_h}h", min_periods=10).var()
    d["variancia_janela"] = var
    d["alerta_travamento"] = var < var_min
    return d[["timestamp", "ponto", "ph_comp", "variancia_janela",
              "alerta_travamento"]]


# ---- Diagnóstico de ruído elétrico / aterramento
def diagnosticar_ruido(df, ponto, janela_min=5, limiar_std=0.3):
    d = df[df["ponto"] == ponto].sort_values("timestamp").copy()
    if d.empty:
        return pd.DataFrame()
    d["ph_std_5min"] = d["ph_comp"].rolling(
        f"{janela_min}min", min_periods=5).std()
    d["alerta_ruido"] = d["ph_std_5min"] > limiar_std
    # correlação com temperatura — ruído elétrico costuma ser independente
    if "temperatura" in d.columns:
        corr = d[["ph_std_5min", "temperatura"]].corr().iloc[0, 1]
        d["corr_temp"] = corr
    return d[["timestamp", "ponto", "ph_comp", "ph_std_5min",
              "alerta_ruido"]]


# ---- Resumo do estado do eletrodo por ponto
def relatorio_eletrodos(eletrodos: dict, ref=None):
    ref = ref or datetime.now()
    linhas = []
    for ponto, el in eletrodos.items():
        s = el.saude(ref)
        v = el.vida_util_estimada(ref)
        s["dias_restantes_estimado"] = v["dias_restantes"] if v else None
        linhas.append(s)
    return pd.DataFrame(linhas)