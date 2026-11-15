"""Camada "Metodologia e normas": cada cálculo diz como é feito, qual norma segue e em que situação está.

Protege:
1. sistema/physis-metodologia.json tem o formato combinado (módulos, cálculos, normas, adequações).
2. Cada aba da plataforma (lista ABAS do painel) tem entrada; aba sem cálculo explica por quê.
3. Cada cálculo cita pelo menos uma norma ou diz "sem norma aplicável"; toda norma citada está no catálogo.
4. As premissas citadas existem em sistema/physis-premissas.json.
5. Nada parece cópia de texto de norma (nenhuma citação entre aspas com mais de 200 caracteres).
6. sistema/physis-metodologia.js leva os mesmos dados do JSON, não tem endereço de internet e monta a seção
   acessível (details/summary, tabela com caption, selos ok/at/al/in).

Só roda dentro do repositório (no pacote do cliente, sistema/ pode não ir).
"""
import json
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
JSON = RAIZ / "sistema" / "physis-metodologia.json"
JS = RAIZ / "sistema" / "physis-metodologia.js"
PREMISSAS = RAIZ / "sistema" / "physis-premissas.json"
PAINEL = RAIZ / "physis-hub" / "web" / "painel.html"
NO_REPO = JSON.is_file() and JS.is_file()

STATUS = {"conforme": "ok", "simplificado": "at", "só citado": "in", "falta implementar": "al"}
CAMPOS_CALCULO = ["id", "nome", "o_que_calcula", "formula", "premissas", "normas", "limites_de_validade",
                  "fonte_de_dados", "status", "o_que_falta", "onde"]
SEM_NORMA = "sem norma aplicável"
ASPAS = re.compile(r"“([^”]*)”|\"([^\"]*)\"|‘([^’]*)’|«([^»]*)»")


def textos(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from textos(v)
    elif isinstance(o, list):
        for v in o:
            yield from textos(v)


@unittest.skipUnless(NO_REPO, "só no repositório")
class Metodologia(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = json.loads(JSON.read_text(encoding="utf-8"))
        cls.js = JS.read_text(encoding="utf-8")
        cls.calcs = [(mk, c) for mk, m in cls.d["modulos"].items() for c in m["calculos"]]

    def test_formato(self):
        for chave in ("versao", "atualizado", "aviso", "status", "modulos", "adequacoes", "normas"):
            self.assertIn(chave, self.d)
        self.assertEqual({k: v["selo"] for k, v in self.d["status"].items()}, STATUS)
        self.assertIn("ART", self.d["aviso"])
        self.assertIn("versão oficial vigente", self.d["aviso"])
        ids = set()
        for mk, m in self.d["modulos"].items():
            self.assertTrue(m.get("nome"), mk)
            self.assertIsInstance(m.get("calculos"), list, mk)
            if not m["calculos"]:
                self.assertTrue(m.get("sem_calculo"), f"{mk}: aba sem cálculo precisa dizer por quê")
        for mk, c in self.calcs:
            for campo in CAMPOS_CALCULO:
                self.assertIn(campo, c, f"{mk}/{c.get('id')}: falta {campo}")
            self.assertNotIn(c["id"], ids, "id repetido: " + c["id"])
            ids.add(c["id"])
            self.assertIn(c["status"], STATUS, c["id"])
            self.assertTrue(c["formula"].get("texto"), c["id"])
            for x in c["formula"].get("variaveis", []):
                self.assertTrue(x.get("simbolo") and x.get("significado") and "unidade" in x, c["id"])
            if c["status"] != "conforme":
                self.assertTrue(c["o_que_falta"].strip(), f"{c['id']}: '{c['status']}' sem dizer o que falta")
        for norma in self.d["normas"].values():
            for campo in ("tipo", "assunto", "edicao", "situacao"):
                self.assertIn(campo, norma)

    def test_cada_aba_tem_entrada(self):
        if not PAINEL.is_file():
            self.skipTest("painel não encontrado")
        m = re.search(r"const ABAS = \[(.*?)\];", PAINEL.read_text(encoding="utf-8"), re.S)
        self.assertIsNotNone(m, "lista ABAS não encontrada no painel")
        abas = re.findall(r'\["([\w-]+)",', m.group(1))
        self.assertGreater(len(abas), 10)
        faltam = [a for a in abas if a not in self.d["modulos"]]
        self.assertEqual(faltam, [], "abas sem metodologia")

    def test_cada_calculo_tem_norma_ou_diz_que_nao_tem(self):
        for mk, c in self.calcs:
            self.assertGreaterEqual(len(c["normas"]), 1, f"{c['id']}: sem norma nem '{SEM_NORMA}'")
            for n in c["normas"]:
                self.assertIn(n["codigo"], self.d["normas"], f"{c['id']}: {n['codigo']} fora do catálogo")
                for campo in ("edicao", "item", "como_e_usada"):
                    self.assertIn(campo, n, c["id"])
                if n["codigo"] != SEM_NORMA:
                    self.assertTrue(n["item"].strip(), f"{c['id']}: {n['codigo']} sem item")
                    self.assertEqual(n["edicao"], self.d["normas"][n["codigo"]]["edicao"], c["id"])

    def test_premissas_existem(self):
        base = {p["id"] for p in json.loads(PREMISSAS.read_text(encoding="utf-8"))["premissas"]}
        for mk, c in self.calcs:
            for p in c["premissas"]:
                self.assertIn(p, base, f"{c['id']}: premissa {p} não está em physis-premissas.json")

    def test_adequacoes(self):
        ids = {c["id"] for _, c in self.calcs}
        prio = [a["prioridade"] for a in self.d["adequacoes"]]
        self.assertEqual(len(prio), len(set(prio)), "prioridade repetida")
        for a in self.d["adequacoes"]:
            self.assertIn(a["quem"], ("software", "engenharia"))
            self.assertTrue(a["o_que_fazer"] and a["criterio_de_aceite"])
            for i in a["calculos"]:
                self.assertIn(i, ids, f"adequação {a['prioridade']} aponta para {i}")
        # todo cálculo que não está conforme tem pelo menos uma adequação ou explica o que falta
        cobertos = {i for a in self.d["adequacoes"] for i in a["calculos"]}
        for _, c in self.calcs:
            if c["status"] == "falta implementar":
                self.assertIn(c["id"], cobertos, f"{c['id']}: falta implementar sem adequação na lista")

    def test_sem_texto_de_norma(self):
        for t in textos(self.d):
            for m in ASPAS.finditer(t):
                trecho = next(g for g in m.groups() if g is not None)
                self.assertLessEqual(len(trecho), 200, "citação longa entre aspas: " + trecho[:60])
        for _, c in self.calcs:
            for n in c["normas"]:
                self.assertLessEqual(len(n["como_e_usada"]), 300, f"{c['id']}: explicação longa demais, resuma")

    def test_edicoes_substituidas(self):
        texto = JSON.read_text(encoding="utf-8")
        self.assertNotIn("15527:2007", texto)
        self.assertNotIn("309/2019", texto)
        achados = [texto[max(0, m.start() - 40):m.end() + 10] for m in re.finditer(r"\b45\s*%", texto)]
        self.assertEqual(achados, [], "APP em encosta é 45° (= 100%), nunca 45%")

    def test_js_igual_ao_json(self):
        m = re.search(r"/\*DADOS-INICIO\*/\s*const DADOS = (.*?);\s*/\*DADOS-FIM\*/", self.js, re.S)
        self.assertIsNotNone(m, "bloco de dados não encontrado no JS")
        self.assertEqual(json.loads(m.group(1)), self.d, "physis-metodologia.js diferente do JSON: copie de novo")

    def test_js_sem_internet_e_acessivel(self):
        self.assertNotRegex(self.js, r"https?://|//cdn|www\.", "endereço de internet no renderizador")
        for trecho in ("window.metodologiaHtml", "window.PHYSIS_METODOLOGIA", "<details", "<summary>", "<caption",
                       'scope="col"', "aria-labelledby", "selo "):
            self.assertIn(trecho, self.js)
        for classe in STATUS.values():
            self.assertIn(f'"{classe}"', self.js)
        self.assertNotIn("<h1", self.js, "a seção não pode ter outro título principal")


if __name__ == "__main__":
    unittest.main()
