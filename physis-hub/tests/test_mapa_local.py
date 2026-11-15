"""Mapa do local (sistema/physis-mapa-local.js), sem navegador.

Protege:
1. Independência: nada de internet (nem tiles nem Leaflet do original), eval ou '</script'; só o MapLibre e o mapa
   da região servidos pelo próprio servidor (/vendor/ e /mapas/regiao.pmtiles), e só tentados por http(s).
2. O limite do Brasil é o mesmo de clima.validar_local (e do receptor); fora dele, só aviso.
3. Inglês: todo texto fixo está no I18N ou no I18N_RX; cores só da paleta; atributos data-pml-…; nunca h1.
4. As rotas usadas existem no servidor (/vendor/ da lista e /mapas/ com HEAD).
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))      # os auxiliares dos outros testes, rodando de qualquer jeito

from physis_hub import clima

from test_aprendizado_ui import codigo_de_tela, coberto, literais_js, objeto_js, visivel

RAIZ = Path(__file__).resolve().parents[2]
MODULO = RAIZ / "sistema" / "physis-mapa-local.js"
HUB = Path(__file__).resolve().parents[1]
NO_REPO = MODULO.is_file()


@unittest.skipUnless(NO_REPO, "só no repositório")
class MapaLocal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = MODULO.read_text(encoding="utf-8")
        cls.i18n = objeto_js(cls.js, "I18N")
        cls.rx = objeto_js(cls.js, "I18N_RX")

    def test_independencia(self):
        js = self.js
        self.assertNotRegex(js, r"https?://")
        self.assertNotRegex(js, r"(?i)unpkg|openstreetmap\.org|tile\.|leaflet")
        self.assertNotRegex(js, r"\beval\s*\(")
        self.assertNotIn("new Function", js)
        self.assertNotRegex(js, r"(?i)</script")
        self.assertNotIn("<h1", js)
        self.assertIn('p === "http:" || p === "https:"', js, "fora do servidor (arquivo, srcdoc) não tenta carregar nada")
        for u in re.findall(r'"(/(?:vendor|mapas)/[^"]+)"', js):
            self.assertTrue(u in ("/vendor/maplibre-gl.js", "/vendor/maplibre-gl.css", "/vendor/pmtiles.js", "/mapas/regiao.pmtiles"), u)
        self.assertIn('existe("/mapas/regiao.pmtiles", "HEAD")', js, "pergunta antes se o mapa existe")
        self.assertTrue(js.rstrip().endswith('})(typeof window !== "undefined" ? window : this);'))
        self.assertIn("global.PhysisMapaLocal = {", js)

    def test_servidor_entrega_o_que_o_mapa_pede(self):
        srv = (HUB / "physis_hub" / "servidor.py").read_text(encoding="utf-8")
        for nome in ("maplibre-gl.js", "maplibre-gl.css", "pmtiles.js"):
            self.assertIn(f'"{nome}"', srv[srv.index("VENDOR_TIPOS"):srv.index("INSTANCIA =")])
        self.assertIn('return self._mapa(u.path, so_cabecalho=True)', srv, "HEAD /mapas/ responde sem mandar o arquivo")
        self.assertIn('"/api/clima/local"', srv)

    def test_limite_do_brasil_igual_ao_servidor(self):
        m = re.search(r"var BR = \{ latMin: (-?\d+), latMax: (-?\d+), lonMin: (-?\d+), lonMax: (-?\d+) \}", self.js)
        la0, la1, lo0, lo1 = map(float, m.groups())
        self.assertEqual((la0, la1, lo0, lo1), (-35.0, 6.0, -75.0, -28.0))
        # o servidor recusa fora desses limites; a tela só avisa (a pessoa decide e vê a resposta do servidor)
        self.assertIsNotNone(clima.validar_local({"lat": la0, "lon": lo0})[0])
        self.assertIsNotNone(clima.validar_local({"lat": la1, "lon": lo1})[0])
        self.assertIsNone(clima.validar_local({"lat": la1 + 0.1, "lon": lo1})[0])
        self.assertIsNone(clima.validar_local({"lat": la0, "lon": lo0 - 0.1})[0])
        self.assertIn("return { ok: true, lat: lat, lon: lon, aviso:", self.js)

    def test_todo_texto_fixo_tem_ingles(self):
        chaves = set(self.i18n)
        rx_textos = [a.replace("\\", "") for a, _ in self.rx]
        faltam = sorted({k for k in map(visivel, literais_js(codigo_de_tela(self.js))) if k and not coberto(k, chaves, rx_textos)})
        self.assertEqual(faltam, [])
        rx = [re.compile(a) for a, _ in self.rx]
        for amostra in ("Mapa de localização. Marcador em latitude -22,5050, longitude -43,1830. Use as setas para mover; com Shift, o passo é maior.",
                        "Latitude -22,5050, longitude -43,1830", "Não salvou: coordenadas fora do Brasil", "500 m", "20 km"):
            self.assertTrue(any(r.match(amostra) for r in rx), amostra)

    def test_paleta_atributos_e_api(self):
        paleta = set(re.findall(r"#[0-9A-F]{6}", (HUB / "docs" / "PALETA.md").read_text(encoding="utf-8")))
        cores = set(c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}\b", self.js))
        self.assertTrue(cores <= paleta, cores - paleta)
        attrs = set(re.findall(r"data-([a-z][\w-]*)", self.js))
        self.assertTrue(attrs and all(a == "pml" or a.startswith("pml-") or a == "tema" for a in attrs), attrs)
        for f in ("html: html", "ligar: ligar", "estado: estado", "I18N: I18N", "I18N_RX: I18N_RX"):
            self.assertIn(f, self.js)
        # teclado: setas movem 0,001° (Shift 0,01°); zoom por botões com nome
        self.assertIn("ev.shiftKey ? 0.01 : 0.001", self.js)
        self.assertIn('aria-label="Aproximar o mapa"', self.js)
        self.assertIn('role="application"', self.js)
        self.assertIn('inputmode="decimal"', self.js)


if __name__ == "__main__":
    unittest.main()
