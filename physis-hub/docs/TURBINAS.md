# Turbinas: hidráulica e eólica

Aba **Turbinas** da plataforma com duas partes (botões com `aria-pressed`): **Hidráulica** e **Eólica**.

| Arquivo | O que tem |
|---|---|
| `sistema/physis-turbinas.js` | Tela (`telaTurbinas()`) e contas puras (`window.TURBINAS.hidraulica(p)`, `.eolica(p)` e as auxiliares) |
| `physis-hub/physis_hub/vento.py` | Vento do lugar (NASA POWER, guardado no hub) e o **espelho** das contas em Python |
| `physis-hub/tests/test_turbinas.py` | Contas conferidas à mão, guarda do vento, e o módulo da tela sem internet |

Regra 4 do CLAUDE.md: a conta existe na tela e no servidor; mudou numa, muda na outra, com teste.
Conferência feita em 15/11/2026: as duas implementações dão o mesmo número (até a 12ª casa) num caso completo
(eólica com 12 meses, perdas e densidade; hidráulica com Hazen-Williams, perdas localizadas e vazão mensal).

## Hidráulica

- Potência: `P (kW) = 1000 · 9,81 · (Q/3600) · H_líquida · η / 1000` (Q em m³/h). É a fórmula que já estava na tela; 1 bar ≈ 10,2 m.
- Queda líquida = queda bruta − perda na tubulação forçada. Se a pressão foi medida com a água correndo, a perda já está na medida (caixa de seleção).
- Perdas: **Darcy-Weisbach** `hf = f·(L/D)·v²/2g`, com `f` de Swamee-Jain `0,25/[log10(ε/3,7D + 5,74/Re^0,9)]²` (64/Re abaixo de Re 2000), ou **Hazen-Williams** `hf = 10,67·L·Q^1,852/(C^1,852·D^4,87)`; as duas somam `ΣK·v²/2g`. Água a 20 °C (ν = 1,004·10⁻⁶ m²/s).
- Tubos (ε em mm; C): PVC 0,0015/150; PEAD 0,007/140; aço 0,045/120; ferro fundido 0,26/100; concreto 0,3/120 — valores típicos de tabela de tubo novo, **conferir com o fabricante**.
- Avisos: perda acima de 10% da queda; velocidade acima de 3 m/s.
- Tipo de turbina: Pelton, Turgo, Francis, Kaplan/hélice, Michell-Banki (fluxo cruzado) e bomba funcionando como turbina, pela queda líquida e pela vazão, com faixa típica de eficiência. Faixas aproximadas de literatura (ESHA 2004; Paish 2002) — **verificar com o fabricante**.
- Energia mês a mês: 12 vazões opcionais; acima da vazão de projeto, o excesso passa pelo vertedouro (`Q_mês = min(Q_mês, Q_projeto)`); a perda é recalculada com a vazão do mês. Sem a lista, vale a vazão de projeto o ano todo (o mesmo resultado da tela antiga).
- Custo e retorno: `analiseInvest(custo, energia_ano/12 · tarifa, vida, taxa, inflação)` da plataforma (o mesmo dos investimentos da Gestão; em Python, `investimento.analise`).
- Estado: `calcLer("turb")`, com as chaves antigas (`vazao, queda, un, eta, horas, n`) mais `mat, diam, comp, metodo, kloc, din, meses, custo, tarifa, vida, taxa, infl`.

## Eólica

- Curva de potência: `P = ½·ρ·A·v³·Cp`, com Cp limitado a Betz (16/27 = 0,593); zero abaixo da partida e acima do corte; limitada à potência nominal (ou nominal a partir da velocidade nominal). Sem potência nominal, ela sai da velocidade nominal.
- Densidade do ar: `ρ = p/(287,05·T)`, `p = 101325·(1 − 2,25577·10⁻⁵·h)^5,25588` (atmosfera padrão). 0 m e 15 °C dão 1,225 kg/m³.
- Cisalhamento (lei de potência): `v(h) = v_ref·(h/h_ref)^α`. α por terreno (Masters 2004, tab. 7.3): água 0,10; campo aberto 0,15; lavoura e cercas vivas 0,20; mata 0,25; cidade pequena 0,30; cidade com prédios 0,40. O α medido entre 10 m e 50 m da base aberta aparece como referência (`ln(v50/v10)/ln 5`).
- Weibull: `c = v̄/Γ(1+1/k)`; k = 2 (Rayleigh) por padrão. Energia = `horas · ∫P(v)·f(v)dv` (ponto médio, passo 0,05 m/s até 40 m/s), menos as perdas informadas.
- Com as 12 médias mensais da base, a energia é a soma dos meses (cada mês com seus dias); com uma velocidade digitada, a conta é anual.
- Fator de capacidade = energia/(potência nominal · 8.760).
- Mensagem: abaixo de 4 m/s no cubo, **pouco viável**; de 4 a 5 m/s, **marginal**; 5 m/s ou mais, **viável a confirmar** (vira marginal se o fator de capacidade ficar abaixo de 10%).
- Modelos de partida: classes genéricas de 1, 3, 5, 10 e 20 kW (diâmetro, partida 3 m/s, nominal 11 m/s, corte 25 m/s, Cp 0,30), marcadas **Verificar**: não são modelos comerciais.
- Cuidados na tela: medir no local por 12 meses, turbulência urbana e de telhado, ruído contra a NBR 10151 da zona, torre com projeto e ART, prefeitura e aeródromos, ligação como microgeração.
- Estado: `calcLer("turb-eol")` (`preset, diametro, cp, p_nom, v_in, v_nom, v_out, perdas, v_ref, href, altura, terreno, alfa, k, altitude, temp, custo, tarifa, vida, taxa, infl`).

### Vento do lugar (servidor)

`GET /api/gis/vento?lat=&lon=` → NASA POWER, climatologia pontual, comunidade RE, parâmetros `WS10M,WS50M,T2M`.
Guardado na tabela `gis_cache` com a chave `vento_alturas:<lat 0,25°>:<lon 0,25°>` (não colide com a camada `vento:` do gis.py, que é WS2M).
Resposta: `ok, ws10 {meses, anual}, ws50 {meses, anual}, t2m, elevacao_m, alfa_medido, fonte, avisos`. Fora do Brasil: 400.
`PHYSIS_VENTO_URL` troca o endereço (testes, espelho).

A tela usa `gisX("vento")` da plataforma (o mesmo carregador de relevo, solo e rio); se ele não existir, busca sozinha `api/gis/vento`.

## Revisão técnica (15/11/2026) e normas

Conferido fórmula por fórmula contra a conta à mão (testes) e entre JavaScript e Python (mesmo número até a 12ª casa).
A tela tem a seção recolhível **Metodologia e normas** em cada parte, com o mesmo conteúdo abaixo (redação própria;
normas citadas pelo número — ler o texto vigente; números de cláusula não foram citados para não errar a edição).

Hidráulica — validade e cuidados:
- Swamee-Jain vale para escoamento turbulento (Re ≈ 5·10³ a 10⁸; ε/D de 10⁻⁶ a 10⁻²); laminar 64/Re; a faixa de transição é aproximada.
- Hazen-Williams é empírica (água fria, turbulento, diâmetros médios e grandes): fica como conferência.
- Eficiência constante na faixa de vazão (falta curva de carga parcial por tipo).
- Golpe de aríete (Joukowsky) não é calculado: o projeto confere.
- Referências: IEC 61116 (equipamento eletromecânico de pequenas centrais), IEC 60041 (ensaio de campo de rendimento),
  IEC 60193 (ensaio em modelo), ABNT NBR 12214 (bombeamento — referência para bomba como turbina e adutora), Eletrobras
  (Diretrizes de PCH; Manual de microcentrais), ASCE Manual 79 (tubulação forçada de aço). Água: outorga (Lei 9.433/1997)
  e licença ambiental; CGH até 5 MW só comunicada à ANEEL (Lei 9.074/1995, redação da Lei 13.360/2016).

Eólica — validade e cuidados:
- Densidade pela atmosfera padrão (ISO 2533) e gás ideal; a curva do fabricante é na densidade padrão (a IEC 61400-12-1 normaliza).
- Rayleigh (k = 2) sem medição, como a IEC 61400-12-1 faz para a energia anual de referência; α = 0,2 é o perfil normal da IEC 61400-1.
- Referências: IEC 61400-2 (pequenas turbinas, área varrida até 200 m²), IEC 61400-12-1 (curva de potência e energia anual),
  IEC 61400-11 (ruído), ABNT NBR 10151:2019 (ruído em áreas habitadas), ABNT NBR 6123 (vento na estrutura), DECEA (obstáculos).

Conexão (as duas): Lei 14.300/2022, ANEEL REN 1.059/2023, PRODIST Módulo 3 e a norma da distribuidora. A NBR 16149/16150
foi escrita para inversores fotovoltaicos; para gerador hidráulico ou eólico vale o PRODIST e a norma da distribuidora.
NBR 5410 e NBR 5419 no lado elétrico; ART de projeto e execução.

## Limites conhecidos

- A base aberta é uma grade de ~50 km (MERRA-2): não vê obstáculos; o número serve para triagem, não para comprar.
- Eficiência hidráulica fixa em toda a faixa de vazão (sem curva de carga parcial por tipo de turbina).
- Sem curva de potência do fabricante importável (só classes genéricas ou dados digitados).
