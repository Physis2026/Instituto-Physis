"""Linha V6: leitura de campos, validacao de telemetria e de comandos.

Regras copiadas de `Projeto Receptor V6/src/protocolo.cpp` e `lora.cpp`.
Qualquer mudanca aqui tem de entrar tambem nos dois `protocolo.cpp` e no
`PROTOCOLO.md` (os casos de `tests/test_protocolo.py` servem de lista comum).
"""
from __future__ import annotations

import math
import os
import re

TOTAL_NOS = 99
PREFIXO_COMANDO = "CMD:"
PREFIXO_BEACON = "BCN:"
EPOCH_MIN_VALIDO = 1_700_000_000   # 2023-11-14
EPOCH_MAX_VALIDO = 4_102_444_800   # 2100-01-01
# PLUV: pluviometro de bascula (docs/ROBOS.md secao 6). MED/PUL: caixinha de remedios e pulseira
# (docs/SAUDE.md, "a homologar"); o hub as entrega a saude.py antes do adaptador generico e nunca
# as grava em `medicao`. PHYSIS_SAUDE_V6=0 volta a recusar MED/PUL (tipo_desconhecido) no receptor e no /api/v6/linha.
TIPOS_SAUDE = ("MED", "PUL")
TIPOS_CONHECIDOS = ("SOLO", "ZONA", "COL", "COM", "PLUV") + TIPOS_SAUDE
# Limites de plausibilidade fisica, largos de proposito. NAO sao faixas de operacao:
# as faixas de operacao de cada equipamento devem ser confirmadas pela equipe tecnica da Physis.
# CHI: mm de chuva no intervalo (0 a 200); PUL so e contador de pulsos quando TIPO:PLUV (na pulseira, PUL e o TIPO).
FAIXAS_PLAUSIVEIS = {"BAT": (0.0, 60.0), "RSSI": (-200.0, 20.0), "SNR": (-60.0, 60.0), "CHI": (0.0, 200.0)}


def saude_v6_ligada() -> bool:
    """PHYSIS_SAUDE_V6 (padrao 1): MED e PUL entram pelo receptor e pelo /api/v6/linha e vao para a Saude."""
    return os.environ.get("PHYSIS_SAUDE_V6", "1").strip() != "0"
LINHA_MAX = 240                    # folga sobre o maior payload (~132 B) + RSSI/SNR

SENTINELAS = {"-", "--", "---", "n/d", "nd", "null", "none", "nan"}
VERDADEIROS = {"1", "SIM", "S", "TRUE", "T", "ON", "LIGADO", "YES"}
FALSOS = {"0", "NAO", "N", "FALSE", "F", "OFF", "DESLIGADO", "NO"}
ACOES = ("SYNC", "LIM1", "LIM2", "IRR1", "IRR2", "MODO", "PING")

_RE_NUM = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")


def limpar_linha(bruta: str) -> str:
    """Uma mensagem por linha: \\r e \\n internos viram espaco (lora.cpp)."""
    return bruta.replace("\r", " ").replace("\n", " ").strip()


def extrair_campos(linha: str) -> dict[str, str]:
    """Devolve {CHAVE: valor} na ordem da linha.

    Separadores `,` e `;`. A primeira ocorrencia de cada chave vence, como em
    `extrairCampo()`. Campo sem `:` ou com valor vazio e ignorado.
    """
    campos: dict[str, str] = {}
    for parte in re.split(r"[,;]", linha):
        parte = parte.strip()
        if ":" not in parte:
            continue
        chave, valor = parte.split(":", 1)
        chave, valor = chave.strip(), valor.strip()
        if not chave or not valor or chave in campos:
            continue
        campos[chave] = valor
    return campos


def para_float(valor: str | None, padrao: float | None = None) -> float | None:
    """Numero do campo; sentinela de 'sem dado' devolve `padrao`.

    Mais estrito que `toFloat()` do firmware de proposito: `35,5` ja chegou
    partido pelo separador e texto solto nao vira zero em silencio.
    """
    if valor is None:
        return padrao
    v = valor.strip()
    if v.lower() in SENTINELAS:
        return padrao
    if not _RE_NUM.match(v):
        return padrao
    f = float(v)
    return f if math.isfinite(f) else padrao


def para_int(valor: str | None, padrao: int = 0) -> int:
    if valor is None:
        return padrao
    m = re.match(r"^\s*([+-]?\d+)", valor)
    return int(m.group(1)) if m else padrao


def para_bool(valor: str | None, padrao: bool = False) -> bool:
    if valor is None:
        return padrao
    v = valor.strip().upper()
    if v in VERDADEIROS:
        return True
    if v in FALSOS:
        return False
    f = para_float(v, None)
    return padrao if f is None else f != 0.0


def validar_telemetria(bruta: str) -> tuple[bool, str, dict[str, str]]:
    """(ok, motivo, campos). Motivos: vazia, comando, beacon, longa, sem_id, id_fora, tipo_desconhecido."""
    linha = limpar_linha(bruta)
    if not linha:
        return False, "vazia", {}
    if linha.startswith(PREFIXO_COMANDO):
        return False, "comando", {}
    if linha.startswith(PREFIXO_BEACON):
        return False, "beacon", {}
    if len(linha) > LINHA_MAX:
        return False, "longa", {}
    campos = extrair_campos(linha)
    if "ID" not in campos:
        return False, "sem_id", campos
    no = para_int(campos["ID"], -1)
    if no < 1 or no > TOTAL_NOS:
        return False, "id_fora", campos
    tipo = campos["TIPO"].strip().upper() if "TIPO" in campos else ""
    if tipo and (tipo not in TIPOS_CONHECIDOS or (tipo in TIPOS_SAUDE and not saude_v6_ligada())):
        return False, "tipo_desconhecido", campos      # um tipo novo nao pode virar "solo" em silencio
    if tipo == "PLUV" and "PUL" in campos:
        p = para_float(campos["PUL"], None)
        if p is not None and (p < 0 or p != int(p)):
            del campos["PUL"]                           # contador de pulsos: inteiro >= 0
            campos["_FORA"] = "PUL"
    fora = []
    for k, (lo, hi) in FAIXAS_PLAUSIVEIS.items():
        if k in campos:
            f = para_float(campos[k], None)
            if f is not None and not (lo <= f <= hi):
                fora.append(k)
    for k in fora:
        del campos[k]                                   # a leitura segue; o campo absurdo, nao
    if fora:
        campos["_FORA"] = ",".join(([campos["_FORA"]] if "_FORA" in campos else []) + fora)
    return True, "", campos


# ── Comandos ────────────────────────────────────────────────────────────────

def separar_comando(linha: str) -> tuple[int, str, str] | None:
    if not linha.startswith(PREFIXO_COMANDO):
        return None
    resto = linha[len(PREFIXO_COMANDO):]
    if ":" not in resto:
        return None
    alvo, depois = resto.split(":", 1)
    alvo = alvo.strip()
    if not alvo or len(alvo) > 2 or not alvo.isdigit() or not alvo.isascii():
        return None
    if ":" in depois:
        acao, arg = depois.split(":", 1)
    else:
        acao, arg = depois, ""
    return int(alvo), acao.strip().upper(), arg.strip()


def argumento_valido(acao: str, arg: str) -> bool:
    if acao == "PING":
        return arg == ""
    if acao in ("IRR1", "IRR2"):
        return arg in ("0", "1")
    if acao == "MODO":
        return arg.upper() in ("AUTO", "MANUAL")
    if acao == "SYNC":
        if not arg.isdigit() or not arg.isascii() or len(arg) > 10:
            return False
        return EPOCH_MIN_VALIDO <= int(arg) <= EPOCH_MAX_VALIDO
    if acao in ("LIM1", "LIM2"):
        # A string TODA tem de ser o numero: "35,5", "nan", "1e9" e "" caem.
        if not _RE_NUM.match(arg):
            return False
        v = float(arg)
        return math.isfinite(v) and 0.0 <= v <= 100.0
    return False


def comando_valido(linha: str) -> tuple[bool, int, str]:
    """(ok, destino, normalizada). Normalizada: CMD:<nn>:<ACAO>[:<ARG>]."""
    partes = separar_comando(limpar_linha(linha))
    if partes is None:
        return False, -1, ""
    destino, acao, arg = partes
    if destino < 0 or destino > TOTAL_NOS:
        return False, destino, ""
    if not argumento_valido(acao, arg):
        return False, destino, ""
    if acao == "MODO":
        arg = arg.upper()
    normal = f"{PREFIXO_COMANDO}{destino:02d}:{acao}"
    if arg:
        normal += f":{arg}"
    return True, destino, normal
