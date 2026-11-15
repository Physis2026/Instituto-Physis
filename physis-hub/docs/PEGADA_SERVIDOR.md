# Pegada do servidor (sistema digital)

Explicação simples: as máquinas que rodam o Sistema Physis também gastam luz e foram fabricadas. Este módulo
mede (ou estima) a energia delas, guarda o total de cada hora e mostra a pegada na aba Carbono, nas subabas
Escopo 2, Escopo 3 e no resumo do Inventário. Obrigatório na instalação da Casa Physis; disponível em qualquer instalação.

## Arquivos

| Arquivo | O que faz |
|---|---|
| `physis_hub/pegada_servidor.py` | Amostras em segundo plano, tabela `servidor_energia`, relatório da rota |
| `physis_hub/carbono.py` | Regra da dupla contagem (`servidor_contagem`, `servidor_inventario`) e as linhas no `calcular` |
| `sistema/physis-carbono.js` | Seção “Pegada do servidor (sistema digital)”, mesma regra (`servidorInventario`) |
| `sistema/physis-fatores-emissao.json` | Bloco `servidor`: potência e carbono de fabricação por classe de máquina (todos “verificar”) |
| `tests/test_pegada_servidor.py` | Leitores falsos (RAPL, nvidia-smi, carga) e relógio falso |

## Como cada máquina é medida (a primeira que funcionar vale)

1. **Medidor** já ligado ao hub (tomada inteligente, nó V6 ou MQTT): energia acumulada (kWh, diferença entre
   leituras) ou potência (W × tempo, só se a leitura tiver menos de 2 intervalos). Qualidade: **medido**.
2. **RAPL** (Linux, `/sys/class/powercap/intel-rapl:N/energy_uj`, só as zonas de pacote; contador que dá a volta
   é tratado) + resto da placa pela classe (`w_resto`) + placas de vídeo pelo `nvidia-smi`. Qualidade: **parcial**.
   Desde o kernel 5.10 só o root lê o RAPL: sem permissão, cai para o passo 3.
3. **Potência da classe** (parada e em carga) interpolada pela carga do processador (`os.getloadavg` ÷ núcleos;
   sem ela, `uso` da configuração ou 30%). Com `nvidia-smi`, a placa nominal sai e entra a medida. Qualidade: **estimado**
   (ou parcial, com placa medida).

Outras máquinas (servidor de IA, host do Docker) entram em `hosts`, cada uma com `metodo`: `medidor`, `watts`
(potência fixa informada) ou `nominal` (classe × `uso`).

Amostra a cada 5 minutos (`intervalo_min`). Um intervalo que cruza a hora é dividido entre as duas horas. Lacuna
longa (hub parado): a estimativa vale só 2 intervalos; contadores (RAPL, kWh do medidor) valem inteiros, porque
mediram de verdade.

## Contas

- kWh por mês = kWh dos últimos 30 dias ÷ horas cobertas × 730 h (sem histórico: potência de agora × 730 h).
- PUE: kWh na tomada × PUE (1,0 no lugar; 1,5 padrão em datacenter, ou o do contrato).
- tCO₂e por ano = kWh por ano ÷ 1.000 × fator da rede. **Mesmo fator do Carbono**: configuração `fator_rede`
  → escolha salva no Carbono do cliente (`physis-carbono`, `rede.fator`/`fator_manual`) → padrão da base.
  Na tela, a conta usa sempre o fator do escopo 2 do próprio inventário.
- Fabricação (escopo 3, categoria 2) = kgCO₂e da classe (+ 150 kg por placa de vídeo) ÷ anos de uso. O GHG
  Protocol pede no relato oficial o total no ano da compra; a tela avisa isso e o risco de contar junto com
  “Bens de capital (por gasto)”.
- Por cliente hospedado (`clientes`, com `peso`): parte do kWh por mês; para o cliente é escopo 3, categoria 1.
  Também sai kWh por mês por conta ativa.

## Dupla contagem (a escolha que importa)

| Onde fica a máquina | O que acontece |
|---|---|
| No lugar cujas contas de luz já estão no inventário (Casa Physis) | “parte do escopo 2 já contado”: só informação, não soma |
| Fora (datacenter, servidor da Physis que hospeda clientes), máquina própria | soma no **escopo 2** como fonte própria |
| Fora, hospedagem comprada de outra empresa (`controle: "servico"`) | soma no **escopo 3, categoria 1** |

Configuração por máquina: `local` (`no_lugar` ou `fora`) e `controle` (`proprio` ou `servico`). No inventário, o
dono escolhe em Escopo 2 → “Como contar a energia do servidor”: Automático (pelo lugar, recomendado), “Já está nas
contas de luz” ou “Somar como fonte própria”; e pode desligar “Incluir a pegada do servidor”.
Fabricação entra sempre (não está na conta de luz), com a categoria 2 marcada.

## Configuração (`instancia.json` → `"pegada_servidor"`, ou `PHYSIS_PEGADA` com o mesmo JSON; `PHYSIS_PEGADA=0` desliga)

```json
{"classe": "rpi5", "nome": "Hub da Casa Physis", "local": "no_lugar", "controle": "proprio",
 "medidor": {"ativo": "lugar01/no7", "grandeza": "energia_kwh", "tipo": "energia_kwh"},
 "hosts": [{"id": "ia", "nome": "Servidor de IA", "classe": "servidor_gpu", "metodo": "nominal", "uso": 0.2, "gpus": 2, "local": "no_lugar"}],
 "intervalo_min": 5, "contagem": "auto", "fator_rede": null,
 "clientes": [{"id": "cliente-a", "nome": "Cliente A", "peso": 1}]}
```

Classes: `rpi4`, `rpi5`, `mini_pc`, `notebook`, `workstation`, `servidor_x86`, `servidor_gpu` (sem `classe`: detecta Raspberry
Pi pelo `/proc/device-tree/model`; com placa NVIDIA, `servidor_gpu`; senão `mini_pc`).

**Casa Physis (decidido em 15/11/2026):** o hub começa num **notebook com 16 GB de RAM (2 × 8 GB)**, classe `notebook`
(`montar_clientes.py`, `PEGADA_PADRAO`). Os valores da classe são ordem de grandeza (8 W parado, 45 W em carga, 200 kgCO₂e de
fabricação, 4 anos): troque pela PCF e pela ficha do modelo comprado. Com uma tomada medidora ligada ao hub, o método passa a
"medido" e a estimativa deixa de valer.

## Rota

> **Aplicado em 15/11/2026** (`servidor.py`): rota e linha de fundo no `main()` (`pegada_servidor.rodar`, a mesma instância
> que a rota lê; `PHYSIS_PEGADA=0` desliga as duas e a rota responde `{"ok": false, "desligada": true}`). O pacote da Casa
> Physis leva `"pegada_servidor"` no `instancia.json` (`montar_clientes.py`, `PEGADA_PADRAO`: a configuração acima sem medidor,
> servidor de IA e clientes de exemplo). Testes: `tests/test_rotas_novas.py` (classes `Pegada` e `PegadaDesligada`).

`GET /api/servidor/pegada` — exige sessão (cliente ou acima). Equipe e direção recebem o detalhe (fonte de cada
medida e a parte de cada cliente hospedado); o cliente recebe só os totais e a lista de máquinas.
Sem servidor (arquivo aberto direto), a tela mostra um **exemplo marcado** que nunca entra no inventário.

## Metodologia

GHG Protocol (escopo 2; escopo 3, categorias 1 e 2), Orientação Setorial de TIC do GHG Protocol e Recomendação
ITU-T L.1450, citados pelo nome. Potências e carbono de fabricação: fichas técnicas, PCF de fabricantes e base aberta
Boavizta, em ordem de grandeza (“verificar”).

## Falta (fase 2)

- Potência do Raspberry Pi 5 pelo PMIC (`vcgencmd pmic_read_adc`) e AMD sem RAPL legível.
- Ler a pegada de outro hub Physis pela rede (hoje: medidor, watts ou classe).
- Curadoria dos valores de fabricação com a PCF do modelo comprado.
- Inglês das frases novas: `PhysisCarbono.i18nServidor` (juntar em `physis-i18n-modulos.json`).
