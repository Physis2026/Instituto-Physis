#include "whatsapp.h"
#include "globals.h"
#include "config.h"
#include "weather.h"

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>

#define UMIDADE_CRITICA 15.0f

void enviarWhatsApp(String mensagem) {
  if (WiFi.status() != WL_CONNECTED) return;

  // O endpoint é HTTPS: sem um WiFiClientSecure o `http.begin(url)` simples
  // falha no core do ESP32. A versão anterior não passava cliente nenhum.
  WiFiClientSecure cliente;
  cliente.setInsecure();

  String url = "https://api.callmebot.com/whatsapp.php?phone=" + String(WA_NUMERO) +
               "&text=" + mensagem + "&apikey=" + String(WA_APIKEY);

  HTTPClient http;
  if (!http.begin(cliente, url)) {
    Serial.println("[WhatsApp] Falha ao iniciar conexao");
    return;
  }
  http.setTimeout(8000);
  int codigo = http.GET();
  Serial.println("[WhatsApp] HTTP " + String(codigo));
  http.end();
}

/// Nome curto do nó para caber na mensagem (o CallMeBot recebe tudo na URL).
static String rotulo(int i) { return "No+" + String(i + 1); }

void verificarAlertas() {
  unsigned long agora = millis();
  if (agora - ultimoAlerta < INTERVALO_ALERTA_MS) return;

  // ── 1. Chuva a caminho com algum setor abaixo do limite ────────────────────
  if (chuvaVemAi()) {
    // A mensagem vai inteira na URL do CallMeBot: listar 99 nomes estouraria o
    // limite e o alerta simplesmente nao chegaria. Cita os primeiros e conta o
    // resto — quem precisa do detalhe abre o painel.
    const int MAX_CITADOS = 6;
    int    total = 0;
    String citados = "";
    for (int i = 0; i < TOTAL_NOS; i++) {
      const NoRede& n = nos[i];
      if (!n.online) continue;
      // O que a chuva inibe é o relé, e o relé obedece à MÉDIA dos dois
      // sensores contra LIM1 — não ao sensor A sozinho. O canal 2 não tem
      // válvula: não há irrigação dele para inibir.
      float u      = umidadeControle(n);
      bool  abaixo = !isnan(u) && !isnan(n.c1.limite) && u <= n.c1.limite;  // `<=` como no nó
      if (!abaixo) continue;
      if (total < MAX_CITADOS) citados += rotulo(i) + "+";
      total++;
    }
    if (total > 0) {
      String msg = "CHUVA+ESPERADA:+irrigacao+inibida+em+" + citados;
      if (total > MAX_CITADOS) msg += "e+mais+" + String(total - MAX_CITADOS) + "+";
      msg += "Int:+" + clima.intensidade;
      enviarWhatsApp(msg);
      ultimoAlerta = agora;
      return;
    }
  }

  // ── 2. Umidade crítica em qualquer nó ──────────────────────────────────────
  for (int i = 0; i < TOTAL_NOS; i++) {
    const NoRede& n = nos[i];
    if (!n.online) continue;
    float pior = NAN;
    if (!isnan(n.c1.umidade)) pior = n.c1.umidade;
    if (!isnan(n.c2.umidade) && (isnan(pior) || n.c2.umidade < pior)) pior = n.c2.umidade;
    if (!isnan(pior) && pior < UMIDADE_CRITICA) {
      String msg = "ALERTA:+umidade+critica+no+" + rotulo(i) + ":+" +
                   String((int)round(pior)) + "%25";
      if (chuvaVemAi()) msg += "+%28chuva+a+caminho%29";
      enviarWhatsApp(msg);
      ultimoAlerta = agora;
      return;
    }
  }

  // ── 3. Nós offline ─────────────────────────────────────────────────────────
  // O estado `online` é mantido por `verificarOnline()` no `lora.cpp`, por nó:
  // um transmissor mudo não derruba os outros do alerta. Aqui os offline são
  // agregados numa mensagem só — 99 alertas separados seriam ruído, e o
  // cooldown de uma hora deixaria 98 deles sem sair.
  int    offline = 0;
  String quais   = "";
  for (int i = 0; i < TOTAL_NOS; i++) {
    if (nos[i].pacotes > 0 && !nos[i].online) {
      if (offline < 6) quais += rotulo(i) + "+";
      offline++;
    }
  }
  if (offline > 0) {
    String msg = "ALERTA:+" + String(offline) + "+no(s)+offline:+" + quais;
    if (offline > 6) msg += "e+mais+" + String(offline - 6);
    enviarWhatsApp(msg);
    ultimoAlerta = agora;
  }
}
