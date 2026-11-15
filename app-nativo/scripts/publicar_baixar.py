"""Prepara a página de download (site/baixar.html) para publicar: endereços, QR (SVG, gerado aqui), versão e SHA-256 do APK.

Uso (de dentro de app-nativo/):
    python scripts/publicar_baixar.py --apk android/app/build/outputs/apk/release/app-release.apk \
        --versao 0.1.0 --url-base https://SERVIDOR \
        --url-play https://play.google.com/store/apps/details?id=br.com.physisengineering.app \
        --url-appstore https://apps.apple.com/app/idNNNN --certificado AA:BB:…

Saída em site/publicar/ (fora do Git): baixar.html, android.apk e android.apk.sha256 — o que a rota
GET /app/baixar e /app/android.apk do hub entregam (ver physis-hub/docs/APP_NATIVO.md).
Endereço não informado fica como [MARCADOR] e o QR dele não é gerado. Só biblioteca padrão.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import re
import shutil
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import qr  # noqa: E402

MODELO = AQUI / "site" / "baixar.html"
QR_ROTULO = {"play": "Código QR: abrir no Google Play", "apk": "Código QR: baixar o APK",
             "appstore": "Código QR: abrir na App Store", "pwa": "Código QR: abrir a plataforma no navegador"}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def tamanho(n: int) -> str:
    return f"{n / 1048576:.1f} MB".replace(".", ",")


def preencher(modelo: str, textos: dict[str, str], links: dict[str, str], qrs: dict[str, str]) -> str:
    for k, v in textos.items():
        modelo = re.sub(rf'(data-preencher="{k}">)[^<]*(<)', lambda m: m.group(1) + html.escape(v) + m.group(2), modelo)
    for k, v in links.items():
        modelo = re.sub(rf'data-preencher-href="{k}" href="[^"]*"', f'data-preencher-href="{k}" href="{html.escape(v, quote=True)}"', modelo)
    for k, v in qrs.items():
        modelo = re.sub(rf"<!--QR:{k}-->.*?<!--/QR:{k}-->", lambda m: f"<!--QR:{k}-->{v}<!--/QR:{k}-->", modelo, flags=re.S)
    return modelo


def publicar(saida: Path, apk: Path | None = None, versao: str = "", url_base: str = "", url_play: str = "",
             url_appstore: str = "", certificado: str = "", url_termos: str = "", url_privacidade: str = "") -> dict:
    saida.mkdir(parents=True, exist_ok=True)
    base = url_base.rstrip("/")
    links = {"url-play": url_play, "url-appstore": url_appstore,
             "url-apk": "/app/android.apk" if apk else "",
             "url-termos": url_termos, "url-privacidade": url_privacidade}
    links = {k: v for k, v in links.items() if v}
    textos = {}
    if versao:
        textos["versao"] = versao
    if certificado:
        textos["certificado"] = certificado
    if apk:
        textos["sha256"] = sha256(apk)
        textos["tamanho"] = tamanho(apk.stat().st_size)
        shutil.copy2(apk, saida / "android.apk")
        (saida / "android.apk.sha256").write_text(f"{textos['sha256']}  android.apk\n", encoding="utf-8", newline="\n")
    alvos = {"play": url_play, "appstore": url_appstore,
             "apk": base + "/app/android.apk" if (apk and base) else "", "pwa": base + "/" if base else ""}
    qrs = {k: qr.svg(v, QR_ROTULO[k]) for k, v in alvos.items() if v}
    pagina = preencher(MODELO.read_text(encoding="utf-8"), textos, links, qrs)
    (saida / "baixar.html").write_text(pagina, encoding="utf-8", newline="\n")
    return {"saida": str(saida), "qr": sorted(qrs), **textos}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Página de download do app Physis")
    ap.add_argument("--saida", type=Path, default=AQUI / "site" / "publicar")
    ap.add_argument("--apk", type=Path)
    ap.add_argument("--versao", default="")
    ap.add_argument("--url-base", default="", help="https://… do servidor que entrega /app/baixar")
    ap.add_argument("--url-play", default="")
    ap.add_argument("--url-appstore", default="")
    ap.add_argument("--url-termos", default="")
    ap.add_argument("--url-privacidade", default="")
    ap.add_argument("--certificado", default="", help="SHA-256 do certificado (apksigner verify --print-certs)")
    a = ap.parse_args(argv)
    for nome in ("url_base", "url_play", "url_appstore"):
        v = getattr(a, nome)
        if v and not v.startswith("https://"):
            ap.error(f"--{nome.replace('_', '-')} tem de começar com https://")
    print(publicar(a.saida, a.apk, a.versao, a.url_base, a.url_play, a.url_appstore, a.certificado, a.url_termos, a.url_privacidade))
    return 0


if __name__ == "__main__":
    sys.exit(main())
