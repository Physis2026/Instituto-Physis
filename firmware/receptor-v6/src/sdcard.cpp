#include "sdcard.h"
#include "globals.h"
#include "config.h"
#include <SD.h>
#include <SPI.h>

static SPIClass spiSD(FSPI);
static long     _totalLinhas = 0;

// ── Escrita de valores ────────────────────────────────────────────────────────
// `-` é o "sem dado" do contrato (PROTOCOLO.md §2.4) e é o que o CSV do controle
// central também usa. Gravar 0 no lugar de um sensor mudo inventa histórico.

static void escreverNum(File& f, float v, int casas) {
  if (isnan(v)) f.print("-");
  else          f.print(v, casas);
}

static void escreverPrev(File& f, float v) {
  if (isnan(v) || v < 0) f.print("-");
  else                   f.print((int)v);
}

static void escreverLinha(File& f, const Registro& r) {
  f.print(r.dataHora);                                        f.print(";");
  f.print(r.tipo == REGISTRO_EVENTO ? "EVENTO" : "LEITURA");  f.print(";");
  escreverNum(f, r.umidade1, 1);                              f.print(";");
  f.print(r.irrigando1 ? "SIM" : "NAO");                      f.print(";");
  escreverNum(f, r.limite1, 1);                               f.print(";");
  escreverNum(f, r.umidade2, 1);                              f.print(";");
  f.print(r.irrigando2 ? "SIM" : "NAO");                      f.print(";");
  escreverNum(f, r.limite2, 1);                               f.print(";");
  escreverNum(f, r.temp, 1);                                  f.print(";");
  escreverPrev(f, r.previsao1);                               f.print(";");
  escreverPrev(f, r.previsao2);                               f.print(";");
  // `No` no FIM, na mesma posição do CSV do controle central: pôr na frente
  // deslocaria todos os índices e quebraria o parser posicional do painel
  // antigo (PROTOCOLO.md §7.1). `UmidAr` e `TempSolo` vêm logo depois.
  if (r.nodeId < 10) f.print("0");
  f.print(r.nodeId);                                          f.print(";");
  escreverNum(f, r.umidadeAr, 1);                             f.print(";");
  escreverNum(f, r.tempSolo, 1);                              f.println();
}

// ── Migração do arquivo antigo ────────────────────────────────────────────────

static bool cabecalhoAtual() {
  File f = SD.open(ARQUIVO_DADOS, FILE_READ);
  if (!f) return false;
  f.readStringUntil('\n');                 // "sep=;"
  String cab = f.readStringUntil('\n');
  f.close();
  cab.trim();
  String esperado = String(ARQUIVO_CABECALHO);
  esperado.trim();
  return cab == esperado;
}

/// Guarda o histórico anterior em vez de sobrescrevê-lo. O CSV mudou de forma
/// (ganhou `No`, `UmidAr` e, no V6, `TempSolo`) e misturar larguras diferentes
/// quebra qualquer leitor.
static void arquivarHistoricoAntigo() {
  String destino = ARQUIVO_DADOS_V1;
  for (int i = 2; i < 10 && SD.exists(destino); i++) {
    destino = "/dados_v" + String(i) + ".csv";
  }
  if (SD.exists(destino)) {
    Serial.println("[SD] Sem nome livre para arquivar o historico antigo");
    return;
  }
  if (SD.rename(ARQUIVO_DADOS, destino)) {
    Serial.println("[SD] Historico anterior movido para " + destino);
  } else {
    Serial.println("[SD] Falha ao arquivar o historico anterior");
  }
}

static bool criarArquivo() {
  File f = SD.open(ARQUIVO_DADOS, FILE_WRITE);
  if (!f) {
    Serial.println("[SD] Erro ao criar arquivo de dados");
    return false;
  }
  f.print("sep=;\n");
  f.print(ARQUIVO_CABECALHO);
  f.close();
  _totalLinhas     = 0;
  totalRegistrosSD = 0;
  return true;
}

// ══════════════════════════════════════════════════════════════════════════════

bool setupSD() {
  pinMode(SD_CS_PIN, OUTPUT);
  digitalWrite(SD_CS_PIN, HIGH);
  delay(50);

  spiSD.begin(SD_SCK_PIN, SD_MISO_PIN, SD_MOSI_PIN, SD_CS_PIN);
  delay(100);

  if (!SD.begin(SD_CS_PIN, spiSD, 1000000)) {
    Serial.println("[SD] Falhou!");
    return false;
  }

  Serial.printf("[SD] OK! Tamanho: %lluMB\n", SD.cardSize() / (1024ULL * 1024ULL));

  if (!SD.exists(ARQUIVO_DADOS)) {
    if (!criarArquivo()) return false;
    Serial.println("[SD] Arquivo criado");
  } else if (!cabecalhoAtual()) {
    arquivarHistoricoAntigo();
    if (!criarArquivo()) return false;
  } else {
    _totalLinhas = contarLinhasSD() - 2;
    if (_totalLinhas < 0) _totalLinhas = 0;
    Serial.printf("[SD] Arquivo existente: %ld registros\n", _totalLinhas);
  }

  totalRegistrosSD = _totalLinhas;
  sdDisponivel     = true;
  flushBufferSD();   // o que ficou na RAM enquanto não havia cartão
  return true;
}

void salvarRegistroSD(const Registro& r) {
  File f = SD.open(ARQUIVO_DADOS, FILE_APPEND);
  if (!f) { Serial.println("[SD] Erro ao abrir para escrita!"); return; }
  escreverLinha(f, r);
  f.close();
  _totalLinhas++;
  totalRegistrosSD = _totalLinhas;
}

void flushBufferSD() {
  if (totalBufferRAM == 0) return;

  File f = SD.open(ARQUIVO_DADOS, FILE_APPEND);
  if (!f) { Serial.println("[SD] Erro no flush!"); return; }

  for (int i = 0; i < totalBufferRAM; i++) {
    escreverLinha(f, bufferRAM[i]);
    _totalLinhas++;
  }
  f.close();

  totalRegistrosSD = _totalLinhas;
  Serial.printf("[SD] Flush: %d registros gravados (total: %ld)\n",
                totalBufferRAM, _totalLinhas);
  totalBufferRAM = 0;
}

static void deletarRecursivo(const String& dir) {
  File d = SD.open(dir);
  if (!d || !d.isDirectory()) return;
  File entry = d.openNextFile();
  while (entry) {
    String nome = String(entry.name());
    int sl = nome.lastIndexOf('/');
    if (sl >= 0) nome = nome.substring(sl + 1);
    String caminho = (dir == "/" ? "" : dir) + "/" + nome;
    if (entry.isDirectory()) {
      entry.close();
      deletarRecursivo(caminho);
      SD.rmdir(caminho);
    } else {
      entry.close();
      SD.remove(caminho);
    }
    yield();
    entry = d.openNextFile();
  }
  d.close();
}

bool formatarSD() {
  Serial.println("[SD] Formatando — deletando todos os arquivos...");
  deletarRecursivo("/");

  SD.end();
  delay(300);

  if (!SD.begin(SD_CS_PIN, spiSD, 1000000)) {
    Serial.println("[SD] Falha ao remontar apos format");
    sdDisponivel = false;
    return false;
  }
  if (!criarArquivo()) return false;

  sdDisponivel = true;
  Serial.println("[SD] Format concluido — arquivo recriado");
  return true;
}

long contarLinhasSD() {
  File f = SD.open(ARQUIVO_DADOS, FILE_READ);
  if (!f) return 0;
  long linhas = 0;
  while (f.available()) {
    if (f.read() == '\n') linhas++;
    if ((linhas & 0x3F) == 0) yield();
  }
  f.close();
  return linhas;
}

long totalLinhasSD() { return _totalLinhas; }
