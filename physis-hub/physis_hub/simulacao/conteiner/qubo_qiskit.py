#!/usr/bin/env python3
"""Adaptador da trilha quântica (P&D) — roda SÓ dentro de um contêiner Linux com Qiskit; o hub nunca importa este
arquivo nem o qiskit (o teste tests/test_simulacao.py confere).

Lê o JSON "physis-qubo/1" gravado por physis_hub.simulacao.qubo.exportar(), monta o QuadraticProgram, resolve
com o autovalor mínimo exato (NumPyMinimumEigensolver, no simulador) e, se pedido, com QAOA no simulador Aer, e
compara a energia com a solução clássica que veio no JSON. Sai com código 1 se não bater.

    docker run --rm -v "$PWD:/dados" physis/qubo-qiskit python qubo_qiskit.py /dados/problema.json [--qaoa]

Aviso: pesquisa. Cabem ~20 a 30 variáveis em simulador; o clássico resolve o mesmo na hora. Nunca usar em
relatório nem certificação. Licenças: Qiskit, Qiskit Aer e qiskit-optimization são Apache-2.0.
"""
from __future__ import annotations

import json
import sys


def energia(d: dict, x: list) -> float:
    e = d["offset"] + sum(h for h, xi in zip(d["linear"], x) if xi)
    return e + sum(w for i, j, w in d["quadratico"] if x[i] and x[j])


def main(argv: list) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    d = json.loads(open(argv[1], encoding="utf-8").read())
    if d.get("formato") != "physis-qubo/1":
        print("formato desconhecido")
        return 2
    # imports só aqui, dentro do contêiner
    from qiskit_optimization import QuadraticProgram
    from qiskit_optimization.algorithms import MinimumEigenOptimizer
    from qiskit_algorithms import NumPyMinimumEigensolver

    qp = QuadraticProgram("physis")
    for nome in d["nomes"]:
        qp.binary_var(nome)
    quad = {(d["nomes"][i], d["nomes"][j]): w for i, j, w in d["quadratico"]}
    qp.minimize(constant=d["offset"], linear=dict(zip(d["nomes"], d["linear"])), quadratic=quad)
    res = MinimumEigenOptimizer(NumPyMinimumEigensolver()).solve(qp)
    x = [int(round(v)) for v in res.x]
    saida = {"problema": d.get("problema"), "x_exato_quantico": x, "energia": energia(d, x)}
    if "--qaoa" in argv:
        from qiskit_algorithms import QAOA
        from qiskit_algorithms.optimizers import COBYLA
        from qiskit_aer.primitives import Sampler
        rq = MinimumEigenOptimizer(QAOA(sampler=Sampler(), optimizer=COBYLA(maxiter=200), reps=2)).solve(qp)
        xq = [int(round(v)) for v in rq.x]
        saida.update({"x_qaoa": xq, "energia_qaoa": energia(d, xq)})
    cl = d.get("solucao_classica") or {}
    saida["energia_classica"] = cl.get("energia")
    ok = cl.get("energia") is None or abs(saida["energia"] - cl["energia"]) < 1e-6
    if "energia_qaoa" in saida and cl.get("energia") is not None:
        saida["qaoa_igual_ao_classico"] = abs(saida["energia_qaoa"] - cl["energia"]) < 1e-6
    saida["igual_ao_classico"] = ok
    saida["aviso"] = d.get("aviso")
    print(json.dumps(saida, ensure_ascii=False, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
