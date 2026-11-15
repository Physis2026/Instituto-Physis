import datetime, shutil, sys, zipfile
from pathlib import Path
RAIZ = Path(r"C:\physis\physis-sistema")
DOCS = Path(r"C:\Users\rafae\OneDrive - Physis Engineering\Documents\Sistema Physis")
FORA = {".git", "__pycache__", "node_modules", "www", "_backup_git", "_backup_arquivos", "sistema_physis_fase1", "sistema_physis_ep_final"}
EXT_FORA = {".db", ".db-wal", ".db-shm", ".env", ".pfx", ".jks", ".keystore", ".pyc"}
destino = DOCS / "_backup_arquivos"
destino.mkdir(exist_ok=True)
carimbo = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
def juntar(z, base, prefixo):
    n = 0
    for p in base.rglob("*"):
        rel = p.relative_to(base)
        if any(parte in FORA for parte in rel.parts) or not p.is_file() or p.suffix.lower() in EXT_FORA or p.name.endswith(".env"):
            continue
        z.write(p, f"{prefixo}/{rel.as_posix()}"); n += 1
    return n
arq = destino / f"sistema-physis-arquivos-{carimbo}.zip"
with zipfile.ZipFile(arq, "w", zipfile.ZIP_DEFLATED) as z:
    a = juntar(z, RAIZ, "codigo")
    b = juntar(z, DOCS, "documentos")
print(arq, a, "arquivos de código,", b, "documentos,", round(arq.stat().st_size / 2**20, 1), "MB")
