"""Solo do lugar: SoilGrids pelo serviço de mapas (GeoTIFF) + classe de solo do IBGE.

Protege:
1. O leitor de GeoTIFF lê janelas sem compressão e com deflate; 0 (máscara) e "sem dado" ficam de fora da média.
2. As duas bases são guardadas: a segunda consulta não busca de novo e funciona sem internet.
3. Ponto urbano: o SoilGrids não mapeia, a resposta é guardada e a classe do IBGE aparece.
4. Uma base fora do ar não derruba a outra; as duas fora → ok False com aviso.
"""
import struct
import unittest
import urllib.error
import zlib

from physis_hub.gis import GisExtra, Irradiacao, ler_pedologia, ler_tiff, valor_tiff
from physis_hub.hub import Hub


def tiff(vals, w=3, h=3, deflate=False, nodata=None):
    dados = struct.pack("<%dh" % len(vals), *vals)
    if deflate:
        dados = zlib.compress(dados)
    tags = [(256, 3, 1, w), (257, 3, 1, h), (258, 3, 1, 16), (259, 3, 1, 8 if deflate else 1),
            (273, 4, 1, 0), (277, 3, 1, 1), (278, 3, 1, h), (279, 4, 1, len(dados)), (339, 3, 1, 2)]
    extra = b""
    if nodata is not None:
        extra = str(nodata).encode() + b"\0"
        tags.append((42113, 2, len(extra), 0))
    n = len(tags)
    ifd_tam = 2 + 12 * n + 4
    base = 8 + ifd_tam
    off_extra = base + len(dados)
    corpo = struct.pack("<H", n)
    for tag, tipo, qtd, val in sorted(tags):
        if tag == 273:
            val = base
        if tag == 42113:
            val = off_extra if len(extra) > 4 else val
        v = struct.pack("<H", val) + b"\0\0" if tipo == 3 else struct.pack("<I", val)
        corpo += struct.pack("<HHI", tag, tipo, qtd) + v
    corpo += b"\0\0\0\0"
    return b"II*\x00" + struct.pack("<I", 8) + corpo + dados + extra


IBGE = {"features": [{"properties": {"legenda": "LVd - Latossolo Vermelho Distrófico", "legenda_2": "LATOSSOLO VERMELHO",
                                     "ordem": "LATOSSOLO", "subordem": "VERMELHO", "grande_gru": "Distrófico", "textura": "argilosa",
                                     "horizonte": "A \nmoderado", "relevo": "forte \nondulado", "leg_ordem": "LATOSSOLO"}}]}
URBANO = {"features": [{"properties": {"legenda": "Área Urbana", "legenda_2": "ÁREA URBANA", "leg_ordem": "OUTROS"}}]}


class Fontes:
    def __init__(self, ph=(52, 52, 0, 52, 52, 52, 52, 52, 52), ibge=IBGE):
        self.n_bytes, self.n_json, self.fora_wcs, self.fora_ibge, self.ph, self.ibge = 0, 0, False, False, ph, ibge

    def bytes(self, url):
        self.n_bytes += 1
        if self.fora_wcs:
            raise urllib.error.URLError("fora do ar")
        return tiff(list(self.ph) if "phh2o" in url else [300] * 9, deflate="clay" in url)

    def json(self, url):
        self.n_json += 1
        if "ibge" in url:
            if self.fora_ibge:
                raise urllib.error.URLError("fora do ar")
            return self.ibge
        raise urllib.error.URLError("REST antigo fora do ar")


class LeitorTiff(unittest.TestCase):
    def test_sem_compressao_e_deflate(self):
        for d in (False, True):
            w, h, g, nd = ler_tiff(tiff([1, 2, 3, 4, 5, 6, 7, 8, 9], deflate=d))
            self.assertEqual((w, h, g, nd), (3, 3, [1, 2, 3, 4, 5, 6, 7, 8, 9], None))

    def test_mascara_e_sem_dado_fora_da_media(self):
        self.assertEqual(valor_tiff(tiff([50, 0, 60, -32768, 0, 0, 0, 0, 0])), 55)
        self.assertEqual(valor_tiff(tiff([50, 9999, 60, 9999, 9999, 9999, 9999, 9999, 9999], nodata=9999)), 55)
        self.assertIsNone(valor_tiff(tiff([0] * 9)))

    def test_pedologia_limpa_espacos(self):
        p = ler_pedologia(IBGE)
        self.assertEqual(p["classe"], "Latossolo vermelho"); self.assertEqual(p["horizonte"], "A moderado")
        self.assertFalse(p["urbano_ou_agua"]); self.assertTrue(ler_pedologia(URBANO)["urbano_ou_agua"])
        self.assertIsNone(ler_pedologia({"features": []}))


class SoloNoHub(unittest.TestCase):
    def novo(self, f):
        return GisExtra(Irradiacao(Hub(), buscar=f.json), buscar_bytes=f.bytes)

    def test_duas_bases_e_guarda(self):
        f = Fontes(); g = self.novo(f)
        r = g.solo(-22.4, -43.1)
        self.assertTrue(r["ok"]); self.assertEqual(r["ph"], 5.2); self.assertTrue(r["acido"])
        self.assertEqual(r["argila_pct"], 30.0); self.assertEqual(r["nitrogenio_gkg"], 3.0)
        self.assertEqual(r["pedologia"]["ordem"], "Latossolo"); self.assertIn("IBGE", r["fonte"]); self.assertIn("SoilGrids", r["fonte"])
        self.assertEqual(f.n_bytes, 21)
        f.fora_wcs = f.fora_ibge = True
        r2 = g.solo(-22.4, -43.1)                                # sem internet: do banco
        self.assertTrue(r2["ok"]); self.assertEqual(r2["ph"], 5.2); self.assertEqual(f.n_bytes, 21 + 0)

    def test_urbano_guarda_sem_mapa(self):
        f = Fontes(ph=[0] * 9, ibge=URBANO); f.bytes = lambda url, f=f: (setattr(f, "n_bytes", f.n_bytes + 1), tiff([0] * 9))[1]
        g = self.novo(f)
        r = g.solo(-22.505, -43.178)
        self.assertTrue(r["ok"]); self.assertIsNone(r.get("ph")); self.assertTrue(r["pedologia"]["urbano_ou_agua"])
        self.assertTrue(any("não mapeia" in a for a in r["avisos"]))
        antes = f.n_bytes; g.solo(-22.505, -43.178); self.assertEqual(f.n_bytes, antes)   # a resposta "sem mapa" foi guardada

    def test_uma_fora_outra_responde(self):
        f = Fontes(); f.fora_wcs = True; g = self.novo(f)
        r = g.solo(-22.4, -43.1)
        self.assertTrue(r["ok"]); self.assertIsNone(r.get("ph")); self.assertEqual(r["pedologia"]["ordem"], "Latossolo")
        self.assertTrue(any("SoilGrids" in a for a in r["avisos"]))
        f2 = Fontes(); f2.fora_wcs = f2.fora_ibge = True
        r2 = self.novo(f2).solo(-10.0, -50.0)
        self.assertFalse(r2["ok"]); self.assertTrue(r2["avisos"])


if __name__ == "__main__":
    unittest.main()
