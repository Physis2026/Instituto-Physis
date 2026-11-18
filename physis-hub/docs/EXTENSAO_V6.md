# Extensao da linha V6 para outros dispositivos via ESP

Versao 0.1 · 13/11/2026 · proposta para aprovacao. Fonte normativa da linha base:
`controle-central/PROTOCOLO.md` e os dois `protocolo.cpp` (revisao de 26/10/2026).

## 1. Principio

O Receptor V6 ja aceita chaves desconhecidas e repassa a linha inteira ao Raspberry
(`lora.cpp`: a linha vai para a fila do Pi como chegou, com `RSSI` e `SNR` ao fim).
Entao um dispositivo novo entra na rede **sem mudar o firmware do receptor**, desde que:

1. envie `ID:<01..99>` unico no receptor (gravado na NVS, como no Transmissor V6);
2. envie `TIPO:<codigo>` para dizer o que e;
3. use ponto decimal, `-` para "sem leitura" e uma mensagem por linha;
4. caiba em 240 caracteres;
5. se for LoRa, entre no TDMA (ouve o beacon, transmite so no proprio slot);
6. se tiver atuador, feche sozinho por tempo, dentro do proprio dispositivo.

Sem `TIPO`, a linha e do no de solo e irrigacao (compatibilidade com o que esta em campo).

## 2. Tipos

| TIPO | Dispositivo | Chaves | Exemplo |
|---|---|---|---|
| (ausente) ou `SOLO` | Transmissor V6 | `U1 IR1 U2 IR2 T UAR TSOLO P1 P2 LIM1 LIM2 BAT TS` | `ID:03,U1:45.2,IR1:1,U2:50.0,IR2:0,T:27.5,UAR:63.5,TSOLO:23.1,P1:12.5,P2:-1,LIM1:30.0,LIM2:30.0,BAT:3.87,TS:1786000000` |
| `ZONA` | Caixinha: 2 zonas e 1 bomba | `U1 IR1 U2 IR2 BOMBA TMAX LIM1 LIM2 BAT TS` | `ID:21,TIPO:ZONA,U1:41.0,IR1:1,U2:38.5,IR2:0,BOMBA:1,TMAX:15,LIM1:35.0,LIM2:35.0,BAT:-,TS:1794600000` |
| `COL` | Coleira | `LAT LON GPS ATV IMP BAT TS` | `ID:41,TIPO:COL,LAT:-22.51003,LON:-43.18012,GPS:1,ATV:1,IMP:0,BAT:3.92,TS:1794600000` |
| `COM` | Comedouro | `NIV PORC TAG BLOQ BAT TS` | `ID:71,TIPO:COM,NIV:62.0,PORC:3,TAG:A1B2,BLOQ:0,BAT:-,TS:1794600000` |
| `PLUV` | Pluviômetro de báscula | `CHI PUL BAT TS` | `ID:31,TIPO:PLUV,CHI:0.20,PUL:44,BAT:-,TS:1794600000` |
| `SEC` | Secador solar (monitoramento, **em desenvolvimento**) | `TI UI TE UE TC VENT ABT PESO IRR BAT TS` (`ABT`, `PESO` e `IRR` opcionais) | `ID:41,TIPO:SEC,TI:38.5,UI:42.0,TE:27.1,UE:70.0,TC:52.3,VENT:1,PESO:84.20,IRR:820,BAT:3.95,TS:1794600000` |
| `ENE` | Medidor de energia (ESP com Modbus ou pulso, ou ponte MQTT) | `PW QR S V I FP BAT TS` (pelo menos uma grandeza) | `ID:61,TIPO:ENE,PW:12.430,QR:4.910,S:13.370,V:221.5,I:19.80,FP:0.930,TS:1794600000` |
| `HID` | Medidor de água (vazão e pressão) | `Q PR BAT TS` (pelo menos uma grandeza) | `ID:62,TIPO:HID,Q:3.250,PR:2.40,TS:1794600000` |
| `VEI` | Veículo da frota: rastreador GPS, leitor OBD-II/CAN ou medidor de vazão (**em desenvolvimento**, `FROTA.md`) | `LAT LON VEL RUMO FLX NIV HOR ODO IGN GPS BAT TS` (todas opcionais; pelo menos uma) | `ID:61,TIPO:VEI,LAT:-22.50512,LON:-43.17845,VEL:42.5,RUMO:183,FLX:12.40,NIV:63.5,HOR:1234.5,ODO:45678.9,IGN:1,GPS:1,BAT:3.95,TS:1794600000` |
| `MED` | Caixinha de remédios (Saúde, **a homologar**) | `CMP EVT BAT TS` | `ID:31,TIPO:MED,CMP:1,EVT:TOMADO,BAT:3.91,TS:1794650400` |
| `PUL` | Pulseira (Saúde, **a homologar**) | `LAT LON GPS CRISE BPM MOV BAT TS` | `ID:51,TIPO:PUL,LAT:-22.51003,LON:-43.18012,GPS:1,CRISE:1,BPM:128,MOV:2,BAT:3.80,TS:1794650400` |

Significados novos:

- `CHI` mm de chuva no intervalo (pulsos × mm por pulso; padrão 0,2794 mm, calibrar com 1 L medido), de 0 a 200;
  fora disso o campo sai e a leitura fica. `PUL` pulsos desde que o aparelho ligou (inteiro ≥ 0), para conferir
  linhas perdidas. O hub gera as grandezas `chuva` (mm) e `chuva_intensidade` (mm/h, pelo intervalo entre duas linhas
  do mesmo nó, até 3 h), soma o `CHI` do dia (fuso de Brasília) e grava como chuva observada de origem `physis`
  (`clima_observado`): o placar das fontes, o modelo de chuva e o alerta de deslizamento passam a usar a chuva do lugar.
- `ENE` (desde 15/11/2026): `PW` potência ativa em kW (negativa = injetando na rede), `QR` potência reativa em kvar
  (indutiva +, capacitiva -), `S` potência aparente em kVA, `V` tensão em V, `I` corrente em A, `FP` fator de potência
  (-1 a 1). Limites só físicos: V, I e S ≥ 0 e FP entre -1 e 1 (`protocolo.FAIXAS_ENE`); o teto de cada medidor é a
  definir [CONFERIR]. Grandezas: `energia` (kW, como no contrato physis/1), `potencia_reativa`, `potencia_aparente`,
  `tensao`, `corrente`, `fp`. Regra do usuário: o fator de potência entra sempre na energia. O hub calcula P, Q, S e FP de
  cada dia (`aprendizado.potencias_dia`): P e S medidos, ou P e Q, ou só FP; sem nada, a premissa
  `eletrica.fator_potencia_padrao` (marcada em `fp_fonte`). Guardado como modelo `potencias:<ativo>`.
- `HID` (desde 15/11/2026): `Q` vazão em m³/h (≥ 0), `PR` pressão em bar. Grandezas: `vazao`, `pressao`.
  Com `ENE` e `HID` em `medicao`, o modelo de consumo do aprendizado (média do dia × 24 h = kWh/dia e m³/dia) passa a
  ter dado. Pela ponte MQTT: nó com `"tipo": "energia"` ou `"tipo": "agua"` (`physis_hub/mqtt.py`, `NoMedidor`).
  Sem comando: `CMD` para esses nós é ignorado. Firmware do medidor (ESP): a definir.
- `VEI` (frota, desde 18/11/2026, **em desenvolvimento**; `FROTA.md`): `LAT`/`LON` em graus (com `GPS:0` a posição não
  vale e não vira grandeza), `VEL` velocidade em km/h, `RUMO` em graus (0 a 360, norte = 0), `FLX` vazão de combustível em L/h,
  `NIV` nível do tanque em %, `HOR` horímetro em horas, `ODO` odômetro em km, `IGN` ignição 0/1. Limites só físicos
  (`protocolo.FAIXAS_VEI`: graus válidos, nada negativo, RUMO até 360, NIV até 100); o teto de cada rastreador ou sensor é da
  folha de dados dele [CONFERIR]. Grandezas physis/1: `latitude`, `longitude`, `velocidade`, `rumo`, `vazao_combustivel`,
  `nivel_combustivel`, `horimetro`, `odometro` e `estado` (ativo `-ignicao`). O hub também entrega cada linha à frota
  (`Hub.frota_receptor` → `frota.Frota.receber_v6`), que guarda o ponto do veículo ligado ao nó. Pela ponte MQTT: nó com
  `"tipo": "veiculo"` (`mqtt.NoVeiculo`, só leitura; ver `MQTT.md`). `NIV` do comedouro (`COM`) continua sem faixa: as
  faixas valem só com `TIPO:VEI`.
- `MED`/`PUL`: o hub entrega à Saúde (`saude.py`) **antes** do adaptador; nada vai para `medicao` nem para o painel.
  `PHYSIS_SAUDE_V6=0` volta a recusar os dois (`tipo_desconhecido`). Ver `SAUDE.md`.

- `BOMBA` 0/1. Regra do dispositivo: bomba so liga com `IR1` ou `IR2` em 1; ao fechar a
  ultima valvula, desliga a bomba **antes**. O hub gera alarme se receber `BOMBA:1` com as
  duas valvulas em 0.
- `TMAX` minutos maximos de rega por acionamento, aplicado no dispositivo.
- `ATV` 0 = repouso, 1 = caminhando, 2 = correndo. `IMP` 0/1 = impacto desde a ultima linha.
  `GPS` 0/1 = posicao valida; com 0, `LAT`/`LON` vao como `-`.
- `NIV` percentual de racao no reservatorio. `PORC` porcoes servidas no dia. `TAG` ultima
  tag lida (hexadecimal, sem `,` `;` `:`). `BLOQ` 1 = limite diario atingido.

## 3. Comandos

Valem as 7 acoes do contrato, sem acrescimo nesta versao:

| Acao | SOLO | ZONA | COL | COM |
|---|---|---|---|---|
| `LIM1`, `LIM2` | limite da media | limite da zona 1 e da zona 2 | ignora | ignora |
| `IRR1` | valvula | valvula da zona 1 | ignora | ignora |
| `IRR2` | recusa (sem segundo rele) | valvula da zona 2 | ignora | ignora |
| `MODO` | AUTO/MANUAL | AUTO/MANUAL | ignora | ignora |
| `SYNC`, `PING` | sim | sim | sim | sim |

Acoes novas (por exemplo, servir porcao ou mudar o limite diario do comedouro) so entram
junto nos dois `protocolo.cpp`, no `physis_hub/protocolo.py` e no `PROTOCOLO.md`.

## 4. Caminhos fisicos

| Dispositivo | Hoje | Caminho na primeira fase |
|---|---|---|
| Transmissor V6 | Heltec V3, LoRa TDMA | Sem mudanca |
| Caixinha | ESP32 DevKit, Wi-Fi, ESPHome | Firmware proprio que fala a linha V6 por Wi-Fi com o hub: `POST /api/v6/linha` (referencia em `firmware_ref/no_wifi_v6`). A resposta do hub ja traz os comandos pendentes |
| Coleira | T-Beam (SX1276), LoRa livre | Portar para RadioLib (aceita SX1276) com os mesmos parametros de radio e o cliente TDMA do Transmissor V6; ate la, so simulada |
| Comedouro | Arduino Mega, sem rede | Mega envia a linha pela serial a um ESP32 que a repassa ao hub por Wi-Fi; ou portar para ESP32 |

## 5. Mapeamento para physis/1

Feito em `physis_hub/adaptador.py`. Ativo = `<lugar>-no<ID>` com sufixo quando ha mais de um ponto.

| Chave | Grandeza | Ativo |
|---|---|---|
| `U1`, `U2` | `umidade_solo` | `-a`, `-b` |
| media de `U1` e `U2` (so SOLO) | `umidade_solo` | sem sufixo |
| `IR1`, `IR2`, `BOMBA` | `estado` | `-valvula1`, `-valvula2`, `-bomba` |
| `P1` (quando >= 0) | `previsao_min` | sem sufixo |
| `T`, `UAR`, `TSOLO` | `temperatura`, `umidade`, `temperatura` | `-ar`, `-ar`, `-solo` |
| `BAT`, `RSSI`, `SNR` | `bateria`, `rssi`, `snr` | sem sufixo |
| `LAT`, `LON` (com `GPS:1`) | `latitude`, `longitude` | sem sufixo |
| `ATV`, `IMP` | `atividade`, `impacto` | sem sufixo |
| `NIV`, `PORC` | `nivel`, `porcoes` | sem sufixo |
| `PW`, `QR`, `S`, `V`, `I`, `FP` (só ENE) | `energia` (kW), `potencia_reativa` (kvar), `potencia_aparente` (kVA), `tensao`, `corrente`, `fp` | sem sufixo |
| `Q`, `PR` (só HID) | `vazao`, `pressao` | sem sufixo |
