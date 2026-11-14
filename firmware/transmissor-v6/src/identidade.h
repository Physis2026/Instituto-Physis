#pragma once
#include <Arduino.h>

// ══════════════════════════════════════════════════════════════════════════════
//  Identidade do nó — comissionamento por NVS.
//
//  Com 99 nós possíveis, gravar uma imagem diferente por placa é inviável: são
//  99 builds, 99 gravações e 99 etiquetas, e um engano no meio coloca duas
//  placas no mesmo setor. Aqui a MESMA imagem vai para todas e o número é
//  gravado uma vez, pela serial, no comissionamento.
//
//  Ordem de precedência:
//
//    1. `-D NODE_ID=n` em tempo de compilação  -> vale ele, imutável em runtime.
//       Mantém funcionando as placas já gravadas com o esquema antigo.
//    2. NVS (chave `node_id`)                  -> o caminho normal.
//    3. Nada                                   -> `noId()` devolve 0, o nó NÃO
//       TRANSMITE e o OLED avisa.
//
//  O padrão de fábrica ser inválido é exigência do PROTOCOLO.md §4.2(d): uma
//  placa não comissionada que entrasse na rede se passando pelo nó 01 poluiria
//  o histórico de um setor real, e ninguém perceberia.
//
//  Comissionamento (monitor serial a 115200, digite e dê Enter):
//
//      id            mostra o ID atual
//      id 7          grava o ID 7 na NVS e reinicia a identidade
//      ajuda         lista os comandos
// ══════════════════════════════════════════════════════════════════════════════

/// Lê a identidade (build flag ou NVS). Chamar cedo no `setup()`.
void identidadeSetup();

/// Console de comissionamento pela serial. Chamar no `loop()`.
void identidadeLoop();

/// `1..TOTAL_NOS`, ou **0** se a placa ainda não foi comissionada.
uint8_t noId();

/// `false` enquanto o nó não tem identidade válida. Nesse estado ele não
/// transmite nada e ignora todo comando, inclusive broadcast.
bool noComissionado();

/// Grava o ID na NVS. Recusa fora de `1..TOTAL_NOS` e quando a identidade veio
/// de `-D NODE_ID` (aí ela é do binário, não da placa).
bool definirNoId(uint8_t novo);

/// `true` quando o ID veio de `-D NODE_ID` e não pode mudar em runtime.
bool identidadeFixaEmCompilacao();

/// Implementada em main.cpp: comandos de console que não são de identidade
/// (ex.: `sensores`). Recebe a linha em minúsculas; devolve `true` se tratou.
bool comandoSerialExtra(const String& cmd);
