"""Physis 3D (EM DESENVOLVIMENTO): peças para impressão 3D com plástico reciclado.

Fora do site e da loja públicos; aparece com o selo "Em desenvolvimento" na instalação de pesquisa (Casa Physis).
Documento: docs/PHYSIS_3D.md. Tela: sistema/physis-3d.js (espelho das contas de malha e de fatiamento abaixo).

O que este módulo faz (só biblioteca padrão; funciona igual no Linux do servidor e no Windows da versão 0):
- malha: lê STL (texto e binário), OBJ e 3MF; mede caixa, volume, área, faces em balanço e arestas com problema;
  fatia em camadas planas (perímetro e área por camada) e estima filamento, massa e tempo. Mesmas contas da tela.
- biblioteca dos participantes (SQLite do hub): peças, revisões (arquivo guardado em disco pelo resumo SHA-256,
  nota da mudança, problemas, configuração, material, resultado, fotos), resumo de integridade por revisão no
  mesmo estilo de integridade.py (JSON canônico + SHA-256, encadeado na revisão anterior), memorial montado sozinho.
- fórum: tópicos por peça e gerais.
- papéis: participante (conta com sessão, papel cliente ou acima) publica; a equipe da Physis cura e modera.
  Publicar pede o consentimento LGPD do participante e uma licença aberta escolhida pelo autor (LICENCAS).
- avisos: Naive Bayes (biblioteca padrão) treinado no histórico de revisões + "impressões parecidas".
  Com poucos dados, diz que são poucos.
- fatiador: adaptador para o serviço aberto em contêiner (servicos/fatiador, PrusaSlicer em linha de comando,
  AGPL-3.0, processo separado). Sem o serviço, devolve None e a tela exporta a malha para fatiar num fatiador aberto.

Pasta dos arquivos: PHYSIS_3D_PASTA, senão "<pasta do banco>/impressao3d" (pasta_padrao). Nada de caminho fixo.
Rotas: Impressao3D.rota(metodo, caminho, quem, corpo, consulta) — o servidor liga (veja docs/PHYSIS_3D.md).
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import math
import os
import re
import secrets
import struct
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from . import integridade

ESTADO = "dev"
VERSAO_TERMO = "1"
FINALIDADE = ("Physis 3D: mostrar o seu nome público junto das peças, revisões, fotos e mensagens que você publicar na "
              "biblioteca aberta dos participantes da plataforma, sob a licença aberta que você escolher. Você pode pedir "
              "a remoção do seu nome a qualquer momento (as peças publicadas seguem sob a licença, sem o seu nome).")
LICENCAS = {"CC-BY-4.0": "Creative Commons Atribuição 4.0", "CC-BY-SA-4.0": "Creative Commons Atribuição-CompartilhaIgual 4.0",
            "CC0-1.0": "Creative Commons Zero 1.0 (domínio público)", "CERN-OHL-S-2.0": "CERN Open Hardware Licence 2.0, fortemente recíproca",
            "CERN-OHL-W-2.0": "CERN Open Hardware Licence 2.0, fracamente recíproca", "CERN-OHL-P-2.0": "CERN Open Hardware Licence 2.0, permissiva"}
PROBLEMAS = {"empenamento": "Empenamento (warping)", "adesao": "Pouca adesão à mesa", "fios": "Fios (stringing)",
             "delaminacao": "Separação de camadas", "subextrusao": "Subextrusão", "sobreextrusao": "Sobre-extrusão",
             "balanco": "Balanço ou ponte caiu", "dimensional": "Medida fora (contração)", "entupimento": "Bico entupido",
             "bolhas": "Bolhas ou umidade no filamento", "outro": "Outro problema"}
RESULTADOS = {"ok": "Deu certo", "parcial": "Serviu com defeito", "falha": "Falhou"}
MATERIAIS = ("rpetg", "rpp", "rhdpe", "rabs", "rpla")
FORMATOS = ("stl", "obj", "3mf")
ARQ_MAX = 40 * 1024 * 1024          # malha guardada
FOTO_MAX = 8 * 1024 * 1024
CORPO_MAX = 60 * 1024 * 1024        # JSON com base64 (o servidor lê com _corpo_grande)
DESCOMPACTADO_MAX = 200 * 1024 * 1024
TRIANGULOS_MAX = 3_000_000
MIN_TREINO, MIN_SEMELHANTES = 10, 3
LIMIAR_AVISO = 0.30
UNIDADES_3MF = {"micron": 0.001, "millimeter": 1.0, "centimeter": 10.0, "inch": 25.4, "foot": 304.8, "meter": 1000.0}
NS_3MF = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"   # nome do formato (namespace XML), não é endereço acessado

RAIZ = Path(__file__).resolve().parents[2]
PREMISSAS = (RAIZ / "sistema" / "physis-premissas.json", RAIZ / "sistema" / "physis-3d-premissas.json")

# configuração de impressão de partida (editável na tela; NÃO é dado técnico do material)
CONFIG_PADRAO = {"altura_camada": 0.2, "largura_linha": 0.45, "paredes": 2, "preenchimento": 0.2, "camadas_topo": 4,
                 "camadas_fundo": 4, "vel_parede": 40.0, "vel_preench": 60.0, "fator_deslocamento": 1.15,
                 "troca_camada_s": 2.0, "diametro_filamento": 1.75, "bico_c": None, "mesa_c": None, "bico_mm": 0.4}


class MalhaInvalida(ValueError):
    pass


# ══ Leitura de malhas ════════════════════════════════════════════════════════════════════════════
def _tri(a, b, c):
    return (tuple(map(float, a)), tuple(map(float, b)), tuple(map(float, c)))


def ler_stl(dados: bytes) -> list:
    if len(dados) >= 84:
        n = struct.unpack_from("<I", dados, 80)[0]
        if len(dados) == 84 + 50 * n:
            if n > TRIANGULOS_MAX:
                raise MalhaInvalida("malha grande demais")
            out = []
            for i in range(n):
                v = struct.unpack_from("<12f", dados, 84 + 50 * i)
                out.append(_tri(v[3:6], v[6:9], v[9:12]))
            return out
    texto = dados.decode("utf-8", errors="replace")
    if not re.match(r"\s*solid", texto) or "facet" not in texto:
        raise MalhaInvalida("STL não reconhecido")
    nums = re.findall(r"vertex\s+(\S+)\s+(\S+)\s+(\S+)", texto)
    if len(nums) % 3 or not nums:
        raise MalhaInvalida("STL de texto incompleto")
    try:
        vs = [tuple(float(x) for x in t) for t in nums]
    except ValueError as e:
        raise MalhaInvalida("número inválido no STL") from e
    return [_tri(vs[i], vs[i + 1], vs[i + 2]) for i in range(0, len(vs), 3)]


def ler_obj(dados: bytes) -> list:
    vs, out = [], []
    for linha in dados.decode("utf-8", errors="replace").splitlines():
        p = linha.split()
        if not p:
            continue
        if p[0] == "v" and len(p) >= 4:
            vs.append(tuple(float(x) for x in p[1:4]))
        elif p[0] == "f" and len(p) >= 4:
            idx = []
            for t in p[1:]:
                k = int(t.split("/")[0])
                idx.append(k - 1 if k > 0 else len(vs) + k)
            for j in range(1, len(idx) - 1):                     # leque: polígono vira triângulos
                out.append(_tri(vs[idx[0]], vs[idx[j]], vs[idx[j + 1]]))
    if not out:
        raise MalhaInvalida("OBJ sem faces")
    return out


def _matriz_3mf(txt):
    if not txt:
        return None
    m = [float(x) for x in txt.split()]
    return m if len(m) == 12 else None


def _aplicar(m, v):
    if not m:
        return v
    x, y, z = v
    return (m[0] * x + m[3] * y + m[6] * z + m[9], m[1] * x + m[4] * y + m[7] * z + m[10], m[2] * x + m[5] * y + m[8] * z + m[11])


def _compor(a, b):
    """a depois de b (as duas no formato 3MF de 12 números)."""
    if not a:
        return b
    if not b:
        return a
    def M(m):
        return [[m[0], m[3], m[6], m[9]], [m[1], m[4], m[7], m[10]], [m[2], m[5], m[8], m[11]], [0, 0, 0, 1]]
    A, B = M(a), M(b)
    C = [[sum(A[i][k] * B[k][j] for k in range(4)) for j in range(4)] for i in range(4)]
    return [C[0][0], C[1][0], C[2][0], C[0][1], C[1][1], C[2][1], C[0][2], C[1][2], C[2][2], C[0][3], C[1][3], C[2][3]]


def ler_3mf(dados: bytes) -> list:
    try:
        z = zipfile.ZipFile(io.BytesIO(dados))
    except zipfile.BadZipFile as e:
        raise MalhaInvalida("3MF não é um ZIP") from e
    nomes = [i for i in z.infolist() if i.filename.lower().endswith(".model")]
    if not nomes:
        raise MalhaInvalida("3MF sem modelo")
    info = next((i for i in nomes if i.filename.lower() == "3d/3dmodel.model"), nomes[0])
    if info.file_size > DESCOMPACTADO_MAX:
        raise MalhaInvalida("3MF grande demais")
    with z.open(info) as f:
        xml = f.read(DESCOMPACTADO_MAX + 1)
    if len(xml) > DESCOMPACTADO_MAX or b"<!DOCTYPE" in xml[:2048].upper():
        raise MalhaInvalida("3MF recusado")
    raiz = ET.fromstring(xml)
    ns = "{" + NS_3MF + "}"
    escala = UNIDADES_3MF.get(raiz.get("unit") or "millimeter", 1.0)
    objetos = {}
    for o in raiz.iter(ns + "object"):
        malha = o.find(ns + "mesh")
        comps = o.find(ns + "components")
        if malha is not None:
            vs = [(float(v.get("x")), float(v.get("y")), float(v.get("z"))) for v in malha.iter(ns + "vertex")]
            ts = [(int(t.get("v1")), int(t.get("v2")), int(t.get("v3"))) for t in malha.iter(ns + "triangle")]
            objetos[o.get("id")] = ("malha", vs, ts)
        elif comps is not None:
            objetos[o.get("id")] = ("comp", [(c.get("objectid"), _matriz_3mf(c.get("transform"))) for c in comps.iter(ns + "component")], None)
    out = []

    def emitir(oid, m, prof=0):
        if prof > 16 or oid not in objetos:
            return
        tipo, a, b = objetos[oid]
        if tipo == "comp":
            for cid, cm in a:
                emitir(cid, _compor(m, cm), prof + 1)
            return
        for i1, i2, i3 in b:
            out.append(_tri(*(tuple(c * escala for c in _aplicar(m, a[i])) for i in (i1, i2, i3))))
            if len(out) > TRIANGULOS_MAX:
                raise MalhaInvalida("malha grande demais")
    build = raiz.find(ns + "build")
    itens = list(build.iter(ns + "item")) if build is not None else []
    if itens:
        for it in itens:
            emitir(it.get("objectid"), _matriz_3mf(it.get("transform")))
    else:
        for oid in objetos:
            emitir(oid, None)
    if not out:
        raise MalhaInvalida("3MF sem triângulos")
    return out


def formato_de(nome: str) -> str:
    ext = (nome or "").rsplit(".", 1)[-1].lower()
    if ext not in FORMATOS:
        raise MalhaInvalida("formato aceito: STL, OBJ ou 3MF")
    return ext


def ler_malha(dados: bytes, nome: str) -> list:
    return {"stl": ler_stl, "obj": ler_obj, "3mf": ler_3mf}[formato_de(nome)](dados)


def escrever_stl(tris: list, nome: str = "physis3d") -> bytes:
    """STL binário (o que a tela também exporta)."""
    cab = nome.encode("ascii", "replace")[:80].ljust(80, b" ")
    partes = [cab, struct.pack("<I", len(tris))]
    for a, b, c in tris:
        n = _normal(a, b, c)
        partes.append(struct.pack("<12fH", *n, *a, *b, *c, 0))
    return b"".join(partes)


# ══ Medidas ══════════════════════════════════════════════════════════════════════════════════════
def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cruz(u, v):
    return (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])


def _normal(a, b, c):
    n = _cruz(_sub(b, a), _sub(c, a))
    m = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
    return (n[0] / m, n[1] / m, n[2] / m) if m > 0 else (0.0, 0.0, 0.0)


def caixa(tris: list) -> dict:
    xs = [v[0] for t in tris for v in t]
    ys = [v[1] for t in tris for v in t]
    zs = [v[2] for t in tris for v in t]
    mn, mx = (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))
    return {"min": mn, "max": mx, "tamanho": tuple(mx[i] - mn[i] for i in range(3))}


def arestas(tris: list, passo: float = 1e-4) -> dict:
    """Arestas com problema: abertas (1 face), não-manifold (3+ faces) e de orientação trocada (mesmo sentido 2×)."""
    chave = lambda v: (round(v[0] / passo), round(v[1] / passo), round(v[2] / passo))
    uso, sentido, degeneradas = {}, {}, 0
    for t in tris:
        k = [chave(v) for v in t]
        if k[0] == k[1] or k[1] == k[2] or k[0] == k[2]:
            degeneradas += 1
            continue
        for i in range(3):
            a, b = k[i], k[(i + 1) % 3]
            e = (a, b) if a < b else (b, a)
            uso[e] = uso.get(e, 0) + 1
            sentido[(a, b)] = sentido.get((a, b), 0) + 1
    abertas = sum(1 for n in uso.values() if n == 1)
    nao_manifold = sum(1 for n in uso.values() if n > 2)
    trocadas = sum(1 for n in sentido.values() if n > 1)
    return {"arestas": len(uso), "abertas": abertas, "nao_manifold": nao_manifold, "orientacao_trocada": trocadas,
            "degeneradas": degeneradas, "fechada": abertas == 0 and nao_manifold == 0 and trocadas == 0}


def medir(tris: list, limite_balanco_graus: float = 45.0) -> dict:
    """Caixa, volume (mm³), área (mm²), fração da área em balanço acima do limite e arestas com problema."""
    if not tris:
        raise MalhaInvalida("malha vazia")
    cx = caixa(tris)
    zmin = cx["min"][2]
    vol = area = area_bal = 0.0
    faces_bal = 0
    seno = math.sin(math.radians(limite_balanco_graus))
    for a, b, c in tris:
        n = _cruz(_sub(b, a), _sub(c, a))
        m = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
        vol += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
        if m <= 0:
            continue
        area += m / 2
        nz = n[2] / m
        na_mesa = max(a[2], b[2], c[2]) <= zmin + 0.01
        if -nz > seno and not na_mesa:            # virada para baixo, mais deitada que o limite, fora da mesa
            area_bal += m / 2
            faces_bal += 1
    return {"caixa_min": cx["min"], "caixa_max": cx["max"], "tamanho": cx["tamanho"], "volume_mm3": abs(vol),
            "volume_sinal": 1 if vol >= 0 else -1, "area_mm2": area, "triangulos": len(tris),
            "balanco_limite_graus": limite_balanco_graus, "balanco_faces": faces_bal, "balanco_area_mm2": area_bal,
            "balanco_fracao": area_bal / area if area else 0.0, "arestas": arestas(tris)}


# ══ Fatiamento plano e estimativas (espelho de physis-3d.js) ═════════════════════════════════════
def fatiar(tris: list, altura: float = 0.2) -> list[dict]:
    """Camadas no meio de cada faixa: z = zmin + (i + ½)·altura. Por camada: perímetro (mm) e área (mm²).
    A área sai sem juntar os segmentos em contornos: cada segmento é orientado pela normal da face (contorno de fora
    no sentido anti-horário, furo no horário) e a fórmula do laço de Gauss soma segmento por segmento."""
    if not tris or altura <= 0:
        return []
    zs = [(min(t[0][2], t[1][2], t[2][2]), max(t[0][2], t[1][2], t[2][2]), t) for t in tris]
    zmin, zmax = min(z[0] for z in zs), max(z[1] for z in zs)
    n = max(0, int(math.floor((zmax - zmin) / altura + 1e-9)))
    zs.sort(key=lambda z: z[0])
    camadas, ativo, j = [], [], 0
    for i in range(n):
        zc = zmin + (i + 0.5) * altura
        while j < len(zs) and zs[j][0] <= zc:
            ativo.append(zs[j])
            j += 1
        ativo = [z for z in ativo if z[1] >= zc]
        per = ar = 0.0
        for _, _, t in ativo:
            s = _corte(t, zc)
            if not s:
                continue
            (px, py), (qx, qy) = s
            per += math.hypot(qx - px, qy - py)
            ar += px * qy - qx * py
        camadas.append({"i": i, "z": zc, "perimetro_mm": per, "area_mm2": ar / 2})
    return camadas


def _corte(t, zc):
    pts = []
    for k in range(3):
        a, b = t[k], t[(k + 1) % 3]
        za, zb = a[2] - zc, b[2] - zc
        if za == 0:
            za = 1e-12                      # vértice exatamente no plano: empurra um fio para cima
        if zb == 0:
            zb = 1e-12
        if (za < 0) != (zb < 0):
            s = za / (za - zb)
            pts.append((a[0] + s * (b[0] - a[0]), a[1] + s * (b[1] - a[1])))
    if len(pts) != 2:
        return None
    n = _cruz(_sub(t[1], t[0]), _sub(t[2], t[0]))
    (px, py), (qx, qy) = pts
    dx, dy = qx - px, qy - py
    if dy * n[0] - dx * n[1] < 0:            # a direita do segmento tem de apontar para fora (normal)
        pts.reverse()
    return pts


def config(cfg: dict | None) -> dict:
    c = dict(CONFIG_PADRAO)
    for k, v in (cfg or {}).items():
        if k in c and v is not None and v != "":
            try:
                c[k] = float(str(v).strip().replace(",", ".")) if isinstance(v, str) else float(v)   # a tela aceita vírgula
            except (TypeError, ValueError):
                pass
    return c


def estimar(camadas: list[dict], cfg: dict | None, densidade_g_cm3: float) -> dict:
    """Filamento (m), massa (g) e tempo (h). Estimativa de pré-projeto: paredes = n × perímetro (sem o recuo para
    dentro), preenchimento = área de dentro ÷ largura da linha × fração (100 % nas camadas de topo e fundo da peça
    inteira; topos internos não entram). O fatiador de verdade (serviço) dá o número final."""
    c = config(cfg)
    h, w, npar = c["altura_camada"], c["largura_linha"], int(c["paredes"])
    total = len(camadas)
    parede = preench = 0.0
    for k, cm in enumerate(camadas):
        solida = k < c["camadas_fundo"] or k >= total - c["camadas_topo"]
        per, area = cm["perimetro_mm"], max(0.0, cm["area_mm2"])
        dentro = max(0.0, area - per * npar * w)
        parede += npar * per
        preench += dentro / w * (1.0 if solida else c["preenchimento"])
    vol = (parede + preench) * w * h
    secao = math.pi * (c["diametro_filamento"] / 2) ** 2
    tempo_s = (parede / c["vel_parede"] + preench / c["vel_preench"]) * c["fator_deslocamento"] + total * c["troca_camada_s"]
    return {"camadas": total, "caminho_parede_mm": parede, "caminho_preench_mm": preench, "volume_extrudado_mm3": vol,
            "filamento_m": vol / secao / 1000, "massa_g": vol / 1000 * densidade_g_cm3, "tempo_h": tempo_s / 3600,
            "config": c}


def analisar(dados: bytes, nome: str, cfg: dict | None = None, densidade: float | None = None, fatiar_tambem: bool = True) -> dict:
    tris = ler_malha(dados, nome)
    m = medir(tris)
    out = {"ok": True, "medidas": m}
    if fatiar_tambem and len(tris) <= 300_000:
        cam = fatiar(tris, config(cfg)["altura_camada"])
        out["estimativa"] = estimar(cam, cfg, densidade or 1.0) if densidade else None
        out["camadas"] = len(cam)
    return out


# ══ Perfis de material (premissas "conferir") ════════════════════════════════════════════════════
def perfis(caminhos=PREMISSAS) -> dict:
    """Perfis de material. Primeiro physis-premissas.json (quando a proposta entrar), depois physis-3d-premissas.json."""
    out = {}
    for arq in caminhos:
        try:
            base = json.loads(Path(arq).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for p in base.get("premissas", []):
            if str(p.get("id", "")).startswith("impressao3d.material."):
                k = p["id"].rsplit(".", 1)[-1]
                out.setdefault(k, dict(p["valor_padrao"], id=p["id"], status=p.get("status", ""), fonte=p.get("fonte", "")))
    return out


# ══ Avisos aprendidos (Naive Bayes, biblioteca padrão) ═══════════════════════════════════════════
def _faixa(v, cortes, nomes):
    if v is None:
        return "?"
    for c, n in zip(cortes, nomes):
        if v <= c:
            return n
    return nomes[-1]


def caracteristicas(r: dict, perfis_mat: dict | None = None) -> dict:
    """Variáveis da revisão em faixas: material, altura de camada, fração em balanço, espessura de parede,
    maior dimensão e temperatura do bico em relação ao perfil do material."""
    cfg = config(r.get("config"))
    mat = r.get("material") or "?"
    parede = r.get("espessura_parede_mm")
    if parede is None:
        parede = cfg["paredes"] * cfg["largura_linha"]
    bico = (r.get("config") or {}).get("bico_c")
    ref = (perfis_mat or {}).get(mat, {}).get("bico_c")
    try:
        bico = float(bico) if bico not in (None, "") else None
    except (TypeError, ValueError):
        bico = None
    tbico = "?" if bico is None else (_faixa(bico - ref, (-7.5, 7.5), ("abaixo", "no_perfil", "acima")) if ref else _faixa(bico, (205, 225, 245), ("ate205", "ate225", "ate245", "acima245")))
    return {"material": mat,
            "camada": _faixa(cfg["altura_camada"], (0.12, 0.2, 0.28), ("fina", "media", "grossa", "muito_grossa")),
            "balanco": _faixa(r.get("balanco_fracao"), (0.02, 0.1, 0.25), ("nenhum", "pouco", "medio", "muito")),
            "parede": _faixa(float(parede), (0.9, 1.3, 2.0), ("fina", "media", "grossa", "muito_grossa")),
            "tamanho": _faixa(r.get("tamanho_mm"), (50, 120, 200), ("pequena", "media", "grande", "muito_grande")),
            "bico": tbico}


VARIAVEIS = ("material", "camada", "balanco", "parede", "tamanho", "bico")


class AvisosNB:
    """Um classificador de Bayes ingênuo (Bernoulli no rótulo, categórico nas variáveis, suavização de Laplace)
    para cada problema registrado. Treino: revisões com resultado."""

    def __init__(self, linhas: list[dict], perfis_mat: dict | None = None):
        self.perfis = perfis_mat or {}
        self.linhas = [dict(l, _x=caracteristicas(l, self.perfis)) for l in linhas if l.get("resultado") in RESULTADOS]
        self.valores = {v: {l["_x"][v] for l in self.linhas} | {"?"} for v in VARIAVEIS}
        self.n = len(self.linhas)

    def probabilidade(self, x: dict, problema: str) -> float:
        com = [l for l in self.linhas if problema in (l.get("problemas") or [])]
        sem_n = self.n - len(com)
        lp1 = math.log((len(com) + 1) / (self.n + 2))
        lp0 = math.log((sem_n + 1) / (self.n + 2))
        for v in VARIAVEIS:
            k = len(self.valores[v]) + (0 if x[v] in self.valores[v] else 1)
            c1 = sum(1 for l in com if l["_x"][v] == x[v])
            c0 = sum(1 for l in self.linhas if l["_x"][v] == x[v]) - c1
            lp1 += math.log((c1 + 1) / (len(com) + k))
            lp0 += math.log((c0 + 1) / (sem_n + k))
        m = max(lp1, lp0)
        return math.exp(lp1 - m) / (math.exp(lp1 - m) + math.exp(lp0 - m))

    def semelhantes(self, x: dict) -> list[dict]:
        """Mesmo material e no máximo uma variável em faixa diferente."""
        out = []
        for l in self.linhas:
            if l["_x"]["material"] != x["material"]:
                continue
            if sum(1 for v in VARIAVEIS[1:] if l["_x"][v] != x[v]) <= 1:
                out.append(l)
        return out

    def avisar(self, r: dict, mudancas: dict | None = None) -> dict:
        """mudancas: {(peca, numero): texto do que mudou na revisão seguinte}."""
        x = caracteristicas(r, self.perfis)
        if self.n < MIN_TREINO:
            return {"ok": True, "poucos_dados": True, "treino": self.n, "caracteristicas": x, "avisos": [],
                    "texto": f"Ainda há poucos dados: {self.n} impressões com resultado registrado (o aviso começa com {MIN_TREINO}). "
                             "Registre o resultado e os problemas de cada impressão para a biblioteca aprender."}
        sem = self.semelhantes(x)
        avisos = []
        for p in PROBLEMAS:
            prob = self.probabilidade(x, p)
            casos = [l for l in sem if p in (l.get("problemas") or [])]
            if not casos and prob < LIMIAR_AVISO:
                continue
            mud = []
            for l in casos:
                t = (mudancas or {}).get((l.get("peca"), l.get("numero")))
                if t and t not in mud:
                    mud.append(t)
            texto = (f"Em {len(sem)} impressões parecidas, {len(casos)} tiveram {PROBLEMAS[p].lower()}."
                     + (" O que mudaram depois: " + "; ".join(mud[:3]) + "." if mud else ""))
            avisos.append({"problema": p, "nome": PROBLEMAS[p], "probabilidade": round(prob, 3), "semelhantes": len(sem),
                           "casos": len(casos), "mudancas": mud[:3], "texto": texto})
        avisos.sort(key=lambda a: (-a["casos"], -a["probabilidade"]))
        pouco = len(sem) < MIN_SEMELHANTES
        return {"ok": True, "poucos_dados": pouco, "treino": self.n, "semelhantes": len(sem), "caracteristicas": x, "avisos": avisos,
                "texto": (f"Só {len(sem)} impressões parecidas na biblioteca: leia os avisos como pista, não como regra." if pouco
                          else f"Comparado com {len(sem)} impressões parecidas de {self.n} registradas.")}


# ══ Fatiador (serviço aberto em contêiner: servicos/fatiador) ════════════════════════════════════
def _destino_local(url: str) -> bool:
    import ipaddress
    try:
        u = urllib.parse.urlparse(url)
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    if u.scheme not in ("http", "https") or not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return host == "localhost" or "." not in host or host.endswith((".local", ".lan", ".internal", ".localhost"))


class Fatiador:
    """Cliente do serviço de fatiamento. Nunca obrigatório: sem PHYSIS_FATIADOR_URL ou com o serviço fora, devolve None.
    `pedir` pode ser trocado (testes usam um fatiador falso)."""

    def __init__(self, url: str | None = None, chave: str | None = None, tempo: float | None = None, pedir=None):
        url = (url if url is not None else os.environ.get("PHYSIS_FATIADOR_URL") or "").strip().rstrip("/")
        if url and not _destino_local(url) and os.environ.get("PHYSIS_FATIADOR_EXTERNO") != "1":
            url = ""
        self.url = url
        self.chave = chave if chave is not None else os.environ.get("PHYSIS_FATIADOR_CHAVE") or ""
        self.tempo = float(tempo or os.environ.get("PHYSIS_FATIADOR_TEMPO") or 300)
        self._pedir = pedir or self._http

    def _http(self, caminho: str, corpo: dict | None):
        dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
        req = urllib.request.Request(self.url + caminho, data=dados, method="POST" if dados else "GET",
                                     headers={"Content-Type": "application/json", "User-Agent": "PhysisHub/1.0"})
        if self.chave:
            req.add_header("Authorization", "Bearer " + self.chave)
        try:
            with urllib.request.urlopen(req, timeout=self.tempo if dados else 3) as r:
                return json.loads(r.read(80 * 1024 * 1024).decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (400, 422):
                try:
                    return json.loads(e.read(65536).decode("utf-8"))
                except (ValueError, OSError):
                    return {"ok": False, "erro": f"HTTP {e.code}"}
            return None
        except (urllib.error.URLError, OSError, ValueError):
            return None

    def disponivel(self) -> dict | None:
        if not self.url and self._pedir == self._http:
            return None
        return self._pedir("/saude", None)

    def fatiar(self, stl: bytes, cfg: dict | None, material: dict | None = None) -> dict | None:
        if not self.url and self._pedir == self._http:
            return None
        c = config(cfg)
        if material:
            c["bico_c"] = c["bico_c"] or material.get("bico_c")
            c["mesa_c"] = c["mesa_c"] or material.get("mesa_c")
            c["densidade_g_cm3"] = material.get("densidade_g_cm3")
            c["diametro_filamento"] = material.get("diametro_mm") or c["diametro_filamento"]
        return self._pedir("/fatiar", {"stl_b64": base64.b64encode(stl).decode("ascii"), "config": c})


# ══ Biblioteca dos participantes ═════════════════════════════════════════════════════════════════
ESQUEMA = """
CREATE TABLE IF NOT EXISTS p3d_participante (
  usuario TEXT PRIMARY KEY, nome_publico TEXT NOT NULL, consentimento REAL NOT NULL, versao_termo TEXT NOT NULL,
  removido INTEGER NOT NULL DEFAULT 0, criado REAL NOT NULL);
CREATE TABLE IF NOT EXISTS p3d_peca (
  id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, descricao TEXT NOT NULL DEFAULT '', autor TEXT NOT NULL,
  material TEXT NOT NULL DEFAULT '', licenca TEXT NOT NULL DEFAULT '', estado TEXT NOT NULL DEFAULT 'rascunho',
  origem INTEGER, curada INTEGER NOT NULL DEFAULT 0, curada_por TEXT NOT NULL DEFAULT '', curada_nota TEXT NOT NULL DEFAULT '',
  oculta INTEGER NOT NULL DEFAULT 0, oculta_motivo TEXT NOT NULL DEFAULT '', publicada REAL, criado REAL NOT NULL, atualizado REAL NOT NULL);
CREATE TABLE IF NOT EXISTS p3d_revisao (
  id INTEGER PRIMARY KEY AUTOINCREMENT, peca INTEGER NOT NULL, numero INTEGER NOT NULL, autor TEXT NOT NULL,
  arquivo_sha256 TEXT NOT NULL, arquivo_nome TEXT NOT NULL, arquivo_bytes INTEGER NOT NULL, nota TEXT NOT NULL DEFAULT '',
  material TEXT NOT NULL DEFAULT '', config TEXT NOT NULL DEFAULT '{}', medidas TEXT NOT NULL DEFAULT '{}',
  resultado TEXT NOT NULL DEFAULT '', problemas TEXT NOT NULL DEFAULT '[]', resultado_nota TEXT NOT NULL DEFAULT '',
  resultado_em REAL, criado REAL NOT NULL, conteudo TEXT NOT NULL, resumo TEXT NOT NULL, resumo_resultado TEXT NOT NULL DEFAULT '',
  UNIQUE (peca, numero));
CREATE TABLE IF NOT EXISTS p3d_foto (
  id INTEGER PRIMARY KEY AUTOINCREMENT, peca INTEGER NOT NULL, revisao INTEGER NOT NULL, sha256 TEXT NOT NULL,
  tipo TEXT NOT NULL, legenda TEXT NOT NULL DEFAULT '', autor TEXT NOT NULL, criado REAL NOT NULL);
CREATE TABLE IF NOT EXISTS p3d_topico (
  id INTEGER PRIMARY KEY AUTOINCREMENT, peca INTEGER, titulo TEXT NOT NULL, autor TEXT NOT NULL, criado REAL NOT NULL,
  oculto INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS p3d_mensagem (
  id INTEGER PRIMARY KEY AUTOINCREMENT, topico INTEGER NOT NULL, autor TEXT NOT NULL, texto TEXT NOT NULL, criado REAL NOT NULL,
  oculta INTEGER NOT NULL DEFAULT 0, oculta_motivo TEXT NOT NULL DEFAULT '', oculta_por TEXT NOT NULL DEFAULT '');
CREATE TRIGGER IF NOT EXISTS p3d_revisao_sem_delete BEFORE DELETE ON p3d_revisao
  BEGIN SELECT RAISE(ABORT, 'revisao nao se apaga: publique uma nova'); END;
"""

_TIPOS_FOTO = ((b"\xff\xd8\xff", "image/jpeg", "jpg"), (b"\x89PNG\r\n\x1a\n", "image/png", "png"))


def pasta_padrao(banco: str | os.PathLike) -> Path:
    """PHYSIS_3D_PASTA ou a pasta do banco + /impressao3d (mesmo padrão de PHYSIS_EDITAIS_PASTA)."""
    return Path(os.environ.get("PHYSIS_3D_PASTA") or (Path(banco).resolve().parent / "impressao3d"))


def _eh_equipe(quem: dict | None) -> bool:
    from . import seguranca as seg
    return bool(quem) and seg.pode(quem, seg.EQUIPE)


def _texto(v, n: int) -> str:
    return str(v or "").strip()[:n]


class Impressao3D:
    def __init__(self, hub, pasta: str | os.PathLike, fatiador: Fatiador | None = None, relogio=None, perfis_mat: dict | None = None):
        self.hub = hub
        self.pasta = Path(pasta)
        self.relogio = relogio or hub.relogio
        self.fatiador = fatiador or Fatiador()
        self.perfis = perfis_mat if perfis_mat is not None else perfis()
        with hub._trava:
            hub._db.executescript(ESQUEMA)
            hub._db.commit()

    @property
    def _db(self):
        return self.hub._db

    # ── arquivos em disco (pelo resumo; o mesmo arquivo não se repete) ─────────────────────────────
    def _caminho(self, sha: str, ext: str) -> Path:
        return self.pasta / "arquivos" / sha[:2] / f"{sha}.{ext}"

    def _guardar(self, dados: bytes, ext: str) -> str:
        sha = hashlib.sha256(dados).hexdigest()
        alvo = self._caminho(sha, ext)
        if not alvo.is_file():
            alvo.parent.mkdir(parents=True, exist_ok=True)
            tmp = alvo.with_suffix(alvo.suffix + f".{secrets.token_hex(4)}.tmp")
            tmp.write_bytes(dados)
            os.replace(tmp, alvo)                   # troca atômica (Linux e Windows)
        return sha

    def arquivo(self, sha: str, quem: dict | None) -> tuple[str, str, bytes] | None:
        if not re.fullmatch(r"[0-9a-f]{64}", sha or ""):
            return None
        r = self._db.execute("SELECT peca, arquivo_nome FROM p3d_revisao WHERE arquivo_sha256=? LIMIT 1", (sha,)).fetchone()
        if r:
            nome, ext = r[1], formato_de(r[1])
        else:
            f = self._db.execute("SELECT peca, tipo FROM p3d_foto WHERE sha256=? LIMIT 1", (sha,)).fetchone()
            if not f:
                return None
            r, ext = f, {"image/jpeg": "jpg", "image/png": "png"}[f[1]]
            nome = f"foto-{sha[:12]}.{ext}"
        p = self._ler_peca(r[0])
        if not p or not self._ve(p, quem):
            return None
        alvo = self._caminho(sha, ext)
        if not alvo.is_file():
            return None
        tipo = {"stl": "model/stl", "obj": "model/obj", "3mf": "model/3mf", "jpg": "image/jpeg", "png": "image/png"}[ext]
        return nome, tipo, alvo.read_bytes()

    # ── participantes (LGPD) ─────────────────────────────────────────────────────────────────────
    def participante(self, usuario: str) -> dict | None:
        r = self._db.execute("SELECT usuario, nome_publico, consentimento, versao_termo, removido FROM p3d_participante WHERE usuario=?",
                             (usuario,)).fetchone()
        return dict(zip(("usuario", "nome_publico", "consentimento", "versao_termo", "removido"), r)) if r else None

    def aderir(self, usuario: str, d: dict) -> dict:
        if not isinstance(d, dict) or d.get("consentimento") is not True:
            return {"ok": False, "erro": "é preciso aceitar a publicação do seu nome público (LGPD)", "finalidade": FINALIDADE}
        nome = _texto(d.get("nome_publico"), 80)
        if len(nome) < 2:
            return {"ok": False, "erro": "escolha um nome público (pode ser apelido)"}
        with self.hub._trava:
            self._db.execute("INSERT INTO p3d_participante(usuario,nome_publico,consentimento,versao_termo,removido,criado) VALUES(?,?,?,?,0,?) "
                             "ON CONFLICT(usuario) DO UPDATE SET nome_publico=excluded.nome_publico, consentimento=excluded.consentimento, "
                             "versao_termo=excluded.versao_termo, removido=0", (usuario, nome, self.relogio(), VERSAO_TERMO, self.relogio()))
            self.hub.registrar("impressao3d", usuario, {"o_que": "consentimento", "termo": VERSAO_TERMO})
            self._db.commit()
        return {"ok": True}

    def remover_participante(self, usuario: str) -> dict:
        """LGPD (art. 18 VI): o nome público sai de tudo; as peças publicadas seguem sob a licença, como 'participante removido'."""
        with self.hub._trava:
            cur = self._db.execute("UPDATE p3d_participante SET nome_publico='Participante removido', removido=1 WHERE usuario=?", (usuario,))
            if cur.rowcount:
                self.hub.registrar("impressao3d", usuario, {"o_que": "nome removido (LGPD)"})
            self._db.commit()
        return {"ok": cur.rowcount > 0}

    def _nome(self, usuario: str) -> str:
        p = self.participante(usuario)
        return p["nome_publico"] if p else "Participante"

    def _consentiu(self, usuario: str) -> bool:
        p = self.participante(usuario)
        return bool(p and not p["removido"] and p["versao_termo"] == VERSAO_TERMO)

    # ── peças ────────────────────────────────────────────────────────────────────────────────────
    COLS = ("id", "nome", "descricao", "autor", "material", "licenca", "estado", "origem", "curada", "curada_por", "curada_nota",
            "oculta", "oculta_motivo", "publicada", "criado", "atualizado")

    def _ler_peca(self, ident) -> dict | None:
        try:
            r = self._db.execute("SELECT " + ",".join(self.COLS) + " FROM p3d_peca WHERE id=?", (int(ident),)).fetchone()
        except (TypeError, ValueError):
            return None
        return dict(zip(self.COLS, r)) if r else None

    def _ve(self, p: dict, quem: dict | None) -> bool:
        if not quem:
            return False
        if _eh_equipe(quem) or p["autor"] == quem.get("usuario"):
            return True
        return p["estado"] == "publicada" and not p["oculta"]

    def criar(self, d: dict, quem: dict) -> dict:
        nome = _texto(d.get("nome"), 120)
        if len(nome) < 3:
            return {"ok": False, "erro": "dê um nome à peça (3 letras ou mais)"}
        mat = str(d.get("material") or "")
        if mat and mat not in MATERIAIS:
            return {"ok": False, "erro": "material: " + ", ".join(MATERIAIS)}
        agora = self.relogio()
        with self.hub._trava:
            cur = self._db.execute("INSERT INTO p3d_peca(nome,descricao,autor,material,criado,atualizado) VALUES(?,?,?,?,?,?)",
                                   (nome, _texto(d.get("descricao"), 4000), quem["usuario"], mat, agora, agora))
            self.hub.registrar("impressao3d", quem["usuario"], {"o_que": "peça criada", "id": cur.lastrowid})
            self._db.commit()
        return {"ok": True, "id": cur.lastrowid, "estado": "rascunho"}

    def derivar(self, ident: int, quem: dict) -> dict:
        """Melhoria de outra pessoa: peça nova que aponta para a original e começa da última revisão dela."""
        p = self._ler_peca(ident)
        if not p or not self._ve(p, quem) or p["estado"] != "publicada":
            return {"ok": False, "erro": "peça não encontrada", "codigo": 404}
        r = self.criar({"nome": (p["nome"] + " (melhoria)")[:120], "descricao": f"Derivada da peça {p['id']} ({p['licenca']}).",
                        "material": p["material"]}, quem)
        if not r["ok"]:
            return r
        ult = self._db.execute("SELECT arquivo_sha256, arquivo_nome, arquivo_bytes, material, config, medidas FROM p3d_revisao WHERE peca=? "
                               "ORDER BY numero DESC LIMIT 1", (p["id"],)).fetchone()
        with self.hub._trava:
            self._db.execute("UPDATE p3d_peca SET origem=? WHERE id=?", (p["id"], r["id"]))
            self._db.commit()
        if ult:
            dados = self._caminho(ult[0], formato_de(ult[1])).read_bytes()
            self.revisar(r["id"], {"arquivo": dados, "arquivo_nome": ult[1], "material": ult[3], "config": json.loads(ult[4]),
                                   "nota": f"Ponto de partida: última revisão da peça {p['id']}."}, quem)
        return dict(r, origem=p["id"])

    def publicar(self, ident: int, d: dict, quem: dict) -> dict:
        p = self._ler_peca(ident)
        if not p or (p["autor"] != quem["usuario"]):
            return {"ok": False, "erro": "só o autor publica a peça", "codigo": 403}
        lic = str((d or {}).get("licenca") or "")
        if lic not in LICENCAS:
            return {"ok": False, "erro": "escolha uma licença aberta: " + ", ".join(LICENCAS)}
        if (d or {}).get("consentimento") is not True or not self._consentiu(quem["usuario"]):
            return {"ok": False, "erro": "é preciso aceitar a publicação (LGPD) antes", "finalidade": FINALIDADE}
        if not self._db.execute("SELECT 1 FROM p3d_revisao WHERE peca=?", (p["id"],)).fetchone():
            return {"ok": False, "erro": "envie o arquivo (a primeira revisão) antes de publicar"}
        with self.hub._trava:
            self._db.execute("UPDATE p3d_peca SET estado='publicada', licenca=?, publicada=?, atualizado=? WHERE id=?",
                             (lic, self.relogio(), self.relogio(), p["id"]))
            self.hub.registrar("impressao3d", quem["usuario"], {"o_que": "peça publicada", "id": p["id"], "licenca": lic})
            self._db.commit()
        return {"ok": True, "estado": "publicada", "licenca": lic}

    def curar(self, ident: int, d: dict, quem: dict) -> dict:
        if not _eh_equipe(quem):
            return {"ok": False, "erro": "só a equipe da Physis faz a curadoria", "codigo": 403}
        p = self._ler_peca(ident)
        if not p:
            return {"ok": False, "erro": "peça não encontrada", "codigo": 404}
        cur_ = 1 if (d or {}).get("curada", True) else 0
        with self.hub._trava:
            self._db.execute("UPDATE p3d_peca SET curada=?, curada_por=?, curada_nota=?, atualizado=? WHERE id=?",
                             (cur_, quem["usuario"], _texto((d or {}).get("nota"), 600), self.relogio(), p["id"]))
            self.hub.registrar("impressao3d", quem["usuario"], {"o_que": "curadoria", "id": p["id"], "curada": cur_})
            self._db.commit()
        return {"ok": True, "curada": bool(cur_)}

    def moderar(self, alvo: str, ident: int, d: dict, quem: dict) -> dict:
        if not _eh_equipe(quem):
            return {"ok": False, "erro": "só a equipe da Physis modera", "codigo": 403}
        oculta = 1 if (d or {}).get("oculta", True) else 0
        motivo = _texto((d or {}).get("motivo"), 400)
        if oculta and not motivo:
            return {"ok": False, "erro": "diga o motivo"}
        tabela = {"peca": ("p3d_peca", "oculta", "oculta_motivo"), "mensagem": ("p3d_mensagem", "oculta", "oculta_motivo")}[alvo]
        with self.hub._trava:
            cur = self._db.execute(f"UPDATE {tabela[0]} SET {tabela[1]}=?, {tabela[2]}=? WHERE id=?", (oculta, motivo, int(ident)))
            if alvo == "mensagem" and cur.rowcount:
                self._db.execute("UPDATE p3d_mensagem SET oculta_por=? WHERE id=?", (quem["usuario"], int(ident)))
            if cur.rowcount:
                self.hub.registrar("impressao3d", quem["usuario"], {"o_que": "moderação", "alvo": alvo, "id": int(ident), "oculta": oculta})
            self._db.commit()
        return {"ok": cur.rowcount > 0}

    # ── revisões ─────────────────────────────────────────────────────────────────────────────────
    def _anterior(self, peca: int) -> tuple[int, str]:
        r = self._db.execute("SELECT numero, resumo FROM p3d_revisao WHERE peca=? ORDER BY numero DESC LIMIT 1", (peca,)).fetchone()
        return (r[0], r[1]) if r else (0, "0" * 64)

    def revisar(self, ident: int, d: dict, quem: dict) -> dict:
        """Nova revisão: arquivo (bytes ou arquivo_b64), nome do arquivo, nota do que mudou, material e configuração.
        Mede a malha no servidor (as variáveis do aviso saem do arquivo, não do que a pessoa digitou)."""
        p = self._ler_peca(ident)
        if not p or p["autor"] != quem["usuario"]:
            return {"ok": False, "erro": "só o autor envia revisões (para melhorar a peça de outra pessoa, use Derivar)", "codigo": 403}
        dados = d.get("arquivo") if isinstance(d.get("arquivo"), (bytes, bytearray)) else None   # bytes só de dentro (derivar)
        if dados is None:
            try:
                dados = base64.b64decode(str(d.get("arquivo_b64") or ""), validate=True)
            except (binascii.Error, ValueError):
                return {"ok": False, "erro": "arquivo inválido"}
        if not dados or len(dados) > ARQ_MAX:
            return {"ok": False, "erro": "arquivo vazio ou maior que 40 MB"}
        nome = str(d.get("arquivo_nome") or "").replace("\\", "/").rsplit("/", 1)[-1][:120]
        try:
            tris = ler_malha(dados, nome)
            med = medir(tris)
        except (MalhaInvalida, ValueError, KeyError, IndexError, struct.error, ET.ParseError) as e:
            return {"ok": False, "erro": f"não consegui ler a malha: {e}"}
        mat = str(d.get("material") or p["material"] or "")
        if mat and mat not in MATERIAIS:
            return {"ok": False, "erro": "material: " + ", ".join(MATERIAIS)}
        cfg = config(d.get("config"))
        sha = self._guardar(dados, formato_de(nome))
        medidas = {"tamanho_mm": max(med["tamanho"]), "tamanho": med["tamanho"], "volume_mm3": med["volume_mm3"], "area_mm2": med["area_mm2"],
                   "balanco_fracao": med["balanco_fracao"], "triangulos": med["triangulos"], "fechada": med["arestas"]["fechada"],
                   "arestas_abertas": med["arestas"]["abertas"], "arestas_nao_manifold": med["arestas"]["nao_manifold"]}
        with self.hub._trava:
            num, ant = self._anterior(p["id"])
            registro = {"esquema": "physis-3d-revisao/1", "peca": p["id"], "numero": num + 1, "autor": quem["usuario"],
                        "arquivo_sha256": sha, "arquivo_nome": nome, "arquivo_bytes": len(dados), "nota": _texto(d.get("nota"), 4000),
                        "material": mat, "config": cfg, "medidas": medidas, "criado": self.relogio(), "anterior": ant}
            res = integridade.resumo(registro)
            cur = self._db.execute(
                "INSERT INTO p3d_revisao(peca,numero,autor,arquivo_sha256,arquivo_nome,arquivo_bytes,nota,material,config,medidas,criado,conteudo,resumo) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (p["id"], num + 1, quem["usuario"], sha, nome, len(dados), registro["nota"], mat, json.dumps(cfg), json.dumps(medidas),
                 registro["criado"], integridade._canonico(registro).decode("utf-8"), res))
            self._db.execute("UPDATE p3d_peca SET atualizado=?, material=COALESCE(NULLIF(?,''), material) WHERE id=?", (self.relogio(), mat, p["id"]))
            self.hub.registrar("impressao3d", quem["usuario"], {"o_que": "revisão", "peca": p["id"], "numero": num + 1, "resumo": res})
            self._db.commit()
        out = {"ok": True, "revisao": cur.lastrowid, "numero": num + 1, "arquivo_sha256": sha, "resumo": res, "medidas": medidas}
        if "resultado" in d:
            rr = self.resultado(p["id"], {"numero": num + 1, **{k: d.get(k) for k in ("resultado", "problemas", "resultado_nota")}}, quem)
            out["resultado"] = rr
        return out

    def resultado(self, ident: int, d: dict, quem: dict) -> dict:
        """Resultado da impressão (uma vez por revisão): ok, parcial ou falha, problemas e nota. Ganha resumo próprio,
        encadeado no resumo da revisão."""
        p = self._ler_peca(ident)
        if not p or p["autor"] != quem["usuario"]:
            return {"ok": False, "erro": "só o autor registra o resultado", "codigo": 403}
        res = str(d.get("resultado") or "")
        if res not in RESULTADOS:
            return {"ok": False, "erro": "resultado: " + ", ".join(RESULTADOS)}
        probs = d.get("problemas") or []
        if not isinstance(probs, list) or any(x not in PROBLEMAS for x in probs):
            return {"ok": False, "erro": "problemas: " + ", ".join(PROBLEMAS)}
        if res == "ok" and probs:
            res = "parcial"
        try:
            numero = int(d.get("numero"))
        except (TypeError, ValueError):
            return {"ok": False, "erro": "qual revisão?"}
        with self.hub._trava:
            r = self._db.execute("SELECT id, resumo, resultado FROM p3d_revisao WHERE peca=? AND numero=?", (p["id"], numero)).fetchone()
            if not r:
                return {"ok": False, "erro": "revisão não encontrada", "codigo": 404}
            if r[2]:
                return {"ok": False, "erro": "o resultado desta revisão já foi registrado: imprima de novo como nova revisão"}
            nota = _texto(d.get("resultado_nota"), 2000)
            reg = {"esquema": "physis-3d-resultado/1", "revisao": r[1], "resultado": res, "problemas": sorted(set(probs)), "nota": nota,
                   "quando": self.relogio()}
            rs = integridade.resumo(reg)
            self._db.execute("UPDATE p3d_revisao SET resultado=?, problemas=?, resultado_nota=?, resultado_em=?, resumo_resultado=? WHERE id=?",
                             (res, json.dumps(reg["problemas"]), nota, reg["quando"], rs, r[0]))
            self.hub.registrar("impressao3d", quem["usuario"], {"o_que": "resultado", "peca": p["id"], "numero": numero, "resultado": res})
            self._db.commit()
        return {"ok": True, "resultado": res, "resumo_resultado": rs}

    def foto(self, ident: int, d: dict, quem: dict) -> dict:
        """Foto real da peça impressa, por revisão (JPEG ou PNG; o tipo vem dos bytes, não do nome)."""
        p = self._ler_peca(ident)
        if not p or p["autor"] != quem["usuario"]:
            return {"ok": False, "erro": "só o autor envia fotos da própria peça", "codigo": 403}
        try:
            dados = base64.b64decode(str(d.get("foto_b64") or ""), validate=True)
        except (binascii.Error, ValueError):
            return {"ok": False, "erro": "foto inválida"}
        if not dados or len(dados) > FOTO_MAX:
            return {"ok": False, "erro": "foto vazia ou maior que 8 MB"}
        tipo = next(((t, e) for m, t, e in _TIPOS_FOTO if dados.startswith(m)), None)
        if not tipo:
            return {"ok": False, "erro": "foto em JPEG ou PNG"}
        r = self._db.execute("SELECT id FROM p3d_revisao WHERE peca=? AND numero=?", (p["id"], int(d.get("numero") or 0))).fetchone()
        if not r:
            return {"ok": False, "erro": "revisão não encontrada", "codigo": 404}
        sha = self._guardar(dados, tipo[1])
        with self.hub._trava:
            cur = self._db.execute("INSERT INTO p3d_foto(peca,revisao,sha256,tipo,legenda,autor,criado) VALUES(?,?,?,?,?,?,?)",
                                   (p["id"], r[0], sha, tipo[0], _texto(d.get("legenda"), 200), quem["usuario"], self.relogio()))
            self.hub.registrar("impressao3d", quem["usuario"], {"o_que": "foto", "peca": p["id"], "sha256": sha})
            self._db.commit()
        return {"ok": True, "id": cur.lastrowid, "sha256": sha}

    RCOLS = ("id", "peca", "numero", "autor", "arquivo_sha256", "arquivo_nome", "arquivo_bytes", "nota", "material", "config", "medidas",
             "resultado", "problemas", "resultado_nota", "resultado_em", "criado", "conteudo", "resumo", "resumo_resultado")

    def _revisoes(self, peca: int | None = None) -> list[dict]:
        q = "SELECT " + ",".join(self.RCOLS) + " FROM p3d_revisao" + (" WHERE peca=?" if peca is not None else "") + " ORDER BY peca, numero"
        out = []
        for r in self._db.execute(q, (peca,) if peca is not None else ()):
            x = dict(zip(self.RCOLS, r))
            x["config"], x["medidas"], x["problemas"] = json.loads(x["config"]), json.loads(x["medidas"]), json.loads(x["problemas"])
            out.append(x)
        return out

    @staticmethod
    def conferir_revisao(r: dict) -> bool:
        return integridade.resumo(json.loads(r["conteudo"])) == r["resumo"]

    # ── leitura ──────────────────────────────────────────────────────────────────────────────────
    def _publica(self, p: dict, quem: dict | None) -> dict:
        out = {k: p[k] for k in ("id", "nome", "descricao", "material", "licenca", "estado", "origem", "curada", "curada_nota", "publicada", "atualizado")}
        out["licenca_nome"] = LICENCAS.get(p["licenca"], "")
        out["autor_nome"] = self._nome(p["autor"])
        out["minha"] = bool(quem and p["autor"] == quem.get("usuario"))
        if _eh_equipe(quem):
            out.update(oculta=bool(p["oculta"]), oculta_motivo=p["oculta_motivo"], autor=p["autor"])
        return out

    def listar(self, quem: dict | None, busca: str = "", material: str = "") -> dict:
        busca = (busca or "").strip().lower()[:80]
        out = []
        for (i,) in self._db.execute("SELECT id FROM p3d_peca ORDER BY curada DESC, atualizado DESC").fetchall():
            p = self._ler_peca(i)
            if not self._ve(p, quem) or (material and p["material"] != material):
                continue
            if busca and busca not in (p["nome"] + " " + p["descricao"]).lower():
                continue
            x = self._publica(p, quem)
            rv = self._db.execute("SELECT COUNT(*), SUM(resultado='ok'), SUM(resultado='falha') FROM p3d_revisao WHERE peca=?", (i,)).fetchone()
            x.update(revisoes=rv[0], ok=rv[1] or 0, falhas=rv[2] or 0)
            out.append(x)
        return {"ok": True, "pecas": out, "licencas": LICENCAS, "materiais": {k: v.get("nome", k) for k, v in self.perfis.items()},
                "problemas": PROBLEMAS, "resultados": RESULTADOS, "estado": ESTADO}

    def peca(self, ident: int, quem: dict | None) -> dict:
        p = self._ler_peca(ident)
        if not p or not self._ve(p, quem):
            return {"ok": False, "erro": "peça não encontrada", "codigo": 404}
        revs = []
        for r in self._revisoes(p["id"]):
            fotos = [{"sha256": s, "legenda": l} for s, l in self._db.execute("SELECT sha256, legenda FROM p3d_foto WHERE revisao=? ORDER BY id", (r["id"],))]
            revs.append({k: r[k] for k in ("numero", "arquivo_sha256", "arquivo_nome", "arquivo_bytes", "nota", "material", "config", "medidas",
                                            "resultado", "problemas", "resultado_nota", "criado", "resumo", "resumo_resultado")}
                        | {"autor_nome": self._nome(r["autor"]), "fotos": fotos, "confere": self.conferir_revisao(r)})
        return {"ok": True, "peca": self._publica(p, quem), "revisoes": revs}

    def memorial(self, ident: int, quem: dict | None) -> dict:
        """Memorial de desenvolvimento montado das revisões: o que se tentou, o que deu errado e o que mudou."""
        r = self.peca(ident, quem)
        if not r["ok"]:
            return r
        p, revs = r["peca"], r["revisoes"]
        linhas = [f"# Memorial de desenvolvimento: {p['nome']}", "",
                  f"Peça {p['id']} · autoria: {p['autor_nome']} · licença: {p['licenca'] or 'não publicada'}"
                  + (f" · derivada da peça {p['origem']}" if p["origem"] else "") + (" · curada pela Physis" if p["curada"] else ""), ""]
        if p["descricao"]:
            linhas += [p["descricao"], ""]
        aprendizados = []
        for i, v in enumerate(revs):
            mat = (self.perfis.get(v["material"]) or {}).get("nome", v["material"] or "material não informado")
            c = v["config"]
            linhas += [f"## Revisão {v['numero']}", "",
                       f"- Arquivo: {v['arquivo_nome']} (SHA-256 {v['arquivo_sha256']})",
                       f"- Material: {mat}; camada {c.get('altura_camada')} mm; {int(c.get('paredes') or 0)} paredes; preenchimento {round(100 * (c.get('preenchimento') or 0))} %"
                       + (f"; bico {c['bico_c']} °C" if c.get("bico_c") else "") + (f"; mesa {c['mesa_c']} °C" if c.get("mesa_c") else ""),
                       f"- Medidas: {' × '.join(f'{x:.1f}' for x in v['medidas'].get('tamanho', []))} mm; balanço {100 * v['medidas'].get('balanco_fracao', 0):.1f} % da área"
                       + ("" if v["medidas"].get("fechada", True) else "; malha ABERTA (conferir antes de imprimir)"),
                       f"- O que mudou: {v['nota'] or '(sem nota)'}",
                       f"- Resultado: {RESULTADOS.get(v['resultado'], 'não registrado')}"
                       + (" — " + ", ".join(PROBLEMAS[x].lower() for x in v["problemas"]) if v["problemas"] else "")
                       + (f". {v['resultado_nota']}" if v["resultado_nota"] else ""),
                       f"- Fotos: {len(v['fotos'])}",
                       f"- Integridade: {v['resumo']}" + (" (confere)" if v["confere"] else " (NÃO CONFERE)"), ""]
            if v["problemas"] and i + 1 < len(revs):
                aprendizados.append(f"Revisão {v['numero']}: {', '.join(PROBLEMAS[x].lower() for x in v['problemas'])} → "
                                    f"revisão {revs[i + 1]['numero']}: {revs[i + 1]['nota'] or '(sem nota)'}"
                                    f" ({RESULTADOS.get(revs[i + 1]['resultado'], 'resultado não registrado')})")
        linhas += ["## Para quem vai imprimir pela primeira vez", ""] + ([f"- {a}" for a in aprendizados] or ["- Nenhum problema registrado ainda."])
        return {"ok": True, "peca": p, "revisoes": len(revs), "aprendizados": aprendizados, "texto": "\n".join(linhas) + "\n",
                "integridade_ok": all(v["confere"] for v in revs)}

    # ── avisos ───────────────────────────────────────────────────────────────────────────────────
    def treino(self) -> tuple[list[dict], dict]:
        """Revisões com resultado (de peças não ocultas) e o mapa (peça, número) → o que mudou na revisão seguinte."""
        ocultas = {i for (i,) in self._db.execute("SELECT id FROM p3d_peca WHERE oculta=1")}
        revs = [r for r in self._revisoes() if r["peca"] not in ocultas]
        por = {(r["peca"], r["numero"]): r for r in revs}
        mud = {}
        for (pc, n), r in por.items():
            prox = por.get((pc, n + 1))
            if prox and prox["nota"]:
                mud[(pc, n)] = prox["nota"]
        linhas = [{"peca": r["peca"], "numero": r["numero"], "material": r["material"], "config": r["config"], "resultado": r["resultado"],
                   "problemas": r["problemas"], "balanco_fracao": r["medidas"].get("balanco_fracao"), "tamanho_mm": r["medidas"].get("tamanho_mm")}
                  for r in revs if r["resultado"]]
        return linhas, mud

    def avisos(self, d: dict) -> dict:
        linhas, mud = self.treino()
        return AvisosNB(linhas, self.perfis).avisar({"material": d.get("material"), "config": d.get("config") or {},
                                                     "balanco_fracao": d.get("balanco_fracao"), "tamanho_mm": d.get("tamanho_mm"),
                                                     "espessura_parede_mm": d.get("espessura_parede_mm")}, mud)

    # ── fórum ────────────────────────────────────────────────────────────────────────────────────
    def topicos(self, quem: dict, peca: int | None = None) -> dict:
        if peca is not None:
            p = self._ler_peca(peca)
            if not p or not self._ve(p, quem):
                return {"ok": False, "erro": "peça não encontrada", "codigo": 404}
        eq = _eh_equipe(quem)
        q = "SELECT t.id, t.peca, t.titulo, t.autor, t.criado, t.oculto, COUNT(m.id), MAX(m.criado) FROM p3d_topico t LEFT JOIN p3d_mensagem m ON m.topico=t.id "
        q += ("WHERE t.peca=? " if peca is not None else "WHERE t.peca IS NULL ") + "GROUP BY t.id ORDER BY MAX(m.criado) DESC"
        out = []
        for i, pc, tit, aut, cr, oc, n, ult in self._db.execute(q, (peca,) if peca is not None else ()):
            if oc and not eq:
                continue
            out.append({"id": i, "peca": pc, "titulo": tit, "autor_nome": self._nome(aut), "criado": cr, "mensagens": n, "ultima": ult})
        return {"ok": True, "topicos": out}

    def abrir_topico(self, d: dict, quem: dict) -> dict:
        if not self._consentiu(quem["usuario"]):
            return {"ok": False, "erro": "aceite a publicação do seu nome público (LGPD) antes de escrever", "finalidade": FINALIDADE}
        peca = d.get("peca")
        if peca not in (None, ""):
            p = self._ler_peca(peca)
            if not p or not self._ve(p, quem):
                return {"ok": False, "erro": "peça não encontrada", "codigo": 404}
            peca = p["id"]
        else:
            peca = None
        tit, txt = _texto(d.get("titulo"), 160), _texto(d.get("texto"), 8000)
        if len(tit) < 3 or len(txt) < 2:
            return {"ok": False, "erro": "título e mensagem"}
        with self.hub._trava:
            cur = self._db.execute("INSERT INTO p3d_topico(peca,titulo,autor,criado) VALUES(?,?,?,?)", (peca, tit, quem["usuario"], self.relogio()))
            self._db.execute("INSERT INTO p3d_mensagem(topico,autor,texto,criado) VALUES(?,?,?,?)", (cur.lastrowid, quem["usuario"], txt, self.relogio()))
            self.hub.registrar("impressao3d", quem["usuario"], {"o_que": "tópico", "id": cur.lastrowid, "peca": peca})
            self._db.commit()
        return {"ok": True, "id": cur.lastrowid}

    def _topico_visivel(self, ident: int, quem: dict):
        t = self._db.execute("SELECT id, peca, titulo, oculto FROM p3d_topico WHERE id=?", (int(ident),)).fetchone()
        if not t or (t[3] and not _eh_equipe(quem)):
            return None
        if t[1] is not None:
            p = self._ler_peca(t[1])
            if not p or not self._ve(p, quem):
                return None
        return t

    def mensagens(self, ident: int, quem: dict) -> dict:
        t = self._topico_visivel(ident, quem)
        if not t:
            return {"ok": False, "erro": "tópico não encontrado", "codigo": 404}
        eq = _eh_equipe(quem)
        out = []
        for i, aut, txt, cr, oc, mot in self._db.execute("SELECT id, autor, texto, criado, oculta, oculta_motivo FROM p3d_mensagem WHERE topico=? ORDER BY id", (t[0],)):
            m = {"id": i, "autor_nome": self._nome(aut), "criado": cr, "oculta": bool(oc)}
            m["texto"] = txt if (not oc or eq) else f"Mensagem retirada pela moderação: {mot}"
            if eq and oc:
                m["oculta_motivo"] = mot
            out.append(m)
        return {"ok": True, "topico": {"id": t[0], "peca": t[1], "titulo": t[2]}, "mensagens": out}

    def responder(self, ident: int, d: dict, quem: dict) -> dict:
        if not self._consentiu(quem["usuario"]):
            return {"ok": False, "erro": "aceite a publicação do seu nome público (LGPD) antes de escrever", "finalidade": FINALIDADE}
        t = self._topico_visivel(ident, quem)
        if not t:
            return {"ok": False, "erro": "tópico não encontrado", "codigo": 404}
        txt = _texto(d.get("texto"), 8000)
        if len(txt) < 2:
            return {"ok": False, "erro": "escreva a mensagem"}
        with self.hub._trava:
            cur = self._db.execute("INSERT INTO p3d_mensagem(topico,autor,texto,criado) VALUES(?,?,?,?)", (t[0], quem["usuario"], txt, self.relogio()))
            self._db.commit()
        return {"ok": True, "id": cur.lastrowid}

    # ── fatiar uma revisão no serviço ────────────────────────────────────────────────────────────
    def fatiar_revisao(self, ident: int, d: dict, quem: dict) -> dict:
        p = self._ler_peca(ident)
        if not p or not self._ve(p, quem):
            return {"ok": False, "erro": "peça não encontrada", "codigo": 404}
        r = self._db.execute("SELECT arquivo_sha256, arquivo_nome, material, config FROM p3d_revisao WHERE peca=? AND numero=?",
                             (p["id"], int(d.get("numero") or 0))).fetchone()
        if not r:
            return {"ok": False, "erro": "revisão não encontrada", "codigo": 404}
        dados = self._caminho(r[0], formato_de(r[1])).read_bytes()
        stl = dados if formato_de(r[1]) == "stl" else escrever_stl(ler_malha(dados, r[1]))
        cfg = dict(json.loads(r[3]), **(d.get("config") or {}))
        res = self.fatiador.fatiar(stl, cfg, self.perfis.get(r[2]))
        if res is None:
            return {"ok": False, "codigo": 503, "sem_fatiador": True,
                    "erro": "fatiador do servidor desligado: baixe a malha (STL ou 3MF) e fatie num fatiador aberto (PrusaSlicer, Cura ou OrcaSlicer)."}
        return res

    def fatiar_malha(self, d: dict) -> dict:
        """G-code da malha aberta na tela (STL em base64), sem guardar nada."""
        try:
            stl = base64.b64decode(str(d.get("stl_b64") or ""), validate=True)
            ler_stl(stl)
        except (binascii.Error, ValueError, struct.error) as e:
            return {"ok": False, "erro": f"STL inválido: {e}"}
        if len(stl) > ARQ_MAX:
            return {"ok": False, "erro": "malha maior que 40 MB"}
        res = self.fatiador.fatiar(stl, d.get("config") or {}, self.perfis.get(str(d.get("material") or "")))
        if res is None:
            return {"ok": False, "codigo": 503, "sem_fatiador": True,
                    "erro": "fatiador do servidor desligado: baixe a malha (STL ou 3MF) e fatie num fatiador aberto (PrusaSlicer, Cura ou OrcaSlicer)."}
        return res

    # ── rotas (o servidor chama depois de conferir a sessão: papel cliente ou acima) ─────────────
    def rota(self, metodo: str, caminho: str, quem: dict | None, corpo: bytes | None = None, consulta: dict | None = None):
        """(código, objeto) ou None (rota que não é deste módulo). Objeto ("bytes", nome, tipo, dados) para arquivos."""
        if not caminho.startswith("/api/3d/"):
            return None
        if not quem:
            return 401, {"ok": False, "erro": "entre com usuario e senha", "login": True}
        g = lambda k: ((consulta or {}).get(k) or [""])[0][:80]
        c = caminho[len("/api/3d"):]
        if metodo == "GET":
            if c == "/pecas":
                return 200, self.listar(quem, g("busca"), g("material"))
            if c == "/materiais":
                return 200, {"ok": True, "materiais": self.perfis, "aviso": "Valores típicos de literatura para o polímero virgem: conferir com o fornecedor."}
            if c == "/fatiador":
                s = self.fatiador.disponivel()
                return 200, {"ok": True, "disponivel": bool(s and s.get("ok")), "detalhe": s}
            if c == "/participante":
                return 200, {"ok": True, "participante": self.participante(quem["usuario"]), "finalidade": FINALIDADE, "versao_termo": VERSAO_TERMO}
            if c == "/forum":
                pc = g("peca")
                return self._r(self.topicos(quem, int(pc) if pc.isdigit() else None))
            m = re.fullmatch(r"/forum/(\d{1,12})", c)
            if m:
                return self._r(self.mensagens(int(m.group(1)), quem))
            m = re.fullmatch(r"/pecas/(\d{1,12})(/memorial)?", c)
            if m:
                return self._r(self.memorial(int(m.group(1)), quem) if m.group(2) else self.peca(int(m.group(1)), quem))
            m = re.fullmatch(r"/arquivo/([0-9a-f]{64})", c)
            if m:
                a = self.arquivo(m.group(1), quem)
                return (200, ("bytes",) + a) if a else (404, {"ok": False, "erro": "arquivo não encontrado"})
            return 404, {"ok": False, "erro": "rota desconhecida"}
        if metodo != "POST":
            return 405, {"ok": False, "erro": "método"}
        if corpo is not None and len(corpo) > CORPO_MAX:
            return 413, {"ok": False, "erro": "corpo grande demais"}
        try:
            d = json.loads((corpo or b"{}").decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return 400, {"ok": False, "erro": "json invalido"}
        if not isinstance(d, dict):
            return 400, {"ok": False, "erro": "json invalido"}
        if c == "/participante":
            return self._r(self.aderir(quem["usuario"], d))
        if c == "/participante/remover":
            return self._r(self.remover_participante(quem["usuario"]))
        if c == "/pecas":
            return self._r(self.criar(d, quem))
        if c == "/avisos":
            return self._r(self.avisos(d))
        if c == "/fatiar":
            return self._r(self.fatiar_malha(d))
        if c == "/forum":
            return self._r(self.abrir_topico(d, quem))
        m = re.fullmatch(r"/forum/(\d{1,12})", c)
        if m:
            return self._r(self.responder(int(m.group(1)), d, quem))
        m = re.fullmatch(r"/forum/mensagem/(\d{1,12})/moderar", c)
        if m:
            return self._r(self.moderar("mensagem", int(m.group(1)), d, quem))
        m = re.fullmatch(r"/pecas/(\d{1,12})/(revisao|resultado|foto|publicar|derivar|curar|moderar|fatiar)", c)
        if not m:
            return 404, {"ok": False, "erro": "rota desconhecida"}
        i, acao = int(m.group(1)), m.group(2)
        return self._r({"revisao": lambda: self.revisar(i, d, quem), "resultado": lambda: self.resultado(i, d, quem),
                        "foto": lambda: self.foto(i, d, quem), "publicar": lambda: self.publicar(i, d, quem),
                        "derivar": lambda: self.derivar(i, quem), "curar": lambda: self.curar(i, d, quem),
                        "moderar": lambda: self.moderar("peca", i, d, quem), "fatiar": lambda: self.fatiar_revisao(i, d, quem)}[acao]())

    @staticmethod
    def _r(r: dict):
        return r.pop("codigo", 200 if r.get("ok") else 400), r
