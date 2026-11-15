"""Adaptador linha V6 -> medicoes physis/1, por tipo de dispositivo.

Tipo vem da chave de extensao `TIPO` (docs/EXTENSAO_V6.md). Sem `TIPO`, e o no
de solo e irrigacao do Transmissor V6. O receptor aceita e repassa chaves
desconhecidas, entao a extensao nao exige mudanca no firmware do receptor.
"""
from __future__ import annotations

from . import nucleo
from .protocolo import para_bool, para_float, para_int

TIPOS = {
    "SOLO": "No de solo e irrigacao (Transmissor V6)",
    "ZONA": "Irrigacao por zonas com bomba (Caixinha)",
    "COL": "Coleira (SmartColar)",
    "COM": "Comedouro (AutoFeeder)",
    "PLUV": "Pluviometro de bascula",
    "SEC": "Secador solar (a homologar)",
    "ENE": "Medidor de energia (potencia ativa, tensao, corrente, fator de potencia)",
    "HID": "Medidor de agua (vazao e pressao)",
}
# MED e PUL (Saude) nunca passam por aqui: o hub as entrega a saude.py antes (dado sensivel fora de `medicao`).
INTENSIDADE_INTERVALO_MAX_S = 3 * 3600     # intervalo maior que isso: a intensidade nao e calculada


def tipo_da_linha(campos: dict[str, str]) -> str:
    t = campos.get("TIPO", "SOLO").strip().upper()
    return t if t in TIPOS else "SOLO"


def intensidade_chuva(mm: float | None, intervalo_s: float | None) -> float | None:
    """mm/h no intervalo entre duas linhas do pluviometro; None sem intervalo valido."""
    if mm is None or not intervalo_s or intervalo_s <= 0 or intervalo_s > INTENSIDADE_INTERVALO_MAX_S:
        return None
    return round(mm * 3600.0 / intervalo_s, 2)


def media_controle(u1: float | None, u2: float | None) -> float | None:
    """Mesma regra de `umidadeMedia()` do no: se um sensor falha, vale o outro."""
    validos = [u for u in (u1, u2) if u is not None]
    return sum(validos) / len(validos) if validos else None


def _m(lista, org, grandeza, ativo, valor, ts, qualidade="boa"):
    if valor is None:
        return
    topico = nucleo.montar_topico(org, grandeza, ativo)
    if topico is None:
        return
    lista.append({
        "contrato": nucleo.VERSAO_CONTRATO, "org_id": org, "topico": topico,
        "grandeza": grandeza, "ativo": ativo, "valor": float(valor),
        "unidade": nucleo.unidade(grandeza), "ts": ts, "qualidade": qualidade,
        "alarme": nucleo.avaliar_alarme(grandeza, float(valor)),
    })


def interpretar(campos: dict[str, str]) -> dict:
    """Estado legivel do dispositivo a partir dos campos da linha."""
    tipo = tipo_da_linha(campos)
    f = lambda k: para_float(campos.get(k))
    est = {
        "id": para_int(campos.get("ID"), -1), "tipo": tipo,
        "ts": para_int(campos.get("TS"), 0), "bat": f("BAT"),
        "rssi": f("RSSI"), "snr": f("SNR"),
    }
    if tipo in ("SOLO", "ZONA"):
        u1, u2 = f("U1"), f("U2")
        p1 = f("P1")
        est.update({
            "u1": u1, "u2": u2, "media": media_controle(u1, u2),
            "ir1": para_bool(campos.get("IR1")), "ir2": para_bool(campos.get("IR2")),
            "lim1": f("LIM1"), "lim2": f("LIM2"),
            "p1": p1, "aprendendo": p1 == -1.0,
            "t": f("T"), "uar": f("UAR"), "tsolo": f("TSOLO"),
        })
        if tipo == "ZONA":
            est["bomba"] = para_bool(campos.get("BOMBA"))
            est["tmax"] = f("TMAX")
    elif tipo == "COL":
        est.update({
            "lat": f("LAT"), "lon": f("LON"), "gps": para_bool(campos.get("GPS")),
            "atv": para_int(campos.get("ATV"), 0), "imp": para_bool(campos.get("IMP")),
        })
    elif tipo == "COM":
        est.update({
            "niv": f("NIV"), "porc": para_int(campos.get("PORC"), 0),
            "tag": campos.get("TAG", ""), "bloq": para_bool(campos.get("BLOQ")),
        })
    elif tipo == "PLUV":
        pul = para_float(campos.get("PUL"))
        est.update({"chi": f("CHI"), "pul": int(pul) if pul is not None else None})
    elif tipo == "SEC":
        b = lambda k: None if para_float(campos.get(k)) is None else para_bool(campos.get(k))
        est.update({"ti": f("TI"), "ui": f("UI"), "te": f("TE"), "ue": f("UE"), "tc": f("TC"),
                    "vent": b("VENT"), "abt": b("ABT"), "peso": f("PESO"), "irr": f("IRR")})
    elif tipo == "ENE":
        est.update({"pw": f("PW"), "qr": f("QR"), "s": f("S"), "v": f("V"), "i": f("I"), "fp": f("FP")})
    elif tipo == "HID":
        est.update({"q": f("Q"), "pr": f("PR")})
    return est


def adaptar(campos: dict[str, str], org: str, lugar: str, intervalo_s: float | None = None) -> list[dict]:
    """Lista de medicoes physis/1 geradas por uma linha valida.

    intervalo_s: segundos desde a linha anterior do mesmo no (o hub informa); so o pluviometro usa,
    para a intensidade da chuva em mm/h."""
    e = interpretar(campos)
    base = f"{lugar}-no{e['id']:02d}"
    ts, out = e["ts"], []
    _m(out, org, "bateria", base, e["bat"], ts)
    _m(out, org, "rssi", base, e["rssi"], ts)
    _m(out, org, "snr", base, e["snr"], ts)
    if e["tipo"] in ("SOLO", "ZONA"):
        _m(out, org, "umidade_solo", base + "-a", e["u1"], ts)
        _m(out, org, "umidade_solo", base + "-b", e["u2"], ts)
        if e["tipo"] == "SOLO":
            _m(out, org, "umidade_solo", base, e["media"], ts)
        _m(out, org, "estado", base + "-valvula1", 1.0 if e["ir1"] else 0.0, ts)
        _m(out, org, "estado", base + "-valvula2", 1.0 if e["ir2"] else 0.0, ts)
        if e["p1"] is not None and e["p1"] >= 0:
            _m(out, org, "previsao_min", base, e["p1"], ts)
        _m(out, org, "temperatura", base + "-ar", e["t"], ts)
        _m(out, org, "umidade", base + "-ar", e["uar"], ts)
        _m(out, org, "temperatura", base + "-solo", e["tsolo"], ts)
        if e["tipo"] == "ZONA":
            _m(out, org, "estado", base + "-bomba", 1.0 if e.get("bomba") else 0.0, ts)
    elif e["tipo"] == "COL":
        if e["gps"]:
            _m(out, org, "latitude", base, e["lat"], ts)
            _m(out, org, "longitude", base, e["lon"], ts)
        _m(out, org, "atividade", base, float(e["atv"]), ts)
        _m(out, org, "impacto", base, 1.0 if e["imp"] else 0.0, ts)
    elif e["tipo"] == "COM":
        _m(out, org, "nivel", base, e["niv"], ts)
        _m(out, org, "porcoes", base, float(e["porc"]), ts)
    elif e["tipo"] == "PLUV":
        _m(out, org, "chuva", base, e["chi"], ts)
        _m(out, org, "chuva_intensidade", base, intensidade_chuva(e["chi"], intervalo_s), ts)
    elif e["tipo"] == "SEC":
        _m(out, org, "temperatura_interna", base, e["ti"], ts)
        _m(out, org, "umidade_interna", base, e["ui"], ts)
        _m(out, org, "temperatura_coletor", base, e["tc"], ts)
        _m(out, org, "temperatura", base + "-ext", e["te"], ts)
        _m(out, org, "umidade", base + "-ext", e["ue"], ts)
        _m(out, org, "peso_produto", base, e["peso"], ts)
        _m(out, org, "irradiancia", base, e["irr"], ts)
        if e["vent"] is not None:
            _m(out, org, "estado", base + "-ventilador", 1.0 if e["vent"] else 0.0, ts)
        if e["abt"] is not None:
            _m(out, org, "estado", base + "-tampa", 1.0 if e["abt"] else 0.0, ts)
    elif e["tipo"] == "ENE":
        # "energia" no contrato physis/1 é potência ativa em kW (nucleo.FAIXAS); o modelo de consumo faz média do dia × 24 h
        _m(out, org, "energia", base, e["pw"], ts)
        _m(out, org, "potencia_reativa", base, e["qr"], ts)      # só o medido; P, Q, S e FP do dia: aprendizado.potencias_dia
        _m(out, org, "potencia_aparente", base, e["s"], ts)
        _m(out, org, "tensao", base, e["v"], ts)
        _m(out, org, "corrente", base, e["i"], ts)
        _m(out, org, "fp", base, e["fp"], ts)
    elif e["tipo"] == "HID":
        _m(out, org, "vazao", base, e["q"], ts)
        _m(out, org, "pressao", base, e["pr"], ts)
    return out
