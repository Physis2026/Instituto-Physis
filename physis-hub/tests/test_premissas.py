"""Premissas técnicas e edições de normas iguais em todas as ferramentas.

Protege:
1. A base de premissas (sistema/physis-premissas.json) existe e cada premissa obrigatória
   tem valor padrão, unidade e fonte.
2. Nenhum programa cita como atual uma edição já substituída:
   NBR 15527:2007, Portaria 309/2019 ou LEED v4.1 (v4.1 só pode aparecer como legado).
3. O limite de APP em encosta é 45° (= 100%), nunca "45%".
4. O fator de emissão da rede é o mesmo na base de premissas e no núcleo.

Só roda dentro do repositório (no pacote do cliente, sistema/physis-premissas.json pode não ir).
"""
import json
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
BASE = RAIZ / "sistema" / "physis-premissas.json"
NO_REPO = BASE.is_file() and (RAIZ / "modulos" / "planejador").is_dir()

PROGRAMAS = ["sistema/*.html", "modulos/planejador/*.html"]
OBRIGATORIAS = ["agua.per_capita", "chuva.coef_escoamento", "app.declividade", "pv.pr",
                "bateria.dod", "rede.fator_emissao"]
NORMAS = ["ABNT NBR 15527", "ABNT NBR 5419", "Portaria Inmetro nº 309/2022", "ABNT NBR 10004",
          "ABNT NBR 15220", "LEED"]
# Blocos grandes em base64 (bibliotecas e imagens embutidas) não são texto do programa.
BASE64 = re.compile(r"[A-Za-z0-9+/=]{400,}")


def textos():
    for padrao in PROGRAMAS:
        for arq in sorted(RAIZ.glob(padrao)):
            yield arq, BASE64.sub(" ", arq.read_text(encoding="utf-8", errors="replace"))


@unittest.skipUnless(NO_REPO, "só no repositório")
class Premissas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = json.loads(BASE.read_text(encoding="utf-8"))
        cls.por_id = {p["id"]: p for p in cls.base["premissas"]}

    def test_premissas_obrigatorias(self):
        for ident in OBRIGATORIAS:
            with self.subTest(ident):
                p = self.por_id.get(ident)
                self.assertIsNotNone(p, f"falta a premissa {ident}")
                for campo in ("grandeza", "valor_padrao", "unidade", "fonte", "opcoes"):
                    self.assertIn(campo, p, f"{ident}: falta {campo}")
                self.assertTrue(str(p["unidade"]).strip(), f"{ident}: unidade vazia")
                self.assertTrue(str(p["fonte"]).strip(), f"{ident}: fonte vazia")
                for o in p["opcoes"]:
                    self.assertTrue({"rotulo", "valor", "quando"} <= set(o), f"{ident}: opção incompleta {o}")

    def test_valores_combinados(self):
        agua = self.por_id["agua.per_capita"]
        self.assertEqual(agua["valor_padrao"], 130)
        valores = {o["valor"] for o in agua["opcoes"]}
        self.assertTrue({160, 130, 100} <= valores, "água por pessoa: faltam os padrões alto, médio e baixo")
        self.assertEqual(self.por_id["chuva.coef_escoamento"]["valor_padrao"], 0.80)
        self.assertEqual(self.por_id["app.declividade"]["valor_padrao"], 45)
        self.assertIn("°", self.por_id["app.declividade"]["unidade"].replace("graus", "°"))
        self.assertEqual(self.por_id["pv.pr"]["valor_padrao"], 0.78)

    def test_normas_com_edicao(self):
        normas = self.base.get("normas", {})
        for n in NORMAS:
            with self.subTest(n):
                self.assertIn(n, normas)
                self.assertTrue(str(normas[n].get("edicao", "")).strip(), f"{n}: sem edição")
        self.assertEqual(normas["ABNT NBR 15527"]["edicao"], "2019")
        self.assertEqual(normas["LEED"]["edicao"], "v5")

    def test_fator_da_rede_igual_ao_nucleo(self):
        nucleo = (RAIZ / "sistema" / "physis-nucleo.js").read_text(encoding="utf-8")
        m = re.search(r"var FATORES = \{\s*rede:\s*([0-9.]+)", nucleo)
        self.assertIsNotNone(m, "não achei FATORES.rede no núcleo")
        self.assertAlmostEqual(float(m.group(1)), self.por_id["rede.fator_emissao"]["valor_padrao"])

    def test_programas_sem_edicao_substituida(self):
        achados = []
        for arq, texto in textos():
            nome = arq.relative_to(RAIZ)
            for proibido in (r"NBR\s*15527\s*[:/]\s*2007", r"309\s*/\s*2019", r"MDIC\s*309"):
                for m in re.finditer(proibido, texto, re.I):
                    achados.append(f"{nome}: {texto[max(0, m.start() - 40):m.end() + 40]!r}")
            for m in re.finditer(r"v4\.1", texto):
                perto = texto[max(0, m.start() - 60):m.end() + 60]
                if not re.search(r"legado|legacy", perto, re.I):
                    achados.append(f"{nome}: LEED v4.1 sem 'legado': {perto!r}")
        self.assertEqual(achados, [], "edição substituída citada como atual")

    def test_app_e_45_graus(self):
        achados = []
        for arq, texto in textos():
            for m in re.finditer(r"45\s*%", texto):
                perto = texto[max(0, m.start() - 80):m.end() + 80]
                if re.search(r"\bAPP\b|Código Florestal|preservação permanente|encosta", perto, re.I):
                    achados.append(f"{arq.relative_to(RAIZ)}: {perto!r}")
        self.assertEqual(achados, [], "APP escrita como 45% (o limite é 45° = 100%)")


if __name__ == "__main__":
    unittest.main()
