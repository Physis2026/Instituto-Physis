"""Pegada do servidor (sistema digital): energia das maquinas da Physis, dupla contagem e fabricacao.

Protege:
1. Prioridade dos metodos: medidor do hub > RAPL > potencia nominal da classe (com carga); GPU pelo nvidia-smi.
2. Soma por hora (intervalo que cruza a hora e dividido) e kWh por mes projetado.
3. Dupla contagem: no lugar = "ja contado" (nao soma); fora = fonte propria (escopo 2 ou escopo 3 cat. 1).
4. Fabricacao amortizada (escopo 3 cat. 2) e conta de emissao com um fator dado.
5. Base de fatores (bloco "servidor") igual ao padrao embutido no modulo; tela do Carbono com a secao.
Leitores falsos (RAPL, nvidia-smi, carga) e relogio falso: nada le o computador de verdade.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
from physis_hub import carbono as cb  # noqa: E402
from physis_hub import pegada_servidor as ps  # noqa: E402
from physis_hub.hub import Hub  # noqa: E402

RAIZ = AQUI.parents[1]
BASE = RAIZ / "sistema" / "physis-fatores-emissao.json"
JS = RAIZ / "sistema" / "physis-carbono.js"
T0 = 1_780_000_000 // 3600 * 3600      # comeco de uma hora


class Relogio:
    def __init__(self, t=T0):
        self.t = float(t)

    def __call__(self):
        return self.t


def perto(tc, a, b, tol=0.01):
    tc.assertTrue(abs(a - b) <= tol * max(abs(b), 1e-9), f"{a} difere de {b}")


def novo(cfg=None, rapl=None, carga=None, gpus=None, medidor=None, modelo="", rel=None):
    rel = rel or Relogio()
    hub = Hub(":memory:", relogio=rel)
    F = cb.carregar(BASE) if BASE.is_file() else None
    pg = ps.PegadaServidor(hub, cfg or {}, F=F, relogio=rel, rapl=rapl or (lambda: None), carga=carga or (lambda: None),
                           gpus=gpus or (lambda: None), medidor=medidor or (lambda a, g: None), modelo=lambda: modelo)
    return hub, pg, rel


def kwh_tabela(hub, ident="hub"):
    return hub._db.execute("SELECT COALESCE(SUM(kwh),0) FROM servidor_energia WHERE equipamento=?", (ident,)).fetchone()[0]


class Leitores(unittest.TestCase):
    @unittest.skipIf(sys.platform.startswith("win"), "o Windows não aceita ':' no nome da pasta")
    def test_rapl_falso_le_so_pacotes(self):
        with tempfile.TemporaryDirectory() as d:
            for z, e in (("intel-rapl:0", 1000), ("intel-rapl:0:0", 999), ("intel-rapl:1", 50)):
                p = Path(d) / z
                p.mkdir()
                (p / "energy_uj").write_text(str(e))
                (p / "max_energy_range_uj").write_text("262143328850")
            r = ps.ler_rapl(d)
            self.assertEqual(set(r), {"intel-rapl:0", "intel-rapl:1"})
        self.assertIsNone(ps.ler_rapl("/caminho/que/nao/existe"))

    def test_nvidia_smi_falso(self):
        class R:
            returncode, stdout = 0, "35.20\n[N/A]\n120.5\n"
        self.assertEqual(ps.ler_gpus(lambda *a, **k: R()), [35.2, 120.5])
        class Erro:
            returncode, stdout = 9, ""
        self.assertIsNone(ps.ler_gpus(lambda *a, **k: Erro()))

    def test_classe_automatica(self):
        self.assertEqual(ps.classe_automatica("Raspberry Pi 5 Model B Rev 1.0", False), "rpi5")
        self.assertEqual(ps.classe_automatica("", True), "servidor_gpu")
        self.assertEqual(ps.classe_automatica("", False), "mini_pc")


class Metodos(unittest.TestCase):
    def test_nominal_com_carga_e_uma_hora(self):
        # mini PC: 8 W parado, 45 W em carga; carga 50% -> 26,5 W; 12 amostras de 5 min = 1 h
        hub, pg, rel = novo({"classe": "mini_pc"}, carga=lambda: 0.5)
        for _ in range(13):
            pg.amostrar()
            rel.t += 300
        perto(self, kwh_tabela(hub), 26.5 / 1000)
        linhas = hub._db.execute("SELECT hora, metodo FROM servidor_energia").fetchall()
        self.assertEqual(linhas, [(T0, "nominal")])
        r = pg.relatorio(agora=rel.t)
        perto(self, r["equipamentos"][0]["kwh_mes"], 26.5 * 730 / 1000)
        self.assertEqual(r["equipamentos"][0]["qualidade"], "estimado")

    def test_rapl_com_contador_que_da_a_volta(self):
        # 300 s a 20 W no processador = 6.000 J = 6e9 uJ; resto do mini PC 4 W
        estado = {"e": 10_000_000_000}
        def rapl():
            return {"intel-rapl:0": (estado["e"], 12_000_000_000)}
        hub, pg, rel = novo({"classe": "mini_pc"}, rapl=rapl, carga=lambda: 0.9)
        pg.amostrar()
        rel.t += 300
        estado["e"] = (10_000_000_000 + 6_000_000_000) % 12_000_000_000     # deu a volta
        g = pg.amostrar()
        self.assertEqual(g[0]["metodo"], "rapl")
        perto(self, g[0]["w"], 24.0)
        perto(self, kwh_tabela(hub), 24 * 300 / 3.6e6)

    def test_medidor_tem_prioridade_e_gpu_nao_entra_de_novo(self):
        leit = {"v": 100.0}
        hub, pg, rel = novo({"classe": "servidor_gpu", "medidor": {"ativo": "lugar01/no7", "grandeza": "energia_kwh", "tipo": "energia_kwh"}},
                            rapl=lambda: {"intel-rapl:0": (1, 0)}, gpus=lambda: [200.0],
                            medidor=lambda a, g: (leit["v"], rel.t))
        pg.amostrar()
        rel.t += 3600
        leit["v"] = 100.25
        g = pg.amostrar()
        self.assertEqual(g[0]["metodo"], "medidor")
        perto(self, kwh_tabela(hub), 0.25)
        perto(self, g[0]["w"], 250)
        self.assertEqual(pg.relatorio(agora=rel.t)["equipamentos"][0]["qualidade"], "medido")

    def test_medidor_parado_cai_para_estimativa(self):
        hub, pg, rel = novo({"classe": "rpi5", "medidor": {"ativo": "x", "grandeza": "potencia_w", "tipo": "potencia_w"}},
                            carga=lambda: 0.0, medidor=lambda a, g: (6.0, T0 - 99999))
        pg.amostrar()
        rel.t += 300
        self.assertEqual(pg.amostrar()[0]["metodo"], "nominal")

    def test_gpu_medida_troca_a_placa_nominal(self):
        # servidor_gpu parado: 150 W com 30 W da placa nominal; placas medidas 2 x 40 W -> 120 + 80 = 200 W
        hub, pg, rel = novo({"classe": "servidor_gpu", "gpus": 2}, carga=lambda: 0.0, gpus=lambda: [40.0, 40.0])
        pg.amostrar()
        rel.t += 300
        g = pg.amostrar()
        self.assertEqual(g[0]["metodo"], "nominal+gpu")
        perto(self, g[0]["w"], 150 - 2 * 30 + 80)
        self.assertTrue(pg.dicas()[0].startswith("A placa de vídeo ficou parada"))

    def test_intervalo_que_cruza_a_hora(self):
        hub, pg, rel = novo({"classe": "mini_pc"}, carga=lambda: 0.0, rel=Relogio(T0 + 3600 - 100))
        pg.amostrar()
        rel.t += 300                       # 100 s numa hora, 200 s na seguinte
        pg.amostrar()
        h = dict(hub._db.execute("SELECT hora, kwh FROM servidor_energia").fetchall())
        perto(self, h[T0], 8 * 100 / 3.6e6)
        perto(self, h[T0 + 3600], 8 * 200 / 3.6e6)

    def test_lacuna_longa_nao_vira_energia_inventada(self):
        hub, pg, rel = novo({"classe": "mini_pc"}, carga=lambda: 0.0)
        pg.amostrar()
        rel.t += 86400                      # hub ficou um dia parado
        pg.amostrar()
        perto(self, kwh_tabela(hub), 8 * 600 / 3.6e6)

    def test_host_extra_por_watts(self):
        cfg = {"classe": "rpi5", "hosts": [{"id": "ia", "nome": "Servidor de IA", "metodo": "watts", "watts": 200, "local": "fora", "pue": 1.4}]}
        hub, pg, rel = novo(cfg, carga=lambda: 0.0)
        pg.amostrar()
        rel.t += 3600
        pg.amostrar()
        perto(self, kwh_tabela(hub, "ia"), 200 * 600 / 3.6e6)   # 1 h sem amostra: a estimativa vale so 2 intervalos (600 s)
        r = pg.relatorio(agora=rel.t)
        ia = [e for e in r["equipamentos"] if e["id"] == "ia"][0]
        self.assertEqual(ia["metodo"], "fixo")
        perto(self, ia["kwh_mes"], 200 * 730 / 1000 * 1.4)


class Inventario(unittest.TestCase):
    EQ = [{"nome": "Hub", "kwh_ano": 1000, "local": "no_lugar", "controle": "proprio", "t_ano_fabricacao": 0.004, "qualidade": "medido"},
          {"nome": "IA no datacenter", "kwh_ano": 10000, "local": "fora", "controle": "proprio", "t_ano_fabricacao": 0.3},
          {"nome": "Nuvem", "kwh_ano": 2000, "local": "fora", "controle": "servico", "t_ano_fabricacao": 0}]

    def test_dupla_contagem(self):
        r = cb.servidor_inventario(self.EQ, 0.0385)
        perto(self, r["ja_contado_t"], 0.0385)          # 1 MWh dentro do lugar: so informacao
        perto(self, r["e2_t"], 10 * 0.0385)             # fora e proprio: escopo 2
        perto(self, r["e3_cat1_t"], 2 * 0.0385)         # hospedagem comprada: escopo 3 cat. 1
        perto(self, r["cat2_t"], 0.304)
        forcado = cb.servidor_inventario(self.EQ, 0.0385, "ja_contado")
        self.assertEqual(forcado["e2_t"], 0)

    def test_entra_no_calcular_do_carbono(self):
        F = cb.carregar(BASE)
        base = cb.calcular({"v": 2, "kwh": "12000", "rede": {"fator": "2023"}, "e3": {"cats": [1, 2]}}, {}, F)
        com = cb.calcular({"v": 2, "kwh": "12000", "rede": {"fator": "2023"}, "e3": {"cats": [1, 2]}}, {"servidor": self.EQ}, F)
        perto(self, com["e2_loc"] - base["e2_loc"], 10 * 0.0385)
        perto(self, com["e3"] - base["e3"], 2 * 0.0385 + 0.304)
        perto(self, com["total"], com["e1"] + com["e2_loc"] + com["e3"], tol=1e-9)
        sem = cb.calcular({"v": 2, "kwh": "12000", "rede": {"fator": "2023"}, "servidor": {"incluir": False}}, {"servidor": self.EQ}, F)
        perto(self, sem["e2_loc"], base["e2_loc"])

    def test_fabricacao_amortizada(self):
        hub, pg, rel = novo({"classe": "servidor_gpu", "gpus": 2})
        kg, t_ano, vida = pg._fabricacao(pg.equipamentos[0])
        self.assertEqual(kg, 1300 + 2 * 150)
        self.assertEqual(vida, 4)
        perto(self, t_ano, 1.6 / 4)

    def test_emissao_com_fator_dado(self):
        hub, pg, rel = novo({"classe": "mini_pc", "fator_rede": "0,1", "local": "fora"}, carga=lambda: 0.5)
        for _ in range(13):
            pg.amostrar()
            rel.t += 300
        r = pg.relatorio(agora=rel.t)
        self.assertEqual(r["fator_rede"], 0.1)
        kwh_ano = 26.5 * 730 / 1000 * 1.5 * 12            # fora: PUE padrao de datacenter 1,5
        perto(self, r["total"]["t_ano"], kwh_ano / 1000 * 0.1)
        perto(self, r["total"]["e2_somar_t"], kwh_ano / 1000 * 0.1)
        self.assertEqual(r["equipamentos"][0]["contagem"], "somar")

    def test_fator_segue_o_carbono_do_cliente(self):
        hub, pg, rel = novo({"classe": "rpi5"})
        hub.cliente_gravar("physis-carbono", json.dumps({"v": 2, "rede": {"fator": "2023"}}), 0, "teste")
        self.assertEqual(pg.fator()[0], 0.0385)

    def test_por_cliente_e_resumo_sem_detalhe(self):
        c = ps.por_cliente(30, 0.1, [{"id": "a", "peso": 2}, {"id": "b"}])
        perto(self, c[0]["kwh_mes"], 20)
        perto(self, c[1]["t_ano"], 10 * 12 / 1000 * 0.1)
        hub, pg, rel = novo({"classe": "rpi5", "clientes": [{"id": "a"}]})
        r = pg.relatorio(detalhado=False)
        self.assertNotIn("clientes", r)
        self.assertNotIn("fonte", r["equipamentos"][0])

    def test_config_de_ambiente(self):
        import os
        antes = os.environ.get("PHYSIS_PEGADA")
        try:
            os.environ["PHYSIS_PEGADA"] = "0"
            self.assertIsNone(ps.config_de({"pegada_servidor": {"classe": "rpi5"}}))
            os.environ["PHYSIS_PEGADA"] = '{"local": "fora"}'
            self.assertEqual(ps.config_de({"pegada_servidor": {"classe": "rpi5"}}), {"classe": "rpi5", "local": "fora"})
        finally:
            if antes is None:
                os.environ.pop("PHYSIS_PEGADA", None)
            else:
                os.environ["PHYSIS_PEGADA"] = antes


@unittest.skipUnless(BASE.is_file(), "só no repositório")
class BaseETela(unittest.TestCase):
    def test_bloco_servidor_igual_ao_padrao(self):
        S = json.loads(BASE.read_text(encoding="utf-8"))["servidor"]
        self.assertTrue(S["verificar"])
        self.assertIn("_fonte", S)
        for k, v in ps.PADRAO["classes"].items():
            for campo, x in v.items():
                self.assertEqual(S["classes"][k][campo], x, f"{k}.{campo}")
        self.assertEqual(S["pue"]["datacenter_padrao"], ps.PADRAO["pue"]["datacenter_padrao"])
        self.assertEqual(S["gpu_placa"]["kgco2e_fabricacao"], ps.PADRAO["gpu_placa"]["kgco2e_fabricacao"])

    def test_tela_carbono_tem_a_secao(self):
        js = JS.read_text(encoding="utf-8")
        for t in ("Pegada do servidor (sistema digital)", "/api/servidor/pegada", "parte do escopo 2 já contado",
                  "ITU-T L.1450", "Orientação Setorial de TIC", "exemplo"):
            self.assertIn(t, js)


if __name__ == "__main__":
    unittest.main()
