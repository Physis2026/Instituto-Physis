"""Integridade dos dados para registro em blockchain (docs/INTEGRIDADE_DADOS.md).

Princípio (15/11/2026): a Physis entrega o mapeamento e a integridade dos dados; o parceiro entrega a camada de
blockchain, os tokens e a custódia. Este módulo NÃO fala com nenhuma rede: ele só fecha um lote de registros
corretos, rastreáveis e auditáveis, com um resumo SHA-256 que qualquer pessoa pode recalcular.

  fechar_lote(registros, ...)   -> lote imutável (dict) com resumo
  conferir_lote(lote)           -> (ok, problemas)  refaz o resumo e confere cada registro
  corrigir(registro, novo, ...) -> registro de correção que aponta para o anterior (nada é apagado)
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json

ESQUEMA = "physis-lote/1"
QUALIDADES = ("valido", "suspeito", "corrigido")
OBRIGATORIOS = ("id", "grandeza", "valor", "unidade", "quando", "origem", "metodo", "qualidade")


def _canonico(obj) -> bytes:
    """JSON canônico: chaves em ordem, sem espaços, UTF-8. Mesmo conteúdo = mesmo resumo, em qualquer máquina."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def resumo(obj) -> str:
    return hashlib.sha256(_canonico(obj)).hexdigest()


def problemas_do_registro(r) -> list[str]:
    """O que impede o registro de entrar num lote (rastreabilidade e qualidade)."""
    if not isinstance(r, dict):
        return ["registro não é um objeto"]
    faltam = [c for c in OBRIGATORIOS if r.get(c) in (None, "", {})]
    erros = [f"{r.get('id', '?')}: falta {c}" for c in faltam]
    origem = r.get("origem") if isinstance(r.get("origem"), dict) else {}
    if r.get("origem") and not origem.get("aparelho") and not origem.get("calculo"):
        erros.append(f"{r.get('id', '?')}: origem sem aparelho nem cálculo")
    if r.get("qualidade") and r.get("qualidade") not in QUALIDADES:
        erros.append(f"{r.get('id', '?')}: qualidade inválida")
    if r.get("qualidade") == "corrigido" and not r.get("corrige"):
        erros.append(f"{r.get('id', '?')}: correção sem o registro anterior")
    v = r.get("valor")
    if isinstance(v, float) and v != v:
        erros.append(f"{r.get('id', '?')}: valor não numérico")
    return erros


def fechar_lote(registros: list[dict], *, lote_id: str, periodo: tuple[str, str], responsavel: str,
                dicionario: str, aceitar_suspeitos: bool = False) -> dict:
    """Fecha o lote. Recusa registro incompleto, id repetido e (por padrão) dado suspeito."""
    erros = [e for r in registros for e in problemas_do_registro(r)]
    ids = [r.get("id") for r in registros if isinstance(r, dict)]
    erros += [f"{i}: id repetido" for i in sorted({i for i in ids if ids.count(i) > 1})]
    if not aceitar_suspeitos:
        erros += [f"{r['id']}: dado suspeito (revisar antes de fechar)" for r in registros
                  if isinstance(r, dict) and r.get("qualidade") == "suspeito"]
    if not registros:
        erros.append("lote vazio")
    if erros:
        raise ValueError("lote não fechado:\n" + "\n".join(erros))
    ordenados = sorted(registros, key=lambda r: str(r["id"]))
    corpo = {"esquema": ESQUEMA, "lote": lote_id, "periodo": list(periodo), "responsavel": responsavel,
             "dicionario": dicionario, "quantidade": len(ordenados),
             "registros": [dict(r, resumo=resumo({k: v for k, v in r.items() if k != "resumo"})) for r in ordenados]}
    return dict(corpo, fechado_em=_dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                resumo_lote=resumo(corpo))


def conferir_lote(lote: dict) -> tuple[bool, list[str]]:
    """Refaz os resumos. Qualquer mudança depois do fechamento aparece aqui."""
    problemas = []
    corpo = {k: v for k, v in lote.items() if k not in ("fechado_em", "resumo_lote")}
    if resumo(corpo) != lote.get("resumo_lote"):
        problemas.append("resumo do lote não confere")
    for r in lote.get("registros", []):
        if resumo({k: v for k, v in r.items() if k != "resumo"}) != r.get("resumo"):
            problemas.append(f"{r.get('id', '?')}: resumo do registro não confere")
    if lote.get("quantidade") != len(lote.get("registros", [])):
        problemas.append("quantidade não confere")
    return (not problemas, problemas)


def corrigir(anterior: dict, novo_valor, *, novo_id: str, quem: str, motivo: str, quando: str) -> dict:
    """Correção sem apagar: um registro novo que aponta para o anterior e guarda o valor antigo."""
    if not motivo.strip():
        raise ValueError("correção precisa de motivo")
    return dict({k: v for k, v in anterior.items() if k != "resumo"}, id=novo_id, valor=novo_valor, qualidade="corrigido",
                corrige={"id": anterior["id"], "valor_anterior": anterior.get("valor"),
                         "resumo_anterior": anterior.get("resumo") or resumo(anterior), "quem": quem, "motivo": motivo,
                         "quando": quando})
