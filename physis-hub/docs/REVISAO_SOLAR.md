# Revisão da conta solar (15/11/2026)

Arquivos: `sistema/physis-solar.js` (tela e conta), `physis-hub/tests/test_solar.py` (espelho Python, conta à mão,
e o mesmo caso completo rodado no JavaScript). A tela atual (`telaSolar`/`solarCalc` em `painel.html`) não foi mexida;
o módulo novo a substitui quando ligado (passos abaixo).

## O que a tela atual faz e o que muda

| Ponto | Hoje (painel) | Novo (physis-solar.js) |
|---|---|---|
| Rendimento global (PR) | 0,78 fixo, digitável | Calculado mês a mês: sombra × sujeira × temperatura × descasamento × cabos CC × inversor × cabos CA |
| Temperatura | não entra | Célula pelo NOCT: Tc = Ta + (NOCT − 20)/800·G; perda γ(Pmax)·(Tc − 25); Ta mensal da base NASA (camada temperatura) ou digitada |
| Plano do telhado | horizontal | Fator do plano (1 = horizontal; valor do Planejador) |
| Inversor | não dimensiona | P CA = kWp ÷ relação alvo (1,2); aviso fora de 1,10–1,35 |
| Strings e MPPT | não confere | Voc na mínima × tensão máxima; Vmp na mínima × topo do MPPT; Vmp na célula quente × piso do MPPT; Isc das strings em paralelo × corrente do MPPT; arranjo de strings iguais |
| Degradação | não entra | Taxa anual do módulo; média na vida útil; no retorno reduz o reajuste: (1 + reajuste)(1 − degradação) − 1 |
| Equipamento | só a potência da placa | Módulo e inversor genéricos (marcados Verificar); coeficiente de Pmax, degradação, eficiência europeia e janela do MPPT vêm de `sistema/physis-equipamentos.json` quando embutido como `<script id="base-equipamentos">` |
| Perdas visíveis | não | Cascata em kWh/ano com gráfico e tabela |
| Retorno | economia simples | analiseInvest (simples, descontado, VPL, TIR) |

Conferência: caso completo (H de Petrópolis, T mensal, fator do plano 1,05, 12.000 kWh/ano, perdas 3/2/1,5/1,5/1 %,
η 97,3 %) → 15 módulos de 550 W, 8,25 kWp, 1.470 kWh/kWp, PR 81,4 %, 12.129 kWh no 1º ano; strings 3 × 5;
aviso de corrente (2 strings de 14 A num MPPT de 16 A). JavaScript e Python iguais até a 9ª casa.

## Cuidados e limites

- Temperatura média mensal inclui a noite (subestima o calor do meio-dia); a irradiância de operação de 800 W/m² compensa em parte. Medição local ou base horária é melhor.
- Corte no pico (clipping) com relação CC/CA alta não entra na conta mensal.
- Vmp usa o coeficiente de Voc (aproximação comum); a folha de dados pode ter o coeficiente de Vmp.
- Os números elétricos dos módulos e inversores genéricos (Voc, Vmp, Isc, NOCT, tensão máxima, corrente do MPPT) são típicos de folha de dados: **verificar** com o modelo.
- Perdas padrão (sujeira 2 %, descasamento 1,5 %, cabos CC 1,5 %, CA 1 %) são valores de partida; o projeto troca.

## Normas (redação própria; também na seção "Metodologia e normas" da tela)

- ABNT NBR 16690:2019 — projeto elétrico do arranjo: tensão máxima com a temperatura mínima, condutores e proteções pela corrente de curto-circuito, seccionamento, aterramento.
- ABNT NBR 16149:2013 (interface com a rede) e NBR 16150:2013 (ensaios da interface); NBR IEC 62116 (anti-ilhamento).
- ABNT NBR 16274:2014 — comissionamento, ensaios (inspeção, curva I-V, isolamento) e documentação.
- ABNT NBR 5410 e NBR 5419.
- Lei 14.300/2022 (micro e minigeração, compensação e transição da cobrança do uso da rede); ANEEL REN 1.059/2023 (regulamenta); PRODIST Módulo 3.
- Inmetro: registro de módulos e inversores (portaria vigente).

## Como ligar (quem cuida do painel.html)

1. `ferramentas/embutir_bases.py`: acrescentar `"mod-solar": RAIZ / "sistema" / "physis-solar.js"` em `MODULOS` (e, se quiser os dados da base, `"base-equipamentos": RAIZ / "sistema" / "physis-equipamentos.json"` em `BASES`).
2. Em `painel.html`: apagar a função `telaSolar()` antiga (uma declaração `function telaSolar` no script principal sobrescreve a do módulo) e trocar o corpo de `solarCalc()` por `return window.SOLAR ? SOLAR.compat() : { … conta antiga … }` — Carbono, Custos e o ranking de investimentos leem os mesmos campos.
3. `TELAS.solar` continua `telaSolar`.
4. Rodar `embutir_bases.py` e os testes.

## Planta solar dentro da aba (15/11/2026)

A aba Energia solar tem duas partes: **Dimensionamento** (a de sempre) e **Planta solar (BIM)** (em desenvolvimento,
com selo): arranjo das placas, carta solar, curva do dia, strings e fator de potência, vindos do Mapeamento
(`sistema/physis-mapeamento.js`, docs/MAPEAMENTO.md). Quando a planta é enviada, o Dimensionamento usa o sistema da planta
e mostra uma geração só, com a fonte; a opção "Dimensionar pelo consumo" volta ao cálculo pelo consumo.
