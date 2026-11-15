"""Põe as permissões e os textos do app Physis nos projetos gerados pelo Capacitor (rodar depois de "npx cap add").

Uso (de dentro de app-nativo/):
    python scripts/aplicar_plataformas.py            # android/ e ios/, o que existir
    python scripts/aplicar_plataformas.py --conferir # só diz o que falta, não muda nada (sai com 1 se faltar)

Android (android/):
  - app/src/main/AndroidManifest.xml: permissões BLE (BLUETOOTH_SCAN neverForLocation, BLUETOOTH_CONNECT; antigas e
    localização só até a API 30), avisos, serviço em primeiro plano (connectedDevice), sem backup na nuvem;
  - variables.gradle: minSdkVersion 26 (Android 8.0).
iPhone (ios/App/):
  - App/Info.plist: textos de permissão em português, modo de fundo bluetooth-central, região pt-BR;
  - Podfile e App.xcodeproj/project.pbxproj: iOS 15.0 no mínimo;
  - App/PrivacyInfo.xcprivacy (depois, acrescentar ao alvo "App" no Xcode).
Pode rodar várias vezes: não duplica nada. Só biblioteca padrão.
"""
from __future__ import annotations

import argparse
import plistlib
import re
import shutil
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent.parent
TRECHO_ANDROID = AQUI / "plataformas" / "android" / "AndroidManifest.trecho.xml"
TRECHO_IOS = AQUI / "plataformas" / "ios" / "Info.trecho.plist"
PRIVACIDADE_IOS = AQUI / "plataformas" / "ios" / "PrivacyInfo.xcprivacy"
MIN_SDK = 26          # Android 8.0
IOS_MIN = "15.0"
NS_TOOLS = 'xmlns:tools="http://schemas.android.com/tools"'


def _parte(trecho: str, nome: str) -> str:
    m = re.search(rf"<{nome}>(.*?)</{nome}>", trecho, flags=re.S)
    return m.group(1) if m else ""


def _elementos(bloco: str) -> list[str]:
    """Elementos de uma parte do trecho (sem comentários), cada um como texto."""
    bloco = re.sub(r"<!--.*?-->", "", bloco, flags=re.S)
    return [m.group(0) for m in re.finditer(r"<(uses-permission|uses-feature|service|receiver)\b.*?/>", bloco, flags=re.S)]


def _nome(el: str) -> str:
    m = re.search(r'android:name="([^"]+)"', el)
    return m.group(1) if m else el


def manifesto_android(texto: str, trecho: str | None = None) -> tuple[str, list[str]]:
    """(novo texto, o que foi acrescentado)."""
    trecho = trecho if trecho is not None else TRECHO_ANDROID.read_text(encoding="utf-8")
    feito = []
    if NS_TOOLS not in texto:
        texto = re.sub(r"<manifest\b", "<manifest " + NS_TOOLS, texto, count=1)
        feito.append("xmlns:tools")
    novos = [el for el in _elementos(_parte(trecho, "permissoes")) if f'android:name="{_nome(el)}"' not in texto]
    if novos:
        i = texto.index("<application")
        texto = texto[:i] + "".join("    " + " ".join(el.split()) + "\n" for el in novos) + "\n    " + texto[i:]
        feito += [_nome(el) for el in novos]
    m = re.search(r"<aplicacao\s+(.*?)/>", trecho, flags=re.S)
    if m:
        for at, val in re.findall(r'(android:\w+)="([^"]*)"', m.group(1)):
            tag = re.search(r"<application\b[^>]*>", texto, flags=re.S)
            t = tag.group(0)
            if re.search(rf'{at}="{re.escape(val)}"', t):
                continue
            nt = re.sub(rf'{at}="[^"]*"', f'{at}="{val}"', t) if at + "=" in t else t.replace("<application", f'<application {at}="{val}"', 1)
            texto = texto.replace(t, nt, 1)
            feito.append(f"{at}={val}")
    novos = [el for el in _elementos(_parte(trecho, "servicos")) if f'android:name="{_nome(el)}"' not in texto]
    if novos:
        i = texto.rindex("</application>")
        texto = texto[:i] + "".join("        " + " ".join(el.split()) + "\n" for el in novos) + "    " + texto[i:]
        feito += [_nome(el) for el in novos]
    return texto, feito


def gradle_min_sdk(texto: str) -> tuple[str, list[str]]:
    m = re.search(r"minSdkVersion\s*=\s*(\d+)", texto)
    if m and int(m.group(1)) < MIN_SDK:
        return texto.replace(m.group(0), f"minSdkVersion = {MIN_SDK}", 1), [f"minSdkVersion {m.group(1)} -> {MIN_SDK}"]
    return texto, []


def info_plist(dados: bytes, trecho: bytes | None = None) -> tuple[bytes, list[str]]:
    info = plistlib.loads(dados)
    extra = plistlib.loads(trecho if trecho is not None else TRECHO_IOS.read_bytes())
    feito = []
    for k, v in extra.items():
        if k == "UIBackgroundModes":
            atual = list(info.get(k, []))
            falta = [x for x in v if x not in atual]
            if falta:
                info[k] = atual + falta
                feito.append(k)
        elif info.get(k) != v:
            info[k] = v
            feito.append(k)
    return (plistlib.dumps(info, fmt=plistlib.FMT_XML, sort_keys=False) if feito else dados), feito


def ios_minimo(texto: str) -> tuple[str, list[str]]:
    feito = []
    novo = re.sub(r"platform :ios, '[\d.]+'", f"platform :ios, '{IOS_MIN}'", texto)
    novo = re.sub(r"IPHONEOS_DEPLOYMENT_TARGET = [\d.]+;", f"IPHONEOS_DEPLOYMENT_TARGET = {IOS_MIN};", novo)
    if novo != texto:
        feito.append(f"iOS mínimo {IOS_MIN}")
    return novo, feito


def _aplicar_texto(p: Path, func, conferir: bool, rel: list[str]):
    if not p.is_file():
        return
    antigo = p.read_text(encoding="utf-8")
    novo, feito = func(antigo)
    if feito:
        rel.append(f"{p.relative_to(AQUI)}: {', '.join(feito)}")
        if not conferir:
            p.write_text(novo, encoding="utf-8", newline="\n")


def aplicar(conferir: bool = False) -> list[str]:
    rel: list[str] = []
    and_ = AQUI / "android"
    _aplicar_texto(and_ / "app" / "src" / "main" / "AndroidManifest.xml", manifesto_android, conferir, rel)
    _aplicar_texto(and_ / "variables.gradle", gradle_min_sdk, conferir, rel)
    app = AQUI / "ios" / "App"
    pl = app / "App" / "Info.plist"
    if pl.is_file():
        novo, feito = info_plist(pl.read_bytes())
        if feito:
            rel.append(f"{pl.relative_to(AQUI)}: {', '.join(feito)}")
            if not conferir:
                pl.write_bytes(novo)
    _aplicar_texto(app / "Podfile", ios_minimo, conferir, rel)
    _aplicar_texto(app / "App.xcodeproj" / "project.pbxproj", ios_minimo, conferir, rel)
    priv = app / "App" / "PrivacyInfo.xcprivacy"
    if (app / "App").is_dir() and (not priv.is_file() or priv.read_bytes() != PRIVACIDADE_IOS.read_bytes()):
        rel.append(f"{priv.relative_to(AQUI)}: copiado (acrescente ao alvo App no Xcode)")
        if not conferir:
            shutil.copy2(PRIVACIDADE_IOS, priv)
    return rel


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Permissões e textos do app Physis nos projetos Android e iOS")
    ap.add_argument("--conferir", action="store_true", help="só mostrar o que falta")
    a = ap.parse_args(argv)
    if not (AQUI / "android").is_dir() and not (AQUI / "ios").is_dir():
        print("Nada a fazer: rode antes  npx cap add android  e/ou  npx cap add ios")
        return 0
    rel = aplicar(a.conferir)
    print("\n".join(rel) if rel else "Tudo em dia.")
    return 1 if (a.conferir and rel) else 0


if __name__ == "__main__":
    sys.exit(main())
