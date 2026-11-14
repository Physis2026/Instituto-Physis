#pragma once
#include <Arduino.h>

// ══════════════════════════════════════════════════════════════════════════════
//  Protocolo de linha — lado do gateway.
//
//  Contrato completo em `Claude Worktree/controle-central/PROTOCOLO.md`; a fonte
//  da verdade do parser é `controle-central/app/protocolo.py`.
//
//  TELEMETRIA (nó → gateway → RPi) — o gateway acrescenta RSSI/SNR:
//    ID:03,U1:45.2,IR1:1,U2:50.0,IR2:0,T:27.5,UAR:63.5,TSOLO:23.1,P1:12.5,
//    P2:-1,LIM1:30.0,LIM2:30.0,BAT:3.87,TS:1786000000,RSSI:-92,SNR:9.5
//
//  UAR, TSOLO e BAT são chaves de extensão (o RPi as guarda em `extras`).
//
//  COMANDO (RPi → gateway → nó):
//    CMD:<nn>:<AÇÃO>[:<ARG>]     nn = 01..99, ou 00 = broadcast
//
//  BEACON (gateway → nós; nunca sobe para o RPi):
//    BCN:<seq>,TS:<epoch>,CH:<0|1>,CIC:<ms>,SLOT:<ms>,GRD:<ms>,DSC:<ms>,MAP:<hex>
//    MAP = nós descobertos, 13 bytes em hex (byte 0 primeiro; nó id = bit
//    (id-1)%8 do byte (id-1)/8). O slot de um nó é a quantidade de descobertos
//    com ID menor; quem não está no mapa fala na janela DSC, depois dos slots.
// ══════════════════════════════════════════════════════════════════════════════

#define PREFIXO_COMANDO "CMD:"
#define PREFIXO_BEACON  "BCN:"
#define NO_BROADCAST    0

// Faixa de epoch plausível, IGUAL no nó: abaixo é relógio zerado, acima é lixo.
#define EPOCH_MIN_VALIDO 1700000000UL   // 2023-11-14
#define EPOCH_MAX_VALIDO 4102444800UL   // 2100-01-01

String doisDigitos(uint8_t n);

/// Extrai o valor de `CHAVE:` numa linha `CHAVE:VALOR,CHAVE:VALOR`.
///
/// Só casa a chave no início da linha ou logo depois de `,`/`;`. Um
/// `indexOf("T:")` ingênuo casaria dentro de outra chave e leria o campo errado
/// em silêncio — que é o tipo de bug que só aparece em campo.
bool  extrairCampo(const String& linha, const char* chave, String& out);
float extrairFloat(const String& linha, const char* chave, float padrao);
int   extrairInt(const String& linha, const char* chave, int padrao);
bool  extrairBool(const String& linha, const char* chave, bool padrao);

/// Float com 1 casa e separador PONTO (obrigatório — PROTOCOLO.md §2.2).
String num1(float v);

/// Separa `CMD:<nn>:<AÇÃO>[:<ARG>]`: destino de 1–2 dígitos, ação em
/// maiúsculas, argumento sem espaços nas pontas (vazio se não houver).
/// `false` se a linha não tem esse formato. Um destino não numérico é recusado,
/// não lido como 0: "CMD:AB:IRR1:1" viraria BROADCAST e ligaria todas as bombas.
bool separarComando(const String& linha, int& destino, String& acao, String& arg);

/// O argumento que cada uma das 7 ações aceita — a MESMA regra do nó:
/// `SYNC` epoch plausível · `LIM1`/`LIM2` número inteiro 0–100 (ponto decimal) ·
/// `IRR1`/`IRR2` `0`|`1` · `MODO` `AUTO`|`MANUAL` · `PING` sem argumento.
/// Ação fora do contrato também dá `false`.
bool argumentoValido(const String& acao, const String& arg);

/// Valida `CMD:<nn>:<AÇÃO>[:<ARG>]` e devolve o destino em `destino`.
///
/// Recusa ação fora das 7 do contrato, argumento que o nó recusaria, destino
/// não numérico e destino fora de `0..TOTAL_NOS`. Sem a checagem do argumento,
/// `LIM1:abc` era aceito aqui, recusado no nó — e como o nó manda `LIM1`/`LIM2`
/// em toda linha, o Pi dava o comando por confirmado.
///
/// `normalizada`, se pedida, recebe a linha na forma canônica que vai para o ar
/// (destino com dois dígitos, ação e modo em maiúsculas).
bool comandoValido(const String& linha, int& destino, String* normalizada = nullptr);
