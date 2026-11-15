"""Ícones e telas de abertura do app nativo (Android e iPhone), a partir da mesma árvore do logo dos ícones do PWA.

Uso (de dentro de app-nativo/):
    python scripts/gerar_icones.py               # gera em recursos/
    python scripts/gerar_icones.py --aplicar     # gera e copia para android/ e ios/ (se já existem: npx cap add …)

Reaproveita physis-hub/physis_hub/app_pwa.py (leitor/gravador de PNG sem PIL e o recorte da árvore do logo
embutido no painel.html). Mesmas cores: árvore #F4F6F1 sobre o verde #33512F. Só biblioteca padrão.

Saída em recursos/:
  android/res/mipmap-<dpi>/ic_launcher.png, ic_launcher_round.png, ic_launcher_foreground.png (ícone adaptativo)
  android/res/values/ic_launcher_background.xml (fundo do ícone adaptativo: #33512F)
  android/res/drawable-<dpi>/ic_stat_physis.png (ícone pequeno das notificações: só a forma, branca, fundo transparente)
  android/res/drawable/splash.png (1280×1280; ao aplicar, substitui TODOS os splash.png do projeto Android)
  ios/AppIcon-512@2x.png (1024×1024, sem canal alfa, como a App Store exige)
  ios/splash-2732x2732.png, splash-2732x2732-1.png, splash-2732x2732-2.png
"""
from __future__ import annotations

import argparse
import shutil
import struct
import sys
import zlib
from pathlib import Path

AQUI = Path(__file__).resolve().parent.parent
RAIZ = AQUI.parent
sys.path.insert(0, str(RAIZ / "physis-hub"))
from physis_hub import app_pwa  # noqa: E402

VERDE, CLARO = app_pwa.VERDE, app_pwa.CLARO
DPI = {"mdpi": 1.0, "hdpi": 1.5, "xhdpi": 2.0, "xxhdpi": 3.0, "xxxhdpi": 4.0}


def png(larg: int, alt: int, linhas: list[bytes], canais: int) -> bytes:
    """PNG 8 bits RGB (canais=3) ou RGBA (canais=4); `linhas` já em bytes, sem o filtro."""
    cru = b"".join(b"\x00" + ln for ln in linhas)
    def bloco(cod: bytes, corpo: bytes) -> bytes:
        return struct.pack(">I", len(corpo)) + cod + corpo + struct.pack(">I", zlib.crc32(cod + corpo) & 0xFFFFFFFF)
    tipo = 2 if canais == 3 else 6
    return (b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", struct.pack(">IIBBBBB", larg, alt, 8, tipo, 0, 0, 0))
            + bloco(b"IDAT", zlib.compress(cru, 9)) + bloco(b"IEND", b""))


class Arvore:
    def __init__(self):
        self.fonte = app_pwa.ler_png(app_pwa.logo_do_painel(RAIZ / "physis-hub" / "web" / "painel.html"))
        self.caixa = app_pwa._arvore(*self.fonte)

    def alfas(self, lado: int, ocupar: float) -> list[list[float]]:
        """Cobertura (0..1) da árvore num quadrado `lado`, ocupando `ocupar` do lado (mesma conta de app_pwa._icone)."""
        larg, alt, px = self.fonte
        x0, y0, x1, y1 = self.caixa
        w, h = x1 - x0, y1 - y0
        esc = ocupar * lado / max(w, h)
        ox, oy = (lado - w * esc) / 2, (lado - h * esc) / 2

        def a(x, y):
            return px[y * larg + x][3] / 255.0 if x0 <= x < x1 and y0 <= y < y1 else 0.0
        out = []
        for Y in range(lado):
            sy = (Y + 0.5 - oy) / esc + y0 - 0.5
            iy = int(sy // 1)
            fy = sy - iy
            linha = []
            for X in range(lado):
                sx = (X + 0.5 - ox) / esc + x0 - 0.5
                if sx < x0 - 1 or sx > x1 or sy < y0 - 1 or sy > y1:
                    linha.append(0.0)
                    continue
                ix = int(sx // 1)
                fx = sx - ix
                v = (a(ix, iy) * (1 - fx) * (1 - fy) + a(ix + 1, iy) * fx * (1 - fy)
                     + a(ix, iy + 1) * (1 - fx) * fy + a(ix + 1, iy + 1) * fx * fy)
                linha.append(min(1.0, max(0.0, (v - 0.08) * 1.35)))
            out.append(linha)
        return out


def mistura(fundo, tinta, a):
    return bytes(round(fundo[i] + (tinta[i] - fundo[i]) * a) for i in range(3))


def icone(arv: Arvore, lado: int, ocupar: float, redondo: bool = False, alfa: bool = True) -> bytes:
    al = arv.alfas(lado, ocupar)
    r2 = (lado / 2) ** 2
    linhas = []
    for y, linha in enumerate(al):
        b = bytearray()
        for x, a in enumerate(linha):
            b += mistura(VERDE, CLARO, a)
            if alfa:
                dentro = not redondo or (x + 0.5 - lado / 2) ** 2 + (y + 0.5 - lado / 2) ** 2 <= r2
                b.append(255 if dentro else 0)
        linhas.append(bytes(b))
    return png(lado, lado, linhas, 4 if alfa else 3)


def silhueta(arv: Arvore, lado: int, ocupar: float, cor=(255, 255, 255)) -> bytes:
    """Só a forma, numa cor, sobre fundo transparente (camada da frente do ícone adaptativo; ícone de notificação)."""
    linhas = [b"".join(bytes(cor) + bytes((round(255 * a),)) for a in linha) for linha in arv.alfas(lado, ocupar)]
    return png(lado, lado, linhas, 4)


def abertura(arv: Arvore, lado: int, ocupar: float = 0.3, alfa: bool = False) -> bytes:
    """Tela de abertura: verde liso com a árvore no centro (só o miolo é calculado; o resto é cor lisa)."""
    miolo = max(8, round(lado * ocupar))
    al = arv.alfas(miolo, 1.0)
    pad = b"\xff" if alfa else b""
    liso = (bytes(VERDE) + pad) * lado
    ini = (lado - miolo) // 2
    linhas = []
    for y in range(lado):
        if ini <= y < ini + miolo:
            meio = b"".join(mistura(VERDE, CLARO, a) + pad for a in al[y - ini])
            linhas.append((bytes(VERDE) + pad) * ini + meio + (bytes(VERDE) + pad) * (lado - ini - miolo))
        else:
            linhas.append(liso)
    return png(lado, lado, linhas, 4 if alfa else 3)


def gerar(saida: Path) -> list[Path]:
    arv = Arvore()
    feitos = []

    def gravar(rel: str, dados: bytes):
        p = saida / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(dados)
        feitos.append(p)

    for d, f in DPI.items():
        gravar(f"android/res/mipmap-{d}/ic_launcher.png", icone(arv, round(48 * f), 0.78))
        gravar(f"android/res/mipmap-{d}/ic_launcher_round.png", icone(arv, round(48 * f), 0.62, redondo=True))
        # camada da frente: 108 dp, árvore dentro da zona segura (66 dp de diâmetro)
        gravar(f"android/res/mipmap-{d}/ic_launcher_foreground.png", silhueta(arv, round(108 * f), 0.5, CLARO))
        gravar(f"android/res/drawable-{d}/ic_stat_physis.png", silhueta(arv, round(24 * f), 0.9))
    p = saida / "android/res/values/ic_launcher_background.xml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
                 '    <color name="ic_launcher_background">#33512F</color>\n</resources>\n', encoding="utf-8", newline="\n")
    feitos.append(p)
    gravar("android/res/drawable/splash.png", abertura(arv, 1280, alfa=True))
    gravar("ios/AppIcon-512@2x.png", icone(arv, 1024, 0.78, alfa=False))
    tela = abertura(arv, 2732)
    for n in ("splash-2732x2732.png", "splash-2732x2732-1.png", "splash-2732x2732-2.png"):
        gravar(f"ios/{n}", tela)
    return feitos


def aplicar(saida: Path) -> list[str]:
    feito = []
    res = AQUI / "android" / "app" / "src" / "main" / "res"
    if res.is_dir():
        for p in (saida / "android" / "res").rglob("*"):
            if p.is_file() and p.name != "splash.png":
                alvo = res / p.relative_to(saida / "android" / "res")
                alvo.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, alvo)
        for s in res.rglob("splash.png"):                 # todas as variantes (port/land/dpi) ficam iguais
            shutil.copy2(saida / "android/res/drawable/splash.png", s)
        feito.append(str(res))
    xc = AQUI / "ios" / "App" / "App" / "Assets.xcassets"
    if xc.is_dir():
        shutil.copy2(saida / "ios/AppIcon-512@2x.png", xc / "AppIcon.appiconset" / "AppIcon-512@2x.png")
        for n in ("splash-2732x2732.png", "splash-2732x2732-1.png", "splash-2732x2732-2.png"):
            if (xc / "Splash.imageset").is_dir():
                shutil.copy2(saida / "ios" / n, xc / "Splash.imageset" / n)
        feito.append(str(xc))
    return feito


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Ícones e telas de abertura do app nativo Physis")
    ap.add_argument("--saida", type=Path, default=AQUI / "recursos")
    ap.add_argument("--aplicar", action="store_true", help="copiar para android/ e ios/ (depois de npx cap add)")
    a = ap.parse_args(argv)
    for p in gerar(a.saida):
        print(p)
    if a.aplicar:
        lugares = aplicar(a.saida)
        print("aplicado em:", ", ".join(lugares) if lugares else "nada (rode antes: npx cap add android / ios)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
