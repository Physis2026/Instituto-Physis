"""Servidor HTTP local do fatiador (só biblioteca padrão; o fatiamento é do PrusaSlicer, um programa separado).

    GET  /saude     {"ok": true, "fatiador": "prusa-slicer", "versao": "..."} ou {"ok": false} sem o programa
    POST /fatiar    {"stl_b64": "...", "config": {altura_camada, largura_linha, paredes, preenchimento, ...}}
                    -> {"ok": true, "gcode": "...", "estimativa": {"tempo_s", "filamento_mm", "filamento_g"}, "ini": "..."}

Licença: o PrusaSlicer é AGPL-3.0. Ele roda como processo separado, neste contêiner, chamado pela linha de comando;
nada dele é importado no hub. O G-code que ele gera é saída do programa (não leva a licença dele).
Variáveis: PHYSIS_FATIADOR_PORTA (8730), PHYSIS_FATIADOR_ENDERECO (0.0.0.0 no contêiner, rede interna),
PHYSIS_FATIADOR_CHAVE (exige "Authorization: Bearer <chave>"), PHYSIS_FATIADOR_BIN (prusa-slicer),
PHYSIS_FATIADOR_TEMPO (s, padrão 240), PHYSIS_FATIADOR_MESA ("220x220", tamanho da mesa em mm).
Roda no Linux do servidor (contêiner); pastas temporárias pelo tempfile, caminhos pelo pathlib.
"""
from __future__ import annotations

import base64
import binascii
import hmac
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__

log = logging.getLogger("physis_fatiador")
MAX_CORPO = 64 * 1024 * 1024
MAX_GCODE = 60 * 1024 * 1024

# chaves do PrusaSlicer (formato .ini da versão 2.x) [CONFERIR com a versão instalada na imagem: prusa-slicer --help-fff]
def montar_ini(cfg: dict, mesa: str = "220x220") -> str:
    def num(k, padrao):
        try:
            v = float(cfg.get(k, padrao))
        except (TypeError, ValueError):
            v = padrao
        return v
    lx, _, ly = (mesa or "220x220").partition("x")
    lx, ly = float(lx or 220), float(ly or 220)
    h = num("altura_camada", 0.2)
    if not 0.04 <= h <= 1.0:
        raise ValueError("altura de camada fora de 0,04 a 1 mm")
    linhas = {
        "layer_height": h, "first_layer_height": h,
        "perimeters": int(num("paredes", 2)), "top_solid_layers": int(num("camadas_topo", 4)), "bottom_solid_layers": int(num("camadas_fundo", 4)),
        "fill_density": f"{round(100 * min(1.0, max(0.0, num('preenchimento', 0.2))))}%",
        "extrusion_width": num("largura_linha", 0.45), "nozzle_diameter": num("bico_mm", 0.4),
        "filament_diameter": num("diametro_filamento", 1.75),
        "perimeter_speed": num("vel_parede", 40), "infill_speed": num("vel_preench", 60),
        "bed_shape": f"0x0,{lx:g}x0,{lx:g}x{ly:g},0x{ly:g}", "gcode_flavor": "marlin2",
    }
    if cfg.get("densidade_g_cm3"):
        linhas["filament_density"] = num("densidade_g_cm3", 1.24)
    for k_ini, k in (("temperature", "bico_c"), ("first_layer_temperature", "bico_c"), ("bed_temperature", "mesa_c"),
                     ("first_layer_bed_temperature", "mesa_c")):
        if cfg.get(k) not in (None, ""):
            linhas[k_ini] = int(num(k, 0))
    return "".join(f"{k} = {v}\n" for k, v in linhas.items())


def _tempo_s(txt: str) -> float | None:
    s = 0.0
    achou = False
    for n, u in re.findall(r"(\d+)\s*([dhms])", txt):
        s += int(n) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[u]
        achou = True
    return s if achou else None


def ler_estimativa(gcode: str) -> dict:
    """Comentários que o PrusaSlicer escreve no fim do G-code [CONFERIR o texto exato na versão instalada]."""
    fim = gcode[-20000:]
    out = {"tempo_s": None, "filamento_mm": None, "filamento_g": None}
    m = re.search(r";\s*estimated printing time \(normal mode\)\s*=\s*(.+)", fim)
    if m:
        out["tempo_s"] = _tempo_s(m.group(1))
    m = re.search(r";\s*filament used \[mm\]\s*=\s*([\d.]+)", fim)
    if m:
        out["filamento_mm"] = float(m.group(1))
    m = re.search(r";\s*filament used \[g\]\s*=\s*([\d.]+)", fim)
    if m:
        out["filamento_g"] = float(m.group(1))
    return out


def programa() -> str | None:
    return shutil.which(os.environ.get("PHYSIS_FATIADOR_BIN") or "prusa-slicer")


def _executar(cmd: list[str], tempo: float) -> tuple[int, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=tempo)
    return r.returncode, (r.stderr or r.stdout or "")[-2000:]


def fatiar(corpo: dict, executar=_executar) -> tuple[int, dict]:
    """Fatia o STL do corpo. `executar` pode ser trocado nos testes (fatiador falso)."""
    try:
        stl = base64.b64decode(str(corpo.get("stl_b64") or ""), validate=True)
    except (binascii.Error, ValueError):
        return 400, {"ok": False, "erro": "stl_b64 inválido"}
    if len(stl) < 84:
        return 400, {"ok": False, "erro": "STL vazio"}
    try:
        ini = montar_ini(corpo.get("config") or {}, os.environ.get("PHYSIS_FATIADOR_MESA", "220x220"))
    except ValueError as e:
        return 400, {"ok": False, "erro": str(e)}
    binario = programa() if executar is _executar else (os.environ.get("PHYSIS_FATIADOR_BIN") or "prusa-slicer")
    if not binario:
        return 503, {"ok": False, "erro": "PrusaSlicer não instalado nesta imagem"}
    with tempfile.TemporaryDirectory(prefix="fatiar-") as tmp:
        d = Path(tmp)
        (d / "peca.stl").write_bytes(stl)
        (d / "config.ini").write_text(ini, encoding="utf-8")
        saida = d / "peca.gcode"
        cmd = [binario, "--export-gcode", "--load", str(d / "config.ini"), "--output", str(saida), str(d / "peca.stl")]
        try:
            codigo, msg = executar(cmd, float(os.environ.get("PHYSIS_FATIADOR_TEMPO") or 240))
        except subprocess.TimeoutExpired:
            return 504, {"ok": False, "erro": "fatiamento passou do tempo"}
        if codigo != 0 or not saida.is_file():
            return 422, {"ok": False, "erro": "o fatiador recusou a peça", "detalhe": msg}
        if saida.stat().st_size > MAX_GCODE:
            return 413, {"ok": False, "erro": "G-code grande demais"}
        gcode = saida.read_text(encoding="utf-8", errors="replace")
    return 200, {"ok": True, "gcode": gcode, "estimativa": ler_estimativa(gcode), "ini": ini, "fatiador": "PrusaSlicer (AGPL-3.0)"}


def criar_manipulador(chave: str | None, vagas: threading.Semaphore):
    class Manipulador(BaseHTTPRequestHandler):
        server_version = "PhysisFatiador"
        sys_version = ""

        def log_message(self, fmt, *args):
            log.info("%s %s", self.address_string(), fmt % args)

        def _json(self, codigo: int, dados: dict):
            b = json.dumps(dados, ensure_ascii=False).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if self.path.split("?")[0] == "/saude":
                p = programa()
                return self._json(200, {"ok": bool(p), "versao": __version__, "fatiador": "prusa-slicer" if p else None})
            self._json(404, {"ok": False, "erro": "rota desconhecida"})

        def do_POST(self):
            if chave:
                dado = self.headers.get("Authorization", "")
                if not (dado.startswith("Bearer ") and hmac.compare_digest(dado[7:].encode(), chave.encode())):
                    self.close_connection = True
                    return self._json(401, {"ok": False, "erro": "chave inválida"})
            if self.path.split("?")[0] != "/fatiar":
                self.close_connection = True
                return self._json(404, {"ok": False, "erro": "rota desconhecida"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = -1
            if n <= 0 or n > MAX_CORPO:
                self.close_connection = True
                return self._json(413 if n > MAX_CORPO else 400, {"ok": False, "erro": "corpo ausente ou grande demais"})
            try:
                corpo = json.loads(self.rfile.read(n))
                if not isinstance(corpo, dict):
                    raise ValueError
            except ValueError:
                return self._json(400, {"ok": False, "erro": "JSON inválido"})
            if not vagas.acquire(timeout=1):
                return self._json(429, {"ok": False, "erro": "fatiador ocupado; tente de novo"})
            try:
                self._json(*fatiar(corpo))
            finally:
                vagas.release()
    return Manipulador


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    porta = int(os.environ.get("PHYSIS_FATIADOR_PORTA") or 8730)
    endereco = os.environ.get("PHYSIS_FATIADOR_ENDERECO") or "127.0.0.1"
    vagas = threading.Semaphore(int(os.environ.get("PHYSIS_FATIADOR_SIMULTANEOS") or 1))
    srv = ThreadingHTTPServer((endereco, porta), criar_manipulador(os.environ.get("PHYSIS_FATIADOR_CHAVE") or None, vagas))
    log.info("fatiador em %s:%s", endereco, porta)
    srv.serve_forever()


if __name__ == "__main__":
    main()
