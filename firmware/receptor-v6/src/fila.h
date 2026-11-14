#pragma once
#include <Arduino.h>
#include "config.h"

// ══════════════════════════════════════════════════════════════════════════════
//  Buffer circular das linhas de telemetria prontas para o controle central.
//
//  Cada linha recebe uma sequência monotônica. Isso serve três consumidores ao
//  mesmo tempo, cada um com o próprio cursor:
//
//    · `GET /api/leituras?desde=<cursor>` — o polling do Raspberry Pi
//    · `GET /eventos`                     — o SSE que o Pi escuta
//    · o push em `POST /api/gateway/webhook`, que reenvia o que ainda não saiu
//
//  Reenviar é seguro: o banco do Pi tem chave única (node_id, timestamp, tipo) e
//  descarta a cópia — desde que o nó esteja mandando `TS:` (PROTOCOLO.md §2.7).
// ══════════════════════════════════════════════════════════════════════════════

void filaAdicionar(const String& linha);

uint32_t filaUltimoSeq();

/// Copia até `max` linhas com sequência **maior** que `desde`, da mais antiga
/// para a mais nova. Devolve quantas copiou e escreve em `ultimo` a maior
/// sequência copiada (ou `desde`, se nada saiu).
int filaDesde(uint32_t desde, String* saida, int max, uint32_t& ultimo);

/// Percorre as linhas com sequencia maior que `desde`, da mais antiga para a
/// mais nova, SEM alocar nada.
///
/// `filaDesde` enche um `String[]`, o que so serve para lotes pequenos: com 99
/// nos a fila tem ~200 posicoes, e um `String lote[FILA_TAM]` na pilha da task
/// (8 KB por padrao no Arduino-ESP32) estoura antes de chegar na metade. Quem
/// entrega ao cliente HTTP usa este percurso e escreve direto no socket.
///
/// `cb` devolve `false` para interromper. `ultimo` recebe a maior sequencia
/// visitada.
void filaPercorrer(uint32_t desde, uint32_t& ultimo,
                   bool (*cb)(const char* linha, uint32_t seq, void* ctx),
                   void* ctx);

// ── Cursor do push para o Pi ──────────────────────────────────────────────────
int      filaPendentesPi(String* saida, int max, uint32_t& ate);
void     filaMarcarEnviado(uint32_t ate);
uint32_t filaPendentesPiTotal();

/// Maior sequência que o Raspberry Pi já **confirmou** ter recebido pelo push.
///
/// Serve de piso para o polling e para o SSE: sem isso, com os dois caminhos
/// ligados a mesma linha chega duas vezes ao Pi. A dedupe do banco de lá só
/// resolve isso quando o nó manda `TS:` — sem relógio, o carimbo é o instante de
/// recepção e as duas cópias entram como leituras distintas (PROTOCOLO.md §2.7).
uint32_t filaEnviadoAte();
