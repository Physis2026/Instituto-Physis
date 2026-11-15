"""Suporte remoto com prazo ("Permitir suporte"): physis_hub/suporte_remoto.py e sistema/physis-suporte-remoto.js.

Protege: concessão só pela direção com reautenticação; prazo com relógio falso; endereço fora da VPN recusado mesmo com
o código; código errado recusado com limite de tentativas; revogação; "só ver" bloqueia escrita; auditoria no registro
encadeado do hub e na lista do cliente; o código nunca aparece em texto no banco nem no registro.
"""
import ipaddress
import json
import re
import unittest
from pathlib import Path

from physis_hub.hub import Hub
from physis_hub import suporte_remoto as sr

RAIZ = Path(__file__).resolve().parents[2]
VPN = [ipaddress.ip_network("100.64.0.0/10")]
EQUIPE = {"suporte@physis.example"}


class Relogio:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class SuporteRemoto(unittest.TestCase):
    def setUp(self):
        self.r = Relogio()
        self.h = Hub(relogio=self.r)
        self.s = sr.SuporteRemoto(self.h, redes=VPN, contas=EQUIPE, relogio=self.r)
        self.dir = {"id": 1, "usuario": "direcao@cliente.example", "papel": "administrador", "reauth": self.r.t}

    def conceder(self, prazo="2h", so_ver=False):
        r = self.s.conceder(self.dir, prazo, "ver o receptor", so_ver, "192.168.0.10")
        self.assertTrue(r["ok"], r)
        return r

    def test_so_a_direcao_com_reautenticacao(self):
        self.assertFalse(self.s.conceder({"usuario": "x", "papel": "operador", "reauth": self.r.t}, "2h")["ok"])
        velho = dict(self.dir, reauth=self.r.t - 3600)
        r = self.s.conceder(velho, "2h")
        self.assertFalse(r["ok"])
        self.assertTrue(r["reautenticar"])
        self.assertFalse(self.s.conceder(self.dir, "5h")["ok"], "só 2h, 8h, 1d ou 3d")

    def test_concessao_e_prazo_com_relogio_falso(self):
        c = self.conceder("2h")
        e = self.s.entrar(c["codigo_acesso"], "suporte@physis.example", "100.101.1.2")
        self.assertTrue(e["ok"], e)
        conta = self.s.sessao(e["token"], "100.101.1.2")
        self.assertEqual(conta["papel"], "operador")
        self.assertTrue(conta["suporte"])
        self.r.t += 2 * 3600 + 1                      # passou o prazo
        self.assertIsNone(self.s.sessao(e["token"], "100.101.1.2"))
        self.assertFalse(self.s.entrar(c["codigo_acesso"], "suporte@physis.example", "100.101.1.2")["ok"])
        lista = self.s.listar(self.dir)
        self.assertEqual(lista["concessoes"][0]["situacao"], "vencida", "vencida fica guardada")
        self.assertIn("expirou", [x["tipo"] for x in lista["eventos"]])

    def test_fora_da_vpn_recusado_mesmo_com_codigo(self):
        c = self.conceder()
        r = self.s.entrar(c["codigo_acesso"], "suporte@physis.example", "203.0.113.7")
        self.assertFalse(r["ok"])
        self.assertEqual(r["codigo"], 403)
        e = self.s.entrar(c["codigo_acesso"], "suporte@physis.example", "100.101.1.2")
        self.assertIsNone(self.s.sessao(e["token"], "203.0.113.7"), "sessão levada para fora da VPN cai")
        self.assertFalse(sr.SuporteRemoto(self.h, redes=[], contas=EQUIPE, relogio=self.r).entrar(c["codigo_acesso"], "suporte@physis.example", "100.101.1.2")["ok"],
                         "sem PHYSIS_SUPORTE_REDES, ninguém entra")

    def test_codigo_errado_com_limite(self):
        self.conceder()
        for _ in range(sr.FALHAS_MAX):
            self.assertEqual(self.s.entrar("AAAAAA-BBBBBB-CCCCCC", "suporte@physis.example", "100.64.0.9")["codigo"], 403)
        self.assertEqual(self.s.entrar("AAAAAA-BBBBBB-CCCCCC", "suporte@physis.example", "100.64.0.9")["codigo"], 429)
        self.r.t += sr.ESPERA_S + 1
        self.assertEqual(self.s.entrar("AAAAAA-BBBBBB-CCCCCC", "suporte@physis.example", "100.64.0.9")["codigo"], 403)

    def test_conta_da_equipe_obrigatoria(self):
        c = self.conceder()
        self.assertFalse(self.s.entrar(c["codigo_acesso"], "outra@pessoa.example", "100.101.1.2")["ok"])

    def test_revogar(self):
        c = self.conceder("3d")
        e = self.s.entrar(c["codigo_acesso"], "suporte@physis.example", "100.101.1.2")
        self.assertTrue(self.s.revogar(self.dir, c["concessao"]["id"])["ok"])
        self.assertIsNone(self.s.sessao(e["token"], "100.101.1.2"))
        self.assertFalse(self.s.revogar(self.dir, c["concessao"]["id"])["ok"], "já encerrada")
        self.assertEqual(self.s.listar(self.dir)["concessoes"][0]["situacao"], "revogada")

    def test_so_ver_bloqueia_escrita(self):
        c = self.conceder(so_ver=True)
        e = self.s.entrar(c["codigo_acesso"], "suporte@physis.example", "100.101.1.2")
        conta = self.s.sessao(e["token"], "100.101.1.2")
        self.assertTrue(self.s.pode_metodo(conta, "GET"))
        self.assertFalse(self.s.pode_metodo(conta, "POST"))
        self.assertTrue(self.s.pode_metodo(self.dir, "POST"), "não mexe nas sessões normais")

    def test_auditoria_e_codigo_nunca_em_texto(self):
        c = self.conceder()
        e = self.s.entrar(c["codigo_acesso"], "suporte@physis.example", "100.101.1.2")
        conta = self.s.sessao(e["token"], "100.101.1.2")
        self.s.uso(conta, "GET", "/api/estado?segredo=1", "100.101.1.2")
        self.s.entrar("ERRADO", "suporte@physis.example", "100.101.1.3")
        self.s.revogar(self.dir, c["concessao"]["id"])
        tipos = [x["tipo"] for x in self.s.listar(self.dir)["eventos"]]
        for t in ("concedido", "entrou", "uso", "recusado", "revogado"):
            self.assertIn(t, tipos)
        uso = [x for x in self.s.listar(self.dir)["eventos"] if x["tipo"] == "uso"][0]
        self.assertEqual(uso["detalhe"], "GET /api/estado", "rota sem a consulta")
        self.assertEqual(uso["ip"], "100.101.1.2")
        reg = [json.loads(r[0]) for r in self.h._db.execute("SELECT conteudo FROM registro WHERE tipo='suporte_remoto'")]
        self.assertGreaterEqual(len(reg), 5)
        self.assertEqual(self.h.verificar_cadeia()[0], True)
        despejo = "\n".join(self.h._db.iterdump())
        self.assertNotIn(c["codigo_acesso"], despejo, "o código nunca fica em texto")
        self.assertIn(sr._sha(c["codigo_acesso"]), despejo, "só o resumo SHA-256")
        self.assertNotIn(e["token"], despejo)

    def test_redes_linux_da_config(self):
        r = sr.redes_config("100.64.0.0/10, 10.8.0.0/24 lixo fd7a:115c:a1e0::/48")
        self.assertEqual(len(r), 3)
        self.assertTrue(sr.na_vpn("10.8.0.5", r))
        self.assertTrue(sr.na_vpn("fd7a:115c:a1e0::1", r))
        self.assertFalse(sr.na_vpn("8.8.8.8", r))

    def test_modulo_da_tela(self):
        js = (RAIZ / "sistema" / "physis-suporte-remoto.js").read_text(encoding="utf-8")
        for t in ("window.PhysisSuporteRemoto", "/api/suporte-remoto/conceder", "/api/suporte-remoto/revogar", "aria-live", "<caption",
                  "Permitir suporte", "Allow support", "LGPD", "só ver"):
            self.assertIn(t, js, t)
        self.assertNotRegex(js, r"https?://", "sem endereço de internet")
        self.assertNotIn("<h1", js)
        self.assertNotIn("\r\n", js)


if __name__ == "__main__":
    unittest.main()
