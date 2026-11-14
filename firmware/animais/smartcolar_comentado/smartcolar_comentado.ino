/*
 * ==================================================================
 *  SMARTCOLAR - firmware da coleira (MVP)
 *  Physis Engineering
 * ==================================================================
 *
 *  oq é
 *  coleira pra gado q mostra onde cada animal tá e avisa se acontecer
 *  alguma coisa: saiu da cerca, levou uma pancada/caiu, ficou parado
 *  tempo demais. sem chip de operadora e sem mensalidade, a
 *  comunicação é por LoRa, q é um rádio de longo alcance (até uns 10 km)
 *
 *  pq
 *  hj pra identificar animal tem q mandar gente no meio do rebanho com
 *  o bastão de RFID (q só lê a menos de 1 metro). e as coleiras
 *  importadas custam de R$ 400 a 1.500 cada + mensalidade, ninguém
 *  consegue colocar no rebanho inteiro
 *
 *  a ideia principal do projeto
 *  a coleira só MEDE e MANDA. quem decide tudo é o gateway (raspberry pi)
 *  cerca virtual, queda, comportamento normal de cada animal... tudo lá.
 *  assim se precisar mudar alguma regra mexe só no gateway, n precisa
 *  ir no pasto pegar coleira por coleira
 *
 *  como funciona
 *    - fica lendo o GPS e o acelerômetro o tempo todo
 *    - de minuto em minuto monta um resuminho (posição, bateria,
 *      quanto o animal se mexeu) e manda por LoRa
 *    - se levar uma pancada forte manda na hora, sem esperar o minuto
 *    - do outro lado tem um receptor ligado no gateway q recebe tudo
 *
 *  hardware (versão de teste, antes de fazer a placa própria)
 *    TTGO T-Beam v1.1   ESP32 + GPS + LoRa + suporte de bateria 18650,
 *                       tudo numa placa só
 *    MPU-6050 (GY-521)  acelerômetro, ligado em SDA 21 / SCL 22
 *    painel solar 5 V   pra carregar a bateria
 *
 *  libs (gerenciar bibliotecas no arduino IDE)
 *    LoRa (Sandeep Mistry), TinyGPSPlus, AXP202X_Library
 *
 *  IMPORTANTE: nunca ligar a placa sem a antena do LoRa conectada,
 *  pode queimar o rádio
 */

#include <Wire.h>
#include <SPI.h>
#include <LoRa.h>
#include <TinyGPSPlus.h>
#include <axp20x.h>

// ------------------------------------------------------------------
// config, o q dá pra mexer
// ------------------------------------------------------------------
#define COLEIRA_ID       1          // cada coleira tem q ter um número diferente
#define INTERVALO_MS     60000UL    // 1 min pra teste. no campo vai ser 10 min (144 envios/dia)
#define LIMIAR_IMPACTO_G 2.5        // pancada acima disso manda na hora (ajustar no campo vendo os dados reais)
#define LORA_FREQ        915.2E6    // 915,2 MHz pra ficar dentro da faixa liberada pela anatel
#define LORA_SF          7          // quanto maior, mais longe vai mas gasta mais bateria

// pinos do T-Beam v1.1 (n mexer, é fixo da placa)
#define LORA_SCK   5
#define LORA_MISO  19
#define LORA_MOSI  27
#define LORA_SS    18
#define LORA_RST   23
#define LORA_DIO0  26
#define GPS_RX     34
#define GPS_TX     12
#define I2C_SDA    21
#define I2C_SCL    22

#define MPU_ADDR   0x68             // endereço do acelerômetro

// ------------------------------------------------------------------
// variáveis
// ------------------------------------------------------------------
AXP20X_Class   axp;                 // chip q controla a energia da placa
TinyGPSPlus    gps;
HardwareSerial gpsSerial(1);

uint16_t      seq = 0;              // número de cada envio, o gateway usa pra ver se perdeu algum
unsigned long ultimoEnvio = 0;
unsigned long ultimoImpacto = 0;

// resumo do acelerômetro entre um envio e outro
float somaAtividade = 0;
float picoG = 0;
int   amostras = 0;

// ------------------------------------------------------------------
// ligando as coisas
// ------------------------------------------------------------------
void iniciarEnergia() {
  // pegadinha do T-Beam: o LoRa e o GPS só ligam se o chip de energia
  // (AXP192) mandar. se esquecer disso nada funciona e n dá erro nenhum
  axp.begin(Wire, AXP192_SLAVE_ADDRESS);
  axp.setPowerOutPut(AXP192_LDO2, AXP202_ON);   // liga o LoRa
  axp.setPowerOutPut(AXP192_LDO3, AXP202_ON);   // liga o GPS
  axp.adc1Enable(AXP202_BATT_VOL_ADC1, true);   // deixa ler a bateria
}

void iniciarGPS() {
  gpsSerial.begin(9600, SERIAL_8N1, GPS_RX, GPS_TX);
}

bool iniciarAcelerometro() {
  // o MPU-6050 começa dormindo, tem q acordar ele
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x6B);
  Wire.write(0x00);
  if (Wire.endTransmission() != 0) return false;   // n respondeu = n tá ligado

  // escala de ±8 g, dá conta de pancada forte sem estourar a leitura
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x1C);
  Wire.write(0x10);
  Wire.endTransmission();
  return true;
}

bool iniciarLoRa() {
  SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_SS);
  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
  if (!LoRa.begin(LORA_FREQ)) return false;
  LoRa.setSpreadingFactor(LORA_SF);
  LoRa.setSignalBandwidth(125E3);
  LoRa.enableCrc();                 // descarta pacote q chegou corrompido
  return true;
}

// ------------------------------------------------------------------
// lendo os sensores
// ------------------------------------------------------------------
void lerGPS() {
  // o GPS fica mandando texto direto, essa lib vai montando a posição
  while (gpsSerial.available()) gps.encode(gpsSerial.read());
}

void lerAcelerometro() {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);
  Wire.endTransmission(false);
  Wire.requestFrom(MPU_ADDR, 6);
  if (Wire.available() < 6) return;

  int16_t ax = (Wire.read() << 8) | Wire.read();
  int16_t ay = (Wire.read() << 8) | Wire.read();
  int16_t az = (Wire.read() << 8) | Wire.read();

  // força total em "g". parado dá ~1 g (só a gravidade)
  float g = sqrt((float)ax * ax + (float)ay * ay + (float)az * az) / 4096.0;

  // o quanto passou de 1 g = o quanto o animal tá se mexendo
  somaAtividade += fabs(g - 1.0);
  if (g > picoG) picoG = g;
  amostras++;
}

float lerBateria() {
  return axp.getBattVoltage();      // em mV, cheia ~4200, vazia ~3300
}

// ------------------------------------------------------------------
// montando e mandando
// ------------------------------------------------------------------
String montarPacote() {
  // formato: id,seq,lat,lon,satélites,bateria,atividade,pico
  // ex:      1,42,-15.912345,-47.812345,7,3980,0.052,1.31
  // tá em texto pq é fácil de ler no teste. depois vira binário pra
  // ficar menor e gastar menos bateria no envio
  bool temPosicao = gps.location.isValid() && gps.location.age() < 5000;
  float atividade = amostras > 0 ? somaAtividade / amostras : 0;

  String p = String(COLEIRA_ID) + "," + String(seq) + ",";
  p += temPosicao ? String(gps.location.lat(), 6) : "0";   // 0 = ainda sem sinal de GPS
  p += ",";
  p += temPosicao ? String(gps.location.lng(), 6) : "0";
  p += "," + String(gps.satellites.value());
  p += "," + String((int)lerBateria());
  p += "," + String(atividade, 3);
  p += "," + String(picoG, 2);
  return p;
}

void enviar() {
  String pacote = montarPacote();
  LoRa.beginPacket();
  LoRa.print(pacote);
  LoRa.endPacket();
  Serial.println("enviado: " + pacote);

  seq++;
  somaAtividade = 0;                // zera o resumo pro próximo período
  picoG = 0;
  amostras = 0;
}

// ------------------------------------------------------------------
// programa principal
// ------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  Wire.begin(I2C_SDA, I2C_SCL);

  iniciarEnergia();
  iniciarGPS();
  if (!iniciarAcelerometro()) {
    // segue funcionando só com GPS, mas avisa
    Serial.println("acelerometro n encontrado, confere os fios SDA 21 / SCL 22");
  }

  if (!iniciarLoRa()) {
    Serial.println("LoRa n iniciou, ve a placa e a antena");
    while (true) delay(1000);
  }
  Serial.println("coleira " + String(COLEIRA_ID) + " pronta");
  // obs: o GPS pode levar uns minutos pra pegar sinal na primeira vez,
  // e só pega bem a céu aberto. dentro de casa vai mandar posição 0
}

void loop() {
  lerGPS();

  // lê o acelerômetro ~25x por segundo
  static unsigned long ultimaAmostra = 0;
  if (millis() - ultimaAmostra >= 40) {
    ultimaAmostra = millis();
    lerAcelerometro();
  }

  // pancada forte: manda na hora, sem esperar o ciclo normal
  // (espera 30 s entre um e outro pra n ficar mandando sem parar)
  if (picoG >= LIMIAR_IMPACTO_G && millis() - ultimoImpacto > 30000) {
    ultimoImpacto = millis();
    Serial.println("impacto!");
    enviar();
  }

  // envio normal
  if (millis() - ultimoEnvio >= INTERVALO_MS) {
    ultimoEnvio = millis();
    enviar();
  }
}

/*
 * ==================================================================
 *  o q falta fazer
 * ==================================================================
 *  - confirmação de recebimento: o gateway responde "recebi" e se n
 *    responder a coleira guarda e reenvia depois (sinal cai no mato)
 *  - economia de bateria: desligar o GPS entre leituras e deixar a
 *    placa dormindo entre envios. sem isso n chega nos 28 dias
 *  - acordar com pancada pelo próprio acelerômetro (pino INT), em vez
 *    de ficar lendo ele o tempo todo
 *  - pacote em binário no lugar do texto
 *  - depois de validado, passar pra placa própria (PCB) com ESP32-S3
 *    e GPS NEO-M8N, q é o q tá na lista de materiais
 * ==================================================================
 */
