"""Rotas do "Permitir suporte" pelo servidor de verdade (estilo test_rotas_novas).

A VPN é simulada com um proxy confiável (PHYSIS_PROXY_CONFIAVEL=127.0.0.1) e X-Forwarded-For: 100.101.1.2 está na rede
da VPN (PHYSIS_SUPORTE_REDES=100.64.0.0/10); 203.0.113.7 não está.
Protege: só a direção libera (com a senha recente); entrar de dentro da VPN funciona e de fora é recusado; o suporte em
"só ver" não escreve; a revogação derruba a sessão; o cliente vê a lista de eventos.
"""
import json
import os
import unittest
import urllib.error
import urllib.request

from physis_hub import seguranca as seg
from physis_hub import servidor
from physis_hub.hub import Hub

SENHAS = {"dir": "frase-longa-da-direcao-1", "eq": "frase-longa-da-equipe-1"}
VPN_OK, VPN_FORA = "100.101.1.2", "203.0.113.7"


class RotasSuporte(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.antes = {k: os.environ.get(k) for k in ("PHYSIS_SUPORTE_REDES", "PHYSIS_SUPORTE_CONTAS", "PHYSIS_PROXY_CONFIAVEL")}
        os.environ.update({"PHYSIS_SUPORTE_REDES": "100.64.0.0/10", "PHYSIS_SUPORTE_CONTAS": "suporte@physis.example",
                           "PHYSIS_PROXY_CONFIAVEL": "127.0.0.1"})
        cls.hub = Hub(org="suporte-rotas")
        cls.srv = servidor.iniciar(cls.hub, 0, endereco="127.0.0.1", instancia={"login": True})
        cls.porta = cls.srv.server_address[1]
        h = cls.hub
        h.criar_conta("Direção", "dir@cliente.example", SENHAS["dir"])
        adm = h.sessao(h.entrar("dir@cliente.example", SENHAS["dir"])["token"])
        h.criar_conta("Equipe", "eq@cliente.example", SENHAS["eq"], adm["id"], papel="operador")
        cls.s = {}
        for k, u in (("dir", "dir@cliente.example"), ("eq", "eq@cliente.example")):
            tk = h.entrar(u, SENHAS[k])["token"]
            cls.s[k] = ("physis_sessao=" + tk, seg.csrf_de(h, tk))

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        for k, v in cls.antes.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def c(self, metodo, rota, corpo=None, quem=None, ip=VPN_OK, cookie=None):
        h = {"Content-Type": "application/json", "X-Forwarded-For": ip}
        if quem:
            ck, tk = self.s[quem]
            h["Cookie"], h["X-Physis-CSRF"] = ck, tk
        if cookie:
            h["Cookie"] = cookie
            h["X-Physis-CSRF"] = seg.csrf_de(self.hub, cookie.split("=", 1)[1])
        dados = json.dumps(corpo).encode() if corpo is not None else None
        req = urllib.request.Request(f"http://127.0.0.1:{self.porta}{rota}", data=dados, method=metodo, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read() or b"{}"), r.headers
        except urllib.error.HTTPError as e:
            b = e.read()
            return e.code, (json.loads(b) if b.strip().startswith(b"{") else {}), e.headers

    def conceder(self, so_ver):
        st, j, _ = self.c("POST", "/api/suporte-remoto/conceder", {"duracao": "2h", "nota": "teste", "so_ver": so_ver}, quem="dir")
        self.assertEqual(st, 200, j)
        return j

    def entrar(self, codigo, ip=VPN_OK):
        return self.c("POST", "/api/suporte-remoto/entrar", {"codigo": codigo, "equipe": "suporte@physis.example"}, ip=ip)

    def test_so_a_direcao_libera(self):
        self.assertEqual(self.c("POST", "/api/suporte-remoto/conceder", {"duracao": "2h"}, quem="eq")[0], 403)
        self.assertEqual(self.c("POST", "/api/suporte-remoto/conceder", {"duracao": "2h"})[0], 401)
        self.assertEqual(self.c("POST", "/api/suporte-remoto/conceder", {"duracao": "2h", "x": 1}, quem="dir")[0], 400, "esquema estrito")

    def test_vpn_so_ver_e_revogar(self):
        j = self.conceder(so_ver=True)
        st, r, _ = self.entrar(j["codigo_acesso"], ip=VPN_FORA)
        self.assertEqual(st, 403, "fora da VPN, recusado mesmo com o código")
        st, r, cab = self.entrar(j["codigo_acesso"])
        self.assertEqual(st, 200, r)
        self.assertNotIn("token", r)
        ck = cab.get("Set-Cookie").split(";")[0]
        self.assertTrue(ck.startswith("physis_suporte="))
        st, inst, _ = self.c("GET", "/api/instancia", cookie=ck)
        self.assertTrue(inst["autenticado"])
        self.assertEqual(inst["papel"], "operador")
        st, _, _ = self.c("POST", "/api/suporte", {"assunto": "x", "mensagem": "y"}, cookie=ck)
        self.assertEqual(st, 403, "só ver: escrita recusada")
        st, _, _ = self.c("GET", "/api/instancia", cookie=ck, ip=VPN_FORA)
        st2, inst2, _ = self.c("GET", "/api/instancia", cookie=ck, ip=VPN_FORA)
        self.assertFalse(inst2["autenticado"], "a sessão de suporte não vale fora da VPN")
        self.assertEqual(self.c("POST", "/api/suporte-remoto/revogar", {"id": j["concessao"]["id"]}, quem="dir")[0], 200)
        st, inst3, _ = self.c("GET", "/api/instancia", cookie=ck)
        self.assertFalse(inst3["autenticado"], "revogada, a sessão cai")
        st, lista, _ = self.c("GET", "/api/suporte-remoto", quem="dir")
        self.assertEqual(st, 200)
        tipos = {e["tipo"] for e in lista["eventos"]}
        self.assertTrue({"concedido", "entrou", "recusado", "revogado"} <= tipos, tipos)
        self.assertNotIn(j["codigo_acesso"], json.dumps(lista))
        self.assertEqual(self.c("GET", "/api/suporte-remoto", quem="eq")[0], 403)

    def test_suporte_com_escrita_pode_escrever_e_e_registrado(self):
        j = self.conceder(so_ver=False)
        st, r, cab = self.entrar(j["codigo_acesso"])
        ck = cab.get("Set-Cookie").split(";")[0]
        st, _, _ = self.c("POST", "/api/suporte", {"assunto": "teste", "mensagem": "do suporte"}, cookie=ck)
        self.assertNotIn(st, (401, 403), "sem 'só ver', a escrita passa pela guarda do suporte (a rota decide o resto)")
        self.assertEqual(self.c("POST", "/api/suporte-remoto/conceder", {"duracao": "2h"}, cookie=ck)[0], 403, "o suporte não libera suporte")
        st, lista, _ = self.c("GET", "/api/suporte-remoto", quem="dir")
        usos = [e["detalhe"] for e in lista["eventos"] if e["tipo"] == "uso"]
        self.assertIn("POST /api/suporte", usos)
        self.assertEqual(self.c("POST", "/api/suporte-remoto/sair", {}, cookie=ck)[0], 200)


if __name__ == "__main__":
    unittest.main()
