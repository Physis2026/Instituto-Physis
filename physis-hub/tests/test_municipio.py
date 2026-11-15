"""Painel municipal de resiliência (municipio.py e web/municipio.html), sem internet: fontes de mentira.

Protege:
1. Limiares de deslizamento: padrão 40/80 mm (24 h) e 60/120 mm (72 h), trocáveis; atenção < alerta.
2. CEMADEN: todas as estações do município, só valem as que mandaram dado nas últimas 3 h; "-" = 0 mm.
3. Bairros por GeoJSON (polígono, multipolígono, ponto) e CSV; classes R1 a R4; fora do Brasil é recusado.
4. Alerta por bairro: estação do próprio bairro; sem estação, a maior chuva do município; rio pelo GloFAS;
   aviso do INMET vale para o município todo. Alerta abre, atualiza (guarda o nível máximo) e encerra com horário.
5. Modo público sem dado pessoal (pluviômetro particular só aparece se marcado público; sem número do nó);
   operador vê configuração e erros.
6. CSV exportado com separador ; e BOM.
7. A página não chama a internet, tem um h1 só, PT/EN, tema claro/escuro e só cores da paleta.
"""
import json
import re
import unittest
from datetime import datetime, timezone
from pathlib import Path

from physis_hub import municipio as mm
from physis_hub.hub import Hub

AGORA = datetime(2026, 11, 15, 15, 0, tzinfo=timezone.utc).timestamp()
IBGE = "3303906"          # Petrópolis


def est(nome, a24, a72, hora="15/11/26 14:30", ibge=IBGE, a1="0.4"):
    return {"codibge": int(ibge), "nomeestacao": nome, "codestacao": "33" + nome[:3], "datahoraUltimovalor": hora,
            "acc1hr": a1, "acc24hr": a24, "acc72hr": a72, "cidade": "PETROPOLIS"}


CEMADEN = [est("Quitandinha", "45.2", "70.1"), est("Centro", "-", "12.0"), est("Velha", "99", "200", hora="14/11/26 01:00"),
           est("Outra cidade", "150", "300", ibge="3304557")]
INMET = {"hoje": [{"id": 77, "descricao": "Acumulado de Chuva", "severidade": "Perigo", "inicio": "2026-11-15 10:00:00",
                   "fim": "2099-11-16 10:00:00", "geocodes": "3303906,3304557", "riscos": "R", "instrucoes": "I"},
                  {"id": 78, "descricao": "Ventos", "severidade": "Perigo Potencial", "geocodes": "3550308"}], "futuro": []}
GEO = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"nome": "Quitandinha", "risco": "R4"},
     "geometry": {"type": "Polygon", "coordinates": [[[-43.21, -22.53], [-43.20, -22.53], [-43.20, -22.52], [-43.21, -22.53]]]}},
    {"type": "Feature", "properties": {"name": "Centro", "classe": "médio"},
     "geometry": {"type": "MultiPolygon", "coordinates": [[[[-43.18, -22.51], [-43.17, -22.51], [-43.17, -22.50], [-43.18, -22.51]]]]}},
    {"type": "Feature", "properties": {"NOME": "Itaipava"}, "geometry": {"type": "Point", "coordinates": [-43.13, -22.40]}}]}


class FalsoBuscar:
    def __init__(self):
        self.urls = []

    def __call__(self, url, timeout=15.0):
        self.urls.append(url)
        if "cemaden" in url:
            return CEMADEN
        if "avisos" in url:
            return INMET
        raise OSError("sem rede no teste")


def rio_falso(lat, lon):
    return {"ok": True, "nivel": "atencao", "historico": {"p90": 50.0, "p99": 120.0},
            "previsao": {"vazao": [30.0, 61.5, None, 40.0]}, "avisos": []}


def montar(relogio=None):
    relogio = relogio or [AGORA]
    h = Hub(":memory:", relogio=lambda: relogio[0])
    b = FalsoBuscar()
    m = mm.Municipio(h, buscar=b, rio=rio_falso, relogio=lambda: relogio[0])
    return h, m, b, relogio


CFG = {"ibge": IBGE, "uf": "rj", "municipio": "Petrópolis", "lat": -22.505, "lon": -43.18,
       "rios": [{"id": "piabanha", "nome": "Rio Piabanha", "lat": -22.51, "lon": -43.17}],
       "pluviometros": [{"no": 7, "nome": "Escola X", "lat": -22.52, "lon": -43.2, "bairro": "quitandinha"},
                        {"no": 8, "nome": "Praça", "bairro": "centro", "publico": True}]}


class Funcoes(unittest.TestCase):
    def test_limiares_padrao_e_troca(self):
        lim = mm.LIMIARES_PADRAO
        self.assertEqual((lim["atencao_24h"], lim["alerta_24h"], lim["atencao_72h"], lim["alerta_72h"]), (40, 80, 60, 120))
        self.assertIsNone(mm.nivel_chuva(39.9, 59.9, lim))
        self.assertEqual(mm.nivel_chuva(40, 0, lim), "atencao")
        self.assertEqual(mm.nivel_chuva(0, 60, lim), "atencao")
        self.assertEqual(mm.nivel_chuva(80, 0, lim), "alerta")
        self.assertEqual(mm.nivel_chuva(10, 120, lim), "alerta")
        novo, _ = mm.validar_limiares({"atencao_24h": 30, "alerta_24h": 50})
        self.assertEqual(mm.nivel_chuva(31, 0, novo), "atencao")
        self.assertEqual(mm.validar_limiares({"atencao_24h": 90})[0], None)          # atenção acima do alerta
        self.assertEqual(mm.validar_limiares({"alerta_72h": -1})[0], None)

    def test_cemaden_por_municipio_e_janela(self):
        e = mm.estacoes_cemaden(CEMADEN, IBGE, AGORA, mm.LIMIARES_PADRAO)
        self.assertEqual([x["nome"] for x in e], ["Quitandinha", "Centro", "Velha"])     # outra cidade fora
        q, c, v = e
        self.assertTrue(q["ativa"]) ; self.assertEqual(q["nivel"], "atencao")
        self.assertEqual(c["mm_24h"], 0.0)              # "-" = não choveu
        self.assertFalse(v["ativa"]) ; self.assertIsNone(v["mm_24h"]) ; self.assertIsNone(v["nivel"])

    def test_inmet_filtra_municipio_e_severidade(self):
        a = mm.ler_avisos_inmet(INMET, IBGE)
        self.assertEqual(len(a), 1)
        self.assertEqual((a[0]["evento"], a[0]["nivel"]), ("Acumulado de Chuva", "alerta"))
        self.assertEqual(mm.ler_avisos_inmet([{"descricao": "x", "severidade": "Perigo Potencial", "municipios": [IBGE]}], IBGE)[0]["nivel"], "atencao")
        self.assertEqual(mm.ler_avisos_inmet({"hoje": []}, IBGE), [])

    def test_riscos(self):
        for v, k in (("R1", "baixo"), ("2", "medio"), ("Alto", "alto"), ("muito alto", "muito_alto"), ("MUITO_ALTO", "muito_alto"),
                     ("very high", "muito_alto"), ("Médio", "medio")):
            self.assertEqual(mm.normalizar_risco(v), k)
        self.assertIsNone(mm.normalizar_risco("enorme"))

    def test_importar_geojson(self):
        b = mm.importar_geojson(GEO)
        self.assertEqual([x["nome"] for x in b], ["Quitandinha", "Centro", "Itaipava"])
        self.assertEqual([x["risco"] for x in b], ["muito_alto", "medio", "baixo"])
        self.assertTrue(b[2]["revisar"])                 # sem classe: entra baixo e pede revisão
        self.assertEqual(b[0]["geometria"]["tipo"], "poligono")
        self.assertEqual(b[2]["geometria"], {"tipo": "ponto", "coords": [-43.13, -22.4]})
        ruim = json.loads(json.dumps(GEO)); ruim["features"][2]["geometry"]["coordinates"] = [2.35, 48.85]   # Paris
        with self.assertRaises(ValueError):
            mm.importar_geojson(ruim)
        with self.assertRaises(ValueError):
            mm.importar_geojson({"type": "Feature"})

    def test_importar_csv(self):
        b = mm.importar_csv("nome;risco;lat;lon\nMorro A;R3;-22,51;-43,19\nVale;;-22.49;-43.15\n")
        self.assertEqual([(x["nome"], x["risco"]) for x in b], [("Morro A", "alto"), ("Vale", "baixo")])
        self.assertEqual(b[0]["geometria"]["coords"], [-43.19, -22.51])
        with self.assertRaises(ValueError):
            mm.importar_csv("nome,risco\nA,R1\n")

    def test_ler_importacao_da_rota(self):
        self.assertEqual(len(mm.ler_importacao(json.dumps(GEO).encode("utf-8"), "application/json")), 3)
        self.assertEqual(len(mm.ler_importacao("﻿nome;risco;lat;lon\nA;R2;-22.5;-43.2\n".encode("utf-8"), "text/csv")), 1)
        with self.assertRaises(ValueError):
            mm.ler_importacao(b'{"type":"FeatureCollection","features":[{"geometry":{"type":"Point","coordinates":[NaN,1]}}]}')

    def test_chuva_physis_soma_por_janela(self):
        L = [("ID:07,TIPO:PLUV,CHI:2.5,PUL:9", AGORA - 600), ("ID:07,TIPO:PLUV,CHI:10", AGORA - 5 * 3600),
             ("ID:07,TIPO:PLUV,CHI:30", AGORA - 48 * 3600), ("ID:03,TIPO:SOLO,CHI:99", AGORA)]
        r = mm.chuva_physis(L, AGORA)
        self.assertEqual(list(r), [7])
        self.assertEqual((r[7]["mm_1h"], r[7]["mm_24h"], r[7]["mm_72h"]), (2.5, 12.5, 42.5))


class NoHub(unittest.TestCase):
    def setUp(self):
        self.h, self.m, self.b, self.rel = montar()

    def test_sem_config(self):
        e = self.m.estado()
        self.assertFalse(e["configurado"])
        self.assertFalse(self.m.consultar()["ok"])
        self.assertEqual(self.b.urls, [])

    def test_config_valida(self):
        self.assertFalse(self.m.definir_config({"ibge": "123", "uf": "RJ"})["ok"])
        self.assertFalse(self.m.definir_config(dict(CFG, lat=48.0))["ok"])
        r = self.m.definir_config(CFG, "ana")
        self.assertTrue(r["ok"])
        self.assertEqual(r["config"]["uf"], "RJ")
        self.assertEqual(r["config"]["limiares"], mm.LIMIARES_PADRAO)

    def _pronto(self):
        self.m.definir_config(CFG, "ana")
        self.m.importar(mm.importar_geojson(GEO), "ana", substituir=True)
        self.assertTrue(self.m.editar_bairro({"id": "quitandinha", "estacoes": ["Quitandinha"]})["ok"])
        self.assertTrue(self.m.editar_bairro({"id": "centro", "rio": "piabanha"})["ok"])
        return self.m.consultar()

    def test_alertas_por_bairro(self):
        r = self._pronto()
        self.assertEqual(r["consultas"], {"cemaden": True, "inmet": True, "rios": 1})
        self.assertTrue(any("uf=RJ" in u for u in self.b.urls))
        al = {(a["bairro"], a["tipo"]): a for a in self.m.alertas()}
        # Quitandinha: estação própria com 45 mm/24 h → atenção
        self.assertEqual(al[("quitandinha", "chuva")]["nivel"], "atencao")
        self.assertIn("Quitandinha", al[("quitandinha", "chuva")]["fonte"])
        # Itaipava: sem estação → maior do município (também Quitandinha), marcado como estimado
        self.assertIn("maior do município", al[("itaipava", "chuva")]["fonte"])
        # Centro: rio acima do p90 → atenção de inundação; e chuva pela maior do município também
        self.assertEqual(al[("centro", "rio")]["nivel"], "atencao")
        # INMET: município inteiro
        self.assertEqual(al[("", "inmet")]["nivel"], "alerta")
        e = self.m.estado()
        self.assertEqual({b["id"]: b["nivel"] for b in e["bairros"]}["quitandinha"], "atencao")

    def test_alerta_abre_sobe_e_encerra(self):
        self._pronto()
        a0 = [a for a in self.m.alertas() if a["bairro"] == "quitandinha" and a["tipo"] == "chuva"][0]
        inicio = a0["inicio"]
        CEMADEN[0]["acc24hr"] = "85"
        try:
            self.rel[0] += 900
            self.m.consultar()
            a1 = [a for a in self.m.alertas() if a["id"] == a0["id"]][0]
            self.assertEqual((a1["nivel"], a1["nivel_max"], a1["inicio"]), ("alerta", "alerta", inicio))
            CEMADEN[0]["acc24hr"], CEMADEN[0]["acc72hr"] = "5", "10"
            self.rel[0] += 900
            self.m.consultar()
            a2 = [a for a in self.m.alertas() if a["id"] == a0["id"]][0]
            self.assertFalse(a2["aberto"])
            self.assertEqual((a2["nivel_max"], a2["fim"]), ("alerta", self.rel[0]))
        finally:
            CEMADEN[0]["acc24hr"], CEMADEN[0]["acc72hr"] = "45.2", "70.1"
        self.assertTrue(self.h.verificar_cadeia()[0])

    def test_pluviometro_physis_e_privacidade(self):
        self._pronto()
        self.h._db.execute("INSERT INTO leitura(no,ts,recebido,origem,linha) VALUES(7,0,?,'receptor','ID:07,TIPO:PLUV,CHI:95')", (AGORA - 60,))
        self.h._db.commit()
        self.m.reavaliar()
        pub, op = self.m.estado(), self.m.estado(operador=True)
        self.assertEqual([p["nome"] for p in pub["pluviometros"]], ["Praça"])        # o particular não aparece
        self.assertNotIn("no", pub["pluviometros"][0])
        self.assertNotIn("config", pub) ; self.assertNotIn("erros", pub)
        self.assertEqual(len(op["pluviometros"]), 2)
        self.assertIn("config", op)
        al = [a for a in self.m.alertas() if a["bairro"] == "quitandinha" and a["tipo"] == "chuva"][0]
        self.assertEqual(al["nivel"], "alerta")            # 95 mm no pluviômetro Physis do bairro
        self.assertIn("Physis", al["fonte"])
        texto = json.dumps(pub, ensure_ascii=False)
        for proibido in ("ana", "@", "cpf", "telefone\":\"9"):
            self.assertNotIn(proibido, texto)

    def test_editar_bairro(self):
        self._pronto()
        self.assertFalse(self.m.editar_bairro({"id": "centro", "risco": "enorme"})["ok"])
        self.assertFalse(self.m.editar_bairro({"id": "centro", "rio": "nilo"})["ok"])
        self.assertFalse(self.m.editar_bairro({"id": "nao-existe"})["ok"])
        self.assertTrue(self.m.editar_bairro({"id": "itaipava", "risco": "R2"})["ok"])
        self.assertEqual({b["id"]: b["risco"] for b in self.m.bairros()}["itaipava"], "medio")
        self.assertTrue(self.m.editar_bairro({"id": "itaipava", "apagar": True})["ok"])
        self.assertEqual(len(self.m.bairros()), 2)

    def test_sem_rede_guarda_erro(self):
        self.m.definir_config(CFG)
        def sem_rede(url, timeout=15.0):
            raise OSError("caiu")
        self.m.buscar = sem_rede
        self.m.consultar()
        e = self.m.estado(operador=True)
        self.assertIn("cemaden", e["erros"])
        self.assertEqual(e["cemaden"]["estacoes"], [])

    def test_csv(self):
        self._pronto()
        for tipo, cab in (("alertas", "bairro;tipo;nivel_atual"), ("chuva", "fonte;estacao"), ("bairros", "id;nome;risco")):
            t = self.m.exportar_csv(tipo)
            self.assertTrue(t.startswith("﻿" + cab), tipo)
        self.assertIn("Quitandinha", self.m.exportar_csv("chuva"))
        self.assertNotIn("Escola X", self.m.exportar_csv("chuva"))          # particular: só para o operador
        self.assertIn("Escola X", self.m.exportar_csv("chuva", operador=True))


class Pagina(unittest.TestCase):
    HTML = Path(__file__).resolve().parents[1] / "web" / "municipio.html"

    def setUp(self):
        self.t = self.HTML.read_text(encoding="utf-8")

    def test_sem_internet(self):
        self.assertIsNone(re.search(r"""(src|href)\s*=\s*["']https?://""", self.t))
        self.assertIsNone(re.search(r"""fetch\(\s*["'`]https?://""", self.t))
        self.assertNotIn("@import", self.t)

    def test_um_titulo_e_idiomas(self):
        self.assertEqual(len(re.findall(r"<h1[\s>]", self.t)), 1)
        self.assertIn('lang="pt-BR"', self.t)
        self.assertIn("en:", self.t)
        self.assertIn('data-tema', self.t)
        for rota in ("/api/municipio/publico", "/api/municipio/exportar", "X-Physis-CSRF"):
            self.assertIn(rota, self.t)

    def test_so_cores_da_paleta(self):
        paleta = set(re.findall(r"#[0-9A-Fa-f]{6}", (Path(__file__).resolve().parents[1] / "docs" / "PALETA.md").read_text(encoding="utf-8")))
        paleta = {c.upper() for c in paleta}
        usadas = {c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}\b", self.t)}
        self.assertEqual(usadas - paleta, set())


if __name__ == "__main__":
    unittest.main()
