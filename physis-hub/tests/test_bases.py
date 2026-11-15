"""Bases de dados embutidas na plataforma (plantas, certificações) iguais aos arquivos de origem.

Protege:
1. sistema/physis-plantas.json tem as 234 plantas, as 14 funções e os 30 espaços das planilhas v88.
2. A base de certificações, quando existe, tem ids únicos e critérios com texto.
3. A cópia dentro do painel.html é a atual (rodar ferramentas/embutir_bases.py não muda nada).
Só roda dentro do repositório.
"""
import importlib.util
import json
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
NO_REPO = (RAIZ / "ferramentas" / "embutir_bases.py").is_file()


@unittest.skipUnless(NO_REPO, "só no repositório")
class Bases(unittest.TestCase):
    def test_plantas(self):
        d = json.loads((RAIZ / "sistema" / "physis-plantas.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(d["plantas"]), 234)
        self.assertEqual(len(d["funcoes"]), 14)
        self.assertGreaterEqual(len(d["espacos"]), 30)
        ids = {f["id"] for f in d["funcoes"]}
        for p in d["plantas"]:
            self.assertTrue(p["nome"]); self.assertTrue(set(p["funcoes"]) <= ids, p["nome"])

    def test_certificacoes(self):
        arq = RAIZ / "sistema" / "physis-certificacoes.json"
        if not arq.is_file():
            self.skipTest("base de certificações ainda não gerada")
        d = json.loads(arq.read_text(encoding="utf-8"))
        vistos = set()
        for c in d["certificacoes"]:
            for g in c["grupos"]:
                for k in g["criterios"]:
                    self.assertNotIn(k["id"], vistos); vistos.add(k["id"]); self.assertTrue(k["texto"].strip())
        texto = arq.read_text(encoding="utf-8")
        for proibido in ("GIZ", "Siemens"):
            self.assertNotIn(proibido, texto)

    def test_painel_com_bases_atuais(self):
        spec = importlib.util.spec_from_file_location("embutir_bases", RAIZ / "ferramentas" / "embutir_bases.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        html = mod.PAINEL.read_text(encoding="utf-8")
        self.assertEqual(mod.embutir(html), html, "rode ferramentas/embutir_bases.py")


if __name__ == "__main__":
    unittest.main()
