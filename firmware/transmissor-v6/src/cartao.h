#pragma once
#include <Arduino.h>

// ══════════════════════════════════════════════════════════════════════════════
//  Registro local em cartão microSD (módulo SPI externo — o Heltec V3 não tem
//  slot próprio).
//
//  O SD usa um barramento SPI SEPARADO (FSPI) do rádio (que fica no HSPI),
//  para que uma escrita lenta ou um cartão com defeito nunca segure o SX1262. Sem cartão o nó segue
//  funcionando normalmente: a falha só aparece na serial e no display, e a
//  montagem é tentada de novo de tempos em tempos (cartão inserido depois).
//
//  Arquivo: ARQUIVO_SD, CSV separado por `;`, decimal PONTO, uma linha por
//  slot (o mesmo instante dos valores enviados ao gateway).
// ══════════════════════════════════════════════════════════════════════════════

void cartaoSetup();

/// Acrescenta uma linha (sem o `\n`). Devolve `false` se o cartão não está
/// disponível ou a escrita falhou.
bool cartaoGravar(const String& linha);

bool cartaoOk();
