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
}


def tipo_da_linha(campos: dict[str, str]) -> str:
    t = campos.get("TIPO", "SOLO").strip().upper()
    return t if t in TIPOS else "SOLO"


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
    return est


def adaptar(campos: dict[str, str], org: str, lugar: str) -> list[dict]:
    """Lista de medicoes physis/1 geradas por uma linha valida."""
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
    return out
