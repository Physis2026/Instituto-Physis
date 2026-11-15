"""Validação de entrada comum aos motores (só biblioteca padrão)."""
from __future__ import annotations

import importlib.util
import math
import re


class EntradaInvalida(ValueError):
    """Erro do pedido (vira HTTP 400)."""


class MotorIndisponivel(RuntimeError):
    """A biblioteca/programa do motor não está instalado (vira HTTP 503)."""


def num(d: dict, chave: str, padrao=None, minimo: float | None = None, maximo: float | None = None) -> float:
    v = d.get(chave, padrao)
    if v is None:
        raise EntradaInvalida(f"falta '{chave}'")
    if isinstance(v, bool):
        raise EntradaInvalida(f"'{chave}' deve ser número")
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise EntradaInvalida(f"'{chave}' deve ser número") from None
    if not math.isfinite(v):
        raise EntradaInvalida(f"'{chave}' deve ser finito")
    if minimo is not None and v < minimo:
        raise EntradaInvalida(f"'{chave}' abaixo de {minimo}")
    if maximo is not None and v > maximo:
        raise EntradaInvalida(f"'{chave}' acima de {maximo}")
    return v


def lista_num(d: dict, chave: str, minimo: float | None = None, maximo: float | None = None,
              tam_min: int = 1, tam_max: int = 8784, obrigatoria: bool = True) -> list[float] | None:
    v = d.get(chave)
    if v is None and not obrigatoria:
        return None
    if not isinstance(v, list) or not (tam_min <= len(v) <= tam_max):
        raise EntradaInvalida(f"'{chave}' deve ser lista com {tam_min} a {tam_max} números")
    return [num({"x": x}, "x", None, minimo, maximo) for x in v]


ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,31}$")


def ident(v, onde: str) -> str:
    s = str(v or "")
    if not ID_RE.match(s):
        raise EntradaInvalida(f"{onde}: id '{s}' inválido (1 a 31 letras, números, _ . -)")
    return s


def tem_modulo(nome: str) -> bool:
    try:
        return importlib.util.find_spec(nome) is not None
    except (ImportError, ValueError):
        return False


def exigir(*modulos: str) -> None:
    falta = [m for m in modulos if not tem_modulo(m)]
    if falta:
        raise MotorIndisponivel("motor indisponível: falta " + ", ".join(falta))
