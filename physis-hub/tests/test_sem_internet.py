"""Os programas da Physis rodam sem internet.

Protege:
1. Nenhum programa carrega script, estilo ou fonte de fora (CDN, Google Fonts...).
   Links para o usuário clicar (<a href>) podem existir; o que não pode é o programa depender deles para funcionar.
2. As bibliotecas guardadas em vendor/ são as mesmas que foram conferidas na origem (resumo SHA-256).
3. O Planejador está com a cópia atual de vendor/ embutida (rodar ferramentas/embutir_bibliotecas.py não muda nada).

Só roda dentro do repositório (no pacote do cliente, vendor/ e ferramentas/ não vão).
"""
import hashlib
import importlib.util
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
NO_REPO = (RAIZ / "vendor").is_dir() and (RAIZ / "ferramentas" / "embutir_bibliotecas.py").is_file()

PROGRAMAS = ["sistema/*.html", "modulos/planejador/*.html", "physis-hub/web/*.html"]
EXTERNO = [
    re.compile(r'<script\b[^>]*\bsrc\s*=\s*["\']?(?:https?:)?//', re.I),
    re.compile(r'<link\b[^>]*\bhref\s*=\s*["\']?(?:https?:)?//[^>]*>', re.I),
    re.compile(r'@import\s+(?:url\()?["\']?(?:https?:)?//', re.I),
    re.compile(r'url\(\s*["\']?(?:https?:)?//', re.I),
]

# SHA-256 dos arquivos baixados em 14/11/2026 (o SHA-512 conferiu com o publicado pelo cdnjs)
VENDOR = {
    "jszip.min.js": "acc7e41455a80765b5fd9c7ee1b8078a6d160bbbca455aeae854de65c947d59e",
    "pdf.min.js": "5b5799e6f8c680663207ac5b42ee14eed2a406fa7af48f50c154f0c0b1566946",
    "pdf.worker.min.js": "feabdf309770ed24bba31a5467836cdc8cf639c705af27d52b585b041bb8527b",
}


@unittest.skipUnless(NO_REPO, "só no repositório")
class SemInternet(unittest.TestCase):
    def test_nenhum_programa_busca_coisas_fora(self):
        achados = []
        for padrao in PROGRAMAS:
            for arq in sorted(RAIZ.glob(padrao)):
                texto = arq.read_text(encoding="utf-8", errors="replace")
                for r in EXTERNO:
                    for m in r.finditer(texto):
                        trecho = texto[m.start():m.start() + 120]
                        if re.match(r"<link\b", trecho, re.I) and not re.search(r'rel\s*=\s*["\']?(stylesheet|preload|preconnect|modulepreload)', m.group(0), re.I):
                            continue        # <link rel="canonical"> etc. não carregam nada
                        achados.append(f"{arq.relative_to(RAIZ)}: {trecho[:90]}")
        self.assertEqual(achados, [], "programa dependendo da internet")

    def test_vendor_confere(self):
        for nome, esperado in VENDOR.items():
            atual = hashlib.sha256((RAIZ / "vendor" / nome).read_bytes()).hexdigest()
            self.assertEqual(atual, esperado, f"vendor/{nome} mudou: confira a origem e atualize vendor/LEIA-ME.md")

    def test_planejador_com_bibliotecas_atuais(self):
        spec = importlib.util.spec_from_file_location("embutir", RAIZ / "ferramentas" / "embutir_bibliotecas.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for alvo in mod.ALVOS:
            html = alvo.read_text(encoding="utf-8")
            self.assertEqual(mod.embutir(html), html, f"{alvo.name}: rode ferramentas/embutir_bibliotecas.py")


if __name__ == "__main__":
    unittest.main()
