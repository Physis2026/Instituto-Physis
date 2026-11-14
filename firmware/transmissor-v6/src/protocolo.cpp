#include "protocolo.h"
#include <math.h>

String doisDigitos(uint8_t n) {
  char b[4];
  snprintf(b, sizeof(b), "%02u", (unsigned)n);
  return String(b);
}

bool extrairCampo(const String& linha, const char* chave, String& out) {
  String alvo = String(chave) + ":";
  int    de   = 0;
  int    pos  = -1;

  while (true) {
    int i = linha.indexOf(alvo, de);
    if (i < 0) break;
    // Só vale se a chave começa a linha ou vem logo depois de um separador —
    // senão "T:" casaria dentro de "PONT:" e leríamos o valor errado.
    char anterior = (i == 0) ? ',' : linha.charAt(i - 1);
    if (anterior == ',' || anterior == ';' || anterior == ' ') { pos = i; break; }
    de = i + 1;
  }
  if (pos < 0) return false;

  int ini = pos + alvo.length();
  int fim = linha.indexOf(',', ini);
  int fim2 = linha.indexOf(';', ini);
  if (fim < 0 || (fim2 >= 0 && fim2 < fim)) fim = fim2;
  if (fim < 0) fim = linha.length();

  out = linha.substring(ini, fim);
  out.trim();
  return out.length() > 0;
}

float extrairFloat(const String& linha, const char* chave, float padrao) {
  String v;
  if (!extrairCampo(linha, chave, v)) return padrao;
  return v.toFloat();
}

int extrairInt(const String& linha, const char* chave, int padrao) {
  String v;
  if (!extrairCampo(linha, chave, v)) return padrao;
  return v.toInt();
}

bool extrairBool(const String& linha, const char* chave, bool padrao) {
  String v;
  if (!extrairCampo(linha, chave, v)) return padrao;
  v.toUpperCase();
  if (v == "1" || v == "SIM" || v == "S" || v == "TRUE" || v == "T" ||
      v == "ON" || v == "LIGADO" || v == "YES")
    return true;
  if (v == "0" || v == "NAO" || v == "N" || v == "FALSE" || v == "F" ||
      v == "OFF" || v == "DESLIGADO" || v == "NO")
    return false;
  return v.toFloat() != 0.0f;
}

String num1(float v) {
  return String(v, 1);
}

bool separarComando(const String& linha, int& destino, String& acao, String& arg) {
  if (!linha.startsWith(PREFIXO_COMANDO)) return false;

  int i1 = strlen(PREFIXO_COMANDO);
  int i2 = linha.indexOf(':', i1);
  if (i2 < 0) return false;

  String alvo = linha.substring(i1, i2);
  alvo.trim();
  if (alvo.length() == 0 || alvo.length() > 2) return false;
  for (unsigned i = 0; i < alvo.length(); i++) {
    if (!isDigit(alvo.charAt(i))) return false;
  }
  destino = alvo.toInt();

  int i3 = linha.indexOf(':', i2 + 1);
  acao = (i3 < 0) ? linha.substring(i2 + 1) : linha.substring(i2 + 1, i3);
  arg  = (i3 < 0) ? String("")              : linha.substring(i3 + 1);
  acao.trim();
  acao.toUpperCase();
  arg.trim();
  return true;
}

static bool soDigitos(const String& s) {
  if (s.length() == 0) return false;
  for (unsigned i = 0; i < s.length(); i++)
    if (!isDigit(s.charAt(i))) return false;
  return true;
}

bool argumentoValido(const String& acao, const String& arg) {
  if (acao == "PING") return arg.length() == 0;
  if (acao == "IRR1" || acao == "IRR2") return arg == "0" || arg == "1";
  if (acao == "MODO") {
    String m = arg;
    m.toUpperCase();
    return m == "AUTO" || m == "MANUAL";
  }
  if (acao == "SYNC") {
    if (!soDigitos(arg) || arg.length() > 10) return false;
    unsigned long long e = strtoull(arg.c_str(), nullptr, 10);
    return e >= EPOCH_MIN_VALIDO && e <= EPOCH_MAX_VALIDO;
  }
  if (acao == "LIM1" || acao == "LIM2") {
    // A string TODA tem de ser o número: `toFloat()` leria "35,5" como 35 e
    // aceitaria "nan" (limiar NaN = o nó nunca mais irriga).
    char* fim;
    float v = strtof(arg.c_str(), &fim);
    return fim != arg.c_str() && *fim == '\0' && isfinite(v) && v >= 0.0f && v <= 100.0f;
  }
  return false;
}
