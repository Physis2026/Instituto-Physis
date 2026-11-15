# Physis 3D — peças impressas com plástico reciclado

**Situação: EM DESENVOLVIMENTO.** Fica fora do site e da loja públicos. Aparece só na instalação de pesquisa
(Casa Physis), com o selo "Em desenvolvimento". A tela tira o selo quando a plataforma marcar
`window.PHYSIS3D_PRONTO = true`.

Pedido: uma plataforma para desenhar e ajustar peças de plástico reciclado, fatiar na mesma tela, ver como a peça
vai ficar, guardar tudo numa biblioteca aberta entre os participantes (com fórum e memorial de cada peça), avisar o
que deu errado antes em impressões parecidas e, na fase 2, simular (escoamento, calor, pressão, compressão, impacto,
tração, flambagem), começando pela programação quântica. **Tudo aberto e de código aberto.**

## Fase 1: o que já existe

| Arquivo | O que faz |
|---|---|
| `sistema/physis-3d.js` | A aba: abre STL, OBJ e 3MF; vista 3D em WebGL escrita à mão; ajustes; medidas; fatiamento; estimativas; biblioteca e fórum (com o servidor). `window.PHYSIS3D`, `window.PHYSIS3D_I18N` |
| `physis-hub/physis_hub/impressao3d.py` | O servidor: as mesmas contas de malha, a biblioteca (SQLite do hub), memorial, fórum, papéis, avisos aprendidos e o cliente do fatiador |
| `sistema/physis-3d-premissas.json` | Os cinco perfis de plástico reciclado, todos **"conferir"** |
| `servicos/fatiador/` | Serviço em contêiner Linux: PrusaSlicer em linha de comando atrás de uma API local (como o `calc`) |
| `physis-hub/tests/test_impressao3d.py` | 24 testes (malha, fatiamento, perfis, biblioteca, avisos, fatiador, rotas, tela, Linux) |
| `ferramentas/testes-navegador/teste-physis-3d.html` | Autoteste da tela no navegador (sem Node): o mesmo cubo e os mesmos números do Python |

### Na tela (aba Physis 3D)

- **Modelo.** Abre STL (texto e binário), OBJ e 3MF com leitores próprios. O arquivo original fica guardado como veio
  ("Baixar o arquivo original"). Unidade do arquivo: milímetros ou polegadas.
- **Vista 3D.** WebGL puro, sem biblioteca de terceiros e sem internet. Arrastar gira, a roda aproxima. No teclado:
  clicar na vista e usar as setas, `+`, `−` e `0`. A cor é a do filamento escolhido e as linhas horizontais mostram as
  camadas na altura escolhida: é a prévia de "como vai ficar". O balanço aparece em vermelho, se pedido.
  "Guardar a imagem na tela" põe uma foto da vista no HTML, para o "Baixar esta tela" levar junto.
- **Ajustes.** Escala, giro em X/Y/Z, espelho, pôr na mesa, corte plano (fica a parte de baixo ou a de cima),
  desfazer e voltar ao original. O corte fecha a face pelo contorno de fora; furos que cruzam o corte ficam tampados
  (limite da fase 1: a conferência de arestas avisa).
- **Medidas** (também em tabela, a alternativa em texto da vista): tamanho, volume, área, massa se fosse maciça,
  área em balanço acima de 45°, arestas abertas, arestas com 3 faces ou mais, faces com o lado trocado.
- **Fatiamento.** Planos no meio de cada camada; por camada, contorno e área. Vista camada por camada (controle
  deslizante, desenho e frase com os números). Estimativa de filamento (m), massa (g) e tempo, com a conta escrita na tela.
- **Levar para a impressora.** STL e 3MF da peça editada. G-code pelo fatiador do servidor, quando ligado; sem ele,
  a tela diz para fatiar num fatiador aberto (PrusaSlicer, Cura ou OrcaSlicer).
- Português e inglês, teclado, foco visível, tema claro e escuro (a vista lê o tema), modo de conforto (a vista não
  anima: só redesenha quando a pessoa mexe).

### Materiais reciclados (premissas "conferir")

rPET/PETG, rPP, rHDPE, rABS e PLA reciclado: densidade, temperatura de bico e de mesa (valor e faixa), contração e
diâmetro. **São valores típicos do polímero virgem, marcados `[CONFERIR]`**: o reciclado muda de lote para lote.
Trocar pela folha de dados do fornecedor ou pelo ensaio da oficina (torre de temperatura, cubo de calibração).
Proposta: estes cinco blocos entram em `sistema/physis-premissas.json` (e no mapa de variáveis) quando o mapa estiver
pronto; até lá ficam em `sistema/physis-3d-premissas.json` e a tela tem uma cópia de reserva igual (o teste confere).

### Biblioteca dos participantes (servidor)

- **Quem faz o quê.** Participante = qualquer conta com sessão (papel cliente ou acima). Ele cria a peça
  (rascunho, só ele e a equipe veem), envia revisões, registra o resultado e as fotos, e publica. A **equipe da
  Physis** cura ("curada pela Physis") e modera (oculta peça ou mensagem, sempre com motivo).
- **LGPD.** Para publicar ou escrever no fórum, o participante aceita mostrar um **nome público** (pode ser apelido);
  data e versão do termo ficam guardadas. "Tirar o meu nome" troca o nome por "Participante removido" em tudo; as
  peças já publicadas seguem sob a licença escolhida, sem o nome.
- **Licença por peça**, escolhida pelo autor: CC BY 4.0, CC BY-SA 4.0, CC0 1.0, CERN-OHL-S 2.0, CERN-OHL-W 2.0 ou
  CERN-OHL-P 2.0. Sem licença aberta não se publica.
- **Revisão** = arquivo (guardado em disco pelo resumo SHA-256), nota do que mudou, material, configuração de
  impressão, medidas tiradas do próprio arquivo pelo servidor, resultado (deu certo, serviu com defeito, falhou) com
  os problemas encontrados, e fotos reais (JPEG ou PNG, o tipo vem dos bytes).
- **Integridade** no estilo de `integridade.py`: cada revisão tem o resumo SHA-256 do seu JSON canônico, que inclui o
  resumo da revisão anterior (cadeia). O resultado, registrado uma vez só, ganha o próprio resumo, ligado ao da
  revisão. Revisão não se apaga (gatilho no banco).
- **Melhorar a peça de outra pessoa**: "Derivar" cria uma peça nova, que aponta para a original e começa da última
  revisão dela.
- **Memorial de desenvolvimento**, montado sozinho das revisões: cada tentativa, o que mudou, o resultado, as fotos, o
  resumo de integridade (e se confere) e, no fim, "Para quem vai imprimir pela primeira vez": problema → o que mudou
  na revisão seguinte → resultado. Baixa em `.md`.
- **Fórum**: tópicos gerais e tópicos de cada peça.

### Avisos aprendidos ("o que tiveram de mudar antes")

Classificador de Bayes ingênuo, escrito só com a biblioteca padrão, treinado nas revisões com resultado. Variáveis:
material, altura de camada, fração da área em balanço, espessura de parede, maior dimensão e temperatura do bico em
relação ao perfil do material (em faixas). Rótulos: os problemas registrados (empenamento, pouca adesão, fios,
separação de camadas, subextrusão…). O aviso diz: "Em N impressões parecidas, X tiveram empenamento. O que mudaram
depois: …" (a nota da revisão seguinte). **Com menos de 10 impressões registradas, ou menos de 3 parecidas, a tela
diz que são poucos dados.** O modelo é refeito a cada pedido (é rápido); se o histórico crescer muito, guardar o modelo
com um temporizador do systemd ou no laço do hub (não há tarefa agendada hoje).

### Fatiador do servidor (`servicos/fatiador`)

Contêiner Debian com o **PrusaSlicer (AGPL-3.0)** em linha de comando e uma API local (só biblioteca padrão):
`GET /saude`, `POST /fatiar` (STL em base64 + configuração → G-code e as estimativas que o PrusaSlicer escreve no fim
do arquivo). Rede só interna, chave `PHYSIS_FATIADOR_CHAVE`, sistema de arquivos só leitura, `/tmp` em memória.
O hub fala com ele por `PHYSIS_FATIADOR_URL` (só rede local, como o `calc`); sem o serviço, a rota responde 503 com o
caminho aberto e a tela segue. **Licença:** o PrusaSlicer roda como programa separado, chamado pela linha de comando;
nada dele é importado no hub. Ao redistribuir a imagem, levar o aviso de licença e o código-fonte (ou o link).
CuraEngine (também AGPL-3.0) pode trocar o PrusaSlicer, mas pede um arquivo de definição da impressora bem maior.

### Rotas (o servidor liga; todas pedem sessão de participante)

| Rota | O que faz |
|---|---|
| `GET /api/3d/pecas?busca=&material=` | Peças que a pessoa pode ver |
| `GET /api/3d/pecas/<id>` · `.../memorial` | Peça com revisões e fotos · memorial |
| `GET /api/3d/arquivo/<sha256>` | Malha ou foto (se a peça for visível) |
| `GET /api/3d/materiais` · `/fatiador` · `/participante` | Perfis · fatiador ligado? · meu consentimento |
| `GET /api/3d/forum[?peca=]` · `/forum/<id>` | Tópicos · mensagens |
| `POST /api/3d/participante` · `/participante/remover` | Aceitar (LGPD) · tirar o nome |
| `POST /api/3d/pecas` | Nova peça (rascunho) |
| `POST /api/3d/pecas/<id>/revisao\|resultado\|foto\|publicar\|derivar\|fatiar` | Autor (derivar: qualquer participante) |
| `POST /api/3d/pecas/<id>/curar\|moderar` · `/forum/mensagem/<id>/moderar` | Equipe |
| `POST /api/3d/avisos` · `/fatiar` · `/forum` · `/forum/<id>` | Avisos · G-code da peça aberta · tópico · resposta |

Os arquivos ficam em `PHYSIS_3D_PASTA` ou, sem ela, em `<pasta do banco>/impressao3d` (pathlib; Linux e Windows).

## Fase 2: simulações

Pedido: simulações gráficas de escoamento, calor, pressão, compressão, impacto, tração, flambagem e outras
influências, "iniciadas com programação quântica", e depois levadas ao Planejador, quando validadas.

### 1. Primeiro, a referência clássica (aberta)

Nenhum resultado entra sem uma referência confiável para comparar. Os resolvedores clássicos abertos vêm primeiro:

| Fenômeno | Resolvedor aberto | Licença |
|---|---|---|
| Tração, compressão, flexão, flambagem (estrutural) | **CalculiX** (elementos finitos) | GPL-2.0 |
| Estrutural e calor, com programação em Python | **FEniCSx** (DOLFINx) | LGPL-3.0 (partes MIT) |
| Escoamento, pressão e calor em fluidos | **OpenFOAM** | GPL-3.0 |
| Malha de volume a partir do STL | Gmsh | GPL-2.0 ou posterior |
| Gráficos dos resultados | ParaView (fora da plataforma) ou a própria tela | BSD-3-Clause |

Cada um roda como serviço em contêiner Linux, igual ao `calc` e ao `fatiador`. A peça impressa não é maciça: as
propriedades vêm do material reciclado **e** da impressão (paredes, preenchimento, direção das camadas, que enfraquece
a tração entre camadas). Esses valores são premissas "conferir", medidas em ensaio quando possível.
Impacto (rápido e com fratura) é o mais difícil: fica por último e precisa de ensaio físico para comparar.

### 2. A trilha de programação quântica (como pedido)

Ferramentas abertas: **Qiskit** (Apache-2.0) e **PennyLane** (Apache-2.0), rodando em **simuladores no próprio
servidor** (regra 11: nada depende de serviço de terceiros; máquina quântica na nuvem só como opção ou espelho).
Formulações candidatas:

- **Otimização de topologia como QUBO**: cada pedacinho da peça vira um bit (tem material ou não); a rigidez e o
  limite de material viram um problema quadrático de bits. Resolve com QAOA (quântico) e, para comparar, com
  recozimento simulado (clássico, "inspirado em quântico").
- **Resolvedor variacional de sistemas lineares (VQLS)** para sistemas pequenos `K·u = f` (rigidez × deslocamento =
  força) de uma peça simples.

**Dito com clareza: hoje isso é pesquisa.** Os simuladores só aguentam problemas pequenos (dezenas de bits), o
resultado é aproximado e o ruído das máquinas reais é alto. Nada da trilha quântica entra no Planejador sem antes
bater com o CalculiX ou o FEniCSx (e o OpenFOAM, no escoamento) em casos de referência (viga em balanço, viga MBB,
placa com furo), com o erro medido e anotado.

### 3. Caminho até o Planejador

1. Caso de referência resolvido no clássico e, quando der, conferido com ensaio da oficina (peça impressa e medida).
2. O mesmo caso pela trilha quântica (ou inspirada em quântico); erro anotado contra o clássico.
3. Relatório de validação assinado pelo engenheiro responsável [MARCADOR: quem assina].
4. Só então o resultado vira um bloco de dados (`physis-sim/1`, com o resumo da revisão da peça e a versão de cada
   resolvedor) que o Planejador lê, ainda com o selo "Em desenvolvimento" até a direção aprovar.

## Licenças de cada parte

| Parte | Licença |
|---|---|
| Código da Physis 3D (tela, servidor, serviço) | Código da Physis, aberto [MARCADOR: a direção escolhe a licença do código da Physis] |
| Vista 3D, leitores STL/OBJ/3MF, descompactador | Escritos aqui (nenhuma biblioteca de terceiros foi copiada) |
| Formato 3MF | Especificação pública do 3MF Consortium |
| PrusaSlicer (serviço `fatiador`) | AGPL-3.0, processo separado |
| Imagem base do contêiner | Debian (pacotes livres; cada um com a sua licença) |
| Peças publicadas | A licença aberta que o autor escolher (CC BY 4.0, CC BY-SA 4.0, CC0 1.0, CERN-OHL-S/W/P 2.0) |
| Fase 2 | CalculiX GPL-2.0; FEniCSx LGPL-3.0; OpenFOAM GPL-3.0; Gmsh GPL-2.0+; Qiskit Apache-2.0; PennyLane Apache-2.0 |

## O que NÃO foi verificado

- A imagem `servicos/fatiador` não foi construída aqui (sem Docker): o pacote `prusa-slicer` do Debian, se ele roda o
  modo linha de comando sem tela, as chaves do `.ini` e o texto exato das estimativas no fim do G-code ficam
  `[CONFERIR]` na máquina Linux.
- As rotas foram testadas chamando `Impressao3D.rota` direto; a ligação em `servidor.py` ainda não existe.
- A tela foi conferida no navegador (autoteste e vista do cubo); a biblioteca e o fórum pela tela, com o servidor de
  verdade, só depois da ligação.
- Valores dos materiais: todos "conferir".
