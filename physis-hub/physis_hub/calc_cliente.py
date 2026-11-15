"""Cliente do hub para os serviços abertos do servidor da Physis: motores de cálculo (calc) e IA local.

Para colocar em physis_hub/ (ex.: physis_hub/servicos_abertos.py) quando a equipe decidir ligar.
Regras:
- Só biblioteca padrão (urllib), tempo-limite em toda chamada.
- NUNCA obrigatório: sem PHYSIS_CALC_URL, fora do ar, tempo esgotado ou resposta estranha → devolve None
  e o hub continua com as contas próprias (cargatermica.py, solar, vento.py...).
- Só fala com a rede local/interna (mesma regra de robos.destino_local), salvo PHYSIS_CALC_EXTERNO=1.
- Nada de dados pessoais: só números de engenharia vão ao serviço.

Variáveis:
  PHYSIS_CALC_URL     ex.: http://calc:8710 (compose) ou http://192.168.0.20:8710
  PHYSIS_CALC_CHAVE   opcional; vai como "Authorization: Bearer ..."
  PHYSIS_CALC_TEMPO   segundos (padrão 60; a térmica com ano inteiro pode pedir mais)
  PHYSIS_IA_URL / PHYSIS_IA_TIPO / PHYSIS_IA_MODELO — já lidos por physis_hub/robos.py (IALocal)
"""
from __future__ import annotations

import ipaddress
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("physis.calc")
MOTORES = ("pv", "eolica", "termica", "rede-agua", "drenagem")
MAX_RESPOSTA = 8 * 1024 * 1024


def destino_local(url: str) -> bool:
    """localhost, IP privado, nome sem domínio (ex.: 'calc' no compose) ou .local/.lan/.internal."""
    try:
        u = urllib.parse.urlparse(url)
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    if u.scheme not in ("http", "https") or not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return host == "localhost" or "." not in host or host.endswith((".local", ".lan", ".internal", ".localhost"))


def calc_url() -> str:
    """URL do serviço ou '' (desligado)."""
    url = (os.environ.get("PHYSIS_CALC_URL") or "").strip().rstrip("/")
    if url and not destino_local(url) and os.environ.get("PHYSIS_CALC_EXTERNO") != "1":
        log.warning("PHYSIS_CALC_URL fora da rede local: ignorada")
        return ""
    return url


def _pedir(url: str, corpo: dict | None, tempo: float) -> dict | None:
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method="POST" if dados is not None else "GET",
                                 headers={"Content-Type": "application/json", "User-Agent": "PhysisHub/1.0"})
    chave = os.environ.get("PHYSIS_CALC_CHAVE")
    if chave:
        req.add_header("Authorization", f"Bearer {chave}")
    try:
        with urllib.request.urlopen(req, timeout=tempo) as r:
            return json.loads(r.read(MAX_RESPOSTA + 1)[:MAX_RESPOSTA].decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (400, 422):                       # erro do pedido: a tela mostra a mensagem
            try:
                return json.loads(e.read(65536).decode("utf-8"))
            except (ValueError, OSError):
                return {"ok": False, "erro": f"HTTP {e.code}"}
        log.info("calc %s: HTTP %s", url, e.code)       # 401/429/503/500: trata como indisponível
        return None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        log.info("calc %s: %s", url, type(exc).__name__)
        return None


def calc_saude(tempo: float = 2.0) -> dict | None:
    """{"ok": true, "motores": {...}} ou None. Bom para a tela mostrar "cálculo avançado disponível"."""
    url = calc_url()
    return _pedir(url + "/saude", None, tempo) if url else None


def calcular(motor: str, dados: dict, tempo: float | None = None, somente_entrada: bool = False) -> dict | None:
    """Chama um motor. None = serviço ausente/fora do ar (o hub usa a conta própria)."""
    if motor not in MOTORES:
        raise ValueError(f"motor desconhecido: {motor}")
    url = calc_url()
    if not url:
        return None
    t = float(tempo or os.environ.get("PHYSIS_CALC_TEMPO") or 60)
    return _pedir(f"{url}/{motor}" + ("?somente_entrada=1" if somente_entrada else ""), dados, t)


# ── atalhos com os nomes da plataforma ───────────────────────────────────────────────────────────
def pv_horario(lat: float, lon: float, kwp: float, *, inclinacao=None, azimute=None, ghi=None, temp_ar=None, **extra):
    d = {"lat": lat, "lon": lon, "kwp": kwp, **extra}
    for k, v in (("inclinacao", inclinacao), ("azimute", azimute), ("ghi", ghi), ("temp_ar", temp_ar)):
        if v is not None:
            d[k] = v
    return calcular("pv", d)


def eolica(altura_cubo: float, rugosidade: float, *, curva=None, turbina=None, velocidades=None, weibull=None,
           altura_medicao: float = 10):
    d = {"altura_cubo": altura_cubo, "rugosidade": rugosidade, "altura_medicao": altura_medicao}
    d.update({k: v for k, v in (("curva", curva), ("turbina", turbina), ("velocidades", velocidades), ("weibull", weibull))
              if v is not None})
    return calcular("eolica", d)


def termica(clima: dict, ambiente: dict, epw: str | None = None):
    """clima/ambiente no formato de cargatermica.calcular, com U, α e FS já resolvidos em cada superfície."""
    d = {"clima": clima, "ambiente": ambiente}
    if epw:
        d["epw"] = epw
    return calcular("termica", d, tempo=float(os.environ.get("PHYSIS_CALC_TEMPO") or 180))


def rede_agua(nos: list, reservatorios: list, tubos: list, formula: str = "H-W"):
    return calcular("rede-agua", {"nos": nos, "reservatorios": reservatorios, "tubos": tubos, "formula": formula})


def drenagem(area_ha: float, impermeabilidade_pct: float, declividade_pct: float, chuva: dict, **extra):
    return calcular("drenagem", {"area_ha": area_ha, "impermeabilidade_pct": impermeabilidade_pct,
                                 "declividade_pct": declividade_pct, "chuva": chuva, **extra})


# ── IA local: o hub já tem physis_hub.robos.IALocal (PHYSIS_IA_URL). Aqui só a conferência de saúde. ──
def ia_saude(tempo: float = 2.0) -> bool:
    """True se a IA local responde (Ollama: GET /api/tags; compatível OpenAI: GET /v1/models)."""
    url = (os.environ.get("PHYSIS_IA_URL") or "").strip().rstrip("/")
    if not url or (not destino_local(url) and os.environ.get("PHYSIS_IA_EXTERNO") != "1"):
        return False
    base = url.split("/api/")[0].split("/v1/")[0]
    caminho = "/api/tags" if os.environ.get("PHYSIS_IA_TIPO") == "ollama" or "/api/" in url else "/v1/models"
    req = urllib.request.Request(base + caminho, headers={"User-Agent": "PhysisHub/1.0"})
    chave = os.environ.get("PHYSIS_IA_CHAVE")
    if chave:
        req.add_header("Authorization", f"Bearer {chave}")
    try:
        with urllib.request.urlopen(req, timeout=tempo) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False
