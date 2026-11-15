# Secador solar (P23) — monitoramento

Versão 0.1 · 15/11/2026 · **a homologar** (nada testado em hardware). Produto da loja: P23 "Secador solar · Frutas,
ervas e cogumelos". Usos previstos: café no terreiro da Fazenda Santa Clara; frutas, ervas e cogumelos na Casa Physis.

## 1. O que tem

| Parte | Arquivo |
|---|---|
| Tela da plataforma (aba "Secador solar") | `sistema/physis-secador.js` — `telaSecador()`, `window.SECADOR`, `window.SECADOR_I18N` |
| Contas espelho (modelo de secagem, dimensionamento, alertas) | `physis_hub/secador.py` |
| Linha V6 `TIPO:SEC` | `physis_hub/protocolo.py`, `adaptador.py`, `nucleo.py` (+ `sistema/physis-nucleo.js`) |
| Ponte MQTT (ESPHome) | `physis_hub/mqtt.py` (`"tipo": "secador"` no nó) |
| Alertas no hub | `physis_hub/hub.py` → `secador.alertas()` |
| Aparelho de exemplo | `firmware/secador/secador-solar.yaml`, `firmware/secador/parametros.json` |
| Testes | `tests/test_secador.py` |

## 2. Linha V6 `TIPO:SEC`

    ID:41,TIPO:SEC,TI:38.5,UI:42.0,TE:27.1,UE:70.0,TC:52.3,VENT:1,PESO:84.20,IRR:820,BAT:3.95,TS:1794600000

| Chave | O que é | Faixa física (fora dela o campo sai, a leitura fica) |
|---|---|---|
| `TI` | temperatura do ar dentro do secador (°C) | −20 a 120 |
| `UI` | umidade relativa dentro (%) | 0 a 100 |
| `TE`, `UE` | temperatura (°C) e umidade (%) de fora | −20 a 70; 0 a 100 |
| `TC` | temperatura na saída do coletor (°C) | −20 a 150 |
| `VENT` | ventilador 0/1 | só 0 ou 1 |
| `ABT` | tampa ou lona aberta 0/1 (opcional) | só 0 ou 1 |
| `PESO` | peso do produto (kg, opcional, célula de carga) | 0 a 5000 |
| `IRR` | irradiância (W/m², opcional) | 0 a 1500 |
| `BAT`, `TS` | como nos outros nós | — |

As faixas só valem com `TIPO:SEC` (em outra linha, `IRR` ou `TI` não têm faixa). São de plausibilidade, não de operação.

Grandezas (physis/1), ativo `<lugar>-no<ID>`:

| Chave | Grandeza | Ativo |
|---|---|---|
| `TI` | `temperatura_interna` (C) | sem sufixo |
| `UI` | `umidade_interna` (%) | sem sufixo |
| `TC` | `temperatura_coletor` (C) | sem sufixo |
| `TE`, `UE` | `temperatura`, `umidade` | `-ext` |
| `PESO` | `peso_produto` (kg) | sem sufixo |
| `IRR` | `irradiancia` (W/m2) | sem sufixo |
| `VENT`, `ABT` | `estado` | `-ventilador`, `-tampa` |

`temperatura_interna` não tem faixa de alarme no núcleo: o limite é do produto (seção 4).

## 3. Comando `VENT`

`CMD:<nn>:VENT:<0|1>` liga ou desliga o ventilador. Entrou em `protocolo.ACOES`; o hub confirma pela linha seguinte
(`VENT` igual ao pedido). **Falta**: levar `VENT` aos dois `protocolo.cpp` e ao `PROTOCOLO.md` antes de um secador LoRa
(regra da EXTENSAO_V6, seção 3). Pela ponte MQTT já funciona.

Segurança, em duas camadas:

1. **No aparelho** (`secador-solar.yaml`): com `TI` ≥ `t_seguranca` (60 °C, verificar), liga o ventilador e o segura
   ligado (um pedido de desligar é desfeito) até esfriar `histerese` (5 °C). Vale sem rede.
2. **Na ponte** (`mqtt.py`): mesma regra com o `"tmax"` do nó; `VENT:0` com o secador no limite é recusado; depois
   de esfriar, volta ao último pedido do hub.

## 4. Alertas

| Alerta | Regra | Nível |
|---|---|---|
| Superaquecimento | `TI` acima do máximo do produto do lote | alarme |
| Umidade alta sem ventilação | `UI` ≥ 80 % e `VENT` 0 | atenção |
| Chuva prevista com o secador aberto | Open-Meteo guardada (≥ 1 mm nas próximas 6 h ou ≥ 60 % de chance hoje) e `ABT` 1 ou sem sensor | atenção |
| Sensor sem leitura | nem `TI` nem `UI` | alarme |
| Nó fora, bateria baixa | regras gerais do hub | alarme / atenção |

No hub, o produto vem de `Hub.secador_produtos` (`{41: "cafe"}`); vazio = "outro" (60 °C). A tela usa o produto do
lote aberto. Ligação sugerida ao integrador: ler `instancia.json` `"secador": {"41": "cafe"}` no `servidor.py`.

Premissas por produto (todas **verificar**; mesmas no `.py` e no `.js`):

| Produto | Faixa boa (°C) | Máximo (°C) | Umidade inicial típica | Meta (% b.u.) |
|---|---|---|---|---|
| Café | 35–40 | 45 | 60 % | 11,5 (11–12) |
| Ervas | 30–35 | 40 | 80 % | 10 |
| Frutas em fatias | 50–60 | 65 | 85 % | 18 |
| Cogumelos | 40–50 | 55 | 90 % | 10 |
| Outro | 40–55 | 60 | 70 % | 12 |

## 5. Contas

- **Massa**: água a tirar = W₀·(u₀ − u)/(100 − u); peso na meta = matéria seca/(1 − u/100); rendimento = W_fim/W₀.
- **Curva** (Lewis): W(t) = We + (W₀ − We)·e^(−k·t). Com 3 ou mais pesos (balança `PESO` ou pesagens à mão), ajuste
  por mínimos quadrados: We numa grade de 100 passos entre 0 e o menor peso, refinado por 40 passos de seção áurea; para
  cada We, ln(W − We) é uma reta. Fim previsto = −ln((W_meta − We)/(W₀ − We))/k; sem resposta quando We fica acima da meta.
  Sem pesos: We pela umidade de equilíbrio típica e k típico do produto (verificar).
- **Dimensionamento**: calor = água × 2,45 MJ/kg ÷ aproveitamento do ar; área = calor ÷ (H × 3,6 × η_coletor × dias);
  Δw = 1,006 × ΔT × aproveitamento ÷ 2.450; vazão = (água ÷ Δw) ÷ 1,15 ÷ (dias × horas). H vem da NASA POWER
  (`ui.gis.irradiacao.ponto.meses`, mês mais fraco por padrão) quando o lugar tem localização.
- **Evitado**: elétrico = calor da água ÷ η ÷ 3,6 kWh × fator da rede (base do Carbono; 0,0289 tCO₂/MWh de reserva);
  lenha = calor ÷ (13 MJ/kg × η) kg, com CH₄ e N₂O do IPCC (GWP AR5) e o CO₂ só se a lenha for sem reposição.

Casos feitos à mão em `tests/test_secador.py` (100 kg de café 60 → 12 %: 54,55 kg de água, 7,42 m², 385 m³/h).

## 6. Ponte MQTT

    "nos": [{"no": "secador-solar", "id": 41, "tipo": "secador", "ti": "temperatura_interna",
             "ui": "umidade_interna", "te": "temperatura_externa", "ue": "umidade_externa",
             "tc": "temperatura_coletor", "vent": "ventilador", "abt": "tampa",
             "peso": "peso_produto", "irr": "irradiancia", "tmax": 60}]

Obrigatórios: `ti` e `vent`. A tampa é `binary_sensor`; o ventilador, `switch`.

## 7. O que precisa de hardware

- Montar e calibrar: SHT31 dentro e fora (abrigo à sombra), DS18B20 no coletor, HX711 com célula de carga sob as
  bandejas (opcional), sensor de irradiância (opcional), fim de curso da tampa (opcional), relé do ventilador.
- Conferir na bancada: segurança de temperatura no nó (aquecer o sensor até 60 °C e ver o ventilador ligar e não desligar).
- Medir a eficiência real do coletor e o k de cada produto para trocar as premissas.
- `VENT` nos `protocolo.cpp` para um secador LoRa.
