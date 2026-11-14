#include "hardware.h"   // `heltec_unofficial.h` só pode ser incluído em main.cpp
#include "lora_no.h"
#include "config.h"
#include "protocolo.h"
#include "identidade.h"
#include "weather.h"

#include <esp_random.h>
#include <time.h>
#include <sys/time.h>

// ── Estado do rádio ───────────────────────────────────────────────────────────
// O instante do RxDone é anotado NA INTERRUPÇÃO: o laço pode estar ocupado
// (display, DHT, cartão) e ler o pacote dezenas de ms depois. Datar o beacon
// pela hora da leitura deslocaria o ciclo inteiro do nó em relação ao receptor.
static volatile bool          _pacoteRecebido = false;
static volatile unsigned long _tIrq           = 0;
void IRAM_ATTR aoReceberPacote() {
  _tIrq           = millis();
  _pacoteRecebido = true;
}

// ── Estado do TDMA ────────────────────────────────────────────────────────────
static unsigned long _tRefCiclo       = 0;  // millis do início do ciclo corrente
static unsigned long _cicloMs         = CICLO_MS_PADRAO;
static unsigned long _slotMs          = SLOT_MS_PADRAO;
static unsigned long _guardaMs        = GUARDA_MS_PADRAO;
static uint32_t      _ciclosSemBeacon = MAX_HOLDOVER_CICLOS + 1;
static bool          _jaTransmitiu    = false;
static long          _jitterMs        = 0;
static float         _rssiBeacon      = 0.0f;
static uint32_t      _ultimoSeq       = 0;

// ── Mapa de nós descobertos (campo MAP do beacon) ─────────────────────────────
// Com o mapa, os slots são só dos descobertos, em ordem de ID: a posição deste
// nó é quantos descobertos têm ID menor. Fora do mapa, o nó fala na janela de
// descoberta, logo depois do último slot, num instante sorteado a cada ciclo.
// Sem mapa (receptor antigo, ou órfão), vale o slot fixo pelo ID.
static bool          _temMapa         = false;
static int           _posicao         = -1;   // -1 = fora do mapa
static unsigned long _nDescobertos    = 0;
static unsigned long _descobertaMs    = 1000;
#define MAPA_HEX_LEN (((TOTAL_NOS + 7) / 8) * 2)
#define DSC_FOLGA_MS 250   // airtime do maior payload + leitura dos sensores

// ── Resposta fora do slot (só para PING) ──────────────────────────────────────
static bool          _respostaAgendada = false;
static unsigned long _respostaEm       = 0;

// ── Relógio ───────────────────────────────────────────────────────────────────
// Nasce inválido a cada boot e só é considerado válido depois de um epoch
// plausível (beacon ou `CMD:<nn>:SYNC`). Enquanto isso o nó NÃO emite `TS:`:
// carimbo de hora errado é pior que carimbo ausente (PROTOCOLO.md §6.1).
static bool _relogioValido = false;

// ── Contadores ────────────────────────────────────────────────────────────────
static uint32_t _txTotal  = 0;
static uint32_t _cmdTotal = 0;

// ══════════════════════════════════════════════════════════════════════════════

// Por valor de propósito: `PhysicalLayer::transmit` recebe `String&` não-const.
static void transmitir(String linha) {
  // Ponto de estrangulamento da seguranca: uma placa sem identidade nao pode
  // pôr NADA no ar. Se transmitisse, entraria na rede se passando por outro no
  // e poluiria o historico de um setor real sem ninguem perceber.
  if (!noComissionado()) return;

  int st = radio.transmit(linha);

  // O próprio TxDone dispara a DIO1: limpar a flag antes de voltar a escutar,
  // senão o loop seguinte tenta ler um pacote que não existe.
  _pacoteRecebido = false;
  radio.setDio1Action(aoReceberPacote);
  radio.startReceive();

  if (st == RADIOLIB_ERR_NONE) {
    _txTotal++;
    Serial.println("[TX] " + linha);
  } else {
    Serial.printf("[TX] falhou (%d)\n", st);
  }
}

static uint32_t extrairEpoch(const String& linha, const char* chave) {
  String v;
  if (!extrairCampo(linha, chave, v)) return 0;
  return (uint32_t)strtoul(v.c_str(), nullptr, 10);
}

/// Tempo no ar de `n` bytes com os parâmetros atuais do rádio, em ms.
static unsigned long tempoNoArMs(size_t n) {
  return (unsigned long)((radio.getTimeOnAir(n) + 999) / 1000);
}

static void aplicarEpoch(uint32_t epoch) {
  // Abaixo é relógio zerado; acima, lixo — e uma hora no século seguinte faria
  // o RPi descartar cada linha deste nó como "do futuro".
  if (epoch < EPOCH_MIN_VALIDO || epoch > EPOCH_MAX_VALIDO) return;

  time_t agora;
  time(&agora);
  long deriva = (long)epoch - (long)agora;
  if (_relogioValido && labs(deriva) < 2) return;  // já está bom, não sacode

  struct timeval tv;
  tv.tv_sec  = (time_t)epoch;
  tv.tv_usec = 0;
  settimeofday(&tv, nullptr);

  if (!_relogioValido) Serial.printf("[Relogio] Sincronizado (epoch %lu)\n", (unsigned long)epoch);
  _relogioValido = true;
}

static int valorHex(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  return -1;
}

/// Lê `MAP:<hex>` (byte 0 primeiro; nó id = bit (id-1)%8 do byte (id-1)/8) e
/// acha a posição deste nó. Mapa ausente ou malformado → volta ao slot por ID.
static void aplicarMapa(const String& linha) {
  String hex;
  _temMapa = false;
  if (!extrairCampo(linha, "MAP", hex)) return;
  hex.trim();
  if (hex.length() != MAPA_HEX_LEN) return;

  unsigned long n   = 0;
  int           pos = -1;
  for (int i = 0; i < TOTAL_NOS; i++) {
    int alto  = valorHex(hex.charAt((i / 8) * 2));
    int baixo = valorHex(hex.charAt((i / 8) * 2 + 1));
    if (alto < 0 || baixo < 0) return;
    if (!(((alto << 4) | baixo) & (1 << (i % 8)))) continue;
    if (i + 1 == noId()) pos = (int)n;
    n++;
  }
  _temMapa      = true;
  _posicao      = pos;
  _nDescobertos = n;
}

// ── Beacon: BCN:<seq>,TS:<epoch>,CH:<0|1>,CIC:<ms>,SLOT:<ms>,GRD:<ms>,DSC:<ms>,MAP:<hex>
/// `tFim` = millis do RxDone. O receptor abre o ciclo quando COMEÇA a transmitir
/// o beacon; descontar o tempo no ar alinha o ciclo do nó ao dele (sem isso o nó
/// ficava ~90 ms atrasado, comendo a folga antes da janela de comandos).
static void processarBeacon(const String& linha, unsigned long tFim) {
  _tRefCiclo       = tFim - tempoNoArMs(linha.length());
  _ciclosSemBeacon = 0;
  _jaTransmitiu    = false;
  _jitterMs        = 0;  // sincronizado: slot exato, sem sorteio
  _rssiBeacon      = radio.getRSSI();
  _ultimoSeq       = (uint32_t)extrairEpoch(linha, "BCN");

  // O cronograma viaja no beacon: mudar o ciclo no receptor não exige regravar
  // os 4 nós. Faixas sanitizadas para que um beacon corrompido não desligue a
  // rede inteira.
  long cic  = extrairInt(linha, "CIC",  0);
  long slot = extrairInt(linha, "SLOT", 0);
  long grd  = extrairInt(linha, "GRD",  -1);
  if (cic  >= 2000 && cic  <= 3600000L)          _cicloMs  = (unsigned long)cic;
  if (slot >= 300  && slot <= (long)_cicloMs)    _slotMs   = (unsigned long)slot;
  if (grd  >= 0    && grd  <  (long)_cicloMs)    _guardaMs = (unsigned long)grd;
  long dsc = extrairInt(linha, "DSC", 0);
  if (dsc  >= DSC_FOLGA_MS && dsc < (long)_cicloMs) _descobertaMs = (unsigned long)dsc;

  aplicarMapa(linha);
  // Fora do mapa: sorteia o instante dentro da janela de descoberta, para que
  // dois nós novos ligados juntos não colidam sempre no mesmo ponto.
  if (_temMapa && _posicao < 0) _jitterMs = random(0, (long)(_descobertaMs - DSC_FOLGA_MS) + 1);

  String ch;
  if (extrairCampo(linha, "CH", ch)) setChuvaFlag(ch.toInt() != 0);

  aplicarEpoch(extrairEpoch(linha, "TS"));
}

// ── Comando: CMD:<nn>:<AÇÃO>[:<ARG>] ─────────────────────────────────────────
static void processarComando(const String& linha) {
  int    destino;
  String acao, arg;
  if (!separarComando(linha, destino, acao, arg)) return;   // fora do formato: ignora

  // Sem identidade, nem broadcast: `noId()` devolve 0, que é o proprio valor do
  // broadcast — sem esta guarda a comparacao abaixo daria "e para mim" e uma
  // placa de bancada obedeceria comando destinado ao campo.
  if (!noComissionado()) return;

  // ── REGRA DE OURO (PROTOCOLO.md §3.3) ──────────────────────────────────────
  if (destino != noId() && destino != NO_BROADCAST) return;

  // Mesma regra que o receptor aplica antes de pôr o comando no ar: `IRR1:abc`
  // não desliga a válvula, `MODO:xyz` não vira AUTO, `LIM1:nan` não zera nada.
  if (!argumentoValido(acao, arg)) {
    Serial.printf("[CMD] Recusado: %s '%s' fora do contrato\n", acao.c_str(), arg.c_str());
    return;
  }

  Serial.printf("[CMD] %s %s (destino %02d)\n", acao.c_str(), arg.c_str(), destino);

  if (acao == "SYNC") {
    aplicarEpoch((uint32_t)strtoul(arg.c_str(), nullptr, 10));
    _cmdTotal++;
    _jaTransmitiu = false;   // reflete no próximo slot (§3.4)
    return;
  }

  if (acao == "PING") {
    _cmdTotal++;
    // Enderecado: so um no responde, e o receptor segura o comando seguinte por
    // ESPERA_RESPOSTA_PING_MS — a resposta imediata que o checklist §9.2 cobra
    // nao colide com nada. Mas ela tem de acabar antes do proximo beacon.
    unsigned long noCiclo = millis() - _tRefCiclo;
    unsigned long precisa = ATRASO_PING_MS + tempoNoArMs(montarTelemetria().length()) + MARGEM_TX_MS;
    if (destino != NO_BROADCAST && tdmaSincronizado() && noCiclo + precisa <= _cicloMs) {
      _respostaAgendada = true;
      _respostaEm       = millis() + ATRASO_PING_MS;
    } else {
      // Broadcast (com 99 nos, espalhar as respostas por ID daria ~12 s de
      // transmissoes invadindo os slots alheios), sem tempo no ciclo, ou sem
      // beacon para saber onde o ciclo acaba: responde no PROPRIO slot, que ja
      // e livre de colisao por construcao.
      _jaTransmitiu = false;
    }
    return;
  }

  if (aplicarAcao(acao, arg)) {
    _cmdTotal++;
    // Não responde fora do slot: o comando chega na janela de downlink e o slot
    // do nó está a poucos segundos. Transmitir aqui arriscaria colidir com a
    // resposta de outro nó ao mesmo broadcast.
    _jaTransmitiu = false;
  }
}

/// Transmite a telemetria do ciclo se ela ainda CABE inteira até `fim` (ms
/// desde o início do ciclo). O teste de "estou na janela" só olha o início:
/// com o laço atrasado, a transmissão podia começar no fim do slot e invadir o
/// do vizinho. Não cabendo, este ciclo fica sem linha deste nó.
static void transmitirAte(unsigned long fim) {
  _jaTransmitiu = true;
  String        linha  = montarTelemetria();
  unsigned long agora  = millis() - _tRefCiclo;
  unsigned long noAr   = tempoNoArMs(linha.length());
  if (agora + noAr + MARGEM_TX_MS > fim) {
    Serial.printf("[TDMA] Slot perdido: em %lu ms a linha (%lu ms no ar) passaria de %lu ms\n",
                  agora, noAr, fim);
    return;
  }
  prepararSlot();
  transmitir(linha);
}

// ══════════════════════════════════════════════════════════════════════════════

void loraSetup() {
  int st = -1;
  for (int tentativa = 0; tentativa < 5 && st != RADIOLIB_ERR_NONE; tentativa++) {
    st = radio.begin();
    if (st != RADIOLIB_ERR_NONE) {
      Serial.printf("[LoRa] Tentativa %d falhou (%d)\n", tentativa + 1, st);
      delay(500);
    }
  }

  if (st != RADIOLIB_ERR_NONE) {
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

  // Nasce dessincronizado: transmite na própria cadência, com jitter, até o
  // primeiro beacon. Assim um nó ligado antes do receptor não fica mudo.
  randomSeed(micros() + (unsigned long)noId() * 7919UL + esp_random());
  _tRefCiclo       = millis();
  _ciclosSemBeacon = MAX_HOLDOVER_CICLOS + 1;
  _jitterMs        = random(0, JITTER_MAX_MS);

  Serial.printf("[LoRa] OK | No %02u | %.1f MHz | SF%d | BW %.0f kHz | SW 0x%02X | %d dBm\n",
                noId(), BAND, SPREADING, BANDWIDTH, SYNC_WORD, TX_POWER);
}

void loraLoop() {
  // ── 1. Recepção ────────────────────────────────────────────────────────────
  if (_pacoteRecebido) {
    _pacoteRecebido = false;
    unsigned long tFim = _tIrq;

    String linha;
    int st = radio.readData(linha);

    if (st == RADIOLIB_ERR_NONE) {
      linha.trim();
      if (linha.startsWith(PREFIXO_BEACON)) {
        processarBeacon(linha, tFim);
      } else if (linha.startsWith(PREFIXO_COMANDO)) {
        processarComando(linha);
      }
      // Telemetria de outro nó: ignorada em silêncio.
    } else if (st != RADIOLIB_ERR_CRC_MISMATCH) {
      Serial.printf("[RX] descartado (%d)\n", st);
    }

    radio.startReceive();
  }

  // ── 2. Avanço do ciclo (holdover quando o beacon não chega) ────────────────
  unsigned long decorrido = millis() - _tRefCiclo;
  while (decorrido >= _cicloMs) {
    _tRefCiclo += _cicloMs;
    decorrido  -= _cicloMs;
    _ciclosSemBeacon++;
    _jaTransmitiu = false;
    if (_ciclosSemBeacon > MAX_HOLDOVER_CICLOS) {
      // Órfão: sorteia o desvio a cada ciclo para que dois nós sem beacon não
      // colidam sempre no mesmo instante. O mapa velho deixa de valer.
      _jitterMs = random(0, JITTER_MAX_MS);
      _temMapa  = false;
    }
  }

  // ── 3. Resposta agendada a um PING ─────────────────────────────────────────
  if (_respostaAgendada && (long)(millis() - _respostaEm) >= 0) {
    _respostaAgendada = false;
    prepararSlot();
    transmitir(montarTelemetria());
  }

  // ── 4. Meu slot ────────────────────────────────────────────────────────────
  if (_temMapa) {
    // Descoberto: slot na posição do mapa. Fora do mapa: janela de descoberta,
    // logo depois do último slot, no instante sorteado no beacon.
    unsigned long inicio, fim;
    if (_posicao >= 0) {
      inicio = _guardaMs + (unsigned long)_posicao * _slotMs;
      fim    = inicio + _slotMs;
    } else {
      unsigned long janela = _guardaMs + _nDescobertos * _slotMs;
      inicio = janela + (unsigned long)_jitterMs;
      fim    = janela + _descobertaMs;
    }
    if (fim > _cicloMs) return;   // cronograma incoerente: melhor calar

    if (!_jaTransmitiu && decorrido >= inicio && decorrido < fim) transmitirAte(fim);
    return;
  }

  // Sem mapa (receptor antigo, ou órfão): slot fixo pelo ID.
  unsigned long inicioSlot = _guardaMs + (unsigned long)(noId() - 1) * _slotMs;

  // Cronograma incoerente (beacon corrompido, ou ciclo encurtado sem encurtar o
  // slot) deixaria os nós de trás com o slot fora do ciclo — mudos para sempre.
  // Nesse caso, divide o que sobra do ciclo igualmente entre os nós.
  if (inicioSlot + _slotMs > _cicloMs) {
    unsigned long util = (_cicloMs > _guardaMs) ? (_cicloMs - _guardaMs) : _cicloMs;
    inicioSlot = _guardaMs + (unsigned long)(noId() - 1) * (util / TOTAL_NOS);
  }
  inicioSlot += _jitterMs;

  unsigned long fimSlot = inicioSlot + _slotMs;
  if (fimSlot > _cicloMs) fimSlot = _cicloMs;

  if (!_jaTransmitiu && decorrido >= inicioSlot && decorrido < fimSlot) transmitirAte(fimSlot);
}

// ── Consultas ─────────────────────────────────────────────────────────────────
bool          tdmaSincronizado()      { return _ciclosSemBeacon <= MAX_HOLDOVER_CICLOS; }
uint32_t      ciclosSemBeacon()       { return _ciclosSemBeacon; }
unsigned long cicloAtualMs()          { return _cicloMs; }
unsigned long slotAtualMs()           { return _slotMs; }
float         rssiBeacon()            { return _rssiBeacon; }
uint32_t      totalTransmitido()      { return _txTotal; }
uint32_t      totalComandosAceitos()  { return _cmdTotal; }
bool          relogioValido()         { return _relogioValido; }

uint32_t epochAtual() {
  time_t agora;
  time(&agora);
  return (uint32_t)agora;
}
