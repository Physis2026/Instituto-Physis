"""D17 (15/11/2026): quatro níveis por certificação da loja, numa tabela só (physis-certificacoes.json → niveis_loja).

N1 gap analysis (aba Certificações, a partir de R$ 750,00); N2 sistema detalhado (N1 + evidências + abas tiradas dos
campos "auto" dos critérios; AVAC só nas de edificação); N3 = N2 + consultoria personalizada; N4 = N3 + M&V (IPMVP).
Preços da D19: N2 R$ 5.000,00; N3 a partir de R$ 30.000,00; N4 a partir de R$ 50.000,00. D20: o SustainKit entra no N4
(gancho sustainkit_d20 = "n4" na tabela; o painel e hub.ITEM_MODULOS seguem a mesma regra).
`modulos_do_nivel` é o espelho de certModulosNivel (painel) e a regra das entradas cert-<id>-nK de hub.ITEM_MODULOS.
"""
import json
import unittest
from pathlib import Path

from physis_hub.hub import Hub

RAIZ = Path(__file__).resolve().parents[2]
BASE = RAIZ / "sistema" / "physis-certificacoes.json"
PAINEL = RAIZ / "physis-hub" / "web" / "painel.html"
NO_REPO = BASE.is_file() and PAINEL.is_file()


def modulos_do_nivel(base: dict, cert_id: str, n: int) -> tuple:
    t = base["niveis_loja"]
    c = next((x for x in base["certificacoes"] if x["id"] == cert_id), None)
    mods = {"certificacoes"}

    def anda(o):
        if isinstance(o, list):
            for x in o:
                anda(x)
        elif isinstance(o, dict):
            if o.get("auto") and o["auto"] in t["modulo_por_criterio"]:
                mods.add(t["modulo_por_criterio"][o["auto"]])
            for v in o.values():
                anda(v)
    if n >= 2 and c:
        anda(c["grupos"])
        if cert_id in t["avac_em"]:
            mods.add("avac")
    if n >= 4:
        mods.update(t["mv_modulos"])
    d20 = t.get("sustainkit_d20")
    if (d20 == "n4" and n >= 4) or (d20 == "n2" and n >= 2):
        mods.add("sustainkit")
    return tuple(sorted(mods, key=t["ordem_modulos"].index))


def entradas_item_modulos(base: dict) -> dict:
    out = {}
    for cid in Hub.CERTIFICACOES_LOJA:
        for nv in base["niveis_loja"]["niveis"]:
            out[f"cert-{cid}{nv['sufixo']}"] = modulos_do_nivel(base, cid, nv["n"])
    return out


@unittest.skipUnless(NO_REPO, "só no repositório")
class NiveisDaCertificacao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = json.loads(BASE.read_text(encoding="utf-8"))
        cls.p = PAINEL.read_text(encoding="utf-8")

    def test_tabela_unica_de_precos(self):
        nv = self.b["niveis_loja"]["niveis"]
        self.assertEqual([x["n"] for x in nv], [1, 2, 3, 4])
        self.assertEqual((nv[0]["preco"], nv[0]["apartir"], nv[0]["sufixo"]), (750, True, ""))
        # D19 (15/11/2026): "750 nivel 1, 5k nivel 2; a partir de 30k nivel 3 e 50k nivel 4"
        self.assertEqual([(x["preco"], x["apartir"]) for x in nv[1:]], [(5000, False), (30000, True), (50000, True)])
        self.assertIn("preco:n1.preco", self.p, "preço do N1 só na tabela da base")

    def test_regra_dos_niveis(self):
        for cid in Hub.CERTIFICACOES_LOJA:
            n1, n2, n3, n4 = (modulos_do_nivel(self.b, cid, n) for n in (1, 2, 3, 4))
            self.assertEqual(n1, ("certificacoes",))
            self.assertTrue(set(n1) <= set(n2) and n2 == n3 and set(n3) <= set(n4))
            self.assertIn("monitoramento", n4)
            self.assertIn("sustainkit", n4)                    # D20: o SustainKit entra no N4
            self.assertNotIn("sustainkit", n3)
            self.assertEqual("avac" in n2, cid in ("leed", "leed_zero", "edge", "aqua_hqe", "pbe"))
            self.assertTrue(set(n4) <= set(Hub.MODULOS_PLATAFORMA))
        self.assertIn("solar", modulos_do_nivel(self.b, "iso50001", 2))
        self.assertIn("circular", modulos_do_nivel(self.b, "true_zw", 2))
        self.assertNotIn("avac", modulos_do_nivel(self.b, "iso9001", 4))

    def test_painel_usa_a_tabela_e_tem_o_gancho_d20(self):
        for s in ("function certModulosNivel(certId, n)", "certNiveis().niveis", "sustainkit_d20", "GANCHO D20",
                  'data-nivel="${esc(c.id)}"', "nivelDe(m, id)"):
            self.assertIn(s, self.p)
        self.assertIn("sustainkit_d20", self.b["niveis_loja"])

    def test_hub_item_modulos_igual_a_regra_quando_tiver_os_niveis(self):
        esperado = entradas_item_modulos(self.b)
        tem = [k for k in esperado if k in Hub.ITEM_MODULOS and k.endswith(("-n2", "-n3", "-n4"))]
        if not tem:
            self.skipTest("hub.ITEM_MODULOS ainda sem os níveis N2 a N4 (entradas no relatório do D17)")
        for k, v in esperado.items():
            self.assertEqual(tuple(Hub.ITEM_MODULOS.get(k, ())), v, k)


if __name__ == "__main__":
    unittest.main()
