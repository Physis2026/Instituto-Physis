"""Alertas de clima enviados às pessoas (e-mail e WhatsApp), não só mostrados na tela.

O que faz, a cada ciclo (15 min no laço de fundo):
  1. lê o que o hub já guardou do clima (Open-Meteo por dia, CEMADEN medido) e a chance de chuva do modelo
     local (aprendizado.py) — nada de internet nesta etapa;
  2. aplica as MESMAS regras da plataforma (painel: alertasAprendidos e Resiliência climática), agora com dois
     níveis: "atencao" e "alerta";
  3. para cada assinatura ativa e com consentimento, filtra pelas atividades, pelos alertas escolhidos e pelo
     nível mínimo; não repete o mesmo alerta no mesmo dia (só sobe de atenção para alerta); respeita o horário
     de silêncio (o nível "alerta" fura o silêncio, se a pessoa deixar);
  4. põe o e-mail na fila email_saida (o correio.py da Physis envia) e manda o WhatsApp pelo enviador
     configurado.

WhatsApp (opcional, desligado por padrão):
  PHYSIS_WHATSAPP_PROVEDOR=callmebot   a mesma API do receptor de campo (firmware/receptor-v6/src/whatsapp.cpp):
                                       GET https://api.callmebot.com/whatsapp.php?phone=&text=&apikey=
                                       Cada pessoa ativa o CallMeBot no próprio WhatsApp e informa a apikey dela.
  PHYSIS_WHATSAPP_PROVEDOR=business    reservado para a API oficial do WhatsApp Business (ainda não implementado)
  RISCO (documentado em docs/ALERTAS_CLIMA.md): a apikey do CallMeBot precisa ir em texto na chamada; com só a
  biblioteca padrão não há cifra de verdade, então ela fica no banco do hub como está. Proteja o arquivo do banco
  (permissões, disco cifrado) e prefira a API oficial quando existir. A apikey nunca aparece nas listagens.

LGPD: só envia para quem deu consentimento (data e versão do termo guardadas); a pessoa pode sair a qualquer
momento (os contatos e a apikey são apagados); o histórico guarda o texto do alerta, não o telefone, e é
apagado depois de 90 dias. O registro do lugar (cadeia) recebe só metadados.
"""
from __future__ import annotations

import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from . import clima as clima_mod

FUSO = clima_mod.FUSO
VERSAO_TERMO = "1"
RETENCAO_DIAS = 90
NIVEIS = {"atencao": 1, "alerta": 2}
NOMES_NIVEL = {"atencao": "Atenção", "alerta": "ALERTA"}
ATIVIDADES = ("cafe", "graos", "gado", "gado_leite", "irrigacao", "hortifruti", "hospedagem")
FINALIDADE = ("Enviar avisos de clima (geada, chuva forte, calor, deslizamento) para o lugar monitorado pela "
              "plataforma Physis, pelos canais escolhidos. Você pode sair quando quiser.")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS alerta_assinatura (
  id INTEGER PRIMARY KEY AUTOINCREMENT, quem TEXT NOT NULL, nome TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '',
  whatsapp TEXT NOT NULL DEFAULT '', whatsapp_chave TEXT NOT NULL DEFAULT '', canais TEXT NOT NULL, alertas TEXT NOT NULL,
  atividades TEXT NOT NULL, nivel_min TEXT NOT NULL DEFAULT 'atencao', silencio_ini TEXT NOT NULL DEFAULT '22:00',
  silencio_fim TEXT NOT NULL DEFAULT '06:00', alerta_fura_silencio INTEGER NOT NULL DEFAULT 1,
  consentimento REAL NOT NULL, versao_termo TEXT NOT NULL, ativa INTEGER NOT NULL DEFAULT 1,
  criado REAL NOT NULL, atualizado REAL NOT NULL);
CREATE TABLE IF NOT EXISTS alerta_envio (
  id INTEGER PRIMARY KEY AUTOINCREMENT, assinatura INTEGER NOT NULL, chave TEXT NOT NULL, dia_envio TEXT NOT NULL,
  nivel TEXT NOT NULL, canal TEXT NOT NULL, estado TEXT NOT NULL, detalhe TEXT NOT NULL DEFAULT '', texto TEXT NOT NULL,
  criado REAL NOT NULL);
CREATE INDEX IF NOT EXISTS alerta_envio_dedup ON alerta_envio(assinatura, chave, dia_envio);
"""

# regra: (título, atividades a que se aplica — None = todo mundo)
REGRAS = {
    "geada_cafe": ("Geada no café", ("cafe",)),
    "chuva_colheita": ("Chuva na colheita", ("cafe", "graos")),
    "calor_rebanho": ("Calor no rebanho", ("gado", "gado_leite")),
    "chuva_irrigacao": ("Chuva prevista: adiar a rega", ("irrigacao",)),
    "chuva_modelo": ("Chuva provável amanhã (modelo do lugar)", ("irrigacao", "hortifruti")),
    "horta": ("Horta e viveiro", ("hortifruti",)),
    "hospedagem_chuva": ("Chuva forte para hóspedes", ("hospedagem",)),
    "deslizamento": ("Chuva acumulada e encostas", None),
}


# ══ Regras (funções puras) ═══════════════════════════════════════════════════════════════════════
def _dm(dia: str) -> str:
    return f"{dia[8:10]}/{dia[5:7]}"


def _n(v, u=""):
    return f"{v:.1f}".replace(".", ",") + u


def avaliar(dias: list[dict], cemaden: dict | None, prob_chuva: dict | None, hoje: str) -> list[dict]:
    """Alertas do momento. dias = Open-Meteo por dia ({dia, mm, tmin, tmax}); cemaden = {mm_24h, mm_72h, estacao};
    prob_chuva = {dia, prob} do modelo local. Cada alerta: {regra, chave, nivel, titulo, texto, dia}."""
    out = []
    futuros = [d for d in dias or [] if str(d.get("dia") or "") >= hoje]

    def add(regra, dia, nivel, texto):
        out.append({"regra": regra, "chave": f"{regra}|{dia}", "nivel": nivel, "titulo": REGRAS[regra][0], "texto": texto, "dia": dia})

    for d in futuros:
        dia, mm, tmin, tmax = d["dia"], d.get("mm") or 0.0, d.get("tmin"), d.get("tmax")
        if tmin is not None and tmin < 3:
            add("geada_cafe", dia, "alerta" if tmin < 1 else "atencao",
                f"Café: risco de geada em {_dm(dia)} (mínima de {_n(tmin, ' °C')}). Proteja as mudas e as plantas novas.")
        if 5 <= int(dia[5:7]) <= 9 and mm >= 10:
            add("chuva_colheita", dia, "alerta" if mm >= 30 else "atencao",
                f"Colheita: chuva de {_n(mm, ' mm')} prevista em {_dm(dia)}. Planeje a colheita e a secagem.")
        if tmax is not None and tmax >= 30:
            add("calor_rebanho", dia, "alerta" if tmax >= 35 else "atencao",
                f"Rebanho: calor de {_n(tmax, ' °C')} em {_dm(dia)}; confira sombra e água.")
        if mm >= 30 or (tmin is not None and tmin < 4) or (tmax is not None and tmax >= 34):
            forte = mm >= 50 or (tmin is not None and tmin < 2) or (tmax is not None and tmax >= 37)
            o_que = f"chuva forte ({_n(mm, ' mm')})" if mm >= 30 else f"frio de {_n(tmin, ' °C')}" if tmin is not None and tmin < 4 else f"calor de {_n(tmax, ' °C')}"
            add("horta", dia, "alerta" if forte else "atencao", f"Horta e viveiro: {o_que} em {_dm(dia)}; proteja canteiros e mudas.")
        if mm >= 30:
            add("hospedagem_chuva", dia, "alerta" if mm >= 50 else "atencao",
                f"Hospedagem: chuva forte ({_n(mm, ' mm')}) em {_dm(dia)}; avise os hóspedes sobre estradas e trilhas.")
    for d in futuros[:2]:
        if (d.get("mm") or 0) >= 5:
            add("chuva_irrigacao", d["dia"], "atencao",
                f"Irrigação: {_n(d['mm'], ' mm')} de chuva prevista em {_dm(d['dia'])}; avalie adiar a rega.")
    if prob_chuva and prob_chuva.get("prob") is not None and prob_chuva["prob"] >= 0.7 and prob_chuva.get("dia"):
        add("chuva_modelo", prob_chuva["dia"], "atencao",
            f"O modelo do lugar dá {round(100 * prob_chuva['prob'])}% de chance de chover em {_dm(prob_chuva['dia'])}; avalie adiar a rega.")
    if cemaden and (cemaden.get("mm_24h") is not None or cemaden.get("mm_72h") is not None):
        a24, a72 = cemaden.get("mm_24h") or 0.0, cemaden.get("mm_72h") or 0.0
        nivel = "alerta" if a24 >= 80 or a72 >= 120 else "atencao" if a24 >= 40 or a72 >= 60 else None
        if nivel:
            est = (cemaden.get("estacao") or {}).get("nome") or "CEMADEN"
            txt = ("Chuva acumulada alta: risco de deslizamento em encostas." if nivel == "alerta" else
                   "Solo encharcando: observe trincas, árvores inclinadas e água barrenta.")
            add("deslizamento", hoje, nivel, f"{txt} Medido ({est}): {_n(a24, ' mm')} em 24 h, {_n(a72, ' mm')} em 72 h. "
                                          "Siga sempre a Defesa Civil.")
    return out


def no_silencio(hhmm: str, ini: str, fim: str) -> bool:
    if not ini or not fim or ini == fim:
        return False
    return ini <= hhmm < fim if ini < fim else (hhmm >= ini or hhmm < fim)


# ══ WhatsApp ═════════════════════════════════════════════════════════════════════════════════════
def _get(url: str, tempo: float) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "PhysisHub/1.0"})
    with urllib.request.urlopen(req, timeout=tempo) as r:
        return r.status, r.read(2000).decode("utf-8", errors="replace")


class CallMeBot:
    """Mesma API do receptor V6. A apikey é de cada pessoa (ela ativa o bot no próprio WhatsApp)."""
    nome = "callmebot"
    URL = "https://api.callmebot.com/whatsapp.php"

    def __init__(self, abrir=_get, tempo: float = 10.0):
        self.abrir, self.tempo = abrir, tempo

    def enviar(self, numero: str, chave: str, texto: str) -> tuple[bool, str]:
        if not numero or not chave:
            return False, "falta número ou apikey do CallMeBot"
        # o texto vai na URL: corta para não estourar o limite (como o receptor faz)
        url = self.URL + "?" + urllib.parse.urlencode({"phone": "+" + numero, "text": texto[:700], "apikey": chave})
        try:
            cod, corpo = self.abrir(url, self.tempo)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return False, f"sem resposta ({type(exc).__name__})"
        return (200 <= cod < 300), f"HTTP {cod}"


class WhatsAppBusiness:
    """Reservado: API oficial (Cloud API da Meta), com token do servidor e modelos de mensagem aprovados."""
    nome = "business"

    def enviar(self, numero: str, chave: str, texto: str) -> tuple[bool, str]:
        return False, "API oficial do WhatsApp Business ainda não implementada"


def enviador_whatsapp():
    p = (os.environ.get("PHYSIS_WHATSAPP_PROVEDOR") or "").strip().lower()
    return CallMeBot() if p == "callmebot" else WhatsAppBusiness() if p == "business" else None


# ══ Assinaturas e envio ═════════════════════════════════════════════════════════════════════════
_EMAIL = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")
_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _numero(v: str) -> str:
    d = re.sub(r"\D", "", str(v or ""))
    if not d:
        return ""
    if len(d) in (10, 11):
        d = "55" + d
    if not 12 <= len(d) <= 13:
        raise ValueError("WhatsApp com DDD, ex.: (24) 99999-0000")
    return d


class AlertasClima:
    def __init__(self, hub, aprendizado=None, whatsapp="padrao", relogio=None):
        self.hub = hub
        self.aprendizado = aprendizado
        self.whatsapp = enviador_whatsapp() if whatsapp == "padrao" else whatsapp
        self.relogio = relogio or hub.relogio
        with hub._trava:
            hub._db.executescript(clima_mod.ESQUEMA + ESQUEMA)
            hub._db.commit()

    @property
    def _db(self):
        return self.hub._db

    # ── assinaturas ──
    def assinar(self, d: dict, quem: str) -> dict:
        """Cria ou altera (com "id") uma assinatura. Exige consentimento explícito (LGPD)."""
        if d.get("consentimento") is not True:
            return {"ok": False, "erro": "é preciso aceitar receber os avisos (consentimento)", "finalidade": FINALIDADE}
        try:
            email = str(d.get("email") or "").strip()[:160]
            if email and not _EMAIL.match(email):
                raise ValueError("e-mail inválido")
            whats = _numero(d.get("whatsapp"))
            chave = str(d.get("whatsapp_chave") or "").strip()[:64]
            canais = [c for c in (d.get("canais") or ["email"]) if c in ("email", "whatsapp")]
            if not canais:
                raise ValueError("escolha e-mail e/ou WhatsApp")
            if "email" in canais and not email:
                raise ValueError("informe o e-mail")
            if "whatsapp" in canais and not whats:
                raise ValueError("informe o WhatsApp")
            alertas = [a for a in (d.get("alertas") or list(REGRAS)) if a in REGRAS] or list(REGRAS)
            atividades = [a for a in (d.get("atividades") or []) if a in ATIVIDADES]
            nivel = d.get("nivel_min") or "atencao"
            if nivel not in NIVEIS:
                raise ValueError("nível mínimo: atencao ou alerta")
            ini, fim = str(d.get("silencio_ini") or "22:00"), str(d.get("silencio_fim") or "06:00")
            if not (_HORA.match(ini) and _HORA.match(fim)):
                raise ValueError("horário de silêncio no formato HH:MM")
        except ValueError as exc:
            return {"ok": False, "erro": str(exc)}
        agora = self.relogio()
        campos = (str(d.get("nome") or "").strip()[:80], email, whats, json.dumps(canais), json.dumps(alertas), json.dumps(atividades),
                  nivel, ini, fim, 0 if d.get("alerta_fura_silencio") is False else 1)
        with self.hub._trava:
            ident = d.get("id")
            if ident:
                atual = self._db.execute("SELECT quem, whatsapp_chave FROM alerta_assinatura WHERE id=? AND ativa=1", (int(ident),)).fetchone()
                if not atual:
                    return {"ok": False, "erro": "assinatura não encontrada"}
                if atual[0] != quem and not d.get("_admin"):
                    return {"ok": False, "erro": "só quem assinou (ou a direção) pode mudar", "codigo": 403}
                self._db.execute("UPDATE alerta_assinatura SET nome=?, email=?, whatsapp=?, canais=?, alertas=?, atividades=?, nivel_min=?, "
                                 "silencio_ini=?, silencio_fim=?, alerta_fura_silencio=?, whatsapp_chave=?, consentimento=?, versao_termo=?, "
                                 "atualizado=? WHERE id=?", campos + (chave or atual[1], agora, VERSAO_TERMO, agora, int(ident)))
            else:
                ident = self._db.execute(
                    "INSERT INTO alerta_assinatura(quem,nome,email,whatsapp,canais,alertas,atividades,nivel_min,silencio_ini,silencio_fim,"
                    "alerta_fura_silencio,whatsapp_chave,consentimento,versao_termo,criado,atualizado) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (quem,) + campos + (chave, agora, VERSAO_TERMO, agora, agora)).lastrowid
            self._db.commit()
        self.hub.registrar("alerta_assinatura", quem or "plataforma", {"o_que": "consentimento", "id": int(ident), "termo": VERSAO_TERMO,
                                                                         "canais": canais})
        with self.hub._trava:
            self._db.commit()
        return {"ok": True, "assinatura": self._uma(int(ident))}

    def sair(self, ident: int, quem: str, admin: bool = False) -> dict:
        """Retira o consentimento: desativa e apaga contatos e apikey (o histórico fica sem telefone)."""
        with self.hub._trava:
            r = self._db.execute("SELECT quem FROM alerta_assinatura WHERE id=? AND ativa=1", (int(ident),)).fetchone()
            if not r:
                return {"ok": False, "erro": "assinatura não encontrada"}
            if r[0] != quem and not admin:
                return {"ok": False, "erro": "só quem assinou (ou a direção) pode cancelar", "codigo": 403}
            self._db.execute("UPDATE alerta_assinatura SET ativa=0, email='', whatsapp='', whatsapp_chave='', atualizado=? WHERE id=?",
                             (self.relogio(), int(ident)))
            self._db.commit()
        self.hub.registrar("alerta_assinatura", quem or "plataforma", {"o_que": "consentimento retirado", "id": int(ident)})
        with self.hub._trava:
            self._db.commit()
        return {"ok": True}

    _COLS = ("id", "quem", "nome", "email", "whatsapp", "whatsapp_chave", "canais", "alertas", "atividades", "nivel_min",
             "silencio_ini", "silencio_fim", "alerta_fura_silencio", "consentimento", "versao_termo", "ativa")

    def _ler(self, onde: str = "ativa=1", args=()) -> list[dict]:
        out = []
        for r in self._db.execute(f"SELECT {','.join(self._COLS)} FROM alerta_assinatura WHERE {onde} ORDER BY id", args):
            d = dict(zip(self._COLS, r))
            for k in ("canais", "alertas", "atividades"):
                d[k] = json.loads(d[k])
            out.append(d)
        return out

    @staticmethod
    def _mascarar(d: dict) -> dict:
        d = dict(d)
        d["whatsapp_chave"] = ("…" + d["whatsapp_chave"][-3:]) if d.get("whatsapp_chave") else ""
        return d

    def _uma(self, ident: int) -> dict | None:
        with self.hub._trava:
            r = self._ler("id=?", (ident,))
        return self._mascarar(r[0]) if r else None

    def assinaturas(self, quem: str | None = None) -> list[dict]:
        """Lista (apikey mascarada). quem=None: todas (direção)."""
        with self.hub._trava:
            lista = self._ler() if quem is None else self._ler("ativa=1 AND quem=?", (quem,))
        return [self._mascarar(d) for d in lista]

    # ── avaliação e envio ──
    def alertas_agora(self) -> list[dict]:
        agora = self.relogio()
        hoje = datetime.fromtimestamp(agora, FUSO).strftime("%Y-%m-%d")
        dados = {}
        with self.hub._trava:
            for fonte, txt, consultado in self._db.execute("SELECT fonte, dados, consultado FROM clima_fonte WHERE consultado > 0"):
                if agora - consultado <= max(clima_mod.VALIDADE_S.get(fonte, 6 * 3600), 6 * 3600) * 2:
                    try:
                        dados[fonte] = json.loads(txt or "{}")
                    except ValueError:
                        pass
        prob = None
        if self.aprendizado is not None:
            try:
                prob = self.aprendizado.previsao_chuva()
            except Exception:       # noqa: BLE001 — sem modelo, as regras seguem valendo
                prob = None
        return avaliar((dados.get("openmeteo") or {}).get("dias") or [], dados.get("cemaden"), prob, hoje)

    def ciclo(self) -> dict:
        agora = self.relogio()
        dt = datetime.fromtimestamp(agora, FUSO)
        hoje, hhmm = dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
        alertas = self.alertas_agora()
        enviados = adiados = 0
        with self.hub._trava:
            assin = self._ler()
            self._db.execute("DELETE FROM alerta_envio WHERE criado < ?", (agora - RETENCAO_DIAS * 86400,))
            self._db.commit()
        for s in assin:
            for a in alertas:
                ativ = REGRAS[a["regra"]][1]
                if a["regra"] not in s["alertas"] or NIVEIS[a["nivel"]] < NIVEIS[s["nivel_min"]]:
                    continue
                if ativ is not None and not set(ativ) & set(s["atividades"]):
                    continue
                with self.hub._trava:
                    ja = self._db.execute("SELECT MAX(CASE nivel WHEN 'alerta' THEN 2 ELSE 1 END) FROM alerta_envio "
                                          "WHERE assinatura=? AND chave=? AND dia_envio=? AND estado != 'falhou'",
                                          (s["id"], a["chave"], hoje)).fetchone()[0]
                if ja and ja >= NIVEIS[a["nivel"]]:
                    continue                                    # já avisado hoje neste nível ou acima
                if no_silencio(hhmm, s["silencio_ini"], s["silencio_fim"]) and not (a["nivel"] == "alerta" and s["alerta_fura_silencio"]):
                    adiados += 1
                    continue                                    # sai no primeiro ciclo depois do silêncio
                enviados += self._despachar(s, a, hoje)
        if enviados:
            self.hub.registrar("alerta_clima", "hub", {"o_que": "avisos enviados", "quantos": enviados,
                                                      "regras": sorted({a["regra"] for a in alertas})})
            with self.hub._trava:
                self._db.commit()
        return {"ok": True, "alertas": alertas, "enviados": enviados, "adiados_silencio": adiados}

    def _despachar(self, s: dict, a: dict, hoje: str) -> int:
        titulo = f"[Physis] {NOMES_NIVEL[a['nivel']]}: {a['titulo']}"
        texto = f"{titulo}\n{a['texto']}\n\nLugar: {self.hub.lugar}. Para deixar de receber, abra a plataforma → Alertas."
        n = 0
        for canal in s["canais"]:
            estado, detalhe = "falhou", ""
            if canal == "email" and s["email"]:
                with self.hub._trava:
                    ident = self._db.execute("INSERT INTO email_saida(para,assunto,corpo,estado,ref,criado) VALUES(?,?,?,?,?,?)",
                                             (s["email"], titulo, texto, "pendente", f"alerta-{s['id']}", self.relogio())).lastrowid
                    self._db.commit()
                estado, detalhe = "enfileirado", f"email_saida {ident}"
            elif canal == "whatsapp" and s["whatsapp"]:
                if self.whatsapp is None:
                    detalhe = "WhatsApp não configurado no servidor (PHYSIS_WHATSAPP_PROVEDOR)"
                else:
                    ok, detalhe = self.whatsapp.enviar(s["whatsapp"], s["whatsapp_chave"], texto)
                    estado = "enviado" if ok else "falhou"
            else:
                continue
            with self.hub._trava:
                self._db.execute("INSERT INTO alerta_envio(assinatura,chave,dia_envio,nivel,canal,estado,detalhe,texto,criado) "
                                 "VALUES(?,?,?,?,?,?,?,?,?)", (s["id"], a["chave"], hoje, a["nivel"], canal, estado, detalhe[:200],
                                                               a["texto"], self.relogio()))
                self._db.commit()
            n += estado != "falhou"
        return n

    def historico(self, limite: int = 200, quem: str | None = None) -> list[dict]:
        cols = ("id", "assinatura", "chave", "dia_envio", "nivel", "canal", "estado", "detalhe", "texto", "criado")
        sql = "SELECT " + ",".join("e." + c for c in cols) + " FROM alerta_envio e"
        args: tuple = ()
        if quem is not None:
            sql += " JOIN alerta_assinatura s ON s.id = e.assinatura WHERE s.quem=?"
            args = (quem,)
        with self.hub._trava:
            return [dict(zip(cols, r)) for r in self._db.execute(sql + " ORDER BY e.id DESC LIMIT ?", args + (max(1, min(int(limite), 2000)),))]


def enviar_emails(hub, enviar_fila) -> int:
    """Manda só os e-mails pendentes dos alertas (ref "alerta-<assinatura>"). enviar_fila = correio.enviar_fila."""
    refs = sorted({e["ref"] for e in hub.emails("pendente") if str(e["ref"]).startswith("alerta-")})
    return sum(enviar_fila(hub, r) for r in refs)


def rodar(alertas: AlertasClima, parar: threading.Event, passo: float = 900.0, enviar=None) -> None:
    """Laço de fundo: avalia a cada 15 min e, se saiu algo, manda os e-mails (enviar())."""
    while not parar.is_set():
        try:
            if alertas.ciclo()["enviados"] and enviar:
                enviar()
        except Exception:          # noqa: BLE001 — um defeito aqui não pode derrubar o hub
            pass
        parar.wait(passo)
