# Integridade dos dados e banco de leitura

Princípio do núcleo do sistema, decidido em 15/11/2026 (documento 01, seção 0.1):

- **A Physis entrega** o mapeamento e a integridade dos dados.
- **O parceiro entrega** a camada de blockchain, os tokens e a custódia.
- O valor da Physis não está no blockchain, e sim em garantir que os dados que entram nele sejam **corretos, rastreáveis, auditáveis e no formato que o parceiro consome**.
- **O banco de dados da Physis existe sempre e por si só.** Ele é a fonte da verdade e pode ser lido e auditado sem blockchain. O blockchain é uma **metodologia adicional e opcional**: ele recebe só o resumo de um lote que já está guardado no banco.

A Physis não emite tokens, não guarda chaves de carteira, não faz custódia, não opera nem escolhe a rede. Nenhum nome de parceiro aparece no código ou nos documentos.

## Camadas

| Camada | Obrigatória? | O que é | Quem faz |
|---|---|---|---|
| 1. Banco de dados da Physis | **Sim, sempre** | Medições, cálculos e lotes fechados, em SQLite. Só aceita acréscimo: o banco recusa alteração e exclusão | Physis |
| 2. Banco de leitura | **Sim, sempre** | Arquivo SQLite separado, aberto só para leitura, com lotes, registros, ancoragens, a visão `integridade_leitura` e um `leia_me` | Physis (para auditor, cliente ou parceiro) |
| 3. Ancoragem adicional (ex.: blockchain) | Não, opcional | O resumo do lote registrado fora, com a referência anotada no banco | Parceiro registra; a Physis anota a referência |

Sem a camada 3, tudo continua auditável: qualquer pessoa abre o banco de leitura, refaz o SHA-256 e confere.

## Divisão de responsabilidades

| Etapa | Physis | Parceiro |
|---|---|---|
| Medir no campo | Aparelho com ID e chave próprias, calibração registrada | — |
| Validar | Faixas de validade, dado suspeito marcado, falhas de envio registradas | — |
| Calcular | Metodologia, normas e fatores versionados (17_Metodologia_e_Normas) | — |
| Mapear | Dicionário de dados: cada campo com nome, unidade, origem e definição | Informa o esquema que consome |
| Fechar e guardar o lote | Lote imutável com resumo SHA-256, gravado no banco da Physis | — |
| Disponibilizar para leitura | Exporta o banco de leitura | — |
| Ancorar (opcional) | Entrega o resumo e anota a referência | Grava na rede, emite tokens e faz a custódia |
| Auditar | O banco de leitura basta para refazer a conta | Mostra o registro na rede, quando houver |

## O que cada registro leva

- `origem`: aparelho (ID) ou cálculo, local (lote, setor ou ponto), firmware, data e hora.
- `metodo`: versão da metodologia, das normas e dos fatores de emissão; data da calibração.
- `qualidade`: válido, suspeito ou corrigido; se corrigido, `corrige` traz quem, quando, por quê, o valor e o resumo anteriores.
- `evidencias` (Fase 2): referências aos documentos e fotos guardados na plataforma.
- `lote`: identificador, período coberto, responsável, dicionário de dados, quantidade e resumo SHA-256.

Nada é apagado: uma correção gera um registro novo que aponta para o anterior. O lote fechado não muda; um erro achado depois entra num lote de correção.

## No código (feito em 15/11/2026)

`physis_hub/integridade.py`, testado em `tests/test_integridade.py` (10 testes):

- `fechar_lote` recusa registro incompleto, id repetido e dado suspeito. Grava o resumo SHA-256 do lote e de cada registro.
- `conferir_lote` refaz os resumos.
- `corrigir` cria a correção sem apagar o registro anterior.
- `preparar` cria as tabelas `integridade_lote`, `integridade_registro` e `integridade_ancoragem`. Gatilhos recusam UPDATE e DELETE. O hub chama `preparar` ao abrir o banco de cada lugar.
- `guardar_lote` só grava um lote que confere. `ler_lote` e `listar_lotes` leem do banco.
- `registrar_ancoragem` anota o método e a referência, e só para um lote já guardado.
- `exportar_banco_leitura` gera o arquivo separado, só com as tabelas de integridade (sem contas nem senhas). `abrir_leitura` abre esse arquivo sem permissão de escrita.

Ao lado disso, o hub mantém o registro encadeado de eventos (tabela `registro`). Cada linha guarda o resumo da anterior.

## Lote diário automático (feito em 15/11/2026)

- Todo dia, a partir das 3 h (fuso de Brasília), o hub fecha o lote do **dia anterior**: `integridade.lote_diario`, chamado por
  `Hub.fechar_lote_diario` dentro do laço diário que o servidor já roda (`aprendizado.rodar` → `passo_diario`, o mesmo do
  treino dos modelos). Não precisa de cron nem de timer do sistema; no Linux de produção basta o serviço do hub estar no ar.
- Entram só registros validados: as medições de `medicao` (já passaram nas faixas físicas do protocolo; o campo absurdo é
  descartado antes) e as leituras de água digitadas (pH, turbidez, cloro) que já chegaram ao servidor. O alarme de operação
  (`ok`, `baixo`, `alto`, `sem_faixa`; ex.: fator de potência abaixo de 0,92) vai junto no registro e não tira o dado do lote.
  Grandeza sem unidade no contrato fica fora (`sem_unidade_fora`).
- Lote `dia-<org>-<lugar>-<AAAA-MM-DD>`, dicionário `physis-variaveis/1` (`sistema/physis-variaveis.json`). Uma vez só por dia;
  dia sem registro não gera lote. `PHYSIS_LOTE_DIARIO=0` ou `instancia.json` `{"integridade": {"lote_diario": false}}` desligam.
- Testado com relógio falso em `tests/test_fluxo_dados.py`.

## Falta (Fase 2)

1. Ligar o lote aos outros dados: Carbono, SbN e Certificações (o Monitoramento e a água já entram no lote diário).
2. Criar as rotas no servidor e os botões "Fechar lote" e "Baixar banco de leitura" na tela.
3. Fazer o esquema de exportação no formato que o parceiro informar.
4. Conferir a ida e volta: o resumo calculado pela Physis tem de bater com o que o parceiro registrou.

Os itens 3 e 4 dependem de o parceiro informar o formato e o tipo de dado de cada token (crédito de carbono, área de SbN, água, energia).
