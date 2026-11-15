"""Tela do aprendizado e dos avisos de clima (sistema/physis-aprendizado-ui.js), sem navegador.

Protege:
1. Independência: nada de internet, eval, '</script' (vai embutido no <head> do painel), nem título h1.
2. Inglês: todo texto fixo do módulo está no I18N (ou é pedaço de uma frase do I18N_RX); as frases prontas que o
   servidor manda (explicações, textos de irrigação e de anomalia, avisos) casam com algum I18N_RX.
3. Os campos de JSON que a tela lê existem nas respostas de verdade de aprendizado.py e alertas_clima.py, e o
   corpo da assinatura só usa campos que alertas_clima.assinar entende.
4. As rotas que a tela chama existem em servidor.py; cores só da paleta; atributos data-pau-… sem colidir com o painel.
"""
import json
import random
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))      # os auxiliares dos outros testes, rodando de qualquer jeito

from physis_hub import alertas_clima as ac
from physis_hub import aprendizado as ap

RAIZ = Path(__file__).resolve().parents[2]
MODULO = RAIZ / "sistema" / "physis-aprendizado-ui.js"
HUB = Path(__file__).resolve().parents[1]
NO_REPO = MODULO.is_file()


def literais_js(src):
    from test_preferencias import _literais_js            # a mesma leitura de literais da barra de preferências
    return _literais_js(src)


IGNORAR = {"use strict", "Enter"}


def visivel(s):
    """Texto que aparece na tela: o critério da barra de preferências, sem pedaços de atributo HTML nem listas de classes."""
    from test_preferencias import _visivel
    k = _visivel(s)
    if not k or k in IGNORAR or '="' in k or k.startswith('"') or re.search(r'="?$', k):
        return None
    if all(re.fullmatch(r"[a-z0-9-]+", p) for p in k.split()) and re.search(r"[-\d]", k):
        return None                                              # lista de classes (ex.: "t2 pq")
    return k


def objeto_js(js, nome):
    """Lê `var NOME = {...};` ou `[...]` (só literais de texto) como JSON."""
    i = js.index(f"var {nome} = ") + len(f"var {nome} = ")
    abre = js[i]
    fecha = "}" if abre == "{" else "]"
    prof, j, txt = 0, i, None
    while j < len(js):
        c = js[j]
        if c == '"':
            j += 1
            while js[j] != '"':
                j += 2 if js[j] == "\\" else 1
        elif c == abre:
            prof += 1
        elif c == fecha:
            prof -= 1
            if not prof:
                txt = js[i:j + 1]
                break
        j += 1
    txt = re.sub(r"^\s*//.*$", "", txt, flags=re.M)
    if re.match(r"\{\s*[A-Za-z_]", txt):                    # chaves sem aspas (ROTAS, ATIVIDADES...): põe aspas
        txt = re.sub(r'([{,]\s*)([A-Za-z_]\w*):\s', r'\1"\2": ', txt)
    return json.loads(txt)


def codigo_de_tela(js):
    """O código sem os blocos I18N, I18N_RX e CSS (que não são texto mostrado na tela)."""
    for nome in ("I18N_RX", "I18N"):
        i = js.index(f"var {nome} = ")
        j = js.index("];" if nome == "I18N_RX" else "};", i)
        js = js[:i] + js[j + 2:]
    i = js.index("var CSS = ")
    return js[:i] + js[js.index(";\n", i) + 2:]


def coberto(k, chaves, rx_textos):
    k = k.strip()
    return k in chaves or any(k in c for c in chaves) or any(k in r for r in rx_textos)


AGORA = 1794747600.0


def respostas_reais():
    """Respostas de verdade das rotas, com os dados sintéticos dos testes do aprendizado (sem servidor HTTP)."""
    import test_aprendizado as ta
    h = ta.hub_com_chuva(120)
    a = ap.Aprendizado(h)
    h._db.execute("INSERT INTO clima_fonte(fonte,dados,consultado) VALUES('openmeteo',?,?)",
                  (json.dumps({"dias": [{"dia": "2026-11-16", "mm": 15.0, "chove": True, "tmin": 17.0, "tmax": 29.0}]}), ta.AGORA))
    h._db.commit()
    ta.inserir_medicoes(h, "lugar01-no03", "umidade_solo", ta.TestIrrigacao().pontos())
    rnd = random.Random(2)
    s = [(ta.AGORA - 100 * 300 + i * 300, round(24 + rnd.gauss(0, 0.3), 2)) for i in range(100)] + [(ta.AGORA, 41.0)]
    ta.inserir_medicoes(h, "lugar01-no05-ar", "temperatura", s)
    ta.inserir_medicoes(h, "lugar01-no90", "energia", [(ta.AGORA - d * 86400 + k * 3600, 2.0 + rnd.random() * 0.2 + (1.4 if d == 2 else 0))
                                                        for d in range(1, 31) for k in range(0, 24, 6)])
    a.treinar()
    al = ac.AlertasClima(h, aprendizado=a, whatsapp=None, relogio=lambda: ta.AGORA)
    assert al.assinar({"consentimento": True, "email": "ana@exemplo.com.br", "atividades": ["irrigacao"]}, "ana")["ok"]
    al.ciclo()
    return {"previsao-chuva": a.previsao_chuva(), "anomalias": a.anomalias(), "consumo": a.consumo(), "irrigacao": a.irrigacao(),
            "estado": a.estado(), "assinaturas": {"ok": True, "assinaturas": al.assinaturas("ana"), "regras": {k: v[0] for k, v in ac.REGRAS.items()},
                                                  "atividades": list(ac.ATIVIDADES), "finalidade": ac.FINALIDADE, "whatsapp": bool(al.whatsapp)},
            "historico": {"ok": True, "historico": al.historico(quem="ana")}}


def frases_do_servidor():
    """Frases prontas que o servidor manda e que a tela mostra como vieram."""
    import test_aprendizado as ta
    out = []
    for n in (10, 365):
        m = ap.treinar_chuva(ap.dados_chuva(ta.hub_com_chuva(n)._db), ta.AGORA)
        out.append(ap.explicar_chuva(m))
    m = ap.treinar_chuva(ap.dados_chuva(ta.hub_com_chuva(365)._db), ta.AGORA)
    m["metricas"]["brier_modelo"] = 0.3                       # forma "ainda não superou"
    out.append(ap.explicar_chuva(m))
    out.append(ap.explicar_anomalias(ap.treinar_anomalias({"x-no01|umidade_solo": ta.TestAnomalias().serie()}, ta.AGORA)))
    s = ta.TestAnomalias().serie()
    out += [x["texto"] for x in ap.detectar_anomalias({"x-no01|umidade_solo": s + [(ta.AGORA, 99.0)]}, ta.AGORA)]
    out += [x["texto"] for x in ap.detectar_anomalias({"x-no01|temperatura": s + [(ta.AGORA + i * 300, 41.0) for i in range(1, 25)]}, ta.AGORA)]
    pts = [(ta.AGORA - (6 - d / 4) * 86400, 0) for d in range(25)]
    pts = [(t, 3.90 - 0.02 * ((t - pts[0][0]) / 86400)) for t, _ in pts]
    out += [x["texto"] for x in ap.detectar_anomalias({"x-no02|bateria": pts}, ta.AGORA)]
    tc = ta.TestConsumo()
    out += [ap.explicar_consumo(ap.treinar_consumo(tc.amostras(), ta.AGORA)), ap.explicar_consumo(ap.treinar_consumo(tc.amostras(5), ta.AGORA))]
    mi = ap.treinar_irrigacao(ta.TestIrrigacao().pontos(), ta.AGORA)
    out.append(ap.explicar_irrigacao(mi))
    out.append(ap.explicar_irrigacao(ap.treinar_irrigacao([(ta.AGORA, 40.0)], ta.AGORA)))
    for lim, p in ((15, 0.1), (15, 0.8), (35, 0.1), (35, 0.8)):
        out.append(ap.prever_irrigacao(mi, {"limite": lim, "prob_chuva": p, "agora": ta.AGORA})["texto"])
    plano = ap.treinar_irrigacao([(ta.AGORA - 3600 * h, 40.0) for h in range(5, 0, -1)], ta.AGORA)
    out.append(ap.prever_irrigacao(plano, {"limite": 30, "prob_chuva": 0.1, "agora": ta.AGORA})["texto"])
    out.append(ap.prever_irrigacao(ap.treinar_irrigacao([(ta.AGORA, 40.0)], ta.AGORA), {"limite": 30})["texto"])
    dias = [{"dia": "2026-07-10", "mm": 35.0, "tmin": 2.5, "tmax": 36.0}, {"dia": "2026-07-11", "mm": 6.0, "tmin": 0.5, "tmax": 20.0},
            {"dia": "2026-07-12", "mm": 0.0, "tmin": 3.5, "tmax": 20.0}, {"dia": "2026-07-13", "mm": 0.0, "tmin": 10.0, "tmax": 34.5}]
    out += [x["texto"] for x in ac.avaliar(dias, {"mm_24h": 45.0, "mm_72h": 50.0, "estacao": {"nome": "Quitandinha"}}, {"dia": "2026-07-11", "prob": 0.8}, "2026-07-10")]
    out += [x["texto"] for x in ac.avaliar([], {"mm_24h": 90.0, "mm_72h": 10.0}, None, "2026-07-10")]
    return out


@unittest.skipUnless(NO_REPO, "só no repositório")
class TelaAprendizado(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = MODULO.read_text(encoding="utf-8")
        cls.i18n = objeto_js(cls.js, "I18N")
        cls.rx = objeto_js(cls.js, "I18N_RX")

    def test_sem_internet_nem_eval_e_embutivel(self):
        js = self.js
        self.assertNotRegex(js, r"https?://")
        self.assertNotRegex(js, r"\beval\s*\(")
        self.assertNotIn("new Function", js)
        self.assertNotIn("document.write", js)
        self.assertNotRegex(js, r"(?i)</script")
        self.assertNotRegex(js, r"\bimportScripts|\bimport\s*\(")
        self.assertNotIn("<h1", js, "o módulo nunca emite h1: a tela tem um título só")
        self.assertTrue(js.rstrip().endswith('})(typeof window !== "undefined" ? window : this);'))
        self.assertIn("global.PhysisAprendizadoUI = api", js)
        self.assertNotIn("innerHTML", js, "o módulo devolve texto; quem põe na tela é o painel")

    def test_todo_texto_fixo_tem_ingles(self):
        chaves = set(self.i18n)
        rx_textos = [a.replace("\\", "") for a, _ in self.rx]
        faltam = sorted({k for k in map(visivel, literais_js(codigo_de_tela(self.js))) if k and not coberto(k, chaves, rx_textos)})
        self.assertEqual(faltam, [], "textos sem tradução no I18N")
        for k, v in self.i18n.items():
            self.assertTrue(v.strip(), k)
        for a, b in self.rx:
            re.compile(a)                      # a sintaxe usada vale em JS e em Python
            self.assertTrue(a.startswith("^") and a.endswith("$"), a)

    def test_textos_do_servidor_casam_com_o_i18n_rx(self):
        rxs = [re.compile(a) for a, _ in self.rx]
        sem = [f for f in frases_do_servidor() if f not in self.i18n and not any(r.match(f) for r in rxs)]
        self.assertEqual(sem, [], "frase do servidor sem tradução (mudou o texto em aprendizado.py ou alertas_clima.py?)")
        for k in list(ac.REGRAS.values()):
            self.assertIn(k[0], self.i18n)
        self.assertIn(ac.FINALIDADE, self.i18n)
        for nome in set(ap.NOMES_VARIAVEIS.values()):
            self.assertIn(nome, self.i18n)

    def test_campos_lidos_existem_nas_respostas_reais(self):
        r = respostas_reais()
        usados = {
            "previsao-chuva": ["dia", "prob", "modo", "explicacao", "contribuicoes", "metricas", "placar_prob", "modelo"],
            "anomalias": ["sensores", "anomalias"],
            "consumo": ["medidores"],
            "irrigacao": ["prob_chuva", "recomendacoes"],
            "estado": ["modelos"],
            "assinaturas": ["assinaturas", "regras", "atividades", "finalidade", "whatsapp"],
            "historico": ["historico"],
        }
        for rota, campos in usados.items():
            for c in campos:
                self.assertIn(c, r[rota], f"{rota}.{c}")
                self.assertRegex(self.js, rf"\.{c}\b", f"a tela deveria ler {c}")
        pc = r["previsao-chuva"]
        for c in ("brier_modelo", "brier_placar", "modo"):
            self.assertIn(c, pc["metricas"])
        self.assertIn("treinado_em", pc["modelo"])
        self.assertTrue({"texto", "efeito"} <= set(pc["contribuicoes"][0]))
        an = r["anomalias"]["anomalias"]
        self.assertTrue(an)
        self.assertTrue({"ativo", "grandeza", "nivel", "tipo", "texto"} <= set(an[0]))
        self.assertTrue({a["nivel"] for a in an} <= {"alarme", "atencao"})
        m = r["consumo"]["medidores"][0]
        self.assertTrue({"ativo", "grandeza", "unidade", "dias", "desperdicio", "explicacao"} <= set(m))
        self.assertTrue({"dia", "esperado", "faixa", "real", "desperdicio"} <= set(m["dias"][0]))
        rec = r["irrigacao"]["recomendacoes"][0]
        self.assertTrue({"ativo", "limite", "acao", "texto", "explicacao"} <= set(rec))
        acoes = set(re.findall(r"(\w+): \[\"(?:al|in|ok)\"", self.js[self.js.index("var ACOES"):self.js.index("var ESTADOS_ENVIO")]))
        self.assertEqual(acoes, {"irrigar_agora", "agendar", "aguardar_chuva", "nao_precisa", "sem_dado"})
        self.assertTrue({"nome", "metricas", "explicacao"} <= set(r["estado"]["modelos"][0]))
        s = r["assinaturas"]["assinaturas"][0]
        self.assertTrue({"id", "canais", "alertas", "atividades", "email", "whatsapp", "nivel_min", "silencio_ini", "silencio_fim", "alerta_fura_silencio"} <= set(s))
        h = r["historico"]["historico"][0]
        self.assertTrue({"criado", "canal", "nivel", "estado", "texto"} <= set(h))
        ativ = objeto_js(self.js, "ATIVIDADES")
        self.assertEqual(set(ativ), set(ac.ATIVIDADES))
        grand = objeto_js(self.js, "GRANDEZAS")
        self.assertTrue(set(ap.GRANDEZAS_CONTINUAS) <= set(grand))
        self.assertEqual(set(objeto_js(self.js, "ESTADOS_ENVIO")), {"enfileirado", "enviado", "falhou"})

    def test_corpo_da_assinatura_e_sair(self):
        i = self.js.index("var corpo = { consentimento: true")
        corpo = self.js[i:self.js.index("};", i)]
        chaves = set(re.findall(r"(\w+):", corpo))
        fonte = (HUB / "physis_hub" / "alertas_clima.py").read_text(encoding="utf-8")
        for k in chaves:
            self.assertRegex(fonte, rf'd\.get\("{k}"\)|d\["{k}"\]', k)
        self.assertIn('corpo.id = F.id', self.js)
        self.assertIn('{ acao: "sair", id: ident }', self.js)
        self.assertIn('consentimento: true', self.js)
        self.assertIn('required aria-required="true"', self.js, "a caixa de consentimento é obrigatória (LGPD)")

    def test_rotas_existem_no_servidor(self):
        srv = (HUB / "physis_hub" / "servidor.py").read_text(encoding="utf-8")
        rotas = objeto_js(self.js, "ROTAS")
        for k, url in rotas.items():
            self.assertFalse(url.startswith("/"), "relativa, como o painel faz (api/clima)")
            if url.startswith("api/aprendizado/"):
                self.assertIn(f'"{url.rsplit("/", 1)[-1]}": aprendizado.', srv, url)
            else:
                self.assertIn(f'"/{url}"', srv, url)

    def test_cores_da_paleta_e_atributos(self):
        paleta = set(re.findall(r"#[0-9A-F]{6}", (HUB / "docs" / "PALETA.md").read_text(encoding="utf-8")))
        cores = set(c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}\b", self.js))
        self.assertTrue(cores <= paleta, cores - paleta)
        attrs = set(re.findall(r"data-([a-z][\w-]*)", self.js))
        self.assertTrue(all(a.startswith("pau-") for a in attrs), attrs)
        painel = (HUB / "web" / "painel.html").read_text(encoding="utf-8")
        painel = re.sub(r'<script id="mod-[\w-]+">.*?</script>', "", painel, flags=re.S)      # os módulos embutidos ficam de fora
        self.assertNotRegex(painel, r"data-pau-|dataset\.pau[A-Z]", "o painel não usa o prefixo do módulo")

    def test_avisos_marcam_as_atividades_do_perfil_do_servidor(self):
        # GET /api/alertas/assinaturas devolve atividades_perfil (servidor.py); o formulário já abre com elas marcadas
        srv = (HUB / "physis_hub" / "servidor.py").read_text(encoding="utf-8")
        self.assertIn('"atividades_perfil"', srv)
        self.assertIn("R.assinaturas.dados.atividades_perfil", self.js)

    def test_ligado_no_painel(self):
        painel = (HUB / "web" / "painel.html").read_text(encoding="utf-8")
        self.assertEqual(painel.count('<script id="mod-aprendizado-ui">'), 1)
        app = painel.split('<script id="mod-aprendizado-ui">', 1)[1]
        self.assertIn("PhysisAprendizadoUI.iniciar({", painel)
        self.assertIn("PhysisAprendizadoUI.secaoResiliencia(2)", painel)      # Resiliência climática, antes da matriz
        self.assertLess(painel.index("PhysisAprendizadoUI.secaoResiliencia(2)"), painel.index('<h2 id="h-re-mat">Matriz de riscos</h2>'))
        self.assertIn("PhysisAprendizadoUI.resumoAnomalias()", painel)        # e no Resumo
        self.assertIn('ligado: () => ui.modo === "hub" && !ui.demo', painel)  # na demonstração nada é buscado


if __name__ == "__main__":
    unittest.main()
