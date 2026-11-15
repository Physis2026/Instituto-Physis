"""Base de materiais (sistema/physis-materiais.json) e a ligação com a carga térmica.

Protege:
1. Esquema: densidade, condutividade e calor específico com unidade coerente, carbono com fonte, custo sem preço inventado.
2. Composições: U, capacidade térmica e atraso recalculados pelo método da NBR 15220-2 batem com o gravado.
3. Conferências à mão:
   - concreto 10 cm: R = 0,10/1,75 = 0,0571; U = 1/(0,13 + 0,0571 + 0,04) = 4,40 W/m²K (igual à tabela de paredes da NBR 15220-3);
     CT = 0,10·2300·1,0 = 230 kJ/m²K; atraso = 1,382·0,10·√(2300·1,0/(3,6·1,75)) = 2,64 h (tabela: 2,7 h).
   - fibrocimento 6 mm, cobertura no verão: U = 1/(0,17 + 0,006/0,65 + 0,04) = 4,56 W/m²K.
4. Os materiais de parede e cobertura da carga térmica usam o U e o atraso das composições (mesma origem).
"""
import json
import math
import re
import sys
import unittest
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
from physis_hub import cargatermica as ct  # noqa: E402

RAIZ = AQUI.parents[1]
BASE = RAIZ / "sistema" / "physis-materiais.json"
NO_REPO = BASE.is_file()


@unittest.skipUnless(NO_REPO, "só no repositório")
class Materiais(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texto = BASE.read_text(encoding="utf-8")
        cls.d = json.loads(cls.texto)
        cls.mats = {m["id"]: m for m in cls.d["materiais"]}

    def test_tamanho_e_ids(self):
        self.assertGreaterEqual(len(self.d["materiais"]), 75)
        self.assertEqual(len(self.mats), len(self.d["materiais"]))
        grupos = {m["grupo"] for m in self.d["materiais"]}
        self.assertIn("terra e bioconstrução", grupos)
        for chave in ("terra_taipa", "terra_adobe", "terra_btc", "terra_cob", "bambu_colmo", "madeira_dura", "canhamo_cal", "palha_fardo",
                      "argamassa_cal", "terra_palha", "cortica_expandida", "la_rocha", "la_vidro", "la_pet", "concreto_normal", "ceramica_bloco_vazado",
                      "bloco_concreto", "aco", "vidro_comum", "vidro_duplo_unidade", "vidro_lowe_unidade", "substrato_telhado_verde"):
            self.assertIn(chave, self.mats)

    def test_propriedades_plausiveis(self):
        for m in self.d["materiais"]:
            with self.subTest(m["id"]):
                self.assertTrue(5 <= m["densidade"] <= 9000)
                if m["condutividade"] is not None:
                    self.assertTrue(0.02 <= m["condutividade"] <= 400)
                    self.assertTrue(300 <= m["calor_especifico"] <= 2500)
                c = m["carbono_incorporado"]
                self.assertTrue(c["fonte"].strip())
                self.assertTrue(c["valor"] is None or 0 <= c["valor"] <= 20)
                self.assertIsNone(m["custo"]["valor"]); self.assertIn("[MARCADOR]", m["custo"]["fonte"])
        self.assertIsNone(re.search(r"https?://", self.texto))

    def test_composicoes_recalculadas(self):
        for c in self.d["composicoes"]:
            with self.subTest(c["id"]):
                k = c["calculo"]
                if c["tabelado"]:
                    self.assertIn("tabelado", k["origem"]); continue
                r = ct.nbr15220(c["camadas"], self.mats, "cobertura" if c["tipo"] == "cobertura" else "parede")
                self.assertAlmostEqual(r["u"], k["u"], delta=0.002)
                self.assertAlmostEqual(r["ct"], k["ct"], delta=0.5)
                self.assertAlmostEqual(r["atraso"], k["atraso"], delta=0.01)

    def test_conferencias_a_mao(self):
        r = ct.nbr15220([{"material": "concreto_normal", "espessura": 0.10}], self.mats)
        self.assertAlmostEqual(r["u"], 4.40, delta=0.02)
        self.assertAlmostEqual(r["ct"], 230, delta=1)
        self.assertAlmostEqual(r["atraso"], 2.64, delta=0.05)
        r = ct.nbr15220([{"material": "fibrocimento", "espessura": 0.006}], self.mats, "cobertura")
        self.assertAlmostEqual(r["u"], 4.56, delta=0.02)
        self.assertAlmostEqual(r["amortecimento"], math.exp(-2 * math.pi * r["atraso"] / 24), places=9)

    def test_avaliacao_normas(self):
        por = {c["id"]: c for c in self.d["composicoes"]}
        # parede de concreto de 10 cm: U 4,40 não atende o limite simplificado em nenhuma zona
        self.assertFalse(any(v["alfa_ate_06"] for v in por["concreto_10"]["avaliacao"]["nbr15575_simplificado"].values()))
        # adobe 25 cm: pesada pela NBR 15220-3 (U ≤ 2,2 e atraso ≥ 6,5 h)
        self.assertIn("pesada", [t["classe"] for t in por["adobe_25"]["avaliacao"]["nbr15220_3"]])
        # telha metálica sem forro reprova a cobertura em todas as zonas
        self.assertFalse(any(v["alfa_baixa"] for v in por["metalica_sem_forro"]["avaliacao"]["nbr15575_simplificado"].values()))

    def test_carga_termica_usa_as_composicoes(self):
        por = {c["id"]: c for c in self.d["composicoes"]}
        for k, m in ct.DADOS["materiais"].items():
            if k.startswith("_") or m.get("tipo") == "vidro":
                continue
            with self.subTest(k):
                self.assertIn(m.get("composicao"), por, "material da carga térmica sem composição na base de materiais")
                calc = por[m["composicao"]]["calculo"]
                self.assertAlmostEqual(m["u"], calc["u"], delta=0.006)
                self.assertAlmostEqual(m["atraso"], calc["atraso"], delta=0.06)


if __name__ == "__main__":
    unittest.main()
