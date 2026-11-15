"""Pegada de carbono do servidor: a energia das maquinas que rodam o proprio Sistema Physis.

Explicacao simples: o sistema digital tambem gasta luz. Este modulo mede (ou estima, quando nao da para medir)
quanta energia as maquinas do sistema usam, guarda o total de cada hora e transforma em gas de efeito estufa:
- energia (escopo 2, ou escopo 3 cat. 1 quando a hospedagem e comprada de outra empresa), com o mesmo fator
  da rede que o modulo Carbono usa;
- fabricacao das maquinas (escopo 3, categoria 2, bens de capital), dividida pelos anos de uso.

Como cada maquina e medida (a primeira que funcionar vale):
1. medidor de energia ja ligado ao hub (tomada inteligente ou no V6/MQTT): "medidor" = medido;
2. contador RAPL do processador (Linux, /sys/class/powercap/intel-rapl*/energy_uj) + o resto da placa
   estimado pela classe: "rapl" = parcialmente medido;
3. potencia nominal da classe (parada e em carga), interpolada pela carga do processador (os.getloadavg):
   "nominal" = estimado;
   e, nos casos 2 e 3, as placas de video medidas pelo nvidia-smi quando existem ("+gpu").
Outras maquinas (servidor de IA, host do Docker) entram pela configuracao, cada uma com o seu metodo.

Dupla contagem: maquina dentro do lugar cujas contas de luz ja estao no inventario (ex.: Casa Physis) aparece
como "parte do escopo 2 ja contado" (so informacao); hospedada em outro lugar (datacenter, servidor da Physis
para clientes) entra como fonte propria. Regra em carbono.servidor_contagem.

Configuracao (instancia.json, chave "pegada_servidor"; ou PHYSIS_PEGADA com o mesmo JSON; PHYSIS_PEGADA=0 desliga):
  {"classe": "rpi5", "nome": "Hub da Casa Physis", "local": "no_lugar", "controle": "proprio", "pue": 1.0,
   "gpus": null, "ano_compra": 2025, "intervalo_min": 5, "fator_rede": null, "contagem": "auto",
   "medidor": {"ativo": "lugar01/no7", "grandeza": "energia_kwh", "tipo": "energia_kwh"},
   "hosts": [{"id": "ia", "nome": "Servidor de IA", "classe": "servidor_gpu", "metodo": "nominal", "uso": 0.2,
              "local": "no_lugar", "gpus": 1}],
   "clientes": [{"id": "cliente-a", "nome": "Cliente A", "peso": 2}]}
So biblioteca padrao. Rotas e linha de fundo: docs/PEGADA_SERVIDOR.md.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from . import carbono

ESQUEMA = """
CREATE TABLE IF NOT EXISTS servidor_energia (
  hora INTEGER NOT NULL, equipamento TEXT NOT NULL, kwh REAL NOT NULL, segundos REAL NOT NULL,
  amostras INTEGER NOT NULL, metodo TEXT NOT NULL, fonte TEXT NOT NULL, w_ultimo REAL NOT NULL DEFAULT 0,
  PRIMARY KEY (hora, equipamento));
"""

H_MES = 730.0                 # horas num mes medio (8760 / 12)
LOCAIS = ("no_lugar", "fora")
CONTROLES = ("proprio", "servico")

# Mesmos valores do bloco "servidor" de sistema/physis-fatores-emissao.json (teste confere); usados se a base faltar.
PADRAO = {
    "classes": {
        "rpi4": {"nome": "Raspberry Pi 4 (com fonte e cartão)", "w_ocioso": 3.0, "w_carga": 7.0, "w_resto": 1.5, "kgco2e_fabricacao": 15, "vida_anos": 5},
        "rpi5": {"nome": "Raspberry Pi 5 (com fonte, ventoinha e SSD)", "w_ocioso": 3.5, "w_carga": 10.0, "w_resto": 2.0, "kgco2e_fabricacao": 20, "vida_anos": 5},
        "mini_pc": {"nome": "Mini PC (tipo NUC)", "w_ocioso": 8, "w_carga": 45, "w_resto": 4, "kgco2e_fabricacao": 120, "vida_anos": 5},
        "workstation": {"nome": "Workstation ou desktop (placa ATX, sem placa de vídeo)", "w_ocioso": 40, "w_carga": 200, "w_resto": 25, "kgco2e_fabricacao": 350, "vida_anos": 5},
        "servidor_x86": {"nome": "Servidor x86 de rack ou torre (2 processadores)", "w_ocioso": 110, "w_carga": 330, "w_resto": 60, "kgco2e_fabricacao": 1300, "vida_anos": 5},
        "servidor_gpu": {"nome": "Servidor com GPU para IA (1 placa incluída na potência)", "w_ocioso": 150, "w_carga": 650, "w_resto": 70, "gpu_w_ocioso": 30, "gpu_w_carga": 300, "kgco2e_fabricacao": 1300, "vida_anos": 4},
    },
    "gpu_placa": {"kgco2e_fabricacao": 150, "vida_anos": 4},
    "pue": {"no_lugar": 1.0, "datacenter_padrao": 1.5},
    "uso_padrao": 0.3,
    "amostra_min": 5,
}
FATOR_REDE_RESERVA = 0.0289    # mesmo valor do nucleo physis/1, so se a base de fatores nao estiver no pacote

DICAS = (
    "Desligue ou suspenda a placa de vídeo quando nenhum modelo de IA estiver rodando: parada, ela ainda gasta de 20 a 50 W.",
    "Agende treinos e tarefas pesadas de IA para o meio do dia, quando há sol: a energia solar própria cobre o pico.",
    "Prefira máquinas pequenas e eficientes (Raspberry Pi ou mini PC) para o hub; servidor grande só onde precisa.",
    "Junte serviços na mesma máquina (contêineres) em vez de várias máquinas meio paradas.",
    "Use a máquina até o fim da vida útil e conserte antes de trocar: a fabricação pesa mais que a luz em máquinas pequenas.",
    "Em datacenter, peça o PUE no contrato e prefira quem usa energia renovável certificada.",
)


# ─────────────── leitores (trocaveis nos testes) ───────────────
def ler_rapl(raiz: str | Path = "/sys/class/powercap") -> dict | None:
    """{zona: (energia_uj, faixa_max_uj)} das zonas de pacote (intel-rapl:N, sem as subzonas, para nao contar
    duas vezes). None se nao existir ou se nao der para ler (desde o kernel 5.10 so o root le energy_uj)."""
    raiz = Path(raiz)
    try:
        zonas = sorted(p for p in raiz.iterdir() if re.fullmatch(r"intel-rapl:\d+", p.name))
    except OSError:
        return None
    out = {}
    for z in zonas:
        try:
            e = int((z / "energy_uj").read_text().strip())
        except (OSError, ValueError):
            return None
        try:
            mx = int((z / "max_energy_range_uj").read_text().strip())
        except (OSError, ValueError):
            mx = 0
        out[z.name] = (e, mx)
    return out or None


def ler_carga() -> float | None:
    """Carga do processador de 0 a 1: media de 1 minuto ÷ numero de nucleos. None se o sistema nao informar."""
    try:
        l1 = os.getloadavg()[0]
    except (AttributeError, OSError):
        try:
            l1 = float(Path("/proc/loadavg").read_text().split()[0])
        except (OSError, ValueError, IndexError):
            return None
    return max(0.0, min(1.0, l1 / max(1, os.cpu_count() or 1)))


def ler_gpus(executar=subprocess.run) -> list | None:
    """Potencia de cada placa NVIDIA em W (nvidia-smi). None se nao houver nvidia-smi ou ele falhar."""
    if executar is subprocess.run and not shutil.which("nvidia-smi"):
        return None
    try:
        r = executar(["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"],
                     capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if getattr(r, "returncode", 1) != 0:
        return None
    ws = []
    for linha in str(r.stdout or "").splitlines():
        try:
            ws.append(float(linha.strip()))
        except ValueError:
            continue           # "[N/A]" ou linha vazia
    return ws or None


def ler_modelo(caminho: str = "/proc/device-tree/model") -> str:
    try:
        return Path(caminho).read_text(errors="ignore").replace("\x00", "").strip()
    except OSError:
        return ""


def classe_automatica(modelo: str, tem_gpu: bool) -> str:
    if "Raspberry Pi 5" in modelo:
        return "rpi5"
    if "Raspberry Pi 4" in modelo:
        return "rpi4"
    return "servidor_gpu" if tem_gpu else "mini_pc"


def ler_medidor_hub(hub, ativo: str, grandeza: str):
    """(valor, ts) da ultima medicao do no medidor guardada pelo hub; None se nao houver."""
    with hub._trava:
        r = hub._db.execute(
            "SELECT m.valor, CASE WHEN m.ts > 0 THEN m.ts ELSE l.recebido END FROM medicao m "
            "JOIN leitura l ON l.seq = m.leitura WHERE m.ativo=? AND m.grandeza=? ORDER BY m.seq DESC LIMIT 1",
            (ativo, grandeza)).fetchone()
    return (float(r[0]), float(r[1])) if r else None


# ─────────────── configuracao ───────────────
def _num(v, padrao=None):
    x = carbono.num(v)
    return padrao if x is None else x


def config_de(instancia: dict | None) -> dict | None:
    """instancia.json "pegada_servidor" + PHYSIS_PEGADA (JSON). PHYSIS_PEGADA=0 desliga (None)."""
    env = os.environ.get("PHYSIS_PEGADA", "").strip()
    if env == "0":
        return None
    c = dict((instancia or {}).get("pegada_servidor") or {})
    if env and env != "1":
        try:
            extra = json.loads(env)
            if isinstance(extra, dict):
                c.update(extra)
        except ValueError:
            pass
    return c


def _base_servidor(F: dict | None) -> dict:
    s = (F or {}).get("servidor") if isinstance(F, dict) else None
    return s if isinstance(s, dict) and s.get("classes") else PADRAO


def _interp(a: float, b: float, u: float) -> float:
    return a + (b - a) * max(0.0, min(1.0, u))


class PegadaServidor:
    """Amostra a energia a cada N minutos e guarda o total por hora em servidor_energia."""

    def __init__(self, hub, cfg: dict | None = None, F: dict | None = None, relogio=None,
                 rapl=ler_rapl, carga=ler_carga, gpus=ler_gpus, medidor=None, modelo=ler_modelo):
        self.hub = hub
        self.cfg = dict(cfg or {})
        if F is None:
            try:
                F = carbono.carregar()
            except (OSError, ValueError):
                F = {}
        self.F = F
        self.S = _base_servidor(F)
        self.relogio = relogio or hub.relogio
        self._rapl, self._carga, self._gpus = rapl, carga, gpus
        self._medidor = medidor or (lambda ativo, grandeza: ler_medidor_hub(hub, ativo, grandeza))
        self.intervalo_s = max(60.0, _num(self.cfg.get("intervalo_min"), self.S.get("amostra_min", 5)) * 60)
        self._ant: dict = {}             # por equipamento: {t, rapl, medidor_kwh}
        self.agora_w: dict = {}          # ultima potencia media por equipamento
        self.gpu_parada_s = 0.0
        self.gpu_ligada_s = 0.0
        with hub._trava:
            hub._db.executescript(ESQUEMA)
            hub._db.commit()
        gp = self._gpus()
        self.equipamentos = self._montar(modelo() if callable(modelo) else str(modelo or ""), bool(gp))

    # ── equipamentos ──
    def _classe(self, k: str | None) -> tuple[str, dict]:
        C = self.S["classes"]
        k = k if k in C else "mini_pc"
        return k, C[k]

    def _montar(self, modelo: str, tem_gpu: bool) -> list:
        c = self.cfg
        eqs = []
        k = c.get("classe") or classe_automatica(modelo, tem_gpu)
        eqs.append(self._equip({**c, "id": "hub", "nome": c.get("nome") or "Este servidor (Physis Hub)", "classe": k,
                                "metodo": "auto"}, principal=True))
        for i, h in enumerate(c.get("hosts") or []):
            if isinstance(h, dict):
                ident = re.sub(r"[^A-Za-z0-9_.-]", "", str(h.get("id") or f"host{i + 1}"))[:40] or f"host{i + 1}"
                eqs.append(self._equip({**h, "id": ident}, principal=False))
        return eqs

    def _equip(self, h: dict, principal: bool) -> dict:
        k, cl = self._classe(h.get("classe"))
        local = h.get("local") if h.get("local") in LOCAIS else "no_lugar"
        pue_pad = self.S["pue"]["datacenter_padrao"] if local == "fora" else self.S["pue"]["no_lugar"]
        med = h.get("medidor") if isinstance(h.get("medidor"), dict) and h["medidor"].get("ativo") else None
        gpus = h.get("gpus")
        return {"id": h["id"], "nome": str(h.get("nome") or cl["nome"])[:80], "classe": k, "principal": principal,
                "metodo_cfg": h.get("metodo") or ("medidor" if med else "nominal"), "medidor": med,
                "watts": _num(h.get("watts")), "uso": _num(h.get("uso")),
                "local": local, "controle": h.get("controle") if h.get("controle") in CONTROLES else "proprio",
                "pue": max(1.0, _num(h.get("pue"), pue_pad)), "gpus": None if gpus in (None, "auto") else int(_num(gpus, 0)),
                "ano_compra": int(_num(h.get("ano_compra"), 0)) or None}

    # ── uma amostra ──
    def _w_nominal(self, eq: dict, u: float | None, gpu_w: list | None) -> tuple[float, str]:
        cl = self.S["classes"][eq["classe"]]
        uu = u if u is not None else (eq["uso"] if eq["uso"] is not None else self.S.get("uso_padrao", 0.3))
        w = _interp(cl["w_ocioso"], cl["w_carga"], uu)
        if gpu_w:
            n_nom = eq["gpus"] if eq["gpus"] is not None else (1 if "gpu_w_ocioso" in cl else 0)
            if "gpu_w_ocioso" in cl:
                w -= _interp(cl["gpu_w_ocioso"], cl["gpu_w_carga"], uu) * n_nom   # a placa nominal sai; entra a medida
            return max(0.0, w) + sum(gpu_w), "nominal+gpu"
        return w, "nominal"

    def _medidor_amostra(self, eq: dict, ant: dict, t: float):
        """(kWh no intervalo ou None, W). Energia acumulada: diferenca; potencia: W × tempo (se a leitura e recente)."""
        m = eq["medidor"]
        r = self._medidor(m["ativo"], m.get("grandeza") or m.get("tipo") or "potencia_w")
        if not r:
            return None
        valor, ts = r
        tipo = m.get("tipo") or ("energia_kwh" if "kwh" in str(m.get("grandeza", "")).lower() else "potencia_w")
        if tipo == "energia_kwh":
            antes = ant.get("medidor_kwh")
            ant["medidor_kwh"] = valor
            if antes is None or valor < antes or t - ant.get("t", t) <= 0:
                return None            # primeira leitura ou contador zerado: este intervalo vai pela estimativa
            dkwh = valor - antes
            return dkwh, dkwh * 1000 * 3600 / (t - ant["t"])
        if t - ts > 2 * self.intervalo_s:
            return None                # leitura velha: o medidor parou de mandar
        return None, max(0.0, valor)

    def amostrar(self) -> list:
        """Mede todos os equipamentos e soma a energia do intervalo na hora certa. Devolve o que gravou."""
        t = float(self.relogio())
        u = self._carga()
        gp = self._gpus()
        rp = None
        gravado = []
        for eq in self.equipamentos:
            ant = self._ant.setdefault(eq["id"], {})
            t0 = ant.get("t")
            dt = (t - t0) if t0 is not None else 0.0
            dt_est = min(dt, 2 * self.intervalo_s)       # lacuna longa (hub parado): estimativa so do ultimo trecho
            kwh, w, metodo, fonte = None, None, None, ""
            contador = False                             # energia de contador (RAPL, medidor de kWh): vale o intervalo inteiro
            if eq["medidor"]:
                r = self._medidor_amostra(eq, ant, t)
                if r:
                    kwh_m, w = r
                    kwh = kwh_m if kwh_m is not None else w * dt_est / 3.6e6
                    contador = kwh_m is not None
                    metodo, fonte = "medidor", "medidor " + str(eq["medidor"]["ativo"])[:60]
            if metodo is None and eq["principal"]:
                rp = self._rapl() if rp is None else rp
                gpu_w = gp if (eq["gpus"] is None or eq["gpus"] > 0) else None
                if rp:
                    antes = ant.get("rapl")
                    ant["rapl"] = rp
                    if antes and dt > 0 and set(antes) == set(rp):
                        uj = 0
                        for z, (e, mx) in rp.items():
                            e0 = antes[z][0]
                            uj += (e - e0) if e >= e0 else (e + mx - e0 if mx else 0)   # contador deu a volta
                        w_cpu = uj / 1e6 / dt
                        w = w_cpu + self.S["classes"][eq["classe"]]["w_resto"] + sum(gpu_w or [])
                        kwh = (uj / 1e6 + (w - w_cpu) * dt) / 3.6e6       # processador: energia real do contador
                        contador = True
                        metodo = "rapl+gpu" if gpu_w else "rapl"
                        fonte = "RAPL do processador + resto da placa estimado" + (" + nvidia-smi" if gpu_w else "")
                if metodo is None:
                    w, metodo = self._w_nominal(eq, u, gpu_w)
                    kwh = w * dt_est / 3.6e6
                    fonte = "potência da classe × carga do processador" if u is not None else "potência da classe × uso típico"
                    if gpu_w:
                        fonte += " + nvidia-smi"
                if gpu_w:
                    self.gpu_ligada_s += dt_est
                    if max(gpu_w) < 50:
                        self.gpu_parada_s += dt_est
            if metodo is None:
                if eq["metodo_cfg"] == "watts" and eq["watts"] is not None:
                    w, metodo, fonte = eq["watts"], "fixo", "potência informada na configuração"
                else:
                    w, metodo = self._w_nominal(eq, None, None)
                    fonte = "potência da classe × uso informado" if eq["uso"] is not None else "potência da classe × uso típico"
                kwh = w * dt_est / 3.6e6
            ant["t"] = t
            self.agora_w[eq["id"]] = w
            if t0 is None or dt <= 0 or kwh is None:
                continue
            self._gravar(eq["id"], t0 if contador else t - dt_est, t, kwh, metodo, fonte, w)
            gravado.append({"id": eq["id"], "kwh": kwh, "w": w, "metodo": metodo})
        return gravado

    def _gravar(self, ident: str, t0: float, t1: float, kwh: float, metodo: str, fonte: str, w: float) -> None:
        """Divide a energia do intervalo [t0, t1] entre as horas que ele cruza, na proporcao do tempo."""
        total = t1 - t0
        if total <= 0:
            return
        partes = []
        a = t0
        while a < t1:
            h = int(a // 3600) * 3600
            b = min(t1, h + 3600)
            partes.append((h, b - a))
            a = b
        with self.hub._trava:
            for h, seg in partes:
                self.hub._db.execute(
                    "INSERT INTO servidor_energia(hora,equipamento,kwh,segundos,amostras,metodo,fonte,w_ultimo) "
                    "VALUES(?,?,?,?,1,?,?,?) ON CONFLICT(hora,equipamento) DO UPDATE SET kwh=kwh+excluded.kwh, "
                    "segundos=segundos+excluded.segundos, amostras=amostras+1, w_ultimo=excluded.w_ultimo, "
                    "metodo=CASE WHEN metodo=excluded.metodo THEN metodo ELSE 'misto' END, fonte=excluded.fonte",
                    (h, ident, kwh * seg / total, seg, metodo, fonte, w))
            self.hub._db.commit()

    # ── relatorio ──
    def fator(self) -> tuple[float, str]:
        """Mesmo fator da rede do modulo Carbono: configuracao > escolha salva no Carbono do cliente > padrao da base."""
        m = carbono.num(self.cfg.get("fator_rede"))
        if m is not None and m >= 0:
            return m, "configuração do servidor"
        if not self.F.get("rede"):
            return FATOR_REDE_RESERVA, "padrão da plataforma (base de fatores ausente)"
        try:
            it = self.hub.cliente_ler(chave="physis-carbono").get("physis-carbono")
            est = json.loads(it["valor"]) if it else {}
            rede = (est or {}).get("rede") or {}
        except Exception:      # noqa: BLE001 (estado do cliente ilegivel: segue o padrao)
            rede = {}
        f = carbono.fator_rede(self.F, rede.get("fator") or None, rede.get("fator_manual"))
        return f, "o mesmo do Carbono (escopo 2)" if rede else "padrão da base de fatores (" + str(self.F["rede"]["padrao"]) + ")"

    def _fabricacao(self, eq: dict) -> tuple[float, float, int]:
        """(kgCO2e da fabricacao, tCO2e por ano amortizado, vida em anos)."""
        cl = self.S["classes"][eq["classe"]]
        kg = float(cl["kgco2e_fabricacao"])
        n_gpu = eq["gpus"] if eq["gpus"] is not None else (1 if "gpu_w_ocioso" in cl else 0)
        kg += n_gpu * float(self.S.get("gpu_placa", {}).get("kgco2e_fabricacao", 0))
        vida = int(cl.get("vida_anos") or 5)
        return kg, kg / 1000 / vida, vida

    def relatorio(self, detalhado: bool = True, agora: float | None = None) -> dict:
        agora = float(self.relogio() if agora is None else agora)
        desde = agora - 30 * 86400
        with self.hub._trava:
            linhas = self.hub._db.execute(
                "SELECT hora, equipamento, kwh, segundos, metodo FROM servidor_energia WHERE hora >= ? ORDER BY hora",
                (int(desde // 3600) * 3600 - 365 * 86400,)).fetchall()
            try:
                contas = self.hub._db.execute("SELECT COUNT(*) FROM conta WHERE ativa=1").fetchone()[0]
            except Exception:      # noqa: BLE001
                contas = 0
        f, f_fonte = self.fator()
        escolha = self.cfg.get("contagem") if self.cfg.get("contagem") in ("ja_contado", "somar") else "auto"
        meses: dict = {}
        por_eq: dict = {}
        for hora, ident, kwh, seg, metodo in linhas:
            m = time.strftime("%Y-%m", time.localtime(hora))
            meses[m] = meses.get(m, 0.0) + kwh
            if hora >= desde - 3600:
                d = por_eq.setdefault(ident, {"kwh": 0.0, "seg": 0.0, "metodos": {}})
                d["kwh"] += kwh
                d["seg"] += seg
                d["metodos"][metodo] = d["metodos"].get(metodo, 0.0) + seg
        eqs = []
        for eq in self.equipamentos:
            d = por_eq.get(eq["id"], {"kwh": 0.0, "seg": 0.0, "metodos": {}})
            w = self.agora_w.get(eq["id"])
            if d["seg"] > 0:
                kwh_mes_ti = d["kwh"] / d["seg"] * 3600 * H_MES
                metodo = max(d["metodos"], key=d["metodos"].get)
            else:          # sem historico ainda: projeta a potencia de agora
                kwh_mes_ti = (w or 0) * H_MES / 1000
                metodo = "nominal" if w is None else "sem_historico"
            kwh_mes = kwh_mes_ti * eq["pue"]
            kg, t_fab, vida = self._fabricacao(eq)
            item = {"id": eq["id"], "nome": eq["nome"], "classe": eq["classe"], "classe_nome": self.S["classes"][eq["classe"]]["nome"],
                    "local": eq["local"], "controle": eq["controle"], "pue": eq["pue"], "contagem": carbono.servidor_contagem(eq, escolha),
                    "metodo": metodo, "qualidade": qualidade(metodo), "w_agora": w, "kwh_mes_ti": kwh_mes_ti, "kwh_mes": kwh_mes,
                    "kwh_ano": kwh_mes * 12, "t_ano": kwh_mes * 12 / 1000 * f, "kg_fabricacao": kg, "vida_anos": vida,
                    "t_ano_fabricacao": t_fab, "ano_compra": eq["ano_compra"], "cobertura_dias": d["seg"] / 86400, "verificar": True}
            if detalhado:
                item["fonte"] = _fonte_eq(eq)
            eqs.append(item)
        inv = carbono.servidor_inventario(eqs, f, escolha)
        kwh_mes = sum(e["kwh_mes"] for e in eqs)
        med = sum(e["kwh_mes"] for e in eqs if e["qualidade"] == "medido")
        r = {"ok": True, "modo": "hub", "agora": agora, "intervalo_min": self.intervalo_s / 60, "fator_rede": f, "fator_fonte": f_fonte,
             "contagem": escolha, "equipamentos": eqs,
             "total": {"w_agora": sum(e["w_agora"] or 0 for e in eqs), "kwh_mes": kwh_mes, "kwh_ano": kwh_mes * 12,
                       "t_ano": kwh_mes * 12 / 1000 * f, "t_ano_fabricacao": sum(e["t_ano_fabricacao"] for e in eqs),
                       "e2_somar_t": inv["e2_t"], "e3_cat1_t": inv["e3_cat1_t"], "ja_contado_t": inv["ja_contado_t"],
                       "medido_pct": med / kwh_mes if kwh_mes else None},
             "meses": [{"mes": k, "kwh": v} for k, v in sorted(meses.items())][-12:],
             "kwh_mes_por_conta": kwh_mes / contas if contas else None, "contas_ativas": contas,
             "dicas": self.dicas(), "verificar": True}
        if detalhado:
            r["clientes"] = por_cliente(kwh_mes, f, self.cfg.get("clientes"))
        return r

    def dicas(self) -> list:
        d = []
        if self.gpu_ligada_s > 0:
            pct = self.gpu_parada_s / self.gpu_ligada_s
            if pct >= 0.5:
                d.append(f"A placa de vídeo ficou parada {round(pct * 100)}% do tempo desde que o hub ligou: desligue ou suspenda quando não houver IA rodando.")
        return d + list(DICAS)


def _fonte_eq(eq: dict) -> str:
    if eq["medidor"]:
        return "medidor " + str(eq["medidor"]["ativo"])[:60] + " (" + str(eq["medidor"].get("grandeza") or "") + ")"
    if eq["principal"]:
        return "RAPL quando legível; senão potência da classe × carga; nvidia-smi para as placas de vídeo"
    return "potência informada" if eq["metodo_cfg"] == "watts" else "potência da classe × uso"


def qualidade(metodo: str) -> str:
    """medido (medidor na tomada), parcial (contador do processador ou placa de vídeo medida) ou estimado."""
    if metodo == "medidor":
        return "medido"
    if metodo.startswith("rapl") or "gpu" in metodo or metodo == "misto":
        return "parcial"
    return "estimado"


def por_cliente(kwh_mes: float, f: float, clientes) -> list:
    """Parte de cada cliente hospedado, pelo peso (igual se faltar). Para o cliente, entra como escopo 3, cat. 1."""
    cs = [c for c in (clientes or []) if isinstance(c, dict)]
    if not cs:
        return []
    pesos = [max(0.0, _num(c.get("peso"), 1.0)) for c in cs]
    soma = sum(pesos) or 1.0
    return [{"id": str(c.get("id") or "")[:60], "nome": str(c.get("nome") or c.get("id") or "")[:80],
             "kwh_mes": kwh_mes * p / soma, "t_ano": kwh_mes * p / soma * 12 / 1000 * f} for c, p in zip(cs, pesos)]


# ─────────────── ligacao com o servidor ───────────────
_TRAVA = threading.Lock()


def para(hub, cfg: dict | None = None, **kw) -> PegadaServidor:
    """A pegada desta instalacao (uma por hub; criada na primeira chamada)."""
    with _TRAVA:
        pg = getattr(hub, "pegada", None)
        if pg is None:
            pg = PegadaServidor(hub, cfg if cfg is not None else {}, **kw)
            hub.pegada = pg
        return pg


def rodar(pegada: PegadaServidor, parar: threading.Event) -> None:
    """Linha de fundo: uma amostra a cada intervalo (padrao 5 min) ate o servidor parar."""
    while not parar.is_set():
        try:
            pegada.amostrar()
        except Exception as e:      # noqa: BLE001 (um erro de leitura nao derruba o servidor)
            print("pegada_servidor:", type(e).__name__, e)
        parar.wait(pegada.intervalo_s)
