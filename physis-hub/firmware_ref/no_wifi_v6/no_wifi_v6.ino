// ============================================================================
//  PHYSIS — No Wi-Fi V6 (TIPO:ZONA) — REFERENCIA, NAO COMPILADA NEM TESTADA
//
//  Substitui o ESPHome da Caixinha por um firmware que fala a linha V6 com o
//  Physis Hub por Wi-Fi. Escrito a partir de esphome/base_sensor.yaml e
//  base_valve.yaml e da extensao em docs/EXTENSAO_V6.md. Conferir pinos,
//  calibracao e logica do rele (ativo em baixo ou em alto) antes de gravar.
//
//  Placa: ESP32 DevKit (esp32dev). Bibliotecas: so o nucleo arduino-esp32.
// ============================================================================
#include <WiFi.h>
#include <HTTPClient.h>
#include <Preferences.h>

// ── Configuracao (em producao: fora do codigo, por console serial/NVS) ──────
static const char* WIFI_SSID = "REDE_DO_LUGAR";
static const char* WIFI_SENHA = "TROCAR";
static const char* HUB_URL   = "http://192.168.0.10:8700/api/v6/linha";

static const int  PINO_SOLO1 = 34, PINO_SOLO2 = 35;   // ADC1, so entrada
static const int  PINO_VALV1 = 26, PINO_VALV2 = 27, PINO_BOMBA = 25;
static const bool RELE_ATIVO_EM_BAIXO = true;          // conferir no modulo de reles
static const float SECO_V = 2.80f, MOLHADO_V = 1.20f;  // calibrar por sensor

static const uint32_t INTERVALO_MS   = 9000UL;         // mesma cadencia do ciclo V6
static const uint32_t TMAX_MIN       = 15;             // tempo maximo de rega
static const uint32_t SEM_HUB_MAX_MS = 5UL * 60UL * 1000UL;  // sem hub: fecha tudo

Preferences nvs;
uint8_t  meuId = 0;
float    lim1 = 35.0f, lim2 = 35.0f;
bool     manual = false, v1 = false, v2 = false, bomba = false;
uint32_t aberto1 = 0, aberto2 = 0, ultimoHubOk = 0, ultimoEnvio = 0;

static void rele(int pino, bool ligado) {
  digitalWrite(pino, (ligado ^ RELE_ATIVO_EM_BAIXO) ? HIGH : LOW);
}

// Ordem segura: abre valvula -> liga bomba; desliga bomba -> fecha a ultima valvula.
static void aplicarSaidas() {
  bool querBomba = v1 || v2;
  if (!querBomba && bomba) { rele(PINO_BOMBA, false); bomba = false; delay(800); }
  rele(PINO_VALV1, v1);
  rele(PINO_VALV2, v2);
  if (querBomba && !bomba) { delay(800); rele(PINO_BOMBA, true); bomba = true; }
}

static void setValvula(int n, bool abrir) {
  if (n == 1) { v1 = abrir; if (abrir) aberto1 = millis(); }
  else        { v2 = abrir; if (abrir) aberto2 = millis(); }
  aplicarSaidas();
}

static float lerUmidade(int pino) {
  uint32_t soma = 0;
  for (int i = 0; i < 16; i++) { soma += analogReadMilliVolts(pino); delay(2); }
  float v = (soma / 16.0f) / 1000.0f;
  float pct = (SECO_V - v) / (SECO_V - MOLHADO_V) * 100.0f;
  return constrain(pct, 0.0f, 100.0f);
}

// Mesma validacao do contrato: a string toda tem de ser o numero, de 0 a 100.
static bool limiteValido(const String& arg, float& out) {
  if (arg.length() == 0) return false;
  char* fim;
  float v = strtof(arg.c_str(), &fim);
  if (fim == arg.c_str() || *fim != '\0' || !isfinite(v) || v < 0.0f || v > 100.0f) return false;
  out = v;
  return true;
}

static void executar(const String& cmd) {            // "CMD:<nn>:<ACAO>[:<ARG>]"
  if (!cmd.startsWith("CMD:")) return;
  int a = cmd.indexOf(':', 4);
  if (a < 0) return;
  int destino = cmd.substring(4, a).toInt();
  if (destino != 0 && destino != meuId) return;
  int b = cmd.indexOf(':', a + 1);
  String acao = (b < 0) ? cmd.substring(a + 1) : cmd.substring(a + 1, b);
  String arg  = (b < 0) ? String("")           : cmd.substring(b + 1);
  acao.toUpperCase(); arg.trim();
  float f;
  if      (acao == "LIM1" && limiteValido(arg, f)) { lim1 = f; nvs.putFloat("lim1", f); }
  else if (acao == "LIM2" && limiteValido(arg, f)) { lim2 = f; nvs.putFloat("lim2", f); }
  else if (acao == "IRR1" && (arg == "0" || arg == "1")) { manual = true; setValvula(1, arg == "1"); }
  else if (acao == "IRR2" && (arg == "0" || arg == "1")) { manual = true; setValvula(2, arg == "1"); }
  else if (acao == "MODO") { arg.toUpperCase(); if (arg == "AUTO") manual = false; else if (arg == "MANUAL") manual = true; }
}

static void enviar(float u1, float u2) {
  char linha[200];
  time_t agora = time(nullptr);
  snprintf(linha, sizeof(linha),
           "ID:%02u,TIPO:ZONA,U1:%.1f,IR1:%d,U2:%.1f,IR2:%d,BOMBA:%d,TMAX:%lu,LIM1:%.1f,LIM2:%.1f,BAT:-,TS:%lu",
           meuId, u1, v1 ? 1 : 0, u2, v2 ? 1 : 0, bomba ? 1 : 0, (unsigned long)TMAX_MIN, lim1, lim2,
           (unsigned long)(agora > 1700000000 ? agora : 0));
  if (WiFi.status() != WL_CONNECTED) return;
  HTTPClient http;
  WiFiClient cliente;
  if (!http.begin(cliente, HUB_URL)) return;
  http.setTimeout(4000);
  http.addHeader("Content-Type", "text/plain; charset=utf-8");
  int codigo = http.POST(String(linha));
  if (codigo == 200) {
    ultimoHubOk = millis();
    String corpo = http.getString();               // {"ok":true,...,"comandos":["CMD:21:IRR1:1"]}
    int p = corpo.indexOf("\"comandos\"");
    while (p >= 0) {
      int i = corpo.indexOf("\"CMD:", p);
      if (i < 0) break;
      int j = corpo.indexOf('"', i + 1);
      if (j < 0) break;
      executar(corpo.substring(i + 1, j));
      p = j;
    }
  }
  http.end();
}

void setup() {
  Serial.begin(115200);
  pinMode(PINO_VALV1, OUTPUT); pinMode(PINO_VALV2, OUTPUT); pinMode(PINO_BOMBA, OUTPUT);
  rele(PINO_BOMBA, false); rele(PINO_VALV1, false); rele(PINO_VALV2, false);   // estado seguro no boot
  nvs.begin("physis", false);
  meuId = nvs.getUChar("id", 0);                   // 0 = nao comissionado: nao transmite
  lim1 = nvs.getFloat("lim1", 35.0f);
  lim2 = nvs.getFloat("lim2", 35.0f);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_SENHA);
  configTime(0, 0, "pool.ntp.org");
  Serial.printf("[no] ID %u. Para gravar: digite ID=<1..99> e Enter.\n", meuId);
}

void loop() {
  // Comissionamento pelo console serial, como no Transmissor V6.
  if (Serial.available()) {
    String s = Serial.readStringUntil('\n'); s.trim();
    if (s.startsWith("ID=")) {
      int n = s.substring(3).toInt();
      if (n >= 1 && n <= 99) { meuId = (uint8_t)n; nvs.putUChar("id", meuId); Serial.printf("[no] ID gravado: %u\n", meuId); }
    }
  }

  uint32_t agora = millis();
  // Travas que valem com ou sem rede.
  if (v1 && agora - aberto1 > TMAX_MIN * 60000UL) setValvula(1, false);
  if (v2 && agora - aberto2 > TMAX_MIN * 60000UL) setValvula(2, false);
  if ((v1 || v2) && manual && agora - ultimoHubOk > SEM_HUB_MAX_MS) { v1 = v2 = false; aplicarSaidas(); }

  if (agora - ultimoEnvio >= INTERVALO_MS) {
    ultimoEnvio = agora;
    float u1 = lerUmidade(PINO_SOLO1), u2 = lerUmidade(PINO_SOLO2);
    if (!manual) {                                   // histerese simples: abre no limite, fecha 12 pontos acima
      if (!v1 && u1 <= lim1) setValvula(1, true); else if (v1 && u1 >= lim1 + 12.0f) setValvula(1, false);
      if (!v2 && u2 <= lim2) setValvula(2, true); else if (v2 && u2 >= lim2 + 12.0f) setValvula(2, false);
    }
    if (meuId >= 1 && meuId <= 99) enviar(u1, u2);
  }
  delay(20);
}
