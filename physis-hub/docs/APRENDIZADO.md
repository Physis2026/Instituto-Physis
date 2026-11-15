# Aprendizado no hub (`physis_hub/aprendizado.py`)

Aprendizado de máquina pequeno, que roda **no próprio hub, sem internet** e só com a biblioteca padrão do
Python (sem numpy). Os modelos aprendem com os dados que o hub já guarda no SQLite, são retreinados uma vez
por dia (3 h da manhã) e cada um sabe se explicar em português.

## 1. Os quatro modelos

| Modelo | O que faz | Como | Começa com |
|---|---|---|---|
| `chuva` | Chance de chover ≥ 1 mm amanhã | Regressão logística (gradiente descendente, L2) com: o que Open-Meteo, INMET e receptor disseram (+1 chove, −1 não, 0 sem dado), mm do Open-Meteo, mês (seno/cosseno), chuva medida no dia anterior à previsão e nos 3 dias antes (CEMADEN ou pluviômetro Physis) | 30 dias com chuva medida; antes disso usa o placar de `clima.py` |
| `anomalias` | Sensor estranho | z robusto (mediana e MAD, limite 3,5), sensor travado (24 leituras iguais), salto impossível (variação por minuto acima do físico) e bateria (reta da tensão nos últimos 7 dias → dias até 3,5 V) | 10 leituras |
| `consumo:<ativo>\|<grandeza>` | Energia (kWh/dia) e água (m³/dia) esperadas | Regressão linear (ridge leve) com mês (seno/cosseno), fim de semana, temperatura do ar do dia e produção/ocupação da Gestão (se houver) → desperdício quando o real passa de esperado + 2σ | 14 dias; antes, a média |
| `irrigacao:<ativo>` | Quando irrigar | Reta da umidade do solo por hora desde a última rega/chuva (subida > 3 pontos) → hora em que chega ao limite da válvula (`LIM1`/`LIM2`, padrão 30 %); com chance de chuva ≥ 60 % (modelo `chuva`) e limite a 12 h ou mais, sugere esperar a chuva | 4 leituras em 1 hora |

Cada modelo tem `dados_<m>(db)`, `treinar_<m>(amostras, agora)`, `prever_<m>(modelo, x)` e `explicar_<m>(modelo)`.
Treino e previsão são funções puras e determinísticas (começam do zero, sem sorteio).

A tabela `modelo` guarda `nome, versao, treinado_em, n_amostras, metricas (JSON), parametros (JSON)`; cada treino
grava uma versão nova e guarda as 30 últimas. Cada treino também entra no registro do lugar (só os nomes).

### Avaliação honesta (chuva)
Treina com os 70 % de dias mais antigos e mede nos 30 % mais novos. As métricas comparam, no mesmo período:
o modelo, o placar das fontes (a conta de `clima.Clima.combinada`), cada fonte sozinha e "sempre a média".
Brier = erro quadrático da probabilidade (0 é perfeito; 0,25 é chutar 50 %). A tabela `calibracao` mostra, por
faixa de chance prevista, quantas vezes choveu de fato.

### Resultados nos dados sintéticos dos testes
| Modelo | Dados | Resultado |
|---|---|---|
| chuva | 365 dias; Open-Meteo acerta 80 %, INMET 70 %, receptor 60 %; mais chuva de nov. a mar. | Brier **0,105** (placar 0,137; Open-Meteo 0,173; INMET 0,273; receptor 0,409; média 0,180); acerto 84 % |
| consumo | 120 dias; 50 kWh + 10 no fim de semana + 2 kWh/°C + ruído 1,5 | r² **0,925**, σ 1,7 kWh/dia; efeito do fim de semana recuperado (10 ± 2) |
| anomalias | série com ruído 0,5 | pico de 99 % pego por z robusto e salto; 24 valores iguais = travado; bateria −0,02 V/dia → 14 dias |
| irrigação | secando 1 ponto/h | taxa 1,000 %/h; limite em 15 h; com 80 % de chuva → "aguardar chuva" |

## 2. Rotas (colar em `servidor.py`)

No começo de `criar_manipulador`, junto de `saude = saude_mod.Saude(hub)`:

```python
from . import aprendizado as aprendizado_mod      # no topo do arquivo
...
    aprendizado = aprendizado_mod.Aprendizado(hub)
```

No `do_GET`:

```python
            # ── Aprendizado (modelos do próprio hub, sem internet) ──
            if u.path.startswith("/api/aprendizado/"):
                if self._barrado():
                    return
                if not self._autorizado():
                    return self._json(401, {"ok": False, "erro": "token ausente ou invalido"})
                qual = u.path.rsplit("/", 1)[-1]
                if qual == "estado":
                    return self._json(200, aprendizado.estado())
                if qual == "anomalias":
                    return self._json(200, aprendizado.anomalias())
                if qual == "previsao-chuva":
                    return self._json(200, aprendizado.previsao_chuva())
                if qual == "consumo":
                    return self._json(200, aprendizado.consumo())
                if qual == "irrigacao":
                    return self._json(200, aprendizado.irrigacao())
```

No `do_POST` (depois de `corpo = self._corpo()`):

```python
            if u.path == "/api/aprendizado/treinar":
                q = self._sessao_ou_401()
                if not q:
                    return
                if q["papel"] != "administrador":
                    return self._json(403, {"ok": False, "erro": "so a direcao pode treinar os modelos agora"})
                return self._json(200, aprendizado.treinar())
```

Em `main()`, depois da thread da saúde (treina ao ligar se o último treino tem mais de 1 dia; depois às 3 h):

```python
    from . import aprendizado as aprendizado_mod
    apr_fundo = aprendizado_mod.Aprendizado(hub)
    threading.Thread(target=aprendizado_mod.rodar, args=(apr_fundo, parar), daemon=True).start()
```

## 3. Onde cada resultado aparece (telas)

| Resultado | Rota | Painel (plataforma) | Gestão |
|---|---|---|---|
| Chance de chuva do modelo | `GET /api/aprendizado/previsao-chuva` | **Monitoramento verde → Previsão**: um cartão "Previsão deste lugar (aprendida)" ao lado da combinada, com `prob`, `explicacao`, as 3 maiores `contribuicoes` e um selo "modelo × placar" com `metricas.brier_modelo` e `brier_placar`. Também em **Resiliência climática → Próximos dias** | — |
| Anomalias | `GET /api/aprendizado/anomalias` | **Resumo** e **SCADA**: entra na lista de alertas (nível `alarme`/`atencao`, texto pronto em `texto`); **Caixinha IoT / Monitoramento verde**: ícone no nó (`ativo`) | **Manutenção**: "bateria acabando" (com `dias_ate_baixa`) e "sensor travado" viram sugestão de ordem de serviço |
| Consumo esperado × real | `GET /api/aprendizado/consumo` | **SustainKit → Energia/Água** e **Indicadores**: gráfico de barras real × faixa esperada dos últimos 7 dias; dias em `desperdicio` em destaque | **Indicadores** e **Relatório**: frase `explicacao` e lista de dias com desperdício |
| Recomendação de irrigação | `GET /api/aprendizado/irrigacao` | **Monitoramento verde**, em cada nó de solo: frase `texto` e o horário `quando` | — |
| Estado dos modelos | `GET /api/aprendizado/estado` | **Configurações → Aprendizado** (só leitura): nome, versão, data, amostras, `explicacao` | **Direção**: botão "Treinar agora" (`POST /api/aprendizado/treinar`, só administrador) |

Regras de tela: mostrar sempre a `explicacao` junto do número; quando `metricas.modo` for `placar` ou `media`,
mostrar "aprendendo (poucos dados)"; nunca esconder a previsão das fontes — o modelo é mais uma opinião.

## 4. Limites conhecidos
- O histórico de temperatura vem dos sensores do ar (`temperatura`, ativo `-ar`); sem sensor, o consumo usa só
  mês e fim de semana.
- Produção/ocupação vem da Gestão **do cliente** (`cliente_estado`, chave `physis-gestao-cliente`, lista `producao`),
  não da Gestão Physis interna (desde 15/11/2026). Regra de mês para dia: o total do mês (`mes` AAAA-MM, `prod`) é
  dividido igualmente pelos dias daquele mês (31, 30, 29 ou 28); item com dia (`dia` ou `data` AAAA-MM-DD) vale para o
  próprio dia. A produção só entra no modelo se cobrir 80 % dos dias com consumo.
- Energia e água medidas chegam pelos tipos V6 `ENE` e `HID` (ou pela ponte MQTT, nó `"tipo": "energia"`/`"agua"`);
  `energia` é potência em kW e a conta do dia é média × 24 h.
- Leituras sem relógio (`TS:0`) não entram em consumo, bateria e irrigação.
- Treino da chuva com 1 ano de dados leva ~3 s num PC; num Raspberry Pi 4, estimado em 15–30 s (1 vez por dia).
