"""Saúde: caixinha de remédios e pulseira (relógio de mentira; nada sai para a internet).

Protege:
1. As linhas novas MED e PUL (a homologar) são lidas com as regras da linha V6 e o que é inválido é recusado.
2. LGPD: nada é guardado sem consentimento com data e hora; menor só com responsável; só vê quem foi autorizado;
   consentimento retirado = aparelho ignorado e ninguém avisado; "apagar" some com tudo; o registro do hub não leva remédio.
3. Doses: tomada, atrasada, esquecida (pelo aparelho ou pelo hub depois da tolerância), adesão e próximas doses.
4. Avisos: dose esquecida e crise da pulseira vão para a fila de e-mail (email_saida, estado 'pendente') uma vez só.
"""
import json
import unittest
from datetime import datetime

from physis_hub.hub import Hub
from physis_hub.saude import (FUSO, Saude, estado_dose, ler_linha, ocorrencias, resumo_adesao)

SENHA = "senha-bem-comprida-123"


def t(dia: int, h: int, m: int = 0) -> float:
    return datetime(2026, 11, dia, h, m, tzinfo=FUSO).timestamp()


class Relogio:
    def __init__(self, agora):
        self.agora = agora

    def __call__(self):
        return self.agora


CONS = {"aceito": True}


class Linhas(unittest.TestCase):
    def test_med(self):
        ok, _, d = ler_linha("ID:31,TIPO:MED,CMP:2,EVT:tomado,BAT:3.91,TS:1794650400")
        self.assertTrue(ok)
        self.assertEqual((d["id"], d["tipo"], d["cmp"], d["evt"], d["bat"], d["ts"]), (31, "MED", 2, "TOMADO", 3.91, 1794650400))

    def test_pul(self):
        ok, _, d = ler_linha("ID:51;TIPO:PUL;LAT:-22.51003;LON:-43.18012;GPS:1;CRISE:1;BPM:-;MOV:2;BAT:3.80;TS:-")
        self.assertTrue(ok)
        self.assertEqual((d["lat"], d["lon"], d["crise"], d["bpm"], d["mov"], d["ts"]), (-22.51003, -43.18012, True, None, 2, 0))
        ok, _, d = ler_linha("ID:51,TIPO:PUL,LAT:-22.5,LON:-43.1,GPS:0,CRISE:0,BPM:400,MOV:7")
        self.assertEqual((d["lat"], d["gps"], d["bpm"], d["mov"]), (None, False, None, None))   # sem GPS não há local

    def test_recusas(self):
        casos = {"": "vazia", "TIPO:MED,CMP:1,EVT:TOMADO": "sem_id", "ID:100,TIPO:MED,CMP:1,EVT:TOMADO": "id_fora",
                 "ID:3,U1:40": "tipo_desconhecido", "ID:3,TIPO:COL": "tipo_desconhecido",
                 "ID:3,TIPO:MED,CMP:9,EVT:TOMADO": "cmp_invalido", "ID:3,TIPO:MED,CMP:1,EVT:ABRIU": "evento_invalido",
                 "CMD:03:PING": "comando", "ID:3,TIPO:MED,CMP:1,EVT:TOMADO," + "X:1," * 80: "longa"}
        for linha, motivo in casos.items():
            self.assertEqual(ler_linha(linha)[:2], (False, motivo), linha)


class ContasPuras(unittest.TestCase):
    H = {"id": 1, "cmp": 1, "hora": "08:00", "dias": "135", "tolerancia": 60}   # seg, qua, sex

    def test_ocorrencias_respeita_dias_e_criacao(self):
        ocs = ocorrencias([self.H], t(9, 0), t(16, 0))          # 09/11/2026 é segunda
        self.assertEqual([o["dia"] for o in ocs], ["2026-11-09", "2026-11-11", "2026-11-13"])
        criado = dict(self.H, criado=t(11, 9, 30))               # criado depois da janela de quarta
        self.assertEqual([o["dia"] for o in ocorrencias([criado], t(9, 0), t(16, 0))], ["2026-11-13"])

    def test_estado_e_adesao(self):
        o = ocorrencias([self.H], t(13, 0), t(14, 0))[0]
        self.assertEqual(estado_dose(o, [], t(13, 7)), "esperando")
        self.assertEqual(estado_dose(o, [], t(13, 8, 30)), "pendente")
        self.assertEqual(estado_dose(o, [("TOMADO", t(13, 7, 45))], t(13, 8, 30)), "tomado")       # um pouco antes vale
        self.assertEqual(estado_dose(o, [("TOMADO", t(13, 9, 30))], t(13, 10)), "atrasado")
        self.assertEqual(estado_dose(o, [], t(13, 9, 1)), "esquecido")
        self.assertEqual(estado_dose(o, [("ESQUECEU", t(13, 9)), ("ATRASO", t(13, 9, 40))], t(13, 10)), "atrasado")
        r = resumo_adesao(["tomado", "tomado", "atrasado", "esquecido"])
        self.assertEqual((r["total"], r["taxa"], r["taxa_no_horario"]), (4, 0.75, 0.5))
        self.assertIsNone(resumo_adesao([])["taxa"])


class SaudeNoHub(unittest.TestCase):
    def setUp(self):
        self.rel = Relogio(t(14, 7))                   # sábado, 14/11/2026, 7 h
        self.h = Hub(relogio=self.rel)
        for u in ("chefe", "ana", "bia"):           # a primeira conta é a administradora e cria as outras
            self.assertTrue(self.h.criar_conta(u.title(), u, SENHA, autor=1)["ok"])
        self.s = Saude(self.h)
        r = self.s.criar_pessoa({"nome": "Maria", "nascimento": "1950-03-02", "consentimento": CONS}, "ana")
        self.assertTrue(r["ok"])
        self.p = r["pessoa"]
        self.assertTrue(self.s.executar("horario", {"pessoa": self.p, "cmp": "1", "hora": "8:00", "dias": "1234567",
                                                    "remedio": "Losartana", "dose": "1 comprimido"}, "ana")["ok"])
        self.assertTrue(self.s.executar("horario", {"pessoa": self.p, "cmp": 2, "hora": "12:00", "dias": list("1234567"),
                                                    "tolerancia": "30"}, "ana")["ok"])
        self.assertTrue(self.s.executar("contato", {"pessoa": self.p, "nome": "Joana", "email": "joana@exemplo.com"}, "ana")["ok"])
        self.assertTrue(self.s.executar("contato", {"pessoa": self.p, "nome": "Zé", "telefone": "24 99999-0000"}, "ana")["ok"])
        self.assertTrue(self.s.executar("dispositivo", {"pessoa": self.p, "no": "31", "tipo": "med"}, "ana")["ok"])
        self.assertTrue(self.s.executar("dispositivo", {"pessoa": self.p, "no": 51, "tipo": "PUL"}, "ana")["ok"])

    def emails(self):
        return self.h._db.execute("SELECT para, assunto, corpo, estado, ref FROM email_saida").fetchall()

    def em(self, h, m=0, dia=14):
        self.rel.agora = t(dia, h, m)

    # ── consentimento e acesso ──
    def test_consentimento_com_data_e_menor_so_com_responsavel(self):
        c = self.s.consentimento(self.p)
        self.assertEqual((c["papel"], c["quem"], c["dado"], c["ativo"]), ("titular", "Maria", t(14, 7), True))
        self.assertFalse(self.s.criar_pessoa({"nome": "X", "consentimento": {"aceito": False}}, "ana")["ok"])
        r = self.s.criar_pessoa({"nome": "Pedro", "nascimento": "2015-06-01", "consentimento": CONS}, "ana")
        self.assertIn("responsável", r["erro"])
        r = self.s.criar_pessoa({"nome": "Pedro", "nascimento": "2015-06-01", "responsavel": "Carla (mãe)",
                                 "consentimento": {"aceito": True, "papel": "titular"}}, "ana")
        self.assertTrue(r["ok"] and r["menor"])
        c = self.s.consentimento(r["pessoa"])
        self.assertEqual((c["papel"], c["quem"]), ("responsavel", "Carla (mãe)"))   # menor: sempre o responsável

    def test_so_ve_quem_foi_autorizado(self):
        self.assertEqual(self.s.estado("bia")["pessoas"], [])
        self.assertEqual(self.s.estado("chefe")["pessoas"], [])                      # nem a administradora
        self.assertEqual(self.s.executar("horario_tirar", {"pessoa": self.p, "id": 1}, "bia")["codigo"], 403)
        self.assertEqual(self.s.executar("contato", {"pessoa": 999, "nome": "x", "email": "a@b.co"}, "ana")["codigo"], 403)
        self.assertEqual(self.s.executar("pessoa", {}, "")["codigo"], 401)
        self.assertFalse(self.s.executar("acesso_dar", {"pessoa": self.p, "usuario": "ninguem"}, "ana")["ok"])
        self.assertTrue(self.s.executar("acesso_dar", {"pessoa": self.p, "usuario": "Bia"}, "ana")["ok"])
        self.assertEqual([p["nome"] for p in self.s.estado("bia")["pessoas"]], ["Maria"])
        self.assertTrue(self.s.executar("acesso_tirar", {"pessoa": self.p, "usuario": "bia"}, "ana")["ok"])
        self.assertFalse(self.s.executar("acesso_tirar", {"pessoa": self.p, "usuario": "ana"}, "ana")["ok"])  # o último fica
        self.assertEqual(self.s.estado("bia")["pessoas"], [])

    def test_registro_do_hub_nao_leva_dado_de_saude(self):
        self.s.registrar_evento("ID:31,TIPO:MED,CMP:1,EVT:TOMADO,TS:-")
        tudo = " ".join(c for (c,) in self.h._db.execute("SELECT conteudo FROM registro"))
        self.assertIn("horario_incluido", tudo)
        for proibido in ("Losartana", "08:00", "joana", "Maria"):
            self.assertNotIn(proibido, tudo)
        self.assertTrue(self.h.verificar_cadeia()[0])

    # ── caixinha ──
    def test_dose_tomada_pela_caixinha(self):
        self.em(8, 10)
        ts = int(t(14, 8, 5))
        r = self.s.registrar_evento(f"ID:31,TIPO:MED,CMP:1,EVT:TOMADO,BAT:3.9,TS:{ts}")
        self.assertTrue(r["ok"]); self.assertEqual(r["dia"], "2026-11-14")
        self.assertTrue(self.s.registrar_evento(f"ID:31,TIPO:MED,CMP:1,EVT:TOMADO,TS:{ts}")["duplicada"])   # repetida
        hoje = {o["hora"]: o["estado"] for o in self.s.estado("ana")["pessoas"][0]["hoje"]}
        self.assertEqual(hoje, {"08:00": "tomado", "12:00": "esperando"})
        self.assertEqual(self.s.registrar_evento("ID:32,TIPO:MED,CMP:1,EVT:TOMADO")["motivo"], "aparelho_desconhecido")
        self.assertEqual(self.s.registrar_evento("ID:31,TIPO:PUL,GPS:0,CRISE:0")["motivo"], "tipo_trocado")
        self.assertTrue(self.s.registrar_evento({"id": 31, "tipo": "MED", "cmp": 2, "evt": "TOMADO"})["ok"])   # dict também

    def test_esquecida_avisa_cuidador_uma_vez(self):
        self.em(8, 30)
        self.assertEqual(self.s.verificar(), 0)                                    # ainda na tolerância
        self.assertEqual([o["estado"] for o in self.s.proximas_doses(pessoa=self.p)][:1], ["pendente"])
        self.em(9, 1)
        self.assertEqual(self.s.verificar(), 1)
        self.assertEqual(self.s.verificar(), 0)                                    # não repete
        em = self.emails()
        self.assertEqual(len(em), 1)                                               # só quem tem e-mail
        para, assunto, corpo, estado, ref = em[0]
        self.assertEqual((para, estado), ("joana@exemplo.com", "pendente"))
        self.assertIn("08:00", corpo); self.assertIn("Maria", corpo); self.assertNotIn("Losartana", corpo)
        pend = self.s.alertas_pendentes()
        self.assertEqual([a["tipo"] for a in pend], ["dose_esquecida"]); self.assertEqual(ref, f"saude-{pend[0]['id']}")
        # a dose tomada depois conta como atrasada, não some
        self.assertTrue(self.s.executar("dose", {"pessoa": self.p, "horario": 1, "dia": "2026-11-14"}, "ana")["ok"])
        self.assertEqual(self.s.estado("ana")["pessoas"][0]["hoje"][0]["estado"], "atrasado")
        self.assertTrue(self.s.executar("alerta_visto", {"pessoa": self.p, "id": pend[0]["id"]}, "ana")["ok"])
        self.assertEqual(self.s.alertas_pendentes(), [])

    def test_caixinha_avisa_esquecida_na_hora(self):
        self.em(9, 0)
        r = self.s.registrar_evento(f"ID:31,TIPO:MED,CMP:1,EVT:ESQUECEU,TS:{int(t(14, 9))}")
        self.assertEqual(len(r["alertas"]), 1)
        self.em(9, 5)
        self.assertEqual(self.s.verificar(), 0)                                    # o hub não avisa de novo
        self.assertEqual(len(self.emails()), 1)

    def test_tempo_ate_esquecida_e_proximas(self):
        self.em(7)
        prox = self.s.proximas_doses(pessoa=self.p)
        self.assertEqual([(o["hora"], o["estado"]) for o in prox[:2]], [("08:00", "esperando"), ("12:00", "esperando")])
        todas = self.s.proximas_doses()
        self.assertEqual(todas[0]["nome"], "Maria")

    def test_adesao_de_varios_dias(self):
        # 14/11: 08 h tomada no horário, 12 h esquecida; 15/11: 08 h com atraso, 12 h no horário
        self.em(8, 10); self.s.registrar_evento(f"ID:31,TIPO:MED,CMP:1,EVT:TOMADO,TS:{int(t(14, 8, 2))}")
        self.em(13); self.s.verificar()
        self.em(9, 30, 15); self.s.registrar_evento(f"ID:31,TIPO:MED,CMP:1,EVT:ATRASO,TS:{int(t(15, 9, 20))}")
        self.em(12, 10, 15); self.s.registrar_evento(f"ID:31,TIPO:MED,CMP:2,EVT:TOMADO,TS:{int(t(15, 12, 5))}")
        self.em(20, 0, 15)
        a = self.s.adesao(7, self.p)
        self.assertEqual((a["total"], a["tomadas"], a["atrasadas"], a["esquecidas"], a["taxa"]), (4, 2, 1, 1, 0.75))
        dia14 = [d for d in a["por_dia"] if d["dia"] == "2026-11-14"][0]
        self.assertEqual((dia14["total"], dia14["taxa"]), (2, 0.5))
        self.assertEqual(len(a["por_dia"]), 7)
        self.assertIn(self.p, self.s.adesao(30))

    def test_horario_removido_mantem_historico(self):
        self.em(13)
        self.s.verificar()
        self.assertTrue(self.s.executar("horario_tirar", {"pessoa": self.p, "id": 1}, "ana")["ok"])
        self.assertEqual([h["hora"] for h in self.s.estado("ana")["pessoas"][0]["horarios"]], ["12:00"])
        self.em(20)
        self.assertEqual(self.s.adesao(1, self.p)["total"], 2)                       # o 08:00 de hoje continua contando
        self.em(20, 0, 15)
        self.assertEqual([d["total"] for d in self.s.adesao(2, self.p)["por_dia"]], [2, 1])

    def test_validacoes_do_horario(self):
        for d, trecho in (({"cmp": 9, "hora": "08:00"}, "Compartimento"), ({"cmp": 1, "hora": "25:00"}, "Hora"),
                          ({"cmp": 1, "hora": "09:00", "dias": "89"}, "dia"), ({"cmp": 1, "hora": "09:00", "tolerancia": 2}, "Tolerância"),
                          ({"cmp": 1, "hora": "08:00"}, "já tem")):
            r = self.s.executar("horario", dict(d, pessoa=self.p), "ana")
            self.assertFalse(r["ok"]); self.assertIn(trecho, r["erro"])
        self.assertFalse(self.s.executar("dispositivo", {"pessoa": self.p, "no": 31, "tipo": "MED"}, "ana")["ok"])   # em uso
        self.assertFalse(self.s.executar("contato", {"pessoa": self.p, "nome": "x", "email": "sem-arroba"}, "ana")["ok"])

    # ── pulseira ──
    def test_crise_avisa_na_hora_e_agrupa(self):
        self.em(15)
        r = self.s.registrar_evento(f"ID:51,TIPO:PUL,LAT:-22.51003,LON:-43.18012,GPS:1,CRISE:1,BPM:128,MOV:2,BAT:3.8,TS:{int(t(14, 15))}")
        self.assertEqual(len(r["alertas"]), 1)
        para, assunto, corpo, estado, _ = self.emails()[0]
        self.assertIn("crise", assunto.lower()); self.assertIn("-22.51003, -43.18012", corpo); self.assertEqual(estado, "pendente")
        self.em(15, 5)
        r = self.s.registrar_evento(f"ID:51,TIPO:PUL,LAT:-22.52,LON:-43.19,GPS:1,CRISE:1,TS:{int(t(14, 15, 5))}")
        self.assertEqual(r["alertas"], [])                                            # mesma crise: só atualiza o local
        crises = [a for a in self.s.alertas_pendentes() if a["tipo"] == "crise"]
        self.assertEqual(len(crises), 1); self.assertEqual(crises[0]["lat"], -22.52)
        pos = self.s.estado("ana")["pessoas"][0]["posicao"]
        self.assertEqual((pos["crise"], pos["bpm"], pos["lat"]), (True, None, -22.52))
        self.s.executar("alerta_visto", {"pessoa": self.p, "id": crises[0]["id"]}, "ana")
        self.em(15, 7)
        r = self.s.registrar_evento("ID:51,TIPO:PUL,GPS:0,CRISE:1,TS:-")
        self.assertEqual(len(r["alertas"]), 1)                                        # depois de visto, crise nova avisa
        self.assertIn("sem posição", self.emails()[-1][2])

    def test_bateria_fraca_uma_vez_por_dia(self):
        self.em(10)
        self.assertEqual(len(self.s.registrar_evento("ID:51,TIPO:PUL,GPS:0,CRISE:0,BAT:3.30")["alertas"]), 1)
        self.assertEqual(self.s.registrar_evento("ID:51,TIPO:PUL,GPS:0,CRISE:0,BAT:3.20")["alertas"], [])

    # ── retirar consentimento e apagar ──
    def test_revogar_para_tudo(self):
        self.assertTrue(self.s.executar("revogar", {"pessoa": self.p}, "ana")["ok"])
        self.assertEqual(self.s.registrar_evento("ID:51,TIPO:PUL,GPS:0,CRISE:1")["motivo"], "sem_consentimento")
        self.em(13)
        self.assertEqual(self.s.verificar(), 0)
        self.assertEqual(self.emails(), [])
        p = self.s.estado("ana")["pessoas"][0]
        self.assertFalse(p["ativo"]); self.assertNotIn("horarios", p)                # sem dado de saúde na tela
        self.assertFalse(self.s.executar("horario", {"pessoa": self.p, "cmp": 3, "hora": "18:00"}, "ana")["ok"])
        self.assertTrue(self.s.executar("consentimento", {"pessoa": self.p, "consentimento": CONS}, "ana")["ok"])
        self.assertTrue(self.s.estado("ana")["pessoas"][0]["ativo"])
        n = self.h._db.execute("SELECT COUNT(*) FROM saude_consentimento WHERE pessoa=?", (self.p,)).fetchone()[0]
        self.assertEqual(n, 2)                                                        # o histórico do consentimento fica

    def test_apagar_some_com_tudo(self):
        self.em(9, 30)
        self.s.verificar()
        self.s.registrar_evento("ID:51,TIPO:PUL,GPS:0,CRISE:1")
        self.assertEqual(len(self.emails()), 2)
        self.assertTrue(self.s.executar("apagar", {"pessoa": self.p}, "ana")["ok"])
        for tab in ("saude_pessoa", "saude_dose", "saude_posicao", "saude_alerta", "saude_horario", "saude_contato",
                    "saude_dispositivo", "saude_acesso", "saude_consentimento", "email_saida"):
            self.assertEqual(self.h._db.execute(f"SELECT COUNT(*) FROM {tab}").fetchone()[0], 0, tab)
        self.assertEqual(self.s.estado("ana")["pessoas"], [])
        self.assertEqual(self.s.registrar_evento("ID:31,TIPO:MED,CMP:1,EVT:TOMADO")["motivo"], "aparelho_desconhecido")

    def test_estado_serializa_em_json(self):
        self.em(9, 30)
        e = self.s.estado("ana")
        json.dumps(e, ensure_ascii=False)
        p = e["pessoas"][0]
        self.assertEqual(set(p["adesao"]), {"semana", "mes"})
        self.assertEqual([c["nome"] for c in p["contatos"]], ["Joana", "Zé"])
        self.assertEqual([d["no"] for d in p["dispositivos"]], [31, 51])
        self.assertEqual(len(e["alertas"]), 1)


if __name__ == "__main__":
    unittest.main()
