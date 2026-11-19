"""Instituto Physis: o mesmo código, outra instalação (docs/INSTITUTO.md).

Protege:
1. A ficha "instituto-physis" de clientes/clientes.json: módulos aceitos, pesquisa ligada, cores só da PALETA.md.
2. montar(..., instalacao="instituto") grava no instancia.json a instalação, o banco próprio, a marca e o suporte próprio.
3. O servidor lê o instancia.json indicado em PHYSIS_INSTANCIA e usa o banco dele (dados nunca se misturam com os da Physis);
   /api/instancia mostra a instalação e a marca para as telas.
"""
import json
import os
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import montar  # noqa: E402
from physis_hub import servidor  # noqa: E402
from physis_hub.hub import Hub  # noqa: E402

FICHAS = RAIZ.parent / "clientes" / "clientes.json"


class Ficha(unittest.TestCase):
    def test_ficha_do_instituto(self):
        if not FICHAS.exists():
            self.skipTest("clientes.json ausente (pacote montado)")
        f = [x for x in json.loads(FICHAS.read_text(encoding="utf-8"))["clientes"] if x["org"] == "instituto-physis"][0]
        self.assertEqual(f["instalacao"], "instituto")
        self.assertTrue(f["pesquisa"])
        self.assertEqual(set(f["modulos"]), {"gestao", "cursos", "sbn", "resiliencia", "carbono", "certificacoes", "impressao3d", "circular", "medicamentos", "pulseira"})   # Physis 3D é do Instituto (18/11/2026)
        self.assertTrue(set(f["modulos"]) <= set(montar.MODULOS))
        self.assertTrue(montar.conferir_marca(f["marca"]))                 # cores da paleta (senão SystemExit)
        self.assertNotEqual(f["banco"], "physis-hub.db")


class Montagem(unittest.TestCase):
    def test_pacote_do_instituto(self):
        with tempfile.TemporaryDirectory() as d:
            marca = {"nome": "Instituto Physis", "logo_texto": "Instituto Physis", "cores": {"primaria": "#2c5a6e"}}
            montar.montar("instituto-physis", "sede", ["gestao", "cursos", "sbn"], Path(d), None, montar.LICENCA_PADRAO,
                          pesquisa=True, nome="Instituto Physis", suporte={"email": "contato@instituto.example", "whatsapp": "+55 61 90000-0000"},
                          instalacao="instituto", marca=marca)
            inst = json.loads((Path(d) / "physis-instituto-physis" / "instancia.json").read_text(encoding="utf-8"))
        self.assertEqual((inst["instalacao"], inst["banco"], inst["suporte_email"]),
                         ("instituto", "physis-instituto.db", "contato@instituto.example"))
        self.assertEqual(inst["marca"]["cores"]["primaria"], "#2C5A6E")
        self.assertTrue(inst["pesquisa"])
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit):                          # cor fora da paleta
                montar.montar("x-teste", "l", [], Path(d), None, "", instalacao="instituto", marca={"cores": {"a": "#123456"}})
            with self.assertRaises(SystemExit):
                montar.montar("x-teste", "l", [], Path(d), None, "", instalacao="outra")
            with self.assertRaises(SystemExit):
                montar.montar("x-teste", "l", [], Path(d), None, "", banco="../fora.db")


class DuasInstalacoesNaMesmaMaquina(unittest.TestCase):
    def test_instancia_e_banco_proprios(self):
        with tempfile.TemporaryDirectory() as d:
            arq = Path(d) / "instancia.json"
            arq.write_text(json.dumps({"org": "instituto-physis", "login": True, "instalacao": "instituto", "banco": "physis-instituto.db",
                                       "marca": {"nome": "Instituto Physis", "logo_texto": "IP", "cores": {"primaria": "#2C5A6E", "x": "red"}}}),
                           encoding="utf-8")
            antes = {k: os.environ.get(k) for k in ("PHYSIS_INSTANCIA", "PHYSIS_BANCO")}
            os.environ["PHYSIS_INSTANCIA"] = str(arq)
            os.environ.pop("PHYSIS_BANCO", None)
            try:
                inst = servidor.ler_instancia()
                self.assertEqual(inst["org"], "instituto-physis")
                self.assertEqual(Path(servidor.banco_da_instancia(inst)), Path(d).resolve() / "physis-instituto.db")
                self.assertEqual(servidor.banco_da_instancia({"banco": "../x.db"}), "physis-hub.db")      # nome inválido: padrão
                os.environ["PHYSIS_BANCO"] = str(Path(d) / "outro.db")
                self.assertEqual(servidor.banco_da_instancia(inst), str(Path(d) / "outro.db"))         # a variável manda
                m = servidor.marca_da_instancia(inst)
                self.assertEqual(m, {"nome": "Instituto Physis", "logo_texto": "IP", "cores": {"primaria": "#2C5A6E"}})
                hub = Hub(org=inst["org"])
                srv = servidor.iniciar(hub, 0, endereco="127.0.0.1", instancia=inst)
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/api/instancia", timeout=10) as r:
                        j = json.loads(r.read())
                    self.assertEqual((j["instalacao"], j["marca"]["nome"], j["org"]), ("instituto", "Instituto Physis", "instituto-physis"))
                finally:
                    srv.shutdown(); srv.server_close(); hub.fechar()
            finally:
                for k, v in antes.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
        self.assertEqual(servidor.marca_da_instancia({})["nome"], "")


if __name__ == "__main__":
    unittest.main()
