# Modelos dos documentos automáticos

Modelos de partida. Os modelos reais que a equipe mandar ficam no servidor, na pasta de `PHYSIS_MODELOS_PASTA`,
com os mesmos nomes; lá eles valem antes destes. Pode ser `.odt` (LibreOffice) ou `.md`.

| Pasta | O que é |
|---|---|
| `documentos/` | proposta, contrato, nf (dados da nota), consultoria |
| `relatorios/` | um modelo por módulo, mais `_capa` e `_fecho` |
| `manual/comum.md` | a parte do manual que toda compra leva |
| `manual/modulos/` | a parte de cada módulo no manual |

Marcações (as mesmas dos sites):

- `{{campo}}` — o sistema preenche (ex.: `{{cliente.nome}}`, `{{pedido.total}}`). Sem dado, vira `[MARCADOR: campo]`.
- `[MARCADOR: o que falta]` — a pessoa completa antes de aprovar.

No `.odt`, escreva a marcação de uma vez, sem mudar a formatação no meio (senão o sistema não a encontra).
Ver `docs/DOCUMENTOS_AUTOMATICOS.md`.
