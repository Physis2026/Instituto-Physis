// ══════════════════════════════════════════════════════════════════════════════
//  NÓ TRANSMISSOR V6 — Heltec WiFi LoRa 32 V3 (ESP32-S3 + SX1262)
//  Par do `Projeto Receptor V6`.
//
//  2 sensores capacitivos de solo · DS18B20 (temperatura do solo) ·
//  DHT22 (temperatura + umidade do ar) · 1 relé de irrigação · sem WiFi ·
//  registro local em microSD (opcional — sem cartão o nó segue normal).
//
//  O nó transmite APENAS dentro do seu slot TDMA (ver `lora_no.cpp`) e fala o
//  protocolo de linha do controle central (ver `controle-central/PROTOCOLO.md`).
//  A identidade e comissionada pela NVS (uma imagem para todas as placas) ou
//  fixada com `-D NODE_ID` — ver `identidade.h`. Rede de ate 99 nos.
// ══════════════════════════════════════════════════════════════════════════════

#include "heltec_unofficial.h"

#include <DHT.h>
#include <Preferences.h>
#include <time.h>

#include "config.h"
#include "protocolo.h"
#include "modelo.h"
#include "weather.h"
#include "identidade.h"
#include "lora_no.h"
#include "temp_solo.h"
#include "cartao.h"

// ── Sensores ──────────────────────────────────────────────────────────────────
DHT dht(PINO_DHT, DHT_TIPO);

static float umid1 = 0.0f, umid2 = 0.0f;
static bool  umid1Valida = false, umid2Valida = false;

static float temperatura = 0.0f, umidadeAr = 0.0f;
static bool  tempValida  = false, umidArValida = false;
static unsigned long ultimoDHT = 0;
static int           falhasDHT = 0;

// `heltec_vbat()` segura o barramento por 5 ms para medir. Amostrado uma vez por
// slot, fora do caminho da transmissão.
static float tensaoBateria = 0.0f;

// Temperatura do solo congelada no instante do slot: a linha transmitida e a
// linha gravada no cartão têm de mostrar o MESMO valor.
static float tSolo = 0.0f;
static bool  tSoloValida = false;

// `prepararSlot()` roda colado na transmissão; o SD é gravado só depois, no
// `loop()`, para que uma escrita lenta não atrase o rádio dentro do slot.
// (o nó se ATUALIZA a cada INTERVALO_LEITURA_MS, mas só transmite e grava uma
// vez por ciclo TDMA, no próprio slot)
static bool gravarCartaoPendente = false;

// ── Irrigação (um relé, decidido pela média dos dois sensores) ────────────────
static bool          irrigando       = false;
static bool          modoManual      = false;
static unsigned long inicioIrrigacao = 0;
static unsigned long ultimaIrrigacao = 0;

// ── Modelos de secagem ────────────────────────────────────────────────────────
static Modelo   modelo1;  // canal 1 — usa a MÉDIA dos sensores, comanda o relé
static Modelo   modelo2;  // canal 2 — sensor B isolado, informativo
static Segmento seg1, seg2;
static float    prev1 = -1.0f, prev2 = -1.0f;

// ══════════════════════════════════════════════════════════════════════════════
//  Tempo
// ══════════════════════════════════════════════════════════════════════════════

/// Minuto do dia na hora local, ou -1 sem relógio. Sem relógio não há faixa
/// horária: inventar uma (horas desde o boot) espalharia o aprendizado pelas
/// faixas erradas e mudaria o mapeamento a cada reboot.
static int minutoDoDia() {
  struct tm info;
  if (!relogioValido() || !getLocalTime(&info, 0)) return -1;
  return info.tm_hour * 60 + info.tm_min;
}

// ══════════════════════════════════════════════════════════════════════════════
//  Leitura dos sensores
// ══════════════════════════════════════════════════════════════════════════════

/// Mediana de N amostras: um pico isolado do ADC não vira uma queda de umidade
/// que o modelo aprenderia como taxa de secagem.
static int lerRawMediana(uint8_t pino) {
  int v[AMOSTRAS_ADC];
  for (int i = 0; i < AMOSTRAS_ADC; i++) {
    v[i] = analogRead(pino);
    delayMicroseconds(300);
  }
  for (int i = 1; i < AMOSTRAS_ADC; i++) {  // insertion sort, N é minúsculo
    int k = v[i], j = i - 1;
    while (j >= 0 && v[j] > k) { v[j + 1] = v[j]; j--; }
    v[j + 1] = k;
  }
  return v[AMOSTRAS_ADC / 2];
}

static float rawParaUmidade(int raw, int seco, int molhado) {
  if (seco == molhado) return 0.0f;
  float pct = 100.0f * (float)(seco - raw) / (float)(seco - molhado);
  return constrain(pct, 0.0f, 100.0f);
}

/// Raw colado nos extremos da escala é sensor desligado ou em curto, não solo
/// encharcado — melhor reportar vazio do que um 100 % que ninguém questiona.
static bool rawPlausivel(int raw) { return raw > 200 && raw < 4090; }

static void lerSensores() {
  int rawA = lerRawMediana(PINO_SOLO_A);
  int rawB = lerRawMediana(PINO_SOLO_B);

  umid1Valida = rawPlausivel(rawA);
  umid2Valida = rawPlausivel(rawB);
  if (umid1Valida) umid1 = rawParaUmidade(rawA, SECO_A, MOLHADO_A);
  if (umid2Valida) umid2 = rawParaUmidade(rawB, SECO_B, MOLHADO_B);

  if (millis() - ultimoDHT >= INTERVALO_DHT_MS) {
    ultimoDHT = millis();
    float t = dht.readTemperature();
    float h = dht.readHumidity();
    if (!isnan(t) && !isnan(h)) {
      temperatura = t; tempValida   = true;
      umidadeAr   = h; umidArValida = true;
      if (falhasDHT >= MAX_FALHAS_DHT) Serial.println("[DHT] Voltou a responder");
      falhasDHT = 0;
    } else if (++falhasDHT == MAX_FALHAS_DHT) {
      // Sem isso o último valor bom ficaria na tela e no rádio para sempre,
      // e um sensor morto passaria por um dia de tempo estável.
      tempValida = umidArValida = false;
      Serial.printf("[DHT] Sem resposta no GPIO %d — digite 'sensores' para diagnosticar\n",
                    PINO_DHT);
    }
  }

  // Só consome o último valor pronto — a conversão corre em `tempSoloLoop()`.
  tSoloValida = tempSoloValida();
  if (tSoloValida) tSolo = tempSolo();
}

/// A média dos dois sensores é o que comanda a válvula. Se só um estiver bom,
/// vale o que sobrou; se nenhum, não há decisão a tomar.
static bool umidadeMedia(float& saida) {
  if (umid1Valida && umid2Valida) { saida = (umid1 + umid2) / 2.0f; return true; }
  if (umid1Valida)                { saida = umid1;                  return true; }
  if (umid2Valida)                { saida = umid2;                  return true; }
  return false;
}

// ══════════════════════════════════════════════════════════════════════════════
//  Relé
// ══════════════════════════════════════════════════════════════════════════════

static void iniciarIrrigacao(const char* motivo) {
  if (irrigando) return;
  digitalWrite(PINO_RELE, RELE_LIGADO);
  irrigando       = true;
  inicioIrrigacao = millis();
  Serial.printf("[Irrig] Iniciada (%s)\n", motivo);
}

static void pararIrrigacao(const char* motivo) {
  if (!irrigando) return;
  digitalWrite(PINO_RELE, RELE_DESLIGADO);
  irrigando       = false;
  ultimaIrrigacao = millis();
  Serial.printf("[Irrig] Parada (%s)\n", motivo);
}

// ══════════════════════════════════════════════════════════════════════════════
//  Decisão de irrigação
// ══════════════════════════════════════════════════════════════════════════════

static void decidirIrrigacao() {
  if (modoManual || irrigando) return;

  float media;
  if (!umidadeMedia(media)) return;  // sem sensor bom, não se irriga no escuro

  if (chuvaVemAi()) return;

  bool cooldownOk = (ultimaIrrigacao == 0) || (millis() - ultimaIrrigacao >= COOLDOWN_MS);
  if (!cooldownOk) return;

  if (media <= modelo1.limiteUmidade) {
    iniciarIrrigacao("umidade abaixo do limite");
    return;
  }

  if (prev1 >= 0 && prev1 <= MARGEM_PREVISAO_MIN) {
    iniciarIrrigacao("previsao dentro da margem");
  }
}

// ══════════════════════════════════════════════════════════════════════════════
//  Atualização periódica (a cada INTERVALO_LEITURA_MS, independente do rádio)
// ══════════════════════════════════════════════════════════════════════════════

/// Lê sensores, alimenta o aprendizado, prevê e decide a irrigação, a cada
/// segundo: o display e o relé reagem na hora e o slot só envia o estado mais
/// recente. Toda leitura entra no aprendizado (ver modelo.h).
static void atualizarNo() {
  lerSensores();
#if ENVIAR_BATERIA
  tensaoBateria = heltec_vbat();
#endif

  float media    = 0.0f;
  bool  temMedia = umidadeMedia(media);
  // Origem da média: se um sensor cai ou volta, o nível muda e a reta recomeça.
  uint8_t fonte1 = (umid1Valida ? 1 : 0) | (umid2Valida ? 2 : 0);
  uint8_t fonte2 = umid2Valida ? 2 : 0;

  int           minuto = minutoDoDia();
  float         tAr    = tempValida ? temperatura : NAN;
  unsigned long agora  = millis();

  observarUmidade(modelo1, seg1, media, fonte1, irrigando, tAr, minuto, agora, "1");
  observarUmidade(modelo2, seg2, umid2, fonte2, irrigando, tAr, minuto, agora, "2");

  // NAN = sem leitura (vai `-`); -1 = modelo aprendendo. Antes os dois saíam
  // `-1` e o painel mostrava "Aprend." para um sensor desconectado.
  prev1 = temMedia    ? minutosParaLimite(modelo1, media, minuto, tAr) : NAN;
  prev2 = umid2Valida ? minutosParaLimite(modelo2, umid2, minuto, tAr) : NAN;

  decidirIrrigacao();
}

// ══════════════════════════════════════════════════════════════════════════════
//  Ganchos chamados pela camada de rádio
// ══════════════════════════════════════════════════════════════════════════════

/// Os valores já estão frescos (no máximo INTERVALO_LEITURA_MS de idade): nada
/// de ler sensor aqui dentro do slot. Só marca a gravação no cartão, que sai
/// no `loop()` logo depois da transmissão, com os mesmos valores enviados.
void prepararSlot() {
  gravarCartaoPendente = true;
}

/// `-` é a sentinela de "sem dado" do contrato (PROTOCOLO.md §2.4): o RPi grava
/// NULO e o painel mostra um traço. Mandar o último valor bom seria inventar.
static String numOuVazio(float v, bool valido) {
  return valido ? num1(v) : String("-");
}

/// Previsão legível no OLED: "42 min", "5.2 h", "8.4 d". Medindo a secagem de
/// verdade, a previsão passa a ir a dias.
static String textoMinutos(float minutos) {
  if (minutos >= PREVISAO_MAX_MIN) return "> " + String((int)(PREVISAO_MAX_MIN / 1440.0f)) + " d";
  if (minutos < 90.0f)             return String((int)minutos) + " min";
  if (minutos < 2880.0f)           return num1(minutos / 60.0f) + " h";
  return num1(minutos / 1440.0f) + " d";
}

/// `P1`/`P2` na linha e no cartão: `-` sem leitura, `-1` aprendendo, minutos.
static String textoPrevisao(float p) {
  if (isnan(p)) return "-";
  return p >= 0 ? num1(p) : String("-1");
}

String montarTelemetria() {
  String p = "ID:" + doisDigitos(noId());
  p += ",U1:"   + numOuVazio(umid1, umid1Valida);
  p += ",IR1:"  + String(irrigando ? 1 : 0);
  p += ",U2:"   + numOuVazio(umid2, umid2Valida);
  p += ",IR2:0";                                    // este nó não tem relé 2
  p += ",T:"    + numOuVazio(temperatura, tempValida);
  p += ",UAR:"  + numOuVazio(umidadeAr, umidArValida);
  p += ",TSOLO:" + numOuVazio(tSolo, tSoloValida);  // chave nova: vai para `extras`
  p += ",P1:"   + textoPrevisao(prev1);
  p += ",P2:"   + textoPrevisao(prev2);
  // LIM1 e LIM2 SEMPRE juntos: é a presença dos dois na mesma linha que faz o
  // painel marcar o comando de limite como confirmado (PROTOCOLO.md §2.3).
  p += ",LIM1:" + num1(modelo1.limiteUmidade);
  p += ",LIM2:" + num1(modelo2.limiteUmidade);
#if ENVIAR_BATERIA
  p += ",BAT:"  + String(tensaoBateria, 2);         // chave nova: vai para `extras`
#endif
  if (relogioValido()) p += ",TS:" + String(epochAtual());
  return p;
}

/// O argumento já passou por `argumentoValido()` em `processarComando`: o
/// limiar é um número 0–100, o relé é `0`/`1` e o modo é AUTO/MANUAL.
bool aplicarAcao(const String& acao, const String& arg) {
  if (acao == "LIM1" || acao == "LIM2") {
    bool    canal1 = (acao == "LIM1");
    Modelo& m      = canal1 ? modelo1 : modelo2;
    m.limiteUmidade = arg.toFloat();
    salvarLimite(m, canal1 ? "1" : "2");
    Serial.printf("[Config] %s = %.1f%%\n", acao.c_str(), m.limiteUmidade);
    return true;
  }
  if (acao == "IRR1") {
    // Liga/desliga a válvula agora SEM mudar o modo. O RPi manda IRR1 sozinho
    // (agenda, chuva, trava de duração) e nunca devolve MODO:AUTO, e o modo nem
    // vai na telemetria: travar MANUAL aqui deixava o nó sem irrigação
    // automática para sempre, sem ninguém ver. Enquanto a válvula está aberta a
    // decisão automática já fica de fora; depois vale o cooldown. Modo manual
    // fixo só por MODO:MANUAL.
    if (arg == "1") iniciarIrrigacao("comando IRR1:1");
    else            pararIrrigacao("comando IRR1:0");
    return true;
  }
  if (acao == "IRR2") {
#if TEM_RELE2
    // Reservado: quando houver segunda válvula, acionar aqui e passar a
    // reportar IR2 de verdade em montarTelemetria().
    return true;
#else
    // Este nó tem um relé só. Aceitar o comando e continuar reportando IR2:0
    // seria mentir; ignorar deixa o painel mostrando o estado real.
    Serial.println("[Config] IRR2 ignorado: este no nao tem rele 2");
    return false;
#endif
  }
  if (acao == "MODO") {
    modoManual = arg.equalsIgnoreCase("MANUAL");
    Serial.printf("[Config] Modo = %s\n", modoManual ? "MANUAL" : "AUTO");
    return true;
  }
  return false;  // ação desconhecida: ignorada sem travar o nó
}

// ══════════════════════════════════════════════════════════════════════════════
//  Cartão SD
// ══════════════════════════════════════════════════════════════════════════════

/// Mesmos valores (e a mesma sentinela `-`) da linha enviada ao gateway, na
/// ordem do cabeçalho de `cartao.cpp`.
static void gravarNoCartao() {
#if USAR_SD
  String l = String(millis());
  l += ";" + (relogioValido() ? String(epochAtual()) : String(""));
  l += ";" + numOuVazio(umid1, umid1Valida);
  l += ";" + numOuVazio(umid2, umid2Valida);
  l += ";" + numOuVazio(temperatura, tempValida);
  l += ";" + numOuVazio(umidadeAr, umidArValida);
  l += ";" + numOuVazio(tSolo, tSoloValida);
  l += ";" + String(irrigando ? 1 : 0);
  l += ";" + textoPrevisao(prev1);
  l += ";" + textoPrevisao(prev2);
  l += ";" + num1(modelo1.limiteUmidade);
  l += ";" + num1(modelo2.limiteUmidade);
  l += ";" + String(tensaoBateria, 2);
  cartaoGravar(l);
#endif
}

// ══════════════════════════════════════════════════════════════════════════════
//  Diagnóstico pela serial (comando `sensores`)
// ══════════════════════════════════════════════════════════════════════════════

static void diagnosticoDHT() {
  Serial.printf("[Diag] DHT22 no GPIO %d\n", PINO_DHT);

  // O DHT segura a linha em 1 pelo pull-up enquanto está em repouso.
  pinMode(PINO_DHT, INPUT);
  delay(2);
  bool alta = digitalRead(PINO_DHT) == HIGH;
  Serial.printf("[Diag]   linha em repouso: %s\n",
                alta ? "ALTA (pull-up ok)"
                     : "BAIXA -> falta pull-up (4,7k-10k para VCC), sensor sem "
                       "alimentacao ou fio em curto");

  // O DHT22 recusa leituras com menos de 2 s de intervalo.
  unsigned long desde = millis() - ultimoDHT;
  if (desde < 2100) delay(2100 - desde);
  ultimoDHT = millis();

  float t = dht.readTemperature(false, true);  // força uma leitura nova
  float h = dht.readHumidity();
  if (isnan(t) || isnan(h)) {
    Serial.println("[Diag]   leitura: FALHOU (sem resposta ou checksum errado)");
    Serial.println("[Diag]   confira: VCC no 3V3/Ve, GND, dados no pino certo, pull-up");
  } else {
    Serial.printf("[Diag]   leitura: T=%.1f C  UR=%.1f %%  OK\n", t, h);
  }
}

bool comandoSerialExtra(const String& cmd) {
  if (cmd != "sensores") return false;
  Serial.println();
  Serial.println("[Diag] ===== Sensores (trava o no por ~3 s) =====");
  diagnosticoDHT();
  tempSoloDiagnostico();
  Serial.println("[Diag] ==========================================");
  Serial.println();
  return true;
}

// ══════════════════════════════════════════════════════════════════════════════
//  Display
// ══════════════════════════════════════════════════════════════════════════════

static void atualizarDisplay() {
  display.clear();
  display.setFont(ArialMT_Plain_10);

  // Placa nao comissionada: a tela inteira vira o aviso. Ela nao transmite, e
  // deixar isso escondido num canto faria alguem instalar no campo achando que
  // o problema era antena ou alcance.
  if (!noComissionado()) {
    display.drawString(0,  0, "*** SEM IDENTIDADE ***");
    display.drawString(0, 14, "Este no NAO transmite.");
    display.drawString(0, 28, "Ligue a serial 115200 e");
    display.drawString(0, 42, "digite:  id <1.." + String(TOTAL_NOS) + ">");
    display.display();
    return;
  }

  String estado = tdmaSincronizado()
                    ? (relogioValido() ? "SINC" : "SINC s/hora")
                    : ("ORFAO " + String(ciclosSemBeacon()));
  display.drawString(0, 0, "No " + doisDigitos(noId()) + "  [" + estado + "]");

  // Seis linhas com passo de 10 px: a temperatura do solo ganhou uma linha
  // própria em vez de espremer a do DHT além dos 128 px.
  display.drawString(0, 10, "S1:" + numOuVazio(umid1, umid1Valida) + "%  " +
                            "S2:" + numOuVazio(umid2, umid2Valida) + "%");

  display.drawString(0, 20, "T:" + numOuVazio(temperatura, tempValida) + "C  " +
                            "Ar:" + numOuVazio(umidadeAr, umidArValida) + "%");

  // Lê direto do módulo (não do valor congelado no slot) para a tela reagir
  // na hora em que o sensor é ligado ou cai.
  String linhaSolo = "Solo:" + numOuVazio(tempSolo(), tempSoloValida()) + "C";
#if USAR_SD
  linhaSolo += cartaoOk() ? "   SD:OK" : "   SD:--";
#endif
  display.drawString(0, 30, linhaSolo);

  String linha4;
  if (irrigando)          linha4 = "[IRRIGANDO]";
  else if (modoManual)    linha4 = "MANUAL — em espera";
  else if (chuvaVemAi())  linha4 = "** CHUVA ESPERADA **";
  else if (prev1 >= 0)    linha4 = "Prev: " + textoMinutos(prev1);
  else if (modeloValido(modelo1)) linha4 = "Prev: --";  // modelo pronto, sensor sem leitura
  else                    linha4 = "Aprend. " + String(modelo1.a.retas) + "/" +
                                   String(MIN_SEGMENTOS_MODELO) +
                                   (seg1.esperando ? String(" drenando")
                                                   : " (" + String(seg1.minutos) + " min)");
  display.drawString(0, 40, linha4);

  display.drawString(0, 50, "L:" + num1(modelo1.limiteUmidade) +
                            " TX:" + String(totalTransmitido()) +
                            " B:" + String((int)rssiBeacon()));
  display.display();
}

// ══════════════════════════════════════════════════════════════════════════════

void setup() {
  Serial.begin(115200);
  delay(200);

  // `heltec_setup()` já faz Serial.begin, display.init(), contraste e flip.
  heltec_setup();

  // Vext alimenta os sensores externos (LOW liga). É o que torna o deep sleep
  // útil depois: dormindo, o nó corta a alimentação dos sensores junto.
  heltec_ve(true);
  delay(100);

  display.clear();
  display.drawString(0, 0, "Iniciando...");
  display.display();

  pinMode(PINO_RELE, OUTPUT);
  digitalWrite(PINO_RELE, RELE_DESLIGADO);  // relé desligado ANTES de tudo

  analogReadResolution(12);
  analogSetPinAttenuation(PINO_SOLO_A, ADC_11db);
  analogSetPinAttenuation(PINO_SOLO_B, ADC_11db);

  setenv("TZ", "BRT3", 1);  // UTC-3, sem horário de verão
  tzset();

  dht.begin();
  tempSoloSetup();
#if USAR_SD
  cartaoSetup();
#endif

  // Antes do radio: `loraSetup()` ja usa o ID para semear o jitter.
  identidadeSetup();

  carregarModelo(modelo1, "1");
  carregarModelo(modelo2, "2");

  loraSetup();

  atualizarNo();
  atualizarDisplay();

  Serial.printf("[Sistema] No %02u pronto | ciclo %lu ms | slot %lu ms | rede de %d nos\n",
                noId(), cicloAtualMs(), slotAtualMs(), TOTAL_NOS);
}

void loop() {
  heltec_loop();
  identidadeLoop();   // console de comissionamento pela serial
  loraLoop();
  tempSoloLoop();     // conversão assíncrona do DS18B20

  // O slot já foi transmitido dentro do `loraLoop()` acima; agora é seguro
  // gastar alguns ms no cartão.
  if (gravarCartaoPendente) {
    gravarCartaoPendente = false;
    gravarNoCartao();
  }

  // Trava dura de duração: mesmo em modo manual, a válvula fecha sozinha.
  if (irrigando && millis() - inicioIrrigacao >= MAX_IRRIGACAO_MS) {
    pararIrrigacao("duracao maxima atingida");
  }

  static unsigned long ultimaLeitura = 0;
  if (millis() - ultimaLeitura >= INTERVALO_LEITURA_MS) {
    ultimaLeitura = millis();
    atualizarNo();
  }

  static unsigned long ultimoDisplay = 0;
  if (millis() - ultimoDisplay >= 500) {
    ultimoDisplay = millis();
    atualizarDisplay();
  }

#if USAR_DEEP_SLEEP
  // PENDENTE: dormir entre o fim do slot e o próximo beacon. Precisa de
  //   (a) guardar tRefCiclo/epoch em RTC_DATA_ATTR,
  //   (b) acordar MARGEM_ACORDAR_MS antes do beacon esperado,
  //   (c) reinicializar o rádio a cada boot (~300 ms) dentro dessa margem.
  // Não ativar sem medir o tempo real de boot da sua placa.
#endif
}
