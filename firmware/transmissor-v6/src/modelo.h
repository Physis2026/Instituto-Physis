#pragma once
#include <Arduino.h>
#include "config.h"

// ══════════════════════════════════════════════════════════════════════════════
//  Modelo de secagem do solo — aprendizado contínuo.
//
//  Aprende a taxa de queda da umidade (%/min) por faixa horária, normalizada a
//  20 °C, e o ganho dessa taxa com a temperatura do ar; prevê em quantos minutos
//  a umidade cruza o limiar.
//
//  Por que não comparar leituras próximas (o que o V4 e o V6 original faziam):
//  uma contagem do ADC vale ~0,05 % de umidade e o solo seca na ordem de
//  0,002 %/min. Entre leituras a 30 s a queda real é ~1/50 de contagem — o que
//  se mede é quantização e ruído, e guardar só as quedas transforma ruído em
//  "secagem". A taxa aprendida ficava presa em ~0,1 %/min qualquer que fosse a
//  taxa real. Agora:
//
//    1. toda leitura válida entra na média do minuto;
//    2. a cada SEGMENTO_MIN médias, uma reta de mínimos quadrados dá a taxa
//       observada — quedas, estabilidade e pequenas subidas entram igual;
//    3. a reta só vale com a umidade vinda sempre da mesma fonte e sem o solo
//       ser molhado (relé, chuva); depois de molhar, espera-se a drenagem;
//    4. a taxa aceita, levada a 20 °C, entra na média da sua faixa e na média
//       geral, que é a que vale sem relógio.
//
//  A temperatura entra uma vez só: a taxa é guardada a 20 °C e o ganho é
//  aplicado na previsão. O ganho sai da comparação de retas mais quentes e mais
//  frias DENTRO da mesma faixa, para o efeito do horário ficar na faixa.
//
//  Persistência na NVS: o aprendizado num bloco versionado por modelo (gravado
//  a cada reta aceita, no máximo uma vez por hora) e o limiar numa chave
//  própria (gravado só quando um comando o muda).
// ══════════════════════════════════════════════════════════════════════════════

/// O que o aprendizado produz. É o bloco gravado na NVS.
struct Aprendido {
  float    taxa[FAIXAS_HORA];        // %/min a 20 °C, por faixa horária
  float    tempFaixa[FAIXAS_HORA];   // temperatura típica do ar na faixa (°C; NaN = sem dado)
  uint16_t retasFaixa[FAIXAS_HORA];  // retas aceitas na faixa
  float    taxaGeral;                // %/min a 20 °C de todas as retas
  uint32_t retas;                    // retas aceitas no total
  float    sxy, sxx, nGanho;         // mínimos quadrados do ganho de temperatura
};

struct Modelo {
  Aprendido a;
  float     limiteUmidade;           // limiar que dispara a irrigação (%)
};

/// Reta em construção. Fica só na RAM: um reboot perde no máximo a reta corrente.
struct Segmento {
  uint8_t       fonte;               // sensores que formam a umidade (0 = nenhum)
  bool          esperando;           // drenando depois de o solo ser molhado
  unsigned long molhadoEm;
  unsigned long inicioMinuto;
  float         somaMinuto;
  uint16_t      leiturasMinuto;
  unsigned long inicioReta;          // centro do 1º minuto da reta
  uint16_t      minutos;
  float         uRef, uAnterior;
  double        st, su, stt, stu, suu;
  float         somaTemp;
  uint16_t      leiturasTemp;
};

/// 0 = manhã, 1 = tarde, 2 = noite.
int faixaHora(int hora);

/// Só prevê depois de MIN_SEGMENTOS_MODELO retas aceitas.
bool modeloValido(const Modelo& m);

/// Uma leitura, a cada INTERVALO_LEITURA_MS. `fonte` identifica os sensores que
/// formam `umidade` (0 = sem leitura válida), `molhando` = relé ligado,
/// `temperatura` NaN = DHT sem leitura, `minutoDia` -1 = sem relógio.
void observarUmidade(Modelo& m, Segmento& s, float umidade, uint8_t fonte, bool molhando,
                     float temperatura, int minutoDia, unsigned long agora, const char* sufixo);

/// Minutos até a umidade atingir `limiteUmidade`, percorrendo as faixas do dia
/// a partir de `minutoDia` (sem relógio, vale a taxa geral). `-1` = modelo ainda
/// aprendendo (é a sentinela que o contrato manda emitir em `P1`/`P2`);
/// PREVISAO_MAX_MIN = o limiar não chega dentro desse horizonte.
float minutosParaLimite(const Modelo& m, float umidade, int minutoDia, float temperatura);

/// `sufixo` separa os dois modelos na NVS ("1" e "2").
void salvarModelo(const Modelo& m, const char* sufixo);
void salvarLimite(const Modelo& m, const char* sufixo);
bool carregarModelo(Modelo& m, const char* sufixo);
void zerarModelo(Modelo& m);
