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
7. Modelagem Physis 3D (dona, 20/11/2026): fila de impressão (papéis, sessão e CSRF, estados, recusa com motivo, registro sem dado
   pessoal, só na instalação inovastem); /laboratorio com as 8 subabas na ordem (Enviar arquivo primeiro) e com role/aria de
   abas, fluxo visível e passos no projeto comum inovastem-projeto/1, um bloco por fenômeno pelo motor da simulação,
   sistema/physis-imagem-3d.js (imagem → CAD 2D e 3D; peças de teste) copiado igual, gerador em dia; site em PT e EN.
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

    def test_sem_planejador(self):
        # dona, 20/11/2026: Planejador e Modelagem Physis 3D são ferramentas relacionadas, mas separadas
        self.assertEqual(self.pedir("GET", "/planejador")[0], 404)

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
        bloco = re.search(r"(?m)^" + re.escape(seletor) + r"\{(.*?)\n\}", self.css, re.S).group(1)   # bloco que começa na linha
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
        delas_escuro = dict(escuro, **self.tokens('body.aba-delas'), **{})   # herda o bloco claro da Delas, como no navegador
        delas_escuro.update(self.tokens('html[data-tema="escuro"] body.aba-delas'))
        delas_claro = dict(claro, **self.tokens('body.aba-delas'))   # tela lilás da Delas no claro (dona, 20/11/2026)
        conforto = dict(escuro, **self.tokens('html.a11y-verde[data-tema] body:not(.aba-delas)'))   # modo de conforto (20/11/2026)
        pares = [("texto", "fundo"), ("texto", "sup"), ("tinta2", "fundo"), ("tinta2", "sup"), ("titulo-cor", "fundo"),
                 ("titulo-cor", "sup"), ("link", "fundo"), ("link", "sup"), ("sobre-acao", "acao"), ("sobre-delas", "delas"),
                 ("delas-t", "delas-f"), ("texto", "delas-f"), ("ok-t", "ok-f"), ("al-t", "al-f"), ("at-t", "at-f"),
                 ("sobrancelha", "fundo"), ("sec", "fundo"), ("sec", "sup"), ("sobre-faixa", "faixa"), ("texto", "campo"),
                 ("erro-msg", "sup"), ("erro-msg", "fundo")]
        for nome, tk in (("claro", claro), ("escuro", escuro), ("Delas escuro", delas_escuro), ("Delas claro", delas_claro), ("conforto", conforto)):
            for a, b in pares:
                self.assertGreaterEqual(round(contraste(tk[a], tk[b]), 2), 4.5, f"{nome}: --{a} sobre --{b}")
            self.assertGreaterEqual(contraste(tk["borda-campo"], tk["sup"]), 3.0, f"{nome}: borda dos campos")
            self.assertGreaterEqual(contraste(tk["borda-campo"], tk["campo"]), 3.0, f"{nome}: borda do campo sobre o campo")
        self.assertLess(contraste("#FFFFFF", "#F97316"), 4.5, "o laranja nunca é fundo de texto branco")
        # Guia de Identidade de 19/11/2026 e tipos de tela da dona (20/11/2026, PALETA.md): papéis sem alteração
        for tk in (claro, escuro):
            self.assertEqual((tk["acao"].upper(), tk["sobre-acao"].upper(), tk["semente"].upper()), ("#C2410C", "#FFFFFF", "#F97316"))
        # tipo B (claro)
        self.assertEqual((claro["fundo"].upper(), claro["sup"].upper(), claro["faixa"].upper(), claro["titulo-cor"].upper(),
                          claro["sec"].upper(), claro["sobrancelha"].upper(), claro["delas-f"].upper()),
                         ("#FFF7ED", "#FFFFFF", "#0B3D2E", "#1A4D2E", "#1A4D2E", "#C2410C", "#EDE9FE"))
        # tipo A (escuro verde): laranja nunca em texto pequeno
        self.assertEqual((escuro["fundo"].upper(), escuro["sup"].upper(), escuro["linha"].upper(), escuro["texto"].upper(),
                          escuro["tinta2"].upper(), escuro["sobrancelha"].upper(), escuro["delas-t"].upper()),
                         ("#0B3D2E", "#0F4535", "#2F5E4E", "#F4F1EA", "#C3D0BD", "#D9A58C", "#C4B5FD"))
        # Delas no escuro: roxo profundo
        self.assertEqual((delas_escuro["fundo"].upper(), delas_escuro["sup"].upper(), delas_escuro["linha"].upper()),
                         ("#2B2143", "#3D2A5C", "#5B4A7A"))

    def test_so_cores_do_guia_sem_azul_roxo_so_na_delas(self):
        # direção, 19/11/2026: verdes, laranja e terracota; roxo exclusivo da Delas; nada de azul; nada alterado
        guia = {"#0B3D2E", "#1B1F23", "#F4F1EA", "#F97316", "#C2410C", "#FFF7ED", "#7C3AED", "#EDE9FE", "#C4B5FD", "#FFFFFF"}
        neutros = {"#D9D3C2", "#8A9284", "#8A9182", "#4A4F44", "#4A5A47"}
        avisos = {"#7A2214", "#F5E2D7", "#D9A58C", "#BB6B4A"}     # terracota nos avisos (dona, 20/11/2026): o laranja fica para a marca
        tipos = {"#1A4D2E", "#0F4535", "#2F5E4E", "#C3D0BD", "#8FB183"}    # tipos de tela A e B (dona, 20/11/2026)
        tipos |= {"#1C2B21", "#2A3829", "#EEF2EA", "#B9CDB3"}           # modo de conforto: "fundo verde (opção)" da PALETA.md
        delas = {"#7C3AED", "#EDE9FE", "#C4B5FD", "#2B2143", "#3D2A5C", "#5B4A7A"}   # roxo: só a Delas
        usadas = {c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}", self.css)}
        self.assertEqual(usadas - guia - neutros - avisos - tipos - delas, set(), "cor fora do guia")
        self.assertTrue(all("aba-delas" in bloco or "delas" in bloco for bloco in re.findall(r"[^}]*(?:#2E1A47|#3D2A5C|#5B4A7A)[^}]*", self.css)),
                        "roxo profundo só no bloco da Delas")
        estados = re.findall(r"--(?:at|al)-t:(#[0-9A-Fa-f]{6})", self.css) + re.findall(r"--erro-msg:(#[0-9A-Fa-f]{6})", self.css)
        self.assertFalse({c.upper() for c in estados} & {"#F97316", "#C2410C"}, "laranja da marca em aviso")
        for c in usadas:
            r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
            if c not in delas:
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
        self.assertIn("Conectar pessoas, organizações e projetos para trocar informações, formar parcerias e resolver desafios de modelagem com códigos abertos", self.js)
        self.assertNotIn("Formar mulheres e jovens", self.h)   # formação só na Delas (dona, 20/11/2026)
        self.assertNotIn("M&V aberto", self.h)

    def test_tema_escuro_da_delas_sem_verde(self):
        # dona, 21/11/2026: na tela roxa o rótulo do tema escuro é só "Escuro"/"Dark"; o módulo comum não muda
        self.assertIn('escuroDelas(aba === "delas" || aba === "delas_entrar");', self.js)
        self.assertIn(r'replace(/ \((verde|green)\)/i, "")', self.js)

    def test_toda_chave_usada_existe(self):
        # botão vazio na Delas (20/11/2026): chave renomeada e ainda usada
        bloco = re.search(r"const T = \{(.*?)\n\};", self.js, re.S).group(1)
        pt = bloco.split("\n  en: {", 1)[0]
        for k in set(re.findall(r'\bt\("([a-z0-9_]+)"\)', self.js)):
            self.assertRegex(pt, rf"(?<![a-z0-9_]){k}:", k)

    def test_portugues_e_ingles_iguais(self):
        bloco = re.search(r"const T = \{(.*?)\n\};", self.js, re.S).group(1)
        pt, en = bloco.split("\n  en: {", 1)
        self.assertEqual(_chaves(pt) - {"pt"}, _chaves(en))
        for k in ("ini_blocos", "ini_duas", "del_o_que", "del_entrar", "for_regras", "mod_cols", "mod_linhas", "hac_regras",
                  "hac_falta", "mat_rede", "mat_pat_cols", "mat_pat_linhas", "mat_pat_regras", "mat_eco", "ter_blocos", "pri_blocos"):
            self.assertEqual(_n_itens(pt, k), _n_itens(en, k), k)

    def test_conteudo_pedido(self):
        # formulário próprio da Delas: entra na Delas e, automaticamente, na InovaSTEM (dona, 20/11/2026)
        self.assertIn('"delas_entrar"', self.js)
        self.assertIn('href="#delas_entrar"', self.js)
        self.assertIn('genero: "feminino", quero_delas: true', self.js)
        self.assertIn('areas: ["delas"].concat(', self.js)
        for aba in ("inicio", "delas", "desafios", "forum", "modelagem", "hackathon", "materiais", "participar", "termos", "privacidade"):
            self.assertIn(f'"{aba}"', self.js, aba)
        for rota in ("/api/publico/inovastem/interesse", "/api/publico/inovastem/projeto", "/api/publico/cadastro",
                     "/api/publico/comunidade", "/api/publico/3d/pecas", "/laboratorio", "/plataforma/", "X-Physis-CSRF"):
            self.assertIn(rota, self.js, rota)
        self.assertIn("Março de 2027", self.js)
        # cotas da dona (20/11/2026): Amigo 500 (só pessoa física), Apoiador 1.000, Parceiros 2.500, Patrocinador 5.000, master 10.000+
        self.assertIn('["Amigo","Só pessoa física","R$ 500"', self.js)
        for v in ('"R$ 1.000"', '"R$ 2.500"', '"R$ 5.000"', '"A partir de R$ 10.000"'):
            self.assertIn(v, self.js, v)
        self.assertNotIn("R$ 750", self.h)
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
        self.assertNotIn("/planejador", fora)   # Planejador fora da InovaSTEM (dona, 20/11/2026); fora = sem os scripts
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
                # LEIA-ME do pacote: senha mínima e banco do próprio sistema (falha informada pela sessão do Instituto)
                leia = z.read(next(n for n in nomes if n.endswith("/LEIA-ME.md"))).decode("utf-8")
                self.assertIn(f"pelo menos {seg.SENHA_MIN} caracteres", leia)
                self.assertIn("`physis-inovastem.db`", leia)
                self.assertIn("/laboratorio", leia)
                for arq in ("three.min.js", "web-ifc-api-iife.js", "web-ifc.wasm", "LICENSE-three.txt"):   # Modelagem Physis 3D: /vendor/
                    self.assertTrue(any(n.endswith("/web/vendor/" + arq) for n in nomes), arq)
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


# ── Modelagem Physis 3D, estrutura aprovada pela dona em 20/11/2026 ──────────────────────────────────────────────
STL_1 = (b"\0" * 80) + (1).to_bytes(4, "little") + (b"\0" * 12) + b"".join(
    v.to_bytes(4, "little") for v in [0, 0, 0, 0x3F800000, 0, 0, 0, 0x3F800000, 0]) + b"\0\0"      # um triângulo


class FilaImpressao(unittest.TestCase):
    """Fila de impressão (physis_hub/inovastem.py): papéis, estados, recusa com motivo, registro sem dado pessoal."""

    def setUp(self):
        import base64
        from physis_hub import impressao3d as m3
        self.tmp = tempfile.TemporaryDirectory()
        self.h = Hub(org="ino-fila")
        self.i3d = m3.Impressao3D(self.h, Path(self.tmp.name) / "p3d", fatiador=m3.Fatiador(url=""))
        self.i = ino_mod.InovaSTEM(self.h, {}, impressao3d=lambda: self.i3d)      # como o servidor liga (função)
        self.ana = {"usuario": "ana@x.example", "papel": seg.CLIENTE}
        self.bia = {"usuario": "bia@x.example", "papel": seg.CLIENTE}
        self.peca = self.i3d.criar({"nome": "Suporte de vaso"}, self.ana)["id"]
        self.sem_arquivo = self.i3d.criar({"nome": "Sem arquivo"}, self.ana)["id"]
        r = self.i3d.revisar(self.peca, {"arquivo_b64": base64.b64encode(STL_1).decode(), "arquivo_nome": "vaso.stl", "nota": "primeira"}, self.ana)
        self.assertTrue(r["ok"], r)

    def tearDown(self):
        self.tmp.cleanup()

    def test_papeis_e_estados(self):
        self.assertEqual(self.i.pedir_impressao({"peca": self.peca}, self.bia).get("codigo"), 404, "rascunho de outra pessoa")
        self.assertFalse(self.i.pedir_impressao({"peca": self.sem_arquivo}, self.ana)["ok"])
        self.assertFalse(self.i.pedir_impressao({"peca": self.peca, "material": "ouro"}, self.ana)["ok"])
        self.assertEqual(self.i.pedir_impressao({"peca": self.peca}, None).get("codigo"), 401)
        r = self.i.pedir_impressao({"peca": self.peca, "material": "rpetg", "observacao": "para a horta"}, self.ana)
        self.assertEqual((r["ok"], r["estado"]), (True, "pendente"), r)
        pid = r["id"]
        # participante não vê a fila da equipe nem muda a situação
        self.assertEqual(self.i.fila_impressao(self.ana).get("codigo"), 403)
        self.assertEqual(self.i.mudar_impressao({"id": pid, "estado": "aprovada"}, self.ana).get("codigo"), 403)
        # a equipe segue os passos; pular passo é recusado (409)
        self.assertEqual(self.i.mudar_impressao({"id": pid, "estado": "pronta"}, EQUIPE).get("codigo"), 409)
        self.assertFalse(self.i.mudar_impressao({"id": pid, "estado": "voando"}, EQUIPE)["ok"])
        for e in ("aprovada", "imprimindo", "pronta"):
            self.assertEqual(self.i.mudar_impressao({"id": pid, "estado": e}, EQUIPE).get("estado"), e)
        self.assertEqual(self.i.mudar_impressao({"id": pid, "estado": "recusada", "motivo": "tarde"}, EQUIPE).get("codigo"), 409)
        self.assertEqual(self.i.mudar_impressao({"id": 999, "estado": "aprovada"}, EQUIPE).get("codigo"), 404)
        minhas = self.i.minhas_impressoes(self.ana)["itens"]
        self.assertEqual([(x["id"], x["estado"], x["peca_nome"]) for x in minhas], [(pid, "pronta", "Suporte de vaso")])
        self.assertEqual(self.i.minhas_impressoes(self.bia)["itens"], [], "cada um vê só os seus pedidos")
        # o arquivo é o da última revisão, baixado pela rota do Physis 3D (a equipe vê todas as peças)
        sha = minhas[0]["arquivo_sha256"]
        self.assertEqual(minhas[0]["arquivo_url"], "/api/3d/arquivo/" + sha)
        self.assertEqual(self.i3d.arquivo(sha, EQUIPE)[0], "vaso.stl")

    def test_recusa_com_motivo_e_peca_publicada(self):
        r = self.i.pedir_impressao({"peca": self.peca}, self.ana)
        self.assertFalse(self.i.mudar_impressao({"id": r["id"], "estado": "recusada"}, EQUIPE)["ok"], "recusa pede motivo")
        self.assertEqual(self.i.mudar_impressao({"id": r["id"], "estado": "recusada", "motivo": "peça maior que a mesa"}, EQUIPE)["estado"], "recusada")
        x = self.i.minhas_impressoes(self.ana)["itens"][0]
        self.assertEqual((x["estado"], x["motivo"], x["proximos"]), ("recusada", "peça maior que a mesa", []))
        # peça publicada (e não oculta): qualquer participante com conta pode pedir
        self.i3d.aderir("ana@x.example", {"nome_publico": "Ana", "consentimento": True})
        self.assertTrue(self.i3d.publicar(self.peca, {"licenca": "CC-BY-4.0", "consentimento": True}, self.ana)["ok"])
        self.assertTrue(self.i.pedir_impressao({"peca": self.peca}, self.bia)["ok"])

    def test_registro_e_fila_sem_dado_pessoal(self):
        r = self.i.pedir_impressao({"peca": self.peca, "observacao": "obs"}, self.ana)
        self.i.mudar_impressao({"id": r["id"], "estado": "recusada", "motivo": "sem filamento"}, EQUIPE)
        linhas = self.h._db.execute("SELECT origem, conteudo FROM registro WHERE tipo='inovastem'").fetchall()
        self.assertEqual(len(linhas), 2)
        texto = json.dumps(linhas, ensure_ascii=False)
        for pessoal in ("ana@x.example", "eq@x.example", "obs", "sem filamento"):
            self.assertNotIn(pessoal, texto)
        fila = self.i.fila_impressao(EQUIPE)
        self.assertEqual(len(fila["itens"]), 1)
        self.assertNotIn("ana@x.example", json.dumps(fila), "a equipe vê o nome público, nunca o e-mail")
        self.assertIn("nome_publico", fila["itens"][0])

    def test_esquemas_estritos(self):
        self.assertIn("ino_impressao", seg.ESQUEMAS)
        self.assertIsNone(seg.validar({"peca": 1, "material": "rpla", "observacao": "x"}, seg.ESQUEMAS["ino_impressao"]))
        self.assertIsNotNone(seg.validar({"peca": 1, "email": "a@b.example"}, seg.ESQUEMAS["ino_impressao"]))
        self.assertIsNotNone(seg.validar({"arquivo": "x" * 65}, seg.ESQUEMAS["ino_impressao"]))
        self.assertIsNotNone(seg.validar({"id": 1}, seg.ESQUEMAS["ino_impressao_estado"]))
        self.assertEqual(ino_mod.ESTADOS_IMPRESSAO, ("pendente", "aprovada", "imprimindo", "pronta", "recusada"))


class FilaArquivoDoLaboratorio(unittest.TestCase):
    """STL ou 3MF gerado no laboratório vai para a fila (21/11/2026): privado, tipo conferido pelos bytes, limite de 20 MB,
    registro sem dado pessoal; só quem pediu e a equipe baixam."""

    def setUp(self):
        from physis_hub import impressao3d as m3
        self.tmp = tempfile.TemporaryDirectory()
        self.h = Hub(org="ino-fila-lab")
        self.i = ino_mod.InovaSTEM(self.h, {}, impressao3d=lambda: None, pasta_impressao=Path(self.tmp.name) / "lab")
        self.ana = {"usuario": "ana@x.example", "papel": seg.CLIENTE}
        self.bia = {"usuario": "bia@x.example", "papel": seg.CLIENTE}
        self.stl = m3.escrever_stl([[[0, 0, 0], [10, 0, 0], [0, 10, 0]], [[0, 0, 0], [0, 10, 0], [0, 0, 10]]])

    def tearDown(self):
        self.tmp.cleanup()

    def test_tipo_pelos_bytes_e_limite(self):
        self.assertEqual(self.i.enviar_arquivo_impressao(self.stl, "peca.stl", None).get("codigo"), 401)
        self.assertFalse(self.i.enviar_arquivo_impressao(self.stl, "peca.obj", self.ana)["ok"], "a fila recebe STL ou 3MF")
        self.assertFalse(self.i.enviar_arquivo_impressao(b"nao e malha nenhuma", "peca.stl", self.ana)["ok"])
        self.assertFalse(self.i.enviar_arquivo_impressao(self.stl, "peca.3mf", self.ana)["ok"], "3MF tem de ser ZIP")
        self.assertEqual(self.i.enviar_arquivo_impressao(b"x" * (ino_mod.ARQ_IMPRESSAO_MAX + 1), "g.stl", self.ana).get("codigo"), 413)
        r = self.i.enviar_arquivo_impressao(self.stl, "../../peça 1.stl", self.ana)
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["formato"], r["triangulos"]), ("stl", 2))
        self.assertNotIn("/", r["nome"])
        self.assertTrue((Path(self.tmp.name) / "lab" / (r["arquivo"] + ".stl")).is_file())

    def test_pedido_privado_e_registro_sem_dado_pessoal(self):
        a = self.i.enviar_arquivo_impressao(self.stl, "suporte.stl", self.ana)
        self.assertEqual(self.i.pedir_impressao({"arquivo": a["arquivo"]}, self.bia).get("codigo"), 404, "arquivo de outra pessoa")
        r = self.i.pedir_impressao({"arquivo": a["arquivo"], "material": "rpla", "observacao": "obs pessoal"}, self.ana)
        self.assertEqual((r["ok"], r["estado"]), (True, "pendente"), r)
        x = self.i.minhas_impressoes(self.ana)["itens"][0]
        self.assertEqual((x["origem"], x["peca_nome"], x["arquivo_url"]), ("laboratorio", "suporte.stl", f"/api/inovastem/impressao/{r['id']}/arquivo"))
        self.assertEqual(self.i.baixar_arquivo_impressao(r["id"], self.ana)[2], self.stl)
        self.assertEqual(self.i.baixar_arquivo_impressao(r["id"], EQUIPE)[1], "model/stl")
        self.assertIsNone(self.i.baixar_arquivo_impressao(r["id"], self.bia))
        self.assertIsNone(self.i.baixar_arquivo_impressao(r["id"], None))
        self.assertEqual(self.i.mudar_impressao({"id": r["id"], "estado": "aprovada"}, EQUIPE)["estado"], "aprovada")
        texto = json.dumps(self.h._db.execute("SELECT origem, conteudo FROM registro WHERE tipo='inovastem'").fetchall(), ensure_ascii=False)
        for pessoal in ("ana@x.example", "suporte.stl", "obs pessoal", "eq@x.example"):
            self.assertNotIn(pessoal, texto)
        self.assertFalse(self.i.pedir_impressao({}, self.ana)["ok"], "sem peça nem arquivo")


class FilaImpressaoRotas(unittest.TestCase):
    """Rotas /api/inovastem/impressao*: só na instalação inovastem, sessão, papel e CSRF como as outras."""

    @classmethod
    def setUpClass(cls):
        cls.antes = {k: os.environ.get(k) for k in ("PHYSIS_3D_PASTA", "PHYSIS_LIMITE_ENTRAR", "PHYSIS_CONFIRMAR_EMAIL", "PHYSIS_IMPRESSAO_PASTA")}
        for k in cls.antes:
            os.environ.pop(k, None)
        os.environ["PHYSIS_LIMITE_ENTRAR"] = "0"
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["PHYSIS_3D_PASTA"] = str(Path(cls.tmp.name) / "3d")
        os.environ["PHYSIS_IMPRESSAO_PASTA"] = str(Path(cls.tmp.name) / "impressao_lab")     # nada de arquivo de teste no repositório
        cls.h = Hub(org="ino-fila-rotas")
        cls.srv = servidor.iniciar(cls.h, 0, endereco="127.0.0.1", instancia={
            "login": True, "cadastro_aberto": True, "moderacao_previa": True, "instalacao": "inovastem"})
        cls.porta = cls.srv.server_address[1]
        adm = cls.h.criar_conta("Direção", "dir@f.example", SENHA)
        cls.h.criar_conta("Participante", "par@f.example", SENHA, adm["id"], papel="cliente")
        cls.dir, cls.par = cls.sessao("dir@f.example"), cls.sessao("par@f.example")

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()
        for k, v in cls.antes.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v

    @classmethod
    def sessao(cls, usuario):
        tk = cls.h.entrar(usuario, SENHA)["token"]
        return ("physis_sessao=" + tk, seg.csrf_de(cls.h, tk))

    def pedir(self, metodo, rota, corpo=None, s=None, porta=None):
        return Rotas.pedir(self, metodo, rota, corpo, s, porta)

    def test_fluxo_com_sessao_papel_e_csrf(self):
        import base64
        st, r = self.pedir("POST", "/api/3d/pecas", {"nome": "Gancho", "material": ""}, self.par)
        self.assertEqual(st, 200, r)
        pid = r["id"]
        st, r = self.pedir("POST", f"/api/3d/pecas/{pid}/revisao", {"arquivo_b64": base64.b64encode(STL_1).decode(), "arquivo_nome": "g.stl"}, self.par)
        self.assertEqual(st, 200, r)
        # sem sessão: 401; campo fora do esquema: 400; CSRF errado: 403
        self.assertEqual(self.pedir("POST", "/api/inovastem/impressao", {"peca": pid})[0], 401)
        self.assertEqual(self.pedir("GET", "/api/inovastem/impressao/minhas")[0], 401)
        self.assertEqual(self.pedir("POST", "/api/inovastem/impressao", {"peca": pid, "extra": 1}, self.par)[0], 400)
        st, r = self.pedir("POST", "/api/inovastem/impressao", {"peca": pid}, (self.par[0], "csrf-errado"))
        self.assertEqual((st, r.get("csrf")), (403, True))
        st, r = self.pedir("POST", "/api/inovastem/impressao", {"peca": pid, "material": "rpla", "observacao": "teste"}, self.par)
        self.assertEqual((st, r.get("estado")), (200, "pendente"), r)
        iid = r["id"]
        st, m = self.pedir("GET", "/api/inovastem/impressao/minhas", s=self.par)
        self.assertIn(iid, [x["id"] for x in m["itens"]])
        # participante não é equipe
        self.assertEqual(self.pedir("GET", "/api/inovastem/impressao/fila", s=self.par)[0], 403)
        self.assertEqual(self.pedir("POST", "/api/inovastem/impressao/estado", {"id": iid, "estado": "aprovada"}, self.par)[0], 403)
        st, f = self.pedir("GET", "/api/inovastem/impressao/fila", s=self.dir)
        self.assertEqual(st, 200)
        self.assertIn(iid, [x["id"] for x in f["itens"]])
        self.assertNotIn("par@f.example", json.dumps(f))
        st, r = self.pedir("POST", "/api/inovastem/impressao/estado", {"id": iid, "estado": "imprimindo"}, self.dir)
        self.assertEqual(st, 409, r)
        st, r = self.pedir("POST", "/api/inovastem/impressao/estado", {"id": iid, "estado": "aprovada"}, self.dir)
        self.assertEqual((st, r.get("estado")), (200, "aprovada"), r)
        # o arquivo baixa pela rota do Physis 3D, com sessão (para abrir localmente no CrealityPrint ou no HALOT)
        item = next(x for x in f["itens"] if x["id"] == iid)
        req = urllib.request.Request(f"http://127.0.0.1:{self.porta}{item['arquivo_url']}", headers={"Cookie": self.dir[0]})
        with urllib.request.urlopen(req, timeout=30) as resp:
            self.assertEqual((resp.status, resp.read()), (200, STL_1))
            self.assertIn("attachment", resp.headers["Content-Disposition"])

    def test_arquivo_do_laboratorio_pela_rota(self):
        from physis_hub import impressao3d as m3
        stl = m3.escrever_stl([[[0, 0, 0], [10, 0, 0], [0, 10, 0]], [[0, 0, 0], [0, 10, 0], [0, 0, 10]]])

        def subir(dados, s=None, nome="peca.stl"):
            cab = {"Content-Type": "application/octet-stream", "X-Physis-Nome": urllib.request.quote(nome)}
            if s:
                cab.update({"Cookie": s[0], "X-Physis-CSRF": s[1]})
            req = urllib.request.Request(f"http://127.0.0.1:{self.porta}/api/inovastem/impressao/arquivo", data=dados, method="POST", headers=cab)
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read() or b"{}")
        self.assertEqual(subir(stl)[0], 401)
        self.assertEqual(subir(stl, (self.par[0], "csrf-errado"))[0], 403)
        self.assertEqual(subir(b"lixo", self.par)[0], 400)
        st, r = subir(stl, self.par, "minha peça.stl")
        self.assertEqual(st, 200, r)
        st, p = self.pedir("POST", "/api/inovastem/impressao", {"arquivo": r["arquivo"], "material": ""}, self.par)
        self.assertEqual((st, p.get("estado")), (200, "pendente"), p)
        req = urllib.request.Request(f"http://127.0.0.1:{self.porta}/api/inovastem/impressao/{p['id']}/arquivo", headers={"Cookie": self.dir[0]})
        with urllib.request.urlopen(req, timeout=30) as resp:
            self.assertEqual((resp.status, resp.read()), (200, stl))
            self.assertIn("attachment", resp.headers["Content-Disposition"])
        self.assertEqual(self.pedir("GET", f"/api/inovastem/impressao/{p['id']}/arquivo")[0], 401)

    def test_unsafe_eval_so_no_laboratorio(self):
        # web-ifc precisa de 'unsafe-eval' (21/11/2026): só em /laboratorio da instalação inovastem; o resto segue sem eval
        with urllib.request.urlopen(f"http://127.0.0.1:{self.porta}/laboratorio", timeout=30) as r:
            self.assertIn("'unsafe-eval'", r.headers["Content-Security-Policy"])
        with urllib.request.urlopen(f"http://127.0.0.1:{self.porta}/", timeout=30) as r:
            self.assertNotIn("'unsafe-eval'", r.headers["Content-Security-Policy"])
        with urllib.request.urlopen(f"http://127.0.0.1:{self.porta}/api/publico/inovastem", timeout=30) as r:
            self.assertNotIn("'unsafe-eval'", r.headers["Content-Security-Policy"])
        with urllib.request.urlopen(f"http://127.0.0.1:{self.porta}/vendor/web-ifc-api-iife.js", timeout=30) as r:
            self.assertEqual(r.status, 200)
        h = Hub(org="ino-csp-outra")
        srv = servidor.iniciar(h, 0, endereco="127.0.0.1", instancia={"login": True, "instalacao": "instituto"})
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/laboratorio")
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    csp = r.headers["Content-Security-Policy"]
            except urllib.error.HTTPError as e:
                csp = e.headers["Content-Security-Policy"]
            self.assertNotIn("'unsafe-eval'", csp)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_rotas_nao_existem_em_outra_instalacao(self):
        h = Hub(org="ino-fila-outra")
        srv = servidor.iniciar(h, 0, endereco="127.0.0.1", instancia={"login": True, "instalacao": "instituto"})
        try:
            porta = srv.server_address[1]
            self.assertEqual(self.pedir("GET", "/api/inovastem/impressao/minhas", porta=porta)[0], 404)
            self.assertEqual(self.pedir("POST", "/api/inovastem/impressao", {"peca": 1}, porta=porta)[0], 404)
        finally:
            srv.shutdown()
            srv.server_close()


class Modelagem3D(unittest.TestCase):
    """/laboratorio = Modelagem Physis 3D: 8 subabas, projeto comum, simulação por fenômeno, fila e galeria."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(RAIZ / "ferramentas"))
        import montar_lab_inovastem as lab
        cls.lab = lab
        cls.h = ler(AQUI / "web" / "inovastem-lab.html")
        cls.js = re.search(r'<script id="lab-inovastem">\n(.*?)</script>', cls.h, re.S).group(1)
        cls.fora = re.sub(r"<script.*?</script>", "", cls.h, flags=re.S)

    def test_oito_subabas_na_ordem_com_aria(self):
        # dona, 20 e 21/11/2026: "Enviar arquivo" primeiro; "Modelos BIM (CAD e IFC)" (chave edificacao) e logo depois
        # "Montagens"; "Escaneamento" saiu por enquanto
        ordem = ["arquivo", "lugar", "edificacao", "montagem", "pecas", "simulacao", "fila", "galeria"]
        self.assertEqual(dict(self.lab.SUBABAS)["edificacao"], "Modelos BIM (CAD e IFC)")
        self.assertNotRegex(self.fora, r"(?i)escaneamento|crealityscan|scanning", "Escaneamento fora por enquanto")
        self.assertNotRegex(re.search(r"\nconst T = \{\n(.*?)\n\};\n", self.js, re.S).group(1), r"(?i)escaneamento|crealityscan|scanning")
        self.assertIn('"escaneamento": "arquivo"', self.js, "o endereço antigo abre Enviar arquivo")
        self.assertEqual([k for k, _ in self.lab.SUBABAS], ordem)
        self.assertEqual(re.findall(r'<a role="tab" id="tab-([a-z]+)" href="#\1" aria-controls="lab"', self.fora), ordem)
        self.assertEqual(self.fora.count('role="tablist"'), 1)
        self.assertIn('id="lab" role="tabpanel"', self.fora)
        self.assertEqual(self.fora.count('aria-selected="true"'), 1)
        for k in ordem:
            self.assertRegex(self.js, rf"\b{k}: tela[A-Za-z]+", k)
        self.assertIn('"3d": "pecas"', self.js, "endereço antigo #3d abre Peças 3D")
        for tecla in ("ArrowRight", "ArrowLeft", "Home", "End"):
            self.assertIn(tecla, self.js)
        self.assertEqual(self.h, self.lab.montar(), "rode: python ferramentas/montar_lab_inovastem.py")

    def test_projeto_comum(self):
        self.assertIn('ESQ_PROJETO = "inovastem-projeto/1"', self.js)
        self.assertIn("lugar: null, edificacao: null, montagem: null, pecas: [], resultados: [], arquivos: [], passos: []", self.js)
        # localStorage só com try/catch; exportar e importar arquivo
        for linha in self.js.splitlines():
            if "localStorage." in linha:
                self.assertIn("try", linha, linha.strip())
        for k in ("proj-exportar", "proj-importar", "Exportar o projeto", "Importar um projeto", 'id="lab-proj"', "indexedDB.open("):
            self.assertIn(k, self.h, k)
        # o contrato do lugar é o do Mapeamento
        from physis_hub import mapeamento
        self.assertIn(f'ESQ_LUGAR = "{mapeamento.ESQUEMA_GEOMETRIA}"', self.js)
        self.assertIn('localStorage.getItem("physis-geometria-lugar")', self.js)
        self.assertNotIn("/api/mapeamento/ifc/ler", self.js, "o IFC agora abre no navegador (web-ifc), sem servidor")

    def test_simulacao_um_bloco_por_fenomeno_pelo_motor(self):
        nomes = re.findall(r'\{ id: "([a-z]+)", prefixos: \[([^\]]+)\], pt: \{ nome: "([^"]+)"', self.js)
        self.assertEqual([n for _, _, n in nomes], ["Calor", "Estrutura", "Ventilação e vento", "Terreno e água", "Incerteza", "Biogás", "Otimização QUBO"])
        self.assertEqual(len(re.findall(r"\ben: \{ nome: ", self.js)), 7, "cada fenômeno em inglês")
        casos = json.loads(ler(RAIZ / "sistema" / "simulacao-exemplos" / "casos.json"))["casos"]
        for fid, pref, _ in nomes:
            p = re.findall(r'"([a-z]+\.)"', pref)
            self.assertTrue(any(c.get("exemplo") and any(c["solver"].startswith(x) for x in p) for c in casos), fid)
        for k in ("O que faz", "Entradas", "O que sai", "Limites de validade", "Guardar no projeto"):
            self.assertIn(k, self.js, k)
        motor = ler(RAIZ / "sistema" / "physis-simulacao.js")
        for f in ("rodarCaso", "desenhoCaso"):
            self.assertIn(f"SIMULACAO.{f}(", self.js)
            self.assertIn(f"{f}: {f}", motor, f"o motor exporta {f}")
        self.assertIn("SIMULACAO.terreno.gradeDaGeometria(proj.lugar.dados)", self.js)
        self.assertIn("telaPhysis3D()", self.js)

    def test_fila_e_galeria(self):
        for rota in ("/api/inovastem/impressao/minhas", "/api/inovastem/impressao/fila", "/api/inovastem/impressao/estado",
                     '"/api/inovastem/impressao"', "/api/publico/3d/pecas", "/api/publico/3d/arquivo/", "/api/3d/pecas", "X-Physis-CSRF"):
            self.assertIn(rota, self.js, rota)
        for k in ("CrealityPrint", "HALOT", "Nada é instalado nem chamado pelo navegador", "[MARCADOR: modelos exatos das impressoras]",
                  "Todos os direitos reservados", "moderação", "STL", "OBJ", "/api/inovastem/impressao/arquivo", "X-Physis-Nome"):
            self.assertIn(k, self.js, k)
        from physis_hub import impressao3d as m3
        for cod, nome in m3.LICENCAS.items():          # só licenças abertas (decisão da dona)
            self.assertRegex(cod, r"^(CC|CERN-OHL)")
            self.assertNotRegex(nome.lower(), r"reservad|proprietár")

    def test_regras_da_tela(self):
        self.assertEqual(len(re.findall(r"<h1\b", self.fora)), 1)
        self.assertNotRegex(self.js, r"<h1[\s>]", "a casca não escreve h1 (o único é o logo)")
        self.assertNotRegex(self.js, r"\beval\(|new Function\(")
        self.assertNotRegex(self.js.replace("http://www.w3.org/2000/svg", ""), r"https?://", "só o nome do formato SVG (namespace)")
        self.assertNotRegex(self.fora, r'(?i)(src|href)\s*=\s*"https?://')
        css = re.search(r"<style>\n(.*?)</style>", self.h, re.S).group(1)
        casca = self.lab.CASCA_CSS
        self.assertEqual(re.findall(r"#[0-9A-Fa-f]{6}", casca), [], "a casca só usa as variáveis do guia")
        self.assertIn(casca, css)
        self.assertNotRegex(re.sub(r"const CORES = .*", "", self.js), r"#[0-9A-Fa-f]{6}\b", "nenhuma cor nova na casca")
        corpo = re.sub(r"<script.*?</script>", "", self.h, flags=re.S)
        ids = re.findall(r'\bid="([^"$]+)"', corpo)
        self.assertEqual(len(ids), len(set(ids)), ids)
        self.assertNotIn("Modelagem online", self.h)

    def test_portugues_e_ingles(self):
        """Toda chave usada com t("…") existe em T.pt e em T.en; as duas línguas têm as mesmas chaves (auditoria de 21/11/2026)."""
        bloco = re.search(r"\nconst T = \{\n(.*?)\n\};\n", self.js, re.S).group(1)
        pt, en = bloco.split("\n  en: {", 1)
        cpt, cen = _chaves(pt) - {"pt"}, _chaves(en)
        self.assertEqual(cpt, cen, "PT e EN com as mesmas chaves")
        usadas = set(re.findall(r'\bt\("([a-z0-9_]+)"\)', self.js))
        self.assertTrue(len(usadas) > 150, len(usadas))
        for k in usadas:
            self.assertRegex(pt, rf"(?<![a-z0-9_]){k}:", "falta em PT: " + k)
            self.assertRegex(en, rf"(?<![a-z0-9_]){k}:", "falta em EN: " + k)
        for k in ("fluxo", "fi_como", "si_cols", "fi_cols", "mo_prog_cols"):
            self.assertEqual(_n_itens(pt.replace(": [", ":["), k), _n_itens(en.replace(": [", ":["), k), k)
        # vocabulário do inglês do site; Delas em inglês é "Hers"
        for termo in ('nav_delas: "InovaSTEM Hers"', 'nav_desafios: "Challenges and projects"', 'nav_forum: "Forum"', 'nav_modelagem: "Physis 3D modelling"',
                      'nav_materiais: "Materials"', 'inscreva: "Join"'):
            self.assertIn(termo, en, termo)
        # o HTML fixo (menu, pular, rodapé, subabas) troca de língua ao vivo
        for k in ("pular", "endosso_a", "nav_delas", "nav_desafios", "nav_forum", "nav_modelagem", "nav_materiais", "inscreva", "rodape_beta", "faixa", "intro"):
            self.assertIn(f'data-t="{k}"', self.fora, k)
        self.assertIn('idioma:{ atual:() => lang, definir:v =>', self.h)
        self.assertIn('document.documentElement.lang = lang === "en" ? "en" : "pt-BR"', self.js)
        site = ler(PAGINA)
        for termo in ('delas:"InovaSTEM Hers"', 'desafios:"Challenges and projects"', 'forum:"Forum"', 'modelagem:"Physis 3D modelling"', 'materiais:"Materials"', 'participar:"Join"'):
            self.assertIn(termo, site, "o site usa o mesmo inglês: " + termo)

    def test_modelos_bim_e_montagens(self):
        mod = ler(RAIZ / "sistema" / "physis-modelagem.js").replace("\r\n", "\n")
        self.assertIn(("lab-modelagem", RAIZ / "sistema" / "physis-modelagem.js"), self.lab.BLOCOS)
        self.assertEqual(re.search(r'<script id="lab-modelagem">\n(.*?)</script>', self.h, re.S).group(1), mod)
        # bibliotecas só de /vendor/ (three.js MIT, web-ifc MPL-2.0); nada de fora, sem eval próprio
        self.assertEqual(set(re.findall(r'"(/vendor/[^"]*)"', mod)), {"/vendor/three.min.js", "/vendor/web-ifc-api-iife.js", "/vendor/"})
        self.assertNotRegex(mod.replace("http://www.w3.org/2000/svg", ""), r"https?://")
        self.assertNotRegex(mod, r"\beval\(|new Function\(|fetch\(")
        for arq in self.lab.VENDOR_LAB:
            self.assertTrue((RAIZ / "vendor" / arq).is_file(), arq)
        self.assertIn("web-ifc-api-iife.js", ler(RAIZ / "vendor" / "LEIA-ME.md"))
        for k in ("StreamAllMeshes", "GetVertexArray", "IFCRELCONTAINEDINSPATIALSTRUCTURE", "GetNameFromTypeCode", "SetWasmPath"):
            self.assertIn(k, mod, k)
        # ferramentas no estilo do SketchUp, com ícones SVG próprios e nome visível
        for f in ("selecionar", "mover", "girar", "escalar", "puxar", "linha", "retangulo", "circulo", "medir"):
            self.assertIn(f'"{f}"', mod, f)
        icones = re.search(r"const ICONES = \{(.*?)\};", self.js, re.S).group(1)
        for f in ("selecionar", "mover", "girar", "escalar", "puxar", "linha", "retangulo", "circulo", "medir", "desfazer", "refazer", "enquadrar"):
            self.assertRegex(icones, rf"\b{f}: '<", f)
        self.assertIn('role="toolbar"', self.js)
        self.assertIn('aria-hidden="true" focusable="false"', self.js)
        for k in ("Ctrl+Z", "Shift", "Delete", "ArrowLeft", "aria-pressed"):
            self.assertIn(k, self.js + mod, k)
        # formas paramétricas e formatos abertos
        for k in ("caixa", "cilindro", "chapa", "perfil"):
            self.assertIn(f"{k}:", re.search(r"prim: \{([^}]*)\}", self.js).group(1), k)
        for k in ("escreverIfc(", "escrever3MFMontagem(", "dxfTexto()", "svgTexto()", "PHYSIS3D.escrever3MF(", "PHYSIS3D.escreverSTL("):
            self.assertIn(k, self.js, k)
        self.assertIn("STEP e IGES precisam de OpenCascade", self.js)
        self.assertIn("Gravar de volta no IFC original", self.js, "dito com clareza: salvar no IFC original é próxima etapa")
        # Montagens: colisão por caixas e os programas mapeados nos documentos (o que falta é [MARCADOR])
        self.assertIn("PhysisImagem3D.colisoes(", self.js)
        progs = re.findall(r'^  \["([A-Za-z]+)", \[', re.search(r"const PROGRAMAS = \[(.*?)\]\]\];", self.js, re.S).group(1), re.M)
        self.assertEqual(progs, ["FreeCAD", "CadQuery", "OpenSCAD", "Gmsh", "CalculiX", "OpenFOAM", "FEniCSx", "PrusaSlicer"])
        for lic in ("LGPL-2.1", "Apache-2.0", "GPL-2.0+", "GPL-3.0", "LGPL-3.0", "AGPL-3.0"):
            self.assertIn(lic, self.js, lic)
        self.assertIn("Fase 2, em servidor: em desenvolvimento", self.js)

    def test_todo_caminho_termina_na_fila(self):
        # Enviar arquivo, Modelos BIM, Montagens, Peças 3D e as peças de teste levam o STL/3MF gerado para a fila
        self.assertIn("function pedirImpressaoDe(", self.js)
        for origem in ('"arq-imp"', '"arq-malha-imp"', "pre === \"mo\") pedirImpressaoDe(", 'else pedirImpressaoDe(nome + ".stl", stlDe(T, nome), t("abas").edificacao)',
                       '"peca-imp"', '"teste-imp"'):
            self.assertIn(origem, self.js, origem)
        self.assertGreaterEqual(self.js.count('t("pedir_impressao")'), 5)
        self.assertIn('postBytes("/api/inovastem/impressao/arquivo"', self.js)

    def test_site_mostra_as_subabas(self):
        site = ler(PAGINA)
        js = re.search(r'<script id="site-inovastem">\n(.*?)</script>', site, re.S).group(1)
        bloco = re.search(r"const T = \{(.*?)\n\};", js, re.S).group(1)
        pt, en = bloco.split("\n  en: {", 1)
        for lingua in (pt, en):
            linhas = re.search(r"mod_linhas:\[(.*?)\]\],", lingua, re.S).group(1)
            self.assertEqual(re.findall(r'\["([a-z]+)",', linhas), [k for k, _ in self.lab.SUBABAS])
        self.assertIn('modelagem:"Modelagem Physis 3D"', pt)
        self.assertIn('href="/laboratorio#${esc(l[0])}"', js)
        self.assertNotIn("Modelagem online", site)


class EnviarArquivoEImagem3D(unittest.TestCase):
    """Subaba "Enviar arquivo" e sistema/physis-imagem-3d.js (acréscimos da dona em 20/11/2026). O autoteste do módulo roda no
    navegador (PhysisImagem3D.autoteste(): máscara, contornos, DXF, SVG, relevo fechado com volume conferido, peças de teste)."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(RAIZ / "ferramentas"))
        import montar_lab_inovastem as lab
        cls.lab = lab
        cls.mod = ler(RAIZ / "sistema" / "physis-imagem-3d.js").replace("\r\n", "\n")
        cls.h = ler(AQUI / "web" / "inovastem-lab.html")
        cls.js = re.search(r'<script id="lab-inovastem">\n(.*?)</script>', cls.h, re.S).group(1)

    def test_modulo_copiado_igual_e_sem_mudar_o_motor(self):
        self.assertIn(("lab-imagem3d", RAIZ / "sistema" / "physis-imagem-3d.js"), self.lab.BLOCOS)
        m = re.search(r'<script id="lab-imagem3d">\n(.*?)</script>', self.h, re.S)
        self.assertEqual(m.group(1), self.mod)
        self.assertLess(self.h.index('id="lab-3d"'), self.h.index('id="lab-imagem3d"'), "o módulo vem depois do motor do Physis 3D")
        self.assertNotRegex(self.mod, r"window\.PHYSIS3D\s*=|PHYSIS3D\.[A-Za-z]+\s*=[^=]", "não troca nada do motor")
        self.assertNotRegex(self.mod, r"\beval\(|new Function\(|fetch\(|XMLHttpRequest")
        self.assertNotRegex(re.sub(r"http://(www\.w3\.org|schemas\.[a-z.]+)/[A-Za-z0-9/._-]*", "", self.mod), r"https?://", "só nomes de formato (namespaces XML)")
        for f in ("mascara", "contornos", "svg", "dxf", "relevo", "testes", "autoteste"):
            self.assertRegex(self.mod, r"window\.PhysisImagem3D = \{[^}]*\b" + f + r"\b", f)
        self.assertIn("P.escreverSTL(", self.mod)

    def test_pecas_de_teste_proprias(self):
        ids = re.findall(r'id: "([a-z0-9-]+)", nome: "', self.mod)
        self.assertEqual(ids, ["cubo-calibracao-20mm", "teste-balanco-30-45-60", "teste-ponte-10-20-30mm", "teste-espessura-parede"])
        self.assertEqual(self.mod.count("observar:"), 8, "português e inglês")
        self.assertNotRegex(self.mod.lower(), r"benchy|3dbenchy|thingiverse|printables")
        for k in ("teste-baixar", "teste-abrir", "Arquivos de teste para impressão", "Baixar STL"):
            self.assertIn(k, self.js, k)

    def test_enviar_arquivo_fluxo_e_passos(self):
        for k in ("PhysisImagem3D.svg(", "PhysisImagem3D.dxf(", "PHYSIS3D.escreverSTL(", "PHYSIS3D.escrever3MF(", "I.relevo(pf.M,", "window.PhysisImagem3D",
                  "I.processarFoto(", "I.contornos(pf.M", 'getElementById("p3d-arquivo")', "new DataTransfer()", "getPointAtLength",
                  "Sem uma biblioteca de fora", "[MARCADOR: decidir a leitura de PDF]", "data-lab-par", "lab-lado"):
            self.assertIn(k, self.js, k)
        # SVG: só formas e atributos de geometria (nada de script, evento ou link)
        atrib = re.search(r"const SVG_ATRIBUTOS = \[(.*?)\];", self.js).group(1)
        self.assertNotRegex(atrib, r'"on|href|style')
        self.assertIn('arquivos: [], passos: []', self.js)
        fluxo = re.findall(r'\["([a-z]+)", "[^"]+", "[^"]*"', re.search(r'fluxo: \[(.*?)\]\],', self.js, re.S).group(1))
        self.assertEqual(fluxo, ["arquivo", "lugar", "montagem", "pecas", "simulacao", "fila", "galeria"])
        # foto → CAD 2D → 3D: escala de cinza, suavização, Otsu com ajuste manual, ruído e fundo; contorno + Douglas-Peucker
        for f in ("function cinza(", "function suavizar(", "function otsu(", "function limpar(", "function processarFoto(", "function contornos(", "function dp("):
            self.assertIn(f, self.mod, f)
        self.assertIn("foto: fica só a peça (ruído e fundo da borda tirados)", self.mod, "autoteste com foto sintética")
        for k in ("ar-auto", "ar-suav", "ar-ruido", "ar-fundo", "ar-largura", "ar-altura"):
            self.assertIn(k, self.js, k)
        for passo in ("arquivo", "lugar", "edificacao", "montagem", "pecas", "simulacao", "fila", "galeria"):
            self.assertIn(f'registrarPasso("{passo}"', self.js, passo)
        self.assertIn("qualquer assunto", self.h)
        # Planejador fora da InovaSTEM (dona, 20/11/2026: relacionadas, mas separadas)
        fora = re.sub(r'<script id="(?:physis-preferencias|lab-[a-z0-9]+)">.*?</script>', "", self.h, flags=re.S)
        self.assertNotIn("/planejador", fora)
        self.assertNotRegex(fora, r"Planejador|Planner")




class DesenhoTecnicoNaTela(unittest.TestCase):
    """A tela do modo desenho técnico (Enviar arquivo): recorte, escala pela cota, eixo, centro, tipos dos contornos, operações,
    "Voltar ao modo foto", Fase 2 marcada e as funções do módulo que ela usa."""

    @classmethod
    def setUpClass(cls):
        cls.h = ler(AQUI / "web" / "inovastem-lab.html")
        cls.js = re.search(r'<script id="lab-inovastem">\n(.*?)</script>', cls.h, re.S).group(1)
        cls.mod = ler(RAIZ / "sistema" / "physis-imagem-3d.js")

    def test_funcoes_do_modulo(self):
        for f in ("lerDesenho", "afinar", "tracarEsqueleto", "ajustarCirculo", "primitivas", "lacosDaRegiao", "revolver", "padraoCircular", "corpos", "folhaSintetica"):
            self.assertRegex(self.mod, rf"function {f}\(", f)
            self.assertRegex(re.search(r"\nwindow\.PhysisImagem3D = \{(.*?)\};", self.mod, re.S).group(1), rf"\b{f}\b", f)
        self.assertIn("Zhang", self.mod)
        self.assertIn("Kåsa", self.mod)

    def test_tela(self):
        for k in ("I.lerDesenho(", "I.revolver(", "I.padraoCircular(", "I.lacosDaRegiao(", "data-lab-tipo", 'data-lab="dt-modo"', '["foto", "desenho"].map(k =>',
                  'id="ar-marcas"', '"dt-clique"', '"dt-inteira"', "dt-cmm", "dt-op", "dt-seg", "dt-padrao", "dt-lado", "dt-texto", "dt-hachura", "pointerdown"):
            self.assertIn(k, self.js, k)
        self.assertRegex(self.js, r'dt_marcar: \{ recorte: "[^"]+", cota: "[^"]+", eixo: "[^"]+", centro: "[^"]+" \}')
        for campo in ("dt-rx", "dt-ry", "dt-rw", "dt-rh", "dt-c1x", "dt-c2y", "dt-e1x", "dt-e2y", "dt-ox", "dt-oy"):
            self.assertIn(campo, self.js, campo)
        self.assertIn("Voltar ao modo foto", self.js)
        self.assertIn("Back to photo mode", self.js)
        self.assertIn("COLMAP", self.js)
        self.assertIn("TripoSR", self.js)
        self.assertRegex(self.js, r"dt_fase2: \"[^\"]*\[MARCADOR\]")
        css = re.search(r"<style>\n(.*?)</style>", self.h, re.S).group(1)
        for c in (".dt-perfil", ".dt-furo", ".dt-ignorado", ".dt-padrao", ".lab-marcas.ativo"):
            self.assertIn(c, css, c)


def _navegador():
    """Edge, Chrome ou Chromium para rodar o autoteste do módulo no navegador, sem tela (PHYSIS_NAVEGADOR troca)."""
    import shutil
    cands = [os.environ.get("PHYSIS_NAVEGADOR", ""), r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
             r"C:\Program Files\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Google\Chrome\Application\chrome.exe"]
    cands += [shutil.which(n) or "" for n in ("msedge", "google-chrome", "chromium", "chromium-browser", "chrome")]
    return next((c for c in cands if c and Path(c).is_file()), None)


class DesenhoTecnicoNoNavegador(unittest.TestCase):
    """Modo desenho técnico (dona, 21/11/2026): roda PhysisImagem3D.autoteste() num navegador sem tela, com o motor do Physis 3D.
    Folha sintética com a meia-seção de uma bucha de cotas conhecidas → revolução fechada a ±2 % do volume analítico;
    texto, cotas e quadro de notas não viram contorno; padrão circular de 6 → 6 corpos."""

    @classmethod
    def setUpClass(cls):
        import html
        import subprocess
        nav = _navegador()
        if not nav:
            raise unittest.SkipTest("sem Edge, Chrome ou Chromium nesta máquina")
        cls.tmp = tempfile.TemporaryDirectory()
        pagina = Path(cls.tmp.name) / "autoteste.html"
        sis = RAIZ / "sistema"
        pagina.write_text('<!doctype html><html><head><meta charset="utf-8"></head><body><pre id="r">rodando</pre><script>'
                          + ler(sis / "physis-3d.js") + "</script><script>" + ler(sis / "physis-imagem-3d.js") + "</script><script>"
                          + 'try{document.getElementById("r").textContent="RES:"+JSON.stringify(PhysisImagem3D.autoteste());}'
                          + 'catch(e){document.getElementById("r").textContent="ERRO:"+e.message;}</script></body></html>', encoding="utf-8")
        cmd = [nav, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", f"--user-data-dir={Path(cls.tmp.name) / 'perfil'}",
               "--virtual-time-budget=30000", "--dump-dom", pagina.resolve().as_uri()]
        try:
            saida = subprocess.run(cmd, capture_output=True, timeout=180).stdout.decode("utf-8", errors="replace")
        except (OSError, subprocess.TimeoutExpired) as e:
            raise unittest.SkipTest(f"o navegador não rodou: {e}")
        m = re.search(r'<pre id="r">(.*?)</pre>', saida, re.S)
        texto = html.unescape(m.group(1)) if m else ""
        if not texto.startswith("RES:"):
            raise AssertionError("autoteste não rodou: " + texto[:300])
        cls.res = json.loads(texto[4:])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def item(self, trecho):
        x = [r for r in self.res if trecho in r["nome"]]
        self.assertTrue(x, "falta o item do autoteste: " + trecho)
        return x[0]

    def test_tudo_passa(self):
        falhas = [f'{r["nome"]}: {r["info"]}' for r in self.res if not r["ok"]]
        self.assertEqual(falhas, [])

    def test_revolucao_da_meia_secao_a_2_por_cento(self):
        r = self.item("volume a ±2 % do analítico")
        self.assertTrue(r["ok"], r["info"])
        self.assertTrue(self.item("revolução da meia-seção: malha fechada")["ok"])

    def test_texto_e_cotas_nao_viram_contorno(self):
        for k in ("texto, cotas e quadro de notas não viram corpo", "na folha inteira, notas e cotas ficam de fora", "a hachura é lida como hachura"):
            self.assertTrue(self.item(k)["ok"], k)

    def test_padrao_circular_de_6(self):
        self.assertTrue(self.item("padrão circular de 6: 6 corpos")["ok"])



VARREDURA_EN = r"""
(async function () {
  const espera = ms => new Promise(r => setTimeout(r, ms));
  const PT = /[ãõáéíóúâêôçàÃÕÁÉÍÓÚÂÊÔÇÀ]|\b(não|você|para|com|peça|peças|simulação|uma|das|dos|ou|que|sem|até|mais|ainda|são|está|pelo|pela|nas|nos|cada|entre|sobre|depois|antes|também|aqui|isso|este|esta)\b/i;
  const LIVRE = /\[(MARCADOR|CONFERIR)[^\]]*\]|Petrópolis|Português|InovaSTEM|PHYSIS|Physis|Kåsa|Zhang|Suen|Ø|°|×|²|³|·|—|–|…|→/g;
  const sobra = {};
  const olhar = (onde) => { const linhas = (document.getElementById("conteudo").innerText || "").split("\n").map(x => x.trim()).filter(Boolean);
    linhas.forEach(l => { if (/^[{\[]"/.test(l)) return;   /* dado bruto em JSON (detalhes do cálculo) não é texto de tela */
    const s = l.replace(LIVRE, " "); if (PT.test(s)) (sobra[onde] = sobra[onde] || new Set()).add(l.slice(0, 200)); }); };
  try {
    await espera(300);
    for (const k of SUBABAS.map(s => s[0])) {
      irPara(k); await espera(250); olhar(k);
      if (k === "pecas") {
        const x = document.getElementById("p3d-arquivo"), dt = new DataTransfer();
        dt.items.add(new File([PHYSIS3D.escreverSTL(PHYSIS3D.cubo(20), "cubo")], "cubo.stl")); x.files = dt.files; x.dispatchEvent(new Event("change", { bubbles: true }));
        await espera(600); olhar("pecas/modelo");
        for (const sub of ["fatiar", "biblioteca", "forum", "metodo"]) { ui.p3dSub = sub; desenhar(); await espera(400); olhar("pecas/" + sub); }
        ui.p3dSub = "modelo"; desenhar();
      }
      if (k === "simulacao") {
        // todos os casos de cada fenômeno (35), não só o primeiro: escolhe no seletor, roda e olha
        for (const sid of Array.from(document.querySelectorAll("[data-lab-sel]")).map(s => s.id)) {
          const vals = Array.from(document.getElementById(sid).options).map(o => o.value);
          for (const v of vals) {
            const s = document.getElementById(sid); s.value = v; s.dispatchEvent(new Event("change", { bubbles: true })); await espera(120);
            const b = document.getElementById(sid.replace("sim-sel-", "sim-rodar-")); if (b) { b.click(); await espera(200); }
            olhar("simulacao/" + v);
          }
        }
      }
    }
    const out = {}; Object.keys(sobra).forEach(k => { out[k] = Array.from(sobra[k]); });
    document.getElementById("r-en").textContent = "RES:" + JSON.stringify(out);
  } catch (e) { document.getElementById("r-en").textContent = "ERRO:" + (e && e.stack || e); }
})();
"""


class InglesNoNavegador(unittest.TestCase):
    """Com o idioma English, nenhuma subaba do laboratório pode mostrar texto em português (dona, 21/11/2026): percorre as
    8 subabas num navegador sem tela, abre um cubo em Peças 3D (com as 5 partes do Physis 3D) e roda um exemplo de cada
    fenômeno da Simulação. Exceções: nomes próprios e [MARCADOR]/[CONFERIR]."""

    @classmethod
    def setUpClass(cls):
        import html
        import subprocess
        nav = _navegador()
        if not nav:
            raise unittest.SkipTest("sem Edge, Chrome ou Chromium nesta máquina")
        cls.tmp = tempfile.TemporaryDirectory()
        pagina = Path(cls.tmp.name) / "lab-en.html"
        h = ler(AQUI / "web" / "inovastem-lab.html")
        h = h.replace("<head>", '<head><script>try{localStorage.setItem("physis-idioma","en");}catch(e){}</script>', 1)
        h = h.replace("</body>", '<pre id="r-en">rodando</pre><script>' + VARREDURA_EN + "</script></body>", 1)
        pagina.write_text(h, encoding="utf-8")
        cmd = [nav, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", f"--user-data-dir={Path(cls.tmp.name) / 'perfil'}",
               "--virtual-time-budget=60000", "--dump-dom", pagina.resolve().as_uri()]
        try:
            saida = subprocess.run(cmd, capture_output=True, timeout=240).stdout.decode("utf-8", errors="replace")
        except (OSError, subprocess.TimeoutExpired) as e:
            raise unittest.SkipTest(f"o navegador não rodou: {e}")
        m = re.search(r'<pre id="r-en">(.*?)</pre>', saida, re.S)
        texto = html.unescape(m.group(1)) if m else ""
        if not texto.startswith("RES:"):
            raise AssertionError("a varredura não rodou: " + texto[:500])
        cls.sobra = json.loads(texto[4:])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_nada_em_portugues(self):
        self.assertEqual(self.sobra, {}, json.dumps(self.sobra, ensure_ascii=False, indent=1)[:6000])


BAIXA_RES = r"""
(async function () {
  const espera = ms => new Promise(r => setTimeout(r, ms)), out = {};
  try {
    for (const pxmm of [6, 3]) {
      const F = PhysisImagem3D.folhaSintetica(document, pxmm);
      // a folha entra como canvas (fonte de imagem válida para o drawImage), sem esperar decodificar arquivo
      lab.arq = { nome: "folha-" + pxmm + ".png", base: "folha", tipo: "image/png", tamanho: 0, fonte: "imagem", par: Object.assign({}, PAR_PADRAO), r: null, tipos: {},
                  img: F.cv, w: F.cv.width, h: F.cv.height };
      const P = lab.arq.par, ex = F.eixoPx.p[0], ey = (F.eixoPx.p[1] + F.eixoPx.q[1]) / 2;
      P.modo = "desenho"; P.recorte = F.recorte; P.operacao = "revolucionar"; P.lado = "auto";
      P.eixo = { p: F.eixoPx.p, q: F.eixoPx.q }; P.cota = { p: [ex, ey], q: [ex + F.bucha.rf * F.pxmm, ey], mm: F.bucha.rf };
      processarArquivo();
      const r = lab.arq.r;
      out[pxmm] = r && r.med ? { volume: r.med.volume_mm3, esperado: F.volume, ampliada: r.ampliada } : { erro: r && r.erro };
    }
    document.getElementById("r-br").textContent = "RES:" + JSON.stringify(out);
  } catch (e) { document.getElementById("r-br").textContent = "ERRO:" + (e && e.stack || e); }
})();
"""


class DesenhoBaixaResolucao(unittest.TestCase):
    """Folha sintética a 3 px/mm (metade da resolução): o laboratório amplia o recorte antes de ler e a revolução fica
    dentro de ±3 % do volume analítico; a 6 px/mm continua dentro de ±2 % (dona, 21/11/2026)."""

    @classmethod
    def setUpClass(cls):
        import html
        import subprocess
        nav = _navegador()
        if not nav:
            raise unittest.SkipTest("sem Edge, Chrome ou Chromium nesta máquina")
        cls.tmp = tempfile.TemporaryDirectory()
        pagina = Path(cls.tmp.name) / "lab-br.html"
        h = ler(AQUI / "web" / "inovastem-lab.html").replace("</body>", '<pre id="r-br">rodando</pre><script>' + BAIXA_RES + "</script></body>", 1)
        pagina.write_text(h, encoding="utf-8")
        cmd = [nav, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", f"--user-data-dir={Path(cls.tmp.name) / 'perfil'}",
               "--virtual-time-budget=60000", "--dump-dom", pagina.resolve().as_uri()]
        try:
            saida = subprocess.run(cmd, capture_output=True, timeout=240).stdout.decode("utf-8", errors="replace")
        except (OSError, subprocess.TimeoutExpired) as e:
            raise unittest.SkipTest(f"o navegador não rodou: {e}")
        m = re.search(r'<pre id="r-br">(.*?)</pre>', saida, re.S)
        texto = html.unescape(m.group(1)) if m else ""
        if not texto.startswith("RES:"):
            raise AssertionError("o teste não rodou: " + texto[:500])
        cls.res = json.loads(texto[4:])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def erro(self, pxmm):
        r = self.res[str(pxmm)]
        self.assertNotIn("erro", r, r)
        return abs(r["volume"] - r["esperado"]) / r["esperado"]

    def test_resolucao_normal(self):
        self.assertLess(self.erro(6), 0.02, self.res)

    def test_baixa_resolucao_amplia_e_acerta(self):
        self.assertGreater(self.res["3"]["ampliada"], 1, self.res)
        self.assertLess(self.erro(3), 0.03, self.res)


if __name__ == "__main__":
    unittest.main()
