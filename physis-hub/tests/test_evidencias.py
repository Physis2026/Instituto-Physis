"""Certificação assistida (evidencias.py, sistema/physis-evidencias.js e sistema/physis-evidencias.json).

Protege:
1. O mapa só cita critérios que existem na base de certificações e fontes que existem nos dois lados (Python e JS).
2. Cobertura mínima: LEED, EDGE, ISO 14001, ISO 50001, AQUA-HQE e Casa Azul têm regra própria nos itens de água
   e energia (e nos outros com 'auto').
3. Cada fonte devolve atendido / parcial / sem evidência com valor, data e tela; o 'teto' segura dado de
   planejamento em parcial; anexo vencido vira parcial.
4. Servidor: dias medidos, sensores, modelos de consumo, nomes de arquivos da Gestão (nunca o conteúdo), risco
   do bairro do lugar; anexos validados e registrados na cadeia.
5. O módulo da tela mantém o contrato (evidenciasPara, telaEvidencias), não usa eval nem internet e usa os mesmos
   textos do Python (espelho).
"""
import json
import re
import unittest
from pathlib import Path

from physis_hub import evidencias as ev
from physis_hub.hub import Hub

RAIZ = Path(__file__).resolve().parents[2]
JS = (RAIZ / "sistema" / "physis-evidencias.js").read_text(encoding="utf-8")
MAPA = ev.carregar_mapa()
CERTS = ev.carregar_certs()
CRIT = {k["id"]: k for c in CERTS for g in c["grupos"] for k in g["criterios"]}


def crit(i):
    return CRIT[i]


def perfil(n_kwh=0, n_m3=0, area=None):
    h = [{"mes": f"2025-{m:02d}", "kwh": "1.200,5" if m <= n_kwh else "", "m3": "30" if m <= n_m3 else None} for m in range(1, 13)]
    return {"tipo": "pj", "nivel": "completo", "historico": h, "c": {"area_construida": area} if area else {}}


class Mapa(unittest.TestCase):
    def test_ids_e_fontes_existem(self):
        for cid in MAPA["por_criterio"]:
            self.assertIn(cid, CRIT, cid)
        usados = {r["fonte"] for rs in list(MAPA["por_criterio"].values()) + list(MAPA["por_auto"].values()) + [MAPA["regra_geral"]] for r in rs}
        self.assertEqual(usados - set(ev.FONTES), set())
        self.assertEqual(set(ev.FONTES) - set(MAPA["fontes"]), set())
        bloco = JS[JS.index("const FONTES = {"):JS.index("/* ── mapa e base")]
        js = set(re.findall(r"^  (\w+)\(d", bloco, re.M))
        self.assertEqual(js, set(ev.FONTES), "as fontes do JS e do Python precisam ser as mesmas")
        autos = {k.get("auto") for k in CRIT.values()} - {None}
        self.assertEqual(autos - set(MAPA["por_auto"]), set())

    def test_cobertura_agua_energia(self):
        for cid in ("leed", "edge", "iso14001", "iso50001", "aqua_hqe", "casa_azul"):
            cert = next(c for c in CERTS if c["id"] == cid)
            ks = [k for g in cert["grupos"] for k in g["criterios"]]
            proprios = [k for k in ks if k["id"] in MAPA["por_criterio"]]
            self.assertGreaterEqual(len(proprios), 5, cid)
            for k in ks:
                if k.get("auto") in ("agua", "energia_hist", "solar", "medicao") or k["id"] in ("i50_6_enpi", "i50_6_enb", "i50_6_var", "i50_6_6"):
                    regras = [r for r in ev.regras_do_criterio(k, MAPA) if r not in MAPA["regra_geral"]]
                    self.assertTrue(regras, k["id"])


class Fontes(unittest.TestCase):
    def av(self, cid, d):
        return ev.avaliar_criterio(crit(cid), dict({"hoje": "2026-11-15"}, **d))

    def test_num(self):
        self.assertEqual(ev.num("1.200,5"), 1200.5)
        self.assertEqual(ev.num("12.5"), 12.5)
        self.assertEqual(ev.num(3), 3.0)
        for v in ("", None, "abc", "1_000", True, "inf", float("nan")):
            self.assertIsNone(ev.num(v), v)

    def test_sem_nada(self):
        r = self.av("leed_wep2", {})
        self.assertEqual((r["status"], r["evidencias"], r["sugestao"]), ("sem_evidencia", [], None))

    def test_agua_contas_com_teto(self):
        r = self.av("ca_agua", {"perfil": perfil(n_m3=12)})
        self.assertEqual(r["status"], "parcial")          # contas não provam medição individualizada: teto parcial
        e = r["evidencias"][0]
        self.assertEqual((e["fonte"], e["tela"], e["data"]), ("agua_contas", "inicio", "2025-12"))
        r = self.av("aq_5", {"servidor": {"medidores": {"agua": {"dias": 45, "ultimo": "2026-11-14"}}}})
        self.assertEqual((r["status"], r["sugestao"]), ("atendido", "atende"))
        self.assertIn("45 dias de água medidos pelo hub", r["evidencias"][0]["valor"])
        r = self.av("aq_5", {"servidor": {"medidores": {"agua": {"dias": 10}}}})
        self.assertEqual(r["status"], "parcial")

    def test_cisterna(self):
        self.assertEqual(self.av("edge_w_chuva", {"calc": {"agua": {"cisterna_m3": "12,5"}}})["evidencias"][0]["valor"],
                         "Cisterna dimensionada: 12,5 m³ (falta medição de operação)")
        r = self.av("edge_w_chuva", {"servidor": {"medidores": {"nivel": {"dias": 60, "ultimo": "2026-11-10"}}}})
        self.assertEqual(r["status"], "atendido")

    def test_energia_e_enpi(self):
        r = self.av("i50_6", {"perfil": perfil(n_kwh=12)})
        self.assertEqual(r["status"], "atendido")
        r = self.av("i50_6_enpi", {"perfil": perfil(n_kwh=12, area=1000)})
        self.assertEqual(r["status"], "parcial")
        self.assertEqual(r["evidencias"][0]["valor"], "Indicador: 14,4 kWh/m² por ano (12 meses de contas)")
        r = self.av("i50_6_enpi", {"servidor": {"modelos_consumo": [{"nome": "consumo:no1-quadro|energia", "n_amostras": 60, "treinado_em": "2026-11-01"}]}})
        self.assertEqual(r["status"], "atendido")
        self.assertIsNone(ev.f_enpi({"perfil": perfil(n_kwh=11)}, {}, None))

    def test_solar(self):
        r = self.av("edge_e_fv", {"carbono": {"solar_kwh": "9000", "kwh": "21000"}})
        self.assertEqual((r["status"], r["evidencias"][0]["valor"]), ("atendido", "Geração solar de 9000 kWh/ano (30% do consumo)"))
        self.assertEqual(self.av("edge_adv", {"carbono": {"solar_kwh": "9000"}})["status"], "parcial")       # teto
        self.assertEqual(ev.f_solar({"carbono": {"solar_kwh": 50, "kwh": 50}}, {"min_cobertura": 0.6}, None)["status"], "parcial")
        self.assertEqual(self.av("ca_energia", {"calc": {"solar": {"kwp": "5"}}})["status"], "parcial")

    def test_residuos_carbono_sbn(self):
        r = self.av("leed_resid", {"residuos": {"n": 4, "com_rota": 4, "pct": 0.62}})
        self.assertEqual((r["status"], r["evidencias"][0]["valor"]), ("atendido", "62% desviado do aterro (meta 50%)"))
        self.assertEqual(self.av("leed_resid", {"residuos": {"n": 4, "com_rota": 2, "pct": 0.3}})["status"], "parcial")
        self.assertEqual(self.av("aq_6", {"residuos": {"n": 4, "com_rota": 3}})["status"], "parcial")
        self.assertEqual(self.av("leed_carbono", {"carbono": {"kwh": "20000", "diesel": "0"}})["status"], "atendido")
        self.assertEqual(self.av("leed_carbono", {"carbono": {"kwh": "20000"}})["status"], "parcial")
        self.assertEqual(self.av("leed_ssc1", {"sbn": {"plano": [{"n": "Ipê"}] * 8}})["status"], "parcial")

    def test_calibracao(self):
        cal = [{"ponto": "A", "data": "2026-01-10", "validade": "2026-07-10"}, {"ponto": "A", "data": "2026-09-01", "validade": "2027-03-01"},
               {"ponto": "B", "data": "2026-10-01", "validade": "2027-04-01"}]
        r = self.av("i50_9", {"calibracoes": cal})
        self.assertEqual((r["status"], r["evidencias"][0]["data"]), ("atendido", "2026-10-01"))
        cal[2]["validade"] = "2026-11-01"
        self.assertEqual(self.av("i50_9", {"calibracoes": cal})["status"], "parcial")
        self.assertIn("sem registro de calibração", self.av("i14_9", {"servidor": {"sensores": [{"no": 1}]}})["evidencias"][0]["valor"])

    def test_documentos_e_anexos(self):
        arq = [{"nome": "Politica_Ambiental_2026.pdf", "data": "2026-03-01"}, {"nome": "foto.jpg", "data": "2026-01-01"}]
        r = self.av("i14_5_2", {"servidor": {"arquivos": arq}})
        self.assertEqual((r["status"], r["evidencias"][0]["fonte"]), ("atendido", "documentos"))
        # sem palavra própria: usa o texto de 'evidencia' do critério ("Declaração de escopo")
        self.assertEqual(self.av("i14_4_3", {"servidor": {"arquivos": [{"nome": "declaracao de escopo v2.odt", "data": "2026-02-02"}]}})["status"], "atendido")
        self.assertEqual(self.av("i14_4_3", {"servidor": {"arquivos": arq}})["status"], "sem_evidencia")
        r = self.av("i14_10", {"anexos": [{"criterio": "i14_10", "nome": "RAC 12", "data": "2026-05-01", "validade": "2026-06-01", "responsavel": "Ana"}]})
        self.assertEqual(r["status"], "parcial")
        self.assertIn("vencida em 2026-06-01", r["evidencias"][0]["valor"])
        self.assertEqual(self.av("i14_10", {"anexos": [{"criterio": "i14_10", "nome": "RAC 12", "data": "2026-05-01"}]})["status"], "atendido")

    def test_risco_municipal(self):
        self.assertEqual(self.av("ca_qu_risco", {"municipio": {"risco_lugar": "baixo"}})["status"], "atendido")
        r = self.av("ca_qu_risco", {"servidor": {"municipio": {"risco_lugar": "muito_alto"}}})
        self.assertEqual(r["status"], "sem_evidencia")
        self.assertIn("Defesa Civil", r["evidencias"][0]["valor"])

    def test_evidencias_para(self):
        r = ev.evidencias_para("leed", {"hoje": "2026-11-15", "perfil": perfil(n_kwh=12, n_m3=12), "carbono": {"kwh": 1, "glp": 2}})
        self.assertTrue(r["ok"])
        self.assertEqual(r["resumo"]["total"], sum(len(g["criterios"]) for g in next(c for c in CERTS if c["id"] == "leed")["grupos"]))
        self.assertGreater(r["resumo"]["atendido"] + r["resumo"]["parcial"], 3)
        self.assertFalse(ev.evidencias_para("nao-existe", {})["ok"])


class Servidor(unittest.TestCase):
    def setUp(self):
        self.h = Hub(":memory:", relogio=lambda: 1794600000.0)

    def test_dados_servidor(self):
        db = self.h._db
        for dia in range(40):
            db.execute("INSERT INTO medicao(leitura,topico,grandeza,ativo,valor,ts,alarme) VALUES(1,'t','vazao','no1-agua',1.0,?,'')", (1790000000 + dia * 86400,))
        db.execute("INSERT INTO medicao(leitura,topico,grandeza,ativo,valor,ts,alarme) VALUES(1,'t','energia','no1-q',2.0,1790000000,'')")
        db.execute("INSERT INTO leitura(no,ts,recebido,origem,linha) VALUES(3,0,1794500000,'r','ID:03')")
        db.execute("INSERT INTO gestao_arquivo(id,nome,tipo,dados,tamanho,criado,por) VALUES('a1','Politica ambiental.pdf','application/pdf',x'25504446',4,1794000000,'ana')")
        db.commit()
        d = ev.dados_servidor(self.h)
        self.assertEqual(d["medidores"]["agua"]["dias"], 40)
        self.assertEqual(d["medidores"]["energia"]["dias"], 1)
        self.assertEqual(d["sensores"][0]["no"], 3)
        self.assertEqual(d["arquivos"][0]["nome"], "Politica ambiental.pdf")
        self.assertNotIn("dados", d["arquivos"][0])
        self.assertEqual(ev.dados_servidor(self.h, incluir_arquivos=False)["arquivos"], [])
        r = ev.avaliar_criterio(crit("i14_5_2"), {"hoje": "2026-11-15", "servidor": d})
        self.assertEqual(r["status"], "atendido")

    def test_anexar_e_remover(self):
        self.assertFalse(ev.anexar(self.h, {"cert": "leed", "criterio": "i14_10", "nome": "x", "data": "2026-01-01"}, "ana")["ok"])
        self.assertFalse(ev.anexar(self.h, {"cert": "leed", "criterio": "leed_reg", "nome": "", "data": "2026-01-01"}, "ana")["ok"])
        self.assertFalse(ev.anexar(self.h, {"cert": "leed", "criterio": "leed_reg", "nome": "Registro", "data": "01/01/2026"}, "ana")["ok"])
        self.assertFalse(ev.anexar(self.h, {"cert": "leed", "criterio": "leed_reg", "nome": "Registro", "data": "2026-01-01", "arquivo": "nao"}, "ana")["ok"])
        r = ev.anexar(self.h, {"cert": "leed", "criterio": "leed_reg", "nome": "Comprovante GBCI", "data": "2026-01-01", "responsavel": "Ana"}, "ana")
        self.assertTrue(r["ok"])
        lst = ev.anexos(self.h, "leed")
        self.assertEqual(lst[0]["nome"], "Comprovante GBCI")
        st = ev.avaliar_criterio(crit("leed_reg"), {"hoje": "2026-11-15", "servidor": ev.dados_servidor(self.h)})
        self.assertEqual((st["status"], st["evidencias"][0]["fonte"]), ("atendido", "anexo"))
        self.assertTrue(ev.remover(self.h, r["id"], "ana")["ok"])
        self.assertFalse(ev.remover(self.h, r["id"], "ana")["ok"])
        self.assertTrue(self.h.verificar_cadeia()[0])

    def test_risco_do_lugar(self):
        from physis_hub import municipio as mm
        db = self.h._db
        db.executescript(mm.ESQUEMA)
        db.execute("CREATE TABLE IF NOT EXISTS clima_local (id INTEGER PRIMARY KEY, dados TEXT, atualizado REAL)")
        db.execute("INSERT INTO clima_local VALUES(1, ?, 0)", (json.dumps({"lat": -22.525, "lon": -43.205}),))
        geo = {"tipo": "poligono", "coords": [[[-43.21, -22.53], [-43.20, -22.53], [-43.20, -22.52], [-43.21, -22.52]]]}
        db.execute("INSERT INTO mun_bairro(id,nome,risco,geometria,atualizado) VALUES('q','Quitandinha','alto',?,0)", (json.dumps(geo),))
        db.commit()
        self.assertEqual(ev.risco_do_lugar(db), {"risco_lugar": "alto", "bairro": "Quitandinha"})


class ModuloJS(unittest.TestCase):
    def test_contrato_e_sem_internet(self):
        for nome in ("function evidenciasPara(", "function telaEvidencias(", "global.evidenciasPara", "global.telaEvidencias", "base-evidencias"):
            self.assertIn(nome, JS)
        self.assertIsNone(re.search(r"https?://", JS))
        self.assertIsNone(re.search(r"\beval\s*\(|new Function", JS))
        self.assertNotRegex(JS.lower(), r"</script")
        self.assertNotIn("<h1", JS)

    def test_mesmos_textos(self):
        for frase in ("meses de consumo de água nas contas", "meses de consumo de energia nas contas", "medidos pelo hub",
                      "Cisterna em operação:", "Cisterna dimensionada:", "falta medição de operação", "Geração solar de",
                      "Linha de base de energia ajustada por clima e produção", "kWh/m² por ano (12 meses de contas)",
                      "falta a área construída para normalizar o indicador", "desviado do aterro (meta", "resíduos com rota definida",
                      "Inventário com escopos 1 e 2", "Inventário só com escopo 2 (eletricidade)", "espécies no plano de plantio",
                      "LBI 13.146/2015, art. 63", "pontos com calibração registrada", "sem registro de calibração", "Documento: ",
                      "Início preenchido (perfil e lugar)", "Matriz de riscos preenchida na Resiliência climática",
                      "no painel municipal", "investimento(s) com retorno", "Custo e retorno do sistema solar calculados", "vencida em "):
            self.assertIn(frase, JS, frase)
            self.assertIn(frase, (Path(ev.__file__)).read_text(encoding="utf-8"), frase)


class FontesEsgotoMateriais(unittest.TestCase):
    """Reúso de água, biogás e materiais (carbono incorporado e NBR 15575) como evidência."""
    def av(self, cid, d):
        return ev.avaliar_criterio(crit(cid), dict({"hoje": "2026-11-15"}, **d))

    def test_reuso(self):
        r = self.av("edge_w_chuva", {"esgoto": {"reuso_m3_dia": 0.65, "fonte": "Planejador", "atualizado": "2026-11-15"}})
        self.assertEqual(r["status"], "parcial")
        self.assertIn("Reúso de efluente tratado planejado: 0,65 m³/dia (Planejador)", [e["valor"] for e in r["evidencias"]])
        self.assertIsNone(ev.FONTES["agua_reuso"]({"esgoto": {"reuso_m3_dia": 0}}, {}, {}))

    def test_biogas(self):
        r = self.av("tr_comp", {"biogas": {"biogas_m3_dia": 0.2, "biodigestor_m3": 1.1, "fonte": "SustainKit"}})
        self.assertIn("Biodigestor dimensionado: 0,20 m³/dia de biogás, 1,1 m³ (SustainKit)", [e["valor"] for e in r["evidencias"]])
        self.assertEqual(r["status"], "parcial")

    def test_materiais_carbono_e_envoltoria(self):
        m = {"composicoes": [{"id": "x", "area_m2": 100, "kgco2e_m2": 50, "nbr15575": "atende"}, {"id": "y", "area_m2": 20, "nbr15575": "nao"}], "zona": "3"}
        r = self.av("edge_mat", {"materiais": m})
        self.assertIn("Carbono incorporado das composições: 5,0 tCO₂e (1 de 2 com valor por m²)", [e["valor"] for e in r["evidencias"]])
        f = ev.FONTES["materiais"]({"materiais": m}, {"modo": "envoltoria"}, {})
        self.assertEqual((f["status"], f["valor"]), ("parcial", "1 de 2 composições atendem à NBR 15575 (procedimento simplificado, zona 3)"))
        r2 = self.av("pb_desemp", {"materiais": m})
        self.assertEqual(r2["status"], "parcial")               # teto: o procedimento simplificado não comprova a norma inteira

    def test_mesmos_textos_js_e_python(self):
        for frase in ("Reúso de efluente tratado planejado: ", "Biodigestor dimensionado: ", "composições atendem à NBR 15575 (procedimento simplificado",
                      "composições escolhidas, sem carbono incorporado por m²", "Carbono incorporado das composições: ", "com valor por m²"):
            self.assertIn(frase, JS, frase)
            self.assertIn(frase, (Path(ev.__file__)).read_text(encoding="utf-8"), frase)
        self.assertIn("base-materiais", JS)
        self.assertIn("ebAtual", JS)


if __name__ == "__main__":
    unittest.main()
