# Saúde: caixinha de remédios e pulseira

Versão 0.1 · 14/11/2026 · módulo novo, linhas MED e PUL **a homologar**.

Dois produtos que funcionam juntos ou separados:

- **Caixinha de remédios** — hoje um Arduino (`caixa_remedios.ino`: 4 compartimentos, 08/12/18 h, 60 min de
  tolerância, estados ESPERANDO/PENDENTE/TOMADO/ESQUECEU, botão de confirmar, LCD). Vai para ESP32 com Wi-Fi/BLE.
- **Pulseira para pessoas autistas** — alerta de crise e local. Base: firmware da coleira
  (`firmware/animais/smartcolar_comentado`: GPS + LoRa + acelerômetro, impacto > 2,5 g).

Arquivos: `physis_hub/saude.py` (servidor), `tests/test_saude.py`, `sistema/physis-saude.js` (aba da tela).

## LGPD (dado de saúde é sensível)

| Regra | Como está feito |
|---|---|
| Só vê quem foi autorizado | tabela `saude_acesso`; quem cadastra entra; outros só por autorização (nem o administrador vê sem ela) |
| Consentimento com data e hora | `saude_consentimento` (quem, papel, finalidade, versão do termo, `dado`, `revogado`) |
| Menor de 18 anos | calculado pela data de nascimento; exige responsável legal e o consentimento é dele |
| Retirar o consentimento | o que chega dos aparelhos é descartado (`sem_consentimento`), não há avisos, a tela não mostra dados |
| Apagar | `apagar` remove tudo da pessoa, inclusive e-mails de aviso ainda não enviados |
| Minimização | o registro do hub (`registrar`) só leva ação + id + quem fez; e-mail de dose não leva o nome do remédio; local da pulseira apagado após 30 dias |

Rotas sempre com sessão (`_sessao_ou_401`), mesmo em instalação sem login: sem contas não há como autorizar ninguém.

## Linhas novas (proposta para o EXTENSAO_V6.md)

| TIPO | Aparelho | Chaves | Exemplo |
|---|---|---|---|
| `MED` | Caixinha de remédios | `CMP EVT BAT TS` | `ID:31,TIPO:MED,CMP:1,EVT:TOMADO,BAT:3.91,TS:1794650400` |
| `PUL` | Pulseira | `LAT LON GPS CRISE BPM MOV BAT TS` | `ID:51,TIPO:PUL,LAT:-22.51003,LON:-43.18012,GPS:1,CRISE:1,BPM:128,MOV:2,BAT:3.80,TS:1794650400` |

- `CMP` compartimento 1 a 8. `EVT` `TOMADO` (confirmou), `ATRASO` (confirmou depois da tolerância), `ESQUECEU`
  (a tolerância acabou sem confirmar). A caixinha manda uma linha **por evento**, não por período.
- `CRISE` 0/1, decidido no aparelho (por exemplo, movimento brusco repetido + batimento alto; **regra a definir com a
  equipe técnica e clínica**). `BPM` batimentos por minuto ou `-` sem sensor. `MOV` 0 parado, 1 andando, 2 correndo
  (igual ao `ATV` da coleira). `GPS:0` → `LAT`/`LON` como `-`.
- `BAT` em volts; abaixo de 3,45 V gera aviso uma vez por dia (**limite a confirmar**).
- Sem `TS` válido, vale a hora de chegada. Linha repetida (mesmo `ID`, `TS`, evento) é ignorada.

As linhas entram por `POST /api/saude/linha` (texto, uma por linha; chave do dispositivo ou `X-Physis-Token`
quando o hub tem token) e, desde 15/11/2026, também pelo receptor (`/api/gateway/webhook`), pelo `/api/v6/linha` e
pela ponte MQTT: `MED` e `PUL` estão em `protocolo.TIPOS_CONHECIDOS` e o `Hub._receber_linha` as entrega à Saúde
(`hub.saude_receptor`, ligado pelo servidor) **antes** do adaptador genérico, sem gravar em `leitura`/`medicao` e sem
mostrar a linha no painel (o descarte aparece só como `saude_<motivo>`). Continuam **a homologar**.

Bandeira: `PHYSIS_SAUDE_V6` (padrão `1`). Com `PHYSIS_SAUDE_V6=0`, o receptor e o `/api/v6/linha` voltam a recusar
`MED`/`PUL` (`tipo_desconhecido`); `/api/saude/linha` continua aceitando.

### Homologação: o que foi feito e o que falta

Feito no servidor (passos 1 a 3 abaixo, só a parte Python; testes em `tests/test_pluviometro_saude.py` e `tests/test_fluxos.py`).
Falta: os dois `protocolo.cpp`, o passo 4 (mover os casos para `test_protocolo.py`) e o passo 5 (firmware).

1. Acrescentar `"MED", "PUL"` a `TIPOS_CONHECIDOS` em `physis_hub/protocolo.py`, nos dois `protocolo.cpp` e no `PROTOCOLO.md`.
2. Em `Hub._receber_linha`, **antes** do adaptador genérico: se `TIPO` for MED/PUL, chamar `saude.registrar_evento(linha)`
   e não gravar em `medicao` (lá qualquer usuário veria dado de saúde).
3. `adaptador.py`: não mapear MED/PUL para physis/1 (ou mapear só bateria e RSSI).
4. Passar os casos de `tests/test_saude.py::Linhas` para `tests/test_protocolo.py`.
5. Pulseira por LoRa: entrar no TDMA como a coleira (ver EXTENSAO_V6, seção 4). Caixinha por Wi-Fi: `POST /api/saude/linha`.

## Regras de dose

- Janela de cada dose: de 30 min antes até a tolerância (padrão 60 min) depois da hora marcada.
- Estados: `esperando`, `pendente` (na hora), `tomado`, `atrasado`, `esquecido`.
- O hub cobra sozinho as doses vencidas das últimas 24 h (`verificar`, a cada minuto e a cada leitura da tela):
  grava `ESQUECEU` e põe e-mail em `email_saida` (estado `pendente`, ref `saude-<alerta>`) para os cuidadores com
  e-mail e aviso ligado. Um aviso por dose. A crise da pulseira avisa na hora; sinais seguidos em 15 min viram um só aviso.
- Adesão = (tomadas + atrasadas) ÷ doses com resultado. Horário retirado não apaga o histórico.

## Falta (hardware e operação)

- Firmware ESP32 da caixinha: horários vindos do hub, relógio por NTP/`SYNC`, envio da linha MED por Wi-Fi, fila local sem rede.
- Pulseira: placa, sensor de batimento, regra de crise validada com especialista, bateria, porte LoRa/RadioLib ou Wi-Fi/BLE.
- Chave por aparelho (hoje vale o token geral do hub).
- Texto do termo de consentimento revisado pelo jurídico (versão `1` é provisória).
- SMS/WhatsApp para cuidadores sem e-mail (hoje só e-mail).
