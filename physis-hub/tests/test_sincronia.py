"""As cópias embutidas do exportador de documentos têm de ser iguais ao original.

Se alguém mudar uma cópia à mão, este teste reprova: mude o original
(sistema/physis-exportar.js) e rode `python ferramentas/sincronizar.py`.
"""
import subprocess
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


class Sincronia(unittest.TestCase):
    def test_copias_iguais_ao_original(self):
        r = subprocess.run([sys.executable, str(RAIZ / "ferramentas" / "sincronizar.py"), "--conferir"],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_titulo_antigo_do_scada_nao_volta(self):
        for arq in (RAIZ / "sistema" / "physis-scada-demo.html", RAIZ / "physis-hub" / "web" / "painel.html"):
            self.assertNotIn("fazenda net zero", arq.read_text(encoding="utf-8"), arq.name)


if __name__ == "__main__":
    unittest.main()
