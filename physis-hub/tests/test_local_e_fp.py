"""Local único da instalação e fator de potência nos módulos de energia (pedidos de 15/11/2026).

Local: UMA função no navegador (localDaInstalacao, mesma ordem e campos de hub.local_da_instalacao): lote do
Planejador > cadastro do Início > Monitoramento; sem nada, fonte "nao_informado" e nenhum ponto padrão. O Início pede
endereço, município, UF, latitude e longitude (obrigatórios) e mostra o mapa. Os módulos que dependem do lugar avisam
"local não informado" e não calculam o que depende dele.

FP: P (kW), Q (kvar), S (kVA) e FP em todo módulo que calcula potência ou demanda; FP medido vale antes da premissa
eletrica.fator_potencia_padrao; aviso de FP baixo pela premissa eletrica.fator_potencia_minimo [CONFERIR NA NORMA].
"""
import json
import math
import re
import unittest
from pathlib import Path

from physis_hub.hub import Hub

RAIZ = Path(__file__).resolve().parents[2]
S = RAIZ / "sistema"
PAINEL = RAIZ / "physis-hub" / "web" / "painel.html"
NO_REPO = PAINEL.is_file() and (S / "physis-solar.js").is_file()


def ler(p: Path) -> str:
    return p.read_text(encoding="utf-8")


@unittest.skipUnless(NO_REPO, "só no repositório")
class LocalUnico(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = ler(PAINEL)

    def test_getter_unico_com_os_campos_do_servidor(self):
        m = re.search(r"function localDaInstalacao\(\)\{(.*?)\n  return out; \}", self.p, re.S)
        self.assertIsNotNone(m)
        corpo = m.group(1)
        h = Hub(":memory:")
        h.instancia = {}
        for campo in h.local_da_instalacao():
            if campo in ("fontes", "cemaden_estacao"):
                continue
            self.assertIn(campo, corpo, f"campo {campo} do servidor fora do getter")
        ordem = [corpo.index(f) for f in ('fonte:"planejador"', 'fonte:"inicio"', 'fonte:"monitoramento"')]
        self.assertEqual(ordem, sorted(ordem), "ordem Planejador > Início > Monitoramento")
        self.assertIn('fonte:"nao_informado"', corpo)
        self.assertIn("window.localDaInstalacao = localDaInstalacao", self.p)
        self.assertIn("const latDoLugar = () => localDaInstalacao().lat", self.p)
        self.assertIn("const gisLugar = () => { const l = localDaInstalacao();", self.p)

    def test_inicio_pede_o_local_e_mostra_o_mapa(self):
        # regra de 15/11/2026 (tarde): CEP obrigatório; latitude e longitude opcionais (vêm do CEP, do mapa ou digitadas)
        for k in ("cep", "endereco", "municipio", "uf"):
            self.assertRegex(self.p, r'\{ k:"' + k + r'", r:"[^"]+", o:1,', f"{k} não é obrigatório no Início")
        for k in ("lat", "lon"):
            self.assertRegex(self.p, r'\{ k:"' + k + r'", r:"[^"]+", q:', f"{k} deveria ser opcional")
        self.assertIn('${s === "unidade" ? mapaDoInicio(p) : ""}', self.p)
        self.assertIn('id:"pf-mapa"', self.p)

    def test_monitoramento_grava_no_mesmo_cadastro(self):
        self.assertRegex(self.p, r"pf\.c = Object\.assign\(\{\}, pf\.c, \{ lat: String\(j\.local\.lat\)")

    def test_sem_ponto_padrao(self):
        solar = ler(S / "physis-solar.js")
        for n in ("-22.5", "-43.18"):
            self.assertNotIn(n, solar)
        calc = re.search(r"function solarCalc\(\)\{.*?\n", self.p).group(0)
        self.assertNotIn("-22.5", calc)
        self.assertNotIn('cidade:"São Paulo"', ler(S / "physis-cargatermica.js"))

    def test_modulos_avisam_local_nao_informado(self):
        self.assertIn("avisoSemLocal", ler(S / "physis-solar.js"))
        self.assertIn("avisoSemLocal", ler(S / "physis-cargatermica.js"))
        self.assertIn("avisoSemLocal", ler(S / "physis-secador.js"))
        self.assertIn("Local não informado — preencha na página Início", ler(S / "physis-circular-mapa.js"))
        self.assertIn("Local não informado — preencha na página Início", ler(S / "physis-turbinas.js"))
        self.assertIn("localDaInstalacao", ler(S / "physis-cargatermica.js"))
        self.assertIn("localDaInstalacao", ler(S / "physis-servidor-verde.js"))

    def test_ingles_dos_textos_novos(self):
        en = json.loads(ler(S / "physis-i18n-modulos.json"))["I18N"]
        for k in ("Endereço (obrigatório)", "UF (obrigatório)", "Latitude (obrigatório)", "Local não informado",
                  "Ir para o Início", "Marque o ponto no mapa ou digite a latitude e a longitude.",
                  "Potência ativa, reativa e aparente", "Potências do gerador", "Inversor na potência nominal"):
            self.assertIn(k, en)


@unittest.skipUnless(NO_REPO, "só no repositório")
class FatorDePotencia(unittest.TestCase):
    def test_premissas(self):
        prem = {p["id"]: p for p in json.loads(ler(S / "physis-premissas.json"))["premissas"]}
        pad, minimo = prem["eletrica.fator_potencia_padrao"], prem["eletrica.fator_potencia_minimo"]
        self.assertEqual(pad["status"], "conferir")
        self.assertIn("[CONFERIR]", pad["fonte"])
        self.assertIn("[CONFERIR NA NORMA]", minimo["fonte"])
        self.assertTrue(0 < pad["valor_padrao"] <= 1 and 0 < minimo["valor_padrao"] <= 1)

    def test_contas_espelho(self):
        """S = P ÷ FP; Q = √(S² − P²); o FP medido (0 < FP ≤ 1) vale antes da premissa."""
        js = ler(S / "physis-calc-comum.js")
        self.assertIn("fpM != null && fpM > 0 && fpM <= 1 ? fpM", js)
        self.assertIn("var s = p / fp, q = Math.sqrt(Math.max(0, s * s - p * p));", js)
        self.assertIn("potencias: potencias, potenciasHtml: potenciasHtml", js)
        p, fp = 10.0, 0.92
        s = p / fp
        self.assertAlmostEqual(math.sqrt(s * s - p * p), 4.25998, places=4)

    def test_em_todo_modulo_de_energia(self):
        for arq in ("physis-solar.js", "physis-turbinas.js", "physis-avac.js", "SustainKit_Definitivo.html"):
            self.assertIn("potenciasHtml", ler(S / arq), arq)
        self.assertIn("potenciasHtml", ler(RAIZ / "modulos" / "planejador" / "planejador-physis.html"))
        self.assertIn('premissa("eletrica.fator_potencia_padrao")', ler(S / "physis-servidor-verde.js"))
        ui = ler(S / "physis-aprendizado-ui.js")
        self.assertIn("p.fp_fonte", ui)          # FP medido (V6) na tela de consumo, com a origem
        self.assertIn("q_kvarh", ui)


if __name__ == "__main__":
    unittest.main()
