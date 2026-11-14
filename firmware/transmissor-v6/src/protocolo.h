#pragma once
#include <Arduino.h>

// ══════════════════════════════════════════════════════════════════════════════
//  Protocolo de linha — lado do nó.
//
//  Contrato completo em `controle-central/PROTOCOLO.md`; a fonte da verdade do
//  parser é `controle-central/app/protocolo.py`.
//
//  TELEMETRIA (nó → gateway → RPi), separador vírgula, decimal PONTO:
//    ID:03,U1:45.2,IR1:1,U2:50.0,IR2:0,T:27.5,UAR:63.5,TSOLO:23.1,P1:12.5,
//    P2:-1,LIM1:40.0,LIM2:40.0,BAT:3.87,TS:1786000000
//
//  COMANDO (RPi → gateway → nó):
//    CMD:<nn>:<AÇÃO>[:<ARG>]     nn = 01..99, ou 00 = broadcast
//
//  BEACON (gateway → todos os nós; nunca chega ao RPi):
//    BCN:<seq>,TS:<epoch>,CH:<0|1>,CIC:<ms>,SLOT:<ms>,GRD:<ms>,DSC:<ms>,MAP:<hex>
//    MAP = nós descobertos, 13 bytes em hex (byte 0 primeiro; nó id = bit
//    (id-1)%8 do byte (id-1)/8). O slot de um nó é a quantidade de descobertos
//    com ID menor; quem não está no mapa fala na janela DSC, depois dos slots.
// ══════════════════════════════════════════════════════════════════════════════

#define PREFIXO_COMANDO "CMD:"
#define PREFIXO_BEACON  "BCN:"

// Faixa de epoch plausível, IGUAL no receptor: abaixo é relógio zerado, acima é lixo.
#define EPOCH_MIN_VALIDO 1700000000UL   // 2023-11-14
#define EPOCH_MAX_VALIDO 4102444800UL   // 2100-01-01

/// `1` → `"01"`. O contrato é de dois dígitos (PROTOCOLO.md §4.2a).
String doisDigitos(uint8_t n);

/// Extrai o valor de `CHAVE:` numa linha `CHAVE:VALOR,CHAVE:VALOR`.
///
/// Só casa a chave quando ela está no início da linha ou logo depois de `,`/`;`.
/// Sem essa checagem, um `indexOf("T:")` ingênuo casaria dentro de outra chave e
/// leria o campo errado em silêncio.
bool extrairCampo(const String& linha, const char* chave, String& out);

float extrairFloat(const String& linha, const char* chave, float padrao);
int   extrairInt(const String& linha, const char* chave, int padrao);
bool  extrairBool(const String& linha, const char* chave, bool padrao);

/// Formata um float com 1 casa decimal e PONTO como separador.
///
/// `String(v, 1)` do Arduino usa `dtostrf`, que já emite ponto. Nunca troque por
/// formatação sensível a locale: num payload separado por vírgula, `U1:45,2` é
/// lido pelo RPi como `45` e o `,2` some sem erro nenhum (PROTOCOLO.md §2.2).
String num1(float v);

/// Separa `CMD:<nn>:<AÇÃO>[:<ARG>]`: destino de 1–2 dígitos, ação em
/// maiúsculas, argumento sem espaços nas pontas (vazio se não houver).
/// `false` se a linha não tem esse formato. Um destino não numérico é recusado,
/// não lido como 0: "CMD:AB:IRR1:1" viraria BROADCAST e ligaria todas as bombas.
bool separarComando(const String& linha, int& destino, String& acao, String& arg);

/// O argumento que cada uma das 7 ações aceita — a MESMA regra do receptor:
/// `SYNC` epoch plausível · `LIM1`/`LIM2` número inteiro 0–100 (ponto decimal) ·
/// `IRR1`/`IRR2` `0`|`1` · `MODO` `AUTO`|`MANUAL` · `PING` sem argumento.
/// Ação fora do contrato também dá `false`.
bool argumentoValido(const String& acao, const String& arg);
