"""Pedido de 15/11/2026: todo cliente baixa os próprios dados em Word e Excel editáveis, em toda tela.

- a plataforma mostra "Baixar esta tela" em toda aba com dado do cliente (lista curta de exceções, não mais uma lista de 7 abas);
- os programas abertos sozinhos (SustainKit, Planejador, SCADA) têm a mesma barra, escondida dentro da plataforma;
- onde se baixava só CSV, há também Excel (.xlsx) pelo mesmo exportador.
"""
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PAINEL = RAIZ / "physis-hub" / "web" / "painel.html"
SISTEMA = RAIZ / "sistema"
PROGRAMAS = [SISTEMA / "SustainKit_Definitivo.html", RAIZ / "modulos" / "planejador" / "planejador-physis.html",
             SISTEMA / "physis-scada-demo.html"]


def ler(p: Path) -> str:
    return p.read_text(encoding="utf-8")


class ExportarEmTodaTela(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.painel = ler(PAINEL)

    def test_plataforma_usa_lista_de_excecoes(self):
        i = self.painel.find("function mostraBaixar(")
        self.assertGreater(i, 0)
        corpo = self.painel[i:self.painel.find("\nfunction ", i + 10)]
        self.assertNotIn('["resumo","agua","inicio","zonas","animais","gestao"]', corpo)
        self.assertIn("ABAS_SEM_BAIXAR", corpo)
        self.assertIn("ui.acesso || ui.conta", corpo)          # telas de acesso e "Minha conta" seguem sem barra
        self.assertIn("soLoja()", corpo)                       # loja antes da compra: regra de sempre
        m = re.search(r"const ABAS_SEM_BAIXAR = new Set\(\[(.*?)\]\)", self.painel, re.S)
        self.assertIsNotNone(m)
        fora = set(re.findall(r'"([\w-]+)"', m.group(1)))
        for aba in ("solar", "avac", "turbinas", "sbn", "circular", "carbono", "resiliencia", "certificacoes", "planejador",
                    "sustainkit", "supervisao", "secador", "servidor-verde", "saude", "mapeamento", "agua", "campo", "gestao"):
            self.assertNotIn(aba, fora, aba)

    def test_exportador_le_o_quadro_e_monta_planilha(self):
        js = ler(SISTEMA / "physis-exportar.js")
        self.assertIn('tag === "IFRAME"', js)                  # o conteúdo do programa no quadro entra no arquivo
        self.assertIn("contentDocument", js)
        for nome in ("planilha: planilha", "csvParaXlsx: csvParaXlsx", "baixarPlanilha: baixarPlanilha"):
            self.assertIn(nome, js)

    def test_programas_sozinhos_tem_a_barra(self):
        original = ler(SISTEMA / "physis-exportar.js").replace("\r\n", "\n").rstrip("\n")
        for p in PROGRAMAS:
            t = ler(p)
            with self.subTest(programa=p.name):
                self.assertIn(original, t)                     # cópia igual ao original (sincronizar.py)
                self.assertIn("PhysisExportar.barra(", t)
                self.assertIn("encaminhar: false", t)
                self.assertIn("idiomaTela", t)
                self.assertIn("html[data-em-quadro] .px-exportar[data-px-geral]{display:none!important}", t)

    def test_onde_havia_csv_ha_excel(self):
        for qual in ("hist", "leituras", "leit", "ph", "premissas"):
            self.assertIn(f'data-csv="{qual}"', self.painel)
            self.assertIn(f'data-xlsx="{qual}"', self.painel)
        self.assertIn('if (b.dataset.xlsx) return baixarCsv(b.dataset.xlsx, "xlsx");', self.painel)
        self.assertIn("PhysisExportar.baixarPlanilha(", self.painel)
        sbn = ler(SISTEMA / "physis-sbn.js")
        self.assertIn('data-sbn-conf-exportar="xlsx"', sbn)
        self.assertIn("csvParaXlsx", sbn)
        ev = ler(SISTEMA / "physis-evidencias.js")
        self.assertIn("data-ev-xlsx", ev)
        self.assertIn("csvParaXlsx", ev)
        scada = ler(SISTEMA / "physis-scada-demo.html")
        self.assertIn('id="btXlsxAgg"', scada)
        self.assertIn("csvParaXlsx(", scada)
        # os módulos embutidos na plataforma são a versão nova (embutir_bases.py)
        self.assertIn('data-sbn-conf-exportar="xlsx"', self.painel)
        self.assertIn("data-ev-xlsx", self.painel)


if __name__ == "__main__":
    unittest.main()
