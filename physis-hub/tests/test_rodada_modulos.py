"""Rodada de 15/11/2026 (auditoria das decisões de módulos).

Protege:
1. Loja: Planejador (P13), Qualidade da água (P6) e Reúso e chuva (P18) à venda; itens próprios de Energia solar e
   Certificações, sem preço inventado (sob consulta); só os módulos à venda podem ir ao público.
2. Toda aba de módulo em desenvolvimento leva o selo "Em desenvolvimento" na instalação de pesquisa.
3. O SCADA não cita mais o Power BI (ferramenta aberta: Apache Superset no servidor da Physis).
4. A barra única de preferências em documento.html, municipio.html e baixar.html; o texto público do app sem caixinha
   de remédios e pulseira (módulos em desenvolvimento).
5. Documento/PDF/Planilha com ODF e PDF/A (PhysisODF.acoplar, pdfa: true) na consultoria, no SustainKit, no Planejador e na Gestão.
6. Teste de navegador das telas principais (ferramentas/testes-navegador/telas.html).
7. A Tela do cliente e as cópias antigas do SustainKit saíram; o formato de importação antigo continua no núcleo.
8. Gestão: Cursos e turmas e a equipe vinda do cadastro (contas do servidor).
"""
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PAINEL = RAIZ / "physis-hub" / "web" / "painel.html"
NO_REPO = (RAIZ / "sistema").is_dir() and PAINEL.is_file()


def ler(*p):
    return (RAIZ.joinpath(*p)).read_text(encoding="utf-8")


@unittest.skipUnless(NO_REPO, "só no repositório")
class RodadaModulos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = PAINEL.read_text(encoding="utf-8")
        cls.cat = re.search(r"const CAT = \[(.*?)\n\];", cls.p, re.S).group(1)

    def test_1_loja_modulos_a_venda(self):
        for cod in ("P13", "P18"):
            self.assertRegex(self.cat, r'Object\.assign\(P\("%s",[^)]*\), \{ g:"func", st:"func", cod:"[^"]*módulo à parte" \}\)' % cod, cod)
            self.assertNotRegex(self.cat, r'P\("%s"[^\n]*preco:' % cod, "sem preço dado: sob consulta")
        self.assertIn('{ g:"func", st:"func", cod:"Água · módulo à parte", preco:11400,', self.cat)
        m = re.search(r'\{ id:"solar",[^\n]*\}', self.cat)
        self.assertIn("preco:300, apartir:true", m.group(0))
        venda = re.search(r"const LOJA_VENDA = new Set\(\[(.*?)\]\)", self.p).group(1)
        for ident in ("base", "campo", "mon-sw", "P13", "solar", "P6", "P18", "sk-e", "sk-w", "sk-m", "sk-c", "scada", "gestao", "consultoria-pers"):
            self.assertIn('"%s"' % ident, venda, ident)
        for fora in ("P5", "P9", "P10", "P12", "P15", "col", "com", "zonas", "servidor-verde"):
            self.assertNotIn('"%s"' % fora, venda, fora)
        self.assertIn('publico() ? !!srvItem(id) && (LOJA_VENDA.has(id) || ehCert(id)', self.p)
        for trecho in ('r.push("planejador")', 'r.push("solar")', 'r.push("certificacoes")', '(ligado(m,"P18") && visivel(m,"P18"))'):
            self.assertIn(trecho, self.p, trecho)

    def test_d01_d02_precos_dados_e_certificacoes(self):
        """D01: solar a partir de R$ 300,00. D02: cada certificação da aba é um módulo a partir de R$ 750,00, com objetivo
        diferente do SustainKit Cert; consultoria personalizada a partir de R$ 5.000,00 (loja e página de consultoria)."""
        import json
        base = json.loads((RAIZ / "sistema" / "physis-certificacoes.json").read_text(encoding="utf-8"))["certificacoes"]
        self.assertIn('const CERT_ITENS = () =>', self.p)
        self.assertIn('id:"cert-" + c.id', self.p)
        self.assertIn('preco:750, apartir:true', self.p)
        self.assertIn("Diferente do SustainKit Cert (checklist rápido dentro do diagnóstico)", self.p)
        self.assertIn('{ id:"consultoria-pers", g:"func", cod:"Consultoria", nome:"Consultoria personalizada"', self.p)
        self.assertIn('preco:5000, apartir:true', self.p)
        self.assertIn('"a partir de " + brl2(pr)', self.p)
        self.assertIn("A partir de R$ 5.000,00", ler("physis-hub", "web", "consultoria.html"))
        import sys
        sys.path.insert(0, str(RAIZ / "physis-hub"))
        from physis_hub.hub import Hub
        self.assertEqual(set(Hub.CERTIFICACOES_LOJA), {c["id"] for c in base}, "hub.py e a base de certificações com os mesmos ids")
        for c in base:
            self.assertEqual(Hub.ITEM_MODULOS["cert-" + c["id"]], ("certificacoes",))
        for k, m in (("solar", ("solar",)), ("P13", ("planejador",)), ("P18", ("agua",)), ("P19", ("sbn",)), ("P11", ("circular",)), ("P16", ("circular",))):
            self.assertEqual(Hub.ITEM_MODULOS[k], m, k)
        self.assertNotIn("cert", Hub.ITEM_MODULOS)

    def test_2_abas_em_desenvolvimento(self):
        abas = re.findall(r'\["([\w-]+)",', re.search(r"const ABAS = \[(.*?)\];", self.p, re.S).group(1))
        venda = set(re.findall(r'"([\w-]+)"', re.search(r"const ABAS_VENDA = new Set\(\[(.*?)\]\);", self.p).group(1)))
        dev = set(re.findall(r'"([\w-]+)"', re.search(r"const ABAS_DEV = new Set\(\[(.*?)\]\);", self.p).group(1)))
        for a in ("carbono", "circular", "avac", "turbinas", "sbn", "resiliencia", "saude", "secador", "servidor-verde", "cursos"):
            self.assertIn(a, dev, a)
        self.assertEqual(venda & dev, set())
        self.assertEqual([a for a in abas if a not in venda | dev], [], "toda aba é à venda ou em desenvolvimento")
        self.assertIn("${emPesquisa() && ABAS_DEV.has(id) ? ' <span class=\"selo at\">Em desenvolvimento</span>' : \"\"}", self.p)

    def test_3_scada_sem_power_bi(self):
        s = ler("sistema", "physis-scada-demo.html")
        self.assertNotIn("Power BI", s)
        self.assertIn("Apache Superset no servidor da Physis", s)
        self.assertIn("Apache Superset on the Physis server", s)

    def test_4_barra_unica_nas_paginas(self):
        pref = ler("sistema", "physis-preferencias.js").replace("\r\n", "\n")
        for partes in (("physis-hub", "web", "documento.html"), ("physis-hub", "web", "municipio.html"), ("app-nativo", "site", "baixar.html")):
            with self.subTest(partes[-1]):
                h = ler(*partes)
                self.assertIn('data-physis-preferencias="lugar"', h)
                self.assertIn("PxPref.iniciar(", h)
                m = re.search(r'<script id="physis-preferencias">\n(.*?)</script>', h, re.S)
                self.assertIsNotNone(m)
                self.assertEqual(m.group(1), pref, "rode ferramentas/sincronizar.py")
                self.assertIn('html[data-tema="escuro"]', h)
        b = ler("app-nativo", "site", "baixar.html")
        self.assertNotRegex(b, r"(?i)pulseira|caixinha|wristband|pill box")

    def test_5_odf_e_pdfa_nas_telas(self):
        for partes in (("physis-hub", "web", "consultoria.html"), ("sistema", "SustainKit_Definitivo.html"), ("modulos", "planejador", "planejador-physis.html")):
            with self.subTest(partes[-1]):
                h = ler(*partes)
                self.assertIn("window.PhysisODF.acoplar(b, { idiomaTela: idioma, raiz: raiz, titulo: titulo, pdfa: true });", h)
                self.assertIn('<script id="physis-odf">', h)
                self.assertIn("function acoplar(barra, op)", h)
                self.assertIn("/* physis-exportar.js v", h)
        g = ler("sistema", "gestao-interna-physis.html")
        self.assertIn("window.PhysisODF.acoplar(", g)

    def test_6_teste_de_navegador_das_telas(self):
        t = ler("ferramentas", "testes-navegador", "telas.html")
        for tela in ("physis-hub/web/painel.html", "sistema/SustainKit_Definitivo.html", "modulos/planejador/planejador-physis.html",
                     "sistema/gestao-interna-physis.html", "sistema/physis-scada-demo.html", "physis-hub/web/consultoria.html",
                     "physis-hub/web/documento.html", "physis-hub/web/municipio.html", "app-nativo/site/baixar.html"):
            self.assertIn('"%s"' % tela, t, tela)
        for conf in ("sem título principal", "sem a barra de preferências", "sem nome", "rolagem lateral", "erro de JavaScript"):
            self.assertIn(conf, t)

    def test_7_legado_removido(self):
        self.assertFalse((RAIZ / "sistema" / "physis-tela-cliente.html").exists())
        self.assertFalse((RAIZ / "modulos" / "sustainkit" / "01_HTML_versao_atual").exists() and any((RAIZ / "modulos" / "sustainkit" / "01_HTML_versao_atual").iterdir()))
        self.assertIn("physis-tela-cliente/1", ler("sistema", "physis-nucleo.js"), "arquivos exportados antigos continuam importando")

    def test_8_gestao_cursos_e_equipe(self):
        g = ler("sistema", "gestao-interna-physis.html")
        self.assertNotIn("<strong>Ainda não construído.</strong> O desenho desta parte foi aprovado: cursos e turmas", g)
        for trecho in ("function pintarCursos(en)", "physis-gestao-cursos", "[MARCADOR: \" + T(\"preço\", \"price\") + \"]",
                       "window.__gpContas", "(window.__gpContas || []).forEach"):
            self.assertIn(trecho, g, trecho)


if __name__ == "__main__":
    unittest.main()
