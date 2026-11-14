#pragma once
#include <Arduino.h>

// ══════════════════════════════════════════════════════════════════════════════
//  Push para o controle central (Raspberry Pi).
//
//  `POST http://<host>:<porta>/api/gateway/webhook`, `text/plain`, uma linha de
//  telemetria por linha do corpo — exatamente o que `rotas_sistema.py` aceita.
//
//  Este é o caminho de PUSH: o dado chega no Pi no instante em que o ciclo
//  fecha, sem esperar o polling. O caminho de PULL (o Pi buscando
//  `/api/leituras` e ouvindo `/eventos` aqui) continua ativo em paralelo, de
//  propósito: se um cair, o outro sustenta, e o banco do Pi descarta a cópia
//  pela chave única (node_id, timestamp, tipo).
//
//  ⚠ Se `PAINEL_USUARIO`/`PAINEL_SENHA` estiverem ligados no `.env` do Pi, o
//    webhook passa a responder 401 e o push morre em silêncio (está no README
//    do controle-central). Nesse caso, desligue o push e use só o polling.
// ══════════════════════════════════════════════════════════════════════════════

void piSetup();
void piLoop();

/// Grava host/porta/ativo na NVS e passa a valer na hora.
bool piConfigurar(const String& host, uint16_t porta, bool ativo);

String        piHost();
uint16_t      piPorta();
bool          piAtivo();
bool          piUltimoOk();
unsigned long piMsDesdeUltimoEnvio();
uint32_t      piEnviados();
uint32_t      piFalhas();
String        piUltimoErro();
