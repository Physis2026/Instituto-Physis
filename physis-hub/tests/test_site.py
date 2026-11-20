"""Site do Instituto e da Rede InovaSTEM (web/site.html, etapa 2 de 19/11/2026).

Protege:
1. Rotas: no Instituto, "/" é o site público e "/plataforma/" é a plataforma; nas outras instalações "/" segue a plataforma.
2. Regras das telas (CLAUDE.md): um título h1 só; barra única de preferências igual ao original; tema escuro; só cores da
   PALETA.md; nada de internet (sem http(s):// em src/href, sem fetch externo), sem eval; ids fixos sem repetir.
3. Português e inglês com as mesmas chaves e listas do mesmo tamanho; todas as abas pedidas existem.
4. Conteúdo: sem nomes de parceiros, sem número inventado (os números dos documentos levam [CONFERIR]); Global South
   Alliance fora até a cessão (D67); horizonte 2027–2031 (D40); IA e química aparecem "em desenvolvimento".
5. O pacote do Instituto leva o site; o de outras instalações, não.
"""
import json
import re
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

from physis_hub import servidor
from physis_hub.hub import Hub

AQUI = Path(__file__).resolve().parents[1]
RAIZ = AQUI.parent
SITE = AQUI / "web" / "site.html"


def ler(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _lista(texto: str, chave: str) -> str:
    """Texto da lista [ ... ] logo depois de 'chave:', respeitando colchetes e aspas."""
    i = texto.index(chave + ":[") + len(chave) + 1
    prof, aspas, j = 0, None, i
    while j < len(texto):
        c = texto[j]
        if aspas:
            if c == "\\":
                j += 1
            elif c == aspas:
                aspas = None
        elif c in "\"'`":
            aspas = c
        elif c == "[":
            prof += 1
        elif c == "]":
            prof -= 1
            if prof == 0:
                return texto[i + 1:j]
        j += 1
    raise ValueError(chave)


def itens(texto: str, chave: str) -> int:
    """Quantos elementos de primeiro nível a lista tem."""
    corpo, prof, aspas, n, algo = _lista(texto, chave), 0, None, 0, False
    for c in corpo:
        if aspas:
            if c == aspas:
                aspas = None
            continue
        if c in "\"'`":
            aspas, algo = c, True
        elif c == "[":
            prof += 1
            algo = True
        elif c == "]":
            prof -= 1
        elif c == "," and prof == 0:
            n += 1
    return n + (1 if algo else 0)


def chaves(texto: str) -> set:
    """Chaves do dicionário de um idioma (nome: antes de valor), fora das strings."""
    sem_strings = re.sub(r'"(?:\\.|[^"\\])*"|`(?:\\.|[^`\\])*`', '""', texto)
    return set(re.findall(r"([a-z][a-z0-9_]*)\s*:", sem_strings))


class Rotas(unittest.TestCase):
    def pegar(self, porta, rota):
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}{rota}", timeout=30) as r:
            return r.status, r.read().decode("utf-8")

    def test_raiz_por_instalacao(self):
        for inst, raiz_site in (({"login": True, "instalacao": "instituto", "cadastro_aberto": True}, True), ({"login": True}, False)):
            h = Hub(org="site-teste")
            srv = servidor.iniciar(h, 0, endereco="127.0.0.1", instancia=inst)
            try:
                porta = srv.server_address[1]
                st, html = self.pegar(porta, "/")
                self.assertEqual(st, 200)
                self.assertEqual('id="site-instituto"' in html, raiz_site, inst)
                if raiz_site:
                    st, html = self.pegar(porta, "/plataforma/")
                    self.assertEqual(st, 200)
                    self.assertNotIn('id="site-instituto"', html)
            finally:
                srv.shutdown()
                srv.server_close()


class Pagina(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = ler(SITE)
        m = re.search(r'<script id="site-instituto">\n(.*?)</script>', cls.h, re.S)
        cls.js = m.group(1)

    def test_um_titulo_e_barra_unica(self):
        self.assertEqual(len(re.findall(r"<h1\b", self.h)), 1)
        self.assertIn('data-physis-preferencias="lugar"', self.h)
        self.assertIn("PxPref.iniciar(", self.h)
        pref = ler(RAIZ / "sistema" / "physis-preferencias.js").replace("\r\n", "\n")
        m = re.search(r'<script id="physis-preferencias">\n(.*?)</script>', self.h, re.S)
        self.assertEqual(m.group(1), pref, "rode ferramentas/sincronizar.py")
        self.assertIn('html[data-tema="escuro"]', self.h)

    def test_so_cores_da_paleta(self):
        paleta = set(re.findall(r"#[0-9A-Fa-f]{6}", ler(AQUI / "docs" / "PALETA.md").split("## Lista completa")[1]))
        estilo = re.search(r"<style>(.*?)</style>", self.h, re.S).group(1)
        fora = {c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}\b", estilo)} - {c.upper() for c in paleta}
        self.assertEqual(fora, set(), "cores fora da PALETA.md")

    def test_sem_internet_sem_eval(self):
        self.assertNotRegex(self.js, r"\beval\(|new Function\(")
        self.assertNotRegex(self.h, r'(?i)(src|href)\s*=\s*"https?://')
        self.assertNotRegex(self.js, r"fetch\(\s*[`'\"]https?://")

    def test_ids_fixos_sem_repetir(self):
        corpo = re.sub(r"<script.*?</script>", "", self.h, flags=re.S)
        ids = re.findall(r'\bid="([^"$]+)"', corpo)
        self.assertEqual(len(ids), len(set(ids)), ids)

    def test_portugues_e_ingles_iguais(self):
        bloco = re.search(r"const T = \{(.*?)\n\};", self.js, re.S).group(1)
        pt, en = bloco.split("\n  en: {", 1)
        self.assertEqual(chaves(pt) - {"pt"}, chaves(en))
        for k in ("p3d_linhas", "lon_linhas", "eve_tipos", "ini_frentes", "del_cotas", "lon_mapa", "par_passos", "ino_trilhas", "p3d_cols"):
            self.assertEqual(itens(pt, k), itens(en, k), k)
            self.assertGreater(itens(pt, k), 0, k)

    def test_abas_pedidas(self):
        for aba in ("inicio", "inovastem", "delas", "p3d", "parcerias", "eventos", "longo", "participar"):
            self.assertIn(f'"{aba}"', self.js)
        for tela in ("telaInicio", "telaInovastem", "telaDelas", "telaP3d", "telaParcerias", "telaEventos", "telaLongo", "telaParticipar"):
            self.assertIn(f"function {tela}(", self.js)

    def test_conteudo_segue_as_decisoes(self):
        for nome in ("Global South", "AWPI", "S2 Services", "Fundo Elas", "Petrobras", "FINEP", "FAPERJ", "Serratec", "GIZ"):
            self.assertNotIn(nome, self.h, nome)
        self.assertNotRegex(self.h, r"2027\s*[–-]\s*2032")
        self.assertIn("2027–2031", self.js)
        self.assertIn("[CONFERIR]", self.js)
        for dev in ('["Química"', '["IA de texto ou imagem para 3D"', '["CAD com parâmetros"'):
            linha = self.js[self.js.index(dev):self.js.index("]", self.js.index(dev)) + 1]
            self.assertTrue(linha.rstrip("]").endswith('"dev"'), dev)
        self.assertIn("/api/publico/cadastro", self.js)
        self.assertIn("X-Physis-CSRF", self.js)


class Pacote(unittest.TestCase):
    def test_site_so_no_pacote_do_instituto(self):
        import zipfile
        sys.path.insert(0, str(AQUI))
        import montar
        with tempfile.TemporaryDirectory() as tmp:
            zi = montar.montar("instituto-x", "sede", ["gestao"], Path(tmp) / "a", None, "", instalacao="instituto")
            zp = montar.montar("cliente-x", "sede", ["gestao"], Path(tmp) / "b", None, "")
            with zipfile.ZipFile(zi) as z:
                nomes = z.namelist()
                self.assertTrue(any(n.endswith("/web/site.html") for n in nomes))
                inst = json.loads(z.read(next(n for n in nomes if n.endswith("/instancia.json"))).decode("utf-8"))
                self.assertTrue(inst["cadastro_aberto"] and inst["moderacao_previa"])
                # LEIA-ME do pacote (achado na versão de teste de 19/11/2026): senha mínima e banco certos, site em "/"
                leia = z.read(next(n for n in nomes if n.endswith("/LEIA-ME.md"))).decode("utf-8")
                from physis_hub import seguranca as seg
                self.assertIn(f"pelo menos {seg.SENHA_MIN} caracteres", leia)
                self.assertIn("`physis-instituto.db`", leia)
                self.assertIn("/plataforma/", leia)
            with zipfile.ZipFile(zp) as z:
                self.assertFalse(any(n.endswith("/web/site.html") for n in z.namelist()))
                leia = z.read(next(n for n in z.namelist() if n.endswith("/LEIA-ME.md"))).decode("utf-8")
                self.assertIn("`physis-hub.db`", leia)
                self.assertNotIn("/plataforma/", leia)


if __name__ == "__main__":
    unittest.main()
