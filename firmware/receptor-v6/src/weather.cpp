#include "weather.h"
#include "config.h"
#include "historico.h"
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <Preferences.h>

ClimaAtual clima         = {"none", 0.0f, false, false, 0, "--:--", 0};
float       weatherLat   = WEATHER_LAT;
float       weatherLon   = WEATHER_LON;
bool        reqAtualizarClima = false;

static float extrairPrecipMax(const String& json) {
  float maxRate = 0.0f;
  int pos = 0;
  while (true) {
    int idx = json.indexOf("\"precipRate\":", pos);
    if (idx < 0) break;
    idx += 13;
    int fim = json.indexOf(',', idx);
    if (fim < 0) fim = json.indexOf('}', idx);
    if (fim < 0) break;
    float v = json.substring(idx, fim).toFloat();
    if (v > maxRate) maxRate = v;
    pos = fim + 1;
  }
  return maxRate;
}

static String extrairIntensidade(const String& json) {
  int idx = json.indexOf("\"intensity\":\"");
  if (idx < 0) return "none";
  idx += 13;
  int fim = json.indexOf('"', idx);
  if (fim < 0) return "none";
  return json.substring(idx, fim);
}

void inicializarLocalizacao() {
  Preferences prefs;
  prefs.begin("irrigacao", true);
  weatherLat = prefs.getFloat("wlat", WEATHER_LAT);
  weatherLon = prefs.getFloat("wlon", WEATHER_LON);
  prefs.end();
  Serial.printf("[Clima] Local: %.4f, %.4f\n", weatherLat, weatherLon);
}

void salvarLocalizacao(float lat, float lon) {
  weatherLat = lat;
  weatherLon = lon;
  Preferences prefs;
  prefs.begin("irrigacao", false);
  prefs.putFloat("wlat", lat);
  prefs.putFloat("wlon", lon);
  prefs.end();
  Serial.printf("[Clima] Local salvo: %.4f, %.4f\n", lat, lon);
}

void atualizarClima() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[Clima] Sem WiFi, consulta ignorada");
    clima.ultimaConsulta = millis();
    return;
  }

  WiFiClientSecure sc;
  sc.setInsecure();
  HTTPClient http;

  String url = String("https://api.rainbow.ai/nowcast/v1/precip-global/")
               + String(weatherLon, 4) + "/" + String(weatherLat, 4)
               + "?token=" + WEATHER_API_KEY;

  if (!http.begin(sc, url)) {
    Serial.println("[Clima] Falha ao iniciar conexao HTTP");
    clima.ultimaConsulta = millis();
    return;
  }

  http.setTimeout(8000);
  int code = http.GET();

  if (code == HTTP_CODE_OK) {
    String resp = http.getString();
    clima.intensidade   = extrairIntensidade(resp);
    clima.precipMax     = extrairPrecipMax(resp);
    clima.chuvaEsperada = (clima.precipMax >= WEATHER_PRECIP_LIMIAR);
    clima.valido        = true;
    clima.ultimoSucesso = millis();
    String dh = obterDataHora();
    clima.horaConsulta  = (dh.length() >= 17) ? dh.substring(9, 14) : dh;
    Serial.printf("[Clima] %s | max %.2f mm/h | Chuva: %s\n",
                  clima.intensidade.c_str(), clima.precipMax,
                  clima.chuvaEsperada ? "SIM" : "NAO");
  } else if (code == 404) {
    clima.intensidade   = "none";
    clima.precipMax     = 0.0f;
    clima.chuvaEsperada = false;
    clima.valido        = true;
    clima.ultimoSucesso = millis();
    String dh = obterDataHora();
    clima.horaConsulta  = (dh.length() >= 17) ? dh.substring(9, 14) : dh;
    Serial.println("[Clima] Sem precipitacao na regiao");
  } else {
    Serial.printf("[Clima] Erro HTTP %d\n", code);
  }

  http.end();
  clima.ultimaConsulta = millis();
}

bool climaAtual() {
  return clima.valido && millis() - clima.ultimoSucesso <= WEATHER_VALIDADE_MS;
}

bool chuvaVemAi() {
  return climaAtual() && clima.chuvaEsperada;
}
