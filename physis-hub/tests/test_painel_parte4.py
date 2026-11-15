"""Painel, integração parte 4: Secador solar (em desenvolvimento), Servidor verde só interno, loja por link
(/loja/?item=<id>), Esgoto e biogás na Economia circular com as MESMAS contas do Planejador e base de materiais embutida.

Protege:
1. A aba Secador solar existe na etapa 3, entre Monitoramento verde e Animais, com módulo embutido, selo
   "Em desenvolvimento", entrada no MODS_PLAN e na COM_INTERFACE; P23 e Servidor verde seguem em desenvolvimento (fora da venda).
2. O link /loja/?item= usa a mesma regra do "Comprar" do Experimente agora (lojaLevar).
3. As constantes e fórmulas de esgoto e biogás do painel são as do Planejador (nenhuma terceira fórmula) e dão os
   números do caso de mesa.
4. Bases embutidas: materiais (para o SustainKit dentro da plataforma) e o inglês do Secador.
"""
import json
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PAINEL = RAIZ / "physis-hub" / "web" / "painel.html"
PLAN = RAIZ / "modulos" / "planejador" / "planejador-physis.html"
CM = RAIZ / "sistema" / "physis-circular-mapa.js"
NO_REPO = PAINEL.is_file() and PLAN.is_file()


def bloco_json(html, ident):
    m = re.search(r'<script type="application/json" id="%s">(.*?)</script>' % re.escape(ident), html, re.S)
    return json.loads(m.group(1).replace("<\\/", "</")) if m else None


@unittest.skipUnless(NO_REPO, "só no repositório")
class Parte4(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = PAINEL.read_text(encoding="utf-8")
        cls.p = PLAN.read_text(encoding="utf-8")

    # 1. Secador solar e itens em desenvolvimento
    def test_aba_secador(self):
        abas = re.search(r"const ABAS = \[(.*?)\];", self.h, re.S).group(1)
        ids = re.findall(r'\["(\w+)","', abas)
        self.assertEqual(ids[ids.index("campo") + 1:ids.index("campo") + 3], ["secador", "animais"])
        self.assertIn('"secador"', re.search(r"const COM_INTERFACE = new Set\(\[(.*?)\]\)", self.h).group(1))
        self.assertRegex(self.h, r"\n  secador: \{ grupo:")
        self.assertIn('secador:"Secador solar"', self.h)
        self.assertIn('secador: () => typeof telaSecador === "function" ? seloDev(telaSecador(),', self.h)
        self.assertIn('"certificacoes","secador"].includes(ui.aba)', self.h)          # clima carregado no modo hub
        self.assertIn('<script id="mod-secador">', self.h)
        self.assertIn("<strong>Em desenvolvimento.</strong>", self.h)

    def test_itens_em_desenvolvimento_fora_da_venda(self):
        self.assertIn('P("P23","Secador solar"', self.h)                            # P() nasce com st:"dev"
        self.assertRegex(self.h, r'\{ id:"servidor-verde", g:"pdi",[^}]*st:"dev" \}')
        vend = re.search(r"const LOJA_VENDA = new Set\(\[(.*?)\]\)", self.h).group(1)   # VENDAVEIS usa LOJA_VENDA desde 15/11/2026
        self.assertNotIn("P23", vend)
        self.assertNotIn("servidor-verde", vend)

    def test_aba_servidor_verde(self):
        abas = re.findall(r'\["([\w-]+)","', re.search(r"const ABAS = \[(.*?)\];", self.h, re.S).group(1))
        self.assertEqual(abas[abas.index("solar"):abas.index("solar") + 4], ["solar", "avac", "servidor-verde", "turbinas"])
        self.assertIn('"servidor-verde"', re.search(r"const COM_INTERFACE = new Set\(\[(.*?)\]\)", self.h).group(1))
        dev = re.search(r"const ABAS_DEV = new Set\(\[(.*?)\]\);", self.h)
        self.assertIsNotNone(dev)
        for a in ("secador", "servidor-verde"):            # desde 15/11/2026 o conjunto tem todos os módulos em desenvolvimento
            self.assertIn('"%s"' % a, dev.group(1))
        self.assertIn('"servidor-verde": { grupo:', self.h)
        self.assertIn('"servidor-verde": () => { if (typeof telaServidorVerde !== "function") return telaPlanejado("servidor-verde");', self.h)
        self.assertIn('<script id="mod-servidor-verde">', self.h)
        self.assertIsNotNone(bloco_json(self.h, "base-servidor-catalogo"))
        self.assertNotRegex(self.h, r"SERVIDOR_VERDE_PRONTO\s*=\s*true\s*;")          # continua em desenvolvimento
        cat = re.search(r'\{ id:"servidor-verde", g:"pdi",[^}]*\}', self.h).group(0)
        self.assertNotIn("Eric", cat)                                               # responsável é informação interna

    # 2. Loja por link
    def test_loja_por_link(self):
        self.assertIn("function lojaLevar(q)", self.h)
        self.assertIn("function lojaItemDaUrl()", self.h)
        self.assertIn('new URLSearchParams(location.search).get("item")', self.h)
        self.assertIn("acoplarOdf(); lojaItemDaUrl();", self.h)
        self.assertIn("const { alvo, nome } = lojaLevar(q);", self.h)                # o Comprar do Experimente agora usa a mesma regra
        self.assertIn('data-cartao="${esc(c.id)}"', self.h)
        self.assertIn('data-cartao="sk-pacote"', self.h)
        self.assertIn(".sol.destaque{", self.h)
        self.assertIn('anunciar("Adicionado à sua seleção: " + r.nome + ".")', self.h)
        self.assertIn('el("m-pers")', self.h[self.h.index("function lojaItemDaUrl()"):])

    # 3. Esgoto e biogás com as contas do Planejador
    def test_constantes_iguais_ao_planejador(self):
        tipos = {k: (u, float(c), float(l)) for k, u, c, l in re.findall(r"\n (\w+):\{n:'[^']*',cat:'ed'[^}]*?uso:'(\w)'[^}]*?esg:\[([\d.]+),([\d.]+)\]", self.p)}
        self.assertIn("residencia", tipos)
        eb = {k: (float(c), float(l), float(n)) for k, c, l, n in re.findall(r'(\w+):\["[^"]*", ([\d.]+), ([\d.]+), ([\d.]+)\]', re.search(r"const EB_TIPOS = \{(.*?)\};", self.h).group(1))}
        for k, (c, l, nb) in eb.items():
            u, cp, lp = tipos[k]
            self.assertEqual((c, l), (cp, lp), k)
            self.assertEqual(nb, 1.0 if u in "AB" else 0.3 if u == "D" else 0.0, k)
        solos = {k: float(ci) for k, ci in re.findall(r"(\w+):\['[^']*',\d+,(\d+)\]", re.search(r"const SOLOS=\{(.*?)\};", self.p).group(1))}
        solos_eb = {k: float(ci) for k, ci in re.findall(r'(\w+):\["[^"]*", (\d+)\]', re.search(r"const EB_SOLOS = \{(.*?)\};", self.h).group(1))}
        self.assertEqual(solos_eb, solos)

    def test_formulas_iguais_ao_planejador(self):
        """physisSaneamento e physisBiogas: cópia letra por letra do bloco physis-calc-planejador do Planejador."""
        for nome in ("physisSaneamento", "physisBiogas"):
            rx = re.compile(r"function %s\(.*?\n\}\n" % nome, re.S)
            no_plan, no_painel = rx.search(self.p), rx.search(self.h)
            self.assertIsNotNone(no_plan, nome)
            self.assertIsNotNone(no_painel, nome)
            self.assertEqual(no_painel.group(0), no_plan.group(0), f"{nome} do painel difere da do Planejador")
        so = lambda s: re.sub(r"\s+", "", s)
        # o mesmo caminho do run(): 20 °C e 20 L de águas negras quando vazios; usos A e B inteiros, D × 0,3
        self.assertIn(so("R.bio=physisBiogas(Nb,S.premissas.negras||20,res)"), so(self.p))
        self.assertIn(so("physisSaneamento(Cdia, Lf, o.temp == null ? 20 : o.temp, o.ci)"), so(self.h))
        self.assertIn(so("negras = o.negras || 20"), so(self.h))
        self.assertIn(so("['A','B'].includes(TIPOS[i.tipo].uso)?(i.ocup||0):TIPOS[i.tipo].uso==='D'?(i.ocup||0)*0.3:0"), so(self.p))
        self.assertIn('const EB_RES_PLANEJADOR = ["alimentos"];', self.h)     # só cozinha tem biogás por kg no Planejador; o resto é [MARCADOR]

    def test_caso_de_mesa(self):
        # 5 moradores e 10 colaboradores, 20 °C (padrão do Planejador), argila: contas à mão com a NBR 7229 e a NBR 13969
        cdia, lf = 5 * 130 + 10 * 50, 5 * 1 + 10 * 0.2               # 1.150 L/dia; 7 L/dia
        t, k = 1, 65                                                  # Cdia ≤ 1.500; 10 < 20 ≤ 20
        self.assertAlmostEqual((1000 + cdia * t + k * lf) / 1000, 2.605)
        self.assertAlmostEqual(1.6 * cdia * t / 1000, 1.84)
        self.assertAlmostEqual(cdia / 20, 57.5)
        nb = 5 + 10 * 0.3                                             # biodigestor: pessoas-equivalentes
        self.assertAlmostEqual((nb * 20 + 2) * 35 * 1.25 / 1000, 7.0875)   # + 2 kg/dia de restos de alimentos
        self.assertAlmostEqual(nb * 0.04 + 2 * 0.1, 0.52)

    def test_parte_esgoto_e_biogas(self):
        self.assertIn('["esgoto","Esgoto e biogás"]', self.h)
        self.assertIn("function telaEsgotoBiogas()", self.h)
        for k in ('ebRegistros("esgoto")', 'ebRegistros("biogas")', "function ebRegistros(k){ const v = calcLer(k)"):   # physis-calc-esgoto e physis-calc-biogas
            self.assertIn(k, self.h)
        self.assertIn('pick(re, "planejador")', self.h)                                    # Planejador antes do SustainKit
        self.assertIn("const esgoto = e.p || e.s || est.esgoto, biogas = b.p || b.s || est.biogas;", self.h)
        self.assertIn("Math.abs(a - b) / Math.max(a, b) > 0.2", self.h)                   # aviso de diferença > 20%
        self.assertIn("NBR 17076:2024", self.h)
        self.assertIn('<script id="mod-circular-mapa">', self.h)
        cm = CM.read_text(encoding="utf-8")
        self.assertIn("rcExtrasFluxo()", cm)
        self.assertIn("if (!r.extra) { tot += kg;", cm)                                    # fora do desvio do aterro
        self.assertEqual(self.h.count("<h1>Economia circular</h1>"), 1)

    # 4. Bases embutidas
    def test_bases(self):
        m = bloco_json(self.h, "base-materiais")
        self.assertEqual(m, json.loads((RAIZ / "sistema" / "physis-materiais.json").read_text(encoding="utf-8")))
        i18n = bloco_json(self.h, "base-i18n-modulos")["I18N"]
        js = (RAIZ / "sistema" / "physis-secador.js").read_text(encoding="utf-8")
        sec = json.loads(re.search(r"window\.SECADOR_I18N = (\{.*?\n\});", js, re.S).group(1))
        do_painel = json.loads(re.search(r"\nconst I18N = (\{.*?\});\n", self.h, re.S).group(1))
        self.assertEqual([k for k in sec if k not in i18n and k not in do_painel], [])
        for k in ("Esgoto e biogás", "Em desenvolvimento.", "Servidor verde"):
            self.assertIn(k, i18n)
        self.assertIn("window.SECADOR_I18N, window.SERVIDOR_VERDE_I18N", self.h)       # e em tempo de execução


if __name__ == "__main__":
    unittest.main()
