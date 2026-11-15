# Carbono: inventário de emissões (GHG Protocol), metas, SBCE e créditos

Explicação simples: o módulo conta quanto gás de efeito estufa a organização solta no ar em um ano,
separa por origem (escopos 1, 2 e 3), mostra à parte o que as plantas tiram do ar e o que se deixou de
emitir, desenha o caminho até o net zero e diz se a empresa entra no mercado regulado (SBCE).

## Arquivos

| Arquivo | O que faz |
|---|---|
| `sistema/physis-carbono.js` | Tela inteira (`telaCarbono()`), contas e eventos. Expõe `window.PhysisCarbono`. |
| `sistema/physis-fatores-emissao.json` | Fatores com fonte e ano; os marcados `verificar` são conferidos antes de relato oficial. |
| `physis-hub/physis_hub/carbono.py` | Espelho das contas em Python (mesmas regras), para testes de mesa. |
| `physis-hub/tests/test_carbono_ghg.py` | Casos calculados à mão (±1%), base de fatores, formato antigo, contrato da tela. |

## Subabas

1. **Inventário**: ano, GWP (AR5 ou AR6), área; totais por escopo, por grupo de fontes e por gás (gráficos SVG
   com tabela), intensidade por m² e por unidade produzida, parte medida e incerteza; CO₂ biogênico, HCFC-22,
   remoções e evitadas sempre à parte.
2. **Escopo 1**: combustão estacionária e móvel (diesel B e gasolina C com a mistura obrigatória; teor
   editável), fugitivas (R-410A, R-32, R-134a, R-404A, R-407C, R-22; por massa recarregada ou carga × taxa;
   sugestão a partir da aba AVAC), processos, rebanho (entérica, dejetos, N₂O no pasto), adubo/ureia/calcário,
   resíduos tratados no lugar (da Economia circular) e mudança de uso do solo (opcional, 20 anos).
3. **Escopo 2**: localização com fator anual do SIN (ano escolhido) ou 12 fatores mensais × 12 contas do Início;
   escolha de compra com I-REC e contratos; geração solar mostrada à parte (não é descontada duas vezes).
4. **Escopo 3**: categorias 1 a 15 marcáveis; calculadoras para 1 (gasto e materiais), 2 (bens de capital),
   4/9 (t·km), 5 (resíduos da Economia circular + outros), 6 (passageiro·km), 7 (casa–trabalho), 12 (fim de vida)
   e linha livre para as demais.
5. **Remoções e evitadas**: restauração por bioma, área e idade (soma as árvores do plano SbN: 1.667 mudas = 1 ha);
   evitadas por solar, biogás no lugar do GLP e reciclagem no lugar do aterro.
6. **Metas e net zero**: ano-base, redução linear por ano (referência 4,2%), ano do net zero (corte de 90%),
   medidas de redução e gráfico do caminho.
7. **SBCE e créditos**: enquadramento pelos limites de 10 mil e 25 mil tCO₂e (escopo 1), lista de preparação
   e “Pronto para o SBCE?”; potencial de créditos (restauração, biogás, eficiência) com famílias de metodologia,
   adicionalidade e permanência; nota do CBIO.

Seção “Metodologia e normas” no fim de todas as subabas (GHG Protocol, Programa Brasileiro GHG Protocol,
ISO 14064-1:2018, Lei 15.042/2024, IPCC).

## Dados que vêm de outros módulos

| De onde | Chave ou leitor | Uso |
|---|---|---|
| Início | `physis-perfil` (`perfilLer`) | kWh dos 12 meses (ou média levada a 12), área construída, colaboradores |
| Economia circular | `physis-residuos-plano` (`rcLer`) | resíduos por rota: no lugar = escopo 1; para fora = escopo 3 cat. 5; biogás e reciclagem = evitadas |
| Gestão | `physis-gestao-cliente` (`gLer`) | produção (intensidade), combustível (aviso), compras (cat. 1) e investimentos (cat. 2) |
| SbN | `physis-sbn` (`sbnLer`, `SBN`) | árvores do plano (estratos médio, alto, emergente) para remoções |
| AVAC | `calcLer("avac")` + `window.AVAC.calcular` | kW de frio → carga estimada de fluido |
| Energia solar | `solarCalc()` | geração anual sugerida |

## Estado salvo (`physis-carbono`)

Formato 2 (`v: 2`). Os campos antigos `kwh` e `solar_kwh` continuam no topo, porque Certificações e Solar os leem.
O formato antigo `{kwh, diesel, glp, gn, solar_kwh, medidas}` é migrado na leitura: diesel → diesel B,
glp → GLP, gn → gás natural (estacionária), medidas → Metas.

## Regras do GHG Protocol seguidas

- CO₂ de biomassa e biocombustível: informado à parte; CH₄ e N₂O deles entram.
- HCFC-22 (Protocolo de Montreal): à parte, não soma ao total.
- Remoções e evitadas: nunca abatem o inventário.
- Escopo 2: relato duplo (localização e escolha de compra); o total usa localização.
- Resíduo em aterro: metano total que o resíduo vai gerar, lançado no ano do envio.

## Fatores principais (todos “verificar”)

| Item | Valor | Fonte |
|---|---|---|
| Rede (padrão da plataforma) | 0,0289 tCO₂/MWh | núcleo physis/1 = premissas |
| Rede 2019–2023 | 0,0750 · 0,0617 · 0,1264 · 0,0426 · 0,0385 | MCTI, média anual do SIN |
| Diesel A | 35,5 MJ/L; 74.100 kgCO₂/TJ | BEN (PCI) + IPCC 2006 v2 |
| Gasolina A / etanol | 32,2 / 22,3 MJ/L | BEN + IPCC 2006 |
| GLP / gás natural | 46,5 MJ/kg / 36,8 MJ/m³ | BEN + IPCC 2006 |
| Mistura | B15 / E30 | Lei 14.993/2024 e CNPE |
| GWP AR5 | CH₄ 28 · N₂O 265 · HFC-32 677 · HFC-125 3.170 · HFC-134a 1.300 | IPCC AR5 |
| GWP AR6 | CH₄ 29,8 fóssil / 27,0 bio · N₂O 273 · HFC-32 771 · HFC-125 3.740 | IPCC AR6 |
| Gado de corte | 56 kg CH₄ entérico + 1 kg dejetos/cabeça·ano | IPCC 2006 v4, América Latina |
| Aterro | DOC × 0,5 × 1,0 × 0,5 × 16/12 × (1 − 0,1) | IPCC 2006 v5 |
| Restauração | 9 tCO₂/ha·ano (Mata Atlântica) | Refinamento IPCC 2019 + literatura |
| Escopo 3 (frete, viagens) | 0,107 kg/t·km; 0,246 kg/p·km (voo nacional) | DEFRA/DESNZ 2024 |
| Gasto (cat. 1) | 0,03 a 0,20 kgCO₂e/R$ | provisório Physis (triagem) |

## Casos de mesa (testes)

| Caso | Resultado (AR5) |
|---|---|
| 1.000 L diesel A em gerador | 2,646 tCO₂e |
| 12 MWh × 0,0385 | 0,462 tCO₂ |
| 2 kg de R-410A recarregados | 3,847 tCO₂e (AR6: 4,511) |
| 50 cabeças de gado de corte | 100,04 tCO₂e |
| 10 t de rejeito no aterro | 12,6 tCO₂e (0,45 t de CH₄) |

## Fase 2 (curadoria do engenheiro)

- Conferir todos os fatores `verificar`, principalmente: fatores anuais e mensais do SIN 2024 e 2025;
  o valor 0,0289 do núcleo (não bate com nenhum ano da lista: alinhar núcleo, premissas e esta base juntos);
  PCI do BEN do ano; teor de biodiesel e etanol vigente; GWP padrão do Programa Brasileiro.
- Trocar os fatores de gasto (cat. 1 e 2) por base brasileira ou fatores de fornecedor.
- Dejetos de suínos em lagoa (MCF), confinamento de bovinos, N₂O de manejo de dejetos (hoje só pasto).
- Taxas de remoção por bioma com fonte de referência por fitofisionomia e idade; estoque por bioma para uso do solo.
- Aterro com captação de biogás (R) por município; fator de incineração por composição.
- Regulamentação do SBCE (formato do relato, prazos, verificação) quando publicada.
