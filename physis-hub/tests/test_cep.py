"""CEP obrigatório no Início, consulta pelo servidor (cep.py, GET /api/local/cep/<cep>) e precedência das coordenadas
(pedido de 15/11/2026: "CEP deve ser obrigatório, latitude e longitude opcionais e preenchidas automaticamente com o CEP").

Confere: máscara e validação; provedor falso (com coordenadas, só endereço, falha); só o CEP sai do servidor; cache;
limite por IP na rota; precedência mapa > digitado > CEP; local da instalação com perfil só com CEP.
"""
import json
import re
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from physis_hub import cep as cep_mod
from physis_hub import seguranca as seg
from physis_hub.hub import Hub

RAIZ = Path(__file__).resolve().parents[2]
PAINEL = RAIZ / "physis-hub" / "web" / "painel.html"


class Falso:
    """Provedor falso: guarda as URLs pedidas e devolve o que cada teste manda."""
    def __init__(self, respostas):
        self.respostas, self.urls = respostas, []

    def __call__(self, url):
        self.urls.append(url)
        for chave, r in self.respostas.items():
            if chave in url:
                return r
        return None


BRASILAPI = {"cep": "01310100", "state": "SP", "city": "São Paulo", "neighborhood": "Bela Vista", "street": "Avenida Paulista",
             "service": "x", "location": {"type": "Point", "coordinates": {"longitude": "-46.6527", "latitude": "-23.5639"}}}
VIACEP = {"cep": "01310-100", "logradouro": "Avenida Paulista", "bairro": "Bela Vista", "localidade": "São Paulo", "uf": "SP", "ibge": "3550308"}


def hub():
    h = Hub(":memory:")
    h.instancia = {}
    return h


class Mascara(unittest.TestCase):
    def test_valido_e_mascara(self):
        for ok in ("01310-100", "01310100", " 25600-000 "):
            self.assertTrue(cep_mod.valido(ok), ok)
        for ruim in ("", "1234567", "123456789", "01310_100", "00000-000", "abcde-fgh", "0131-0100"):
            self.assertFalse(cep_mod.valido(ruim), ruim)
        self.assertEqual(cep_mod.mascara("01310100"), "01310-100")
        self.assertEqual(cep_mod.mascara("0131"), "0131")

    def test_provedores(self):
        self.assertEqual(cep_mod.provedores_config("brasilapi,viacep"), ["brasilapi", "viacep"])
        self.assertEqual(cep_mod.provedores_config("desligado"), [])
        self.assertEqual(cep_mod.provedores_config("viacep, qualquer"), ["viacep"])


class Consulta(unittest.TestCase):
    def test_com_coordenadas_e_ibge(self):
        f = Falso({"brasilapi": BRASILAPI, "viacep": VIACEP})
        cod, r = cep_mod.ServicoCEP(hub(), ["brasilapi", "viacep"], f).consultar("01310-100")
        self.assertEqual(cod, 200)
        self.assertTrue(r["ok"])
        self.assertEqual((r["municipio"], r["uf"], r["ibge"]), ("São Paulo", "SP", "3550308"))
        self.assertAlmostEqual(r["lat"], -23.5639)
        self.assertEqual(r["fonte_coordenadas"], "cep")

    def test_so_endereco_sem_coordenadas(self):
        f = Falso({"viacep": VIACEP})
        cod, r = cep_mod.ServicoCEP(hub(), ["brasilapi", "viacep"], f).consultar("01310100")
        self.assertTrue(r["ok"])
        self.assertIsNone(r["lat"])
        self.assertIsNone(r["fonte_coordenadas"])
        self.assertIn("marque no mapa", r["aviso"])           # nunca um ponto inventado

    def test_falha_e_desligado(self):
        cod, r = cep_mod.ServicoCEP(hub(), ["brasilapi", "viacep"], Falso({})).consultar("01310100")
        self.assertEqual(cod, 200)
        self.assertFalse(r["ok"])
        self.assertIsNone(r["lat"])
        cod, r = cep_mod.ServicoCEP(hub(), [], Falso({})).consultar("01310100")
        self.assertFalse(r["ok"])
        self.assertIn("desligada", r["aviso"])
        cod, r = cep_mod.ServicoCEP(hub(), ["viacep"], Falso({})).consultar("123")
        self.assertEqual(cod, 400)

    def test_so_o_cep_sai_do_servidor(self):
        f = Falso({"brasilapi": BRASILAPI})
        cep_mod.ServicoCEP(hub(), ["brasilapi", "viacep"], f).consultar("01310-100")
        self.assertTrue(f.urls)
        for u in f.urls:
            self.assertRegex(u, r"^https://[a-z.]+/[a-z0-9/]*01310100[/]?(json/)?$")
            self.assertNotIn("?", u)
        self.assertNotRegex(cep_mod.USER_AGENT, r"@")         # User-Agent genérico, sem e-mail

    def test_cache(self):
        f = Falso({"brasilapi": BRASILAPI, "viacep": VIACEP})
        s = cep_mod.ServicoCEP(hub(), ["brasilapi", "viacep"], f)
        s.consultar("01310100")
        n = len(f.urls)
        cod, r = s.consultar("01310-100")
        self.assertEqual(len(f.urls), n, "segunda consulta tem de vir do cache")
        self.assertTrue(r.get("cache"))

    def test_limite_da_rota(self):
        self.assertIn("cep", seg.LIMITES_PADRAO)
        srv = (RAIZ / "physis-hub" / "physis_hub" / "servidor.py").read_text(encoding="utf-8")
        self.assertIn('if self._exigir(seg.CLIENTE) and not self._limitado("cep"):', srv)
        self.assertIn('p.startswith("/api/local/cep/")', srv)


class LocalDaInstalacao(unittest.TestCase):
    def _perfil(self, h, c):
        with h._trava:
            h._db.execute("INSERT OR REPLACE INTO cliente_estado(org, chave, valor, versao, atualizado, por) VALUES(?,?,?,?,?,?)",
                          (h.org, "physis-perfil", json.dumps({"c": c}), 1, 0, "t"))
            h._db.commit()

    def test_so_cep(self):
        h = hub()
        self._perfil(h, {"cep": "01310100", "municipio": "São Paulo", "uf": "SP"})
        loc = h.local_da_instalacao()
        self.assertEqual((loc["cep"], loc["fonte"], loc["lat"], loc["fonte_coordenadas"]), ("01310-100", "nao_informado", None, None))
        self.assertEqual(loc["municipio"], "São Paulo")

    def test_coordenadas_do_cep_e_do_mapa(self):
        h = hub()
        self._perfil(h, {"cep": "01310100", "lat": "-23,56", "lon": "-46,65", "fonte_coordenadas": "cep"})
        self.assertEqual(h.local_da_instalacao()["fonte_coordenadas"], "cep")
        self._perfil(h, {"cep": "01310100", "lat": "-23,56", "lon": "-46,65", "fonte_coordenadas": "mapa"})
        self.assertEqual(h.local_da_instalacao()["fonte_coordenadas"], "mapa")
        self._perfil(h, {"cep": "01310100", "lat": "-23,56", "lon": "-46,65"})
        self.assertEqual(h.local_da_instalacao()["fonte_coordenadas"], "digitado")


@unittest.skipUnless(PAINEL.is_file(), "só no repositório")
class Painel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = PAINEL.read_text(encoding="utf-8")

    def test_cep_obrigatorio_e_coordenadas_opcionais(self):
        self.assertRegex(self.p, r'\{ k:"cep", r:"CEP", o:1, q:\(\) => true, im:"numeric", ac:"postal-code", val:v => cepValido\(v\)')
        self.assertRegex(self.p, r'\{ k:"lat", r:"Latitude", q:\(\) => true')
        self.assertRegex(self.p, r'\{ k:"lon", r:"Longitude", q:\(\) => true')
        self.assertIn("(f.val && !f.val(p.c[f.k]))", self.p)
        m = re.search(r"const cepValido = v => (.*?);\n", self.p)
        self.assertIn("\\d{5}-?\\d{3}", m.group(1))

    def test_precedencia_mapa_digitado_cep(self):
        self.assertIn('fonte_coordenadas:"mapa"', self.p)                       # o ponto do mapa marca "mapa"
        self.assertIn('p0.c.fonte_coordenadas = "digitado"', self.p)            # digitar marca "digitado"
        self.assertIn('(!fc || fc === "cep" || c.lat == null', self.p)           # o CEP só preenche sem mapa/digitado
        self.assertIn('fetch("api/local/cep/" + cep', self.p)                    # pelo servidor, nunca direto do navegador
        self.assertNotIn("viacep.com.br", self.p)
        self.assertNotIn("brasilapi.com.br", self.p)

    def test_aviso_de_local_aproximado(self):
        self.assertIn("Local aproximado pelo CEP.", self.p)
        self.assertIn("avisoLocalCep", (RAIZ / "sistema" / "physis-solar.js").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
