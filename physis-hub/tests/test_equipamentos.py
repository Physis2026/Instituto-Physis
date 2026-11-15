"""Base de equipamentos (sistema/physis-equipamentos.json) e importadores (ferramentas/importar_cec.py e importar_inmetro.py).

Protege:
1. Esquema de cada item, ids únicos, unidades coerentes por categoria.
2. Faixas de eficiência plausíveis: COP 2–7, IDRS 2,5–11, η de motor 0,80–0,97, módulo FV 18–25 %,
   inversor 95–99 %, e tipico dentro da faixa.
3. Nenhum preço inventado (custo fica [MARCADOR]) e nenhum endereço de internet dentro da base.
4. Importadores: leem CSV e XLSX mínimos (gerados aqui, sem internet) e convertem para o mesmo esquema.
"""
import importlib.util
import json
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
BASE = RAIZ / "sistema" / "physis-equipamentos.json"
FERR = RAIZ / "ferramentas"
NO_REPO = BASE.is_file()
CAMPOS = ["id", "categoria", "subtipo", "descricao", "faixa_capacidade", "unidade", "eficiencia", "potencia", "vida_util_anos",
          "manutencao", "custo_referencia_brl", "normas", "fonte", "data", "verificar"]
CATEGORIAS = {"ar-condicionado", "ventiladores e exaustores", "filtros de ar", "bombas", "motores", "módulos fotovoltaicos", "inversores",
              "baterias", "controladores de carga", "sensores", "componentes de quadro", "automação", "esgoto e saneamento", "biogás",
              "aquecimento solar de água"}
SEM_EFICIENCIA = {"sensores", "automação", "distribuição de ar"}


def carregar(nome):
    spec = importlib.util.spec_from_file_location(nome, FERR / f"{nome}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(FERR))
    spec.loader.exec_module(mod)
    return mod


def xlsx_minimo(caminho, linhas):
    """Planilha .xlsx mínima (só strings em linha), para testar a leitura sem arquivo de fora."""
    def cel(ci, ri, v):
        ref = chr(65 + ci) + str(ri)
        return f'<c r="{ref}" t="inlineStr"><is><t>{v}</t></is></c>'
    rows = "".join(f'<row r="{i + 1}">' + "".join(cel(j, i + 1, v) for j, v in enumerate(l)) + "</row>" for i, l in enumerate(linhas))
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   f"<sheetData>{rows}</sheetData></worksheet>")


@unittest.skipUnless(NO_REPO, "só no repositório")
class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texto = BASE.read_text(encoding="utf-8")
        cls.d = json.loads(cls.texto)
        cls.itens = cls.d["itens"]

    def test_tamanho_e_categorias(self):
        self.assertGreaterEqual(len(self.itens), 150)
        cats = {i["categoria"] for i in self.itens}
        self.assertTrue(CATEGORIAS <= cats, CATEGORIAS - cats)
        self.assertEqual(self.d["contagem"], {c: sum(1 for i in self.itens if i["categoria"] == c) for c in self.d["contagem"]})

    def test_esquema(self):
        for it in self.itens:
            with self.subTest(it["id"]):
                for c in CAMPOS:
                    self.assertIn(c, it)
                self.assertRegex(it["id"], r"^[a-z0-9][a-z0-9_-]*$")
                self.assertTrue(it["fonte"].strip() and str(it["data"]).strip())
                self.assertIsInstance(it["verificar"], bool)
                self.assertIsInstance(it["normas"], list)
                fc = it["faixa_capacidade"]
                self.assertLessEqual(fc["min"], fc["max"])
                v = it["vida_util_anos"]
                self.assertEqual(len(v), 2); self.assertLessEqual(v[0], v[1])
                if it["eficiencia"] is None:
                    self.assertIn(it["categoria"], SEM_EFICIENCIA | {"componentes de quadro"})
                    self.assertIn("desempenho", it)
                else:
                    e = it["eficiencia"]
                    self.assertTrue({"indicador", "tipico", "faixa"} <= set(e))
                    self.assertLessEqual(e["faixa"][0], e["tipico"]); self.assertLessEqual(e["tipico"], e["faixa"][1])

    def test_ids_unicos(self):
        ids = [i["id"] for i in self.itens]
        self.assertEqual(len(ids), len(set(ids)))

    def test_faixas_de_eficiencia(self):
        for it in self.itens:
            e = it["eficiencia"]
            if not e:
                continue
            with self.subTest(it["id"]):
                ind, a, b = e["indicador"], e["faixa"][0], e["faixa"][1]
                if ind == "COP":
                    self.assertTrue(2 <= a and b <= 7, (a, b))
                    self.assertTrue(2 <= e.get("sazonal", e["tipico"]) <= 10)
                elif ind == "IDRS":
                    self.assertTrue(2.5 <= a and b <= 11)
                elif ind == "η":
                    self.assertEqual(it["categoria"], "motores")
                    self.assertTrue(0.80 <= a and b <= 0.97, (a, b))
                elif it["categoria"] == "módulos fotovoltaicos":
                    self.assertTrue(18 <= a and b <= 25, (a, b))
                    self.assertTrue(-0.45 <= it["coef_temperatura_pmax_pct_por_C"] <= -0.2)
                elif it["categoria"] == "inversores":
                    self.assertTrue(95 <= a and b <= 99, (a, b)); self.assertIn("faixa_mppt", it)
                elif ind == "%":
                    self.assertTrue(0 <= a and b <= 100, (a, b))

    def test_unidades_por_categoria(self):
        for it in self.itens:
            with self.subTest(it["id"]):
                if it["categoria"] == "ar-condicionado":
                    self.assertEqual(it["unidade"], "kW térmico")
                    self.assertIn(it["sistema"], {"split", "vrf", "chiller", "central-dx", "bomba-calor"})
                    if it.get("capacidade_nominal_btuh"):
                        self.assertAlmostEqual(it["faixa_capacidade"]["max"], it["capacidade_nominal_btuh"] / 3412.142, delta=0.01)
                if it["categoria"] == "motores":
                    self.assertEqual(it["unidade"], "kW (no eixo)")
                    p = it["potencia"]["min"]
                    self.assertAlmostEqual(p, it["faixa_capacidade"]["min"] / it["eficiencia"]["tipico"], delta=0.02)
                if it["categoria"] == "módulos fotovoltaicos":
                    self.assertEqual(it["unidade"], "Wp")
                if it["categoria"] == "esgoto e saneamento":
                    self.assertEqual(it["eficiencia"]["condicao"], "remoção de DBO5")

    def test_motores_ie_crescem(self):
        por = {}
        for it in self.itens:
            if it["categoria"] == "motores":
                kw = it["faixa_capacidade"]["min"]
                por.setdefault(kw, {})[it["subtipo"].split()[-1]] = it["eficiencia"]["tipico"]
        for kw, v in por.items():
            self.assertLess(v["IE2"], v["IE3"], kw); self.assertLess(v["IE3"], v["IE4"], kw)

    def test_sem_preco_inventado_nem_url(self):
        for it in self.itens:
            c = it["custo_referencia_brl"]
            self.assertIsNone(c["faixa"]); self.assertIn("[MARCADOR]", c["fonte"])
        self.assertIsNone(re.search(r"https?://", self.texto))

    def test_tabelas_da_planilha_iguais_ao_avac(self):
        js = (RAIZ / "sistema" / "physis-avac.js").read_text(encoding="utf-8")
        t = self.d["tabelas_avac"]
        for nome, chave in (("DEG_BTU", "degraus_btuh"), ("MOTOR_KW", "motores_kw"), ("DISJ", "disjuntores_a"), ("SEC", "secoes_mm2")):
            m = re.search(r"const %s = \[([^\]]*)\]" % nome, js)
            self.assertIsNotNone(m, nome)
            self.assertEqual([float(x) for x in m.group(1).split(",")], [float(x) for x in t[chave]], nome)


@unittest.skipUnless((FERR / "importar_cec.py").is_file(), "só no repositório")
class Importadores(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_cec_modulos_csv(self):
        cec = carregar("importar_cec")
        arq = self.dir / "modulos.csv"
        arq.write_text("PV Module List\nManufacturer,Model Number,Description,Nameplate Pmax (W),A_c (m2),γPmax (%/°C)\n"
                       "Fabricante X,XM-430,Mono TOPCon,430,1.95,-0.30\nFabricante Y,YM-400,Mono PERC,400,1.95,-0.35\n,,,,\n", encoding="utf-8")
        itens = cec.converter_modulos(cec.ler_tabela(arq), "2026-11-15")
        self.assertEqual(len(itens), 2)
        self.assertAlmostEqual(itens[0]["eficiencia"]["tipico"], 22.05, places=2)
        self.assertEqual(itens[0]["coef_temperatura_pmax_pct_por_C"], -0.30)
        self.assertTrue(itens[0]["id"].startswith("cec-fv-"))

    def test_cec_inversores_xlsx(self):
        cec = carregar("importar_cec")
        arq = self.dir / "inv.xlsx"
        xlsx_minimo(arq, [["Manufacturer", "Model Number", "Description", "Maximum Continuous Output Power (W)", "Weighted Efficiency (%)"],
                          ["Marca Z", "Z-5K", "string inverter", "5000", "97.5"], ["Marca Z", "Z-M", "microinverter", "380", "96.5"]])
        itens = cec.converter_inversores(cec.ler_tabela(arq), "2026-11-15")
        self.assertEqual([i["subtipo"] for i in itens], ["string", "microinversor"])
        self.assertEqual(itens[0]["faixa_capacidade"]["min"], 5.0)

    def test_inmetro_ar_e_mesclar(self):
        inm = carregar("importar_inmetro")
        arq = self.dir / "ar.csv"
        arq.write_text("Marca;Modelo;Tipo;Capacidade de refrigeração (BTU/h);IDRS;Classe\nMarca A;AB-12;Split hi-wall inverter;12.000;7,10;A\n"
                       "Marca B;BC-9;Split hi-wall;9000;5,2;C\n", encoding="utf-8")
        itens = inm.converter_ar(inm.ler_tabela(arq), "2026-11-15")
        self.assertEqual(itens[0]["capacidade_nominal_btuh"], 12000)
        self.assertAlmostEqual(itens[0]["eficiencia"]["tipico"], 7.10)
        self.assertAlmostEqual(itens[0]["faixa_capacidade"]["min"], 3.52, places=2)
        if NO_REPO:
            copia = self.dir / "base.json"
            copia.write_text(BASE.read_text(encoding="utf-8"), encoding="utf-8")
            n0 = len(json.loads(copia.read_text(encoding="utf-8"))["itens"])
            self.assertEqual(inm.mesclar(itens, "inmetro-ar-", copia), n0 + 2)
            self.assertEqual(inm.mesclar(itens[:1], "inmetro-ar-", copia), n0 + 1)

    def test_inmetro_motores(self):
        inm = carregar("importar_inmetro")
        arq = self.dir / "mot.csv"
        arq.write_text("Marca;Linha;Potência (cv);Polos;Rendimento nominal (%)\nM;L1;10;4;91,7\n", encoding="utf-8")
        it = inm.converter_motores(inm.ler_tabela(arq), "2026-11-15")[0]
        self.assertAlmostEqual(it["faixa_capacidade"]["min"], 7.355, places=2)
        self.assertAlmostEqual(it["eficiencia"]["tipico"], 0.917)


if __name__ == "__main__":
    unittest.main()
