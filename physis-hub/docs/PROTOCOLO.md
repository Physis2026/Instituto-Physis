# Protocolo V6 — reconstruído a partir do firmware

Versão de 13/11/2026. O `PROTOCOLO.md` original, citado nos READMEs do transmissor e do
receptor como parte do `controle-central`, não foi localizado. Este documento foi reescrito
lendo `protocolo.cpp`, `protocolo.h`, `lora.cpp`, `pi_client.cpp`, `webpages.cpp` e `config.h`
do Projeto Receptor V6 e do Transmissor V6 (revisão de 26/10/2026). Se o original aparecer,
ele prevalece e este deve ser conferido contra ele.

## 1. Rádio

| Parâmetro | Valor no código | Observação |
|---|---|---|
| Frequência | 915,0 MHz | Com 250 kHz de banda ocupa 914,875 a 915,125 MHz; mover o centro para 915,2 MHz ou acima |
| Largura de banda | 250 kHz | |
| Fator de espalhamento | 7 | |
| Potência | 14 dBm | |
| Palavra de sincronismo | 0x12 | |
| Biblioteca | RadioLib, mesma versão nos dois lados | Mudança em qualquer parâmetro exige regravar transmissor e receptor juntos |

## 2. Ciclo (TDMA)

O receptor é o mestre. A cada ciclo envia um beacon; cada nó descoberto fala só no seu slot.

```
BCN:<seq>,TS:<epoch>,CH:<0|1>,CIC:<ms>,SLOT:<ms>,GRD:<ms>,DSC:<ms>,MAP:<hex>
```

- `TS` relógio em segundos (epoch). `CH` 1 = chuva prevista, os nós não irrigam.
- `CIC` duração do ciclo, `SLOT` duração de cada slot, `GRD` guarda, `DSC` janela de descoberta.
- `MAP` mapa de bits dos nós descobertos (até 99). O cronograma viaja no beacon: mudar o ciclo
  não exige regravar os nós.
- Um nó é dado como offline depois de 3 ciclos sem falar. Sem beacon, o nó mantém o
  cronograma por 3 ciclos e depois volta a procurar.
- Até 99 nós por receptor (`TOTAL_NOS`).

## 3. Telemetria (nó → receptor)

Uma mensagem por linha, pares `CHAVE:VALOR` separados por vírgula (o receptor também aceita `;`).

```
ID:03,U1:45.2,IR1:1,U2:50.0,IR2:0,T:27.5,UAR:63.5,TSOLO:23.1,P1:12.5,P2:-1,LIM1:30.0,LIM2:30.0,BAT:3.87,TS:1786000000
```

| Chave | Significado | Regras |
|---|---|---|
| `ID` | Número do nó, 01 a 99, gravado na NVS | Obrigatória. Linha sem `ID` válido é descartada. Placa sem ID não transmite |
| `U1`, `U2` | Umidade do sensor A e do sensor B, em % | A média dos dois (ou o que estiver bom) comanda o relé |
| `IR1`, `IR2` | Válvula 1 e 2: 0 ou 1 | Sempre presentes. O nó de solo tem um relé; `IR2` vai 0 |
| `T`, `UAR` | Temperatura e umidade do ar (DHT22) | |
| `TSOLO` | Temperatura do solo (DS18B20) | |
| `P1`, `P2` | Minutos previstos até a umidade chegar ao limite | `-1` = modelo aprendendo; `0` = no limite; `43200` = não chega em 30 dias |
| `LIM1`, `LIM2` | Limites de umidade em % | Sempre juntos. Confirmam os comandos `LIM1` e `LIM2` |
| `BAT` | Tensão da bateria em V | |
| `TS` | Epoch do nó | 0 ou ausente = nó sem relógio |
| `RSSI`, `SNR` | Sinal medido na recepção | Acrescentados pelo receptor, não pelo nó |

Regras gerais: decimal sempre com ponto; `-` (ou `--`, `n/d`, `null`, `nan`) = sem leitura;
quebra de linha dentro da mensagem vira espaço; chaves desconhecidas são aceitas como extensão
e repassadas ao computador central (ver `EXTENSAO_V6.md`).

Tipos (`TIPO`) que o hub aceita (`physis_hub/protocolo.py`, `TIPOS_CONHECIDOS`): `SOLO` (ou ausente), `ZONA`, `COL`,
`COM`, `PLUV` (pluviômetro, desde 15/11/2026), `ENE` (medidor de energia) e `HID` (medidor de água: vazão e pressão),
ambos desde 15/11/2026, `SEC` (secador solar, em desenvolvimento; chaves e faixas em `SECADOR.md`), `VEI` (veículo da
frota, em desenvolvimento desde 18/11/2026: GPS, velocidade, rumo, vazão e nível de combustível, horímetro, odômetro e
ignição; chaves e faixas em `EXTENSAO_V6.md` e `FROTA.md`) e,
com `PHYSIS_SAUDE_V6=1` (padrão), `MED` e `PUL` (Saúde, a homologar; vão para a Saúde, nunca para `medicao`). Outro `TIPO` =
`tipo_desconhecido`. Chaves e exemplos em `EXTENSAO_V6.md`.
**Firmware (conferido em 15/11/2026):** os dois `protocolo.cpp` (receptor e transmissor V6) não têm lista de `TIPO`. O
receptor repassa chaves e tipos sem conferir, e quem confere é só o hub (`TIPOS_CONHECIDOS`). Um tipo novo, portanto, não exige
regravar o receptor; o firmware só muda no aparelho que passa a mandar o tipo novo.

## 4. Comandos (receptor → nó)

```
CMD:<nn>:<AÇÃO>[:<ARG>]
```

`nn` de 01 a 99; `00` = todos os nós. O comando sai na janela de comandos do próximo ciclo.

| Ação | Argumento | Efeito | Confirmação |
|---|---|---|---|
| `LIM1`, `LIM2` | Número de 0 a 100, com ponto decimal; a string inteira tem de ser o número | Novo limite | A próxima telemetria traz o novo `LIM1`/`LIM2` |
| `IRR1`, `IRR2` | `0` ou `1` | Fecha ou abre a válvula | A próxima telemetria traz `IR1`/`IR2` |
| `MODO` | `AUTO` ou `MANUAL` | Liga ou desliga a decisão automática | Não aparece na telemetria |
| `SYNC` | Epoch entre 1700000000 e 4102444800 | Acerta o relógio | Não aparece na telemetria |
| `PING` | Sem argumento | Teste de enlace | Não aparece na telemetria |

A validação é idêntica nos dois `protocolo.cpp` (`argumentoValido()`), e o hub a repete em
`physis_hub/protocolo.py`. Destino não numérico, fora de 0 a 99 ou argumento fora do formato:
o comando é recusado. No nó de solo, `IRR2` é recusado (não há segundo relé).

Travas do nó, que valem com ou sem rede: duração máxima de irrigação de 15 minutos e espera
de 2 horas entre irrigações automáticas.

## 5. Receptor ↔ computador central (HTTP)

| Sentido | Rota | Formato |
|---|---|---|
| Receptor → central | `POST http://<host>:8700/api/gateway/webhook` | `text/plain`, uma linha por linha; lotes de até 8 a cada 2 s; só avança com resposta 200 |
| Central → receptor | `GET /api/leituras?desde=<cursor>` | `{"leituras":[...],"cursor":N}` |
| Central → receptor | `GET /eventos` | SSE |
| Central → receptor | `POST /api/comando` | `{"comando":"CMD:02:LIM1:35"}` ou a linha crua; `{"ok":true,"fila":n}` |
| Suporte | `GET /api/estado`, `GET /api/no` | JSON de diagnóstico |
| Bancada | `POST /api/data` | Uma linha de telemetria, sem rádio |

O endereço do computador central é configurado no receptor em `/config` (rota `/set-pi`).

## 6. O que ainda falta no protocolo

- Autenticação dos comandos: hoje qualquer rádio com os mesmos parâmetros pode enviar um comando.
- Autenticação das rotas HTTP do receptor.
- Mudança da frequência central (seção 1).
