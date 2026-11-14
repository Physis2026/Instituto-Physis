#pragma once
#include <Arduino.h>

struct ClimaAtual {
  String        intensidade;    // "none", "light", "moderate", "heavy"
  float         precipMax;      // mm/h máximo previsto nas próximas 4h
  bool          chuvaEsperada;
  bool          valido;         // já houve UMA resposta boa desde o boot
  unsigned long ultimaConsulta; // última tentativa, boa ou não
  String        horaConsulta;   // "HH:MM" da última atualização
  unsigned long ultimoSucesso;  // millis da última resposta boa
};

extern ClimaAtual clima;
extern float weatherLat;
extern float weatherLon;
extern bool  reqAtualizarClima;

void atualizarClima();

/// Há previsão e ela tem menos de WEATHER_VALIDADE_MS. Previsão velha não
/// vale nada — nem para inibir irrigação, nem para alertar.
bool climaAtual();

/// Chuva prevista numa previsão ATUAL. É o que vai no `CH:` do beacon.
bool chuvaVemAi();
void inicializarLocalizacao();
void salvarLocalizacao(float lat, float lon);
