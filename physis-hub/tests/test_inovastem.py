"""InovaSTEM: site e living lab online (physis_hub/inovastem.py e web/inovastem.html; D94 de 19/11/2026).

Protege:
1. Cadastro de interesse com coleta mínima: e-mail válido, aceite do aviso beta, responsável para menores, gênero opcional
   (só "feminino" abre o convite Delas); o registro encadeado não leva nome, e-mail nem gênero; mesmo e-mail atualiza.
2. Desafios (só a equipe publica) e projetos abertos (sugestão pública, só aparece depois da moderação; recusa pede motivo);
   o e-mail de quem sugeriu nunca sai na rota pública; pedido de exclusão (LGPD) apaga o cadastro e o contato.
3. Materiais: só arquivos listados no instancia.json E presentes na pasta; nada de subir de pasta.
   WhatsApp: só convite https://chat.whatsapp.com/.
4. Servidor: "/" é o site na instalação inovastem; /plataforma/; /termos e /privacidade vão para o aviso beta do site;
   as rotas da InovaSTEM não existem nas outras instalações; as da equipe pedem sessão da equipe.
5. Página: um h1, barra única igual ao original, tema escuro, só cores da PALETA.md, contraste AA dos pares de cores
   (claro e escuro), sem internet, sem eval, ids fixos únicos, PT e EN com as mesmas chaves, abas pedidas, sem a marca do
   Instituto, sem "open source" (D92), hackathon em março de 2027, Amigo só pessoa física.
6. Pacote inovastem: leva o site, a pasta de materiais e a configuração; o do Instituto não leva o site da InovaSTEM.
"""
import json
import os
import re
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from physis_hub import inovastem as ino_mod
from physis_hub import seguranca as seg
from physis_hub import servidor
from physis_hub.hub import Hub

AQUI = Path(__file__).resolve().parents[1]
RAIZ = AQUI.parent
PAGINA = AQUI / "web" / "inovastem.html"
SENHA = "frase-longa-da-direcao-1"
EQUIPE = {"usuario": "eq@x.example", "papel": seg.EQUIPE}
CLIENTE = {"usuario": "cli@x.example", "papel": seg.CLIENTE}
OK = {"nome": "Ana", "email": "ana@x.example", "areas": ["gis", "bim"], "maior_de_idade": True, "aceite": True}


def ler(p: Path) -> str:
    return p.read_text(encoding="utf-8")


class Interesse(unittest.TestCase):
    def setUp(self):
        self.h = Hub(org="ino-teste")
        self.i = ino_mod.InovaSTEM(self.h, {})

    def test_coleta_minima_e_erros(self):
        self.assertTrue(self.i.interesse(dict(OK))["ok"])
        for mudar, trecho in (({"email": "sem-arroba"}, "e-mail"), ({"aceite": False}, "aviso de privacidade"),
                              ({"maior_de_idade": False}, "responsável"), ({"genero": "x"}, "Gênero"), ({"nome": "A"}, "nome")):
            r = self.i.interesse(dict(OK, **mudar))
            self.assertFalse(r["ok"], mudar)
            self.assertIn(trecho, r["erro"])
        r = self.i.interesse(dict(OK, email="bia@x.example", maior_de_idade=False, responsavel_nome="Mãe da Bia",
                                  responsavel_email="mae@x.example"))
        self.assertTrue(r["ok"])

    def test_delas_so_com_feminino_e_mesmo_email_atualiza(self):
        r = self.i.interesse(dict(OK, genero="masculino", quero_delas=True))
        self.assertFalse(r["delas"])
        r = self.i.interesse(dict(OK, nome="Ana Clara", genero="feminino", quero_delas=True))
        self.assertTrue(r["delas"])
        lista = self.i.interesses(EQUIPE)
        self.assertEqual(lista["total"], 1, "o mesmo e-mail atualiza, não duplica")
        x = lista["itens"][0]
        self.assertEqual((x["nome"], x["quero_delas"]), ("Ana Clara", 1))
        self.assertIn("delas", x["areas"])
        self.assertNotIn("genero", x, "a equipe vê só o convite Delas, não o gênero")
        self.assertFalse(self.i.interesses(CLIENTE)["ok"])

    def test_registro_sem_dado_pessoal(self):
        self.i.interesse(dict(OK, genero="feminino"))
        texto = json.dumps(self.h._db.execute("SELECT * FROM registro").fetchall(), ensure_ascii=False) \
            if self.h._db.execute("SELECT name FROM sqlite_master WHERE name='registro'").fetchone() else ""
        for pessoal in ("ana@x.example", "Ana", "feminino"):
            self.assertNotIn(pessoal, texto)


class Propostas(unittest.TestCase):
    def setUp(self):
        self.h = Hub(org="ino-prop")
        self.i = ino_mod.InovaSTEM(self.h, {})
        self.sug = {"titulo": "Mapa de hortas urbanas", "descricao": "Mapear hortas do bairro com GIS aberto e a comunidade.",
                    "area": "gis", "email": "eva@x.example", "nome": "Eva", "aceite": True}

    def test_moderacao_e_privacidade(self):
        self.assertFalse(self.i.sugerir_projeto(dict(self.sug, aceite=False))["ok"])
        self.assertFalse(self.i.sugerir_projeto(dict(self.sug, email=""))["ok"])
        r = self.i.sugerir_projeto(self.sug)
        self.assertEqual(r["estado"], "pendente")
        self.assertEqual(self.i.propostas()["itens"], [], "pendente não aparece")
        self.assertFalse(self.i.moderar({"id": r["id"], "decisao": "aprovar"}, CLIENTE)["ok"])
        self.assertFalse(self.i.moderar({"id": r["id"], "decisao": "recusar"}, EQUIPE)["ok"], "recusa pede motivo")
        self.assertTrue(self.i.moderar({"id": r["id"], "decisao": "aprovar"}, EQUIPE)["ok"])
        pub = self.i.propostas("projeto")
        self.assertEqual([x["titulo"] for x in pub["itens"]], ["Mapa de hortas urbanas"])
        self.assertNotIn("eva@x.example", json.dumps(pub))
        self.assertNotIn("Eva", json.dumps(pub))
        self.assertEqual(self.i.moderar({"id": r["id"], "decisao": "aprovar"}, EQUIPE).get("codigo"), 409)

    def test_desafio_so_equipe(self):
        d = {"titulo": "Desafio do telhado verde", "descricao": "Reduzir a temperatura do telhado da oficina com SbN.", "prazo": "2027-02-28"}
        self.assertEqual(self.i.publicar_desafio(d, CLIENTE).get("codigo"), 403)
        self.assertEqual(self.i.publicar_desafio(d, EQUIPE)["estado"], "publicado")
        self.assertFalse(self.i.publicar_desafio(dict(d, prazo="28/02/2027"), EQUIPE)["ok"])
        self.assertEqual(len(self.i.propostas("desafio")["itens"]), 1)
        self.assertFalse(self.i.propostas("outro")["ok"])

    def test_exclusao_lgpd(self):
        self.i.interesse(dict(OK))
        self.i.sugerir_projeto(dict(self.sug, email="ana@x.example"))
        r = self.i.remover_interesse({"email": "ANA@x.example"}, EQUIPE)
        self.assertEqual((r["interesses"], r["propostas"]), (1, 1))
        self.assertEqual(self.i.interesses(EQUIPE)["total"], 0)
        self.assertEqual(self.i.fila(EQUIPE)["itens"][0]["email"], "")


class MateriaisEWhatsApp(unittest.TestCase):
    def test_so_listados_e_presentes(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            (pasta / "apresentacao.pdf").write_bytes(b"%PDF-1.4 teste")
            (pasta / "segredo.pdf").write_bytes(b"%PDF nao listado")
            inst = {"inovastem": {"materiais": [{"titulo": "Apresentação", "arquivo": "apresentacao.pdf"},
                                                {"titulo": "Falta", "arquivo": "falta.pdf"},
                                                {"titulo": "Fora", "arquivo": "../fora.pdf"},
                                                {"titulo": "Exe", "arquivo": "x.exe"}]}}
            i = ino_mod.InovaSTEM(Hub(org="ino-mat"), inst, pasta_materiais=pasta)
            self.assertEqual([m["arquivo"] for m in i.materiais()], ["apresentacao.pdf"])
            self.assertEqual(i.arquivo_material("apresentacao.pdf")[0], "application/pdf")
            for nome in ("segredo.pdf", "../fora.pdf", "falta.pdf"):
                self.assertIsNone(i.arquivo_material(nome), nome)

    def test_areas_separadas(self):
        # direção, 20/11/2026: "devem ser separados, são escopos diferentes"
        for k in ("modelagem3d", "physis3d", "gemeo", "simulacoes", "ciberseguranca", "hackathon", "desafios", "projetos",
                  "patrocinio", "parcerias"):
            self.assertIn(k, ino_mod.AREAS)
        for nome in list(ino_mod.AREAS.values()) + list(ino_mod.AREAS_EN.values()):
            self.assertNotRegex(nome, r" (e|and) ", nome)
        self.assertEqual(set(ino_mod.AREAS), set(ino_mod.AREAS_EN))

    def test_whatsapp_so_convite(self):
        self.assertEqual(ino_mod.link_whatsapp("https://chat.whatsapp.com/AbCdEf1234567890"), "https://chat.whatsapp.com/AbCdEf1234567890")
        for ruim in ("http://chat.whatsapp.com/AbCdEf1234567890", "https://exemplo.com/x", "javascript:alert(1)", "", None):
            self.assertEqual(ino_mod.link_whatsapp(ruim), "")
        antes = os.environ.pop("PHYSIS_INOVASTEM_WHATSAPP", None)
        try:
            self.assertEqual(ino_mod.config_de({"inovastem": {"whatsapp_grupo": "https://evil.example"}})["whatsapp"], "")
        finally:
            if antes is not None:
                os.environ["PHYSIS_INOVASTEM_WHATSAPP"] = antes


class Rotas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.antes = os.environ.get("PHYSIS_LIMITE_ENTRAR")
        os.environ["PHYSIS_LIMITE_ENTRAR"] = "0"
        cls.h = Hub(org="ino-rotas")
        cls.srv = servidor.iniciar(cls.h, 0, endereco="127.0.0.1", instancia={
            "login": True, "cadastro_aberto": True, "moderacao_previa": True, "instalacao": "inovastem",
            "inovastem": {"whatsapp_grupo": "https://chat.whatsapp.com/AbCdEf1234567890"}})
        cls.porta = cls.srv.server_address[1]
        cls.h.criar_conta("Direção", "dir@r.example", SENHA)
        tk = cls.h.entrar("dir@r.example", SENHA)["token"]
        cls.dir = ("physis_sessao=" + tk, seg.csrf_de(cls.h, tk))

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        os.environ.pop("PHYSIS_LIMITE_ENTRAR", None)
        if cls.antes is not None:
            os.environ["PHYSIS_LIMITE_ENTRAR"] = cls.antes

    def pedir(self, metodo, rota, corpo=None, s=None, porta=None):
        cab = {"Content-Type": "application/json"}
        if s:
            cab.update({"Cookie": s[0], "X-Physis-CSRF": s[1]})
        req = urllib.request.Request(f"http://127.0.0.1:{porta or self.porta}{rota}", method=metodo, headers=cab,
                                     data=json.dumps(corpo).encode() if corpo is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                corpo_r = r.read()
                return r.status, (json.loads(corpo_r) if corpo_r.strip().startswith(b"{") else corpo_r.decode("utf-8"))
        except urllib.error.HTTPError as e:
            b = e.read()
            return e.code, (json.loads(b) if b.strip().startswith(b"{") else {})

    def test_paginas(self):
        st, html = self.pedir("GET", "/")
        self.assertEqual(st, 200)
        self.assertIn('id="site-inovastem"', html)
        st, html = self.pedir("GET", "/plataforma/")
        self.assertEqual(st, 200)
        self.assertNotIn('id="site-inovastem"', html)
        # fontes do guia servidas aqui (OFL), sem internet; nada além das duas
        with urllib.request.urlopen(f"http://127.0.0.1:{self.porta}/fontes/JosefinSans.ttf", timeout=30) as r:
            self.assertEqual((r.status, r.headers["Content-Type"]), (200, "font/ttf"))
        self.assertEqual(self.pedir("GET", "/fontes/../servidor.py")[0] in (400, 404), True)
        with urllib.request.urlopen(f"http://127.0.0.1:{self.porta}/", timeout=30) as r:
            self.assertEqual(r.headers["Cache-Control"], "no-cache")

        class SemSeguir(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        abrir = urllib.request.build_opener(SemSeguir)
        for rota in ("/termos", "/privacidade"):
            with self.assertRaises(urllib.error.HTTPError) as c:
                abrir.open(f"http://127.0.0.1:{self.porta}{rota}", timeout=30)
            self.assertEqual((c.exception.code, c.exception.headers["Location"]), (302, "/#" + rota.strip("/")))

    def test_fluxo_publico_e_equipe(self):
        st, r = self.pedir("GET", "/api/publico/inovastem")
        self.assertEqual((st, r["whatsapp"], r["hackathon"]), (200, "https://chat.whatsapp.com/AbCdEf1234567890", "2027-03"))
        st, r = self.pedir("POST", "/api/publico/inovastem/interesse", dict(OK, email="rota@x.example", genero="feminino", quero_delas=True))
        self.assertEqual((st, r.get("delas")), (200, True), r)
        st, r = self.pedir("POST", "/api/publico/inovastem/interesse", dict(OK, extra=1))
        self.assertEqual(st, 400, "campo fora do esquema é recusado")
        st, r = self.pedir("POST", "/api/publico/inovastem/projeto", {"titulo": "Gêmeo digital da horta", "aceite": True,
                                                                      "descricao": "Sensores e modelo da horta comunitária.", "email": "z@x.example"})
        self.assertEqual(st, 200, r)
        self.assertEqual(self.pedir("GET", "/api/inovastem/fila")[0], 401)
        self.assertEqual(self.pedir("POST", "/api/inovastem/moderar", {"id": r["id"], "decisao": "aprovar"})[0], 401)
        st, f = self.pedir("GET", "/api/inovastem/fila", s=self.dir)
        self.assertEqual(len(f["itens"]), 1)
        st, m = self.pedir("POST", "/api/inovastem/moderar", {"id": r["id"], "decisao": "aprovar"}, self.dir)
        self.assertEqual(st, 200, m)
        st, pub = self.pedir("GET", "/api/publico/inovastem/propostas?tipo=projeto")
        self.assertEqual(len(pub["itens"]), 1)
        self.assertNotIn("z@x.example", json.dumps(pub))
        st, lst = self.pedir("GET", "/api/inovastem/interesses", s=self.dir)
        self.assertEqual(lst["total"], 1)
        st, cats = self.pedir("GET", "/api/publico/comunidade/categorias")
        self.assertTrue({"modelagem", "desafios", "hackathon"} <= {c["id"] for c in cats["categorias"]})

    def test_rotas_nao_existem_em_outra_instalacao(self):
        h = Hub(org="ino-outra")
        srv = servidor.iniciar(h, 0, endereco="127.0.0.1", instancia={"login": True, "instalacao": "instituto", "cadastro_aberto": True})
        try:
            porta = srv.server_address[1]
            self.assertEqual(self.pedir("GET", "/api/publico/inovastem", porta=porta)[0], 404)
            self.assertEqual(self.pedir("POST", "/api/publico/inovastem/interesse", dict(OK), porta=porta)[0], 404)
            st, html = self.pedir("GET", "/", porta=porta)
            self.assertNotIn('id="site-inovastem"', html)
        finally:
            srv.shutdown()
            srv.server_close()


def _lum(h: str) -> float:
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contraste(a: str, b: str) -> float:
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _chaves(texto: str) -> set:
    sem = re.sub(r'"(?:\\.|[^"\\])*"|`(?:\\.|[^`\\])*`', '""', texto)
    return set(re.findall(r"([a-z][a-z0-9_]*)\s*:", sem))


def _n_itens(texto: str, chave: str) -> int:
    i = texto.index(chave + ":[") + len(chave) + 1
    prof, aspas, n, j = 0, None, 0, i
    while True:
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
                return n + 1
        elif c == "," and prof == 1:
            n += 1
        j += 1


class Pagina(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = ler(PAGINA)
        cls.js = re.search(r'<script id="site-inovastem">\n(.*?)</script>', cls.h, re.S).group(1)
        cls.css = re.search(r"<style>(.*?)</style>", cls.h, re.S).group(1)

    def tokens(self, seletor: str) -> dict:
        bloco = re.search(re.escape(seletor) + r"\{(.*?)\n\}", self.css, re.S).group(1)
        return dict(re.findall(r"--([a-z0-9-]+):(#[0-9A-Fa-f]{6})", bloco))

    def test_regras_da_tela(self):
        self.assertEqual(len(re.findall(r"<h1\b", self.h)), 1)
        self.assertIn('data-physis-preferencias="lugar"', self.h)
        pref = ler(RAIZ / "sistema" / "physis-preferencias.js").replace("\r\n", "\n")
        m = re.search(r'<script id="physis-preferencias">\n(.*?)</script>', self.h, re.S)
        self.assertEqual(m.group(1), pref, "rode ferramentas/sincronizar.py")
        self.assertIn('html[data-tema="escuro"]', self.css)
        self.assertNotRegex(self.js, r"\beval\(|new Function\(")
        self.assertNotRegex(self.h, r'(?i)(src|href)\s*=\s*"https?://')
        self.assertNotRegex(self.js, r"fetch\(\s*[`'\"]https?://")
        corpo = re.sub(r"<script.*?</script>", "", self.h, flags=re.S)
        ids = re.findall(r'\bid="([^"$]+)"', corpo)
        self.assertEqual(len(ids), len(set(ids)), ids)

    def test_cores_da_paleta_e_contraste(self):
        paleta = {c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}", ler(AQUI / "docs" / "PALETA.md"))}
        fora = {c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}\b", self.css)} - paleta
        self.assertEqual(fora, set(), "cores fora da PALETA.md")
        claro, escuro = self.tokens(":root"), self.tokens('html[data-tema="escuro"]')
        escuro = dict(claro, **escuro)
        pares = [("texto", "fundo"), ("texto", "sup"), ("tinta2", "fundo"), ("tinta2", "sup"), ("titulo-cor", "fundo"),
                 ("titulo-cor", "sup"), ("link", "fundo"), ("link", "sup"), ("sobre-acao", "acao"), ("sobre-delas", "delas"),
                 ("delas-t", "delas-f"), ("texto", "delas-f"), ("ok-t", "ok-f"), ("al-t", "al-f"), ("at-t", "at-f"),
                 ("sobrancelha", "fundo"), ("sec", "fundo"), ("sec", "sup"), ("sobre-faixa", "faixa"), ("texto", "campo"),
                 ("erro-msg", "sup"), ("erro-msg", "fundo")]
        for nome, tk in (("claro", claro), ("escuro", escuro)):
            for a, b in pares:
                self.assertGreaterEqual(round(contraste(tk[a], tk[b]), 2), 4.5, f"{nome}: --{a} sobre --{b}")
            self.assertGreaterEqual(contraste(tk["borda-campo"], tk["sup"]), 3.0, f"{nome}: borda dos campos")
        self.assertLess(contraste("#FFFFFF", "#F97316"), 4.5, "o laranja nunca é fundo de texto branco")
        # Guia de Identidade de 19/11/2026: papéis sem alteração
        for tk in (claro, escuro):
            self.assertEqual((tk["acao"].upper(), tk["sobre-acao"].upper(), tk["semente"].upper()), ("#C2410C", "#FFFFFF", "#F97316"))
            self.assertEqual(tk["faixa"].upper(), "#0B3D2E")
        self.assertEqual((claro["fundo"].upper(), claro["titulo-cor"].upper(), claro["delas-f"].upper()), ("#FFF7ED", "#0B3D2E", "#EDE9FE"))
        self.assertEqual((escuro["fundo"].upper(), escuro["texto"].upper(), escuro["delas-t"].upper()), ("#1B1F23", "#F4F1EA", "#C4B5FD"))

    def test_so_cores_do_guia_sem_azul_roxo_so_na_delas(self):
        # direção, 19/11/2026: verdes, laranja e terracota; roxo exclusivo da Delas; nada de azul; nada alterado
        guia = {"#0B3D2E", "#1B1F23", "#F4F1EA", "#F97316", "#C2410C", "#FFF7ED", "#7C3AED", "#EDE9FE", "#C4B5FD", "#FFFFFF"}
        neutros = {"#D9D3C2", "#8A9284", "#8A9182", "#4A4F44", "#4A5A47"}
        avisos = {"#7A2214", "#F5E2D7", "#D9A58C"}     # terracota nos avisos (dona, 20/11/2026): o laranja fica para a marca
        usadas = {c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}", self.css)}
        self.assertEqual(usadas - guia - neutros - avisos, set(), "cor fora do guia")
        estados = re.findall(r"--(?:at|al)-t:(#[0-9A-Fa-f]{6})", self.css) + re.findall(r"--erro-msg:(#[0-9A-Fa-f]{6})", self.css)
        self.assertFalse({c.upper() for c in estados} & {"#F97316", "#C2410C"}, "laranja da marca em aviso")
        for c in usadas:
            r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
            if c not in {"#7C3AED", "#EDE9FE", "#C4B5FD"}:
                self.assertLess(b - max(r, g), 16, f"tom azul ou roxo fora da Delas: {c}")   # carvão #1B1F23 é neutro (+4)
        roxos = [linha for linha in self.css.splitlines() if "var(--delas" in linha]
        for linha in roxos:
            self.assertRegex(linha, r"delas", linha)

    def test_guia_de_identidade(self):
        # logos do guia (InovaSTEM opção 2 e Delas opção 1), embutidos, versão clara e escura; sem desenho próprio
        self.assertEqual(len(re.findall(r'src="data:image/webp;base64,', self.h)), 2)
        self.assertEqual(len(re.findall(r'"data:image/webp;base64,', self.js)), 2)
        self.assertIn('class="so-claro"', self.h)
        self.assertIn('class="so-escuro"', self.h)
        self.assertNotIn("<svg", re.sub(r"<script.*?</script>", "", self.h, flags=re.S))
        self.assertIn('"Josefin Sans"', self.css)
        self.assertIn("Lora", self.css)
        self.assertNotRegex(self.css, r"Fraunces|Lexend")
        self.assertIn('id="endosso"', self.h)
        self.assertIn('endosso_a:"uma iniciativa"', self.js)
        menu = re.search(r"const MENU = \[(.*?)\]", self.js).group(1)
        self.assertLessEqual(menu.count(","), 5, "guia: menu de até 6 itens")
        self.assertIn('id="cta" href="#participar"', self.h)
        for k in ("int-p1", "int-p2", 'role="progressbar"', "int-seguir"):
            self.assertIn(k, self.js, k)
        # missões recomendadas do doc 37 (D92) no ecossistema; "M&V aberto" fora até a licença
        self.assertIn("Acelerar a transição justa com engenharia de precisão e dados verificáveis", self.js)
        self.assertIn("Formar mulheres e jovens de comunidades sub-representadas em STEM", self.js)
        self.assertNotIn("M&V aberto", self.h)

    def test_portugues_e_ingles_iguais(self):
        bloco = re.search(r"const T = \{(.*?)\n\};", self.js, re.S).group(1)
        pt, en = bloco.split("\n  en: {", 1)
        self.assertEqual(_chaves(pt) - {"pt"}, _chaves(en))
        for k in ("ini_blocos", "ini_duas", "del_o_que", "del_entrar", "for_regras", "mod_cols", "mod_linhas", "hac_regras",
                  "hac_falta", "mat_rede", "mat_pat_cols", "mat_pat_linhas", "mat_pat_regras", "mat_eco", "ter_blocos", "pri_blocos"):
            self.assertEqual(_n_itens(pt, k), _n_itens(en, k), k)

    def test_conteudo_pedido(self):
        for aba in ("inicio", "delas", "desafios", "forum", "modelagem", "hackathon", "materiais", "participar", "termos", "privacidade"):
            self.assertIn(f'"{aba}"', self.js, aba)
        for rota in ("/api/publico/inovastem/interesse", "/api/publico/inovastem/projeto", "/api/publico/cadastro",
                     "/api/publico/comunidade", "/api/publico/3d/pecas", "/planejador", "/plataforma/", "X-Physis-CSRF"):
            self.assertIn(rota, self.js, rota)
        self.assertIn("Março de 2027", self.js)
        self.assertIn('["Amigo","Só pessoa física","R$ 750"', self.js)
        self.assertIn("R$ 1.000 a R$ 4.999", self.js)
        self.assertIn("uma iniciativa da Physis Engineering", self.h)
        self.assertIn("Versão beta · em revisão jurídica", self.js)
        self.assertIn("jovens, cis e trans", self.js)
        self.assertIn("Não oferece atendimento psicológico nem clínico", self.js)
        self.assertIn('chat.whatsapp.com/', self.js)
        # marcas separadas (D94) e linguagem externa até a licença (D92)
        self.assertNotIn("Instituto Physis", self.h)
        self.assertNotRegex(self.h, r"(?i)open[ -]source|código aberto")
        for nome in ("Global South", "AWPI", "rafaella", "@physisengineering.com"):
            self.assertNotIn(nome, self.h, nome)


class Laboratorio(unittest.TestCase):
    """/laboratorio (web/inovastem-lab.html, gerado por ferramentas/montar_lab_inovastem.py): Simulação e Physis 3D."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(RAIZ / "ferramentas"))
        import montar_lab_inovastem as lab
        cls.lab = lab
        cls.h = ler(AQUI / "web" / "inovastem-lab.html")

    def test_em_dia_com_os_motores(self):
        self.assertEqual(self.h, self.lab.montar(), "rode: python ferramentas/montar_lab_inovastem.py")
        for ident, arq in self.lab.BLOCOS:
            m = re.search(rf'<script id="{ident}">\n(.*?)</script>', self.h, re.S)
            self.assertEqual(m.group(1), ler(arq).replace("\r\n", "\n"), ident)

    def test_regras_da_tela(self):
        fora = re.sub(r"<script.*?</script>", "", self.h, flags=re.S)
        self.assertEqual(len(re.findall(r"<h1\b", fora)), 1)        # os h1 dos motores viram h2 ao desenhar
        self.assertIn('.replace(/<h1(\\s[^>]*)?>/g, "<h2$1>")', self.h)
        self.assertNotRegex(fora, r'(?i)(src|href)\s*=\s*"https?://')
        self.assertIn('id="physis-preferencias"', self.h)
        self.assertIn('href="/planejador"', self.h)
        self.assertIn("não aprova projeto", self.h)

    def test_nenhum_azul_dos_motores_fica_sem_troca(self):
        for _, arq in self.lab.BLOCOS:
            for c in {c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}\b", ler(arq))}:
                r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
                if b - max(r, g) >= 16:
                    self.assertIn(c, self.lab.CORES, f"{arq.name}: {c} azul sem troca")
        guia = {"#0B3D2E", "#1B1F23", "#F4F1EA", "#F97316", "#C2410C", "#FFF7ED"}
        neutros = {"#D9D3C2", "#8A9284", "#4A5A47"}
        self.assertEqual(set(self.lab.CORES.values()) - guia - neutros, set())

    def test_rota(self):
        h = Hub(org="ino-lab")
        srv = servidor.iniciar(h, 0, endereco="127.0.0.1", instancia={"login": True, "instalacao": "inovastem"})
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/laboratorio", timeout=30) as r:
                self.assertIn('id="lab-inovastem"', r.read().decode("utf-8"))
        finally:
            srv.shutdown()
            srv.server_close()


class Pacote(unittest.TestCase):
    def test_pacote_inovastem(self):
        sys.path.insert(0, str(AQUI))
        import montar
        with tempfile.TemporaryDirectory() as tmp:
            zi = montar.montar("inovastem", "living-lab-online", ["cursos", "impressao3d"], Path(tmp) / "a", None, "", instalacao="inovastem")
            zs = montar.montar("instituto-x", "sede", ["gestao"], Path(tmp) / "b", None, "", instalacao="instituto")
            with zipfile.ZipFile(zi) as z:
                nomes = z.namelist()
                self.assertTrue(any(n.endswith("/web/inovastem.html") for n in nomes))
                self.assertFalse(any(n.endswith("/web/site.html") for n in nomes), "sem o site do Instituto")
                self.assertTrue(any(n.endswith("/materiais/LEIA-ME.txt") for n in nomes))
                for f in ("JosefinSans.ttf", "Lora.ttf", "OFL-JosefinSans.txt", "OFL-Lora.txt"):
                    self.assertTrue(any(n.endswith("/web/fontes/" + f) for n in nomes), f)
                inst = json.loads(z.read(next(n for n in nomes if n.endswith("/instancia.json"))).decode("utf-8"))
                self.assertEqual((inst["instalacao"], inst["banco"]), ("inovastem", "physis-inovastem.db"))
                self.assertTrue(inst["cadastro_aberto"] and inst["moderacao_previa"])
                self.assertEqual(inst["inovastem"]["whatsapp_grupo"], "")
            # com o Planejador, o nome da instalação não pode ser trocado pelo último arquivo de vendor/ (defeito de 19/11)
            plan = Path(tmp) / "planejador.html"
            plan.write_text("<!doctype html><title>p</title>", encoding="utf-8")
            zn = montar.montar("inovastem", "lab", ["planejador"], Path(tmp) / "c", None, "", planejador=plan, nome="InovaSTEM",
                               instalacao="inovastem")
            with zipfile.ZipFile(zn) as z:
                inst = json.loads(z.read(next(n for n in z.namelist() if n.endswith("/instancia.json"))).decode("utf-8"))
                self.assertEqual(inst["nome"], "InovaSTEM")
            with zipfile.ZipFile(zs) as z:
                self.assertFalse(any(n.endswith("/web/inovastem.html") for n in z.namelist()))

    def test_ficha_inovastem(self):
        fichas = json.loads(ler(RAIZ / "clientes" / "clientes.json"))["clientes"]
        f = next(x for x in fichas if x["org"] == "inovastem")
        self.assertEqual(f["instalacao"], "inovastem")
        sys.path.insert(0, str(AQUI))
        import montar
        montar.conferir_marca(f["marca"])          # cores só da PALETA.md (SystemExit se não)
        self.assertNotIn("Instituto", f["marca"]["logo_texto"])


if __name__ == "__main__":
    unittest.main()
