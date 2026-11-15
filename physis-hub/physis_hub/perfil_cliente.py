"""Dados da plataforma do cliente guardados no servidor (antes ficavam só no navegador, em localStorage).

Cada organização tem um pequeno armário de chave → texto (o mesmo texto JSON que a tela guardava no
navegador), com número de versão. Quem grava informa a versão em que se baseou; se outra pessoa gravou
antes, o servidor recusa (409, conflito) e devolve a versão atual. A ponte do navegador
(sistema/physis-ponte-cliente.js) decide: a mudança mais nova vence e a pessoa é avisada.

Só as chaves da lista entram (CHAVES e PREFIXOS). Rotas em servidor.py:
  GET  /api/cliente/estado[?desde=]      todas as chaves da organização (a ponte lê ao abrir)
  GET  /api/cliente/estado/<chave>       uma chave; ETag "v<versao>"; If-None-Match -> 304
  PUT  /api/cliente/estado/<chave>       {"valor": "<texto>", "versao": <n>} (ou If-Match: "v<n>") -> 200 | 409
  GET  /api/cliente/perfil               o que o servidor aprendeu da descrição do negócio (atividades)

O "aprendido" (atividades do negócio, tirado da descrição escrita no Início) é calculado aqui também,
com as MESMAS regras da tela (web/painel.html, const ATIVIDADES). É conta espelho: mudou lá, muda aqui,
com teste (tests/test_cliente_estado.py). Os alertas de clima (alertas_clima.py) usam essas atividades.
"""
from __future__ import annotations

import json
import re

# Qualidade da água (15/11/2026): leituras, calibrações, laboratório, limites, laudos e configuração. O lote diário de
# integridade leva as leituras; a ponte do navegador (sistema/physis-ponte-cliente.js, embutida no painel) envia as
# mesmas chaves (test_cliente_estado confere as duas listas).
CHAVES_AGUA = ("physis-ph-leituras", "physis-ph-calibracoes", "physis-ph-laboratorio", "physis-agua-limites",
               "physis-agua-laudos", "physis-agua-config")
# chaves que a plataforma do cliente guarda (iguais às do localStorage)
CHAVES = ("physis-perfil", "physis-gestao-cliente", "physis-carbono", "physis-residuos-plano", "physis-cert-gap",
          "physis-sbn", "physis.terreno.v1", "physis-servidor-verde") + CHAVES_AGUA
PREFIXOS = ("physis-calc-", "physis-curso-")
_SUFIXO = re.compile(r"^[A-Za-z0-9_.:-]{1,60}$")
VALOR_MAX = 2 * 1024 * 1024          # por chave (texto UTF-8)
TOTAL_MAX = 32 * 1024 * 1024         # por organização
CHAVES_MAX = 300                     # por organização

ESQUEMA = """
CREATE TABLE IF NOT EXISTS cliente_estado (
  org TEXT NOT NULL, chave TEXT NOT NULL, valor TEXT NOT NULL, versao INTEGER NOT NULL, atualizado REAL NOT NULL,
  por TEXT NOT NULL, PRIMARY KEY (org, chave));
"""


def chave_valida(chave: str) -> bool:
    c = str(chave or "")
    if c in CHAVES or c in CHAVES_AGUA:
        return True
    return any(c.startswith(p) and _SUFIXO.match(c[len(p):]) for p in PREFIXOS)


# ── Atividades do negócio (espelho de ATIVIDADES em web/painel.html) ─────────────────────────────
# (id, expressão, nome, riscos, módulos que ajudam)
ATIVIDADES = (
    ("cafe", r"caf[eé]", "Cafeicultura",
     ("geada (temperatura mínima abaixo de 3 °C)", "chuva na colheita (maio a setembro)", "seca na florada (setembro e outubro)"),
     ("monitoramento", "agua", "resiliencia", "solar")),
    ("gado_leite", r"leite|leiteir|ordenh", "Pecuária de leite",
     ("estresse térmico do rebanho (calor acima de 30 °C)", "água de bebida dos animais"), ("coleiras", "comedouros", "agua", "solar")),
    ("gado", r"gado|bovin|pecu[aá]ria|boi\b|rebanho", "Pecuária",
     ("água de bebida dos animais", "estresse térmico do rebanho (calor acima de 30 °C)"), ("coleiras", "comedouros", "agua")),
    ("irrigacao", r"irriga|gotejamento|aspers|piv[oô]", "Irrigação",
     ("irrigar antes de chuva prevista", "falta de água na seca"), ("monitoramento", "zonas", "agua")),
    ("hortifruti", r"hort|hortali[cç]|verdura|legume|fruta|pomar|fruticult", "Hortifrúti",
     ("granizo e chuva forte", "calor no plantio"), ("monitoramento", "zonas", "sbn")),
    ("graos", r"soja|milho|feij[aã]o|gr[aã]os|trigo", "Grãos", ("chuva na colheita", "veranico"), ("monitoramento", "resiliencia")),
    ("cana", r"cana|usina de a[cç][uú]car|etanol", "Cana-de-açúcar", ("queimadas na seca", "geada"),
     ("monitoramento", "resiliencia", "carbono")),
    ("peixes", r"peixe|piscicult|aquapon|tilápia|tilapia", "Piscicultura", ("oxigênio da água no calor", "qualidade da água"),
     ("agua", "sbn")),
    ("hospedagem", r"hotel|pousada|chal[eé]|hospedagem|glamping", "Hospedagem",
     ("pico de consumo de água e energia na alta temporada",), ("solar", "agua", "circular", "certificacoes")),
    ("restaurante", r"restaurante|cozinha|alimenta[cç][aã]o", "Alimentação", ("óleo de cozinha e resíduo orgânico",),
     ("circular", "carbono")),
    ("industria", r"ind[uú]stria|f[aá]brica|manufatur", "Indústria",
     ("demanda contratada e multas de energia", "resíduos perigosos (classe I)"), ("solar", "circular", "carbono", "certificacoes")),
    ("construcao", r"constru|obra|loteamento|condom[ií]nio", "Construção", ("chuva forte e drenagem na obra", "resíduos da construção"),
     ("planejador", "circular", "certificacoes")),
    ("educacao", r"escola|universidade|faculdade|ensino", "Educação", ("consumo fora do horário de aula",), ("solar", "agua", "carbono")),
    ("saude", r"hospital|cl[ií]nica|sa[uú]de", "Saúde", ("energia de reserva para equipamentos críticos",), ("solar", "avac", "circular")),
)
_RE = {a[0]: re.compile(a[1], re.IGNORECASE) for a in ATIVIDADES}
IDS = tuple(a[0] for a in ATIVIDADES)


def achar_atividades(texto: str) -> list[str]:
    """Mesma regra de acharAtividades() da tela: gado de leite tira o "gado" genérico."""
    t = str(texto or "")
    ids = [a[0] for a in ATIVIDADES if _RE[a[0]].search(t)]
    return [i for i in ids if i != "gado"] if "gado_leite" in ids else ids


def aprendido_do_perfil(valor: str | None) -> dict:
    """Do texto de physis-perfil: atividades (recalculadas da descrição; sem descrição, as que a tela guardou),
    nomes, riscos e módulos. Texto inválido = nada aprendido."""
    try:
        p = json.loads(valor) if valor else {}
    except ValueError:
        p = {}
    p = p if isinstance(p, dict) else {}
    c = p.get("c") if isinstance(p.get("c"), dict) else {}
    descricao = str(c.get("descricao") or "").strip()
    if descricao:
        ids, fonte = achar_atividades(descricao), "descricao"
    else:
        ap = p.get("aprendido") if isinstance(p.get("aprendido"), dict) else {}
        ids = [a for a in (ap.get("atividades") or []) if a in IDS] if isinstance(ap.get("atividades"), list) else []
        fonte = "tela" if ids else "nenhuma"
    por_id = {a[0]: a for a in ATIVIDADES}
    riscos, mods = [], []
    for i in ids:
        riscos += [r for r in por_id[i][3] if r not in riscos]
        mods += [m for m in por_id[i][4] if m not in mods]
    return {"atividades": ids, "nomes": [por_id[i][2] for i in ids], "riscos": riscos, "modulos": mods, "fonte": fonte}
