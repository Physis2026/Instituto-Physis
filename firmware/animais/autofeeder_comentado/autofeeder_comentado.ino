/*
 * ==================================================================
 *  ANIMAL AUTOFEEDER  -  Firmware do protótipo (Arduino Mega 2560)
 *  Physis Engineering
 * ==================================================================
 *
 *  O QUE É
 *  Um alimentador automático que reconhece cada animal pela tag RFID
 *  presa à coleira e libera ração apenas para os animais cadastrados.
 *  Também libera porções automáticas a cada 8 horas e mostra no
 *  display o nível de ração que ainda resta no reservatório.
 *
 *  O PROBLEMA QUE RESOLVE
 *  Em casas com mais de um animal, o pote é compartilhado: um come a
 *  ração do outro e a dieta prescrita pelo veterinário deixa de
 *  existir na prática. Saber quem está no pote resolve isso.
 *
 *  HARDWARE
 *    Arduino Mega 2560     controlador principal
 *    RFID RC522 (3,3 V)    identifica o animal       SPI: SS 53, RST 49
 *    Servo motor           abre e fecha o dosador    pino 3
 *    Ultrassônico HC-SR04  mede o nível de ração     TRIG 7, ECHO 6
 *    RTC DS3231            relógio com bateria       I2C
 *    LCD 16x2 I2C          interface com o tutor     I2C, endereço 0x27
 *
 *  COMO FUNCIONA (a cada volta do laço principal)
 *    1. Procura uma tag RFID no leitor
 *    2. Se a tag estiver cadastrada, libera uma porção
 *    3. Consulta o relógio: se já passaram 8 h da última porção, libera outra
 *    4. Mede o nível de ração (média das últimas 5 leituras)
 *    5. Atualiza o display, alternando as telas a cada 5 s
 *       (ou mostra o alerta piscante, se a ração estiver acabando)
 *
 *  SITUAÇÃO ATUAL
 *  Protótipo validado em bancada durante 48 h de teste contínuo:
 *  100% de leitura RFID até 3 cm, servo sem travamentos com ração de
 *  diferentes tamanhos e relógio sem desvio perceptível.
 *  A próxima fase (ESP32) está descrita no final deste arquivo.
 *
 *  BIBLIOTECAS: LiquidCrystal_I2C, MFRC522, Servo, RTClib (Adafruit)
 */

#include <LiquidCrystal_I2C.h>
#include <SPI.h>
#include <MFRC522.h>
#include <Servo.h>
#include <RTClib.h>
#include <Wire.h>
#include <EEPROM.h>

// ------------------------------------------------------------------
// Pinos
// ------------------------------------------------------------------
#define SS_PIN    53
#define RST_PIN   49
#define SERVO_PIN 3
#define TRIG_PIN  7
#define ECHO_PIN  6

// ------------------------------------------------------------------
// Parâmetros ajustáveis
// ------------------------------------------------------------------
const unsigned long INTERVALO_ALIMENTACAO_S = 8UL * 3600UL;  // porção automática a cada 8 h
const unsigned long TEMPO_TELA_MS     = 5000;   // tempo de cada tela no display
const unsigned long TEMPO_PISCA_MS    = 500;    // ritmo do alerta piscante
const unsigned int  TEMPO_DOSAGEM_MS  = 2500;   // tempo com o dosador aberto = tamanho da porção
const float ALTURA_RESERVATORIO_CM    = 15.0;   // distância do sensor até o fundo (vazio)
const float LIMIAR_RACAO_BAIXA_CM     = 12.0;   // a partir daqui, alerta de ração acabando
const int   EEPROM_ULTIMA_ALIMENTACAO = 0;      // endereço onde o horário fica salvo

// ------------------------------------------------------------------
// Animais cadastrados
// ------------------------------------------------------------------
// Cada linha é o código (UID) da tag RFID de um animal.
// Para descobrir o UID de uma tag nova: abra o Monitor Serial
// (9600 baud) e aproxime a tag do leitor, o código aparece na tela.
const byte TAGS_AUTORIZADAS[][4] = {
  {0x00, 0x00, 0x00, 0x01},   // Animal 1  (exemplo: substituir pelo UID real)
  {0x00, 0x00, 0x00, 0x02},   // Animal 2  (exemplo: substituir pelo UID real)
};
const int NUM_TAGS = sizeof(TAGS_AUTORIZADAS) / sizeof(TAGS_AUTORIZADAS[0]);

// ------------------------------------------------------------------
// Objetos e estado do sistema
// ------------------------------------------------------------------
LiquidCrystal_I2C lcd(0x27, 16, 2);
MFRC522 rfid(SS_PIN, RST_PIN);
Servo servoRacao;
RTC_DS3231 rtc;

unsigned long contadorRFID = 0;      // quantas vezes os animais usaram o alimentador
unsigned long ultimaTrocaTela = 0;
unsigned long ultimoPisca = 0;
uint32_t ultimaAlimentacao = 0;      // horário da última porção (segundos, via RTC)
int  telaAtual = 0;
bool emAlerta = false;
bool piscaAceso = true;

// Média móvel do sensor ultrassônico (5 amostras)
const int NUM_AMOSTRAS = 5;
float amostras[NUM_AMOSTRAS];
int   indiceAmostra = 0;
int   amostrasValidas = 0;

// ------------------------------------------------------------------
// Barra gráfica do display
// ------------------------------------------------------------------
// O LCD permite criar 8 caracteres personalizados (memória CGRAM).
// Criamos 5 blocos com 1 a 5 colunas preenchidas: assim cada uma das
// 16 posições tem 5 níveis, e a barra ganha 80 passos em vez de 16.
void criarCaracteresBarra() {
  for (int colunas = 1; colunas <= 5; colunas++) {
    byte linha = (0x1F << (5 - colunas)) & 0x1F;
    byte desenho[8];
    for (int i = 0; i < 8; i++) desenho[i] = linha;
    lcd.createChar(colunas - 1, desenho);
  }
}

void desenharBarra(int porcentagem) {
  int total = map(porcentagem, 0, 100, 0, 80);
  lcd.setCursor(0, 1);
  for (int i = 0; i < 16; i++) {
    int preenchido = constrain(total - i * 5, 0, 5);
    if (preenchido == 0) lcd.print(" ");
    else lcd.write(byte(preenchido - 1));
  }
}

// ------------------------------------------------------------------
// Identificação do animal
// ------------------------------------------------------------------
bool tagAutorizada() {
  if (rfid.uid.size != 4) return false;   // as tags usadas têm UID de 4 bytes
  for (int t = 0; t < NUM_TAGS; t++) {
    bool igual = true;
    for (int b = 0; b < 4; b++) {
      if (rfid.uid.uidByte[b] != TAGS_AUTORIZADAS[t][b]) igual = false;
    }
    if (igual) return true;
  }
  return false;
}

void imprimirUID() {
  Serial.print("Tag lida: {");
  for (byte i = 0; i < rfid.uid.size; i++) {
    Serial.print("0x");
    if (rfid.uid.uidByte[i] < 0x10) Serial.print("0");
    Serial.print(rfid.uid.uidByte[i], HEX);
    if (i < rfid.uid.size - 1) Serial.print(", ");
  }
  Serial.println("}");
}

// ------------------------------------------------------------------
// Dosagem
// ------------------------------------------------------------------
// O horário da última porção é guardado na EEPROM (memória que não
// apaga sem energia). Se faltar luz, o alimentador volta sabendo
// quando foi a última refeição e não repete nem pula uma porção.
void salvarUltimaAlimentacao() {
  EEPROM.put(EEPROM_ULTIMA_ALIMENTACAO, ultimaAlimentacao);
}

void liberarRacao() {
  servoRacao.write(180);           // abre o dosador
  delay(TEMPO_DOSAGEM_MS);
  servoRacao.write(90);            // fecha
  ultimaAlimentacao = rtc.now().unixtime();
  salvarUltimaAlimentacao();
}

// ------------------------------------------------------------------
// Nível de ração
// ------------------------------------------------------------------
// O sensor mede a distância até a superfície da ração:
// quanto maior a distância, menos ração no reservatório.
// d = (tempo de ida e volta do som x velocidade do som) / 2
float lerDistancia() {
  digitalWrite(TRIG_PIN, LOW);  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  long duracao = pulseIn(ECHO_PIN, HIGH, 30000);
  if (duracao == 0) return -1;     // sem eco: leitura inválida (sensor solto ou com defeito)
  float distancia = duracao * 0.0343 / 2.0;
  if (distancia > ALTURA_RESERVATORIO_CM) distancia = ALTURA_RESERVATORIO_CM;
  return distancia;
}

// Média das últimas 5 leituras: elimina a oscilação de cerca de
// 0,3 cm observada nos testes e deixa a barra do display estável.
// Leituras inválidas são descartadas. Se o sensor parar de responder,
// o sistema considera o reservatório vazio e mostra o alerta: é mais
// seguro avisar o tutor do que mostrar "cheio" sem saber.
float lerDistanciaMedia() {
  float leitura = lerDistancia();
  if (leitura >= 0) {
    amostras[indiceAmostra] = leitura;
    indiceAmostra = (indiceAmostra + 1) % NUM_AMOSTRAS;
    if (amostrasValidas < NUM_AMOSTRAS) amostrasValidas++;
  }
  if (amostrasValidas == 0) return ALTURA_RESERVATORIO_CM;

  float soma = 0;
  for (int i = 0; i < amostrasValidas; i++) soma += amostras[i];
  return soma / amostrasValidas;
}

// ------------------------------------------------------------------
// Telas do display
// ------------------------------------------------------------------
void mostrarMensagem(const char *linha1, const char *linha2) {
  lcd.clear();
  lcd.setCursor(0, 0); lcd.print(linha1);
  lcd.setCursor(0, 1); lcd.print(linha2);
}

void telaRelogio(DateTime agora) {
  char linha1[17], linha2[17];
  sprintf(linha1, "%02d:%02d:%02d", agora.hour(), agora.minute(), agora.second());
  sprintf(linha2, "%02d/%02d/%04d", agora.day(), agora.month(), agora.year());
  lcd.setCursor(0, 0); lcd.print(linha1);
  lcd.setCursor(0, 1); lcd.print(linha2);
}

void telaNivel(int porcentagem) {
  lcd.setCursor(0, 0);
  lcd.print("Racao: "); lcd.print(porcentagem); lcd.print("%  ");
  desenharBarra(porcentagem);
}

void telaContador() {
  lcd.setCursor(0, 0); lcd.print("Pet utilizou:");
  lcd.setCursor(0, 1); lcd.print(contadorRFID); lcd.print(" vezes");
}

// Alerta de ração baixa: interrompe as telas normais e pisca
// a mensagem até o reservatório ser reabastecido.
void telaAlerta() {
  if (millis() - ultimoPisca < TEMPO_PISCA_MS) return;
  ultimoPisca = millis();
  piscaAceso = !piscaAceso;
  if (piscaAceso) mostrarMensagem("Racao esta", "acabando!");
  else lcd.clear();
}

// ------------------------------------------------------------------
// Inicialização
// ------------------------------------------------------------------
void setup() {
  Serial.begin(9600);
  lcd.init(); lcd.backlight();
  criarCaracteresBarra();
  SPI.begin(); rfid.PCD_Init();

  if (!rtc.begin()) {
    mostrarMensagem("Erro RTC", "Verifique I2C");
    while (1);
  }
  // Se a bateria do relógio acabou, acerta com o horário da compilação
  if (rtc.lostPower()) rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));

  // Recupera o horário da última porção salvo antes de desligar
  EEPROM.get(EEPROM_ULTIMA_ALIMENTACAO, ultimaAlimentacao);
  uint32_t agora = rtc.now().unixtime();
  if (ultimaAlimentacao == 0xFFFFFFFF || ultimaAlimentacao > agora) {
    ultimaAlimentacao = agora;     // primeira vez ligado: começa a contar agora
    salvarUltimaAlimentacao();
  }

  servoRacao.attach(SERVO_PIN);
  servoRacao.write(90);            // dosador fechado
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  mostrarMensagem("Pet Feeder", "Iniciando");
  delay(2000); lcd.clear();
}

// ------------------------------------------------------------------
// Laço principal
// ------------------------------------------------------------------
void loop() {
  // 1 e 2. Animal no pote: libera ração só se a tag estiver cadastrada
  if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    imprimirUID();
    if (tagAutorizada()) {
      contadorRFID++;
      mostrarMensagem("RFID OK", "Liberando");
      liberarRacao();
    } else {
      mostrarMensagem("Tag nao", "cadastrada");
    }
    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
    delay(1000); lcd.clear();
  }

  // 3. Porção automática: consulta o relógio (RTC), não o millis(),
  //    para continuar correto mesmo depois de uma queda de energia
  DateTime agora = rtc.now();
  uint32_t segundos = agora.unixtime();
  if (segundos < ultimaAlimentacao) ultimaAlimentacao = segundos;   // relógio foi reajustado
  if (segundos - ultimaAlimentacao >= INTERVALO_ALIMENTACAO_S) {
    mostrarMensagem("Horario", "Liberando");
    liberarRacao();
    delay(1000); lcd.clear();
  }

  // 4. Nível de ração
  float distancia = lerDistanciaMedia();
  int porcentagem = map((int)(distancia * 10), 0, (int)(ALTURA_RESERVATORIO_CM * 10), 100, 0);
  bool racaoBaixa = distancia >= LIMIAR_RACAO_BAIXA_CM;

  // 5. Display
  if (racaoBaixa) {
    if (!emAlerta) { emAlerta = true; lcd.clear(); }
    telaAlerta();
  } else {
    if (emAlerta) { emAlerta = false; lcd.clear(); ultimaTrocaTela = millis(); }

    if (millis() - ultimaTrocaTela >= TEMPO_TELA_MS) {
      ultimaTrocaTela = millis();
      telaAtual = (telaAtual + 1) % 3;
      lcd.clear();
    }
    if (telaAtual == 0)      telaRelogio(agora);
    else if (telaAtual == 1) telaNivel(porcentagem);
    else                     telaContador();
  }

  delay(100);
}

/*
 * ==================================================================
 *  PRÓXIMOS PASSOS (versão ESP32)
 * ==================================================================
 *  - Trocar o Arduino Mega por ESP32: traz Wi-Fi e Bluetooth.
 *  - Motor de passo (Nema 17 + A4988) no lugar do servo, para porções
 *    mais precisas, e célula de carga (HX711) para pesar o que foi
 *    servido e o que foi consumido.
 *  - Avisos no celular pelo Telegram (ração acabando, porção servida).
 *  - Perfil por animal: tamanho de porção e limite diário diferentes
 *    para cada tag. Hoje uma tag cadastrada libera ração toda vez que
 *    o animal se aproxima, sem limite de porções por dia.
 *  - Integração com a coleira GPS/BLE, que passa a identificar o
 *    animal no pote no lugar da tag RFID.
 * ==================================================================
 */
