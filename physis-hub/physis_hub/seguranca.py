"""Segurança do servidor quando ele fica exposto à internet (só biblioteca padrão).

O que mora aqui (explicado em docs/SEGURANCA.md):
  - rede: qual é o IP de verdade de quem chama (atrás de um proxy confiável), se o pedido veio por HTTPS,
    se quem chama está na rede local;
  - papéis: direção (administrador), equipe (operador) e cliente, e quem pode o quê;
  - limitador por IP (balde de fichas, em memória) para formulários públicos, envio de arquivo e login;
  - chaves por dispositivo (só o resumo SHA-256 fica no banco; a chave aparece uma vez, na criação);
  - registro de acessos (Marco Civil, art. 15: 6 meses);
  - LGPD art. 18: "Meus dados" (exportar) e "Apagar meus dados" (apaga ou anonimiza);
  - política de retenção (PHYSIS_RETENCAO_DIAS_*), rodada uma vez por dia;
  - fluxos de conta: recuperar a senha por e-mail, confirmar o e-mail, convite da equipe, consentimento LGPD;
  - política de senha, 2FA por aplicativo (TOTP, RFC 6238) com códigos de recuperação, reautenticação,
    CSRF (Origin/Referer + token no cabeçalho), JSON e arquivos validados, eventos de segurança na cadeia.

Nada aqui importa o hub: as funções recebem o hub (ou o banco) como parâmetro.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import threading
import time
import unicodedata

# ── Papéis ──────────────────────────────────────────────────────────────────
# Os nomes guardados no banco não mudam (as telas já usam "administrador" e "operador");
# "direcao"/"direção" e "equipe" são aceitos como apelidos na entrada. "cliente" é novo.
DIRECAO, EQUIPE, CLIENTE = "administrador", "operador", "cliente"
PAPEIS = (DIRECAO, EQUIPE, CLIENTE)
_APELIDOS = {"administrador": DIRECAO, "direcao": DIRECAO, "direção": DIRECAO, "admin": DIRECAO,
             "operador": EQUIPE, "equipe": EQUIPE, "cliente": CLIENTE}
_NIVEL = {CLIENTE: 1, EQUIPE: 2, DIRECAO: 3}


def normalizar_papel(papel) -> str | None:
    """'direção' -> 'administrador', 'equipe' -> 'operador', 'cliente' -> 'cliente'; outro -> None."""
    return _APELIDOS.get(str(papel or "").strip().lower())


def pode(conta: dict | None, minimo: str) -> bool:
    """A conta (da sessão) tem pelo menos o papel pedido? Sem conta, nunca.
    Conta com o e-mail ainda não confirmado (quando a confirmação é exigida) vale no máximo como cliente."""
    if not conta:
        return False
    nivel = _NIVEL.get(normalizar_papel(conta.get("papel")) or "", 0)
    if conta.get("confirmado") is False:
        nivel = min(nivel, _NIVEL[CLIENTE])
    return nivel >= _NIVEL[normalizar_papel(minimo)]


# ── Rede: IP de quem chama, HTTPS e rede local ──────────────────────────────
def _ip(texto: str | None):
    try:
        a = ipaddress.ip_address(str(texto or "").strip().strip("[]"))
    except ValueError:
        return None
    if a.version == 6 and a.ipv4_mapped:
        return a.ipv4_mapped
    return a


def proxies_confiaveis(valor: str | None = None) -> list:
    """PHYSIS_PROXY_CONFIAVEL: IPs ou redes (CIDR) separados por vírgula, ex. "127.0.0.1,::1".
    Só desses endereços o servidor acredita em X-Forwarded-For e X-Forwarded-Proto."""
    bruto = os.environ.get("PHYSIS_PROXY_CONFIAVEL", "") if valor is None else valor
    redes = []
    for parte in bruto.split(","):
        parte = parte.strip()
        if not parte:
            continue
        try:
            redes.append(ipaddress.ip_network(parte, strict=False))
        except ValueError:
            continue
    return redes


def _confiavel(ip: str, proxies: list) -> bool:
    a = _ip(ip)
    return a is not None and any(a.version == r.version and a in r for r in proxies)


def ip_do_cliente(par: str, cabecalhos, proxies: list) -> str:
    """IP de quem chama. Direto: o par da conexão. Por um proxy confiável: o último endereço de
    X-Forwarded-For que não é proxy confiável. Proxy confiável sem X-Forwarded-For: "desconhecido"
    (tratado como de fora, nunca como rede local)."""
    if not proxies or not _confiavel(par, proxies):
        return par
    partes = [p.strip() for p in (cabecalhos.get("X-Forwarded-For") or "").split(",") if p.strip()]
    for p in reversed(partes):
        a = _ip(p)
        if a is None:
            return "desconhecido"
        if not _confiavel(str(a), proxies):
            return str(a)
    return "desconhecido"


def eh_https(par: str, cabecalhos, proxies: list) -> bool:
    """PHYSIS_HTTPS=1 (o servidor só é alcançado por HTTPS) ou X-Forwarded-Proto: https vindo de um proxy confiável."""
    if os.environ.get("PHYSIS_HTTPS") == "1":
        return True
    if not proxies or not _confiavel(par, proxies):
        return False
    return (cabecalhos.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower() == "https"


# Redes locais de verdade (RFC 1918, loopback, link-local, IPv6 ULA). Não usa ip.is_private: no Python ele
# também marca faixas de documentação (ex. 203.0.113.0/24) como privadas.
REDES_LOCAIS = tuple(ipaddress.ip_network(r) for r in (
    "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "::1/128", "fc00::/7", "fe80::/10"))


def eh_rede_local(ip: str) -> bool:
    """Loopback ou rede privada (192.168.x, 10.x, 172.16-31.x, fc00::/7, link-local), mais as redes de
    PHYSIS_REDE_LOCAL (CIDR, vírgulas). Com PHYSIS_EXPOSTO=1 ninguém é considerado da rede local."""
    if os.environ.get("PHYSIS_EXPOSTO") == "1":
        return False
    a = _ip(ip)
    if a is None:
        return False
    redes = REDES_LOCAIS + tuple(proxies_confiaveis(os.environ.get("PHYSIS_REDE_LOCAL", "")))
    return any(a.version == r.version and a in r for r in redes)


# ── Cabeçalhos de segurança (além da CSP, que fica em servidor.politica) ─────
HSTS = "max-age=31536000; includeSubDomains"


def politica_permissoes(chamadas: str | None = None) -> str:
    """Permissions-Policy: câmera e microfone só na própria página (Reuniões) e no servidor de chamadas,
    se houver; localização só na própria página (clima do lugar); o resto desligado."""
    o = f' "{chamadas}"' if chamadas else ""
    return (f"camera=(self{o}), microphone=(self{o}), display-capture=(self{o}), geolocation=(self), "
            "payment=(), usb=(), serial=(), hid=(), bluetooth=(), midi=(), magnetometer=(), gyroscope=(), "
            "accelerometer=(), browsing-topics=()")


def cabecalhos_extra(https: bool, chamadas: str | None = None) -> list[tuple[str, str]]:
    c = [("Permissions-Policy", politica_permissoes(chamadas)),
         ("Cross-Origin-Opener-Policy", "same-origin"),
         ("Cross-Origin-Resource-Policy", "same-origin"),
         ("X-Frame-Options", "SAMEORIGIN")]
    if https:
        c.append(("Strict-Transport-Security", HSTS))
    return c


# ── Limitador por IP (balde de fichas, em memória) ──────────────────────────
class Limitador:
    """Cada chave (IP) tem um balde com `capacidade` fichas que se recarrega por inteiro em `janela_s`.
    tentar() gasta uma ficha e devolve 0; sem ficha, devolve quantos segundos esperar."""

    def __init__(self, capacidade: float, janela_s: float, relogio=time.monotonic, max_chaves: int = 50_000):
        self.capacidade, self.taxa = float(capacidade), float(capacidade) / float(janela_s)
        self.relogio, self.max_chaves = relogio, max_chaves
        self._baldes: dict[str, tuple[float, float]] = {}
        self._trava = threading.Lock()

    def tentar(self, chave: str, custo: float = 1.0) -> float:
        with self._trava:
            agora = self.relogio()
            fichas, antes = self._baldes.get(chave, (self.capacidade, agora))
            fichas = min(self.capacidade, fichas + (agora - antes) * self.taxa)
            if fichas >= custo:
                self._baldes[chave] = (fichas - custo, agora)
                if len(self._baldes) > self.max_chaves:
                    self._limpar(agora)
                return 0.0
            self._baldes[chave] = (fichas, agora)
            return (custo - fichas) / self.taxa

    def _limpar(self, agora: float) -> None:
        cheio = [k for k, (f, t) in self._baldes.items() if f + (agora - t) * self.taxa >= self.capacidade]
        for k in cheio:
            del self._baldes[k]
        if len(self._baldes) > self.max_chaves:          # ainda grande: começa do zero (melhor que crescer sem fim)
            self._baldes.clear()


# categoria -> (variável de ambiente, padrão "fichas/segundos")
LIMITES_PADRAO = {
    "publico": ("PHYSIS_LIMITE_PUBLICO", "20/600"),           # compra, pedido (consultoria e loja), suporte sem sessão
    "arquivo": ("PHYSIS_LIMITE_ARQUIVO", "10/600"),           # anexos de até 20 MB do pedido
    "entrar": ("PHYSIS_LIMITE_ENTRAR", "10/300"),             # login, criar conta, código de ativação (por IP)
    "dispositivo": ("PHYSIS_LIMITE_DISPOSITIVO", "1200/60"),  # linhas dos aparelhos
}


def ler_limite(texto: str | None, padrao: str) -> tuple[float, float] | None:
    """"20/600" -> (20, 600). "0" ou "off" desliga (None). Valor estranho -> padrão."""
    t = (texto if texto is not None else padrao).strip().lower()
    if t in ("0", "off", "nao", "não"):
        return None
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", t)
    if not m or float(m.group(1)) <= 0 or float(m.group(2)) <= 0:
        m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", padrao)
    return float(m.group(1)), float(m.group(2))


class Limites:
    """Um limitador por categoria, lidos do ambiente quando o servidor nasce."""

    def __init__(self, relogio=time.monotonic):
        self._lim: dict[str, Limitador | None] = {}
        for cat, (var, padrao) in LIMITES_PADRAO.items():
            v = ler_limite(os.environ.get(var), padrao)
            self._lim[cat] = Limitador(v[0], v[1], relogio) if v else None

    def tentar(self, categoria: str, ip: str) -> float:
        lim = self._lim.get(categoria)
        return lim.tentar(ip) if lim else 0.0


# ── Segredos: sessão e chaves de dispositivo guardadas só como resumo ───────
def resumo(segredo: str) -> str:
    return hashlib.sha256(str(segredo or "").encode("utf-8")).hexdigest()


def iguais(a: str | None, b: str | None) -> bool:
    """Comparação em tempo constante (não vaza, pelo tempo, quantos caracteres batem)."""
    return a is not None and b is not None and hmac.compare_digest(str(a).encode("utf-8"), str(b).encode("utf-8"))


PREFIXO_CHAVE = "phk_"


def chave_do_pedido(cabecalhos) -> str | None:
    """Authorization: Bearer <chave>  ou  X-Physis-Chave: <chave>."""
    a = (cabecalhos.get("Authorization") or "").strip()
    if a[:7].lower() == "bearer ":
        return a[7:].strip() or None
    return (cabecalhos.get("X-Physis-Chave") or "").strip() or None


TABELAS = """
CREATE TABLE IF NOT EXISTS dispositivo_chave (
  id INTEGER PRIMARY KEY AUTOINCREMENT, no INTEGER, rotulo TEXT NOT NULL DEFAULT '', resumo TEXT NOT NULL UNIQUE,
  criado REAL NOT NULL, por TEXT NOT NULL DEFAULT '', revogado REAL, usado REAL);
CREATE TABLE IF NOT EXISTS acesso_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, quando REAL NOT NULL, usuario TEXT NOT NULL, ip TEXT NOT NULL, evento TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS acesso_log_quando ON acesso_log(quando);
CREATE TABLE IF NOT EXISTS segredo (nome TEXT PRIMARY KEY, valor BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS conta_token (
  id INTEGER PRIMARY KEY AUTOINCREMENT, resumo TEXT NOT NULL UNIQUE, tipo TEXT NOT NULL, conta INTEGER,
  usuario TEXT NOT NULL, dados TEXT NOT NULL DEFAULT '{}', criado REAL NOT NULL, expira REAL NOT NULL,
  usado REAL, revogado REAL, por TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS consentimento (
  id INTEGER PRIMARY KEY AUTOINCREMENT, conta INTEGER NOT NULL, versao TEXT NOT NULL, aceito INTEGER NOT NULL,
  quando REAL NOT NULL, ip_resumo TEXT NOT NULL DEFAULT '');
"""

# colunas novas da conta (2FA, confirmação do e-mail, consentimento) e da sessão (ociosidade, reautenticação)
_COLUNAS_CONTA = {"confirmado": "REAL", "consentimento_versao": "TEXT NOT NULL DEFAULT ''", "consentimento_em": "REAL",
                  "totp_segredo": "TEXT NOT NULL DEFAULT ''", "totp_ativo": "INTEGER NOT NULL DEFAULT 0",
                  "totp_recuperacao": "TEXT NOT NULL DEFAULT '[]'", "totp_ultimo": "INTEGER NOT NULL DEFAULT 0"}
_COLUNAS_SESSAO = {"visto": "REAL NOT NULL DEFAULT 0", "reauth": "REAL NOT NULL DEFAULT 0"}


def preparar(db) -> None:
    db.executescript(TABELAS)
    cols = {r[1] for r in db.execute("PRAGMA table_info(conta)")}
    for nome, tipo in _COLUNAS_CONTA.items():
        if nome not in cols:
            db.execute(f"ALTER TABLE conta ADD COLUMN {nome} {tipo}")
            if nome == "confirmado":           # contas que já existiam contam como confirmadas
                db.execute("UPDATE conta SET confirmado=criado")
    cols = {r[1] for r in db.execute("PRAGMA table_info(sessao)")}
    for nome, tipo in _COLUNAS_SESSAO.items():
        if nome not in cols:
            db.execute(f"ALTER TABLE sessao ADD COLUMN {nome} {tipo}")


def chave_criar(hub, no, rotulo: str, por: str) -> dict:
    """Cria a chave de um dispositivo. no=None: chave de receptor/gateway (aceita qualquer nó);
    no=N: só aceita linhas com ID:N. A chave volta aqui UMA vez; o banco guarda só o resumo."""
    if no not in (None, ""):
        try:
            no = int(no)
        except (TypeError, ValueError):
            return {"ok": False, "erro": "nó inválido"}
        if not 0 <= no <= 9999:
            return {"ok": False, "erro": "nó inválido"}
    else:
        no = None
    rotulo = re.sub(r"[\x00-\x1f]", "", str(rotulo or "")).strip()[:80]
    chave = PREFIXO_CHAVE + secrets.token_urlsafe(32)
    with hub._trava:
        cur = hub._db.execute("INSERT INTO dispositivo_chave(no,rotulo,resumo,criado,por) VALUES(?,?,?,?,?)",
                              (no, rotulo, resumo(chave), hub.relogio(), por))
        ident = cur.lastrowid
        hub.registrar("dispositivo", por, {"o_que": "chave criada", "id": ident, "no": no, "rotulo": rotulo})
        hub._db.commit()
    return {"ok": True, "id": ident, "no": no, "rotulo": rotulo, "chave": chave,
            "aviso": "guarde a chave agora: ela não aparece de novo"}


def chave_listar(hub) -> list[dict]:
    with hub._trava:
        linhas = hub._db.execute("SELECT id, no, rotulo, criado, por, revogado, usado FROM dispositivo_chave ORDER BY id").fetchall()
    return [{"id": i, "no": n, "rotulo": r, "criado": c, "por": p, "revogado": rv, "usado": u, "ativa": rv is None}
            for i, n, r, c, p, rv, u in linhas]


def chave_revogar(hub, ident, por: str) -> bool:
    try:
        ident = int(ident)
    except (TypeError, ValueError):
        return False
    with hub._trava:
        cur = hub._db.execute("UPDATE dispositivo_chave SET revogado=? WHERE id=? AND revogado IS NULL", (hub.relogio(), ident))
        if cur.rowcount:
            hub.registrar("dispositivo", por, {"o_que": "chave revogada", "id": ident})
        hub._db.commit()
        return cur.rowcount > 0


def chave_conferir(hub, chave: str | None) -> dict | None:
    """{"id", "no"} da chave ativa, ou None."""
    if not chave or not chave.startswith(PREFIXO_CHAVE) or len(chave) > 200:
        return None
    r_ = resumo(chave)
    with hub._trava:
        r = hub._db.execute("SELECT id, no, resumo, usado FROM dispositivo_chave WHERE resumo=? AND revogado IS NULL", (r_,)).fetchone()
        if not r or not iguais(r[2], r_):
            return None
        agora = hub.relogio()
        if not r[3] or agora - r[3] > 60:            # marca o último uso sem gravar a cada linha
            hub._db.execute("UPDATE dispositivo_chave SET usado=? WHERE id=?", (agora, r[0]))
            hub._db.commit()
    return {"id": r[0], "no": r[1]}


_ID_LINHA = re.compile(r"^\s*ID:(\d+)")


def filtrar_do_no(corpo: str, no: int | None) -> tuple[str, int]:
    """Com chave presa a um nó, só passam as linhas desse nó (ID:N). Devolve (corpo, recusadas)."""
    if no is None:
        return corpo, 0
    ficam, fora = [], 0
    for linha in corpo.split("\n"):
        if not linha.strip():
            continue
        m = _ID_LINHA.match(linha)
        if m and int(m.group(1)) == no:
            ficam.append(linha)
        else:
            fora += 1
    return "\n".join(ficam), fora


# ── Registro de acessos (Marco Civil da Internet, art. 15: guardar 6 meses) ─
def acesso_registrar(hub, usuario: str, ip: str, evento: str, cadeia: bool = True) -> None:
    """Guarda no registro de acessos (6 meses) e, se cadeia, também como evento de segurança na cadeia
    (com pseudônimo no lugar do e-mail, para a cadeia não guardar dado pessoal)."""
    with hub._trava:
        hub._db.execute("INSERT INTO acesso_log(quando,usuario,ip,evento) VALUES(?,?,?,?)",
                        (hub.relogio(), (usuario or "")[:160], (ip or "")[:64], evento[:40]))
        hub._db.commit()
    if cadeia:
        evento_seguranca(hub, evento, usuario, ip=ip)


# ── LGPD art. 18: Meus dados e Apagar meus dados ─────────────────────────────
def _parece_email(t: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", t or ""))


def _menciona(dados, usuario: str) -> bool:
    return bool(usuario) and usuario.lower() in json.dumps(dados, ensure_ascii=False).lower()


def _registros_da_central(hub, conta: dict) -> list[tuple]:
    """Linhas da central (compra, pedido, suporte, alocação) que são desta pessoa: pelo e-mail
    (quando o usuário é um e-mail) ou, no suporte, pelo usuário que abriu o chamado."""
    u = (conta.get("usuario") or "").lower()
    with hub._trava:
        linhas = hub._db.execute("SELECT tipo, numero, dados, estado, criado, atualizado FROM central ORDER BY criado").fetchall()
    fica = []
    for t, n, d, e, c, a in linhas:
        try:
            dd = json.loads(d)
        except ValueError:
            continue
        if (t == "suporte" and isinstance(dd, dict) and str(dd.get("usuario") or "").lower() == u) or \
                (_parece_email(u) and t != "alocacao" and _menciona(dd, u)):
            fica.append((t, n, dd, e, c, a))
    return fica


def meus_dados(hub, conta: dict) -> dict:
    """Tudo o que o servidor guarda sobre a pessoa da sessão, em JSON (LGPD art. 18, II e V)."""
    u = conta["usuario"]
    with hub._trava:
        c = hub._db.execute("SELECT nome, usuario, papel, pessoa, ativa, criado FROM conta WHERE id=?", (conta["id"],)).fetchone()
        sess = hub._db.execute("SELECT criado, expira, ip, agente FROM sessao WHERE conta=? ORDER BY criado", (conta["id"],)).fetchall()
        acessos = hub._db.execute("SELECT quando, ip, evento FROM acesso_log WHERE usuario=? ORDER BY quando", (u,)).fetchall()
        inst = hub._db.execute("SELECT numero, compra, org, nome, email, modulos, criado, ativado FROM instalacao WHERE lower(email)=?",
                               (u.lower(),)).fetchall() if _parece_email(u) else []
        mails = hub._db.execute("SELECT id, assunto, estado, ref, criado, enviado FROM email_saida WHERE lower(para) LIKE ? ESCAPE '\\'",
                                ("%" + re.sub(r"([%_\\])", r"\\\1", u.lower()) + "%",)).fetchall() if _parece_email(u) else []
        padrao = "%" + re.sub(r"([%_\\])", r"\\\1", u) + "%"
        ps = '%"ref":"' + pseudonimo(hub, u) + '"%'
        reg = hub._db.execute("SELECT tipo, quando, origem, conteudo FROM registro WHERE origem=? OR conteudo LIKE ? ESCAPE '\\' "
                              "OR conteudo LIKE ? ORDER BY seq LIMIT 5000", (u, padrao, ps)).fetchall()
        cons = hub._db.execute("SELECT versao, aceito, quando FROM consentimento WHERE conta=? ORDER BY id", (conta["id"],)).fetchall()
        dois = hub._db.execute("SELECT totp_ativo, confirmado FROM conta WHERE id=?", (conta["id"],)).fetchone()
        gest = hub._db.execute("SELECT chave, versao, atualizado FROM gestao_estado WHERE por=? ORDER BY chave", (u,)).fetchall()
        garq = hub._db.execute("SELECT id, nome, tamanho, criado FROM gestao_arquivo WHERE por=? ORDER BY criado", (u,)).fetchall()
    return {
        "ok": True, "formato": "physis-meus-dados/1", "gerado": hub.relogio(), "org": hub.org, "lugar": hub.lugar,
        "conta": dict(zip(("nome", "usuario", "papel", "pessoa", "ativa", "criado"), c), dois_fatores=bool(dois[0]),
                      email_confirmado=dois[1]) if c else None,
        "consentimentos": [{"versao": v, "aceito": bool(a), "quando": q} for v, a, q in cons],
        "sessoes": [{"criado": a, "expira": b, "ip": i, "navegador": g} for a, b, i, g in sess],
        "acessos": [{"quando": q, "ip": i, "evento": e} for q, i, e in acessos],
        "central": [{"tipo": t, "numero": n, "dados": d, "estado": e, "criado": c_, "atualizado": a}
                    for t, n, d, e, c_, a in _registros_da_central(hub, conta)],
        "instalacoes": [{"numero": n, "compra": cp, "org": o, "nome": nm, "email": e, "modulos": json.loads(m), "criado": cr, "ativado": at}
                        for n, cp, o, nm, e, m, cr, at in inst],
        "emails": [{"id": i, "assunto": a, "estado": e, "ref": r, "criado": c_, "enviado": en} for i, a, e, r, c_, en in mails],
        "registro": [{"tipo": t, "quando": q, "origem": o, "conteudo": json.loads(ct)} for t, q, o, ct in reg],
        "gestao": {"partes": [{"chave": k, "versao": v, "atualizado": a} for k, v, a in gest],
                   "arquivos": [{"id": i, "nome": n, "tamanho": t, "criado": c_} for i, n, t, c_ in garq]},
        "observacoes": ["A senha não é guardada: só um resumo PBKDF2 com sal, que não volta a ser senha.",
                        "Dados de saúde (caixinha de remédios e pulseira) têm exportação própria na aba Saúde.",
                        "Pedidos e compras aparecem aqui quando trazem o seu e-mail."],
    }


_ANON = "[anonimizado]"
_CHAVES_PESSOAIS = {"nome", "email", "mail", "cpf", "rg", "telefone", "fone", "celular", "whatsapp", "contato", "endereco",
                    "cep", "quem", "pagador", "cliente", "responsavel", "titular", "documento", "usuario", "ip", "mensagem",
                    "texto", "observacao", "observacoes", "nascimento"}
_LISTAS_DE_ITENS = {"itens", "produtos", "modulos", "carrinho", "linhas"}


def _chave_limpa(k) -> str:
    k = unicodedata.normalize("NFKD", str(k)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", k)


def anonimizar(dados, email: str = ""):
    """Troca os campos pessoais (nome, e-mail, CPF, telefone, endereço, contato, mensagem...) por
    "[anonimizado]". Mantém valores, datas, números de fatura e os itens comprados (registro fiscal)."""
    e = (email or "").lower()
    if isinstance(dados, dict):
        fora = {}
        for k, v in dados.items():
            ck = _chave_limpa(k)
            if ck in _LISTAS_DE_ITENS:
                fora[k] = v
            elif ck in _CHAVES_PESSOAIS or any(ck.startswith(p) or ck.endswith(p) for p in ("email", "cpf", "telefone", "endereco", "nome")):
                fora[k] = _ANON if v not in (None, "", [], {}) else v
            else:
                fora[k] = anonimizar(v, email)
        return fora
    if isinstance(dados, list):
        return [anonimizar(v, email) for v in dados]
    if isinstance(dados, str) and e and e in dados.lower():
        return _ANON
    return dados


def apagar_titular(hub, conta: dict, senha: str) -> dict:
    """Apaga a conta da pessoa e anonimiza o que precisa ficar (LGPD art. 16 e 18, VI):
    - compras: ficam (registro fiscal, CTN art. 173/195: 5 anos), sem nome/e-mail/CPF/telefone/endereço;
    - pedidos e chamados: anonimizados; anexos dos pedidos: apagados;
    - e-mails não enviados para ela: apagados; enviados: endereço e texto apagados;
    - sessões: apagadas; registro de acessos: fica até completar 6 meses (Marco Civil, art. 15);
    - registro encadeado: não muda (quebraria a cadeia); recebe a entrada "dados apagados" com um resumo do usuário.
    Exige a senha atual. A última conta de direção ativa não pode se apagar (a instalação ficaria sem dono)."""
    u = conta["usuario"]
    with hub._trava:
        r = hub._db.execute("SELECT id, papel, sal, resumo FROM conta WHERE id=?", (conta["id"],)).fetchone()
        if not r or not hmac.compare_digest(hub._resumir(senha or "", r[2]), r[3]):
            return {"ok": False, "codigo": 403, "erro": "A senha não confere."}
        if r[1] == DIRECAO and hub._db.execute("SELECT COUNT(*) FROM conta WHERE papel=? AND ativa=1 AND id<>?",
                                               (DIRECAO, r[0])).fetchone()[0] == 0:
            return {"ok": False, "codigo": 409, "erro": "Esta é a única conta da direção. Passe a direção a outra conta antes de apagar a sua."}
        n = {"central": 0, "anexos": 0, "emails_apagados": 0, "emails_anonimizados": 0, "instalacoes": 0, "sessoes": 0}
        for t, num, d, _e, _c, _a in _registros_da_central(hub, conta):
            hub._db.execute("UPDATE central SET dados=?, atualizado=? WHERE tipo=? AND numero=?",
                            (json.dumps(anonimizar(d, u), ensure_ascii=False), hub.relogio(), t, num))
            n["central"] += 1
            if t == "pedido":
                n["anexos"] += hub._db.execute("DELETE FROM central_arquivo WHERE pedido=?", (num,)).rowcount
        if _parece_email(u):
            like = "%" + re.sub(r"([%_\\])", r"\\\1", u.lower()) + "%"
            n["emails_apagados"] = hub._db.execute("DELETE FROM email_saida WHERE lower(para) LIKE ? ESCAPE '\\' AND estado IN ('pendente','falhou')",
                                                   (like,)).rowcount
            n["emails_anonimizados"] = hub._db.execute("UPDATE email_saida SET para=?, corpo='[apagado a pedido do titular]' "
                                                       "WHERE lower(para) LIKE ? ESCAPE '\\'", (_ANON, like)).rowcount
            n["instalacoes"] = hub._db.execute("UPDATE instalacao SET email=? WHERE lower(email)=?", (_ANON, u.lower())).rowcount
        hub._db.execute("UPDATE gestao_estado SET por='[conta apagada]' WHERE por=?", (u,))
        hub._db.execute("UPDATE gestao_arquivo SET por='[conta apagada]' WHERE por=?", (u,))
        n["sessoes"] = hub._db.execute("DELETE FROM sessao WHERE conta=?", (r[0],)).rowcount
        hub._db.execute("DELETE FROM conta_token WHERE conta=? OR lower(usuario)=?", (r[0], u.lower()))
        hub._db.execute("DELETE FROM consentimento WHERE conta=?", (r[0],))
        hub._db.execute("DELETE FROM conta WHERE id=?", (r[0],))
        hub.registrar("lgpd", "titular", {"o_que": "dados apagados a pedido do titular (LGPD art. 18, VI)",
                                          "ref": resumo(u.lower())[:16], "contagens": n})
        hub._db.commit()
    return {"ok": True, "apagado": True, "contagens": n,
            "mantido": ["compras anonimizadas (registro fiscal, 5 anos)",
                        "registro de acessos até completar 6 meses (Marco Civil, art. 15)",
                        "registro encadeado de auditoria (não pode ser alterado)"]}


# ── Retenção: o que sai do banco com o tempo ────────────────────────────────
# PHYSIS_RETENCAO_DIAS_<NOME>; 0 desliga aquela regra. As sessões vencidas sempre saem.
RETENCAO_PADRAO = {
    "SESSAO": 0,            # >0: também derruba sessões abertas há mais de N dias (além das vencidas)
    "ACESSO": 183,          # registro de acessos: 6 meses (Marco Civil, art. 15) e depois apaga
    "EMAIL_PENDENTE": 30,   # e-mails que nunca saíram (pendente/falhou)
    "EMAIL_ENVIADO": 365,   # texto dos e-mails enviados (fica só assunto, estado e data)
    "PEDIDO": 0,            # pedidos de proposta: anonimiza e apaga os anexos depois de N dias
    "SUPORTE": 0,           # chamados de suporte: anonimiza depois de N dias
}


def retencao_config() -> dict:
    cfg = {}
    for k, padrao in RETENCAO_PADRAO.items():
        try:
            cfg[k] = max(0, int(os.environ.get(f"PHYSIS_RETENCAO_DIAS_{k}", padrao)))
        except ValueError:
            cfg[k] = padrao
    return cfg


def aplicar_retencao(hub, cfg: dict | None = None) -> dict:
    cfg = retencao_config() if cfg is None else dict(RETENCAO_PADRAO, **cfg)
    dia = 86400.0
    with hub._trava:
        agora = hub.relogio()
        n = {"sessoes": hub._db.execute("DELETE FROM sessao WHERE expira < ?", (agora,)).rowcount}
        if cfg["SESSAO"]:
            n["sessoes"] += hub._db.execute("DELETE FROM sessao WHERE criado < ?", (agora - cfg["SESSAO"] * dia,)).rowcount
        n["tokens"] = hub._db.execute("DELETE FROM conta_token WHERE expira < ?", (agora - 7 * dia,)).rowcount
        if cfg["ACESSO"]:
            n["acessos"] = hub._db.execute("DELETE FROM acesso_log WHERE quando < ?", (agora - cfg["ACESSO"] * dia,)).rowcount
        if cfg["EMAIL_PENDENTE"]:
            n["emails_pendentes"] = hub._db.execute("DELETE FROM email_saida WHERE estado IN ('pendente','falhou') AND criado < ?",
                                                    (agora - cfg["EMAIL_PENDENTE"] * dia,)).rowcount
        if cfg["EMAIL_ENVIADO"]:
            n["emails_enviados"] = hub._db.execute("UPDATE email_saida SET corpo='[apagado pela política de retenção]' "
                                                   "WHERE estado LIKE 'enviado%' AND criado < ? AND corpo NOT LIKE '[apagado%'",
                                                   (agora - cfg["EMAIL_ENVIADO"] * dia,)).rowcount
        for tipo, chave in (("pedido", "PEDIDO"), ("suporte", "SUPORTE")):
            if not cfg[chave]:
                continue
            linhas = hub._db.execute("SELECT numero, dados FROM central WHERE tipo=? AND criado < ? AND dados NOT LIKE '%\"_anonimizado\": true%'",
                                     (tipo, agora - cfg[chave] * dia)).fetchall()
            for num, d in linhas:
                try:
                    dd = anonimizar(json.loads(d))
                except ValueError:
                    continue
                if isinstance(dd, dict):
                    dd["_anonimizado"] = True
                hub._db.execute("UPDATE central SET dados=? WHERE tipo=? AND numero=?", (json.dumps(dd, ensure_ascii=False), tipo, num))
                if tipo == "pedido":
                    hub._db.execute("DELETE FROM central_arquivo WHERE pedido=?", (num,))
            n[tipo] = len(linhas)
        if any(v for k, v in n.items() if k not in ("sessoes", "tokens")):
            hub.registrar("retencao", "servidor", {"o_que": "política de retenção aplicada", "contagens": n})
        hub._db.commit()
    return n


def rodar_retencao(hub, parar: threading.Event, intervalo: float = 86400.0) -> None:
    while not parar.is_set():
        try:
            aplicar_retencao(hub)
        except Exception:          # um erro aqui não pode derrubar o servidor; tenta de novo amanhã
            pass
        parar.wait(intervalo)


# ════════════════════════════════════════════════════════════════════════════
# Segunda parte: contas (senha, e-mail, convite, consentimento), 2FA, CSRF e validação
# ════════════════════════════════════════════════════════════════════════════

# ── Segredo do servidor (gerado uma vez com secrets, guardado no banco) ─────
def segredo_servidor(hub) -> bytes:
    """32 bytes aleatórios, criados na primeira vez. Servem para HMAC: token CSRF, pseudônimos e resumo de IP."""
    s = getattr(hub, "_segredo_seg", None)
    if s:
        return s
    with hub._trava:
        r = hub._db.execute("SELECT valor FROM segredo WHERE nome='servidor'").fetchone()
        if not r:
            hub._db.execute("INSERT INTO segredo(nome,valor) VALUES('servidor',?)", (secrets.token_bytes(32),))
            hub._db.commit()
            r = hub._db.execute("SELECT valor FROM segredo WHERE nome='servidor'").fetchone()
    hub._segredo_seg = bytes(r[0])
    return hub._segredo_seg


def _hmac(hub, texto: str) -> str:
    return hmac.new(segredo_servidor(hub), texto.encode("utf-8"), hashlib.sha256).hexdigest()


def pseudonimo(hub, usuario: str) -> str:
    """Identifica a pessoa na cadeia sem guardar o e-mail (a cadeia não pode ser apagada)."""
    return _hmac(hub, "pessoa|" + (usuario or "").strip().lower())[:16]


def ip_resumo(hub, ip: str) -> str:
    return _hmac(hub, "ip|" + (ip or ""))[:24]


def evento_seguranca(hub, o_que: str, usuario: str = "", ip: str = "", **extra) -> None:
    """Evento de segurança na cadeia do registro: o quê, pseudônimo da pessoa, resumo do IP."""
    conteudo = {"o_que": o_que[:60], "ref": pseudonimo(hub, usuario) if usuario else "", "ip": ip_resumo(hub, ip) if ip else ""}
    conteudo.update({k: v for k, v in extra.items() if isinstance(v, (str, int, float, bool)) or v is None})
    with hub._trava:
        hub.registrar("seguranca", "servidor", conteudo)
        hub._db.commit()


# ── Política de senha (ASVS 2.1): tamanho mínimo, lista de senhas comuns, sem regras de composição ──
SENHA_MIN = 12
SENHA_MAX = 256
_COMUNS = frozenset("""
123456789012 1234567890123 12345678910 1234567890 123456789 000000000000 111111111111 123123123123 121212121212
qwertyuiop qwertyuiopas asdfghjkl zxcvbnm qwerty123456 1qaz2wsx3edc qazwsxedcrfv abcdefghijkl abcdef123456
password passw0rd password1 password123 password1234 senha senha123 senha1234 senha12345 senhasenha minhasenha
senhaforte senhasegura mudar123 mudarsenha trocar123 alterar123 admin admin123 administrador administrator
iloveyou princess sunshine football baseball welcome welcome123 letmein monkey dragon master shadow superman
batman trustno1 starwars whatever freedom computer internet bemvindo bemvinda brasil brasil123 flamengo corinthians
palmeiras saopaulo vasco gremio cruzeiro santos botafogo fluminense amor amorzinho teamo jesus deus deusefiel
familia felicidade saudade estrela princesa physis physisengineering engenharia sustentabilidade energia solar
""".split())


def senha_fraca(senha, usuario: str = "") -> str | None:
    """Mensagem dizendo por que a senha não serve, ou None se serve."""
    if not isinstance(senha, str):
        return "Senha inválida."
    if len(senha) < SENHA_MIN:
        return f"A senha precisa de pelo menos {SENHA_MIN} caracteres."
    if len(senha) > SENHA_MAX:
        return f"A senha pode ter até {SENHA_MAX} caracteres."
    baixa = senha.lower()
    letras = re.sub(r"[^a-zà-ÿ]", "", baixa)
    if baixa in _COMUNS or (letras in _COMUNS and len(letras) >= 3) or re.sub(r"[^a-z0-9]", "", baixa) in _COMUNS:
        return "Essa senha é muito comum. Use uma frase com palavras suas."
    if len(set(senha)) <= 3:
        return "A senha repete poucos caracteres. Use uma frase com palavras suas."
    numeros = "01234567890123456789"
    alfabeto = "abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyz"
    if baixa in numeros or baixa in alfabeto or baixa in numeros[::-1] or baixa in alfabeto[::-1]:
        return "A senha é uma sequência. Use uma frase com palavras suas."
    local = (usuario or "").strip().lower().split("@")[0]
    if len(local) >= 4 and local in baixa and len(baixa.replace(local, "")) < 8:
        return "A senha é quase igual ao seu usuário. Use uma frase com palavras suas."
    return None


# ── 2FA por aplicativo autenticador (TOTP, RFC 6238; HMAC-SHA1, 30 s, 6 dígitos) ──
TOTP_PASSO = 30


def totp_novo_segredo() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _hotp(segredo_b32: str, contador: int, digitos: int = 6) -> str:
    chave = base64.b32decode(segredo_b32 + "=" * (-len(segredo_b32) % 8), casefold=True)
    h = hmac.new(chave, contador.to_bytes(8, "big"), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    n = (int.from_bytes(h[o:o + 4], "big") & 0x7FFFFFFF) % (10 ** digitos)
    return str(n).zfill(digitos)


def totp_codigo(segredo_b32: str, agora: float) -> str:
    return _hotp(segredo_b32, int(agora // TOTP_PASSO))


def totp_conferir(segredo_b32: str, codigo: str, agora: float, ultimo: int = 0, janela: int = 1) -> int | None:
    """Passo de tempo aceito (para impedir reuso), ou None. Aceita 1 passo de folga para cada lado."""
    codigo = re.sub(r"\s", "", str(codigo or ""))
    if not segredo_b32 or not re.fullmatch(r"\d{6}", codigo):
        return None
    passo = int(agora // TOTP_PASSO)
    for p in range(passo - janela, passo + janela + 1):
        if p > ultimo and hmac.compare_digest(_hotp(segredo_b32, p), codigo):
            return p
    return None


def totp_uri(segredo_b32: str, usuario: str, emissor: str = "Physis") -> str:
    from urllib.parse import quote
    return f"otpauth://totp/{quote(emissor)}:{quote(usuario)}?secret={segredo_b32}&issuer={quote(emissor)}&algorithm=SHA1&digits=6&period=30"


def _codigos_recuperacao(n: int = 10) -> list[str]:
    abc = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return ["-".join("".join(secrets.choice(abc) for _ in range(5)) for _ in range(2)) for _ in range(n)]


def _limpo(codigo: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(codigo or "").upper())


def totp_iniciar(hub, conta_id: int, usuario: str) -> dict:
    seg_ = totp_novo_segredo()
    with hub._trava:
        r = hub._db.execute("SELECT totp_ativo FROM conta WHERE id=?", (conta_id,)).fetchone()
        if not r:
            return {"ok": False, "erro": "Conta não encontrada."}
        if r[0]:
            return {"ok": False, "erro": "A verificação em duas etapas já está ligada."}
        hub._db.execute("UPDATE conta SET totp_segredo=?, totp_ultimo=0 WHERE id=?", (seg_, conta_id))
        hub._db.commit()
    return {"ok": True, "segredo": seg_, "uri": totp_uri(seg_, usuario, "Physis " + hub.org)}


def totp_ativar(hub, conta_id: int, usuario: str, codigo: str) -> dict:
    with hub._trava:
        r = hub._db.execute("SELECT totp_segredo, totp_ativo, totp_ultimo FROM conta WHERE id=?", (conta_id,)).fetchone()
        if not r or not r[0] or r[1]:
            return {"ok": False, "erro": "Comece pelo passo 1 (gerar a chave)."}
        passo = totp_conferir(r[0], codigo, hub.relogio(), r[2])
        if passo is None:
            return {"ok": False, "erro": "O código não confere. Confira a hora do celular e tente o código novo."}
        cods = _codigos_recuperacao()
        hub._db.execute("UPDATE conta SET totp_ativo=1, totp_ultimo=?, totp_recuperacao=? WHERE id=?",
                        (passo, json.dumps([resumo(_limpo(c)) for c in cods]), conta_id))
        hub._db.commit()
    evento_seguranca(hub, "2fa ligada", usuario)
    return {"ok": True, "recuperacao": cods, "aviso": "Guarde estes códigos: cada um entra uma vez, se você perder o celular."}


def totp_desativar(hub, conta_id: int, usuario: str, codigo: str) -> dict:
    if not segundo_fator(hub, conta_id, codigo, usuario):
        return {"ok": False, "erro": "O código não confere."}
    with hub._trava:
        hub._db.execute("UPDATE conta SET totp_ativo=0, totp_segredo='', totp_recuperacao='[]', totp_ultimo=0 WHERE id=?", (conta_id,))
        hub._db.commit()
    evento_seguranca(hub, "2fa desligada", usuario)
    return {"ok": True}


def totp_ligado(hub, conta_id: int) -> bool:
    with hub._trava:
        r = hub._db.execute("SELECT totp_ativo FROM conta WHERE id=?", (conta_id,)).fetchone()
    return bool(r and r[0])


def segundo_fator(hub, conta_id: int, codigo: str, usuario: str = "") -> bool:
    """Confere o código do aplicativo (sem reuso) ou um código de recuperação (gasta)."""
    with hub._trava:
        r = hub._db.execute("SELECT totp_segredo, totp_ultimo, totp_recuperacao FROM conta WHERE id=? AND totp_ativo=1", (conta_id,)).fetchone()
        if not r:
            return False
        passo = totp_conferir(r[0], codigo, hub.relogio(), r[1])
        if passo is not None:
            hub._db.execute("UPDATE conta SET totp_ultimo=? WHERE id=?", (passo, conta_id))
            hub._db.commit()
            return True
        c = _limpo(codigo)
        lista = json.loads(r[2] or "[]")
        alvo = resumo(c) if len(c) == 10 else None
        if alvo and any(hmac.compare_digest(alvo, x) for x in lista):
            lista = [x for x in lista if not hmac.compare_digest(alvo, x)]
            hub._db.execute("UPDATE conta SET totp_recuperacao=? WHERE id=?", (json.dumps(lista), conta_id))
            hub._db.commit()
            evento_seguranca(hub, "codigo de recuperacao usado", usuario, restam=len(lista))
            return True
    return False


# ── Sessão: ociosidade, vida máxima e reautenticação ────────────────────────
def _min_env(nome: str, padrao: float) -> float:
    try:
        return max(0.0, float(os.environ.get(nome, padrao)))
    except ValueError:
        return padrao


def sessao_ociosa_s() -> float:
    """PHYSIS_SESSAO_OCIOSA_MIN (720 = 12 h): sem uso por esse tempo, a sessão cai. 0 desliga."""
    return _min_env("PHYSIS_SESSAO_OCIOSA_MIN", 720) * 60


def sessao_vida_s(padrao: float) -> float:
    """PHYSIS_SESSAO_DIAS (30): vida máxima da sessão, mesmo em uso."""
    d = _min_env("PHYSIS_SESSAO_DIAS", padrao / 86400)
    return d * 86400 if d > 0 else padrao


def reauth_janela_s() -> float:
    """PHYSIS_REAUT_MIN (10): por quanto tempo a senha digitada vale para ações sensíveis."""
    return _min_env("PHYSIS_REAUT_MIN", 10) * 60


def reauth_recente(hub, conta: dict | None) -> bool:
    return bool(conta) and hub.relogio() - float(conta.get("reauth") or 0) <= reauth_janela_s()


def reautenticar(hub, token_sessao: str, conta: dict, senha: str, codigo: str = "") -> dict:
    with hub._trava:
        r = hub._db.execute("SELECT sal, resumo FROM conta WHERE id=?", (conta["id"],)).fetchone()
        if not r or not hmac.compare_digest(hub._resumir(senha or "", r[0]), r[1]):
            evento_seguranca(hub, "reautenticacao falhou", conta["usuario"])
            return {"ok": False, "codigo": 403, "erro": "A senha não confere."}
    if totp_ligado(hub, conta["id"]) and not segundo_fator(hub, conta["id"], codigo, conta["usuario"]):
        return {"ok": False, "codigo": 403, "erro": "Digite o código do aplicativo autenticador.", "precisa_2fa": True}
    with hub._trava:
        hub._db.execute("UPDATE sessao SET reauth=? WHERE resumo=?", (hub.relogio(), resumo(token_sessao)))
        hub._db.commit()
    return {"ok": True, "valida_s": int(reauth_janela_s())}


# ── Confirmação do e-mail ────────────────────────────────────────────────────
def confirmacao_exigida() -> bool:
    """PHYSIS_CONFIRMAR_EMAIL: "1" sempre, "0" nunca; vazio = só quando há servidor de e-mail (PHYSIS_SMTP_HOST)."""
    v = os.environ.get("PHYSIS_CONFIRMAR_EMAIL", "").strip()
    if v in ("0", "1"):
        return v == "1"
    return bool(os.environ.get("PHYSIS_SMTP_HOST"))


# ── Termos e consentimento (LGPD) ────────────────────────────────────────────
_TERMOS: dict = {}


def termos_versao(caminho=None) -> str | None:
    """Versão dos Termos/Política de privacidade: PHYSIS_TERMOS_VERSAO ou o "versao" de sistema/physis-juridico.js
    (lido uma vez). None = sem versão conhecida: o consentimento não é cobrado."""
    if os.environ.get("PHYSIS_TERMOS_VERSAO"):
        return os.environ["PHYSIS_TERMOS_VERSAO"].strip()[:40]
    if caminho is None and "v" in _TERMOS:
        return _TERMOS["v"]
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent
    cands = [Path(caminho)] if caminho else [raiz / "programas" / "physis-juridico.js", raiz.parent / "sistema" / "physis-juridico.js",
                                             raiz / "web" / "physis-juridico.js"]
    v = None
    for c in cands:
        try:
            m = re.search(r'"versao"\s*:\s*"([^"]{1,40})"', c.read_text(encoding="utf-8")[:20000])
        except OSError:
            continue
        if m:
            v = m.group(1)
            break
    if caminho is None:
        _TERMOS["v"] = v
    return v


def consentimento_registrar(hub, conta_id: int, usuario: str, versao: str, aceito: bool, ip: str = "") -> dict:
    atual = termos_versao()
    if aceito and atual and versao != atual:
        return {"ok": False, "erro": f"Os termos mudaram (versão {atual}). Leia a versão nova e aceite de novo.", "versao": atual}
    with hub._trava:
        agora = hub.relogio()
        hub._db.execute("INSERT INTO consentimento(conta,versao,aceito,quando,ip_resumo) VALUES(?,?,?,?,?)",
                        (conta_id, str(versao or "")[:40], 1 if aceito else 0, agora, ip_resumo(hub, ip) if ip else ""))
        hub._db.execute("UPDATE conta SET consentimento_versao=?, consentimento_em=? WHERE id=?",
                        (str(versao or "")[:40] if aceito else "", agora, conta_id))
        hub._db.commit()
    evento_seguranca(hub, "consentimento aceito" if aceito else "consentimento retirado", usuario, ip=ip, versao=str(versao or "")[:40])
    return {"ok": True, "versao": versao if aceito else "", "pendente": not aceito}


def consentimento_pendente(conta: dict | None) -> bool:
    v = termos_versao()
    return bool(conta) and bool(v) and (conta.get("consentimento") or "") != v


def consentimento_estrito() -> bool:
    """PHYSIS_CONSENTIMENTO_ESTRITO=1: sem o aceite da versão atual, só as rotas da própria conta funcionam."""
    return os.environ.get("PHYSIS_CONSENTIMENTO_ESTRITO") == "1"


def _consentimento_do_corpo(d: dict) -> tuple[bool, str]:
    c = d.get("consentimento")
    if isinstance(c, dict) and c.get("aceito") is True and isinstance(c.get("versao"), str):
        return True, c["versao"]
    return False, ""


# ── Tokens de conta (senha, confirmação, convite): só o resumo no banco, uso único ──
def _token_criar(hub, tipo: str, conta_id, usuario: str, validade_s: float, dados: dict | None = None, por: str = "") -> tuple[str, int]:
    tk = secrets.token_urlsafe(32)
    with hub._trava:
        agora = hub.relogio()
        cur = hub._db.execute("INSERT INTO conta_token(resumo,tipo,conta,usuario,dados,criado,expira,por) VALUES(?,?,?,?,?,?,?,?)",
                              (resumo(tk), tipo, conta_id, usuario, json.dumps(dados or {}, ensure_ascii=False), agora, agora + validade_s, por))
        hub._db.commit()
    return tk, cur.lastrowid


def _token_ler(hub, tipo: str, token: str) -> dict | None:
    if not isinstance(token, str) or not 20 <= len(token) <= 100:
        return None
    r_ = resumo(token.strip())
    with hub._trava:
        r = hub._db.execute("SELECT id, conta, usuario, dados, expira, usado, revogado, resumo FROM conta_token WHERE resumo=? AND tipo=?",
                            (r_, tipo)).fetchone()
    if not r or r[5] or r[6] or r[4] < hub.relogio() or not iguais(r[7], r_):
        return None
    return {"id": r[0], "conta": r[1], "usuario": r[2], "dados": json.loads(r[3] or "{}"), "expira": r[4]}


def _token_gastar(hub, ident: int) -> bool:
    with hub._trava:
        cur = hub._db.execute("UPDATE conta_token SET usado=? WHERE id=? AND usado IS NULL AND revogado IS NULL AND expira >= ?",
                              (hub.relogio(), ident, hub.relogio()))
        hub._db.commit()
        return cur.rowcount == 1


def _enfileirar(hub, para: str, assunto: str, corpo: str, ref: str) -> None:
    with hub._trava:
        hub._db.execute("INSERT INTO email_saida(para,assunto,corpo,estado,ref,criado) VALUES(?,?,?,?,?,?)",
                        (para, assunto, corpo, "pendente", ref, hub.relogio()))
        hub._db.commit()


def _onde(base: str, caminho: str, token: str) -> str:
    """Com PHYSIS_URL_PUBLICA, o link completo (o código vai depois de #, que não é enviado ao servidor nem
    fica em registro de proxy). Sem ela, nunca usa o cabeçalho Host (pode ser forjado): manda o caminho e o código."""
    if base:
        return f"Abra este link (vale uma vez):\n{base}{caminho}#t={token}\n"
    return f"Abra a plataforma no endereço de sempre, vá em {caminho} e cole este código (vale uma vez):\n{token}\n"


REF_CONTA = "conta-"          # e-mails dos fluxos de conta: não aparecem na fila da Gestão (levam código secreto)
SENHA_TOKEN_S = 30 * 60
CONFIRMAR_TOKEN_S = 3 * 86400
CONVITE_TOKEN_S = 7 * 86400
MSG_ESQUECI = "Se este e-mail tiver conta, enviamos um link para criar uma senha nova. Ele vale 30 minutos."


def senha_esqueci(hub, usuario: str, base: str, ip: str = "") -> tuple[dict, str | None]:
    """Sempre a mesma resposta, exista ou não a conta. Devolve (resposta, ref do e-mail ou None)."""
    usuario = str(usuario or "").strip().lower()[:160]
    tk = secrets.token_urlsafe(32)              # gasta o mesmo trabalho nos dois casos
    with hub._trava:
        r = hub._db.execute("SELECT id, nome FROM conta WHERE usuario=? AND ativa=1", (usuario,)).fetchone()
        recente = r and hub._db.execute("SELECT 1 FROM conta_token WHERE conta=? AND tipo='senha' AND criado > ? AND usado IS NULL",
                                        (r[0], hub.relogio() - 60)).fetchone()
    evento_seguranca(hub, "senha esquecida pedida", usuario, ip=ip, conta_existe=bool(r))
    if not r or recente or not _parece_email(usuario):
        return {"ok": True, "mensagem": MSG_ESQUECI}, None
    with hub._trava:          # um pedido novo derruba os links anteriores
        hub._db.execute("UPDATE conta_token SET revogado=? WHERE conta=? AND tipo='senha' AND usado IS NULL", (hub.relogio(), r[0]))
        hub._db.commit()
    tk, ident = _token_criar(hub, "senha", r[0], usuario, SENHA_TOKEN_S)
    ref = f"{REF_CONTA}senha-{ident}"
    _enfileirar(hub, usuario, "Physis · senha nova", f"Olá, {r[1]}.\n\nAlguém (talvez você) pediu uma senha nova para a sua conta Physis.\n\n"
                + _onde(base, "/conta/nova-senha", tk)
                + "\nO link vale 30 minutos. Se não foi você, ignore este e-mail: a sua senha continua a mesma.\n", ref)
    return {"ok": True, "mensagem": MSG_ESQUECI}, ref


def senha_redefinir(hub, token: str, senha: str, ip: str = "") -> dict:
    t = _token_ler(hub, "senha", token)
    if not t:
        return {"ok": False, "erro": "Link vencido ou já usado. Peça outro em \"Esqueci a senha\"."}
    erro = senha_fraca(senha, t["usuario"])
    if erro:
        return {"ok": False, "erro": erro}
    if not _token_gastar(hub, t["id"]):
        return {"ok": False, "erro": "Link vencido ou já usado. Peça outro em \"Esqueci a senha\"."}
    sal = os.urandom(16)
    with hub._trava:
        agora = hub.relogio()
        hub._db.execute("UPDATE conta SET sal=?, resumo=?, confirmado=COALESCE(confirmado, ?) WHERE id=?",
                        (sal, hub._resumir(senha, sal), agora, t["conta"]))
        n = hub._db.execute("DELETE FROM sessao WHERE conta=?", (t["conta"],)).rowcount     # derruba todas as sessões
        hub._db.commit()
        getattr(hub, "_falhas", {}).pop(t["usuario"], None)
    evento_seguranca(hub, "senha redefinida por e-mail", t["usuario"], ip=ip, sessoes_encerradas=n)
    return {"ok": True, "mensagem": "Senha nova gravada. Entre com ela."}


def confirmar_enviar(hub, conta_id: int, base: str) -> str | None:
    with hub._trava:
        r = hub._db.execute("SELECT usuario, nome, confirmado FROM conta WHERE id=?", (conta_id,)).fetchone()
    if not r or r[2] or not _parece_email(r[0]):
        return None
    with hub._trava:
        hub._db.execute("UPDATE conta_token SET revogado=? WHERE conta=? AND tipo='confirmar' AND usado IS NULL", (hub.relogio(), conta_id))
        hub._db.commit()
    tk, ident = _token_criar(hub, "confirmar", conta_id, r[0], CONFIRMAR_TOKEN_S)
    ref = f"{REF_CONTA}confirmar-{ident}"
    _enfileirar(hub, r[0], "Physis · confirme o seu e-mail", f"Olá, {r[1]}.\n\nConfirme que este e-mail é seu para usar a conta Physis.\n\n"
                + _onde(base, "/conta/confirmar", tk) + "\nO link vale 3 dias.\n", ref)
    return ref


def confirmar(hub, token: str) -> dict:
    t = _token_ler(hub, "confirmar", token)
    if not t or not _token_gastar(hub, t["id"]):
        return {"ok": False, "erro": "Link vencido ou já usado. Entre na plataforma e peça outro."}
    with hub._trava:
        hub._db.execute("UPDATE conta SET confirmado=? WHERE id=?", (hub.relogio(), t["conta"]))
        hub._db.commit()
    evento_seguranca(hub, "email confirmado", t["usuario"])
    return {"ok": True, "mensagem": "E-mail confirmado."}


def convite_criar(hub, email: str, papel: str, pessoa: str, nome: str, por: str, base: str) -> dict:
    email = str(email or "").strip().lower()
    papel_n = normalizar_papel(papel or EQUIPE)
    if not _parece_email(email) or len(email) > 160:
        return {"ok": False, "erro": "Informe um e-mail válido."}
    if not papel_n:
        return {"ok": False, "erro": "Papel inválido."}
    dominio = (os.environ.get("PHYSIS_DOMINIO_EMAIL") or "").strip().lower().lstrip("@")
    if dominio and papel_n != CLIENTE and not email.endswith("@" + dominio):
        return {"ok": False, "erro": f"Use um e-mail @{dominio}."}
    with hub._trava:
        if hub._db.execute("SELECT 1 FROM conta WHERE usuario=?", (email,)).fetchone():
            return {"ok": False, "erro": "Já existe uma conta com esse e-mail."}
        hub._db.execute("UPDATE conta_token SET revogado=? WHERE tipo='convite' AND usuario=? AND usado IS NULL", (hub.relogio(), email))
        hub._db.commit()
    dados = {"papel": papel_n, "pessoa": str(pessoa or "")[:40], "nome": str(nome or "")[:120]}
    tk, ident = _token_criar(hub, "convite", None, email, CONVITE_TOKEN_S, dados, por)
    ref = f"{REF_CONTA}convite-{ident}"
    rotulo = {DIRECAO: "direção", EQUIPE: "equipe", CLIENTE: "cliente"}[papel_n]
    _enfileirar(hub, email, "Physis · convite para a plataforma",
                f"Olá{', ' + dados['nome'] if dados['nome'] else ''}.\n\nVocê foi convidada(o) para a plataforma Physis ({hub.org}) como {rotulo}.\n\n"
                + _onde(base, "/conta/convite", tk) + "\nNo link, você escolhe o seu nome e a sua senha. O convite vale 7 dias.\n", ref)
    evento_seguranca(hub, "convite criado", email, papel=papel_n, por=pseudonimo(hub, por))
    with hub._trava:
        expira = hub._db.execute("SELECT expira FROM conta_token WHERE id=?", (ident,)).fetchone()[0]
    return {"ok": True, "id": ident, "email": email, "papel": papel_n, "expira": expira, "ref": ref}


def convite_listar(hub) -> list[dict]:
    with hub._trava:
        linhas = hub._db.execute("SELECT id, usuario, dados, criado, expira, usado, revogado, por FROM conta_token WHERE tipo='convite' "
                                 "ORDER BY id DESC LIMIT 200").fetchall()
    agora = hub.relogio()
    fora = []
    for i, u, d, c, e, us, rv, p in linhas:
        dd = json.loads(d or "{}")
        estado = "aceito" if us else "revogado" if rv else "vencido" if e < agora else "pendente"
        fora.append({"id": i, "email": u, "papel": dd.get("papel"), "pessoa": dd.get("pessoa"), "nome": dd.get("nome"),
                     "criado": c, "expira": e, "estado": estado, "por": p})
    return fora


def convite_revogar(hub, ident, por: str) -> bool:
    try:
        ident = int(ident)
    except (TypeError, ValueError):
        return False
    with hub._trava:
        cur = hub._db.execute("UPDATE conta_token SET revogado=? WHERE id=? AND tipo='convite' AND usado IS NULL AND revogado IS NULL",
                              (hub.relogio(), ident))
        hub._db.commit()
    if cur.rowcount:
        evento_seguranca(hub, "convite revogado", "", id=ident, por=pseudonimo(hub, por))
    return cur.rowcount > 0


def convite_ver(hub, token: str) -> dict:
    t = _token_ler(hub, "convite", token)
    if not t:
        return {"ok": False, "erro": "Convite vencido, revogado ou já usado. Peça outro à direção."}
    return {"ok": True, "email": t["usuario"], "papel": t["dados"].get("papel"), "nome": t["dados"].get("nome", ""),
            "org": hub.org, "expira": t["expira"], "termos_versao": termos_versao()}


def convite_aceitar(hub, token: str, nome: str, senha: str, d: dict, ip: str = "") -> dict:
    """Cria a conta (já confirmada: o link chegou no e-mail) com o papel do convite. Exige o aceite dos termos
    quando há versão conhecida. Devolve {"ok", "usuario"}; quem chama faz o login."""
    t = _token_ler(hub, "convite", token)
    if not t:
        return {"ok": False, "erro": "Convite vencido, revogado ou já usado. Peça outro à direção."}
    nome = re.sub(r"[\x00-\x1f]", "", str(nome or t["dados"].get("nome") or "")).strip()[:120]
    if not nome:
        return {"ok": False, "erro": "Informe o seu nome."}
    erro = senha_fraca(senha, t["usuario"])
    if erro:
        return {"ok": False, "erro": erro}
    aceito, versao = _consentimento_do_corpo(d)
    atual = termos_versao()
    if atual and (not aceito or versao != atual):
        return {"ok": False, "erro": "Para criar a conta, leia e aceite os Termos de uso e a Política de privacidade.",
                "consentimento": True, "versao": atual}
    if not _token_gastar(hub, t["id"]):
        return {"ok": False, "erro": "Convite vencido, revogado ou já usado. Peça outro à direção."}
    sal = os.urandom(16)
    with hub._trava:
        try:
            cur = hub._db.execute("INSERT INTO conta(nome,usuario,papel,sal,resumo,criado,pessoa,confirmado) VALUES(?,?,?,?,?,?,?,?)",
                                  (nome, t["usuario"], t["dados"].get("papel") or EQUIPE, sal, hub._resumir(senha, sal), hub.relogio(),
                                   t["dados"].get("pessoa") or "", hub.relogio()))
        except Exception:
            return {"ok": False, "erro": "Já existe uma conta com esse e-mail."}
        conta_id = cur.lastrowid
        hub.registrar("conta", t["usuario"], {"o_que": "conta criada por convite", "papel": t["dados"].get("papel")})
        hub._db.commit()
    if atual:
        consentimento_registrar(hub, conta_id, t["usuario"], versao, True, ip)
    evento_seguranca(hub, "convite aceito", t["usuario"], ip=ip)
    return {"ok": True, "usuario": t["usuario"]}


# ── CSRF: Origin/Referer + token no cabeçalho X-Physis-CSRF ─────────────────
def csrf_de(hub, token_sessao: str | None) -> str | None:
    """Token CSRF da sessão: HMAC do token da sessão com o segredo do servidor (não precisa ser guardado)."""
    return _hmac(hub, "csrf|" + token_sessao)[:40] if token_sessao else None


def csrf_estrito() -> bool:
    """PHYSIS_CSRF_ESTRITO=1: com sessão, todo POST/PUT/DELETE precisa do cabeçalho X-Physis-CSRF."""
    return os.environ.get("PHYSIS_CSRF_ESTRITO") == "1"


def origem_confere(cabecalhos, url_publica: str = "") -> bool | None:
    """True: Origin (ou Referer) é o próprio servidor; False: é outro site (ou "null"); None: sem Origin nem Referer
    (programa, não navegador). Próprio servidor = o Host do pedido, PHYSIS_URL_PUBLICA ou PHYSIS_ORIGENS."""
    from urllib.parse import urlparse
    o = (cabecalhos.get("Origin") or "").strip()
    if not o:
        ref = (cabecalhos.get("Referer") or "").strip()
        if not ref:
            return None
        o = ref
    if o.lower() == "null":
        return False
    alvo = urlparse(o).netloc.lower()
    if not alvo:
        return False
    validos = {(cabecalhos.get("Host") or "").strip().lower()}
    for extra in [url_publica] + (os.environ.get("PHYSIS_ORIGENS") or "").split(","):
        n = urlparse(extra.strip()).netloc.lower()
        if n:
            validos.add(n)
    validos.discard("")
    return alvo in validos


# ── JSON e campos: tamanho, profundidade e tipo ──────────────────────────────
class JsonInvalido(ValueError):
    pass


def _rejeitar_constante(c):
    raise JsonInvalido(f"valor não permitido: {c}")


def carregar_json(texto, max_profundidade: int = 20, max_itens: int = 20000):
    """json.loads mais rígido: sem NaN/Infinity, números gigantes, profundidade ou quantidade de itens absurdas.
    Erro = ValueError (as rotas já respondem 400)."""
    if isinstance(texto, (bytes, bytearray)):
        texto = texto.decode("utf-8")
    if texto is None:
        texto = "{}"
    d = json.loads(texto, parse_constant=_rejeitar_constante,
                   parse_int=lambda s: int(s) if len(s) <= 30 else _rejeitar_constante("número grande demais"))
    pilha, n = [(d, 0)], 0
    while pilha:
        x, prof = pilha.pop()
        n += 1
        if prof > max_profundidade or n > max_itens:
            raise JsonInvalido("estrutura grande ou profunda demais")
        if isinstance(x, dict):
            pilha.extend((v, prof + 1) for v in x.values())
        elif isinstance(x, list):
            pilha.extend((v, prof + 1) for v in x)
    return d


def validar(d, esquema: dict, estrito: bool = True) -> str | None:
    """esquema = {campo: (tipo, máximo, obrigatório)}; tipo str (máximo = letras), bool, int/float (máximo = valor),
    dict/list (máximo = itens). Estrito (rotas novas): campos fora do esquema são recusados; nas rotas antigas
    são ignorados, para as telas atuais seguirem funcionando. Devolve a mensagem de erro ou None."""
    if not isinstance(d, dict):
        return "json invalido"
    if len(d) > 100:
        return "campos demais"
    for k in d:
        if estrito and k not in esquema:
            return f"campo desconhecido: {str(k)[:40]}"
    for k, (tipo, maximo, obrig) in esquema.items():
        if k not in d or d[k] is None:
            if obrig:
                return f"falta o campo {k}"
            continue
        v = d[k]
        tipos = tipo if isinstance(tipo, tuple) else (tipo,)
        if bool in tipos and isinstance(v, bool):
            continue
        if isinstance(v, bool) or not isinstance(v, tipos):
            return f"campo {k} com tipo errado"
        if isinstance(v, str) and maximo and len(v) > maximo:
            return f"campo {k} longo demais"
        if isinstance(v, (int, float)) and maximo is not None and abs(v) > maximo:
            return f"campo {k} fora do limite"
        if isinstance(v, (dict, list)) and maximo and len(v) > maximo:
            return f"campo {k} grande demais"
    return None


S = str
ESQUEMAS = {
    "entrar": {"usuario": (S, 160, True), "senha": (S, SENHA_MAX, True), "codigo": (S, 20, False), "nome": (S, 120, False),
               "consentimento": (dict, 4, False)},
    "criar": {"usuario": (S, 160, True), "senha": (S, SENHA_MAX, True), "nome": (S, 120, False), "codigo": (S, 20, False),
              "consentimento": (dict, 4, False)},
    "contas": {"nome": (S, 120, True), "usuario": (S, 160, True), "senha": (S, SENHA_MAX, True), "pessoa": (S, 40, False),
               "papel": (S, 20, False)},
    "conta_alterar": {"senha": (S, SENHA_MAX, False), "ativa": (bool, None, False), "papel": (S, 20, False), "pessoa": (S, 40, False)},
    "senha": {"atual": (S, SENHA_MAX, True), "nova": (S, SENHA_MAX, True)},
    "apagar": {"senha": (S, SENHA_MAX, True), "codigo": (S, 20, False)},
    "reautenticar": {"senha": (S, SENHA_MAX, True), "codigo": (S, 20, False)},
    "esqueci": {"usuario": (S, 160, True)},
    "nova_senha": {"token": (S, 100, True), "senha": (S, SENHA_MAX, True)},
    "token": {"token": (S, 100, True)},
    "convite": {"email": (S, 160, True), "papel": (S, 20, False), "pessoa": (S, 40, False), "nome": (S, 120, False)},
    "convite_aceitar": {"token": (S, 100, True), "nome": (S, 120, False), "senha": (S, SENHA_MAX, True), "consentimento": (dict, 4, False)},
    "consentimento": {"versao": (S, 40, False), "aceito": (bool, None, True)},
    "codigo": {"codigo": (S, 20, True)},
    "suporte": {"assunto": (S, 140, True), "mensagem": (S, 4000, True), "contato": (S, 160, False), "canal": (S, 20, False)},
    "chave": {"no": ((int, S), 9999, False), "rotulo": (S, 80, False)},
    "vazio": {},
}


# ── Arquivos enviados: tipo pelo conteúdo, nada executável ──────────────────
_EXECUTAVEIS = (b"MZ", b"\x7fELF", b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe",
                b"\xca\xfe\xba\xbe", b"#!", b"\x00asm")
_ASSINATURAS = {".pdf": (b"%PDF-",), ".xlsx": (b"PK\x03\x04",), ".xlsm": (b"PK\x03\x04",), ".docx": (b"PK\x03\x04",),
                ".xls": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",), ".doc": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",)}
_EXT_PERIGOSAS = (".exe", ".dll", ".com", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".jse", ".wsf", ".scr", ".msi", ".jar",
                  ".sh", ".py", ".pl", ".app", ".apk", ".lnk", ".hta", ".html", ".htm", ".svg", ".xhtml")


def eh_executavel(dados: bytes) -> bool:
    return any(dados.startswith(a) for a in _EXECUTAVEIS)


def arquivo_confere(nome: str, dados: bytes) -> str | None:
    """Para os anexos públicos (Excel, PDF, Word, CSV): o conteúdo precisa bater com a extensão."""
    ext = os.path.splitext((nome or "").lower())[1]
    if eh_executavel(dados):
        return "arquivo executável não é aceito"
    if ext == ".csv":
        if b"\x00" in dados[:65536]:
            return "o CSV não parece ser texto"
        return None
    assin = _ASSINATURAS.get(ext)
    if assin and not any(dados.startswith(a) for a in assin):
        return "o conteúdo do arquivo não confere com a extensão"
    return None


def tipo_seguro(tipo: str, nome: str = "") -> str:
    """Tipo guardado para os arquivos da Gestão: nada que o navegador execute (HTML, SVG, JS, XML)."""
    t = (tipo or "").split(";")[0].strip().lower()
    if not re.fullmatch(r"[\w.+-]+/[\w.+-]+", t) or any(x in t for x in ("html", "svg", "javascript", "ecmascript", "xml")) \
            or (nome or "").lower().endswith(_EXT_PERIGOSAS):
        return "application/octet-stream"
    return t


# ── security.txt (RFC 9116) ──────────────────────────────────────────────────
def security_txt(contato: str, url_publica: str, agora: float) -> str:
    from datetime import datetime, timezone
    expira = datetime.fromtimestamp(agora + 365 * 86400, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    linhas = []
    for c in [x.strip() for x in (contato or "").split(",") if x.strip()]:
        linhas.append("Contact: " + (c if re.match(r"^(mailto:|https://|tel:)", c) else "mailto:" + c))
    linhas += [f"Expires: {expira}", "Preferred-Languages: pt, en"]
    if url_publica:
        linhas.append(f"Canonical: {url_publica}/.well-known/security.txt")
    return "\n".join(linhas) + "\n"
