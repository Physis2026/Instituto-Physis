# Kits de revisão por módulo

Cada responsável recebe **só os arquivos do seu módulo**, revisa e devolve. O Eric Oliveira confere a devolução com uma ferramenta, aplica numa cópia separada do sistema, roda os testes e só então junta ao sistema. Assim a revisão dos engenheiros entra sem mexer na estrutura do que foi construído.

- Mapa dos módulos, responsáveis e arquivos: `ferramentas/kits/modulos.json`
- Gerar os kits: `ferramentas/gerar_kits_revisao.py`
- Conferir e aplicar a devolução: `ferramentas/validar_devolucao.py` (passo a passo do Eric em `INCORPORAR_REVISOES.md`)

## Quem revisa o quê

| Kit | Módulo | Responsáveis |
|---|---|---|
| `planejador` | Planejador | Rafaella |
| `sustainkit` | SustainKit | Erick Lopes |
| `solar` | Energia solar | Erick Lopes |
| `avac` | AVAC e carga térmica | Ryan |
| `turbinas` | Turbinas | Ryan, Emerson |
| `agua` | Qualidade da água | Erick Lopes, Rafael |
| `sbn` | SbN e viveiro | Rafaella, Erick Lopes |
| `circular` | Economia circular | Rafaella, Rafael |
| `carbono` | Carbono e ESG | Rafaella, Marzia, Laura |
| `resiliencia` | Resiliência climática | Rafaella, Arthur |
| `certificacoes` | Certificações | Rafaella, Laura, Ryan |
| `equipamentos` | Equipamentos e materiais | Ryan |
| `monitoramento` | Monitoramento verde e Caixinha (telas) | Arthur |
| `saude` | Saúde (telas e consentimento) | Emerson, Rafael |
| `scada` | SCADA | Erick Lopes, Laura, Rafaella |
| `cursos` | Cursos | Rafaella, Laura |
| `acessibilidade` | Acessibilidade, inglês e textos jurídicos | Rafaella |
| `hw-lora` | Transmissor LoRa e Receptor V6 | Arthur |
| `hw-caixinha` | Caixinha Physis IoT (firmware) | Erick Lopes |
| `hw-coleira` | Coleira e comedouro | Rafael |
| `hw-pluviometro` | Pluviômetro Physis | Rafaella, Arthur |
| `hw-remedios` | Caixinha de remédios | Emerson, Rafael |
| `hw-pulseira` | Pulseira | Emerson |
| `servidor` | Servidor e implantação | Eric Oliveira |

Quando há mais de um responsável, combinem quem devolve: **uma devolução por kit**. Se dois mexerem no mesmo arquivo em paralelo, a segunda devolução para e precisa ser juntada à mão.

## O que vem no kit

| Pasta ou arquivo | Para quê |
|---|---|
| `LEIA-ME.md` | O que revisar (documentos 17 e 18), os cálculos do módulo e a situação de cada um diante da norma, os itens marcados "verificar", as regras de edição, como ver o resultado e como devolver. |
| `ABRIR-PREVIA.html` | Prévia na hora: a plataforma de demonstração com as suas mudanças (veja "Como ver o resultado"). |
| `editaveis/` | O que pode mudar: bases de dados do módulo (arquivo inteiro), só a parte do módulo de um arquivo que é de todos (arquivo `…__parte-<módulo>.json`), o inglês das telas do módulo (`physis-i18n-modulos__parte-<módulo>.json`), os parâmetros do aparelho (kits de hardware) e `trocas-de-texto.json`. |
| `referencia/` | Código, documentos, testes e páginas de conferência, só para ler. |
| `FICHA_REVISAO.md` | Modelo para contar o que mudou, por quê e com qual fonte. |
| `MANIFESTO.json` | A "impressão digital" (SHA-256) de cada arquivo e a versão do sistema. Não mexer. |

## Regras para mudar sem estragar

1. **Mude só valores.** Não apague, não renomeie nem mude de lugar nenhuma chave nem nenhum `id`.
2. **Mantenha o tipo.** Número continua número (com ponto: `0.8`), texto continua texto, lista continua lista. Vazio (`null`) ou `[MARCADOR]` pode virar o valor conferido.
3. **Registro novo** (planta, equipamento, material, critério): copie um parecido, troque o `id` (ou `n`) por um que não existe e preencha todos os campos.
4. **Marque o que conferiu:** `"verificar": false` e, no mesmo item, `"conferido": {"por": "Seu Nome", "em": "AAAA-MM-DD", "fonte": "norma ou tabela, edição e item"}`. Nas plantas, tire o item da lista `a_conferir`. Numa norma do catálogo, `situacao` de "conferir" para "vigente", com data e nome na `nota`.
5. **Fonte sempre.** Sem fonte, fica `[MARCADOR]`. Não inventar preço, limite técnico nem texto legal.
6. **Não copiar texto de norma**: só número, edição e item, com redação própria.
7. **Sem endereço de internet, sem código e sem tag HTML** nos valores.
8. **Salvar em UTF-8**, sem mudar o nome do arquivo.

### Textos de tela, inglês e parâmetros de aparelho

- **Texto de tela ou de documento** (erro de digitação, frase confusa, termo técnico): em `editaveis/trocas-de-texto.json`, uma troca por item: `{"arquivo": "...", "antes": "...", "depois": "...", "motivo": "..."}`. O `arquivo` tem de estar em `arquivos_permitidos` (telas em `sistema/`, a plataforma `physis-hub/web/painel.html`, documentos `.md`; nunca Python, firmware nem dados). O `antes` é o texto exato e tem de aparecer **uma vez só** no arquivo (se aparecer mais, copie um trecho maior). Até 400 caracteres, numa linha, sem os sinais `<` `>` `{` `}` crase `;` `=>`, sem endereço de internet e com as mesmas aspas do `antes`. Na plataforma vale o texto que se vê na tela; se ele vier de um programa embutido, o validador leva a troca para o arquivo certo.
- **Inglês**: no arquivo `physis-i18n-modulos__parte-<módulo>.json`, a chave (`caminho`) é a frase em português e o `valor` é o inglês. Mude só o inglês. As frases das abas que ficam dentro do próprio painel (água, cursos, equipamentos…) e as regras com variável (`I18N_RX`) estão no kit de Acessibilidade, inglês e textos jurídicos.
- **Parâmetros de aparelho** (kits de hardware): `firmware/pluviometro/parametros.json`, `firmware/saude/parametros-pulseira.json` e `firmware/saude/parametros-caixinha.json`. Mude o `valor` (dentro de `faixa_aceita`) e marque `conferido`. O bloco `aparelho` (pluviômetro) e o bloco `ble` (pulseira e caixinha) não mudam: são o contrato com o celular e com o hub. `null` = `[MARCADOR]`; limite clínico (batimentos, janela de crise) só com a equipe clínica.

**Conta, regra, comportamento ou código** não mudam pelo kit: vão descritos na `FICHA_REVISAO.md` (o que, onde, por quê, fonte). O Eric leva para quem mexe no código.

Os textos jurídicos são editados no documento 09 (Minutas Jurídicas); o Eric gera de novo `sistema/physis-juridico.js` com `ferramentas/gerar_juridico.py`.

## Como ver o resultado

**Na hora, em todo kit:** abra `ABRIR-PREVIA.html` (duplo clique; funciona sem internet e sem servidor). No botão, escolha os arquivos que você mudou em `editaveis/` (vários de uma vez). A página junta as suas partes com as cópias completas que vão no kit, monta a plataforma de demonstração com as mudanças e abre na aba do módulo, com a lista do que mudou. Nada é gravado. O que aparece:

- bases embutidas na plataforma (plantas, certificações, evidências, equipamentos, fatores de emissão, inglês) e a metodologia: na própria aba;
- premissas: na seção "Metodologia e normas" de cada aba, linha "Premissas da base" (`id = valor unidade`);
- trocas de texto: na tela, quando o texto aparece uma vez na plataforma;
- casos de teste, materiais e parâmetros de aparelho: só na lista (não aparecem na plataforma).

Além da prévia, o `LEIA-ME.md` de cada kit diz qual página de conferência abrir. As principais:

| Módulo | Página (em `referencia/`) |
|---|---|
| SbN e viveiro | `ferramentas/conferir-sbn.html` — escolha no botão o seu `editaveis/sistema/physis-plantas.json` |
| SustainKit | `ferramentas/conferir-sustainkit-blocos.html`, `ferramentas/conferir-sustainkit.html`, `demos/physis-demo-sustainkit.html` |
| AVAC | `ferramentas/testes-navegador/teste-avac.html` (casos de quando o kit foi feito) |
| Carbono e ESG | `ferramentas/conferir-odf.html` (documento aberto do relatório) |
| Planejador | `demos/physis-demo-planejador.html` |
| SCADA | `demos/physis-demo-scada.html` |
| Abas da plataforma | `demos/physis-demo-cliente.html` |

As páginas de `demos/` e `teste-avac.html` usam os dados de quando o kit foi feito; a `conferir-sbn.html` lê o arquivo que você escolher.

## Como devolver

1. Preencha a `FICHA_REVISAO.md`.
2. Compacte **só** a pasta `editaveis/` e a `FICHA_REVISAO.md` num ZIP: `devolucao-<kit>-SeuNome.zip`.
3. Mande ao Eric Oliveira. Ele responde com o relatório: o que entrou, o que foi recusado e por quê.

## O que a validação recusa

- mudança fora de `editaveis/` (por exemplo, num arquivo de `referencia/`) ou arquivo a mais dentro de `editaveis/`;
- JSON que não abre, chave repetida, chave ou `id` apagado ou renomeado, tipo trocado;
- chave nova que não seja `conferido`, `fonte`, `data` ou `nota`; `conferido` sem quem, quando e fonte;
- registro novo sem todos os campos do modelo;
- endereço de internet, script, tag HTML, caractere invisível ou texto longo demais;
- em arquivo de texto (firmware, `.yaml`, `.env.exemplo`): linha com senha ou chave;
- parâmetro fora da `faixa_aceita` ou mudança no bloco do contrato do aparelho (`aparelho`, `ble`);
- troca de texto com sinal de código, com `antes` que não aparece exatamente uma vez, com aspas diferentes ou em arquivo que não está na lista;
- parte do arquivo que mudou no sistema depois do kit (precisa de junção à mão).
