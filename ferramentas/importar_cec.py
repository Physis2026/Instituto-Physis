#!/usr/bin/env python3
"""Importa listas públicas da CEC (California Energy Commission) para a base de equipamentos da Physis.

De onde baixar (arquivo .xlsx ou .csv, gratuito):
  Módulos FV:   https://solarequipment.energy.ca.gov/Home/PVModuleList
  Inversores:   https://solarequipment.energy.ca.gov/Home/Inverters
Salve o arquivo baixado numa pasta própria (dado de fora; não rode nada dentro dela) e rode:

    python ferramentas/importar_cec.py modulos  <arquivo.xlsx|csv> [--saida itens.json] [--mesclar] [--limite 200]
    python ferramentas/importar_cec.py inversores <arquivo.xlsx|csv> [--saida itens.json] [--mesclar]

Sem --mesclar, só grava os itens convertidos (padrão: imprime um resumo). Com --mesclar, troca na base
sistema/physis-equipamentos.json os itens cujo id começa com "cec-" pelos importados (os outros ficam).
Os cabeçalhos da CEC mudam de tempos em tempos: a leitura procura as colunas por pedaço do nome.
Só biblioteca padrão.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BASE = RAIZ / "sistema" / "physis-equipamentos.json"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _col(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def ler_tabela(caminho: Path) -> list[list[str]]:
    """Linhas de um .csv (vírgula ou ponto e vírgula) ou da primeira aba de um .xlsx."""
    if caminho.suffix.lower() == ".csv":
        texto = caminho.read_bytes().decode("utf-8-sig", errors="replace")
        dialeto = ";" if texto.count(";") > texto.count(",") else ","
        return [r for r in csv.reader(io.StringIO(texto), delimiter=dialeto)]
    z = zipfile.ZipFile(caminho)
    ss = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(NS + "si"):
            ss.append("".join(t.text or "" for t in si.iter(NS + "t")))
    folha = sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n))[0]
    linhas = []
    for row in ET.fromstring(z.read(folha)).iter(NS + "row"):
        vals: dict[int, str] = {}
        for c in row.findall(NS + "c"):
            v = c.find(NS + "v")
            if c.get("t") == "s" and v is not None:
                vals[_col(c.get("r"))] = ss[int(v.text)]
            elif c.get("t") == "inlineStr":
                vals[_col(c.get("r"))] = "".join(x.text or "" for x in c.iter(NS + "t"))
            elif v is not None:
                vals[_col(c.get("r"))] = v.text or ""
        if vals:
            linhas.append([vals.get(i, "") for i in range(max(vals) + 1)])
    return linhas


def achar_cabecalho(linhas, obrigatorias):
    """Índice da linha de cabeçalho e mapa nome->coluna, procurando cada coluna por pedaços do nome."""
    for i, l in enumerate(linhas[:40]):
        baixo = [str(x).strip().lower() for x in l]
        mapa = {}
        for chave, pedacos in obrigatorias.items():
            for j, h in enumerate(baixo):
                if any(p in h for p in pedacos):
                    mapa[chave] = j
                    break
        if all(k in mapa for k in obrigatorias if not k.startswith("?")):
            return i, mapa
    raise SystemExit("cabeçalho não reconhecido: confira se o arquivo é a lista da CEC")


def num(v):
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return None


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


def converter_modulos(linhas, data):
    i0, m = achar_cabecalho(linhas, {"fab": ["manufacturer"], "modelo": ["model number"], "pmax": ["nameplate pmax", "pmax"],
                                     "area": ["a_c", "area"], "?gama": ["γpmax", "gamma", "pmax (%/"], "?tec": ["technology", "description"]})
    itens = []
    for l in linhas[i0 + 1:]:
        g = lambda k: l[m[k]] if k in m and m[k] < len(l) else ""
        p, a = num(g("pmax")), num(g("area"))
        if not g("fab") or not p or not a:
            continue
        ef = round(p / (1000 * a) * 100, 2)
        it = {"id": "cec-fv-" + slug(g("fab") + "-" + g("modelo")), "categoria": "módulos fotovoltaicos", "subtipo": (g("?tec") or "módulo FV")[:60],
              "descricao": f"{g('fab')} {g('modelo')}", "faixa_capacidade": {"min": p, "max": p}, "unidade": "Wp",
              "eficiencia": {"indicador": "%", "tipico": ef, "faixa": [ef, ef], "condicao": "Pmax/(1000 W/m² × área), STC"},
              "potencia": {"min": p / 1000, "max": p / 1000, "unidade": "kWp"}, "vida_util_anos": [25, 30], "manutencao": "ver item genérico da classe",
              "custo_referencia_brl": {"faixa": None, "data": None, "fonte": "[MARCADOR] cotação"}, "normas": ["IEC 61215", "IEC 61730"],
              "fonte": "CEC — PV Module List (arquivo importado)", "data": data, "verificar": False, "fabricantes_referencia": [g("fab")]}
        gama = num(g("?gama"))
        if gama is not None:
            it["coef_temperatura_pmax_pct_por_C"] = gama
        itens.append(it)
    return itens


def converter_inversores(linhas, data):
    i0, m = achar_cabecalho(linhas, {"fab": ["manufacturer"], "modelo": ["model number"], "pot": ["maximum continuous output power", "power rating", "continuous"],
                                     "ef": ["weighted efficiency", "cec efficiency"], "?desc": ["description"]})
    itens = []
    for l in linhas[i0 + 1:]:
        g = lambda k: l[m[k]] if k in m and m[k] < len(l) else ""
        p, ef = num(g("pot")), num(g("ef"))
        if not g("fab") or not p or not ef:
            continue
        kw = p / 1000 if p > 100 else p   # CEC dá em W; aceita kW
        desc = g("?desc") or ""
        sub = "microinversor" if kw < 2.5 and re.search(r"micro", desc, re.I) else "string"
        itens.append({"id": "cec-inv-" + slug(g("fab") + "-" + g("modelo")), "categoria": "inversores", "subtipo": sub, "descricao": f"{g('fab')} {g('modelo')}",
                      "faixa_capacidade": {"min": kw, "max": kw}, "unidade": "kW CA",
                      "eficiencia": {"indicador": "%", "tipico": ef, "faixa": [ef, ef], "condicao": "eficiência ponderada CEC"},
                      "potencia": {"min": kw, "max": kw, "unidade": "kW CA"}, "vida_util_anos": [10, 15], "manutencao": "ver item genérico da classe",
                      "custo_referencia_brl": {"faixa": None, "data": None, "fonte": "[MARCADOR] cotação"}, "normas": ["UL 1741", "IEEE 1547"],
                      "fonte": "CEC — Inverter List (arquivo importado); no Brasil conferir registro no Inmetro", "data": data, "verificar": True,
                      "fabricantes_referencia": [g("fab")]})
    return itens


def mesclar(itens, prefixo, base=BASE):
    d = json.loads(base.read_text(encoding="utf-8"))
    d["itens"] = [i for i in d["itens"] if not i["id"].startswith(prefixo)] + itens
    vistos = set()
    d["itens"] = [i for i in d["itens"] if not (i["id"] in vistos or vistos.add(i["id"]))]
    base.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    return len(d["itens"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tipo", choices=["modulos", "inversores"])
    ap.add_argument("arquivo", type=Path)
    ap.add_argument("--saida", type=Path)
    ap.add_argument("--mesclar", action="store_true")
    ap.add_argument("--limite", type=int, default=0, help="guarda só os N de maior eficiência (0 = todos)")
    a = ap.parse_args(argv)
    data = dt.date.today().isoformat()
    linhas = ler_tabela(a.arquivo)
    itens = converter_modulos(linhas, data) if a.tipo == "modulos" else converter_inversores(linhas, data)
    if a.limite:
        itens = sorted(itens, key=lambda i: -i["eficiencia"]["tipico"])[:a.limite]
    if a.saida:
        a.saida.write_text(json.dumps(itens, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.mesclar:
        print("base agora com", mesclar(itens, "cec-fv-" if a.tipo == "modulos" else "cec-inv-"), "itens")
    print(len(itens), "itens convertidos")
    return itens


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
