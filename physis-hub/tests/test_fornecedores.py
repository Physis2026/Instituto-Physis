"""Banco de fornecedores e equipamentos (fornecedores.py e sistema/physis-fornecedores.js).

Protege:
1. Região: município → estado → Brasil, cada passo só quando o anterior não tem ninguém, com o rótulo dizendo qual valeu;
   raio do fornecedor local; sem local, "local não informado — preencha no Início".
2. Desatualizado: data da última atualização por região contra o limite da premissa (status "conferir").
3. CSV por região: validado (tudo ou nada), com resumo SHA-256 que não muda com ; ou , nem CRLF; conferir depois.
4. Preço só com data, região e fonte; cliente vê só preço de catálogo, nunca cotação.
5. Cliente x equipe: o cliente vê só aprovado e ativo, só campos públicos (nada de CNPJ, contato, nota interna,
   arquivo interno, local da sede); a equipe vê tudo. A rota do cliente nunca devolve campo interno nem arquivo interno.
6. LGPD: contato só com consentimento; apagar contato; histórico sem dado pessoal, só cresce e com a cadeia íntegra.
7. Equipamentos ligados aos ids da base (categoria tem de bater).
8. Fila por região (Ryan), "pedir atualização" vira tarefa na Gestão; importar a região fecha a tarefa.
9. Arquivos: só PDF/imagem conferidos pelo conteúdo, até 20 MB, SHA-256; download da equipe; cliente só o público.
10. Mapa da equipe: filtros e instalações dos clientes com fornecedores perto.
11. O módulo da tela não chama a internet e usa as mesmas listas.
"""
import json
import re
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from physis_hub import fornecedores as fo
from physis_hub.clima import FUSO
from physis_hub.hub import Hub

AGORA = datetime(2026, 11, 15, 10, 0, tzinfo=FUSO).timestamp()
DIA = 86400
CNPJ_A, CNPJ_B, CNPJ_C = "11.222.333/0001-81", "11.444.777/0001-61", "45.997.418/0001-53"
JS = (Path(__file__).resolve().parents[2] / "sistema" / "physis-fornecedores.js").read_text(encoding="utf-8")
EQUIP = {"itens": [{"id": "fv-perc-144", "categoria": "módulos fotovoltaicos", "descricao": "Módulo PERC 144"},
                   {"id": "inv-string-mono-3-6", "categoria": "inversores", "descricao": "Inversor 3 a 6 kW"},
                   {"id": "bat-lfp-48v-5", "categoria": "baterias", "descricao": "Bateria LFP"},
                   {"id": "motor-x", "categoria": "motores", "descricao": "fora da solar"}]}
PREM = {"premissas": [{"id": fo.PREMISSA_DIAS, "valor_padrao": 60, "status": "conferir"}]}
PDF = b"%PDF-1.4\n%teste\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
EQUIPE = {"usuario": "ryan", "papel": "operador"}
DIRECAO = {"usuario": "dir", "papel": "administrador"}
CLIENTE = {"usuario": "maria", "papel": "cliente"}


def base(**k):
    d = {"cnpj": CNPJ_A, "nome": "Sol Distribuidora Ltda", "nome_publico": "Sol Distribuidora", "site": "sol.example",
         "abrangencia": "regional", "uf": "RJ", "municipio": "Petrópolis", "ibge": "3303906", "lat": -22.505, "lon": -43.178,
         "notas_internas": "negocia desconto de 7%", "regioes": [{"uf": "RJ", "municipio": "Petrópolis", "ibge": "3303906"}],
         "contatos": [{"nome": "Ana Vendas", "email": "ana@sol.example", "telefone": "(24) 98888-1111", "consentimento": True}]}
    d.update(k)
    return d


class Regras(unittest.TestCase):
    def test_base_e_premissa(self):
        b = fo.base_equipamentos(EQUIP)
        self.assertEqual(b["fv-perc-144"]["categoria"], "modulos")
        self.assertNotIn("motor-x", b)
        self.assertEqual(fo.premissa_dias(PREM), (60, "conferir"))
        self.assertEqual(fo.premissa_dias({"premissas": []}), (fo.DIAS_PADRAO, "conferir"))
        real = fo.base_equipamentos()            # a base do repositório tem as classes da aba solar
        for i in ("fv-perc-144", "fv-perc-108", "fv-topcon-144", "inv-string-mono-3-6", "inv-string-mono-8-10", "inv-string-tri-15-30"):
            self.assertIn(i, real)

    def test_alcance(self):
        regs = [{"uf": "RJ", "ibge": "3303906", "municipio": "Petrópolis", "atualizado": AGORA},
                {"uf": "SP", "ibge": "", "municipio": "", "atualizado": AGORA}]
        self.assertEqual(fo.alcance({}, regs, "RJ", "3303906")[0], 3)
        self.assertEqual(fo.alcance({}, regs, "rj", "", "petropolis")[0], 3)
        self.assertEqual(fo.alcance({}, regs, "RJ", "3304557", "Rio de Janeiro")[0], 0)
        self.assertEqual(fo.alcance({}, regs, "SP", "", "Campinas")[0], 2)
        self.assertEqual(fo.alcance({}, [{"uf": "BR", "ibge": "", "municipio": "", "atualizado": AGORA}], "AM")[0], 1)
        local = {"lat": -22.5, "lon": -43.18, "raio_km": 30}
        self.assertEqual(fo.alcance(local, regs[:1], "RJ", "3305802", "Teresópolis", -22.41, -42.97)[0], 3)    # ~23 km
        self.assertEqual(fo.alcance(local, regs[:1], "RJ", "3304557", "Rio", -22.90, -43.20)[0], 0)           # ~45 km

    def test_preco_exige_data_regiao_fonte(self):
        ok = {"valor": 1.2, "unidade": "R$/Wp", "data": "2026-11-10", "fonte": "catálogo", "uf": "RJ"}
        self.assertEqual(fo.validar_preco(ok, "2026-11-15")[0]["fonte"], "catalogo")
        for falta, msg in (("data", "sem data"), ("fonte", "sem fonte"), ("uf", "sem região")):
            p, erro = fo.validar_preco({k: v for k, v in ok.items() if k != falta}, "2026-11-15")
            self.assertIsNone(p)
            self.assertIn(msg, erro)
        self.assertIsNone(fo.validar_preco(dict(ok, data="2026-12-01"), "2026-11-15")[0])       # futuro
        self.assertIsNone(fo.validar_preco(dict(ok, data="2026-02-30"), "2026-11-15")[0])       # não existe
        self.assertIsNone(fo.validar_preco(dict(ok, valor=0), "2026-11-15")[0])
        self.assertFalse(fo.preco_mostravel({"valor": 1, "fonte": "catalogo", "uf": "RJ", "data": ""}))

    def test_arquivo_tipo(self):
        self.assertEqual(fo.tipo_arquivo("cat.pdf", PDF)[0], "application/pdf")
        self.assertIsNone(fo.tipo_arquivo("cat.pdf", b"MZ\x90\x00")[0])
        self.assertIsNone(fo.tipo_arquivo("cat.png", PDF)[0])              # conteúdo não bate com a extensão
        self.assertIsNone(fo.tipo_arquivo("cat.html", b"<html>")[0])
        self.assertIsNone(fo.tipo_arquivo("cat.pdf", b"%PDF-" + b"0" * fo.ARQ_MAX)[0])


class NoHub(unittest.TestCase):
    def setUp(self):
        self.rel = [AGORA]
        self.tmp = tempfile.TemporaryDirectory()
        self.h = Hub(":memory:", relogio=lambda: self.rel[0])
        self.f = fo.Fornecedores(self.h, pasta=self.tmp.name, equipamentos=EQUIP, premissas=PREM)

    def tearDown(self):
        self.tmp.cleanup()

    def novo(self, aprovar=True, **k):
        r = self.f.cadastrar(base(**k), "ryan")
        self.assertTrue(r["ok"], r)
        i = r["id"]
        self.assertTrue(self.f.oferta(i, {"categoria": "modulos", "marca": "MarcaX", "modelo": "X-550", "equipamento_id": "fv-perc-144"}, "ryan")["ok"])
        if aprovar:
            self.assertTrue(self.f.curar(i, "aprovado", "", "dir", True)["ok"])
        return i

    def test_cadastro_cnpj_e_lgpd(self):
        self.assertIn("CNPJ", self.f.cadastrar(base(cnpj="11.222.333/0001-82"), "ryan")["erro"])
        r = self.f.cadastrar(base(contatos=[{"nome": "Ana", "email": "ana@sol.example"}]), "ryan")
        self.assertFalse(r["ok"])
        self.assertIn("LGPD", r["erro"])
        self.assertIn("finalidade", r)
        i = self.novo(aprovar=False)
        self.assertFalse(self.f.cadastrar(base(nome="Outra"), "ryan")["ok"])                  # CNPJ repetido
        self.assertFalse(self.f.contato(i, {"nome": "Beto", "telefone": "24999990000"}, "ryan")["ok"])
        c = self.f.contato(i, {"nome": "Beto", "telefone": "24999990000", "consentimento": True}, "ryan")
        self.assertTrue(c["ok"])
        self.assertTrue(self.f.contato_remover(i, c["id"], "ryan")["ok"])
        hist = json.dumps([r for r in self.h._db.execute("SELECT detalhe FROM fornecedor_historico")], ensure_ascii=False)
        registro = " ".join(r[0] for r in self.h._db.execute("SELECT conteudo FROM registro"))
        for proibido in ("Ana", "ana@", "98888", "Beto", "99990000"):
            self.assertNotIn(proibido, hist + registro)
        self.assertEqual(self.f.verificar_historico(), (True, len(self.f.historico()["itens"])))
        with self.assertRaises(Exception):
            self.h._db.execute("DELETE FROM fornecedor_historico")
        with self.assertRaises(Exception):
            self.h._db.execute("UPDATE fornecedor_historico SET quem='x'")
        self.assertTrue(self.h.verificar_cadeia()[0])

    def test_curadoria(self):
        i = self.f.cadastrar(base(regioes=[], abrangencia="estadual", uf=""), "ryan")["id"]
        self.assertEqual(self.f.curar(i, "aprovado", "", "ryan", False)["codigo"], 403)
        r = self.f.curar(i, "aprovado", "", "dir", True)
        self.assertIn("pelo menos uma região atendida", r["pendencias"])
        self.assertFalse(self.f.curar(i, "suspenso", "", "dir", True)["ok"])

    def test_cascata_municipio_estado_brasil(self):
        a = self.novo()                                                            # Petrópolis
        b = self.novo(cnpj=CNPJ_B, nome="Estado Solar SA", nome_publico="Estado Solar", regioes=[{"uf": "RJ"}], abrangencia="estadual")
        c = self.novo(cnpj=CNPJ_C, nome="Brasil Solar SA", nome_publico="Brasil Solar", regioes=[], abrangencia="nacional")
        r = self.f.na_regiao("RJ", "3303906", "Petrópolis", ["fv-perc-144"])
        self.assertEqual((r["nivel"], [x["id"] for x in r["fornecedores"]]), ("municipio", [a]))
        self.assertIn("Petrópolis/RJ", r["rotulo"])
        r = self.f.na_regiao("RJ", "3304557", "Rio de Janeiro", ["fv-perc-144"])
        self.assertEqual((r["nivel"], [x["id"] for x in r["fornecedores"]]), ("uf", [b]))
        self.assertIn("todo o estado", r["rotulo"])
        r = self.f.na_regiao("AM", "", "Manaus", ["fv-perc-144"])
        self.assertEqual((r["nivel"], [x["id"] for x in r["fornecedores"]]), ("nacional", [c]))
        self.assertIn("todo o Brasil", r["rotulo"])
        self.assertEqual(r["itens"][0]["fornecedores"][0]["casamento"], "exato")
        r = self.f.na_regiao("", "", "", ["fv-perc-144"])
        self.assertEqual(r["nivel"], "sem_local")
        self.assertEqual(r["aviso"], "local não informado — preencha no Início")
        # por item: inversor só o nacional oferece (categoria); em Petrópolis o item cai para o Brasil
        self.f.oferta(c, {"categoria": "inversores", "marca": "InvY", "modelo": "Y5"}, "ryan")
        it = self.f.na_regiao("RJ", "3303906", "Petrópolis", ["fv-perc-144", "inv-string-mono-3-6"])["itens"]
        self.assertEqual((it[0]["nivel"], it[1]["nivel"]), ("municipio", "nacional"))
        self.assertEqual(it[1]["fornecedores"][0]["casamento"], "categoria")

    def test_desatualizado(self):
        i = self.novo()
        r = self.f.na_regiao("RJ", "3303906")["fornecedores"][0]
        self.assertEqual((r["desatualizado"], r["ultima_atualizacao"]), (False, "2026-11-15"))
        self.rel[0] = AGORA + 61 * DIA
        self.assertTrue(self.f.na_regiao("RJ", "3303906")["fornecedores"][0]["desatualizado"])
        fila = self.f.fila()
        self.assertEqual((fila["responsavel"]["nome"], fila["regioes"][0]["situacao"]), ("Ryan", "desatualizada"))
        rid = self.f.interno()["fornecedores"][0]["regioes"][0]["id"]
        self.assertTrue(self.f.regiao_conferida(i, rid, "ryan")["ok"])
        self.assertFalse(self.f.na_regiao("RJ", "3303906")["fornecedores"][0]["desatualizado"])

    def test_pedir_atualizacao_vira_tarefa_na_gestao(self):
        self.novo()
        self.rel[0] = AGORA + 90 * DIA
        r = self.f.pedir_atualizacao({"uf": "RJ", "ibge": "3303906", "municipio": "Petrópolis"}, "ryan")
        self.assertTrue(r["ok"] and r["gestao"])
        self.assertEqual(r["responsavel"], "Ryan")
        self.assertTrue(self.f.pedir_atualizacao({"uf": "RJ", "ibge": "3303906"}, "ryan")["ja_existia"])
        g = json.loads(self.h.gestao_ler()[fo.CHAVE_GESTAO]["valor"])
        self.assertEqual((g["tarefas"][0]["responsavel"], g["tarefas"][0]["estado"]), ("ryan", "aberta"))
        csv_txt = f"cnpj;categoria;marca;modelo\n{CNPJ_A};modulos;MarcaX;X-550\n"
        self.assertTrue(self.f.importar({"uf": "RJ", "ibge": "3303906", "municipio": "Petrópolis", "csv": csv_txt}, "ryan")["ok"])
        g = json.loads(self.h.gestao_ler()[fo.CHAVE_GESTAO]["valor"])
        self.assertEqual(g["tarefas"][0]["estado"], "feita")

    def test_csv_validacao_e_resumo(self):
        self.novo()
        reg = {"uf": "RJ", "ibge": "3303906", "municipio": "Petrópolis"}
        ruim = ("cnpj;categoria;marca;modelo;equipamento_id;preco;preco_unidade;preco_data;preco_fonte\n"
                f"{CNPJ_A};modulos;M;A;inv-string-mono-3-6;;;;\n"                 # id de outra categoria
                f"{CNPJ_B};modulos;M;B;;;;;\n"                                     # fornecedor não cadastrado
                f"{CNPJ_A};modulos;M;C;;1,10;R$/Wp;;catalogo\n"                     # preço sem data
                f"{CNPJ_A};pintura;M;D;;;;;\n")
        r = self.f.importar(dict(reg, csv=ruim), "ryan")
        self.assertFalse(r["ok"])
        self.assertEqual(len(r["erros"]), 4)
        self.assertEqual(self.h._db.execute("SELECT COUNT(*) FROM fornecedor_importacao").fetchone()[0], 0)   # tudo ou nada
        self.assertFalse(self.f.importar(dict(reg, csv="cnpj;coisa\n1;2\n"), "ryan")["ok"])
        bom = ("cnpj;categoria;marca;modelo;equipamento_id;prazo_entrega_dias;pedido_minimo_brl;preco;preco_unidade;preco_data;preco_fonte;preco_fonte_ref\n"
               f"{CNPJ_A};modulos;MarcaX;X-550;fv-perc-144;5;1.500,00;1,10;R$/Wp;2026-11-01;catalogo;Tabela nov/26\n"
               f"{CNPJ_A};inversores;InvY;Y5;inv-string-mono-3-6;;;;;;;\n")
        sim = self.f.importar(dict(reg, csv=bom, simular=True), "ryan")
        self.assertTrue(sim["simulado"])
        r = self.f.importar(dict(reg, csv=bom, nome="rj.csv"), "ryan")
        self.assertTrue(r["ok"], r)
        self.assertRegex(r["resumo"], r"^[0-9a-f]{64}$")
        self.assertEqual((r["linhas"], r["precos"], r["resumo"]), (2, 1, sim["resumo"]))
        variante = bom.replace(";", ",").replace("1.500,00", "1500").replace("1,10", "1.10").replace("\n", "\r\n")
        self.assertEqual(self.f.importar(dict(reg, csv=variante, simular=True), "ryan")["resumo"], r["resumo"])
        self.assertTrue(self.f.conferir_importacao(r["importacao"], bom)["confere"])
        self.assertFalse(self.f.conferir_importacao(r["importacao"], bom.replace("X-550", "X-560"))["confere"])
        txt, nome = self.f.exportar_csv("RJ", "3303906", "Petrópolis")
        self.assertEqual(nome, "fornecedores-RJ-3303906.csv")
        self.assertIn("1,1;R$/Wp;2026-11-01;catalogo", txt)
        self.assertEqual(self.f.importar(dict(reg, csv=txt, simular=True), "ryan")["linhas"], 2)    # volta pelo import

    def test_cliente_x_equipe_e_precos(self):
        a = self.novo()
        oid = self.f.interno()["fornecedores"][0]["ofertas"][0]["oferta"]
        self.assertFalse(self.f.preco(a, {"oferta": oid, "valor": 1.0, "unidade": "R$/Wp", "fonte": "cotacao", "uf": "RJ"}, "ryan")["ok"])
        self.assertTrue(self.f.preco(a, {"oferta": oid, "valor": 0.98, "unidade": "R$/Wp", "data": "2026-11-12", "fonte": "cotacao",
                                         "fonte_ref": "cotação 123", "uf": "RJ", "ibge": "3303906"}, "ryan")["ok"])
        self.assertTrue(self.f.preco(a, {"oferta": oid, "valor": 1.05, "unidade": "R$/Wp", "data": "2026-11-01", "fonte": "catalogo",
                                         "uf": "RJ"}, "ryan")["ok"])
        self.assertFalse(self.f.preco(a, {"oferta": oid, "valor": 1.0, "unidade": "R$/Wp", "data": "2026-11-01", "fonte": "catalogo",
                                          "uf": "SP"}, "ryan")["ok"])                                  # região que não atende
        self.f.arquivo_por("catalogo.pdf", PDF, "ryan", fornecedor=a)
        pub = self.f.arquivo_por("publico.pdf", PDF + b"x", "ryan", fornecedor=a)
        self.assertEqual(self.f.arquivo_publico(pub["id"], True, "ryan", False)["codigo"], 403)
        self.assertTrue(self.f.arquivo_publico(pub["id"], True, "dir", True)["ok"])
        self.novo(aprovar=False, cnpj=CNPJ_B, nome="Em Análise Ltda")                 # não aparece ao cliente
        cod, r = self.f.rota("GET", "/api/fornecedores/regiao", CLIENTE, consulta={"uf": ["RJ"], "ibge": ["3303906"], "itens": ["fv-perc-144,instalacao"]})
        self.assertEqual(cod, 200)
        self.assertEqual([x["id"] for x in r["fornecedores"]], [a])
        f = r["fornecedores"][0]
        self.assertEqual(set(f), {"id", "nome", "site", "descricao", "abrangencia", "alcance", "regiao", "ultima_atualizacao", "desatualizado",
                                  "prazo_entrega_dias", "pedido_minimo_brl", "categorias", "produtos", "catalogos"})
        self.assertEqual(f["site"], "https://sol.example")
        self.assertEqual(f["produtos"][0]["precos"], [{"valor": 1.05, "unidade": "R$/Wp", "data": "2026-11-01", "fonte": "Catálogo",
                                                       "regiao": "RJ (estado todo)"}])
        self.assertEqual([c["nome"] for c in f["catalogos"]], ["publico.pdf"])
        texto = json.dumps(r, ensure_ascii=False)
        for proibido in ("11222333", "Sol Distribuidora Ltda", "Ana", "ana@", "98888", "desconto", "0.98", "cotação 123", "catalogo.pdf",
                         "-22.505", "notas_internas", "contatos", "cnpj", "sha256", "Em Análise", "Ryan"):
            self.assertNotIn(proibido, texto)
        cod, r = self.f.rota("GET", "/api/fornecedores/regiao", EQUIPE, consulta={"uf": ["RJ"], "ibge": ["3303906"]})
        self.assertEqual(len(r["fornecedores"]), 2)
        self.assertIn("negocia desconto", json.dumps(r, ensure_ascii=False))
        # rotas internas e arquivos: cliente barrado; arquivo interno 404 para o cliente, público sai
        for p in ("/api/fornecedores/interno", "/api/fornecedores/mapa", "/api/fornecedores/fila", "/api/fornecedores/exportar"):
            self.assertEqual(self.f.rota("GET", p, CLIENTE)[0], 403)
        interno = [x for x in self.f.interno()["fornecedores"] if x["id"] == a][0]["arquivos"]
        priv = [x["id"] for x in interno if not x["publico"]][0]
        self.assertEqual(self.f.rota("GET", f"/api/fornecedores/arquivo/{priv}", CLIENTE)[0], 404)
        self.assertEqual(self.f.rota("GET", f"/api/fornecedores/arquivo/{priv}", EQUIPE)[1][3], PDF)
        self.assertEqual(self.f.rota("GET", f"/api/fornecedores/arquivo/{pub['id']}", CLIENTE)[1][1], "publico.pdf")
        self.assertEqual(self.f.rota("POST", "/api/fornecedores/cadastro", CLIENTE, "{}")[0], 403)
        self.assertEqual(self.f.rota("GET", "/api/fornecedores/regiao", None)[0], 401)

    def test_equipamento_ligado_a_base(self):
        a = self.novo(aprovar=False)
        self.assertFalse(self.f.oferta(a, {"categoria": "modulos", "marca": "M", "equipamento_id": "inv-string-mono-3-6"}, "ryan")["ok"])
        self.assertFalse(self.f.oferta(a, {"categoria": "modulos", "marca": "M", "equipamento_id": "nao-existe"}, "ryan")["ok"])
        self.assertFalse(self.f.oferta(a, {"categoria": "instalacao", "marca": "M"}, "ryan")["ok"])     # instalação = parceiro
        e = self.f.equipamento({"categoria": "baterias", "marca": "B", "modelo": "B5", "equipamento_id": "bat-lfp-48v-5",
                                "ficha_url": "https://b.example/ficha.pdf"}, "ryan")
        self.assertTrue(e["ok"])
        self.assertTrue(self.f.oferta(a, {"equipamento": e["id"]}, "ryan")["ok"])
        eq = [x for x in self.f.interno()["equipamentos"] if x["id"] == e["id"]][0]
        self.assertEqual((eq["base"], eq["fornecedores"]), ("Bateria LFP", [a]))
        self.assertTrue(self.f.equipamento({"id": e["id"], "modelo": "B5 Pro"}, "ryan")["ok"])
        self.assertTrue(self.f.arquivo_por("ficha.pdf", PDF, "ryan", equipamento=e["id"], tipo_doc="ficha")["ok"])
        self.assertTrue(self.f.equipamento_remover(e["id"], "ryan")["ok"])
        self.assertFalse(list(Path(self.tmp.name).iterdir()))                      # arquivo sem dono sai do disco
        # instalação: link para o parceiro, não cadastro duplicado
        self.assertTrue(self.f.editar(a, {"parceiros": [7]}, "ryan")["ok"])
        self.f.curar(a, "aprovado", "", "dir", True)
        it = self.f.na_regiao("RJ", "3303906", "", ["instalacao"])["itens"][0]
        self.assertEqual((it["categoria"], it["parceiros_vitrine"]), ("instalacao", "/api/parceiros?servico=solar&uf=RJ"))

    def test_rota_esquema_e_auditoria(self):
        cod, r = self.f.rota("POST", "/api/fornecedores/cadastro", EQUIPE, json.dumps(dict(base(), extra=1)))
        self.assertEqual((cod, r["erro"]), (400, "campo desconhecido: extra"))
        cod, r = self.f.rota("POST", "/api/fornecedores/cadastro", EQUIPE, json.dumps(base()))
        self.assertEqual(cod, 200)
        i = r["id"]
        self.assertEqual(self.f.rota("POST", f"/api/fornecedores/{i}/curadoria", EQUIPE, '{"status":"aprovado"}')[0], 403)
        self.assertEqual(self.f.rota("POST", f"/api/fornecedores/{i}/editar", EQUIPE, '{"site":"https://novo.example"}')[0], 200)
        h = self.f.historico(i)
        self.assertEqual([x["o_que"] for x in h["itens"]], ["editado", "cadastro"])
        self.assertEqual((h["itens"][0]["quem"], h["itens"][0]["data"], h["integro"]), ("ryan", "2026-11-15", True))
        self.assertTrue(self.f.apagar(i, "dir")["ok"])
        self.assertEqual(self.h._db.execute("SELECT COUNT(*) FROM fornecedor_contato").fetchone()[0], 0)

    def test_mapa_e_clientes(self):
        a = self.novo()
        self.novo(cnpj=CNPJ_C, nome="Brasil Solar SA", regioes=[], abrangencia="nacional")
        self.h.cliente_gravar("physis-perfil", json.dumps({"c": {"municipio": "Petrópolis", "uf": "RJ", "ibge": "3303906", "lat": -22.5, "lon": -43.2}}),
                              0, "maria", org="cliente-a")
        m = self.f.mapa()
        self.assertEqual(len(m["fornecedores"]), 2)
        self.assertEqual(self.f.mapa(abrangencia="nacional")["fornecedores"][0]["abrangencia"], "nacional")
        self.assertEqual(len(self.f.mapa(categoria="inversores")["fornecedores"]), 0)
        cl = [c for c in m["clientes"] if c["org"] == "cliente-a"][0]
        self.assertEqual((cl["perto"], cl["fornecedores"]), (True, {"municipio": 1, "uf": 0, "nacional": 1}))
        self.rel[0] = AGORA + 70 * DIA
        self.assertEqual(len(self.f.mapa(situacao="desatualizado")["fornecedores"]), 2)
        self.assertIn("Nominatim", m["geocodificacao"])
        self.assertEqual(a, m["fornecedores"][0]["id"] if m["fornecedores"][0]["abrangencia"] == "regional" else m["fornecedores"][1]["id"])


class ModuloJS(unittest.TestCase):
    def test_contrato(self):
        for nome in ("montarSolar", "montarGestao", "montarMapa", "htmlSolar", "/api/fornecedores/regiao", "/api/fornecedores/interno",
                     "/api/fornecedores/mapa", "/api/fornecedores/importar", "/api/fornecedores/pedir-atualizacao", "X-Physis-CSRF",
                     "localDaInstalacao", "local não informado — preencha no Início", "PhysisODF", "cnpjValido"):
            self.assertIn(nome, JS)
        self.assertIsNone(re.search(r"https?://(?!www\.w3\.org/2000/svg)", JS))
        self.assertNotIn("<h1", JS)
        self.assertNotRegex(JS.lower(), r"</script")

    def test_mesmas_listas(self):
        for grupo in (fo.CATEGORIAS, fo.ABRANGENCIAS, fo.STATUS, fo.FONTES_PRECO):
            for k, v in grupo.items():
                self.assertIn(f'{k}:"{v}"', JS)
        self.assertIn(f"DIAS_PADRAO = {fo.DIAS_PADRAO}", JS)


if __name__ == "__main__":
    unittest.main()
