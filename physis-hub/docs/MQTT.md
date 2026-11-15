# Caixinha Physis IoT pelo MQTT

A Caixinha (ESP32 com ESPHome) fala com o broker MQTT (Mosquitto, no Raspberry Pi). O servidor da
plataforma assina os tópicos e transforma tudo na mesma linha V6 dos outros aparelhos (`TIPO:ZONA`).
Assim as telas, os alarmes, o registro e a exportação funcionam sem nada novo.

```
ESP32 (ESPHome) ──Wi-Fi──► Mosquitto (Pi) ◄──► servidor Physis (physis_hub/mqtt.py) ──► banco, telas, alarmes
        ▲                                                   │
        └──────── válvula ON/OFF (comando) ◄─────────────────┘
```

## 1. Ligar

No `instancia.json` do servidor:

```json
"mqtt": {
  "broker": "192.168.0.10",
  "usuario": "physis-hub",
  "nos": [
    {"no": "irrigacao-zona1", "id": 21, "u1": "umidade_solo_zona_1", "ir1": "valvula_zona_1",
     "bat": "tensao_alimentacao", "tmax": 15}
  ]
}
```

A senha do broker vai **só** na variável de ambiente `PHYSIS_MQTT_SENHA`. Também dá para configurar tudo
por ambiente: `PHYSIS_MQTT_BROKER`, `PHYSIS_MQTT_PORTA` (1883; 8883 com TLS), `PHYSIS_MQTT_USUARIO`,
`PHYSIS_MQTT_TLS=1`, `PHYSIS_MQTT_NOS` (a lista de nós em JSON). Sem broker ou sem nós, a ponte não liga.

Campos de cada nó: `no` (nome do ESPHome), `id` (1 a 99, único no lugar), `u1`/`u2` (sensores de umidade),
`ir1`/`ir2` (válvulas), `bomba`, `bat` e `tmax` (minutos máximos por rega). O nome do objeto é o `name`
do ESPHome em minúsculas, com `_` no lugar dos espaços.

## 2. O que a ponte faz

| Vem do nó | Vira |
|---|---|
| `<nó>/sensor/<u1>/state` = `41.3` | `U1:41.3` na linha V6 |
| `<nó>/switch/<ir1>/state` = `ON` | `IR1:1` |
| `<nó>/status` = `offline` | nó marcado fora (a tela já mostra pelo tempo sem leitura) |

| Comando da plataforma | Vai para o nó |
|---|---|
| `CMD:21:IRR1:1` / `:0` | `<nó>/switch/<ir1>/command` = `ON` / `OFF` |
| `CMD:21:LIM1:35` e `CMD:21:MODO:AUTO` | rega automática na ponte: abre abaixo de 35 %, fecha em 40 % (limite + 5) |

## 3. Segurança

- Três travas para a água não ficar aberta: a ponte fecha depois de `tmax`; o ESPHome fecha sozinho depois
  de `tmax_min` (sem rede); e o ESPHome fecha se perder o broker. Ao religar, a válvula começa fechada.
- Broker com usuário e senha (Mosquitto: `allow_anonymous false`). Em rede aberta, use TLS (porta 8883).
- A senha nunca fica no código nem no `instancia.json`.

## 4. Calibração

O sensor de umidade é calibrado no `irrigacao-zona1.yaml` (`calibrate_linear`: tensão seco → 0 %,
saturado → 100 %), com o sensor enterrado no lugar real. Anote a data da calibração na Gestão → Manutenção.

## 5. Testes

`tests/test_mqtt.py`: tradução dos tópicos, comandos, rega automática, tempo máximo e uma conversa completa
com um broker de mentira pela rede. Falta testar com o ESP32 e o Mosquitto de verdade (TRL 3 → 5).
