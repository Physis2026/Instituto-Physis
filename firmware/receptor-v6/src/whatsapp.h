#pragma once
#include <Arduino.h>

// O nome do arquivo é minúsculo de propósito: ele era `Whatsapp.h` e só
// compilava no Windows, onde o sistema de arquivos ignora a caixa.

void enviarWhatsApp(String mensagem);
void verificarAlertas();
