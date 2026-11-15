"""Energia solar revista (sistema/physis-solar.js): espelho em Python das contas de energia, perdas e strings.

Protege:
1. Temperatura da célula (NOCT) e fator de temperatura conferem com a conta à mão.
2. PR calculado = produto das perdas × fator de temperatura; energia mês a mês; cascata de perdas fecha na energia entregue.
3. Dimensionamento: kWp para cobrir o consumo, módulos inteiros, relação CC/CA e aviso fora de 1,10 a 1,35.
4. Strings: Voc na mínima, Vmp na mínima e na célula quente, número em série, arranjo de strings iguais, corrente no MPPT.
5. Mesmo resultado do JavaScript num caso completo (números tirados do módulo no navegador em 15/11/2026).
6. O módulo da tela não chama a internet e mantém o contrato (telaSolar, SOLAR.calcular, SOLAR.compat).
"""
import math
import re
import unittest
from pathlib import Path

JS = Path(__file__).resolve().parents[2] / "sistema" / "physis-solar.js"
DIAS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
MOD = {"pmax": 550, "voc": 49.9, "vmp": 41.9, "isc": 14.0, "beta_voc": -0.27, "gamma_pmax": -0.35, "noct": 45, "area": 2.58, "deg": 0.55}
INV = {"pca": 5, "eta": 0.973, "vdc_max": 600, "mppt_min": 80, "mppt_max": 550, "n_mppt": 2, "imax_mppt": 16}


# ── espelho de window.SOLAR (mudou lá, muda aqui) ──
def t_celula(ta, noct, g):
    return ta + (noct - 20) / 800 * g


def f_temp(tc, gamma):
    return 1 + gamma / 100 * (tc - 25)


def strings(m, v, placas, tmin, tmax):
    b = m["beta_voc"] / 100
    tc_max = t_celula(tmax, m["noct"], 1000)
    voc_frio, vmp_frio, vmp_quente = m["voc"] * (1 + b * (tmin - 25)), m["vmp"] * (1 + b * (tmin - 25)), m["vmp"] * (1 + b * (tc_max - 25))
    n_max, n_max_mppt, n_min = math.floor(v["vdc_max"] / voc_frio), math.floor(v["mppt_max"] / vmp_frio), math.ceil(v["mppt_min"] / vmp_quente)
    n_sup, s, n, por = min(n_max, n_max_mppt), 0, 0, 0
    if n_sup >= n_min and placas > 0:
        s = math.ceil(placas / n_sup); n = max(n_min, math.ceil(placas / s))
        k = s
        while k * n_min <= placas:
            if placas % k == 0 and placas // k <= n_sup:
                s, n = k, placas // k
                break
            k += 1
        por = math.ceil(s / max(1, v["n_mppt"]))
    return {"tc_max": tc_max, "voc_frio": voc_frio, "vmp_frio": vmp_frio, "vmp_quente": vmp_quente, "n_max": n_max, "n_max_mppt": n_max_mppt,
            "n_min": n_min, "strings": s, "em_serie": n, "por_mppt": por, "corrente_ok": not (por and m["isc"] * por > v["imax_mppt"])}


def calcular(H, T, fp, consumo, cobertura, m, v, perdas, eta, g_op, deg, vida, razao, tmin, tmax):
    fixo = (1 - perdas["sombra"] / 100) * (1 - perdas["sujeira"] / 100) * (1 - perdas["mismatch"] / 100) * (1 - perdas["cabos_cc"] / 100) * eta * (1 - perdas["cabos_ca"] / 100)
    meses = []
    for i, h in enumerate(H):
        ft = f_temp(t_celula(T[i], m["noct"], g_op), m["gamma_pmax"])
        meses.append(h * fp * DIAS[i] * fixo * ft)
    rend = sum(meses)
    h_plano = sum(h * fp * DIAS[i] for i, h in enumerate(H))
    kwp_nec = consumo * cobertura / rend
    placas = math.ceil(kwp_nec * 1000 / m["pmax"] - 1e-9)
    kwp = placas * m["pmax"] / 1000
    ger = kwp * rend
    media = sum(ger * (1 - deg / 100) ** a for a in range(vida)) / vida
    f_t_medio = sum(h * fp * DIAS[i] * f_temp(t_celula(T[i], m["noct"], g_op), m["gamma_pmax"]) for i, h in enumerate(H)) / h_plano
    e, cascata = kwp * h_plano, []
    for f in (1 - perdas["sombra"] / 100, 1 - perdas["sujeira"] / 100, f_t_medio, 1 - perdas["mismatch"] / 100, 1 - perdas["cabos_cc"] / 100, eta, 1 - perdas["cabos_ca"] / 100):
        cascata.append(e * (1 - f)); e *= f
    return {"rend": rend, "pr": rend / h_plano, "placas": placas, "kwp": kwp, "ger": ger, "media": media, "pca": kwp / razao, "cascata": cascata,
            "entregue_cascata": e, "s": strings(m, v, placas, tmin, tmax)}


H = [5.78, 5.97, 5.14, 4.52, 3.68, 3.46, 3.64, 4.26, 4.57, 5.0, 5.05, 5.56]
T = [26, 26.5, 25.8, 24, 22, 21, 20.5, 21.5, 22.5, 23.5, 24.5, 25.5]
PERDAS = {"sombra": 3, "sujeira": 2, "mismatch": 1.5, "cabos_cc": 1.5, "cabos_ca": 1}
# caso completo rodado no módulo JavaScript (Edge, 15/11/2026)
JS_REF = {"rend": 1470.2178426162632, "pr": 0.8140646441078278, "placas": 15, "kwp": 8.25, "ger": 12129.297201584171, "media": 11361.521468077626,
          "pca": 6.875, "cascata": [446.9901975000004, 289.05366105000024, 1185.4090947196553, 194.67330445095533, 191.753204884191, 339.9784322596706, 122.51815355135537],
          "s": {"voc_frio": 52.99879, "vmp_frio": 44.50199, "vmp_quente": 36.8939975, "n_max": 11, "n_max_mppt": 12, "n_min": 3}}


class Contas(unittest.TestCase):
    def test_temperatura(self):
        # 25 °C ambiente, NOCT 45, 800 W/m²: Tc = 25 + 25/800·800 = 50 °C; γ −0,35: fator 1 − 0,0035·25 = 0,9125
        self.assertAlmostEqual(t_celula(25, 45, 800), 50.0)
        self.assertAlmostEqual(f_temp(50, -0.35), 0.9125)

    def test_pr_e_energia_a_mao(self):
        # 1 mês só, sem temperatura (T tal que Tc = 25): PR = 0,98·0,985·0,985·0,97·0,99 (sem sombra)
        m = dict(MOD, noct=20)                              # NOCT 20 → Tc = Ta
        r = calcular([5.0] * 12, [25] * 12, 1, 10000, 1, m, INV, dict(PERDAS, sombra=0), 0.97, 800, 0.5, 25, 1.2, 0, 40)
        pr = 0.98 * 0.985 * 0.985 * 0.97 * 0.99
        self.assertAlmostEqual(r["pr"], pr, places=12)
        self.assertAlmostEqual(r["rend"], 5.0 * 365 * pr, places=9)            # ≈ 1 680 kWh/kWp
        self.assertAlmostEqual(r["kwp"], math.ceil(10000 / r["rend"] * 1000 / 550) * 0.55)
        self.assertAlmostEqual(r["entregue_cascata"], r["ger"], places=6)      # a cascata fecha na energia entregue

    def test_strings_a_mao(self):
        # Voc a 0 °C: 49,9·(1 + 0,0027·25) = 53,268 V → 11 em série até 600 V
        s = strings(MOD, INV, 15, 0, 40)
        self.assertAlmostEqual(s["voc_frio"], 53.26825, places=5); self.assertEqual(s["n_max"], 11)
        # célula quente: 40 + 25/800·1000 = 71,25 °C; Vmp = 41,9·(1 − 0,0027·46,25) = 36,668 V → 3 em série para 80 V
        self.assertAlmostEqual(s["tc_max"], 71.25); self.assertAlmostEqual(s["vmp_quente"], 36.668, places=3); self.assertEqual(s["n_min"], 3)
        self.assertEqual((s["strings"], s["em_serie"]), (3, 5))                 # 15 = 3 × 5, strings iguais
        self.assertEqual(s["por_mppt"], 2); self.assertFalse(s["corrente_ok"])  # 2 × 14 A > 16 A
        self.assertTrue(strings(MOD, dict(INV, imax_mppt=32), 15, 0, 40)["corrente_ok"])
        self.assertEqual(strings(MOD, dict(INV, mppt_min=500, mppt_max=520), 15, 0, 40)["strings"], 0)   # janela estreita: não cabe

    def test_igual_ao_javascript(self):
        r = calcular(H, T, 1.05, 12000, 1, MOD, INV, PERDAS, 0.973, 800, 0.55, 25, 1.2, 2, 38)
        for k in ("rend", "pr", "kwp", "ger", "media", "pca"):
            self.assertAlmostEqual(r[k], JS_REF[k], delta=abs(JS_REF[k]) * 1e-9, msg=k)
        self.assertEqual(r["placas"], JS_REF["placas"])
        for a, b in zip(r["cascata"], JS_REF["cascata"]):
            self.assertAlmostEqual(a, b, delta=1e-6)
        for k, v in JS_REF["s"].items():
            self.assertAlmostEqual(r["s"][k], v, places=6, msg=k)
        self.assertEqual((r["s"]["strings"], r["s"]["em_serie"]), (3, 5))
        self.assertTrue(0.75 < r["pr"] < 0.85)


@unittest.skipUnless(JS.is_file(), "sistema/physis-solar.js ausente")
class ModuloDaTela(unittest.TestCase):
    def test_sem_internet_e_contrato(self):
        s = JS.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"https?://", s)); self.assertNotIn("</script", s.lower())
        for x in ("window.SOLAR", "window.telaSolar", "compat", "__solEventos", "<h1>Energia solar</h1>", "Metodologia e normas",
                  "NBR 16690", "NBR 16149", "NBR 16150", "NBR 16274", "14.300", "1.059/2023", "base-equipamentos"):
            self.assertIn(x, s)
        self.assertEqual(s.count("<h1>"), 1)
        for x in ("(noct - 20) / 800", "gamma / 100 * (tc - 25)", "N % k === 0"):
            self.assertIn(x, s)


if __name__ == "__main__":
    unittest.main()
