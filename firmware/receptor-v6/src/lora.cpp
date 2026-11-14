#include "hardware.h"   // `heltec_unofficial.h` só pode ser incluído em main.cpp
#include "lora.h"
#include "globals.h"
#include "config.h"
#include "protocolo.h"
#include "historico.h"
#include "fila.h"
#include "weather.h"
#include "webpages.h"

#include <time.h>
#include <Preferences.h>

// ── Interrupção do rádio (definida em main.cpp) ───────────────────────────────
extern volatile bool pacoteRecebido;
void IRAM_ATTR aoReceberPacote();

// ══════════════════════════════════════════════════════════════════════════════
//  Divisão de trabalho entre a tarefa do rádio e o loop
//
//  · A TAREFA (`tarefaRadio`) é a única que toca no rádio: beacon, recepção,
//    downlink. Prioridade acima do loop, então um HTTP de 8 s no loop não
//    atrasa o beacon nem deixa um pacote ser sobrescrito no SX1262.
//  · O que ela recebe vai para `_filaRx`; o LOOP consome (`loraLoop`) e faz o
//    resto: estado do nó, cartão, fila do Pi, painel.
//  · O que o loop quer transmitir vai para `_filaTx`.
//  · Mapa de descobertos, flag de chuva e contadores por nó são partilhados e
//    passam por `_mux`.
// ══════════════════════════════════════════════════════════════════════════════

struct PacoteRx {
  char  linha[FILA_LINHA_MAX];
  float rssi;
  float snr;
};

#define FILA_CMD 16
#define NOS_BITMAP_BYTES ((TOTAL_NOS + 7) / 8)

static QueueHandle_t _filaRx = nullptr;
static QueueHandle_t _filaTx = nullptr;
static portMUX_TYPE  _mux    = portMUX_INITIALIZER_UNLOCKED;

static volatile bool     _pararTarefa   = false;
static volatile bool     _tarefaParada  = false;
static volatile uint32_t _rxDescartados = 0;
static volatile bool     _chuva         = false;   // escrito pelo loop, lido no beacon

// Escritos só pela tarefa; o loop só lê (32 bits: leitura atômica no ESP32).
// O ciclo e os slots são escolhidos no beacon e fixos até o próximo: é o valor
// que viaja no CIC, então mudar no meio do ciclo desalinharia os nós.
static volatile unsigned long _cicloMs    = CICLO_MAX_MS;
static volatile unsigned long _slotsCiclo = 0;
static volatile uint32_t      _seqBeacon  = 0;

// Protegidos por `_mux`.
static uint8_t  _mapa[NOS_BITMAP_BYTES]  = {0};   // descobertos, publicado pelo loop
static uint32_t _pacotesCiclo[TOTAL_NOS] = {0};
static uint8_t  _mudosSeguidos[TOTAL_NOS] = {0};  // ciclos seguidos sem ouvir o nó
static uint32_t _ciclosPerdidos[TOTAL_NOS] = {0};
static bool     _ouvido[TOTAL_NOS]       = {0};   // já falou desde o boot

// Só do loop: evita floodar SYNC num nó que já recebe a hora pelo beacon.
static unsigned long _ultimoSyncNo[TOTAL_NOS] = {0};
#define INTERVALO_SYNC_MS (5UL * 60UL * 1000UL)

/// Conta uma linha do nó `id` no ciclo corrente. Chamada pela tarefa no
/// instante da recepção — e não quando o loop chega a ler — para que a linha
/// conte no ciclo em que foi ao ar.
static void contarPacote(int id) {
  portENTER_CRITICAL(&_mux);
  _pacotesCiclo[id - 1]++;
  _mudosSeguidos[id - 1] = 0;
  _ouvido[id - 1]        = true;
  portEXIT_CRITICAL(&_mux);
}

// ── Nós conhecidos ────────────────────────────────────────────────────────────
// Um bit por nó que já falou alguma vez, na NVS. É o que o painel usa para não
// listar os 99 slots possíveis — e, por sobreviver ao reboot, um nó que morreu
// continua aparecendo como offline em vez de sumir da lista em silêncio.
// A gravação só acontece quando um nó aparece pela PRIMEIRA vez: desgaste nulo.
// É também o mapa do beacon: cada mudança é publicada para a tarefa do rádio.

static void bitsConhecidos(uint8_t* bits) {
  memset(bits, 0, NOS_BITMAP_BYTES);
  for (int i = 0; i < TOTAL_NOS; i++)
    if (nos[i].conhecido) bits[i / 8] |= (uint8_t)(1 << (i % 8));
}

static void publicarMapa() {
  uint8_t bits[NOS_BITMAP_BYTES];
  bitsConhecidos(bits);
  portENTER_CRITICAL(&_mux);
  memcpy(_mapa, bits, sizeof(bits));
  portEXIT_CRITICAL(&_mux);
}

static void gravarNosConhecidos() {
  uint8_t bits[NOS_BITMAP_BYTES];
  bitsConhecidos(bits);
  Preferences p;
  p.begin("irrigacao", false);
  p.putBytes("nos_vistos", bits, sizeof(bits));
  p.end();
  publicarMapa();
}

void carregarNosConhecidos() {
  uint8_t bits[NOS_BITMAP_BYTES] = {0};
  Preferences p;
  p.begin("irrigacao", true);
  p.getBytes("nos_vistos", bits, sizeof(bits));
  p.end();
  int n = 0;
  for (int i = 0; i < TOTAL_NOS; i++) {
    nos[i].conhecido = bits[i / 8] & (1 << (i % 8));
    if (nos[i].conhecido) n++;
  }
  publicarMapa();
  Serial.printf("[LoRa] %d no(s) conhecido(s) na NVS\n", n);
}

void esquecerNosConhecidos() {
  // Quem está falando agora continua na lista; só somem os que estão mudos.
  for (int i = 0; i < TOTAL_NOS; i++) nos[i].conhecido = nos[i].online;
  gravarNosConhecidos();
}

// ══════════════════════════════════════════════════════════════════════════════
//  Tarefa do rádio — nada daqui roda no loop
// ══════════════════════════════════════════════════════════════════════════════

// Por valor de propósito: `PhysicalLayer::transmit` recebe `String&` não-const.
static void transmitir(String linha) {
  int st = radio.transmit(linha);

  // O próprio TxDone dispara a DIO1: limpar a flag antes de voltar a escutar,
  // senão a volta seguinte tenta ler um pacote que não existe.
  pacoteRecebido = false;
  radio.setDio1Action(aoReceberPacote);
  radio.startReceive();

  if (st != RADIOLIB_ERR_NONE) Serial.printf("[TX] falhou (%d)\n", st);
}

/// Mapa dos nós descobertos para o campo MAP do beacon: NOS_BITMAP_BYTES bytes
/// em hex, byte 0 primeiro; o nó `id` é o bit (id-1)%8 do byte (id-1)/8.
/// Devolve também quantos nós estão no mapa — é o número de slots do ciclo.
static String mapaDescobertos(unsigned long& n) {
  uint8_t bits[NOS_BITMAP_BYTES];
  portENTER_CRITICAL(&_mux);
  memcpy(bits, _mapa, sizeof(bits));
  portEXIT_CRITICAL(&_mux);

  n = 0;
  for (int i = 0; i < TOTAL_NOS; i++)
    if (bits[i / 8] & (1 << (i % 8))) n++;

  static const char HEX_DIG[] = "0123456789ABCDEF";
  String s;
  s.reserve(NOS_BITMAP_BYTES * 2);
  for (int i = 0; i < NOS_BITMAP_BYTES; i++) {
    s += HEX_DIG[bits[i] >> 4];
    s += HEX_DIG[bits[i] & 0x0F];
  }
  return s;
}

/// Epoch para o beacon e o SYNC, ou 0 sem hora. `time()` em vez de
/// `horaValida()`: aquele espera até 10 ms quando não há hora, e aqui é o
/// instante exato da abertura do ciclo. Faixa igual à que o nó aceita.
static uint32_t epochAgora() {
  time_t agora = time(nullptr);
  return (agora >= (time_t)EPOCH_MIN_VALIDO && agora <= (time_t)EPOCH_MAX_VALIDO)
           ? (uint32_t)agora : 0;
}

static void enviarBeacon() {
  // O mapa e o ciclo são fotografados AQUI e valem até o próximo beacon: um nó
  // descoberto no meio do ciclo só ganha slot (e alonga o ciclo) no seguinte.
  unsigned long n;
  String mapa = mapaDescobertos(n);
  _slotsCiclo = n;
  _cicloMs    = CICLO_DE(n);
  _seqBeacon  = _seqBeacon + 1;

  String b = String(PREFIXO_BEACON) + String((uint32_t)_seqBeacon);
  b += ",TS:"   + String(epochAgora());     // 0 = "ainda não tenho hora"
  b += ",CH:"   + String(_chuva ? 1 : 0);
  b += ",CIC:"  + String((unsigned long)_cicloMs);
  b += ",SLOT:" + String(SLOT_MS);
  b += ",GRD:"  + String(GUARDA_MS);
  b += ",DSC:"  + String(JANELA_DESCOBERTA_MS);
  b += ",MAP:"  + mapa;

  transmitir(b);
}

/// Fecha o ciclo anterior: quem não falou no próprio slot perdeu o ciclo.
static void fecharCiclo() {
  portENTER_CRITICAL(&_mux);
  for (int i = 0; i < TOTAL_NOS; i++) {
    if (_pacotesCiclo[i] == 0) {
      if (_ouvido[i]) _ciclosPerdidos[i]++;
      if (_mudosSeguidos[i] < 255) _mudosSeguidos[i]++;
    }
    _pacotesCiclo[i] = 0;
  }
  portEXIT_CRITICAL(&_mux);
}

/// Linha recebida: conta para o nó e passa para o loop. Fila cheia (o loop
/// travado há mais de FILA_RX_TAM linhas) descarta a MAIS VELHA.
static void receberLinha(const String& linha, float rssi, float snr) {
  int id = extrairInt(linha, "ID", -1);
  if (id >= 1 && id <= TOTAL_NOS) contarPacote(id);

  PacoteRx p;
  strncpy(p.linha, linha.c_str(), sizeof(p.linha) - 1);
  p.linha[sizeof(p.linha) - 1] = '\0';
  p.rssi = rssi;
  p.snr  = snr;
  if (xQueueSend(_filaRx, &p, 0) != pdTRUE) {
    PacoteRx velho;
    xQueueReceive(_filaRx, &velho, 0);
    xQueueSend(_filaRx, &p, 0);
    _rxDescartados = _rxDescartados + 1;
  }
}

/// `CMD:<nn>:PING` com nn != 00. A linha da fila já está normalizada.
static bool pingEnderecado(const char* cmd) {
  return strncmp(cmd + 7, "PING", 4) == 0 && !(cmd[4] == '0' && cmd[5] == '0');
}

/// SYNC leva a hora de AGORA, não a de quando foi enfileirado: na fila ele pode
/// esperar ciclos, e o nó atrasaria o relógio pelo tempo de espera.
static String carimbarSync(const char* cmd) {
  String linha = cmd;
  uint32_t epoch;
  if (strncmp(cmd + 7, "SYNC:", 5) == 0 && (epoch = epochAgora()) != 0)
    linha = linha.substring(0, 12) + String(epoch);
  return linha;
}

static void passoTdma() {
  static unsigned long tCiclo           = millis();
  static bool          beaconEnviado    = false;
  static int           cmdEnviadosCiclo = 0;
  static unsigned long ultimoCmdEm      = 0;
  static unsigned long esperaCmd        = 0;

  // ── 1. Recepção ────────────────────────────────────────────────────────────
  if (pacoteRecebido) {
    pacoteRecebido = false;

    String linha;
    int st = radio.readData(linha);

    if (st == RADIOLIB_ERR_NONE) {
      linha.trim();
      // O gateway ignora o próprio eco e qualquer comando no ar: só telemetria
      // interessa aqui.
      if (!linha.startsWith(PREFIXO_BEACON) && !linha.startsWith(PREFIXO_COMANDO))
        receberLinha(linha, radio.getRSSI(), radio.getSNR());
    } else if (st == RADIOLIB_ERR_CRC_MISMATCH) {
      Serial.println("[LoRa] CRC invalido — ignorando");
    } else {
      Serial.printf("[LoRa] Pacote descartado (%d)\n", st);
    }

    radio.startReceive();
  }

  // ── 2. Virada de ciclo ─────────────────────────────────────────────────────
  unsigned long decorrido = millis() - tCiclo;
  while (decorrido >= _cicloMs) {
    fecharCiclo();
    tCiclo           += _cicloMs;
    decorrido        -= _cicloMs;
    beaconEnviado     = false;
    cmdEnviadosCiclo  = 0;
  }

  // ── 3. Beacon: abre o ciclo e sincroniza todos os nós de uma vez ───────────
  if (!beaconEnviado) {
    beaconEnviado = true;
    enviarBeacon();
    return;   // a transmissão já consumiu o tempo desta volta
  }

  // ── 4. Janela de downlink, no fim do ciclo ─────────────────────────────────
  // Fora dela o canal pertence aos slots dos nós; transmitir aqui atropelaria
  // a telemetria de alguém.
  if (decorrido < _cicloMs - JANELA_CMD_MS || cmdEnviadosCiclo >= MAX_CMD_POR_CICLO) return;
  if (cmdEnviadosCiclo > 0 && millis() - ultimoCmdEm < esperaCmd) return;

  char cmd[CMD_LINHA_MAX];
  if (xQueuePeek(_filaTx, cmd, 0) != pdTRUE) return;

  bool ping = pingEnderecado(cmd);
  // A resposta a um PING endereçado precisa caber antes do próximo beacon.
  if (ping && _cicloMs - decorrido < ESPERA_RESPOSTA_PING_MS) return;

  xQueueReceive(_filaTx, cmd, 0);
  String linha = carimbarSync(cmd);
  transmitir(linha);
  Serial.println("[TX] " + linha);
  cmdEnviadosCiclo++;
  ultimoCmdEm = millis();
  esperaCmd   = ping ? ESPERA_RESPOSTA_PING_MS : ESPACO_CMD_MS;
}

static void tarefaRadio(void*) {
  while (!_pararTarefa) {
    passoTdma();
    vTaskDelay(1);   // 1 ms: cede a CPU sem perder o início de slot nem o RxDone
  }
  _tarefaParada = true;
  vTaskDelete(nullptr);
}

// ══════════════════════════════════════════════════════════════════════════════
//  Loop — telemetria recebida
// ══════════════════════════════════════════════════════════════════════════════

static void tratarTelemetria(float rssi, float snr, String payload) {
  payload.trim();
  if (payload.length() == 0) return;

  // Uma mensagem por linha é o enquadramento do protocolo (PROTOCOLO.md §1.4).
  // Um `\n` no meio — possível via `POST /api/data`, que aceita corpo livre —
  // quebraria o lote do webhook em duas linhas, uma delas sem `ID:`.
  payload.replace('\r', ' ');
  payload.replace('\n', ' ');

  // ── Identidade: sem `ID:` válido a linha é DESCARTADA ─────────────────────
  // Creditar telemetria anônima ao nó 1 (o que o firmware antigo fazia por
  // omissão) mistura o histórico de setores diferentes sem deixar rastro.
  int id = extrairInt(payload, "ID", -1);
  if (id < 1 || id > TOTAL_NOS) {
    Serial.println("[LoRa] Sem ID valido — linha descartada: " + payload);
    return;
  }

  NoRede& n = nos[id - 1];
  bool ir1Antes   = n.c1.irrigando;
  bool ir2Antes   = n.c2.irrigando;

  n.id           = (uint8_t)id;
  if (rssi != 0.0f) n.rssi = rssi;
  if (snr  != 0.0f) n.snr  = snr;
  n.ultimoPacket = millis();
  n.online       = true;
  n.pacotes++;
  if (!n.conhecido) {
    n.conhecido = true;
    gravarNosConhecidos();
  }

  n.c1.umidade   = extrairFloat(payload, "U1",   NAN);
  n.c2.umidade   = extrairFloat(payload, "U2",   NAN);
  n.c1.irrigando = extrairBool (payload, "IR1",  false);
  n.c2.irrigando = extrairBool (payload, "IR2",  false);
  n.c1.limite    = extrairFloat(payload, "LIM1", n.c1.limite);
  n.c2.limite    = extrairFloat(payload, "LIM2", n.c2.limite);
  // `P1:-` (sem leitura de solo) vira NAN; `P1:-1` (aprendendo) fica -1.
  n.c1.previsao  = extrairFloat(payload, "P1",   NAN);
  n.c2.previsao  = extrairFloat(payload, "P2",   NAN);
  n.temp         = extrairFloat(payload, "T",    NAN);
  n.umidadeAr    = extrairFloat(payload, "UAR",  NAN);
  // `TSOLO:-` (DS18B20 ausente) cai na sentinela e vira NAN — não 0 °C.
  n.tempSolo     = extrairFloat(payload, "TSOLO", NAN);
  n.bateria      = extrairFloat(payload, "BAT",  NAN);
  n.comRelogio   = extrairInt  (payload, "TS",   0) > 0;

  // ── Linha para o controle central ─────────────────────────────────────────
  // RSSI e SNR são medidos AQUI, na recepção: o nó não os envia (§2.3).
  String linha = payload;
  if (rssi != 0.0f || snr != 0.0f) {
    linha += ",RSSI:" + String(rssi, 1) + ",SNR:" + String(snr, 1);
  }
  filaAdicionar(linha);

  salvarRegistro(REGISTRO_LEITURA, id);
  if (n.c1.irrigando != ir1Antes || n.c2.irrigando != ir2Antes) {
    salvarRegistro(REGISTRO_EVENTO, id);
    Serial.printf("[LoRa] No %02d irrigacao C1:%s C2:%s\n", id,
                  n.c1.irrigando ? "LIGA" : "DESL",
                  n.c2.irrigando ? "LIGA" : "DESL");
  }

  // ── Relógio ───────────────────────────────────────────────────────────────
  // O beacon já leva `TS:` a cada ciclo; um SYNC endereçado só faz sentido para
  // um nó que continua reportando sem hora, e mesmo assim com parcimônia. O
  // epoch é carimbado de novo na hora de ir para o ar.
  if (!n.comRelogio && horaValida() &&
      (_ultimoSyncNo[id - 1] == 0 || millis() - _ultimoSyncNo[id - 1] > INTERVALO_SYNC_MS)) {
    time_t agora;
    time(&agora);
    if (enfileirarAcao(id, "SYNC", String((uint32_t)agora))) {
      _ultimoSyncNo[id - 1] = millis();
      Serial.printf("[LoRa] SYNC agendado para o no %02d\n", id);
    }
  }

  Serial.printf("[RX] No %02d | U1:%.1f IR1:%d | U2:%.1f IR2:%d | T:%.1f UAR:%.1f TSOLO:%.1f | RSSI:%.1f SNR:%.1f\n",
                id, n.c1.umidade, n.c1.irrigando, n.c2.umidade, n.c2.irrigando,
                n.temp, n.umidadeAr, n.tempSolo, rssi, snr);
}

void processarPacket(float rssi, float snr, String payload) {
  // Linha injetada por HTTP não passou pela tarefa do rádio: conta aqui, para
  // o nó de bancada não cair para offline.
  int id = extrairInt(payload, "ID", -1);
  if (id >= 1 && id <= TOTAL_NOS) contarPacote(id);
  tratarTelemetria(rssi, snr, payload);
}

void loraLoop() {
  // A chuva vale enquanto a previsão é atual (weather.cpp); o beacon só lê.
  _chuva = chuvaVemAi();

  // Algumas linhas por volta: com a fila cheia depois de uma trava longa, o
  // painel e o servidor web não ficam esperando ela esvaziar inteira.
  PacoteRx p;
  for (int i = 0; i < 8 && xQueueReceive(_filaRx, &p, 0) == pdTRUE; i++) {
    tratarTelemetria(p.rssi, p.snr, String(p.linha));
    notificarClientes();
  }
}

// ══════════════════════════════════════════════════════════════════════════════
//  Comandos
// ══════════════════════════════════════════════════════════════════════════════

bool enfileirarComando(const String& linhaCmd) {
  String linha = linhaCmd;
  linha.trim();

  int    destino;
  String normalizada;
  if (!comandoValido(linha, destino, &normalizada) ||
      normalizada.length() >= CMD_LINHA_MAX) {
    Serial.println("[CMD] Recusado (fora do contrato): " + linha);
    return false;
  }

  char cmd[CMD_LINHA_MAX] = {0};
  strncpy(cmd, normalizada.c_str(), sizeof(cmd) - 1);
  if (xQueueSend(_filaTx, cmd, 0) != pdTRUE) {
    Serial.println("[CMD] Fila cheia — descartado: " + normalizada);
    return false;
  }
  Serial.println("[CMD] Enfileirado: " + normalizada);
  return true;
}

bool enfileirarAcao(int destino, const String& acao, const String& arg) {
  String linha = String(PREFIXO_COMANDO) + doisDigitos((uint8_t)destino) + ":" + acao;
  if (arg.length() > 0) linha += ":" + arg;
  return enfileirarComando(linha);
}

int comandosPendentes() { return _filaTx ? (int)uxQueueMessagesWaiting(_filaTx) : 0; }

// ══════════════════════════════════════════════════════════════════════════════

void loraSetup() {
  _filaRx = xQueueCreate(FILA_RX_TAM, sizeof(PacoteRx));
  _filaTx = xQueueCreate(FILA_CMD, CMD_LINHA_MAX);

  carregarNosConhecidos();

  int st = -1;
  for (int tentativa = 0; tentativa < 5 && st != RADIOLIB_ERR_NONE; tentativa++) {
    st = radio.begin();
    if (st == RADIOLIB_ERR_NONE) break;
    Serial.printf("[LoRa] Tentativa %d falhou (%d)\n", tentativa + 1, st);
    delay(500);
  }

  if (st != RADIOLIB_ERR_NONE || !_filaRx || !_filaTx) {
    Serial.printf("[LoRa] ERRO FATAL: %d\n", st);
    display.clear();
    display.drawString(0,  0, "ERRO: LoRa falhou!");
    display.drawString(0, 14, "Codigo: " + String(st));
    display.display();
    while (true) delay(1000);
  }

  radio.setFrequency(BAND);
  radio.setSpreadingFactor(SPREADING);
  radio.setBandwidth(BANDWIDTH);
  radio.setCodingRate(CODING_RATE);
  radio.setSyncWord(SYNC_WORD);
  radio.setOutputPower(TX_POWER);
  radio.setDio1Action(aoReceberPacote);

  st = radio.startReceive();
  if (st != RADIOLIB_ERR_NONE) {
    Serial.printf("[LoRa] startReceive falhou: %d\n", st);
    while (true) delay(1000);
  }

  for (int i = 0; i < TOTAL_NOS; i++) nos[i].id = (uint8_t)(i + 1);

  // Mesmo núcleo do loop, prioridade acima dele: o rádio interrompe o loop, não
  // o contrário. O primeiro beacon sai na primeira volta da tarefa.
  xTaskCreatePinnedToCore(tarefaRadio, "tdma", TDMA_PILHA, nullptr, TDMA_PRIORIDADE,
                          nullptr, ARDUINO_RUNNING_CORE);

  Serial.printf("[LoRa] OK | %.1f MHz | SF%d | BW %.0f kHz | SW 0x%02X | %d dBm\n",
                BAND, SPREADING, BANDWIDTH, SYNC_WORD, TX_POWER);
  Serial.printf("[TDMA] ciclo variavel %lu..%lu ms | slot %lu ms | guarda %lu ms | %d nos\n",
                CICLO_DE(0), CICLO_MAX_MS, SLOT_MS, GUARDA_MS, TOTAL_NOS);
}

void loraParar() {
  _pararTarefa = true;
  // A tarefa sai na próxima volta (≤ uma transmissão, ~100 ms). Matá-la de fora
  // podia deixar o barramento SPI travado no meio de uma transação.
  for (int i = 0; i < 100 && !_tarefaParada; i++) delay(10);
}

void verificarOnline() {
  static unsigned long ultima = 0;
  if (millis() - ultima < 2000) return;
  ultima = millis();

  uint8_t mudos[TOTAL_NOS];
  portENTER_CRITICAL(&_mux);
  memcpy(mudos, _mudosSeguidos, sizeof(mudos));
  portEXIT_CRITICAL(&_mux);

  bool mudou = false;
  for (int i = 0; i < TOTAL_NOS; i++) {
    NoRede& n = nos[i];
    // Relógio POR NÓ: um nó mudo não derruba os outros.
    if (n.online && mudos[i] >= CICLOS_PARA_OFFLINE) {
      n.online = false;
      mudou    = true;
      Serial.printf("[Status] No %02d offline (%u ciclos / %lu ms sem falar)\n",
                    i + 1, mudos[i], millis() - n.ultimoPacket);
    }
  }
  if (mudou) notificarClientes();
}

uint32_t ciclosPerdidosNo(int id) {
  if (id < 1 || id > TOTAL_NOS) return 0;
  portENTER_CRITICAL(&_mux);
  uint32_t v = _ciclosPerdidos[id - 1];
  portEXIT_CRITICAL(&_mux);
  return v;
}

unsigned long cicloMs()          { return _cicloMs; }
unsigned long slotsCiclo()       { return _slotsCiclo; }
uint32_t cicloAtual()            { return _seqBeacon; }
uint32_t beaconsEnviados()       { return _seqBeacon; }
uint32_t linhasRxDescartadas()   { return _rxDescartados; }
