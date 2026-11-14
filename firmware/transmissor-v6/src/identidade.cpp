#include "identidade.h"
#include "config.h"
#include <Preferences.h>

#define CHAVE_ID "node_id"

static uint8_t _id   = 0;
static bool    _fixo = false;

// ─── Leitura ─────────────────────────────────────────────────────────────────

void identidadeSetup() {
#ifdef NODE_ID
  // O binário manda: uma placa gravada com -D NODE_ID é o que ela é, e mexer
  // nisso por serial só criaria divergência entre a etiqueta e o firmware.
  _id   = (uint8_t)NODE_ID;
  _fixo = true;
  Serial.printf("[ID] No %02u (fixo em compilacao)\n", _id);
  return;
#else
  _fixo = false;
  Preferences p;
  if (p.begin(NVS_NAMESPACE, true)) {
    _id = (uint8_t)p.getUChar(CHAVE_ID, 0);
    p.end();
  }
  if (_id >= 1 && _id <= TOTAL_NOS) {
    Serial.printf("[ID] No %02u (da NVS)\n", _id);
  } else {
    _id = 0;
    Serial.println();
    Serial.println("[ID] *** PLACA NAO COMISSIONADA ***");
    Serial.println("[ID] O no nao vai transmitir ate receber um numero.");
    Serial.printf ("[ID] Digite:  id <1..%d>   (ex.: id 7)\n", TOTAL_NOS);
    Serial.println();
  }
#endif
}

uint8_t noId()                      { return _id; }
bool    noComissionado()            { return _id >= 1 && _id <= TOTAL_NOS; }
bool    identidadeFixaEmCompilacao(){ return _fixo; }

// ─── Escrita ─────────────────────────────────────────────────────────────────

bool definirNoId(uint8_t novo) {
  if (_fixo) {
    Serial.println("[ID] Recusado: identidade fixada em compilacao (-D NODE_ID).");
    return false;
  }
  if (novo < 1 || novo > TOTAL_NOS) {
    Serial.printf("[ID] Recusado: %u fora da faixa 1..%d.\n", novo, TOTAL_NOS);
    return false;
  }

  Preferences p;
  if (!p.begin(NVS_NAMESPACE, false)) {
    Serial.println("[ID] Recusado: NVS indisponivel.");
    return false;
  }
  p.putUChar(CHAVE_ID, novo);
  p.end();

  _id = novo;
  Serial.printf("[ID] Gravado: no %02u. Etiquete a placa AGORA.\n", novo);
  return true;
}

// ─── Console de comissionamento ──────────────────────────────────────────────

static void ajuda() {
  Serial.println();
  Serial.println("  id           mostra o ID atual");
  Serial.printf ("  id <n>       grava o ID (1..%d)\n", TOTAL_NOS);
  Serial.println("  sensores     diagnostico do DHT22 e do DS18B20");
  Serial.println("  ajuda        esta lista");
  Serial.println();
}

static void mostrar() {
  if (!noComissionado()) {
    Serial.printf("[ID] NAO COMISSIONADA. Use:  id <1..%d>\n", TOTAL_NOS);
  } else {
    Serial.printf("[ID] No %02u%s\n", _id,
                  _fixo ? " (fixo em compilacao)" : " (NVS)");
  }
}

static void processar(String linha) {
  linha.trim();
  if (linha.length() == 0) return;

  String cmd = linha;
  cmd.toLowerCase();

  if (cmd == "ajuda" || cmd == "help" || cmd == "?") { ajuda(); return; }

  if (cmd == "id") { mostrar(); return; }

  if (cmd.startsWith("id ")) {
    String arg = linha.substring(3);
    arg.trim();
    // `toInt()` devolve 0 para lixo, e 0 já é recusado por `definirNoId` — mas
    // um aviso explícito evita o operador achar que digitou certo.
    for (unsigned i = 0; i < arg.length(); i++) {
      if (!isDigit(arg.charAt(i))) {
        Serial.println("[ID] Recusado: o ID tem que ser um numero.");
        return;
      }
    }
    definirNoId((uint8_t)arg.toInt());
    return;
  }

  if (comandoSerialExtra(cmd)) return;

  Serial.println("[ID] Comando desconhecido. Digite 'ajuda'.");
}

void identidadeLoop() {
  static String buf;
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (buf.length()) { processar(buf); buf = ""; }
    } else if (buf.length() < 40) {
      buf += c;
    }
    // Acima de 40 caracteres o excesso é descartado: nenhum comando daqui chega
    // perto disso, e sem o teto uma serial com ruído encheria a heap.
  }
}
