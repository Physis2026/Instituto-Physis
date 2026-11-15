"""Base de plantas da lógica de SbN (sistema/physis-plantas.json) e o módulo sistema/physis-sbn.js.

Protege:
1. Cada espécie tem espaçamento com fonte e confiança, clima, solo.textura no padrão do GIS, nativa_de ⊆ cultivavel_em,
   biomas = união, antagonistas e o campo conferir.
2. Companheiras recíprocas, sem invasoras, sem bandejas de viveiro e sem antagonistas; antagonistas recíprocos.
3. Nomes científicos únicos (variedades marcadas em variedade_de; grupos em item_grupo).
4. Nativas por bioma, nativas para APP (preenchimento e diversidade) e madeiras por bioma acima dos mínimos.
5. Os números 1–234 continuam os mesmos (o painel e os planos gravados apontam para eles).
6. physis-sbn.js e ferramentas/conferir-sbn.html sem endereços externos, UTF-8 sem BOM, fim de linha LF.
A lógica em si (consórcios, filtros, mapa) é conferida no navegador por ferramentas/conferir-sbn.html.
"""
import json
import re
import unicodedata
import unittest
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
BASE = RAIZ / "sistema" / "physis-plantas.json"
JS = RAIZ / "sistema" / "physis-sbn.js"
PAGINA = RAIZ / "ferramentas" / "conferir-sbn.html"
NO_REPO = BASE.is_file() and JS.is_file()

BIOMAS = ["Mata Atlântica", "Cerrado", "Caatinga", "Amazônia", "Pampa", "Pantanal"]
TEXTURAS = {"argiloso", "médio", "arenoso"}
MIN_NATIVAS = {"Mata Atlântica": 120, "Cerrado": 85, "Amazônia": 65, "Pampa": 45, "Caatinga": 45, "Pantanal": 30}
MIN_APP = {"Mata Atlântica": 60, "Cerrado": 45, "Amazônia": 35, "Pampa": 30, "Caatinga": 30, "Pantanal": 25}
MIN_MADEIRA = {"Mata Atlântica": 20, "Cerrado": 20, "Amazônia": 15, "Pampa": 8, "Caatinga": 12, "Pantanal": 8}


def norm(s):
    return "".join(c for c in unicodedata.normalize("NFD", str(s).lower()) if unicodedata.category(c) != "Mn").strip()


@unittest.skipUnless(NO_REPO, "só no repositório")
class BaseSbn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = json.loads(BASE.read_text(encoding="utf-8"))
        cls.P = cls.d["plantas"]
        cls.PN = {p["n"]: p for p in cls.P}
        cls.esp = [p for p in cls.P if not p.get("item_viveiro") and not p.get("item_grupo")]

    def test_numeros_estaveis(self):
        ns = [p["n"] for p in self.P]
        self.assertEqual(len(ns), len(set(ns)))
        for n in range(1, 235):
            self.assertIn(n, self.PN)
        self.assertEqual(self.PN[1]["nome"], "Jabuticabeira")
        self.assertEqual(self.PN[95]["nome"], "Feijão (grão)")
        self.assertEqual(self.PN[215]["nome"], "Alho-poró")

    def test_bandejas_de_viveiro_marcadas(self):
        for n in range(199, 204):
            p = self.PN[n]
            self.assertTrue(p["item_viveiro"], n)
            self.assertFalse(p["especie"], n)
            self.assertEqual(p["companheiras"], [])

    def test_campos_de_cada_especie(self):
        fun = {f["id"] for f in self.d["funcoes"]}
        for p in self.esp:
            with self.subTest(p=p["nome"]):
                e = p["espacamento"]
                self.assertGreater(e["entre_plantas_m"], 0)
                self.assertGreater(e["entre_linhas_m"], 0)
                self.assertTrue(e["fonte"])
                self.assertIn(e["confianca"], ("alta", "media", "baixa"))
                c = p["clima"]
                self.assertIn(c["geada"], ("tolera", "sensivel"))
                self.assertLessEqual(c["chuva_mm_ano"][0], c["chuva_mm_ano"][1])
                self.assertLessEqual(c["temp_media_c"][0], c["temp_media_c"][1])
                self.assertTrue(0 <= c["meses_secos_max"] <= 12)
                self.assertIsInstance(c["tmin_tolerada_c"], (int, float))
                self.assertLess(p["altitude_m"][0], p["altitude_m"][1])
                self.assertTrue(p["solo"]["textura"])
                self.assertTrue(set(p["solo"]["textura"]) <= TEXTURAS, p["solo"]["textura"])
                self.assertTrue(set(p["nativa_de"]) <= set(p["cultivavel_em"]) <= set(BIOMAS))
                self.assertEqual(set(p["biomas"]), set(p["cultivavel_em"]))
                self.assertTrue(p["cultivavel_em"], "toda espécie precisa de ao menos um bioma")
                self.assertEqual(p["nativa_br"], bool(p["nativa_de"]))
                self.assertEqual(p["conferir"], bool(p["a_conferir"]))
                self.assertIsInstance(p["antagonistas"], list)
                self.assertIsInstance(p["madeira"], bool)
                self.assertIn("imagem", p)
                self.assertTrue(set(p["funcoes"]) <= fun)
                if p["invasora"]:
                    self.assertFalse(p["restauracao_app"])
                if p["restauracao_app"] and p["nativa_de"] and p["estrato"] in ("emergente", "alto", "medio"):
                    self.assertIn(p["grupo_restauracao"], ("preenchimento", "diversidade", None))

    def test_companheiras_reciprocas_e_limpas(self):
        proibido = {p["n"] for p in self.P if p.get("invasora") or p.get("item_viveiro")}
        for p in self.P:
            for c in p["companheiras"]:
                with self.subTest(a=p["n"], b=c):
                    self.assertIn(c, self.PN)
                    self.assertNotEqual(c, p["n"])
                    self.assertIn(p["n"], self.PN[c]["companheiras"], "companheira não recíproca")
                    self.assertNotIn(c, proibido, "companheira invasora ou de viveiro")
                    self.assertNotIn(c, p["antagonistas"])
            self.assertLessEqual(len(p["companheiras"]), 12)
            if p["n"] in proibido:
                self.assertEqual(p["companheiras"], [])

    def test_antagonistas_reciprocos(self):
        total = 0
        for p in self.P:
            for a in p["antagonistas"]:
                total += 1
                self.assertIn(p["n"], self.PN[a]["antagonistas"], (p["n"], a))
        self.assertGreaterEqual(total, 40)

    def test_nomes_cientificos_unicos(self):
        cont = Counter(norm(p["cientifico"]) for p in self.esp if not p.get("variedade_de"))
        rep = [k for k, v in cont.items() if v > 1]
        self.assertFalse(rep, rep)
        nomes = Counter(norm(p["nome"]) for p in self.P)
        self.assertFalse([k for k, v in nomes.items() if v > 1])
        for p in self.P:
            if p.get("variedade_de"):
                self.assertIn(p["variedade_de"], self.PN)

    def test_nativas_por_bioma(self):
        nat = Counter(b for p in self.esp for b in p["nativa_de"])
        app = Counter(b for p in self.esp if p["restauracao_app"] for b in p["nativa_de"])
        mad = Counter(b for p in self.esp if p["madeira"] for b in p["nativa_de"])
        for b in BIOMAS:
            with self.subTest(bioma=b):
                self.assertGreaterEqual(nat[b], MIN_NATIVAS[b])
                self.assertGreaterEqual(app[b], MIN_APP[b])
                self.assertGreaterEqual(mad[b], MIN_MADEIRA[b])
                for g in ("preenchimento", "diversidade"):
                    q = sum(1 for p in self.esp if p["restauracao_app"] and b in p["nativa_de"] and p.get("grupo_restauracao") == g)
                    self.assertGreaterEqual(q, 5, g)

    def test_especies_conhecidas_da_caatinga(self):
        cient = {norm(p["cientifico"]): p for p in self.esp}
        for c in ("Spondias tuberosa", "Sarcomphalus joazeiro", "Cereus jamacaru", "Cenostigma pyramidale", "Astronium urundeuva"):
            self.assertIn("Caatinga", cient[norm(c)]["nativa_de"], c)

    def test_combinacoes_tem_planta_na_base(self):
        """os nomes usados nas combinações A/B/C continuam na base (a correção do texto depende disso)"""
        nomes = {norm(p["nome"]) for p in self.P}
        for e in self.d["espacos"]:
            for k, t in (e.get("combinacoes") or {}).items():
                antes = t.split("→")[0]
                if "→" in t or "+" in antes:
                    continue
                for m in re.finditer(r"(\d+)\s*×\s*([^,]+?)(?=,\s*\d+\s*×|$)", re.sub(r"^[^:\d×]{3,}:\s*", "", antes.strip())):
                    self.assertIn(norm(m.group(2)), nomes, (e["nome"], k, m.group(2)))


@unittest.skipUnless(NO_REPO, "só no repositório")
class ModuloSbn(unittest.TestCase):
    def test_sem_enderecos_externos(self):
        for arq in (JS, PAGINA):
            t = arq.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"https?://", t), arq.name)
            self.assertNotIn("import(", t)

    def test_codificacao(self):
        for arq in (JS, PAGINA, BASE):
            b = arq.read_bytes()
            self.assertFalse(b.startswith(b"\xef\xbb\xbf"), arq.name + " com BOM")
            self.assertNotIn(b"\r\n", b, arq.name + " com CRLF")

    def test_api(self):
        t = JS.read_text(encoding="utf-8")
        self.assertIn("raiz.SBN_LOGICA = api", t)
        for nome in ("filtrar", "montarConsorcio", "mudas", "lerTerreno", "corrigirCombinacao", "telaSbnConsorcio", "telaSbnAreas",
                     "telaSbnMapa", "telaSbnUcs", "ligarMapa", "gradePlantio", "estadoMapa", "criteriosDoLugar", "ucsDoLugar", "verificar", "carregar",
                     "telaSbnConferencia", "itensConferencia", "ligarConferencia", "conferenciaCsv"):
            self.assertRegex(t, r"\b" + nome + r"\b[,\s}]", nome)
        self.assertIn("physis.terreno.v1", t)
        # chaves equilibradas (conferência barata de sintaxe; a página de conferência roda o código de verdade)
        sem_txt = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
        self.assertEqual(sem_txt.count("{") - sem_txt.count("}"), 0)


if __name__ == "__main__":
    unittest.main()
