"""Mapa de variáveis e fluxo de dados (sistema/physis-variaveis.json; texto em docs/MAPA_DE_VARIAVEIS.md).

Protege (pedido de 15/11/2026: "todas as variáveis estatísticas mapeadas e modeladas; fluxo de dados contínuo"):
1. Toda variável tem unidade, tipo válido, módulo conhecido e o lugar no código (arquivo que existe e símbolo que
   está dentro dele).
2. Todo módulo de hub.ITEM_MODULOS (e de MODULOS_PLATAFORMA) aparece no mapa, e cada item da loja liga no mapa os
   mesmos módulos que liga no hub. Os itens à venda são os de LOJA_VENDA (painel) mais as certificações.
3. Toda variável consumida tem produtor ou uma fonte alternativa declarada (campo manual, premissa, …).
4. Toda premissa citada existe em sistema/physis-premissas.json, e toda premissa da base está no mapa.
5. Toda grandeza do contrato (nucleo.FAIXAS) e todo TIPO V6 aceito aparecem em alguma variável.
6. Para cada item à venda sozinho e cada par de itens à venda: nenhuma lacuna sem tratamento declarado
   (módulo comprado precisa de um número cujo produtor não veio junto). E nenhuma lacuna declarada é fantasma.
7. Estatísticas e fluxos apontam para variáveis que existem, com produtor e consumidor coerentes.
8. Ruptura consertada sai da lista declarada e o conserto continua no código (R1, R3, R5, R6, R11).

Só roda dentro do repositório (no pacote do cliente o JSON e o painel podem não ir).
"""
import itertools
import json
import re
import unittest
from pathlib import Path

from physis_hub import adaptador, nucleo, protocolo
from physis_hub.hub import Hub

RAIZ = Path(__file__).resolve().parents[2]
MAPA = RAIZ / "sistema" / "physis-variaveis.json"
PREMISSAS = RAIZ / "sistema" / "physis-premissas.json"
PAINEL = RAIZ / "physis-hub" / "web" / "painel.html"
DOC = RAIZ / "physis-hub" / "docs" / "MAPA_DE_VARIAVEIS.md"
NO_REPO = MAPA.is_file() and PREMISSAS.is_file() and PAINEL.is_file()

TIPOS = {"measured", "typed", "calculated", "premissa", "external"}
TRATAMENTOS = {"campo_manual", "premissa_padrao", "tela_oculta", "valor_fixo_codigo", "sem_dado"}
MODOS = {"automatico", "sugestao", "manual"}


@unittest.skipUnless(NO_REPO, "só no repositório")
class TestMapaDeVariaveis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = json.loads(MAPA.read_text(encoding="utf-8"))
        cls.vars = {v["id"]: v for v in cls.m["variaveis"]}
        cls.mods = set(cls.m["modulos"])
        cls.sempre = set(cls.m["loja"]["sempre_disponiveis"])
        cls.prem = {p["id"] for p in json.loads(PREMISSAS.read_text(encoding="utf-8"))["premissas"]}
        cls.painel = PAINEL.read_text(encoding="utf-8")
        achado = re.search(r"const LOJA_VENDA = new Set\(\[([^\]]*)\]", cls.painel)
        cls.venda = sorted(set(re.findall(r'"([^"]+)"', achado.group(1))) | {"cert-" + c for c in Hub.CERTIFICACOES_LOJA})
        cls.declaradas = {(g["variavel"], g["consumidor"]): g for g in cls.m["lacunas"]}
        cls.textos = {}

    def _texto(self, arq):
        if arq not in self.textos:
            p = RAIZ / arq
            self.textos[arq] = self.painel if p == PAINEL else (p.read_text(encoding="utf-8") if p.is_file() else None)
        return self.textos[arq]

    def _lacunas(self, itens):
        """(variável, consumidor) necessárias cujo produtor não está nos módulos dos itens nem nos sempre ligados."""
        m = set(self.sempre)
        for it in itens:
            m |= set(Hub.ITEM_MODULOS.get(it, ()))
        out = set()
        for v in self.m["variaveis"]:
            if set(v["produtores"]) & m:
                continue
            for c in v["consumidores"]:
                if c["necessario"] and c["modulo"] in m:
                    out.add((v["id"], c["modulo"]))
        return out

    # 1. cada variável bem formada
    def test_variaveis_tem_unidade_tipo_modulo_e_lugar_no_codigo(self):
        self.assertEqual(self.m["esquema"], "physis-variaveis/1")
        self.assertEqual(len(self.vars), len(self.m["variaveis"]), "id repetido")
        for v in self.m["variaveis"]:
            with self.subTest(v=v["id"]):
                self.assertTrue(str(v["unidade"]).strip(), "unidade não declarada")
                self.assertIn(v["tipo"], TIPOS)
                self.assertIn(v["modulo"], self.mods)
                self.assertTrue(v["nome"]["pt"] and v["nome"]["en"])
                self.assertTrue(v["armazenamento"], "sem armazenamento")
                self.assertTrue(v["frequencia"] and v["agregacao"])
                self.assertIn("fonte", v["faixa"])
                self.assertTrue(v["lote"])
                self.assertTrue(v["onde"], "sem lugar no código")
                for o in v["onde"]:
                    texto = self._texto(o["arquivo"])
                    self.assertIsNotNone(texto, f"arquivo não existe: {o['arquivo']}")
                    self.assertIn(o["simbolo"], texto, f"{o['simbolo']!r} não está em {o['arquivo']}")
                for p in v["produtores"]:
                    self.assertIn(p, self.mods)
                for c in v["consumidores"]:
                    self.assertIn(c["modulo"], self.mods)
                    self.assertIn(c["modo"], MODOS)
                    self.assertIsInstance(c["necessario"], bool)
                for e in v["entradas"]:
                    self.assertIn(e, self.vars, f"entrada desconhecida {e}")

    # 2. loja × hub
    def test_todo_modulo_e_item_do_hub_esta_no_mapa(self):
        itens = self.m["loja"]["itens"]
        for item, mods in Hub.ITEM_MODULOS.items():
            with self.subTest(item=item):
                self.assertIn(item, itens)
                self.assertEqual(itens[item]["modulos"], list(mods), "módulos do item diferentes do hub")
                for mod in mods:
                    self.assertIn(mod, self.mods)
        for mod in Hub.MODULOS_PLATAFORMA:
            self.assertIn(mod, self.mods)
        for item in self.venda:
            with self.subTest(venda=item):
                self.assertIn(item, itens)
                self.assertTrue(itens[item]["venda"])
                if item not in Hub.ITEM_MODULOS:
                    self.assertTrue(itens[item]["sem_modulo"], "item à venda sem módulo e sem motivo declarado")
        self.assertEqual(sorted(self.m["loja"]["itens_a_venda"]), self.venda)
        self.assertTrue(self.sempre <= self.mods)

    # 3. produtor ou fonte declarada
    def test_variavel_consumida_tem_produtor_ou_fonte_declarada(self):
        for v in self.m["variaveis"]:
            if not v["consumidores"]:
                continue
            with self.subTest(v=v["id"]):
                alt = v.get("fonte_alternativa")
                self.assertTrue(v["produtores"] or (alt and alt["tratamento"] in TRATAMENTOS and alt["descricao"]),
                                "consumida sem produtor e sem fonte alternativa declarada")

    # 4. premissas
    def test_premissas_citadas_existem_e_todas_estao_no_mapa(self):
        citadas = {p for v in self.m["variaveis"] for p in v["premissas"]}
        citadas |= {p for e in self.m["estatisticas"] for p in e["premissas"]}
        self.assertFalse(citadas - self.prem, f"premissas que não existem na base: {sorted(citadas - self.prem)}")
        no_mapa = {v["premissas"][0] for v in self.m["variaveis"] if v["tipo"] == "premissa"}
        self.assertEqual(no_mapa, self.prem, "premissa da base fora do mapa (ou sobrando)")

    # 5. contrato e protocolo cobertos
    def test_grandezas_do_nucleo_e_tipos_v6_estao_no_mapa(self):
        armaz = " ".join(" ".join(v["armazenamento"]) for v in self.m["variaveis"])
        for g in nucleo.FAIXAS:
            self.assertIn(g, armaz, f"grandeza {g} do contrato sem variável")
        tipos = " ".join(v["origem"]["sensor"]["tipo_v6"] for v in self.m["variaveis"] if "sensor" in v["origem"])
        for t in set(adaptador.TIPOS) | set(protocolo.TIPOS_SAUDE):
            self.assertIn(t, tipos, f"TIPO V6 {t} sem variável")

    # 6. combinações da loja
    def test_itens_a_venda_sozinhos_e_em_par_sem_lacuna_escondida(self):
        for combo in itertools.chain(((i,) for i in self.venda), itertools.combinations(self.venda, 2)):
            faltam = self._lacunas(combo) - set(self.declaradas)
            self.assertFalse(faltam, f"{combo}: lacuna sem tratamento declarado {sorted(faltam)}")

    def test_lacunas_declaradas_sao_reais_e_tem_tratamento(self):
        reais = self._lacunas(())
        for item in Hub.ITEM_MODULOS:
            reais |= self._lacunas((item,))
        for chave, g in self.declaradas.items():
            with self.subTest(lacuna=chave):
                self.assertIn(chave, reais, "lacuna declarada que não acontece")
                self.assertIn(g["tratamento"], TRATAMENTOS)
                self.assertIn(g["impacto"], ("alto", "medio", "baixo"))
                self.assertTrue(g["como_o_sistema_trata"] and g["correcao_recomendada"])
                self.assertEqual(g["produtores"], self.vars[chave[0]]["produtores"])
        self.assertFalse(reais - set(self.declaradas), "lacuna (de qualquer item do hub) sem tratamento declarado")

    # 7. estatísticas e fluxos coerentes
    def test_estatisticas_tem_metodo_amostra_e_entradas(self):
        for e in self.m["estatisticas"]:
            with self.subTest(e=e["id"]):
                self.assertTrue(e["metodo"] and e["amostra_minima"] and e["validacao"] and e["saidas"])
                for x in e["entradas"]:
                    self.assertIn(x, self.vars)
                for c in e["consumidores"]:
                    self.assertIn(c, self.mods)
                for o in e["onde"]:
                    self.assertIn(o["simbolo"], self._texto(o["arquivo"]) or "", f"{o['simbolo']!r} fora de {o['arquivo']}")

    def test_fluxos_ligam_produtor_a_consumidor(self):
        self.assertTrue(self.m["fluxos"])
        for f in self.m["fluxos"]:
            with self.subTest(f=(f["de"], f["para"], f["variavel"])):
                v = self.vars[f["variavel"]]
                self.assertIn(f["de"], v["produtores"])
                usa = {c["modulo"] for c in v["consumidores"]} | {x["modulo"] for x in self.m["variaveis"] if f["variavel"] in x["entradas"]}
                self.assertIn(f["para"], usa)
        for r in self.m["rupturas"]:
            for o in r["onde"]:
                self.assertIn(o["simbolo"], self._texto(o["arquivo"]) or "", f"{r['id']}: {o['simbolo']!r}")

    # 8. rupturas consertadas saem da lista e não voltam
    def test_rupturas_consertadas_fora_da_lista_e_continuam_consertadas(self):
        import inspect
        from physis_hub import aprendizado, carbono, integridade
        consertadas = {"R1", "R3", "R5", "R6", "R11",           # 15/11/2026, ver docstring de tests/test_fluxo_dados.py
                       "R2", "R4", "R7", "R8", "R9", "R10"}     # 15/11/2026, lado do painel (lista de mudanças do painel)
        abertas = {r["id"] for r in self.m["rupturas"]}
        self.assertFalse(abertas & consertadas, "ruptura consertada ainda declarada")
        # R1: toda grandeza medida em medicao tem produtor (nenhuma 'sem produtor') e os medidores geram as grandezas
        for v in self.m["variaveis"]:
            if v["tipo"] == "measured" and any(a.startswith("tabela medicao") for a in v["armazenamento"]):
                self.assertTrue(v["produtores"] and "fonte_alternativa" not in v, v["id"])
        gerados = set()
        for linha in ("ID:61,TIPO:ENE,PW:1,V:220,I:5,FP:0.9", "ID:62,TIPO:HID,Q:1,PR:2"):
            gerados |= {m["grandeza"] for m in adaptador.adaptar(dict(x.split(":", 1) for x in linha.split(",")), "org-teste", "l")}
        self.assertTrue({"energia", "tensao", "corrente", "fp", "vazao", "pressao"} <= gerados)
        # R3, R6, R11: o código consertado continua lá
        self.assertIn("physis-gestao-cliente", inspect.getsource(aprendizado._producao_gestao))
        self.assertIn("fechar_lote_diario", inspect.getsource(aprendizado.passo_diario))
        self.assertTrue(callable(integridade.lote_diario))
        self.assertIn("base", Hub.ITEM_MODULOS)
        self.assertIn("consultoria-pers", Hub.ITEM_MODULOS)
        # R5: mesmas parcelas de evitadas no Python e no JS
        js = self._texto("sistema/physis-carbono.js")
        chaves_js = set(re.findall(r"(\w+):", re.search(r"const evit = \{(.*?)\};", js).group(1)))
        self.assertEqual(set(carbono.calcular({"v": 2}, {}, carbono.carregar())["evitadas"]), chaves_js)
        # R2: a ponte do navegador manda as mesmas chaves da água que o servidor aceita
        from physis_hub import alertas_clima, perfil_cliente
        ponte = self._texto("sistema/physis-ponte-cliente.js")
        for k in perfil_cliente.CHAVES_AGUA:
            self.assertIn(k, perfil_cliente.CHAVES)
            self.assertIn(f'"{k}"', re.search(r"var CHAVES = \[(.*?)\];", ponte, re.S).group(1))
        # R4: Solar, Secador e Turbinas nas evitadas, nos dois lados
        self.assertTrue({"solar", "secador", "turbinas"} <= chaves_js)
        r = carbono.calcular({"v": 2}, {"solar_kwh": 1000, "secador_co2_kg": 500, "turbinas_kwh": 2000}, carbono.carregar())
        self.assertGreater(r["evitadas"]["solar"], 0)
        self.assertAlmostEqual(r["evitadas"]["secador"], 0.5)
        self.assertGreater(r["evitadas"]["turbinas"], 0)
        # R7: limiares dos alertas vêm das premissas (nenhum número de limiar no código das regras)
        fonte = inspect.getsource(alertas_clima.avaliar)
        self.assertIn("limiares()", fonte)
        for n in ("< 3", ">= 10", ">= 30", "< 1", ">= 35", ">= 50", ">= 80", ">= 120"):
            self.assertNotIn(n, fonte)
        # R8: toda grandeza do nucleo.py está no núcleo JS
        nucleo_js = self._texto("sistema/physis-nucleo.js")
        bloco = re.search(r"var FAIXAS = \{(.*?)\};", nucleo_js, re.S).group(1)
        for g in nucleo.FAIXAS:
            self.assertRegex(bloco, rf"\b{g}:")
        # R9: sem 0,0289 próprio no secador e no servidor verde do navegador
        for arq in ("sistema/physis-secador.js", "sistema/physis-servidor-verde.js"):
            self.assertNotIn("0.0289", self._texto(arq))
        # R10: taxa e inflação do ranking vêm das premissas
        self.assertTrue({"gestao.taxa_desconto", "gestao.inflacao"} <= self.prem)
        self.assertIn('PhysisCalc.premissa("gestao.taxa_desconto")', self.painel)

    # 9. local do cliente: uma função só no servidor, modelada com fontes e consumidores
    def test_local_do_cliente_modelado_e_funcao_unica(self):
        v = self.vars["lugar.coordenadas"]
        self.assertEqual(set(v["entradas"]), {"lugar.inicio", "lugar.lote_planejador", "lugar.monitoramento", "lugar.instalacao"})
        usa = {c["modulo"] for c in v["consumidores"]}
        self.assertTrue({"clima", "solar", "resiliencia", "secador", "avac", "sbn", "circular", "carbono"} <= usa)
        self.assertIn("def local_da_instalacao", self._texto("physis-hub/physis_hub/hub.py"))
        h = Hub(":memory:")
        h.instancia = {}
        loc = h.local_da_instalacao()
        self.assertTrue({"lat", "lon", "municipio", "uf", "poligono", "area_m2", "fonte"} <= set(loc))
        self.assertEqual((loc["fonte"], loc["lat"], loc["lon"]), ("nao_informado", None, None))
        for f in self.m["fluxos"]:
            if f["variavel"] == "lugar.coordenadas":
                self.assertIn(f["de"], {"planejador", "monitoramento", "inicio", "instalacao"})

    # 10. fator de potência sempre na energia (regra do usuário); premissa pendente sai da lista quando existir
    def test_fator_de_potencia_modelado_e_premissa_pendente(self):
        pend = self.m.get("premissas_pendentes", {})
        for pid in pend:
            self.assertNotIn(pid, self.prem, f"{pid} já existe na base: tirar de premissas_pendentes e citar nas variáveis")
        v = self.vars["energia.potencias_dia"]
        self.assertTrue({"sup.energia", "sup.potencia_reativa_aparente", "sup.eletrica"} <= set(v["entradas"]))
        self.assertIn("eletrica.fator_potencia_padrao", v["formula"])
        self.assertTrue("eletrica.fator_potencia_padrao" in pend or "eletrica.fator_potencia_padrao" in v["premissas"])
        self.assertIn("aprendizado.potencias", {e["id"] for e in self.m["estatisticas"]})
        for g in ("energia", "potencia_reativa", "potencia_aparente", "fp"):
            self.assertIn(g, nucleo.FAIXAS)

    def test_texto_simples_existe_e_cita_as_lacunas(self):
        self.assertTrue(DOC.is_file())
        doc = DOC.read_text(encoding="utf-8")
        self.assertIn("```mermaid", doc)
        for g in self.m["lacunas"]:
            self.assertIn(f"`{g['variavel']}`", doc)


if __name__ == "__main__":
    unittest.main()
