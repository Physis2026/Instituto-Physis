#pragma once
#include <Arduino.h>

void   setupNTP();

/// Chamar quando o STA (re)conecta: pede a hora já, sem esperar o SNTP.
void   ntpAoConectar();

/// `true` quando o relógio já foi acertado por NTP. Consulta sem bloquear —
/// `getLocalTime()` com o timeout padrão trava 5 s quando não há hora, o que
/// destruiria o cronograma do TDMA.
bool   horaValida();

String obterDataHora();
String obterDataArquivo();
String millisParaHora(unsigned long ms);

/// Grava uma linha do histórico com o estado ATUAL do nó `nodeId`.
void   salvarRegistro(int tipo, int nodeId);
