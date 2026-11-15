# Documentos automáticos

Decisões de 15/11/2026: documentos saem sozinhos dos modelos e dos dados do sistema; projetos personalizados e
editais partem de um documento parecido da biblioteca; relatório formal por módulo; manual em toda compra; e
**todo documento é conferido e aprovado antes de ser emitido**.

Código: `physis_hub/documentos_auto.py` (rotas `/api/emissao/...`), modelos em `physis-hub/modelos/`,
tela na Gestão (menu **Emissão de documentos**), testes em `tests/test_documentos_auto.py`.

## Em uma frase

O sistema preenche o modelo com os dados que já tem, marca o que falta como `[MARCADOR]` e põe o documento na fila;
uma pessoa revisa, a direção aprova, e só então ele é emitido (ODT, e PDF/A quando o servidor tem LibreOffice).

## O caminho de todo documento

| Situação | Quem faz | O que acontece |
|---|---|---|
| Rascunho | o sistema ou a equipe | Gerado do modelo. A equipe completa os `[MARCADOR]` e envia para revisão. |
| Em revisão | a equipe envia | A direção lê e **aprova** ou **devolve** (com o motivo). |
| Aprovado | a direção | Fica guardado quem aprovou e quando. Mudou o texto? Volta para revisão. |
| Emitido | a equipe | Só se estiver aprovado e igual ao que foi aprovado. Depois disso não muda mais. |

- Emissão sem aprovação é **recusada** pelo servidor (há teste que prova).
- Cada passo vai para o registro encadeado do hub (quem, quando, de que situação para qual). Mudança escondida aparece.
- Antes da emissão, o arquivo baixado é uma prévia marcada **RASCUNHO**.
- Papéis: equipe gera, edita, envia e emite; só a direção aprova e devolve. As rotas exigem sessão e o token CSRF.

## Modelos e marcações

Os modelos ficam em pastas. Primeiro vale a pasta do servidor (`PHYSIS_MODELOS_PASTA`, onde entram os modelos
reais que a equipe vai mandar); depois a do repositório (`physis-hub/modelos/`, modelos de partida).

- `{{campo}}` — o sistema preenche. Exemplos: `{{cliente.nome}}`, `{{cliente.documento}}`, `{{pedido.total}}`,
  `{{pedido.modulos}}`, `{{itens_tabela}}`, `{{hoje}}`. Sem dado, vira `[MARCADOR: campo]`. Nada é inventado.
- `[MARCADOR: o que falta]` — a pessoa completa antes de aprovar. A tela mostra a lista do que falta.
- Modelo em ODT (LibreOffice) ou Markdown. No ODT, escreva a marcação inteira sem mudar a formatação no meio.

| Tipo | Modelo | Dados de |
|---|---|---|
| Proposta | `documentos/proposta` | compra da loja ou pedido |
| Contrato | `documentos/contrato` | compra da loja |
| Dados da nota fiscal | `documentos/nf` | compra + dados do prestador na configuração |
| Projeto personalizado | `documentos/consultoria` | pedido de projeto (consultoria) |
| Relatório de módulos | `relatorios/<módulo>` | dados do período |
| Manual da compra | `manual/comum` + `manual/modulos/<módulo>` | compra |

## Nota fiscal

Agora: o sistema monta os **dados** da nota (prestador, tomador, serviço, itens, valor) e eles passam pela
aprovação. Os dados do prestador vêm só da configuração do servidor (`PHYSIS_NF_RAZAO_SOCIAL`, `PHYSIS_NF_CNPJ`,
`PHYSIS_NF_INSCRICAO_MUNICIPAL`, `PHYSIS_NF_MUNICIPIO`, `PHYSIS_NF_CODIGO_SERVICO`, `PHYSIS_NF_ALIQUOTA_ISS`).
Emitir a nota no provedor é **Fase 2** (doc 21: Asaas recomendado). O ponto de encaixe é a classe `EmissorNF`;
`PHYSIS_NF_PROVEDOR=asaas` vai ligar o `EmissorAsaas` quando ele existir. Até lá, ao emitir, o sistema avisa que a
nota deve ser lançada no provedor com os dados aprovados.

## Projetos personalizados e editais: biblioteca de documentos parecidos

- Pasta no servidor: `PHYSIS_BIBLIOTECA_PASTA` (arquivos `.md`, `.txt` ou `.odt`). Para cada arquivo, um `.json`
  ao lado é opcional: `{"titulo": "...", "tipo": "edital", "setor": "agro", "porte": "medio"}`.
- "Ler a pasta da biblioteca" põe os arquivos no índice (SQLite do hub). Arquivo repetido não entra duas vezes.
- "Procurar e adaptar": o sistema acha o mais parecido (busca BM25 no texto, título com peso dobrado, mais um
  bônus para o mesmo tipo, setor e porte), e a IA (Claude, sem dados pessoais) adapta ao pedido novo, deixando
  `[MARCADOR]` onde faltar dado. Sem IA, o documento parecido entra com os requisitos no topo para adaptar à mão.
- O resultado é sempre **rascunho**. O uso da IA fica no registro (provedor, modelo, quando).

## Relatório formal por módulo

Cada módulo tem o seu modelo (`modelos/relatorios/<módulo>.md`), com a mesma identidade Physis (capa e fecho).
Um relatório de vários módulos junta os modelos **na ordem das abas da plataforma**. O botão "Baixar esta tela"
continua como está; o relatório formal é o que passa pela aprovação. A tabela de indicadores de cada módulo usa os
mesmos ids, nomes e unidades do mapa de variáveis (`sistema/physis-variaveis.json`): o campo `{{agua.leituras}}`
recebe o valor do período da variável `agua.leituras`. Sem valor, fica `[MARCADOR]`. Um teste confere que todo id
usado nos modelos existe no mapa. Módulo ainda sem variável no mapa (SustainKit, Equipamentos, Cursos) fica com `[MARCADOR]`.

## Manual de cada compra

- Quando a direção aprova uma compra (instalação montada), os rascunhos do manual, do contrato e dos dados da NF
  entram sozinhos na fila.
- O pacote do cliente (`montar.py`, `montar_clientes.py`) leva `manual/MANUAL-RASCUNHO.md` e `.odt`.
- O manual tem as seções do manual da Fazenda Santa Clara: Como validar, Apresentação, Primeiro acesso, As telas,
  Equipamentos, Alertas, Rotina, Segurança, Pontos em aberto.
- Só entram os módulos comprados: 1 módulo dá um manual curto; os 8 módulos à venda dão o manual completo.
  Toda compra leva primeiro acesso, segurança e LGPD, os alertas dos módulos, a rotina e os pontos em aberto.
- Módulos com seção própria: Monitoramento verde, Planejador, Energia solar, Qualidade da água, SustainKit,
  Certificações, SCADA e Gestão. O que não sabemos ainda está como `[MARCADOR]`.
- As seções do manual também são a base do robô Suporte para clientes (nunca a documentação técnica).

## No servidor (Linux)

- Pastas: `PHYSIS_MODELOS_PASTA` e `PHYSIS_BIBLIOTECA_PASTA` em volume persistente, com cópia de segurança.
  Arquivos em UTF-8 com fim de linha LF.
- PDF/A: LibreOffice sem tela em container (o serviço de documentos do compose), não instalado no hub. Sem ele,
  o documento é emitido em ODT e o PDF/A fica para depois.
- Ler a pasta da biblioteca é pelo botão na Gestão. Se quiserem que leia sozinho todo dia, usar o laço diário do
  hub ou um timer do systemd chamando a rota — nunca o Agendador de Tarefas do Windows.
- Os dados do prestador da NF ficam no `hub.env` (permissão 600, fora do Git).

## Fase 2 (não feito agora)

- **Fase 2** — Emitir a NF no provedor (Asaas, doc 21): `EmissorAsaas`, chave `PHYSIS_ASAAS_CHAVE` no servidor.
- **Fase 2** — Modelos reais da equipe (proposta, contrato, relatórios): hoje são modelos de partida com `[MARCADOR]`.
- **Fase 2** — Buscar sozinho no banco o valor do período de cada variável do relatório (hoje os valores entram
  em `dados` ao gerar; sem eles, ficam `[MARCADOR]`).
- **Fase 2** — Tabela de itens dentro de modelo ODT (hoje a tabela de itens sai no modelo Markdown).
- **Fase 2** — Marcação partida por formatação dentro do ODT (hoje fica sem preencher e aparece na revisão).
- **Fase 2** — Gerar sozinha a proposta quando chega um pedido de projeto (hoje: botão "Gerar" na Gestão; o
  contrato, os dados da NF e o manual já entram sozinhos na fila quando a compra é aprovada).
- **Fase 2** — Exigir duas pessoas diferentes (quem escreve não aprova); hoje a regra é o papel de direção.
- **Fase 2** — Enviar o documento emitido ao cliente pela fila de e-mail.
