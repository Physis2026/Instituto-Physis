# Base de equipamentos

Arquivo: `sistema/physis-equipamentos.json`. Testes: `physis-hub/tests/test_equipamentos.py`.
Importadores: `ferramentas/importar_cec.py` e `ferramentas/importar_inmetro.py`.

## O que tem (versão 1, 15/11/2026)

203 itens por **classe genérica** (sem modelo inventado), em 16 categorias:

| Categoria | Itens | Indicador de eficiência |
|---|---|---|
| ar-condicionado (split hi-wall, convencional, cassete, piso-teto, dutado, janela, multi-split, VRF, chillers a ar e a água, self-contained, bombas de calor de piscina e de água quente) | 39 | IDRS (split), COP + sazonal (IEER ou IPLV) |
| ventiladores e exaustores (inclui ventilador de teto e recuperador ERV) | 12 | % (rendimento total); teto em (m³/min)/W |
| filtros de ar (G3 a F9, H13, H14, carvão) | 10 | % na fração ePM da ISO 16890 |
| bombas (centrífuga, periférica, submersa, drenagem, solar, circuladora) | 12 | % (rendimento hidráulico) |
| motores (IE2, IE3, IE4 de 0,75 a 37 kW, 4 polos, 60 Hz) | 18 | η (fração) |
| módulos fotovoltaicos (PERC, TOPCon, HJT, contato traseiro, CdTe) | 7 | % + coeficiente de temperatura |
| inversores (string mono e tri, micro, híbrido, off-grid) | 10 | % (europeia) + faixa MPPT |
| baterias (LFP, Li-NMC, chumbo AGM, GEL, OPzS, estacionária) | 8 | % ida e volta + ciclos + DoD |
| controladores de carga (PWM, MPPT) | 5 | % |
| sensores (solo, pH, turbidez, temperatura/umidade, vazão, nível, corrente, energia, CO₂, PM, condutividade) | 22 | `desempenho.exatidao` |
| componentes de quadro (disjuntores, DR, DPS, contator, relés, fontes) | 17 | `desempenho` (fontes em %) |
| automação (CLP, ESP32, LoRa, relés, RS-485, IHM, servidor local) | 11 | `desempenho` |
| esgoto e saneamento (tanque séptico, filtro anaeróbio, wetlands, BET, biodigestor, UASB, ETE compacta, círculo de bananeiras) | 11 | % de remoção de DBO5 |
| biogás (tubular, indiano, chinês, substratos, gerador) | 8 | m³ de biogás por kg de sólidos voláteis |
| aquecimento solar de água (coletores plano A e B/C, tubo a vácuo, piscina, reservatório, acoplado) | 7 | kWh/mês·m² (PMEe do Inmetro) |
| distribuição de ar (difusores, grelha, dampers, VAV) | 6 | `desempenho` |

Além dos itens: `fabricantes_por_segmento` (copiado da aba Fabricantes da planilha PHYSIS_AVAC-5, sem contatos), `hidraulica`
(coeficiente C de Hazen-Williams, rugosidade, comprimentos equivalentes de conexões de PVC — **verificar** no catálogo) e `tabelas_avac`
(degraus de BTU/h, motores, seções, Iz e disjuntores da planilha; o teste confere que são iguais às do `physis-avac.js`).

## Esquema de um item

```
id, categoria, subtipo, descricao,
faixa_capacidade {min, max}, unidade,
eficiencia {indicador, tipico, faixa[min,max], minimo_classe_A?, sazonal?, condicao?}   (null em sensores, automação, quadro, distribuição)
desempenho {grandeza, exatidao}                                                       (quando eficiencia é null)
potencia {min, max, unidade, nota?}, vida_util_anos [min, max], manutencao,
custo_referencia_brl {faixa, data, fonte}   → faixa = null e fonte = "[MARCADOR] …" (regra 1 do CLAUDE.md: não inventar preço)
normas [], fonte, data (ano da fonte), verificar (bool),
fabricantes_referencia [], familias_de_catalogo {linhas[], verificar}   (opcionais)
sistema, capacidade_nominal_btuh, cop_nominal, auxiliares_fator          (ar-condicionado; usados pela carga térmica)
```

Unidades: ar-condicionado sempre em **kW térmico** (1 TR = 3,517 kW = 12.000 BTU/h); η em fração; "%" de 0 a 100; COP e IEER em W/W;
IDRS em Wh/Wh.

## De onde vieram os números e por que quase tudo está "verificar"

Os valores foram lembrados de tabelas públicas (Inmetro PBE, ASHRAE 90.1 e Fundamentals, IEC 60034-30-1, ISO 16890, EN 1822, NBR 7229
e 13969, literatura da Embrapa e de wetlands, folhas de dados públicas). Não houve consulta às tabelas na data; por isso `verificar = true`
em quase todos os itens. Só ficaram `false` itens cujo valor é a própria definição da classe (PT100, medidores classe 1 e 0,5S, motores
IE2/IE3 pela tabela da IEC, componentes de quadro).

Fabricantes: cada classe traz `fabricantes_referencia` (quem publica catálogo daquela classe). Linhas de produto só aparecem quando o
nome da linha é público e estável (ex.: WEG W22; Sungrow SG/SH; Fronius Primo/Symo/Tauro/GEN24; Huawei SUN2000/LUNA2000; Jinko Tiger Neo;
Trina Vertex N; JA DeepBlue 4.0; Schneider Acti9; ABB System pro M; Siemens 5SL/5SV/SIRIUS, S7-1200 e LOGO!). Nenhum número de modelo foi inventado.
Atenção: a base de certificações proíbe citar "Siemens" (decisão de não citar parceiros). Aqui o nome aparece só como fabricante de
catálogo, copiado da planilha AVAC; se a decisão valer também para esta base, apagar das listas `fabricantes_referencia`,
`familias_de_catalogo` e `fabricantes_por_segmento`.

## Fontes abertas para continuar a coleta

| Fonte | O que tem | Endereço | Como importar |
|---|---|---|---|
| Inmetro PBE — tabelas de consumo e eficiência | ar-condicionado (IDRS e classe por modelo), motores, bombas, coletores solares, reservatórios, módulos e inversores FV, ventiladores de teto | https://www.gov.br/inmetro/pt-br/assuntos/avaliacao-da-conformidade/programa-brasileiro-de-etiquetagem/tabelas-de-consumo-eficiencia-energetica | `python ferramentas/importar_inmetro.py ar <arquivo>` ou `motores <arquivo>`; outras tabelas: copiar o padrão de `converter_ar` |
| Procel (selo e listas) | equipamentos com Selo Procel | https://www.procelinfo.com.br | manual, por enquanto |
| CEC — California Energy Commission | módulos FV (Pmax, área, coeficiente de temperatura) e inversores (eficiência ponderada) | https://solarequipment.energy.ca.gov/Home/PVModuleList e https://solarequipment.energy.ca.gov/Home/Inverters | `python ferramentas/importar_cec.py modulos <arquivo> --limite 200 --mesclar`; `inversores <arquivo> --mesclar` |
| AHRI Directory | chillers, VRF, recuperadores (certificados) | https://www.ahridirectory.org | manual |
| Catálogos dos fabricantes (WEG, Trox, Sicflux, Berliner Luft, Jacuzzi, Tigre, Sungrow etc.) | folhas de dados | site de cada fabricante | manual: criar item com `fonte` = nome do catálogo e `data` da edição |

Regras do importador:

- Baixe o arquivo para uma pasta só dele (dado de fora); rode o script de fora da pasta.
- Sem `--mesclar`, o script só converte e mostra quantos itens leu (`--saida itens.json` grava para conferência).
- Com `--mesclar`, troca na base apenas os itens com o prefixo do importador (`cec-fv-`, `cec-inv-`, `inmetro-ar-`, `inmetro-motor-`);
  os itens genéricos ficam.
- Os cabeçalhos mudam de ano para ano: o script procura as colunas por pedaço do nome. Se não achar, ele para com
  "cabeçalho não reconhecido". Aí, acrescente o novo nome da coluna na lista de pedaços.
- Depois de mesclar: rodar os testes. `test_equipamentos` reprova faixa absurda (por exemplo, eficiência de módulo fora de 18–25 %).

## Como acrescentar um item à mão

1. Copie um item da mesma categoria e troque `id` (único, minúsculas e hífen), faixas, `fonte` e `data`.
2. Deixe `verificar: true` até alguém conferir a tabela original.
3. Preço: só com cotação ou SINAPI, com data; sem isso, `[MARCADOR]`.
4. Rode `python -m unittest tests.test_equipamentos`.
