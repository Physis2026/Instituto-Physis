# Irrigação Automática de Gramado — Chácara (múltiplas zonas)

Projeto: gramado de uma chácara, irrigado por uma mistura de aspersores e mangueiras/canhotes fixos, dividido em **várias zonas independentes** — cada zona liga sozinha conforme a umidade do solo naquele trecho, não todas juntas. Uma bomba de alta pressão (220V) alimenta o sistema todo. Isso vai complementar a central que já existe na chácara, rodando num Raspberry Pi (software ainda não identificado com certeza).

## Arquitetura geral

Como o WiFi cobre bem todo o quintal, a abordagem mais simples e robusta é: **um "nó" ESP32 por zona (ou por grupo de zonas próximas)**, em vez de tentar levar fiação de sensor até uma única caixinha central. Isso evita cabos de sinal analógico muito longos (que perdem precisão) e facilita expandir depois.

```
[Sensor umidade zona 1] ─┐
                          ├─ ESP32 nó 1 (ESPHome/MQTT) ──┐
[Válvula zona 1] ────────┘                                │
                                                            │
[Sensor umidade zona 2] ─┐                                 │
                          ├─ ESP32 nó 2 (ESPHome/MQTT) ──┼── WiFi ── Raspberry Pi (central)
[Válvula zona 2] ────────┘                                │              │
        ... (um nó por zona) ...                          │              │
                                                            │              ├── decide quando ligar cada válvula
[Sonoff já existente] ── liga a bomba 220V ────────────────┘              └── liga o Sonoff da bomba quando
                                                                                qualquer zona estiver ativa
```

Como ainda não sabemos com certeza o que roda no Raspberry Pi, a integração via **MQTT** (broker Mosquitto, leve, roda no próprio Pi) é o caminho mais universal: qualquer software do lado central (Home Assistant, Node-RED, OpenHAB, script próprio) consegue assinar os tópicos sem exigir reconfiguração se descobrir depois que é outro sistema.

**Regra de ouro da bomba**: ela só deve ligar quando **pelo menos uma válvula de zona estiver aberta** (bomba rodando contra todas as válvulas fechadas gera pressão excessiva e desgasta o equipamento). Isso vira uma automação central: "ligar Sonoff da bomba SE qualquer zona = ligada; desligar SE todas as zonas = desligadas".

## Lista de peças — por zona (multiplique pela quantidade de zonas)

| Peça | Função | Qtd por zona | Observação |
|---|---|---|---|
| ESP32 DevKit V1 (WROOM-32) | Nó local da zona | 1 (pode atender 2-3 zonas próximas se tiver GPIO sobrando) | Roda ESPHome |
| Sensor de umidade do solo capacitivo, versão **enterrável/à prova d'água** (IP68) | Mede umidade daquele trecho de gramado | 1-2 | Precisa aguentar ficar enterrado permanentemente |
| Válvula solenoide de irrigação 24V AC (padrão Rain Bird/Hunter) | Libera água só naquela zona | 1 | Componente padrão de irrigação |
| Módulo relé (baixa tensão, contato aguenta 24VAC/1A) | ESP32 aciona a válvula | 1 | O relé isola e chaveia o 24VAC da válvula |
| Caixa/case IP65 | Proteger o ESP32 e o relé | 1 | Essencial — o nó fica exposto no quintal |
| Cabo de irrigação (18AWG, próprio para enterrar) | Levar sinal do relé até a válvula | conforme distância | |
| Fonte 5V | Alimentar o ESP32 daquele nó | 1 | Tomada próxima, ou powerbank/solar se for longe |

## Peças compartilhadas (uma vez só)

| Peça | Função | Observação |
|---|---|---|
| Sonoff existente (ou compatível com a bomba) | Liga/desliga a bomba de 220V | Confirmar potência + corrente de partida |
| Bomba de alta pressão 220V | Pressuriza a água do sistema | Já definida |
| Transformador 24VAC para irrigação | Alimenta as válvulas | Dimensionado pela soma das válvulas que podem abrir ao mesmo tempo |
| Raspberry Pi (central existente) | Roda a automação | Já existe na chácara |
| Broker MQTT (Mosquitto) | Ponte entre nós e central | Instalar no próprio Raspberry Pi |

## Cuidados importantes

- **220V + água nunca se misturam fisicamente**: Sonoff e fiação de 220V numa caixa seca, separada.
- **Proteção DR/disjuntor dedicado** no circuito da bomba.
- **Bomba nunca liga com todas as válvulas fechadas** — obrigatório na automação central.
- **Nós de zona IP65+**: proteção contra chuva/sol.
- **Sensores enterráveis** vedados para ficar enterrados permanentemente.
- **Corte de segurança por tempo** em cada zona, mesmo que o sensor trave lendo "seco".
- **Calibração por zona**: calibrar sensor por sensor.

## Código

- Nó ESP32: `esphome/irrigacao-zona1.yaml`
- Automação central: `homeassistant/automacoes-irrigacao.yaml`

## Passo a passo de montagem

1. Confirmar o que roda no Raspberry Pi — define se a integração é direta (Home Assistant) ou via MQTT genérico.
2. Instalar o broker MQTT (Mosquitto) no Raspberry Pi, se ainda não tiver.
3. Montar **um** nó de zona primeiro, de ponta a ponta, testando cada peça isoladamente antes de enterrar.
4. Validar leituras do sensor e abertura/fechamento da válvula pelo painel, ainda sem a bomba ligada.
5. Configurar o Sonoff da bomba e a automação "bomba segue as zonas" — testar com a válvula da zona 1 aberta manualmente.
6. Replicar o nó para as demais zonas, uma de cada vez.
7. Só depois colocar tudo em operação automática, com tempo máximo de rega em cada zona.
