"""A antiga "Tela do cliente" (Painel do cliente, sistema/physis-tela-cliente.html) saiu em 15/11/2026:
nenhuma página entregue pode ter link ou item de menu para ela (pedido da Physis: "a página do cliente ainda aparece")."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PASTAS = [RAIZ / "sistema", RAIZ / "physis-hub" / "web", RAIZ / "demos", RAIZ / "modulos", RAIZ / "app-nativo" / "site"]
LEGADO = "physis-tela-cliente.html"


class SemTelaDoCliente(unittest.TestCase):
    def test_nenhum_link_para_a_tela_antiga(self):
        achados = []
        for pasta in PASTAS:
            if not pasta.is_dir():
                continue
            for arq in pasta.rglob("*.html"):
                if arq.name == LEGADO:
                    continue
                t = arq.read_text(encoding="utf-8", errors="replace")
                if re.search(r'(href|src)\s*=\s*["\'][^"\']*' + re.escape(LEGADO), t):
                    achados.append(str(arq.relative_to(RAIZ)))
        self.assertEqual(achados, [], "link para a Tela do cliente antiga")


if __name__ == "__main__":
    unittest.main()
