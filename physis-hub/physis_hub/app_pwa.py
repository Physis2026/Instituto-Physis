"""App instalável (PWA) da plataforma e da Gestão — só biblioteca padrão.

O que fica aqui:
  * ARQUIVOS: a lista fechada do que o servidor entrega em /app/<arquivo> e o tipo (MIME) de cada um;
  * resposta(nome): bytes + cabeçalhos prontos para a rota /app/ do servidor;
  * versao(web): uma "impressão digital" curta das telas e bibliotecas. Ela entra no sw.js no lugar de
    __VERSAO__; quando qualquer tela muda, o sw.js muda, o celular baixa o service worker novo e
    apaga os caches velhos;
  * ler_png / gravar_png / gerar_icones: os ícones saem da árvore do logo embutido no painel.html,
    sem PIL (decodifica o PNG com zlib, amplia com interpolação bilinear e grava de novo).

Regerar os ícones:  python -m physis_hub.app_pwa
"""
from __future__ import annotations

import base64
import hashlib
import re
import struct
import threading
import zlib
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
PASTA = WEB / "app"

# só estes arquivos saem de /app/; qualquer outro nome é 404 (nunca um caminho qualquer do disco)
ARQUIVOS = {
    "manifest-plataforma.webmanifest": "application/manifest+json; charset=utf-8",
    "manifest-gestao.webmanifest": "application/manifest+json; charset=utf-8",
    "sw.js": "text/javascript; charset=utf-8",
    "icone-192.png": "image/png",
    "icone-512.png": "image/png",
    "icone-maskable-512.png": "image/png",
}

MARCA_VERSAO = "__VERSAO__"

# o que entra na impressão digital: as telas que o service worker guarda e as bibliotecas de /vendor/
_TELAS = ("painel.html", "gestao.html", "planejador.html")
_VENDOR = ("maplibre-gl.js", "maplibre-gl.css", "pmtiles.js", "web-ifc-api-iife.js", "web-ifc.wasm", "three.min.js")

_trava = threading.Lock()
_memo: dict[str, tuple[int, int, str]] = {}  # caminho -> (mtime_ns, tamanho, sha256) — não relê arquivo que não mudou


def _hash_arquivo(p: Path) -> str | None:
    try:
        st = p.stat()
    except OSError:
        return None
    chave = str(p)
    with _trava:
        m = _memo.get(chave)
        if m and m[0] == st.st_mtime_ns and m[1] == st.st_size:
            return m[2]
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for pedaco in iter(lambda: f.read(1 << 20), b""):
            h.update(pedaco)
    d = h.hexdigest()
    with _trava:
        _memo[chave] = (st.st_mtime_ns, st.st_size, d)
    return d


def versao(web: Path | None = None) -> str:
    """12 caracteres que mudam quando muda qualquer tela, biblioteca ou arquivo do app."""
    web = Path(web) if web else WEB
    caminhos = [web / n for n in _TELAS]
    for n in _VENDOR:
        caminhos += [web / "vendor" / n, web.parent.parent / "vendor" / n]
    caminhos += [web / "app" / n for n in sorted(ARQUIVOS)]
    h = hashlib.sha256()
    for p in caminhos:
        d = _hash_arquivo(p)
        if d:
            h.update(p.name.encode() + b"\0" + d.encode() + b"\n")
    return h.hexdigest()[:12]


def resposta(nome: str, web: Path | None = None) -> tuple[bytes, dict[str, str]] | None:
    """(corpo, cabeçalhos) do arquivo /app/<nome>, ou None se o nome não está na lista ou falta o arquivo."""
    tipo = ARQUIVOS.get(nome)
    web = Path(web) if web else WEB
    arq = web / "app" / nome
    if not tipo or not arq.is_file():
        return None
    dados = arq.read_bytes()
    cab = {"Content-Type": tipo}
    if nome == "sw.js":
        dados = dados.replace(MARCA_VERSAO.encode(), versao(web).encode())
        # o service worker mora em /app/ mas cuida do site inteiro (escopo "/")
        cab["Service-Worker-Allowed"] = "/"
        # sempre conferir com o servidor: é assim que a versão nova chega ao celular
        cab["Cache-Control"] = "no-cache"
    elif nome.endswith(".webmanifest"):
        cab["Cache-Control"] = "no-cache"
    else:
        cab["Cache-Control"] = "public, max-age=86400"
    cab["Content-Length"] = str(len(dados))
    return dados, cab


# ───────────────────────── PNG sem PIL ─────────────────────────

def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def ler_png(dados: bytes) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    """Decodifica um PNG (não entrelaçado; 8 bits, ou paleta de 1/2/4/8 bits) em (largura, altura, pixels RGBA)."""
    if dados[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("não é PNG")
    pos, idat, plte, trns = 8, b"", None, None
    larg = alt = prof = tipo = entrel = 0
    while pos < len(dados):
        n, = struct.unpack(">I", dados[pos:pos + 4])
        cod, corpo = dados[pos + 4:pos + 8], dados[pos + 8:pos + 8 + n]
        pos += 12 + n
        if cod == b"IHDR":
            larg, alt, prof, tipo, _, _, entrel = struct.unpack(">IIBBBBB", corpo)
        elif cod == b"PLTE":
            plte = [tuple(corpo[i:i + 3]) for i in range(0, len(corpo), 3)]
        elif cod == b"tRNS":
            trns = corpo
        elif cod == b"IDAT":
            idat += corpo
        elif cod == b"IEND":
            break
    if entrel:
        raise ValueError("PNG entrelaçado não suportado")
    canais = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[tipo]
    if tipo != 3 and prof != 8:
        raise ValueError("só 8 bits por canal")
    bits = canais * prof
    bpp = max(1, bits // 8)
    linha = (larg * bits + 7) // 8
    cru = zlib.decompress(idat)
    ant = bytearray(linha)
    px: list[tuple[int, int, int, int]] = []
    for y in range(alt):
        f = cru[y * (linha + 1)]
        L = bytearray(cru[y * (linha + 1) + 1:(y + 1) * (linha + 1)])
        for i in range(linha):
            a = L[i - bpp] if i >= bpp else 0
            b = ant[i]
            c = ant[i - bpp] if i >= bpp else 0
            if f == 1:
                L[i] = (L[i] + a) & 255
            elif f == 2:
                L[i] = (L[i] + b) & 255
            elif f == 3:
                L[i] = (L[i] + ((a + b) >> 1)) & 255
            elif f == 4:
                L[i] = (L[i] + _paeth(a, b, c)) & 255
        ant = L
        for x in range(larg):
            if tipo == 3:
                if prof == 8:
                    k = L[x]
                else:
                    por = 8 // prof
                    k = (L[x // por] >> (8 - prof * (x % por + 1))) & ((1 << prof) - 1)
                r, g, b_ = plte[k]
                al = trns[k] if trns and k < len(trns) else 255
                px.append((r, g, b_, al))
            elif tipo == 6:
                px.append(tuple(L[x * 4:x * 4 + 4]))
            elif tipo == 2:
                r, g, b_ = L[x * 3:x * 3 + 3]
                px.append((r, g, b_, 255))
            elif tipo == 4:
                v, al = L[x * 2:x * 2 + 2]
                px.append((v, v, v, al))
            else:
                v = L[x]
                px.append((v, v, v, 255))
    return larg, alt, px


def gravar_png(larg: int, alt: int, px: list[tuple[int, int, int, int]]) -> bytes:
    """PNG RGBA 8 bits (filtro 0 em toda linha; o zlib comprime bem o fundo liso)."""
    cru = bytearray()
    for y in range(alt):
        cru.append(0)
        for r, g, b, a in px[y * larg:(y + 1) * larg]:
            cru += bytes((r, g, b, a))
    def bloco(cod: bytes, corpo: bytes) -> bytes:
        return struct.pack(">I", len(corpo)) + cod + corpo + struct.pack(">I", zlib.crc32(cod + corpo) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", struct.pack(">IIBBBBB", larg, alt, 8, 6, 0, 0, 0))
            + bloco(b"IDAT", zlib.compress(bytes(cru), 9)) + bloco(b"IEND", b""))


def logo_do_painel(painel: Path | None = None) -> bytes:
    """O PNG do logo da faixa do painel (`.px-faixa .px-id img`, embutido em base64)."""
    t = Path(painel or WEB / "painel.html").read_text(encoding="utf-8")
    m = re.search(r'class="px-id"\s*>\s*<img[^>]*?src="data:image/png;base64,([A-Za-z0-9+/=]+)"', t)
    if not m:
        raise ValueError("logo da faixa não encontrado no painel.html")
    return base64.b64decode(m.group(1))


def _arvore(larg: int, alt: int, px: list) -> tuple[int, int, int, int]:
    """Caixa (x0, y0, x1, y1) da árvore: o primeiro bloco de colunas com tinta, antes do vão que separa o texto."""
    cols = [any(px[y * larg + x][3] > 24 for y in range(alt)) for x in range(larg)]
    x0 = cols.index(True)
    x1 = x0
    vazio = 0
    for x in range(x0, larg):
        if cols[x]:
            x1, vazio = x, 0
        else:
            vazio += 1
            if vazio >= 6:
                break
    linhas = [y for y in range(alt) if any(px[y * larg + x][3] > 24 for x in range(x0, x1 + 1))]
    return x0, linhas[0], x1 + 1, linhas[-1] + 1


def _icone(lado: int, fonte: tuple, caixa: tuple, ocupar: float, fundo: tuple, tinta: tuple) -> bytes:
    """Ícone quadrado: fundo liso e a árvore (só a forma, pintada na cor `tinta`) ampliada e centrada."""
    larg, alt, px = fonte
    x0, y0, x1, y1 = caixa
    w, h = x1 - x0, y1 - y0
    esc = ocupar * lado / max(w, h)
    ox, oy = (lado - w * esc) / 2, (lado - h * esc) / 2

    def alfa(x: int, y: int) -> float:
        if x0 <= x < x1 and y0 <= y < y1:
            return px[y * larg + x][3] / 255.0
        return 0.0

    saida = []
    for Y in range(lado):
        sy = (Y + 0.5 - oy) / esc + y0 - 0.5
        iy = int(sy // 1)
        fy = sy - iy
        for X in range(lado):
            sx = (X + 0.5 - ox) / esc + x0 - 0.5
            ix = int(sx // 1)
            fx = sx - ix
            a = (alfa(ix, iy) * (1 - fx) * (1 - fy) + alfa(ix + 1, iy) * fx * (1 - fy)
                 + alfa(ix, iy + 1) * (1 - fx) * fy + alfa(ix + 1, iy + 1) * fx * fy)
            # realce leve da borda: a ampliação bilinear de traço fino fica pálida
            a = min(1.0, max(0.0, (a - 0.08) * 1.35))
            saida.append(tuple(round(fundo[i] + (tinta[i] - fundo[i]) * a) for i in range(3)) + (255,))
    return gravar_png(lado, lado, saida)


VERDE = (0x33, 0x51, 0x2F)   # #33512F
CLARO = (0xF4, 0xF6, 0xF1)   # #F4F6F1


def gerar_icones(destino: Path | None = None, painel: Path | None = None) -> list[Path]:
    """Gera icone-192.png, icone-512.png e icone-maskable-512.png (árvore clara sobre o verde Physis)."""
    destino = Path(destino or PASTA)
    destino.mkdir(parents=True, exist_ok=True)
    fonte = ler_png(logo_do_painel(painel))
    caixa = _arvore(*fonte)
    feitos = []
    # "any": a árvore ocupa 78%; "maskable": cabe na zona segura (círculo de 80%), então 58%
    for nome, lado, ocupar in (("icone-192.png", 192, 0.78), ("icone-512.png", 512, 0.78), ("icone-maskable-512.png", 512, 0.58)):
        p = destino / nome
        p.write_bytes(_icone(lado, fonte, caixa, ocupar, VERDE, CLARO))
        feitos.append(p)
    return feitos


if __name__ == "__main__":
    for p in gerar_icones():
        print(p)
