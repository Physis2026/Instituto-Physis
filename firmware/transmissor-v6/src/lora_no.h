#pragma once
#include <Arduino.h>

// ══════════════════════════════════════════════════════════════════════════════
//  Camada de rádio do nó: TDMA escravo + recepção de comandos.
//
//  O nó nunca transmite quando quer. Ele ouve o beacon do receptor, calcula o
//  próprio slot dentro do ciclo e só abre a boca lá dentro — e só se a linha
//  (≤ ~110 ms no ar) ainda couber inteira no slot de 500 ms.
//
//  Exemplo com 3 nós descobertos (IDs 02, 07, 15) → ciclo de 5 s:
//    t=0    0,6s    1,1s    1,6s    2,1s          3,1s   3,3s       5s
//    ├BEACON┤guarda├─Nó 02─├─Nó 07─├─Nó 15─├─DESCOBERTA─┤folga├─…─CMDs─┤
//
//  O ciclo conta do INÍCIO do beacon (o instante do RxDone menos o tempo no ar),
//  o mesmo zero do receptor.
//
//  Sem beacon o nó entra em HOLDOVER: mantém a cadência pelo próprio relógio por
//  MAX_HOLDOVER_CICLOS e depois passa a sortear um jitter, para que dois nós
//  órfãos não colidam ciclo após ciclo no mesmo instante.
// ══════════════════════════════════════════════════════════════════════════════

void loraSetup();
void loraLoop();

// ── Estado, para o display e o diagnóstico ────────────────────────────────────
bool          tdmaSincronizado();
uint32_t      ciclosSemBeacon();
unsigned long cicloAtualMs();
unsigned long slotAtualMs();
float         rssiBeacon();
uint32_t      totalTransmitido();
uint32_t      totalComandosAceitos();

// ── Relógio ───────────────────────────────────────────────────────────────────
// O nó não tem RTC nem NTP: a hora chega no `TS:` do beacon ou num
// `CMD:<nn>:SYNC:<epoch>`. Enquanto `relogioValido()` for falso, a telemetria
// NÃO pode levar `TS:` — hora errada faz o watchdog do RPi marcar o nó offline
// achando que ele "não fala há dois anos" (PROTOCOLO.md §6.2).
bool     relogioValido();
uint32_t epochAtual();

// ── Implementadas em main.cpp (o rádio chama, a aplicação responde) ───────────

/// Chamada logo antes da transmissão do slot. Os sensores já são lidos a cada
/// INTERVALO_LEITURA_MS no `loop()`, então aqui não se lê nada (o slot é curto).
void prepararSlot();

/// Monta a linha de telemetria no formato do contrato.
String montarTelemetria();

/// Aplica uma ação já validada e endereçada a este nó (`SYNC`, `LIM1`, `LIM2`,
/// `IRR1`, `IRR2`, `MODO`, `PING`). Devolve `true` se algo mudou.
bool aplicarAcao(const String& acao, const String& arg);
