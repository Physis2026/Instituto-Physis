"""App instalável (PWA): manifestos, ícones e service worker.

Protege:
1. Os dois manifestos são JSON válido com os campos que o navegador exige para instalar.
2. Os ícones existem, são PNG e têm o tamanho declarado (lido do cabeçalho IHDR).
3. O sw.js não chama nada fora do próprio servidor, guarda as rotas da casca, nunca guarda POST
   e só guarda da API o clima e o GIS.
4. A rota /app/ só entrega os arquivos da lista, com o tipo certo (quando o servidor já tem a rota).
"""
import json
import re
import struct
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from physis_hub import app_pwa

APP = Path(__file__).resolve().parents[1] / "web" / "app"


def ihdr(p: Path) -> tuple[int, int]:
    d = p.read_bytes()[:33]
    assert d[:8] == b"\x89PNG\r\n\x1a\n" and d[12:16] == b"IHDR", p
    return struct.unpack(">II", d[16:24])


class Manifestos(unittest.TestCase):
    def ler(self, nome):
        return json.loads((APP / nome).read_text(encoding="utf-8"))

    def test_campos_obrigatorios(self):
        for nome, inicio in (("manifest-plataforma.webmanifest", "/"), ("manifest-gestao.webmanifest", "/gestao/")):
            with self.subTest(nome):
                m = self.ler(nome)
                self.assertEqual(m["name"], "Physis")
                self.assertEqual(m["short_name"], "Physis")
                self.assertEqual(m["theme_color"].upper(), "#33512F")
                self.assertEqual(m["background_color"].upper(), "#F4F6F1")
                self.assertEqual(m["display"], "standalone")
                self.assertEqual(m["lang"], "pt-BR")
                self.assertEqual(m["scope"], "/")
                self.assertEqual(m["start_url"], inicio)
                self.assertTrue(m["start_url"].startswith(m["scope"]))

    def test_ids_diferentes(self):
        # dois apps distintos no mesmo endereço: o celular instala os dois sem confundir
        self.assertNotEqual(self.ler("manifest-plataforma.webmanifest")["id"], self.ler("manifest-gestao.webmanifest")["id"])

    def test_icones_declarados_existem_e_batem(self):
        for nome in ("manifest-plataforma.webmanifest", "manifest-gestao.webmanifest"):
            m = self.ler(nome)
            tamanhos = {i["sizes"] for i in m["icons"]}
            self.assertIn("192x192", tamanhos)
            self.assertIn("512x512", tamanhos)
            self.assertTrue(any("maskable" in i.get("purpose", "") for i in m["icons"]))
            for i in m["icons"]:
                self.assertTrue(i["src"].startswith("/app/"))
                arq = APP / i["src"][len("/app/"):]
                self.assertIn(arq.name, app_pwa.ARQUIVOS)
                self.assertTrue(arq.is_file(), arq)
                w, h = map(int, i["sizes"].split("x"))
                self.assertEqual(ihdr(arq), (w, h))
                self.assertEqual(i["type"], "image/png")


class Icones(unittest.TestCase):
    def test_tamanhos(self):
        for nome, lado in (("icone-192.png", 192), ("icone-512.png", 512), ("icone-maskable-512.png", 512)):
            with self.subTest(nome):
                self.assertEqual(ihdr(APP / nome), (lado, lado))

    def test_png_ida_e_volta(self):
        px = [(x * 40, y * 40, 7, 255 - x) for y in range(5) for x in range(6)]
        self.assertEqual(app_pwa.ler_png(app_pwa.gravar_png(6, 5, px)), (6, 5, px))

    def test_icone_maskable_tem_borda_lisa(self):
        # zona segura: os cantos e a borda são só o fundo verde (nada da árvore é cortado pela máscara)
        w, h, px = app_pwa.ler_png((APP / "icone-maskable-512.png").read_bytes())
        borda = {px[y * w + x][:3] for y in range(h) for x in range(w)
                 if min(x, y, w - 1 - x, h - 1 - y) < int(w * 0.1)}
        self.assertEqual(borda, {app_pwa.VERDE})

    def test_regera_a_partir_do_painel(self):
        with tempfile.TemporaryDirectory() as d:
            feitos = app_pwa.gerar_icones(Path(d))
            self.assertEqual(sorted(p.name for p in feitos), ["icone-192.png", "icone-512.png", "icone-maskable-512.png"])
            for p in feitos:
                self.assertEqual(p.read_bytes(), (APP / p.name).read_bytes(), "ícone guardado difere do gerado do painel")


class ServiceWorker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = (APP / "sw.js").read_text(encoding="utf-8")

    def test_sem_endereco_externo(self):
        self.assertIsNone(re.search(r"https?:|wss?:|[\"']//", self.js))
        self.assertNotIn("importScripts", self.js)

    def test_rotas_da_casca(self):
        for rota in ('"/"', '"/painel.html"', '"/gestao/"', '"/planejador/"', '"/vendor/', '"/vendor/maplibre-gl.js"',
                     '"/app/manifest-plataforma.webmanifest"', '"/app/icone-192.png"'):
            self.assertIn(rota, self.js)

    def test_api_so_clima_e_gis(self):
        self.assertIn('p === "/api/clima"', self.js)
        self.assertIn('p.indexOf("/api/gis/") === 0', self.js)
        # qualquer outra rota da API passa direto, sem respondWith
        self.assertRegex(self.js, r'return;\s*// resto da API')

    def test_nunca_guarda_post(self):
        self.assertIn('if (req.method !== "GET") return;', self.js)

    def test_versao_e_limpeza(self):
        self.assertIn(app_pwa.MARCA_VERSAO, self.js)
        self.assertIn("caches.delete", self.js)
        self.assertIn('"physis-casca-" + VERSAO', self.js)
        self.assertIn('"physis-dados-" + VERSAO', self.js)


class Resposta(unittest.TestCase):
    def test_lista_fechada(self):
        for nome in ("../servidor.py", "..\\painel.html", "sw.js.bak", "", "app/sw.js", "painel.html"):
            self.assertIsNone(app_pwa.resposta(nome), nome)

    def test_tipos(self):
        corpo, cab = app_pwa.resposta("manifest-plataforma.webmanifest")
        self.assertTrue(cab["Content-Type"].startswith("application/manifest+json"))
        json.loads(corpo)
        self.assertEqual(app_pwa.resposta("icone-192.png")[1]["Content-Type"], "image/png")

    def test_sw_versionado(self):
        corpo, cab = app_pwa.resposta("sw.js")
        self.assertTrue(cab["Content-Type"].startswith("text/javascript"))
        self.assertEqual(cab["Service-Worker-Allowed"], "/")
        self.assertEqual(cab["Cache-Control"], "no-cache")
        self.assertNotIn(app_pwa.MARCA_VERSAO.encode(), corpo)
        self.assertIn(('"' + app_pwa.versao() + '"').encode(), corpo)
        self.assertEqual(cab["Content-Length"], str(len(corpo)))

    def test_versao_muda_com_a_tela(self):
        with tempfile.TemporaryDirectory() as d:
            web = Path(d)
            (web / "app").mkdir()
            (web / "app" / "sw.js").write_text('var VERSAO = "__VERSAO__";', encoding="utf-8")
            (web / "painel.html").write_text("um", encoding="utf-8")
            v1 = app_pwa.versao(web)
            self.assertRegex(v1, r"^[0-9a-f]{12}$")
            self.assertEqual(v1, app_pwa.versao(web))
            (web / "painel.html").write_text("dois", encoding="utf-8")
            self.assertNotEqual(v1, app_pwa.versao(web))


def _tem_rota_app() -> bool:
    try:
        from physis_hub import servidor
        return "/app/" in Path(servidor.__file__).read_text(encoding="utf-8")
    except Exception:
        return False


@unittest.skipUnless(_tem_rota_app(), "servidor ainda sem a rota /app/")
class RotaServidor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from physis_hub.hub import Hub
        from physis_hub.servidor import iniciar
        cls.srv = iniciar(Hub(), 0, endereco="127.0.0.1", instancia={"login": True})
        cls.porta = cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def get(self, caminho):
        return urllib.request.urlopen(f"http://127.0.0.1:{self.porta}{caminho}", timeout=5)

    def test_entrega_sem_login(self):
        # o celular baixa manifesto, ícones e sw.js antes de qualquer login
        for nome, tipo in app_pwa.ARQUIVOS.items():
            with self.subTest(nome), self.get("/app/" + nome) as r:
                self.assertEqual(r.status, 200)
                self.assertEqual(r.headers["Content-Type"], tipo)
        with self.get("/app/sw.js") as r:
            self.assertEqual(r.headers["Service-Worker-Allowed"], "/")
            self.assertEqual(r.headers["Cache-Control"], "no-cache")

    def test_fora_da_lista_404(self):
        for c in ("/app/../physis_hub/servidor.py", "/app/%2e%2e/painel.html", "/app/nada.js", "/app/"):
            with self.subTest(c), self.assertRaises(urllib.error.HTTPError) as e:
                self.get(c)
            self.assertEqual(e.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
