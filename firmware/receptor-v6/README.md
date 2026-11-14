# Receptor / Gateway V6 — Heltec WiFi LoRa 32 V3

Recebe os **nós de campo** (até 99) (`Transmissor V6 - No LoRa V3`), grava o histórico no cartão SD, serve o
painel local e faz a ponte com o **controle central** no Raspberry Pi
(`Claude Worktree/controle-central`).

Contrato de linha: `controle-central/PROTOCOLO.md`. Fonte da verdade do parser: `app/protocolo.py`.

## O que mudou no V6 (acompanhando o `Transmissor V6 - No LoRa V3`)

O nó V6 ganhou um **DS18B20** (temperatura do solo) e passou a enviar a chave `TSOLO:`:

```
ID:03,U1:45.2,IR1:1,U2:50.0,IR2:0,T:27.5,UAR:63.5,TSOLO:23.1,P1:12.5,P2:-1,LIM1:30.0,LIM2:30.0,BAT:3.87,TS:1786000000
```

| Onde | O que mudou |
|---|---|
| Estado do nó | `NoRede::tempSolo`; `TSOLO:-` (sensor ausente) vira vazio, não 0 °C |
| Painel `/` | coluna **Solo** na tabela; **Temp solo °C** no detalhe do nó |
| JSON | `ts` no resumo (`/data`, `/events`), `tsolo` em `/api/no` |
| Cartão SD | `/dados.csv` ganhou a 14ª coluna `TempSolo (C)` no fim. Um cartão com o arquivo de 13 colunas é **arquivado** como `/dados_vN.csv` no primeiro boot |
| Fila para o Pi | `FILA_LINHA_MAX` 160 → 200 B: com `TSOLO` a linha + `RSSI`/`SNR` passa de 150 B e seria truncada em silêncio |

O Raspberry não precisa de mudança: `TSOLO` é chave de extensão e vai para `extras`, e o gateway
repassa a linha inteira.

O cartão SD do próprio nó (`/telemetria.csv`) é independente deste aqui; os dois não se falam.

## Compatibilidade com o Transmissor V6 (revisão de 26/10/2026)

Campos, comandos e parâmetros de rádio já batiam. O que falhava era o funcionamento conjunto. **Regrave os dois
lados juntos** (receptor e nós): o cronograma do nó e o deste receptor mudaram em conjunto.

| Problema | Correção |
|---|---|
| O loop trava segundos (POST ao Pi, HTTPS do clima, WhatsApp, download do CSV); com o rádio dentro dele, o beacon atrasava, os slots dos nós invadiam a janela de comandos e o SX1262 sobrescrevia pacotes | O TDMA roda numa **tarefa FreeRTOS própria**, acima do loop; o que ela recebe espera o loop numa fila de 48 linhas (`linhasRxDescartadas()` em `/data` → `tdma.rxDescartados` deve ficar em 0). O `/download` e o `/file-get` mandam o arquivo **em partes**, uma por volta do loop |
| "Vai chover" ficava valendo para sempre quando a internet caía depois dele: `CH:1` em todo beacon, nenhum nó irrigava | A previsão vale `WEATHER_VALIDADE_MS` (1,5 h) a partir da última consulta **bem-sucedida** |
| Resposta a PING endereçado (150 ms) colidia com o comando seguinte (também 150 ms) | Depois de um PING endereçado o receptor fica `ESPERA_RESPOSTA_PING_MS` (400 ms) calado; sem esse tempo antes do fim do ciclo, o PING fica para o próximo |
| Folga de ~50 ms entre a janela de descoberta e a de comandos | `FOLGA_PRE_CMD_MS` (200 ms) no ciclo — os tamanhos de ciclo não mudaram; o nó também passou a datar o beacon pela interrupção, descontando o tempo no ar |
| Canal 1 com sentido diferente: no nó, `LIM1`/`P1`/`IR1` valem para a **média** dos dois sensores; aqui o alerta e o "mais seco" comparavam o sensor A (`U1`) com `LIM1` | `umidadeControle()` (a mesma média do nó) no alerta, no OLED e no detalhe do painel ("Média (controle)", campo `um` em `/api/no`) |
| `LIM1:abc` era aceito aqui e recusado no nó — e o Pi dava por confirmado | A validação do argumento (`argumentoValido()`) é a **mesma** nos dois `protocolo.cpp`; o receptor normaliza a linha antes de pôr no ar |
| `P1:-1` significava "aprendendo" e também "sem sensor" | O nó manda `-` sem leitura e `-1` aprendendo; o painel mostra `--` e `Aprend.` |
| SYNC ia para o ar com a hora de quando entrou na fila | O epoch é carimbado na hora da transmissão |
| Sem internet no boot, NTP nunca era armado e o STA nunca era retentado | NTP armado sempre; o STA é retentado em provisionamento (5 min com o AP vazio, 30 min com alguém nele) |
| RadioLib 7.6.0 aqui, 7.7.1 no nó | Fixada em `7.7.1` nos dois `platformio.ini` |

## O que mudou no V5 em relação às versões anteriores

| Antes | Agora |
|---|---|
| `no1`/`no2` eram os **dois sensores de uma placa**, tratados como se fossem dois nós | `nos[4]`, um por transmissor, cada um com dois canais |
| O campo `ID:` do payload era transmitido mas **nunca lido** | O `ID:` decide o nó; linha sem `ID:` válido é **descartada com log**, não creditada ao nó 1 |
| `enviarComando()` cravava `CMD:01:` | Comando endereçado, validado contra as 7 ações do contrato |
| Fila de comando de **uma posição** — dois comandos seguidos e o primeiro sumia | FIFO de 16, drenada na janela de downlink |
| Transmissões livres — 4 nós colidiriam no ar | **TDMA**: beacon do gateway + um slot por nó |
| AP era derrubado quando o STA conectava | **AP + STA sempre juntos** |
| Sem caminho para o Raspberry Pi | Push (webhook) **e** API de gateway (polling/SSE/comando) |
| `verificarOnline()` e `flushBufferSD()` eram código morto | Ambos rodam; o offline é **por nó** |

## TDMA

```
Exemplo: 3 nós descobertos (IDs 02, 07, 15) → ciclo de 5 s
t=0    0,6s    1,1s    1,6s    2,1s          3,1s  3,3s       3,8s     5s
├BEACON┤guarda├─Nó 02─├─Nó 07─├─Nó 15─├─DESCOBERTA─┤folga├(sobra)├─CMDs─┤
```

O ciclo é **variável: muda a cada nó descoberto**, 1 s a cada dois nós (slot de 500 ms;
`guarda + N × slot + descoberta + folga + janela de comandos`, arredondado para o segundo inteiro). Nenhum nó →
3 s; 1–2 → 4 s; 3–4 → 5 s; 99 → 53 s. Só os nós que já falaram (`conhecido`, na NVS) têm slot, em ordem
de ID: o beacon leva o mapa deles e cada nó conta quantos descobertos têm ID menor que o seu. Um nó fora
do mapa fala na **janela de descoberta** (1 s, logo depois do último slot) num instante sorteado; ouvido
uma vez, entra no mapa do beacon seguinte. Um nó cai para offline depois de `CICLOS_PARA_OFFLINE` (3)
ciclos seguidos sem falar. "Esquecer nós offline" em `/config` tira os mudos do mapa e encurta o ciclo.

O beacon (`BCN:<seq>,TS:<epoch>,CH:<0|1>,CIC:<ms>,SLOT:<ms>,GRD:<ms>,DSC:<ms>,MAP:<hex>`) carrega o relógio, a previsão de
chuva e o próprio cronograma. Como o cronograma viaja no beacon, **mudar o ciclo exige regravar só esta
placa** — os nós se ajustam sozinhos.

Os comandos vão para o ar na janela final do ciclo, quando os nós estão ouvindo e nenhum transmite: até
6 por ciclo, 150 ms entre eles, 400 ms depois de um PING endereçado (o tempo da resposta).

O TDMA roda numa tarefa própria (`tarefaRadio` em `lora.cpp`), com prioridade acima do loop do Arduino: é a
única que toca no rádio. Nada no loop — HTTP, HTTPS, cartão, servidor web — atrasa o beacon.

> ⚠ **`WATCHDOG_TIMEOUT_S` no `.env` do Raspberry precisa cobrir três ciclos.** Com a rede toda
> descoberta (`CICLO_MAX_MS`): **99 nós (53 s) → 160 s**; com 10 nós (8 s) bastam 30 s. Deixar o padrão de 15 s faz os nós piscarem
> offline sem parar e torra o cooldown do WhatsApp com alarme falso.

## Rotas

### Painel local

| Rota | O que é |
|---|---|
| `GET /` | tabela compacta de todos os nós, com filtros e detalhe ao clicar |
| `GET /events` | SSE do navegador (JSON completo do painel) |
| `GET /data` | o mesmo JSON, sob demanda |
| `GET /tabela?p=&no=` | histórico do SD paginado, com filtro por nó |
| `GET /download` | CSV completo (14 colunas, `No`, `Umid. ar` e `Temp solo` no fim) |
| `GET /config` | host do Raspberry, diagnóstico do TDMA, WiFi |
| `GET /files`, `/file-*`, `/format-sd`, `/ejetar` | gerenciador do cartão SD |

### API de gateway — o que o Raspberry Pi consome

| Rota | O que é |
|---|---|
| `GET /api/leituras?desde=<cursor>` | polling: `{"leituras":[...], "cursor":N}` |
| `GET /eventos` | SSE de **linhas de telemetria** (não confundir com `/events`) |
| `POST /api/comando` | `{"comando":"CMD:02:LIM1:35"}` → janela de downlink |
| `GET /api/estado` | diagnóstico completo do enlace, com o estado de cada nó |
| `GET /api/no?id=N` | detalhe de um nó (o resumo do painel não carrega tudo) |
| `POST /api/data` | injeção manual de uma linha, para bancada sem rádio |
| `POST /api/localizacao` | `lat=..&lon=..` — ponto do nowcast de chuva (NVS); o mapa fica em `/config` |
| `POST /api/nos/esquecer` | tira do painel os nós conhecidos que estão offline |

E, no sentido inverso, o gateway faz `POST http://<pi>:8700/api/gateway/webhook` a cada ciclo.

**Os dois caminhos convivem sem duplicar dado:** o polling e o SSE só entregam o que o push ainda não
confirmou. Sem esse piso, a mesma linha chegaria duas vezes ao Pi — e a dedupe do banco de lá só resolve
isso quando o nó manda `TS:`; sem relógio, o carimbo é o instante de recepção e as duas cópias entram
como leituras distintas.

## Rede

O AP `ESP32_IRRIGA_V3` (192.168.4.1) fica **sempre** no ar, junto com o STA. Isso cobre os dois cenários:

* **Sem rede local** — o Raspberry entra no AP do receptor e usa o default de fábrica dele,
  `GATEWAY_HTTP_URL=http://192.168.4.1`. Zero configuração. O push aponta para `192.168.4.2`.
* **Com rede da fazenda (recomendado)** — reserve IP fixo para o receptor no roteador e aponte
  `GATEWAY_HTTP_URL` para ele. Existe mDNS (`irrigacao.local`), mas o cliente HTTP do Pi pode não
  resolver `.local` — use o IP.

Sem STA o gateway continua inteiro: recebe os nós, grava no SD e serve o Raspberry pelo AP. O que se
perde é NTP, previsão de chuva e alerta de WhatsApp — e a página principal avisa isso numa faixa. Uma
previsão de chuva com mais de 1,5 h deixa de inibir a irrigação. O STA continua sendo retentado (a cada
30 s depois de uma queda; a cada 5 ou 30 min se nunca conectou desde o boot), e o NTP acerta o relógio
sozinho quando a rede volta.

## Cartão SD

`/dados.csv`, separado por `;`, com 14 colunas. `No`, `UmidAr` e `TempSolo` entram **no fim** para não deslocar os
índices que o `dashboard_irrigacaov2.html` lê por posição.

Se o cartão tiver um `/dados.csv` do formato antigo, ele é **arquivado** como `/dados_v1.csv` (ou `_v2`,
`_v3`…) e um novo é criado — misturar duas larguras de linha quebra qualquer leitor.

## Segurança — leia antes de ir a campo

* **Os segredos em `src/config.h` já estiveram versionados: rotacione-os.** Senha do WiFi, API key do
  CallMeBot e do Rainbow. Todos podem ser sobrescritos por `build_flags` no `platformio.ini` local, sem
  tocar no código — o cabeçalho do arquivo mostra como.
* **Nenhuma rota tem autenticação**, incluindo `/format-sd`, `/file-delete`, `/file-upload` e
  `/wifi-disconnect`. O modelo previsto é **rede local apenas**: coloque o gateway e o Raspberry numa
  VLAN ou num WiFi separado.
* A senha do AP é a de fábrica (`12345678`). Troque-a via `-D AP_PASS=...`.
