#pragma once
#include <Arduino.h>

// ══════════════════════════════════════════════════════════════════════════════
//  Previsão de chuva — o nó não tem WiFi.
//
//  Quem consulta a API de nowcast é o receptor; a flag chega em CADA beacon, no
//  campo `CH:<0|1>`. No V4 isso era um `CMD:01:CHUVA:` endereçado a um nó só;
//  agora uma transmissão informa a rede inteira.
// ══════════════════════════════════════════════════════════════════════════════

void setChuvaFlag(bool chuva);
bool chuvaVemAi();

/// Idade da última informação de chuva, em ms. Depois de muito tempo sem beacon
/// a flag deixa de ser confiável e a irrigação volta a decidir sozinha.
unsigned long idadeInfoChuva();
