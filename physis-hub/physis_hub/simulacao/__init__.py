"""Simulações leves da Fase 1 (pedido de 15/11/2026): calor, estrutura, fluidos simplificados, terreno e
hidrologia, Monte Carlo, otimização em QUBO (clássica agora; exportação para a trilha quântica) e biogás.

Cada solver existe aqui (servidor: relatórios e testes) e em sistema/physis-simulacao.js (navegador, sem
internet), com os mesmos resultados conferidos por testes em casos comuns (sistema/simulacao-exemplos/).
Todo resultado traz método, hipóteses, premissas usadas, malha/grade e limites de validade, e o aviso de que é
pré-dimensionamento para revisão do engenheiro: nada aprova projeto sozinho. Leia docs/SIMULACAO.md.

Rotas (para o servidor.py; ver o patch de integração em docs/SIMULACAO.md): rota(caminho, corpo).
"""
from __future__ import annotations

from . import biogas, comum, estrutura, fluidos, incerteza, qubo, termica, terreno
from .comum import AVISO, FaltaDado

__all__ = ["biogas", "comum", "estrutura", "fluidos", "incerteza", "qubo", "termica", "terreno", "rota", "AVISO"]

LIMITES = {"celulas_2d": 40_000, "celulas_lbm": 20_000, "passos_lbm": 2_000, "graus_liberdade": 3_000,
           "grade_terreno": 250_000, "mc_amostras": 50_000}


def _limitar(caminho: str, c: dict) -> None:
    """Tamanho máximo por pedido: o hub é um notebook (16 GB) e o Python puro é lento; caso grande vai para a Fase 2."""
    if caminho.endswith("/termica/2d") and int(c.get("nx", 0)) * int(c.get("ny", 0)) > LIMITES["celulas_2d"]:
        raise ValueError("malha 2D grande demais para o servidor da Fase 1")
    if caminho.endswith("/fluidos/lbm") and (int(c.get("nx", 0)) * int(c.get("ny", 0)) > LIMITES["celulas_lbm"]
                                              or int(c.get("passos", 0)) > LIMITES["passos_lbm"]):
        raise ValueError("LBM grande demais para o servidor: rode no navegador (aba Simulação)")
    if caminho.startswith("/api/simulacao/terreno") and int(c.get("grade", {}).get("nx", 0)) * int(c.get("grade", {}).get("ny", 0)) > LIMITES["grade_terreno"]:
        raise ValueError("grade de terreno grande demais")
    if caminho.endswith("/incerteza") and int(c.get("n", 0) or 0) > LIMITES["mc_amostras"]:
        raise ValueError("amostras demais")


def rota(caminho: str, c: dict, contexto: dict | None = None) -> tuple[int, dict]:
    """POST /api/simulacao/<parte>. contexto: {temperatura_mensal, local} vindo de biogas.clima_do_local (servidor).
    Devolve (status HTTP, corpo). Erros de dado faltando voltam 422 com o [MARCADOR]."""
    try:
        _limitar(caminho, c)
        p = caminho[len("/api/simulacao/"):]
        if p.startswith("terreno/") and not c.get("grade") and c.get("geometria"):
            c = dict(c, grade=terreno.grade_da_geometria(c["geometria"]))     # contrato physis-geometria-lugar/1
        if p == "termica/u":
            return 200, termica.u_composicao(c["composicao"]) if c.get("composicao") else termica.u_valor(c["camadas"], c.get("tipo", "parede"))
        if p == "termica/1d":
            return 200, termica.transiente_1d(c)
        if p == "termica/2d":
            return 200, termica.placa_2d(c)
        if p == "termica/envoltoria":
            return 200, termica.perda_envoltoria(c["itens"], c["ti"], c["te"])
        if p == "estrutura/portico":
            r = estrutura.portico(c)
            if c.get("verificar"):
                r["verificacao"] = estrutura.verificar(r, c.get("apoio_flambagem", "biapoiada"))
            return 200, r
        if p == "estrutura/cst":
            return 200, estrutura.cst(c)
        if p == "estrutura/euler":
            return 200, estrutura.euler(c["E"], c["I"], c["L"], c.get("apoio", "biapoiada"), c.get("K"))
        if p == "fluidos/ventilacao":
            return 200, fluidos.ventilacao_natural(c)
        if p == "fluidos/lbm":
            return 200, fluidos.lbm(c)
        if p == "fluidos/eolica":
            return 200, fluidos.eolica_serie(c)
        if p == "terreno/escoamento":
            return 200, terreno.escoamento(c["grade"])
        if p == "terreno/declividade":
            return 200, terreno.declividade_aspecto(c["grade"])
        if p == "terreno/scs":
            return 200, terreno.escoamento_scs(c["grade"], c["chuva_mm"], c["usos"], c["grupo"])
        if p == "terreno/usle":
            return 200, terreno.usle(c["grade"], c.get("R"), c.get("K"), c.get("C"), c.get("P"), c.get("comprimento_m"))
        if p == "terreno/visada":
            return 200, terreno.visada(c["grade"], c["i"], c["j"], c.get("altura_obs", 1.6), c.get("altura_alvo", 0.0))
        if p == "incerteza":
            return 200, incerteza.monte_carlo(c["entradas"], c["modelo"], c.get("n"), c.get("semente"))
        if p in ("qubo/paineis", "qubo/rota", "qubo/topologia"):
            r = getattr(qubo, p.split("/")[1])(c)
            r["exportacao"] = qubo.exportar(r["Q"], p.split("/")[1], r["solucao"])
            return 200, r
        if p == "biogas":
            c = dict(c)
            if c.get("regime") == "ambiente" and not c.get("temperatura_mensal") and contexto:
                c["temperatura_mensal"] = contexto.get("temperatura_mensal")
            r = biogas.simular(c)
            if contexto and contexto.get("local"):
                r["local"] = contexto["local"]
            return 200, r
        return 404, {"erro": "simulação desconhecida"}
    except FaltaDado as e:
        return 422, {"erro": str(e), "marcador": True}
    except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError) as e:
        return 400, {"erro": f"entrada inválida: {e}"}
