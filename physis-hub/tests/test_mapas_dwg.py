"""Mapa de fundo da região (PMTiles) e conversão de DWG, no próprio servidor.

Protege:
1. O mapa sai por partes (Range), como o leitor de PMTiles pede; HEAD diz se existe; nome restrito.
2. Sem o conversor de DWG instalado, a resposta é clara (501) e pede DXF; arquivo que não é DWG é recusado.
3. Com o conversor, o DXF volta para o Planejador.
"""
import json
import os
import subprocess
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from physis_hub import servidor
from physis_hub.hub import Hub
from physis_hub.servidor import converter_dwg, iniciar


class Mapas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["PHYSIS_MAPAS"] = cls.tmp.name
        cls.dados = bytes(range(256)) * 40                      # 10 240 bytes de "mapa"
        (Path(cls.tmp.name) / "regiao.pmtiles").write_bytes(cls.dados)
        cls.srv = iniciar(Hub(), 0, endereco="127.0.0.1", instancia={"login": False})
        cls.porta = cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        os.environ.pop("PHYSIS_MAPAS", None)
        cls.tmp.cleanup()

    def pedir(self, rota, metodo="GET", cab=None, corpo=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.porta}{rota}", method=metodo, headers=cab or {}, data=corpo)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def test_partes_e_inteiro(self):
        st, hd, corpo = self.pedir("/mapas/regiao.pmtiles", cab={"Range": "bytes=100-199"})
        self.assertEqual((st, len(corpo), hd.get("Content-Range")), (206, 100, "bytes 100-199/10240"))
        self.assertEqual(corpo, self.dados[100:200])
        st, hd, corpo = self.pedir("/mapas/regiao.pmtiles", cab={"Range": "bytes=-16"})
        self.assertEqual((st, corpo), (206, self.dados[-16:]))
        st, _, corpo = self.pedir("/mapas/regiao.pmtiles")
        self.assertEqual((st, len(corpo)), (200, 10240))
        self.assertEqual(self.pedir("/mapas/regiao.pmtiles", cab={"Range": "bytes=99999-"})[0], 416)

    def test_head_e_nomes(self):
        self.assertEqual(self.pedir("/mapas/regiao.pmtiles", "HEAD")[0], 200)
        self.assertEqual(self.pedir("/mapas/outra.pmtiles", "HEAD")[0], 404)
        for rota in ("/mapas/../physis_hub/servidor.py", "/mapas/REGIAO.pmtiles", "/mapas/x.zip"):
            self.assertEqual(self.pedir(rota)[0], 404, rota)

    def test_dwg_sem_conversor(self):
        with mock.patch.object(servidor.shutil if hasattr(servidor, "shutil") else __import__("shutil"), "which", return_value=None):
            os.environ.pop("PHYSIS_DWG2DXF", None)
            st, _, corpo = self.pedir("/api/converter/dwg", "POST", {"Content-Type": "application/octet-stream"}, b"AC1027" + b"\0" * 64)
        self.assertEqual(st, 501)
        self.assertIn("DXF", json.loads(corpo)["erro"])


class ConverterDwg(unittest.TestCase):
    def test_recusa_o_que_nao_e_dwg(self):
        self.assertEqual(converter_dwg(b"%PDF-1.7", programa="dwg2dxf")["codigo"], 400)

    def test_com_conversor(self):
        def falso(args, **kw):
            Path(args[args.index("-o") + 1]).write_bytes(b"0\nSECTION\n")
            return subprocess.CompletedProcess(args, 0, b"", b"")
        with mock.patch("subprocess.run", side_effect=falso):
            r = converter_dwg(b"AC1027" + b"\0" * 64, programa="dwg2dxf")
        self.assertTrue(r["ok"]); self.assertTrue(r["dxf"].startswith(b"0\nSECTION"))

    def test_conversor_falha(self):
        with mock.patch("subprocess.run", return_value=subprocess.CompletedProcess([], 1, b"", b"ERROR: unsupported version")):
            r = converter_dwg(b"AC1032" + b"\0" * 64, programa="dwg2dxf")
        self.assertEqual(r["codigo"], 422); self.assertIn("unsupported version", r["erro"])


if __name__ == "__main__":
    unittest.main()
