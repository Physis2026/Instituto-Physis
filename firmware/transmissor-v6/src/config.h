#pragma once

// ══════════════════════════════════════════════════════════════════════════════
//  Nó transmissor V6 — Heltec WiFi LoRa 32 V3 (ESP32-S3 + SX1262)
//  Par do `Projeto Receptor V6`.
//  2 sensores capacitivos de solo · 1 DS18B20 (temp. do solo) · 1 DHT22 ·
//  1 relé de irrigação · registro em microSD
// ══════════════════════════════════════════════════════════════════════════════

// ── Identidade ────────────────────────────────────────────────────────────────
// A identidade NÃO é mais obrigatória em tempo de compilação. Com dezenas de
// placas, uma imagem por nó vira um dia inteiro de gravação e etiquetagem; por
// isso o padrão agora é comissionar pela NVS (uma imagem para todas), como o
// PROTOCOLO.md §4.2(d2) já previa. Ver `identidade.h`.
//
//   · Com `-D NODE_ID=n` no platformio.ini  -> vale ele, imutável em runtime.
//     (mantém compatíveis as placas já gravadas com o esquema antigo)
//   · Sem o flag                            -> lê da NVS; sem comissionar, o nó
//     NÃO TRANSMITE e avisa no OLED.
//
// O padrão de fábrica é 0, que é inválido de propósito: uma placa não
// comissionada entrando na rede se passando pelo nó 01 é pior que uma placa muda.
#if defined(NODE_ID) && (NODE_ID < 1 || NODE_ID > 99)
#error "NODE_ID fora da faixa do protocolo (1..99)"
#endif

#define NO_BROADCAST 0

// Teto do protocolo: `ID:` tem dois dígitos, `01`..`99`, e `00` é o broadcast de
// comando. Passar de 99 exigiria mudar o contrato de linha (PROTOCOLO.md §2.3).
// Precisa bater com TOTAL_NOS do receptor e do `.env` do Raspberry Pi.
#define TOTAL_NOS 99

// ── Rádio (idêntico nos 5 dispositivos — PROTOCOLO.md §1.2) ───────────────────
#define BAND        915.0   // MHz
#define SPREADING   7
#define BANDWIDTH   250.0   // kHz
#define CODING_RATE 5       // 4/5
#define SYNC_WORD   0x12    // privado, não-LoRaWAN
#define TX_POWER    14      // dBm

// ── Pinos ─────────────────────────────────────────────────────────────────────
// ⚠ CONFERIR CONTRA O ESQUEMA DA SUA PLACA. Variantes do Heltec V3 expõem pinos
//   diferentes. Evitados: 33–37 (reservados em módulos S3 com PSRAM octal),
//   45/46 (strapping) e os pinos de OLED/LoRa, que vêm de heltec_unofficial.h
//   (SDA 17, SCL 18, RST 21; SS 8, DIO1 14, RST 12, BUSY 13).
#define PINO_SOLO_A 5   // ADC1_CH4 — ADC2 é inutilizável com o rádio ativo
#define PINO_SOLO_B 6   // ADC1_CH5
#define PINO_DHT    7
#define PINO_RELE   4   // ativo em LOW (módulo de relé comum)
#define PINO_TEMP_SOLO 2  // DS18B20 (OneWire) — exige pull-up de 4,7 kΩ para 3V3

// microSD em barramento SPI próprio (FSPI), separado do rádio (HSPI, SCK 9/MISO 11/
// MOSI 10). 38–42 ficam no header J3 do Heltec V3.
#define PINO_SD_SCK  40
#define PINO_SD_MISO 41
#define PINO_SD_MOSI 42
#define PINO_SD_CS   39
// Vext (alimentação dos sensores) não aparece aqui de propósito: quem cuida é
// `heltec_ve(true)`, que já usa o pino certo de cada variante da placa.

#define RELE_LIGADO   LOW
#define RELE_DESLIGADO HIGH

// ── Calibração do solo, POR SENSOR ────────────────────────────────────────────
// Raw ADC de 12 bits. Valor ALTO = seco. Medir cada sensor: seco ao ar livre
// (SECO_*) e submerso até a marca (MOLHADO_*). O V4 usava um par só para os dois
// sensores — é fonte silenciosa de erro de vários pontos percentuais.
#define SECO_A     3900
#define MOLHADO_A  1878
#define SECO_B     3900
#define MOLHADO_B  1878

#define AMOSTRAS_ADC 5   // mediana de N leituras por sensor

// ── DHT ───────────────────────────────────────────────────────────────────────
#define DHT_TIPO         DHT22   // -40..80 °C, ±0,5 °C; umidade 0..100 %, ±2 %
#define INTERVALO_DHT_MS 2200    // o DHT22 exige no mínimo 2 s entre leituras
#define MAX_FALHAS_DHT   5       // falhas seguidas (~11 s) até reportar vazio

// ── Atualização local ─────────────────────────────────────────────────────────
// O nó lê sensores, roda o modelo e decide a irrigação neste intervalo, mas só
// TRANSMITE (e grava no SD) uma vez por ciclo, dentro do próprio slot TDMA.
// O DHT22 continua limitado a INTERVALO_DHT_MS: entre leituras vale o último valor.
#define INTERVALO_LEITURA_MS 1000UL

// ── Temperatura do solo (DS18B20) ─────────────────────────────────────────────
#define RESOLUCAO_TEMP_SOLO    12      // bits: 12 = 0,0625 °C, conversão de 750 ms
#define INTERVALO_TEMP_SOLO_MS 1000UL  // acompanha INTERVALO_LEITURA_MS (conversão leva 750 ms)
#define VALIDADE_TEMP_SOLO_MS  30000UL // sem leitura boa há 30 s -> reporta vazio

// ── Cartão SD ─────────────────────────────────────────────────────────────────
#define USAR_SD        1
#define ARQUIVO_SD     "/telemetria.csv"
#define RETENTAR_SD_MS (5UL * 60UL * 1000UL)  // sem cartão, tenta montar a cada 5 min

// ── TDMA ──────────────────────────────────────────────────────────────────────
// Estes são apenas os valores de PARTIDA: o cronograma real chega no beacon
// (campos CIC/SLOT/GRD), então mudar o ciclo no receptor não exige regravar os
// nós. Usados enquanto nenhum beacon foi ouvido.
// Slot de 500 ms: o maior payload previsto (120 B) leva ~100 ms no ar em
// SF7/BW250/CR4-5, e a leitura dos sensores antes de transmitir custa outros
// ~40 ms no pior caso. Sobra mais de 3x de folga.
#define SLOT_MS_PADRAO        500UL
#define GUARDA_MS_PADRAO      600UL
#define JANELA_DSC_PADRAO    1000UL
#define FOLGA_PRE_CMD_PADRAO  200UL
#define JANELA_CMD_PADRAO    1200UL

// No receptor V6 o ciclo é VARIÁVEL (1 s a cada dois nós DESCOBERTOS, com slot
// pela posição no mapa do beacon). Este padrão só vale antes do primeiro beacon
// ou para um nó órfão, que cai no slot fixo pelo ID: por isso cobre os
// TOTAL_NOS slots. É a MESMA conta do `CICLO_DE` do receptor — com 99 nós, 53 s,
// o `CICLO_MAX_MS` de lá.
#define CICLO_MS_PADRAO (((GUARDA_MS_PADRAO + (unsigned long)TOTAL_NOS * SLOT_MS_PADRAO \
                          + JANELA_DSC_PADRAO + FOLGA_PRE_CMD_PADRAO + JANELA_CMD_PADRAO) \
                          + 999UL) / 1000UL * 1000UL)

// Uma transmissão só começa se CABE inteira na janela (slot ou descoberta):
// tempo no ar da linha + esta margem. Se o laço atrasou e não cabe mais, o nó
// pula o ciclo — invadir o slot do vizinho derrubaria os dois pacotes.
// 50 ms cobrem o erro de fase em relação ao receptor (~10 ms) com sobra; com a
// linha mais longa (~110 ms) o nó ainda tem 340 ms do slot de 500 para começar.
#define MARGEM_TX_MS 50UL

// Ciclos sem beacon antes de o nó se declarar dessincronizado e passar a
// transmitir com jitter (para não colidir de forma determinística).
#define MAX_HOLDOVER_CICLOS 3
#define JITTER_MAX_MS       400

// Atraso da resposta a um PING ENDEREÇADO. Só um nó responde, então um valor
// fixo e curto basta. O receptor segura o próximo comando por
// ESPERA_RESPOSTA_PING_MS (400 ms) depois de um PING endereçado: cabe este
// atraso + a resposta no ar (~110 ms) com folga. Mudar um sem o outro faz a
// resposta colidir com o comando seguinte. Sem tempo para responder antes do
// fim do ciclo, o nó responde no próprio slot.
//
// PING em BROADCAST não usa isto: espalhar 99 respostas por ID (o que a versão
// de 4 nós fazia) daria quase 12 s de respostas invadindo os slots alheios. Em
// broadcast o nó responde no PRÓPRIO slot, que já é livre de colisão por
// construção — ver `processarComando` em lora_no.cpp.
#define ATRASO_PING_MS 150UL

// ── Irrigação ─────────────────────────────────────────────────────────────────
// Este nó tem UM relé, decidido pela MÉDIA dos dois sensores de solo.
// O canal 2 é monitorado e reportado, mas não tem válvula: IR2 é sempre 0 e
// `CMD:<id>:IRR2` é ignorado — o nó não mente sobre o estado de um relé que
// não existe (PROTOCOLO.md §2.3, nota "omitir é mentir").
#define TEM_RELE2 0

#define LIMITE_UMIDADE_PADRAO 30.0f
#define MAX_IRRIGACAO_MS      (15UL * 60UL * 1000UL)  // 15 min por acionamento
#define COOLDOWN_MS           (2UL * 60UL * 60UL * 1000UL)  // 2 h entre ciclos
#define MARGEM_PREVISAO_MIN   10.0f   // irriga preventivamente a N min do limite

// ── Modelo de secagem (aprendizado contínuo — ver modelo.h) ───────────────────
// A taxa observada é a inclinação de uma reta de mínimos quadrados sobre
// SEGMENTO_MIN médias de 1 minuto. Uma contagem do ADC vale ~0,05 % de umidade:
// com o ruído típico, a reta de 60 min mede a taxa com erro de ~0,0001 %/min,
// enquanto comparar leituras a 30 s não chega a medir uma contagem de secagem.
#define SEGMENTO_MIN           60      // médias de 1 min por reta
#define MIN_SEGMENTOS_MODELO    4      // retas aceitas até a primeira previsão
#define MEMORIA_DIAS            2      // as médias (por faixa e geral) lembram ~2 dias
#define ESPERA_POS_MOLHAR_MIN 120      // drenagem depois de irrigar/chover não é secagem
#define SALTO_MAX_PTS        0.5f      // entre médias de 1 min: acima disso é água ou defeito
#define TAXA_MAX            0.05f      // %/min (72 %/dia): acima disso não é secagem
#define PREVISAO_MAX_MIN 43200.0f      // 30 dias: além disso, "o limiar não chega"
#define FAIXAS_HORA             3
#define HORA_MANHA_INI          6
#define HORA_TARDE_INI         12
#define HORA_NOITE_INI         18

// ── Extras ────────────────────────────────────────────────────────────────────
#define ENVIAR_BATERIA 1   // acrescenta BAT:<volts> (o Pi guarda em `extras`)

// ── Deep sleep (preparado, desligado) ─────────────────────────────────────────
// Ligar exige alinhar o ciclo com o tempo de boot (~300 ms) e acordar ANTES do
// beacon. Com o nó em rede elétrica não há motivo para pagar esse risco agora.
#define USAR_DEEP_SLEEP 0
#define MARGEM_ACORDAR_MS 800   // acorda esse tanto antes do beacon esperado

// ── NVS ───────────────────────────────────────────────────────────────────────
#define NVS_NAMESPACE "no"
