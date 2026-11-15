"""Marketplace de serviços (parceiros.py e sistema/physis-parceiros.js).

Protege:
1. CPF e CNPJ conferidos pelos dígitos verificadores; documento mascarado para a equipe; completo só a pedido.
2. Sem consentimento não há cadastro; tudo nasce "em análise"; CPF/CNPJ repetido é recusado.
3. Só a direção muda a curadoria; aprovar exige registro conferido e os documentos da especialidade em dia;
   suspender exige motivo.
4. Vitrine: só aprovados com documento em dia, por especialidade e região (município antes do estado), ordem por
   nota com média puxada para 3; sem CPF/CNPJ, contato, número do registro nem comentários.
5. Pedido de orçamento com consentimento vira pedido na Central (origem "parceiros"); só para quem atende.
6. Avaliação só depois do serviço concluído, por quem pediu (ou pela equipe), uma por pedido.
7. Eliminação (LGPD) apaga parceiro, documentos e avaliações; a cadeia de registro continua íntegra.
8. O módulo da tela não chama a internet nem mostra dado pessoal na loja.
"""
import json
import re
import unittest
from datetime import datetime
from pathlib import Path

from physis_hub import parceiros as pa
from physis_hub.clima import FUSO
from physis_hub.hub import Hub

AGORA = datetime(2026, 11, 15, 10, 0, tzinfo=FUSO).timestamp()
CPF, CNPJ = "529.982.247-25", "11.222.333/0001-81"
JS = (Path(__file__).resolve().parents[2] / "sistema" / "physis-parceiros.js").read_text(encoding="utf-8")


def base(**k):
    d = {"tipo": "pj", "documento": CNPJ, "nome": "Sol & Cia Instalações Ltda", "nome_publico": "Sol & Cia", "conselho": "CREA",
         "registro": "2012345678", "registro_uf": "RJ", "especialidades": ["solar"], "regioes": [{"uf": "RJ", "municipio": "Petrópolis"}],
         "email": "contato@solecia.example", "telefone": "(24) 99999-0000", "consentimento": True}
    d.update(k)
    return d


class Documentos(unittest.TestCase):
    def test_cpf_cnpj(self):
        self.assertTrue(pa.cpf_valido(CPF))
        self.assertFalse(pa.cpf_valido("529.982.247-24"))
        self.assertFalse(pa.cpf_valido("111.111.111-11"))
        self.assertTrue(pa.cnpj_valido(CNPJ))
        self.assertFalse(pa.cnpj_valido("11.222.333/0001-82"))
        self.assertFalse(pa.cnpj_valido("00000000000000"))
        self.assertEqual(pa.mascarar(CPF), "***.982.247-**")
        self.assertEqual(pa.mascarar(CNPJ), "11.***.***/0001-**")

    def test_requisitos_e_regiao(self):
        self.assertEqual(pa.requisitos(["solar"]), ["art_modelo", "seguro", "nr10", "nr35"])
        self.assertEqual(pa.requisitos(["hidraulica"]), ["art_modelo", "seguro"])
        p = {"regioes": [{"uf": "RJ", "municipio": "Petrópolis", "ibge": ""}, {"uf": "SP", "municipio": "", "ibge": ""}]}
        self.assertEqual(pa.atende(p, "rj", "petropolis"), 2)
        self.assertEqual(pa.atende(p, "RJ", "Teresópolis"), 0)
        self.assertEqual(pa.atende(p, "SP", "Campinas"), 1)
        self.assertLess(pa.nota_bayes(5, 1), pa.nota_bayes(96, 20))


class NoHub(unittest.TestCase):
    def setUp(self):
        self.rel = [AGORA]
        self.h = Hub(":memory:", relogio=lambda: self.rel[0])
        self.p = pa.Parceiros(self.h)

    def pronto(self, **k):
        r = self.p.cadastrar(base(**k), "site")
        self.assertTrue(r["ok"], r)
        i = r["id"]
        for t, v in (("art_modelo", ""), ("seguro", "2027-06-30"), ("nr10", "2027-01-01"), ("nr35", "2027-01-01")):
            self.assertTrue(self.p.documento(i, {"tipo": t, "validade": v}, "eq")["ok"])
        self.assertTrue(self.p.conferir_registro(i, "eq")["ok"])
        self.assertTrue(self.p.curar(i, "aprovado", "", "dir", True)["ok"])
        return i

    def test_cadastro_consentimento_e_validacao(self):
        self.assertFalse(self.p.cadastrar(base(consentimento=False))["ok"])
        self.assertFalse(self.p.cadastrar(base(documento="11.222.333/0001-82"))["ok"])
        self.assertFalse(self.p.cadastrar(base(especialidades=["pintura"]))["ok"])
        self.assertFalse(self.p.cadastrar(base(regioes=[{"uf": "XX"}]))["ok"])
        self.assertFalse(self.p.cadastrar(base(conselho="CREA", registro="", registro_uf="RJ"))["ok"])
        self.assertFalse(self.p.cadastrar(base(email="", telefone=""))["ok"])
        r = self.p.cadastrar(base())
        self.assertEqual((r["ok"], r["status"]), (True, "em_analise"))
        self.assertFalse(self.p.cadastrar(base(nome="Outro"))["ok"])          # mesmo CNPJ
        self.assertEqual(self.p.vitrine()["parceiros"], [])                  # em análise não aparece

    def test_curadoria_so_direcao_e_pendencias(self):
        i = self.p.cadastrar(base())["id"]
        self.assertEqual(self.p.curar(i, "aprovado", "", "eq", False)["codigo"], 403)
        r = self.p.curar(i, "aprovado", "", "dir", True)
        self.assertFalse(r["ok"])
        self.assertIn("registro profissional conferido pela equipe", r["pendencias"])
        self.assertIn("Certificado NR-35 ausente", r["pendencias"])
        self.assertFalse(self.p.documento(i, {"tipo": "nr10"}, "eq")["ok"])          # NR sem validade
        self.assertFalse(self.p.curar(i, "suspenso", "", "dir", True)["ok"])          # sem motivo
        self.assertTrue(self.p.curar(i, "suspenso", "documentação incompleta", "dir", True)["ok"])

    def test_vitrine_sem_dado_pessoal_e_ordem(self):
        a = self.pronto()
        b = self.pronto(documento=CPF, tipo="pf", nome="João Silva", nome_publico="João Eletricista",
                        especialidades=["solar", "eletrica"], regioes=[{"uf": "RJ"}])
        v = self.p.vitrine("solar", "RJ", "Petrópolis")["parceiros"]
        self.assertEqual([x["id"] for x in v], [a, b])               # quem cita o município vem antes do estado todo
        self.assertEqual(self.p.vitrine("solar", "RJ", "Niterói")["parceiros"][0]["id"], b)
        self.assertEqual(self.p.vitrine("hidraulica", "RJ")["parceiros"], [])
        texto = json.dumps(self.p.vitrine(), ensure_ascii=False)
        for proibido in ("52998224725", "529.982", "11222333", "contato@", "99999", "2012345678", "João Silva"):
            self.assertNotIn(proibido, texto)
        self.assertEqual(v[0]["registro"], "CREA-RJ")
        # documento vence: sai da vitrine
        self.rel[0] = datetime(2027, 2, 1, tzinfo=FUSO).timestamp()
        self.assertEqual(self.p.vitrine("solar", "RJ")["parceiros"], [])
        self.assertIn("Certificado NR-10 vencido", self.p.interno()["parceiros"][0]["pendencias"])

    def test_interno_mascara(self):
        self.pronto()
        self.assertEqual(self.p.interno()["parceiros"][0]["documento"], "11.***.***/0001-**")
        self.assertEqual(self.p.interno(completo=True)["parceiros"][0]["documento"], "11222333000181")

    def test_orcamento_e_avaliacao(self):
        i = self.pronto()
        pedido = {"parceiro": i, "servico": "solar", "uf": "RJ", "municipio": "Petrópolis", "nome": "Maria",
                  "email": "maria@exemplo.example", "descricao": "Sistema de 5 kWp no telhado", "consentimento": True}
        self.assertFalse(self.p.pedir_orcamento(dict(pedido, consentimento=False))["ok"])
        self.assertFalse(self.p.pedir_orcamento(dict(pedido, municipio="Manaus", uf="AM"))["ok"])
        self.assertFalse(self.p.pedir_orcamento(dict(pedido, servico="avac"))["ok"])
        self.assertFalse(self.p.pedir_orcamento(dict(pedido, email="", telefone=""))["ok"])
        r = self.p.pedir_orcamento(pedido, usuario="maria")
        self.assertTrue(r["ok"])
        self.assertRegex(r["numero"], r"^PQ-261115-[0-9A-F]{6}$")
        c = [x for x in self.h.central_listar() if x["numero"] == r["numero"]][0]
        self.assertEqual((c["tipo"], c["estado"], c["dados"]["origem"], c["dados"]["parceiro"]), ("pedido", "novo", "parceiros", i))
        av = {"pedido": r["numero"], "nota": 5, "comentario": "Ótimo"}
        self.assertIn("concluído", self.p.avaliar(i, av, "maria")["erro"])
        self.h.central_marcar("pedido", r["numero"], "concluido", "eq")
        self.assertEqual(self.p.avaliar(i, av, "outra")["codigo"], 403)
        self.assertFalse(self.p.avaliar(i, dict(av, nota=6), "maria")["ok"])
        self.assertTrue(self.p.avaliar(i, av, "maria")["ok"])
        self.assertFalse(self.p.avaliar(i, av, "maria")["ok"])          # uma por pedido
        v = self.p.vitrine("solar")["parceiros"][0]
        self.assertEqual((v["nota"], v["avaliacoes"]), (5.0, 1))
        self.assertNotIn("Ótimo", json.dumps(self.p.vitrine(), ensure_ascii=False))
        self.assertEqual(self.p.interno()["parceiros"][0]["comentarios"][0]["comentario"], "Ótimo")

    def test_editar_e_apagar(self):
        i = self.pronto()
        self.assertTrue(self.p.editar(i, {"registro": "999", "conselho": "CREA", "registro_uf": "SP"}, "eq")["ok"])
        self.assertIsNone(self.p.interno()["parceiros"][0]["registro_conferido"])          # mudou: conferir de novo
        self.assertFalse(self.p.editar(i, {"especialidades": []}, "eq")["ok"])
        self.assertTrue(self.p.apagar(i, "dir")["ok"])
        self.assertEqual(self.p.interno()["parceiros"], [])
        n = self.h._db.execute("SELECT (SELECT COUNT(*) FROM parceiro_documento) + (SELECT COUNT(*) FROM parceiro_avaliacao)").fetchone()[0]
        self.assertEqual(n, 0)
        self.assertTrue(self.h.verificar_cadeia()[0])
        registro = " ".join(r[0] for r in self.h._db.execute("SELECT conteudo FROM registro"))
        self.assertNotIn("11222333", registro)          # a cadeia guarda só metadados


class ModuloJS(unittest.TestCase):
    def test_contrato(self):
        for nome in ("montarLoja", "montarCuradoria", "/api/parceiros", "/api/parceiros/orcamento", "/api/parceiros/interno",
                     "X-Physis-CSRF", "cpfValido", "cnpjValido"):
            self.assertIn(nome, JS)
        self.assertIsNone(re.search(r"https?://", JS))
        self.assertNotIn("<h1", JS)
        self.assertNotRegex(JS.lower(), r"</script")

    def test_mesmas_listas(self):
        for k, v in pa.ESPECIALIDADES.items():
            self.assertIn(f'{k}:"{v}"', JS)
        for k, v in pa.TIPOS_DOC.items():
            self.assertIn(f'{k}:"{v}"', JS)


if __name__ == "__main__":
    unittest.main()
