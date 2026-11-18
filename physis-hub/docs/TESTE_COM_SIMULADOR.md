# Testar um pacote de cliente com o simulador de dispositivos

Versão de 15/11/2026. Ferramenta: `ferramentas/simulador_dispositivos.py` (só no repositório; não vai no pacote).

> **NUNCA rode o simulador na instalação de um cliente de verdade.** Ele cria aparelhos e leituras inventados.
> Numa instalação real os dados têm de vir só dos aparelhos do cliente. O simulador recusa qualquer hub que não esteja
> neste computador (`localhost` ou `127.0.0.1`), a não ser com `--permitir-remoto`, que só serve para um hub de **teste**
> em outra máquina.

## Por que existe

Um pacote novo (por exemplo, o da Fazenda Santa Clara) sai zerado: sem aparelhos, sem leituras. É de propósito: não
há dado falso numa instalação real. Por isso Monitoramento, Água, energia e alertas ficam vazios até chegar o primeiro
aparelho. Para ver os módulos funcionando numa versão de teste, o simulador faz o papel dos aparelhos: manda leituras
pelo mesmo caminho que os aparelhos de verdade usam (as linhas V6 de `PROTOCOLO.md` e `EXTENSAO_V6.md`).

Tudo o que ele cria fica marcado como **SIMULADO / teste**: cada linha leva `SIM:SIMULADO/teste`, as chaves dos
aparelhos têm esse rótulo e as leituras de água têm `origem: "simulador"` e `simulado: true`.

## Passo a passo

### 1. Montar e ligar o pacote no seu computador

    cd physis-hub
    python montar_clientes.py --saida ../pacotes-teste --so fazenda-santa-clara

Entre na pasta do pacote gerada (`../pacotes-teste/physis-fazenda-santa-clara`) e ligue o hub na porta 8802:

    # Linux
    PHYSIS_PORTA=8802 python3 -m physis_hub.servidor
    # Windows (PowerShell)
    $env:PHYSIS_PORTA="8802"; python -m physis_hub.servidor

Abra `http://localhost:8802/`, crie a primeira conta (ela vira a **direção**) e preencha o **Início** com o CEP do lugar.

### 2. Previsão do tempo: agora é automática

Assim que o local é gravado no Início, o hub busca a previsão sozinho, em até uns 10 segundos. Não precisa mais clicar
em "Consultar agora" (o botão continua lá). Depois disso, cada fonte tem o seu ritmo: Open-Meteo a cada hora, INMET a
cada 3 horas, CEMADEN a cada 15 minutos. Se uma fonte não responde, o hub espera um pouco mais a cada tentativa e
continua mostrando a última previsão boa.

Se faltar município ou UF, o cartão do INMET e do CEMADEN mostra **"falta município/UF (preencha o CEP no Início)"**.

### 3. Ligar o simulador

Em outro terminal, na pasta do repositório:

**Histórico rápido** (21 dias de leituras de uma vez, para os gráficos e o aprendizado):

    python ferramentas/simulador_dispositivos.py --hub http://localhost:8802 --uma-vez --dias 21

**Tempo real** (uma leitura por aparelho a cada 30 segundos; Ctrl+C para parar):

    python ferramentas/simulador_dispositivos.py --hub http://localhost:8802 --intervalo 30

O normal é rodar os dois: primeiro o histórico, depois o tempo real.

**Com a conta da direção** (opcional): o simulador cria uma chave para cada aparelho, grava leituras de qualidade da água
(pH, turbidez, cloro) na aba Água e manda treinar os modelos na hora. A senha vem de um arquivo seu ou é pedida no
terminal; ela nunca aparece na tela nem fica no código:

    python ferramentas/simulador_dispositivos.py --hub http://localhost:8802 --uma-vez --usuario ana --senha-arquivo ~/senha-teste.txt

Sem `--usuario`, o hub aceita as linhas sem chave só porque elas vêm do próprio computador (rede local).

## O que você deve ver

Os aparelhos simulados são os nós **81 a 89**:

| Nó | Aparelho | Onde aparece |
|---|---|---|
| 81, 82 | Nó de solo e clima (Talhão A e B): umidade do solo, irrigação, temperatura e umidade do ar | Monitoramento |
| 83 | Pluviômetro | Monitoramento (chuva medida no lugar), placar das previsões |
| 84 | Medidor de energia: P, Q, S, V, I e fator de potência, com geração solar ao meio-dia | energia, consumo |
| 85 | Medidor de água: vazão e pressão | Água, consumo |
| 86 | Secador solar | Secador |
| 87, 88, 89 | Caminhão, carro e trator SIMULADOS (linha `TIPO:VEI`): GPS em volta do local da instalação, vazão e nível de combustível, odômetro (trator: horímetro). Nível do caminhão caindo parado de madrugada um dia por semana; o carro sai da cerca de teste um dia por semana | Frota e combustível (com `--usuario`, os 3 veículos e a cerca de teste são cadastrados; sem ele, aparecem como "nós sem veículo") |

- **Monitoramento:** os nós aparecem online, com a umidade do solo subindo e descendo no dia; a irrigação liga quando o
  solo passa do limite de 30 %. O cartão de previsão mostra Open-Meteo, INMET e CEMADEN atualizados.
- **Alertas:** o nó 81 está com a bateria descarregando (perto do fim dos 21 dias, aparece "bateria baixa").
- **Aprendizado (anomalias):** de vez em quando um salto impossível de temperatura (58 °C) e, um dia por semana, o
  sensor B do nó 82 fica travado no mesmo valor.
- **Energia:** consumo maior no horário de trabalho, energia injetada ao meio-dia (potência negativa), um dia de
  desperdício a cada 9 e fator de potência baixo em algumas manhãs. O modelo de consumo precisa de 14 dias; por isso o
  histórico padrão tem 21.
- **Água:** vazão maior de dia e na irrigação, e um vazamento de madrugada a cada 6 dias. Com `--usuario`, leituras
  de pH, turbidez e cloro antes e depois do filtro, algumas fora da faixa. O alerta da água só aparece depois que
  alguém digitar os limites (na água, nenhum limite vem de fábrica).
- **Indicadores:** com o modo tempo real ligado, "nós com dado na hora" e "leituras" sobem a cada hora.

## Limpar depois do teste

Desligue o hub (Ctrl+C na janela dele) e rode, apontando para o banco do pacote (`physis-hub.db` na pasta do pacote,
ou o nome que estiver em `"banco"` no `instancia.json`):

    python ferramentas/simulador_dispositivos.py --limpar --banco ../pacotes-teste/physis-fazenda-santa-clara/physis-hub.db --hub http://localhost:8802

Sai tudo o que tem a marca de simulado: leituras e medições, chaves dos aparelhos (revogadas), leituras de água
simuladas, a chuva do pluviômetro simulado e os modelos aprendidos (o hub treina de novo ao ligar). O que é de verdade
fica. O registro encadeado e os lotes de integridade **não** são apagados (eles não podem ser alterados, de propósito):
os eventos "nó descoberto" dos nós 81 a 89 continuam lá. Por isso, para entregar a um cliente, use sempre um pacote
**novo**, nunca um que passou pelo simulador.

## Opções

| Opção | Para quê |
|---|---|
| `--hub URL` | endereço do hub (só deste computador) |
| `--uma-vez` e `--dias N` | manda N dias de histórico e termina (padrão 21) |
| `--passo-min M` | minutos entre leituras no histórico (padrão 15) |
| `--intervalo S` | segundos entre leituras no tempo real (padrão 30) |
| `--id-base B` | muda os números dos nós (B+1 a B+6) |
| `--semente X` | mesma semente, mesmos dados |
| `--sem-anomalias` | só dados normais |
| `--usuario` e `--senha-arquivo` | conta da direção (chaves, água, treino) |
| `--permitir-remoto` | hub de teste em outra máquina (nunca o cliente real) |
| `--limpar` e `--banco` | apaga os dados simulados (hub desligado) |

## Limites das fontes de previsão

- **Open-Meteo:** a API gratuita aceita até 600 chamadas por minuto, 5.000 por hora e 10.000 por dia, e é **só para
  uso não comercial** (termos lidos em 15/11/2026). O hub faz 1 por hora, e nunca mais de 1 a cada 10 minutos (1 por
  minuto logo depois de trocar o local). Para cliente pagante, ver plano pago ou servidor próprio [CONFERIR].
- **INMET e CEMADEN:** não achamos limite publicado [CONFERIR]. O hub consulta o INMET a cada 3 horas e o CEMADEN a cada
  15 minutos, nunca abaixo de 30 e 10 minutos.
