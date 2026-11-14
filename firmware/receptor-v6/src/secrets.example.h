#pragma once
// Modelo dos segredos do Receptor V6.
// 1. Copie este arquivo para `secrets.h` (na mesma pasta).
// 2. Troque cada [DEFINIR] pelo valor real.
// O `secrets.h` NUNCA vai para o Git (está no .gitignore).

#ifndef WIFI_SSID
#define WIFI_SSID "[DEFINIR]"          // rede Wi-Fi da fazenda
#endif
#ifndef WIFI_PASS
#define WIFI_PASS "[DEFINIR]"
#endif
#ifndef AP_PASS
#define AP_PASS "[DEFINIR]"            // senha do ponto de acesso do receptor: 12+ caracteres, única por placa
#endif
#ifndef WA_NUMERO
#define WA_NUMERO "[DEFINIR]"          // número que recebe os alertas (CallMeBot)
#endif
#ifndef WA_APIKEY
#define WA_APIKEY "[DEFINIR]"
#endif
#ifndef WEATHER_API_KEY
#define WEATHER_API_KEY "[DEFINIR]"
#endif
