#include "fila.h"

struct ItemFila {
  uint32_t seq;
  char     linha[FILA_LINHA_MAX];
};

static ItemFila _fila[FILA_TAM];
static int      _prox        = 0;  // próxima posição a escrever (a mais antiga)
static uint32_t _ultimoSeq   = 0;
static uint32_t _enviadoAte  = 0;

void filaAdicionar(const String& linha) {
  _ultimoSeq++;
  _fila[_prox].seq = _ultimoSeq;
  strncpy(_fila[_prox].linha, linha.c_str(), FILA_LINHA_MAX - 1);
  _fila[_prox].linha[FILA_LINHA_MAX - 1] = '\0';
  _prox = (_prox + 1) % FILA_TAM;
}

uint32_t filaUltimoSeq() { return _ultimoSeq; }

int filaDesde(uint32_t desde, String* saida, int max, uint32_t& ultimo) {
  ultimo = desde;
  int n = 0;
  // `_prox` aponta para a posição mais antiga: percorrer a partir dele devolve
  // as linhas em ordem de sequência, sem precisar ordenar.
  for (int i = 0; i < FILA_TAM && n < max; i++) {
    const ItemFila& item = _fila[(_prox + i) % FILA_TAM];
    if (item.seq == 0 || item.seq <= desde) continue;
    saida[n++] = String(item.linha);
    ultimo     = item.seq;
  }
  return n;
}

void filaPercorrer(uint32_t desde, uint32_t& ultimo,
                   bool (*cb)(const char* linha, uint32_t seq, void* ctx),
                   void* ctx) {
  ultimo = desde;
  for (int i = 0; i < FILA_TAM; i++) {
    const ItemFila& item = _fila[(_prox + i) % FILA_TAM];
    if (item.seq == 0 || item.seq <= desde) continue;
    if (!cb(item.linha, item.seq, ctx)) return;
    ultimo = item.seq;
  }
}

int filaPendentesPi(String* saida, int max, uint32_t& ate) {
  return filaDesde(_enviadoAte, saida, max, ate);
}

void filaMarcarEnviado(uint32_t ate) {
  if (ate > _enviadoAte) _enviadoAte = ate;
}

uint32_t filaPendentesPiTotal() {
  return (_ultimoSeq > _enviadoAte) ? (_ultimoSeq - _enviadoAte) : 0;
}

uint32_t filaEnviadoAte() { return _enviadoAte; }
