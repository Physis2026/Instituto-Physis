"""Alertas de clima por e-mail e WhatsApp (sem rede: o WhatsApp é uma função de mentira).

Protege:
1. As regras são as mesmas da plataforma (geada no café, chuva na colheita, calor no rebanho, rega, horta,
   hospedagem, encostas pelo CEMADEN) e cada uma tem atenção e alerta.
2. Sem consentimento não há assinatura; ao sair, contatos e apikey são apagados.
3. O mesmo alerta sai uma vez por dia por pessoa; só repete se subir de atenção para alerta.
4. Horário de silêncio segura a atenção, mas não o alerta (se a pessoa deixar).
5. E-mail vai para a fila email_saida; WhatsApp usa a API do CallMeBot (como o receptor), com a apikey
   mascarada nas listagens.
"""
import json
import unittest
import urllib.parse
from datetime import datetime

from physis_hub import alertas_clima as ac
from physis_hub.alertas_clima import FUSO
from physis_hub.hub import Hub

HOJE = "2026-07-10"


def em(h, m=0, dia=10):
    return datetime(2026, 7, dia, h, m, tzinfo=FUSO).timestamp()


class FalsoWhats:
    def __init__(self, ok=True):
        self.envios, self.ok = [], ok

    def enviar(self, numero, chave, texto):
        self.envios.append((numero, chave, texto))
        return self.ok, "HTTP 200" if self.ok else "HTTP 500"


def montar(relogio, whats=None, dias=None, cemaden=None):
    h = Hub(":memory:", relogio=lambda: relogio[0])
    a = ac.AlertasClima(h, whatsapp=whats, relogio=lambda: relogio[0])
    om = {"dias": dias if dias is not None else [{"dia": HOJE, "mm": 0.0, "tmin": 2.0, "tmax": 22.0},
                                                 {"dia": "2026-07-11", "mm": 12.0, "tmin": 0.5, "tmax": 21.0}]}
    h._db.execute("INSERT INTO clima_fonte(fonte,dados,consultado) VALUES('openmeteo',?,?)", (json.dumps(om), relogio[0]))
    if cemaden:
        h._db.execute("INSERT INTO clima_fonte(fonte,dados,consultado) VALUES('cemaden',?,?)", (json.dumps(cemaden), relogio[0]))
    h._db.commit()
    return h, a


ASSINATURA = {"consentimento": True, "nome": "Ana", "email": "ana@exemplo.com.br", "whatsapp": "(24) 99999-0000",
              "whatsapp_chave": "123456", "canais": ["email", "whatsapp"], "atividades": ["cafe"]}


class TestRegras(unittest.TestCase):
    def test_regras_e_niveis(self):
        dias = [{"dia": "2026-07-10", "mm": 35.0, "tmin": 2.5, "tmax": 36.0}, {"dia": "2026-07-11", "mm": 6.0, "tmin": 0.5, "tmax": 20.0}]
        al = ac.avaliar(dias, {"mm_24h": 45.0, "mm_72h": 50.0, "estacao": {"nome": "Quitandinha"}}, {"dia": "2026-07-11", "prob": 0.8}, HOJE)
        por = {(a["regra"], a["dia"]): a["nivel"] for a in al}
        self.assertEqual(por[("geada_cafe", "2026-07-10")], "atencao")
        self.assertEqual(por[("geada_cafe", "2026-07-11")], "alerta")
        self.assertEqual(por[("chuva_colheita", "2026-07-10")], "alerta")
        self.assertEqual(por[("calor_rebanho", "2026-07-10")], "alerta")
        self.assertEqual(por[("chuva_irrigacao", "2026-07-11")], "atencao")
        self.assertEqual(por[("hospedagem_chuva", "2026-07-10")], "atencao")
        self.assertEqual(por[("horta", "2026-07-10")], "atencao")   # 35 mm, 36 °C: abaixo de 50 mm e 37 °C
        self.assertEqual(por[("chuva_modelo", "2026-07-11")], "atencao")
        self.assertEqual(por[("deslizamento", HOJE)], "atencao")
        self.assertEqual(ac.avaliar([], {"mm_24h": 90.0, "mm_72h": 10.0}, None, HOJE)[0]["nivel"], "alerta")
        # colheita só de maio a setembro; dia passado não conta
        self.assertFalse([a for a in ac.avaliar([{"dia": "2026-11-20", "mm": 40.0}], None, None, "2026-11-19") if a["regra"] == "chuva_colheita"])
        self.assertFalse(ac.avaliar([{"dia": "2026-07-09", "tmin": 0.0}], None, None, HOJE))

    def test_silencio(self):
        self.assertTrue(ac.no_silencio("23:00", "22:00", "06:00"))
        self.assertTrue(ac.no_silencio("05:59", "22:00", "06:00"))
        self.assertFalse(ac.no_silencio("06:00", "22:00", "06:00"))
        self.assertTrue(ac.no_silencio("13:00", "12:00", "14:00"))


class TestAssinatura(unittest.TestCase):
    def test_consentimento_e_sair(self):
        rel = [em(10)]
        h, a = montar(rel)
        self.assertFalse(a.assinar(dict(ASSINATURA, consentimento=False), "ana")["ok"])
        self.assertFalse(a.assinar(dict(ASSINATURA, whatsapp="123"), "ana")["ok"])
        r = a.assinar(ASSINATURA, "ana")
        self.assertTrue(r["ok"])
        s = r["assinatura"]
        self.assertEqual(s["whatsapp"], "5524999990000")
        self.assertEqual(s["whatsapp_chave"], "…456")
        self.assertGreater(s["consentimento"], 0)
        self.assertEqual(a.assinaturas("ana")[0]["id"], s["id"])
        self.assertFalse(a.sair(s["id"], "outra")["ok"])
        self.assertTrue(a.sair(s["id"], "ana")["ok"])
        linha = h._db.execute("SELECT email, whatsapp, whatsapp_chave, ativa FROM alerta_assinatura").fetchone()
        self.assertEqual(linha, ("", "", "", 0))
        self.assertTrue(h.verificar_cadeia()[0])
        self.assertNotIn("99999", json.dumps([x["conteudo"] for x in h.painel()["registro"]]))


class TestEnvio(unittest.TestCase):
    def test_envia_uma_vez_por_dia_e_escala(self):
        rel = [em(10)]
        w = FalsoWhats()
        h, a = montar(rel, whats=w, dias=[{"dia": HOJE, "mm": 0.0, "tmin": 2.0, "tmax": 22.0}])
        a.assinar(ASSINATURA, "ana")
        r = a.ciclo()
        self.assertEqual(r["enviados"], 2)                   # e-mail + WhatsApp da geada (atenção)
        self.assertEqual(len(h.emails("pendente")), 1)
        self.assertIn("geada", w.envios[0][2])
        self.assertEqual(a.ciclo()["enviados"], 0)           # mesmo dia: não repete
        # a previsão piora: geada vira alerta → sai de novo
        h._db.execute("UPDATE clima_fonte SET dados=? WHERE fonte='openmeteo'",
                      (json.dumps({"dias": [{"dia": HOJE, "mm": 0.0, "tmin": 0.0, "tmax": 22.0}]}),))
        h._db.commit()
        self.assertEqual(a.ciclo()["enviados"], 2)
        rel[0] = em(10, dia=11)                              # dia seguinte: a regra do dia 10 já passou
        self.assertEqual(a.ciclo()["enviados"], 0)
        self.assertEqual(len(a.historico()), 4)
        self.assertEqual(len(a.historico(quem="ana")), 4)
        self.assertEqual(len(a.historico(quem="outra")), 0)

    def test_filtros_e_silencio(self):
        rel = [em(23)]
        w = FalsoWhats()
        h, a = montar(rel, whats=w, cemaden={"mm_24h": 90.0, "mm_72h": 130.0})
        a.assinar(dict(ASSINATURA, atividades=["gado"]), "bia")          # não planta café: geada não vale
        r = a.ciclo()
        regras = {x["chave"].split("|")[0] for x in a.historico()}
        self.assertEqual(regras, {"deslizamento"})          # alerta fura o silêncio
        self.assertGreater(r["enviados"], 0)
        h2, a2 = montar([em(23)], whats=FalsoWhats())
        a2.assinar(ASSINATURA, "ana")
        r2 = a2.ciclo()
        self.assertEqual(r2["adiados_silencio"], 2)          # geada de hoje e chuva na colheita são atenção: esperam
        self.assertGreater(r2["enviados"], 0)                # a geada de amanhã já é alerta

    def test_sem_whatsapp_configurado(self):
        rel = [em(10)]
        h, a = montar(rel, whats=None)
        a.assinar(dict(ASSINATURA, canais=["whatsapp"]), "ana")
        a.ciclo()
        self.assertEqual({x["estado"] for x in a.historico()}, {"falhou"})


class TestCallMeBot(unittest.TestCase):
    def test_url_igual_ao_receptor(self):
        pedidos = []
        def abrir(url, tempo):
            pedidos.append(url)
            return 200, "Message queued"
        ok, det = ac.CallMeBot(abrir).enviar("5524999990000", "123456", "Atenção: geada amanhã")
        self.assertTrue(ok)
        u = urllib.parse.urlparse(pedidos[0])
        q = urllib.parse.parse_qs(u.query)
        self.assertEqual(u.netloc + u.path, "api.callmebot.com/whatsapp.php")
        self.assertEqual(q["phone"], ["+5524999990000"])
        self.assertEqual(q["apikey"], ["123456"])
        self.assertEqual(q["text"], ["Atenção: geada amanhã"])
        self.assertFalse(ac.CallMeBot(abrir).enviar("", "1", "x")[0])
        def falha(url, tempo):
            raise OSError("sem rede")
        self.assertFalse(ac.CallMeBot(falha).enviar("5524999990000", "1", "x")[0])
        self.assertFalse(ac.WhatsAppBusiness().enviar("1", "1", "x")[0])


if __name__ == "__main__":
    unittest.main()
