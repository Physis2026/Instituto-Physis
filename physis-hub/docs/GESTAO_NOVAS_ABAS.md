# Gestão Physis: partes novas (15/11/2026)

Calendário único, Editais, Eventos, Marketing e E-mails no estilo Outlook/Gmail.
Decisões de origem: `04_Respostas_e_Decisoes.md`, rodada de 14/11/2026.

## Onde está cada coisa

| Parte | Arquivo | O que é |
|---|---|---|
| Telas | `sistema/gestao-interna-physis.html`, blocos `<style id="gx-estilo">` e `<script id="gp-extras">` (no fim do arquivo) | Tudo o que a equipe vê |
| Menu e ligações | mesmo arquivo, bloco `gp-casca` (lista `ITENS`, `marcar`, `abrirAlvo`, `PhysisGestaoCasca`) | Itens novos no menu e o aviso à parte nova quando a tela muda |
| Servidor | `physis-hub/physis_hub/editais.py` | Busca de editais e eventos (com cache) e e-mail novo na fila de saída |
| Testes | `physis-hub/tests/test_editais.py` | 20 testes, todos sem internet |

## Onde os dados ficam

Tudo em chaves `gestao-physis:...` do navegador. Com o servidor, a ponte (`gestao-ponte.js`) sincroniza
sozinha (registros com `id` são juntados um a um entre as pessoas).

| Chave | Conteúdo |
|---|---|
| `gestao-physis:agenda` | Anotações do calendário e atividades com caixa de marcar (inclui as datas dos editais) |
| `gestao-physis:eventos` | Eventos cadastrados (com quem vai, lembrete, se está no calendário) |
| `gestao-physis:editais` | Editais em que alguém mexeu (guardado, aceito, recusado) e as etapas até o envio |
| `gestao-physis:mkt-conteudos` | Posts, artigos, artigo técnico e vídeo de cada semana, com aprovação e data |
| `gestao-physis:mkt-temas` | Temas com tendência, interesse, votos e nota |
| `gestao-physis:mkt-enquetes` | Enquetes de segunda e votos |
| `gestao-physis:mkt-modelos` | Nome e link dos modelos do Canva |
| `gestao-physis:mkt-metricas` | Seguidores, visualizações, contatos e clientes por rede e data |
| `gestao-physis:mail-rascunhos`, `mail-modelos`, `mail-rotulos` | Rascunhos, modelos de e-mail e rótulos |

As propostas criadas a partir de um edital entram na lista que já existe (`gestao-physis:adm-financeiro`, campo
`propostas`), com `origem: "edital"` e `editalId`.

## 1. Calendário único
- Um só calendário, mostrado em **Atividades** (acima do aplicativo), **Reuniões** (no fim) e **Eventos** (no topo).
- Junta: anotações e atividades (`agenda`), reuniões registradas, eventos marcados para o calendário (e o prazo de inscrição),
  prazos dos projetos (marcos do painel) e publicações agendadas do marketing.
- Jeito de ver: mês (tabela) ou lista dos próximos 60 dias (com as atrasadas no topo).
- Teclado: setas andam pelos dias; Home e End vão ao começo e ao fim da semana; Page Up e Page Down trocam o mês.
  Cada dia diz por voz o que tem (por exemplo "2 atividades, 1 reunião").
- Em Atividades há também a lista "Atividades com data", com caixa de marcar e o filtro "só as minhas".
- Alertas: atividades perto do prazo ou atrasadas, inscrição de evento, evento chegando, etapas de edital, conteúdo
  aguardando aprovação e a enquete de segunda entram na mesma lista de alertas do topo de Atividades.

## 2. Editais (só Rafaella, Erick Lopes e Marzia)
- **Quem vê:** a lista fica em `ACESSO_EDITAIS` no HTML e em `ACESSO_PADRAO` no servidor (ou na variável
  `PHYSIS_EDITAIS_ACESSO=rafaella,ericklopes,marzia`). O botão do menu some para as outras pessoas e o servidor responde 403.
  **Confirmar:** "Erick" foi entendido como **Erick Lopes** (`ericklopes`). Se for o Eric Oliveira, troque nos dois lugares.
- **Fontes:** FINEP, BNDES, Fundo Clima, CNPq, FAPERJ, FAPESP, FAPEMIG, FAPDF, Prosas, EMBRAPII, União Europeia, BID, BID Lab
  e Green Climate Fund. São páginas públicas. Todas estão marcadas como **"a conferir"**: os sites mudam de endereço, e a
  equipe precisa olhar uma vez se cada uma ainda lista editais. A tela "Fontes" mostra o resultado da última busca de cada
  uma e deixa acrescentar fontes novas (só endereços públicos; nada da rede interna).
- **Como o servidor lê:** RSS/Atom ou HTML (links cujo texto parece edital). Cada formato é uma função em `INTERPRETES`;
  um formato novo (por exemplo uma API em JSON) entra com `registrar_interprete`. A busca guarda o resultado por 6 horas.
- **Relevância:** regra simples, sem IA: 10 pontos por área da Physis citada, +5 se o prazo não passou, -20 se passou.
  O gancho `GANCHO_IA` (em `editais.py`) é o lugar do servidor de IA local, quando existir.
- **Fluxo:**
  1. *Para decidir* → **Aceitar** ou **Recusar** (com motivo opcional) ou guardar para depois.
  2. Ao aceitar: a pessoa confere as **datas-chave do TdR** (lidas sozinhas do texto do edital), quem cuida de cada uma,
     o **modelo da proposta** (modelo da Physis para editais, ou cópia de uma proposta que já existe) e quem dá a
     **aprovação final**. Confirmando: nasce a proposta em **Propostas** (situação Rascunho), cada data vira atividade
     com caixa de marcar e alerta, e, se houver prazo de envio, entram as etapas internas (rascunho pronto 10 dias antes,
     revisão 6, aprovação 4, autorizar e enviar 2).
  3. **Revisão da equipe:** usa a revisão que já existe nas Propostas (cada pessoa dá o próprio OK).
  4. **Aprovação final:** só a pessoa responsável, e só depois do OK de todos.
  5. **Autorizar envio:** a pessoa responsável (ou a direção), só depois da aprovação final.
  6. **Marcar como enviado** (com o número de protocolo do portal). A proposta passa a "Enviada".
- Sem o servidor (arquivo aberto no computador), dá para cadastrar à mão e seguir o mesmo fluxo.

## 3. Eventos
- Cadastro: nome, área, nacional ou internacional, formato, lugar, datas, inscrição até, link, custo, quem vai,
  lembrete (dias antes) e "pôr no calendário".
- Lista com filtros (próximos, passados, abrangência, área, busca).
- **Procurar eventos:** o servidor lê agendas públicas (Sympla, Eventbrite, ABRAVA, ABSOLAR, UNFCCC, IEA; todas "a
  conferir") e a equipe cadastra o que interessar com um clique. Há também a lista "Onde procurar".

## 4. Marketing (aprovação: Rafaella e Marzia)
- **Plano da semana:** 2 ou 3 posts com os temas de nota mais alta, um artigo (blog e LinkedIn) para cada post, um
  artigo técnico sobre um sistema da Physis (rodízio semanal) e um roteiro de vídeo curto que divulga os cursos.
  Os textos são **esqueletos por regra simples**, com colchetes para completar. Nada é inventado como fato.
- **Aprovação:** "Pedir aprovação" → Rafaella e Marzia aprovam (as duas) ou pedem ajuste. Mudar o texto depois de
  aprovado volta para rascunho. Só aprovado pode ser **agendado**; agendado aparece no calendário da equipe.
  A publicação é feita **à mão** pelas contas oficiais e marcada como publicada (nenhuma chave de rede social no sistema).
- **Agenda por rede:** tabela das próximas 6 semanas por Instagram, LinkedIn, site e YouTube.
- **Enquete de segunda:** monta o texto com os 4 temas de nota mais alta, botão **Copiar** e link
  `https://wa.me/?text=...` (o WhatsApp abre e a pessoa escolhe o grupo da equipe). Os votos anotados entram na nota.
- **Temas e nota:** 40% tendência + 30% interesse + 30% votos (cada voto vale 2, até 10) − 3 se o tema foi usado nas
  últimas 2 semanas. Tendência e interesse (0 a 10) são dados pela equipe.
- **Modelos do Canva:** nome, formato e link (os modelos continuam no Canva).
- **Métricas:** seguidores, visualizações, contatos e clientes por rede e data; gráfico de linhas simples (SVG, sem
  biblioteca de fora) com descrição para leitor de tela, e a tabela com todos os números.
- **IA local (para depois):** defina no navegador `window.PHYSIS_IA_LOCAL = { gerar: function (pedido) { return Promise<string>; } }`
  (chamando o servidor de IA da Physis). Aí aparece o botão "Melhorar com a IA local". Nenhuma IA externa é chamada.

## 5. E-mails no estilo Outlook/Gmail
- Pastas: **Caixa de saída** (pendentes e com falha da fila do servidor), **Enviados** (enviados pelo servidor ou à mão),
  **Rascunhos** e **Modelos** (5 modelos iniciais, editáveis). Busca na pasta e filtro por rótulo.
- Escrever: modelo, para (vários, separados por vírgula), assunto, texto e rótulos. O envio não deixa sair com campo
  `{entre chaves}` ainda por trocar.
- **Enviar pela fila do servidor:** `POST /api/gestao/correio` grava na tabela `email_saida` (a mesma dos e-mails de
  acesso). Com o servidor de e-mail configurado (`PHYSIS_SMTP_*`), sai sozinho; sem ele, fica pendente.
- As ações da Caixa de saída usam as rotas que já existiam: `GET /api/central/emails`,
  `POST /api/central/emails/<id>/enviado` e `POST /api/central/emails/<id>/enviar`.
- Sem o servidor: escrever, guardar rascunho e "Abrir no meu programa de e-mail" (mailto).

## Rotas novas (a colar em `servidor.py`)

O código das rotas fica em `editais.rota(...)`; no servidor entram só três trechos curtos (ver o relatório da entrega).

| Método | Rota | Quem | O que faz |
|---|---|---|---|
| GET | `/api/editais` | Rafaella, Erick Lopes, Marzia | Lista guardada (não vai à internet) |
| POST | `/api/editais/buscar` | idem | Busca nas fontes (`{"forcar": true}` ignora o cache de 6 h) |
| GET/POST | `/api/editais/fontes` | idem | Lista; acrescenta `{nome, url, formato, grupo}`; remove `{remover: id}` |
| GET | `/api/eventos` | toda a equipe com sessão | Lista guardada |
| POST | `/api/eventos/buscar` | idem | Busca nas agendas |
| GET/POST | `/api/eventos/fontes` | idem | Como nos editais |
| POST | `/api/gestao/correio` | toda a equipe com sessão | `{para, assunto, corpo}` → fila `email_saida` |

Arquivos de cache: `editais-cache.json`, `eventos-cache.json`, `editais-fontes.json`, `eventos-fontes.json`, na pasta
`PHYSIS_EDITAIS_PASTA` (padrão: pasta `editais` ao lado do banco).

## O que falta

- Colar as rotas no `servidor.py` (Eric Oliveira) e conferir, uma vez, o endereço de cada fonte padrão.
- Confirmar se o "Erick" dos editais é o Erick Lopes.
- Nomes dos cursos (o roteiro do vídeo tem `[nome do curso]`).
- Servidor de IA local: quando existir, ligar `GANCHO_IA` (servidor) e `PHYSIS_IA_LOCAL` (navegador).
- Os textos fixos de Marketing (tipos, estados, redes) ficam em português mesmo com a tela em inglês.
