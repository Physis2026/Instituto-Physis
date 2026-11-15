"""App nativo (Capacitor) e Bluetooth da Saúde — ver docs/APP_NATIVO.md e firmware/saude/BLE_PERFIL.md.

Protege:
1. package.json e capacitor.config.json: JSON válido, Capacitor 6 com versões fixas, nada remoto, sem tráfego aberto.
2. Permissões Android (BLE sem localização no 12+, localização só até a API 30, serviço connectedDevice) e textos iOS.
3. Nenhum segredo nos arquivos do app.
4. physis-ble.js (e os scripts do app): sem endereço externo, sem eval, com a API inteira.
5. UUIDs e ações de comando do BLE_PERFIL.md iguais às do physis-ble.js.
6. Scripts: preparar_www (sem Gestão, sem sw.js, CSP e scripts no <head>), aplicar_plataformas (não duplica),
   publicar_baixar (SHA-256 e QR), qr (formato, versão, Reed-Solomon).
7. Página de download: um h1, PT/EN, só cores da paleta, sem endereço externo.
"""
import hashlib
import importlib.util
import json
import plistlib
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
APP = RAIZ / "app-nativo"
BLE = RAIZ / "sistema" / "physis-ble.js"
PERFIL = RAIZ / "firmware" / "saude" / "BLE_PERFIL.md"
DOCS = RAIZ / "physis-hub" / "docs"
ANDROID = "{http://schemas.android.com/apk/res/android}"

URL_EXTERNA = re.compile(r"\b(?:https?|wss?)://[A-Za-z0-9\[]", re.I)


def modulo(nome):
    pasta = str(APP / "scripts")
    if pasta not in sys.path:
        sys.path.insert(0, pasta)
    spec = importlib.util.spec_from_file_location("app_nativo_" + nome, APP / "scripts" / f"{nome}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def ler(p: Path) -> str:
    return p.read_text(encoding="utf-8")


class Configuracao(unittest.TestCase):
    def test_package_json(self):
        p = json.loads(ler(APP / "package.json"))
        deps = {**p["dependencies"], **p["devDependencies"]}
        for nome in ("@capacitor/core", "@capacitor/cli", "@capacitor/android", "@capacitor/ios",
                     "@capacitor-community/bluetooth-le", "@capacitor/preferences", "@capacitor/local-notifications"):
            with self.subTest(nome):
                self.assertIn(nome, deps)
                self.assertRegex(deps[nome], r"^\d+\.\d+\.\d+$", "versão fixa, sem ^ ou ~")
                self.assertTrue(deps[nome].startswith("6."), "linha 6 do Capacitor")
        self.assertIn("conferir versões ao instalar", p["//"].lower())
        self.assertNotIn("firebase", json.dumps(p).lower(), "sem Firebase por padrão (independência)")

    def test_capacitor_config(self):
        c = json.loads(ler(APP / "capacitor.config.json"))
        self.assertEqual(c["appId"], "br.com.physisengineering.app")
        self.assertEqual(c["appName"], "Physis")
        self.assertEqual(c["webDir"], "www")
        self.assertNotIn("url", c["server"], "nada remoto: o app carrega a plataforma embutida")
        self.assertIs(c["server"]["cleartext"], False)
        self.assertEqual(c["server"]["allowNavigation"], [])
        self.assertIs(c["android"]["allowMixedContent"], False)
        self.assertIs(c["android"]["webContentsDebuggingEnabled"], False)
        self.assertIs(c["plugins"]["CapacitorHttp"]["enabled"], True)
        self.assertIs(c["plugins"]["CapacitorCookies"]["enabled"], True)


class Permissoes(unittest.TestCase):
    def test_android(self):
        t = ET.parse(APP / "plataformas" / "android" / "AndroidManifest.trecho.xml").getroot()
        perm = {e.get(ANDROID + "name").rsplit(".", 1)[-1]: e for e in t.iter("uses-permission")}
        for nome in ("BLUETOOTH_SCAN", "BLUETOOTH_CONNECT", "BLUETOOTH", "BLUETOOTH_ADMIN", "ACCESS_FINE_LOCATION",
                     "ACCESS_COARSE_LOCATION", "POST_NOTIFICATIONS", "FOREGROUND_SERVICE", "FOREGROUND_SERVICE_CONNECTED_DEVICE"):
            self.assertIn(nome, perm)
        self.assertEqual(perm["BLUETOOTH_SCAN"].get(ANDROID + "usesPermissionFlags"), "neverForLocation")
        for nome in ("BLUETOOTH", "BLUETOOTH_ADMIN", "ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION"):
            self.assertEqual(perm[nome].get(ANDROID + "maxSdkVersion"), "30", nome)
        servico = next(t.iter("service"))
        self.assertEqual(servico.get(ANDROID + "foregroundServiceType"), "connectedDevice")
        apl = next(t.iter("aplicacao"))
        self.assertEqual(apl.get(ANDROID + "allowBackup"), "false")

    def test_ios(self):
        p = plistlib.loads((APP / "plataformas" / "ios" / "Info.trecho.plist").read_bytes())
        self.assertIn("Bluetooth", p["NSBluetoothAlwaysUsageDescription"])
        self.assertIn("não é usado para saber onde", p["NSBluetoothAlwaysUsageDescription"])
        self.assertIn("NSBluetoothPeripheralUsageDescription", p)
        self.assertIn("bluetooth-central", p["UIBackgroundModes"])
        self.assertEqual(p["CFBundleDevelopmentRegion"], "pt-BR")
        priv = plistlib.loads((APP / "plataformas" / "ios" / "PrivacyInfo.xcprivacy").read_bytes())
        self.assertIs(priv["NSPrivacyTracking"], False)
        self.assertEqual(priv["NSPrivacyTrackingDomains"], [])


class Segredos(unittest.TestCase):
    PADROES = [r"phk_[A-Za-z0-9_-]{12,}", r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"AIza[0-9A-Za-z_-]{30,}",
               r"(?i)(storePassword|keyPassword)\s*[=:]\s*\S{4,}", r"(?i)\"(senha|password|token)\"\s*:\s*\"[^\"]{6,}\""]

    def test_sem_segredos(self):
        arquivos = [p for p in APP.rglob("*") if p.is_file() and p.suffix in (".json", ".js", ".py", ".html", ".xml", ".plist", ".xcprivacy", ".md")
                    and "node_modules" not in p.parts and "www" not in p.parts]
        arquivos += [BLE, PERFIL, DOCS / "APP_NATIVO.md"]
        for p in arquivos:
            t = ler(p)
            for padrao in self.PADROES:
                with self.subTest(arquivo=p.name, padrao=padrao):
                    self.assertIsNone(re.search(padrao, t))


class Biblioteca(unittest.TestCase):
    def setUp(self):
        self.js = ler(BLE)

    def test_sem_endereco_externo_nem_eval(self):
        for p in [BLE] + sorted((APP / "www-extra").glob("*.js")):
            with self.subTest(p.name):
                t = ler(p)
                self.assertIsNone(URL_EXTERNA.search(t), "nenhum endereço fixo")
                self.assertNotRegex(t, r"\beval\s*\(")
                self.assertNotRegex(t, r"new\s+Function\s*\(")
                self.assertNotRegex(t, r"\bimportScripts\s*\(|\bimport\s*\(")

    def test_api(self):
        self.assertIn("window.PhysisBLE = Object.freeze(", self.js)
        api = self.js[self.js.index("window.PhysisBLE = Object.freeze("):]
        for nome in ("disponivel", "procurar", "conectar", "inscrever", "escrever", "desconectar",
                     "configurar", "pendentes", "enviarPendentes", "texto", "UUID"):
            self.assertRegex(api, rf"\b{nome}\b", nome)

    def test_backends_e_envio(self):
        self.assertIn("isNativePlatform", self.js)
        self.assertIn("navigator.bluetooth", self.js)
        self.assertIn("/api/saude/linha", self.js)
        self.assertIn('"X-Physis-Chave"', self.js)
        self.assertIn('credentials: "omit"', self.js)
        self.assertIn("AES-GCM", self.js)
        self.assertIn("indexedDB", self.js)
        self.assertIn("androidNeverForLocation: true", self.js)
        self.assertNotIn("localStorage", self.js, "a fila de saúde não vai para localStorage (sem cifra)")

    def test_textos_pt_en(self):
        for idioma in ("pt", "en"):
            self.assertRegex(self.js, rf"\b{idioma}: \{{")
        chaves_pt = re.findall(r"^    (\w+): \"", self.js.split("en: {")[0].split("pt: {")[1], flags=re.M)
        chaves_en = re.findall(r"^    (\w+): \"", self.js.split("en: {")[1].split("};")[0], flags=re.M)
        self.assertEqual(chaves_pt, chaves_en)
        self.assertIn("nenhum", chaves_pt)


class Perfil(unittest.TestCase):
    def test_uuids_iguais(self):
        js, md = ler(BLE), ler(PERFIL)
        for chave in ("SERVICO_MED", "SERVICO_PUL", "LINHA", "COMANDO"):
            m = re.search(rf'{chave}:\s*"([0-9a-f-]{{36}})"', js)
            self.assertIsNotNone(m, chave)
            self.assertIn(f"`{m.group(1)}`", md, chave)
        uu = re.findall(r"`([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})`", md)
        proprios = {u for u in uu if not u.endswith("-0000-1000-8000-00805f9b34fb")}
        self.assertEqual(len(proprios), 4)
        for u in proprios:
            self.assertEqual(u[14], "4", "UUID aleatória (versão 4)")
            self.assertIn(u, js)
        self.assertIn("0000180f-0000-1000-8000-00805f9b34fb", js)
        self.assertIn("0000180a-0000-1000-8000-00805f9b34fb", js)

    def test_acoes_iguais(self):
        js = ler(BLE)
        acoes_js = re.findall(r'"([A-Z]+)"', re.search(r"const ACOES = \[(.*?)\]", js).group(1))
        secao = ler(PERFIL).split("### 2.2")[1].split("## 3.")[0]
        acoes_md = re.findall(r"^\| `([A-Z]+)` \|", secao, flags=re.M)
        self.assertEqual(sorted(acoes_js), sorted(acoes_md))

    def test_linha_max_do_protocolo(self):
        from physis_hub import protocolo
        self.assertIn(f"LINHA_MAX = {protocolo.LINHA_MAX}", ler(BLE))
        self.assertIn(f"TOTAL_NOS = {protocolo.TOTAL_NOS}", ler(BLE))


class PrepararWww(unittest.TestCase):
    def test_monta(self):
        pw = modulo("preparar_www")
        with tempfile.TemporaryDirectory() as t:
            web = Path(t) / "web"
            (web / "app").mkdir(parents=True)
            (web / "vendor").mkdir()
            (web / "painel.html").write_text('<!doctype html><html><head>\n<meta charset="utf-8">\n<title>P</title></head><body><h1>x</h1></body></html>', encoding="utf-8")
            (web / "gestao.html").write_text("<html><head></head></html>", encoding="utf-8")
            (web / "sustainkit.html").write_text("<html><head></head></html>", encoding="utf-8")
            (web / "app" / "sw.js").write_text("//", encoding="utf-8")
            (web / "app" / "manifest-plataforma.webmanifest").write_text("{}", encoding="utf-8")
            (web / "vendor" / "x.js").write_text("//", encoding="utf-8")
            dest = Path(t) / "www"
            info = pw.preparar(web, dest, hub="https://hub.exemplo.test")
            self.assertGreater(info["arquivos"], 5)
            self.assertTrue((dest / "index.html").is_file())
            self.assertFalse((dest / "gestao.html").exists(), "Gestão nunca no app do cliente")
            self.assertFalse((dest / "app" / "sw.js").exists())
            self.assertTrue((dest / "app" / "manifest-plataforma.webmanifest").exists())
            self.assertTrue((dest / "sustainkit.html").exists() and (dest / "vendor" / "x.js").exists())
            for n in ("physis-ble.js", "physis-nativo.js", "primeiro-uso.html", "primeiro-uso.js"):
                self.assertTrue((dest / n).is_file(), n)
            idx = ler(dest / "index.html")
            cab = idx[:idx.index("</head>")]
            self.assertLess(cab.index('<meta charset="utf-8">'), cab.index("Content-Security-Policy"))
            self.assertLess(cab.index('src="physis-nativo.js"'), cab.index('src="physis-ble.js"'))
            self.assertIn("capacitor://localhost https://localhost", cab)
            self.assertIn("connect-src 'self' capacitor://localhost https://localhost blob: https://hub.exemplo.test;", cab)
            self.assertIn('src="physis-nativo.js"', ler(dest / "primeiro-uso.html"))
            # de novo: não duplica
            pw.preparar(web, dest)
            self.assertEqual(ler(dest / "index.html").count('src="physis-nativo.js"'), 1)
            self.assertIn("connect-src 'self' capacitor://localhost https://localhost blob: https:;", ler(dest / "index.html"))


class AplicarPlataformas(unittest.TestCase):
    MANIFESTO = ('<?xml version="1.0" encoding="utf-8"?>\n<manifest xmlns:android="http://schemas.android.com/apk/res/android">\n'
                 '    <application android:allowBackup="true" android:label="Physis">\n        <activity android:name=".MainActivity" />\n'
                 '    </application>\n    <uses-permission android:name="android.permission.INTERNET" />\n</manifest>\n')

    def test_android_idempotente(self):
        ap = modulo("aplicar_plataformas")
        novo, feito = ap.manifesto_android(self.MANIFESTO)
        self.assertTrue(feito)
        raiz = ET.fromstring(novo.encode("utf-8"))           # continua XML válido
        nomes = [e.get(ANDROID + "name") for e in raiz.iter("uses-permission")]
        self.assertIn("android.permission.BLUETOOTH_CONNECT", nomes)
        self.assertEqual(nomes.count("android.permission.BLUETOOTH_SCAN"), 1)
        self.assertEqual(raiz.find("application").get(ANDROID + "allowBackup"), "false")
        self.assertIsNotNone(raiz.find("application/service"))
        de_novo, feito2 = ap.manifesto_android(novo)
        self.assertEqual(feito2, [])
        self.assertEqual(de_novo, novo)
        g, f = ap.gradle_min_sdk("ext {\n    minSdkVersion = 22\n    targetSdkVersion = 34\n}")
        self.assertIn("minSdkVersion = 26", g)
        self.assertEqual(ap.gradle_min_sdk(g)[1], [])

    def test_ios(self):
        ap = modulo("aplicar_plataformas")
        base = plistlib.dumps({"CFBundleDevelopmentRegion": "en", "CFBundleName": "Physis", "UIBackgroundModes": ["audio"]})
        novo, feito = ap.info_plist(base)
        p = plistlib.loads(novo)
        self.assertEqual(p["CFBundleName"], "Physis")
        self.assertEqual(p["CFBundleDevelopmentRegion"], "pt-BR")
        self.assertEqual(p["UIBackgroundModes"], ["audio", "bluetooth-central"])
        self.assertEqual(ap.info_plist(novo)[1], [])
        t, f = ap.ios_minimo("platform :ios, '13.0'\nIPHONEOS_DEPLOYMENT_TARGET = 13.0;")
        self.assertIn("'15.0'", t)
        self.assertIn("= 15.0;", t)


class PaginaDownload(unittest.TestCase):
    def paleta(self):
        return {c.upper() for c in re.findall(r"`(#[0-9A-Fa-f]{6})`", ler(DOCS / "PALETA.md"))}

    def test_pagina(self):
        t = ler(APP / "site" / "baixar.html")
        self.assertEqual(len(re.findall(r"<h1\b", t)), 1)
        self.assertIn('<html lang="pt-BR">', t)
        self.assertIn('data-en="Get the Physis app"', t)
        for parte in ("Google Play", "App Store", "SHA-256", "apksigner verify", "Adicionar à Tela de Início",
                      "Instalar app", "Android 8.0", "iOS 15", "F-Droid", "Política de privacidade"):
            self.assertIn(parte, t, parte)
        for attr in re.findall(r'(?:href|src)="([^"]*)"', t):
            self.assertIsNone(URL_EXTERNA.search(attr), attr)
        self.assertIsNone(URL_EXTERNA.search(re.sub(r"<!--.*?-->", "", t, flags=re.S)))

    def test_cores_da_paleta(self):
        pal = self.paleta()
        for p in (APP / "site" / "baixar.html", APP / "www-extra" / "primeiro-uso.html"):
            for cor in re.findall(r"#[0-9A-Fa-f]{6}\b", ler(p)):
                with self.subTest(arquivo=p.name, cor=cor):
                    self.assertIn(cor.upper(), pal)

    def test_primeiro_uso(self):
        t = ler(APP / "www-extra" / "primeiro-uso.html")
        self.assertEqual(len(re.findall(r"<h1\b", t)), 1)
        self.assertIn('<label for="servidor">', t)
        self.assertIn('id="aceito"', t)
        self.assertIn('role="status"', t)

    def test_publicar(self):
        pb = modulo("publicar_baixar")
        with tempfile.TemporaryDirectory() as t:
            apk = Path(t) / "app-release.apk"
            apk.write_bytes(b"PK\x03\x04 apk de teste")
            r = pb.publicar(Path(t) / "saida", apk, "0.1.0", "https://hub.exemplo.test", url_play="https://loja.exemplo.test/app")
            pagina = ler(Path(t) / "saida" / "baixar.html")
            soma = hashlib.sha256(apk.read_bytes()).hexdigest()
            self.assertEqual(r["sha256"], soma)
            self.assertIn(soma, pagina)
            self.assertIn(soma, ler(Path(t) / "saida" / "android.apk.sha256"))
            self.assertEqual(sorted(r["qr"]), ["apk", "play", "pwa"])
            self.assertEqual(pagina.count("<svg"), 3)
            self.assertIn('href="/app/android.apk"', pagina)
            self.assertIn("QR da App Store: gerado na publicação", pagina)    # sem endereço, fica o marcador


class QR(unittest.TestCase):
    def setUp(self):
        self.qr = modulo("qr")

    def test_bch(self):
        self.assertEqual(self.qr.bits_formato(0), 0x5412)       # nível M, máscara 0 (tabela da norma)
        self.assertEqual(self.qr.bits_versao(7), 0x07C94)
        self.assertEqual([self.qr.capacidade(v) for v in (1, 2, 5, 10)], [16, 28, 86, 216])

    def test_reed_solomon(self):
        div = self.qr.rs_divisor(10)
        dados = list(range(16))
        palavra = dados + self.qr.rs_resto(dados, div)
        self.assertEqual(self.qr.rs_resto(palavra, div), [0] * 10)     # múltiplo do gerador

    def test_matriz(self):
        texto = "https://hub.exemplo.test/app/android.apk"
        m = self.qr.gerar(texto)
        v, _ = self.qr.codificar_dados(texto)
        n = 4 * v + 17
        self.assertEqual((len(m), len(m[0])), (n, n))
        for cx, cy in ((0, 0), (n - 7, 0), (0, n - 7)):             # três localizadores 7x7
            self.assertTrue(all(m[cy][cx + i] and m[cy + 6][cx + i] and m[cy + i][cx] and m[cy + i][cx + 6] for i in range(7)))
            self.assertTrue(m[cy + 3][cx + 3])
        self.assertTrue(m[n - 8][8], "módulo escuro fixo")
        bits = 0
        pos = [(8, i) for i in range(6)] + [(8, 7), (8, 8), (7, 8)] + [(14 - i, 8) for i in range(9, 15)]
        for i, (x, y) in enumerate(pos):
            bits |= int(m[y][x]) << i
        self.assertIn(bits, [self.qr.bits_formato(k) for k in range(8)], "formato nível M válido")
        svg = self.qr.svg(texto, "Baixar")
        self.assertIn('role="img"', svg)
        self.assertIn("<title>Baixar</title>", svg)

    def test_longo_demais(self):
        with self.assertRaises(ValueError):
            self.qr.svg("x" * 400)


if __name__ == "__main__":
    unittest.main()
