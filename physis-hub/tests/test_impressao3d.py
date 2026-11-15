"""Physis 3D (EM DESENVOLVIMENTO): impressao3d.py, sistema/physis-3d.js e o serviço servicos/fatiador.

Protege:
1. Malha: STL (texto e binário), OBJ e 3MF (ZIP com deflate, unidade em polegadas, componentes e transformações)
   dão o mesmo cubo; volume, área, balanço e arestas abertas.
2. Fatiamento do cubo de 20 mm a 0,2 mm: 100 camadas, contorno 80 mm e área 400 mm² em cada uma; filamento,
   massa e tempo pela fórmula; os MESMOS números estão no autoteste da tela (espelho JS, conferido no navegador em
   ferramentas/testes-navegador/teste-physis-3d.html, sem Node).
3. Perfis de material: cinco premissas "conferir" com fonte [CONFERIR]; a cópia de reserva da tela é igual.
4. Biblioteca: consentimento LGPD, licença aberta, rascunho invisível para os outros, revisões com resumo de
   integridade encadeado, resultado uma vez, foto pelo tipo dos bytes, derivada, curadoria e moderação só da equipe,
   memorial montado das revisões, fórum, remoção do nome (LGPD), arquivo em disco pela pasta configurada.
5. Avisos: Naive Bayes com dados sintéticos (rHDPE grande empena; PLA pequeno dá certo); com poucos dados, diz.
6. Fatiador: sem serviço devolve None e a rota responde 503 com o caminho aberto; com um fatiador falso, G-code.
   Serviço: .ini do PrusaSlicer e leitura das estimativas do G-code, com um executável falso.
7. Rotas: sem sessão 401; JSON inválido 400; rota desconhecida 404; arquivo como bytes.
8. Contrato da tela e portabilidade (Linux): um só <h1>, selo, sem internet, sem biblioteca de terceiros, LF.
"""
import base64
import io
import json
import math
import os
import re
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from physis_hub import impressao3d as m3
from physis_hub.hub import Hub

RAIZ = Path(__file__).resolve().parents[2]
JS = RAIZ / "sistema" / "physis-3d.js"
PREM = RAIZ / "sistema" / "physis-3d-premissas.json"
SERV = RAIZ / "servicos" / "fatiador"
if SERV.is_dir() and str(SERV) not in sys.path:
    sys.path.insert(0, str(SERV))

ANA = {"usuario": "ana", "papel": "cliente", "nome": "Ana"}
BIA = {"usuario": "bia", "papel": "cliente", "nome": "Bia"}
EQ = {"usuario": "eq", "papel": "operador", "nome": "Equipe"}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40


def caixa_tris(x0, y0, z0, x1, y1, z1):
    v = [(x, y, z) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    f = [(0, 2, 3), (0, 3, 1), (4, 5, 7), (4, 7, 6), (0, 1, 5), (0, 5, 4), (2, 6, 7), (2, 7, 3), (0, 4, 6), (0, 6, 2), (1, 3, 7), (1, 7, 5)]
    return [tuple(tuple(float(c) for c in v[i]) for i in t) for t in f]


CUBO = caixa_tris(0, 0, 0, 20, 20, 20)


def stl_texto(tris):
    s = "solid c\n"
    for t in tris:
        s += " facet normal 0 0 0\n  outer loop\n" + "".join(f"   vertex {a} {b} {c}\n" for a, b, c in t) + "  endloop\n endfacet\n"
    return (s + "endsolid c\n").encode()


def tres_mf(polegadas=False):
    """Cubo de 20 mm como componente (transladado) de outro objeto, em ZIP com deflate."""
    e = 1 / 25.4 if polegadas else 1.0
    vs = "".join(f'<vertex x="{x * e}" y="{y * e}" z="{z * e}"/>' for z in (0, 20) for y in (0, 20) for x in (0, 20))
    ts = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in
                 [(0, 2, 3), (0, 3, 1), (4, 5, 7), (4, 7, 6), (0, 1, 5), (0, 5, 4), (2, 6, 7), (2, 7, 3), (0, 4, 6), (0, 6, 2), (1, 3, 7), (1, 7, 5)])
    xml = (f'<?xml version="1.0" encoding="UTF-8"?><model unit="{"inch" if polegadas else "millimeter"}" xmlns="{m3.NS_3MF}"><resources>'
           f'<object id="1" type="model"><mesh><vertices>{vs}</vertices><triangles>{ts}</triangles></mesh></object>'
           f'<object id="2" type="model"><components><component objectid="1" transform="1 0 0 0 1 0 0 0 1 {5 * e} 0 0"/></components></object>'
           f'</resources><build><item objectid="2" transform="1 0 0 0 1 0 0 0 1 0 {7 * e} 0"/></build></model>')
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("3D/3dmodel.model", xml)
    return b.getvalue()


def perto(tc, a, b, tol=1e-6):
    tc.assertTrue(abs(a - b) <= tol * max(1.0, abs(b)), f"{a} difere de {b}")


class Malha(unittest.TestCase):
    def test_formatos_dao_o_mesmo_cubo(self):
        obj = b"v 0 0 0\nv 20 0 0\nv 0 20 0\nv 20 20 0\nv 0 0 20\nv 20 0 20\nv 0 20 20\nv 20 20 20\nf 1 3 4 2\nf 5 6 8 7\nf 1/1/1 2 6 5\nf 3 7 8 4\nf 1 5 7 3\nf 2 4 8 6\n"
        for nome, dados in (("c.stl", m3.escrever_stl(CUBO)), ("c.stl", stl_texto(CUBO)), ("c.obj", obj), ("c.3mf", tres_mf()), ("c.3mf", tres_mf(True))):
            with self.subTest(nome):
                t = m3.ler_malha(dados, nome)
                md = m3.medir(t)
                perto(self, md["volume_mm3"], 8000, 1e-5)
                perto(self, md["area_mm2"], 2400, 1e-5)
                self.assertTrue(md["arestas"]["fechada"])
                self.assertEqual(md["volume_sinal"], 1)
        cx = m3.caixa(m3.ler_malha(tres_mf(), "x.3mf"))
        self.assertEqual([round(v, 6) for v in cx["min"]], [5, 7, 0])          # componente (+5 em x) e item (+7 em y)
        with self.assertRaises(m3.MalhaInvalida):
            m3.ler_malha(b"qualquer", "x.step")

    def test_balanco_e_arestas_abertas(self):
        mesa = caixa_tris(-5, -5, 0, 5, 5, 10) + caixa_tris(-15, -15, 10, 15, 15, 12)   # pé e tampo: o fundo do tampo fica no ar
        md = m3.medir(mesa)
        perto(self, md["balanco_area_mm2"], 900)
        perto(self, md["balanco_fracao"], 900 / (600 + 2 * 900 + 4 * 30 * 2))
        self.assertEqual(md["balanco_faces"], 2)
        self.assertEqual(m3.medir(CUBO)["balanco_fracao"], 0)                            # o fundo na mesa não conta
        aberta = m3.medir(CUBO[:-1])["arestas"]
        self.assertEqual(aberta["abertas"], 3)
        self.assertFalse(aberta["fechada"])

    def test_fatiar_e_estimar_o_cubo(self):
        cam = m3.fatiar(CUBO, 0.2)
        self.assertEqual(len(cam), 100)
        for c in cam:
            perto(self, c["perimetro_mm"], 80, 1e-9)
            perto(self, c["area_mm2"], 400, 1e-9)
        e = m3.estimar(cam, None, 1.24)
        w, h = 0.45, 0.2
        parede = 2 * 80 * 100
        dentro = 400 - 80 * 2 * w
        preench = 8 * dentro / w + 92 * dentro / w * 0.2
        vol = (parede + preench) * w * h
        perto(self, e["caminho_parede_mm"], parede)
        perto(self, e["caminho_preench_mm"], preench)
        perto(self, e["filamento_m"], vol / (math.pi * 0.875 ** 2) / 1000)
        perto(self, e["massa_g"], vol / 1000 * 1.24)
        perto(self, e["tempo_h"], ((parede / 40 + preench / 60) * 1.15 + 100 * 2) / 3600)
        # espelho: os mesmos números estão no autoteste de physis-3d.js
        js = JS.read_text(encoding="utf-8")
        for v, texto in ((e["caminho_preench_mm"], "19242.666666666664"), (e["massa_g"], "3.9330816"), (e["tempo_h"], "0.2857827160493827")):
            perto(self, v, float(texto))
            self.assertIn(texto, js)

    def test_fatiar_com_furo(self):
        """Tubo quadrado (furo de 10 mm): a área desconta o furo sem montar os contornos."""
        fora, furo = caixa_tris(0, 0, 0, 20, 20, 4), caixa_tris(5, 5, 0, 15, 15, 4)
        dentro = [(a, c, b) for a, b, c in furo]                                       # faces do furo viradas para dentro
        tubo = [t for t in fora + dentro if len({v[2] for v in t}) > 1]                 # só as paredes: tampas não cortam
        cam = m3.fatiar(tubo, 1.0)
        self.assertEqual(len(cam), 4)
        perto(self, cam[0]["area_mm2"], 400 - 100)
        perto(self, cam[0]["perimetro_mm"], 80 + 40)

    def test_stl_binario_ida_e_volta(self):
        d = m3.escrever_stl(CUBO)
        self.assertEqual(len(d), 84 + 50 * 12)
        self.assertEqual(struct.unpack_from("<I", d, 80)[0], 12)


@unittest.skipUnless(PREM.is_file(), "só no repositório")
class Materiais(unittest.TestCase):
    def test_premissas_conferir(self):
        base = json.loads(PREM.read_text(encoding="utf-8"))
        ids = {p["id"]: p for p in base["premissas"]}
        for k in m3.MATERIAIS:
            p = ids["impressao3d.material." + k]
            self.assertEqual(p["status"], "conferir")
            self.assertIn("[CONFERIR]", p["fonte"])
            for c in ("grandeza", "valor_padrao", "unidade", "fonte", "opcoes"):
                self.assertIn(c, p)
            v = p["valor_padrao"]
            for c in ("densidade_g_cm3", "bico_c", "mesa_c", "contracao_pct", "diametro_mm"):
                self.assertIsInstance(v[c], (int, float), f"{k}.{c}")
            self.assertTrue(v["bico_faixa_c"][0] <= v["bico_c"] <= v["bico_faixa_c"][1])
            self.assertTrue(v["mesa_faixa_c"][0] <= v["mesa_c"] <= v["mesa_faixa_c"][1])
        self.assertEqual(set(m3.perfis()), set(m3.MATERIAIS))

    def test_reserva_da_tela_igual(self):
        js = JS.read_text(encoding="utf-8")
        base = {p["id"].rsplit(".", 1)[-1]: p["valor_padrao"] for p in json.loads(PREM.read_text(encoding="utf-8"))["premissas"]}
        for k, v in base.items():
            m = re.search(rf"\b{k}: \{{ nome:\"([^\"]+)\", densidade_g_cm3:([\d.]+), bico_c:(\d+), bico_faixa_c:\[(\d+), (\d+)\], mesa_c:(\d+), "
                          rf"mesa_faixa_c:\[(\d+), (\d+)\], contracao_pct:([\d.]+), contracao_faixa_pct:\[([\d.]+), ([\d.]+)\], diametro_mm:([\d.]+) \}}", js)
            self.assertIsNotNone(m, k)
            self.assertEqual(m.group(1), v["nome"])
            self.assertEqual([float(x) for x in m.groups()[1:]], [float(x) for x in (v["densidade_g_cm3"], v["bico_c"], *v["bico_faixa_c"], v["mesa_c"],
                                                                                     *v["mesa_faixa_c"], v["contracao_pct"], *v["contracao_faixa_pct"], v["diametro_mm"])])


class FatiadorFalso:
    def __init__(self):
        self.pedidos = []

    def __call__(self, caminho, corpo):
        self.pedidos.append((caminho, corpo))
        if caminho == "/saude":
            return {"ok": True, "fatiador": "falso"}
        return {"ok": True, "gcode": ";FALSO\nG1 X0\n", "estimativa": {"tempo_s": 600, "filamento_mm": 1000, "filamento_g": 3}}


class Biblioteca(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.rel = [1_794_000_000.0]
        self.h = Hub(":memory:", relogio=lambda: self.rel[0])
        self.b = m3.Impressao3D(self.h, Path(self.tmp.name) / "p3d", fatiador=m3.Fatiador(url=""))

    def tearDown(self):
        self.h._db.close()
        self.tmp.cleanup()

    def peca_publicada(self, quem=ANA):
        self.assertTrue(self.b.aderir(quem["usuario"], {"nome_publico": quem["nome"], "consentimento": True})["ok"])
        i = self.b.criar({"nome": "Suporte de vaso", "material": "rpetg"}, quem)["id"]
        r = self.b.revisar(i, {"arquivo_b64": base64.b64encode(m3.escrever_stl(CUBO)).decode(), "arquivo_nome": "suporte.stl", "nota": "primeira"}, quem)
        self.assertTrue(r["ok"], r)
        self.assertTrue(self.b.publicar(i, {"licenca": "CC-BY-SA-4.0", "consentimento": True}, quem)["ok"])
        return i

    def test_lgpd_licenca_e_visibilidade(self):
        i = self.b.criar({"nome": "Gancho", "material": "rpla"}, ANA)["id"]
        self.assertFalse(self.b.peca(i, BIA)["ok"])                                    # rascunho: só o autor e a equipe
        self.assertTrue(self.b.peca(i, EQ)["ok"])
        self.assertIn("arquivo", self.b.publicar(i, {"licenca": "CC-BY-4.0", "consentimento": True}, ANA)["erro"] + "arquivo")
        self.b.revisar(i, {"arquivo_b64": base64.b64encode(m3.escrever_stl(CUBO)).decode(), "arquivo_nome": "g.stl"}, ANA)
        r = self.b.publicar(i, {"licenca": "CC-BY-4.0", "consentimento": True}, ANA)
        self.assertFalse(r["ok"])                                                       # ainda não aderiu (LGPD)
        self.b.aderir("ana", {"nome_publico": "Ana Maker", "consentimento": True})
        self.assertFalse(self.b.publicar(i, {"licenca": "proprietaria", "consentimento": True}, ANA)["ok"])
        self.assertFalse(self.b.publicar(i, {"licenca": "CC-BY-4.0", "consentimento": True}, BIA)["ok"])
        self.assertTrue(self.b.publicar(i, {"licenca": "CC-BY-4.0", "consentimento": True}, ANA)["ok"])
        p = self.b.peca(i, BIA)
        self.assertTrue(p["ok"])
        self.assertEqual(p["peca"]["autor_nome"], "Ana Maker")
        self.assertNotIn("autor", p["peca"])                                            # usuário não sai para os outros
        self.assertFalse(self.b.aderir("bia", {"nome_publico": "Bia"})["ok"])         # sem consentimento
        self.assertEqual(self.b.rota("GET", "/api/3d/pecas", None)[0], 401)

    def test_revisoes_integridade_resultado_e_arquivo(self):
        i = self.peca_publicada()
        r2 = self.b.revisar(i, {"arquivo_b64": base64.b64encode(m3.escrever_stl(caixa_tris(0, 0, 0, 20, 20, 10))).decode(), "arquivo_nome": "v2.stl",
                                "nota": "baixei a altura", "config": {"altura_camada": "0,28", "bico_c": 245}}, ANA)
        self.assertEqual(r2["numero"], 2)
        revs = self.b._revisoes(i)
        self.assertEqual(json.loads(revs[1]["conteudo"])["anterior"], revs[0]["resumo"])  # encadeada
        self.assertTrue(all(self.b.conferir_revisao(r) for r in revs))
        adulterada = dict(revs[0], conteudo=revs[0]["conteudo"].replace("primeira", "outra"))
        self.assertFalse(self.b.conferir_revisao(adulterada))
        perto(self, revs[1]["config"]["altura_camada"], 0.28)
        self.assertEqual(revs[1]["medidas"]["tamanho_mm"], 20)
        with self.assertRaises(Exception):
            self.h._db.execute("DELETE FROM p3d_revisao")
        self.assertFalse(self.b.revisar(i, {"arquivo_b64": "AAAA", "arquivo_nome": "x.stl"}, ANA)["ok"])
        self.assertFalse(self.b.revisar(i, {"arquivo_b64": base64.b64encode(m3.escrever_stl(CUBO)).decode(), "arquivo_nome": "x.stl"}, BIA)["ok"])
        r = self.b.resultado(i, {"numero": 1, "resultado": "falha", "problemas": ["empenamento", "adesao"], "resultado_nota": "soltou da mesa"}, ANA)
        self.assertTrue(r["ok"], r)
        self.assertFalse(self.b.resultado(i, {"numero": 1, "resultado": "ok"}, ANA)["ok"])          # uma vez só
        self.assertEqual(self.b.resultado(i, {"numero": 2, "resultado": "ok", "problemas": ["fios"]}, ANA)["resultado"], "parcial")
        self.assertFalse(self.b.resultado(i, {"numero": 2, "resultado": "talvez"}, ANA)["ok"])
        f = self.b.foto(i, {"numero": 2, "foto_b64": base64.b64encode(PNG).decode(), "legenda": "pronta"}, ANA)
        self.assertTrue(f["ok"], f)
        self.assertFalse(self.b.foto(i, {"numero": 2, "foto_b64": base64.b64encode(b"MZ\x90\x00").decode()}, ANA)["ok"])
        sha = revs[0]["arquivo_sha256"]
        alvo = Path(self.tmp.name) / "p3d" / "arquivos" / sha[:2] / f"{sha}.stl"
        self.assertTrue(alvo.is_file())                                                  # pasta da configuração, pathlib
        self.assertEqual(self.b.arquivo(sha, BIA)[1], "model/stl")
        self.assertEqual(self.b.arquivo(f["sha256"], BIA)[1], "image/png")
        cod, obj = self.b.rota("GET", f"/api/3d/arquivo/{sha}", BIA)
        self.assertEqual((cod, obj[0]), (200, "bytes"))
        mem = self.b.memorial(i, BIA)
        self.assertTrue(mem["integridade_ok"])
        self.assertIn("## Revisão 2", mem["texto"])
        self.assertIn("baixei a altura", mem["aprendizados"][0])
        self.assertIn("empenamento", mem["aprendizados"][0])
        self.assertIn("CC-BY-SA-4.0", mem["texto"])

    def test_derivar_curar_moderar(self):
        i = self.peca_publicada()
        self.b.aderir("bia", {"nome_publico": "Bia", "consentimento": True})
        d = self.b.derivar(i, BIA)
        self.assertTrue(d["ok"], d)
        self.assertEqual(self.b.peca(d["id"], BIA)["peca"]["origem"], i)
        self.assertEqual(len(self.b._revisoes(d["id"])), 1)                            # começa da última revisão da original
        self.assertFalse(self.b.curar(i, {}, BIA)["ok"])
        self.assertTrue(self.b.curar(i, {"nota": "conferida na oficina"}, EQ)["curada"])
        self.assertFalse(self.b.moderar("peca", i, {"oculta": True}, EQ)["ok"])        # sem motivo
        self.assertTrue(self.b.moderar("peca", i, {"oculta": True, "motivo": "arquivo de terceiros"}, EQ)["ok"])
        self.assertFalse(self.b.peca(i, BIA)["ok"])
        self.assertTrue(self.b.peca(i, ANA)["ok"])                                      # o autor ainda vê
        self.assertTrue(self.b.peca(i, EQ)["peca"]["oculta"])

    def test_forum_e_remocao_do_nome(self):
        i = self.peca_publicada()
        self.assertFalse(self.b.abrir_topico({"titulo": "Dúvida", "texto": "oi"}, BIA)["ok"])   # sem consentimento
        self.b.aderir("bia", {"nome_publico": "Bia Recicla", "consentimento": True})
        t = self.b.abrir_topico({"peca": i, "titulo": "Empenou no rHDPE", "texto": "usei borda de 8 mm"}, BIA)
        self.assertTrue(t["ok"])
        g = self.b.abrir_topico({"titulo": "Secar o PET", "texto": "quantas horas?"}, ANA)
        self.assertEqual([x["titulo"] for x in self.b.topicos(ANA, i)["topicos"]], ["Empenou no rHDPE"])
        self.assertEqual([x["titulo"] for x in self.b.topicos(ANA)["topicos"]], ["Secar o PET"])
        self.assertTrue(self.b.responder(g["id"], {"texto": "4 h a 65 °C, conferir"}, BIA)["ok"])
        msgs = self.b.mensagens(g["id"], ANA)["mensagens"]
        self.assertEqual(len(msgs), 2)
        self.assertFalse(self.b.moderar("mensagem", msgs[1]["id"], {"oculta": True, "motivo": "x"}, ANA)["ok"])
        self.assertTrue(self.b.moderar("mensagem", msgs[1]["id"], {"oculta": True, "motivo": "dado pessoal"}, EQ)["ok"])
        self.assertIn("retirada", self.b.mensagens(g["id"], ANA)["mensagens"][1]["texto"])
        self.assertIn("4 h", self.b.mensagens(g["id"], EQ)["mensagens"][1]["texto"])
        self.assertTrue(self.b.remover_participante("bia")["ok"])
        self.assertEqual(self.b.mensagens(g["id"], ANA)["mensagens"][1]["autor_nome"], "Participante removido")
        self.assertFalse(self.b.responder(g["id"], {"texto": "de novo"}, BIA)["ok"])    # precisa aderir outra vez

    def test_fatiador_ausente_e_falso(self):
        i = self.peca_publicada()
        r = self.b.fatiar_revisao(i, {"numero": 1}, ANA)
        self.assertEqual(r["codigo"], 503)
        self.assertIn("fatiador aberto", r["erro"])
        cod, obj = self.b.rota("POST", "/api/3d/fatiar", ANA, json.dumps({"stl_b64": base64.b64encode(m3.escrever_stl(CUBO)).decode()}).encode())
        self.assertEqual(cod, 503)
        falso = FatiadorFalso()
        self.b.fatiador = m3.Fatiador(url="", pedir=falso)
        r = self.b.fatiar_revisao(i, {"numero": 1, "config": {"altura_camada": 0.28}}, ANA)
        self.assertTrue(r["ok"])
        self.assertIn(";FALSO", r["gcode"])
        cfg = falso.pedidos[-1][1]["config"]
        self.assertEqual((cfg["altura_camada"], cfg["bico_c"], cfg["densidade_g_cm3"]), (0.28, 240, 1.27))   # bico e densidade do rPETG
        self.assertTrue(self.b.rota("GET", "/api/3d/fatiador", ANA)[1]["disponivel"])
        self.assertEqual(m3.Fatiador(url="https://fatiador.exemplo.com.br").url, "")   # fora da rede local: recusado

    def test_rotas(self):
        self.assertEqual(self.b.rota("GET", "/api/outra", ANA), None)
        self.assertEqual(self.b.rota("POST", "/api/3d/pecas", ANA, b"{nao json")[0], 400)
        self.assertEqual(self.b.rota("GET", "/api/3d/nada", ANA)[0], 404)
        self.assertEqual(self.b.rota("POST", "/api/3d/participante", ANA, json.dumps({"nome_publico": "Ana", "consentimento": True}).encode())[0], 200)
        cod, r = self.b.rota("POST", "/api/3d/pecas", ANA, json.dumps({"nome": "Peça"}).encode())
        self.assertEqual(cod, 200)
        self.assertEqual(self.b.rota("POST", f"/api/3d/pecas/{r['id']}/curar", ANA, b"{}")[0], 403)
        self.assertEqual(self.b.rota("GET", f"/api/3d/pecas/{r['id']}/memorial", BIA)[0], 404)
        self.assertEqual(self.b.rota("GET", "/api/3d/materiais", BIA)[1]["materiais"]["rpp"]["status"], "conferir")
        self.assertTrue(self.b.rota("POST", "/api/3d/avisos", BIA, json.dumps({"material": "rpla"}).encode())[1]["poucos_dados"])

    def test_pasta_padrao_pela_configuracao(self):
        antes = os.environ.pop("PHYSIS_3D_PASTA", None)
        try:
            self.assertEqual(m3.pasta_padrao(Path(self.tmp.name) / "hub.db"), Path(self.tmp.name).resolve() / "impressao3d")
            os.environ["PHYSIS_3D_PASTA"] = str(Path(self.tmp.name) / "outra")
            self.assertEqual(m3.pasta_padrao("x.db"), Path(self.tmp.name) / "outra")
        finally:
            os.environ.pop("PHYSIS_3D_PASTA", None)
            if antes is not None:
                os.environ["PHYSIS_3D_PASTA"] = antes


def sinteticos():
    """rHDPE grande, camada grossa: empena (e depois mudaram a borda). PLA pequeno: dá certo. PETG com balanço: fios."""
    out, n = [], 0
    for k in range(12):
        out.append({"peca": 1, "numero": k + 1, "material": "rhdpe", "config": {"altura_camada": 0.28, "bico_c": 240},
                    "balanco_fracao": 0.01, "tamanho_mm": 180, "resultado": "falha" if k < 9 else "ok", "problemas": ["empenamento"] if k < 9 else []})
    for k in range(15):
        out.append({"peca": 2, "numero": k + 1, "material": "rpla", "config": {"altura_camada": 0.2, "bico_c": 205},
                    "balanco_fracao": 0.0, "tamanho_mm": 40, "resultado": "ok", "problemas": []})
    for k in range(6):
        out.append({"peca": 3, "numero": k + 1, "material": "rpetg", "config": {"altura_camada": 0.2, "bico_c": 250},
                    "balanco_fracao": 0.3, "tamanho_mm": 60, "resultado": "parcial", "problemas": ["fios", "balanco"]})
    return out


class Avisos(unittest.TestCase):
    def test_poucos_dados(self):
        r = m3.AvisosNB(sinteticos()[:5], m3.perfis()).avisar({"material": "rhdpe", "config": {}})
        self.assertTrue(r["poucos_dados"])
        self.assertIn("poucos dados", r["texto"])
        self.assertEqual(r["avisos"], [])

    def test_aprende_com_o_historico(self):
        mud = {(1, k): "borda de 10 mm e mesa a 105 °C" for k in range(1, 10)}
        nb = m3.AvisosNB(sinteticos(), m3.perfis())
        r = nb.avisar({"material": "rhdpe", "config": {"altura_camada": 0.28, "bico_c": 240}, "balanco_fracao": 0.0, "tamanho_mm": 170}, mud)
        self.assertFalse(r["poucos_dados"])
        a = r["avisos"][0]
        self.assertEqual(a["problema"], "empenamento")
        self.assertGreater(a["probabilidade"], 0.5)
        self.assertEqual((a["semelhantes"], a["casos"]), (12, 9))
        self.assertIn("Em 12 impressões parecidas, 9 tiveram empenamento (warping).", a["texto"])
        self.assertIn("borda de 10 mm", a["texto"])
        pla = nb.avisar({"material": "rpla", "config": {"altura_camada": 0.2, "bico_c": 205}, "balanco_fracao": 0.0, "tamanho_mm": 35})
        self.assertEqual([x for x in pla["avisos"] if x["probabilidade"] > 0.3], [])
        self.assertLess(nb.probabilidade(m3.caracteristicas({"material": "rpla", "config": {}, "tamanho_mm": 35}, nb.perfis), "empenamento"), 0.2)
        petg = nb.avisar({"material": "rpetg", "config": {"bico_c": 250}, "balanco_fracao": 0.35, "tamanho_mm": 60})
        self.assertEqual({x["problema"] for x in petg["avisos"][:2]}, {"fios", "balanco"})
        novo = nb.avisar({"material": "rabs", "config": {}, "tamanho_mm": 60})          # material sem histórico
        self.assertTrue(novo["poucos_dados"])
        self.assertEqual(m3.caracteristicas({"material": "rpla", "config": {"bico_c": 220}}, nb.perfis)["bico"], "acima")

    def test_biblioteca_treina_com_as_revisoes(self):
        h = Hub(":memory:")
        with tempfile.TemporaryDirectory() as tmp:
            b = m3.Impressao3D(h, tmp, fatiador=m3.Fatiador(url=""))
            b.aderir("ana", {"nome_publico": "Ana", "consentimento": True})
            i = b.criar({"nome": "Caixa", "material": "rhdpe"}, ANA)["id"]
            grande = base64.b64encode(m3.escrever_stl(caixa_tris(0, 0, 0, 180, 60, 20))).decode()
            for k in range(11):
                b.revisar(i, {"arquivo_b64": grande, "arquivo_nome": "caixa.stl", "nota": f"tentativa {k + 1}", "config": {"altura_camada": 0.28}}, ANA)
                b.resultado(i, {"numero": k + 1, "resultado": "falha", "problemas": ["empenamento"]}, ANA)
            r = b.avisos({"material": "rhdpe", "config": {"altura_camada": 0.28}, "tamanho_mm": 175, "balanco_fracao": 0})
            self.assertFalse(r["poucos_dados"])
            self.assertEqual(r["avisos"][0]["problema"], "empenamento")
            self.assertIn("tentativa", r["avisos"][0]["texto"])
            h._db.close()


@unittest.skipUnless((SERV / "physis_fatiador").is_dir(), "só no repositório")
class ServicoFatiador(unittest.TestCase):
    def test_ini_e_estimativa(self):
        from physis_fatiador import servidor as fs
        ini = fs.montar_ini({"altura_camada": 0.28, "paredes": 3, "preenchimento": 0.15, "bico_c": 240, "mesa_c": 100, "densidade_g_cm3": 0.95}, "250x210")
        for linha in ("layer_height = 0.28", "perimeters = 3", "fill_density = 15%", "temperature = 240", "bed_temperature = 100",
                      "filament_density = 0.95", "bed_shape = 0x0,250x0,250x210,0x210"):
            self.assertIn(linha, ini)
        self.assertNotIn("temperature = 0", fs.montar_ini({}))
        with self.assertRaises(ValueError):
            fs.montar_ini({"altura_camada": 5})
        g = "G1 X1\n; filament used [mm] = 1234.5\n; filament used [g] = 3.70\n; estimated printing time (normal mode) = 1h 2m 3s\n"
        self.assertEqual(fs.ler_estimativa(g), {"tempo_s": 3723, "filamento_mm": 1234.5, "filamento_g": 3.7})

    def test_fatiar_com_executavel_falso(self):
        from physis_fatiador import servidor as fs
        chamados = []

        def falso(cmd, tempo):
            chamados.append(cmd)
            saida = Path(cmd[cmd.index("--output") + 1])
            saida.write_text("G28\n; estimated printing time (normal mode) = 5m 0s\n", encoding="utf-8")
            return 0, ""
        cod, r = fs.fatiar({"stl_b64": base64.b64encode(m3.escrever_stl(CUBO)).decode(), "config": {"altura_camada": 0.2}}, executar=falso)
        self.assertEqual(cod, 200, r)
        self.assertEqual(r["estimativa"]["tempo_s"], 300)
        self.assertIn("--export-gcode", chamados[0])
        self.assertEqual(fs.fatiar({"stl_b64": "!!"}, executar=falso)[0], 400)
        self.assertEqual(fs.fatiar({"stl_b64": base64.b64encode(m3.escrever_stl(CUBO)).decode()}, executar=lambda c, t: (1, "erro"))[0], 422)


@unittest.skipUnless(JS.is_file(), "sem o módulo")
class Tela(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_contrato(self):
        self.assertEqual(self.js.count("<h1>"), 1)
        self.assertIn("<h1>Physis 3D</h1>", self.js)
        for t in ("Em desenvolvimento", "PHYSIS3D_PRONTO", "window.telaPhysis3D", "window.PHYSIS3D_I18N", "window.PHYSIS3D_I18N_RX", "window.PHYSIS3D ",
                  "base-3d-premissas", "Modelo", "Fatiamento", "Biblioteca", "Fórum", "Método e licenças", "api/3d/avisos", "api/3d/fatiar",
                  "ArrowLeft", 'role="img"', "<caption", "data-tema", "toDataURL", "Baixar esta tela", "CC-BY-SA-4.0", "CERN-OHL-S-2.0", "[CONFERIR]"):
            self.assertIn(t, self.js)

    def test_sem_internet_e_sem_biblioteca_de_terceiros(self):
        urls = set(re.findall(r"https?://[^\s\"'`<>]+", self.js))
        self.assertTrue(urls <= {m3.NS_3MF, "http://schemas...", "http://schemas.openxmlformats.org/package/2006/content-types",
                                 "http://schemas.openxmlformats.org/package/2006/relationships",
                                 "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"}, urls)   # só nomes do formato 3MF/OPC
        self.assertNotRegex(self.js, r"(?i)three\.js|\bimport\s|require\(|\bcdn\b|</script")   # </script quebraria o embutido no painel
        self.assertNotRegex(self.js, r"\bGIZ\b")
        self.assertIn("__p3dEventos", self.js)
        self.assertEqual(len(re.findall(r"document\.addEventListener\(", self.js)), 3)

    def test_mesmas_constantes_do_python(self):
        for k, v in m3.CONFIG_PADRAO.items():
            if v is not None:
                self.assertRegex(self.js, rf"\b{k}:{v:g}\b")
        self.assertIn("micron:0.001, millimeter:1, centimeter:10, inch:25.4", self.js)
        for p in m3.PROBLEMAS:
            self.assertIn(f"{p}:\"{m3.PROBLEMAS[p]}\"", self.js)
        for k in m3.LICENCAS:
            self.assertIn(f"\"{k}\":\"{m3.LICENCAS[k]}\"", self.js)

    def test_harness_do_navegador(self):
        h = (RAIZ / "ferramentas" / "testes-navegador" / "teste-physis-3d.html").read_text(encoding="utf-8")
        self.assertIn("../../sistema/physis-3d.js", h)                                 # caminho relativo (Linux e Windows)
        self.assertIn("autoteste3MF", h)


class Portabilidade(unittest.TestCase):
    ARQS = [RAIZ / "physis-hub" / "physis_hub" / "impressao3d.py", JS, PREM, SERV / "Dockerfile", SERV / "physis_fatiador" / "servidor.py",
            RAIZ / "physis-hub" / "docs" / "PHYSIS_3D.md", Path(__file__)]

    def test_utf8_lf_e_sem_api_do_windows(self):
        for a in self.ARQS:
            if not a.is_file():
                continue
            b = a.read_bytes()
            self.assertNotIn(b"\r\n", b, f"CRLF em {a.name}")
            self.assertFalse(b.startswith(b"\xef\xbb\xbf"), f"BOM em {a.name}")
            t = b.decode("utf-8")
            if a.suffix == ".py" and a.name != Path(__file__).name:
                self.assertNotRegex(t, r"winreg|msvcrt|os\.startfile|ctypes\.windll|[A-Z]:\\\\")
