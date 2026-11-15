"""Código QR em SVG, sem biblioteca e sem serviço de fora (só biblioteca padrão).

Modo byte (UTF-8), correção de erro nível M (~15%), versões 1 a 10 (até 213 bytes: sobra para um endereço).
Segue a norma ISO/IEC 18004 na estrutura descrita pela implementação de referência de Project Nayuki
(Reed-Solomon em GF(256) com 0x11D, máscaras 0–7 escolhidas pela menor penalidade).

    from qr import svg
    open("qr.svg", "w").write(svg("https://exemplo.org/app/android.apk", rotulo="Baixar o APK"))

Conferir com a câmera de um celular antes de publicar (o teste confere estrutura, não a leitura).
"""
from __future__ import annotations

# nível M, versões 1..10
ECC_POR_BLOCO = (None, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26)
BLOCOS = (None, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5)
ALINHAMENTO = (None, (), (6, 18), (6, 22), (6, 26), (6, 30), (6, 34), (6, 22, 38), (6, 24, 42), (6, 26, 46), (6, 28, 50))
BITS_NIVEL_M = 0
VERSAO_MAX = 10


def modulos_dados(v: int) -> int:
    """Quantos módulos sobram para dados+correção depois dos padrões fixos."""
    r = (16 * v + 128) * v + 64
    if v >= 2:
        n = v // 7 + 2
        r -= (25 * n - 10) * n - 55
        if v >= 7:
            r -= 36
    return r


def capacidade(v: int) -> int:
    """Bytes de dados (antes da correção) da versão v no nível M."""
    return modulos_dados(v) // 8 - ECC_POR_BLOCO[v] * BLOCOS[v]


# ── Reed-Solomon em GF(256) ──
def gf_mul(x: int, y: int) -> int:
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def rs_divisor(grau: int) -> list[int]:
    r = [0] * (grau - 1) + [1]
    raiz = 1
    for _ in range(grau):
        for j in range(grau):
            r[j] = gf_mul(r[j], raiz)
            if j + 1 < grau:
                r[j] ^= r[j + 1]
        raiz = gf_mul(raiz, 0x02)
    return r


def rs_resto(dados: list[int], divisor: list[int]) -> list[int]:
    r = [0] * len(divisor)
    for b in dados:
        f = b ^ r.pop(0)
        r.append(0)
        for i, c in enumerate(divisor):
            r[i] ^= gf_mul(c, f)
    return r


# ── Bits de formato e de versão (BCH) ──
def bits_formato(mascara: int, nivel: int = BITS_NIVEL_M) -> int:
    d = (nivel << 3) | mascara
    r = d
    for _ in range(10):
        r = (r << 1) ^ ((r >> 9) * 0x537)
    return ((d << 10) | r) ^ 0x5412


def bits_versao(v: int) -> int:
    r = v
    for _ in range(12):
        r = (r << 1) ^ ((r >> 11) * 0x1F25)
    return (v << 12) | r


# ── Montagem ──
def codificar_dados(texto: str) -> tuple[int, list[int]]:
    """(versão, palavras de dados+correção já intercaladas)."""
    dados = texto.encode("utf-8")
    for v in range(1, VERSAO_MAX + 1):
        cont = 8 if v <= 9 else 16
        if 4 + cont + 8 * len(dados) <= capacidade(v) * 8:
            break
    else:
        raise ValueError(f"texto longo demais para um QR versão {VERSAO_MAX} nível M ({len(dados)} bytes)")
    cap_bits = capacidade(v) * 8
    bits: list[int] = []

    def por(valor: int, n: int):
        bits.extend((valor >> i) & 1 for i in range(n - 1, -1, -1))
    por(0b0100, 4)
    por(len(dados), cont)
    for b in dados:
        por(b, 8)
    por(0, min(4, cap_bits - len(bits)))
    por(0, (-len(bits)) % 8)
    pal = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    enche = 0xEC
    while len(pal) < capacidade(v):
        pal.append(enche)
        enche ^= 0xEC ^ 0x11
    # blocos
    nb, ecc = BLOCOS[v], ECC_POR_BLOCO[v]
    total = modulos_dados(v) // 8
    curtos = nb - total % nb
    tam_curto = total // nb
    div = rs_divisor(ecc)
    blocos_d, blocos_e, k = [], [], 0
    for i in range(nb):
        n = tam_curto - ecc + (0 if i < curtos else 1)
        d = pal[k:k + n]
        k += n
        blocos_d.append(d)
        blocos_e.append(rs_resto(d, div))
    saida = []
    for i in range(max(len(b) for b in blocos_d)):
        saida += [b[i] for b in blocos_d if i < len(b)]
    for i in range(ecc):
        saida += [b[i] for b in blocos_e]
    return v, saida


class Matriz:
    def __init__(self, v: int):
        self.v, self.n = v, 4 * v + 17
        self.m = [[False] * self.n for _ in range(self.n)]
        self.fixo = [[False] * self.n for _ in range(self.n)]

    def pos(self, x: int, y: int, escuro: bool):
        self.m[y][x] = escuro
        self.fixo[y][x] = True

    def padroes(self):
        n = self.n
        for i in range(n):
            self.pos(6, i, i % 2 == 0)
            self.pos(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < n and 0 <= y < n:
                        dist = max(abs(dx), abs(dy))
                        self.pos(x, y, dist not in (2, 4))
        al = ALINHAMENTO[self.v]
        for i, a in enumerate(al):
            for j, b in enumerate(al):
                if (i == 0 and j == 0) or (i == 0 and j == len(al) - 1) or (i == len(al) - 1 and j == 0):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.pos(a + dx, b + dy, max(abs(dx), abs(dy)) != 1)
        self.formato(0)
        if self.v >= 7:
            b = bits_versao(self.v)
            for i in range(18):
                bit = (b >> i) & 1 == 1
                a, c = n - 11 + i % 3, i // 3
                self.pos(a, c, bit)
                self.pos(c, a, bit)

    def formato(self, mascara: int):
        b = bits_formato(mascara)
        bit = lambda i: (b >> i) & 1 == 1  # noqa: E731
        n = self.n
        for i in range(6):
            self.pos(8, i, bit(i))
        self.pos(8, 7, bit(6))
        self.pos(8, 8, bit(7))
        self.pos(7, 8, bit(8))
        for i in range(9, 15):
            self.pos(14 - i, 8, bit(i))
        for i in range(8):
            self.pos(n - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self.pos(8, n - 15 + i, bit(i))
        self.pos(8, n - 8, True)

    def dados(self, pal: list[int]):
        n, i, total = self.n, 0, len(pal) * 8
        dir_ = n - 1
        while dir_ >= 1:
            if dir_ == 6:
                dir_ = 5
            for vert in range(n):
                for j in range(2):
                    x = dir_ - j
                    subindo = ((dir_ + 1) & 2) == 0
                    y = n - 1 - vert if subindo else vert
                    if not self.fixo[y][x] and i < total:
                        self.m[y][x] = (pal[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1
            dir_ -= 2

    def mascarar(self, k: int):
        f = (lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0,
             lambda x, y: (x + y) % 3 == 0, lambda x, y: (x // 3 + y // 2) % 2 == 0,
             lambda x, y: x * y % 2 + x * y % 3 == 0, lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
             lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0)[k]
        for y in range(self.n):
            for x in range(self.n):
                if not self.fixo[y][x] and f(x, y):
                    self.m[y][x] = not self.m[y][x]

    def penalidade(self) -> int:
        n, m, p = self.n, self.m, 0
        linhas = [m[y] for y in range(n)] + [[m[y][x] for y in range(n)] for x in range(n)]
        padrao_a = [True, False, True, True, True, False, True, False, False, False, False]
        padrao_b = padrao_a[::-1]
        for ln in linhas:
            corrida = 1
            for i in range(1, n + 1):
                if i < n and ln[i] == ln[i - 1]:
                    corrida += 1
                else:
                    if corrida >= 5:
                        p += 3 + corrida - 5
                    corrida = 1
            for i in range(n - 10):
                seg = ln[i:i + 11]
                if seg == padrao_a or seg == padrao_b:
                    p += 40
        for y in range(n - 1):
            for x in range(n - 1):
                if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                    p += 3
        escuros = sum(sum(1 for c in ln if c) for ln in m)
        total = n * n
        k = (abs(escuros * 20 - total * 10) + total - 1) // total - 1
        return p + max(0, k) * 10


def gerar(texto: str) -> list[list[bool]]:
    """Matriz do QR (True = escuro), sem a margem."""
    v, pal = codificar_dados(texto)
    melhor, melhor_p = None, None
    for k in range(8):
        q = Matriz(v)
        q.padroes()
        q.dados(pal)
        q.mascarar(k)
        q.formato(k)
        p = q.penalidade()
        if melhor_p is None or p < melhor_p:
            melhor, melhor_p = q, p
    return melhor.m


def svg(texto: str, rotulo: str = "", margem: int = 4, escuro: str = "#1C2B21", claro: str = "#FFFFFF") -> str:
    """SVG acessível (role="img" + <title>), cores da paleta Physis."""
    m = gerar(texto)
    n = len(m) + 2 * margem
    caminho = "".join(f"M{x + margem} {y + margem}h1v1h-1z" for y, ln in enumerate(m) for x, c in enumerate(ln) if c)
    titulo = (rotulo or texto).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" role="img" aria-label="{titulo}" '
            f'shape-rendering="crispEdges" width="176" height="176"><title>{titulo}</title>'
            f'<rect width="{n}" height="{n}" fill="{claro}"/><path d="{caminho}" fill="{escuro}"/></svg>')


if __name__ == "__main__":
    import sys
    print(svg(sys.argv[1] if len(sys.argv) > 1 else "Physis"))
