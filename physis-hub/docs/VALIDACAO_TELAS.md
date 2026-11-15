# Validação das telas · 15/11/2026

Validação final do front-end: cada tela × idioma (PT, EN) × tema (claro, escuro) × largura (computador 1280 px, celular 375 px).

## Resumo

| | Quantidade |
|---|---|
| Telas diferentes conferidas | 146 (plataforma 48, loja 2, SustainKit 11, Planejador 11, SCADA 6, Gestão Physis 21, Consultoria 5, demonstrações 36, páginas do servidor 6) |
| Conferências (tela × combinação) | cerca de 1.100 |
| Problemas encontrados | 14 |
| Corrigidos | 14 |
| Lacunas abertas (precisam de decisão ou de trabalho maior) | 9 |
| Testes do servidor | 793 testes, OK (8 pulados) |

## Como foi feito

1. Servidor estático em `http://127.0.0.1:8871` (a pasta do repositório) e o servidor real da Physis numa pasta temporária (porta 8711, com a loja de teste publicada com os 8 módulos à venda).
2. Para cada combinação, a escolha foi gravada em `physis-pref` (`idioma`, `tema`) e `physis-pref-tema`, e a página recarregada. A largura de 375 px foi simulada no navegador.
3. Um roteiro no navegador abriu cada aba, subaba, bloco, etapa ou item de menu e conferiu:
   - **um título só**: exatamente um `h1` visível, contando também os `h1` dentro dos quadros (programas abertos dentro da plataforma);
   - **uma barra de preferências só**: a barra `#pxp-barra` visível uma vez, com os 4 controles `pp-idioma`, `pp-tema`, `pp-conforto`, `pp-a11y`, e nenhuma barra dentro dos quadros;
   - **sem rolagem lateral**: `scrollWidth` da página e de cada quadro não passa da largura da janela, e nenhum elemento passa da borda;
   - **sem português no inglês**: `PhysisPreferencias.faltando()` (SustainKit, Consultoria, Planejador) e, nas telas que se traduzem sozinhas (plataforma, Gestão, SCADA), todo texto visível e todo `aria-label`, `title` e `placeholder` com cara de português;
   - **troca de idioma**: PT → EN → PT na plataforma e no SCADA (sem recarregar) e na Gestão (recarrega) volta ao mesmo leiaute, sem estilo antigo.
4. Fotos de tela em claro e escuro, no computador e no celular, de cada página, para conferir o modelo visual (faixa Physis com o logo, fontes, cartões, botões).
5. A plataforma com **todas as abas, inclusive as em desenvolvimento**, foi aberta pela demonstração `demos/physis-demo-cliente.html` com o modo pesquisa ligado (`ui.inst.pesquisa = true`), que mostra as mesmas abas da instalação Casa Physis: 25 abas e 23 subabas.

## Resultado por tela

`ok` = tudo certo. Número entre colchetes = problema da lista abaixo (corrigido) ou lacuna aberta (L).

| Tela | PT claro 1280 | PT claro 375 | PT escuro 1280 | PT escuro 375 | EN claro 1280 | EN claro 375 | EN escuro 1280 | EN escuro 375 |
|---|---|---|---|---|---|---|---|---|
| **Plataforma** (demonstração com modo pesquisa): Início (Perfil, Lugar), Mapeamento, Planejador, SustainKit, Energia solar, Qualidade da água, Monitoramento verde (Painel, Registros, Configuração, Diagnóstico), Caixinha IoT, SCADA, Resumo, Gestão (Plano, Compras, Manutenção, Produção, Fatores, Indicadores, Relatório, Suporte Physis), Cursos | ok | ok | ok | ok | ok [2] [4] [5] | ok [2] [4] [5] | ok [2] [4] [5] | ok [2] [4] [5] |
| Plataforma · Planejador (demonstração) | ok [1] | ok [1] | ok [1] | ok [1] | ok [1] | ok [1] | ok [1] | ok [1] |
| Plataforma · Certificações (visão geral + 13 subabas) | ok | ok | ok | ok | ok [3] [4] | ok [3] [4] | ok [3] [4] | ok [3] [4] |
| Plataforma · abas em desenvolvimento: Em desenvolvimento, Registro, Teste, AVAC, Servidor verde, Turbinas, SbN, Economia circular, Carbono, Resiliência, Secador, Saúde | ok | ok | ok | ok | L3 | L3 | L3 | L3 |
| Loja pública `/loja/` (servidor): só os 8 módulos à venda (11 itens) + "Experimente agora" | — | ok | — | — | — | — | ok [6] | — |
| Loja `/loja/?item=scada` (servidor): rola, destaca, põe na seleção e avisa | — | ok | — | — | — | — | — | — |
| Loja como arquivo (`painel.html`) | ok | ok [12] | ok | ok | ok | ok | ok [12] | ok |
| SustainKit (11 blocos) | ok | ok | ok | ok | ok | ok | ok | ok (L6) |
| Planejador (7 etapas + Conferências, Assistente, Fontes, Glossário) | ok (L2) | ok (L2) | ok (L2) | ok (L2) | ok (L2) | ok (L2) | ok (L2) | ok (L2) |
| SCADA (Sinótico, Supervisório, Painel do cliente, Historiador, Automação, Exportar) | ok [11] | ok [11] | ok [11] | ok [11] | ok [10] (L5) | ok [10] | ok [10] | ok [10] |
| Gestão Physis (21 itens do menu) | ok [7] | ok [7] | ok [7] | ok [7] | ok [8] [9] [10] (L4) | ok (L4) | ok [7] [8] [9] [10] (L4) | ok (L4) |
| Consultoria (Como trabalhamos, Fases 0/1/2, Serviços, Diárias, Casos, formulário com consentimento LGPD) | ok | ok | ok | ok | ok | ok | ok | ok |
| Demonstração SustainKit (faixa "Demonstração · dados simulados" + "Comprar a versão completa") | ok | ok | ok | ok | — | ok | ok | ok |
| Demonstração SCADA | ok | ok | ok | ok | — | ok | ok | ok |
| Demonstração Monitoramento verde (5 abas + 3 subabas) | ok | ok | ok | ok | — | ok | ok [2] | ok |
| Demonstração Planejador | ok | ok | ok | ok | — | ok | ok | ok |
| Demonstração Plataforma (= linha "Plataforma" acima) | ok | ok | ok | ok | ok | ok | ok | ok |
| Servidor: `/gestao` (entrar), `/conta/esqueci`, `/conta/nova-senha`, `/conta/confirmar`, `/conta/convite`, `/ativar/PH-0001` | — | L1 | — | — | — | — | L1 | — |

"—" = combinação não repetida nesta rodada. Nas linhas da plataforma, das demonstrações e dos programas, o roteiro abriu todas as abas e subabas em cada combinação marcada.

## Problemas encontrados e corrigidos

| # | Problema | Correção | Arquivo |
|---|---|---|---|
| 1 | Na demonstração da plataforma, a aba Planejador mostrava "O arquivo planejador.html não está nesta pasta" (404) | A demonstração abre a demonstração do Planejador; dentro de um quadro, a faixa e a barra de compra da demonstração somem (sem faixa repetida) | `demos/gerar_demos.py` |
| 2 | Em inglês, a faixa "Demonstração gratuita. Uma versão reduzida…" ficava em português em todas as abas das demonstrações | Pares em inglês | `sistema/physis-i18n-modulos.json` |
| 3 | Certificações (módulo à venda): cerca de 80 textos em português no inglês (critérios LEED, EDGE, Casa Azul, GreenKey, PBQP-H, PBE, ISO, conformidade legal, IPMVP) | Pares e 4 regras (`…: Critérios`, `N de M avaliados`, `Resolução CONAMA …`, `Resíduos do lugar (N)`) | `sistema/physis-i18n-modulos.json` |
| 4 | Os nomes das tabelas roláveis para leitor de tela ficavam meio traduzidos ("Variáveis de Rega automática. Scroll sideways…", "Indicators: Produção. Role para o lado…") em todas as abas | A tradução da plataforma passa a traduzir também o pedaço capturado por uma regra (antes só olhava o dicionário exato) | `physis-hub/web/painel.html` (função `trad`) |
| 5 | O título da aba do navegador ficava em português no inglês (plataforma, loja, demonstrações) | `tituloIdioma()` traduz cada parte do título | `physis-hub/web/painel.html` |
| 6 | Loja no servidor, em inglês: "Escolha, confira o extrato…", "Quer ver antes de comprar?", "Continuar para o pedido", "Editar catálogo e preços…" e outros em português | Pares em inglês | `sistema/physis-i18n-modulos.json` |
| 7 | Gestão Physis: Tarefas e projetos, Propostas, Contratos, Financeiro, Fornecedores e Conta não tinham nenhum título (`h1`) | Título para o leitor de tela com o nome do item do menu, na língua escolhida | `sistema/gestao-interna-physis.html` |
| 8 | Gestão Physis: título da aba do navegador "Gestão Physis" no inglês | "Physis Management" no inglês | `sistema/gestao-interna-physis.html` |
| 9 | Botões "Formatos abertos / Compartilhar para comentários" seguiam a língua do navegador, não a escolha da pessoa (português na Gestão em inglês) | Opção `idiomaTela`; a Gestão passa a escolha da pessoa | `sistema/physis-odf.js` (cópias por `sincronizar.py`), `sistema/gestao-interna-physis.html` |
| 10 | Barra "Baixar esta tela" seguia a língua do navegador e não mudava quando o SCADA trocava de idioma | Opção `idiomaTela` e a barra acompanha o `lang` da tela; SCADA e Gestão usam | `sistema/physis-exportar.js` (cópias por `sincronizar.py`), `sistema/physis-scada-demo.html`, `sistema/gestao-interna-physis.html` |
| 11 | Faixa do SCADA ligava à antiga Tela do cliente (legado) e a `gestao-physis.html` (não existe, 404), com os nomes sem tradução; a Gestão interna não se mistura com o cliente (regra 9) | Ficou só o SCADA na faixa; a troca da demonstração foi ajustada | `sistema/physis-scada-demo.html`, `demos/gerar_demos.py` |
| 12 | A 375 px a faixa "Loja Physis. Escolha os módulos…" virava uma pílula oval com o nome espremido numa coluna; no inglês faltava o espaço ("Physisthe") | O texto quebra em linhas e a pílula vira cartão em tela estreita | `physis-hub/web/painel.html` (CSS de `#faixa-modo`) |
| 13 | Textos soltos em português nas abas Economia circular, Carbono, Secador e Registro | Pares (o que é texto da tela; números compostos ficaram para L3) | `sistema/physis-i18n-modulos.json` |
| 14 | Teste `test_copias_iguais_ao_original` falhava: o comentário do módulo de preferências citava a etiqueta `<script id="physis-preferencias">` e a página contava duas | Comentário reescrito, cópias sincronizadas | `sistema/physis-preferencias.js` (cópias por `sincronizar.py`) |

Ao todo, 116 pares e 4 regras novos no dicionário em inglês da plataforma (itens 2, 3, 6 e 13).

Depois das correções: `ferramentas/embutir_bases.py`, `ferramentas/sincronizar.py`, `demos/gerar_demos.py` e os testes.

## Lacunas abertas

| # | Lacuna | O que falta |
|---|---|---|
| L1 | As páginas montadas pelo servidor (`/gestao` entrar, `/conta/*`, `/ativar/*`) têm uma barra própria com só **Idioma** e **Tema**; faltam **Modo de conforto** e **Acessibilidade**. O nome "Gestão Physis" na página de entrar fica em português no inglês. Título, tema, inglês e 375 px estão certos. | Trocar a barra do modelo de página do servidor (`_PX_FAIXA` em `servidor.py`) pelo módulo `physis-preferencias.js`. Não foi feito: é mudança no servidor, maior que um ajuste. |
| L2 | O Planejador tem um botão próprio **Ajustes de leitura** ao lado da barra única de preferências | Decidir se sai (a barra única já tem tamanho de texto, espaçamento etc.) ou se fica como ajuste só do Planejador |
| L3 | Inglês das partes **em desenvolvimento** (só aparecem na instalação de pesquisa): Servidor verde (cerca de 200 textos), base de plantas da SbN (funções, nomes, estratos, épocas, cerca de 270), e frases com números em Economia circular, Carbono e Secador | Dicionário dessas partes antes de irem para a loja |
| L4 | Gestão Physis: a curadoria de **Parceiros** (`physis-parceiros.js`) não tem inglês. Tarefas e eventos aparecem em português porque são dados (lista da fase 2, nomes de eventos), não texto da tela | Dicionário em `physis-parceiros.js` |
| L5 | Nome do SCADA na faixa: "Physis PDI - Sistema Integrado", diferente dos outros programas ("Physis SustainKit", "Planejador Physis") | Decidir o nome |
| L6 | SustainKit mantém "IPMVP (Opções A–D)" sem tradução (está na lista do que não se traduz) | Decidir se vira "IPMVP (Options A–D)" no inglês |
| L7 | A instalação Casa Physis não foi montada (`montar_clientes.py --so casa-physis`); as mesmas abas foram vistas pela demonstração com o modo pesquisa ligado | Conferir no pacote quando ele for montado |
| L8 | As páginas do servidor foram vistas em 2 das 8 combinações (EN escuro 1280, PT claro 375) | Repetir nas outras 6 |
| L9 | Em alguns passos o simulador de largura voltou para a largura do painel (514 px) e a conferência rodou nessa largura em vez de 1280 (Planejador e Monitoramento demonstração PT escuro, loja EN claro, final da plataforma EN claro); nenhum problema apareceu, mas não foi a 1280 | Repetir a 1280 |

## Ruído esperado (não é erro)

Sem o servidor da Physis, as telas abertas como arquivo pedem coisas que só o servidor tem:

- `404` em `/api/*` (plataforma, Gestão: `/api/gestao/estado`, `/api/instancia`, `/api/central/*`, `/api/aprendizado/*`, `/api/alertas/*`, `/api/eventos`, `/api/editais`, `/api/suporte/chamados`, `/api/parceiros/interno`; SCADA: `/api/painel`; plataforma: `/api/servidor/pegada`, `/api/evidencias/dados`);
- "An unknown error occurred when fetching the script" do service worker (`/app/sw.js`), que só existe no servidor;
- `404` em `/mapas/regiao.pmtiles` (mapa só no servidor);
- `404` nos testes de presença da aba "Em desenvolvimento" (`gestao-interna.html`, `consultoria.html`, `painel-municipal.html`, `documento.html`, `municipio.html`, `baixar-o-app.html`, `documento-para-comentarios.html`): são páginas do computador central, que a aba procura e mostra como ausentes quando a plataforma é aberta como arquivo.

Nenhum erro de programa (exceção de JavaScript) apareceu no console.

## Não verificado

- Leitor de tela de verdade, Libras, voz e comandos de voz (só a presença dos controles e dos títulos).
- Contraste AA medido cor a cor (as telas usam a paleta; foi conferido só a olho, em claro e escuro).
- Telas atrás de login no servidor (plataforma do cliente autenticada, Gestão com dados).
