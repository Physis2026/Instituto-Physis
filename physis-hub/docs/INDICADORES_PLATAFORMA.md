# Indicadores da plataforma

Decisão D18 (15/11/2026): a plataforma interna, onde ficam os supervisórios de projetos e clientes, tem a sua
própria tela de indicadores — todos os dados da plataforma, erros e o que melhorar — e aprende sempre com o que
aconteceu.

Onde: Gestão interna → menu **Indicadores da plataforma** (perto de Clientes e Chamados). Só equipe e direção.
Código: `physis_hub/indicadores.py`, rotas `/api/indicadores/...`, testes `tests/test_indicadores.py`.

## Em uma frase

De 5 em 5 minutos o hub anota os números da hora (só números, nunca nome, e-mail ou documento de cliente),
compara cada número com o mesmo horário dos dias anteriores, avisa o que saiu do normal, mostra a tendência e
monta uma lista de melhorias. A equipe diz se o aviso foi real ou falso e registra incidentes; o sistema aprende.

## O que é medido (por hora)

| Grupo | Indicadores |
|---|---|
| Servidor | pedidos por rota, taxa de erros 4xx e 5xx, tempo de resposta p50/p95/p99, pedidos barrados pelo limite (429) |
| Acesso | entradas, senhas erradas, entradas bloqueadas, pedidos recusados por CSRF |
| Sensores | nós com dado na hora, nós calados (vistos em 7 dias, sem dado na hora), leituras, alarmes de sensor |
| Alertas | alertas de clima enviados e com falha |
| Sincronização | conflitos (409) e erros ao gravar o estado do cliente |
| Integridade | lotes fechados e lotes que não conferem mais |
| IA | chamadas, falhas, robôs que voltaram às respostas prontas (falha ou teto), gasto na hora e no mês |
| Documentos | quantos em rascunho, em revisão, aprovados e emitidos |
| Suporte | acessos de suporte ativos e concedidos |
| Loja | compras, plataformas montadas, módulos ligados |
| Operação | idade da cópia de segurança e testes com falha na última implantação |

Por cliente e projeto: a instalação (número `PH-0000`, nunca o nome), os módulos, se foi ativada e as **lacunas de
fluxo de dados** do mapa de variáveis (`sistema/physis-variaveis.json`) para os módulos que ela tem.

As rotas são guardadas sem identificadores (`/api/emissao/:id/editar`), sem consulta e sem corpo.

## Como o sistema aprende (explicável, sem caixa-preta)

- **Anomalia:** o normal de cada hora é a mediana da mesma hora nos dias anteriores (o ciclo do dia não vira
  alarme). A distância é medida em "z robusto" (resíduos e MAD). Passou de 3,5: alerta. A tela mostra o valor, o
  esperado, o z, o tamanho da amostra e a confiança. Com menos de 8 horas de histórico: "dados insuficientes".
- **Real ou falso:** cada clique "Alerta real" / "Alarme falso" muda a chance de um alerta daquele indicador ser
  real (começa em 50%). Indicador com muitos alarmes falsos precisa de um desvio maior para avisar de novo.
- **Tendência e previsão:** reta pelas médias diárias (inclinação por dia e R²) e previsão das próximas 24 h pelo
  perfil de cada hora. Menos de 3 dias: "dados insuficientes".
- **Isto já aconteceu antes?** Ao registrar um incidente (o que houve, causa, o que resolveu), o sistema guarda
  quais indicadores estavam fora do normal nas 6 horas antes. Quando um padrão parecido aparece, ele sugere a causa
  provável e a correção usada, com a semelhança em %. "Esta sugestão ajudou" faz ela pesar mais.

## Lista de melhorias

Montada sozinha: erro 5xx que se repete (3 ou mais em 7 dias), rota lenta (p95 acima de 1.500 ms em 3 horas ou
mais), sensor que cai (3 ou mais horas sem dado nas últimas 24) e lacuna de fluxo de impacto alto num cliente.
"Virar tarefa na Gestão" cria a tarefa na lista da Gestão e marca o item no servidor (quem e quando). Quem decide é
a equipe.

## Configuração (servidor Linux)

| Variável | Para quê | Padrão |
|---|---|---|
| `PHYSIS_INDICADORES_RETENCAO_DIAS` | quantos dias de horas guardar | 400 |
| `PHYSIS_INDICADORES_LENTO_MS` | p95 que conta como rota lenta | 1500 |
| `PHYSIS_BACKUP_MARCA` | marca da última cópia (o `implantacao/backup.sh` já escreve) | `/var/backups/physis/ultimo.json` |
| `PHYSIS_TESTES_MARCA` | resultado dos testes na implantação | `/var/lib/physis/testes.json` |

A coleta roda no próprio laço do hub (a cada 5 min), sem cron e sem o Agendador do Windows. Os dados ficam no
SQLite do hub (tabelas `indicador_*`). Para gravar o resultado dos testes na implantação, o `atualizar.sh` pode
escrever, depois de rodar os testes (sugestão para o Eric; o script não foi mudado nesta rodada):

```
printf '{"quando": %s, "testes": %s, "falhas": %s}\n' "$(date +%s)" "$TOTAL" "$FALHAS" > /var/lib/physis/testes.json
```

## Medição dos pedidos

Para contar pedidos, erros e tempos, o servidor anota em cada resposta só o método, a rota normalizada, o código e
o tempo (quatro linhas em `servidor.py`, em `handle_one_request` e `send_response`). A própria tela de indicadores
não entra na conta.

## Fase 2 (não feito agora)

- **Fase 2** — "Alerta reconhecido" dos alertas de clima e de sensor: ainda não há onde a equipe marque isso
  (hoje: enviados e com falha).
- **Fase 2** — Gráficos das séries na tela (hoje: tabelas, acessíveis ao leitor de tela; a rota
  `GET /api/indicadores/serie?chave=...` já devolve a série e a previsão).
- **Fase 2** — Indicadores vindos das plataformas dos clientes (hoje: o que passa por este servidor).
- **Fase 2** — Aviso por e-mail quando uma anomalia de nota alta aparecer.
- **Fase 2** — Escrever a marca dos testes no `atualizar.sh`.
