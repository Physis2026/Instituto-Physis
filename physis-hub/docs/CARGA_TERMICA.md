# Carga térmica

Arquivos: `sistema/physis-cargatermica.js` (tela e cálculo), `physis-hub/physis_hub/cargatermica.py` (espelho em Python, mesmas fórmulas),
`physis-hub/tests/test_cargatermica.py` (casos feitos à mão). Bases usadas: `sistema/physis-materiais.json` (U e atraso das paredes e
coberturas) e `sistema/physis-equipamentos.json` (equipamento sugerido e eficiência).

Redação própria. As normas são citadas só pelo número e pela seção; nenhum texto delas é reproduzido. Todo número de tabela
pública lembrado de memória está marcado como **verificar** nas bases.

## O que a tela faz

Para cada ambiente, calcula a carga de resfriamento de verão, sensível e latente, hora a hora das 8 às 18 h (hora solar), acha o pico,
aplica o fator de segurança e mostra W, BTU/h e TR. Soma o conjunto hora a hora para achar o pico simultâneo (que dimensiona sistema central)
e a soma dos picos (que dimensiona split por ambiente). Mostra de onde vem o calor (gráfico e tabela), compara split, VRF e chiller, sugere
o equipamento da base e estima a energia anual e o custo.

## Contrato

- `window.CARGA_TERMICA.calcular(ambientes, clima, opcoes)` — função pura. Devolve `{clima, opcoes, ambientes[], total, sistema, avisos}`.
- `window.telaCargaTermica(estado?)` — HTML com um único `<h2>` ("Carga térmica"), subseções em `<h3>`, tabelas com `<caption>` e
  `<th scope>`, todo campo com `<label for>`. Sem `estado`, lê e grava `calcLer("cargatermica")` / `calcGravar` (mesmo padrão do AVAC).
- Globais usadas só ao desenhar: `esc`, `n2`, `numBr`, `brl`, `el`, `desenhar` (e `calcLer`/`calcGravar` se existirem).
- Eventos por atributos `data-ct-k` (campo), `data-ct-t` (tipo: `s` texto, `n` número, `nn` número que pode ficar vazio) e `data-ct-acao`
  (`add-amb`, `del-amb:i`, `add-sup:i`, `del-sup:i:j`, `reset`). Não conflita com os `data-avac-*` do AVAC.
- Base de equipamentos: `opcoes.equipamentos` ou `<script type="application/json" id="base-equipamentos">` no painel. Sem base, usa
  eficiências-padrão (`DADOS.sistemas_padrao`) e avisa na tela.

Entrada de um ambiente:

```
{ nome, area (m²), pe_direito (m), pessoas, atividade, uso, iluminacao_wm2, equipamentos_wm2, equipamentos_w,
  infiltracao_ach, ar_externo_lpp, ar_externo_lpm2, ar_externo_ls, ini, fim,
  superficies: [ { tipo: parede|cobertura|vidro|adjacente|piso_exterior|piso_solo, orient: N|NE|L|SE|S|SO|O|NO|H|graus,
                   area, material, u, atraso, amortecimento, absortancia, cor, sol (false = sombreada), fs, sombra, fator } ] }
```

Campo vazio usa o padrão (cidade, material ou `DADOS.padroes`). Clima: `{cidade, lat, alt, tbs, tbu, dr, w (g/kg) ou ur (%), tint, urint}`.
Opções: `{mes, declinacao, horas[], fs, horas_ano, fator_carga, tarifa, ar_externo: false, equipamentos}`.

## Método, passo a passo, com a referência de cada conta

A NBR 16401-1:2008 (seção de cálculo de carga térmica) pede que a carga seja calculada a partir das condições externas de projeto da
localidade, das condições internas de conforto, das trocas pela envoltória (condução e insolação, considerando o armazenamento
nas massas), das cargas internas e do ar externo, verificando a hora de maior carga. Ela admite métodos reconhecidos (a ASHRAE é a
referência usual). O que segue é um método simplificado nesse caminho.

| # | Conta | Fórmula usada | Referência |
|---|---|---|---|
| 1 | Pressão atmosférica pela altitude | p = 101,325·(1 − 2,25577·10⁻⁵·z)^5,2559 kPa | ASHRAE Fundamentals, cap. 1 (psicrometria) |
| 2 | Pressão de saturação | pws = 0,61094·e^(17,625·T/(T+243,04)) kPa (Magnus, igual ao `physis-avac.js`) | idem |
| 3 | Umidade absoluta externa | por TBS e TBU: w = [(2501 − 2,326·TBU)·ws(TBU) − 1,006·(TBS − TBU)] / (2501 + 1,86·TBS − 4,186·TBU); ou por UR | ASHRAE Fundamentals, cap. 1 |
| 4 | Umidade interna | w = 0,621945·φ·pws/(p − φ·pws); padrão 24 °C e 50 % | faixa de conforto de verão da NBR 16401-2:2008 (parâmetros de conforto) |
| 5 | Condições externas de projeto | TBS (frequência 0,4 %), TBU coincidente e amplitude diária por cidade (19 capitais na tabela `DADOS.cidades`) | NBR 16401-1:2008, anexo com dados climáticos de cidades (origem ASHRAE). **verificar** |
| 6 | Temperatura externa hora a hora | T(h) = TBS − amplitude × fração(h) | ASHRAE Fundamentals, cap. 14 (perfil de amplitude diária) |
| 7 | Posição do sol | sen β = cos L·cos δ·cos H + sen L·sen δ; azimute por atan2; δ = 23,45°·sen(360·(284+n)/365), dia 21 do mês | geometria solar (ASHRAE Fundamentals, cap. 14) |
| 8 | Irradiância de céu claro | I_DN = A·e^(−B/sen β); difusa = C·I_DN·(1+cos Σ)/2; refletida = ρ_solo·I_DN·(C+sen β)·(1−cos Σ)/2, ρ_solo 0,2 | modelo de céu claro da ASHRAE (A, B, C por mês). **verificar**: as edições novas usam o modelo tau |
| 9 | Incidência | parede: cos θ = cos β·cos(azimute sol − azimute parede); cobertura: cos θ = sen β | idem |
| 10 | Paredes e coberturas ao sol | T sol-ar = T(h) + α·I/h_e − ε·ΔR/h_e (h_e 17 W/m²K; 3,9 K só na horizontal) | ASHRAE Fundamentals, cap. 18 (temperatura sol-ar) |
| 11 | Massa térmica (atraso e amortecimento) | Q(h) = U·A·[(T̄sa − Ti) + f·(Tsa(h − φ) − T̄sa)], com T̄sa a média de 24 h | método de admitância / fator de decremento (literatura de conforto); φ pela NBR 15220-2 |
| 12 | U, capacidade e atraso das camadas | R = Σe/λ + Rsi + Rse; CT = Σ e·ρ·c; atraso pelas fórmulas de camadas (B0, B1, B2) | NBR 15220-2 (método de cálculo) — ver `MATERIAIS.md` |
| 13 | Amortecimento | f = e^(−2π·φ/24) | onda periódica em placa homogênea; premissa Physis |
| 14 | Divisa com ambiente sem ar | Q = U·A·fator·(T(h) − Ti), fator 0,5 | premissa Physis |
| 15 | Piso sobre o solo | 0 (no verão o solo costuma retirar calor) | simplificação conservadora usual |
| 16 | Vidros, insolação | Q = A·FS·sombreamento·I_total(h) (sem curva de ângulo do fator solar) | ASHRAE Fundamentals, cap. 15 (ganho solar por fator solar) |
| 17 | Vidros, condução | Q = U_vidro·A·(T(h) − Ti) | idem |
| 18 | Pessoas | sensível e latente por atividade (W/pessoa), só nas horas de ocupação | ASHRAE Fundamentals, cap. 18 (tabela de calor por pessoa); anexo de cargas internas da NBR 16401-1. **verificar** |
| 19 | Iluminação e equipamentos | W/m² × área (+ W extras), só nas horas de ocupação | NBR 16401-1 (cargas internas); valores por projeto |
| 20 | Infiltração | Q = trocas/h × volume / 3,6 (L/s); sensível 1,23·Q·ΔT; latente 3010·Q·Δw | ASHRAE Fundamentals, cap. 16 e 18 (ar a 1,2 kg/m³) |
| 21 | Ar externo | Q = Rp·pessoas + Ra·área (L/s); mesmas fórmulas de sensível e latente, só ocupado | lógica da NBR 16401-3:2008 (vazão eficaz por pessoa e por área, tabela por tipo de local). **verificar** os valores |
| 22 | Pico do ambiente | maior total (sensível + latente) entre as horas | NBR 16401-1 (verificar a hora de maior carga) |
| 23 | Pico simultâneo | maior soma dos ambientes na mesma hora; diversidade = simultâneo / soma dos picos | prática usual |
| 24 | Fator de segurança | projeto = pico × FS (padrão 1,10) | premissa Physis |
| 25 | Unidades | BTU/h = W × 3,412142; TR = W / 3516,853 | definição |
| 26 | Escolha do sistema | split se cada ambiente ≤ 60.000 BTU/h e total ≤ 20 TR; VRF de 3 a 150 TR e ≥ 3 ambientes (ideal ≥ 4 e ≥ 6 TR); chiller ≥ 40 TR (ideal ≥ 100 TR; a água ≥ 150 TR) | premissa Physis, `DADOS.regras_sistema` |
| 27 | Equipamento | split: menor capacidade nominal ≥ BTU/h do ambiente, preferindo hi-wall, depois cassete e piso-teto; VRF e chiller: faixa da base que contém a carga | base de equipamentos |
| 28 | Energia anual | kWh/ano = pico simultâneo (kW térmico, sem FS) × horas/ano × fator de carga ÷ eficiência sazonal × auxiliares | premissa Physis (2600 h, fator 0,5). Split: IDRS ponderado pela carga; VRF: IEER; chiller: IPLV |
| 29 | Custo | kWh/ano × tarifa (sem tarifa, fica em branco: nenhum preço é inventado) | — |

Limitações conhecidas (estão escritas na tela):

- Instantâneo para insolação de vidros e cargas internas: não aplica fator de armazenamento da parte radiante (RTS/CLF). Tende a
  superestimar o pico de ambiente envidraçado e leve.
- Só um mês de sol por cálculo (padrão: janeiro no hemisfério sul). Fachada norte recebe mais sol no inverno: rodar também abril a agosto.
- Fator solar do vidro constante com o ângulo; sem sombreamento geométrico de brises (use o campo "sombra").
- Umidade externa constante ao longo do dia.
- Estudo preliminar; projeto executivo deve usar simulação horária (EnergyPlus ou equivalente).

## Casos de conferência

Estão no docstring de `tests/test_cargatermica.py`, com as contas à mão: (A) cargas internas, ar externo, infiltração e parede sem sol;
(B) cobertura escura ao meio-dia no equador; (C) vidro a leste às 8 h; (D) parede com massa e atraso; (E) psicrometria 32/24 °C.
Também foi conferido num navegador que o `.js` dá o mesmo resultado do `.py` em três cenários com materiais reais (diferença relativa
de 10⁻¹⁶) e que a tela tem um `<h2>`, nenhum campo sem rótulo e nenhum id repetido.

## Como ligar no painel (quem cuida de `painel.html`, `physis-avac.js` e `embutir_bases.py`)

Recomendado: sub-aba dentro do AVAC (o AVAC já tem `<h1>` e cada sub-aba desenha `<h2>`).

1. `sistema/physis-avac.js`, constante `SUBS` (linha ≈ 376): acrescentar `["carga", "Carga térmica"]` logo depois de `["tip", "Tipologias e ambientes"]`.
2. `sistema/physis-avac.js`, função `telaAvac` (linha ≈ 590), no objeto de telas: acrescentar
   `carga: () => typeof telaCargaTermica === "function" ? telaCargaTermica() : "<p class=\"t2\">Módulo de carga térmica não carregado.</p>"`.
3. `ferramentas/embutir_bases.py`: em `BASES`, acrescentar `"base-equipamentos": RAIZ / "sistema" / "physis-equipamentos.json"`
   (≈ 170 kB compacto; `"base-materiais"` só se a tela de materiais for usar); em `MODULOS`, acrescentar
   `"mod-cargatermica": RAIZ / "sistema" / "physis-cargatermica.js"`. Rodar `python ferramentas/embutir_bases.py` e depois os testes
   (`test_bases` confere a cópia embutida).
4. Opcional, depois: no AVAC, um botão "usar a carga térmica" que grava em `e.ac.amb[i].override` o BTU/h de projeto do ambiente de
   mesmo nome (troca a regra de m²/TR pela carga calculada).

Alternativa: entrada própria em `TELAS` do painel chamando `telaCargaTermica()` — nesse caso a tela precisa de um `<h1>` em volta, porque a função devolve só `<h2>`.

## O que falta

- Conferir na norma e nas tabelas os valores marcados **verificar**: cidades, pessoas, ar externo, céu claro, materiais de bioconstrução.
- Fator de armazenamento (RTS) para vidros e cargas radiantes; varredura de meses.
- Ligação com o dimensionamento do AVAC (passo 4 acima) e com o quadro elétrico (potência elétrica por equipamento escolhido).
- Tarifa de energia vem do projeto; não há valor-padrão.
