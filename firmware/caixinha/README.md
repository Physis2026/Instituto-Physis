# Caixinha de Automação (caixinha IoT / SustainKit 2.0) — material atual

Responsável: Erick Lopes — Physis Engineering Ltda.

## Status
Fase de arquitetura (TRL 3). Nenhum código foi testado em hardware ainda;
os arquivos abaixo são a base de partida para a montagem do módulo de irrigação.

## Conteúdo
- `docs/caixinha-irrigacao-automatizada.md` — guia técnico: arquitetura, peças, cuidados de segurança e passo a passo
- `esphome/irrigacao-zona1.yaml` — configuração ESPHome de um nó ESP32 (sensor de umidade + válvula), via MQTT
- `esphome/secrets.example.yaml` — modelo de credenciais (sem dados reais)
- `homeassistant/automacoes-irrigacao.yaml` — automações centrais (rega por zona + regra de segurança da bomba)

## Outros módulos (apenas arquitetura, sem código)
- Portão: atuador linear + fins de curso + reconhecimento de placas (Raspberry Pi + OpenALPR/YOLO)
- Segurança/monitoramento: Frigate NVR + Home Assistant + Coral USB
