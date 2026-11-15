"""Indicadores da plataforma (D18, 15/11/2026): a interface interna da equipe para melhoria contínua.

Junta, de hora em hora, os números da própria plataforma — só metadados, nunca dado pessoal — e aprende com eles:

  * Coleta (tabela indicador_hora, uma linha por hora e indicador; indicador_rota por rota):
    pedidos por rota, taxa de erros 4xx/5xx e tempos (p50/p95/p99); entradas, senhas erradas, bloqueios, CSRF e
    limite (429); nós ativos e calados, leituras e alarmes de sensor; alertas de clima enviados e com falha;
    conflitos de sincronização (perfil_cliente, 409); lotes de integridade fechados e com problema; uso da IA
    (chamadas, falhas, bloqueadas pelo teto = voltaram às respostas prontas, gasto); documentos por situação na
    fila de aprovação; acessos de suporte concedidos; compras e módulos ligados; idade da cópia de segurança e o
    resultado dos testes gravado na implantação. Por cliente: a instalação (número, nunca o nome), módulos, nós e as
    lacunas de fluxo de dados de sistema/physis-variaveis.json para os módulos que ele tem.
  * Aprendizado de máquina explicável (só biblioteca padrão):
    - anomalia: z robusto (mediana e MAD) contra a MESMA HORA DO DIA dos dias anteriores (sazonalidade); poucos
      dados da mesma hora → compara com as horas vizinhas; poucos dados no total → diz "dados insuficientes";
    - tendência e previsão: reta dos mínimos quadrados nas médias diárias + perfil por hora do dia, com R² e n;
    - retorno da equipe: "alerta real" / "alarme falso" muda a chance de o alerta daquele indicador ser real
      (Beta-Binomial) e, com ela, a nota e o limiar;
    - incidentes: a equipe registra o que houve, a causa e a correção; o sistema guarda o padrão dos indicadores
      nas 6 horas antes e, quando um padrão parecido aparece (Jaccard), sugere a causa provável e a correção usada.
    Tudo diz o tamanho da amostra e a confiança.
  * Lista de melhorias: erros que se repetem, rotas lentas, sensores que caem, lacunas de fluxo; cada item pode
    virar tarefa na Gestão (decisão humana).

Configuração: PHYSIS_INDICADORES_RETENCAO_DIAS (padrão 400), PHYSIS_INDICADORES_LENTO_MS (1500),
PHYSIS_BACKUP_MARCA (/var/backups/physis/ultimo.json, escrito pelo backup.sh), PHYSIS_TESTES_MARCA
(/var/lib/physis/testes.json, escrito na implantação). Ver docs/INDICADORES_PLATAFORMA.md.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import statistics
import threading
import time
from datetime import datetime
from pathlib import Path

from . import seguranca as seg

REPO = Path(__file__).resolve().parent.parent.parent
TABELAS = """
CREATE TABLE IF NOT EXISTS indicador_hora (hora INTEGER NOT NULL, chave TEXT NOT NULL, valor REAL NOT NULL, PRIMARY KEY(hora, chave));
CREATE TABLE IF NOT EXISTS indicador_rota (hora INTEGER NOT NULL, rota TEXT NOT NULL, n INTEGER NOT NULL, e4 INTEGER NOT NULL,
  e5 INTEGER NOT NULL, e429 INTEGER NOT NULL DEFAULT 0, e409 INTEGER NOT NULL DEFAULT 0, p50 REAL, p95 REAL, p99 REAL, PRIMARY KEY(hora, rota));
CREATE TABLE IF NOT EXISTS indicador_feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, chave TEXT NOT NULL, hora INTEGER NOT NULL,
  real INTEGER NOT NULL, quem TEXT NOT NULL, quando REAL NOT NULL);
CREATE TABLE IF NOT EXISTS indicador_incidente (id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL, causa TEXT NOT NULL,
  correcao TEXT NOT NULL, quando REAL NOT NULL, criado_por TEXT NOT NULL, padrao TEXT NOT NULL, ajudou INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS indicador_backlog (id TEXT PRIMARY KEY, tipo TEXT NOT NULL, titulo TEXT NOT NULL, detalhe TEXT NOT NULL,
  primeira REAL NOT NULL, ultima REAL NOT NULL, vezes INTEGER NOT NULL, tarefa_por TEXT, tarefa_em REAL);
"""

# nome de cada indicador (pt, en) e o lado ruim: +1 = subir é ruim, -1 = cair é ruim, 0 = os dois
NOMES = {
    "req.total": ("Pedidos ao servidor", "Server requests", 0), "req.taxa_4xx": ("Taxa de erros 4xx", "4xx error rate", 1),
    "req.taxa_5xx": ("Taxa de erros 5xx", "5xx error rate", 1), "req.p95_ms": ("Tempo de resposta p95 (ms)", "Response time p95 (ms)", 1),
    "req.p50_ms": ("Tempo de resposta p50 (ms)", "Response time p50 (ms)", 1), "req.limite_429": ("Pedidos barrados pelo limite (429)", "Rate-limited requests (429)", 1),
    "login.ok": ("Entradas", "Sign-ins", 0), "login.senha_errada": ("Senhas erradas", "Wrong passwords", 1),
    "login.bloqueado": ("Entradas bloqueadas", "Blocked sign-ins", 1), "csrf.recusado": ("Pedidos recusados por CSRF", "CSRF refusals", 1),
    "disp.nos_ativos": ("Nós com dado na hora", "Nodes reporting this hour", -1), "disp.nos_calados": ("Nós calados (vistos em 7 dias, sem dado na hora)", "Silent nodes", 1),
    "med.leituras": ("Leituras recebidas", "Readings received", -1), "med.alarmes": ("Alarmes de sensor", "Sensor alarms", 1),
    "alerta.enviados": ("Alertas de clima enviados", "Weather alerts sent", 0), "alerta.falhas": ("Alertas de clima com falha", "Failed weather alerts", 1),
    "sync.conflitos": ("Conflitos de sincronização", "Sync conflicts", 1), "sync.erros": ("Erros de sincronização", "Sync errors", 1),
    "integ.lotes_fechados": ("Lotes de integridade fechados", "Integrity lots closed", 0), "integ.lotes_problema": ("Lotes de integridade com problema", "Failing integrity lots", 1),
    "ia.chamadas": ("Chamadas à IA", "AI calls", 0), "ia.falhas": ("Chamadas à IA com falha", "Failed AI calls", 1),
    "ia.respostas_prontas": ("Robôs nas respostas prontas (falha ou teto)", "Robots on ready answers", 1), "ia.gasto_usd": ("Gasto da IA na hora (US$)", "AI spend this hour (US$)", 1),
    "ia.gasto_mes_usd": ("Gasto da IA no mês (US$)", "AI spend this month (US$)", 1),
    "doc.rascunho": ("Documentos em rascunho", "Draft documents", 0), "doc.em_revisao": ("Documentos esperando revisão", "Documents awaiting review", 1),
    "doc.aprovado": ("Documentos aprovados, não emitidos", "Approved, not issued", 1), "doc.emitido": ("Documentos emitidos", "Issued documents", 0),
    "suporte.acessos_ativos": ("Acessos de suporte ativos", "Active support grants", 0), "suporte.acessos_novos": ("Acessos de suporte concedidos", "Support grants issued", 0),
    "loja.compras": ("Compras recebidas", "Orders received", -1), "loja.instalacoes": ("Plataformas montadas", "Platforms built", 0),
    "loja.modulos_ligados": ("Módulos ligados", "Modules turned on", 0), "backup.idade_h": ("Idade da cópia de segurança (h)", "Backup age (h)", 1),
    "testes.falhas": ("Testes com falha na última implantação", "Failed tests at last deploy", 1),
}
# indicadores de nível (estoque), não de fluxo: não entram na detecção de anomalia por hora
NIVEIS = {"ia.gasto_mes_usd", "doc.rascunho", "doc.emitido", "suporte.acessos_ativos", "backup.idade_h", "testes.falhas"}
MIN_AMOSTRA = 8            # menos que isso: "dados insuficientes"
MIN_MESMA_HORA = 5         # menos que isso na mesma hora do dia: usa as horas vizinhas
LIMIAR = 3.5               # |z| robusto que vira alerta com chance de real 50%
JANELA_INCIDENTE_H = 6


# ══════════════════════════ estatística e aprendizado (funções puras, testáveis) ══════════════════════════
def percentil(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    k = (len(s) - 1) * p
    f, c = math.floor(k), math.ceil(k)
    return s[f] + (s[c] - s[f]) * (k - f)


def _mad(xs: list[float], med: float) -> float:
    return statistics.median([abs(x - med) for x in xs]) if xs else 0.0


def anomalia(historico: list[tuple[int, float]], hora: int, valor: float, p_real: float = 0.5) -> dict:
    """z robusto do valor da hora `hora` contra o histórico (lista de (hora, valor), sem a própria hora).
    Sazonalidade: o centro é a mediana da MESMA HORA DO DIA; a escala é o MAD dos resíduos de todas as horas
    (cada valor menos a mediana da hora dele) — muitas amostras, escala estável, sem alarme falso pelo ciclo diário.
    Poucos dias na mesma hora: centro e escala de todas as horas. p_real (0..1) vem do retorno da equipe."""
    hist = [(h, v) for h, v in historico if h != hora]
    n = len(hist)
    if n < MIN_AMOSTRA:
        return {"suficiente": False, "n": n, "modo": "—", "z": None, "nota": 0.0, "alerta": False,
                "confianca": "dados insuficientes", "esperado": None}
    perfil: dict[int, list[float]] = {}
    for h, v in hist:
        perfil.setdefault(h % 24, []).append(v)
    hd = hora % 24
    if len(perfil.get(hd, [])) >= MIN_MESMA_HORA:
        med_h = {k: statistics.median(vs) for k, vs in perfil.items() if len(vs) >= 3}
        med = med_h[hd]
        resid = [v - med_h[h % 24] for h, v in hist if h % 24 in med_h]
        modo, n_hora = "mesma hora do dia", len(perfil[hd])
    else:
        med = statistics.median(v for _, v in hist)
        resid = [v - med for _, v in hist]
        modo, n_hora = "todas as horas (poucos dias)", 0
    mr = statistics.median(resid)
    mad = _mad(resid, mr)
    escala = 1.4826 * mad if mad > 0 else max(statistics.pstdev(resid), 0.05 * abs(med), 1e-9)
    z = (valor - med) / escala
    nota = abs(z) * (0.5 + p_real)                # p_real = 0,5 → nota = |z|
    conf = "alta" if n_hora >= 21 else "média" if n_hora >= 10 else "baixa"
    return {"suficiente": True, "n": n, "n_mesma_hora": n_hora, "modo": modo, "z": round(z, 2), "esperado": round(med, 4),
            "faixa": [round(med - LIMIAR * escala, 4), round(med + LIMIAR * escala, 4)], "nota": round(nota, 2),
            "alerta": nota >= LIMIAR, "confianca": conf, "p_real": round(p_real, 3)}


def tendencia(serie: list[tuple[int, float]], horizonte_h: int = 24) -> dict:
    """Médias diárias → reta (mínimos quadrados): inclinação por dia e R². Previsão das próximas horas = perfil da
    hora do dia (mediana) + inclinação × dias à frente. Diz n (dias) e a confiança."""
    por_dia: dict[int, list[float]] = {}
    for h, v in serie:
        por_dia.setdefault(h // 24, []).append(v)
    dias = sorted(por_dia)
    n = len(dias)
    if n < 3:
        return {"suficiente": False, "n_dias": n, "confianca": "dados insuficientes"}
    xs = [d - dias[0] for d in dias]
    ys = [statistics.fmean(por_dia[d]) for d in dias]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    incl = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (my + incl * (x - mx))) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    perfil: dict[int, list[float]] = {}
    for h, v in serie:
        perfil.setdefault(h % 24, []).append(v)
    ultima = max(h for h, _ in serie)
    prev = []
    for k in range(1, horizonte_h + 1):
        h = ultima + k
        base = statistics.median(perfil[h % 24]) if h % 24 in perfil else my
        prev.append({"hora": h, "valor": round(base + incl * (k / 24), 4)})
    conf = "baixa" if n < 7 or r2 < 0.3 else "média" if n < 14 or r2 < 0.6 else "alta"
    return {"suficiente": True, "n_dias": n, "inclinacao_dia": round(incl, 4), "r2": round(r2, 3), "media": round(my, 4),
            "previsao": prev, "confianca": conf}


def chance_real(reais: int, falsos: int) -> float:
    """Beta(1,1) + retorno da equipe: chance de um alerta deste indicador ser real."""
    return (1 + reais) / (2 + reais + falsos)


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a or b else 0.0


def normalizar_rota(caminho: str) -> str:
    """/api/emissao/AbC123xyz.../editar → /api/emissao/:id/editar (números e códigos viram :id; nada da consulta)."""
    partes = []
    for p in (caminho or "/").split("?", 1)[0].split("/")[1:7]:
        if re.fullmatch(r"\d+|[A-Za-z0-9_-]{12,}|[A-Z]{1,4}-[\w-]+|PH-\d+", p) or (re.search(r"\d", p) and len(p) > 6):
            p = ":id"
        partes.append(p[:40])
    return "/" + "/".join(partes)


# ══════════════════════════ coleta e painel ══════════════════════════
class Indicadores:
    def __init__(self, hub, robos=None, relogio=None, variaveis: Path | None = None):
        self.hub = hub
        self.robos = robos                        # para achar o contador da IA (robos.claude_da_cadeia)
        self.relogio = relogio or hub.relogio
        self.variaveis = Path(variaveis) if variaveis else REPO / "sistema" / "physis-variaveis.json"
        self.trava = threading.Lock()
        self._req: dict[tuple[int, str], list] = {}
        with hub._trava:
            hub._db.executescript(TABELAS)
            hub._db.commit()

    # ── pedidos (o servidor chama a cada resposta; só rota normalizada, código e tempo) ──
    def requisicao(self, metodo: str, caminho: str, status: int, ms: float) -> None:
        if not caminho or caminho.startswith("/api/indicadores"):
            return
        hora = int(self.relogio() // 3600)
        rota = f"{(metodo or '?')[:7]} {normalizar_rota(caminho)}"
        with self.trava:
            r = self._req.setdefault((hora, rota), [0, 0, 0, 0, 0, []])
            r[0] += 1
            r[1] += 400 <= status < 500
            r[2] += status >= 500
            r[3] += status == 429
            r[4] += status == 409
            if len(r[5]) < 2000:
                r[5].append(float(ms))
            for k in [k for k in self._req if k[0] < hora - 2]:       # memória curta: o banco guarda o resto
                del self._req[k]

    def _gravar_rotas(self, hora: int) -> dict:
        with self.trava:
            itens = [(k[1], list(v[:5]), list(v[5])) for k, v in self._req.items() if k[0] == hora]
        tot = [0, 0, 0, 0, 0]
        todas, sync = [], [0, 0]
        with self.hub._trava:
            for rota, c, lat in itens:
                self.hub._db.execute("INSERT OR REPLACE INTO indicador_rota(hora,rota,n,e4,e5,e429,e409,p50,p95,p99) VALUES(?,?,?,?,?,?,?,?,?,?)",
                                     (hora, rota, c[0], c[1], c[2], c[3], c[4], percentil(lat, .5), percentil(lat, .95), percentil(lat, .99)))
                tot = [a + b for a, b in zip(tot, c)]
                todas += lat
                if "/api/cliente/estado" in rota:
                    sync[0] += c[4]
                    sync[1] += c[1] + c[2] - c[4]
        out = {"req.total": tot[0], "req.limite_429": tot[3], "sync.conflitos": sync[0], "sync.erros": max(0, sync[1])}
        if tot[0]:
            out.update({"req.taxa_4xx": tot[1] / tot[0], "req.taxa_5xx": tot[2] / tot[0],
                        "req.p50_ms": percentil(todas, .5), "req.p95_ms": percentil(todas, .95)})
        return out

    def _q(self, sql: str, args=()) -> list:
        try:
            with self.hub._trava:
                return self.hub._db.execute(sql, args).fetchall()
        except Exception:                   # tabela de módulo que ainda não existe nesta instalação
            return []

    def _um(self, sql: str, args=(), padrao=0):
        r = self._q(sql, args)
        return r[0][0] if r and r[0][0] is not None else padrao

    def _contador_ia(self) -> dict:
        if self.robos is None:
            return {}
        try:
            from .robos import claude_da_cadeia
            cl = claude_da_cadeia(self.robos["suporte"].ia if isinstance(self.robos, dict) else self.robos)
            return cl.consumo.ler() if cl else {}
        except Exception:
            return {}

    @staticmethod
    def _marca(var: str, padrao: str) -> dict | None:
        p = Path(os.environ.get(var) or padrao)
        try:
            return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
        except (OSError, ValueError):
            return None

    def coletar(self, agora: float | None = None) -> dict:
        """Grava os indicadores da hora corrente (refaz a hora se rodar de novo). Só números."""
        agora = self.relogio() if agora is None else agora
        hora = int(agora // 3600)
        ini, fim = hora * 3600, (hora + 1) * 3600
        v = self._gravar_rotas(hora)
        ev = dict(self._q("SELECT evento, COUNT(*) FROM acesso_log WHERE quando>=? AND quando<? GROUP BY evento", (ini, fim)))
        v.update({"login.ok": ev.get("entrou", 0), "login.senha_errada": ev.get("senha errada", 0),
                  "login.bloqueado": ev.get("bloqueado", 0), "csrf.recusado": ev.get("csrf recusado", 0)})
        ativos = {r[0] for r in self._q("SELECT DISTINCT no FROM leitura WHERE recebido>=? AND recebido<?", (ini, fim))}
        conhecidos = {r[0] for r in self._q("SELECT DISTINCT no FROM leitura WHERE recebido>=? AND recebido<?", (fim - 7 * 86400, fim))}
        v.update({"disp.nos_ativos": len(ativos), "disp.nos_calados": len(conhecidos - ativos),
                  "med.leituras": self._um("SELECT COUNT(*) FROM leitura WHERE recebido>=? AND recebido<?", (ini, fim)),
                  "med.alarmes": self._um("SELECT COUNT(*) FROM medicao m JOIN leitura l ON l.seq=m.leitura WHERE l.recebido>=? AND l.recebido<? "
                                          "AND m.alarme IN ('alto','baixo')", (ini, fim))})
        al = dict(self._q("SELECT estado, COUNT(*) FROM alerta_envio WHERE criado>=? AND criado<? GROUP BY estado", (ini, fim)))
        v.update({"alerta.enviados": al.get("enviado", 0), "alerta.falhas": sum(n for e, n in al.items() if e not in ("enviado", "pendente"))})
        v["integ.lotes_fechados"] = self._um("SELECT COUNT(*) FROM integridade_lote WHERE fechado_em>=? AND fechado_em<?", (ini, fim))
        v["integ.lotes_problema"] = self._lotes_com_problema(fim)
        c = self._contador_ia()
        envios = [e for e in (c.get("envios") or []) if isinstance(e, dict) and str(e.get("quando", ""))[:13] == datetime.fromtimestamp(ini).strftime("%Y-%m-%dT%H")]
        if c:
            v.update({"ia.chamadas": len(envios), "ia.falhas": sum(1 for e in envios if not e.get("ok")),
                      "ia.gasto_usd": round(sum(float(e.get("custo_usd") or 0) for e in envios), 6),
                      "ia.respostas_prontas": sum(1 for e in envios if not e.get("ok")) + self._delta_bloqueadas(hora, int(c.get("bloqueadas_teto") or 0)),
                      "ia.gasto_mes_usd": float(c.get("gasto_usd") or 0)})
        for est, n in self._q("SELECT estado, COUNT(*) FROM docauto GROUP BY estado"):
            v[f"doc.{est}"] = n
        v["suporte.acessos_ativos"] = self._um("SELECT COUNT(*) FROM suporte_concessao WHERE expira>? AND revogada IS NULL AND encerrada IS NULL", (agora,))
        v["suporte.acessos_novos"] = self._um("SELECT COUNT(*) FROM suporte_concessao WHERE inicio>=? AND inicio<?", (ini, fim))
        v["loja.compras"] = self._um("SELECT COUNT(*) FROM central WHERE tipo='compra' AND criado>=? AND criado<?", (ini, fim))
        inst = self._q("SELECT modulos FROM instalacao WHERE criado>=? AND criado<?", (ini, fim))
        v["loja.instalacoes"] = len(inst)
        v["loja.modulos_ligados"] = sum(len(json.loads(m or "[]")) for (m,) in inst)
        bk = self._marca("PHYSIS_BACKUP_MARCA", "/var/backups/physis/ultimo.json")
        if bk and isinstance(bk.get("quando"), (int, float)):
            v["backup.idade_h"] = round((agora - bk["quando"]) / 3600, 1)
        ts = self._marca("PHYSIS_TESTES_MARCA", "/var/lib/physis/testes.json")
        if ts and isinstance(ts.get("falhas"), (int, float)):
            v["testes.falhas"] = ts["falhas"]
        v = {k: float(x) for k, x in v.items() if x is not None}
        with self.hub._trava:
            self.hub._db.executemany("INSERT OR REPLACE INTO indicador_hora(hora,chave,valor) VALUES(?,?,?)", [(hora, k, x) for k, x in v.items()])
            self.hub._db.commit()
        self._atualizar_backlog(agora)
        return {"hora": hora, "valores": v}

    def _delta_bloqueadas(self, hora: int, total_mes: int) -> int:
        """O contador da IA guarda o total do mês: a hora recebe a diferença para a hora anterior gravada."""
        r = self._q("SELECT valor FROM indicador_hora WHERE chave='_ia.bloqueadas_mes' AND hora<? ORDER BY hora DESC LIMIT 1", (hora,))
        antes = int(r[0][0]) if r else total_mes
        with self.hub._trava:
            self.hub._db.execute("INSERT OR REPLACE INTO indicador_hora(hora,chave,valor) VALUES(?,?,?)", (hora, "_ia.bloqueadas_mes", total_mes))
        return max(0, total_mes - antes)

    def _lotes_com_problema(self, fim: float) -> int:
        try:
            from . import integridade
            n = 0
            for (lote,) in self._q("SELECT lote FROM integridade_lote WHERE fechado_em>=? ORDER BY fechado_em DESC LIMIT 60", (fim - 30 * 86400,)):
                with self.hub._trava:
                    try:
                        integridade.ler_lote(self.hub._db, lote)
                    except ValueError:
                        n += 1
            return n
        except Exception:
            return 0

    def limpar(self, dias: float | None = None) -> int:
        try:
            dias = float(os.environ.get("PHYSIS_INDICADORES_RETENCAO_DIAS") or 400) if dias is None else dias
        except ValueError:
            dias = 400.0
        limite = int((self.relogio() - dias * 86400) // 3600)
        with self.hub._trava:
            n = self.hub._db.execute("DELETE FROM indicador_hora WHERE hora<?", (limite,)).rowcount
            n += self.hub._db.execute("DELETE FROM indicador_rota WHERE hora<?", (limite,)).rowcount
            self.hub._db.commit()
        return n

    def tarefa_periodica(self) -> None:
        """Para o laço do hub (rodar_diario com passo de 5 min): coleta a hora e, uma vez por dia, aplica a retenção."""
        self.coletar()
        if int(self.relogio() // 3600) % 24 == 3:
            self.limpar()

    # ── séries e aprendizado ──
    def serie(self, chave: str, dias: int = 28, ate: int | None = None) -> list[tuple[int, float]]:
        ate = int(self.relogio() // 3600) if ate is None else ate
        return [(h, v) for h, v in self._q("SELECT hora, valor FROM indicador_hora WHERE chave=? AND hora>? AND hora<=? ORDER BY hora",
                                            (chave, ate - dias * 24, ate))]

    def _retorno(self) -> dict:
        out: dict[str, list[int]] = {}
        for chave, real, n in self._q("SELECT chave, real, COUNT(*) FROM indicador_feedback GROUP BY chave, real"):
            out.setdefault(chave, [0, 0])[0 if real else 1] += n
        return out

    def p_real(self, chave: str, retorno: dict | None = None) -> float:
        r = (retorno if retorno is not None else self._retorno()).get(chave, [0, 0])
        return chance_real(r[0], r[1])

    def anomalias(self, hora: int | None = None, todas: bool = False) -> list[dict]:
        hora = int(self.relogio() // 3600) if hora is None else hora
        ret = self._retorno()
        out = []
        for (chave,) in self._q("SELECT DISTINCT chave FROM indicador_hora WHERE hora=? AND chave NOT LIKE '\\_%' ESCAPE '\\'", (hora,)):
            if chave in NIVEIS:
                continue
            s = self.serie(chave, 28, hora)
            atual = [v for h, v in s if h == hora]
            if not atual:
                continue
            a = anomalia([(h, v) for h, v in s if h < hora], hora, atual[0], self.p_real(chave, ret))
            lado = NOMES.get(chave, ("", "", 0))[2]
            ruim = a.get("z") is not None and (lado == 0 or (a["z"] > 0) == (lado > 0))
            if todas or (a["alerta"] and ruim):
                r = ret.get(chave, [0, 0])
                out.append(dict(a, chave=chave, hora=hora, valor=atual[0], nome=NOMES.get(chave, (chave, chave))[:2],
                                retorno={"reais": r[0], "falsos": r[1]}, lado_ruim=ruim))
        out.sort(key=lambda x: -x["nota"])
        return out

    def padrao(self, ate_hora: int) -> set[str]:
        """Indicadores fora do normal (|z| ≥ 2, com sinal) nas 6 horas antes de `ate_hora`."""
        p = set()
        for (chave,) in self._q("SELECT DISTINCT chave FROM indicador_hora WHERE hora>=? AND hora<=?", (ate_hora - JANELA_INCIDENTE_H, ate_hora)):
            if chave in NIVEIS or chave.startswith("_"):
                continue
            s = self.serie(chave, 28, ate_hora)
            for h, v in s:
                if h < ate_hora - JANELA_INCIDENTE_H:
                    continue
                a = anomalia([(x, y) for x, y in s if x < h], h, v)
                if a.get("suficiente") and abs(a["z"]) >= 2:
                    p.add(f"{chave}{'+' if a['z'] > 0 else '-'}")
        return p

    def registrar_incidente(self, titulo: str, causa: str, correcao: str, quem: str, quando: float | None = None) -> dict:
        titulo, causa, correcao = (str(x or "").strip()[:300] for x in (titulo, causa, correcao))
        if not titulo or not causa:
            return {"ok": False, "codigo": 400, "erro": "falta o título ou a causa"}
        quando = self.relogio() if quando is None else float(quando)
        p = sorted(self.padrao(int(quando // 3600)))
        with self.hub._trava:
            cur = self.hub._db.execute("INSERT INTO indicador_incidente(titulo,causa,correcao,quando,criado_por,padrao) VALUES(?,?,?,?,?,?)",
                                       (titulo, causa, correcao, quando, quem, json.dumps(p)))
            self.hub.registrar("indicadores", quem, {"o_que": "incidente registrado", "id": cur.lastrowid, "padrao": len(p)})
            self.hub._db.commit()
        return {"ok": True, "id": cur.lastrowid, "padrao": p}

    def sugestoes(self, hora: int | None = None, padrao_atual: set | None = None) -> dict:
        """Incidentes passados com padrão parecido (Jaccard ≥ 0,3; 'ajudou' pesa a favor)."""
        hora = int(self.relogio() // 3600) if hora is None else hora
        atual = self.padrao(hora) if padrao_atual is None else set(padrao_atual)
        incs = self._q("SELECT id, titulo, causa, correcao, quando, padrao, ajudou FROM indicador_incidente")
        out = []
        for i, t, c, cor, q, p, aj in incs:
            sim = jaccard(atual, set(json.loads(p or "[]")))
            if sim >= 0.3:
                out.append({"id": i, "titulo": t, "causa": c, "correcao": cor, "quando": q, "semelhanca": round(sim, 2),
                            "nota": round(sim * (1 + 0.2 * min(aj, 5)), 3), "ajudou": aj})
        out.sort(key=lambda x: -x["nota"])
        n = len(incs)
        return {"padrao_atual": sorted(atual), "incidentes_registrados": n, "sugestoes": out[:3],
                "confianca": "dados insuficientes" if n < 3 else "baixa" if n < 10 else "média"}

    def retorno(self, chave: str, hora: int, real: bool, quem: str) -> dict:
        if not re.fullmatch(r"[a-z0-9_.]{2,60}", str(chave or "")) or not isinstance(hora, int):
            return {"ok": False, "codigo": 400, "erro": "alerta inválido"}
        with self.hub._trava:
            self.hub._db.execute("INSERT INTO indicador_feedback(chave,hora,real,quem,quando) VALUES(?,?,?,?,?)",
                                 (chave, hora, 1 if real else 0, quem, self.relogio()))
            self.hub._db.commit()
        return {"ok": True, "p_real": round(self.p_real(chave), 3)}

    def incidente_ajudou(self, ident: int, quem: str) -> dict:
        with self.hub._trava:
            n = self.hub._db.execute("UPDATE indicador_incidente SET ajudou=ajudou+1 WHERE id=?", (ident,)).rowcount
            self.hub._db.commit()
        return {"ok": bool(n)} if n else {"ok": False, "codigo": 404, "erro": "incidente não encontrado"}

    # ── clientes, lacunas e melhorias ──
    def _lacunas(self) -> list[dict]:
        try:
            return json.loads(self.variaveis.read_text(encoding="utf-8")).get("lacunas") or []
        except (OSError, ValueError):
            return []

    def clientes(self) -> list[dict]:
        """Por instalação: número (nunca o nome), módulos, ativação, compra e lacunas de fluxo dos módulos que tem."""
        lac = self._lacunas()
        out = []
        for numero, mods, ativado, criado, compra in self._q("SELECT numero, modulos, ativado, criado, compra FROM instalacao ORDER BY criado"):
            m = set(json.loads(mods or "[]"))
            if "animais" in m:
                m |= {"coleiras", "comedouros"}
            gaps = [{"variavel": l.get("variavel"), "consumidor": l.get("consumidor"), "impacto": l.get("impacto"),
                     "correcao": l.get("correcao_recomendada")} for l in lac
                    if l.get("consumidor") in m and not (set(l.get("produtores") or []) & m)]
            estado = self._um("SELECT estado FROM central WHERE tipo='compra' AND numero=?", (compra,), "")
            out.append({"instalacao": numero, "modulos": sorted(m), "ativado": bool(ativado), "criado": criado, "compra_estado": estado,
                        "lacunas": gaps, "lacunas_altas": sum(1 for g in gaps if g["impacto"] == "alto"),
                        "situacao": "atenção" if any(g["impacto"] == "alto" for g in gaps) or not ativado else "ok"})
        return out

    def _atualizar_backlog(self, agora: float) -> None:
        hora = int(agora // 3600)
        lento = float(os.environ.get("PHYSIS_INDICADORES_LENTO_MS") or 1500)
        itens = []
        for rota, e5, horas in self._q("SELECT rota, SUM(e5), COUNT(*) FROM indicador_rota WHERE hora>? AND e5>0 GROUP BY rota", (hora - 168,)):
            if e5 >= 3:
                itens.append(("erro", rota, f"Erro 5xx que se repete: {rota}", f"{int(e5)} erros 5xx em {horas} hora(s) nos últimos 7 dias"))
        for rota, h_lentas, p95 in self._q("SELECT rota, COUNT(*), MAX(p95) FROM indicador_rota WHERE hora>? AND p95>? GROUP BY rota", (hora - 168, lento)):
            if h_lentas >= 3:
                itens.append(("lenta", rota, f"Rota lenta: {rota}", f"p95 acima de {lento:.0f} ms em {h_lentas} hora(s); pior {p95:.0f} ms"))
        vistos = {r[0] for r in self._q("SELECT DISTINCT no FROM leitura WHERE recebido>?", (agora - 7 * 86400,))}
        for no in sorted(vistos):
            horas = {int(r[0] // 3600) for r in self._q("SELECT recebido FROM leitura WHERE no=? AND recebido>?", (no, agora - 86400))}
            caladas = sum(1 for h in range(hora - 23, hora + 1) if h not in horas)
            if caladas >= 3:
                itens.append(("sensor", f"no{no}", f"Sensor que cai: nó {no}", f"{caladas} de 24 horas sem dado"))
        for c in self.clientes():
            for g in c["lacunas"]:
                if g["impacto"] == "alto":
                    itens.append(("lacuna", f"{c['instalacao']}:{g['variavel']}", f"Lacuna de fluxo em {c['instalacao']}: {g['variavel']}",
                                  str(g.get("correcao") or "")[:300]))
        with self.hub._trava:
            for tipo, ref, titulo, detalhe in itens:
                ident = hashlib.sha256(f"{tipo}|{ref}".encode()).hexdigest()[:16]
                self.hub._db.execute("INSERT INTO indicador_backlog(id,tipo,titulo,detalhe,primeira,ultima,vezes) VALUES(?,?,?,?,?,?,1) "
                                     "ON CONFLICT(id) DO UPDATE SET detalhe=excluded.detalhe, ultima=excluded.ultima, "
                                     "vezes=vezes+CASE WHEN ultima<excluded.ultima-3000 THEN 1 ELSE 0 END",
                                     (ident, tipo, titulo[:200], detalhe[:400], agora, agora))
            self.hub._db.commit()

    def backlog(self) -> list[dict]:
        linhas = self._q("SELECT id,tipo,titulo,detalhe,primeira,ultima,vezes,tarefa_por,tarefa_em FROM indicador_backlog ORDER BY tarefa_em IS NOT NULL, vezes DESC, ultima DESC")
        return [{"id": i, "tipo": t, "titulo": ti, "detalhe": d, "primeira": p, "ultima": u, "vezes": v, "tarefa_por": tp, "tarefa_em": te}
                for i, t, ti, d, p, u, v, tp, te in linhas]

    def virou_tarefa(self, ident: str, quem: str) -> dict:
        with self.hub._trava:
            n = self.hub._db.execute("UPDATE indicador_backlog SET tarefa_por=?, tarefa_em=? WHERE id=?", (quem, self.relogio(), ident)).rowcount
            if n:
                self.hub.registrar("indicadores", quem, {"o_que": "melhoria virou tarefa", "id": ident})
            self.hub._db.commit()
        return {"ok": True} if n else {"ok": False, "codigo": 404, "erro": "item não encontrado"}

    def painel(self) -> dict:
        hora = int(self.relogio() // 3600)
        ult = {k: v for k, v in self._q("SELECT chave, valor FROM indicador_hora WHERE hora=(SELECT MAX(hora) FROM indicador_hora) AND chave NOT LIKE '\\_%' ESCAPE '\\'")}
        horas = self._um("SELECT COUNT(DISTINCT hora) FROM indicador_hora")
        tend = []
        for chave in sorted(ult):
            t = tendencia(self.serie(chave, 14, hora))
            prev = t.pop("previsao", [])
            tend.append(dict(t, chave=chave, nome=NOMES.get(chave, (chave, chave))[:2], ultimo=ult[chave],
                             previsao_24h=prev[-1]["valor"] if prev else None))
        anom = self.anomalias(hora)
        rotas = [{"rota": r, "n": n, "e4": e4, "e5": e5, "p95": p95} for r, n, e4, e5, p95 in self._q(
            "SELECT rota, SUM(n), SUM(e4), SUM(e5), MAX(p95) FROM indicador_rota WHERE hora>? GROUP BY rota ORDER BY SUM(e5) DESC, MAX(p95) DESC LIMIT 10", (hora - 24,))]
        topo = [{"tipo": "anomalia", "titulo": a["nome"][0], "detalhe": f"valor {a['valor']:g}, esperado {a['esperado']:g} (z {a['z']})"} for a in anom[:5]]
        topo += [{"tipo": b["tipo"], "titulo": b["titulo"], "detalhe": b["detalhe"]} for b in self.backlog() if not b["tarefa_em"]][:5]
        return {"ok": True, "hora": hora, "horas_coletadas": horas,
                "amostra": "dados insuficientes: o aprendizado começa a valer com alguns dias de coleta" if horas < 72 else f"{horas} horas coletadas",
                "valores": ult, "nomes": {k: v[:2] for k, v in NOMES.items()}, "clientes": self.clientes(), "problemas": topo[:8],
                "anomalias": anom, "tendencias": tend, "rotas": rotas, "backlog": self.backlog(), "sugestoes": self.sugestoes(hora),
                "incidentes": [{"id": i, "titulo": t, "causa": c, "correcao": cor, "quando": q, "ajudou": a} for i, t, c, cor, q, a in
                               self._q("SELECT id,titulo,causa,correcao,quando,ajudou FROM indicador_incidente ORDER BY quando DESC LIMIT 20")]}

    # ── rotas ──
    def rota(self, metodo: str, caminho: str, conta: dict | None, corpo=None, consulta: dict | None = None):
        """/api/indicadores…: só equipe e direção. Coletar à força: só direção. CSRF: o servidor confere antes."""
        if not caminho.startswith("/api/indicadores"):
            return None
        if not conta:
            return 401, {"ok": False, "erro": "entre com usuario e senha", "login": True}
        if not seg.pode(conta, seg.EQUIPE):
            return 403, {"ok": False, "erro": "o seu papel não permite esta ação"}
        quem = conta.get("usuario") or "?"
        partes = [p for p in caminho.split("/") if p][2:]
        resp = lambda r: (r.pop("codigo", 200 if r.get("ok") else 400), r)
        if metodo == "GET":
            if not partes:
                return 200, self.painel()
            if partes == ["serie"]:
                chave = ((consulta or {}).get("chave") or [""])[0]
                s = self.serie(chave, 14)
                return 200, {"ok": True, "chave": chave, "serie": s, "tendencia": tendencia(s)}
            return 404, {"ok": False, "erro": "rota desconhecida"}
        if metodo != "POST":
            return 405, {"ok": False, "erro": "método não aceito"}
        try:
            d = seg.carregar_json((corpo.decode("utf-8", "replace") if isinstance(corpo, bytes) else corpo) or "{}")
        except ValueError:
            return 400, {"ok": False, "erro": "json invalido"}
        d = d if isinstance(d, dict) else {}
        if partes == ["retorno"]:
            return resp(self.retorno(str(d.get("chave") or ""), d.get("hora"), d.get("real") is True, quem))
        if partes == ["incidentes"]:
            return resp(self.registrar_incidente(d.get("titulo"), d.get("causa"), d.get("correcao"), quem))
        if len(partes) == 3 and partes[0] == "incidentes" and partes[2] == "ajudou" and partes[1].isdigit():
            return resp(self.incidente_ajudou(int(partes[1]), quem))
        if len(partes) == 3 and partes[0] == "backlog" and partes[2] == "tarefa" and re.fullmatch(r"[0-9a-f]{16}", partes[1]):
            return resp(self.virou_tarefa(partes[1], quem))
        if partes == ["coletar"]:
            if not seg.pode(conta, seg.DIRECAO):
                return 403, {"ok": False, "erro": "só a direção força a coleta"}
            return 200, dict(self.coletar(), ok=True)
        return 404, {"ok": False, "erro": "rota desconhecida"}
