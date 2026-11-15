"""Mapeamento sem servidor (15/11/2026: "garantir que aba mapeamento funcione sem servidor").

Confere: o escritor e o leitor de IFC do navegador (sistema/physis-ifc.js) têm as mesmas entidades e conjuntos de
propriedades do ifc.py; a entrada do modelo de exemplo está no disco e o ifc.py gera dela o modelo.ifc de exemplo (a
página conferir-modelos.html compara o texto do navegador com ele); o Mapeamento monta contexto, lê arquivos, calcula
o sol com a estimativa da Solar e gera/lê IFC sem /api/mapeamento, sempre com "calculado no navegador (sem servidor)".
"""
import json
import re
import unittest
from pathlib import Path

from physis_hub import ifc

RAIZ = Path(__file__).resolve().parents[2]
JS = RAIZ / "sistema" / "physis-ifc.js"
MP = RAIZ / "sistema" / "physis-mapeamento.js"
EX = RAIZ / "modulos" / "mapeamento" / "exemplos"
NO_REPO = JS.is_file() and MP.is_file() and (EX / "modelo-entrada.json").is_file()


@unittest.skipUnless(NO_REPO, "só no repositório")
class SemServidor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")
        cls.mp = MP.read_text(encoding="utf-8")

    def test_mesmas_entidades_e_conjuntos(self):
        for tipo, (ent, pre, _ot, pset, _el) in ifc.TIPOS.items():
            self.assertRegex(self.js, rf'{tipo}: \["{ent}", "{pre}", "[^"]+", "{pset}"', tipo)
        for k in ("Physis_Eletrica", "Physis_Materiais", "FatorPotencia", "PotenciaReativa", "PotenciaAparente", "IFCRELCONTAINEDINSPATIALSTRUCTURE",
                  "IFCRELAGGREGATES", "IFCDOCUMENTREFERENCE", "FILE_SCHEMA(('IFC4'))", "NS_OID", "function sha1", "function ler("):
            self.assertIn(k, self.js)
        for un, (t, _pre, nome) in ifc.SI.items():
            self.assertIn(f'"{un}": ["{t}", ', self.js)

    def test_exemplo_reproduzivel(self):
        d = json.loads((EX / "modelo-entrada.json").read_text(encoding="utf-8"))
        agora = d.pop("agora")
        d.pop("aviso", None)
        self.assertEqual(ifc.escrever(d, agora=agora), (EX / "modelo.ifc").read_text(encoding="utf-8"))
        pag = (RAIZ / "ferramentas" / "testes-navegador" / "conferir-modelos.html").read_text(encoding="utf-8")
        self.assertIn("IFC no navegador = IFC do servidor (mesmo texto)", pag)
        self.assertIn("Leitor do navegador = leitor do servidor (resumo)", pag)
        self.assertIn('physis-ifc.js', pag)

    def test_mapeamento_funciona_sem_servidor(self):
        for s in ("function contextoNavegador(L, S)", "async function lerArquivoNavegador(nome, buf)", "function lerShp(", "function lerKml(", "async function lerZip(",
                  "window.PhysisIFC.escrever(d)", "window.PhysisIFC.ler(", '"calculado no navegador (sem servidor)"', "disponível com o servidor",
                  "physis-mapeamento-arquivos", "if (!emHub()) { const S = SOL();"):
            self.assertIn(s, self.mp, s)
        self.assertNotIn('return faixa("in", "Sem servidor.", "O catálogo', self.mp)
        emb = (RAIZ / "ferramentas" / "embutir_bases.py").read_text(encoding="utf-8")
        self.assertLess(emb.index('"mod-ifc"'), emb.index('"mod-mapeamento"'))
        self.assertIn('<script id="mod-ifc">', (RAIZ / "physis-hub" / "web" / "painel.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
