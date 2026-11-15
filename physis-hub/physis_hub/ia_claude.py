"""IA Claude (Anthropic) para os robôs, com a conta da Physis. Só biblioteca padrão (urllib).

Ordem de quem responde (robos.ia_do_ambiente): Claude, se configurado → servidor de IA local (Fase 2) → respostas
prontas por regras. Se o Claude falhar, estourar o tempo ou bater o teto do mês, o robô segue para o próximo.

Configuração (só no servidor; nunca no código, no log ou no navegador):
  PHYSIS_CLAUDE_CHAVE_ARQUIVO  caminho de um arquivo com a chave (preferido: segredo do Docker / arquivo protegido)
  PHYSIS_CLAUDE_CHAVE          a chave direto na variável (alternativa)
  ANTHROPIC_API_KEY            nome padrão da Anthropic (última alternativa)
  PHYSIS_CLAUDE_MODELO         padrão claude-opus-5-5
  PHYSIS_CLAUDE_ESFORCO        low | medium | high (padrão low: respostas curtas, menos tokens de raciocínio)
  PHYSIS_CLAUDE_MAX_TOKENS     teto de tokens de saída por chamada (padrão 8000; inclui o raciocínio)
  PHYSIS_CLAUDE_TEMPO          tempo máximo por chamada em segundos (padrão 60)
  PHYSIS_CLAUDE_TETO_USD       teto de gasto por mês em dólares (padrão 25; 0 desliga o Claude)
  PHYSIS_CLAUDE_CONSUMO        arquivo do contador do mês (padrão dados/ia_claude_consumo.json)
  PHYSIS_CLAUDE_RESERVA=0      desliga a reserva da Anthropic ("fallbacks": outro modelo responde se o 1º recusar)

Dados pessoais (LGPD): antes de sair, e-mail, CPF, CNPJ, telefone, CEP, coordenadas, links e nomes informados são
trocados por [e-mail], [CPF]... O contador guarda, por chamada, só metadados: robô, modelo, tokens, custo e quantos
dados de cada tipo foram tirados — nunca o texto. Toda resposta do Claude volta marcada "gerado por IA" e exige
revisão humana (preço de proposta e encaixe de edital são só sugestão). Ver docs/IA_CLAUDE.md.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

log = logging.getLogger("physis.ia_claude")
RAIZ = Path(__file__).resolve().parent.parent

URL_API = "https://api.anthropic.com/v1/messages"
VERSAO_API = "2026-10-21"                       # cabeçalho anthropic-version (skill claude-api, 2026-11)
MODELO_PADRAO = "claude-opus-5-5"
BETA_RESERVA = "server-side-fallback-2026-07-01"
# modelos que aceitam a reserva automática ("fallbacks": "default")
MODELOS_COM_RESERVA = {"claude-fable-5-2", "claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}

# Preço em US$ por 1 milhão de tokens (entrada, saída) — tabela da skill claude-api, "cached: 2026-11-03". [CONFERIR]
PRECOS_DATA = "2026-11-03"
PRECOS_USD_POR_MILHAO = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),       # até 100 mil tokens de entrada por pedido
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-fable-5-2": (8.00, 40.00),
}
# modelo desconhecido (ex.: a reserva respondeu com outro): conta pelo mais caro da tabela, para não subestimar
PRECO_DESCONHECIDO = max(PRECOS_USD_POR_MILHAO.values())

AVISO_IA = ("Texto gerado com IA (Claude). É sugestão: precisa de revisão humana antes de ir a um cliente "
            "(preços de proposta e encaixe de edital não são decisão).")
AVISO_SISTEMA = ("Os dados pessoais foram trocados por marcadores como [e-mail], [CPF], [pessoa]; não tente recuperá-los. "
                 "Não invente números, preços, prazos nem fontes. Sua resposta será revisada por uma pessoa da Physis.")


def custo_usd(modelo: str, entrada: int, saida: int, cache_escrita: int = 0, cache_leitura: int = 0) -> float:
    """Custo em US$. Cache: escrita ~1,25× e leitura ~0,1× o preço de entrada (skill claude-api)."""
    p_in, p_out = PRECOS_USD_POR_MILHAO.get(modelo, PRECO_DESCONHECIDO)
    return (entrada * p_in + cache_escrita * p_in * 1.25 + cache_leitura * p_in * 0.1 + saida * p_out) / 1_000_000


def _destino_permitido(url: str) -> bool:
    """A chave só vai para a Anthropic (https) ou para o próprio computador (testes)."""
    try:
        u = urllib.parse.urlparse(url)
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    if u.scheme == "https" and host == "api.anthropic.com":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def _post(url: str, corpo: dict, cabecalhos: dict, tempo: float) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=json.dumps(corpo).encode("utf-8"), method="POST", headers=cabecalhos)
    try:
        with urllib.request.urlopen(req, timeout=tempo) as r:
            return r.status, json.loads(r.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        try:
            dados = json.loads(exc.read().decode("utf-8", errors="replace"))
        except (ValueError, OSError):
            dados = {}
        return exc.code, dados if isinstance(dados, dict) else {}


def ler_chave() -> str:
    arq = (os.environ.get("PHYSIS_CLAUDE_CHAVE_ARQUIVO") or "").strip()
    if arq:
        try:
            return Path(arq).read_text(encoding="utf-8").strip()
        except OSError:
            log.warning("ia_claude: não consegui ler PHYSIS_CLAUDE_CHAVE_ARQUIVO")
            return ""
    return (os.environ.get("PHYSIS_CLAUDE_CHAVE") or os.environ.get("ANTHROPIC_API_KEY") or "").strip()


class Consumo:
    """Contador do mês em arquivo JSON (gasto, chamadas, tokens e os últimos envios, só metadados)."""

    def __init__(self, caminho: str | Path | None, relogio=time.time):
        self.caminho = Path(caminho) if caminho else None
        self.relogio = relogio
        self.trava = threading.Lock()
        self._memoria: dict = {}

    def mes(self) -> str:
        return datetime.fromtimestamp(self.relogio()).strftime("%Y-%m")

    def ler(self) -> dict:
        d = self._memoria
        if self.caminho and self.caminho.exists():
            try:
                d = json.loads(self.caminho.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                d = {}
        if d.get("mes") != self.mes():
            d = {"mes": self.mes(), "gasto_usd": 0.0, "chamadas": 0, "falhas": 0, "bloqueadas_teto": 0,
                 "tokens_entrada": 0, "tokens_saida": 0, "envios": []}
        return d

    def gravar(self, d: dict) -> None:
        self._memoria = d
        if not self.caminho:
            return
        try:
            self.caminho.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.caminho.with_suffix(".tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.caminho)
        except OSError as exc:
            log.warning("ia_claude: não gravei o contador (%s)", type(exc).__name__)

    def somar(self, **campos) -> dict:
        with self.trava:
            d = self.ler()
            envio = campos.pop("envio", None)
            for k, v in campos.items():
                d[k] = round(d.get(k, 0) + v, 6) if isinstance(v, float) else d.get(k, 0) + v
            if envio:
                d["envios"] = (d.get("envios") or [])[-199:] + [envio]
            self.gravar(d)
            return d


class IAClaude:
    tipo = "claude"

    def __init__(self, chave: str | None = None, modelo: str | None = None, tempo: float | None = None,
                 teto_usd: float | None = None, consumo: str | Path | None = None, url: str | None = None,
                 enviar=None, relogio=time.time, max_tokens: int | None = None, esforco: str | None = None,
                 reserva: bool | None = None):
        env = os.environ.get
        self.__chave = (chave if chave is not None else ler_chave()).strip()
        self.modelo = (modelo or env("PHYSIS_CLAUDE_MODELO") or MODELO_PADRAO).strip()
        self.tempo = float(tempo or env("PHYSIS_CLAUDE_TEMPO") or 60)
        self.teto_usd = float(teto_usd if teto_usd is not None else (env("PHYSIS_CLAUDE_TETO_USD") or 25))
        self.max_tokens = int(max_tokens or env("PHYSIS_CLAUDE_MAX_TOKENS") or 8000)
        self.esforco = (esforco if esforco is not None else env("PHYSIS_CLAUDE_ESFORCO", "low")).strip()
        self.reserva = (env("PHYSIS_CLAUDE_RESERVA", "1") != "0") if reserva is None else reserva
        self.url = url or URL_API
        self.enviar = enviar or _post
        caminho = consumo if consumo is not None else (env("PHYSIS_CLAUDE_CONSUMO") or RAIZ / "dados" / "ia_claude_consumo.json")
        self.consumo = Consumo(caminho or None, relogio)
        self.erro = ""
        self.ultimo: dict = {}
        if self.__chave and not _destino_permitido(self.url):
            self.erro = "endereço da API não é api.anthropic.com: Claude desligado"
            self.__chave = ""

    def __repr__(self) -> str:                      # a chave nunca aparece
        return f"IAClaude(modelo={self.modelo!r}, configurada={bool(self.__chave)}, teto_usd={self.teto_usd})"

    @property
    def ativa(self) -> bool:
        return bool(self.__chave) and self.teto_usd > 0

    def estado(self) -> dict:
        """Para a tela de estado / manutenção: nunca inclui a chave."""
        d = self.consumo.ler()
        return {"configurada": bool(self.__chave), "modelo": self.modelo, "teto_usd": self.teto_usd,
                "gasto_usd": round(d.get("gasto_usd", 0.0), 4), "mes": d.get("mes"), "chamadas": d.get("chamadas", 0),
                "falhas": d.get("falhas", 0), "bloqueadas_teto": d.get("bloqueadas_teto", 0),
                "precos_de": PRECOS_DATA}

    def _pior_caso(self, texto: str) -> float:
        # ~3 caracteres por token (estimativa conservadora para português) + todos os tokens de saída
        return custo_usd(self.modelo, len(texto) // 3 + 1, self.max_tokens)

    def gerar(self, sistema: str, pedido: str, robo: str = "", nomes=()) -> str | None:
        """Texto do Claude ou None (sem chave, teto, erro, recusa). O pedido sai sem dados pessoais."""
        self.ultimo = {}
        if not self.ativa:
            return None
        from .robos import anonimizar_relatorio      # aqui dentro para não haver importação circular
        sistema, rem_s = anonimizar_relatorio(sistema, nomes)
        pedido, rem_p = anonimizar_relatorio(pedido, nomes)
        removidos = {k: rem_s.get(k, 0) + rem_p.get(k, 0) for k in set(rem_s) | set(rem_p)}
        gasto = self.consumo.ler().get("gasto_usd", 0.0)
        if gasto + self._pior_caso(sistema + pedido) > self.teto_usd:
            self.erro = f"teto mensal atingido (US$ {gasto:.2f} de {self.teto_usd:.2f})"
            self.consumo.somar(bloqueadas_teto=1)
            log.warning("ia_claude robo=%s bloqueada pelo teto gasto=%.4f teto=%.2f", robo, gasto, self.teto_usd)
            return None
        corpo = {"model": self.modelo, "max_tokens": self.max_tokens,
                 "system": f"{sistema}\n\n{AVISO_SISTEMA}",
                 "messages": [{"role": "user", "content": pedido}]}
        if self.esforco:
            corpo["output_config"] = {"effort": self.esforco}
        cab = {"Content-Type": "application/json", "x-api-key": self.__chave, "anthropic-version": VERSAO_API,
               "User-Agent": "PhysisHub/1.0"}
        if self.reserva and self.modelo in MODELOS_COM_RESERVA:
            corpo["fallbacks"] = "default"
            cab["anthropic-beta"] = BETA_RESERVA
        inicio = time.monotonic()
        texto, status, modelo_resp, uso, motivo = None, 0, self.modelo, {}, ""
        try:
            status, r = self.enviar(self.url, corpo, cab, self.tempo)
            if status == 200 and isinstance(r, dict):
                modelo_resp = str(r.get("model") or self.modelo)
                uso = r.get("usage") or {}
                motivo = str(r.get("stop_reason") or "")
                if motivo == "refusal":
                    self.erro = "o Claude recusou o pedido"
                else:
                    texto = "".join(b.get("text", "") for b in (r.get("content") or [])
                                    if isinstance(b, dict) and b.get("type") == "text").strip() or None
                    if not texto:
                        self.erro = f"resposta sem texto ({motivo or 'vazia'})"
            else:
                tipo_erro = ((r or {}).get("error") or {}).get("type", "") if isinstance(r, dict) else ""
                self.erro = f"API respondeu {status}" + (f" ({tipo_erro})" if tipo_erro else "")
        except (urllib.error.URLError, OSError, ValueError, TypeError, AttributeError) as exc:
            self.erro = f"falha de rede: {type(exc).__name__}"
        ms = int((time.monotonic() - inicio) * 1000)
        t_in, t_out = int(uso.get("input_tokens") or 0), int(uso.get("output_tokens") or 0)
        c_w, c_r = int(uso.get("cache_creation_input_tokens") or 0), int(uso.get("cache_read_input_tokens") or 0)
        custo = custo_usd(modelo_resp, t_in, t_out, c_w, c_r)
        envio = {"quando": datetime.fromtimestamp(self.consumo.relogio()).isoformat(timespec="seconds"), "robo": robo,
                 "modelo": modelo_resp, "ok": bool(texto), "status": status, "ms": ms, "tokens_entrada": t_in + c_w + c_r,
                 "tokens_saida": t_out, "custo_usd": round(custo, 6), "bytes_enviados": len((sistema + pedido).encode()),
                 "dados_pessoais_removidos": removidos}
        self.consumo.somar(gasto_usd=custo, chamadas=1, falhas=0 if texto else 1, tokens_entrada=t_in + c_w + c_r,
                           tokens_saida=t_out, envio=envio)
        self.ultimo = {"tipo": "claude", "modelo": modelo_resp, "custo_usd": round(custo, 6),
                       "dados_pessoais_removidos": removidos}
        log.info("ia_claude robo=%s modelo=%s status=%s ms=%d entrada=%d saida=%d custo=%.5f ok=%s removidos=%s",
                 robo, modelo_resp, status, ms, t_in, t_out, custo, bool(texto), removidos)
        return texto
