#include "historico.h"
#include "globals.h"
#include "config.h"
#include "sdcard.h"
#include <time.h>
#include <WiFi.h>

#define NTP_SERVER1 "a.ntp.br"
#define NTP_SERVER2 "b.ntp.br"
#define NTP_SERVER3 "pool.ntp.org"
#define TZ_BRASILIA "BRT3"   // UTC-3, sem horário de verão

void ntpAoConectar() {
  // Reinicia o SNTP para pedir a hora na hora, sem esperar o próximo
  // reenvio dele.
  configTzTime(TZ_BRASILIA, NTP_SERVER1, NTP_SERVER2, NTP_SERVER3);
  Serial.println("[NTP] STA conectado — pedindo a hora");
}

void setupNTP() {
  // Armado SEMPRE, com ou sem internet: o SNTP fica tentando sozinho e acerta
  // o relógio quando a rede aparecer. Antes, um boot sem internet deixava o
  // receptor sem hora até reiniciar — beacon com `TS:0` para sempre.
  configTzTime(TZ_BRASILIA, NTP_SERVER1, NTP_SERVER2, NTP_SERVER3);
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[NTP] Sem internet — a hora chega quando a rede voltar");
    return;
  }
  Serial.print("[NTP] Sincronizando");
  struct tm info;
  unsigned long inicio = millis();
  while (!getLocalTime(&info, 100) && millis() - inicio < 10000) {
    delay(400);
    Serial.print(".");
  }
  if (getLocalTime(&info, 100)) {
    char buf[32];
    strftime(buf, sizeof(buf), "%d/%m/%Y %H:%M:%S", &info);
    Serial.println(" OK! " + String(buf));
  } else {
    Serial.println(" Falhou! Usando tempo relativo.");
  }
}

bool horaValida() {
  struct tm info;
  // Timeout curto de propósito: o padrão de `getLocalTime()` é 5000 ms e ele
  // fica em loop até estourar quando não há hora. Chamado a cada beacon, isso
  // congelaria o TDMA por 5 s.
  return getLocalTime(&info, 5);
}

String obterDataHora() {
  struct tm info;
  if (getLocalTime(&info, 5)) {
    char buf[20];
    strftime(buf, sizeof(buf), "%d/%m/%y %H:%M:%S", &info);
    return String(buf);
  }
  return millisParaHora(millis());
}

String obterDataArquivo() {
  struct tm info;
  if (getLocalTime(&info, 5)) {
    char buf[12];
    strftime(buf, sizeof(buf), "%d-%m-%y", &info);
    return String(buf);
  }
  return "sem-data";
}

String millisParaHora(unsigned long ms) {
  unsigned long seg = ms / 1000;
  char buf[12];
  sprintf(buf, "%02lu:%02lu:%02lu", seg / 3600, (seg % 3600) / 60, seg % 60);
  return String(buf);
}

void salvarRegistro(int tipo, int nodeId) {
  NoRede* n = noPorId(nodeId);
  if (n == nullptr) return;

  Registro r;
  r.timestamp  = millis();
  r.tipo       = tipo;
  r.nodeId     = (uint8_t)nodeId;

  r.umidade1   = n->c1.umidade;
  r.irrigando1 = n->c1.irrigando;
  r.limite1    = n->c1.limite;

  r.umidade2   = n->c2.umidade;
  r.irrigando2 = n->c2.irrigando;
  r.limite2    = n->c2.limite;

  r.temp       = n->temp;
  r.umidadeAr  = n->umidadeAr;
  r.tempSolo   = n->tempSolo;
  r.previsao1  = n->c1.previsao;
  r.previsao2  = n->c2.previsao;

  String dh = obterDataHora();
  strncpy(r.dataHora, dh.c_str(), sizeof(r.dataHora) - 1);
  r.dataHora[sizeof(r.dataHora) - 1] = '\0';

  if (sdDisponivel) {
    salvarRegistroSD(r);
  } else if (totalBufferRAM < MAX_REGISTROS_RAM) {
    bufferRAM[totalBufferRAM++] = r;
  } else {
    memmove(&bufferRAM[0], &bufferRAM[1], sizeof(Registro) * (MAX_REGISTROS_RAM - 1));
    bufferRAM[MAX_REGISTROS_RAM - 1] = r;
  }
}
