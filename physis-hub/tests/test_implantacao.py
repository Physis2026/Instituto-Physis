"""Implantação (implantacao/) e serviços abertos do servidor (servicos/): conferências estáticas e dos motores.

Protege:
1. Scripts de shell com `set -euo pipefail` (bash) / `set -eu` (sh) e sintaxe válida (bash -n, quando houver bash).
2. Nenhum segredo escrito nos arquivos; exemplos de ambiente com os segredos vazios.
3. Unidade systemd com as chaves de endurecimento.
4. docker-compose: só o Caddy publica portas; todo serviço com healthcheck e restart; redes internas.
5. Motores de cálculo: montagem de IDF/INP e API sempre testadas; os motores de verdade só se as bibliotecas existirem.
6. Exportador do BI: lê o instantâneo, nunca dados pessoais nem de Saúde.
Arquivos UTF-8 sem BOM, fim de linha LF; .ps1 só ASCII (o PowerShell 5.1 lê sem BOM como ANSI).
"""
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
IMPL = RAIZ / "implantacao"
SERV = RAIZ / "servicos"
CALC = SERV / "calc"
TEM_REPO = IMPL.is_dir() and SERV.is_dir()      # no pacote do cliente (montar.py) estas pastas não vão

if TEM_REPO and str(CALC) not in sys.path:
    sys.path.insert(0, str(CALC))


def arquivos(*pastas, sufixos=None):
    for p in pastas:
        for a in sorted(p.rglob("*")):
            if a.is_file() and "__pycache__" not in a.parts and (sufixos is None or a.suffix in sufixos or a.name in sufixos):
                yield a


def bash_utilizavel():
    for cand in (shutil.which("bash"), r"C:\Program Files\Git\bin\bash.exe"):
        if cand and os.path.isfile(cand) and "system32" not in cand.lower():
            try:
                if subprocess.run([cand, "-c", "echo ok"], capture_output=True, timeout=20).returncode == 0:
                    return cand
            except (OSError, subprocess.TimeoutExpired):
                pass
    return None


def servicos_compose(texto: str) -> dict:
    """Leitor mínimo do docker-compose.yml (sem PyYAML): {serviço: bloco de texto}."""
    blocos, atual, dentro = {}, None, False
    for ln in texto.splitlines():
        if re.match(r"^services:\s*$", ln):
            dentro = True
            continue
        if dentro and re.match(r"^\S", ln):
            dentro = False
        if not dentro or re.match(r"^\s*#", ln):
            continue
        m = re.match(r"^  ([a-z0-9_-]+):\s*$", ln)
        if m:
            atual = m.group(1)
            blocos[atual] = []
        elif atual:
            blocos[atual].append(ln)
    return {k: "\n".join(v) for k, v in blocos.items()}


@unittest.skipUnless(TEM_REPO, "implantacao/ e servicos/ só existem no repositório")
class Arquivos(unittest.TestCase):
    def test_utf8_sem_bom_e_lf(self):
        for a in arquivos(IMPL, SERV):
            b = a.read_bytes()
            self.assertFalse(b.startswith(b"\xef\xbb\xbf"), f"BOM em {a}")
            self.assertNotIn(b"\r\n", b, f"CRLF em {a}")
            b.decode("utf-8")
            if a.suffix == ".ps1":
                self.assertTrue(all(c < 128 for c in b), f"{a}: .ps1 deve ser só ASCII")

    def test_scripts_de_shell_param_no_erro(self):
        scripts = list(arquivos(IMPL, SERV, sufixos={".sh"}))
        self.assertGreaterEqual(len(scripts), 8)
        for a in scripts:
            t = a.read_text(encoding="utf-8")
            if t.startswith("#!/usr/bin/env bash") or t.startswith("#!/bin/bash"):
                self.assertRegex(t, r"(?m)^set -euo pipefail$", f"{a.name}: falta set -euo pipefail")
            else:
                self.assertTrue(t.startswith("#!/bin/sh"), f"{a.name}: shebang desconhecido")
                self.assertRegex(t, r"(?m)^set -eu", f"{a.name}: falta set -eu")

    def test_sintaxe_bash(self):
        bash = bash_utilizavel()
        if not bash:
            self.skipTest("sem bash utilizável")
        for a in arquivos(IMPL, SERV, sufixos={".sh"}):
            r = subprocess.run([bash, "-n", str(a)], capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0, f"{a.name}: {r.stderr}")

    def test_nenhum_segredo_escrito(self):
        proibidos = [
            re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
            re.compile(r"AGE-SECRET-KEY-1[0-9A-Z]{20,}"),
            re.compile(r"\bage1[0-9a-z]{50,}\b"),
            re.compile(r"\$2[aby]\$\d\d\$[./A-Za-z0-9]{53}"),                         # hash bcrypt
            re.compile(r"(?i)\b(senha|password|secret|segredo|token|chave|api_key)\w*\s*(=|:\s+)\s*['\"]?(?![$<\[{(])[A-Za-z0-9+_\-]{16,}"),
        ]
        for a in arquivos(IMPL, SERV):
            t = a.read_text(encoding="utf-8")
            for p in proibidos:
                m = p.search(t)
                self.assertIsNone(m, f"{a.relative_to(RAIZ)}: parece segredo: {m.group(0)[:40] if m else ''}")

    def test_exemplos_de_ambiente_sem_valores_reais(self):
        exemplos = list(arquivos(IMPL, SERV, sufixos={".exemplo"})) + [SERV / ".env.exemplo"]
        self.assertGreaterEqual(len(exemplos), 10)
        secreto = re.compile(r"(SENHA|PASSWORD|SECRET|SEGREDO|CHAVE|TOKEN|API_KEY|HASH)$")
        for a in exemplos:
            for ln in a.read_text(encoding="utf-8").splitlines():
                if "=" not in ln or ln.lstrip().startswith("#"):
                    continue
                k, v = (x.strip() for x in ln.split("=", 1))
                if (secreto.search(k) and "SEM_CHAVE" not in k) or k in ("PG_URL", "SERIES_URL"):
                    self.assertEqual(v, "", f"{a.name}: {k} deve ficar vazio no exemplo")
                self.assertNotRegex(v, r"(?i)@(?!exemplo\.com\.br)[a-z0-9-]+\.[a-z]", f"{a.name}: e-mail real em {k}")
                if "dominio" in k.lower() or "url" in k.lower():
                    self.assertTrue(v == "" or "exemplo" in v, f"{a.name}: {k} deve usar domínio de exemplo")

    def test_segredos_fora_do_git(self):
        gi = (SERV / ".gitignore").read_text(encoding="utf-8").split()
        self.assertIn("env/*.env", gi)
        self.assertIn(".env", gi)


@unittest.skipUnless(TEM_REPO, "só no repositório")
class Implantacao(unittest.TestCase):
    def test_unidade_systemd_endurecida(self):
        t = (IMPL / "systemd" / "physis-hub.service").read_text(encoding="utf-8")
        for chave in ("NoNewPrivileges=yes", "ProtectSystem=strict", "ReadWritePaths=/var/lib/physis", "PrivateTmp=yes",
                      "ProtectHome=yes", "PrivateDevices=yes", "CapabilityBoundingSet=", "RestrictAddressFamilies=",
                      "SystemCallFilter=@system-service", "User=physis", "EnvironmentFile=/etc/physis/physis.env",
                      "KillSignal=SIGINT", "Restart=on-failure"):
            self.assertIn(chave, t)
        self.assertNotIn("User=root", t)

    def test_instalador_gera_segredos_sem_mostrar(self):
        t = (IMPL / "instalar.sh").read_text(encoding="utf-8")
        self.assertIn("secrets.token_urlsafe", t)
        self.assertIn('chmod 0640 "$ENVF"', t)
        self.assertRegex(t, r"sys\.version_info >= \(3, 10\)")
        self.assertIn("allow_anonymous", (IMPL / "mosquitto" / "physis.conf").read_text(encoding="utf-8"))
        self.assertIn("pattern readwrite %u/#", (IMPL / "mosquitto" / "acl.exemplo").read_text(encoding="utf-8"))
        # nenhum echo/printf de variável de segredo
        self.assertNotRegex(t, r"(echo|msg|printf)[^\n]*\$\{?(S|PHYSIS_MQTT_SENHA)\b")
        for f in ("Caddyfile.lan", "Caddyfile.dominio"):
            self.assertIn("Strict-Transport-Security", (IMPL / "caddy" / f).read_text(encoding="utf-8"))

    def test_backup_cifra_gira_e_confere(self):
        t = (IMPL / "backup.sh").read_text(encoding="utf-8")
        for trecho in (".backup", "integrity_check", "age -r", "openssl enc -aes-256-cbc -pbkdf2", "MANTER_DIARIAS:-7",
                       "MANTER_SEMANAIS:-4", "MANTER_MENSAIS:-12", "rsync", "mountpoint -q", "runuser -u"):
            self.assertIn(trecho, t)
        r = (IMPL / "restaurar.sh").read_text(encoding="utf-8")
        self.assertIn("antes-restauro", r)
        self.assertIn("sha256sum -c", r)

    def test_atualizar_volta_sozinho(self):
        t = (IMPL / "atualizar.sh").read_text(encoding="utf-8")
        for trecho in ("systemctl stop physis-hub", 'backup.sh" --rotulo pre-atualizacao', 'ln -sfn "$VER"', "voltar()",
                       'ln -sfn "$ANTERIOR"', "/api/saude", "integro", "unittest"):
            self.assertTrue(trecho in t, trecho)
        # testa ANTES de parar o serviço
        self.assertLess(t.index("unittest"), t.index("systemctl stop physis-hub"))

    def test_verificar_cobre_os_pontos(self):
        t = (IMPL / "verificar.sh").read_text(encoding="utf-8")
        for trecho in ("is-active", "/api/saude", "integro", "df -P", "ultimo.json", "1883", "NTPSynchronized"):
            self.assertIn(trecho, t)

    def test_windows(self):
        t = (IMPL / "instalar.ps1").read_text(encoding="utf-8")
        for trecho in ("nssm", "Register-ScheduledTask", "LOCALSERVICE", "New-NetFirewallRule", "LocalSubnet", "version_info >= (3, 10)"):
            self.assertIn(trecho, t)


@unittest.skipUnless(TEM_REPO, "só no repositório")
class Compose(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texto = (SERV / "docker-compose.yml").read_text(encoding="utf-8")
        cls.svc = servicos_compose(cls.texto)

    def test_servicos_esperados(self):
        for s in ("caddy", "hub", "mosquitto", "nodered", "superset", "superset-db", "postgis", "geoserver",
                  "timescaledb", "calc", "ia", "exportador", "instantaneo", "documentos"):
            self.assertIn(s, self.svc)

    def test_so_caddy_publica_portas(self):
        for nome, bloco in self.svc.items():
            if nome == "caddy":
                self.assertRegex(bloco, r"(?m)^    ports:")
            else:
                self.assertNotRegex(bloco, r"(?m)^    ports:", f"{nome} publica portas")
            self.assertNotRegex(bloco, r"network_mode:\s*[\"']?host", f"{nome} na rede do host")
            self.assertNotIn("privileged: true", bloco)

    def test_healthcheck_restart_e_perfil(self):
        for nome, bloco in self.svc.items():
            self.assertRegex(bloco, r"(?m)^    healthcheck:", f"{nome} sem healthcheck")
            self.assertRegex(bloco, r"(?m)^    restart: (unless-stopped|always)", f"{nome} sem restart")
            self.assertRegex(bloco, r"(?m)^    profiles:", f"{nome} sem perfil")
            self.assertIn("no-new-privileges:true", bloco, f"{nome} sem no-new-privileges")

    def test_imagens_com_versao_fixa(self):
        for nome, bloco in self.svc.items():
            m = re.search(r"(?m)^    image: (\S+)", bloco)
            self.assertIsNotNone(m, nome)
            img = m.group(1)
            if not img.startswith("physis/"):
                self.assertRegex(img, r":[^:]*\d", f"{nome}: imagem sem versão fixa ({img})")
                self.assertNotIn(":latest", img)

    def test_redes_internas_e_segredos_por_arquivo(self):
        for rede in ("borda", "motores", "iot", "dados", "meta", "series"):
            self.assertRegex(self.texto, rf"(?ms)^  {rede}:\n    internal: true")
        for m in re.finditer(r"env_file: \[env/([a-z0-9-]+)\.env\]", self.texto):
            self.assertTrue((SERV / "env" / f"{m.group(1)}.env.exemplo").is_file(), m.group(1))
        # nenhum segredo no próprio compose
        self.assertIsNone(re.search(r"(?i)(PASSWORD|SENHA|SECRET|CHAVE)\w*:\s+\S", self.texto), "segredo no compose")
        for n in ("calc", "ia", "mosquitto", "postgis", "timescaledb", "superset-db", "documentos"):
            self.assertNotIn("saida", self.svc[n], f"{n} não deve ter saída para a internet")
            self.assertNotIn("publica", self.svc[n])

    def test_hub_confia_so_no_caddy(self):
        self.assertIn("ipv4_address: 172.30.10.2", self.svc["caddy"])
        self.assertIn("PHYSIS_PROXY_CONFIAVEL: 172.30.10.2", self.svc["hub"])
        self.assertIn('PHYSIS_EXPOSTO: "1"', self.svc["hub"])
        self.assertIn("http://calc:8710", self.svc["hub"])

    def test_nodered_e_superset_com_login(self):
        s = (SERV / "nodered" / "settings.js").read_text(encoding="utf-8")
        self.assertIn("adminAuth", s)
        self.assertIn("throw new Error", s)
        c = (SERV / "superset" / "superset_config.py").read_text(encoding="utf-8")
        self.assertIn('os.environ["SUPERSET_SECRET_KEY"]', c)
        self.assertIn("PREVENT_UNSAFE_DB_CONNECTIONS = True", c)
        self.assertIn("bi_leitor", (SERV / "superset" / "iniciar.sh").read_text(encoding="utf-8"))
        self.assertIn("default_transaction_read_only = on", (SERV / "postgis" / "init" / "01-papeis.sh").read_text(encoding="utf-8"))

    def test_requirements_fixos(self):
        for req in (CALC / "requirements.txt", SERV / "exportador" / "requirements.txt"):
            for ln in req.read_text(encoding="utf-8").splitlines():
                if ln.strip() and not ln.startswith("#"):
                    self.assertRegex(ln, r"^[A-Za-z0-9_.\[\]-]+==\d", f"{req.name}: {ln}")


TERMICA = {"clima": {"lat": -15.8, "lon": -47.9, "tbs": 32, "tbu": 24, "dr": 10, "tint": 24},
           "ambiente": {"area": 30, "pe_direito": 2.8, "pessoas": 4, "atividade_w": 120, "iluminacao_wm2": 10,
                        "equipamentos_wm2": 10, "infiltracao_ach": 0.5, "ar_externo_ls": 30, "ini": 8, "fim": 18,
                        "superficies": [
                            {"tipo": "parede", "orient": "N", "area": 15, "u": 2.4, "alfa": 0.5},
                            {"tipo": "parede", "orient": "O", "area": 15, "u": 2.4, "alfa": 0.5},
                            {"tipo": "vidro", "orient": "N", "area": 4, "u": 5.7, "fs": 0.8},
                            {"tipo": "cobertura", "area": 30, "u": 2.0, "alfa": 0.7},
                            {"tipo": "piso_solo", "area": 30}]}}
REDE = {"reservatorios": [{"id": "R1", "carga": 60}],
        "nos": [{"id": "N1", "cota": 10, "demanda_ls": 2}, {"id": "N2", "cota": 12, "demanda_ls": 1.5}],
        "tubos": [{"id": "T1", "de": "R1", "para": "N1", "comprimento": 300, "diametro_mm": 100, "rugosidade": 130},
                  {"id": "T2", "de": "N1", "para": "N2", "comprimento": 200, "diametro_mm": 75, "rugosidade": 130}]}
BACIA = {"area_ha": 2, "impermeabilidade_pct": 60, "declividade_pct": 1, "chuva": {"total_mm": 50, "duracao_min": 60}}


def tem(*mods):
    return all(importlib.util.find_spec(m) is not None for m in mods)


@unittest.skipUnless(TEM_REPO, "só no repositório")
class MotoresEntrada(unittest.TestCase):
    """Montagem das entradas e validação: só biblioteca padrão, sempre roda."""

    def test_idf_zona_unica(self):
        from physis_calc import termica
        r = termica.calcular(TERMICA, somente_idf=True)
        idf = r["idf"]
        self.assertTrue(idf.startswith("Version, 24.2;"))
        for obj in ("SizingPeriod:DesignDay", "ZoneHVAC:IdealLoadsAirSystem", "ThermostatSetpoint:SingleCooling",
                    "FenestrationSurface:Detailed, JanelaN", "People, Pessoas", "Zone Ideal Loads Zone Total Cooling Rate"):
            self.assertIn(obj, idf)
        self.assertEqual(idf.count("BuildingSurface:Detailed"), 6)       # 4 paredes, cobertura, piso
        # R do material = 1/U - Rsi - Rse (NBR 15220-2)
        self.assertIn(f"{1 / 2.4 - 0.17:.4f}", idf)
        self.assertTrue(any("Parede L sem dado" in a for a in r["avisos"]))
        self.assertTrue(any("piso" in a for a in r["avisos"]))

    def test_idf_sem_inventar_valores(self):
        from physis_calc import termica
        from physis_calc.comum import EntradaInvalida
        sem_u = json.loads(json.dumps(TERMICA))
        del sem_u["ambiente"]["superficies"][0]["u"]
        with self.assertRaises(EntradaInvalida):
            termica.validar(sem_u)
        sem_cob = json.loads(json.dumps(TERMICA))
        sem_cob["ambiente"]["superficies"] = sem_cob["ambiente"]["superficies"][:3]
        with self.assertRaises(EntradaInvalida):
            termica.validar(sem_cob)

    def test_inp_epanet(self):
        from physis_calc import rede_agua
        from physis_calc.comum import EntradaInvalida
        inp = rede_agua.calcular(REDE, somente_inp=True)["inp"]
        for sec in ("[JUNCTIONS]", "[RESERVOIRS]", "[PIPES]", "Units  LPS", "Headloss  H-W", "[END]"):
            self.assertIn(sec, inp)
        solto = json.loads(json.dumps(REDE))
        solto["nos"].append({"id": "N9", "cota": 1})
        with self.assertRaisesRegex(EntradaInvalida, "N9"):
            rede_agua.validar(solto)
        ruim = json.loads(json.dumps(REDE))
        ruim["tubos"][0]["id"] = "T 1; DROP"
        with self.assertRaises(EntradaInvalida):
            rede_agua.validar(ruim)

    def test_inp_swmm(self):
        from physis_calc import drenagem
        p = drenagem.validar(BACIA)
        self.assertEqual(len(p["intensidades"]), 12)
        self.assertAlmostEqual(sum(i * 5 / 60 for i in p["intensidades"]), 50, places=6)
        inp = drenagem.montar_inp(p)
        for sec in ("[RAINGAGES]", "[SUBCATCHMENTS]", "[SUBAREAS]", "[INFILTRATION]", "[OUTFALLS]", "[TIMESERIES]",
                    "INFILTRATION HORTON", "FLOW_UNITS LPS"):
            self.assertIn(sec, inp)
        self.assertIn("horton", p["usou_padroes"])

    def test_eolica_e_pv_validam(self):
        from physis_calc import eolica, pv
        from physis_calc.comum import EntradaInvalida
        with self.assertRaises(EntradaInvalida):
            eolica.validar({"altura_cubo": 30, "rugosidade": 0.1, "velocidades": [5]})          # sem curva
        p = eolica.validar({"altura_cubo": 30, "rugosidade": 0.1, "weibull": {"k": 2, "c": 6},
                            "curva": [{"v": 3, "kw": 0}, {"v": 12, "kw": 100}, {"v": 25, "kw": 100}]})
        self.assertEqual(p["curva"][1], (12.0, 100.0))
        self.assertGreater(eolica._extrapolar(5, 10, 30, 0.1), 5)
        self.assertEqual(pv.validar({"lat": -15, "lon": -47, "kwp": 5, "temp_ar": 25})["azimute"], 0)   # voltado ao norte
        with self.assertRaises(EntradaInvalida):
            pv.validar({"lat": -15, "lon": -47, "kwp": 5})          # sem irradiância nem temperatura
        with self.assertRaises(EntradaInvalida):
            pv.validar({"lat": 95, "lon": -47, "kwp": 5, "temp_ar": 25})


@unittest.skipUnless(TEM_REPO, "só no repositório")
class MotoresAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from physis_calc import servidor
        cls.srv = servidor.iniciar(0, "127.0.0.1", chave="chave-de-teste-local")
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def pedir(self, rota, corpo=None, chave="chave-de-teste-local"):
        req = urllib.request.Request(self.url + rota, data=json.dumps(corpo).encode() if corpo is not None else None,
                                     method="POST" if corpo is not None else "GET")
        if chave:
            req.add_header("Authorization", "Bearer " + chave)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_rotas(self):
        st, r = self.pedir("/saude")
        self.assertEqual(st, 200)
        self.assertEqual(set(r["motores"]), {"pv", "eolica", "termica", "rede-agua", "drenagem"})
        self.assertEqual(self.pedir("/pv", {"lat": 0}, chave="errada")[0], 401)
        self.assertEqual(self.pedir("/nada", {"a": 1})[0], 404)
        self.assertEqual(self.pedir("/pv", {"lat": 0})[0], 400)
        st, r = self.pedir("/termica?somente_entrada=1", TERMICA)
        self.assertEqual(st, 200)
        self.assertIn("Version, 24.2;", r["idf"])
        st, r = self.pedir("/pv", {"lat": -15.8, "lon": -47.9, "kwp": 5, "temp_ar": 25})
        self.assertEqual(st, 200 if tem("pvlib") else 503)

    def test_conector_do_hub(self):
        sys.path.insert(0, str(SERV / "hub-conectores"))
        try:
            import calc_cliente as cc
        finally:
            sys.path.remove(str(SERV / "hub-conectores"))
        antes = {k: os.environ.get(k) for k in ("PHYSIS_CALC_URL", "PHYSIS_CALC_CHAVE")}
        try:
            os.environ.pop("PHYSIS_CALC_URL", None)
            self.assertIsNone(cc.calcular("drenagem", BACIA))                         # sem serviço: None, hub segue
            os.environ["PHYSIS_CALC_URL"] = "https://calc.exemplo.com.br"
            self.assertEqual(cc.calc_url(), "")                                     # fora da rede local: recusado
            os.environ["PHYSIS_CALC_URL"] = "http://127.0.0.1:9"                     # porta fechada
            self.assertIsNone(cc.calc_saude(tempo=1))
            os.environ["PHYSIS_CALC_URL"] = self.url
            os.environ["PHYSIS_CALC_CHAVE"] = "chave-de-teste-local"
            self.assertTrue(cc.calc_saude()["ok"])
            self.assertIn("[SUBCATCHMENTS]", cc.calcular("drenagem", BACIA, somente_entrada=True)["inp"])
            self.assertFalse(cc.calcular("rede-agua", {"tubos": []})["ok"])           # 400 volta com a mensagem
            r = cc.drenagem(2, 60, 1, {"total_mm": 50, "duracao_min": 60})
            if tem("pyswmm"):
                self.assertTrue(r["ok"])
            else:
                self.assertIsNone(r)                                                 # 503: tratado como ausente
        finally:
            for k, v in antes.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


@unittest.skipUnless(TEM_REPO, "só no repositório")
class MotoresDeVerdade(unittest.TestCase):
    """Rodam só onde as bibliotecas abertas estão instaladas (imagem do calc)."""

    @unittest.skipUnless(tem("pvlib", "pandas"), "pvlib não instalado")
    def test_pv(self):
        from physis_calc import pv
        r = pv.calcular({"lat": -15.8, "lon": -47.9, "kwp": 10, "temp_ar": 25})
        self.assertEqual(len(r["horario_kw"]), 8760)
        self.assertGreater(r["anual_kwh"], 0)
        self.assertLessEqual(max(r["horario_kw"]), 10)

    @unittest.skipUnless(tem("windpowerlib", "pandas"), "windpowerlib não instalado")
    def test_eolica(self):
        from physis_calc import eolica
        curva = [{"v": v, "kw": min(100, max(0, (v - 3) * 12))} for v in range(0, 26)]
        r = eolica.calcular({"altura_cubo": 30, "rugosidade": 0.1, "curva": curva, "velocidades": [6.0] * 24})
        self.assertGreater(r["energia_kwh"], 0)

    @unittest.skipUnless(tem("wntr"), "wntr não instalado")
    def test_rede(self):
        from physis_calc import rede_agua
        r = rede_agua.calcular(REDE)
        self.assertLess(r["pressao_m"]["N2"], 60 - 12)
        self.assertAlmostEqual(r["tubos"]["T1"]["vazao_ls"], 3.5, places=1)

    @unittest.skipUnless(tem("pyswmm"), "pyswmm não instalado")
    def test_drenagem(self):
        from physis_calc import drenagem
        r = drenagem.calcular(BACIA)
        self.assertGreater(r["vazao_pico_ls"], 0)
        self.assertLess(r["coeficiente_escoamento"], 1)

    def test_termica(self):
        from physis_calc import termica
        if not termica.energyplus():
            self.skipTest("EnergyPlus não instalado")
        r = termica.calcular(TERMICA)
        self.assertTrue(r["ok"], r)
        self.assertGreater(r["projeto"]["W"], 0)


RELATORIO_VERA = """<?xml version="1.0" encoding="utf-8"?>
<report><jobs><job><item size="1"><name>/tmp/documento.pdf</name></item>
<validationReport jobEndStatus="normal" profileName="PDF/A-2B validation profile"
  statement="PDF file is not compliant with Validation Profile requirements." isCompliant="false">
<details passedRules="140" failedRules="2" passedChecks="900" failedChecks="4">
<rule specification="ISO 19005-2:2011" clause="6.2.11.4.1" testNumber="1" status="failed" failedChecks="3">
<description>The font programs for all fonts used for rendering within a conforming file shall be embedded</description></rule>
<rule specification="ISO 19005-2:2011" clause="6.6.2.1" testNumber="1" status="failed" failedChecks="1">
<description>The Catalog dictionary of a conforming file shall contain the Metadata key</description></rule>
</details></validationReport></job></jobs></report>"""


@unittest.skipUnless(TEM_REPO, "só no repositório")
class Documentos(unittest.TestCase):
    """LibreOffice PDF/A + veraPDF: resumo e API sempre; os programas de verdade só se estiverem instalados."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(SERV / "documentos"))
        from physis_doc import servidor
        cls.mod = servidor
        cls.srv = servidor.iniciar(0, "127.0.0.1", chave="chave-doc-de-teste")
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        sys.path.remove(str(SERV / "documentos"))

    def pedir(self, rota, corpo=None, chave="chave-doc-de-teste"):
        req = urllib.request.Request(self.url + rota, data=corpo, method="POST" if corpo is not None else "GET")
        if chave:
            req.add_header("Authorization", "Bearer " + chave)
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_resumo_do_relatorio(self):
        r = self.mod.resumo_verapdf(RELATORIO_VERA)
        self.assertTrue(r["ok"])
        self.assertFalse(r["compliant"])
        self.assertEqual(r["perfil"], "PDF/A-2B")
        self.assertEqual((r["regras_ok"], r["regras_falhas"]), (140, 2))
        self.assertEqual(r["falhas"][0]["clausula"], "6.2.11.4.1")
        self.assertEqual(r["falhas"][0]["ocorrencias"], 3)
        self.assertFalse(self.mod.resumo_verapdf("<report><jobs/></report>")["ok"])

    def test_filtro_igual_ao_do_hub(self):
        from physis_hub import documentos
        self.assertEqual(self.mod.PDFA_FILTRO, documentos.PDFA_FILTRO)

    def test_rotas(self):
        st, _, b = self.pedir("/saude")
        self.assertEqual(st, 200)
        self.assertEqual(set(json.loads(b)) >= {"soffice", "verapdf"}, True)
        self.assertEqual(self.pedir("/pdfa/validar", b"%PDF-1.7", chave="errada")[0], 401)
        self.assertEqual(self.pedir("/pdfa/validar", b"nao e pdf")[0], 400)
        self.assertEqual(self.pedir("/pdfa/converter?extensao=odt", b"nao e odt")[0], 400)
        self.assertEqual(self.pedir("/pdfa/converter?extensao=exe", b"PK\x03\x04")[0], 400)
        self.assertEqual(self.pedir("/outra", b"x")[0], 404)
        st = self.pedir("/pdfa/validar", b"%PDF-1.7\n%%EOF")[0]
        self.assertEqual(st, 200 if self.mod.verapdf() else 503)

    def test_conector(self):
        sys.path.insert(0, str(SERV / "hub-conectores"))
        try:
            import documentos_cliente as dc
        finally:
            sys.path.remove(str(SERV / "hub-conectores"))
        antes = {k: os.environ.get(k) for k in ("PHYSIS_DOC_URL", "PHYSIS_DOC_CHAVE")}
        try:
            os.environ.pop("PHYSIS_DOC_URL", None)
            self.assertIsNone(dc.pdfa_validar(b"%PDF-1.7"))                      # sem serviço: None, hub segue
            os.environ["PHYSIS_DOC_URL"] = "https://documentos.exemplo.com.br"
            self.assertEqual(dc.doc_url(), "")                                    # fora da rede local
            os.environ["PHYSIS_DOC_URL"] = self.url
            os.environ["PHYSIS_DOC_CHAVE"] = "chave-doc-de-teste"
            self.assertTrue(dc.doc_saude()["ok"])
            self.assertFalse(dc.pdfa_converter(b"nao e odt")["ok"])              # 400 volta com a mensagem
            r = dc.pdfa_validar(b"%PDF-1.7\n%%EOF")
            if self.mod.verapdf():
                self.assertIn("compliant", r)
            else:
                self.assertIsNone(r)                                              # 503: tratado como ausente
        finally:
            for k, v in antes.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_conversao_e_validacao_de_verdade(self):
        if not self.mod.soffice():
            self.skipTest("LibreOffice não instalado")
        import io
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr(zipfile.ZipInfo("mimetype"), "application/vnd.oasis.opendocument.text")
            z.writestr("META-INF/manifest.xml", '<?xml version="1.0" encoding="UTF-8"?><manifest:manifest '
                       'xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2">'
                       '<manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/>'
                       '<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/></manifest:manifest>')
            z.writestr("content.xml", '<?xml version="1.0" encoding="UTF-8"?><office:document-content '
                       'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
                       'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" office:version="1.2">'
                       '<office:body><office:text><text:p>Teste Physis PDF/A</text:p></office:text></office:body>'
                       '</office:document-content>')
        st, cab, pdf = self.pedir("/pdfa/converter?extensao=odt&validar=1", buf.getvalue())
        self.assertEqual(st, 200)
        self.assertTrue(pdf.startswith(b"%PDF-"))
        if self.mod.verapdf():
            self.assertEqual(cab.get("X-Physis-PDFA"), "conforme")


@unittest.skipUnless(TEM_REPO, "só no repositório")
class ExportadorBI(unittest.TestCase):
    def test_instantaneo_e_lista_fechada(self):
        sys.path.insert(0, str(SERV / "exportador"))
        try:
            import exportar_hub
            import instantaneo
        finally:
            sys.path.remove(str(SERV / "exportador"))
        from physis_hub.hub import Hub
        with tempfile.TemporaryDirectory() as d:
            banco = Path(d) / "physis-hub.db"
            h = Hub(str(banco), org="org-teste", lugar="lugar01")
            try:
                h.receber_lote("ID:03,U1:45.0,IR1:0,U2:45.0,IR2:0,LIM1:30.0,LIM2:30.0,TS:1794600001")
                h._db.execute("CREATE TABLE IF NOT EXISTS clima_local (id INTEGER PRIMARY KEY, dados TEXT NOT NULL, "
                              "atualizado REAL NOT NULL)")
                h._db.execute("INSERT OR REPLACE INTO clima_local(id,dados,atualizado) VALUES(1,?,0)",
                              (json.dumps({"lat": -15.8, "lon": -47.9, "municipio": "Brasília", "uf": "DF"}),))
                h._db.commit()
                (Path(d) / "inst").mkdir()
                destino = Path(d) / "inst" / "physis-hub.db"
                instantaneo.MARCA = destino.parent / ".ultimo"
                self.assertGreater(instantaneo.copiar(banco, destino), 0)      # com o hub aberto
            finally:
                h.fechar()
            c = exportar_hub.abrir(destino)
            try:
                med = exportar_hub.medicoes(c)
                self.assertTrue(med)
                self.assertTrue(all(len(r) == 9 for r in med))
                lei = exportar_hub.leituras(c)
                self.assertEqual(len(lei), 1)
                self.assertNotIn("U1:45", json.dumps(lei))                       # o texto da linha não sai
                lg = exportar_hub.lugar(c)
                self.assertEqual(lg["geometry"]["coordinates"], [-47.9, -15.8])
                arq = exportar_hub.gravar_geojson({"hub_lugar": [lg]}, Path(d) / "geo")[0]
                self.assertEqual(json.loads(arq.read_text(encoding="utf-8"))["type"], "FeatureCollection")
                with self.assertRaises(sqlite3.OperationalError):              # instantâneo é só leitura
                    c.execute("DELETE FROM leitura")
            finally:
                c.close()
        texto = (SERV / "exportador" / "exportar_hub.py").read_text(encoding="utf-8")
        for proibida in ("FROM conta", "FROM sessao", "FROM email_saida", "FROM gestao", "FROM saude_pessoa", "FROM central"):
            self.assertNotIn(proibida, texto)


if __name__ == "__main__":
    unittest.main()
