#pragma once
#include <Arduino.h>

// ══════════════════════════════════════════════════════════════════════════════
//  Camada de rádio do gateway: mestre TDMA + roteador de comandos.
//
//  Exemplo com 3 nós descobertos (IDs 02, 07, 15) → ciclo de 5 s:
//    t=0    0,6s    1,1s    1,6s    2,1s          3,1s  3,3s        5s
//    ├BEACON┤guarda├─Nó 02─├─Nó 07─├─Nó 15─├─DESCOBERTA─┤folga├…─CMDs─┤
//
//  O receptor abre o ciclo com um beacon que carrega o relógio, a previsão de
//  chuva e o próprio cronograma; cada nó calcula o slot dele a partir daí. No
//  fim do ciclo abre-se a janela de downlink, quando os nós estão ouvindo e
//  nenhum transmite — é ali que os comandos do Raspberry Pi vão para o ar.
//
//  O TDMA roda numa TAREFA PRÓPRIA, acima do loop do Arduino: o loop trava
//  segundos em HTTP/HTTPS/cartão, e com o rádio dentro dele cada trava atrasava
//  o beacon e perdia pacotes. O loop só consome o que a tarefa recebeu
//  (`loraLoop`) e entrega comandos a ela (`enfileirarComando`).
// ══════════════════════════════════════════════════════════════════════════════

/// Liga o rádio e sobe a tarefa do TDMA. Chamar no `setup()`.
void loraSetup();

/// Trata as linhas que a tarefa do rádio recebeu. Chamar no `loop()`.
void loraLoop();

/// Para a tarefa do rádio (antes do deep sleep, que mexe no rádio).
void loraParar();

/// Injeção de uma linha de telemetria por HTTP (`POST /api/data`), para
/// bancada: identifica o nó pelo `ID:`, atualiza o estado e empurra para a fila
/// do controle central, como uma linha vinda do ar. `rssi`/`snr` iguais a 0
/// significam "não medido".
void processarPacket(float rssi, float snr, String payload);

/// Enfileira `CMD:<nn>:<AÇÃO>[:<ARG>]` para a próxima janela de downlink.
/// Devolve `false` se a linha não passar na validação do contrato (inclusive o
/// argumento) ou se a fila estiver cheia.
bool enfileirarComando(const String& linhaCmd);

/// Açúcar para os botões do painel local — monta a linha e enfileira.
bool enfileirarAcao(int destino, const String& acao, const String& arg = "");

/// Duração do ciclo corrente (variável: 1 s a cada dois nós descobertos) e
/// quantos slots ele abre — um por nó descoberto.
unsigned long cicloMs();
unsigned long slotsCiclo();

int      comandosPendentes();
uint32_t cicloAtual();
uint32_t beaconsEnviados();

/// Ciclos em que o nó `id` (1-based), já ouvido antes, ficou mudo no próprio slot.
uint32_t ciclosPerdidosNo(int id);

/// Linhas recebidas e jogadas fora porque o loop demorou a buscar e a fila da
/// tarefa do rádio encheu. Deve ficar em zero.
uint32_t linhasRxDescartadas();

/// Nós que já falaram alguma vez (bitmap na NVS). `carregar` roda no loraSetup;
/// `esquecer` tira da lista os que estão offline agora.
void carregarNosConhecidos();
void esquecerNosConhecidos();

/// Marca offline, individualmente, os nós que perderam o slot por tempo demais.
void verificarOnline();
