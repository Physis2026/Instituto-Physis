#!/usr/bin/env python3
"""Bot testador do Physis 3D: varre combinações de modelagem no validador do fatiador e grava um relatório
JSON (base completa e consistente antes de enviar a parceiros). Sem rede, sem PrusaSlicer.

    python ferramentas/bot_auditoria_3d.py [--saida relatorio_auditoria_3d.json]
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "servicos" / "fatiador"))
from physis_fatiador.servidor import montar_ini, validar_cfg  # noqa: E402

GRADE = {
    "bico_mm": [0.25, 0.4, 0.6, 0.8], "altura_camada": [0.08, 0.2, 0.3, 0.5], "largura_linha": [0.3, 0.45, 0.9],
    "paredes": [0, 1, 2, 3], "camadas_topo": [0, 3, 5], "comp_xy": [0, -0.1, 0.25], "costura": ["alinhada", "traseira"],
    "pele_felpuda": ["nenhuma", "externa"], "pele_espessura": [0.2, 0.5], "pele_dist": [0.3, 0.8],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default="relatorio_auditoria_3d.json")
    a = ap.parse_args()
    chaves = list(GRADE)
    total, ok_sem_aviso, erros, avisos, exemplos = 0, 0, Counter(), Counter(), {}
    for valores in itertools.product(*GRADE.values()):
        cfg = dict(zip(chaves, valores))
        total += 1
        try:
            montar_ini(cfg)
            av = validar_cfg(cfg)
        except ValueError as e:
            erros[str(e)] += 1
            exemplos.setdefault("erro: " + str(e), cfg)
            continue
        if not av:
            ok_sem_aviso += 1
        for x in av:
            avisos[x] += 1
            exemplos.setdefault("aviso: " + x, cfg)
    rel = {"combinacoes": total, "aprovadas_sem_aviso": ok_sem_aviso, "recusadas": sum(erros.values()),
           "erros": dict(erros.most_common()), "avisos": dict(avisos.most_common()), "exemplos": exemplos}
    Path(a.saida).write_text(json.dumps(rel, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{total} combinações: {ok_sem_aviso} sem aviso, {rel['recusadas']} recusadas; relatório em {a.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
