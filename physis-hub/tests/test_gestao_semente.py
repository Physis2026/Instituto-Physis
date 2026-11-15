"""Gestão: a semente da Fase 2 é MESCLADA ao estado guardado (15/11/2026: "Nada aqui ainda" em "Esta semana" com estado
antigo no navegador), e "Meus contratos" sem servidor explica em vez de não fazer nada.

O comportamento foi conferido no navegador (estado antigo → tarefas novas entram, a editada fica, a apagada não volta;
com o servidor, o estado mesclado sobe para /api/gestao/estado). Aqui: o código da junção e as ligações dela.
"""
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
G = RAIZ / "sistema" / "gestao-interna-physis.html"


@unittest.skipUnless(G.is_file(), "só no repositório")
class Semente(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = G.read_text(encoding="utf-8")
        cls.s = re.search(r'<script id="gp-semente">(.*?)</script>', cls.g, re.S).group(1)

    def test_juncao_por_id_com_resumo_e_apagadas(self):
        for trecho in ("g.gpMesclarSemente = function (estado, equipe, tarefas)", "apagadas.push(id)",          # apagada vira lápide
                       "apagadas.indexOf(s.id) >= 0) return;",                                                  # e não volta
                       'antes[x.id] === resumo(x, campos)',                                                     # só muda o que não foi editado
                       "if (!s) { out.push(x); return; }",                                                      # criada pela pessoa: intacta
                       '"pessoa", "h", "depende", "projeto", "projetoEn", "texto", "textoEn"',                  # campos da tarefa
                       '"nome", "lang", "papel", "papelEn", "admin", "sol"',                                    # e da pessoa
                       "tarefas novas da Fase 2 foram adicionadas"):
            self.assertIn(trecho, self.s, trecho)

    def test_ligado_ao_aplicativo_e_ao_servidor(self):
        self.assertIn("window.gpMesclarSemente(M,Fy,$y)", self.g)
        self.assertIn("feitas:x,semente:window.__gpSemente", self.g)            # o resumo é gravado com o estado
        self.assertIn('PP&&PP.ativa&&PP.agendar&&PP.agendar("gestao-physis:"+C0)', self.g)   # e sobe para o servidor
        self.assertLess(self.g.index('id="gp-semente"'), self.g.index("$y=[{"))

    def test_meus_contratos_sem_servidor(self):
        self.assertIn("Disponível quando entrar pelo servidor (conta de cliente)", self.g)
        self.assertIn("if (x && srv) { x.click(); return; } semMeus();", self.g)

    def test_horizontes_novos(self):
        self.assertNotIn('nome:"Setembro"', self.g)
        self.assertNotIn('nome:"At\\xE9 outubro"', self.g)


if __name__ == "__main__":
    unittest.main()
