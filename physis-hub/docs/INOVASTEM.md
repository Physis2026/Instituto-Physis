# InovaSTEM: site e plataforma como living lab online

Versão de 19/11/2026 · decisão **D94** (prioridade 0): **teste em 24/11/2026, lançamento público em 26/11/2026**, só com
a autorização da direção. Código: `physis_hub/inovastem.py`, `web/inovastem.html`. Testes: `tests/test_inovastem.py`.

## Em uma frase

Terceira instalação do mesmo código do Instituto (`"instalacao": "inovastem"`), com **banco, porta, marca e subdomínio
próprios** (`inovastem.physisengineering.com`, a confirmar pelo Eric). Até o CNPJ do Instituto, sai **sob a Physis**, com a
marca endossada ("uma iniciativa PHYSIS"). **Sem a marca do Instituto**: ele terá site separado.

## Decisões da direção (19/11/2026, caixas de perguntas)

| Tema | Decisão |
|---|---|
| Onde montar | Instalação própria `inovastem`, gerada do código do Instituto (fórum, cadastro, Delas, agenda e Physis 3D já prontos) |
| Marca | Endossada pela Physis; Guia de Identidade da Família Physis de 19/11/2026, **Opção B** |
| Logo | InovaSTEM **opção 2 (pessoas em círculo)**; Delas **opção 1 (roxo + laranja)**; imagens do guia, **sem alteração**, versão clara e escura |
| Cores e fontes | As do guia, sem alteração (`docs/PALETA.md`, seção da Família Physis); Josefin Sans e Lora |
| Missão, visão e propósito | Recomendadas (mescla) do doc 37, aprovadas na D92; propósito e papéis no doc 41 (Sistema Physis): InovaSTEM = conexão e trocas abertas para o desenvolvimento tecnológico (living lab de PDI); Delas = mulheres que lideram |
| Hackathon | Março de 2027 (dia a confirmar), online, CTF em ambiente isolado |
| Moderação | Equipe a nomear (toda conta da equipe modera; tudo passa pela moderação antes de aparecer) |
| Endereço | `inovastem.physisengineering.com` [CONFERIR com o Eric] |
| WhatsApp | A direção manda o convite até 25/11; o botão só aparece com um link `https://chat.whatsapp.com/…` |
| Cadastro de interesse | Nome, e-mail e interesse (passo 1); idade, gênero opcional, cidade e instituição opcionais e aceite (passo 2). "Feminino" abre o convite da InovaSTEM Delas (mulheres jovens, cis e trans) |
| Idade | A partir de **16 anos**, com responsável de 16 a 17 (dona, 19/11/2026; substitui o 14+ da D93; [CONFERIR com o advogado]) |

## Páginas e rotas (só na instalação inovastem)

| Endereço | O que é |
|---|---|
| `/` | Site: Início, InovaSTEM Delas, Desafios e projetos, Fórum, Modelagem 3D, Hackathon, Materiais, Participar; Termos e Privacidade (beta) no rodapé |
| `/laboratorio` | **Modelagem 3D (Physis 3D)** (dona, 20 e 21/11/2026): a bancada de desenvolvimento, aberta a qualquer assunto, em português e inglês (a barra de preferências troca ao vivo; Delas = "Hers"). O Planejador é outra ferramenta e não aparece aqui. Fluxo visível, com cada passo registrado no projeto: Enviar arquivo → Lugar ou Modelos BIM → Montagens → Peças 3D → Simulação → Fila de impressão → Galeria; **todo caminho termina em "Pedir impressão"**. Oito subabas por hash: `#arquivo` (foto ou imagem → escala de cinza, suavização, limiar automático de Otsu com ajuste manual, remoção de ruído e de fundo → contorno vetorizado com Douglas-Peucker em SVG e DXF → extrusão em STL e 3MF, com foto, CAD 2D e 3D lado a lado; SVG pelos caminhos; malhas para Peças 3D; PDF e STEP/IGES: próxima etapa; peças de teste de impressão geradas aqui), `#lugar` (contrato `physis-geometria-lugar/1`), `#edificacao` **Modelos BIM (CAD e IFC)** (IFC com geometria pelo web-ifc e vista 3D pelo three.js, os dois de `vendor/` e entregues em `/vendor/`; árvore por tipo e pavimento; ferramentas no estilo do SketchUp: selecionar, mover, girar, escalar, empurrar/puxar, linha, retângulo, círculo, medir/cota, desfazer/refazer, com ícones SVG próprios e teclado; formas paramétricas caixa, cilindro, chapa com furo e perfil L/U/T; DXF 2D; saída SVG, DXF, STL, 3MF e IFC4 com a malha do que foi modelado — gravar de volta no IFC original é próxima etapa), `#montagem` **Montagens** (várias peças com posição, giro, material e cor; colisão simples por caixas; STL e 3MF com uma peça por objeto e cor; quadro dos programas mapeados: FreeCAD, CadQuery, OpenSCAD, Gmsh, CalculiX, OpenFOAM, FEniCSx, PrusaSlicer), `#pecas` (tela do Physis 3D), `#simulacao` (um bloco por fenômeno), `#fila` e `#galeria`. **Escaneamento saiu por enquanto (dona, 21/11/2026) e volta depois**; `#escaneamento` abre Enviar arquivo. Projeto comum `inovastem-projeto/1` no navegador (seções lugar, edificacao, montagem, pecas, resultados, arquivos e passos; as malhas das peças guardadas ficam no IndexedDB deste navegador). Só esta página, e só nesta instalação, recebe `'unsafe-eval'` na política de segurança (o web-ifc precisa; como o Planejador). Gerada por `ferramentas/montar_lab_inovastem.py` com cópias iguais de `physis-simulacao.js`, `casos.js`, `physis-turbinas.js`, `physis-3d.js`, `physis-imagem-3d.js` e `physis-modelagem.js`; o pacote leva `vendor/three.min.js`, `web-ifc-api-iife.js` e `web-ifc.wasm`. Regerar depois de mudar qualquer motor ou a casca |
| `/planejador` | Planejador (GIS e BIM IFC), **aberto sem conta** |
| `/plataforma/` | Plataforma do Sistema: só **Área da equipe** (para participante ela abre na Loja Physis). Participantes entram e saem pelo site (Participar) |
| `/fontes/JosefinSans.ttf`, `/fontes/Lora.ttf` | Fontes do guia (OFL) |
| `/termos`, `/privacidade` | Levam ao texto **beta** do próprio site (em revisão jurídica) |
| `/materiais/<arquivo>` | Só arquivos listados em `inovastem.materiais` **e** presentes na pasta `materiais/` |
| `GET /api/publico/inovastem` | WhatsApp (se houver), mês do hackathon, áreas e materiais |
| `GET /api/publico/inovastem/propostas?tipo=desafio\|projeto` | Desafios e projetos publicados (sem nome nem e-mail de quem sugeriu) |
| `POST /api/publico/inovastem/interesse` | Cadastro de interesse (limite por IP; esquema estrito) |
| `POST /api/publico/inovastem/projeto` | Sugestão de projeto aberto (vai para a moderação) |
| `GET /api/inovastem/fila` · `/interesses` | Equipe: sugestões pendentes · cadastros (com contagem por área) |
| `POST /api/inovastem/desafio` · `/moderar` · `/remover` | Equipe: publicar desafio · aprovar, recusar (com motivo) ou encerrar · exclusão a pedido (LGPD) |
| `POST /api/inovastem/impressao` · `GET /api/inovastem/impressao/minhas` | Participante com conta: pedir impressão de uma peça do Physis 3D (id, material, observação) · os seus pedidos |
| `POST /api/inovastem/impressao/arquivo` · `GET /api/inovastem/impressao/<id>/arquivo` | Participante com conta: enviar o STL ou 3MF gerado no laboratório (corpo cru até 20 MB, nome em `X-Physis-Nome`; tipo conferido pelos bytes pelo leitor de malha; guardado privado em `<pasta do banco>/impressao_lab` ou `PHYSIS_IMPRESSAO_PASTA`) e depois pedir com `{"arquivo": <sha256>}` · baixar o arquivo do pedido (só quem pediu e a equipe). Registro encadeado só com formato, tamanho e resumo |
| `GET /api/inovastem/impressao/fila` · `POST /api/inovastem/impressao/estado` | Equipe: fila de impressão · mudar a situação (pendente → aprovada → imprimindo → pronta, ou recusada com motivo). O arquivo baixa por `/api/3d/arquivo/<sha256>` e é aberto localmente no CrealityPrint ou no HALOT (o navegador não instala nem chama nada). Registro encadeado só com números e situações. Modelos das impressoras: [MARCADOR] |

O fórum, o cadastro com conta, a autodeclaração da Delas e a fila de moderação são os de `docs/COMUNIDADE.md`
(categorias novas: `modelagem`, `desafios`, `hackathon`).

## Configuração (`instancia.json`)

```json
"inovastem": {
  "whatsapp_grupo": "",                       // convite https://chat.whatsapp.com/… (ou PHYSIS_INOVASTEM_WHATSAPP)
  "hackathon": "2027-03",
  "endereco": "inovastem.physisengineering.com",
  "materiais": [ {"titulo": "Apresentação da rede", "arquivo": "apresentacao-inovastem.pdf", "grupo": "rede"} ]
}
```

Os materiais ficam em `<pasta do banco>/materiais/` (no Acer com o instalador: `/var/lib/physis/materiais/`). Só PDF e
ODF. Arquivo fora da lista não aparece nem baixa.

## Montar e testar

```
cd physis-hub
python montar_clientes.py --saida ../pacotes --so inovastem
python -m unittest discover -s tests
```

Versão de teste local: pacote em pasta própria, `PHYSIS_PORTA=8702`, `PHYSIS_ENDERECO=127.0.0.1`, abrir `http://localhost:8702/`.

## LGPD e privacidade

- Coleta mínima. O gênero só serve para o convite da Delas: a equipe vê o convite ("quero participar da Delas"), não o gênero.
- O registro encadeado guarda só número e áreas, nunca nome, e-mail ou gênero.
- O e-mail de quem sugere projeto nunca aparece no site.
- Exclusão a pedido: Participar → "Pedido de exclusão (LGPD)" (equipe), apaga o cadastro e o contato das sugestões.
- A planilha CSV dos cadastros é montada no navegador da equipe (não fica no servidor).
- Termos de uso e aviso de privacidade: **beta, em revisão jurídica**; razão social, CNPJ, encarregado e prazo de guarda
  são `[MARCADOR]`.

## Desvios conscientes das regras gerais do Sistema Physis

- **Regra 10 (título em Fraunces no verde `#33512F`)**: a InovaSTEM segue o Guia de Identidade da Família (logo da marca
  no título, Josefin Sans e Lora). O h1 é o logo, com o nome no texto alternativo.
- **Fontes**: Josefin Sans e Lora (licença OFL) em `web/fontes/`, servidas pelo próprio servidor em `/fontes/`
  (cópia de `C:\physis\identidade\fontes`). Sem Google Fonts.
- **Logos**: as imagens do guia, recortadas sem alteração e embutidas em WebP. Os SVG vetorizados de
  `C:\physis\identidade\logos\final` (proposta, D43) **não** foram usados: o contorno automático deixa bordas irregulares,
  cerca de 30 tons fora da paleta e a semente da versão escura num laranja mais escuro. Trocar quando houver o vetor
  limpo (guia, passo 2).

## O que NÃO foi verificado

- Instalação no Acer, DNS e HTTPS (dependem do Eric).
- Leitores de tela reais (NVDA, TalkBack): conferidos só os nomes acessíveis, o foco e a ordem pelo teclado.
- O Planejador e o Physis 3D foram abertos pelos testes existentes; o uso por visitantes sem conta, na internet, só depois da publicação.
