"""Suporte remoto com prazo ("Permitir suporte"), pedido em docs/LISTA-DE-MODIFICACOES.md §3 (15/11/2026).

A direção do cliente (papel administrador desta instalação) libera, depois de confirmar a senha (reautenticação), um
acesso de suporte por 2 h, 8 h, 1 dia ou 3 dias, com nota opcional e a opção "só ver". O sistema gera um código
aleatório (secrets) que aparece UMA vez na tela; o banco guarda só o resumo SHA-256.

Enquanto a concessão vale, a equipe da Physis abre uma sessão "suporte_physis" com o código + a conta da equipe Physis
(lista em PHYSIS_SUPORTE_CONTAS), SOMENTE a partir das redes de PHYSIS_SUPORTE_REDES (CIDR da VPN, por exemplo
WireGuard/Tailscale 100.64.0.0/10). Outro endereço é recusado, mesmo com o código certo. Sem PHYSIS_SUPORTE_REDES, nada entra.
A sessão tem o papel equipe (operador) nesta instalação; com "só ver", só leitura (GET/HEAD).

A direção revoga quando quiser; o prazo encerra sozinho. Concessões vencidas ou revogadas ficam guardadas (auditoria).
Cada concessão, uso (rota chamada, nunca o conteúdo), tentativa recusada, revogação e vencimento vai para o registro
encadeado do hub (hub.registrar, tipo "suporte_remoto") e para a lista que o cliente vê. O código nunca é registrado.
Nada é copiado para a Physis por este recurso: o acesso é na própria instalação do cliente, pela VPN montada por fora
(doc 10, item 0.3). Este módulo não hospeda túnel nenhum.
"""
from __future__ import annotations

import hashlib
import ipaddress
import os
import secrets
import time

from . import seguranca as seg

# corpos das rotas (seguranca.validar; o servidor usa seg.ESQUEMAS)
seg.ESQUEMAS.setdefault("suporte_conceder", {"duracao": (str, 4, True), "nota": (str, 300, False), "so_ver": (bool, None, False)})
seg.ESQUEMAS.setdefault("suporte_revogar", {"id": (str, 40, True)})
seg.ESQUEMAS.setdefault("suporte_entrar", {"codigo": (str, 40, True), "equipe": (str, 160, True)})

DURACOES = {"2h": 2 * 3600, "8h": 8 * 3600, "1d": 24 * 3600, "3d": 72 * 3600}
PAPEL_SUPORTE = seg.EQUIPE                  # "operador": o papel equipe da instalação
FALHAS_MAX, ESPERA_S = 5, 60.0              # limite de tentativas por endereço
SESSAO_MAX_S = 8 * 3600                     # uma sessão de suporte dura no máximo 8 h (e nunca passa da concessão)
LEITURA = ("GET", "HEAD", "OPTIONS")
ESQUEMA = """
CREATE TABLE IF NOT EXISTS suporte_concessao (
  id TEXT PRIMARY KEY, resumo TEXT NOT NULL, inicio REAL NOT NULL, expira REAL NOT NULL, por TEXT NOT NULL,
  nota TEXT NOT NULL DEFAULT '', so_ver INTEGER NOT NULL DEFAULT 0, revogada REAL, revogada_por TEXT NOT NULL DEFAULT '',
  encerrada INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS suporte_sessao (
  resumo TEXT PRIMARY KEY, concessao TEXT NOT NULL, equipe TEXT NOT NULL, ip TEXT NOT NULL, criado REAL NOT NULL, expira REAL NOT NULL);
CREATE TABLE IF NOT EXISTS suporte_evento (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, quando REAL NOT NULL, concessao TEXT NOT NULL DEFAULT '', tipo TEXT NOT NULL,
  quem TEXT NOT NULL DEFAULT '', ip TEXT NOT NULL DEFAULT '', detalhe TEXT NOT NULL DEFAULT '');
"""


def _sha(texto: str) -> str:
    return hashlib.sha256((texto or "").encode("utf-8")).hexdigest()


def redes_config(valor: str | None = None) -> list:
    """PHYSIS_SUPORTE_REDES: lista de CIDR separados por vírgula ou espaço. Vazio = nenhuma rede (suporte desligado)."""
    v = os.environ.get("PHYSIS_SUPORTE_REDES", "") if valor is None else valor
    redes = []
    for parte in str(v).replace(",", " ").split():
        try:
            redes.append(ipaddress.ip_network(parte, strict=False))
        except ValueError:
            continue
    return redes


def contas_config(valor: str | None = None) -> set:
    """PHYSIS_SUPORTE_CONTAS: contas da equipe Physis que podem usar o código (e-mails, separados por vírgula)."""
    v = os.environ.get("PHYSIS_SUPORTE_CONTAS", "") if valor is None else valor
    return {x.strip().lower() for x in str(v).replace(";", ",").split(",") if x.strip()}


def na_vpn(ip: str, redes: list) -> bool:
    try:
        a = ipaddress.ip_address((ip or "").strip())
    except ValueError:
        return False
    return any(a in r for r in redes if a.version == r.version)


class SuporteRemoto:
    def __init__(self, hub, redes: list | None = None, contas: set | None = None, relogio=None):
        self.hub = hub
        self.redes = redes_config() if redes is None else redes
        self.contas = contas_config() if contas is None else contas
        self.relogio = relogio or getattr(hub, "relogio", time.time)
        self._falhas: dict[str, tuple[int, float]] = {}
        with hub._trava:
            hub._db.executescript(ESQUEMA)
            hub._db.commit()

    # ── registro: banco próprio (lista do cliente) + cadeia do hub. Nunca o código. ──
    def _evento(self, tipo: str, concessao: str = "", quem: str = "", ip: str = "", detalhe: str = "") -> None:
        agora = self.relogio()
        with self.hub._trava:
            self.hub._db.execute("INSERT INTO suporte_evento(quando,concessao,tipo,quem,ip,detalhe) VALUES(?,?,?,?,?,?)",
                                 (agora, concessao, tipo, quem[:120], (ip or "")[:64], detalhe[:300]))
            self.hub._db.commit()
        self.hub.registrar("suporte_remoto", "suporte", {"evento": tipo, "concessao": concessao, "quem": quem[:120],
                                                          "ip": (ip or "")[:64], "detalhe": detalhe[:300]})

    def _vencer(self) -> None:
        """Marca as concessões vencidas (uma vez cada) e apaga as sessões delas."""
        agora = self.relogio()
        with self.hub._trava:
            vencidas = self.hub._db.execute("SELECT id FROM suporte_concessao WHERE encerrada=0 AND revogada IS NULL AND expira <= ?",
                                            (agora,)).fetchall()
            for (ident,) in vencidas:
                self.hub._db.execute("UPDATE suporte_concessao SET encerrada=1 WHERE id=?", (ident,))
                self.hub._db.execute("DELETE FROM suporte_sessao WHERE concessao=?", (ident,))
            self.hub._db.commit()
        for (ident,) in vencidas:
            self._evento("expirou", ident)

    # ── direção do cliente ──
    def conceder(self, conta: dict | None, duracao: str, nota: str = "", so_ver: bool = False, ip: str = "") -> dict:
        if not seg.pode(conta, seg.DIRECAO):
            return {"ok": False, "codigo": 403, "erro": "Só a direção desta instalação libera o suporte."}
        if not seg.reauth_recente(self.hub, conta):
            return {"ok": False, "codigo": 403, "reautenticar": True, "erro": "Confirme a sua senha para liberar o suporte."}
        if duracao not in DURACOES:
            return {"ok": False, "codigo": 400, "erro": "Prazo: 2h, 8h, 1d ou 3d."}
        self._vencer()
        agora = self.relogio()
        codigo = "-".join(secrets.token_hex(3).upper() for _ in range(3))   # ex.: 4F2A9C-1B7E03-C0D5E8, mostrado uma vez
        ident = secrets.token_hex(6)
        with self.hub._trava:
            self.hub._db.execute("INSERT INTO suporte_concessao(id,resumo,inicio,expira,por,nota,so_ver) VALUES(?,?,?,?,?,?,?)",
                                 (ident, _sha(codigo), agora, agora + DURACOES[duracao], conta["usuario"], (nota or "")[:300], 1 if so_ver else 0))
            self.hub._db.commit()
        self._evento("concedido", ident, conta["usuario"], ip, f"prazo {duracao}" + ("; só ver" if so_ver else "") + (f"; nota: {nota[:200]}" if nota else ""))
        return {"ok": True, "codigo_acesso": codigo, "concessao": self._uma(ident),
                "aviso": "Anote o código agora: ele não aparece de novo. Passe-o só à equipe Physis."}

    def revogar(self, conta: dict | None, ident: str, ip: str = "") -> dict:
        if not seg.pode(conta, seg.DIRECAO):
            return {"ok": False, "codigo": 403, "erro": "Só a direção desta instalação revoga o suporte."}
        agora = self.relogio()
        with self.hub._trava:
            n = self.hub._db.execute("UPDATE suporte_concessao SET revogada=?, revogada_por=?, encerrada=1 WHERE id=? AND revogada IS NULL AND encerrada=0",
                                     (agora, conta["usuario"], str(ident))).rowcount
            self.hub._db.execute("DELETE FROM suporte_sessao WHERE concessao=?", (str(ident),))
            self.hub._db.commit()
        if not n:
            return {"ok": False, "codigo": 404, "erro": "Concessão não encontrada ou já encerrada."}
        self._evento("revogado", str(ident), conta["usuario"], ip)
        return {"ok": True}

    def _uma(self, ident: str) -> dict | None:
        r = self.hub._db.execute("SELECT id,inicio,expira,por,nota,so_ver,revogada,revogada_por,encerrada FROM suporte_concessao WHERE id=?", (ident,)).fetchone()
        if not r:
            return None
        agora = self.relogio()
        sit = "revogada" if r[6] else ("vencida" if r[8] or r[2] <= agora else "valendo")
        return {"id": r[0], "inicio": r[1], "expira": r[2], "por": r[3], "nota": r[4], "so_ver": bool(r[5]),
                "revogada": r[6], "revogada_por": r[7], "situacao": sit}

    def listar(self, conta: dict | None, limite: int = 200) -> dict:
        """Concessões (todas, para auditoria) e o que o suporte fez: quem, quando, endereço da VPN e rota (sem conteúdo)."""
        if not seg.pode(conta, seg.DIRECAO):
            return {"ok": False, "codigo": 403, "erro": "Só a direção desta instalação vê o suporte."}
        self._vencer()
        with self.hub._trava:
            ids = [r[0] for r in self.hub._db.execute("SELECT id FROM suporte_concessao ORDER BY inicio DESC LIMIT 50")]
            conc = [self._uma(i) for i in ids]
            ev = [dict(zip(("quando", "concessao", "tipo", "quem", "ip", "detalhe"), r)) for r in self.hub._db.execute(
                "SELECT quando,concessao,tipo,quem,ip,detalhe FROM suporte_evento ORDER BY seq DESC LIMIT ?", (int(limite),))]
        return {"ok": True, "concessoes": conc, "eventos": ev, "vpn_configurada": bool(self.redes),
                "contas_configuradas": bool(self.contas), "duracoes": list(DURACOES)}   # D23: vazio = ninguém da Physis entra

    # ── equipe da Physis, pela VPN ──
    def entrar(self, codigo: str, equipe: str, ip: str, agente: str = "") -> dict:
        agora, equipe = self.relogio(), (equipe or "").strip().lower()
        if not na_vpn(ip, self.redes):
            self._evento("recusado", "", equipe, ip, "fora da rede da VPN")
            return {"ok": False, "codigo": 403, "erro": "Acesso de suporte só pela VPN configurada nesta instalação."}
        n, ate = self._falhas.get(ip, (0, 0.0))
        if agora < ate:
            self._evento("recusado", "", equipe, ip, "muitas tentativas")
            return {"ok": False, "codigo": 429, "erro": f"Muitas tentativas. Tente de novo em {int(ate - agora) + 1} s."}
        self._vencer()
        r = None
        if equipe and equipe in self.contas:
            with self.hub._trava:
                r = self.hub._db.execute("SELECT id, expira, so_ver FROM suporte_concessao WHERE resumo=? AND revogada IS NULL AND encerrada=0 AND expira > ?",
                                         (_sha((codigo or "").strip().upper()), agora)).fetchone()
        if not r:
            n += 1
            self._falhas[ip] = (n, agora + ESPERA_S if n >= FALHAS_MAX else 0.0)
            self._evento("recusado", "", equipe, ip, "código ou conta da equipe não confere")
            return {"ok": False, "codigo": 403, "erro": "Código ou conta da equipe Physis não confere, ou a concessão já terminou."}
        self._falhas.pop(ip, None)
        token = secrets.token_urlsafe(32)
        with self.hub._trava:
            self.hub._db.execute("INSERT INTO suporte_sessao(resumo,concessao,equipe,ip,criado,expira) VALUES(?,?,?,?,?,?)",
                                 (seg.resumo(token), r[0], equipe, ip[:64], agora, min(r[1], agora + SESSAO_MAX_S)))
            self.hub._db.commit()
        self._evento("entrou", r[0], equipe, ip, (agente or "")[:120])
        return {"ok": True, "token": token, "so_ver": bool(r[2]), "expira": min(r[1], agora + SESSAO_MAX_S)}

    def sessao(self, token: str | None, ip: str) -> dict | None:
        """Conta da sessão de suporte (papel equipe), ou None. Fora da VPN ou depois do prazo, cai."""
        if not token:
            return None
        self._vencer()
        agora = self.relogio()
        with self.hub._trava:
            r = self.hub._db.execute("SELECT s.concessao, s.equipe, s.ip, c.so_ver FROM suporte_sessao s JOIN suporte_concessao c ON c.id = s.concessao "
                                     "WHERE s.resumo=? AND s.expira > ? AND c.revogada IS NULL AND c.encerrada=0 AND c.expira > ?",
                                     (seg.resumo(token), agora, agora)).fetchone()
        if not r:
            return None
        if not na_vpn(ip, self.redes):
            self._evento("recusado", r[0], r[1], ip, "sessão usada fora da VPN")
            return None
        return {"id": 0, "nome": "Suporte Physis", "usuario": "suporte_physis:" + r[1], "papel": PAPEL_SUPORTE, "pessoa": "",
                "suporte": True, "so_ver": bool(r[3]), "concessao": r[0], "confirmado": True, "reauth": 0.0}

    def pode_metodo(self, conta: dict | None, metodo: str) -> bool:
        """Sessão "só ver": só leitura. Sair é sempre permitido."""
        return not (conta and conta.get("suporte") and conta.get("so_ver") and metodo.upper() not in LEITURA)

    def uso(self, conta: dict | None, metodo: str, rota: str, ip: str, recusado: bool = False) -> None:
        """Registra o que o suporte fez: método e rota (sem a consulta nem o corpo)."""
        if conta and conta.get("suporte"):
            self._evento("recusado" if recusado else "uso", conta.get("concessao", ""), conta["usuario"], ip,
                         f"{metodo.upper()} {str(rota).split('?')[0][:200]}" + (" (só ver: escrita bloqueada)" if recusado else ""))

    def sair(self, token: str | None, conta: dict | None = None, ip: str = "") -> None:
        with self.hub._trava:
            self.hub._db.execute("DELETE FROM suporte_sessao WHERE resumo=?", (seg.resumo(token or ""),))
            self.hub._db.commit()
        if conta and conta.get("suporte"):
            self._evento("saiu", conta.get("concessao", ""), conta["usuario"], ip)
