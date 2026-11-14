#include "cartao.h"
#include <SPI.h>
#include <SD.h>
#include "config.h"

// FSPI, NÃO HSPI: o `heltec_unofficial.h` põe o SX1262 no HSPI (o define de
// board que ele testa não bate com `heltec_wifi_lora_32_V3`). Um segundo
// SPIClass no HSPI remapeia os pinos do rádio e o `radio.begin()` falha com -2.
static SPIClass      _spiSD(FSPI);
static bool          _montado        = false;
static unsigned long _ultimaTentativa = 0;
static bool          _jaTentou       = false;

static const char* CABECALHO =
    "millis;epoch;U1;U2;T;UAR;TSOLO;IR1;P1;P2;LIM1;LIM2;BAT";

static bool montar() {
  _jaTentou        = true;
  _ultimaTentativa = millis();

  if (!SD.begin(PINO_SD_CS, _spiSD, 4000000)) {
    Serial.println("[SD] Cartao nao encontrado — registro local desligado");
    SD.end();
    return false;
  }

  // Arquivo novo ganha cabeçalho; existente só recebe linhas no fim.
  if (!SD.exists(ARQUIVO_SD)) {
    File f = SD.open(ARQUIVO_SD, FILE_WRITE);
    if (!f) { SD.end(); return false; }
    f.println(CABECALHO);
    f.close();
  }
  Serial.printf("[SD] Cartao montado (%llu MB) — gravando em %s\n",
                SD.cardSize() / (1024ULL * 1024ULL), ARQUIVO_SD);
  return true;
}

void cartaoSetup() {
  _spiSD.begin(PINO_SD_SCK, PINO_SD_MISO, PINO_SD_MOSI, PINO_SD_CS);
  _montado = montar();
}

bool cartaoGravar(const String& linha) {
  if (!_montado) {
    // SD.begin sem cartão demora; não insistir a cada slot.
    if (_jaTentou && millis() - _ultimaTentativa < RETENTAR_SD_MS) return false;
    _montado = montar();
    if (!_montado) return false;
  }

  File f = SD.open(ARQUIVO_SD, FILE_APPEND);
  if (!f) {
    Serial.println("[SD] Falha ao abrir arquivo — cartao removido?");
    SD.end();
    _montado = false;
    return false;
  }
  size_t n = f.println(linha);
  f.close();

  if (n == 0) {
    Serial.println("[SD] Falha de escrita");
    SD.end();
    _montado = false;
    return false;
  }
  return true;
}

bool cartaoOk() { return _montado; }
