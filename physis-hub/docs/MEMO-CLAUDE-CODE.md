# Memo para o Claude Code: o que falta no Sistema Physis

Data: 14/11/2026 · Versão do pacote: physis-hub 0.28 · Escrito para quem vai continuar a programação.

Este memo substitui, onde houver conflito, as instruções anteriores sobre a plataforma do cliente.
**Leia primeiro a seção 8**, que registra a segunda rodada de correções e corrige pontos das seções 2 a 4.
As seções 17 e 18 do memo de detalhamento (interface do receptor, protocolo e roteiro de hardware) continuam válidas.

## 0. Regras que valem para tudo

1. **Não inventar.** Preço, texto legal, limite técnico, nome de cliente, depoimento ou número sem fonte ficam como
   marcador entre colchetes, por exemplo `[PREÇO A DEFINIR]`. Dado de exemplo é marcado como exemplo na tela.
2. **Não alterar função nem conta dos programas da Physis** (SustainKit, SCADA, Tela do cliente, Gestão) sem pedido
   explícito. O que se muda neles é só a aparência, pelo template da seção 6.
3. **Acessibilidade em toda entrega:** teclado, foco visível, nome em cada controle, contraste AA, alvos de 44 px
   (36 px só nas ferramentas do cabeçalho), nada de rolagem lateral a 320 px, texto simples e um passo por vez.
   Zero violações no axe é o mínimo, não a meta.
4. **Paleta e logo da Physis, sem cores novas.** A lista de cores aceitas está em `docs/PALETA.md`.
5. **Sem internet nas telas.** Fontes e bibliotecas vão dentro do arquivo.
6. **A seleção de módulos existe só na loja.** A plataforma do cliente nunca mostra preço nem catálogo.
7. **Rodar a regressão antes de entregar** (seção 7) e dizer o que não foi verificado.

## 1. Mapa do repositório

| Caminho | O que é |
|---|---|
| `physis_hub/hub.py` | Núcleo do servidor local: leituras, registro, comandos, caixa central (compras, pedidos, arquivos), faturas. |
| `physis_hub/servidor.py` | Rotas HTTP. Sem dependências além do Python 3.10. |
| `physis_hub/protocolo.py` | Leitura e validação das linhas V6. |
| `physis_hub/ph_eletrodo.py` | Gestão do eletrodo de pH (P6), portado do módulo da Physis, com quatro correções documentadas no cabeçalho. |
| `physis_hub/acesso.py` | Contas, senhas e sessões. |
| `web/painel.html` | Loja (site) e plataforma do cliente, num arquivo só. Traz embutidos SustainKit, SCADA, Tela do cliente e Gestão. |
| `montar.py` | Monta o pacote de um cliente com os módulos escolhidos. |
| `tests/` | 42 testes automatizados. `estresse.py`: 10 cenários. |
| `docs/originais/ph_electrode_original.py` | O módulo de pH como a Physis enviou. Não alterar. |
| `firmware_ref/` | Firmware de referência. Não compilado nesta etapa. |

Programas da Physis, fora deste pacote (zip `physis-sistema-com-exportacao`):
`gestao-interna-physis.html` (gestão interna), `gestao-physis.html` (módulo de gestão do cliente; mesmo código, com
`data-physis-perfil="cliente"` na tag `<html>`), `physis-tela-cliente.html`, `physis-scada-demo.html`,
`SustainKit_Definitivo.html`, `physis-exportar.js` (Word, PDF e Excel sem dependências).

## 2. Estrutura atual da plataforma do cliente

Abas, nesta ordem: **Início** (perfil, lugar e equipamentos, em duas telas), **Monitoramento verde** (Irrigação,
Registros, Configuração, Diagnóstico), **Qualidade da água**, **SustainKit**, **SCADA**, **Gestão**, **Resumo**.

- Início, SCADA, Gestão e Resumo aparecem sempre. As outras dependem dos módulos comprados.
- A aba **Tela do cliente** (o programa completo, com dez seções) só aparece com o módulo de consultoria.
- Versão em branco, sem dado de exemplo: endereço `#plataforma-vazia`.
- Versão com dados de exemplo: endereço `#plataforma`.

## 3. Paridade com a programação original

### 3.1 Monitoramento verde (painel do receptor, `webpages.cpp`)

| No painel original | Na plataforma | Situação |
|---|---|---|
| Contadores online, conhecidos, irrigando, offline | Tela Irrigação | Feito |
| Contador “chuva” | Não há | **Falta** |
| Filtros todos, online, offline, irrigando, mais secos | Tela Irrigação | Feito |
| Tabela com Sensor A, Sensor B, temperatura, solo, visto | Tabela com média e limite, previsão, estado, bateria, sinal; Sensor A e B no detalhe | Parcial: falta “visto” na tabela |
| Detalhe do nó: média, ar, solo, RSSI, SNR, bateria | Detalhe do nó | Feito |
| Comandos irrigar, parar, auto, manual, ping, limiar | Detalhe do nó, com revisão antes de enviar | Feito |
| Baixar CSV | Botão “Baixar o histórico (CSV)” em Irrigação e em Registros | Feito |
| Registros: tabela de leituras, páginas, filtro por nó | Tela Registros | Feito |
| Registros: filtro por tipo | Não há | **Falta** |
| Configuração: rede TDMA (ciclo, slot, beacons, fila) | Só contagem de dispositivos e descartes | Parcial |
| Configuração: localização para previsão de chuva | Texto dizendo que fica no receptor | **Falta** |
| Configuração: esquecer nós offline | Não há | **Falta** |
| Configuração: Wi-Fi, cartão SD, arquivos | Ficam no receptor | Fora do escopo da plataforma |
| Diagnóstico | Tela Diagnóstico (teste de protocolo e saúde) | Feito, com conteúdo diferente |
| Alertas por WhatsApp (`whatsapp.cpp`) | Não há | **Falta** |
| Previsão de chuva (`weather.cpp`) | Não há | **Falta** |

### 3.2 Qualidade da água (`ph_electrode_original.py`)

| No módulo | No servidor | Na tela | Situação |
|---|---|---|---|
| Compensação por temperatura | Sim | Sim | Feito |
| Calibração versionada, validade | Sim | Sim, com formulário e histórico | Feito |
| Drift entre calibrações | Sim | Sim | Feito |
| Nota de saúde | Sim | Sim | Feito |
| Vida útil estimada | Sim (corrigida) | Sim | Feito |
| Redundância pré e pós | Sim | Só com leitura de exemplo | Parcial |
| Comparação com laboratório | Sim | Não | **Falta a tela** |
| Tempo de resposta | Sim (corrigido) | Não | **Falta a tela** |
| Leitura travada | Sim | Não | **Falta a tela** |
| Ruído elétrico | Sim | Não | **Falta a tela** |
| Download do histórico | n/a | CSV das calibrações | Feito |
| Leituras reais do eletrodo | Não há entrada | Não | **Falta: definir como o eletrodo fala com a rede** |
| Turbidez e cloro (ficha do P6) | Não | Não | **Falta: não foram enviados** |

### 3.3 SustainKit

O programa abre inteiro, com as dez abas e todas as contas. Mudou só: as duas menções a WELL saíram, e o template de
design troca cores do cabeçalho, abas, cartões e campos. **Falta:** as cores escritas dentro do JavaScript dos
resultados (por exemplo `#074031`, `#C8E6C9`) continuam as do programa; os emojis dos títulos continuam.

## 4. Tarefas, por prioridade

Cada tarefa tem: onde mexer, o que fazer e como saber que acabou.

### P0 · Segurança e rádio (antes de qualquer piloto)

- **T01 Frequência do rádio.** Onde: firmwares TX e RX. Fazer: 915,2 MHz ou acima. Aceite: constante alterada nos
  dois, compilando.
- **T02 Autenticação dos comandos de rádio e das rotas do receptor.** Onde: firmwares e `pi_client`. Aceite: comando
  sem assinatura válida é descartado; teste de reenvio falha.
- **T03 Trocar senha de Wi-Fi e chaves do `config.h`.** Aceite: nenhum segredo no repositório.
- **T04 HTTPS e limite de envios** nas rotas públicas (`/loja/`, `/api/central/*`). Aceite: teste de taxa e certificado.

### P1 · Plataforma do cliente

- **T10 Gestão do cliente em branco.** Onde: `gestao-physis.html`. Problema: o módulo abre com a equipe e os projetos
  da Physis e o título “Gestão Physis”. Fazer: com `data-physis-perfil="cliente"`, começar sem pessoas, projetos
  nem tarefas, com o nome da organização do cliente, e uma tela para cadastrar a própria equipe. Aceite: aberto num
  navegador limpo, nenhum nome da Physis aparece; a regressão `regressao.js` continua em 49 de 49 para a gestão interna.
- **T11 Início gravado no servidor.** Onde: `web/painel.html` (`perfilLer`, `perfilGravar`) e `hub.py`. Hoje fica no
  navegador. Fazer: rota `GET/POST /api/perfil`, uma linha por organização. Aceite: preencher num aparelho e ver em outro.
- **T12 Início alimentando os módulos.** Fazer: SustainKit e SCADA lerem do perfil o que já foi informado (município,
  área, equipamentos), sem pedir de novo. Depende de decisão: quais campos cada programa aceita receber.
- **T13 Resumo com números de todos os programas.** Hoje só Monitoramento, Qualidade da água, Gestão e Início enviam
  resumo. Fazer: SustainKit, SCADA e Tela do cliente publicarem um resumo curto (por `postMessage` ou
  `localStorage`). Aceite: cada cartão do Resumo mostra pelo menos um número do programa.
- **T14 Monitoramento: fechar a paridade da seção 3.1** (chuva, “visto”, filtro por tipo, TDMA, localização,
  esquecer nós). Aceite: cada linha “Falta” da tabela vira “Feito”, com teste.
- **T15 Qualidade da água: quatro telas que faltam** (laboratório, tempo de resposta, travamento, ruído), usando as
  funções já prontas em `ph_eletrodo.py`. Depende de T16.
- **T16 Entrada das leituras de pH.** Decidir com a Physis o tipo de dispositivo e os campos na linha V6
  (sugestão: `TIPO:PH`, `PH`, `T`, `VALV`). Aceite: leitura real aparece no lugar da de exemplo.
- **T17 Calibrações de pH no servidor** (hoje no navegador). Rota e tabela próprias.
- **T18 Template de design completo no SustainKit.** Trocar as cores escritas no JavaScript por variáveis e remover
  emojis dos títulos, sem tocar em fórmula. Aceite: comparar os resultados numéricos de dez entradas antes e depois;
  devem ser idênticos.
- **T19 Tela do cliente adaptável.** Hoje esconde “Resíduos” e “Certificações”. Falta decidir “Carbono” (parte
  parecida com o SustainKit) e ligar cada seção a um módulo.
- **T20 Animais com todas as telas dos firmwares** de coleira e comedouro. Não está na versão de teste.
- **T21 Telas em inglês** no `painel.html` (a gestão já é bilíngue).
- **T22 Recuperação de senha** e criação de contas pela direção.

### P2 · Gestão interna

- **T30 Desenho do protótipo de gestão interna** (menu lateral, entrada com senha por pessoa, quatro ajustes de
  conforto) aplicado ao `gestao-interna-physis.html`, mantendo todas as funções.
- **T31 Senha por pessoa.** Hoje a pessoa é a selecionada no aplicativo. A aprovação pela gestão depende disso.
- **T32 Histórico de valores, análise interna e contrato congelado** (existem no protótipo de propostas) levados à
  gestão interna.
- **T33 Dados da gestão no servidor**: propostas, contratos, receitas, fornecedores e comprovantes como tabelas, no
  formato do núcleo. Hoje ficam no navegador; comprovantes e anexos ficam fora da cópia de segurança.
- **T34 Fornecedor por organização** no `physis-esquema-2.sql`.
- **T35 Assistente de propostas no servidor** (hoje só no protótipo publicado).

### P3 · Loja e servidor

- **T40 Provedor de pagamento.** Depende de escolha da Physis. A confirmação do pagamento tem de vir do provedor.
  Trocar `PAGAMENTO_TESTE` para `false` e voltar a bloquear item sob consulta.
- **T41 Envio de e-mail** (pedido de proposta, aviso à direção). Depende do endereço de propostas.
- **T42 Envio dos dados do Hub do cliente ao servidor Physis** (a fila já existe em `hub.fila_envio`).
- **T43 Página de suporte interno**, conforme o esboço aprovado, com consentimento e prazo.
- **T44 Canal de barreira de acessibilidade** (e-mail e formulário).
- **T45 Página pública da loja**, com as demos e as páginas “em desenvolvimento”.

### P4 · Documentos

- **T50 PDF marcado para leitor de tela** em `physis-exportar.js`.
- **T51 Dados da Physis, validade e condições de pagamento** nos documentos (hoje marcadores).
- **T52 Cláusulas do contrato e textos legais.** Só depois da assessoria jurídica.

### P5 · Verificação com pessoas e equipamento

- **T60** Leitor de tela real. **T61** Pessoas neurodivergentes e PcD. **T62** Celular de verdade.
- **T63** Roteiro de 12 passos no hardware (memo de detalhamento, seção 18). **T64** Calibração do sensor de solo.

## 5. Decisões que a Physis ainda precisa tomar

Não programar antes da resposta: preços e validade; valores de viagem por zona; provedor de pagamento; licença do
código; quem atende o suporte; quatro dúvidas do pH (cabeçalho de `ph_eletrodo.py`); se “Carbono” fica na Tela do
cliente; se o Diagnóstico aparece para o cliente; quais campos do Início cada programa recebe; se a água é de
irrigação, potável e de reúso, ou as três.

## 6. Template de design Physis para os programas

Em `web/painel.html`, objeto `TEMPLATE_PROG`. É uma folha de estilo aplicada por cima do programa, sem tocar no
código dele. Regras: fundo `#F4F6F1`, superfície `#FFFFFF`, texto `#1C2B21`, secundário `#4A4F44`, ação `#33512F`,
marca `#4B7547`, linha `#C9D2C4`, areia `#B9A97F` e `#EFE8D6`; aba ativa em `#1C2B21`; campos brancos com borda
`#8A9284`; foco de 3 px em `#33512F`. O cabeçalho próprio do programa (`.px-faixa`) fica escondido dentro da
plataforma, para o logo não aparecer duas vezes.

## 7. Como rodar a regressão

```
python3 -m unittest discover -s tests        # 42 testes
python3 estresse.py                          # 10 cenários
node testes/regressao.js                     # regressão da Physis: 49 verificações
```

A regressão de tela usa Playwright e axe: abre a loja, compra, entra na plataforma e passa por todas as abas e
telas, em fundo branco e verde, com as preferências de acessibilidade ligadas e desligadas, a 1280 e a 320 px.
Em 14/11/2026: 250 estados, 0 violações. Ela não entra dentro dos programas embutidos.

## 8. Segunda rodada de correções (14/11/2026)

Onde esta seção contradiz as anteriores, vale esta.

### 8.1 O que mudou

- **Loja zerada.** Nada vem marcado. A plataforma de exemplo é fixa (`EXEMPLO` em `web/painel.html`): SustainKit completo, Kit Monitoramento e Qualidade da água. Endereços `#plataforma` e `#plataforma-vazia`.
- **Valores.** Posicionados a 75% da faixa de referência, dólar a R$ 5,00 (`METODO_PRECO`). Continuam como estimativa até a Physis confirmar.
- **Projeto personalizado.** Nove áreas opcionais (`AREAS_PED`); seguem no pedido (`areas`) e entram na observação da proposta.
- **Recibo.** Padrão de loja online: confirmação, itens, próximos passos e sugestões de outros produtos. Controles de simulação dentro de um quadro “Só nesta versão de teste”.
- **“Baixar esta tela”.** Função `mostraBaixar()`: só no recibo, Início, Monitoramento (menos Diagnóstico), Qualidade da água, Gestão e Resumo.
- **Início.** Instalação elétrica (tensão, FP, capacitores, circuitos) e histórico de 12 a 24 meses (contas anexadas em IndexedDB, importação de CSV, dois gráficos).
- **Qualidade da água.** Leituras (digitadas, CSV ou exemplo), turbidez e cloro com limites de quem usa, leitura travada, ruído, tempo de resposta e laboratório. As funções `anTravamento`, `anRuido`, `anResposta`, `anRedundancia` e `anLaboratorio` espelham `ph_eletrodo.py`; a paridade do tempo de resposta e do travamento foi conferida.
- **Gestão do cliente.** Não é mais o programa embutido. É nativa (`telaGestao`, `G_SEC`, `G_SIS`), nasce em branco e guarda em `physis-gestao-cliente`. **A tarefa T10 está resolvida por este caminho.**
- **Resumo.** `alertasTodos()` e `mediasTodas()` juntam Monitoramento, Qualidade da água, Gestão e Início.
- **Programas embutidos.** SustainKit só com o título; SCADA com o título “SCADA” (troca de texto feita na cópia embutida, em `montarQuadros`).
- **Fundo verde.** Logo branco por filtro CSS.
- **Gestão interna.** Cada atividade tem modelo `consultoria` ou `parceria`. Parceria: `contaParceria()` = (receita do módulo − 20% − custos) ÷ 2.

### 8.2 Tarefas novas

- **T70 Cursos.** Não existe nada. Decisão registrada da Physis: começar numa plataforma de cursos pronta. Fazer, nesta ordem: (a) cursos como itens da loja, com a mesma conta; (b) aba “Cursos” na plataforma que abre o curso comprado na plataforma externa; (c) só depois, avaliar trazer o conteúdo para dentro. Não construir reprodutor de vídeo, provas nem certificados antes dessa decisão. Cursos com menores exigem consulta jurídica antes.
- **T71 Página de produto com 11 blocos**, um projeto por página.
- **T72 Aba de preço automático de projetos personalizados** na gestão interna.
- **T73 Fechamento da parceria**: recalcular a parte do parceiro com os custos realmente lançados no projeto, depois da quitação.
- **T74 Modelagem financeira na Gestão do cliente** (hoje só totais). Depende de a Physis dizer quais modelos.
- **T75 Sistemas de gestão**: trocar as listas de apoio pelos requisitos que a Physis usa em cada norma. Não copiar texto de norma.
- **T76 Gestão do cliente e Início no servidor** (junta T11): rotas e tabelas por organização.
- **T77 Leitura automática de contas** de água e de luz a partir do PDF anexado.
- **T78 SCADA**: incluir os outros sistemas de supervisão quando a Physis enviar; nos arquivos atuais só há um programa.
- **T79 Rascunho de termos, privacidade, garantia e suporte, e a lista de perguntas jurídicas.**
- **T80 Canal de contato e de sugestões** na loja e na plataforma.
- **T81 Regressão de tela em quatro partes**: passou de cinco minutos. Rodar as dez combinações em fatias (0–3, 3–6, 6–8, 8–10).

### 8.3 Estado da regressão

42 testes do servidor, 10 cenários de estresse, 49 verificações da regressão da Physis e 350 estados de tela sem violação.

## 9. Duas edições e as revisões externas (14/11/2026)

### 9.1 Duas edições

- **Sistema simplificado:** Início, os módulos comprados e Resumo.
- **Sistema com gestão e SCADA:** o mesmo, mais as abas SCADA e Gestão.

A diferença é só a lista de módulos da instância: `supervisao` liga a aba SCADA e `gestao` liga a aba Gestão (`A.sup` e `A.ges` em `abasAtivas`). Na loja, “Supervisão” e “Gestão da organização” são itens do catálogo; a Gestão está sem preço.
Endereços de demonstração: `#plataforma-simples`, `#plataforma`, e os dois com `-vazia` no fim.

    python3 montar.py --org cliente --modulos monitoramento,agua,sustainkit --sustainkit <arquivo>                      # simplificado
    python3 montar.py --org cliente --modulos monitoramento,agua,sustainkit,supervisao,gestao --sustainkit <arquivo> --supervisao <arquivo>   # completo

`--gestao` agora só serve ao pacote interno da Physis (programa de gestão interna). A Gestão do cliente é nativa.

### 9.2 Revisões externas: o que adotar

Três relatórios externos foram conferidos contra o código. Parte descreve uma versão antiga (Gestão embutida, aba de água sem pH). Adotar, nesta ordem:

- **T90** `interpretar` deve recusar `TIPO` desconhecido em vez de tratar como SOLO; conferir o mesmo em `protocolo.py`. Teste com `TIPO:XYZ`.
- **T91** Validar faixas de `BAT`, `RSSI` e `SNR`. As faixas precisam vir da Physis; não inventar.
- **T92** Poda da lista `vistos` no hub em memória da página.
- **T93** Pausar a atualização com a aba oculta (`visibilitychange`) e dar tempo limite ao `fetch`.
- **T94** Repassar as preferências de acessibilidade aos programas embutidos (classe no `body` do quadro, pelo mesmo caminho de `aplicarTemplate`).
- **T95** “Modo calma” não esconde o desenho do mapa; “modo foco” não esconde o “ao vivo”. Reduzir, não remover.
- **T96** Ponte campo → auditoria: cada leitura V6 gera uma medição com origem identificada.
- **T97** Mesmos casos de teste do protocolo no Python e no JavaScript.
- **T98** Política de segurança de conteúdo e `sandbox` nos quadros, junto com a hospedagem.
- **T99** Programas como arquivos separados servidos pelo hub, com versão e hash; página hospedeira sem texto codificado.
- **T100** Registrar erros em vez de engolir (26 blocos `catch` vazios).
- **T101** Aviso de finalidade, prazo de guarda e “apagar meus dados”.
- **T102** Campo `origem` (medido, digitado, exemplo) em todo registro exportado.

**Não adotar agora:** reescrever SustainKit e SCADA num aplicativo único (contraria a regra de manter funções e contas); tema escuro automático; metas de pontuação de ferramentas; trocar a base por React e empacotador.

**Água, relatório da Fazenda Santa Clara:** a revisão lista diferença de pH com atraso de mistura, condutividade, indicador de filtro, vazamento por vazão noturna, proteção de bomba por corrente, modos de operação e registro de laudo. Nada disso existe. Os limites e fórmulas citados vêm de um documento que não está no repositório: **não implementar a partir do resumo; pedir o relatório.**

## 10. Terceira e quarta rodadas (14/11/2026)

O registro completo está em `docs/LISTA-DE-MODIFICACOES.md` (31 itens). O que muda para quem programa:

- **Tarefas resolvidas:** T90 (tipo desconhecido), T91 (faixas, com limites largos de plausibilidade em `FAIXAS_PLAUSIVEIS`), T92 (poda), T93 (aba oculta), T94 (preferências dentro dos programas, `repassarPrefs`), T95 (modos que escondiam), T98 em parte (cabeçalhos em `servidor.py`), T74 em parte (`investimento.py` e `analiseInvest`).
- **Módulos novos no servidor:** `physis_hub/agua.py` (atraso de mistura, diferença de pH, vazão noturna, filtro, bomba, modo automático, queda de energia) e `physis_hub/investimento.py`. As funções de mesmo papel em `web/painel.html` são espelhos; qualquer mudança vale nos dois, com teste.
- **Regra da água:** nenhum limite vem de fábrica, e limite provisório não gera alerta (`confirmado`, `achadosAgua`, `alertasAgua`). Não trocar por valores fixos.
- **Três sistemas separados:** plataforma do cliente, central de clientes (só desenho) e Gestão Physis. Não juntar a central de clientes ao financeiro.

### Tarefas novas

- **T110 Central de clientes**, conforme o desenho aprovado: interface própria, só técnica, sem propostas, contratos nem financeiro. Depende do servidor da Physis e da ponte de suporte.
- **T111 Ponte de suporte**: botão “Permitir suporte” com prazo no servidor do cliente, ligação de saída, nada guardado na Physis, registro de cada acesso.
- **T112 Cursos**, conforme os três desenhos aprovados (substitui T70): assunto “Cursos” na loja; aba “Cursos” na plataforma com progresso e certificado; “Cursos e turmas” na Gestão Physis. Faltam nomes, cargas, preços e a plataforma de cursos.
- **T113 Módulo “Sistemas de gestão”**, que saiu da Gestão do cliente e está na loja como próximo módulo.
- **T114 Produtos acrescentados pela loja** (`physis-loja-produtos`) guardados no servidor.
- **T115 Água:** leitura do controlador de irrigação e valor em reais da diferença de pH. Só com o relatório da Fazenda Santa Clara.
- **T116 Conferir os dígitos do CPF e do CNPJ** (hoje só a quantidade de números).
- **T117 Fundo verde dentro dos programas embutidos.**

## 11. Fechamento de 14/11/2026

### 11.1 O que mudou por último

- **Gestão Physis com menu lateral.** Uma casca (`<style id="gp-estilo">` e `<script id="gp-casca">`, no fim de `gestao-interna-physis.html`) põe o menu do desenho aprovado por cima do programa: Atividades, Mapa da equipe e Direção (as três telas do aplicativo original, que a casca abre apertando os botões do próprio aplicativo: `telaDoApp`), Tarefas e projetos, Propostas, Contratos, Financeiro, Fornecedores, Alertas, Cursos e Meus contratos. A casca só navega: abre o painel administrativo na aba certa e esconde as abas dos outros grupos. “Quem está usando” fica no menu e comanda o seletor do aplicativo. A Gestão Physis não tem atalho para o SCADA nem para o Painel do cliente: são outros sistemas. Não vale para o perfil `cliente`.
- **Compra guardada.** Na demonstração, a loja abre sempre no catálogo; compra de teste antiga é apagada (`VERSAO_COMPRA`). Com servidor, a compra só é retomada se for da versão atual.
- **Obrigatórios.** CPF ou CNPJ, nome, e-mail e telefone no pagamento e no pedido personalizado. No Início, CEP obrigatório; nome, e-mail, telefone e nome do lugar opcionais.

### 11.2 Os quatro programas internos

| Arquivo | O que é | Estado |
|---|---|---|
| `gestao-interna-physis.html` | Gestão Physis | Funções completas até aqui; casca nova; por dentro, visual antigo; sem senha por pessoa; dados no navegador |
| `physis-tela-cliente.html` | Tela do cliente (consultoria) | Como a Physis enviou, com exportação; aparece só com o módulo de consultoria |
| `physis-scada-demo.html` | SCADA | Como a Physis enviou; dados simulados |
| `SustainKit_Definitivo.html` | SustainKit | Como a Physis enviou, sem as duas menções a WELL |

### 11.3 Tarefas novas

- **T120 Visual interno da Gestão Physis.** A casca está pronta; falta levar o Padrão Physis para dentro de cada parte (formulários e tabelas do painel administrativo), sem tirar função. Aceite: os testes de proposta, consultores, parceria e comprovantes continuam passando.
- **T121 Gestão Physis no servidor**, com senha por pessoa (junta T31 e T33). É o que falta para guardar dado financeiro real.
- **T122 Levar ao painel da Gestão Physis** o histórico de valores, a análise interna e o contrato congelado do protótipo de propostas (T32).
- **T123 Cursos e turmas** na Gestão Physis, conforme o desenho aprovado (parte de T112).
- **T124 Decidir** se “Tarefas e projetos” e “Meus contratos” ficam como itens do menu ou dentro de Atividades e Contratos.

### 11.4 Ordem sugerida de trabalho

1. T121 (servidor e senha da Gestão Physis) e HTTPS: sem isso, nada de dado real.
2. T76 e T114 (Início, Gestão do cliente e produtos da loja no servidor).
3. T14 (paridade do Monitoramento verde) e T16 (sensores de água na rede).
4. T110 e T111 (Central de clientes e ponte de suporte).
5. T112 (cursos), quando houver nomes, preços e plataforma.
6. T120 (visual interno) e T99 (programas como arquivos separados).
7. T01 a T03 (rádio) antes de qualquer piloto com equipamento.

## 12. Inglês (14/11/2026)

**Como funciona no Modelo 1.** A tela é desenhada em português e traduzida por cima: `I18N` (texto exato → inglês) e `I18N_RX` (padrões com números), em `web/painel.html`. `traduzirTudo()` percorre os textos e os atributos `aria-label`, `placeholder` e `title`; um observador repete a tradução a cada mudança da tela. O que não tem par fica em português. O idioma fica em `physis-idioma` e é repassado aos programas embutidos (`idiomaNosProgramas`).

**Cobertura** (segunda rodada, 976 textos e 103 padrões). Uma varredura por todas as telas, partes, mensagens de erro e ajustes abertos encontrou 30 textos sem par em inglês, e todos são nomes próprios, unidades ou dados (por exemplo “SustainKit”, “SCADA”, “nov/25”, “0,3 bar”). A lista está em `docs/i18n-faltando.json`. O único texto corrido que ficou em português são as notas de “Referência de mercado” da edição do catálogo, de uso interno.

**Tarefas**

- **T130 Manter a tradução em dia.** Todo texto novo em português precisa do par em `I18N` ou `I18N_RX`; rodar a varredura (`i18n-faltando.json`) antes de entregar. Falta revisar o inglês com alguém da área (termos de irrigação, elétrica e contabilidade) e traduzir as notas de referência de mercado.
- **T131 Números e datas em inglês.** Hoje continuam no formato brasileiro (R$ 57.700; 14/11/2026).
- **T132 Arquivos baixados em inglês** (Word, PDF, Excel e CSV): saem com os textos da tela no momento, mas cabeçalhos de CSV são fixos em português.
- **T133 SustainKit em inglês.** O programa só existe em português.
- **T134 Painel administrativo da Gestão Physis.** O aplicativo e o menu trocam de idioma na hora; o painel administrativo só troca ao recarregar a página.
- **T135 Trocar a tradução por cima por textos escolhidos na hora de desenhar** (uma função `t()`), quando houver tempo: é mais robusto e não depende de o texto em português ser idêntico.

## 13. Reuniões e documentos internos (14/11/2026)

Duas partes nativas da casca da Gestão Physis (`pintarReunioes`, `pintarDocs`, no `<script id="gp-casca">`):

- **Reuniões e transcrições** (`gestao-physis:reunioes` em localStorage): data, assunto, projeto, participantes, notas, transcrição, encaminhamentos e um arquivo anexo. Arquivo de texto (.txt, .vtt, .srt, .md) é lido para a caixa da transcrição.
- **Documentos internos** (`gestao-physis:documentos` para a lista; os arquivos em IndexedDB `gestao-physis-arquivos`): categoria, projeto, observação, quem enviou, filtro, busca, download e exclusão. Limite de 20 MB por arquivo.

Tudo fica no navegador e **fora da cópia de segurança**.

**Tarefas**

- **T140** Guardar reuniões e documentos no servidor, com permissão por pessoa (junta T121). Documento interno não pode depender do navegador.
- **T141** Transformar encaminhamentos em tarefas das Atividades, com responsável e prazo.
- **T142** Transcrição automática de áudio e resumo da chamada. Depende de escolher o serviço e de consentimento dos participantes.
- **T143** Incluir reuniões e documentos na cópia de segurança.

