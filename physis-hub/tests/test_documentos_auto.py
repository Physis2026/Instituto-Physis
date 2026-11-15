"""Documentos automáticos (documentos_auto.py): modelos, fila de aprovação, NF, relatórios, manual e biblioteca.

Protege:
1. {{campo}} é preenchido com os dados do sistema; sem dado vira [MARCADOR: campo] (nada inventado). O modelo da
   pasta do servidor (PHYSIS_MODELOS_PASTA, ODT) vale antes do modelo do repositório.
2. Fluxo rascunho → em_revisao → aprovado → emitido: EMISSÃO SEM APROVAÇÃO É RECUSADA; mudar um aprovado volta
   para revisão; emitido não muda; só a direção aprova/devolve; cada passo no registro encadeado (íntegro).
3. NF: dados montados da compra; prestador só da configuração; emissão no provedor é Fase 2 (fica pendente).
4. Relatório de vários módulos na ordem das abas; manual só com os módulos comprados (1 módulo = curto, 8 = completo)
   e sempre com primeiro acesso, segurança/LGPD, alertas, rotina e pontos em aberto.
5. Biblioteca: o parecido vem primeiro (BM25 + tipo/setor/porte); a IA adapta sem dados pessoais e o resultado é rascunho.
6. Servidor: aprovar a compra cria o rascunho do manual; rotas exigem sessão/papel e CSRF; montar() põe o manual no pacote.
"""
import io
import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from unittest import mock

from physis_hub import documentos as odf
from physis_hub import documentos_auto as da
from physis_hub.hub import Hub

AGORA = datetime(2026, 11, 15, 10, 0).timestamp()
COMPRA = {"_formato": "physis-compra/1", "numero": "LJ-DOC-1", "recibo": "RC-1", "total": 1500.0, "forma": "Pix",
          "pagador": {"nome": "Fazenda Teste", "doc": "12345678000199", "email": "fazenda@exemplo.com", "telefone": "61999990000"},
          "itens": [{"d": "Kit qualidade da água", "qtd": 1, "unit": 1500.0, "total": 1500.0}], "modulos": ["agua"]}
EQUIPE = {"usuario": "erick", "papel": "operador"}
DIRECAO = {"usuario": "rafaella", "papel": "administrador"}
CLIENTE = {"usuario": "cli", "papel": "cliente"}


class Base(unittest.TestCase):
    def setUp(self):
        self.h = Hub(":memory:", relogio=lambda: AGORA)
        self.h.central_por("compra", COMPRA["numero"], COMPRA)
        self.tmp = tempfile.TemporaryDirectory()
        self.d = da.DocumentosAuto(self.h, pasta_biblioteca=Path(self.tmp.name) / "bib")

    def tearDown(self):
        self.tmp.cleanup()

    def registros(self, tipo):
        return [json.loads(c) for (c,) in self.h._db.execute("SELECT conteudo FROM registro WHERE tipo=? ORDER BY seq", (tipo,))]


class TestMarcacoes(Base):
    def test_preencher_sem_inventar(self):
        t, pend = da.preencher("Olá {{cliente.nome}}, total {{pedido.total}}. [MARCADOR: prazo]", {"cliente": {"nome": "Ana"}})
        self.assertEqual(t, "Olá Ana, total [MARCADOR: pedido.total]. [MARCADOR: prazo]")
        self.assertEqual(pend, ["pedido.total", "prazo"])

    def test_dados_da_compra(self):
        d = da.dados_da_compra(COMPRA, hoje="15/11/2026")
        self.assertEqual(d["pedido"]["total"], "R$ 1.500,00")
        self.assertEqual(d["cliente"]["documento"], "12345678000199")
        self.assertIn("| Kit qualidade da água | 1 | R$ 1.500,00 | R$ 1.500,00 |", d["itens_tabela"])
        self.assertEqual(da.brl(1234567.891), "R$ 1.234.567,89")

    def test_modelo_odt_do_servidor_vale_antes(self):
        pasta = Path(self.tmp.name) / "modelos"
        (pasta / "documentos").mkdir(parents=True)
        modelo = odf.odt("Proposta", [{"t": "Cliente: {{cliente.nome}} · total {{pedido.total}} · {{nada.aqui}}"}], logo_png=False)
        (pasta / "documentos" / "proposta.odt").write_bytes(modelo)
        with mock.patch.dict(os.environ, {"PHYSIS_MODELOS_PASTA": str(pasta)}):
            r = self.d.gerar({"tipo": "proposta", "fonte": {"tipo": "compra", "numero": "LJ-DOC-1"}}, "erick")
        doc = self.d.ver(r["id"])["documento"]
        self.assertTrue(doc["tem_odt_modelo"])
        self.assertEqual(doc["modelo"], "proposta.odt")
        self.assertIn("Cliente: Fazenda Teste · total R$ 1.500,00 · [MARCADOR: nada.aqui]", doc["texto"])
        self.assertIn("nada.aqui", doc["pendencias"])
        arq = self.d.arquivo(r["id"])
        self.assertIn("Fazenda Teste", zipfile.ZipFile(io.BytesIO(arq["bytes"])).read("content.xml").decode())

    def test_sem_modelo_vira_marcador(self):
        with mock.patch.object(da, "achar_modelo", return_value=None):
            c = da.compor_documento("contrato", {})
        self.assertIn("[MARCADOR: modelo de contrato", c["texto"])


class TestFluxo(Base):
    def novo(self):
        return self.d.gerar({"tipo": "proposta", "fonte": {"tipo": "compra", "numero": "LJ-DOC-1"}}, "erick")["id"]

    def test_emissao_sem_aprovacao_e_recusada(self):
        i = self.novo()
        r = self.d.emitir(i, "erick", converter_pdf=False)
        self.assertFalse(r["ok"])
        self.assertEqual(r["codigo"], 409)
        self.assertIn("aprovado", r["erro"])
        self.d.enviar_revisao(i, "erick")
        self.assertFalse(self.d.emitir(i, "erick", converter_pdf=False)["ok"])          # em revisão também não
        self.assertEqual(self.d.ver(i)["documento"]["estado"], "em_revisao")
        self.assertTrue(any(x["o_que"] == "emissão recusada" for x in self.registros("documento_auto")))

    def test_fluxo_completo_e_registro(self):
        i = self.novo()
        self.assertEqual(self.d.enviar_revisao(i, "erick")["estado"], "em_revisao")
        self.assertEqual(self.d.aprovar(i, "rafaella")["estado"], "aprovado")
        doc = self.d.ver(i)["documento"]
        self.assertEqual((doc["aprovado_por"], doc["aprovado_em"]), ("rafaella", AGORA))
        r = self.d.emitir(i, "erick", converter_pdf=lambda b: {"ok": True, "pdf": b"%PDF-1.7 teste"})
        self.assertTrue(r["ok"])
        self.assertTrue(r["resultado"]["pdf"])
        arq = self.d.arquivo(i)
        self.assertTrue(arq["nome"].endswith(".odt") and "RASCUNHO" not in arq["nome"])
        self.assertEqual(self.d.arquivo(i, "pdf")["bytes"], b"%PDF-1.7 teste")
        self.assertEqual(self.d.editar(i, "outro texto", "erick")["codigo"], 409)        # emitido não muda
        acoes = [x["o_que"] for x in self.registros("documento_auto")]
        self.assertEqual(acoes, ["criado", "enviar para revisão", "aprovar", "emitir"])
        self.assertEqual(self.registros("documento_auto")[-1]["aprovado_por"], "rafaella")
        self.assertEqual(self.h.verificar_cadeia()[0], True)
        self.assertEqual([x["acao"] for x in self.d.ver(i)["documento"]["historico"]], ["criado", "enviar para revisão", "aprovar", "emitir"])

    def test_mudar_aprovado_volta_para_revisao(self):
        i = self.novo()
        self.d.enviar_revisao(i, "erick")
        self.d.aprovar(i, "rafaella")
        r = self.d.editar(i, "# Proposta\n\nTexto novo", "erick")
        self.assertEqual((r["estado"], r["voltou_para_revisao"]), ("em_revisao", True))
        self.assertIsNone(self.d.ver(i)["documento"]["aprovado_por"])
        self.assertFalse(self.d.emitir(i, "erick", converter_pdf=False)["ok"])
        self.assertEqual(self.d.devolver(i, "rafaella", "falta prazo")["estado"], "rascunho")
        self.assertEqual(self.d.aprovar(i, "rafaella")["codigo"], 409)                  # rascunho não se aprova direto

    def test_previa_antes_da_emissao_e_rascunho(self):
        i = self.novo()
        arq = self.d.arquivo(i)
        self.assertIn("RASCUNHO", arq["nome"])
        self.assertIn("RASCUNHO", zipfile.ZipFile(io.BytesIO(arq["bytes"])).read("content.xml").decode())
        self.assertFalse(self.d.arquivo(i, "pdf")["ok"])

    def test_papeis_na_rota(self):
        corpo = json.dumps({"tipo": "proposta", "fonte": {"tipo": "compra", "numero": "LJ-DOC-1"}})
        self.assertEqual(self.d.rota("POST", "/api/emissao/gerar", None, corpo)[0], 401)
        self.assertEqual(self.d.rota("POST", "/api/emissao/gerar", CLIENTE, corpo)[0], 403)
        cod, r = self.d.rota("POST", "/api/emissao/gerar", EQUIPE, corpo)
        self.assertEqual(cod, 200)
        i = r["id"]
        self.assertEqual(self.d.rota("POST", f"/api/emissao/{i}/enviar", EQUIPE, "")[0], 200)
        self.assertEqual(self.d.rota("POST", f"/api/emissao/{i}/aprovar", EQUIPE, "")[0], 403)          # equipe não aprova
        self.assertEqual(self.d.rota("POST", f"/api/emissao/{i}/aprovar", DIRECAO, "")[0], 200)
        cod, fila = self.d.rota("GET", "/api/emissao", DIRECAO, None, {"estado": ["aprovado"]})
        self.assertEqual([x["id"] for x in fila["documentos"]], [i])
        self.assertTrue(fila["pode_aprovar"])
        cod, b = self.d.rota("GET", f"/api/emissao/{i}/arquivo", EQUIPE, None, {"formato": ["odt"]})
        self.assertTrue(b["_bytes"].startswith(b"PK"))


class TestNF(Base):
    def test_dados_e_adaptador_fase2(self):
        with mock.patch.dict(os.environ, {"PHYSIS_NF_CNPJ": "00.000.000/0001-00"}, clear=False):
            for k in ("PHYSIS_NF_CODIGO_SERVICO", "PHYSIS_NF_ALIQUOTA_ISS", "PHYSIS_NF_RAZAO_SOCIAL"):
                os.environ.pop(k, None)
            i = self.d.gerar({"tipo": "nf", "fonte": {"tipo": "compra", "numero": "LJ-DOC-1"}}, "erick")["id"]
        doc = self.d.ver(i)["documento"]
        self.assertIn("CNPJ: 00.000.000/0001-00", doc["texto"])
        self.assertIn("Tomador", doc["texto"])
        self.assertIn("servico.codigo", doc["pendencias"])           # código de serviço só da configuração
        self.assertIn("**Valor total: R$ 1.500,00**", doc["texto"])
        self.d.enviar_revisao(i, "erick")
        self.d.aprovar(i, "rafaella")
        r = self.d.emitir(i, "erick", converter_pdf=False)
        self.assertTrue(r["resultado"]["nf"]["pendente"])               # provedor de NF: Fase 2
        self.assertEqual(da.EmissorNF().emitir({})["provedor"], "manual")


class TestRelatorioEManual(Base):
    def test_relatorio_na_ordem_das_abas(self):
        c = da.compor_relatorio(["supervisao", "agua", "solar", "xyz"], {"cliente": {"nome": "F"}}, "Mensal")
        self.assertEqual(c["modulos"], ["solar", "agua", "supervisao", "xyz"])
        t = c["texto"]
        self.assertLess(t.index("## Energia solar"), t.index("## Qualidade da água"))
        self.assertLess(t.index("## Qualidade da água"), t.index("## SCADA"))
        self.assertIn("modelo de relatório do módulo xyz", t)
        self.assertTrue(t.startswith("# Relatório Physis — Mensal"))
        for m in da.VENDAVEIS:                                  # todo módulo vendável tem modelo de relatório
            self.assertIsNotNone(da.achar_modelo(f"relatorios/{m}"), m)

    def test_relatorios_usam_os_ids_do_mapa_de_variaveis(self):
        mapa = da.REPO / "sistema" / "physis-variaveis.json"
        if not mapa.is_file():
            self.skipTest("mapa de variáveis ausente")
        ids = {v["id"] for v in json.loads(mapa.read_text(encoding="utf-8"))["variaveis"]}
        usados = set()
        for arq in sorted(da.MODELOS_REPO.joinpath("relatorios").glob("*.md")):
            for campo in da._CAMPO.findall(arq.read_text(encoding="utf-8")):
                if not campo.startswith(("relatorio.", "cliente.", "hoje")):
                    self.assertIn(campo, ids, f"{arq.name}: {campo} não está no mapa de variáveis")
                    usados.add(campo)
        self.assertTrue(usados)
        c = da.compor_relatorio(["agua"], {"agua.leituras": "pH 7,1 (média)"})
        self.assertIn("| pH 7,1 (média) |", c["texto"])

    def test_manual_so_com_os_modulos_comprados(self):
        curto = da.compor_manual(["agua"], {"cliente": {"nome": "F"}})["texto"]
        longo = da.compor_manual(list(da.VENDAVEIS), {"cliente": {"nome": "F"}})["texto"]
        self.assertLess(len(curto), len(longo))
        self.assertIn("### Qualidade da água", curto)
        self.assertNotIn("### SCADA", curto)
        self.assertLess(curto.index("## As telas"), curto.index("Aba **Qualidade da água**"))      # a seção do módulo entra no lugar
        self.assertLess(curto.index("Aba **Qualidade da água**"), curto.index("## Equipamentos"))
        for nome in ("Monitoramento verde", "SCADA", "SustainKit", "Planejador", "Certificações", "Energia solar", "Gestão"):
            self.assertIn(f"### {nome}", longo)
        for _, secao in da.SECOES_MANUAL:                       # estrutura da Santa Clara, sempre
            self.assertIn(f"## {secao}", curto)
        self.assertIn("Proteção de dados (LGPD)", curto)
        self.assertIn("limite provisório não gera alerta", curto.lower())
        for m in da.VENDAVEIS:                                  # todo vendável tem seção própria de manual
            sec = da.secoes_md(da._ler_md(f"manual/modulos/{m}") or "")
            for s in ("as-telas", "alertas", "rotina", "pontos-em-aberto"):
                self.assertTrue(sec.get(s), f"{m}: falta {s}")

    def test_manual_da_compra_na_fila(self):
        r = self.d.manual_da_compra("LJ-DOC-1", ["agua"], "rafaella")
        doc = self.d.ver(r["id"])["documento"]
        self.assertEqual((doc["tipo"], doc["estado"], doc["origem"]), ("manual", "rascunho", "compra:LJ-DOC-1"))
        self.assertIn("Fazenda Teste", doc["texto"])


class FalsaIA:
    ativa, tipo = True, "claude"

    def __init__(self):
        self.pedidos = []
        self.ultimo = {"tipo": "claude", "modelo": "claude-opus-5-5", "quando": "2026-11-15T10:00:00"}

    def gerar(self, sistema, pedido, robo="", nomes=()):
        from physis_hub.robos import anonimizar
        pedido = anonimizar(pedido, nomes)          # como a IAClaude faz
        self.pedidos.append((sistema, pedido, robo))
        return "# Proposta adaptada\n\nTexto adaptado. [MARCADOR: valores]"


class TestBiblioteca(Base):
    def popular(self):
        self.d.bib_acrescentar("Irrigação por gotejamento em fazenda de café", "Projeto de irrigação com sensores de umidade do solo "
                               "e energia solar para bombeamento em fazenda de café.", "erick", "edital", "agro", "medio")
        self.d.bib_acrescentar("Eficiência energética em escola", "Diagnóstico energético, iluminação LED e climatização em escola pública.",
                               "erick", "proposta", "educacao", "pequeno")
        self.d.bib_acrescentar("Reúso de água em indústria", "Estação de reúso de água cinza, qualidade da água e pH para indústria.",
                               "erick", "proposta", "industria", "grande")

    def test_busca_e_metadados(self):
        self.popular()
        r = self.d.bib_buscar("irrigação com sensores de umidade e bomba solar", tipo="edital", setor="agro")
        self.assertEqual(r[0]["titulo"], "Irrigação por gotejamento em fazenda de café")
        r2 = self.d.bib_buscar("água", tipo="proposta")
        self.assertEqual(r2[0]["titulo"], "Reúso de água em indústria")
        self.assertTrue(self.d.bib_acrescentar("x", "Diagnóstico energético, iluminação LED e climatização em escola pública.", "e")["repetido"])

    def test_indexar_pasta(self):
        pasta = Path(self.tmp.name) / "bib"
        pasta.mkdir()
        (pasta / "solar-escola.md").write_text("Usina solar fotovoltaica em escola rural.", encoding="utf-8")
        (pasta / "solar-escola.md.json").write_text(json.dumps({"tipo": "edital", "setor": "educacao"}), encoding="utf-8")
        (pasta / "agro.odt").write_bytes(odf.odt("Agro", [{"t": "Agrofloresta e viveiro de mudas"}], logo_png=False))
        self.assertEqual(self.d.bib_indexar()["novos"], 2)
        self.assertEqual(self.d.bib_indexar()["novos"], 0)
        self.assertEqual(self.d.bib_buscar("viveiro de mudas")[0]["titulo"], "agro")

    def test_adaptar_com_ia_sem_dados_pessoais(self):
        self.popular()
        ia = FalsaIA()
        d = da.DocumentosAuto(self.h, ia=ia)
        r = d.adaptar({"texto": "Irrigação com sensores para fazenda de soja. Contato: joao@fazenda.com, CPF 123.456.789-09",
                       "tipo": "edital", "setor": "agro"}, "erick")
        self.assertTrue(r["ok"])
        self.assertEqual(r["base"]["titulo"], "Irrigação por gotejamento em fazenda de café")
        enviado = ia.pedidos[0][1]
        self.assertNotIn("joao@fazenda.com", enviado)
        self.assertNotIn("123.456.789-09", enviado)
        self.assertEqual(ia.pedidos[0][2], "documentos")
        doc = d.ver(r["id"])["documento"]
        self.assertEqual((doc["tipo"], doc["estado"]), ("adaptado", "rascunho"))       # nunca sai direto
        self.assertEqual(doc["ia"]["modelo"], "claude-opus-5-5")
        self.assertEqual(self.registros("documento_auto")[-1]["ia"]["provedor"], "claude")
        self.assertFalse(d.emitir(r["id"], "erick", converter_pdf=False)["ok"])

    def test_adaptar_sem_ia(self):
        self.popular()
        r = self.d.adaptar({"texto": "Eficiência energética em escola, contato ana@x.com"}, "erick")
        doc = self.d.ver(r["id"])["documento"]
        self.assertIn("[MARCADOR: adaptar este documento", doc["texto"])
        self.assertNotIn("ana@x.com", doc["texto"])
        self.assertIsNone(doc["ia"])
        self.assertEqual(self.d.adaptar({"texto": ""}, "e")["codigo"], 400)


class TestMontar(unittest.TestCase):
    def test_pacote_leva_o_manual_dos_modulos(self):
        import montar
        with tempfile.TemporaryDirectory() as t:
            pac = montar.montar("cliente-teste", "l1", ["agua"], Path(t), None, montar.LICENCA_PADRAO, nome="Fazenda Teste")
            with zipfile.ZipFile(pac) as z:
                nomes = z.namelist()
                md = z.read(next(n for n in nomes if n.endswith("manual/MANUAL-RASCUNHO.md"))).decode("utf-8")
            self.assertTrue(any(n.endswith("manual/MANUAL-RASCUNHO.odt") for n in nomes))
            self.assertTrue(any(n.endswith("modelos/manual/comum.md") for n in nomes))
            self.assertIn("Fazenda Teste", md)
            self.assertIn("### Qualidade da água", md)
            self.assertNotIn("### SCADA", md)


class TestServidor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from physis_hub.servidor import iniciar
        cls.tmp = tempfile.TemporaryDirectory()
        cls.env = mock.patch.dict(os.environ, {"PHYSIS_ENTREGAS": cls.tmp.name, "PHYSIS_CLAUDE_CONSUMO": str(Path(cls.tmp.name) / "c.json")})
        cls.env.start()
        for k in ("PHYSIS_SMTP_HOST", "ANTHROPIC_API_KEY", "PHYSIS_CLAUDE_CHAVE", "PHYSIS_CLAUDE_CHAVE_ARQUIVO"):
            os.environ.pop(k, None)
        cls.hub = Hub()
        cls.srv = iniciar(cls.hub, 0, endereco="127.0.0.1", instancia={"login": False})
        cls.porta = cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.env.stop()
        cls.tmp.cleanup()

    def chamar(self, metodo, rota, corpo=None, cookie=None, extra=None):
        h = {"Content-Type": "application/json"}
        if cookie:
            h["Cookie"] = cookie
        h.update(extra or {})
        req = urllib.request.Request(f"http://127.0.0.1:{self.porta}{rota}", data=json.dumps(corpo).encode() if corpo is not None else None,
                                     method=metodo, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                b = r.read()
                return r.status, (json.loads(b) if "json" in (r.headers.get("Content-Type") or "") else b)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or "{}")

    def test_compra_aprovada_gera_manual_e_fila(self):
        self.assertEqual(self.chamar("GET", "/api/emissao")[0], 401)
        self.assertEqual(self.chamar("POST", "/api/central/compra", COMPRA)[0], 200)
        req = urllib.request.Request(f"http://127.0.0.1:{self.porta}/api/conta/criar", method="POST", headers={"Content-Type": "application/json"},
                                     data=json.dumps({"nome": "Rafa", "usuario": "rafa", "senha": "senha-bem-longa-123"}).encode())
        with urllib.request.urlopen(req, timeout=10) as r:
            ck = r.headers.get("Set-Cookie").split(";")[0]
        st, r = self.chamar("POST", "/api/central/compra/LJ-DOC-1/aprovar", {}, ck)
        self.assertEqual(st, 200)
        mid = r["instalacao"]["manual"]
        st, fila = self.chamar("GET", "/api/emissao", cookie=ck)
        self.assertIn(mid, [x["id"] for x in fila["documentos"]])
        self.assertEqual(sorted(x["tipo"] for x in fila["documentos"]), ["contrato", "manual", "nf"])      # sozinhos, como rascunho
        self.assertEqual({x["estado"] for x in fila["documentos"]}, {"rascunho"})
        self.assertEqual(self.chamar("POST", f"/api/emissao/{mid}/emitir", None, ck)[0], 409)          # sem aprovação: recusa
        self.assertEqual(self.chamar("POST", f"/api/emissao/{mid}/enviar", None, ck, {"X-Physis-CSRF": "errado"})[0], 403)   # CSRF
        self.assertEqual(self.chamar("POST", f"/api/emissao/{mid}/enviar", None, ck)[0], 200)
        self.assertEqual(self.chamar("POST", f"/api/emissao/{mid}/aprovar", {"nota": "ok"}, ck)[0], 200)
        with mock.patch.object(odf, "converter_pdfa", return_value={"ok": False}):
            st, r = self.chamar("POST", f"/api/emissao/{mid}/emitir", None, ck)
        self.assertEqual((st, r["estado"]), (200, "emitido"))
        st, b = self.chamar("GET", f"/api/emissao/{mid}/arquivo?formato=odt", cookie=ck)
        self.assertTrue(b.startswith(b"PK"))
        st, c = self.chamar("GET", "/api/ia/consumo", cookie=ck)
        self.assertEqual(st, 200)
        self.assertFalse(c["consumo"]["configurada"])
        self.assertNotIn("chave", json.dumps(c).lower().replace("configurada", ""))


if __name__ == "__main__":
    unittest.main()
