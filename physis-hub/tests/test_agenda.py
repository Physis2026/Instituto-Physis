"""Agenda de eventos e oportunidades do Instituto (physis_hub/agenda.py; etapa 3 de 19/11/2026).

Protege:
1. Classificação nos quatro tipos mapeados (hackathons de segurança e quântica; modelos virtuais e gêmeo digital;
   feiras e outras redes; desafios e chamadas); o que não é de nenhum fica de fora.
2. Equipe publica direto; participante sugere e só aparece depois da moderação (fila única da comunidade).
3. Coletor de eventos: só entram os itens dos quatro tipos, como sugeridos; o mesmo item não entra duas vezes;
   sem data ou sem link https, fica vazio (nada inventado).
4. Leitura pública: só publicados e que ainda não terminaram; link só https; data AAAA-MM-DD.
5. Pelo servidor: rotas públicas, de participante e de equipe, com o papel certo.
"""
import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from physis_hub import agenda as ag
from physis_hub import comunidade as cm
from physis_hub import seguranca as seg
from physis_hub import servidor
from physis_hub.hub import Hub

SENHA = "frase-longa-da-direcao-1"
SENHA_P = "senha-longa-da-participante-9"
ACEITE = {"aceito": True, "versao": "1"}


class Classificar(unittest.TestCase):
    def test_quatro_tipos(self):
        casos = {"Hackathon de Segurança Cibernética 2027": "hackathon_seg_quantum", "Quantum Computing Challenge": "hackathon_seg_quantum",
                 "Workshop de gêmeo digital na indústria": "modelos_gemeo", "Digital Twin Summit": "modelos_gemeo",
                 "Feira de Inovação e Sustentabilidade": "feiras_redes", "Encontro da rede de mulheres em STEM": "feiras_redes",
                 "Desafio de inovação aberta em energia": "desafios_chamadas", "Prêmio Mulheres na Ciência": "desafios_chamadas",
                 "Curso de Excel avançado": None}
        for titulo, esperado in casos.items():
            self.assertEqual(ag.classificar(titulo), esperado, titulo)


class Modulo(unittest.TestCase):
    def setUp(self):
        self.h = Hub(org="agenda-teste")
        self.h.criar_conta("Direção", "dir@x.example", SENHA)
        self.dir = self.h.sessao(self.h.entrar("dir@x.example", SENHA)["token"])
        self.com = cm.Comunidade(self.h, aberto=True)
        self.a = ag.Agenda(self.h, hoje=lambda: "2026-11-19")
        self.com.agenda = self.a
        self.com.cadastrar({"nome": "Ana", "usuario": "ana@x.example", "senha": SENHA_P, "nome_publico": "Ana", "maior_de_idade": True,
                            "consentimento": ACEITE})
        self.ana = self.h.sessao(self.h.entrar("ana@x.example", SENHA_P)["token"])

    def test_equipe_publica_e_participante_sugere(self):
        r = self.a.criar({"categoria": "instituto", "titulo": "Mostra anual da rede", "inicio": "2027-12-05", "link": "https://exemplo.org/mostra"}, self.dir)
        self.assertEqual(r["estado"], "publicado")
        self.assertEqual(self.a.criar({"categoria": "instituto", "titulo": "Outro"}, self.ana)["codigo"], 403)
        r = self.a.sugerir({"categoria": "feiras_redes", "titulo": "Feira de ciência", "inicio": "2027-03-10"}, self.ana, self.com.pode_publicar)
        self.assertEqual(r["estado"], "sugerido")
        self.assertEqual([x["titulo"] for x in self.a.publicos()["itens"]], ["Mostra anual da rede"])
        fila = self.com.fila(self.dir)
        ev = [x for x in fila["itens"] if x["tipo"] == "evento"]
        self.assertEqual(len(ev), 1)
        self.assertTrue(self.com.moderar({"tipo": "evento", "id": ev[0]["id"], "decisao": "aprovar"}, self.dir)["ok"])
        self.assertEqual([x["titulo"] for x in self.a.publicos()["itens"]], ["Feira de ciência", "Mostra anual da rede"])
        self.assertEqual([x["titulo"] for x in self.a.publicos("feiras_redes")["itens"]], ["Feira de ciência"])

    def test_validacao(self):
        f = lambda **kw: self.a.criar({"categoria": "instituto", "titulo": "Evento X", **kw}, self.dir)
        self.assertFalse(f(link="http://inseguro.org")["ok"])
        self.assertFalse(f(inicio="19/11/2026")["ok"])
        self.assertFalse(f(inicio="2027-02-10", fim="2027-02-01")["ok"])
        self.assertFalse(self.a.criar({"categoria": "outra", "titulo": "Evento X"}, self.dir)["ok"])
        self.assertTrue(f(modalidade="online")["ok"])

    def test_passados_nao_aparecem(self):
        self.a.criar({"categoria": "instituto", "titulo": "Já passou", "inicio": "2026-01-10"}, self.dir)
        self.a.criar({"categoria": "instituto", "titulo": "Sem data"}, self.dir)
        self.assertEqual([x["titulo"] for x in self.a.publicos()["itens"]], ["Sem data"])
        self.assertEqual(len(self.a.publicos(passados=True)["itens"]), 2)

    def test_importar_do_coletor(self):
        itens = [{"id": "c1", "titulo": "Hackathon de computação quântica", "resumo": "Inscrições até 10 de março de 2027",
                  "link": "https://ex.org/hack", "fonteNome": "Fonte A", "datas": [{"data": "2027-03-10", "rotulo": "Inscrição"}]},
                 {"id": "c2", "titulo": "Seminário de contabilidade", "resumo": "", "link": "https://ex.org/x"},
                 {"id": "c3", "titulo": "Desafio de gêmeo digital", "resumo": "", "link": "http://ex.org/inseguro"}]
        r = self.a.importar(itens, self.dir)
        self.assertEqual((r["novos"], r["fora_dos_tipos"]), (2, 1))
        self.assertEqual(self.a.importar(itens, self.dir)["repetidos"], 2)
        todos = {x["titulo"]: x for x in self.a.todos(self.dir)["itens"]}
        self.assertEqual(todos["Hackathon de computação quântica"]["inicio"], "2027-03-10")
        self.assertEqual(todos["Hackathon de computação quântica"]["estado"], "sugerido")
        self.assertEqual(todos["Desafio de gêmeo digital"]["link"], "", "link sem https não entra")
        self.assertEqual(self.a.publicos()["itens"], [], "nada do coletor aparece sem moderação")
        self.assertEqual(self.a.importar(itens, self.ana)["codigo"], 403)


class Rotas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.antes = os.environ.get("PHYSIS_LIMITE_ENTRAR")
        os.environ["PHYSIS_LIMITE_ENTRAR"] = "0"
        cls.h = Hub(org="agenda-rotas")
        cls.srv = servidor.iniciar(cls.h, 0, endereco="127.0.0.1", instancia={"login": True, "cadastro_aberto": True, "moderacao_previa": True,
                                                                               "instalacao": "instituto"})
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

    def pedir(self, metodo, rota, corpo=None, s=None):
        cab = {"Content-Type": "application/json"}
        if s:
            cab.update({"Cookie": s[0], "X-Physis-CSRF": s[1]})
        req = urllib.request.Request(f"http://127.0.0.1:{self.porta}{rota}", method=metodo, headers=cab,
                                     data=json.dumps(corpo).encode() if corpo is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            b = e.read()
            return e.code, (json.loads(b) if b.strip().startswith(b"{") else {})

    def test_fluxo_pelo_servidor(self):
        st, r = self.pedir("POST", "/api/agenda/criar", {"categoria": "instituto", "titulo": "Mostra anual"}, self.dir)
        self.assertEqual(st, 200, r)
        st, pub = self.pedir("GET", "/api/publico/agenda")
        self.assertEqual([x["titulo"] for x in pub["itens"]], ["Mostra anual"])
        self.assertNotIn("criado_por", json.dumps(pub), "quem cadastrou não sai na rota pública")
        st, r = self.pedir("POST", "/api/publico/cadastro", {"nome": "Bia", "usuario": "bia@r.example", "senha": SENHA_P, "nome_publico": "Bia",
                                                               "maior_de_idade": True, "consentimento": ACEITE})
        self.assertEqual(st, 200, r)
        tk = self.h.entrar("bia@r.example", SENHA_P)["token"]
        bia = ("physis_sessao=" + tk, seg.csrf_de(self.h, tk))
        st, r = self.pedir("POST", "/api/agenda/sugerir", {"categoria": "desafios_chamadas", "titulo": "Desafio aberto de energia"}, bia)
        self.assertEqual((st, r["estado"]), (200, "sugerido"))
        st, r = self.pedir("POST", "/api/agenda/criar", {"categoria": "instituto", "titulo": "Não pode"}, bia)
        self.assertEqual(st, 403)
        st, r = self.pedir("GET", "/api/agenda", s=bia)
        self.assertEqual(st, 403)
        st, fila = self.pedir("GET", "/api/comunidade/moderacao", s=self.dir)
        ev = [x for x in fila["itens"] if x["tipo"] == "evento"]
        st, r = self.pedir("POST", "/api/comunidade/moderar", {"tipo": "evento", "id": ev[0]["id"], "decisao": "aprovar"}, self.dir)
        self.assertEqual(st, 200, r)
        st, pub = self.pedir("GET", "/api/publico/agenda?categoria=desafios_chamadas")
        self.assertEqual([x["titulo"] for x in pub["itens"]], ["Desafio aberto de energia"])
        st, r = self.pedir("POST", "/api/agenda/importar", {}, self.dir)
        self.assertEqual(st, 200, r)          # coletor sem cache: nada novo, sem erro
        st, _ = self.pedir("POST", "/api/agenda/sugerir", {"categoria": "instituto", "titulo": "Sem conta"})
        self.assertEqual(st, 401)


if __name__ == "__main__":
    unittest.main()
