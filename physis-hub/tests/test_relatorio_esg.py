"""Relatorio ESG e taxonomia (sistema/physis-relatorio-esg.js).

Protege:
1. O contrato com a plataforma: relatorioEsgDados, relatorioEsgHtml e telaRelatorioEsg globais.
2. A estrutura da metodologia IGEA (Physis): resumo, limites e qualidade dos dados, ambiental, social, governanca
   (maturidade em 13 elementos, escala 1 a 5), investimento e prontidao para financiamento, taxonomia,
   correspondencia de codigos, lacunas e nota metodologica.
3. Os 13 elementos de maturidade usam os mesmos ids da base de certificacoes (igea_01 a igea_13).
4. A tabela de correspondencia traz so codigos GRI, IFRS S1/S2 e CBPS bem formados.
5. Le as chaves certas do aparelho, mostra lacunas, nao busca nada na internet e nao cita parceiros.
"""
import json
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
JS = RAIZ / "sistema" / "physis-relatorio-esg.js"
CERT = RAIZ / "sistema" / "physis-certificacoes.json"


@unittest.skipUnless(JS.is_file(), "sem o módulo")
class RelatorioEsg(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_contrato(self):
        for g in ("window.relatorioEsgDados", "window.relatorioEsgHtml", "window.telaRelatorioEsg"):
            self.assertIn(g, self.js)
        self.assertNotIn("<h1", self.js, "o relatório entra dentro de uma aba que já tem h1")

    def test_estrutura_igea(self):
        for t in ("1. Resumo executivo", "2. Limites do relato e qualidade dos dados", "3. Ambiental", "3.1 Energia", "3.2 Água",
                  "3.3 Resíduos", "3.4 Carbono por escopo", "3.5 Biodiversidade", "4. Social", "5. Governança",
                  "5.1 Maturidade da gestão", "6. Medidas, investimento e prontidão para financiamento",
                  "7. Alinhamento com a Taxonomia Sustentável Brasileira", "8. Correspondência com GRI, IFRS S1/S2 e CBPS",
                  "9. Lacunas de dados", "10. Nota metodológica", "metodologia IGEA (Physis)"):
            self.assertIn(t, self.js, t)

    def test_maturidade_com_ids_da_base(self):
        ids = re.findall(r'\["(igea_\d\d)"', self.js)
        self.assertEqual(ids, [f"igea_{i:02d}" for i in range(1, 14)])
        if CERT.is_file():
            base = json.loads(CERT.read_text(encoding="utf-8"))
            na_base = {k["id"] for c in base["certificacoes"] for g in c["grupos"] if g.get("escala") == "maturidade" for k in g["criterios"]}
            self.assertTrue(set(ids) <= na_base, set(ids) - na_base)

    def test_codigos_bem_formados(self):
        bloco = self.js[self.js.index("const ref = ["):]
        bloco = bloco[:bloco.index("]];") + 2]
        linhas = re.findall(r'\["[^"]+", "([^"]+)", "([^"]+)", "([^"]+)", ', bloco)
        self.assertGreaterEqual(len(linhas), 15)
        for gri, ifrs, cbps in linhas:
            for c in gri.split("; "):
                self.assertRegex(c, r"^(\d{3}-\d{1,2}|2-\d{1,2})$", gri)
            self.assertRegex(ifrs, r"^(—|S[12] · .+)$")
            self.assertRegex(cbps, r"^(—|0[12] · .+)$")
        for g in ("305-1", "305-2", "305-3", "302-1", "303-5", "306-3", "304-3", "403-9", "404-1"):
            self.assertIn(g, self.js)

    def test_le_as_chaves_dos_modulos(self):
        for k in ("physis-perfil", "physis-carbono", "physis-residuos-plano", "physis-sbn", "physis-gestao-cliente",
                  "physis-cert-gap", "physis-calc-solar", "physis-curso-"):
            self.assertIn(k, self.js, k)
        self.assertIn("PhysisCarbono", self.js)

    def test_lacunas_explicitas(self):
        self.assertIn("sem dado", self.js)
        self.assertIn("LAC.push", self.js)

    def test_sem_internet_e_sem_parceiros(self):
        self.assertNotRegex(self.js, r"https?://")
        self.assertNotRegex(self.js, r"\bGIZ\b|INTEGRATION environment|PREEEP|\bMEMD\b|Uganda")

    def test_taxonomia_com_verificar(self):
        self.assertIn("contribuição substancial", self.js)
        self.assertIn("não causar dano significativo", self.js)
        self.assertIn("salvaguardas mínimas", self.js)
        self.assertIn("verificar", self.js)


if __name__ == "__main__":
    unittest.main()
