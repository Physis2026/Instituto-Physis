#include "modelo.h"
#include <Preferences.h>

// Versão do bloco na NVS. Mudou o formato ou a forma de aprender: suba o número
// e o bloco antigo é descartado no boot.
#define VERSAO_MODELO 2u

static const float GANHO_MAX = 0.1f;  // ganho por °C acima de 20 °C (teto herdado do V4)

// ── Faixas horárias ───────────────────────────────────────────────────────────

int faixaHora(int hora) {
  if (hora >= HORA_MANHA_INI && hora < HORA_TARDE_INI) return 0;
  if (hora >= HORA_TARDE_INI && hora < HORA_NOITE_INI) return 1;
  return 2;
}

/// Minuto do dia em que termina a faixa que contém `minutoDia`.
static int fimDaFaixa(int minutoDia) {
  switch (faixaHora(minutoDia / 60)) {
    case 0:  return HORA_TARDE_INI * 60;
    case 1:  return HORA_NOITE_INI * 60;
    default: return HORA_MANHA_INI * 60;
  }
}

/// Peso de uma reta numa média que cobre `minutos` do dia: a média lembra
/// ~MEMORIA_DIAS dias INTEIROS da faixa. Um peso fixo lembraria as últimas
/// horas — numa faixa de 12 h, só o fim dela.
static float pesoMemoria(int minutos) {
  return (float)SEGMENTO_MIN / (float)(MEMORIA_DIAS * minutos);
}

static float pesoFaixa(int f) {
  static const int inicio[FAIXAS_HORA] = {HORA_MANHA_INI * 60, HORA_TARDE_INI * 60, HORA_NOITE_INI * 60};
  return pesoMemoria((fimDaFaixa(inicio[f]) - inicio[f] + 1440) % 1440);
}

// ── Estado derivado ───────────────────────────────────────────────────────────

bool modeloValido(const Modelo& m) { return m.a.retas >= MIN_SEGMENTOS_MODELO; }

/// Ganho da taxa por °C acima de 20 °C (0 enquanto não há retas que o meçam).
static float ganho(const Aprendido& a) {
  if (a.nGanho < 3.0f || a.sxx <= 0.0f) return 0.0f;
  return constrain(a.sxy / a.sxx, 0.0f, GANHO_MAX);
}

/// Razão entre a taxa a `temperatura` e a taxa a 20 °C.
static float fatorTemp(float g, float temperatura) {
  return isnan(temperatura) ? 1.0f : 1.0f + g * max(0.0f, temperatura - 20.0f);
}

/// Média móvel exponencial que começa como média simples: com `n` valores
/// anteriores o peso é 1/(n+1) até cair a `peso`. Sem isso a primeira reta
/// dominaria a média por dias.
static float media(float atual, float nova, uint32_t n, float peso) {
  float w = max(peso, 1.0f / (float)(n + 1));
  return atual + w * (nova - atual);
}

// ── Aprendizado ───────────────────────────────────────────────────────────────

static void reiniciarReta(Segmento& s) {
  s.somaMinuto     = 0.0f;
  s.leiturasMinuto = 0;
  s.minutos        = 0;
  s.st = s.su = s.stt = s.stu = s.suu = 0.0;
  s.somaTemp       = 0.0f;
  s.leiturasTemp   = 0;
}

static void marcarMolhado(Segmento& s, unsigned long agora, const char* sufixo, const char* motivo) {
  if (!s.esperando) {
    Serial.printf("[Aprend%s] Solo molhado (%s): pausa de %d min para a drenagem\n",
                  sufixo, motivo, ESPERA_POS_MOLHAR_MIN);
  }
  s.esperando = true;
  s.molhadoEm = agora;
  reiniciarReta(s);
}

/// Uma reta aceita vira conhecimento: entra na sua faixa e na média geral.
static void aprenderReta(Aprendido& a, float taxa, float temp, int f) {
  // Ganho de temperatura: dentro da MESMA faixa, quanto a taxa sobe por grau
  // acima de 20 °C — mínimos quadrados de (taxa − base) = ganho·base·(T − 20).
  // A base é a da faixa ANTES desta reta, para a reta não se comparar consigo.
  const float pesoGeral = pesoMemoria(1440);
  if (f >= 0 && a.retasFaixa[f] >= 3 && a.taxa[f] > 0.0f && !isnan(temp) && temp > 20.0f) {
    float x = a.taxa[f] * (temp - 20.0f);
    float y = taxa - a.taxa[f];
    a.sxy    = (1.0f - pesoGeral) * a.sxy + x * y;
    a.sxx    = (1.0f - pesoGeral) * a.sxx + x * x;
    a.nGanho = (1.0f - pesoGeral) * a.nGanho + 1.0f;
  }

  float taxa20 = taxa / fatorTemp(ganho(a), temp);
  a.taxaGeral  = media(a.taxaGeral, taxa20, a.retas, pesoGeral);
  a.retas++;
  if (f < 0) return;  // sem relógio não há faixa: só a média geral aprende

  a.taxa[f] = media(a.taxa[f], taxa20, a.retasFaixa[f], pesoFaixa(f));
  if (!isnan(temp)) {
    a.tempFaixa[f] = isnan(a.tempFaixa[f]) ? temp : media(a.tempFaixa[f], temp, a.retasFaixa[f], pesoFaixa(f));
  }
  if (a.retasFaixa[f] < UINT16_MAX) a.retasFaixa[f]++;
}

void observarUmidade(Modelo& m, Segmento& s, float umidade, uint8_t fonte, bool molhando,
                     float temperatura, int minutoDia, unsigned long agora, const char* sufixo) {
  // Relé ligado: a subida é água entrando, e a drenagem que vem depois também
  // não é secagem. A espera conta da última leitura com o relé ligado.
  if (molhando) { marcarMolhado(s, agora, sufixo, "irrigacao"); return; }
  if (s.esperando) {
    if (agora - s.molhadoEm < ESPERA_POS_MOLHAR_MIN * 60000UL) return;
    s.esperando = false;
    Serial.printf("[Aprend%s] Drenagem encerrada: aprendizado retomado\n", sufixo);
  }

  // Uma reta só compara umidades da mesma origem: a média dos dois sensores e
  // um sensor sozinho têm níveis diferentes, e a troca viraria um degrau.
  if (fonte != s.fonte) { s.fonte = fonte; reiniciarReta(s); }
  if (fonte == 0) return;

  if (s.leiturasMinuto == 0) s.inicioMinuto = agora;
  s.somaMinuto += umidade;
  s.leiturasMinuto++;
  if (!isnan(temperatura)) { s.somaTemp += temperatura; s.leiturasTemp++; }
  if (agora - s.inicioMinuto < 60000UL) return;

  // ── Fecha o minuto: um ponto da reta ───────────────────────────────────────
  float         u      = s.somaMinuto / s.leiturasMinuto;
  unsigned long centro = s.inicioMinuto + (agora - s.inicioMinuto) / 2;
  s.somaMinuto     = 0.0f;
  s.leiturasMinuto = 0;

  if (s.minutos > 0) {
    float salto = u - s.uAnterior;
    // Secando, a umidade não sobe meio ponto num minuto: é chuva ou água de fora.
    if (salto > SALTO_MAX_PTS) { marcarMolhado(s, agora, sufixo, "subida brusca"); return; }
    // Nem cai: é defeito ou mexida no sensor. A reta recomeça daqui.
    if (salto < -SALTO_MAX_PTS) reiniciarReta(s);
  }
  if (s.minutos == 0) { s.inicioReta = centro; s.uRef = u; }
  s.uAnterior = u;

  double t = (double)(centro - s.inicioReta) / 60000.0;  // minutos desde o 1º ponto
  double y = (double)(u - s.uRef);                       // centrado: preserva a precisão
  s.st  += t;      s.su  += y;
  s.stt += t * t;  s.stu += t * y;  s.suu += y * y;
  if (++s.minutos < SEGMENTO_MIN) return;

  // ── Fecha a reta ───────────────────────────────────────────────────────────
  const double n    = s.minutos;
  const double vtt  = s.stt - s.st * s.st / n;   // Σ(t − t̄)²
  const double vty  = s.stu - s.st * s.su / n;   // Σ(t − t̄)(u − ū)
  const double vyy  = s.suu - s.su * s.su / n;
  const float  taxa = (float)(-vty / vtt);       // %/min; positiva = secando
  const float  erro = (float)sqrt(max(0.0, (vyy - vty * vty / vtt) / (n - 2.0)) / vtt);
  const float  temp = s.leiturasTemp ? s.somaTemp / s.leiturasTemp : NAN;
  // A faixa é a do MEIO da reta, que é quando ela de fato aconteceu.
  const int    meio = minutoDia < 0 ? -1 : (minutoDia - (int)((agora - s.inicioReta) / 120000UL) + 1440) % 1440;
  const int    f    = meio < 0 ? -1 : faixaHora(meio / 60);
  reiniciarReta(s);

  // Subida sustentada (chuva fina, irrigação de fora) é água entrando.
  if (taxa < -TAXA_MAX) { marcarMolhado(s, agora, sufixo, "subida lenta"); return; }
  if (taxa > TAXA_MAX) {
    Serial.printf("[Aprend%s] Reta descartada: queda de %.4f %%/min nao e secagem\n", sufixo, taxa);
    return;
  }

  aprenderReta(m.a, taxa, temp, f);
  salvarModelo(m, sufixo);
  Serial.printf("[Aprend%s] Faixa %d | Taxa: %.5f +/- %.5f %%/min (%.2f %%/dia) | T %.1f C | "
                "ganho %.3f/C | n=%lu\n",
                sufixo, f, taxa, erro, taxa * 1440.0f, temp, ganho(m.a), (unsigned long)m.a.retas);
}

// ── Previsão ──────────────────────────────────────────────────────────────────

float minutosParaLimite(const Modelo& m, float umidade, int minutoDia, float temperatura) {
  if (!modeloValido(m)) return -1.0f;

  float falta = umidade - m.limiteUmidade;
  if (falta <= 0) return 0.0f;

  const Aprendido& a = m.a;
  const float      g = ganho(a);

  if (minutoDia < 0) {  // sem relógio não há faixa: vale a taxa geral
    float taxa = max(0.0f, a.taxaGeral) * fatorTemp(g, temperatura);
    return (taxa > 0.0f && falta < taxa * PREVISAO_MAX_MIN) ? falta / taxa : PREVISAO_MAX_MIN;
  }

  // Percorre as faixas a partir de agora: a noite seca menos que a tarde, e
  // supor a taxa de agora para sempre erra a previsão de mais de algumas horas.
  float minutos  = 0.0f;
  int   relogio  = minutoDia;
  bool  primeira = true;
  while (minutos < PREVISAO_MAX_MIN) {
    int   f    = faixaHora(relogio / 60);
    int   fim  = fimDaFaixa(relogio);
    int   dur  = (fim - relogio + 1440) % 1440;
    float base = a.retasFaixa[f] ? a.taxa[f] : a.taxaGeral;  // faixa sem reta: a média geral
    float temp = (primeira || isnan(a.tempFaixa[f])) ? temperatura : a.tempFaixa[f];
    float taxa = max(0.0f, base) * fatorTemp(g, temp);
    if (taxa * dur >= falta) return min(minutos + falta / taxa, PREVISAO_MAX_MIN);
    falta   -= taxa * dur;
    minutos += dur;
    relogio  = fim;
    primeira = false;
  }
  return PREVISAO_MAX_MIN;
}

// ── Persistência em NVS ───────────────────────────────────────────────────────
// Um bloco por modelo ("mod1"/"mod2") e o limiar à parte ("lim1"/"lim2"). As
// chaves da NVS têm no máximo 15 caracteres, por isso os nomes curtos.

struct Bloco {
  uint32_t  versao;
  Aprendido a;
};

static String chave(const char* base, const char* sufixo) {
  return String(base) + sufixo;
}

// Chaves do aprendizado por janela de 30 s (V4 → V6 original). Aquelas taxas
// eram quantização do ADC, não secagem: não servem de ponto de partida.
static const char* const CHAVES_ANTIGAS[] = {"t0_", "t1_", "t2_", "ft_", "n_", "ok_"};

void salvarModelo(const Modelo& m, const char* sufixo) {
  Preferences p;
  if (!p.begin(NVS_NAMESPACE, false)) {
    Serial.println("[Modelo] NVS indisponivel — nao salvo");
    return;
  }
  Bloco b = {VERSAO_MODELO, m.a};
  p.putBytes(chave("mod", sufixo).c_str(), &b, sizeof(b));
  p.end();
}

void salvarLimite(const Modelo& m, const char* sufixo) {
  Preferences p;
  if (!p.begin(NVS_NAMESPACE, false)) {
    Serial.println("[Modelo] NVS indisponivel — limiar nao salvo");
    return;
  }
  p.putFloat(chave("lim", sufixo).c_str(), m.limiteUmidade);
  p.end();
}

bool carregarModelo(Modelo& m, const char* sufixo) {
  zerarModelo(m);
  Preferences p;
  if (!p.begin(NVS_NAMESPACE, false)) return false;

  // O limiar é lido sempre: um LIM1 recebido por comando sobrevive ao reboot e
  // à troca do formato do aprendizado.
  m.limiteUmidade = p.getFloat(chave("lim", sufixo).c_str(), LIMITE_UMIDADE_PADRAO);

  for (const char* base : CHAVES_ANTIGAS) {
    String k = chave(base, sufixo);
    if (p.isKey(k.c_str())) p.remove(k.c_str());
  }

  String k  = chave("mod", sufixo);
  Bloco  b;
  bool   ok = p.isKey(k.c_str()) && p.getBytesLength(k.c_str()) == sizeof(b) &&
              p.getBytes(k.c_str(), &b, sizeof(b)) == sizeof(b) && b.versao == VERSAO_MODELO;
  p.end();

  if (ok) {
    m.a = b.a;
    Serial.printf("[Modelo%s] Carregado da NVS — %lu retas, valido: %s, lim %.1f%%\n", sufixo,
                  (unsigned long)m.a.retas, modeloValido(m) ? "sim" : "nao", m.limiteUmidade);
  }
  return ok;
}

void zerarModelo(Modelo& m) {
  m.a = Aprendido{};
  for (int i = 0; i < FAIXAS_HORA; i++) m.a.tempFaixa[i] = NAN;
  m.limiteUmidade = LIMITE_UMIDADE_PADRAO;
}
