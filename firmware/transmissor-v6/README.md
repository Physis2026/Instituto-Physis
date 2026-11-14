# Nó transmissor V6 — Heltec WiFi LoRa 32 V3

Par do `Projeto Receptor V6`. **Regrave os dois juntos** depois da revisão de compatibilidade de 26/10/2026
(cronograma, validação de comando e PING mudaram nos dois lados; ver "Compatibilidade" no README do receptor).

Firmware dos **nós de campo** da rede de irrigação — até **99** deles (teto do
protocolo: `ID:` tem dois dígitos e `00` é o broadcast). Cada nó tem 2 sensores capacitivos de umidade de
solo, 1 DHT22 (temperatura + umidade do ar) e 1 relé de irrigação. Sem WiFi, sem cartão SD.

O nó fala o protocolo de linha do controle central — o contrato normativo está em
`Claude Worktree/controle-central/PROTOCOLO.md`, e a fonte da verdade do parser é
`controle-central/app/protocolo.py`.

## Gravar e comissionar

**Uma imagem para todas as placas.** A identidade é gravada depois, uma vez, pela serial:

```bash
pio run -t upload
```

A placa sobe **sem identidade**: ela não transmite nada e o OLED avisa em tela cheia. Abra a serial e
dê o número:

```bash
pio device monitor -b 115200
```

Digite `id 7` e Enter. `id` sozinho mostra o atual, `ajuda` lista os comandos. O número fica na NVS e
**sobrevive a regravações do firmware**. **Etiquete a placa** no mesmo momento.

Por que não uma imagem por nó: com 99 placas seriam 99 builds, 99 gravações e 99 etiquetas, e um engano
no meio põe duas placas no mesmo setor — exatamente o erro que a identidade em compilação queria evitar.
O `PROTOCOLO.md` §4.2(d) documenta as duas opções e por que a recomendação inverteu.

### Legado

As placas já gravadas com `-D NODE_ID` continuam funcionando: os envs `no1`..`no4` existem para elas.
Com o flag, a identidade vem do binário e o comando `id` é recusado.

```bash
pio run -e no2 -t upload
```

## TDMA — por que os sinais não se sobrepõem

O nó nunca transmite quando quer. O receptor emite um beacon no início de cada ciclo e cada nó só abre a
boca dentro do próprio slot:

```
Exemplo: 3 nós descobertos (IDs 02, 07, 15) → ciclo de 5 s
t=0    0,6s    1,1s    1,6s    2,1s          3,1s  3,3s        5s
├BEACON┤guarda├─Nó 02─├─Nó 07─├─Nó 15─├─DESCOBERTA─┤folga├…─CMDs─┤
```

O ciclo é **variável** e decidido pelo receptor: muda a cada nó **descoberto**, 1 s a cada dois nós
(slot de 500 ms). O beacon leva o mapa dos descobertos (`MAP:`, 13 bytes em hex) e este nó ocupa o slot
de número igual à quantidade de descobertos com ID menor que o seu. Fora do mapa, ele fala na janela de
descoberta (`DSC:`, logo depois do último slot) num instante sorteado a cada ciclo; ouvido uma vez, ganha
slot no beacon seguinte. Sem `MAP:` (receptor antigo) ou órfão, volta ao slot fixo pelo ID. O maior payload
fica ~110 ms no ar (132 B em SF7 / BW 250 kHz / CR 4/5).

Duas regras de tempo mantêm o nó dentro da própria janela:

* O ciclo conta do **início** do beacon: o instante do RxDone é anotado na interrupção (o laço pode estar
  ocupado com display, DHT ou cartão) e o tempo no ar do beacon é descontado — o mesmo zero do receptor.
* Uma transmissão só começa se **couber inteira** até o fim da janela, com `MARGEM_TX_MS` (50 ms) de sobra.
  Se o laço atrasou demais, o nó pula o ciclo (`[TDMA] Slot perdido` na serial) em vez de invadir o slot
  do vizinho.

O cronograma (`CIC`/`SLOT`/`GRD`/`DSC`/`MAP`) e o relógio (`TS`) viajam **dentro do beacon**, então mudar o ciclo no
receptor **não exige regravar os nós**. Sem beacon, o nó mantém a cadência pelo próprio relógio
(*holdover*) por 3 ciclos; depois se declara órfão, para de enviar `TS:` e passa a sortear um jitter para
que dois nós órfãos não colidam sempre no mesmo instante.

## Linha transmitida

```
ID:03,U1:45.2,IR1:1,U2:50.0,IR2:0,T:27.5,UAR:63.5,TSOLO:23.1,P1:12.5,P2:-1,LIM1:30.0,LIM2:30.0,BAT:3.87,TS:1786000000
```

* **Decimal é PONTO.** Num payload separado por vírgula, `U1:45,2` é lido como `45` e o `,2` some sem
  erro nenhum (`PROTOCOLO.md` §2.2). Nunca troque `String(v, 1)` por formatação com locale.
* `IR1`/`IR2` estão **sempre presentes**: campo ausente vira `false` no RPi, e o painel registraria
  "irrigação encerrada" com a água ligada.
* `LIM1` e `LIM2` saem **sempre juntos** — é a presença dos dois na mesma linha que confirma um comando
  de limite no painel.
* `P1`/`P2` = minutos até o limiar; `-1` enquanto o modelo aprende (as 4 primeiras horas de secagem
  limpa); `43200` (30 dias, `PREVISAO_MAX_MIN`) = o limiar não chega nesse horizonte; `-` = sem leitura
  de solo para prever (sensor com defeito). O painel do receptor mostra `Aprend.` e `--`.
* `U1` é o **sensor A**, mas `LIM1`, `P1` e `IR1` valem para a **média** dos dois sensores — é ela que
  liga o relé. `U2`/`LIM2`/`P2` são o sensor B sozinho, sem válvula.
* `UAR` (umidade do ar), `TSOLO` (temperatura do solo, DS18B20) e `BAT` (tensão) são chaves de extensão; o RPi as aceita sem derrubar a linha.
* O nó **não** emite `RSSI` nem `SNR` — quem mede é o gateway, na recepção.

## Comandos aceitos

`CMD:<nn>:<AÇÃO>[:<ARG>]`, com `nn` = `01`…`99` ou `00` (broadcast).

| Ação | Efeito |
|---|---|
| `SYNC:<epoch>` | ajusta o relógio; a partir daí a telemetria leva `TS:` |
| `LIM1:<0-100>` | limiar do canal 1 (a média dos dois sensores), persistido em NVS |
| `LIM2:<0-100>` | limiar do canal 2 (sensor B), persistido em NVS |
| `IRR1:<0\|1>` | abre/fecha o relé agora, sem mudar o modo (depois de fechar vale o cooldown); modo manual fixo só com `MODO:MANUAL` |
| `IRR2:<0\|1>` | **ignorado** — este nó tem um relé só e não mente sobre `IR2` |
| `MODO:AUTO\|MANUAL` | alterna entre controle por limiar e comando manual (maiúsculas ou minúsculas) |
| `PING` | endereçado: responde em 150 ms (`ATRASO_PING_MS`); o receptor fica 400 ms calado depois dele para não atropelar a resposta. Sem tempo antes do fim do ciclo, ou em **broadcast**, responde no próprio slot — espalhar 99 respostas por ID daria ~12 s invadindo os slots alheios |

**Regra de ouro:** destino diferente do próprio ID e diferente de `00` é ignorado em silêncio.
Sem isso, um `CMD:02:IRR1:1` ligaria a bomba de todos os setores.

**Argumento fora do contrato é recusado** (`[CMD] Recusado` na serial), com a mesma regra que o receptor
aplica antes de pôr o comando no ar (`argumentoValido()`, igual nos dois `protocolo.cpp`): `LIM1`/`LIM2` só
um número de 0 a 100 com ponto decimal, `IRR1`/`IRR2` só `0` ou `1`, `MODO` só `AUTO`/`MANUAL`, `SYNC` só um
epoch entre 2023 e 2100, `PING` sem argumento. Antes, `IRR1:abc` desligava a válvula e `MODO:xyz` virava AUTO.

Uma placa **não comissionada** ignora até o broadcast, e não transmite nada. Sem essa trava ela entraria
na rede se passando pelo nó `00`/`01` e poluiria o histórico de um setor real sem ninguém perceber.

## Irrigação

Um relé por nó, decidido pela **média dos dois sensores** contra `LIM1`, com previsão de secagem
(`MARGEM_PREVISAO_MIN`), inibição por chuva (flag `CH` do beacon), cooldown entre ciclos e trava dura de
duração máxima. O canal 2 é monitorado e reportado, mas não tem válvula.

A flag de chuva vale 30 min sem beacon. Como cada beacon a renova, quem garante que ela não fique presa é o
receptor: uma previsão com mais de 1,5 h desde a última consulta bem-sucedida sai como `CH:0`.

## Aprendizado da secagem

O nó aprende sozinho a que velocidade o solo seca e, com isso, prevê `P1`/`P2`. Há dois modelos: o do
canal 1 (média dos sensores, o que comanda o relé) e o do canal 2 (sensor B sozinho, informativo).

**O que aprende:** a taxa de queda da umidade (%/min) em cada faixa horária — manhã 6–12 h, tarde
12–18 h, noite 18–6 h —, levada a 20 °C, e o ganho dessa taxa com a temperatura do ar (DHT22).

**Como (contínuo, a cada leitura):**

1. Toda leitura válida (1 por segundo) entra na média do minuto.
2. A cada 60 médias (`SEGMENTO_MIN`), uma reta de mínimos quadrados dá a taxa da última hora. Quedas,
   estabilidade e pequenas subidas entram igual — não há seleção que transforme ruído em secagem.
3. A reta é descartada se a umidade mudou de origem no meio (um sensor caiu ou voltou), se subiu mais de
   `SALTO_MAX_PTS` entre dois minutos ou de forma sustentada (chuva, irrigação de fora), ou se a taxa
   passa de `TAXA_MAX`. Depois de molhar (relé ou chuva), o aprendizado espera `ESPERA_POS_MOLHAR_MIN`:
   a drenagem não é secagem.
4. A taxa aceita entra na média da sua faixa e na média geral. As médias lembram ~`MEMORIA_DIAS` dias
   inteiros de cada faixa.

**Previsão:** percorre as faixas a partir da hora atual (a noite seca menos que a tarde), com a
temperatura de agora na faixa corrente e a temperatura típica nas seguintes. Sem relógio (beacon com
`TS:0`, receptor sem internet), as faixas não aprendem — não há como saber a hora — e vale a média
geral. Só prevê depois de `MIN_SEGMENTOS_MODELO` retas aceitas.

**Por que não comparar leituras próximas** (o que o V4 e o V6 original faziam): uma contagem do ADC vale
~0,05 % de umidade e o solo seca na ordem de 0,002 %/min. Em 30 s a queda real é ~1/50 de contagem — o
que se media era quantização e ruído, e guardar só as quedas transformava ruído em taxa. A taxa aprendida
ficava presa em ~0,1 %/min (≈ 140 %/dia) qualquer que fosse a secagem real, e a previsão saía de 10 a
200 vezes curta.

**No monitor serial**, cada reta aceita aparece assim:

```
[Aprend1] Faixa 1 | Taxa: 0.00412 +/- 0.00004 %/min (5.93 %/dia) | T 31.2 C | ganho 0.012/C | n=37
```

O OLED mostra `Aprend. n/4 (m min)` enquanto aprende (`drenando` durante a espera) e depois
`Prev: 42 min`, `Prev: 5.2 h` ou `Prev: 8.4 d`.

**NVS:** o aprendizado fica num bloco versionado por modelo (`mod1`/`mod2`), gravado a cada reta aceita
(no máximo uma vez por hora); o limiar fica à parte (`lim1`/`lim2`) e só é gravado por comando. Ao gravar
esta versão por cima da antiga, as chaves do aprendizado antigo (`t0_1`…`ok_2`) são apagadas no primeiro
boot — aquelas taxas eram ruído — e o nó reaprende em ~4 h. O limiar configurado é preservado.

## Calibração dos sensores

`SECO_A`/`MOLHADO_A` e `SECO_B`/`MOLHADO_B` em `src/config.h` são **por sensor** — o Transmissor V4 usava
um par só para os dois, o que introduz erro de vários pontos percentuais. Para cada sensor (são dois por nó):
anote o raw ao ar livre (seco) e submerso até a marca (molhado), e ajuste antes de ir a campo.

## Antes de soldar

* **Confira a pinagem** (`PINO_SOLO_A` 5, `PINO_SOLO_B` 6, `PINO_DHT` 7, `PINO_RELE` 4,
  `PINO_TEMP_SOLO` 2, microSD em SCK 40 / MISO 41 / MOSI 42 / CS 39) contra o esquema
  da sua placa — variantes do Heltec V3 expõem pinos diferentes.
* `DHT_TIPO` é `DHT22` (-40..80 °C). O RPi ainda descarta temperatura fora da faixa **aberta**
  `0 < T < 80`: leituras abaixo de 0 °C saem na linha, mas o Pi as joga fora.
* `MAX_IRRIGACAO_MS` e `COOLDOWN_MS` estão em 15 min / 2 h. Dimensione para a sua cultura.

## Temperatura do solo e cartão SD

* **DS18B20** no `PINO_TEMP_SOLO` (GPIO 2), com **pull-up de 4,7 kΩ** entre dados e 3V3. A conversão é
  assíncrona (750 ms em 12 bits não cabem no slot de 400 ms). Sensor ausente → `TSOLO:-`.
* **microSD** (módulo SPI externo) num barramento próprio (FSPI), separado do rádio (HSPI). Uma linha por slot em
  `/telemetria.csv` (`;` como separador, decimal ponto), com os mesmos valores enviados ao gateway.
  Sem cartão o nó segue normal; o OLED mostra `SD:--` e a montagem é tentada de novo a cada 5 min.
  `USAR_SD 0` em `config.h` desliga o registro.

## Deep sleep

Preparado, desligado (`USAR_DEEP_SLEEP 0`). Ligar exige guardar a referência do ciclo em `RTC_DATA_ATTR`,
acordar `MARGEM_ACORDAR_MS` antes do beacon esperado e caber a reinicialização do rádio (~300 ms) dentro
dessa margem. Não ative sem medir o tempo real de boot da sua placa.
