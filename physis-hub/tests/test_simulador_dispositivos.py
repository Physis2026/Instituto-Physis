"""Simulador de dispositivos (ferramentas/simulador_dispositivos.py) — ferramenta SÓ DE TESTE.

Protege:
1. A guarda: só hub neste computador (localhost, 127.x, ::1); outro endereço só com --permitir-remoto, e endereço com
   usuário/senha (truque "127.0.0.1@outro") nunca.
2. As linhas: válidas para o hub (protocolo V6, até 240 caracteres, nenhum campo fora da faixa), marcadas como simuladas,
   com as contas certas (S² = P² + Q², FP = P/S, I = S/V), ciclo diário, anomalias de propósito e sempre iguais com a
   mesma semente.
3. O hub aceita tudo pela rota dos aparelhos, com e sem chave, e a água vai para a lista da aba Água marcada.
4. --limpar tira só o que é simulado.
5. Veículos (frota, TIPO:VEI): linhas válidas em volta do centro, nível caindo parado um dia por semana, o carro saindo
   da cerca, e a frota do hub acha os alertas com os veículos e a cerca cadastrados.
"""
import importlib.util
import json
import math
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from physis_hub import protocolo
from physis_hub.clima import FUSO
from physis_hub.hub import Hub
from physis_hub.servidor import iniciar

RAIZ = Path(__file__).resolve().parents[2]
ARQ = RAIZ / "ferramentas" / "simulador_dispositivos.py"
FIM = datetime(2026, 11, 15, 12, 0, tzinfo=FUSO).timestamp()


def carregar():
    spec = importlib.util.spec_from_file_location("simulador_dispositivos", ARQ)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@unittest.skipUnless(ARQ.is_file(), "simulador fica só no repositório (não vai no pacote do cliente)")
class Guarda(unittest.TestCase):
    def setUp(self):
        self.s = carregar()

    def test_so_local(self):
        for url in ("http://localhost:8802", "http://127.0.0.1:8802/", "http://127.1.2.3", "https://[::1]:8443"):
            self.assertTrue(self.s.hub_local(url)[0], url)
        for url in ("http://192.168.0.10:8700", "http://example.com", "http://localhost.example.com",
                    "http://127.0.0.1@example.com", "http://user:x@localhost", "ftp://localhost", "localhost:8802",
                    "http://10.0.0.1"):
            self.assertFalse(self.s.hub_local(url)[0], url)

    def test_remoto_so_com_permissao(self):
        with self.assertRaises(SystemExit):
            self.s.conferir_hub("http://192.168.0.10:8700", False)
        self.assertEqual(self.s.conferir_hub("http://192.168.0.10:8700/", True), "http://192.168.0.10:8700")
        with self.assertRaises(SystemExit):                       # nem com permissão: usuário escondido no endereço
            self.s.conferir_hub("http://127.0.0.1@example.com", True)
        with self.assertRaises(SystemExit):
            self.s.main(["--hub", "http://example.com:8802", "--uma-vez"])


@unittest.skipUnless(ARQ.is_file(), "simulador fica só no repositório")
class Linhas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = carregar()
        cls.passo = 900.0
        cls.mundo = cls.s.Mundo(FIM - 21 * 86400, "teste", 80)
        cls.linhas, t = [], cls.mundo.inicio + cls.passo
        while t <= FIM:
            cls.linhas += [(t, l) for l in cls.mundo.linhas(t, cls.passo)]
            t += cls.passo
        cls.campos = [(t, protocolo.extrair_campos(l)) for t, l in cls.linhas]

    def de(self, tipo, no=None):
        return [(t, c) for t, c in self.campos if c.get("TIPO") == tipo and (no is None or c["ID"] == f"{no:02d}")]

    def test_validas_marcadas_e_curtas(self):
        self.assertEqual(len([l for _, l in self.linhas if ",TIPO:VEI," not in l]), 21 * 96 * 6)
        for _, l in self.linhas:
            ok, motivo, c = protocolo.validar_telemetria(l)
            self.assertTrue(ok, (motivo, l))
            self.assertNotIn("_FORA", c, l)
            self.assertLessEqual(len(l), protocolo.LINHA_MAX)
            self.assertTrue(l.endswith(",SIM:SIMULADO/teste"))
        self.assertEqual({c["TIPO"] for _, c in self.campos}, {"SOLO", "PLUV", "ENE", "HID", "SEC", "VEI"})
        self.assertEqual({c["ID"] for _, c in self.campos}, {"81", "82", "83", "84", "85", "86", "87", "88", "89"})

    def test_energia_coerente(self):
        for _, c in self.de("ENE"):
            p, q, s, v, i, fp = (float(c[k]) for k in ("PW", "QR", "S", "V", "I", "FP"))
            self.assertAlmostEqual(s, math.hypot(p, q), delta=0.002)
            self.assertAlmostEqual(fp, p / s, delta=0.002)
            self.assertAlmostEqual(i, s * 1000 / v, delta=0.02 + 0.001 * i)   # V vai com 1 casa decimal
            self.assertTrue(-1 <= fp <= 1 and v > 0 and s >= 0)
        self.assertTrue(any(float(c["PW"]) < 0 for _, c in self.de("ENE")), "meio-dia de sol injeta na rede")
        self.assertTrue(any(0 < float(c["FP"]) < 0.8 for _, c in self.de("ENE")), "fator de potência baixo (anomalia)")

    def test_ciclo_diario(self):
        def media(tipo, chave, h0, h1, no=None):
            v = [float(c[chave]) for t, c in self.de(tipo, no) if h0 <= datetime.fromtimestamp(t, FUSO).hour < h1
                 and c[chave] != "58.0"]                       # sem o salto de propósito
            return sum(v) / len(v)
        self.assertGreater(media("SOLO", "T", 13, 16, 81), media("SOLO", "T", 3, 6, 81) + 5)
        self.assertLess(media("SOLO", "UAR", 13, 16, 81), media("SOLO", "UAR", 3, 6, 81) - 10)
        self.assertGreater(media("SEC", "IRR", 11, 13), 300)
        self.assertEqual(media("SEC", "IRR", 0, 5), 0)
        self.assertTrue(any(c["IR1"] == "1" for _, c in self.de("SOLO")), "irrigação liga quando o solo seca")
        self.assertGreater(sum(float(c["CHI"]) for _, c in self.de("PLUV")), 0, "choveu em algum dia")

    def test_anomalias(self):
        self.assertTrue(any(c["T"] == "58.0" for _, c in self.de("SOLO", 81)), "salto de temperatura")
        por_dia = {}
        for t, c in self.de("SOLO", 82):
            por_dia.setdefault(datetime.fromtimestamp(t, FUSO).date(), set()).add(c["U2"])
        self.assertTrue(any(len(v) == 1 for v in list(por_dia.values())[1:-1]), "sensor travado um dia")
        self.assertLess(float(self.de("SOLO", 81)[-1][1]["BAT"]), 3.5, "bateria do nó 81 ficou baixa")
        noite = [float(c["Q"]) for t, c in self.de("HID") if datetime.fromtimestamp(t, FUSO).hour < 5]
        self.assertGreater(max(noite), 1.0, "vazamento de madrugada")
        calmo = self.s.Mundo(FIM - 3 * 86400, "teste", 80, anomalias=0.0)
        t, ls = calmo.inicio + 900, []
        while t <= FIM:
            ls += calmo.linhas(t, 900)
            t += 900
        self.assertFalse(any(",T:58.0," in l for l in ls))

    def test_mesma_semente_mesmas_linhas(self):
        a, b = self.s.Mundo(FIM - 86400, "x", 80), self.s.Mundo(FIM - 86400, "x", 80)
        self.assertEqual(a.linhas(FIM - 3600, 900), b.linhas(FIM - 3600, 900))
        self.assertNotEqual(a.linhas(FIM, 900), self.s.Mundo(FIM - 86400, "y", 80).linhas(FIM, 900))

    def test_agua_marcada(self):
        for x in self.mundo.agua(FIM):
            self.assertTrue(x["simulado"]); self.assertEqual(x["origem"], "simulador"); self.assertIn("SIMULADO", x["obs"])
            self.assertIn(x["ponto"], ("pre", "pos")); self.assertTrue(x["q"].endswith("Z"))

    def test_hub_aceita_tudo_e_avisa(self):
        h = Hub(relogio=lambda: FIM)
        h.instancia = {}
        r = h.receber_lote("\n".join(l for _, l in self.linhas))
        self.assertEqual((r["aceitas"], r["descartadas"]), (len(self.linhas), 0))
        textos = " ".join(a["texto"] for a in h.alertas())
        self.assertIn("bateria baixa", textos)
        self.assertTrue(h._db.execute("SELECT COUNT(*) FROM clima_observado WHERE origem='physis'").fetchone()[0])
        self.assertTrue(h._db.execute("SELECT COUNT(*) FROM medicao WHERE grandeza='fp'").fetchone()[0])


@unittest.skipUnless(ARQ.is_file(), "simulador fica só no repositório")
class PelaRedeELimpar(unittest.TestCase):
    def setUp(self):
        self.s = carregar()
        self.dir = tempfile.TemporaryDirectory()
        self.banco = os.path.join(self.dir.name, "physis-hub.db")
        self.h = Hub(self.banco)
        self.h.instancia = {}
        self.srv = iniciar(self.h, 0, endereco="127.0.0.1", instancia={"login": False})
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.h.fechar()
        self.dir.cleanup()

    def test_envia_com_chave_grava_agua_e_limpa(self):
        cli = self.s.Hub(self.url)
        st, _ = cli.pedir("POST", "/api/conta/criar", {"nome": "Teste", "usuario": "teste", "senha": "senha-bem-longa-1"})
        self.assertEqual(st, 200)
        cli = self.s.Hub(self.url)
        cli.entrar("teste", "senha-bem-longa-1")
        mundo = self.s.Mundo(FIM - 86400, "teste", 80)
        cli.preparar_chaves(mundo)
        self.assertEqual(sorted(cli.chaves), [81, 82, 83, 84, 85, 86, 87, 88, 89])
        linhas = mundo.linhas(FIM - 900, 900) + mundo.linhas(FIM, 900)
        self.assertEqual(cli.enviar(linhas)["aceitas"], len(linhas))
        sem_chave = self.s.Hub(self.url)                              # rede local: sem chave também entra
        mais = mundo.linhas(FIM + 900, 900)
        self.assertEqual(sem_chave.enviar(mais)["aceitas"], len(mais))
        self.assertEqual(cli.preparar_frota(mundo), 3)                # os 3 veículos SIMULADOS e a cerca de teste
        self.assertEqual(cli.preparar_frota(mundo), 0)                # de novo: não duplica
        # água: uma leitura de verdade já existe e fica
        real = [{"q": "2026-11-14T12:00:00.000Z", "ponto": "pos", "ph": 7.0, "origem": "manual"}]
        self.h.cliente_gravar("physis-ph-leituras", json.dumps(real), 0, "pessoa")
        self.assertTrue(cli.gravar_agua(mundo.agua(FIM)))
        lista = json.loads(self.h.cliente_ler(chave="physis-ph-leituras")["physis-ph-leituras"]["valor"])
        self.assertEqual((len(lista), sum(1 for x in lista if x.get("simulado"))), (3, 2))
        rotulos = [r[0] for r in self.h._db.execute("SELECT rotulo FROM dispositivo_chave WHERE revogado IS NULL")]
        self.assertTrue(rotulos and all(r.startswith("SIMULADO / teste") for r in rotulos))
        # uma linha de aparelho de verdade (sem a marca) não pode sumir no --limpar
        self.h.receber_lote("ID:03,U1:45.2,IR1:0,U2:50.0,IR2:0,T:27.5,UAR:63.5,BAT:3.87,TS:1794600000")
        with self.assertRaises(SystemExit):                          # hub ligado: recusa
            self.s.main(["--limpar", "--banco", self.banco, "--hub", self.url])
        r = self.s.limpar(Path(self.banco))
        self.assertEqual((r["leituras"], r["chaves"], r["agua"]), (len(linhas) + len(mais), 9, 2))
        self.assertGreater(r["frota"], 0)
        db = sqlite3.connect(self.banco)
        try:
            self.assertEqual([x[0] for x in db.execute("SELECT no FROM leitura")], [3])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM dispositivo_chave WHERE revogado IS NULL").fetchone()[0], 0)
            agua = json.loads(db.execute("SELECT valor FROM cliente_estado WHERE chave='physis-ph-leituras'").fetchone()[0])
            self.assertEqual(agua, real)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(ARQ.is_file(), "simulador fica só no repositório")
class Veiculos(unittest.TestCase):
    """Frota SIMULADA: 3 veículos em volta do centro, com as duas anomalias de propósito."""

    @classmethod
    def setUpClass(cls):
        cls.s = carregar()
        cls.centro = (-15.79, -47.88)
        cls.mundo = cls.s.Mundo(FIM - 8 * 86400, "teste", 80, centro=cls.centro)
        cls.linhas, t = [], cls.mundo.inicio + 900
        while t <= FIM:
            cls.linhas += [l for l in cls.mundo.linhas(t, 900) if ",TIPO:VEI," in l]
            t += 900

    def test_linhas_validas_em_volta_do_centro(self):
        self.assertGreater(len(self.linhas), 1000)
        for l in self.linhas:
            ok, motivo, c = protocolo.validar_telemetria(l)
            self.assertTrue(ok, (motivo, l))
            self.assertNotIn("_FORA", c, l)
            self.assertLessEqual(len(l), protocolo.LINHA_MAX)
            self.assertTrue(l.endswith(",SIM:SIMULADO/teste"))
            self.assertLess(abs(float(c["LAT"]) - self.centro[0]), 0.1)
            self.assertLess(abs(float(c["LON"]) - self.centro[1]), 0.1)
        self.assertEqual({protocolo.extrair_campos(l)["ID"] for l in self.linhas}, {"87", "88", "89"})
        self.assertTrue(any("HOR:" in l for l in self.linhas if l.startswith("ID:89,")))

    def test_hub_acha_as_anomalias(self):
        from physis_hub import carbono, frota
        h = Hub(relogio=lambda: FIM + 60)
        h.instancia = {}
        f = frota.Frota(h, fatores=carbono.carregar())
        h.frota_receptor = f.receber_v6
        for n, (placa, tipo, comb, tanque, cons, un) in self.s.VEICULOS.items():
            f.gravar_veiculo({"tipo": tipo, "placa": placa, "combustivel": comb, "tanque_l": tanque, "consumo_esperado": cons,
                              "consumo_unidade": un, "no": self.mundo.ident(n)}, "teste")
        f.gravar_cerca({"nome": "Cerca de teste", "poligono": [list(self.mundo.desloca(a, b)) for a, b in self.s.CERCA_KM]}, "teste")
        r = h.receber_lote("\n".join(self.linhas))
        self.assertEqual((r["aceitas"], r["descartadas"]), (len(self.linhas), 0))
        tipos = {a["tipo"] for a in f.estado()["alertas"]}
        self.assertIn("queda_nivel", tipos)                       # nível caindo parado (vazamento ou furto)
        self.assertIn("cerca", tipos)                             # o carro saiu da cerca
        self.assertNotIn("consumo", tipos)                        # consumo normal: nenhum alarme falso
        self.assertEqual(f.estado()["para_carbono"], [])          # simulado não vai para o Carbono
        calmo = self.s.Mundo(FIM - 8 * 86400, "teste", 80, anomalias=0.0, centro=self.centro)
        self.assertEqual(calmo.anomalias, 0.0)
