#pragma once
#include <Arduino.h>
#include <WiFi.h>
#include "globals.h"

bool  setupSD();
bool  formatarSD();
void  salvarRegistroSD(const Registro& r);

/// Despeja no cartão o que ficou no buffer de RAM enquanto não havia SD.
/// Chamado sempre que o cartão passa a estar disponível.
void  flushBufferSD();

long  contarLinhasSD();
long  totalLinhasSD();
