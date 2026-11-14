#include "temp_solo.h"
#include <OneWire.h>
#include <DallasTemperature.h>
#include "config.h"

static OneWire           _oneWire(PINO_TEMP_SOLO);
static DallasTemperature _sensores(&_oneWire);

static float         _temp            = 0.0f;
static bool          _valida          = false;
static unsigned long _ultimaBoa       = 0;
static bool          _convertendo     = false;
static unsigned long _inicioConversao = 0;
static unsigned long _esperaMs        = 750;

static void dispararConversao() {
  _sensores.requestTemperatures();  // não bloqueia: setWaitForConversion(false)
  _convertendo     = true;
  _inicioConversao = millis();
}

void tempSoloSetup() {
  _sensores.begin();
  _sensores.setResolution(RESOLUCAO_TEMP_SOLO);
  _sensores.setWaitForConversion(false);
  _esperaMs = _sensores.millisToWaitForConversion(RESOLUCAO_TEMP_SOLO) + 10;

  Serial.printf("[TSolo] %u sensor(es) DS18B20 no pino %d\n",
                (unsigned)_sensores.getDeviceCount(), PINO_TEMP_SOLO);
  dispararConversao();
}

void tempSoloLoop() {
  // Leitura velha demais deixa de valer: o painel mostra traço em vez de um
  // valor congelado de um sensor que caiu.
  if (_valida && millis() - _ultimaBoa > VALIDADE_TEMP_SOLO_MS) {
    _valida = false;
    Serial.println("[TSolo] Sem leitura recente — sensor desconectado?");
  }

  if (!_convertendo) {
    if (millis() - _inicioConversao >= INTERVALO_TEMP_SOLO_MS) {
      // Sem sensor no boot, procura de novo: permite ligar o DS18B20 depois.
      if (_sensores.getDeviceCount() == 0) _sensores.begin();
      dispararConversao();
    }
    return;
  }

  if (millis() - _inicioConversao < _esperaMs) return;
  _convertendo = false;

  float t = _sensores.getTempCByIndex(0);
  // -127 = DEVICE_DISCONNECTED_C; 85 = valor de power-on, lido quando a
  // conversão não chegou a acontecer. Nenhum dos dois é temperatura de solo.
  bool ok = (t != DEVICE_DISCONNECTED_C) && (t != 85.0f) && t > -55.0f && t < 125.0f;
  if (ok) {
    _temp      = t;
    _valida    = true;
    _ultimaBoa = millis();
  }
}

void tempSoloDiagnostico() {
  Serial.printf("[Diag] DS18B20 no GPIO %d\n", PINO_TEMP_SOLO);

  // Sem pull-up a linha OneWire flutua ou fica em 0 — e aí nenhum sensor
  // responde. É a causa nº 1 de "0 sensores".
  pinMode(PINO_TEMP_SOLO, INPUT);
  delay(2);
  bool alta = digitalRead(PINO_TEMP_SOLO) == HIGH;
  Serial.printf("[Diag]   linha em repouso: %s\n",
                alta ? "ALTA (pull-up ok)"
                     : "BAIXA -> falta o resistor de 4,7k para 3V3, sensor sem "
                       "alimentacao ou fio em curto");

  bool presenca = _oneWire.reset();
  Serial.printf("[Diag]   pulso de presenca: %s\n",
                presenca ? "SIM (ha algo no barramento)"
                         : "NAO -> nenhum dispositivo respondeu (fiacao/pino/alimentacao)");

  uint8_t addr[8];
  int     n = 0;
  _oneWire.reset_search();
  while (_oneWire.search(addr)) {
    n++;
    bool crcOk = OneWire::crc8(addr, 7) == addr[7];
    Serial.printf("[Diag]   #%d ROM %02X%02X%02X%02X%02X%02X%02X%02X  familia 0x%02X%s%s\n",
                  n, addr[0], addr[1], addr[2], addr[3], addr[4], addr[5], addr[6], addr[7],
                  addr[0], addr[0] == 0x28 ? " (DS18B20)" : " (NAO e DS18B20)",
                  crcOk ? "" : "  CRC INVALIDO -> ruido/fio longo");
  }
  if (n == 0) {
    Serial.println("[Diag]   nenhum endereco encontrado");
    return;
  }

  _sensores.begin();
  _sensores.setWaitForConversion(true);
  _sensores.requestTemperatures();
  float t = _sensores.getTempCByIndex(0);
  _sensores.setWaitForConversion(false);
  _convertendo     = false;
  _inicioConversao = millis();

  if (t == DEVICE_DISCONNECTED_C)
    Serial.println("[Diag]   leitura: -127 (sensor sumiu durante a leitura)");
  else if (t == 85.0f)
    Serial.println("[Diag]   leitura: 85.0 (valor de power-on -> alimentacao fraca/parasita)");
  else
    Serial.printf("[Diag]   leitura: %.2f C  OK\n", t);
}

bool  tempSoloValida() { return _valida; }
float tempSolo()       { return _temp; }
