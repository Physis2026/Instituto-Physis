"""Validação pré-exportação do fatiador (ciclo de auditoria 2026-11-22): compensação X/Y, costura,
pele felpuda, resolução e combinações impossíveis."""
import sys
import unittest
from pathlib import Path

SERV = Path(__file__).resolve().parents[2] / "servicos" / "fatiador"


@unittest.skipUnless((SERV / "physis_fatiador").is_dir(), "só no repositório")
class ValidacaoFatiador(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(SERV))
        from physis_fatiador import servidor as fs
        cls.fs = fs

    def test_padrao_sem_mudanca(self):
        ini = self.fs.montar_ini({})
        for k in ("xy_size_compensation", "seam_position", "fuzzy_skin", "resolution"):
            self.assertNotIn(k, ini)
        self.assertEqual(self.fs.validar_cfg({}), [])

    def test_chaves_novas_no_ini(self):
        ini = self.fs.montar_ini({"comp_xy": -0.1, "comp_furo": 0.1, "pe_elefante": 0.2, "costura": "traseira",
                                  "pele_felpuda": "externa", "pele_espessura": 0.2, "pele_dist": 0.6, "resolucao": 0.0125, "paredes": 3})
        for linha in ("xy_size_compensation = -0.1", "xy_inner_size_compensation = 0.1", "elefant_foot_compensation = 0.2",
                      "seam_position = rear", "fuzzy_skin = external", "fuzzy_skin_thickness = 0.2", "fuzzy_skin_point_dist = 0.6",
                      "resolution = 0.0125"):
            self.assertIn(linha, ini)

    def test_impossiveis(self):
        for cfg in ({"paredes": -1}, {"paredes": 1.5}, {"camadas_topo": -2}, {"altura_camada": 0.5, "bico_mm": 0.4},
                    {"bico_mm": 0}, {"largura_linha": 0}, {"comp_xy": 0.5}, {"pe_elefante": -0.1}, {"costura": "lateral"},
                    {"pele_felpuda": "muita"}, {"pele_felpuda": "externa", "pele_espessura": 0.6, "paredes": 1, "largura_linha": 0.45},
                    {"pele_felpuda": "todas", "pele_dist": 0}, {"resolucao": -1}, {"paredes": "duas"}, {"bico_mm": "nan"}):
            with self.assertRaises(ValueError, msg=cfg):
                self.fs.montar_ini(cfg)

    def test_avisos_de_qualidade(self):
        a = self.fs.validar_cfg({"pele_felpuda": "externa", "pele_dist": 0.3, "comp_xy": -0.1, "comp_furo": 0.1,
                                 "camadas_topo": 2, "largura_linha": 0.3, "paredes": 3})
        texto = " | ".join(a)
        for trecho in ("costura fica visível", "menor que o bico", "o furo recebe as duas", "menos de 0,6 mm", "largura de linha"):
            self.assertIn(trecho, texto)

    def test_mesa_invalida_em_portugues(self):
        with self.assertRaisesRegex(ValueError, "LARGURAxPROFUNDIDADE"):
            self.fs.montar_ini({}, "abc")


if __name__ == "__main__":
    unittest.main()
