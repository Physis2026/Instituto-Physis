#include "weather.h"
#include <limits.h>

static bool          _chuvaEsperada = false;
static bool          _jaRecebeu     = false;
static unsigned long _recebidaEm    = 0;

/// Depois disso a informação de chuva é velha demais para inibir irrigação.
static const unsigned long VALIDADE_MS = 30UL * 60UL * 1000UL;  // 30 min

void setChuvaFlag(bool chuva) {
  if (chuva != _chuvaEsperada || !_jaRecebeu) {
    Serial.printf("[Clima] Previsao de chuva: %s (via beacon)\n", chuva ? "SIM" : "NAO");
  }
  _chuvaEsperada = chuva;
  _jaRecebeu     = true;
  _recebidaEm    = millis();
}

bool chuvaVemAi() {
  if (!_jaRecebeu) return false;
  if (millis() - _recebidaEm > VALIDADE_MS) return false;
  return _chuvaEsperada;
}

unsigned long idadeInfoChuva() {
  if (!_jaRecebeu) return ULONG_MAX;
  return millis() - _recebidaEm;
}
