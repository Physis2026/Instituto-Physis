"""Pluviômetro (TIPO:PLUV, docs/ROBOS.md §6) e linhas da Saúde (MED/PUL, docs/SAUDE.md) no protocolo V6.

Protege:
1. PLUV é tipo conhecido; CHI fora de 0–200 e PUL que não é inteiro ≥ 0 saem (a leitura fica).
2. O adaptador gera a grandeza "chuva" (mm, ativo <lugar>-noXX) e a intensidade (mm/h) pelo intervalo entre linhas.
3. A soma do CHI do dia vira chuva observada de origem "physis" (placar das fontes e modelo de chuva), e a chuva
   medida no lugar substitui o CEMADEN nos alertas (deslizamento).
4. MED/PUL pelo receptor/hub vão para a Saúde ANTES do adaptador: nada em `medicao`, nada no painel; sem o
   módulo, são descartadas sem mostrar a linha. PHYSIS_SAUDE_V6=0 volta a recusar (tipo_desconhecido).
"""
import os
import unittest
from datetime import datetime

from physis_hub import adaptador, nucleo, protocolo
from physis_hub import alertas_clima as al
from physis_hub import clima as clima_mod
from physis_hub import saude as saude_mod
from physis_hub.hub import Hub

T0 = int(datetime(2026, 11, 15, 10, 0, tzinfo=clima_mod.FUSO).timestamp())


class Relogio:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t


class Protocolo(unittest.TestCase):
    def test_pluv_conhecido_e_faixas(self):
        ok, motivo, c = protocolo.validar_telemetria("ID:31,TIPO:PLUV,CHI:0.20,PUL:44,BAT:-,TS:1794600000")
        self.assertEqual((ok, c["CHI"], c["PUL"]), (True, "0.20", "44"))
        ok, _, c = protocolo.validar_telemetria("ID:31,TIPO:PLUV,CHI:250,PUL:4.5,TS:1794600000")
        self.assertTrue(ok)
        self.assertNotIn("CHI", c); self.assertNotIn("PUL", c)
        self.assertEqual(set(c["_FORA"].split(",")), {"CHI", "PUL"})
        ok, _, c = protocolo.validar_telemetria("ID:31,TIPO:PLUV,CHI:1,PUL:-3")
        self.assertNotIn("PUL", c)
        self.assertEqual(nucleo.FAIXAS["chuva"], (0, 200, "mm"))
        self.assertIn("chuva", nucleo.GRANDEZAS_NOVAS)

    def test_saude_com_e_sem_bandeira(self):
        self.assertTrue(protocolo.validar_telemetria("ID:31,TIPO:MED,CMP:1,EVT:TOMADO,TS:1794650400")[0])
        os.environ["PHYSIS_SAUDE_V6"] = "0"
        try:
            self.assertEqual(protocolo.validar_telemetria("ID:31,TIPO:MED,CMP:1,EVT:TOMADO")[1], "tipo_desconhecido")
            self.assertEqual(protocolo.validar_telemetria("ID:51,TIPO:PUL,GPS:0,CRISE:1")[1], "tipo_desconhecido")
            self.assertTrue(protocolo.validar_telemetria("ID:31,TIPO:PLUV,CHI:1")[0])
        finally:
            del os.environ["PHYSIS_SAUDE_V6"]


class Adaptador(unittest.TestCase):
    def test_chuva_e_intensidade(self):
        c = protocolo.validar_telemetria("ID:31,TIPO:PLUV,CHI:0.60,PUL:44,BAT:3.9,TS:1794600000")[2]
        e = adaptador.interpretar(c)
        self.assertEqual((e["tipo"], e["chi"], e["pul"]), ("PLUV", 0.6, 44))
        m = {x["grandeza"]: x for x in adaptador.adaptar(c, "fazenda-teste", "sede", intervalo_s=600)}
        self.assertEqual((m["chuva"]["valor"], m["chuva"]["ativo"], m["chuva"]["unidade"]), (0.6, "sede-no31", "mm"))
        self.assertEqual(m["chuva_intensidade"]["valor"], 3.6)                       # 0,6 mm em 10 min = 3,6 mm/h
        self.assertNotIn("chuva_intensidade", {x["grandeza"] for x in adaptador.adaptar(c, "fazenda-teste", "sede")})
        self.assertIsNone(adaptador.intensidade_chuva(1.0, 5 * 3600))                # intervalo longo demais


class HubPluviometro(unittest.TestCase):
    def setUp(self):
        self.r = Relogio(T0)
        self.h = Hub(org="fazenda-teste", lugar="sede", relogio=self.r)

    def test_soma_do_dia_vira_chuva_observada(self):
        for i, chi in enumerate((0.2, 0.4, 1.0)):
            self.r.t = T0 + i * 600
            self.assertEqual(self.h.receber_lote(f"ID:31,TIPO:PLUV,CHI:{chi},PUL:{i},TS:{T0 + i * 600}")["aceitas"], 1)
        self.h.receber_lote(f"ID:31,TIPO:PLUV,CHI:5,PUL:9,TS:{T0 - 86400}")           # ontem: outro dia
        obs = dict(self.h._db.execute("SELECT dia, mm FROM clima_observado WHERE origem='physis'").fetchall())
        self.assertEqual(obs, {"2026-11-15": 1.6, "2026-11-14": 5.0})
        intens = [v for (v,) in self.h._db.execute("SELECT valor FROM medicao WHERE grandeza='chuva_intensidade' ORDER BY seq")]
        self.assertEqual(intens, [2.4, 6.0])                                             # 0,4 e 1,0 mm em 10 min
        no = [n for n in self.h.painel()["nos"] if n["id"] == 31][0]
        self.assertEqual((no["tipo"], no["chi"], no["pul"]), ("PLUV", 5.0, 9))
        # dois pluviômetros: média entre eles
        self.r.t = T0 + 1800
        self.h.receber_lote(f"ID:32,TIPO:PLUV,CHI:0.4,TS:{T0 + 1800}")
        self.assertEqual(self.h._db.execute("SELECT mm FROM clima_observado WHERE dia='2026-11-15'").fetchone()[0], 1.0)

    def test_modelo_e_placar_e_alertas_usam_a_chuva_do_lugar(self):
        c = clima_mod.Clima(self.h, buscar=lambda url: {})
        self.h._db.execute("INSERT INTO clima_aposta(fonte,dia,chove,mm,feita) VALUES('openmeteo','2026-11-15',0,0,0)")
        clima_mod.observar_no_banco(self.h._db, "2026-11-15", "cemaden", 0.0, T0)
        self.h.receber_lote(f"ID:31,TIPO:PLUV,CHI:45,TS:{T0}")
        self.h.receber_lote(f"ID:31,TIPO:PLUV,CHI:30,TS:{T0 + 600}")
        self.assertEqual(c.placar()["openmeteo"]["acertos"], 0)                          # o pluviômetro (75 mm) manda
        self.r.t = T0 + 1200
        local = clima_mod.chuva_medida_local(self.h._db, self.r())
        self.assertEqual((local["mm_24h"], local["estacao"]["codigo"]), (75.0, "physis"))
        self.assertEqual(c.estado()["chuva_local"]["mm_24h"], 75.0)
        alertas = al.AlertasClima(self.h, whatsapp=None).alertas_agora()
        desl = [a for a in alertas if a["regra"] == "deslizamento"]
        self.assertEqual(desl[0]["nivel"], "atencao")
        self.assertIn("Pluviômetro Physis", desl[0]["texto"])
        self.r.t = T0 + 5 * 3600                                                          # pluviômetro calado: vale o CEMADEN
        self.assertIsNone(clima_mod.chuva_medida_local(self.h._db, self.r()))


class HubSaude(unittest.TestCase):
    def setUp(self):
        self.r = Relogio(T0)
        self.h = Hub(relogio=self.r)

    def test_sem_modulo_descarta_sem_mostrar(self):
        r = self.h.receber_lote("ID:31,TIPO:MED,CMP:1,EVT:TOMADO,TS:1794650400")
        self.assertEqual((r["aceitas"], r["descartadas"]), (0, 1))
        self.assertEqual(self.h.descartes["saude_sem_modulo"], 1)
        self.assertNotIn("TOMADO", str(self.h.painel()))

    def test_vai_para_a_saude_antes_do_adaptador(self):
        s = saude_mod.Saude(self.h)
        vistos = []
        self.h.saude_receptor = lambda linha, origem: (vistos.append(origem), s.registrar_evento(linha, origem=origem))[1]
        self.assertTrue(self.h.criar_conta("Ana", "ana", "senha-bem-comprida-123")["ok"])
        r = s.criar_pessoa({"nome": "Rui", "nascimento": "1950-01-01", "consentimento": {"aceito": True}}, "ana")
        self.assertTrue(r["ok"], r)
        self.assertTrue(s.executar("dispositivo", {"pessoa": r["pessoa"], "no": 31, "tipo": "MED"}, "ana")["ok"])
        r = self.h.receber_lote(f"ID:31,TIPO:MED,CMP:1,EVT:TOMADO,BAT:3.9,TS:{T0}", origem="receptor")
        self.assertEqual(r["aceitas"], 1)
        self.assertEqual(self.h.receber_lote(f"ID:31,TIPO:MED,CMP:1,EVT:TOMADO,BAT:3.9,TS:{T0}")["duplicadas"], 1)
        self.assertEqual(vistos[0], "receptor")
        self.assertEqual(self.h._db.execute("SELECT COUNT(*) FROM medicao").fetchone()[0], 0)       # nada em medicao
        self.assertEqual(self.h._db.execute("SELECT COUNT(*) FROM leitura").fetchone()[0], 0)
        self.assertEqual(self.h.painel()["nos"], [])
        self.assertEqual(self.h._db.execute("SELECT COUNT(*) FROM saude_dose").fetchone()[0], 1)
        # aparelho não cadastrado: recusado pela Saúde, contado sem a linha
        self.assertEqual(self.h.receber_lote("ID:52,TIPO:PUL,GPS:0,CRISE:1")["descartadas"], 1)
        self.assertEqual(self.h.descartes["saude_aparelho_desconhecido"], 1)
        self.assertTrue(all("CRISE" not in d["linha"] for d in self.h.ultimas_descartadas))


if __name__ == "__main__":
    unittest.main()
