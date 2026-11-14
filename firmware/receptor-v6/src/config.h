#pragma once

// ══════════════════════════════════════════════════════════════════════════════
//  RECEPTOR / GATEWAY V6 — Heltec WiFi LoRa 32 V3 (ESP32-S3 + SX1262)
//  Par do firmware `Transmissor V6 - No LoRa V3`.
//
//  Recebe os nós de campo em janelas TDMA separadas, acrescenta RSSI/SNR à
//  linha, serve o painel local e conversa com o controle central no Raspberry Pi
//  (`Claude Worktree/controle-central`). Contrato de linha: `PROTOCOLO.md`.
// ══════════════════════════════════════════════════════════════════════════════

// ── Parâmetros LoRa (iguais nos 5 dispositivos — PROTOCOLO.md §1.2) ──────────
#define BAND        915.0
#define SYNC_WORD   0x12
#define SPREADING   7
#define BANDWIDTH   250.0
#define CODING_RATE 5
#define TX_POWER    14

// ── Rede ──────────────────────────────────────────────────────────────────────
// Teto do protocolo: `ID:` tem dois digitos, `01`..`99`, e `00` e o broadcast de
// comando. Passar de 99 exigiria mudar o contrato de linha (PROTOCOLO.md §2.3).
// PRECISA bater com TOTAL_NOS do `.env` do Raspberry Pi e com o dos nos.
#define TOTAL_NOS 99

// ── TDMA ──────────────────────────────────────────────────────────────────────
//  Exemplo com 3 nós descobertos (IDs 02, 07 e 15) → ciclo de 5 s:
//  t=0    0,6s     1,1s     1,6s     2,1s           3,1s  3,3s        5s
//  ├BEACON┤ guarda ├─Nó 02─►├─Nó 07─►├─Nó 15─►├─DESCOBERTA─►│folga├…─CMDs─►│
//
//  Os slots são só dos nós DESCOBERTOS, em ordem de ID — o beacon leva o mapa
//  deles (campo MAP) e cada nó conta quantos descobertos têm ID menor que o
//  seu para achar a própria posição. Um nó que ainda não está no mapa fala na
//  janela de DESCOBERTA, num instante sorteado; ouvido uma vez, entra no mapa
//  do beacon seguinte e ganha slot próprio.
//
//  Estes valores viajam DENTRO do beacon (campos CIC/SLOT/GRD/DSC/MAP), então
//  mudar o ciclo aqui não exige regravar os nós — basta regravar o receptor.
//
//  ⚠ WATCHDOG_TIMEOUT_S no .env do Pi precisa cobrir 3 ciclos: com a rede
//    toda descoberta (99 nós, CICLO_MAX_MS = 53 s) são 160 s.
// Slot de 500 ms: o maior payload previsto (120 B) leva ~100 ms no ar em
// SF7/BW250/CR4-5, e a leitura dos sensores no no antes de transmitir custa
// outros ~40 ms no pior caso. Sobra mais de 3x de folga.
#define SLOT_MS              500UL
#define GUARDA_MS            600UL
#define JANELA_DESCOBERTA_MS 1000UL   // nós fora do mapa, em instante sorteado
#define JANELA_CMD_MS        1200UL   // downlink no fim do ciclo, com todos ouvindo

// Folga entre o fim da descoberta e a janela de comandos. Um nó novo pode
// começar a falar até 750 ms dentro da descoberta e ficar ~110 ms no ar; sem
// esta folga, com número PAR de descobertos, a janela de comandos começava
// colada no fim da descoberta e sobravam ~50 ms para qualquer atraso.
#define FOLGA_PRE_CMD_MS      200UL

// O ciclo é VARIÁVEL: muda a cada nó DESCOBERTO, 1 s a cada dois nós
// (arredondado para cima ao segundo inteiro). Nenhum nó → 3 s; 1–2 → 4 s;
// 3–4 → 5 s; ... 99 → 53 s. A conta é feita a cada beacon, em lora.cpp.
// O nó usa a mesma conta como padrão antes do primeiro beacon (CICLO_MS_PADRAO).
#define CICLO_DE(nDescobertos) \
  ((GUARDA_MS + (unsigned long)(nDescobertos) * SLOT_MS + JANELA_DESCOBERTA_MS + \
    FOLGA_PRE_CMD_MS + JANELA_CMD_MS + 999UL) / 1000UL * 1000UL)
#define CICLO_MAX_MS CICLO_DE(TOTAL_NOS)

// Com 99 nos a fila de downlink precisa dar vazao: a janela cabe
// JANELA_CMD_MS / ESPACO_CMD_MS comandos por ciclo.
#define MAX_CMD_POR_CICLO      6
#define ESPACO_CMD_MS       150UL
#define CMD_LINHA_MAX        48      // "CMD:00:SYNC:4102444800" tem 22

// Depois de um PING ENDEREÇADO o nó responde em ATRASO_PING_MS (150 ms, no
// config.h do nó) e fica ~110 ms no ar. Mandar o próximo comando em
// ESPACO_CMD_MS (também 150 ms) caía exatamente em cima da resposta. Este
// silêncio cobre atraso + resposta + folga; um PING endereçado sem esse tempo
// antes do fim do ciclo fica para o ciclo seguinte.
#define ESPERA_RESPOSTA_PING_MS 400UL

// ── Tarefa do rádio ───────────────────────────────────────────────────────────
// O TDMA roda numa tarefa própria (ver lora.cpp), acima do loop do Arduino,
// que trava segundos em HTTP, HTTPS e cartão. O que ela recebe espera o loop
// nesta fila: 48 linhas = ~25 s da rede cheia (99 nós a cada 53 s).
#define TDMA_PRIORIDADE      2       // loop do Arduino = 1
#define TDMA_PILHA        6144
#define FILA_RX_TAM         48

// Ciclos seguidos sem ouvir UM nó antes de marcá-lo offline (os outros seguem
// online). Contado em ciclos, não em tempo, porque a duração do ciclo varia.
#define CICLOS_PARA_OFFLINE 3

// ── WiFi ──────────────────────────────────────────────────────────────────────
//  Segredos (WIFI_SSID, WIFI_PASS, AP_PASS, WA_NUMERO, WA_APIKEY,
//  WEATHER_API_KEY) NÃO ficam neste arquivo. Ficam em `src/secrets.h`, que o
//  Git ignora. Modelo: `src/secrets.example.h`. Sem o secrets.h o firmware
//  não compila, de propósito: nunca sai uma placa com senha de fábrica.
//  As chaves antigas já estiveram em arquivos compartilhados: ROTACIONE-AS.
//    Também podem ser sobrescritos por `build_flags` no platformio.ini local, ex.:
//        build_flags = -D WIFI_PASS=\"outra-senha\"
//    O SSID/senha da rede STA também podem ser gravados pela página /wifi-setup,
//    que tem precedência sobre estes valores.
#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "Falta src/secrets.h: copie src/secrets.example.h para src/secrets.h e preencha."
#endif
#if !defined(WIFI_SSID) || !defined(WIFI_PASS) || !defined(AP_PASS) || \
    !defined(WA_NUMERO) || !defined(WA_APIKEY) || !defined(WEATHER_API_KEY)
#error "src/secrets.h incompleto: confira com src/secrets.example.h."
#endif

// O AP fica SEMPRE no ar, junto com o STA: é por ele que o painel local
// continua acessível quando a rede da fazenda cai, e é o endereço de fábrica
// que o controle-central procura (GATEWAY_HTTP_URL=http://192.168.4.1).
#ifndef AP_SSID
#define AP_SSID "ESP32_IRRIGA_V3"
#endif

// ── Controle central (Raspberry Pi) ───────────────────────────────────────────
// O receptor entrega os dados por DOIS caminhos, de propósito:
//   1. PUSH  — POST das linhas do ciclo em http://<host>:<porta>/api/gateway/webhook
//   2. PULL  — o Pi busca GET /api/leituras e ouve GET /eventos aqui no receptor,
//              e manda comandos em POST /api/comando
// Se um cair, o outro sustenta. O Pi deduplica por (node_id, timestamp, tipo).
// Host e porta são editáveis em /config e ficam na NVS.
#ifndef PI_HOST_PADRAO
#define PI_HOST_PADRAO "192.168.0.106"   // o Pi entrando no AP do receptor
#endif
#define PI_PORTA_PADRAO 8700
#define PI_ROTA_WEBHOOK "/api/gateway/webhook"
#define PI_TIMEOUT_MS   4000
#define PI_ATIVO_PADRAO true

// Buffer circular das linhas de telemetria: serve o polling do Pi, o SSE e o
// reenvio do push. Dois ciclos completos da rede, com piso de 48 para redes
// pequenas. Com 99 nos sao 198 linhas x 200 B = ~39 KB de RAM estatica.
//
// 200 e nao 160: a linha do Transmissor V6 ganhou `TSOLO:` e, somada a BAT, TS
// e ao RSSI/SNR que o gateway acrescenta, chega a ~154 B no pior caso (P1/P2 no
// teto de 43200.0). 160 truncaria a linha EM SILENCIO no primeiro campo novo —
// cortando justamente RSSI/SNR, que ficam no fim.
#define FILA_TAM       (TOTAL_NOS * 2 < 48 ? 48 : TOTAL_NOS * 2)
#define FILA_LINHA_MAX 200

// ── WhatsApp CallMeBot ────────────────────────────────────────────────────────
// WA_NUMERO e WA_APIKEY: em src/secrets.h.
#define INTERVALO_ALERTA_MS 3600000

// ── Histórico em RAM (fallback quando não há SD) ──────────────────────────────
#define MAX_REGISTROS_RAM 50

// ── Tipos de registro ─────────────────────────────────────────────────────────
#define REGISTRO_LEITURA 0
#define REGISTRO_EVENTO  1

// ── SD Card ───────────────────────────────────────────────────────────────────
#define SD_MISO_PIN 37
#define SD_MOSI_PIN 38
#define SD_SCK_PIN  39
#define SD_CS_PIN   40

// ── Arquivos no SD ────────────────────────────────────────────────────────────
// A coluna `No` vai no FIM, na mesma posição do CSV do controle central
// (PROTOCOLO.md §7.1): inserir na frente deslocaria os índices e quebraria o
// parser posicional do dashboard_irrigacaov2.html. `UmidAr` vem depois dela, e
// `TempSolo` (DS18B20 do Transmissor V6) depois de `UmidAr` — 14 colunas.
// Um cartão com o cabeçalho antigo (13 colunas) é arquivado no boot, não
// misturado: ver `arquivarHistoricoAntigo()` em sdcard.cpp.
#define ARQUIVO_DADOS     "/dados.csv"
#define ARQUIVO_DADOS_V1  "/dados_v1.csv"   // histórico de antes do multi-nó
#define ARQUIVO_CABECALHO "Data/Hora;Tipo;Umidade1 (%);Irrigando1;Limite1 (%);Umidade2 (%);Irrigando2;Limite2 (%);Temp (C);Prev1 (min);Prev2 (min);No;UmidAr (%);TempSolo (C)\n"
#define ARQUIVO_COLUNAS   14
#define REGISTROS_POR_PAGINA 1000

// ── Rainbow Weather API ───────────────────────────────────────────────────────
// WEATHER_API_KEY: em src/secrets.h.
#define WEATHER_LAT           -15.7801f
#define WEATHER_LON           -47.9292f
#define WEATHER_INTERVALO_MS  3600000UL
#define WEATHER_PRECIP_LIMIAR 0.1f
// Idade máxima da última consulta BEM-SUCEDIDA para a chuva valer. Sem isto um
// "vai chover" ficava valendo para sempre quando a internet caía depois dele:
// o `CH:1` ia em todo beacon, o nó renovava a própria validade a cada ciclo e
// nenhum setor irrigava até a internet voltar. 1,5× o intervalo tolera uma
// consulta perdida.
#define WEATHER_VALIDADE_MS   (WEATHER_INTERVALO_MS * 3UL / 2UL)

// ── Limiar padrão ─────────────────────────────────────────────────────────────
#define LIMITE_UMIDADE_PADRAO 30.0f
