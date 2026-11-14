#pragma once
#include <Arduino.h>
#include <WebServer.h>
#include "config.h"

// ══════════════════════════════════════════════════════════════════════════════
//  Estado compartilhado do receptor.
//
//  MUDANÇA ESTRUTURAL EM RELAÇÃO À VERSÃO ANTERIOR: `no1`/`no2` eram os DOIS
//  SENSORES de uma única placa, não dois nós — compartilhavam RSSI, SNR,
//  temperatura e o próprio estado online. Agora existe `nos[TOTAL_NOS]`, um por
//  transmissor de campo, cada um com seus dois canais de umidade.
// ══════════════════════════════════════════════════════════════════════════════

/// Um canal dentro de um nó, como a linha o descreve.
///
/// ⚠ No Transmissor V6 o canal 1 NÃO é o sensor A: `U1` é o sensor A, mas
/// `LIM1`, `P1` e `IR1` valem para a MÉDIA dos dois sensores — é ela que liga o
/// relé. Comparar `c1.umidade` com `c1.limite` compara grandezas diferentes;
/// use `umidadeControle()`. O canal 2 é o sensor B sozinho, sem válvula.
struct Canal {
  float umidade   = NAN;    // %, NAN = sem leitura (U1 = sensor A, U2 = sensor B)
  bool  irrigando = false;  // nunca nulo: campo ausente vira false no contrato
  float limite    = NAN;    // limiar vigente NO NÓ (chega em LIM1/LIM2)
  float previsao  = NAN;    // minutos até o limite; -1 = aprendendo; NAN = sem leitura
};

/// Um nó de campo (Heltec V3 com 2 sensores de solo, DHT22, DS18B20 e 1 relé).
struct NoRede {
  uint8_t       id           = 0;      // 1..TOTAL_NOS
  Canal         c1, c2;
  float         temp         = NAN;
  float         umidadeAr    = NAN;
  float         tempSolo     = NAN;    // DS18B20 (TSOLO), Transmissor V6
  float         bateria      = NAN;
  float         rssi         = 0.0f;   // medidos AQUI, na recepção
  float         snr          = 0.0f;
  unsigned long ultimoPacket = 0;      // millis
  bool          online       = false;
  bool          comRelogio   = false;  // o nó mandou TS: (já sincronizou)
  uint32_t      pacotes      = 0;
  bool          conhecido    = false;  // já falou alguma vez (persiste na NVS)
};

/// A umidade que o nó compara com `LIM1` para ligar o relé: a média dos dois
/// sensores, ou o que sobrou se um deles estiver sem leitura — a mesma regra de
/// `umidadeMedia()` no Transmissor V6. NAN se os dois estiverem sem leitura.
inline float umidadeControle(const NoRede& n) {
  bool a = !isnan(n.c1.umidade), b = !isnan(n.c2.umidade);
  if (a && b) return (n.c1.umidade + n.c2.umidade) / 2.0f;
  return a ? n.c1.umidade : n.c2.umidade;
}

/// Uma linha do histórico (SD ou buffer de RAM).
struct Registro {
  unsigned long timestamp;
  char          dataHora[20];
  int           tipo;      // REGISTRO_LEITURA | REGISTRO_EVENTO
  uint8_t       nodeId;

  float         umidade1;
  bool          irrigando1;
  float         limite1;

  float         umidade2;
  bool          irrigando2;
  float         limite2;

  float         temp;
  float         umidadeAr;
  float         tempSolo;
  float         previsao1;
  float         previsao2;
};

extern NoRede    nos[TOTAL_NOS];
extern Registro  bufferRAM[];
extern int       totalBufferRAM;
extern long      totalRegistrosSD;
extern bool      sdDisponivel;

extern WebServer     server;
extern unsigned long ultimoAlerta;
extern bool          modoProvisionamento;
extern String        wifiSsidAtual;

/// `nos[id-1]`, ou `nullptr` se o id estiver fora da rede configurada.
NoRede* noPorId(int id);
