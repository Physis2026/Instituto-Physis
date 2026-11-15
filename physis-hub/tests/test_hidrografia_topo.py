"""Hidrografia do servidor (D05), APP de topo de morro (D06) e modo de teste da Qualidade da água (D11), 15/11/2026.

Protege:
1. GET /api/gis/hidrografia: lê o GeoJSON instalado (PHYSIS_HIDROGRAFIA), recorta na janela, limita o tamanho;
   sem o arquivo responde sem_camada; janela grande demais é recusada. Testado com um GeoJSON falso, minúsculo.
2. ferramentas/hidrografia_servidor.py padroniza e recorta a base baixada pelo engenheiro (sem dado copiado no repositório).
3. O Planejador busca os rios do servidor e só desenha a faixa depois da largura digitada.
4. Topo de morro: parâmetros na base com status conferir e [CONFERIR NA LEI]; espelho da conta num relevo sintético.
5. Água: modo de teste desligado por padrão; ligado, preenche os limites vazios pela referência e libera o alerta.
"""
import importlib.util
import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
sys.path.insert(0, str(AQUI.parent))
from physis_hub import gis  # noqa: E402

FALSO = {"type": "FeatureCollection", "fonte": "teste", "features": [
    {"type": "Feature", "properties": {"nome": "Córrego A"}, "geometry": {"type": "LineString", "coordinates": [[-43.20, -22.50], [-43.19, -22.50], [-43.10, -22.40]]}},
    {"type": "Feature", "properties": {"nome": "Rio longe"}, "geometry": {"type": "LineString", "coordinates": [[-40.0, -20.0], [-40.1, -20.1]]}},
    {"type": "Feature", "properties": {"nome": "Nascente 1"}, "geometry": {"type": "Point", "coordinates": [-43.195, -22.505]}},
    {"type": "Feature", "properties": {"nome": "Nascente fora"}, "geometry": {"type": "Point", "coordinates": [-43.0, -22.0]}}]}
JANELA = ["-43.21", "-22.51", "-43.18", "-22.49"]


class Hidrografia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.arq = os.path.join(self.tmp.name, "hidro.geojson")
        Path(self.arq).write_text(json.dumps(FALSO), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_sem_camada(self):
        r = gis.hidrografia(JANELA, os.path.join(self.tmp.name, "nao-existe.geojson"))
        self.assertFalse(r["ok"])
        self.assertTrue(r["sem_camada"])

    def test_recorta_na_janela(self):
        r = gis.hidrografia(JANELA, self.arq)
        self.assertTrue(r["ok"])
        self.assertEqual([x["nome"] for x in r["rios"]], ["Córrego A"])
        self.assertEqual([x["nome"] for x in r["nascentes"]], ["Nascente 1"])
        self.assertIsNone(r["rios"][0]["largura_m"], "a largura vem digitada no Planejador")
        # o vértice longe (-43.10, -22.40) entra só como vizinho do último de dentro: a linha cruza a borda
        self.assertEqual(len(r["rios"][0]["coords"]), 3)

    def test_janela_grande_e_invalida(self):
        self.assertFalse(gis.hidrografia(["-44", "-23", "-43", "-22"], self.arq)["ok"])
        self.assertFalse(gis.hidrografia(["a", "b"], self.arq)["ok"])

    def test_teto_de_feicoes(self):
        muitos = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [-43.2, -22.5]}}] * (gis.MAX_FEICOES + 50)}
        Path(self.arq).write_text(json.dumps(muitos), encoding="utf-8")
        gis._HIDRO_CACHE.clear()
        r = gis.hidrografia(JANELA, self.arq)
        self.assertTrue(r["cortado"])
        self.assertLessEqual(len(r["nascentes"]), gis.MAX_FEICOES)

    def test_rota_no_servidor(self):
        s = (AQUI.parent / "physis_hub" / "servidor.py").read_text(encoding="utf-8")
        self.assertIn('if u.path == "/api/gis/hidrografia":', s)
        self.assertIn("gis_mod.hidrografia(", s)

    def test_ferramenta_de_conversao(self):
        spec = importlib.util.spec_from_file_location("hs", RAIZ / "ferramentas" / "hidrografia_servidor.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        bho = {"features": [{"geometry": {"type": "LineString", "coordinates": [[-43.2, -22.5], [-43.19, -22.5]]}, "properties": {"noriocomp": "Rio X"}},
                            {"geometry": {"type": "LineString", "coordinates": [[-40, -20], [-40.1, -20.1]]}, "properties": {"noriocomp": "Rio Y"}}]}
        r = m.converter(bho, JANELA)
        self.assertEqual([f["properties"]["nome"] for f in r["features"]], ["Rio X"])
        self.assertIn("[CONFERIR", r["fonte"])
        texto = (RAIZ / "ferramentas" / "hidrografia_servidor.py").read_text(encoding="utf-8")
        self.assertIn("Base Hidrográfica Ottocodificada", texto)
        self.assertNotIn('"coordinates": [[-4', texto, "nenhum dado da base copiado no repositório")

    def test_planejador_busca_e_pede_a_largura(self):
        pl = (RAIZ / "modulos" / "planejador" / "planejador-physis.html").read_text(encoding="utf-8")
        self.assertIn("fetch('/api/gis/hidrografia?bbox='+bb", pl)
        self.assertIn("largura:r.largura_m??larg[r.nome]??null", pl)
        self.assertIn("if(!(L>0)){out.semLargura.push", pl)


def topo_morro(Z, sl, cs, p):
    """Espelho de physisTopoMorro (Planejador)."""
    zmin, zmax = min(Z), max(Z)
    H = zmax - zmin
    inc = sum(math.degrees(math.atan(s / 100)) for s in sl) / len(sl)
    cota = zmin + p["fracao_base"] * H
    eleg = H >= p["altura_min_m"] and inc > p["inclinacao_media_graus"]
    area = sum(cs * cs for z in Z if z >= cota) if eleg else 0
    return {"H": H, "inc": inc, "cota": cota, "area": area}


class TopoDeMorro(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        b = json.loads((RAIZ / "sistema" / "physis-premissas.json").read_text(encoding="utf-8"))
        cls.p = {x["id"]: x for x in b["premissas"]}["app.topo_morro"]

    def test_premissa_conferir(self):
        self.assertEqual(self.p["status"], "conferir")
        self.assertIn("[CONFERIR NA LEI]", self.p["fonte"])
        self.assertIn("art. 4º, IX", self.p["fonte"])

    def test_espelho_morro_e_plano(self):
        v = self.p["valor_padrao"]
        # morro de 150 m em cone com inclinação média de 35° (70% ≈ 35°)
        Z = [0, 30, 60, 90, 110, 130, 150]
        sl = [70] * len(Z)
        r = topo_morro(Z, sl, 10, v)
        self.assertAlmostEqual(r["cota"], 100, delta=0.01)
        self.assertEqual(r["area"], 3 * 100)            # 110, 130 e 150 ficam acima de 2/3 da altura
        plano = topo_morro([0, 5, 10], [5, 5, 5], 10, v)
        self.assertEqual(plano["area"], 0)
        pl = (RAIZ / "modulos" / "planejador" / "planejador-physis.html").read_text(encoding="utf-8")
        self.assertIn("function physisTopoMorro(g)", pl)
        self.assertIn("PhysisCalc.premissa('app.topo_morro')", pl)
        self.assertIn("R.topoMorro=physisTopoMorro(g)", pl)


class AguaModoTeste(unittest.TestCase):
    def test_modo_de_teste(self):
        p = (RAIZ / "physis-hub" / "web" / "painel.html").read_text(encoding="utf-8")
        self.assertIn('limLer = () => limComTeste(guardaLer("physis-agua-limites", {}));', p)
        self.assertIn("const emTesteAgua = cfg => !!(cfg && cfg.testeRef && cfg.usoRef && AG_REF()[cfg.usoRef]);", p)
        self.assertIn("if (!emTesteAgua(cfg)) return l;", p, "desligado: nada é preenchido")
        self.assertIn('(emTesteAgua(cfg) && (g === "turb" || g === "cloro"))', p)
        self.assertIn('data-ag-teste="1" ${cfg.testeRef ? "checked" : ""}', p, "desligado por padrão (só liga marcado)")
        self.assertIn("teste — valores a conferir", p)
        self.assertIn('const l = guardaLer("physis-agua-limites", {}); l[t.dataset.lim] = t.value;', p, "o valor de teste nunca é gravado como limite")


if __name__ == "__main__":
    unittest.main()
