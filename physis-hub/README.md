# Physis Hub 0.30 — Modelo 1 do projeto personalizado

Servico local do Raspberry Pi para a rede V6, com painel web, simulador e teste de
estresse. Feito em 13/11/2026 a partir do Receptor V6 e do Transmissor V6 (revisao de
26/10/2026), da Caixinha, do SmartColar, do AutoFeeder e do sistema integrado.

So usa a biblioteca padrao do Python 3.10 ou mais novo. Nao instala nada.

## O que foi verificado e o que nao foi

| Parte | Situacao |
|---|---|
| `physis_hub/` (protocolo, adaptador, hub, servidor, simulador) | 29 testes automatizados e 10 cenarios de estresse passaram no ambiente de desenvolvimento |
| `web/painel.html` | Aberto num navegador automatizado, com hub e sem hub: 8 telas (incluindo o hub de selecao com todos os sistemas e projetos), comando confirmado, estresse e injecao funcionaram |
| Ligacao com o Receptor V6 real | **Nao testada.** As rotas e formatos foram copiados do firmware (`pi_client.cpp`, `webpages.cpp`), mas nenhum receptor fisico foi ligado |
| Convivencia com o `controle-central` | **Nao verificada.** O `controle-central` nao estava disponivel; este hub usa a mesma porta (8700) e a mesma rota de entrega, entao os dois nao rodam juntos no mesmo Pi sem mudar a porta de um deles |
| `firmware_ref/no_wifi_v6` | **Referencia nao compilada nem testada** |

## Montar a plataforma de um cliente (depois do pagamento)

```
python3 montar.py --org fazenda-boa-vista --modulos monitoramento,sustainkit \
                  --sustainkit /caminho/SustainKit_Definitivo.html --saida entregas
```

Gera `entregas/physis-<org>.zip` so com os modulos comprados, um `instancia.json` e um LEIA-ME
para o cliente. A plataforma sai zerada (sem simulador) e exige cadastro e senha no primeiro
acesso. Modulos aceitos: monitoramento, zonas, animais, sustainkit.

## Loja e gestão no mesmo servidor: nada é copiado à mão

Com `web/gestao.html` presente (montar.py --modulos ...,gestao --gestao gestao-interna-physis.html, a gestão interna da Physis; o `gestao-physis.html` é o módulo vendido ao cliente e não recebe compras nem pedidos):

- `/loja/` é pública: seleção, pagamento e pedido de projeto personalizado, sem login.
- Ao confirmar o pagamento, a loja entrega a compra em `POST /api/central/compra`.
  Pedido de projeto personalizado vai para `POST /api/central/pedido`.
- `/gestao/` (com login) busca `GET /api/central/caixa` a cada 10 s e registra sozinha:
  compra -> contrato de licença, lançamento pago e uso aguardando aprovação; pedido -> proposta nova.
- "Aprovar uso" na gestão chama `POST /api/central/compra/<numero>/aprovar`; a tela da cliente
  consulta `GET /api/central/compra/<numero>` e muda sozinha.

As rotas de entrega são públicas de propósito (quem compra não tem conta). Antes de expor à
internet: HTTPS, limite de envios por endereço e confirmação do pagamento pelo provedor, não pela página.

## Supervisão ligada ao campo

Com o módulo `supervisao` (montar.py --modulos ...,supervisao --supervisao physis-scada-demo.html),
o hub serve a supervisão em `/supervisao/`. Ela lê `/api/painel` a cada 5 s e cria um ativo por
medição real, com tópico `physis/{org}/{grandeza}/{ativo}`: umidade e temperaturas dos nós de solo,
umidade das duas zonas de cada Caixinha e nível de ração dos comedouros. A faixa de alarme de
umidade usa o limite do próprio nó. Nó que para de falar sai da tela. A exportação `medicao`
marca essas linhas com a organização real e `simulado: false`; a planta simulada continua ao lado.
Ainda não entram: bateria, sinal, estado de válvula e coleiras, porque o núcleo não tem essas grandezas.

## Acesso

Com `"login": true` no `instancia.json`, toda rota `/api/*` das telas e o SustainKit exigem
sessao. A primeira conta e criada na primeira abertura e vira administradora; senha de 10
caracteres ou mais, guardada como PBKDF2-SHA256 com sal; 5 erros seguidos bloqueiam por 30 s;
sessao de 30 dias em cookie HttpOnly. As rotas de entrega do receptor e dos dispositivos Wi-Fi
continuam abertas na rede local (token na F0). Sem HTTPS, a senha trafega em claro na rede local:
para acesso pela internet e obrigatorio por um servidor com HTTPS na frente.

## Rodar

```
# 1. Sem hardware: hub + simulador (6 solo, 1 caixinha, 3 coleiras, 1 comedouro)
PHYSIS_SIMULAR=6,1,3,1 python3 -m physis_hub.servidor
#    abrir http://<ip-do-pi>:8700/

# 2. Testes
python3 -m unittest discover -s tests
python3 estresse.py --ciclos 200

# 3. Com o Receptor V6 real
PHYSIS_RX_URL=http://<ip-do-receptor> PHYSIS_ORG=<org> PHYSIS_LUGAR=<lugar> python3 -m physis_hub.servidor
#    No receptor: /config -> host = IP do Pi, porta 8700, envio ativo.
```

Com `PHYSIS_RX_URL` definido, o hub (a) recebe o envio do receptor em
`POST /api/gateway/webhook`, (b) consulta `GET /api/leituras?desde=<cursor>` como segundo
caminho e (c) entrega comandos em `POST /api/comando` do receptor. Leituras repetidas pelos
dois caminhos sao descartadas quando o no manda `TS` valido.

## Rotas

| Rota | Quem chama | Corpo | Resposta |
|---|---|---|---|
| `POST /api/gateway/webhook` | Receptor V6 (`PI_ROTA_WEBHOOK`) | `text/plain`, uma linha V6 por linha | `200 {"ok":true,"aceitas":n,"duplicadas":n,"descartadas":n}` |
| `POST /api/v6/linha` | Dispositivo Wi-Fi via ESP | igual | igual, mais `"comandos":["CMD:.."]` pendentes do no |
| `POST /api/comando` | Painel | `{"comando":"CMD:03:LIM1:35"}` ou a linha crua | `200` com `estado`, ou `400` se fora do contrato |
| `GET /api/painel` | Painel | — | dispositivos, alertas, comandos, registro, saude |
| `GET /api/serie?ativo=&grandeza=` | Painel | — | ultimas medicoes physis/1 do ativo |
| `GET /api/saude` | Suporte | — | contadores, descartes por motivo, integridade do registro |

Corpo acima de 64 kB devolve 413. Com `PHYSIS_TOKEN` definido, `POST /api/comando` exige o
cabecalho `X-Physis-Token`. A rota de entrega do receptor fica aberta porque o firmware atual
nao envia token; isso se resolve na F0.

## Estados de um comando

`pendente` (aguarda a entrega) -> `enviado` -> `confirmado` (a leitura seguinte do no traz o
valor pedido) ou `nao_confirmado` (3 leituras sem o valor). `SYNC`, `MODO` e `PING` terminam em
`sem_confirmacao`, porque a telemetria nao os reflete. `falhou` = receptor inacessivel.

## Banco (SQLite, um arquivo por lugar)

- `leitura(seq, no, ts, recebido, origem, linha)` — indice unico `(no, ts)` quando `ts > 0`.
- `medicao(seq, leitura, topico, grandeza, ativo, valor, ts, alarme)` — physis/1.
- `registro(seq, id, tipo, quando, origem, conteudo, anterior, resumo)` — cadeia SHA-256.
- `comando(seq, linha, destino, estado, criado, atualizado, restam, detalhe)`.
- `envio(seq, registro, enviado)` — fila para o servidor Physis (o envio em si fica para a programacao).

## Diferencas conhecidas em relacao ao firmware

- `LIM1`/`LIM2`: o hub recusa `0x10`, que o `strtof` do firmware leria como 16. O hub e mais
  estrito; nunca envia ao receptor algo que o receptor recuse.
- Numeros de telemetria: texto que nao e numero vira "sem leitura" no hub; no firmware,
  `toFloat()` devolveria 0. O hub nao inventa zero.

## Arquivos

```
physis_hub/protocolo.py   linha V6: campos, telemetria, comandos
physis_hub/nucleo.py      recorte do contrato physis/1 e grandezas novas
physis_hub/adaptador.py   linha V6 -> medicoes physis/1, por TIPO
physis_hub/hub.py         banco, registro encadeado, comandos, alertas
physis_hub/servidor.py    rotas HTTP, cliente do receptor, laco do simulador
physis_hub/simulador.py   dispositivos simulados e linhas defeituosas
estresse.py               10 cenarios de estresse (gera relatorio_estresse.json)
tests/test_protocolo.py   22 testes
tests/test_acesso.py      7 testes de cadastro, senha e rotas protegidas
montar.py                 monta a plataforma de um cliente por modulos
web/painel.html           interface (com hub ou com simulador embutido)
docs/EXTENSAO_V6.md       TIPO ZONA, COL e COM
docs/PROTOCOLO.md         protocolo V6 reconstruido a partir do firmware
firmware_ref/no_wifi_v6/  referencia de no Wi-Fi para a Caixinha (nao testada)
```
