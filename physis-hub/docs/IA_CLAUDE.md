# IA Claude nos robôs da Physis

Decisão de 15/11/2026: incluir o Claude agora, com a conta da Physis; o que não deu para fazer fica marcado como
**Fase 2**; aqui estão os detalhes para o Eric fazer a manutenção e a expectativa de custos.

Código: `physis_hub/ia_claude.py` (o Claude) e `physis_hub/robos.py` (a ordem de quem responde).
Testes: `tests/test_ia_claude.py` (servidor falso, sem internet) e `tests/test_robos.py`.

## Em uma frase

Quando o hub tem a chave da Physis, os robôs pedem ao Claude para escrever a resposta melhor; se o Claude não
estiver configurado, falhar, demorar ou o gasto do mês chegar no teto, o robô responde do jeito de antes (respostas
prontas por regras). Nada quebra sem o Claude.

## O que já está pronto (agora)

- **Ordem de quem responde:** Claude (se tiver chave) → servidor de IA local (Fase 2, se `PHYSIS_IA_URL` existir)
  → respostas prontas por regras.
- **Robôs que usam o Claude:** Suporte (melhora a resposta citando a documentação), Preços das propostas (explica
  o que está fora da faixa), Editais (resumo e encaixe com a Physis) e Instituto (melhora o roteiro de projeto).
  Marketing e Pluviômetro continuam só com regras.
- **Chave só no servidor:** lida de arquivo ou variável de ambiente; nunca no código, nunca no log, nunca vai ao
  navegador (a resposta do robô leva só o nome do modelo e o custo).
- **Modelo configurável:** padrão `claude-opus-5-5` (o recomendado pela documentação da Anthropic em 11/2026).
- **Tempo máximo** por chamada (60 s) e **teto de gasto por mês** (US$ 25). Passou do teto: o Claude não é
  chamado e o robô responde por regras até virar o mês.
- **LGPD:** antes de enviar, saem e-mail, CPF, CNPJ, telefone, CEP, coordenadas, links e nomes informados (viram
  `[e-mail]`, `[CPF]`...). Para cada chamada fica anotado **quantos** dados de cada tipo saíram, nunca o texto.
- **Sempre revisão humana:** toda resposta do Claude vem com `gerado_por_ia: true`, `revisao_humana: true` e o aviso
  no fim do texto: "Texto gerado com IA (Claude). É sugestão...". Preço de proposta e encaixe de edital são só
  sugestão (`dados.sugestao: true`).
- **Recusa do Claude:** se o Claude recusar um pedido, a Anthropic tenta outro modelo sozinha (reserva
  automática, `fallbacks: "default"`). Para desligar: `PHYSIS_CLAUDE_RESERVA=0`.

## Fase 2 (não feito agora)

- **Fase 2** — Servidor de IA local da Physis (o encaixe já existe: `PHYSIS_IA_URL`; falta a máquina e o modelo).
- **Fase 2** — Tela no painel com o gasto do mês e o teto (hoje o Eric lê o arquivo do contador ou o Console da
  Anthropic). A função `IAClaude.estado()` já devolve os números, sem a chave.
- **Fase 2** — Aviso por e-mail quando o gasto passar de 80% do teto.
- **Fase 2** — Teto por robô (hoje o teto é um só para todos).
- **Fase 2** — Cache de prompt da Anthropic para baratear o Suporte (precisa medir antes; o material muda a cada pergunta).
- **Fase 2** — Teste automático com a chave real (hoje os testes usam um servidor falso, sem internet).
- **Fase 2** — Tirar nomes de pessoas que não foram informados ao robô (hoje só sai o nome que o sistema conhece;
  um nome solto no meio de um texto livre pode passar).
- **Fase 2** — Ligar o `docs/ROBOS.md` a este documento (não mexi nele para não conflitar com outras mudanças).

## Passo a passo para o Eric

### 1. Criar a chave na organização da Physis

1. Entrar no Console da Anthropic (platform.claude.com) com a conta da **organização da Physis** — não uma conta
   pessoal. [CONFERIR o caminho dos menus]
2. Criar um *workspace* só para o hub (ex.: `physis-hub`), para o gasto do hub aparecer separado. [CONFERIR]
3. Em **API keys**, criar uma chave nesse workspace com nome claro: `physis-hub-AAAA-MM`.
4. Copiar a chave **uma vez** direto para o arquivo do servidor (passo 2). Não mandar por WhatsApp, e-mail ou chat.

### 2. Onde pôr a chave no servidor

Preferido — arquivo protegido:

```
# no servidor, fora da pasta do código
servicos/env/claude.key                    (só a chave, uma linha; permissão só para o usuário do hub)
# em servicos/env/hub.env
PHYSIS_CLAUDE_CHAVE_ARQUIVO=/run/secrets/claude.key     (ou o caminho do arquivo dentro do container)
PHYSIS_CLAUDE_MODELO=claude-opus-5-5
PHYSIS_CLAUDE_TETO_USD=25
PHYSIS_CLAUDE_TEMPO=60
PHYSIS_CLAUDE_CONSUMO=/dados/ia_claude_consumo.json     (pasta que sobrevive ao reinício do container)
```

Alternativa: `PHYSIS_CLAUDE_CHAVE=...` (ou `ANTHROPIC_API_KEY=...`) no `hub.env`. O `.gitignore` já impede `.env`
e `*.key` de irem ao Git, mas confira antes de qualquer commit.

Atenção: **não** use `PHYSIS_IA_CHAVE` para o Claude — essa variável é a senha do servidor de IA local e seria
mandada para ele.

Depois, reiniciar o hub (`docker compose restart hub`). A chave é lida na partida.

### 3. Trocar a chave (rotação) — a cada 90 dias ou se vazar

1. Criar a chave nova no Console (passo 1), com o mês no nome.
2. Trocar o conteúdo de `claude.key` e reiniciar o hub.
3. Fazer uma pergunta ao robô Suporte e ver no log `ia_claude ... ok=True`.
4. Só então **desativar a chave antiga** no Console.
Se vazou: desativar a chave na hora (passo 4 primeiro); os robôs seguem por regras até a nova entrar.

### 4. Ler o uso

- **No hub:** o arquivo `ia_claude_consumo.json` tem o mês, `gasto_usd`, `chamadas`, `falhas`, `bloqueadas_teto`,
  tokens e os últimos 200 envios (robô, modelo, tokens, custo, dados pessoais tirados — sem texto). O log tem uma
  linha `ia_claude robo=... custo=...` por chamada.
- **Na Anthropic:** páginas de uso e custo do Console (filtrar pelo workspace `physis-hub`). Existe também a
  Usage and Cost Analytics API (beta, precisa de chave de administrador). [CONFERIR]
- O gasto do hub é uma **estimativa** pela tabela de preços; a fatura da Anthropic é o valor oficial.

### 5. Ajustar o teto

- `PHYSIS_CLAUDE_TETO_USD=25` no `hub.env` e reiniciar. `0` desliga o Claude.
- O hub para **antes** de passar do teto: só chama o Claude se o gasto do mês mais o pior caso da chamada
  couber no teto.
- No Console, conferir se a organização tem limite de gasto próprio; segundo a documentação, em organizações do
  Console isso pode estar só em prévia. O teto que sempre vale é o do hub. [CONFERIR]

## Expectativa de custos

**Estimativa**, não orçamento. Preços da tabela da documentação da Anthropic (skill `claude-api`, tabela de
**03/11/2026**), em US$ por 1 milhão de tokens. **[CONFERIR na página de preços da Anthropic antes de usar]**

| Modelo | Entrada | Saída |
|---|---|---|
| `claude-opus-5-5` (padrão) | 4,00 | 20,00 |
| `claude-sonnet-5-5` | 2,00 | 10,00 |
| `claude-haiku-5-5` | 0,10 | 0,50 (até 100 mil tokens de entrada) |

**Fórmula por robô:** custo/mês = chamadas/mês × (tokens de entrada × preço de entrada + tokens de saída × preço de
saída) ÷ 1.000.000. A saída inclui o raciocínio do modelo (no Opus 5.5 ele está sempre ligado; usamos esforço
`low` para gastar menos).

Premissas (suposições nossas, a medir no 1º mês pelo contador):

| Robô | Entrada/chamada | Saída/chamada | Chamadas/mês | Custo/chamada (Opus 5.5) | Custo/mês (Opus 5.5) |
|---|---|---|---|---|---|
| Suporte | 2.000 | 1.000 | 300 | 0,008 + 0,020 = US$ 0,028 | US$ 8,40 |
| Preços das propostas | 3.000 | 1.500 | 100 | 0,012 + 0,030 = US$ 0,042 | US$ 4,20 |
| Editais (resumo e encaixe) | 6.000 | 2.000 | 60 | 0,024 + 0,040 = US$ 0,064 | US$ 3,84 |
| Instituto (roteiro) | 3.000 | 3.000 | 20 | 0,012 + 0,060 = US$ 0,072 | US$ 1,44 |
| **Total** | | | **480** | | **≈ US$ 17,88/mês** |

Com as mesmas premissas: `claude-sonnet-5-5` ≈ US$ 8,94/mês (metade dos preços do Opus 5.5) e
`claude-haiku-5-5` ≈ US$ 0,45/mês (1/40). São contas grosseiras: modelos diferentes gastam quantidades diferentes de
tokens de raciocínio. Recusas atendidas pela reserva automática são cobradas pelo preço do outro modelo.

O teto padrão de US$ 25/mês dá folga de ~40% sobre a estimativa. Valor em reais: multiplicar pelo câmbio do dia
da fatura. [CONFERIR]

## Item para a lista do Eric (copiar para `10_Perguntas_Eric_Infraestrutura.md`)

> **IA Claude nos robôs (15/11/2026)** — Criar no Console da Anthropic, na organização da Physis, um workspace
> `physis-hub` e uma chave `physis-hub-AAAA-MM`; gravar a chave em `servicos/env/claude.key` (fora do Git) e pôr
> `PHYSIS_CLAUDE_CHAVE_ARQUIVO`, `PHYSIS_CLAUDE_TETO_USD=25` e `PHYSIS_CLAUDE_CONSUMO` (pasta persistente) no
> `hub.env`; reiniciar o hub e testar o robô Suporte. Combinar: quem recebe o alerta de gasto, rotação da chave a
> cada 90 dias, e se o teto de US$ 25/mês está bom (estimativa ≈ US$ 17,88/mês com Opus 5.5 — [CONFERIR] preços
> de 03/11/2026). Guia: `physis-hub/docs/IA_CLAUDE.md`.
