#!/usr/bin/env python3
"""Importa tabelas públicas do PBE/Inmetro (condicionadores de ar e outras) para a base de equipamentos da Physis.

De onde baixar (planilha .xlsx ou .csv, gratuita): portal do Inmetro, Programa Brasileiro de Etiquetagem,
"Tabelas de consumo e eficiência energética":
  https://www.gov.br/inmetro/pt-br/assuntos/avaliacao-da-conformidade/programa-brasileiro-de-etiquetagem/tabelas-de-consumo-eficiencia-energetica
Salve o arquivo numa pasta própria e rode:

    python ferramentas/importar_inmetro.py ar <arquivo.xlsx|csv> [--saida itens.json] [--mesclar]
    python ferramentas/importar_inmetro.py motores <arquivo.xlsx|csv> [--saida itens.json] [--mesclar]

Ar-condicionado: procura as colunas marca, modelo (ou modelo da unidade interna), tipo, capacidade de refrigeração
(BTU/h ou W), IDRS e classe. Motores: marca, modelo/linha, potência (cv ou kW), polos e rendimento nominal (%).
Com --mesclar, troca na base os itens "inmetro-ar-" ou "inmetro-motor-" pelos importados.
Só biblioteca padrão; reaproveita a leitura de importar_cec.py.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from importar_cec import achar_cabecalho, ler_tabela, mesclar, num, slug  # noqa: E402


def converter_ar(linhas, data):
    i0, m = achar_cabecalho(linhas, {"marca": ["marca", "fabricante"], "modelo": ["modelo"], "cap": ["capacidade"], "idrs": ["idrs", "índice de desempenho"],
                                     "?classe": ["classe"], "?tipo": ["tipo", "categoria"], "?pot": ["potência", "potencia"]})
    cab = [str(x).lower() for x in linhas[i0]]
    em_w = "(w)" in cab[m["cap"]] and "btu" not in cab[m["cap"]]
    itens = []
    for l in linhas[i0 + 1:]:
        g = lambda k: str(l[m[k]]).strip() if k in m and m[k] < len(l) else ""
        cap = num(re.sub(r"\.(?=\d{3}(\D|$))", "", g("cap")))   # "12.000" (milhar pt-BR) -> 12000
        idrs = num(g("idrs"))
        if not g("marca") or not cap or not idrs:
            continue
        btu = cap * 3.412142 if em_w else cap
        kw = round(btu / 3412.142, 2)
        tipo = (g("?tipo") or "condicionador de ar").lower()
        sistema = "split"
        itens.append({"id": "inmetro-ar-" + slug(g("marca") + "-" + g("modelo")), "categoria": "ar-condicionado", "subtipo": tipo[:60],
                      "descricao": f"{g('marca')} {g('modelo')} — {round(btu):,} BTU/h".replace(",", "."), "faixa_capacidade": {"min": kw, "max": kw},
                      "unidade": "kW térmico", "eficiencia": {"indicador": "IDRS", "tipico": idrs, "faixa": [idrs, idrs], "sazonal": idrs,
                                                              "classe_pbe": g("?classe") or None},
                      "potencia": {"min": None, "max": None, "unidade": "kW"}, "vida_util_anos": [10, 15], "manutencao": "ver item genérico da classe",
                      "custo_referencia_brl": {"faixa": None, "data": None, "fonte": "[MARCADOR] cotação"},
                      "normas": ["Portaria Inmetro nº 269/2021 (verificar vigente)"], "fonte": "Inmetro PBE — tabela de condicionadores de ar (arquivo importado)",
                      "data": data, "verificar": False, "sistema": sistema, "capacidade_nominal_btuh": round(btu), "fabricantes_referencia": [g("marca")]})
    return itens


def converter_motores(linhas, data):
    i0, m = achar_cabecalho(linhas, {"marca": ["marca", "fabricante"], "modelo": ["modelo", "linha"], "pot": ["potência", "potencia"],
                                     "rend": ["rendimento"], "?polos": ["polos", "pólos"]})
    cab = str(linhas[i0][m["pot"]]).lower()
    itens = []
    for l in linhas[i0 + 1:]:
        g = lambda k: str(l[m[k]]).strip() if k in m and m[k] < len(l) else ""
        p, r = num(g("pot")), num(g("rend"))
        if not g("marca") or not p or not r:
            continue
        kw = round(p * 0.7355, 3) if "cv" in cab else p
        eta = r / 100 if r > 1 else r
        itens.append({"id": "inmetro-motor-" + slug(f"{g('marca')}-{g('modelo')}-{kw}kw-{g('?polos')}p"), "categoria": "motores",
                      "subtipo": "indução trifásico", "descricao": f"{g('marca')} {g('modelo')} {kw} kW {g('?polos')} polos",
                      "faixa_capacidade": {"min": kw, "max": kw}, "unidade": "kW (no eixo)",
                      "eficiencia": {"indicador": "η", "tipico": round(eta, 4), "faixa": [round(eta, 4), round(eta, 4)]},
                      "potencia": {"min": round(kw / eta, 3), "max": round(kw / eta, 3), "unidade": "kW"}, "vida_util_anos": [15, 25],
                      "manutencao": "ver item genérico da classe", "custo_referencia_brl": {"faixa": None, "data": None, "fonte": "[MARCADOR] cotação"},
                      "normas": ["ABNT NBR 17094-1", "Portaria Interministerial nº 1/2017"], "fonte": "Inmetro PBE — tabela de motores (arquivo importado)",
                      "data": data, "verificar": False, "fabricantes_referencia": [g("marca")]})
    return itens


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tipo", choices=["ar", "motores"])
    ap.add_argument("arquivo", type=Path)
    ap.add_argument("--saida", type=Path)
    ap.add_argument("--mesclar", action="store_true")
    a = ap.parse_args(argv)
    data = dt.date.today().isoformat()
    linhas = ler_tabela(a.arquivo)
    itens = converter_ar(linhas, data) if a.tipo == "ar" else converter_motores(linhas, data)
    if a.saida:
        a.saida.write_text(json.dumps(itens, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.mesclar:
        print("base agora com", mesclar(itens, "inmetro-ar-" if a.tipo == "ar" else "inmetro-motor-"), "itens")
    print(len(itens), "itens convertidos")
    return itens


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
