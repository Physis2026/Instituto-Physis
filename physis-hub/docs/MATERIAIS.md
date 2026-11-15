# Base de materiais

Arquivo: `sistema/physis-materiais.json`. Testes: `physis-hub/tests/test_materiais.py`. Cálculo: `nbr15220()` em
`physis-hub/physis_hub/cargatermica.py`.

## O que tem

- **78 materiais** em 10 grupos (concreto e cimentícios, cerâmicos, vidros, metais, madeiras e fibras, isolantes, terra e bioconstrução,
  pedras, plásticos, acabamentos). Bioconstrução: taipa (natural e estabilizada), adobe, BTC/solo-cimento, cob, terra-palha, pau a pique,
  superadobe, reboco de terra, cal, bambu (colmo e laminado), madeira certificada, cânhamo e cal, fardo de palha, sapê, cortiça, fibra de
  coco, fibra de madeira, celulose, lã de ovelha, substrato de telhado verde.
- Para cada material: densidade (kg/m³), condutividade (W/m·K), calor específico (J/kg·K), espessura típica, U da camada sozinha como
  parede (quando faz sentido), carbono incorporado (kgCO₂e/kg, berço ao portão, com fonte) e custo.
- **26 composições** típicas de parede e cobertura, com U, capacidade térmica, atraso, amortecimento, massa e carbono por m², e a
  avaliação frente à NBR 15575 (procedimento simplificado) e às diretrizes da NBR 15220-3.

## Custo

A regra 1 do `CLAUDE.md` proíbe preço inventado. Todos os custos estão com `valor: null` e fonte `[MARCADOR]`. Para preencher:
SINAPI (Caixa) do estado e do mês do orçamento, ou cotação; gravar `valor`, `unidade`, `data` e `fonte`.
Endereço do SINAPI: https://www.caixa.gov.br/poder-publico/modernizacao-gestao/sinapi

## Carbono incorporado

Valores de ordem de grandeza do ICE v3.0 (Circular Ecology / Universidade de Bath, 2019; https://circularecology.com/embodied-carbon-footprint-database.html),
todos marcados para conferência. Para materiais brasileiros (cimento, concreto, blocos, cerâmica), preferir o SIDAC
(Sistema de Informação do Desempenho Ambiental da Construção; https://sidac.org.br) ou a EPD do fabricante: o cimento nacional costuma
ficar abaixo da média mundial pelas adições. Carbono biogênico de madeira, palha e cânhamo **não** foi descontado.

## Cálculo pela NBR 15220-2 (em palavras próprias)

A NBR 15220-2 dá o método para calcular, em componentes de camadas, a resistência e a transmitância, a capacidade térmica, o atraso
térmico e o fator solar de elementos opacos. O que está implementado:

| Grandeza | Fórmula | Observação |
|---|---|---|
| Resistência da camada | R = e/λ (m²K/W) | câmara de ar entra como resistência fixa (0,21 m²K/W, câmara não ventilada > 5 cm, fluxo descendente, superfícies comuns) |
| Resistência total | R_T = Rsi + ΣR + Rse | parede: Rsi 0,13 e Rse 0,04; cobertura no verão (fluxo para baixo): Rsi 0,17 e Rse 0,04 |
| Transmitância | U = 1/R_T (W/m²K) | |
| Capacidade térmica | CT = Σ e·ρ·c (kJ/m²K) | c em kJ/kg·K |
| Atraso, uma camada | φ = 1,382·e·√(ρ·c / (3,6·λ)) (h) | |
| Atraso, várias camadas | φ = 1,382·R_t·√(B1 + B2); B0 = CT − CT_ext; B1 = 0,226·B0/R_t; B2 = 0,205·(λρc)_ext/R_t·(R_ext − (R_t − R_ext)/10), B2 negativo vira 0 | R_t sem as resistências superficiais; "ext" = camada externa |
| Amortecimento (para a carga térmica) | f = e^(−2π·φ/24) | premissa Physis (onda periódica em placa homogênea) |

Componentes com furos (tijolo 6 furos, bloco de concreto) e telha cerâmica com forro de madeira **não** são camadas homogêneas: usam valores
tabelados (anexo de paredes e coberturas da NBR 15220-3), marcados `tabelado` e "verificar".

Conferência à mão (no teste): concreto 10 cm → U 4,40 W/m²K, CT 230 kJ/m²K, φ 2,6 h (a tabela da NBR 15220-3 traz 4,40 / 240 / 2,7).

## Comparação com as normas de desempenho

- **NBR 15575-4 e 15575-5 (procedimento simplificado)**: limites de U de paredes externas por zona bioclimática e absortância
  (e capacidade térmica mínima nas zonas 1 a 7), e de U de coberturas por zona e absortância. Os valores usados estão em
  `limites.nbr15575_parede` e `limites.nbr15575_cobertura` — lembrados da edição de 2021, **verificar**. Se a parede ou a cobertura
  não passa, o caminho é o procedimento de simulação da NBR 15575-1.
- **NBR 15220-3 (diretrizes por zona)**: classifica a parede em leve, leve refletora ou pesada (limites de U e de atraso) e a cobertura em
  leve isolada, leve refletora ou pesada, e diz em que zonas cada uma é recomendada. O fator solar de opacos (que depende da cor) não foi
  avaliado. A NBR 15220 está em revisão — conferir a edição vigente (`physis-premissas.json` já pede isso).

Resultados que vale olhar: taipa 30 cm dá U 2,26 (um pouco acima de 2,2) — não fecha "pesada" pela NBR 15220-3 apesar do atraso de 8,6 h;
adobe 25 cm, cob, superadobe, terra-palha, fardo de palha e cânhamo-cal fecham "pesada"; concreto 10 cm, telha metálica e fibrocimento sem forro
não atendem o simplificado da NBR 15575 em nenhuma zona.

## Ligação com a carga térmica

Os materiais de parede e cobertura de `physis-cargatermica.js` (bloco `DADOS.materiais`) têm o campo `composicao`; o U e o atraso
vêm da composição de mesmo nome (o teste `test_carga_termica_usa_as_composicoes` reprova se divergirem). Para mudar um material:
editar a composição aqui, recalcular (o teste mostra o valor novo) e atualizar o mesmo bloco no `.js` e no `.py`
(os dois são iguais; `test_dados_iguais_no_js_e_no_py` confere).

## Fontes

- ABNT NBR 15220-2 (propriedades e método), NBR 15220-3 (zonas e diretrizes), NBR 15575-1/4/5:2021 (desempenho) — citadas só por número e seção.
- Terra crua: Minke, *Building with Earth*; Houben e Guillaud, *Earth Construction*; NBR 8491 (tijolo de solo-cimento); NBR 16828-1 (bambu).
- ICE v3.0 e SIDAC (carbono). SINAPI (custo).
