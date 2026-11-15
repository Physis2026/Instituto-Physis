"""Resultados do Planejador e do SustainKit gravados para a plataforma, e a base de materiais embutida nos dois.

Protege:
1. As cópias embutidas da base de materiais (<script id="base-materiais">) são iguais a sistema/physis-materiais.json
   (rodar ferramentas/embutir_materiais.py não muda nada) e os dois programas leem primeiro a do documento pai.
2. O Planejador calcula esgoto e biogás pelas funções physisSaneamento e physisBiogas (uma conta só, com as
   constantes da NBR 7229/13969 e as premissas do Planejador) e grava physis-calc-esgoto, -biogas e -materiais.
3. O SustainKit grava as mesmas chaves com fonte "SustainKit" e não usa mais a lista antiga MATERIAIS (com preços).
4. A zona bioclimática pode ser escolhida no Cadastro do SustainKit (1 a 8).
"""
import importlib.util
import json
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
BASE = RAIZ / "sistema" / "physis-materiais.json"
SK = RAIZ / "sistema" / "SustainKit_Definitivo.html"
PL = RAIZ / "modulos" / "planejador" / "planejador-physis.html"
FERR = RAIZ / "ferramentas" / "embutir_materiais.py"
NO_REPO = BASE.is_file() and SK.is_file() and PL.is_file() and FERR.is_file()


def bloco_json(html, ident):
    m = re.search(r'<script type="application/json" id="%s">(.*?)</script>' % re.escape(ident), html, re.S)
    return json.loads(m.group(1).replace("<\\/", "</")) if m else None


@unittest.skipUnless(NO_REPO, "só no repositório")
class CalcProgramas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sk = SK.read_text(encoding="utf-8")
        cls.pl = PL.read_text(encoding="utf-8")
        cls.base = json.loads(BASE.read_text(encoding="utf-8"))

    def test_base_embutida_igual(self):
        spec = importlib.util.spec_from_file_location("embutir_materiais", FERR)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for html, nome in ((self.sk, "SustainKit"), (self.pl, "Planejador")):
            with self.subTest(nome):
                self.assertEqual(bloco_json(html, "base-materiais"), self.base)
                self.assertEqual(html.count('id="base-materiais"'), 1)
                self.assertEqual(mod.embutir(html), html, "rode ferramentas/embutir_materiais.py")
                self.assertIn('window.parent.document.getElementById(', html)       # dentro da plataforma, a base do pai

    def test_planejador_uma_conta_so(self):
        run = self.pl[self.pl.index("function run(){"):]
        fim = run.index("MOD.verificar(R,C);", run.index("/* esgoto */"))
        run = run[:run.index("return R}", fim) + 9]
        self.assertIn("R.esg=physisSaneamento(Cdia,Lf,S.clima.temp,S.solo.ci);", run)
        self.assertIn("R.bio=physisBiogas(Nb,S.premissas.negras||20,res);", run)
        self.assertNotIn("fossa:(1000", run)                                       # nenhuma segunda fórmula dentro de run()
        so = re.sub(r"\s+", "", self.pl)
        for trecho in ("varT=C<=1500?1:C<=3000?0.92:C<=4500?0.83:C<=6000?0.75:C<=7500?0.67:C<=9000?0.58:0.5",
                       "varK=temp>20?57:temp>10?65:94", "fossa:(1000+C*T+K*Lf)/1000", "filtro:1.6*C*T/1000",
                       "if(ci)r.inf=C/ci", "varvol=(Nb*negras+res)*35*1.25/1000", "vargas=Nb*0.04+res*0.1",
                       "kwh:gas*6,fogao:gas/0.35"):
            self.assertIn(trecho, so, trecho)
        self.assertIn("physisPlanejadorGravar(R,S)", run)
        for chave in ("physis-calc-esgoto", "physis-calc-biogas", "physis-calc-materiais"):
            self.assertIn('"%s"' % chave, self.pl)
        self.assertIn('fonte: "Planejador"', self.pl)

    def test_sustainkit_grava_e_sem_lista_antiga(self):
        for chave in ("physis-calc-esgoto", "physis-calc-biogas", "physis-calc-materiais"):
            self.assertIn("'%s'" % chave, self.sk)
        self.assertIn("fonte:'SustainKit'", self.sk)
        self.assertNotIn("const MATERIAIS=[", self.sk)
        self.assertNotRegex(self.sk, r"custo:'R\$")                                 # preço inventado da lista antiga
        self.assertIn("a cotar (SINAPI/cotação)", self.sk)

    def test_zona_no_cadastro(self):
        m = re.search(r'<select id="s-zona"[^>]*>(.*?)</select>', self.sk, re.S)
        self.assertIsNotNone(m)
        self.assertEqual(re.findall(r'<option value="(\d)">', m.group(1)), [str(i) for i in range(1, 9)])

    def test_composicoes_e_nomes_em_ingles(self):
        sk = bloco_json(self.sk, "base-materiais")
        texto_sk = self.sk[self.sk.rindex("    dicionario: {"):]
        for c in sk["composicoes"]:
            self.assertIn(json.dumps(c["nome"], ensure_ascii=False) + ":", texto_sk, c["nome"])
        for m in sk["materiais"]:
            self.assertIn(json.dumps(m["nome"], ensure_ascii=False) + ":", texto_sk, m["nome"])
        texto_pl = self.pl[self.pl.index("  var T = {"):]
        for c in sk["composicoes"]:
            self.assertIn(json.dumps(c["nome"], ensure_ascii=False) + ":", texto_pl, c["nome"])


if __name__ == "__main__":
    unittest.main()
