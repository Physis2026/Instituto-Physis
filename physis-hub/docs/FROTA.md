# Frota e combustível

Versão 0.1, de 18/11/2026. **Em desenvolvimento**: a aba aparece com o selo "Em desenvolvimento" na instalação de pesquisa
(Casa Physis), fica fora da loja pública (só na loja interna, item `frota`) e nada foi testado em veículo ainda.

## O que faz

Uma aba da plataforma para caminhões, carros, tratores e máquinas:

- **Mapa:** a última posição de cada veículo e a rota do dia escolhido. O mapa é desenhado na própria tela (sem
  biblioteca nem fundo de terceiros, como o mapa da Economia circular); a mesma informação está numa tabela logo abaixo.
  Sem ligação com o computador central, a tela mostra os pontos guardados no aparelho.
- **Abastecimentos:** data, litros, preço (só com a fonte: nota, cartão, bomba ou estimado), odômetro ou horímetro e o
  comprovante opcional (PDF ou foto, até 10 MB, guardado com o resumo SHA-256; só a equipe vê).
- **Consumo:** distância (fórmula de haversine, ou o odômetro), litros pela vazão, horas de motor, marcha lenta, consumo
  por km (L/100 km) e por hora (L/h), por veículo, por dia e por mês, e o CO₂e pela mesma conta do Carbono.
- **Alertas:** consumo acima do normal aprendido do veículo (z robusto com mediana e MAD, média móvel exponencial, com o
  tamanho da amostra), nível do tanque caindo com o veículo parado (vazamento ou furto possível), marcha lenta longa e
  saída de uma cerca desenhada no mapa. Os limites são premissas `frota.*` com status "conferir".
- **Cercas:** polígono desenhado com clique no mapa, com as setas do teclado (mira + Enter) ou digitando as coordenadas.
- **Ligações:** os litros medidos (abastecimentos do ano, ou a vazão para veículo sem abastecimento) substituem o valor
  digitado da "Combustão móvel (frota própria)" no Carbono, com a fonte escrita; o digitado fica de reserva (uma caixa
  volta a ele). O custo dos abastecimentos aparece na Gestão (Indicadores → Financeiro). A frota simulada nunca entra.

Onde está: `physis_hub/frota.py` (servidor), `sistema/physis-frota.js` (tela, espelho das contas), testes em
`tests/test_frota.py`. Rotas: `GET /api/frota/estado`, `GET /api/frota/rota?veiculo=&dia=`, `GET /api/frota/exportar`,
`POST /api/frota/veiculo | abastecimento | cerca | importar | comprovante | config` (cliente lê; equipe grava; apagar
veículo e mudar a retenção, só a direção).

## LGPD

A posição de um veículo mostra onde a pessoa que dirige está: é dado pessoal. Por isso:

- a tela mostra um aviso para avisar quem dirige e usar os dados só para a gestão da frota;
- o motorista é só um **código opcional** (nada de nome, CPF ou telefone);
- a exportação e a tela do cliente saem **sem** o código do motorista; só a direção pede com ele;
- os pontos de GPS são apagados depois da retenção (premissa `frota.retencao_dias`, 365 dias; a direção muda na aba).

## Opções de equipamento

Nada aqui é especificação de compra: modelo, faixa e precisão de cada aparelho vêm da folha de dados dele **[CONFERIR]**.

| Opção | O que mede | Como chega | Observação |
|---|---|---|---|
| Rastreador GPS (veicular, com chip de dados ou LoRa) | posição, velocidade, rumo, ignição; alguns têm entrada para sensor de nível | linha V6 `TIPO:VEI` por um ESP32/gateway (MQTT ou Wi-Fi), ou o CSV exportado da plataforma do rastreador | o protocolo de cada fabricante é diferente: precisa de um tradutor para a linha V6 [CONFERIR] |
| Medidor de vazão de combustível (fluxômetro) | litros por hora | entrada de pulso num ESP32 → `FLX` | diesel com retorno pede medição diferencial (ida − volta) [CONFERIR] |
| Leitor OBD-II (carros e caminhões leves) ou CAN/J1939 (caminhões, tratores) | velocidade, rotação, às vezes vazão, nível e horímetro | gateway → MQTT (`"tipo": "veiculo"`, objeto `json`) | cada veículo informa coisas diferentes pela rede; conferir o que o modelo entrega [CONFERIR] |
| Sensor de nível no tanque (boia, capacitivo ou ultrassônico) | % do tanque | ESP32 → `NIV` | a resolução define o menor vazamento que dá para ver (premissa `frota.queda_nivel_pct`) |
| CSV do cartão-combustível | abastecimentos (data, litros, preço, odômetro) | importação na aba (tudo ou nada, resumo SHA-256) | renomear as colunas para `data;litros;preco_l;odometro;horimetro;motorista` |

Caminho dos dados (o mesmo dos outros aparelhos): aparelho → linha V6 `TIPO:VEI` (`EXTENSAO_V6.md`) → `POST /api/v6/linha`
ou ponte MQTT (`MQTT.md`) → hub (`medicao` e `frota_ponto`). Para testar sem aparelho: `ferramentas/simulador_dispositivos.py`
(nós 87 a 89, tudo marcado SIMULADO; ver `TESTE_COM_SIMULADOR.md`).

## Fase 2 (não feito)

- Integração com um rastreador de verdade em campo (escolha do aparelho, tradutor do protocolo do fabricante, teste na
  Casa Physis) e os limites dos alertas conferidos com os dados reais.
- API do cartão-combustível (hoje só o CSV exportado), sem depender dela para funcionar.
- App do motorista (registrar abastecimento com foto, checklist), com o mesmo cuidado de LGPD.
- Fundo de mapa da região (MapLibre e PMTiles servidos pelo próprio servidor, como na Economia circular), opcional.

## Licenças

Nada de terceiros foi acrescentado: o mapa, os gráficos, as contas e a ponte MQTT são código próprio da Physis, só com a
biblioteca padrão do Python e o JavaScript do navegador. Métodos citados (sem cópia de texto): fórmula de haversine;
z modificado de Iglewicz e Hoaglin (1993); GHG Protocol e IPCC 2006 (volume 2, capítulo 3) pelos fatores já na base do
Carbono; Lei 13.709/2018 (LGPD).
