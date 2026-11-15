"""Servidor verde (EM DESENVOLVIMENTO): dimensionamento, catalogo de modulos e conferencias de compatibilidade.

Protege:
1. Regras de mesa: memoria de video, crescimento do banco, RAID, restauracao, nobreak, solar, calor (BTU/h e TR),
   PUE e curva de eficiencia da fonte.
2. Espelho: physis_hub/servidor_verde.py da o mesmo resultado que sistema/physis-servidor-verde.js no perfil
   Casa Physis (numeros copiados da tela, rodada no navegador em 15/11/2026).
3. Catalogo sistema/physis-servidor-catalogo.json: campos de cada modulo, licencas, dependencias, perfis validos,
   custos sem preco inventado, estado "dev".
4. Conferencias: placa de video no Raspberry Pi, vLLM sem placa, fonte sem folga, memoria curta, encaixes PCIe,
   Proxmox no ARM, dependencias, disco menor que o crescimento.
5. Contrato da tela: um so <h1>Servidor verde</h1>, selo "Em desenvolvimento", mapa PT/EN, sem internet.
"""
import json
import re
import sys
import unittest
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
from physis_hub import servidor_verde as sv  # noqa: E402

RAIZ = AQUI.parents[1]
JS = RAIZ / "sistema" / "physis-servidor-verde.js"
CAT = RAIZ / "sistema" / "physis-servidor-catalogo.json"
NO_REPO = CAT.is_file()


def perto(tc, a, b, tol=0.01):
    tc.assertTrue(abs(a - b) <= tol * max(abs(b), 1e-9), f"{a} difere de {b}")


class RegrasDeMesa(unittest.TestCase):
    def test_vram(self):
        perto(self, sv.vram_gb(7, 4), 4.2)                 # 7 × 0,5 byte × 1,2
        perto(self, sv.vram_gb(70, 4), 42.0)
        perto(self, sv.vram_gb(13, 8), 15.6)
        perto(self, sv.vram_treino_gb(7, 4), 6.3)          # QLoRA ≈ 1,5 × rodar
        perto(self, sv.vram_treino_gb(7, 4, "completo"), 134.4)
        self.assertEqual(sv.gpus_necessarias(42, 16), 3)
        self.assertEqual(sv.gpus_necessarias(42, 16, 30), 4)    # 54,6 GB
        self.assertEqual(sv.gpus_necessarias(0, 8), 0)

    def test_crescimento_do_banco_e_disco(self):
        # 60 sensores × 1 leitura/min × 525.600 min/ano × 200 B × 10 anos
        perto(self, sv.banco_gb(60, 1, 200, 10), 63.072)
        perto(self, sv.disco_bruto_gb(1000, "raid1", 2), 2000)
        perto(self, sv.disco_bruto_gb(900, "raid5", 4), 1200)
        perto(self, sv.disco_bruto_gb(800, "raid6", 6), 1200)
        perto(self, sv.tempo_restauro_h(450, 100), 10)      # 450 GB × 8.000 ÷ 100 Mbps ÷ 3.600

    def test_nobreak(self):
        u = sv.nobreak(600, 500, 30, "lifepo4", 24)
        perto(self, u["va"], 600 / 0.9 * 1.25)
        perto(self, u["bateria_wh"], 500 * 0.5 / (0.9 * 0.9))
        perto(self, u["bateria_ah"], u["bateria_wh"] / 24)
        perto(self, sv.nobreak(600, 500, 30, "chumbo", 12)["bateria_wh"], 250 / (0.5 * 0.9))

    def test_solar(self):
        s = sv.solar(3.6, 4.5, 0.75, 1.0, 150, 14, 1, "lifepo4")
        perto(self, s["kwp"], 3.6 / (4.5 * 0.75))          # 1,067 kWp
        perto(self, s["bateria_kwh"], (150 * 14 / 1000 + 3.6) / (0.9 * 0.9))
        perto(self, s["ger_dia_kwh"], 3.6)
        self.assertEqual(sv.solar(3.6, 0, 0.75)["kwp"], 0)

    def test_calor_e_pue(self):
        perto(self, sv.btu_h(1000), 3412)
        perto(self, sv.tr(1000), 3412 / 12000)
        perto(self, sv.pue(10, 3, 0.5, 0.1), 1.36)
        self.assertEqual(sv.pue(0, 1), 0)

    def test_curva_da_fonte(self):
        c = {"10": 0.80, "20": 0.87, "50": 0.90, "100": 0.87}
        perto(self, sv.eficiencia_curva(c, 0.35), 0.885)
        perto(self, sv.eficiencia_curva(c, 0.05), 0.80)
        perto(self, sv.eficiencia_curva(c, 1.2), 0.87)

    def test_componente_e_ciclo_da_ia(self):
        wm, wp, wo = sv.w_componente({"qtd": 2, "w_ocioso": 12, "w_carga": 130, "ciclo": "", "tipo": "gpu"}, 0.25)
        perto(self, wm, 2 * (12 + 118 * 0.25))
        self.assertEqual((wp, wo), (260, 24))


# Perfil Casa Physis como a tela cria (hsp 4,5; tarifa 0,9; solar R$ 4.000/kWp e bateria R$ 3.000/kWh digitados para o teste)
P_CASA = json.loads(r'''{"nome_local":"","lat":"","lon":"","hsp":4.5,"hsp_base":"critico","fator_rede":"","fator_ano":"","tarifa":"0,9","instalacoes":1,"usuarios_sim":8,"sensores":60,"leituras_min":1,"retencao_anos":10,"req_min":60,"bi_usuarios":2,"geo_camadas":10,"geo_tiles_gb":20,"calc_rodadas_dia":6,"calc_min_rodada":10,"calc_nucleos_rodada":2,"docs_dia":30,"usar_selecao":true,"ia_ativa":true,"ia_params_b":7,"ia_bits":4,"ia_tokens_dia":300000,"ia_usuarios_sim":3,"ia_tok_s":"","treino_h_mes":20,"treino_modo":"qlora","gpu_qtd":2,"gpu_vram_gb":8,"gpu_alt_qtd":4,"gpu_alt_vram_gb":16,"folga_pct":30,"bytes_leitura":200,"arquivos_gb_ano":30,"modelos_gb":"","raid":"raid1","discos":2,"snapshots_pct":20,"backup_versoes":7,"mudanca_dia_pct":2,"backup_mbps":50,"janela_backup_h":6,"usuarios_remotos":5,"kbps_usuario":500,"sync_mb_dia":100,"latencia_ms":40,"vpn":true,"link_reserva":"4g","componentes":[{"nome":"Raspberry Pi 5 com SSD","tipo":"cpu","qtd":1,"w_ocioso":3.5,"w_carga":10,"ciclo":0.2,"fonte":false},{"nome":"Servidor de IA: placa-mãe, processador e memória","tipo":"cpu","qtd":1,"w_ocioso":45,"w_carga":150,"ciclo":0.3,"fonte":true},{"nome":"Placa de vídeo 8 GB","tipo":"gpu","qtd":2,"w_ocioso":12,"w_carga":130,"ciclo":"","fonte":true},{"nome":"SSD NVMe","tipo":"disco","qtd":2,"w_ocioso":1,"w_carga":5,"ciclo":0.3,"fonte":true},{"nome":"Switch de rede","tipo":"rede","qtd":1,"w_ocioso":5,"w_carga":8,"ciclo":0.5,"fonte":false},{"nome":"Roteador","tipo":"rede","qtd":1,"w_ocioso":8,"w_carga":12,"ciclo":0.5,"fonte":false}],"fonte_80plus":"ouro","ups_autonomia_min":30,"ups_bateria":"lifepo4","ups_tensao":24,"solar_modo":"dedicado","solar_fracao":100,"pr":0.75,"horas_noite":14,"dias_nublados":1,"agendar_ia_solar":true,"cop":3,"free_cooling":false,"perdas_ups_pct":5,"iluminacao_w":0,"rack_u":"","ruido_ok":true,"poeira":"filtro","fator_dc":"","pue_dc":1.5,"custo_kwp":4000,"custo_bat_kwh":3000,"custo_hw":"","anos_analise":10,"ligar_pegada":true}''')
SEL_CASA = {"hardware": {"rpi5_8gb": 1, "workstation": 1, "cpu_ryzen7_8c": 1, "ram_dimm_32": 2, "gpu_8gb": 2, "nvme_2tb": 2, "raid_zfs": 1, "psu_750_ouro": 1,
                         "switch_8p": 1, "roteador_4g": 1, "ups_lfp_1500": 1, "solar_base": 1, "vent_forcada": 1, "gabinete_torre": 1},
            "software": ["debian12", "rpi_os", "docker", "physis_hub", "sqlite", "postgresql", "postgis", "timescaledb", "ollama", "superset", "pmtiles",
                         "geoserver", "energyplus", "pvlib", "libreoffice", "verapdf", "mosquitto", "caddy", "wireguard", "restic", "netdata", "fail2ban"],
            "modelo": {"params_b": 7, "bits": 4}}
# resultados da tela (JS) para o mesmo projeto
JS_SEL = [151.04239105427726, 464.1235508413372, 0.8330983333333334, 1.0740792252748605, 7.085939333410537, 644.6160428351905, 321.7639740788765,
          1583.5895554706424, 1.05, 0.149, 7, 26, 1327.78464, 8.749134222222223, 20.437436300788228, 1389.2879129172425]
JS_MAN = [167.90185185185183, 496.6666666666667, 1.1939687242798354, 689.8148148148148, 1.3833333333333333, 0.4, 0.07833343366851851, 8.190000000000001, 2, 2.75]


@unittest.skipUnless(NO_REPO, "só no repositório")
class EspelhoDaTela(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.C = sv.carregar_catalogo(CAT)

    def test_casa_physis_com_selecao(self):
        R = sv.dimensionar(P_CASA, 0.0385, 0, None, SEL_CASA, self.C)
        py = [R["energia"]["w_medio"], R["energia"]["w_pico"], R["energia"]["eficiencia_fonte"], R["solar"]["kwp"], R["solar"]["bateria_kwh"],
              R["nobreak"]["va"], R["nobreak"]["autonomia_min_selecao"], R["termico"]["btu_h"], R["termico"]["pue"], R["carbono"]["t_fabricacao_ano"],
              R["computacao"]["nucleos"], R["computacao"]["ram_gb"], R["armazenamento"]["bruto_gb"], R["rede"]["subida_mbps"],
              R["carbono"]["payback_anos"], R["carbono"]["kwh_ano"]]
        for i, (a, b) in enumerate(zip(py, JS_SEL)):
            perto(self, a, b, 1e-6) if b else self.assertEqual(a, b, i)
        self.assertEqual([c for c in R["selecao"]["compat"] if not c["ok"]], [])

    def test_casa_physis_lista_manual(self):
        R = sv.dimensionar(dict(P_CASA, usar_selecao=False), 0.0385, 0, None, SEL_CASA, self.C)
        self.assertNotIn("selecao", R)
        py = [R["energia"]["w_medio"], R["energia"]["w_pico"], R["solar"]["kwp"], R["nobreak"]["va"], R["termico"]["pue"], R["carbono"]["t_fabricacao_ano"],
              R["carbono"]["t_sem_solar"], R["computacao"]["vram_precisa_gb"], R["computacao"]["gpus_precisa"], R["computacao"]["h_ia_dia"]]
        for a, b in zip(py, JS_MAN):
            perto(self, a, b, 1e-6)


@unittest.skipUnless(NO_REPO, "só no repositório")
class Catalogo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.C = sv.carregar_catalogo(CAT)
        cls.I = {x["id"]: x for x in cls.C["hardware"] + cls.C["software"]}

    def test_estado_dev_e_sem_preco_inventado(self):
        self.assertEqual(self.C["estado"], "dev")
        self.assertEqual(sv.ESTADO, "dev")
        for x in self.C["hardware"]:
            self.assertTrue(x["custo"] == "[MARCADOR]" or x["custo"].startswith("sem custo"), x["id"])
            self.assertTrue(x.get("verificar"), x["id"])
        txt = CAT.read_text(encoding="utf-8")
        self.assertNotRegex(txt, r"https?://")
        self.assertNotRegex(txt, r"R\$\s*\d")

    def test_campos_por_categoria(self):
        campos = {"plataforma": ("arch", "pcie_x16", "pcie_slots", "classe", "encaixe"), "cpu": ("encaixe", "nucleos", "threads", "tdp_w"),
                  "ram": ("formato", "gb", "ecc"), "gpu": ("vram_gb", "tdp_w", "tflops_fp16", "pcie", "conectores", "slots_largura"),
                  "armazenamento": ("tipo", "tb", "tbw"), "fonte": ("w", "classe80"), "nobreak": ("va", "w", "bateria_wh", "quimica", "tipo")}
        ids = set()
        for x in self.C["hardware"]:
            self.assertNotIn(x["id"], ids)
            ids.add(x["id"])
            for k in ("id", "cat", "nome", "w_ocioso", "w_carga"):
                self.assertIn(k, x, x["id"])
            self.assertLessEqual(x["w_ocioso"], x["w_carga"], x["id"])
            for k in campos.get(x["cat"], ()):
                self.assertIn(k, x, f"{x['id']}.{k}")
            if x["cat"] == "fonte":
                self.assertIn(x["classe80"], self.C["eficiencia_80plus"])
            if x["cat"] == "plataforma":
                self.assertIn(x["classe"], sv.ps.PADRAO["classes"])
        for cat in ("plataforma", "cpu", "ram", "gpu", "armazenamento", "raid", "fonte", "rede", "nobreak", "solar", "refrigeracao", "rack"):
            self.assertTrue(any(x["cat"] == cat for x in self.C["hardware"]), cat)
        vrams = {x["vram_gb"] for x in self.C["hardware"] if x["cat"] == "gpu"}
        self.assertTrue({8, 12, 16, 24, 20, 48} <= vrams)

    def test_programas_com_licenca_e_dependencias(self):
        for x in self.C["software"]:
            for k in ("licenca", "nucleos", "ram_gb", "disco_gb", "requer", "deps"):
                self.assertIn(k, x, x["id"])
            for d in x["deps"]:
                self.assertIn(d, self.I, x["id"])
        nomes = {x["id"] for x in self.C["software"]}
        for k in ("debian12", "ubuntu_lts", "proxmox_ve", "rpi_os", "docker", "podman", "physis_hub", "sqlite", "postgresql", "postgis", "timescaledb",
                  "influxdb", "ollama", "vllm", "llama_cpp", "superset", "metabase", "geoserver", "qgis_server", "pmtiles", "energyplus", "pvlib",
                  "windpowerlib", "epanet", "swmm", "libreoffice", "verapdf", "mosquitto", "node_red", "caddy", "nginx", "wireguard", "restic", "borg",
                  "prometheus_grafana", "netdata", "fail2ban", "crowdsec", "forgejo", "jitsi"):
            self.assertIn(k, nomes)

    def test_perfis_existem_e_sao_compativeis(self):
        for nome, pf in self.C["perfis"].items():
            for k in list(pf["hardware"]) + pf["software"]:
                self.assertIn(k, self.I, f"{nome}: {k}")
            sel = sv.selecao_do_perfil(self.C, nome)
            if not sel["hardware"]:
                continue
            R = sv.dimensionar({"ia_ativa": bool(sel["modelo"]), "ia_params_b": sel["modelo"].get("params_b", 7), "hsp": 4.5}, 0.0385, None, None, sel, self.C)
            erros = [c["msg"] for c in R["selecao"]["compat"] if not c["ok"] and c["nivel"] == "erro"]
            self.assertEqual(erros, [], nome)

    def test_totais_casa_physis(self):
        T = sv.totais(SEL_CASA, self.C)
        self.assertEqual((T["nucleos"], T["threads"]), (12, 20))     # Raspberry 4/4 + Ryzen 7 8/16
        self.assertEqual(T["ram_gb"], 8 + 64)
        self.assertEqual((T["gpus"], T["vram_gb"]), (2, 16))
        self.assertEqual(T["disco_tb"], 4)
        perto(self, T["vram_modelo_gb"], 4.2)
        perto(self, T["w_pico_dc"], 25 + 88 + 2 * 4 + 2 * 115 + 2 * 7)
        self.assertTrue(T["x86"] and T["arm"])

    def test_fabricacao_pela_selecao(self):
        kg, t = sv.kg_fabricacao_selecao(SEL_CASA, self.C, sv.ps.PADRAO)
        self.assertEqual(kg, 20 + 350 + 2 * 150)
        perto(self, t, 20 / 1000 / 5 + 350 / 1000 / 5 + 300 / 1000 / 4)


@unittest.skipUnless(NO_REPO, "só no repositório")
class Conferencias(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.C = sv.carregar_catalogo(CAT)

    def falhas(self, sel, bruto=None):
        return {c["id"]: c["nivel"] for c in sv.compat(sel, self.C, bruto) if not c["ok"]}

    def test_raspberry_nao_recebe_placa_nem_vllm_nem_proxmox(self):
        f = self.falhas({"hardware": {"rpi5_8gb": 1, "gpu_8gb": 1}, "software": ["rpi_os", "vllm", "proxmox_ve"], "modelo": {"params_b": 7, "bits": 4}})
        self.assertEqual(f.get("gpu_encaixe"), "erro")
        self.assertEqual(f.get("x86_vllm"), "erro")
        self.assertEqual(f.get("x86_proxmox_ve"), "erro")

    def test_vram_do_modelo(self):
        base = {"workstation": 1, "cpu_ryzen7_8c": 1, "ram_dimm_32": 2, "gpu_8gb": 1, "psu_750_ouro": 1}
        f = self.falhas({"hardware": base, "software": ["debian12", "ollama"], "modelo": {"params_b": 13, "bits": 4}})
        self.assertIsNone(f.get("vram"))                         # 13 × 0,5 × 1,2 = 7,8 GB cabe numa placa de 8 GB
        f = self.falhas({"hardware": base, "software": ["debian12", "vllm"], "modelo": {"params_b": 32, "bits": 4}})
        self.assertEqual(f.get("vram"), "erro")                  # 19,2 GB numa placa de 8 GB com vLLM
        f = self.falhas({"hardware": base, "software": ["debian12", "ollama"], "modelo": {"params_b": 32, "bits": 4}})
        self.assertEqual(f.get("vram"), "aviso")                 # Ollama roda na memoria, devagar

    def test_fonte_com_30_por_cento_de_folga(self):
        sel = {"hardware": {"workstation": 1, "cpu_ryzen9_16c": 1, "ram_dimm_32": 2, "gpu_16gb": 2, "psu_750_ouro": 1}, "software": ["debian12"]}
        self.assertEqual(self.falhas(sel).get("fonte"), "erro")   # pico 25 + 230 + 8 + 570 = 833 W
        sel["hardware"]["psu_750_ouro"] = 0
        sel["hardware"]["psu_1200_platina"] = 1
        self.assertNotIn("fonte", self.falhas(sel))

    def test_memoria_encaixes_e_dependencias(self):
        sel = {"hardware": {"minipc_n100": 1, "ram_sodimm_16": 1}, "software": ["debian12", "timescaledb", "superset", "jitsi"]}
        f = self.falhas(sel)
        self.assertEqual(f.get("ram"), None)                      # 16 GB para 0,5 + 0,5 + 4 + 4 = 9 GB
        self.assertEqual(f.get("dep_timescaledb_postgresql"), "erro")
        self.assertEqual(f.get("dep_superset_postgresql"), "erro")
        self.assertEqual(f.get("nucleos"), "aviso")               # 4 threads para 8,4 núcleos
        f = self.falhas({"hardware": {"minipc_n100": 1, "ram_dimm_16": 1}, "software": ["debian12"]})
        self.assertEqual(f.get("ram_fmt_ram_dimm_16"), "erro")
        f = self.falhas({"hardware": {"workstation": 1, "cpu_xeon_e": 1, "gpu_8gb": 3, "ram_dimm_16": 1}, "software": []})
        self.assertEqual(f.get("encaixe_cpu_xeon_e"), "erro")
        self.assertEqual(f.get("cpu_workstation"), "erro")
        self.assertEqual(f.get("pcie_x16"), "erro")
        self.assertEqual(f.get("so"), "aviso")
        f = self.falhas({"hardware": {"servidor_1u": 1, "cpu_xeon_e": 1, "ram_dimm_16": 1}, "software": ["debian12"]})
        self.assertEqual(f.get("ecc_ram_dimm_16"), "aviso")

    def test_disco_menor_que_o_crescimento_e_nobreak(self):
        sel = {"hardware": {"rpi5_8gb": 1, "nvme_1tb": 1, "ups_li_1000": 1}, "software": ["rpi_os"]}
        self.assertEqual(self.falhas(sel, 2000).get("disco"), "erro")
        self.assertNotIn("disco", self.falhas(sel, 500))
        sel = {"hardware": {"workstation": 1, "cpu_ryzen9_16c": 1, "ram_dimm_32": 2, "gpu_24gb": 2, "psu_1600_titanio": 1, "ups_li_1000": 1}, "software": ["debian12"]}
        self.assertEqual(self.falhas(sel).get("nobreak"), "erro")


@unittest.skipUnless(JS.is_file(), "sem o módulo")
class Tela(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_contrato(self):
        self.assertEqual(self.js.count("<h1>"), 1)
        self.assertIn("<h1>Servidor verde</h1>", self.js)
        self.assertIn("Em desenvolvimento", self.js)
        self.assertIn("SERVIDOR_VERDE_PRONTO", self.js)
        for t in ("window.telaServidorVerde", "window.SERVIDOR_VERDE_I18N", "window.SERVIDOR_VERDE", '"physis-servidor-verde"', "base-servidor-catalogo",
                  "Seleção de módulos", "Cargas de trabalho", "Computação", "Armazenamento e cópias", "Rede", "Energia", "Térmico e ambiente",
                  "Carbono e custos", "Resultado", "/api/servidor/pegada", "api/gis/irradiacao", "[MARCADOR]", "ASHRAE TC 9.9", "ITU-T L.1450"):
            self.assertIn(t, self.js)
        for nome in ("Casa Physis (hub + IA 2×8 GB)", "Pequena empresa / fazenda (Raspberry Pi ou mini PC)", "Escritório com BI e mapas",
                     "Servidor de IA (GPU)", "Datacenter/colocation", "Personalizado"):
            self.assertIn(nome, self.js)

    def test_um_ouvinte_guardado_e_sem_internet(self):
        self.assertIn("__svEventos", self.js)
        self.assertEqual(len(re.findall(r"document\.addEventListener\(", self.js)), 2)
        self.assertNotRegex(self.js, r"https?://")
        self.assertNotRegex(self.js, r"\bGIZ\b")
        self.assertGreaterEqual(self.js.count("<caption"), 1)

    def test_mesmas_constantes_do_python(self):
        for t in ("BTU_POR_W = 3.412", "BTU_POR_TR = 12000", "H_MES = 730", "lifepo4:0.90", "chumbo:0.50", "* 1.3", "280 / paramsB", "525600"):
            self.assertIn(t, self.js)


if __name__ == "__main__":
    unittest.main()
