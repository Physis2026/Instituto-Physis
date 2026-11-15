# Perfil BLE da Saúde (caixinha de remédios e pulseira) — proposta

Versão 0.1 · 15/11/2026 · **proposta, a homologar** junto com as linhas MED/PUL (`physis-hub/docs/SAUDE.md`).
Pilha: ESP32 com **NimBLE** (Arduino `NimBLE-Arduino` ou ESP-IDF `nimble`). Do lado do celular: `sistema/physis-ble.js`
(app nativo com `@capacitor-community/bluetooth-le` ou Web Bluetooth no Chrome). As UUIDs abaixo são fixas: o teste
`physis-hub/tests/test_app_nativo.py` confere que são as mesmas do `physis-ble.js`.

## 1. Ideia, em uma frase

O aparelho fala **a mesma linha V6** que já mandaria por Wi-Fi ou LoRa (`ID:31,TIPO:MED,CMP:1,EVT:TOMADO,BAT:3.91,TS:…`),
só que por Bluetooth até o celular; o celular guarda (cifrado) e entrega ao hub em `POST /api/saude/linha`.
Nenhuma conta nova: o hub trata a linha exatamente como trataria vinda do receptor.

## 2. Serviços e características

| Nome | UUID | Propriedades | Segurança |
|---|---|---|---|
| Serviço Saúde — caixinha (MED) | `461d76e3-6508-4db6-9886-05374c5fbb50` | primário, anunciado | — |
| Serviço Saúde — pulseira (PUL) | `e970dc7d-400e-4b4e-924c-948d2198e81b` | primário, anunciado | — |
| Linha V6 (nos dois serviços) | `bbca3cf4-40e0-4103-9420-7c1f5f693fd4` | notify | leitura/CCCD só cifrado + autenticado (MITM) |
| Comando (nos dois serviços) | `529cbb10-062f-4ca8-aa64-cca0c1307234` | write (com resposta) | escrita só cifrada + autenticada (MITM) |
| Battery Service | `0x180F` (`0000180f-0000-1000-8000-00805f9b34fb`) | — | padrão |
| Battery Level | `0x2A19` | read, notify | aberto (só a porcentagem) |
| Device Information | `0x180A` | — | padrão |
| Manufacturer Name `0x2A29` / Model Number `0x2A24` / Firmware Revision `0x2A26` | | read | aberto; **sem número de série nem nome de pessoa** |

Nome anunciado: `Physis-MED-xxxx` ou `Physis-PUL-xxxx` (xxxx = 4 últimos dígitos hex do MAC, só para distinguir
dois aparelhos na mesma sala). **Nunca** o nome da pessoa nem o remédio no anúncio (qualquer celular por perto lê).

### 2.1 Linha V6 (notify)

- Conteúdo: a linha V6 em ASCII, terminada em `\n`. Até 240 bytes (`protocolo.LINHA_MAX`).
- Pedaços: cada notificação leva **no máximo 240 bytes** e no máximo `MTU − 3`. O firmware pede MTU 247
  (`NimBLEDevice::setMTU(247)`); se o celular negociar menos (mínimo 23 → 20 bytes), manda mais pedaços.
  O celular junta os pedaços até o `\n` (buffer de 1024; passou disso, descarta).
- Uma linha **por evento** (MED: tomou, atrasou, esqueceu) e, na pulseira, uma linha por período de envio
  (seção 4) e uma linha **na hora** quando `CRISE` vira 1.
- Fila no aparelho: sem celular conectado, guarda as linhas (MED: até `[MARCADOR]` eventos na flash/NVS; PUL: só
  a última normal e todas as de crise das últimas 24 h) e despeja ao conectar, em ordem, com o `TS` original.
- Sem relógio acertado, o aparelho manda `TS:-` e o celular põe a hora dele (`physis-ble.js`). Assim que conecta,
  o celular manda `SYNC`.

### 2.2 Comando (write)

Mesmo formato do V6 (`PROTOCOLO.md`, seção 4): `CMD:<nn>:<AÇÃO>[:<ARG>]` + `\n` opcional, ASCII, ≤ 64 bytes.
`nn` = ID do aparelho, ou `00` = "este aparelho" (o celular ainda não sabe o ID antes da primeira linha).

| Ação | Argumento | Aparelho | Efeito |
|---|---|---|---|
| `SYNC` | epoch 1700000000–4102444800 | os dois | acerta o relógio (o celular manda ao conectar) |
| `PING` | — | os dois | responde com uma linha normal na característica Linha |
| `HOR` | `<cmp>/<HHMM>/<dias>` ex. `1/0800/12345` (dias 1=seg … 7=dom) | caixinha | grava o horário do compartimento (os horários vêm do hub: `saude_horario`) |
| `HORAPAGA` | `<cmp>` (1–8) ou `0` = todos | caixinha | apaga horários |
| `TOL` | minutos (0–999) | caixinha | tolerância para confirmar (padrão do hub: 60) |
| `LIMBPM` | batimentos (0–250) | pulseira | parâmetro da regra de crise — **valor definido pela equipe clínica, nada de fábrica** |

Comando fora do formato ou fora da faixa: o aparelho **recusa** (erro ATT `0x80` "valor inválido") e não muda nada.
A lista de ações é a mesma do `physis-ble.js` (`ACOES`); o celular já recusa antes de enviar.

## 3. Segurança

- **LE Secure Connections** (Bluetooth 4.2+), **com proteção MITM** e **bonding**:
  `NimBLEDevice::setSecurityAuth(true /*bond*/, true /*mitm*/, true /*sc*/)`.
- Passkey de 6 dígitos:
  - caixinha (tem tela LCD): `setSecurityIOCap(BLE_HS_IO_DISPLAY_ONLY)`; o número aparece no LCD e a pessoa digita no celular;
  - pulseira (sem tela): passkey **fixo por aparelho**, gerado aleatório na fábrica, gravado na NVS e impresso na
    etiqueta/QR que vai na caixa (`setSecurityPasskey(n)`); nunca `000000` nem igual entre aparelhos.
- Características Linha e Comando com `NIMBLE_PROPERTY::READ_ENC | READ_AUTHEN` / `WRITE_ENC | WRITE_AUTHEN`
  (e o CCCD da Linha também cifrado): sem pareamento autenticado, nada é lido nem escrito.
- Pareamento só em "modo de pareamento" (botão longo de 5 s, janela de 2 min). Fora dele, o aparelho só aceita
  quem já está pareado (whitelist de bonds). Botão longo de 15 s = apagar todos os pareamentos.
- No máximo `[MARCADOR]` celulares pareados (cuidadores); o mais antigo sai quando passa do limite.
- Endereço privado resolvível (RPA) no anúncio: quem passa na rua não consegue seguir a pulseira pelo MAC.
- A chave do hub (`phk_…`) **não fica no aparelho BLE**: fica no celular (cifrada, ver `physis-ble.js`), presa ao ID do aparelho
  (`POST /api/dispositivos/chaves` com `no`), então uma chave vazada só aceita linhas daquele ID.

## 4. Consumo da pulseira (orçamento)

Valores **a medir na placa** (nada aqui é número de fábrica); a conta é para escolher os intervalos.

| Estado | Intervalo | Comentário |
|---|---|---|
| Anúncio sem celular | 1 s a 2 s (`[MARCADOR]`) | só enquanto não há conexão; depois de 10 min sem conexão, 5 s |
| Conectado, normal | connection interval 500 ms–1 s, slave latency 4 | o rádio dorme entre eventos |
| Linha normal | a cada `[MARCADOR]` min (proposta: 5 min) | BPM e MOV médios; GPS só se `GPS:1` mudou de posição |
| Crise | na hora, e a cada 30 s enquanto `CRISE:1` | connection interval cai para 30–50 ms durante a crise |
| GPS | desligado fora da crise (o celular sabe onde está) | o maior consumo da pulseira |

Conta de referência (substituir pelos números medidos): `média_mA = Σ (corrente_estado × fração_do_tempo)`;
`autonomia_h = capacidade_mAh × 0,8 ÷ média_mA`. Bateria em volts na linha (`BAT`) e em % no `0x2A19`.

## 5. Como cai no `saude.py`

| Chega por BLE | O celular faz | O hub (`saude.registrar_evento`) |
|---|---|---|
| `ID:31,TIPO:MED,CMP:1,EVT:TOMADO,BAT:3.91,TS:…` | confere (ID 1–99, TIPO, ≤ 240), fila cifrada, POST `/api/saude/linha` com `X-Physis-Chave` | dose do compartimento 1 marcada como tomada (`estado_dose`) |
| `…EVT:ATRASO…` / `…EVT:ESQUECEU…` | idem | atrasado / esquecido (+ aviso aos cuidadores) |
| `ID:51,TIPO:PUL,…,CRISE:1,…` | idem; envio imediato | alerta de crise na hora (sinais em 15 min viram um) |
| `ID:51,TIPO:PUL,GPS:0,LAT:-,LON:-,…` | idem | sem local |
| linha sem `TS` válido | põe o `TS` do celular | usa esse `TS` |
| linha repetida | envia | ignorada (`duplicada`) |
| pessoa sem consentimento | envia | descartada (`sem_consentimento`) |
| `0x2A19` (bateria %) | só mostra na tela | — (a bateria do hub vem do `BAT` da linha) |

## 6. Plano de teste

1. **Bancada (nRF Connect ou `bluetoothctl`)**: serviços e UUIDs certos; Linha/Comando recusam leitura/escrita sem
   pareamento; Battery e Device Info abertos; nome sem dado pessoal.
2. **Pareamento**: passkey certo pareia; errado recusa; fora do modo de pareamento, celular novo não conecta;
   reset de 15 s apaga os bonds.
3. **Pedaços**: MTU 23, 185 e 247; linha de 240 bytes chega inteira; linha com dois `\n` no mesmo pedaço vira duas.
4. **Comandos**: cada ação válida aplica; inválidos (`HOR:9/2500/8`, `SYNC:1`, `LIMBPM:999`) recusados sem efeito.
5. **Fila**: aparelho 24 h sem celular → conecta → todas as linhas chegam em ordem com o TS original; celular sem
   internet → linhas ficam na fila cifrada (IndexedDB) → volta a rede → chegam ao hub; hub devolve `aceitas`.
6. **Chave**: chave revogada → 401 → a tela avisa "peça uma chave nova"; chave de outro nó → `recusadas_outro_no`.
7. **Pulseira em uso**: app em segundo plano 8 h (Android com serviço em primeiro plano; iPhone com
   `bluetooth-central`), reconexão sozinha ao sair e voltar do alcance; crise simulada chega ao hub em < `[MARCADOR]` s.
8. **Consumo**: medir corrente de cada estado da seção 4 e registrar a autonomia real.
9. **Acessibilidade**: textos da `PhysisBLE.texto()` lidos pelo TalkBack/VoiceOver; nenhum estado só por cor.
