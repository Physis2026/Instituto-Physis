// ══════════════════════════════════════════════════════════════════════════════
//  RECEPTOR / GATEWAY V6 — Heltec WiFi LoRa 32 V3 (ESP32-S3 + SX1262)
//
//  · Mestre TDMA: abre cada ciclo com um beacon e recebe os nós em janelas
//    separadas, sem colisão.
//  · Acrescenta RSSI/SNR à linha e a entrega ao controle central no Raspberry Pi
//    por push (webhook) e por pull (/api/leituras, /eventos, /api/comando).
//  · Serve o painel local em AP + STA simultâneos.
//  · Grava o histórico no cartão SD.
// ══════════════════════════════════════════════════════════════════════════════

#include "heltec_unofficial.h"   // ÚNICO lugar onde este header pode entrar
#include <WiFi.h>
#include <Preferences.h>
#include <WebServer.h>
#include <ESPmDNS.h>
#include <SD.h>

#include "config.h"
#include "globals.h"
#include "protocolo.h"   // doisDigitos()
#include "historico.h"
#include "sdcard.h"
#include "lora.h"
#include "fila.h"
#include "pi_client.h"
#include "whatsapp.h"
#include "webpages.h"
#include "weather.h"

// ── Estado global ─────────────────────────────────────────────────────────────
NoRede        nos[TOTAL_NOS];
Registro      bufferRAM[MAX_REGISTROS_RAM];
int           totalBufferRAM   = 0;
long          totalRegistrosSD = 0;
bool          sdDisponivel     = false;
volatile bool pacoteRecebido   = false;
unsigned long ultimoAlerta     = 0;
bool          modoProvisionamento = false;
String        wifiSsidAtual       = "";
WebServer     server(80);

void IRAM_ATTR aoReceberPacote() { pacoteRecebido = true; }

NoRede* noPorId(int id) {
  if (id < 1 || id > TOTAL_NOS) return nullptr;
  return &nos[id - 1];
}

// ── Desligamento seguro ───────────────────────────────────────────────────────
static void desligar() {
  display.clear();
  display.drawString(0,  0, "Desligando...");
  display.drawString(0, 16, "Desmontando SD...");
  display.display();

  loraParar();               // o deep sleep reinicia o rádio: a tarefa não pode estar nele
  cancelarEnvioArquivo();    // um download aberto seguraria um arquivo do SD
  if (sdDisponivel) {
    SD.end();
    sdDisponivel = false;
  }

  delay(2000);
  display.clear();
  display.drawString(0,  0, "SD desmontado.");
  display.drawString(0, 16, "Seguro remover.");
  display.drawString(0, 32, "RST para ligar.");
  display.display();
  delay(5000);

  heltec_deep_sleep();
}

// ── Display ───────────────────────────────────────────────────────────────────
// Com ate 4 nos cabia um resumo por no na tela. Com 99 nao cabe nem a lista:
// o OLED passa a mostrar AGREGADOS e a apontar os nos que precisam de atencao,
// que e o que alguem de pe na frente do gateway precisa saber.
struct ResumoRede {
  int  online;
  int  irrigando;
  int  mudos;      // nunca falaram: placa desligada ou nao comissionada
  int  maisSeco;   // id do no com a menor umidade de controle entre os online
  float umidadeMin;
};

static ResumoRede levantarRede() {
  ResumoRede r = {0, 0, 0, 0, NAN};
  for (int i = 0; i < TOTAL_NOS; i++) {
    const NoRede& n = nos[i];
    if (n.pacotes == 0)  { r.mudos++; continue; }
    if (n.online)        r.online++;
    if (n.online && (n.c1.irrigando || n.c2.irrigando)) r.irrigando++;
    // A média dos dois sensores, que é o que o nó compara com o limiar — não o
    // sensor A sozinho (U1).
    float u = umidadeControle(n);
    if (n.online && !isnan(u) && (isnan(r.umidadeMin) || u < r.umidadeMin)) {
      r.umidadeMin = u;
      r.maisSeco   = i + 1;
    }
  }
  return r;
}

void atualizarDisplay() {
  ResumoRede r = levantarRede();

  display.clear();
  display.setFont(ArialMT_Plain_10);

  display.drawString(0, 0, "GATEWAY V6   " + String(r.online) + "/" +
                           String(TOTAL_NOS) + " ON");

  display.drawString(0, 12, "Irrigando:" + String(r.irrigando) +
                            "  Mudos:" + String(r.mudos));

  if (r.maisSeco > 0) {
    display.drawString(0, 24, "Mais seco: No " + doisDigitos((uint8_t)r.maisSeco) +
                              "  " + String(r.umidadeMin, 1) + "%");
  } else {
    display.drawString(0, 24, "Nenhum no reportando");
  }

  String pi = piAtivo() ? (piUltimoOk() ? "OK" : "ERR") : "off";
  display.drawString(0, 36, "C:" + String(cicloAtual()) +
                            " Pi:" + pi +
                            " P:" + String(filaPendentesPiTotal()) +
                            " Q:" + String(comandosPendentes()));

  String ip = (WiFi.status() == WL_CONNECTED)
                ? WiFi.localIP().toString()
                : ("AP " + WiFi.softAPIP().toString());
  display.drawString(0, 50, ip);
  display.display();
}

// ── WiFi: AP e STA SEMPRE juntos ──────────────────────────────────────────────
//
//  A versão anterior derrubava o AP assim que o STA conectava. Isso quebra os
//  dois cenários de campo previstos: o painel local some quando a rede da
//  fazenda está de pé, e o Raspberry Pi perde o endereço de fábrica que ele
//  procura (GATEWAY_HTTP_URL=http://192.168.4.1). Agora o AP fica no ar sempre.
static void subirAP() {
  WiFi.softAP(AP_SSID, AP_PASS);
  Serial.println("[WiFi] AP " AP_SSID " em " + WiFi.softAPIP().toString());
}

static void setupWiFi() {
  String pass;
  {
    Preferences p;
    p.begin("wifi-cfg", true);
    wifiSsidAtual = p.getString("ssid", WIFI_SSID);
    pass          = p.getString("pass", WIFI_PASS);
    p.end();
  }

  WiFi.mode(WIFI_AP_STA);
  subirAP();

  display.clear();
  display.drawString(0,  0, "AP: " AP_SSID);
  display.drawString(0, 14, WiFi.softAPIP().toString());
  display.drawString(0, 28, "STA: " + wifiSsidAtual);
  display.display();

  WiFi.setAutoReconnect(false);   // a reconexão é gerida por gerenciarModoWiFi()
  WiFi.begin(wifiSsidAtual.c_str(), pass.c_str());
  Serial.print("[WiFi] STA: " + wifiSsidAtual);

  unsigned long inicio = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - inicio < 8000) {
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    modoProvisionamento = false;
    Serial.println("\n[WiFi] STA OK: " + WiFi.localIP().toString());
  } else {
    modoProvisionamento = true;
    Serial.println("\n[WiFi] STA falhou — painel de provisionamento pelo AP");
  }
  delay(300);
}

/// Reconecta o STA sem nunca desligar o AP.
///
/// Em provisionamento (o STA falhou no boot) também tenta, mas espaçado: depois
/// de uma queda de energia o ESP32 volta antes do roteador, e sem nova tentativa
/// o receptor ficava sem internet até alguém reiniciá-lo — sem NTP (beacon com
/// `TS:0`, os nós sem hora e o aprendizado sem faixa horária) e sem previsão de
/// chuva. Cada tentativa varre canais e incomoda quem está no AP, por isso:
/// 5 min com o AP vazio, 30 min com alguém nele (o portal ou o Pi).
static void gerenciarModoWiFi() {
  static unsigned long ultimaGerencia  = 0;
  static unsigned long ultimoReconnect = 0;
  static bool          estavaConectado = false;

  if (millis() - ultimaGerencia < 5000) return;
  ultimaGerencia = millis();

  bool conectado = (WiFi.status() == WL_CONNECTED);

  if (conectado != estavaConectado) {
    Serial.println(conectado ? "[WiFi] STA conectou" : "[WiFi] STA caiu");
    if (conectado) {
      modoProvisionamento = false;
      ntpAoConectar();
      reqAtualizarClima = true;   // a previsão velha já não vale; busca agora
    }
    atualizarDisplay();
  }

  // O AP pode cair junto com uma reconfiguração do rádio WiFi; se sumiu, volta.
  if (WiFi.softAPgetStationNum() == 0 && WiFi.softAPIP() == IPAddress(0, 0, 0, 0)) {
    subirAP();
  }

  unsigned long intervalo = !modoProvisionamento           ? 30000UL
                          : WiFi.softAPgetStationNum() == 0 ? 5UL * 60000UL
                                                            : 30UL * 60000UL;
  if (!conectado && millis() - ultimoReconnect >= intervalo) {
    ultimoReconnect = millis();
    WiFi.reconnect();
    Serial.println("[WiFi] Tentando reconectar STA...");
  }

  estavaConectado = conectado;
}

// ══════════════════════════════════════════════════════════════════════════════

void setup() {
  Serial.begin(115200);
  delay(200);

  heltec_setup();
  heltec_ve(true);
  display.clear();
  display.drawString(0, 0, "Iniciando Gateway V6...");
  display.display();

  setupWiFi();
  setupNTP();
  sdDisponivel = setupSD();
  piSetup();

  if (MDNS.begin("irrigacao")) Serial.println("[mDNS] http://irrigacao.local");
  setupWebServer();

  inicializarLocalizacao();
  atualizarClima();

  loraSetup();
  atualizarDisplay();

  Serial.printf("[Sistema] Pronto | SD:%s | Registros:%ld | %d nos\n",
                sdDisponivel ? "OK" : "FALHOU", totalRegistrosSD, TOTAL_NOS);
}

void loop() {
  heltec_loop();
  if (button.pressedFor(2000)) desligar();

  // O TDMA roda na própria tarefa (lora.cpp); aqui só se trata o que ela
  // recebeu. Nada abaixo consegue atrasar o beacon.
  loraLoop();

  server.handleClient();
  enviarArquivoPendente();   // download do SD em partes, sem prender o loop
  verificarSSE();
  verificarOnline();
  gerenciarModoWiFi();
  piLoop();

  static unsigned long ultimoClima = 0;
  if (reqAtualizarClima || millis() - ultimoClima >= WEATHER_INTERVALO_MS) {
    reqAtualizarClima = false;
    ultimoClima       = millis();
    atualizarClima();
    // A flag de chuva não vai mais por comando endereçado: ela viaja no campo
    // `CH` de cada beacon e informa todos os nós numa transmissão só.
    notificarClientes();
  }

  static unsigned long ultimoDisplay = 0;
  if (millis() - ultimoDisplay >= 500) {
    ultimoDisplay = millis();
    atualizarDisplay();
  }

  verificarAlertas();
  delay(1);
}
