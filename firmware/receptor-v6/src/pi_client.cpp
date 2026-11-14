#include "pi_client.h"
#include "config.h"
#include "fila.h"

#include <WiFi.h>
#include <HTTPClient.h>
#include <Preferences.h>

#define MAX_LOTE        8       // ~4 linhas/s de vazão; 99 nós geram ~2,2/s
#define INTERVALO_MS    2000UL
#define BACKOFF_MAX_MS  60000UL

static String        _host   = PI_HOST_PADRAO;
static uint16_t      _porta  = PI_PORTA_PADRAO;
static bool          _ativo  = PI_ATIVO_PADRAO;

static bool          _ultimoOk       = false;
static unsigned long _ultimoEnvio    = 0;
static unsigned long _proximaTentativa = 0;
static unsigned long _backoff        = INTERVALO_MS;
static uint32_t      _enviados       = 0;
static uint32_t      _falhas         = 0;
static String        _ultimoErro     = "";

void piSetup() {
  Preferences p;
  if (p.begin("pi", true)) {
    _host  = p.getString("host", PI_HOST_PADRAO);
    _porta = (uint16_t)p.getUShort("porta", PI_PORTA_PADRAO);
    _ativo = p.getBool("ativo", PI_ATIVO_PADRAO);
    p.end();
  }
  Serial.printf("[Pi] Push %s para http://%s:%u%s\n",
                _ativo ? "ativo" : "desligado", _host.c_str(), _porta, PI_ROTA_WEBHOOK);
}

bool piConfigurar(const String& host, uint16_t porta, bool ativo) {
  if (host.length() == 0 || host.length() > 64) return false;
  if (porta == 0) return false;

  _host  = host;
  _porta = porta;
  _ativo = ativo;

  Preferences p;
  if (p.begin("pi", false)) {
    p.putString("host", _host);
    p.putUShort("porta", _porta);
    p.putBool("ativo", _ativo);
    p.end();
  }
  _proximaTentativa = 0;   // aplica na hora, sem esperar o backoff
  _backoff          = INTERVALO_MS;
  Serial.printf("[Pi] Configurado: http://%s:%u (%s)\n",
                _host.c_str(), _porta, _ativo ? "ativo" : "desligado");
  return true;
}

/// Há caminho de rede? O Pi pode estar na rede da fazenda (STA) **ou** ter
/// entrado no AP do próprio receptor — os dois contam.
static bool temRede() {
  return WiFi.status() == WL_CONNECTED || WiFi.softAPgetStationNum() > 0;
}

void piLoop() {
  if (!_ativo) return;
  if (millis() < _proximaTentativa) return;
  if (filaPendentesPiTotal() == 0) return;
  if (!temRede()) return;

  String   linhas[MAX_LOTE];
  uint32_t ate = 0;
  int      n   = filaPendentesPi(linhas, MAX_LOTE, ate);
  if (n == 0) return;

  String corpo;
  corpo.reserve((unsigned)n * (FILA_LINHA_MAX + 1));
  for (int i = 0; i < n; i++) { corpo += linhas[i]; corpo += "\n"; }

  WiFiClient cliente;
  HTTPClient http;
  String url = "http://" + _host + ":" + String(_porta) + PI_ROTA_WEBHOOK;

  if (!http.begin(cliente, url)) {
    _falhas++;
    _ultimoOk   = false;
    _ultimoErro = "conexao";
    _backoff    = min(_backoff * 2, BACKOFF_MAX_MS);
    _proximaTentativa = millis() + _backoff;
    return;
  }

  http.setTimeout(PI_TIMEOUT_MS);
  http.setConnectTimeout(PI_TIMEOUT_MS);
  http.addHeader("Content-Type", "text/plain; charset=utf-8");
  int codigo = http.POST(corpo);
  http.end();

  if (codigo == 200) {
    // Só avança o cursor com o 200 na mão. Se o Pi não recebeu, as linhas
    // continuam pendentes e vão junto no próximo lote.
    filaMarcarEnviado(ate);
    _enviados   += n;
    _ultimoOk    = true;
    _ultimoErro  = "";
    _ultimoEnvio = millis();
    _backoff     = INTERVALO_MS;
    _proximaTentativa = millis() + INTERVALO_MS;
    Serial.printf("[Pi] %d linha(s) entregues (ate seq %lu)\n", n, (unsigned long)ate);
  } else {
    _falhas++;
    _ultimoOk   = false;
    _ultimoErro = (codigo > 0) ? ("HTTP " + String(codigo)) : ("erro " + String(codigo));
    if (codigo == 401) {
      // Autenticação ligada no painel do Pi tranca o webhook junto — o push
      // nunca vai passar até alguém desligar uma coisa ou outra.
      _ultimoErro += " (autenticacao do painel bloqueia o webhook)";
    }
    _backoff = min(_backoff * 2, BACKOFF_MAX_MS);
    _proximaTentativa = millis() + _backoff;
    Serial.printf("[Pi] Falha: %s — nova tentativa em %lu ms\n",
                  _ultimoErro.c_str(), _backoff);
  }
}

String        piHost()               { return _host; }
uint16_t      piPorta()              { return _porta; }
bool          piAtivo()              { return _ativo; }
bool          piUltimoOk()           { return _ultimoOk; }
uint32_t      piEnviados()           { return _enviados; }
uint32_t      piFalhas()             { return _falhas; }
String        piUltimoErro()         { return _ultimoErro; }
unsigned long piMsDesdeUltimoEnvio() {
  return (_ultimoEnvio == 0) ? 0 : (millis() - _ultimoEnvio);
}
