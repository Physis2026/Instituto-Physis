#include "webpages.h"
#include "globals.h"
#include "config.h"
#include "historico.h"
#include "lora.h"
#include "protocolo.h"
#include "fila.h"
#include "pi_client.h"
#include "sdcard.h"
#include "weather.h"
#include <WiFi.h>
#include <Preferences.h>
#include <SD.h>
#include <SPI.h>

// ══════════════════════════════════════════════════════════════════════════════
//  DOIS canais de tempo real, de propósito separados:
//
//   · `/events`  — SSE do NAVEGADOR. Empurra o JSON completo do painel (os 4
//                  nós, clima, estado do enlace com o Pi).
//   · `/eventos` — SSE do RASPBERRY PI. Empurra a LINHA DE TELEMETRIA crua, uma
//                  por evento, que é o formato que `app/gateway/http_client.py`
//                  espera em `GATEWAY_ROTA_SSE`.
//
//  Misturar os dois obrigaria um dos lados a entender o formato do outro.
// ══════════════════════════════════════════════════════════════════════════════

#define MAX_SSE_CLIENTS 3   // navegadores
#define MAX_SSE_PI      2   // controle central

static WiFiClient sseClientes[MAX_SSE_CLIENTS];
static bool       sseAtivo[MAX_SSE_CLIENTS] = {false};

static WiFiClient ssePi[MAX_SSE_PI];
static bool       ssePiAtivo[MAX_SSE_PI]   = {false};
static uint32_t   ssePiCursor[MAX_SSE_PI]  = {0};

static String htmlEscape(const String& s) {
  String r = s;
  r.replace("&", "&amp;");
  r.replace("<", "&lt;");
  r.replace(">", "&gt;");
  r.replace("\"", "&quot;");
  return r;
}

// ══════════════════════════════════════════════════════════════════════════════
//  Serialização do painel — escrita DIRETA no socket, sem String intermediária.
//
//  A versão de 4 nós montava o JSON inteiro numa `String` e só então enviava.
//  Com 99 nós isso seria uma alocação contígua de ~25 KB, remontada a cada
//  pacote recebido: heap fragmentada e picos de RAM que derrubam o servidor web
//  justamente quando a rede está cheia. Aqui cada campo vai direto para o
//  `Print` (o socket), então o custo de memória não depende do número de nós.
//
//  São DOIS payloads, de propósito:
//
//    · RESUMO   — todos os nós, só o que a tabela mostra. Chaves curtas porque
//                 isto vai para o navegador a cada atualização: ~56 B por nó,
//                 ~5,5 KB com a rede cheia.
//    · DETALHE  — um nó só, com tudo. Buscado sob demanda quando o operador
//                 clica na linha da tabela.
//
//  Enviar o detalhe de 99 nós a cada ciclo seria 25 KB de WiFi por atualização
//  para mostrar dados que ninguém está olhando.
// ══════════════════════════════════════════════════════════════════════════════

/// `null` em vez de `0` quando não há leitura: no painel isso vira "--" em vez
/// de um zero que parece medida.
static void pnum(Print& out, float v, int casas = 1) {
  if (isnan(v)) out.print("null");
  else          out.print(v, casas);
}

static void pbool(Print& out, bool v) { out.print(v ? "true" : "false"); }

/// Segundos desde o último pacote daquele nó (0 se ele nunca falou).
static unsigned long vistoHa(const NoRede& n) {
  return n.pacotes ? (millis() - n.ultimoPacket) / 1000UL : 0UL;
}

/// Cauda comum aos dois payloads: clima, enlace com o Pi, TDMA e cartão.
/// Escreve sem as chaves externas — quem chama abre e fecha o objeto.
static void escreverContexto(Print& out) {
  out.print("\"clima\":{\"chuva\":");
  pbool(out, chuvaVemAi());
  out.print(",\"intens\":\"");   out.print(clima.intensidade);
  out.print("\",\"precip\":");   out.print(clima.precipMax, 2);
  out.print(",\"valido\":");     pbool(out, climaAtual());
  out.print(",\"hora\":\"");     out.print(clima.horaConsulta);

  out.print("\"},\"pi\":{\"ativo\":");
  pbool(out, piAtivo());
  out.print(",\"ok\":");         pbool(out, piUltimoOk());
  out.print(",\"host\":\"");     out.print(piHost());
  out.print(':');                out.print(piPorta());
  out.print("\",\"enviados\":"); out.print(piEnviados());
  out.print(",\"falhas\":");     out.print(piFalhas());
  out.print(",\"pendentes\":");  out.print(filaPendentesPiTotal());
  out.print(",\"erro\":\"");     out.print(piUltimoErro());

  out.print("\"},\"tdma\":{\"ciclo\":");
  out.print(cicloMs());
  out.print(",\"cicloMax\":");   out.print((unsigned long)CICLO_MAX_MS);
  out.print(",\"slot\":");       out.print((unsigned long)SLOT_MS);
  out.print(",\"guarda\":");     out.print((unsigned long)GUARDA_MS);
  out.print(",\"beacons\":");    out.print(beaconsEnviados());
  out.print(",\"cmdFila\":");    out.print(comandosPendentes());
  out.print(",\"rxDescartados\":"); out.print(linhasRxDescartadas());

  out.print("},\"dataHora\":\""); out.print(obterDataHora());
  out.print("\",\"registros\":");  out.print(totalRegistrosSD);
  out.print(",\"sd\":");           pbool(out, sdDisponivel);
}

/// RESUMO: um objeto enxuto por nó. Chaves curtas — `u1`/`u2` são as umidades,
/// `ir` diz se QUALQUER canal está irrigando, `v` é "visto há N segundos".
/// Só entram os nós que já falaram alguma vez (`conhecido`): listar os 99 slots
/// possíveis enchia a tabela de linhas vazias e inflava cada atualização.
static void escreverResumo(Print& out) {
  int online = 0;
  for (int i = 0; i < TOTAL_NOS; i++) if (nos[i].online) online++;

  out.print("{\"total\":");   out.print(TOTAL_NOS);
  out.print(",\"online\":");  out.print(online);
  out.print(",\"nos\":[");

  bool primeiro = true;
  for (int i = 0; i < TOTAL_NOS; i++) {
    const NoRede& n = nos[i];
    if (!n.conhecido) continue;
    if (!primeiro) out.print(',');
    primeiro = false;
    out.print("{\"id\":");  out.print(i + 1);
    out.print(",\"on\":");  out.print(n.online ? 1 : 0);
    out.print(",\"u1\":");  pnum(out, n.c1.umidade);
    out.print(",\"u2\":");  pnum(out, n.c2.umidade);
    out.print(",\"ir\":");  out.print((n.c1.irrigando || n.c2.irrigando) ? 1 : 0);
    out.print(",\"t\":");   pnum(out, n.temp);
    out.print(",\"ts\":");  pnum(out, n.tempSolo);
    out.print(",\"v\":");   out.print(vistoHa(n));
    out.print(",\"p\":");   out.print(n.pacotes);
    out.print('}');
  }

  out.print("],");
  escreverContexto(out);
  out.print('}');
}

/// DETALHE de um nó, com nomes por extenso. `id` é 1-based.
/// `um` é a umidade de controle (média dos sensores): é ela que `lim1`, `p1` e
/// `ir1` descrevem — `u1` é só o sensor A.
static void escreverDetalhe(Print& out, int id) {
  const NoRede& n = nos[id - 1];
  out.print("{\"id\":");        out.print(id);
  out.print(",\"online\":");    pbool(out, n.online);
  out.print(",\"um\":");        pnum(out, umidadeControle(n));
  out.print(",\"u1\":");        pnum(out, n.c1.umidade);
  out.print(",\"ir1\":");       pbool(out, n.c1.irrigando);
  out.print(",\"lim1\":");      pnum(out, n.c1.limite);
  out.print(",\"p1\":");        pnum(out, n.c1.previsao, 0);
  out.print(",\"u2\":");        pnum(out, n.c2.umidade);
  out.print(",\"ir2\":");       pbool(out, n.c2.irrigando);
  out.print(",\"lim2\":");      pnum(out, n.c2.limite);
  out.print(",\"p2\":");        pnum(out, n.c2.previsao, 0);
  out.print(",\"temp\":");      pnum(out, n.temp);
  out.print(",\"uar\":");       pnum(out, n.umidadeAr);
  out.print(",\"tsolo\":");     pnum(out, n.tempSolo);
  out.print(",\"bat\":");       pnum(out, n.bateria, 2);
  out.print(",\"rssi\":");      out.print(n.rssi, 1);
  out.print(",\"snr\":");       out.print(n.snr, 1);
  out.print(",\"relogio\":");   pbool(out, n.comRelogio);
  out.print(",\"pacotes\":");   out.print(n.pacotes);
  out.print(",\"perdidos\":");  out.print(ciclosPerdidosNo(id));
  out.print(",\"visto\":");     out.print(vistoHa(n));
  out.print('}');
}

// ── SSE do navegador ──────────────────────────────────────────────────────────
//
// A atualização é COALESCIDA. `notificarClientes()` só marca o painel como
// sujo; quem envia é `verificarSSE()`, no máximo a cada INTERVALO_PAINEL_MS.
//
// Sem isso, com 99 nós chegando ~2 pacotes por segundo, cada pacote dispararia
// uma serialização completa para cada navegador conectado — trabalho jogado
// fora, porque o olho humano não acompanha e o dado seguinte já vem em seguida.

#define INTERVALO_PAINEL_MS 1000UL

static bool          _painelSujo   = false;
static unsigned long _ultimoPainel = 0;

void notificarClientes() { _painelSujo = true; }

/// Envia o resumo para todos os navegadores conectados.
static void empurrarPainel() {
  _painelSujo   = false;
  _ultimoPainel = millis();

  for (int i = 0; i < MAX_SSE_CLIENTS; i++) {
    if (!sseAtivo[i]) continue;
    if (!sseClientes[i].connected()) {
      sseClientes[i].stop();
      sseAtivo[i] = false;
      Serial.println("[SSE] Navegador " + String(i) + " desconectou");
      continue;
    }
    sseClientes[i].print("data: ");
    escreverResumo(sseClientes[i]);
    sseClientes[i].print("\n\n");
  }
}

void handleEvents() {
  int slot = -1;
  for (int i = 0; i < MAX_SSE_CLIENTS; i++) {
    if (!sseAtivo[i]) { slot = i; break; }
  }
  if (slot == -1) { server.send(503, "text/plain", "Muitos clientes"); return; }

  WiFiClient cliente = server.client();
  cliente.println("HTTP/1.1 200 OK");
  cliente.println("Content-Type: text/event-stream");
  cliente.println("Cache-Control: no-cache");
  cliente.println("Connection: keep-alive");
  cliente.println("Access-Control-Allow-Origin: *");
  cliente.println();
  cliente.print("data: ");
  escreverResumo(cliente);
  cliente.print("\n\n");
  sseClientes[slot] = cliente;
  sseAtivo[slot]    = true;
  Serial.println("[SSE] Navegador " + String(slot) + " conectado");
}

// ── SSE do controle central: uma linha de telemetria por evento ───────────────

void handleEventosPi() {
  int slot = -1;
  for (int i = 0; i < MAX_SSE_PI; i++) {
    if (!ssePiAtivo[i]) { slot = i; break; }
  }
  if (slot == -1) { server.send(503, "text/plain", "Muitos assinantes"); return; }

  WiFiClient cliente = server.client();
  cliente.println("HTTP/1.1 200 OK");
  cliente.println("Content-Type: text/event-stream");
  cliente.println("Cache-Control: no-cache");
  cliente.println("Connection: keep-alive");
  cliente.println("Access-Control-Allow-Origin: *");
  cliente.println();

  ssePi[slot]       = cliente;
  ssePiAtivo[slot]  = true;
  // Começa do agora: o histórico de quem chegou depois sai pelo polling em
  // `/api/leituras?desde=`, que é onde o cursor do Pi é reconstruído.
  ssePiCursor[slot] = filaUltimoSeq();
  Serial.println("[SSE] Controle central " + String(slot) + " conectado");
}

static void entregarSSEPi() {
  uint32_t ultimo = filaUltimoSeq();
  // Mesmo piso do polling: o que o push já entregou não sai de novo por aqui.
  uint32_t piso = piAtivo() ? filaEnviadoAte() : 0;

  for (int i = 0; i < MAX_SSE_PI; i++) {
    if (!ssePiAtivo[i]) continue;
    if (!ssePi[i].connected()) {
      ssePi[i].stop();
      ssePiAtivo[i] = false;
      Serial.println("[SSE] Controle central " + String(i) + " desconectou");
      continue;
    }

    uint32_t de = (ssePiCursor[i] > piso) ? ssePiCursor[i] : piso;
    if (de >= ultimo) { ssePiCursor[i] = de; continue; }

    String   lote[8];
    uint32_t ate = de;
    int      n   = filaDesde(de, lote, 8, ate);
    for (int k = 0; k < n; k++) ssePi[i].print("data: " + lote[k] + "\n\n");
    ssePiCursor[i] = ate;
  }
}

void verificarSSE() {
  entregarSSEPi();   // a cada volta: o Pi não deve esperar o heartbeat

  // Painel: envia no máximo uma vez por INTERVALO_PAINEL_MS, e só se algo mudou.
  if (_painelSujo && millis() - _ultimoPainel >= INTERVALO_PAINEL_MS) {
    empurrarPainel();
  }

  static unsigned long ultimoHB = 0;
  if (millis() - ultimoHB < 5000) return;
  ultimoHB = millis();

  for (int i = 0; i < MAX_SSE_CLIENTS; i++) {
    if (!sseAtivo[i]) continue;
    if (!sseClientes[i].connected()) {
      sseClientes[i].stop();
      sseAtivo[i] = false;
      Serial.println("[SSE] Navegador " + String(i) + " desconectou (HB)");
    } else {
      sseClientes[i].print(": hb\n\n");
    }
  }
  for (int i = 0; i < MAX_SSE_PI; i++) {
    if (!ssePiAtivo[i]) continue;
    if (!ssePi[i].connected()) {
      ssePi[i].stop();
      ssePiAtivo[i] = false;
    } else {
      ssePi[i].print(": hb\n\n");
    }
  }
}

// ── Provisionamento WiFi ──────────────────────────────────────
static void handleWifiSetup() {
  static String        scanCache    = "";
  static unsigned long ultimoScanMs = 0;
  bool forcarScan = server.hasArg("scan");

 
  if (forcarScan || scanCache.isEmpty() || millis() - ultimoScanMs > 30000UL) {
    int n = WiFi.scanNetworks();
    scanCache = "";
    if (n == 0) {
      scanCache = "<div class='nenhuma'>Nenhuma rede encontrada.</div>";
    } else {
      int lim = n > 20 ? 20 : n;
      for (int i = 0; i < lim; i++) {
        String ssid = WiFi.SSID(i);
        int    rssi = WiFi.RSSI(i);
        bool   enc  = WiFi.encryptionType(i) != WIFI_AUTH_OPEN;
        String cor  = rssi > -65 ? "#2e7d32" : rssi > -75 ? "#e65100" : "#c62828";
        String esc  = htmlEscape(ssid);
        scanCache += "<label class='rede' data-ssid=\"" + esc + "\">";
        scanCache += "<input type='radio' name='_r' value='" + String(i) + "'>";
        scanCache += "<span class='rede-nome'>" + esc + "</span>";
        scanCache += "<span class='rede-inf' style='color:" + cor + "'>" + String(rssi) + " dBm</span>";
        scanCache += enc ? "<span class='rede-inf'>&#128274;</span>"
                         : "<span class='rede-inf'>&#128275;</span>";
        scanCache += "</label>";
      }
    }
    WiFi.scanDelete();
    ultimoScanMs = millis();
  }

  String html = R"=====(
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Configurar WiFi</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:Arial,sans-serif;background:#e3f2fd;padding:16px}
    h1{text-align:center;color:#1565C0;font-size:1.3em;margin-bottom:12px}
    .card{background:#fff;border-radius:12px;padding:18px;max-width:420px;margin:0 auto;box-shadow:0 2px 8px rgba(0,0,0,.12)}
    .aviso{background:#e8eaf6;border-left:4px solid #3949AB;padding:8px 12px;border-radius:0 6px 6px 0;font-size:.83em;color:#1a237e;margin-bottom:14px}
    .rede{display:flex;align-items:center;padding:10px 12px;border:1px solid #ddd;border-radius:8px;margin-bottom:5px;cursor:pointer;background:#fafafa}
    .rede:hover,.rede.sel{background:#e8f5e9;border-color:#4CAF50}
    .rede input[type=radio]{margin-right:9px;accent-color:#4CAF50}
    .rede-nome{flex:1;font-size:.92em;font-weight:bold;text-align:left;word-break:break-all}
    .rede-inf{font-size:.76em;margin-left:5px;white-space:nowrap}
    .nenhuma{color:#aaa;font-size:.87em;padding:10px 0;text-align:center}
    .fg{margin:12px 0}
    .lbl{font-size:.88em;color:#444;display:block;margin-bottom:4px}
    input[type=text],input[type=password]{padding:10px;font-size:15px;width:100%;border:1px solid #ccc;border-radius:6px}
    .hint{font-size:.77em;color:#888;margin-top:4px}
    .btn{padding:12px;width:100%;border:none;border-radius:6px;font-size:1em;cursor:pointer;color:#fff;margin-top:6px;display:block}
    .btn-con{background:#4CAF50}
    .btn-scan{background:#1565C0;margin-top:10px;padding:9px;font-size:.9em}
  </style>
</head>
<body>
  <h1>Configurar WiFi</h1>
  <div class="card">
    <div class="aviso">
      Falha ao conectar ao WiFi.<br>
      SSID configurado: <strong>%SSID_ATUAL%</strong>
    </div>
    <form action="/wifi-save" method="POST">
      <p style="font-size:.85em;color:#555;margin-bottom:8px"><b>Redes encontradas:</b></p>
      %REDES%
      <div class="fg" style="margin-top:10px">
        <label class="lbl">Nome da rede (SSID):</label>
        <input type="text" name="ssid" id="ssid-inp" placeholder="Selecione acima ou digite" required>
      </div>
      <div class="fg">
        <label class="lbl">Senha:</label>
        <input type="password" name="pass" id="pass-inp" placeholder="Deixe vazio para rede aberta">
        <div class="hint">Redes abertas &#128275; nao precisam de senha.</div>
      </div>
      <button type="submit" class="btn btn-con">Conectar e Salvar</button>
    </form>
    <button class="btn btn-scan" onclick="location.href='/wifi-setup?scan=1'">&#128260; Buscar Redes Novamente</button>
  </div>
  <script>
    document.querySelectorAll('.rede').forEach(el=>{
      el.addEventListener('click',()=>{
        document.querySelectorAll('.rede').forEach(r=>r.classList.remove('sel'));
        el.classList.add('sel');
        el.querySelector('input').checked=true;
        document.getElementById('ssid-inp').value=el.dataset.ssid;
        document.getElementById('pass-inp').focus();
      });
    });
  </script>
</body>
</html>
)=====";

  html.replace("%SSID_ATUAL%", htmlEscape(wifiSsidAtual));
  html.replace("%REDES%", scanCache);
  server.send(200, "text/html; charset=utf-8", html);
}

static void handleWifiSave() {
  String ssid = server.arg("ssid");
  String pass = server.arg("pass");

  if (ssid.length() == 0) {
    server.sendHeader("Location", "/wifi-setup");
    server.send(303);
    return;
  }

  {
    Preferences p;
    p.begin("wifi-cfg", false);
    p.putString("ssid", ssid);
    p.putString("pass", pass);
    p.end();
  }
  Serial.println("[WiFi] Credenciais salvas: " + ssid);

  String html = R"=====(
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Salvando...</title>
  <style>
    body{font-family:Arial;background:#e8f5e9;padding:40px 16px;text-align:center}
    .card{background:#fff;border-radius:12px;padding:24px;max-width:380px;margin:0 auto;box-shadow:0 2px 8px rgba(0,0,0,.1)}
    h2{color:#2e7d32;margin-bottom:12px}
    p{color:#555;font-size:.9em;margin:7px 0}
    .spin{display:inline-block;width:36px;height:36px;border:4px solid #e0e0e0;border-top-color:#4CAF50;border-radius:50%;animation:giro 1s linear infinite;margin:14px 0}
    @keyframes giro{to{transform:rotate(360deg)}}
    .net{font-weight:bold;color:#1565C0}
    .dica{margin-top:16px;font-size:.82em;color:#777;border-top:1px solid #eee;padding-top:12px;text-align:left;line-height:1.6}
  </style>
</head>
<body>
  <div class="card">
    <h2>Credenciais Salvas</h2>
    <div class="spin"></div>
    <p>Rede: <span class="net">%SSID%</span></p>
    <p>Reiniciando o ESP32...</p>
    <div class="dica">
      <b>O AP continua no ar de qualquer jeito.</b><br>
      Ele e o endereco de fabrica que o controle central procura,<br>
      e o painel local nao pode sumir quando a rede cai.<br><br>
      <b>Se conectar:</b> acesse tambem pelo IP do roteador<br>
      ou por <b>irrigacao.local</b><br><br>
      <b>Se falhar:</b> continue no AP <b>ESP32_IRRIGA_V3</b><br>
      e acesse <b>192.168.4.1</b> para tentar novamente.
    </div>
  </div>
</body>
</html>
)=====";

  html.replace("%SSID%", htmlEscape(ssid));

  WiFiClient c = server.client();
  c.println("HTTP/1.1 200 OK");
  c.println("Content-Type: text/html; charset=utf-8");
  c.println("Connection: close");
  c.println();
  c.print(html);
  c.flush();
  delay(1500);
  ESP.restart();
}


void handleRoot() {
  // O painel NUNCA cede lugar ao provisionamento: numa instalação em que o
  // Raspberry entra no AP do próprio receptor e não existe rede da fazenda,
  // redirecionar para /wifi-setup deixaria o painel inacessível para sempre.
  //
  // A página é enviada em pedaços (`enviarPedaco`) em vez de montada numa
  // String única: com 99 nós o HTML+CSS+JS passa de 20 KB, e alocar isso de uma
  // vez numa heap já ocupada pela fila de telemetria é pedir para o servidor
  // web cair quando a rede está cheia.
  WiFiClient c = server.client();
  c.println("HTTP/1.1 200 OK");
  c.println("Content-Type: text/html; charset=utf-8");
  c.println("Connection: close");
  c.println();

  c.print(F(R"=====(<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Irrigação — Gateway V6</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:system-ui,Arial,sans-serif;background:#eef2ee;color:#222;padding:12px}
  h1{font-size:1.2em;color:#1b5e20}
  .topo{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;margin-bottom:10px}
  .topo-inf{display:flex;gap:12px;align-items:center;font-size:.8em;color:#555;flex-wrap:wrap}
  .dot{width:9px;height:9px;border-radius:50%;background:#4CAF50;display:inline-block;margin-right:5px;animation:pulso 2s infinite}
  .dot.off{background:#c62828;animation:none}
  @keyframes pulso{50%{opacity:.25}}
  .cartao{background:#fff;border-radius:10px;padding:12px;box-shadow:0 2px 8px rgba(0,0,0,.09);margin-bottom:12px}
  .cartao h2{font-size:1em;color:#1b5e20;margin-bottom:8px}
  .faixa{background:#fff8e1;border-left:4px solid #ef6c00;padding:9px 13px;border-radius:0 7px 7px 0;font-size:.82em;color:#5d4037;margin-bottom:12px}
  .faixa a{color:#1565C0}
  .resumo{display:flex;gap:16px;flex-wrap:wrap;font-size:.85em;margin-bottom:10px}
  .resumo b{font-size:1.5em;display:block;color:#1b5e20}
  .filtros{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
  .filtros button{padding:5px 11px;border:none;border-radius:14px;background:#cfd8dc;color:#37474f;font-size:.78em;cursor:pointer}
  .filtros button.sel{background:#1b5e20;color:#fff}
  table{width:100%;border-collapse:collapse;font-size:.82em}
  th{background:#e8f0e8;color:#1b5e20;padding:7px 6px;text-align:left;position:sticky;top:0;font-size:.92em}
  td{padding:6px;border-bottom:1px solid #f0f0f0}
  tr.no{cursor:pointer}
  tr.no:hover{background:#f1f8e9}
  tr.off{opacity:.5}
  .bolha{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px}
  .b-ok{background:#4CAF50}.b-off{background:#9e9e9e}.b-irr{background:#0288D1}
  .barra{height:7px;background:#e6e6e6;border-radius:4px;overflow:hidden;min-width:52px;position:relative}
  .barra i{display:block;height:100%;background:#4CAF50}
  .barra i.seco{background:#e53935}
  .vazio{color:#aaa;text-align:center;padding:18px;font-size:.9em}
  dialog{border:none;border-radius:12px;padding:0;max-width:430px;width:92%;box-shadow:0 8px 30px rgba(0,0,0,.3)}
  dialog::backdrop{background:rgba(0,0,0,.45)}
  .dlg-topo{background:#1b5e20;color:#fff;padding:12px 16px;display:flex;justify-content:space-between;align-items:center}
  .dlg-topo b{font-size:1.05em}
  .dlg-corpo{padding:14px 16px}
  .kv{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:10px 0;font-size:.76em;color:#666;text-align:center}
  .kv b{display:block;font-size:1.25em;color:#222}
  .acoes{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
  button.act{padding:7px 11px;border:none;border-radius:6px;color:#fff;font-size:.79em;cursor:pointer}
  .bt-on{background:#0288D1}.bt-off{background:#e53935}.bt-auto{background:#4CAF50}
  .bt-man{background:#795548}.bt-ping{background:#607d8b}.bt-save{background:#2e7d32}.bt-x{background:#455a64}
  .lim{display:flex;gap:6px;align-items:center;margin-top:9px;font-size:.76em;color:#555}
  .lim input{width:60px;padding:5px;border:1px solid #ccc;border-radius:5px}
  .nav{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
  .nav a{padding:8px 14px;border-radius:6px;background:#455a64;color:#fff;text-decoration:none;font-size:.82em}
  .nav a.verde{background:#2e7d32}
  .aviso{font-size:.72em;color:#b71c1c}
</style>
</head>
<body>

<div class="topo">
  <h1>Irrigação — Gateway V6</h1>
  <div class="topo-inf">
    <span><span class="dot" id="sse-dot"></span><span id="sse-status">Conectando…</span></span>
    <span id="hora-atual">--:--:--</span>
    <span id="tdma-inf">TDMA --</span>
    <span id="pi-inf">Pi --</span>
    <span id="sd-inf">SD --</span>
  </div>
</div>

)====="));

  // Sem STA o gateway continua inteiro no ar pelo AP: recebe os nos, grava no
  // SD e serve o Raspberry. O que se perde e NTP, nowcast e alerta.
  if (WiFi.status() != WL_CONNECTED) {
    c.print(F("<div class='faixa'><b>Sem rede WiFi da fazenda.</b> A recepcao LoRa, o "
              "cartao SD e a entrega ao Raspberry pelo AP seguem funcionando; ficam de "
              "fora o relogio por NTP, a previsao de chuva e os alertas. "
              "<a href='/wifi-setup'>Configurar rede</a></div>"));
  }

  c.print(F(R"=====(

<div class="cartao">
  <div class="resumo">
    <div><b id="r-online">--</b>online</div>
    <div><b id="r-total">--</b>conhecidos</div>
    <div><b id="r-irr">--</b>irrigando</div>
    <div><b id="r-off">--</b>offline</div>
    <div><b id="r-chuva">--</b>chuva</div>
  </div>
  <div class="filtros">
    <button class="sel" onclick="filtrar('todos',this)">Todos</button>
    <button onclick="filtrar('online',this)">Online</button>
    <button onclick="filtrar('offline',this)">Offline</button>
    <button onclick="filtrar('irrigando',this)">Irrigando</button>
    <button onclick="filtrar('secos',this)">Mais secos</button>
  </div>
  <div style="overflow-x:auto">
    <table>
      <thead><tr>
        <th>Nó</th><th>Sensor A</th><th>Sensor B</th><th>Temp</th><th>Solo</th><th>Visto</th>
      </tr></thead>
      <tbody id="corpo"></tbody>
    </table>
  </div>
  <div class="vazio" id="vazio" hidden></div>
</div>

<div class="nav">
  <a href="/config">⚙ Configurar</a>
  <a href="/tabela">📋 Registros</a>
  <a href="/download" class="verde">⬇ Baixar CSV</a>
  <a href="/files">📁 Arquivos SD</a>
  <a href="/api/estado">🔎 Diagnóstico</a>
  <a href="/ejetar">⏏ Ejetar SD</a>
</div>

<dialog id="dlg">
  <div class="dlg-topo"><b id="d-tit">Nó</b><button class="act bt-x" onclick="dlg.close()">Fechar</button></div>
  <div class="dlg-corpo" id="d-corpo"></div>
</dialog>

<script>
// O resumo usa chaves curtas de propósito: com 99 nós, nomes por extenso
// dobrariam o tamanho de cada atualização enviada ao navegador.
//   id, on(online), u1/u2(umidades), ir(algum relé ligado), t(temp do ar),
//   ts(temp do solo), v(visto há N s), p(pacotes recebidos desde o boot)
// Só vêm os nós que já falaram alguma vez; `p` = 0 é um nó conhecido que ainda
// não falou desde o último reboot do gateway.
let ultimo = null, filtro = 'todos', aberto = 0;
const dlg = document.getElementById('dlg');

function fmt(v, c, s) {
  if (v === null || v === undefined || isNaN(v)) return '--';
  return Number(v).toFixed(c === undefined ? 1 : c) + (s || '');
}
// P1 em minutos: o nó mede a secagem de verdade e a previsão vai a dias.
// 43200 = PREVISAO_MAX_MIN do Transmissor V6 (o limiar não chega em 30 dias).
// null = o nó não tem leitura de solo para prever; -1 = modelo aprendendo.
function prev(m) {
  if (m === null || m === undefined || isNaN(m)) return '--';
  if (m < 0) return 'Aprend.';
  if (m >= 43200) return '&gt;30 d';
  if (m < 90) return Math.round(m) + ' min';
  return m < 2880 ? (m / 60).toFixed(1) + ' h' : (m / 1440).toFixed(1) + ' d';
}
function idade(s, on, p) {
  if (!on) return p ? 'offline' : 'sem sinal desde o boot';
  return s < 60 ? s + 's' : Math.floor(s / 60) + 'm';
}
function barra(v, seco) {
  const x = (v === null || isNaN(v)) ? 0 : Math.max(0, Math.min(100, v));
  return '<div class="barra"><i class="' + (seco ? 'seco' : '') +
         '" style="width:' + x + '%"></i></div>';
}

function selecionar(nos) {
  if (filtro === 'online')    return nos.filter(n => n.on);
  if (filtro === 'offline')   return nos.filter(n => !n.on);
  if (filtro === 'irrigando') return nos.filter(n => n.ir);
  if (filtro === 'secos') {
    return nos.filter(n => n.on && n.u1 !== null)
              .sort((a, b) => a.u1 - b.u1).slice(0, 20);
  }
  return nos;
}

function pintar(j) {
  ultimo = j;
  const nos = selecionar(j.nos);
  const corpo = document.getElementById('corpo');

  corpo.innerHTML = nos.map(n =>
    '<tr class="no' + (n.on ? '' : ' off') + '" onclick="abrir(' + n.id + ')">' +
    '<td><span class="bolha ' + (n.ir ? 'b-irr' : (n.on ? 'b-ok' : 'b-off')) + '"></span>' +
      String(n.id).padStart(2, '0') + '</td>' +
    '<td>' + (n.on ? fmt(n.u1, 1, '%') : '--') + barra(n.on ? n.u1 : null) + '</td>' +
    '<td>' + (n.on ? fmt(n.u2, 1, '%') : '--') + barra(n.on ? n.u2 : null) + '</td>' +
    '<td>' + fmt(n.t, 1, '°') + '</td>' +
    '<td>' + fmt(n.ts, 1, '°') + '</td>' +
    '<td>' + idade(n.v, n.on, n.p) + '</td></tr>'
  ).join('');

  const vazio = document.getElementById('vazio');
  vazio.hidden = nos.length > 0;
  vazio.textContent = j.nos.length
    ? 'Nenhum nó neste filtro.'
    : 'Nenhum nó se conectou ainda. Cada nó aparece aqui assim que o primeiro pacote dele chega.';

  document.getElementById('r-online').textContent = j.online;
  document.getElementById('r-total').textContent  = j.nos.length;
  document.getElementById('r-irr').textContent    = j.nos.filter(n => n.ir).length;
  document.getElementById('r-off').textContent    = j.nos.filter(n => !n.on).length;
  document.getElementById('r-chuva').textContent  = j.clima.chuva ? 'sim' : 'não';

  document.getElementById('tdma-inf').textContent =
    'TDMA ' + (j.tdma.ciclo / 1000) + 's · ciclo ' + j.tdma.beacons +
    (j.tdma.cmdFila ? ' · ' + j.tdma.cmdFila + ' cmd' : '');
  document.getElementById('pi-inf').textContent =
    !j.pi.ativo ? 'Pi: push desligado'
    : (j.pi.ok ? 'Pi ' + j.pi.host + ' OK (' + j.pi.enviados + ')'
               : 'Pi ' + j.pi.host + ' ✗ ' + (j.pi.erro || '') + ' · ' + j.pi.pendentes + ' pend.');
  document.getElementById('sd-inf').textContent =
    j.sd ? 'SD ' + j.registros + ' reg.' : 'SD ausente';

  if (aberto) desenharDetalhe();
}

function filtrar(f, b) {
  filtro = f;
  document.querySelectorAll('.filtros button').forEach(x => x.classList.remove('sel'));
  b.classList.add('sel');
  if (ultimo) pintar(ultimo);
}

// ── Detalhe sob demanda ────────────────────────────────────────────────────
// Buscado só quando o operador clica. Mandar isto de 99 nós a cada ciclo
// seriam ~25 KB por atualização para mostrar dado que ninguém está olhando.
async function abrir(id) {
  aberto = id;
  document.getElementById('d-tit').textContent = 'Nó ' + String(id).padStart(2, '0');
  document.getElementById('d-corpo').innerHTML = '<p style="color:#888">Carregando…</p>';
  dlg.showModal();
  desenharDetalhe();
}
dlg.addEventListener('close', () => { aberto = 0; });

async function desenharDetalhe() {
  const id = aberto;
  if (!id) return;
  let d;
  try { d = await (await fetch('/api/no?id=' + id)).json(); }
  catch (e) { return; }
  if (aberto !== id) return;

  document.getElementById('d-corpo').innerHTML =
    // O relé obedece à MÉDIA dos dois sensores (limiar LIM1, previsão P1); o
    // sensor B tem limiar e previsão próprios só para acompanhamento.
    '<div><b>Média (controle)</b> ' + fmt(d.um, 1, '%') + ' (limiar ' + fmt(d.lim1, 1, '%') +
      ', previsão ' + prev(d.p1) + ')' +
      (d.ir1 ? ' — <span style="color:#0288D1"><b>IRRIGANDO</b></span>' : '') + '</div>' +
    '<div style="margin-top:4px"><b>Sensor A</b> ' + fmt(d.u1, 1, '%') +
      ' · <b>Sensor B</b> ' + fmt(d.u2, 1, '%') +
      ' (limiar ' + fmt(d.lim2, 1, '%') + ', previsão ' + prev(d.p2) + ')</div>' +
    '<div class="kv">' +
      '<div><b>' + fmt(d.temp, 1) + '</b>Temp ar °C</div>' +
      '<div><b>' + fmt(d.uar, 0) + '</b>Umid. ar %</div>' +
      '<div><b>' + fmt(d.tsolo, 1) + '</b>Temp solo °C</div>' +
      '<div><b>' + fmt(d.rssi, 0) + '</b>RSSI dBm</div>' +
      '<div><b>' + fmt(d.snr, 1) + '</b>SNR dB</div>' +
      '<div><b>' + fmt(d.bat, 2) + '</b>Bateria V</div>' +
    '</div>' +
    '<div style="font-size:.76em;color:#777">' + d.pacotes + ' pacotes · ' +
      d.perdidos + ' ciclos perdidos · visto há ' + d.visto + 's</div>' +
    (d.online && !d.relogio ? '<div class="aviso">Sem relógio: aguardando o TS: do beacon.</div>' : '') +
    '<div class="acoes">' +
      '<button class="act bt-on"   onclick="cmd(' + id + ',&quot;IRR1:1&quot;)">Irrigar</button>' +
      '<button class="act bt-off"  onclick="cmd(' + id + ',&quot;IRR1:0&quot;)">Parar</button>' +
      '<button class="act bt-auto" onclick="cmd(' + id + ',&quot;MODO:AUTO&quot;)">Auto</button>' +
      '<button class="act bt-man"  onclick="cmd(' + id + ',&quot;MODO:MANUAL&quot;)">Manual</button>' +
      '<button class="act bt-ping" onclick="cmd(' + id + ',&quot;PING&quot;)">Ping</button>' +
    '</div>' +
    '<div class="lim">Limiar média <input type="number" id="l1" min="0" max="100" step="0.1" value="' +
      (d.lim1 === null ? '' : d.lim1) + '">' +
    ' B <input type="number" id="l2" min="0" max="100" step="0.1" value="' +
      (d.lim2 === null ? '' : d.lim2) + '">' +
    '<button class="act bt-save" onclick="salvarLimites(' + id + ')">Aplicar</button></div>';
}

// ── Comandos: MESMO caminho que o Raspberry Pi usa ────────────────────────
async function enviarComando(linha) {
  const r = await fetch('/api/comando', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({comando: linha})
  });
  const j = await r.json().catch(() => ({ok: false}));
  if (!j.ok) alert('Comando recusado: ' + (j.erro || 'desconhecido'));
  return j.ok;
}
function cmd(no, acao) {
  return enviarComando('CMD:' + String(no).padStart(2, '0') + ':' + acao);
}
async function salvarLimites(no) {
  const v1 = parseFloat(document.getElementById('l1').value);
  const v2 = parseFloat(document.getElementById('l2').value);
  if (!isNaN(v1)) await cmd(no, 'LIM1:' + v1);
  // Os dois limites precisam voltar juntos na telemetria para o painel do
  // Raspberry Pi marcar o comando como confirmado — por isso mandamos os dois.
  if (!isNaN(v2)) await cmd(no, 'LIM2:' + v2);
}

setInterval(() => {
  document.getElementById('hora-atual').textContent =
    new Date().toLocaleTimeString('pt-BR', {hour:'2-digit',minute:'2-digit',second:'2-digit'});
}, 1000);

function conectarSSE() {
  const dot = document.getElementById('sse-dot');
  const st  = document.getElementById('sse-status');
  const es  = new EventSource('/events');
  es.onopen    = () => { dot.classList.remove('off'); st.textContent = 'Tempo real'; };
  es.onmessage = (e) => { try { pintar(JSON.parse(e.data)); } catch (err) {} };
  es.onerror   = () => {
    dot.classList.add('off'); st.textContent = 'Reconectando…';
    es.close(); setTimeout(conectarSSE, 3000);
  };
}
conectarSSE();
</script>
</body>
</html>
)====="));
}


void handleTabela() {
  int pagina = 1;
  if (server.hasArg("p")) pagina = server.arg("p").toInt();
  if (pagina < 1) pagina = 1;

  // Filtro por nó: o histórico dos 4 setores agora mora no mesmo arquivo.
  int filtroNo = server.hasArg("no") ? server.arg("no").toInt() : 0;
  if (filtroNo < 0 || filtroNo > TOTAL_NOS) filtroNo = 0;

  long total     = totalLinhasSD();
  long totalPags = max(1L, (total + REGISTROS_POR_PAGINA - 1) / REGISTROS_POR_PAGINA);
  if (pagina > totalPags) pagina = totalPags;

  long inicio = (long)(pagina - 1) * REGISTROS_POR_PAGINA + 1;
  long fim    = min((long)pagina * REGISTROS_POR_PAGINA, total);

  WiFiClient cliente = server.client();
  cliente.println("HTTP/1.1 200 OK");
  cliente.println("Content-Type: text/html; charset=utf-8");
  cliente.println("Connection: close");
  cliente.println();

  cliente.println("<!DOCTYPE html><html><head>");
  cliente.println("<meta charset='UTF-8'>");
  cliente.println("<meta name='viewport' content='width=device-width, initial-scale=1'>");
  cliente.println("<title>Registros — Irrigação</title>");
  cliente.println("<style>");
  cliente.println("body{font-family:Arial;background:#f0f4f0;padding:16px}");
  cliente.println("h1{color:#2e7d32;margin-bottom:12px;font-size:1.3em}");
  cliente.println(".info{font-size:.85em;color:#555;margin-bottom:12px}");
  cliente.println("table{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.1)}");
  cliente.println("th{background:#2e7d32;color:#fff;padding:10px 8px;font-size:.82em;text-align:left}");
  cliente.println("td{padding:7px 8px;font-size:.80em;border-bottom:1px solid #eee}");
  cliente.println("tr:nth-child(even){background:#f9f9f9}");
  cliente.println(".evento{background:#fff9c4!important}");
  cliente.println(".nav{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap;align-items:center}");
  cliente.println(".btn{padding:8px 16px;border-radius:6px;text-decoration:none;color:#fff;font-size:.85em;border:none;cursor:pointer}");
  cliente.println(".btn-green{background:#4CAF50}.btn-gray{background:#888}.btn-dl{background:#388e3c}.btn-back{background:#2196F3}");
  cliente.println("</style></head><body>");

  cliente.println("<h1>Registros de Irrigação</h1>");
  cliente.printf("<div class='info'>Total: <b>%ld</b> registros | Página <b>%d</b> de <b>%ld</b> | Mostrando %ld–%ld</div>\n",
                 total, pagina, totalPags, inicio, fim);


  cliente.println("<div class='nav'>");
  cliente.println("<a href='/' class='btn btn-back'>← Voltar</a>");
  if (pagina > 1)     cliente.printf("<a href='/tabela?p=%d&no=%d' class='btn btn-gray'>&#9664; Anterior</a>\n", pagina - 1, filtroNo);
  if (pagina < totalPags) cliente.printf("<a href='/tabela?p=%d&no=%d' class='btn btn-green'>Próxima &#9654;</a>\n", pagina + 1, filtroNo);
  cliente.println("<a href='/download' class='btn btn-dl'>⬇ Baixar tudo (CSV)</a>");
  cliente.println("</div>");

  // Um link por no daria 99 botoes em cima da tabela, empurrando o conteudo
  // para fora da tela no celular. Acima de 12 nos vira um seletor.
  cliente.println("<div class='nav'><span style='font-size:.82em;color:#555'>Filtrar:</span>");
  if (TOTAL_NOS <= 12) {
    cliente.printf("<a href='/tabela' class='btn %s'>Todos</a>\n",
                   filtroNo == 0 ? "btn-green" : "btn-gray");
    for (int i = 1; i <= TOTAL_NOS; i++) {
      cliente.printf("<a href='/tabela?no=%d' class='btn %s'>Nó %02d</a>\n",
                     i, filtroNo == i ? "btn-green" : "btn-gray", i);
    }
  } else {
    cliente.print("<select onchange=\"location='/tabela?no='+this.value\" "
                  "style='padding:7px;border-radius:6px;border:1px solid #ccc'>");
    cliente.printf("<option value='0'%s>Todos os nós</option>",
                   filtroNo == 0 ? " selected" : "");
    for (int i = 1; i <= TOTAL_NOS; i++) {
      cliente.printf("<option value='%d'%s>Nó %02d</option>",
                     i, filtroNo == i ? " selected" : "", i);
    }
    cliente.println("</select>");
  }
  cliente.println("</div>");

  cliente.println("<br><table>");
  cliente.println("<tr><th>#</th><th>Nó</th><th>Data/Hora</th><th>Tipo</th>"
                  "<th>Umid1 (%)</th><th>Irrig1</th><th>Lim1 (%)</th>"
                  "<th>Umid2 (%)</th><th>Irrig2</th><th>Lim2 (%)</th>"
                  "<th>Temp (C)</th><th>Umid. ar (%)</th><th>Temp solo (C)</th></tr>");

  if (sdDisponivel) {
    File f = SD.open(ARQUIVO_DADOS, FILE_READ);
    if (f) {
      long linhaAtual = 0;
      long mostradas  = 0;

      while (f.available()) {
        String linha = f.readStringUntil('\n');
        linhaAtual++;
        if (linhaAtual <= 2) continue;

        long regAtual = linhaAtual - 2;
        if (regAtual < inicio) continue;
        if (regAtual > fim)    break;

        // 14 colunas: …;Prev2;No;UmidAr;TempSolo. Split genérico — o parser
        // posicional anterior tinha os índices cravados e quebraria com a
        // coluna nova.
        String col[ARQUIVO_COLUNAS];
        int    ini = 0, nc = 0;
        while (nc < ARQUIVO_COLUNAS) {
          int p = linha.indexOf(';', ini);
          if (p < 0) { col[nc++] = linha.substring(ini); break; }
          col[nc++] = linha.substring(ini, p);
          ini = p + 1;
        }
        for (int k = nc; k < ARQUIVO_COLUNAS; k++) col[k] = "-";
        col[ARQUIVO_COLUNAS - 1].trim();

        if (filtroNo > 0 && col[11].toInt() != filtroNo) continue;

        bool isEvento = col[1] == "EVENTO";
        cliente.printf("<tr%s><td>%ld</td><td><b>%s</b></td><td>%s</td><td>%s</td>"
                       "<td>%s</td><td>%s</td><td>%s</td>"
                       "<td>%s</td><td>%s</td><td>%s</td>"
                       "<td>%s</td><td>%s</td><td>%s</td></tr>\n",
                       isEvento ? " class='evento'" : "",
                       regAtual,
                       col[11].c_str(), col[0].c_str(), col[1].c_str(),
                       col[2].c_str(), col[3].c_str(), col[4].c_str(),
                       col[5].c_str(), col[6].c_str(), col[7].c_str(),
                       col[8].c_str(), col[12].c_str(), col[13].c_str());

        mostradas++;
        if (regAtual % 20 == 0) yield();
      }
      f.close();

      if (mostradas == 0) {
        cliente.println("<tr><td colspan='13' style='text-align:center;color:#888'>"
                        "Nenhum registro nesta página para o filtro escolhido</td></tr>");
      }
    }
  } else {
    cliente.println("<tr><td colspan='13' style='text-align:center;color:#888'>SD não disponível</td></tr>");
  }

  cliente.println("</table>");


  cliente.println("<div class='nav'>");
  cliente.println("<a href='/' class='btn btn-back'>← Voltar</a>");
  if (pagina > 1)     cliente.printf("<a href='/tabela?p=%d&no=%d' class='btn btn-gray'>&#9664; Anterior</a>\n", pagina - 1, filtroNo);
  if (pagina < totalPags) cliente.printf("<a href='/tabela?p=%d&no=%d' class='btn btn-green'>Próxima &#9654;</a>\n", pagina + 1, filtroNo);
  cliente.println("<a href='/download' class='btn btn-dl'>⬇ Baixar tudo (CSV)</a>");
  cliente.println("</div>");
  cliente.println("</body></html>");
}


// ── Envio de arquivo em partes ────────────────────────────────────────────────
// O `/download` mandava o `/dados.csv` inteiro dentro do handler. O arquivo
// ganha uma linha por pacote recebido — MB por semana —, e o loop ficava
// minutos parado. Agora o handler só manda o cabeçalho HTTP e guarda o arquivo
// e o socket aqui; `enviarArquivoPendente()` manda um pedaço a cada volta do
// loop. (O `WebServer` desta versão solta o cliente ao fim do handler; a cópia
// guardada mantém o socket aberto até o fim do envio.)
//
// Um envio por vez: com o socket do primeiro aberto, um segundo pedido recebe
// 503 em vez de dividir o cartão.
#define ENVIO_POR_VOLTA   4096
#define ENVIO_SEM_AVANCO  15000UL   // cliente parado há tanto tempo: desiste

static File          _envArquivo;
static WiFiClient    _envCliente;
static bool          _envAtivo       = false;
static unsigned long _envUltimoAvanco = 0;
static size_t        _envBytes       = 0;

static void encerrarEnvio(const char* motivo) {
  _envArquivo.close();
  _envCliente.stop();
  _envAtivo = false;
  Serial.printf("[Download] %s (%u bytes)\n", motivo, (unsigned)_envBytes);
}

static bool envioOcupado() {
  if (!_envAtivo) return false;
  server.send(503, "text/plain; charset=utf-8",
              "Outro download em andamento — tente de novo quando ele terminar.");
  return true;
}

static void iniciarEnvio(File& f, WiFiClient& c) {
  _envArquivo      = f;
  _envCliente      = c;
  _envAtivo        = true;
  _envBytes        = 0;
  _envUltimoAvanco = millis();
}

void enviarArquivoPendente() {
  if (!_envAtivo) return;
  if (!_envCliente.connected()) { encerrarEnvio("Cliente desconectou"); return; }

  uint8_t buf[512];
  for (size_t enviado = 0; enviado < ENVIO_POR_VOLTA && _envArquivo.available(); ) {
    int lido = _envArquivo.read(buf, sizeof(buf));
    if (lido <= 0) break;
    size_t escrito = _envCliente.write(buf, lido);
    if (escrito != (size_t)lido) {
      // O socket não aceitou tudo: o cliente parou de ler. Volta para onde
      // parou e tenta na próxima volta — até ENVIO_SEM_AVANCO.
      _envArquivo.seek(_envArquivo.position() - (lido - escrito));
      _envBytes += escrito;
      if (escrito > 0) _envUltimoAvanco = millis();
      break;
    }
    enviado          += escrito;
    _envBytes        += escrito;
    _envUltimoAvanco  = millis();
  }

  if (!_envArquivo.available())                       encerrarEnvio("Arquivo enviado");
  else if (millis() - _envUltimoAvanco > ENVIO_SEM_AVANCO) encerrarEnvio("Cliente parado — envio abandonado");
}

void cancelarEnvioArquivo() {
  if (_envAtivo) encerrarEnvio("Envio cancelado");
}

void handleDownload() {
  if (envioOcupado()) return;

  File f;
  if (sdDisponivel) {
    f = SD.open(ARQUIVO_DADOS, FILE_READ);
    if (!f) { server.send(500, "text/plain", "Nao consegui abrir " ARQUIVO_DADOS); return; }
  }

  String nomeArquivo = "Registro " + obterDataArquivo() + ".csv";

  WiFiClient cliente = server.client();
  cliente.println("HTTP/1.1 200 OK");
  cliente.println("Content-Type: text/csv; charset=utf-8");
  cliente.println("Content-Disposition: attachment; filename=\"" + nomeArquivo + "\"");
  cliente.println("Connection: close");
  cliente.println();
  cliente.print("\xEF\xBB\xBF");

  if (f) {
    Serial.printf("[Download] CSV: %ld registros, %u bytes — enviando em partes\n",
                  totalLinhasSD(), (unsigned)f.size());
    iniciarEnvio(f, cliente);
  } else {
    // Sem cartão: despeja o buffer de RAM no MESMO formato de 14 colunas.
    cliente.print("sep=;\n");
    cliente.print(ARQUIVO_CABECALHO);
    for (int i = 0; i < totalBufferRAM; i++) {
      const Registro& r = bufferRAM[i];
      auto num  = [&](float v) { if (isnan(v)) cliente.print("-"); else cliente.print(v, 1); };
      auto prev = [&](float v) { if (isnan(v) || v < 0) cliente.print("-"); else cliente.print((int)v); };

      cliente.print(r.dataHora);                                     cliente.print(";");
      cliente.print(r.tipo == REGISTRO_EVENTO ? "EVENTO":"LEITURA"); cliente.print(";");
      num(r.umidade1);                                               cliente.print(";");
      cliente.print(r.irrigando1 ? "SIM":"NAO");                     cliente.print(";");
      num(r.limite1);                                                cliente.print(";");
      num(r.umidade2);                                               cliente.print(";");
      cliente.print(r.irrigando2 ? "SIM":"NAO");                     cliente.print(";");
      num(r.limite2);                                                cliente.print(";");
      num(r.temp);                                                   cliente.print(";");
      prev(r.previsao1);                                             cliente.print(";");
      prev(r.previsao2);                                             cliente.print(";");
      if (r.nodeId < 10) cliente.print("0");
      cliente.print(r.nodeId);                                       cliente.print(";");
      num(r.umidadeAr);                                              cliente.print(";");
      num(r.tempSolo);                                               cliente.println();
    }
  }
}


void handleData() {
  // Escrito direto no socket: com 99 nos o resumo passa de 5 KB, e
  // `server.send()` exigiria montar tudo numa String antes de enviar.
  WiFiClient cliente = server.client();
  cliente.println("HTTP/1.1 200 OK");
  cliente.println("Content-Type: application/json");
  cliente.println("Access-Control-Allow-Origin: *");
  cliente.println("Connection: close");
  cliente.println();
  escreverResumo(cliente);
}


/// `GET /api/no?id=N` — detalhe completo de UM no.
///
/// O resumo que alimenta a tabela nao carrega limite, previsao, bateria nem
/// contadores: multiplicado por 99 isso seria 25 KB por atualizacao para
/// mostrar dado que ninguem esta olhando. O detalhe vem quando o operador
/// clica na linha.
void handleApiNo() {
  int id = server.hasArg("id") ? server.arg("id").toInt() : 0;
  if (id < 1 || id > TOTAL_NOS) {
    server.send(400, "application/json",
                "{\"ok\":false,\"erro\":\"id fora de 1..99\"}");
    return;
  }
  WiFiClient cliente = server.client();
  cliente.println("HTTP/1.1 200 OK");
  cliente.println("Content-Type: application/json");
  cliente.println("Access-Control-Allow-Origin: *");
  cliente.println("Connection: close");
  cliente.println();
  escreverDetalhe(cliente, id);
}


static String jsonEsc(const String& s) {
  String r = s; r.replace("\\","\\\\"); r.replace("\"","\\\""); return r;
}

static void handleWifiScan() {
  int n = WiFi.scanNetworks();
  String json = "[";
  for (int i = 0; i < n && i < 20; i++) {
    if (i > 0) json += ",";
    json += "{\"ssid\":\"" + jsonEsc(WiFi.SSID(i))                              + "\","
            "\"rssi\":"    + String(WiFi.RSSI(i))                               + ","
            "\"enc\":"     + (WiFi.encryptionType(i) != WIFI_AUTH_OPEN ? "true":"false") + "}";
  }
  WiFi.scanDelete();
  json += "]";
  server.send(200, "application/json", json);
}


static void handleWifiDisconnect() {
  {
    Preferences p;
    p.begin("wifi-cfg", false);
    p.remove("ssid");
    p.remove("pass");
    p.end();
  }
  Serial.println("[WiFi] Credenciais removidas");
  WiFiClient c = server.client();
  c.println("HTTP/1.1 200 OK");
  c.println("Content-Type: text/html; charset=utf-8");
  c.println("Connection: close");
  c.println();
  c.print("<!DOCTYPE html><html><head><meta charset='UTF-8'>"
          "<meta name='viewport' content='width=device-width,initial-scale=1'>"
          "<style>body{font-family:Arial;background:#f0f4f0;padding:40px 16px;text-align:center}"
          ".card{background:#fff;border-radius:12px;padding:24px;max-width:360px;margin:0 auto;"
            "box-shadow:0 2px 8px rgba(0,0,0,.1)}"
          "h2{color:#c62828}p{color:#555;font-size:.9em;margin:8px 0}"
          ".spin{display:inline-block;width:32px;height:32px;border:4px solid #eee;"
            "border-top-color:#c62828;border-radius:50%;animation:g 1s linear infinite;margin:12px 0}"
          "@keyframes g{to{transform:rotate(360deg)}}"
          "</style></head><body><div class='card'>"
          "<h2>Rede Esquecida</h2><div class='spin'></div>"
          "<p>Credenciais removidas. Reiniciando...</p>"
          "<p style='font-size:.82em;color:#888;margin-top:12px'>"
          "Conecte ao AP <b>ESP32_IRRIGA_V3</b> e acesse <b>192.168.4.1</b> para configurar uma nova rede."
          "</p></div></body></html>");
  c.flush();
  delay(1500);
  ESP.restart();
}


void handleConfig() {
  String html = R"=====(
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Configuração — Gateway V6</title>
  <style>
    body{font-family:system-ui,Arial,sans-serif;padding:24px 16px;background:#eef2ee;color:#222}
    .card{background:#fff;border-radius:12px;padding:22px;max-width:480px;margin:0 auto 14px;box-shadow:0 2px 8px rgba(0,0,0,.09)}
    h2{color:#1b5e20;margin-bottom:14px;font-size:1.05em}
    .form-group{margin-bottom:16px;text-align:left}
    label{font-size:.86em;color:#444;display:block;margin-bottom:4px}
    input[type=text],input[type=number],input[type=password]{padding:10px;font-size:15px;width:100%;border:1px solid #ccc;border-radius:6px}
    .hint{font-size:.76em;color:#888;margin-top:4px;line-height:1.5}
    .linha{display:flex;gap:8px}
    .linha>div{flex:1}
    button{padding:11px;background:#2e7d32;color:#fff;border:none;border-radius:6px;font-size:15px;cursor:pointer;width:100%}
    a.voltar{display:block;text-align:center;margin-top:12px;color:#1565C0;text-decoration:none}
    table.info{width:100%;font-size:.82em;border-collapse:collapse}
    table.info td{padding:5px 0;border-bottom:1px solid #f0f0f0}
    table.info td:last-child{text-align:right;font-weight:bold}
    .chk{display:flex;align-items:center;gap:8px;font-size:.88em;color:#444}
    .chk input{width:auto}
    .wifi-rede{display:flex;align-items:center;padding:8px 10px;border:1px solid #ddd;border-radius:7px;margin-bottom:4px;cursor:pointer;background:#fafafa;text-align:left}
    .wifi-rede:hover,.wifi-rede.wsel{background:#e8f5e9;border-color:#4CAF50}
    .wifi-rede input{width:auto;margin-right:8px;padding:0;font-size:14px}
    .nota{background:#fff8e1;border-left:4px solid #ef6c00;padding:9px 12px;border-radius:0 6px 6px 0;font-size:.78em;color:#5d4037;line-height:1.6;margin-top:10px}
    #mapa{height:300px;border-radius:8px;border:1px solid #ccc;margin-bottom:10px;background:#e8ece8;display:flex;align-items:center;justify-content:center;color:#888;font-size:.84em;text-align:center;padding:0 12px}
    #loc-msg{font-size:.8em;margin-top:8px;min-height:1.2em}
  </style>
</head>
<body>

<div class="card">
  <h2>🔗 Controle central (Raspberry Pi)</h2>
  <form action="/set-pi" method="POST">
    <div class="linha">
      <div class="form-group">
        <label>Host / IP do Raspberry</label>
        <input type="text" name="host" value="%PI_HOST%" required>
      </div>
      <div class="form-group" style="max-width:110px">
        <label>Porta</label>
        <input type="number" name="porta" min="1" max="65535" value="%PI_PORTA%" required>
      </div>
    </div>
    <div class="form-group">
      <label class="chk"><input type="checkbox" name="ativo" value="1" %PI_CHECK%>
        Enviar leituras por push (POST /api/gateway/webhook)</label>
      <div class="hint">
        Estado: <b>%PI_STATUS%</b><br>
        Mesmo com o push desligado, o Raspberry continua podendo buscar os dados
        aqui em <code>/api/leituras</code> e <code>/eventos</code>, e mandar comandos
        em <code>/api/comando</code>.
      </div>
    </div>
    <button type="submit">Salvar</button>
  </form>
  <div class="nota">
    Se você ligar <code>PAINEL_USUARIO</code>/<code>PAINEL_SENHA</code> no <code>.env</code> do
    Raspberry, o webhook passa a responder <b>401</b> e o push para de funcionar sem aviso
    no painel. Nesse caso, desligue o push aqui e use só o polling.
  </div>
</div>

<div class="card">
  <h2>📡 Rede LoRa (TDMA)</h2>
  <table class="info">
    <tr><td>Ciclo atual</td><td>%TDMA_CICLO% ms (%TDMA_SLOTS% nós descobertos)</td></tr>
    <tr><td>Janela de descoberta</td><td>%TDMA_DSC% ms</td></tr>
    <tr><td>Ciclo com a rede toda descoberta</td><td>%TDMA_MAX% ms</td></tr>
    <tr><td>Slot por nó</td><td>%TDMA_SLOT% ms</td></tr>
    <tr><td>Guarda antes do primeiro slot</td><td>%TDMA_GUARDA% ms</td></tr>
    <tr><td>Nós na rede</td><td>%TOTAL_NOS%</td></tr>
    <tr><td>Beacons emitidos</td><td>%BEACONS%</td></tr>
    <tr><td>Comandos na fila</td><td>%CMD_FILA%</td></tr>
    <tr><td>Linhas aguardando o Pi</td><td>%PENDENTES%</td></tr>
  </table>
  <div class="hint" style="margin-top:10px">
    O ciclo é <b>variável: muda a cada nó descoberto</b>, 1 s a cada dois nós. Só os nós
    que já falaram têm slot; o beacon leva o mapa deles e cada nó acha a própria posição.
    Um nó novo fala na janela de descoberta, depois dos slots, e ganha slot no ciclo seguinte.<br>
    <b><code>WATCHDOG_TIMEOUT_S</code> no <code>.env</code> do Raspberry precisa cobrir o ciclo
    com a rede toda descoberta</b> (3 × %TDMA_MAX_S% s ≈ %TDMA_WD% s), senão ele marca os nós como offline.
  </div>
  <div class="hint" style="margin-top:8px">
    Os limiares de umidade de cada nó ficam nos cartões da <a href="/">página principal</a>,
    porque agora são por nó e por canal.
  </div>
</div>

<div class="card">
  <h2>📍 Localização (previsão de chuva)</h2>
  <div class="hint" style="margin-bottom:10px">
    Clique no mapa (ou arraste o marcador) para escolher onde fica a lavoura. O nowcast
    da Rainbow é consultado para este ponto e a flag de chuva segue para todos os nós no
    beacon. Última consulta: <b>%CLIMA%</b>
  </div>
  <div id="mapa">Carregando mapa…</div>
  <div class="linha">
    <div class="form-group">
      <label>Latitude</label>
      <input type="number" id="lat" step="0.0001" min="-35" max="6" value="%LAT%">
    </div>
    <div class="form-group">
      <label>Longitude</label>
      <input type="number" id="lon" step="0.0001" min="-75" max="-28" value="%LON%">
    </div>
  </div>
  <button id="btn-loc" onclick="salvarLocal()">Salvar localização</button>
  <div id="loc-msg"></div>
  <div class="hint">
    O mapa vem da internet (OpenStreetMap). Acessando só pelo AP do receptor, sem rede da
    fazenda, ele não carrega — digite as coordenadas à mão.
  </div>
</div>

<div class="card">
  <h2>🛰 Nós conhecidos</h2>
  <div class="hint" style="margin-bottom:10px">
    O painel lista só os nós que já falaram alguma vez — <b>%NOS_CONHECIDOS%</b> até agora.
    A lista sobrevive ao reboot, para um nó que morreu continuar aparecendo como offline.
    Se um nó foi retirado de vez (ou foi injetado em bancada), esqueça os mudos aqui.
  </div>
  <button onclick="esquecerNos()" style="background:#c62828">Esquecer nós offline</button>
</div>

<div class="card">
  <h2>📶 Rede WiFi</h2>
  <div style="font-size:.85em;color:#555;margin-bottom:10px">Status: <b>%WIFI_STATUS%</b></div>
  <div class="hint" style="margin-bottom:10px">
    O ponto de acesso <b>%AP_SSID%</b> (%AP_IP%) fica <b>sempre</b> ligado, junto com a rede
    da fazenda. É o endereço de fábrica que o controle central procura e o painel de
    emergência quando o WiFi cai.
  </div>
  <div id="wifi-lista" style="margin-bottom:8px"></div>
  <div class="form-group">
    <label>Nome da rede (SSID)</label>
    <input type="text" id="wifi-ssid-inp" placeholder="Selecione acima ou digite">
  </div>
  <div class="form-group">
    <label>Senha</label>
    <input type="password" id="wifi-pass-inp" placeholder="Deixe vazio para rede aberta">
  </div>
  <button id="btn-wifi-con" onclick="salvarWifiConf()" style="margin-bottom:6px">Conectar e salvar</button>
  <button id="btn-wifi-scan" onclick="buscarRedes()" style="background:#1565C0;margin-bottom:6px">🔄 Buscar redes</button>
  <button onclick="desconectarWifi()" style="background:#c62828">🚫 Esquecer rede salva</button>
  <a class="voltar" href="/">← Voltar ao painel</a>
</div>

<script>
  async function buscarRedes() {
    const btn = document.getElementById('btn-wifi-scan');
    const lista = document.getElementById('wifi-lista');
    btn.disabled = true; btn.textContent = 'Buscando...';
    lista.innerHTML = '<div style="color:#888;font-size:.84em;padding:6px 0">Aguardando scan WiFi...</div>';
    try {
      const r = await fetch('/wifi-scan');
      if (!r.ok) throw new Error();
      const redes = await r.json();
      lista.innerHTML = '';
      if (redes.length === 0) {
        lista.innerHTML = '<div style="color:#aaa;font-size:.84em">Nenhuma rede encontrada</div>';
      } else {
        redes.forEach(n => {
          const cor = n.rssi > -65 ? '#2e7d32' : n.rssi > -75 ? '#e65100' : '#c62828';
          const d = document.createElement('label');
          d.className = 'wifi-rede';
          d.appendChild(Object.assign(document.createElement('input'),{type:'radio',name:'_wr'}));
          const nm = d.appendChild(document.createElement('span'));
          nm.textContent = n.ssid;
          nm.style.cssText = 'flex:1;font-weight:bold;font-size:.88em';
          const db = d.appendChild(document.createElement('span'));
          db.textContent = n.rssi + ' dBm';
          db.style.cssText = 'font-size:.74em;color:'+cor+';margin-left:4px';
          const lk = d.appendChild(document.createElement('span'));
          lk.textContent = n.enc ? '🔒' : '🔓';
          lk.style.cssText = 'font-size:.82em;margin-left:4px';
          d.addEventListener('click', () => {
            document.querySelectorAll('.wifi-rede').forEach(r => r.classList.remove('wsel'));
            d.classList.add('wsel');
            document.getElementById('wifi-ssid-inp').value = n.ssid;
            document.getElementById('wifi-pass-inp').focus();
          });
          lista.appendChild(d);
        });
      }
    } catch(e) {
      lista.innerHTML = '<div style="color:#c62828;font-size:.84em">Erro ao buscar redes</div>';
    }
    btn.disabled = false; btn.textContent = '🔄 Buscar redes';
  }
  async function salvarWifiConf() {
    const ssid = document.getElementById('wifi-ssid-inp').value.trim();
    const pass = document.getElementById('wifi-pass-inp').value;
    if (!ssid) { alert('Digite o nome da rede'); return; }
    const btn = document.getElementById('btn-wifi-con');
    btn.disabled = true; btn.textContent = 'Salvando...';
    const b = new URLSearchParams();
    b.append('ssid', ssid); b.append('pass', pass);
    try { await fetch('/wifi-save', {method:'POST', body:b}); } catch(e) {}
  }
  async function desconectarWifi() {
    if (!confirm('Esquecer a rede salva e reiniciar?')) return;
    try { await fetch('/wifi-disconnect', {method:'POST'}); } catch(e) {}
  }

  // ── Mapa de localização ───────────────────────────────────────────────────
  // Leaflet + OpenStreetMap vêm da internet, carregados pelo NAVEGADOR — o
  // ESP32 não serve nada disso. Sem internet o mapa falha e os campos de
  // latitude/longitude continuam funcionando sozinhos.
  let mapa = null, marcador = null;
  const inpLat = document.getElementById('lat');
  const inpLon = document.getElementById('lon');

  function noBrasil(lat, lon) {
    return lat >= -35 && lat <= 6 && lon >= -75 && lon <= -28;
  }
  function moverPara(lat, lon, centralizar) {
    inpLat.value = lat.toFixed(4);
    inpLon.value = lon.toFixed(4);
    if (!marcador) return;
    marcador.setLatLng([lat, lon]);
    if (centralizar) mapa.panTo([lat, lon]);
  }
  function iniciarMapa() {
    const lat = parseFloat(inpLat.value), lon = parseFloat(inpLon.value);
    const div = document.getElementById('mapa');
    div.textContent = '';
    mapa = L.map(div).setView([lat, lon], 12);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18, attribution: '&copy; OpenStreetMap'
    }).addTo(mapa);
    marcador = L.marker([lat, lon], {draggable: true}).addTo(mapa);
    marcador.on('dragend', () => {
      const p = marcador.getLatLng();
      moverPara(p.lat, p.lng, false);
    });
    mapa.on('click', e => moverPara(e.latlng.lat, e.latlng.lng, false));
  }
  [inpLat, inpLon].forEach(i => i.addEventListener('change', () => {
    const lat = parseFloat(inpLat.value), lon = parseFloat(inpLon.value);
    if (!isNaN(lat) && !isNaN(lon) && marcador) {
      marcador.setLatLng([lat, lon]); mapa.panTo([lat, lon]);
    }
  }));
  (function carregarLeaflet() {
    const css = document.createElement('link');
    css.rel = 'stylesheet';
    css.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
    document.head.appendChild(css);
    const js = document.createElement('script');
    js.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    js.onload  = iniciarMapa;
    js.onerror = () => {
      document.getElementById('mapa').textContent =
        'Mapa indisponível (sem internet neste dispositivo). Use os campos abaixo.';
    };
    document.head.appendChild(js);
  })();

  async function salvarLocal() {
    const lat = parseFloat(inpLat.value), lon = parseFloat(inpLon.value);
    const msg = document.getElementById('loc-msg');
    if (isNaN(lat) || isNaN(lon) || !noBrasil(lat, lon)) {
      msg.style.color = '#c62828';
      msg.textContent = 'Coordenadas fora do Brasil (lat -35..6, lon -75..-28).';
      return;
    }
    const btn = document.getElementById('btn-loc');
    btn.disabled = true; btn.textContent = 'Salvando...';
    const b = new URLSearchParams();
    b.append('lat', lat.toFixed(4)); b.append('lon', lon.toFixed(4));
    try {
      const j = await (await fetch('/api/localizacao', {method:'POST', body:b})).json();
      if (!j.ok) throw new Error(j.erro || 'recusado');
      msg.style.color = '#2e7d32';
      msg.textContent = 'Salvo: ' + j.lat + ', ' + j.lon + '. A previsão é consultada de novo em seguida.';
    } catch(e) {
      msg.style.color = '#c62828';
      msg.textContent = 'Erro ao salvar: ' + e.message;
    }
    btn.disabled = false; btn.textContent = 'Salvar localização';
  }

  async function esquecerNos() {
    if (!confirm('Tirar do painel todos os nós que estão offline agora?')) return;
    try { await fetch('/api/nos/esquecer', {method:'POST'}); } catch(e) {}
    location.reload();
  }
</script>
</body>
</html>
)=====";

  html.replace("%PI_HOST%",  htmlEscape(piHost()));
  html.replace("%PI_PORTA%", String(piPorta()));
  html.replace("%PI_CHECK%", piAtivo() ? "checked" : "");

  String piStatus;
  if (!piAtivo())          piStatus = "push desligado";
  else if (piUltimoOk())   piStatus = String(piEnviados()) + " linha(s) entregues";
  else if (piFalhas() > 0) piStatus = "falhando — " + htmlEscape(piUltimoErro());
  else                     piStatus = "aguardando o primeiro envio";
  html.replace("%PI_STATUS%", piStatus);

  html.replace("%TDMA_CICLO%",  String(cicloMs()));
  html.replace("%TDMA_SLOTS%",  String(slotsCiclo()));
  html.replace("%TDMA_DSC%",    String(JANELA_DESCOBERTA_MS));
  html.replace("%TDMA_MAX_S%",  String(CICLO_MAX_MS / 1000UL));
  html.replace("%TDMA_MAX%",    String(CICLO_MAX_MS));
  html.replace("%TDMA_WD%",     String((3UL * CICLO_MAX_MS / 1000UL + 9UL) / 10UL * 10UL));
  html.replace("%TDMA_SLOT%",   String(SLOT_MS));
  html.replace("%TDMA_GUARDA%", String(GUARDA_MS));
  html.replace("%TOTAL_NOS%",   String(TOTAL_NOS));
  html.replace("%BEACONS%",     String(beaconsEnviados()));
  html.replace("%CMD_FILA%",    String(comandosPendentes()));
  html.replace("%PENDENTES%",   String(filaPendentesPiTotal()));

  html.replace("%LAT%", String(weatherLat, 4));
  html.replace("%LON%", String(weatherLon, 4));
  html.replace("%CLIMA%", clima.valido
    ? clima.horaConsulta + " — " + htmlEscape(clima.intensidade) + ", " +
      String(clima.precipMax, 2) + " mm/h" +
      (!climaAtual()  ? " (DESATUALIZADA — não inibe irrigação)"
       : chuvaVemAi() ? " (chuva prevista)" : "")
    : String("ainda sem resposta da API"));

  int conhecidos = 0;
  for (int i = 0; i < TOTAL_NOS; i++) if (nos[i].conhecido) conhecidos++;
  html.replace("%NOS_CONHECIDOS%", String(conhecidos));

  html.replace("%AP_SSID%", AP_SSID);
  html.replace("%AP_IP%",   WiFi.softAPIP().toString());
  html.replace("%WIFI_STATUS%",
    WiFi.status() == WL_CONNECTED
      ? "conectado a <b>" + htmlEscape(wifiSsidAtual) + "</b> (" + WiFi.localIP().toString() + ")"
      : "desconectado (salvo: <b>" + htmlEscape(wifiSsidAtual) + "</b>)");

  server.send(200, "text/html; charset=utf-8", html);
}

void handleSetPi() {
  String   host  = server.arg("host");
  uint16_t porta = (uint16_t)server.arg("porta").toInt();
  bool     ativo = server.hasArg("ativo");   // checkbox só chega quando marcado

  host.trim();
  if (!piConfigurar(host, porta, ativo)) {
    server.send(400, "text/plain", "host ou porta invalidos");
    return;
  }
  server.sendHeader("Location", "/config");
  server.send(303);
}



static File   _uploadFile;
static String _uploadPath = "/";

static String sanitizarCaminho(String p) {
  while (p.indexOf("..") >= 0) p.replace("..", "");
  if (!p.startsWith("/")) p = "/" + p;
  if (p.length() > 1 && p.endsWith("/")) p.remove(p.length() - 1);
  return p;
}

static String tamanhoHuman(size_t b) {
  if (b < 1024)    return String(b) + " B";
  if (b < 1048576) return String(b / 1024.0, 1) + " KB";
  return String(b / 1048576.0, 1) + " MB";
}

void handleFiles() {
  String path = server.hasArg("path") ? sanitizarCaminho(server.arg("path")) : "/";

  WiFiClient c = server.client();
  c.println("HTTP/1.1 200 OK");
  c.println("Content-Type: text/html; charset=utf-8");
  c.println("Connection: close");
  c.println();

  c.println("<!DOCTYPE html><html><head>"
            "<meta charset='UTF-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Arquivos SD</title><style>"
            "body{font-family:Arial;background:#f0f4f0;padding:16px}"
            "h1{color:#2e7d32;font-size:1.3em;margin-bottom:4px}"
            ".info{font-size:.8em;color:#666;margin-bottom:12px}"
            "table{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;"
              "overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.1)}"
            "th{background:#2e7d32;color:#fff;padding:10px 8px;font-size:.82em;text-align:left}"
            "td{padding:8px;font-size:.82em;border-bottom:1px solid #eee;word-break:break-all}"
            "tr:nth-child(even){background:#f9f9f9}"
            ".btn{padding:5px 12px;border-radius:5px;color:#fff;text-decoration:none;"
              "font-size:.8em;border:none;cursor:pointer;display:inline-block}"
            ".btn-dl{background:#388e3c}.btn-del{background:#c62828}.btn-cfg{background:#6a1b9a}"
            ".btn-back{background:#2196F3}.btn-dir{background:#1565C0}"
            ".upload-box{background:#fff;border-radius:10px;padding:16px;margin-top:14px;"
              "box-shadow:0 2px 8px rgba(0,0,0,.1)}"
            ".upload-box h2{color:#2e7d32;font-size:1em;margin-bottom:10px}"
            "input[type=file]{width:100%;padding:6px;border:1px solid #ccc;"
              "border-radius:6px;margin-bottom:8px;box-sizing:border-box}"
            ".btn-upload{background:#F57C00;width:100%;padding:10px;font-size:1em}"
            ".nav{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center}"
            ".path{font-family:monospace;font-size:.85em;color:#444;"
              "background:#e8f5e9;padding:4px 10px;border-radius:5px}"
            ".empty{text-align:center;color:#aaa;padding:20px}"
            "</style></head><body>");

  c.println("<h1>Arquivos do Cartao SD</h1>");

  if (sdDisponivel) {
    uint64_t total = SD.cardSize();
    uint64_t usado = SD.usedBytes();
    c.printf("<div class='info'>Capacidade: %s &nbsp;|&nbsp; Usado: %s &nbsp;|&nbsp; Livre: %s</div>\n",
             tamanhoHuman((size_t)total).c_str(),
             tamanhoHuman((size_t)usado).c_str(),
             tamanhoHuman((size_t)(total - usado)).c_str());
  } else {
    c.println("<div class='info' style='color:#c62828'>SD nao disponivel</div>");
  }


  c.println("<div class='nav'>");
  c.println("<a href='/' class='btn btn-back'>Voltar</a>");
  if (path != "/") {
    String parent = path.substring(0, path.lastIndexOf('/'));
    if (parent.isEmpty()) parent = "/";
    c.printf("<a href='/files?path=%s' class='btn btn-back'>Subir</a>\n", parent.c_str());
  }
  c.printf("<span class='path'>%s</span>\n", path.c_str());
  c.println("<a href='/format-sd' class='btn' style='background:#c62828;margin-left:auto'>Formatar SD</a>");
  c.println("</div>");


  c.println("<table><tr><th>Nome</th><th>Tamanho</th><th>Acoes</th></tr>");

  if (sdDisponivel) {
    File dir = SD.open(path);
    if (dir && dir.isDirectory()) {
      int count = 0;
      File entry = dir.openNextFile();
      while (entry) {
        String nome  = String(entry.name());
        int    sl    = nome.lastIndexOf('/');
        if (sl >= 0) nome = nome.substring(sl + 1);
        bool   isDir = entry.isDirectory();
        size_t tam   = isDir ? 0 : entry.size();
        String full  = (path == "/" ? "" : path) + "/" + nome;
        entry.close();

        if (isDir) {
          c.printf("<tr><td>[ %s ]</td><td>-</td>"
                   "<td><a href='/files?path=%s' class='btn btn-dir'>Abrir</a></td></tr>\n",
                   nome.c_str(), full.c_str());
        } else {
          bool isCfg = nome.endsWith(".cfg");
          c.printf("<tr><td>%s</td><td>%s</td>"
                   "<td style='white-space:nowrap'>",
                   nome.c_str(), tamanhoHuman(tam).c_str());
          if (isCfg)
            c.printf("<a href='/file-view?path=%s' class='btn btn-cfg'>Ver</a> ", full.c_str());
          c.printf("<a href='/file-get?path=%s' class='btn btn-dl'>Baixar</a> "
                   "<a href='/file-delete?path=%s' class='btn btn-del' "
                   "onclick=\"return confirm('Deletar %s?')\">Deletar</a>"
                   "</td></tr>\n",
                   full.c_str(), full.c_str(), nome.c_str());
        }
        count++;
        entry = dir.openNextFile();
        if (count % 20 == 0) yield();
      }
      dir.close();
      if (count == 0)
        c.println("<tr><td colspan='3' class='empty'>Pasta vazia</td></tr>");
    } else {
      c.println("<tr><td colspan='3' class='empty'>Erro ao abrir pasta</td></tr>");
    }
  } else {
    c.println("<tr><td colspan='3' class='empty'>SD nao disponivel</td></tr>");
  }

  c.println("</table>");


  if (sdDisponivel) {
    c.printf("<div class='upload-box'>"
             "<h2>Enviar arquivo para: %s</h2>"
             "<form method='POST' action='/file-upload' enctype='multipart/form-data'>"
             "<input type='hidden' name='path' value='%s'>"
             "<input type='file' name='file' required>"
             "<button type='submit' class='btn btn-upload'>Enviar</button>"
             "</form></div>\n",
             path.c_str(), path.c_str());
  }

  c.println("</body></html>");
}

void handleFileDelete() {
  if (!server.hasArg("path")) { server.send(400, "text/plain", "path obrigatorio"); return; }
  String path = sanitizarCaminho(server.arg("path"));
  cancelarEnvioArquivo();   // pode ser justamente o arquivo que está indo para alguém
  bool ok = SD.remove(path);
  Serial.printf("[SD] Delete %s: %s\n", path.c_str(), ok ? "OK" : "ERRO");
  String parent = path.substring(0, path.lastIndexOf('/'));
  if (parent.isEmpty()) parent = "/";
  server.sendHeader("Location", "/files?path=" + parent);
  server.send(303);
}

void handleFileCfgView() {
  if (!server.hasArg("path")) { server.send(400, "text/plain", "path obrigatorio"); return; }
  String path = sanitizarCaminho(server.arg("path"));
  File f = SD.open(path, FILE_READ);
  if (!f || f.isDirectory()) { server.send(404, "text/plain", "Nao encontrado"); return; }

  String nome = path.substring(path.lastIndexOf('/') + 1);
  String parent = path.substring(0, path.lastIndexOf('/'));
  if (parent.isEmpty()) parent = "/";

  WiFiClient c = server.client();
  c.println("HTTP/1.1 200 OK");
  c.println("Content-Type: text/html; charset=utf-8");
  c.println("Connection: close");
  c.println();
  c.printf("<!DOCTYPE html><html><head>"
           "<meta charset='UTF-8'>"
           "<meta name='viewport' content='width=device-width,initial-scale=1'>"
           "<title>%s</title>"
           "<style>"
           "body{font-family:Arial;background:#f0f4f0;padding:16px}"
           "h1{color:#6a1b9a;font-size:1.2em;margin-bottom:8px}"
           ".nav{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center}"
           ".btn{padding:5px 12px;border-radius:5px;color:#fff;text-decoration:none;"
             "font-size:.8em;border:none;cursor:pointer;display:inline-block}"
           ".btn-back{background:#2196F3}.btn-dl{background:#388e3c}"
           "pre{background:#fff;border-radius:8px;padding:16px;overflow:auto;"
             "font-size:.85em;box-shadow:0 2px 8px rgba(0,0,0,.1);white-space:pre-wrap;word-break:break-all}"
           "</style></head><body>",
           nome.c_str());
  c.printf("<h1>%s</h1>", nome.c_str());
  c.printf("<div class='nav'>"
           "<a href='/files?path=%s' class='btn btn-back'>Voltar</a>"
           "<a href='/file-get?path=%s' class='btn btn-dl'>Baixar</a>"
           "</div>",
           parent.c_str(), path.c_str());
  c.println("<pre>");
  uint8_t buf[256];
  while (f.available()) {
    int n = f.read(buf, sizeof(buf));
    if (n > 0) {
      for (int i = 0; i < n; i++) {
        char ch = (char)buf[i];
        if (ch == '<') c.print("&lt;");
        else if (ch == '>') c.print("&gt;");
        else if (ch == '&') c.print("&amp;");
        else c.write((uint8_t)ch);
      }
    }
    yield();
  }
  f.close();
  c.println("</pre></body></html>");
}

void handleFileDownloadArquivo() {
  if (!server.hasArg("path")) { server.send(400, "text/plain", "path obrigatorio"); return; }
  if (envioOcupado()) return;
  String path = sanitizarCaminho(server.arg("path"));
  File f = SD.open(path, FILE_READ);
  if (!f || f.isDirectory()) { server.send(404, "text/plain", "Nao encontrado"); return; }

  String nome = path.substring(path.lastIndexOf('/') + 1);
  WiFiClient c = server.client();
  c.println("HTTP/1.1 200 OK");
  c.println("Content-Type: application/octet-stream");
  c.println("Content-Disposition: attachment; filename=\"" + nome + "\"");
  c.println("Content-Length: " + String(f.size()));
  c.println("Connection: close");
  c.println();
  iniciarEnvio(f, c);
}

void handleFileUploadDone() {
  server.sendHeader("Location", "/files?path=" + _uploadPath);
  server.send(303);
}

void handleFileUploadChunk() {
  HTTPUpload& upload = server.upload();
  if (upload.status == UPLOAD_FILE_START) {
    _uploadPath = server.hasArg("path") ? sanitizarCaminho(server.arg("path")) : "/";
    String filename = (_uploadPath == "/" ? "" : _uploadPath) + "/" + upload.filename;
    Serial.printf("[SD] Upload: %s\n", filename.c_str());
    _uploadFile = SD.open(filename, FILE_WRITE);
  } else if (upload.status == UPLOAD_FILE_WRITE) {
    if (_uploadFile) _uploadFile.write(upload.buf, upload.currentSize);
  } else if (upload.status == UPLOAD_FILE_END) {
    if (_uploadFile) {
      _uploadFile.close();
      Serial.printf("[SD] Upload concluido: %u bytes\n", upload.totalSize);
    }
  } else if (upload.status == UPLOAD_FILE_ABORTED) {
    if (_uploadFile) _uploadFile.close();
    Serial.println("[SD] Upload abortado");
  }
}


void handleFormatSD() {
  if (server.method() == HTTP_GET) {
    server.send(200, "text/html; charset=utf-8",
      "<!DOCTYPE html><html><head><meta charset='UTF-8'>"
      "<meta name='viewport' content='width=device-width,initial-scale=1'>"
      "<title>Formatar SD</title>"
      "<style>"
      "body{font-family:Arial;text-align:center;padding:40px 16px;background:#f0f4f0}"
      ".card{background:#fff;border-radius:12px;padding:24px;max-width:380px;margin:auto;"
        "box-shadow:0 2px 8px rgba(0,0,0,.1)}"
      "h2{color:#c62828;margin-bottom:12px}"
      "p{color:#444;font-size:.92em;margin:10px 0;text-align:left}"
      ".aviso{background:#fff3e0;border-left:4px solid #F57C00;padding:10px 14px;"
        "border-radius:0 6px 6px 0;margin:14px 0;font-size:.85em;color:#5d4037;text-align:left}"
      ".btn{display:inline-block;padding:12px 28px;border-radius:6px;color:#fff;"
        "text-decoration:none;font-size:1em;border:none;cursor:pointer;margin:6px}"
      ".btn-danger{background:#c62828}.btn-back{background:#2196F3}"
      "</style></head><body>"
      "<div class='card'>"
      "<h2>Formatar Cartao SD</h2>"
      "<div class='aviso'>"
      "<b>Atencao:</b> Esta operacao apaga TODOS os arquivos do cartao e "
      "recria apenas o arquivo de dados vazio. Nao ha desfazer."
      "</div>"
      "<p>O que sera feito:</p>"
      "<p>1. Todos os arquivos sao deletados<br>"
      "2. O SD e desmontado e remontado limpo<br>"
      "3. O arquivo de dados e recriado vazio</p>"
      "<p>Isso pode corrigir o bloqueio de escrita no computador.</p>"
      "<form method='POST' action='/format-sd'>"
      "<button type='submit' class='btn btn-danger'>Confirmar — Apagar tudo</button>"
      "</form>"
      "<a href='/files' class='btn btn-back'>Cancelar</a>"
      "</div></body></html>");
    return;
  }


  cancelarEnvioArquivo();   // nenhum arquivo aberto durante a formatação
  bool ok = formatarSD();
  sdDisponivel = ok;

  String msg = ok
    ? "Cartao formatado com sucesso. Arquivo de dados recriado."
    : "Falha ao remontar o cartao apos a formatacao. Reinicie o ESP32.";
  String cor = ok ? "#2e7d32" : "#c62828";

  server.send(200, "text/html; charset=utf-8",
    "<!DOCTYPE html><html><head><meta charset='UTF-8'>"
    "<meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<title>Resultado</title>"
    "<style>body{font-family:Arial;text-align:center;padding:40px 16px;background:#f0f4f0}"
    ".card{background:#fff;border-radius:12px;padding:24px;max-width:360px;margin:auto;"
      "box-shadow:0 2px 8px rgba(0,0,0,.1)}"
    ".btn{display:inline-block;margin-top:16px;padding:10px 24px;background:#2196F3;"
      "color:#fff;border-radius:6px;text-decoration:none}"
    "</style></head><body><div class='card'>"
    "<h2 style='color:" + cor + "'>" + (ok ? "Formatado!" : "Erro") + "</h2>"
    "<p>" + msg + "</p>"
    "<a href='/files' class='btn'>Arquivos SD</a> "
    "<a href='/' class='btn'>Inicio</a>"
    "</div></body></html>");
}


void handleEjetar() {
  cancelarEnvioArquivo();   // SD.end() com arquivo aberto corrompe o cartão
  if (sdDisponivel) {
    SD.end();
    sdDisponivel = false;
    Serial.println("[SD] Ejetado via web");
  }
  server.send(200, "text/html; charset=utf-8",
    "<!DOCTYPE html><html><head><meta charset='UTF-8'>"
    "<meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<style>body{font-family:Arial;text-align:center;padding:40px;background:#f0f4f0}"
    ".card{background:#fff;border-radius:12px;padding:24px;max-width:360px;margin:auto;"
    "box-shadow:0 2px 8px rgba(0,0,0,.1)}"
    "h2{color:#2e7d32}p{color:#444;margin:12px 0}"
    "a{display:inline-block;margin-top:16px;padding:10px 24px;background:#2196F3;"
    "color:#fff;border-radius:6px;text-decoration:none}</style></head>"
    "<body><div class='card'>"
    "<h2>SD Ejetado</h2>"
    "<p>Cartao desmontado com seguranca.</p>"
    "<p>Pode remover o SD agora.</p>"
    "<p style='font-size:.8em;color:#888'>Para remontar, reinicie o ESP32 (RST).</p>"
    "<a href='/'>Voltar</a></div></body></html>");
}


void handleLocalizacao() {
  if (!server.hasArg("lat") || !server.hasArg("lon")) {
    server.send(400, "application/json", "{\"ok\":false,\"erro\":\"lat/lon obrigatorios\"}");
    return;
  }
  float lat = server.arg("lat").toFloat();
  float lon = server.arg("lon").toFloat();
  if (lat < -35.0f || lat > 6.0f || lon < -75.0f || lon > -28.0f) {
    server.send(400, "application/json", "{\"ok\":false,\"erro\":\"coordenadas fora do Brasil\"}");
    return;
  }
  salvarLocalizacao(lat, lon);
  reqAtualizarClima = true;
  // A localização é do nowcast, consultado aqui no gateway — os nós não usam
  // coordenada nenhuma, só a flag de chuva que já viaja no beacon.
  server.send(200, "application/json",
    "{\"ok\":true,\"lat\":" + String(lat, 4) + ",\"lon\":" + String(lon, 4) + "}");
}

/// `POST /api/nos/esquecer` — tira do painel os nós conhecidos que estão mudos.
static void handleEsquecerNos() {
  esquecerNosConhecidos();
  notificarClientes();
  server.send(200, "application/json", "{\"ok\":true}");
}


// ══════════════════════════════════════════════════════════════════════════════
//  API DE GATEWAY — o que o controle central no Raspberry Pi consome
//
//  Contrato em `controle-central/app/gateway/http_client.py` e
//  `controle-central/PROTOCOLO.md` §1.4.
// ══════════════════════════════════════════════════════════════════════════════

/// `GET /api/leituras?desde=<cursor>` — polling do Raspberry Pi.
///
/// Devolve `{"leituras":[...], "cursor":N}`, que é o formato 4 da lista que o
/// `http_client.py` aceita. O `cursor` é a sequência da última linha entregue:
/// devolvê-lo de volta em `?desde=` continua exatamente de onde parou, sem
/// repetição e sem buraco.
/// Contexto do percurso da fila: o socket e um contador, para saber se a
/// proxima linha precisa de virgula na frente.
struct CtxLeituras {
  WiFiClient* cliente;
  int         n;
};

static bool escreverLinhaFila(const char* linha, uint32_t seq, void* ctx) {
  (void)seq;
  CtxLeituras* c = (CtxLeituras*)ctx;
  if (c->n++) c->cliente->print(',');
  c->cliente->print('"');
  // A linha e ASCII do proprio protocolo (KEY:VALOR separado por virgula), mas
  // `/api/data` aceita corpo livre, entao escapamos por seguranca.
  for (const char* q = linha; *q; q++) {
    if (*q == '"' || *q == 92) c->cliente->print((char)92);
    c->cliente->print(*q);
  }
  c->cliente->print('"');
  return true;
}

void handleApiLeituras() {
  uint32_t desde = 0;
  if (server.hasArg("desde")) desde = (uint32_t)strtoul(server.arg("desde").c_str(), nullptr, 10);

  // Não reentregar o que o push já confirmou. Com os dois caminhos ligados, a
  // mesma linha sairia daqui e do webhook, e o banco do Pi só descarta a cópia
  // quando o nó manda `TS:` — sem relógio, as duas viram leituras distintas.
  uint32_t piso = piAtivo() ? filaEnviadoAte() : 0;
  if (desde < piso) desde = piso;

  // Percurso sem alocacao. A versao anterior enchia um `String lote[FILA_TAM]`:
  // com 99 nos sao ~200 Strings na pilha da task (8 KB), que estoura, alem de
  // montar a resposta inteira (~30 KB) em heap antes de enviar.
  WiFiClient cliente = server.client();
  cliente.println("HTTP/1.1 200 OK");
  cliente.println("Content-Type: application/json");
  cliente.println("Access-Control-Allow-Origin: *");
  cliente.println("Connection: close");
  cliente.println();

  CtxLeituras ctx = { &cliente, 0 };
  uint32_t    ultimo = desde;

  cliente.print("{\"leituras\":[");
  filaPercorrer(desde, ultimo, escreverLinhaFila, &ctx);
  cliente.print("],\"cursor\":");
  cliente.print(ultimo);
  cliente.print('}');
}

/// `POST /api/comando` com `{"comando":"CMD:02:LIM1:35"}`.
///
/// Único caminho de saída de comando — o painel local usa exatamente esta rota,
/// então há uma validação só e uma fila só. A linha vai para a janela de
/// downlink do próximo ciclo TDMA, quando os nós estão ouvindo.
void handleApiComando() {
  String corpo = server.arg("plain");
  corpo.trim();
  if (corpo.length() == 0) {
    server.send(400, "application/json", "{\"ok\":false,\"erro\":\"corpo vazio\"}");
    return;
  }

  String linha = corpo;
  // Aceita tanto `{"comando":"CMD:..."}` quanto a linha crua em text/plain.
  int p = corpo.indexOf("\"comando\"");
  if (p >= 0) {
    int a = corpo.indexOf('"', corpo.indexOf(':', p) + 1);
    int b = (a >= 0) ? corpo.indexOf('"', a + 1) : -1;
    if (a < 0 || b < 0) {
      server.send(400, "application/json", "{\"ok\":false,\"erro\":\"json invalido\"}");
      return;
    }
    linha = corpo.substring(a + 1, b);
  }
  linha.trim();

  if (!enfileirarComando(linha)) {
    server.send(400, "application/json",
                "{\"ok\":false,\"erro\":\"comando fora do contrato ou fila cheia\"}");
    return;
  }
  server.send(200, "application/json",
              "{\"ok\":true,\"fila\":" + String(comandosPendentes()) + "}");
}

/// `GET /api/estado` — diagnóstico do enlace, para bancada e suporte.
void handleApiEstado() {
  WiFiClient c = server.client();
  c.println("HTTP/1.1 200 OK");
  c.println("Content-Type: application/json");
  c.println("Access-Control-Allow-Origin: *");
  c.println("Connection: close");
  c.println();

  c.print("{\"firmware\":\"gateway-v6\"");
  c.print(",\"uptime_s\":");    c.print(millis() / 1000UL);
  c.print(",\"ip_sta\":\"");    c.print(WiFi.localIP().toString());
  c.print("\",\"ip_ap\":\"");   c.print(WiFi.softAPIP().toString());
  c.print("\",\"sta\":");       c.print(WiFi.status() == WL_CONNECTED ? "true" : "false");
  c.print(",\"clientes_ap\":"); c.print(WiFi.softAPgetStationNum());
  c.print(",\"hora\":\"");      c.print(obterDataHora());
  c.print("\",\"hora_valida\":"); c.print(horaValida() ? "true" : "false");
  c.print(",\"heap\":");        c.print(ESP.getFreeHeap());
  c.print(",\"heap_min\":");    c.print(ESP.getMinFreeHeap());
  c.print(",\"cursor\":");      c.print(filaUltimoSeq());
  c.print(',');

  // Mesma fonte que o painel usa: duas serializacoes divergiriam na primeira
  // vez que alguem acrescentasse um campo em so uma delas.
  escreverContexto(c);

  // E o estado por no, para diagnostico de campo.
  c.print(",\"nos\":[");
  for (int i = 0; i < TOTAL_NOS; i++) {
    if (i) c.print(',');
    escreverDetalhe(c, i + 1);
  }
  c.print("]}");
}


/// Injeção manual de uma linha de telemetria, para teste de bancada sem rádio.
/// Continua exigindo `ID:` — `processarPacket` descarta o que não tiver.
void handleApiData() {
  String corpo = server.arg("plain");
  corpo.trim();
  if (corpo.length() == 0) {
    server.send(400, "text/plain", "corpo vazio");
    return;
  }
  // RSSI/SNR zerados = "não medido": `processarPacket` preserva os valores de
  // rádio já conhecidos em vez de sobrescrevê-los com zero.
  processarPacket(0.0f, 0.0f, corpo);
  notificarClientes();
  server.send(200, "application/json", "{\"ok\":true}");
}


void setupWebServer() {
  // ── Painel local ─────────────────────────────────────────────────────────
  server.on("/",                handleRoot);
  server.on("/data",            handleData);
  server.on("/events",          handleEvents);      // SSE do navegador
  server.on("/tabela",          handleTabela);
  server.on("/download",        handleDownload);
  server.on("/config",          handleConfig);
  server.on("/set-pi",          HTTP_POST, handleSetPi);

  // ── API de gateway: o que o Raspberry Pi consome ─────────────────────────
  server.on("/api/leituras",    HTTP_GET,  handleApiLeituras);
  server.on("/eventos",         handleEventosPi);   // SSE do controle central
  server.on("/api/comando",     HTTP_POST, handleApiComando);
  server.on("/api/estado",      HTTP_GET,  handleApiEstado);
  server.on("/api/no",          HTTP_GET,  handleApiNo);
  server.on("/api/data",        HTTP_POST, handleApiData);

  // ── WiFi ─────────────────────────────────────────────────────────────────
  server.on("/wifi-setup",      handleWifiSetup);
  server.on("/wifi-save",       HTTP_POST, handleWifiSave);
  server.on("/wifi-scan",       handleWifiScan);
  server.on("/wifi-disconnect", HTTP_POST, handleWifiDisconnect);

  // ── Cartão SD ────────────────────────────────────────────────────────────
  server.on("/ejetar",          handleEjetar);
  server.on("/files",           handleFiles);
  server.on("/file-delete",     handleFileDelete);
  server.on("/file-get",        handleFileDownloadArquivo);
  server.on("/file-view",       handleFileCfgView);
  server.on("/file-upload",     HTTP_POST, handleFileUploadDone, handleFileUploadChunk);
  server.on("/format-sd",       handleFormatSD);

  server.on("/api/localizacao", HTTP_POST, handleLocalizacao);
  server.on("/api/nos/esquecer", HTTP_POST, handleEsquecerNos);

  server.begin();
  Serial.println("[Web] Servidor iniciado");
}