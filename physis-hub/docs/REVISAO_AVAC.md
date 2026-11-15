# Revisão técnica do módulo AVAC (`sistema/physis-avac.js`)

Data: 15/11/2026. Leitura do código (versão PHYSIS_AVAC-5), sem alterar o arquivo. Normas citadas só por número e seção;
a numeração das seções foi lembrada e deve ser conferida na edição em uso.
Legenda: ✅ conta correta · ⚠️ simplificação ou valor a conferir · ❌ erro.

## Resumo

| # | Achado | Gravidade | Onde |
|---|---|---|---|
| 1 | `potEixo = potAbs × rendMotor` multiplica em vez de dividir: motor subdimensionado | ❌ alta | linha ≈ 185 |
| 2 | Ar-condicionado por m²/TR (regra de bolso), sem carga térmica | ⚠️ alta | seção 2 |
| 3 | Garagem: 7,5 L/s·m² parece o dobro do usual (3,75 L/s·m²) e 300 m³/h por vaga sem fonte | ⚠️ média | seção 3 |
| 4 | Ambientes condicionados sem ar externo (NBR 16401-3) | ⚠️ média | seção 3 |
| 5 | Aquecimento solar sem perdas do reservatório e da tubulação; produção 1,8 kWh/m²·dia fixa | ⚠️ média | seção 5 |
| 6 | Piscina: sem fator de ocupação na evaporação, sem ganho solar, pressão fixa ao nível do mar | ⚠️ média | seção 6 |
| 7 | Quadro: DR obrigatório não verificado; seletividade não verificada | ⚠️ média | seção 8 |
| 8 | Resumo mostra "potência de ventilação" no eixo, não a elétrica | ⚠️ baixa | seção 9 |
| 9 | COP único (3,2) para todas as capacidades e para energia | ⚠️ baixa | seções 2 e 8 |

## 1. O erro do `potEixo` (resposta direta)

```js
o.potAbs = (B === 0 || !rendC) ? 0 : B / 3600 * o.pressao / rendC / 1000;     // kW
...
o.potEixo = o.potAbs * N(D.rendMotor);                                         // ← erro
o.potMargem = o.potEixo * (1 + (o.potEixo <= 1.5 ? N(D.margem1) : N(D.margem2)));
```

`potAbs = Q·Δp/η_ventilador` já é a potência que o ventilador pede no eixo. Qualquer rendimento que fique entre o eixo do ventilador
e a rede (transmissão por correia, motor) só pode **aumentar** a potência pedida a montante; nunca diminuir. Multiplicar por 0,88 reduz
12 % e escolhe motor menor.

Exemplo da própria planilha (exaustão de banheiros, 37.800 m³/h, 205 Pa, η do ventilador 0,6):
potAbs = 10,5 × 205 / 0,6 / 1000 = 3,59 kW.
Hoje: 3,59 × 0,88 = 3,16 → +20 % = 3,79 → motor **4,5 kW**.
Correto (dividindo): 3,59 / 0,88 = 4,08 → +20 % = 4,89 → motor **5,5 kW**. O motor da planilha fica abaixo da potência pedida com margem.

Qual é o certo depende do que `rendMotor` representa:

- Se é o rendimento da **transmissão** (correia, acoplamento): potência no eixo do motor = potAbs / η_transmissão → dividir.
- Se é o rendimento do **motor**: a potência de placa (saída no eixo) se compara direto com potAbs (com margem); o rendimento do motor
  só entra na potência **elétrica** = potência no eixo / η_motor (o quadro já faz isso: `kva = kw / (fp · rend)`).

Correção recomendada (separar os dois rendimentos e manter o padrão conservador):

```js
// padrao(): dutos: { ..., rendTransm: 0.95, rendMotor: 0.88, ... }   (0,95 correia; 1,0 acoplamento direto)
o.potEixo = o.potAbs / (N(D.rendTransm) || 1);                          // potência no eixo do motor
o.potMargem = o.potEixo * (1 + (o.potEixo <= 1.5 ? N(D.margem1) : N(D.margem2)));
o.potEletrica = o.potEixo / (N(D.rendMotor) || 1);                      // para o resumo e para conferência do quadro
```

Se não quiser criar campo novo agora: trocar `*` por `/` na linha 185 (fica conservador: trata 0,88 como perda entre eixo e motor) e
mudar o rótulo do campo na tela para "rendimento da transmissão". Atualizar a memória de cálculo (seção 6 do texto) e o espelho/teste
de AVAC, se houver, com o exemplo acima (5,5 kW).

## 2. Contas, fórmula, norma e situação

### Tipologias (seção 1)
- População = dormitórios × pessoas por dormitório ✅ (premissa de projeto).

### Ar-condicionado (seção 2)
- BTU/h = área / (m²/TR) × 12.000; padronização no próximo degrau comercial (`acima`) ✅ como conta.
- ⚠️ A NBR 16401-1:2008 (seção de cálculo de carga térmica) pede cálculo de carga por ambiente com condições externas, envoltória,
  insolação, ocupação e ar externo. A regra de m²/TR ignora orientação, vidro, ocupação e clima. **Correção**: usar a nova sub-aba
  "Carga térmica" (`physis-cargatermica.js`) e levar o BTU/h de projeto para `ac.amb[i].override` (ver `CARGA_TERMICA.md`, passo 4).
- kW térmico = TR × 3,517 ✅; kW elétrico = kW térmico / COP ✅ para demanda. ⚠️ COP 3,2 único; para energia usar IDRS do equipamento
  (base `physis-equipamentos.json`).

### Ventilação e exaustão (seção 3)
- Banheiro 90 m³/h por peça (= 25 L/s) ✅ ordem de grandeza usual de exaustão contínua; trocas por hora como alternativa ✅.
- Lixo: área × pé-direito × trocas ✅.
- Garagem: maior entre trocas/h, L/s·m² e m³/h por vaga ✅ como critério. ⚠️ 7,5 L/s·m² é o dobro do valor usual de referência
  internacional (≈ 3,75 L/s·m²) e 300 m³/h por vaga não tem fonte no arquivo: conferir a instrução técnica do Corpo de Bombeiros e o
  código de obras do município; gravar a fonte no campo.
- ⚠️ Omissão: não há ar externo para os ambientes condicionados (NBR 16401-3:2008, vazão eficaz = Rp × pessoas + Ra × área).
  A carga térmica nova calcula essa vazão por ambiente (`vazao_ar_externo_ls`); falta somá-la no resumo do AVAC.

### Pressurização de escada (seção 4) — NBR 14880:2014
- Vazamento Q = 0,827·A·ΔP^0,5 ✅ (orifício, ar padrão); portas abertas Q = v·A·n ✅; fator 1,25 ✅ (premissa).
- Força de abertura F = F_fechador + W·A·ΔP / (2·(W − d)), d = 0,075 m ✅; limite 110 N ✅.
- ⚠️ Conferir na norma a velocidade mínima na porta aberta e o número de portas abertas simultâneas por altura do edifício.

### Aquecimento solar (seção 5) — NBR 15569 (conferir edição vigente)
- Energia E = V·4,186·ΔT/3600 (kWh/dia) ✅; área = E·fração / produção ✅; reservatório = maior entre consumo e L/m² ✅; apoio ✅.
- ⚠️ Produção 1,8 kWh/m²·dia é baixa frente à PMEe de coletores classe A do Inmetro (≈ 77–90 kWh/mês·m² ≈ 2,6–3,0 kWh/m²·dia em
  condição de ensaio) e não depende da cidade. **Correção**: produção = PMEe do coletor escolhido (base de equipamentos) × fator de
  irradiação da cidade / 30.
- ⚠️ Omissão: perdas térmicas do reservatório e da tubulação de recirculação (a norma pede considerar). Somar à demanda.

### Piscina (seção 6)
- Evaporação m = (25 + 19·v)·A·(w_s − w_a) kg/h ✅ (fórmula clássica para piscina parada); q = m·2257/3600 ✅.
- Convecção h = 5,7 + 3,8·v ✅; radiação ε·σ·A·(T_w⁴ − T_céu⁴) com céu = ar − 6 °C ✅ (simplificado); paredes e fundo em % ✅; capa ✅;
  aquecimento inicial ✅.
- ⚠️ Piscina em uso evapora mais (fator de atividade de 1,3 a 2,0 conforme uso — literatura ASHRAE): acrescentar campo "fator de uso".
- ⚠️ Piscina descoberta recebe sol: descontar ganho solar (absortância da água × irradiação) — hoje fica a favor da segurança.
- ⚠️ Pressão fixa 101,325 kPa: usar a mesma correção de altitude dos dutos.

### Dutos e ventiladores (seção 7)
- Densidade pela altitude e temperatura ✅; viscosidade por Sutherland ✅; diâmetro pela velocidade ✅; Reynolds ✅;
  Swamee-Jain ✅; Darcy-Weisbach ✅; perdas localizadas e fator de segurança ✅; potência no eixo Q·Δp/η ✅.
- Retangular equivalente (Huebscher) e relação de aspecto ≤ 4:1 ✅; velocidades máximas por tipo ✅ (premissa).
- ❌ `potEixo` — ver item 1.
- ⚠️ Margens (30 % até 1,5 kW, 20 % acima): conferir com o catálogo do fabricante do ventilador; motor deve ser IE3 (mínimo legal).

### Quadro elétrico (seção 8) — NBR 5410:2004 (simplificado)
- Corrente de projeto mono/bi/trifásica ✅; fator de serviço ✅.
- Capacidade de condução: tabela de Iz em B1, PVC, 2 e 3 condutores carregados ✅ (valores conferem com a tabela da norma, seção 6.2.5);
  fator de temperatura ✅ (arredonda para a temperatura de cima, conservador); agrupamento por campo ✅; fator de harmônicas 0,86 ✅.
- Queda de tensão (seção 6.2.7) ✅; limite total 4 % ✅ para alimentação em baixa tensão pela distribuidora (7 % com subestação própria —
  deixar escolher).
- Curto-circuito: S ≥ √(I²t)/k, k = 115 ✅; corrente de curto no quadro pela impedância da fonte e do cabo ✅.
- Seccionamento automático em TN: L_máx = 0,8·U0·S / (ρ·(1 + S/S_PE)·I_a) ✅; I_a = 5, 10 e 20 × In para curvas B, C e D ✅.
- Neutro reduzido acima de 25 mm² sem harmônicas ✅ (seção 6.2.6); PE pela tabela de seções mínimas ✅.
- Queda na partida do motor (Ip/In = 7, limite 10 %) ✅.
- ⚠️ Omissão: a seção 5.1.3.2.2 exige DR de alta sensibilidade (≤ 30 mA) em certos circuitos (áreas molhadas, externas, tomadas em
  cozinha e lavanderia etc.). O módulo deixa DR como escolha livre; acrescentar a verificação e avisar quando faltar.
- ⚠️ Omissão: seletividade entre disjuntor do alimentador e dos circuitos não é verificada.
- ⚠️ Fator de demanda 1 em todos os circuitos: conservador; permitir fator por tipo de carga.

### Resumo e lista (seções 9 e 10)
- ⚠️ "Ventiladores / potência total (kW)" soma potAbs (eixo). Para leitura elétrica, mostrar também a soma das potências elétricas.
- Lista de equipamentos por categoria genérica ✅ (sem marca). Pode puxar a classe da base `physis-equipamentos.json` (eficiência,
  normas, manutenção) pelo tipo e pela capacidade.

## Ordem sugerida das correções

1. `potEixo` (item 1), com teste: caso da exaustão de banheiros deve escolher motor de 5,5 kW.
2. Ligar a sub-aba Carga térmica e levar o BTU/h para o AVAC (item 2) e o ar externo para o resumo (item 4).
3. Garagem: fonte dos critérios (item 3).
4. Solar: PMEe e perdas (item 5). Piscina: fator de uso, sol e altitude (item 6).
5. Quadro: DR obrigatório e seletividade (item 7); rótulo de potência elétrica (item 8).
