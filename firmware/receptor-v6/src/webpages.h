#pragma once
#include <Arduino.h>

void setupWebServer();

// ── Painel local ──────────────────────────────────────────────────────────────
void handleRoot();
void handleData();
void handleEvents();        // SSE do navegador (JSON completo do painel)
void handleTabela();
void handleDownload();
void handleConfig();
void handleSetPi();

// ── API de gateway: o que o controle central no Raspberry Pi consome ──────────
void handleApiLeituras();   // GET  /api/leituras?desde=<cursor>
void handleEventosPi();     // GET  /eventos — SSE de linhas de telemetria
void handleApiComando();    // POST /api/comando  {"comando":"CMD:02:LIM1:35"}
void handleApiEstado();     // GET  /api/estado — diagnóstico
void handleApiNo();         // GET  /api/no?id=N — detalhe de um nó
void handleApiData();       // POST /api/data — injeção manual, para bancada

// ── Cartão SD ─────────────────────────────────────────────────────────────────
void handleEjetar();
void handleFiles();
void handleFileDelete();
void handleFileCfgView();
void handleFileDownloadArquivo();
void handleFileUploadDone();
void handleFileUploadChunk();
void handleFormatSD();

void handleLocalizacao();

// ── Download do SD em partes (o handler só abre; o loop envia) ────────────────
void enviarArquivoPendente();   // chamar no loop
void cancelarEnvioArquivo();    // antes de ejetar/formatar/apagar/dormir

// ── Tempo real ────────────────────────────────────────────────────────────────
void notificarClientes();   // empurra o estado atual para os navegadores
void verificarSSE();        // entrega ao Pi + heartbeat + limpeza de sockets
