#pragma once
#include <Arduino.h>

// ══════════════════════════════════════════════════════════════════════════════
//  Temperatura do SOLO — sensor DS18B20 (OneWire) em PINO_TEMP_SOLO.
//
//  O exemplo clássico da biblioteca chama `requestTemperatures()` em modo
//  bloqueante: o DS18B20 leva até 750 ms para converter em 12 bits. Isso não
//  cabe aqui — o nó se atualiza a cada segundo e o slot TDMA tem 400 ms. Por
//  isso a conversão é ASSÍNCRONA: `tempSoloLoop()` dispara a conversão, volta
//  na hora certa para ler, e a atualização do nó só consome o último valor
//  pronto, sem esperar nada.
// ══════════════════════════════════════════════════════════════════════════════

void tempSoloSetup();
void tempSoloLoop();

/// `true` enquanto houver uma leitura recente e plausível. Sensor desconectado
/// (-127 °C) ou recém-energizado (85 °C) não conta como leitura.
bool  tempSoloValida();
float tempSolo();

/// Diagnóstico pela serial: nível da linha em repouso (pull-up), pulso de
/// presença, endereços no barramento e uma leitura bloqueante. Trava ~750 ms.
void tempSoloDiagnostico();
