"""Adequações às normas feitas só no código (tabela "Adequações que dá para fazer já", 15/11/2026).

Espelho em Python das contas comuns de sistema/physis-calc-comum.js (window.PhysisCalc), usadas pela plataforma,
pelo SustainKit e pelo Planejador, e o critério "Pronto quando" de cada item:
1  Carbono: o inventário do SustainKit não desconta a solar (evitadas à parte).
2  Solar: economia pela Lei 14.300 (100% autoconsumo = conta antiga; 100% injetado cai a cada ano da escala).
3  AVAC: ambiente com carga térmica calculada usa a carga (NBR 16401-1); m²/TR só como triagem.
4  Solar: plano das placas pelo modelo isotrópico (plano deitado = conta antiga; inclinado para o norte ganha no inverno).
5  Aquecimento solar: produção do coletor mês a mês pelo sol do lugar (duas cidades, duas áreas; sem 1,8 fixo).
6  Baterias: uma regra só (plataforma, SustainKit e agro) com premissas da base.
7  Fatores de emissão: SustainKit usa o diesel por litro e a regra do biogás da aba Carbono.
8  Planejador: calhas pela NBR 10844 (vazão = i·A/60, área corrigida pela inclinação).
9  Água de chuva: cisterna mês a mês com descarte inicial, a mesma conta no SustainKit e no Planejador.
15 Premissas soltas (coeficiente de retorno, dias de reserva) lidas da base.
Também: o Planejador não tem mais o botão próprio "Ajustes de leitura" (a barra única de preferências faz isso).
"""
import json
import math
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
CALC = RAIZ / "sistema" / "physis-calc-comum.js"
PREM = RAIZ / "sistema" / "physis-premissas.json"
SK = RAIZ / "sistema" / "SustainKit_Definitivo.html"
PL = RAIZ / "modulos" / "planejador" / "planejador-physis.html"
PAINEL = RAIZ / "physis-hub" / "web" / "painel.html"
SOLAR = RAIZ / "sistema" / "physis-solar.js"
AVAC = RAIZ / "sistema" / "physis-avac.js"
CARB = RAIZ / "sistema" / "physis-carbono.js"
NO_REPO = CALC.is_file() and PREM.is_file() and SK.is_file() and PL.is_file()

DIAS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
DIA_REP = [17, 47, 75, 105, 135, 162, 198, 228, 258, 288, 318, 344]
RAD = math.pi / 180


# ── espelho de window.PhysisCalc (mudou lá, muda aqui) ──
class Calc:
    def __init__(self, base):
        self.p = {x["id"]: x for x in base["premissas"]}

    def premissa(self, i):
        return self.p[i]["valor_padrao"] if i in self.p else None

    def fio_b(self, ano, regra=None):
        esc = self.premissa("solar.fio_b_escala")
        if regra == "antiga":
            return (0 if ano <= 2045 else None), ano > 2045
        anos = sorted(int(a) for a in esc)
        if ano < anos[0]:
            return 0, False
        if ano > anos[-1]:
            return esc[str(anos[-1])], True
        return esc[str(max(a for a in anos if a <= ano))], False

    def economia(self, ger, consumo_ano, auto, tarifa, fio_b, ano, disp, regra=None):
        pct = self.fio_b(ano, regra)[0] or 0
        cred = eco = 0.0
        for g in ger:
            cons = consumo_ano / 12
            au = min(g * auto, cons)
            inj, rede = g - au, cons - au
            cred += inj
            comp = min(cred, rede)
            cred -= comp
            custo = comp * pct * fio_b if fio_b is not None else 0
            antes = max(cons, disp) * tarifa
            depois = max((rede - comp) * tarifa + custo, disp * tarifa)
            eco += antes - depois
        return eco

    @staticmethod
    def h0(lat):
        out = []
        for n in DIA_REP:
            d = 23.45 * math.sin(RAD * 360 * (284 + n) / 365) * RAD
            f = lat * RAD
            ws = math.acos(max(-1, min(1, -math.tan(f) * math.tan(d))))
            e = 1 + 0.033 * math.cos(2 * math.pi * n / 365)
            out.append(24 / math.pi * 1.367 * e * (math.cos(f) * math.cos(d) * math.sin(ws) + ws * math.sin(f) * math.sin(d)))
        return out

    def fator_plano(self, H, lat, incl, azim):
        b, A, rho, H0, f = incl * RAD, azim * RAD, self.premissa("solar.albedo"), self.h0(lat), lat * RAD
        n = [math.sin(b) * math.sin(A), math.sin(b) * math.cos(A), math.cos(b)]
        fat = []
        for m, dn in enumerate(DIA_REP):
            if b == 0:
                fat.append(1.0)
                continue
            d = 23.45 * math.sin(RAD * 360 * (284 + dn) / 365) * RAD
            ws = math.acos(max(-1, min(1, -math.tan(f) * math.tan(d))))
            sp = sh = 0.0
            N = 240
            for k in range(N):
                w = -ws + (k + 0.5) * 2 * ws / N
                s = [-math.cos(d) * math.sin(w), math.sin(d) * math.cos(f) - math.cos(d) * math.sin(f) * math.cos(w),
                     math.sin(f) * math.sin(d) + math.cos(f) * math.cos(d) * math.cos(w)]
                if s[2] <= 0:
                    continue
                sh += s[2]
                sp += max(0, n[0] * s[0] + n[1] * s[1] + n[2] * s[2])
            rb = sp / sh
            kt = max(0.3, min(0.8, H[m] / H0[m]))
            if ws <= 81.4 * RAD:
                fd = 1.391 - 3.560 * kt + 4.189 * kt ** 2 - 2.137 * kt ** 3
            else:
                fd = 1.311 - 3.022 * kt + 3.427 * kt ** 2 - 1.821 * kt ** 3
            fat.append((1 - fd) * rb + fd * (1 + math.cos(b)) / 2 + rho * (1 - math.cos(b)) / 2)
        return fat

    def bateria(self, consumo_dia, horas, dod=None):
        dod = dod or self.premissa("bateria.dod")
        return consumo_dia * horas / 24 / dod / self.premissa("bateria.rendimento")

    @staticmethod
    def dias_chuva(ch):
        return [max(3, min(DIAS[m] - 2, round(2 + c / 12))) for m, c in enumerate(ch)]

    def cisterna(self, ch, area, coef, dem, desc, vols=(5, 10, 15, 20, 30, 45, 60, 90, 120, 160, 220), alvo=0.95, anos=10):
        dias = self.dias_chuva(ch)
        cap = [area * max(0, c * coef - desc * dias[m]) / 1000 for m, c in enumerate(ch)]
        best = None
        for V in vols:
            e, falta = V, 0.0
            for k in range(anos):
                for m in range(12):
                    e = min(V, e + cap[m] - dem)
                    if e < 0:
                        if k == anos - 1:
                            falta += -e
                        e = 0
            best = (V, 1 - falta / (dem * 12 or 1))
            if best[1] >= alvo:
                break
        return best

    def calha(self, a, b, incl, i):
        h = a * math.tan(incl * RAD)
        area = (a + h / 2) * b
        return area, i * area / 60


def antiga_cisterna(roofs, ch, dem):
    """Conta do Planejador até 15/11/2026 (coeficiente 0,80 fixo, sem descarte), para conferir a regressão."""
    best = None
    for V in [5, 10, 15, 20, 30, 45, 60, 90, 120, 160, 220]:
        e, f = V, 0.0
        for k in range(10):
            for m in range(12):
                e = min(V, e + roofs * ch[m] * 0.8 / 1000 - dem)
                if e < 0:
                    if k == 9:
                        f += -e
                    e = 0
        cob = 1 - f / (dem * 12 or 1)
        best = (V, cob)
        if cob >= 0.95:
            break
    return best


H_RIO = [5.78, 5.97, 5.14, 4.52, 3.68, 3.46, 3.64, 4.26, 4.57, 5.0, 5.05, 5.56]
CHUVA = [250, 200, 180, 90, 60, 40, 40, 40, 70, 120, 160, 220]


def bloco(html, ident):
    m = re.search(r'<script id="%s">\n(.*?)</script>' % re.escape(ident), html, re.S)
    return m.group(1) if m else None


@unittest.skipUnless(NO_REPO, "só no repositório")
class ContasComuns(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = json.loads(PREM.read_text(encoding="utf-8"))
        cls.c = Calc(cls.base)
        cls.js = CALC.read_text(encoding="utf-8")
        cls.sk = SK.read_text(encoding="utf-8")
        cls.pl = PL.read_text(encoding="utf-8")
        cls.solar = SOLAR.read_text(encoding="utf-8")
        cls.avac = AVAC.read_text(encoding="utf-8")

    def test_premissas_copiadas_e_blocos_iguais(self):
        m = re.search(r"/\*PREMISSAS-INICIO\*/\nvar PREMISSAS = (.*?);\n/\*PREMISSAS-FIM\*/", self.js, re.S)
        self.assertIsNotNone(m)
        copia = {k: self.base[k] for k in ("versao", "atualizado", "premissas")}
        self.assertEqual(json.loads(m.group(1).replace("<\\/", "</")), copia, "rode ferramentas/sincronizar.py")
        for nome, html in (("SustainKit", self.sk), ("Planejador", self.pl), ("painel", PAINEL.read_text(encoding="utf-8"))):
            with self.subTest(nome):
                self.assertEqual(bloco(html, "physis-calc-comum"), self.js.replace("\r\n", "\n"), "rode ferramentas/sincronizar.py")
        self.assertNotRegex(self.js, r"https?://", "contas comuns sem internet")

    def test_premissas_novas_tem_fonte_e_status(self):
        for i in ("solar.fio_b_escala", "tarifa.custo_disponibilidade", "solar.albedo", "bateria.rendimento", "agro.autonomia_dias",
                  "biogas.pci", "glp.pci", "drenagem.calha_tr", "drenagem.calha_duracao", "drenagem.calha_manning_n",
                  "drenagem.calha_declividade", "drenagem.condutor_diam_min", "chuva.descarte_inicial", "agua.fracao_nao_potavel",
                  "agua.reserva_dias", "esgoto.coef_retorno"):
            with self.subTest(i):
                p = self.c.p[i]
                self.assertTrue(p["fonte"].strip() and str(p["unidade"]).strip())
                self.assertEqual(p.get("status"), "conferir")
        for i in ("drenagem.calha_tr", "drenagem.calha_manning_n", "chuva.descarte_inicial"):
            self.assertIn("[CONFERIR NA NORMA]", self.c.p[i]["fonte"])
        self.assertIn("art. 27", self.c.p["solar.fio_b_escala"]["fonte"])

    # 2 ── Lei 14.300
    def test_2_economia_lei_14300(self):
        ger = [h * 100 for h in H_RIO]
        hoje = sum(ger) * 0.95                                           # conta antiga: geração × tarifa
        self.assertAlmostEqual(self.c.economia(ger, 24000, 1.0, 0.95, 0.30, 2026, 50), hoje, places=6)
        anos = [self.c.economia(ger, 24000, 0.0, 0.95, 0.30, a, 50) for a in range(2023, 2029)]
        self.assertTrue(all(x < hoje for x in anos), "100% injetado tem de economizar menos")
        self.assertTrue(all(b < a for a, b in zip(anos, anos[1:])), "a economia cai a cada ano da escala")
        self.assertAlmostEqual(self.c.economia(ger, 24000, 0.0, 0.95, 0.30, 2026, 50, "antiga"), hoje, places=6)
        self.assertTrue(self.c.fio_b(2031)[1], "depois da escala avisa")
        # custo de disponibilidade: a conta nunca fica abaixo do mínimo
        self.assertLess(self.c.economia([1000] * 12, 6000, 1.0, 1.0, None, 2026, 100), 12000)
        self.assertIn("PC.economiaSolar(", self.solar)
        self.assertIn("tarifa.custo_disponibilidade", self.solar)

    # 4 ── plano inclinado
    def test_4_plano_das_placas(self):
        self.assertEqual(self.c.fator_plano(H_RIO, -22.9, 0, 0), [1.0] * 12)
        norte = self.c.fator_plano(H_RIO, -22.9, 25, 0)
        self.assertGreater(norte[5], 1.2, "inclinado para o norte ganha em junho")
        self.assertLess(norte[0], 1.0, "e perde um pouco no verão")
        sul = self.c.fator_plano(H_RIO, -22.9, 25, 180)
        self.assertLess(sul[5], 1.0)
        self.assertIn("PCx().fatorPlano(", self.solar)
        self.assertIn('"physis-calc-telhado"', self.solar)
        self.assertIn('physisGravarCalc("physis-calc-telhado"', self.pl)

    # 5 ── aquecimento solar
    def test_5_aquecimento_solar_duas_cidades(self):
        eta, parcela = 0.55, 30.0
        area = lambda H: parcela / min(h * eta for h in H)
        curitiba = [x * 0.75 for x in H_RIO]
        self.assertNotAlmostEqual(area(H_RIO), area(curitiba))
        self.assertGreater(area(curitiba), area(H_RIO))
        self.assertNotRegex(self.avac, r"prod:\s*1\.8", "a produção fixa de 1,8 kWh/m²·dia saiu")
        self.assertIn("solar.prodUsada = solar.prodMes[solar.piorMes]", self.avac)
        self.assertIn("window.SOLAR.compat()", self.avac)

    # 3 ── carga térmica no ar-condicionado
    def test_3_avac_usa_carga_termica(self):
        self.assertIn("CARGA_TERMICA", self.avac)
        self.assertIn('"Carga térmica (NBR 16401-1)"', self.avac)
        self.assertIn("ct = N(x.carga) > 0 ? N(x.carga) : null", self.avac)
        # botão "Levar para o dimensionamento do ar-condicionado": confirmação antes, desfazer depois, valor à mão só com confirmação
        for trecho in ("Levar para o dimensionamento do ar-condicionado", 'data-avac-push="ok"', 'data-avac-push="desfazer"',
                       'role="alertdialog"', "valor feito à mão será trocado", "a.carga = c.btuh; a.override = null;",
                       "e0.ac.amb = JSON.parse(ui.avacDesfazer)", "planoCargas, aplicarCargas"):
            self.assertIn(trecho, self.avac, trecho)

    # 6 ── baterias
    def test_6_bateria_regra_unica(self):
        self.assertAlmostEqual(self.c.bateria(24000 / 365, 24, 0.9), 24000 / 365 / 24 * 24 / 0.9 / 0.95)
        self.assertIn("PC.bateria(consumo, auto, dod)", self.sk)
        self.assertIn("pc.bateria(consumoAno / 365, autH, dod)", self.solar)
        self.assertIn("PC.bateria(totalKwh, 24*pm('agro.autonomia_dias'), pm('bateria.dod'))", self.sk)
        self.assertIn("totalKwh/(hps*PR)", self.sk)
        self.assertNotIn("/dod*1.2", self.sk)
        self.assertNotIn("*2/0.80*1.2", self.sk)

    # 7 ── fatores de emissão
    def test_7_fatores_iguais_a_aba_carbono(self):
        self.assertIn("diesel: pm('combustivel.diesel')", self.sk)
        self.assertIn("biogas: pm('biogas.pci')/pm('glp.pci')*pm('combustivel.glp')", self.sk)
        self.assertNotIn("0.7400", self.sk)
        carb = CARB.read_text(encoding="utf-8")
        self.assertIn("biogM3 * PCI_BIOGAS() / PCI_GLP() * glpKg", carb)
        self.assertEqual(self.c.premissa("combustivel.diesel"), 2.671)

    # 1 ── inventário sem dupla contagem no SustainKit
    def test_1_sustainkit_inventario_sem_desconto_solar(self):
        self.assertIn("var inventario = emRede + emDiesel, saldoFirme = inventario, saldoTotal = inventario;", self.sk)
        self.assertNotIn("emRede + emDiesel - evSolar", self.sk)

    # 8 ── calhas
    def test_8_calhas_nbr_10844(self):
        a_plana, q_plana = self.c.calha(4, 10, 0, 150)
        self.assertAlmostEqual(a_plana, 40)
        self.assertAlmostEqual(q_plana, 100)
        a_inc, q_inc = self.c.calha(4, 10, 20, 150)
        self.assertAlmostEqual(a_inc, (4 + 4 * math.tan(20 * RAD) / 2) * 10)
        self.assertGreater(q_inc, q_plana)
        self.assertIn("R.calhas={i:ic,Tr:Trc,t:tdc,linhas:PhysisCalc.calhas(aguas,ic)}", self.pl)
        self.assertIn("card('Calhas e condutores · NBR 10844'", self.pl)

    # 9 ── cisterna mês a mês
    def test_9_cisterna_igual_no_sustainkit_e_no_planejador(self):
        dem = 4 * 160 * self.c.premissa("agua.fracao_nao_potavel") * 30.4 / 1000
        self.assertEqual(self.c.cisterna(CHUVA, 80, 0.8, dem, 0), antiga_cisterna(80, CHUVA, dem), "sem descarte, igual à conta antiga")
        com = self.c.cisterna(CHUVA, 80, 0.8, dem, self.c.premissa("chuva.descarte_inicial"))
        self.assertGreaterEqual(com[0], antiga_cisterna(80, CHUVA, dem)[0], "o descarte não pode diminuir a cisterna")
        # mesma regra de demanda e a mesma função nos dois programas
        self.assertIn("demanda:pess*perCapita*pm('agua.fracao_nao_potavel')*30.4/1000, descarte:pm('chuva.descarte_inicial')", self.sk)
        self.assertIn("const dem=(pes*PhysisCalc.premissa('agua.fracao_nao_potavel')+irr*3+pisc*5)*30.4/1000;R.chuva=PhysisCalc.cisterna(", self.pl)
        self.assertIn("descarte:S.premissas.descarte??PhysisCalc.premissa('chuva.descarte_inicial')", self.pl)
        self.assertIn("localStorage.getItem('physis.terreno.v1')", self.sk)

    # 15 ── premissas soltas
    def test_15_premissas_lidas_da_base(self):
        self.assertIn("var RETORNO=pm('esgoto.coef_retorno');", self.sk)
        self.assertIn("R.agua.resDias=PhysisCalc.premissa('agua.reserva_dias')", self.pl)
        self.assertNotIn("R.agua.res=R.agua.tot*2/1000", self.pl)

    def test_fluxo_de_residuos_sem_nome_vazio(self):
        js = (RAIZ / "sistema" / "physis-circular-mapa.js").read_text(encoding="utf-8")
        self.assertIn('grupo:(tp && tp.grupo) || "Outros"', js)
        self.assertIn('tipo:nomeTipo(r.tipo) || "Tipo não informado"', js)
        self.assertIn('rota:info.nome || r.rota || "Rota não informada"', js)

    def test_planejador_sem_botao_proprio_de_ajustes(self):
        self.assertNotIn("id:'btn-ajustes'", self.pl)
        self.assertIn("PhysisPreferencias.iniciar(", self.pl)
        self.assertIn("aviso: CONF.v.aviso === 15 ? 15 : (e.conforto || e.calma ? 8 : 4)", self.pl)


if __name__ == "__main__":
    unittest.main()
