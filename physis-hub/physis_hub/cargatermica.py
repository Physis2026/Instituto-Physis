"""Carga térmica de verão por ambiente — espelho em Python de sistema/physis-cargatermica.js.

Mesmas fórmulas e mesmas tabelas (bloco DADOS idêntico ao do .js; o teste confere). Serve para os testes
(physis-hub/tests/test_cargatermica.py) e para o servidor, se um dia precisar calcular sem navegador.
Método resumido em physis-hub/docs/CARGA_TERMICA.md. Sem dependências.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

DADOS = json.loads(r'''{
 "versao": 1,
 "constantes": {
  "h_ext": 17,
  "delta_r_horizontal": 3.9,
  "refletancia_solo": 0.2,
  "c_sensivel": 1.23,
  "c_latente": 3010,
  "btu_por_w": 3.412142,
  "w_por_tr": 3516.853,
  "_fonte": "ASHRAE Handbook Fundamentals (cap. 18): h_ext ≈ 17 W/m²K e correção de onda longa de 3,9 K em superfície horizontal; 1,23 W/(L/s·K) e 3010 W/(L/s) por kg/kg para ar a 1,2 kg/m³"
 },
 "padroes": {
  "pe_direito": 2.8,
  "iluminacao_wm2": 10,
  "equipamentos_wm2": 10,
  "infiltracao_ach": 0.5,
  "tint": 24,
  "urint": 50,
  "fs": 1.1,
  "horas": [
   8,
   9,
   10,
   11,
   12,
   13,
   14,
   15,
   16,
   17,
   18
  ],
  "ini": 8,
  "fim": 18,
  "horas_ano": 2600,
  "fator_carga": 0.5,
  "fator_adjacente": 0.5,
  "_fonte": "Interior 24 °C / 50 % UR: faixa de conforto de verão da ABNT NBR 16401-2:2008 (seção de parâmetros de conforto). Iluminação, equipamentos, infiltração, 2600 h/ano (10 h × 260 dias) e fator de carga 0,5: premissa Physis — verificar por projeto"
 },
 "fracao_amplitude": [
  0.82,
  0.88,
  0.92,
  0.95,
  0.98,
  1.0,
  0.98,
  0.91,
  0.74,
  0.55,
  0.38,
  0.23,
  0.13,
  0.05,
  0.0,
  0.0,
  0.06,
  0.14,
  0.24,
  0.39,
  0.5,
  0.59,
  0.68,
  0.75
 ],
 "_fracao_amplitude_fonte": "ASHRAE Handbook Fundamentals (cap. 14), fração da amplitude diária por hora solar; índice 0 = meia-noite. T(h) = TBS_projeto − amplitude × fração(h)",
 "ceu_claro": [
  [
   1230,
   0.142,
   0.058
  ],
  [
   1215,
   0.144,
   0.06
  ],
  [
   1186,
   0.156,
   0.071
  ],
  [
   1136,
   0.18,
   0.097
  ],
  [
   1104,
   0.196,
   0.121
  ],
  [
   1088,
   0.205,
   0.134
  ],
  [
   1085,
   0.207,
   0.136
  ],
  [
   1107,
   0.201,
   0.122
  ],
  [
   1151,
   0.177,
   0.092
  ],
  [
   1192,
   0.16,
   0.073
  ],
  [
   1221,
   0.149,
   0.063
  ],
  [
   1233,
   0.142,
   0.057
  ]
 ],
 "_ceu_claro_fonte": "Modelo de céu claro da ASHRAE (edições 1985–2005 do Fundamentals): A (W/m²), B e C por mês, dia 21. I_DN = A·exp(−B/sen β). Verificar: as edições novas usam o modelo tau.",
 "dia_21": [
  21,
  52,
  80,
  111,
  141,
  172,
  202,
  233,
  264,
  294,
  325,
  355
 ],
 "orientacoes": {
  "N": 0,
  "NE": 45,
  "L": 90,
  "SE": 135,
  "S": 180,
  "SO": 225,
  "O": 270,
  "NO": 315,
  "H": -1
 },
 "cores": {
  "branca": 0.2,
  "clara": 0.3,
  "media": 0.6,
  "escura": 0.8,
  "preta": 0.95,
  "_fonte": "absortância solar típica por cor de superfície (faixas como as da ABNT NBR 15220-2, anexo de absortâncias) — verificar com o material real"
 },
 "atividades": {
  "repouso": {
   "nome": "Sentado em repouso (sala de espera, cinema)",
   "sens": 65,
   "lat": 30
  },
  "escritorio": {
   "nome": "Escritório, trabalho leve sentado",
   "sens": 75,
   "lat": 55
  },
  "residencial": {
   "nome": "Residência, atividade leve em pé ou sentado",
   "sens": 75,
   "lat": 55
  },
  "restaurante": {
   "nome": "Restaurante (refeição)",
   "sens": 80,
   "lat": 80
  },
  "comercio": {
   "nome": "Loja, em pé, andando devagar",
   "sens": 80,
   "lat": 80
  },
  "sala_aula": {
   "nome": "Sala de aula",
   "sens": 70,
   "lat": 45
  },
  "trabalho_leve": {
   "nome": "Bancada, trabalho leve em pé",
   "sens": 80,
   "lat": 140
  },
  "danca": {
   "nome": "Dança moderada",
   "sens": 90,
   "lat": 160
  },
  "academia": {
   "nome": "Academia, exercício",
   "sens": 210,
   "lat": 315
  },
  "_fonte": "ASHRAE Handbook Fundamentals (cap. 18, tabela de calor liberado por pessoa, valores ajustados); tabela equivalente no anexo de cargas internas da ABNT NBR 16401-1:2008 — verificar"
 },
 "ar_externo": {
  "escritorio": {
   "nome": "Escritório",
   "rp": 2.5,
   "ra": 0.3
  },
  "residencial": {
   "nome": "Residência (sala, quarto)",
   "rp": 2.5,
   "ra": 0.3
  },
  "sala_aula": {
   "nome": "Sala de aula",
   "rp": 5.0,
   "ra": 0.6
  },
  "comercio": {
   "nome": "Loja",
   "rp": 3.8,
   "ra": 0.6
  },
  "restaurante": {
   "nome": "Restaurante, salão",
   "rp": 3.8,
   "ra": 0.9
  },
  "academia": {
   "nome": "Academia",
   "rp": 10.0,
   "ra": 0.3
  },
  "reuniao": {
   "nome": "Sala de reunião, auditório",
   "rp": 2.5,
   "ra": 0.3
  },
  "_fonte": "Lógica da ABNT NBR 16401-3:2008 (vazão eficaz = Rp × pessoas + Ra × área; tabela de vazões por tipo de local, nível 1). Valores lembrados da tabela, alinhados à ASHRAE 62.1 — verificar na norma antes de emitir"
 },
 "materiais": {
  "tijolo_6f_14": {
   "nome": "Tijolo cerâmico 6 furos rebocado (14 cm)",
   "tipo": "parede",
   "u": 2.48,
   "atraso": 3.3,
   "amortecimento": 0.421,
   "composicao": "tijolo_6f_14"
  },
  "tijolo_macico_25": {
   "nome": "Tijolo maciço rebocado (≈ 25 cm)",
   "tipo": "parede",
   "u": 2.04,
   "atraso": 7.8,
   "amortecimento": 0.13,
   "composicao": "tijolo_macico_25"
  },
  "bloco_concreto_14": {
   "nome": "Bloco de concreto rebocado (14 cm)",
   "tipo": "parede",
   "u": 2.78,
   "atraso": 3.6,
   "amortecimento": 0.39,
   "composicao": "bloco_concreto_14"
  },
  "concreto_10": {
   "nome": "Parede de concreto maciço (10 cm)",
   "tipo": "parede",
   "u": 4.4,
   "atraso": 2.6,
   "amortecimento": 0.506,
   "composicao": "concreto_10"
  },
  "drywall_la": {
   "nome": "Drywall ou steel frame com lã mineral",
   "tipo": "parede",
   "u": 0.67,
   "atraso": 2.6,
   "amortecimento": 0.506,
   "composicao": "drywall_la"
  },
  "madeira_tabua": {
   "nome": "Tábua de madeira (2,5 cm)",
   "tipo": "parede",
   "u": 2.97,
   "atraso": 1.2,
   "amortecimento": 0.73,
   "composicao": "madeira_tabua"
  },
  "taipa_30": {
   "nome": "Taipa de pilão (30 cm)",
   "tipo": "parede",
   "u": 2.26,
   "atraso": 8.6,
   "amortecimento": 0.105,
   "composicao": "taipa_30"
  },
  "adobe_25": {
   "nome": "Adobe rebocado com terra (25 cm)",
   "tipo": "parede",
   "u": 1.73,
   "atraso": 8.3,
   "amortecimento": 0.114,
   "composicao": "adobe_25"
  },
  "btc_15": {
   "nome": "Tijolo de solo-cimento (BTC) rebocado (15 cm)",
   "tipo": "parede",
   "u": 2.75,
   "atraso": 5.0,
   "amortecimento": 0.27,
   "composicao": "btc_15"
  },
  "cob_40": {
   "nome": "Cob (terra, palha e areia moldada, 40 cm)",
   "tipo": "parede",
   "u": 1.35,
   "atraso": 13.6,
   "amortecimento": 0.028,
   "composicao": "cob_40"
  },
  "pau_a_pique_15": {
   "nome": "Pau a pique (taipa de mão, 15 cm)",
   "tipo": "parede",
   "u": 2.8,
   "atraso": 4.6,
   "amortecimento": 0.3,
   "composicao": "pau_a_pique_15"
  },
  "superadobe_35": {
   "nome": "Superadobe (sacos de terra, 35 cm)",
   "tipo": "parede",
   "u": 1.68,
   "atraso": 10.6,
   "amortecimento": 0.062,
   "composicao": "superadobe_35"
  },
  "fardo_palha_45": {
   "nome": "Fardo de palha rebocado com terra (45 cm)",
   "tipo": "parede",
   "u": 0.13,
   "atraso": 21.1,
   "amortecimento": 0.004,
   "composicao": "fardo_palha_45"
  },
  "canhamo_cal_30": {
   "nome": "Cânhamo e cal (30 cm)",
   "tipo": "parede",
   "u": 0.22,
   "atraso": 19.2,
   "amortecimento": 0.007,
   "composicao": "canhamo_cal_30"
  },
  "telha_ceramica_forro_madeira": {
   "nome": "Telha cerâmica com forro de madeira",
   "tipo": "cobertura",
   "u": 2.0,
   "atraso": 1.3,
   "amortecimento": 0.712,
   "composicao": "telha_ceramica_forro_madeira"
  },
  "telha_ceramica_laje": {
   "nome": "Telha cerâmica com laje mista (12 cm)",
   "tipo": "cobertura",
   "u": 2.06,
   "atraso": 5.2,
   "amortecimento": 0.256,
   "composicao": "telha_ceramica_laje"
  },
  "fibrocimento_sem_forro": {
   "nome": "Telha de fibrocimento sem forro",
   "tipo": "cobertura",
   "u": 4.56,
   "atraso": 0.2,
   "amortecimento": 0.949,
   "composicao": "fibrocimento_sem_forro"
  },
  "fibrocimento_laje": {
   "nome": "Telha de fibrocimento com laje (10 cm)",
   "tipo": "cobertura",
   "u": 2.06,
   "atraso": 5.2,
   "amortecimento": 0.256,
   "composicao": "fibrocimento_laje"
  },
  "metalica_sem_forro": {
   "nome": "Telha metálica sem forro",
   "tipo": "cobertura",
   "u": 4.76,
   "atraso": 0.0,
   "amortecimento": 1.0,
   "composicao": "metalica_sem_forro"
  },
  "sanduiche_pu_30": {
   "nome": "Telha sanduíche metálica com PU (30 mm)",
   "tipo": "cobertura",
   "u": 0.83,
   "atraso": 1.2,
   "amortecimento": 0.73,
   "composicao": "sanduiche_pu_30"
  },
  "laje_exposta_10": {
   "nome": "Laje de concreto exposta (10 cm)",
   "tipo": "cobertura",
   "u": 3.74,
   "atraso": 2.6,
   "amortecimento": 0.506,
   "composicao": "laje_exposta_10"
  },
  "telhado_verde_extensivo": {
   "nome": "Telhado verde extensivo (laje + 10 cm de substrato)",
   "tipo": "cobertura",
   "u": 2.11,
   "atraso": 6.5,
   "amortecimento": 0.182,
   "absortancia": 0.3,
   "composicao": "telhado_verde_extensivo"
  },
  "telhado_verde_intensivo": {
   "nome": "Telhado verde intensivo (laje + 30 cm de substrato)",
   "tipo": "cobertura",
   "u": 1.15,
   "atraso": 13.9,
   "amortecimento": 0.026,
   "absortancia": 0.25,
   "composicao": "telhado_verde_intensivo"
  },
  "palha_sape": {
   "nome": "Cobertura de palha ou sapê (≈ 20 cm)",
   "tipo": "cobertura",
   "u": 0.33,
   "atraso": 8.3,
   "amortecimento": 0.114,
   "composicao": "palha_sape"
  },
  "vidro_simples": {
   "nome": "Vidro simples incolor 6 mm",
   "tipo": "vidro",
   "u": 5.7,
   "fs": 0.82
  },
  "vidro_controle_solar": {
   "nome": "Vidro de controle solar (refletivo/serigrafado)",
   "tipo": "vidro",
   "u": 5.5,
   "fs": 0.45
  },
  "vidro_duplo": {
   "nome": "Vidro duplo incolor",
   "tipo": "vidro",
   "u": 2.8,
   "fs": 0.7
  },
  "vidro_duplo_lowe": {
   "nome": "Vidro duplo com baixo emissivo",
   "tipo": "vidro",
   "u": 1.8,
   "fs": 0.4
  },
  "policarbonato_alveolar": {
   "nome": "Policarbonato alveolar 10 mm",
   "tipo": "vidro",
   "u": 3.0,
   "fs": 0.75
  },
  "laje_entre_pisos": {
   "nome": "Laje de concreto com piso (12 cm)",
   "tipo": "piso",
   "u": 3.94,
   "atraso": 3.2,
   "amortecimento": 0.433,
   "composicao": "laje_entre_pisos"
  },
  "_fonte": "U e atraso de cada parede/cobertura vêm das composições de sistema/physis-materiais.json (método da ABNT NBR 15220-2 ou valor tabelado da NBR 15220-3); amortecimento = exp(−2π·atraso/24) (premissa Physis). Vidros: faixas de catálogo público.",
  "_verificar": true,
  "terra_palha_25": {
   "nome": "Terra-palha (25 cm) com reboco de terra",
   "tipo": "parede",
   "u": 0.82,
   "atraso": 10.7,
   "amortecimento": 0.061,
   "composicao": "terra_palha_25"
  }
 },
 "cidades": [
  {
   "nome": "São Paulo",
   "uf": "SP",
   "lat": -23.6,
   "alt": 800,
   "tbs": 31.6,
   "tbu": 21.4,
   "dr": 9.0
  },
  {
   "nome": "Rio de Janeiro",
   "uf": "RJ",
   "lat": -22.9,
   "alt": 5,
   "tbs": 35.2,
   "tbu": 25.0,
   "dr": 7.0
  },
  {
   "nome": "Brasília",
   "uf": "DF",
   "lat": -15.8,
   "alt": 1060,
   "tbs": 31.6,
   "tbu": 18.8,
   "dr": 11.5
  },
  {
   "nome": "Belo Horizonte",
   "uf": "MG",
   "lat": -19.9,
   "alt": 790,
   "tbs": 32.0,
   "tbu": 20.6,
   "dr": 10.0
  },
  {
   "nome": "Salvador",
   "uf": "BA",
   "lat": -12.9,
   "alt": 10,
   "tbs": 32.0,
   "tbu": 25.0,
   "dr": 6.0
  },
  {
   "nome": "Recife",
   "uf": "PE",
   "lat": -8.1,
   "alt": 10,
   "tbs": 32.6,
   "tbu": 25.0,
   "dr": 7.0
  },
  {
   "nome": "Fortaleza",
   "uf": "CE",
   "lat": -3.8,
   "alt": 25,
   "tbs": 33.0,
   "tbu": 25.0,
   "dr": 7.0
  },
  {
   "nome": "Natal",
   "uf": "RN",
   "lat": -5.8,
   "alt": 50,
   "tbs": 31.8,
   "tbu": 25.2,
   "dr": 6.0
  },
  {
   "nome": "São Luís",
   "uf": "MA",
   "lat": -2.5,
   "alt": 50,
   "tbs": 33.0,
   "tbu": 25.8,
   "dr": 7.5
  },
  {
   "nome": "Teresina",
   "uf": "PI",
   "lat": -5.1,
   "alt": 70,
   "tbs": 38.2,
   "tbu": 23.5,
   "dr": 13.0
  },
  {
   "nome": "Belém",
   "uf": "PA",
   "lat": -1.4,
   "alt": 15,
   "tbs": 33.8,
   "tbu": 26.0,
   "dr": 8.0
  },
  {
   "nome": "Manaus",
   "uf": "AM",
   "lat": -3.1,
   "alt": 70,
   "tbs": 35.0,
   "tbu": 25.8,
   "dr": 9.0
  },
  {
   "nome": "Cuiabá",
   "uf": "MT",
   "lat": -15.6,
   "alt": 180,
   "tbs": 37.6,
   "tbu": 23.4,
   "dr": 11.0
  },
  {
   "nome": "Campo Grande",
   "uf": "MS",
   "lat": -20.5,
   "alt": 560,
   "tbs": 34.4,
   "tbu": 22.4,
   "dr": 11.0
  },
  {
   "nome": "Goiânia",
   "uf": "GO",
   "lat": -16.7,
   "alt": 750,
   "tbs": 34.5,
   "tbu": 20.5,
   "dr": 12.0
  },
  {
   "nome": "Vitória",
   "uf": "ES",
   "lat": -20.3,
   "alt": 5,
   "tbs": 34.0,
   "tbu": 25.5,
   "dr": 7.0
  },
  {
   "nome": "Curitiba",
   "uf": "PR",
   "lat": -25.4,
   "alt": 910,
   "tbs": 30.5,
   "tbu": 20.5,
   "dr": 10.0
  },
  {
   "nome": "Florianópolis",
   "uf": "SC",
   "lat": -27.6,
   "alt": 5,
   "tbs": 32.4,
   "tbu": 25.0,
   "dr": 7.0
  },
  {
   "nome": "Porto Alegre",
   "uf": "RS",
   "lat": -30.0,
   "alt": 5,
   "tbs": 35.5,
   "tbu": 24.0,
   "dr": 10.0
  }
 ],
 "_cidades_fonte": "Condições externas de verão (TBS de projeto com frequência 0,4 %, TBU coincidente médio e amplitude diária) lembradas dos dados climáticos de projeto da ASHRAE, mesma origem da tabela de cidades do anexo da ABNT NBR 16401-1:2008. Todos os valores: verificar na tabela vigente antes de emitir.",
 "_cidades_verificar": true,
 "regras_sistema": {
  "split_max_ambiente_kw": 17.6,
  "split_max_total_tr": 20,
  "vrf_min_tr": 3,
  "vrf_max_tr": 150,
  "vrf_min_ambientes": 3,
  "vrf_ideal_tr": 6,
  "vrf_ideal_ambientes": 4,
  "chiller_min_tr": 40,
  "chiller_ideal_tr": 100,
  "chiller_agua_min_tr": 150,
  "_fonte": "premissa Physis (prática de mercado) — revisar por projeto"
 },
 "sistemas_padrao": {
  "split": {
   "sazonal": 6.0,
   "aux": 1.0
  },
  "vrf": {
   "sazonal": 6.0,
   "aux": 1.0
  },
  "chiller": {
   "sazonal": 4.6,
   "aux": 1.15
  },
  "_fonte": "usado só quando a base physis-equipamentos.json não está disponível"
 }
}''')

RAD = math.pi / 180
K = DADOS["constantes"]
P = DADOS["padroes"]
COMP = ["envoltoria", "vidro_solar", "vidro_conducao", "pessoas_s", "pessoas_l", "iluminacao", "equipamentos",
        "infiltracao_s", "infiltracao_l", "ar_externo_s", "ar_externo_l"]
LATENTES = ["pessoas_l", "infiltracao_l", "ar_externo_l"]


def _tem(v) -> bool:
    if v is None or v == "" or isinstance(v, bool):
        return False
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def _n(v) -> float:
    return float(v) if _tem(v) else 0.0


def _ou(v, d):
    return float(v) if _tem(v) else d


# ───────── Psicrometria ─────────
def pressao(alt):
    return 101.325 * (1 - 2.25577e-5 * alt) ** 5.2559


def pws(t):
    return 0.61094 * math.exp(17.625 * t / (t + 243.04))


def wsat(t, p):
    s = pws(t)
    return 0.621945 * s / (p - s)


def w_bulbos(tbs, tbu, p):
    return ((2501 - 2.326 * tbu) * wsat(tbu, p) - 1.006 * (tbs - tbu)) / (2501 + 1.86 * tbs - 4.186 * tbu)


def w_ur(t, ur, p):
    pv = ur / 100 * pws(t)
    return 0.621945 * pv / (p - pv)


# ───────── Clima ─────────
def cidade_por_nome(nome):
    s = str(nome or "").strip().lower()
    return next((c for c in DADOS["cidades"] if c["nome"].lower() == s), None)


def resolver_clima(clima=None, opcoes=None):
    c, op = clima or {}, opcoes or {}
    cid = cidade_por_nome(c.get("cidade"))
    avisos = []

    def pega(k, d):
        if _tem(c.get(k)):
            return float(c[k])
        if cid and _tem(cid.get(k)):
            return float(cid[k])
        return d
    if not cid and not _tem(c.get("tbs")):
        avisos.append("Sem cidade nem TBS externa: usado 32 °C / TBU 24 °C só como exemplo.")
    r = {"cidade": cid["nome"] if cid else (c.get("cidade") or ""), "lat": pega("lat", -15.8), "alt": pega("alt", 0),
         "tbs": pega("tbs", 32), "tbu": pega("tbu", 24), "dr": pega("dr", 10),
         "tint": _ou(c.get("tint"), P["tint"]), "urint": _ou(c.get("urint"), P["urint"])}
    r["p"] = pressao(r["alt"])
    if _tem(c.get("w")):
        r["w_ext"] = float(c["w"]) / 1000
    elif _tem(c.get("ur")):
        r["w_ext"] = w_ur(r["tbs"], float(c["ur"]), r["p"])
    else:
        r["w_ext"] = w_bulbos(r["tbs"], r["tbu"], r["p"])
    r["w_int"] = w_ur(r["tint"], r["urint"], r["p"])
    # Math.round do JS arredonda .5 para cima
    r["mes"] = min(12, max(1, math.floor(float(op["mes"]) + 0.5))) if _tem(op.get("mes")) else (1 if r["lat"] <= 0 else 7)
    r["decl"] = float(op["declinacao"]) if _tem(op.get("declinacao")) else \
        23.45 * math.sin(360 * (284 + DADOS["dia_21"][r["mes"] - 1]) / 365 * RAD)
    r["text"] = [r["tbs"] - r["dr"] * f for f in DADOS["fracao_amplitude"]]
    r["avisos"] = avisos
    return r


# ───────── Sol ─────────
def sol(cl, h):
    L, d, H = cl["lat"] * RAD, cl["decl"] * RAD, 15 * (h - 12) * RAD
    sb = math.cos(L) * math.cos(d) * math.cos(H) + math.sin(L) * math.sin(d)
    if sb <= 0:
        return {"sb": 0, "cb": 1, "az": 0, "idn": 0, "C": 0}
    cb = math.sqrt(max(0.0, 1 - sb * sb))
    A, B, C = DADOS["ceu_claro"][cl["mes"] - 1]
    if cb < 1e-9:  # sol a pino: azimute indefinido e cos β = 0
        az = 0.0
    else:
        az = math.atan2(-math.cos(d) * math.sin(H) / cb, (math.sin(d) - sb * math.sin(L)) / (cb * math.cos(L))) / RAD
    return {"sb": sb, "cb": cb, "az": az, "idn": A * math.exp(-B / sb), "C": C}


def irradiancia(cl, h, orient):
    s = sol(cl, h)
    if s["idn"] <= 0:
        return 0.0
    if orient < 0:
        return s["idn"] * s["sb"] + s["C"] * s["idn"]
    cos_t = s["cb"] * math.cos((s["az"] - orient) * RAD)
    return s["idn"] * max(cos_t, 0) + s["C"] * s["idn"] * 0.5 + K["refletancia_solo"] * s["idn"] * (s["C"] + s["sb"]) * 0.5


def orient_graus(o):
    if _tem(o):
        return float(o)
    return DADOS["orientacoes"].get(str(o or "").upper(), 0)


# ───────── Superfícies ─────────
def propriedades(s):
    m = DADOS["materiais"].get(s.get("material") or "", {})
    if not isinstance(m, dict):
        m = {}
    cor = DADOS["cores"].get(s.get("cor") or "")
    return {"u": _ou(s.get("u"), _n(m.get("u"))), "atraso": _ou(s.get("atraso"), _n(m.get("atraso"))),
            "amort": _ou(s.get("amortecimento"), float(m["amortecimento"]) if _tem(m.get("amortecimento")) else 1.0),
            "alfa": _ou(s.get("absortancia"), float(m["absortancia"]) if _tem(m.get("absortancia")) else
                        (float(cor) if _tem(cor) else DADOS["cores"]["media"])),
            "fs": _ou(s.get("fs"), float(m["fs"]) if _tem(m.get("fs")) else 0.82), "sombra": _ou(s.get("sombra"), 1.0)}


def _interp(arr, x):
    y = ((x % 24) + 24) % 24
    i = math.floor(y)
    f = y - i
    return arr[i] * (1 - f) + arr[(i + 1) % 24] * f


def superficie(s, cl):
    tipo, A, pr, Ti = s.get("tipo") or "parede", _n(s.get("area")), propriedades(s), cl["tint"]
    if tipo == "vidro":
        og = orient_graus(s.get("orient"))
        return lambda h: (0.0, A * pr["fs"] * pr["sombra"] * irradiancia(cl, h, og), pr["u"] * A * (cl["text"][h] - Ti))
    if tipo == "piso_solo":
        return lambda h: (0.0, 0.0, 0.0)
    if tipo == "adjacente":
        fa = _ou(s.get("fator"), P["fator_adjacente"])
        return lambda h: (pr["u"] * A * fa * (cl["text"][h] - Ti), 0.0, 0.0)
    if tipo == "piso_exterior":
        return lambda h: (pr["u"] * A * (cl["text"][h] - Ti), 0.0, 0.0)
    horiz = tipo == "cobertura"
    og = -1 if horiz else orient_graus(s.get("orient"))
    com_sol = s.get("sol") is not False
    tsa = [cl["text"][h] + ((pr["alfa"] * irradiancia(cl, h, og) / K["h_ext"] - (K["delta_r_horizontal"] if horiz else 0)) if com_sol else 0)
           for h in range(24)]
    tm = sum(tsa) / 24
    return lambda h: (pr["u"] * A * ((tm - Ti) + pr["amort"] * (_interp(tsa, h - pr["atraso"]) - tm)), 0.0, 0.0)


# ───────── Ambiente ─────────
def ambiente(a, cl, op):
    area = _n(a.get("area"))
    pe = _ou(a.get("pe_direito"), P["pe_direito"])
    vol = area * pe
    pes = _n(a.get("pessoas"))
    at = DADOS["atividades"].get(a.get("atividade") or "") or DADOS["atividades"]["escritorio"]
    uso = DADOS["ar_externo"].get(a.get("uso") or "") or DADOS["ar_externo"]["escritorio"]
    ilum = _ou(a.get("iluminacao_wm2"), P["iluminacao_wm2"]) * area
    equip = _ou(a.get("equipamentos_wm2"), P["equipamentos_wm2"]) * area + _n(a.get("equipamentos_w"))
    q_inf = _ou(a.get("infiltracao_ach"), P["infiltracao_ach"]) * vol / 3.6
    if op.get("ar_externo") is False:
        q_ae = 0.0
    elif _tem(a.get("ar_externo_ls")):
        q_ae = float(a["ar_externo_ls"])
    else:
        q_ae = _ou(a.get("ar_externo_lpp"), uso["rp"]) * pes + _ou(a.get("ar_externo_lpm2"), uso["ra"]) * area
    ini, fim = _ou(a.get("ini"), P["ini"]), _ou(a.get("fim"), P["fim"])
    dw = max(cl["w_ext"] - cl["w_int"], 0)
    sups = [superficie(s, cl) for s in (a.get("superficies") or [])]
    horas = []
    for h in op["horas"]:
        ocup = 1 if ini <= h <= fim else 0
        dT = cl["text"][h] - cl["tint"]
        c = {"envoltoria": 0.0, "vidro_solar": 0.0, "vidro_conducao": 0.0}
        for f in sups:
            q = f(h)
            c["envoltoria"] += q[0]; c["vidro_solar"] += q[1]; c["vidro_conducao"] += q[2]
        c["pessoas_s"] = ocup * pes * at["sens"]; c["pessoas_l"] = ocup * pes * at["lat"]
        c["iluminacao"] = ocup * ilum; c["equipamentos"] = ocup * equip
        c["infiltracao_s"] = K["c_sensivel"] * q_inf * dT; c["infiltracao_l"] = K["c_latente"] * q_inf * dw
        c["ar_externo_s"] = ocup * K["c_sensivel"] * q_ae * dT; c["ar_externo_l"] = ocup * K["c_latente"] * q_ae * dw
        lat = sum(c[k] for k in LATENTES)
        tot = sum(c[k] for k in COMP)
        horas.append({"h": h, "comp": c, "sens": tot - lat, "lat": lat, "total": tot})
    pico = horas[0]
    for x in horas:
        if x["total"] > pico["total"]:
            pico = x
    fs = op["fs"]
    W = pico["total"] * fs
    return {"nome": str(a.get("nome") or ""), "area": area, "volume": vol, "pessoas": pes, "vazao_infiltracao_ls": q_inf,
            "vazao_ar_externo_ls": q_ae, "horas": horas, "pico": pico,
            "projeto": {"sens": pico["sens"] * fs, "lat": pico["lat"] * fs, "W": W, "btuh": W * K["btu_por_w"], "tr": W / K["w_por_tr"],
                        "shr": pico["sens"] / pico["total"] if pico["total"] > 0 else 1, "wm2": W / area if area > 0 else 0}}


# ───────── Sistema ─────────
def carregar_base(caminho=None):
    arq = Path(caminho) if caminho else Path(__file__).resolve().parents[2] / "sistema" / "physis-equipamentos.json"
    return json.loads(arq.read_text(encoding="utf-8")) if arq.is_file() else None


def _sazonal(it):
    if not it or not it.get("eficiencia"):
        return 0.0
    e = it["eficiencia"]
    return _ou(e.get("sazonal"), _n(e.get("tipico")))


def _escolher_split(itens, btuh):
    import re
    ok = [i for i in itens if i.get("sistema") == "split" and _tem(i.get("capacidade_nominal_btuh")) and not re.search(r"conv|janela", i["id"])]
    ordem = lambda i: 0 if "hiwall" in i["id"] else 1 if "cassete" in i["id"] else 2 if "pisoteto" in i["id"] else 3
    cand = sorted([i for i in ok if i["capacidade_nominal_btuh"] >= btuh],
                  key=lambda i: (i["capacidade_nominal_btuh"], ordem(i), -_sazonal(i)))
    if cand:
        return {"item": cand[0], "qtd": 1}
    if not ok:
        return None
    maior = max(ok, key=lambda i: i["capacidade_nominal_btuh"])
    return {"item": maior, "qtd": math.ceil(btuh / maior["capacidade_nominal_btuh"])}


def _escolher_faixa(itens, sistema, kw, filtro=None):
    ok = [i for i in itens if i.get("sistema") == sistema and (filtro is None or filtro(i))]
    dentro = sorted([i for i in ok if _n(i["faixa_capacidade"]["min"]) <= kw <= _n(i["faixa_capacidade"]["max"])], key=lambda i: -_sazonal(i))
    if dentro:
        return {"item": dentro[0], "qtd": 1}
    if not ok:
        return None
    maior = max(ok, key=lambda i: _n(i["faixa_capacidade"]["max"]))
    if kw > _n(maior["faixa_capacidade"]["max"]):
        return {"item": maior, "qtd": math.ceil(kw / _n(maior["faixa_capacidade"]["max"]))}
    return {"item": min(ok, key=lambda i: _n(i["faixa_capacidade"]["min"])), "qtd": 1}


def sugerir(res, op):
    R, SP = DADOS["regras_sistema"], DADOS["sistemas_padrao"]
    base = op.get("equipamentos")
    itens = [i for i in base["itens"] if i["categoria"] == "ar-condicionado"] if base and isinstance(base.get("itens"), list) else []
    tr, kw_p, kw_bloco = res["total"]["projeto"]["tr"], res["total"]["projeto"]["W"] / 1000, res["total"]["bloco"]["total"] / 1000
    amb = [a for a in res["ambientes"] if a["pico"]["total"] > 0]
    n = len(amb)
    max_amb = max([a["projeto"]["W"] / 1000 for a in amb], default=0)
    energia = lambda saz, aux: kw_bloco * op["horas_ano"] * op["fator_carga"] / saz * aux if saz > 0 else 0
    ops = []
    esc = []
    if itens:
        for a in amb:
            e = _escolher_split(itens, a["projeto"]["btuh"]) or {}
            esc.append(dict(e, ambiente=a["nome"], btuh=a["projeto"]["btuh"], kw=a["projeto"]["W"] / 1000))
    sq = sum(x["kw"] for x in esc)
    sd = sum(x["kw"] / _sazonal(x.get("item")) for x in esc if x.get("item") and _sazonal(x["item"]) > 0)
    saz = sq / sd if itens and sd > 0 else SP["split"]["sazonal"]
    viavel = max_amb <= R["split_max_ambiente_kw"] * 1.0001 and tr <= R["split_max_total_tr"]
    ops.append({"tipo": "split", "viavel": viavel, "sazonal": saz, "aux": SP["split"]["aux"], "kwh_ano": energia(saz, SP["split"]["aux"]),
                "equipamentos": [{"ambiente": x["ambiente"], "id": x["item"]["id"] if x.get("item") else "", "qtd": x.get("qtd", 1)} for x in esc]})
    e = _escolher_faixa(itens, "vrf", kw_p, lambda i: "recupera" not in i["descricao"].lower()) if itens else None
    saz = _sazonal(e["item"]) if e else SP["vrf"]["sazonal"]
    aux = _ou(e["item"].get("auxiliares_fator"), 1) if e else SP["vrf"]["aux"]
    ops.append({"tipo": "vrf", "viavel": R["vrf_min_tr"] <= tr <= R["vrf_max_tr"] and n >= R["vrf_min_ambientes"], "sazonal": saz, "aux": aux,
                "kwh_ano": energia(saz, aux), "equipamentos": [{"id": e["item"]["id"], "qtd": e["qtd"]}] if e else []})
    agua = tr >= R["chiller_agua_min_tr"]
    e = _escolher_faixa(itens, "chiller", kw_p, (lambda i: "agua" in i["id"]) if agua else (lambda i: "chiller-ar" in i["id"])) if itens else None
    saz = _sazonal(e["item"]) if e else SP["chiller"]["sazonal"]
    aux = _ou(e["item"].get("auxiliares_fator"), 1) if e else SP["chiller"]["aux"]
    ops.append({"tipo": "chiller", "viavel": tr >= R["chiller_min_tr"], "sazonal": saz, "aux": aux, "kwh_ano": energia(saz, aux),
                "equipamentos": [{"id": e["item"]["id"], "qtd": e["qtd"]}] if e else []})
    tarifa = _n(op.get("tarifa"))
    for o in ops:
        o["custo_ano"] = o["kwh_ano"] * tarifa if tarifa > 0 else None
    rec = "chiller" if tr >= R["chiller_ideal_tr"] else "vrf" if (n >= R["vrf_ideal_ambientes"] and tr >= R["vrf_ideal_tr"]) else "split"
    if not next(o for o in ops if o["tipo"] == rec)["viavel"]:
        v = next((o for o in ops if o["viavel"]), None)
        rec = v["tipo"] if v else "split"
    viaveis = [o for o in ops if o["viavel"] and o["kwh_ano"] > 0]
    menor = min(viaveis, key=lambda o: o["kwh_ano"]) if viaveis else None
    return {"opcoes": ops, "recomendado": rec, "menor_consumo": menor["tipo"] if menor else None, "base": bool(itens)}


# ───────── Cálculo principal ─────────
def calcular(ambientes, clima=None, opcoes=None):
    o = opcoes or {}
    horas = [int(round(_n(h))) % 24 for h in o["horas"]] if isinstance(o.get("horas"), list) and o["horas"] else list(P["horas"])
    op = {"horas": horas, "fs": _ou(o.get("fs"), P["fs"]), "horas_ano": _ou(o.get("horas_ano"), P["horas_ano"]),
          "fator_carga": _ou(o.get("fator_carga"), P["fator_carga"]), "tarifa": o.get("tarifa"), "ar_externo": o.get("ar_externo"),
          "equipamentos": o.get("equipamentos")}
    cl = resolver_clima(clima, o)
    avisos = list(cl["avisos"])
    amb = [ambiente(a or {}, cl, op) for a in (ambientes or [])]
    por_hora = []
    for i, h in enumerate(op["horas"]):
        c = {k: sum(a["horas"][i]["comp"][k] for a in amb) for k in COMP}
        lat = sum(c[k] for k in LATENTES)
        tot = sum(c[k] for k in COMP)
        por_hora.append({"h": h, "comp": c, "sens": tot - lat, "lat": lat, "total": tot})
    bloco = por_hora[0] if por_hora else {"h": op["horas"][0], "comp": {}, "sens": 0, "lat": 0, "total": 0}
    for x in por_hora:
        if x["total"] > bloco["total"]:
            bloco = x
    soma = sum(a["pico"]["total"] for a in amb)
    W = bloco["total"] * op["fs"]
    total = {"porHora": por_hora, "bloco": bloco, "soma_picos": soma, "diversidade": bloco["total"] / soma if soma > 0 else 1,
             "projeto": {"W": W, "btuh": W * K["btu_por_w"], "tr": W / K["w_por_tr"], "sens": bloco["sens"] * op["fs"], "lat": bloco["lat"] * op["fs"]},
             "soma_picos_projeto": {"W": soma * op["fs"], "btuh": soma * op["fs"] * K["btu_por_w"], "tr": soma * op["fs"] / K["w_por_tr"]}}
    if any(a["area"] <= 0 for a in amb):
        avisos.append("Há ambiente sem área.")
    res = {"clima": cl, "opcoes": op, "ambientes": amb, "total": total, "avisos": avisos}
    res["sistema"] = sugerir(res, op)
    return res


# ───────── Envoltória pelo método da ABNT NBR 15220-2 (camadas homogêneas em série) ─────────
RSI_RSE = {"parede": (0.13, 0.04), "cobertura": (0.17, 0.04)}  # m²K/W; cobertura com fluxo descendente (verão)


def nbr15220(camadas, materiais, tipo="parede"):
    """U (W/m²K), capacidade térmica CT (kJ/m²K) e atraso térmico φ (h) de um componente em camadas.

    camadas: lista de {"material": id, "espessura": m} (de fora para dentro) ou {"resistencia": R} (câmara de ar).
    materiais: dict id -> {"densidade", "condutividade", "calor_especifico" (J/kgK)}.
    Atraso: forma de camadas da NBR 15220-2 (B0, B1, B2), com a camada externa como referência.
    Amortecimento estimado pela solução da onda periódica em placa homogênea: f = exp(−2πφ/24) (premissa Physis).
    """
    rsi, rse = RSI_RSE[tipo]
    rt = 0.0
    ct = 0.0
    rs = []
    for c in camadas:
        if "resistencia" in c:
            r, cap, lrc = float(c["resistencia"]), 0.0, 0.0
        else:
            m = materiais[c["material"]]
            e = float(c["espessura"])
            r = e / m["condutividade"]
            cap = e * m["densidade"] * m["calor_especifico"] / 1000           # kJ/m²K
            lrc = m["condutividade"] * m["densidade"] * m["calor_especifico"] / 1000
        rs.append((r, cap, lrc))
        rt += r
        ct += cap
    u = 1 / (rsi + rt + rse)
    if len(rs) == 1:
        r, cap, lrc = rs[0]
        m = materiais[camadas[0]["material"]]
        e = float(camadas[0]["espessura"])
        phi = 1.382 * e * math.sqrt(m["densidade"] * m["calor_especifico"] / 1000 / (3.6 * m["condutividade"]))
    else:
        r_ext, ct_ext, lrc_ext = rs[0]
        b0 = ct - ct_ext
        b1 = 0.226 * b0 / rt
        b2 = 0.205 * (lrc_ext / rt) * (r_ext - (rt - r_ext) / 10)
        phi = 1.382 * rt * math.sqrt(max(b1 + max(b2, 0.0), 0.0))
    return {"u": u, "ct": ct, "atraso": phi, "amortecimento": math.exp(-2 * math.pi * phi / 24), "rt": rt}
