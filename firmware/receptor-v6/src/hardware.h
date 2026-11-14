#pragma once
#include <Arduino.h>
#include <RadioLib.h>
#include "SSD1306Wire.h"

// ══════════════════════════════════════════════════════════════════════════════
//  `heltec_unofficial.h` DEFINE (não declara) `radio`, `display` e `button`
//  direto no cabeçalho, sem `inline`. Incluí-lo em mais de um .cpp gera erro de
//  símbolo duplicado no link.
//
//  Regra do projeto: `heltec_unofficial.h` é incluído SÓ em `main.cpp`.
//  Qualquer outro arquivo que precise do rádio ou do display inclui este aqui.
// ══════════════════════════════════════════════════════════════════════════════

extern SX1262      radio;
extern SSD1306Wire display;
