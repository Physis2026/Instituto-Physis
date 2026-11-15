# Incorporar as revisões dos módulos (guia do Eric)

Os engenheiros revisam os kits (`KITS_REVISAO.md`) e devolvem um ZIP. Este guia é o caminho do ZIP até o sistema, sem mudar a estrutura do que foi construído. Regra de ouro: **nada entra direto na `main`**. Cada devolução vira uma branch `revisao/<módulo>-<data>`, com teste, e só entra por merge depois de lida.

Ferramentas (só Python, sem dependências):

- `ferramentas/gerar_kits_revisao.py` gera os kits;
- `ferramentas/validar_devolucao.py` confere a devolução e, com `--aplicar`, aplica numa branch.

## 0. Gerar e enviar os kits

Com o sistema integrado e **commitado** (o manifesto guarda o commit e avisa se algum arquivo do kit tem mudança não salva no Git):

    python ferramentas/gerar_kits_revisao.py --saida "<pasta dos kits>"
    python ferramentas/gerar_kits_revisao.py --saida "<pasta dos kits>" --modulo sbn --modulo carbono

Cada módulo vira a pasta e o ZIP `kit-<id>-<data>` (cerca de 5 MB cada, por causa da prévia, que leva uma cópia da plataforma de demonstração; `--sem-previa` gera kits pequenos, sem `ABRIR-PREVIA.html`). A prévia é montada a partir de `physis-hub/web/painel.html` com os mesmos ajustes de `demos/gerar_demos.py`, com todos os módulos ligados; se um ajuste não couber mais, usa `demos/physis-demo-cliente.html` e avisa. A pasta `<pasta dos kits>/_manifestos/` guarda a cópia do manifesto de cada kit: **guarde essa pasta**, o validador usa ela (o manifesto que volta com o revisor não é confiável). Mande a cada responsável só o ZIP do seu kit.

Os textos do LEIA-ME vêm de `ferramentas/kits/modulos.json`, de `sistema/physis-metodologia.json` (cálculos e adequações) e, se a pasta existir, dos documentos 17 e 18 (`--documentos <pasta>`, padrão: a pasta "Sistema Physis" dos documentos).

## 1. Receber o ZIP

Guarde o ZIP numa pasta de entrada (fora do repositório). Não abra nem rode nada que venha nele: o validador só lê.

## 2. Validar

    python ferramentas/validar_devolucao.py devolucao-kit-sbn-2026-11-15-Rafaella.zip --kits "<pasta dos kits>"

O relatório diz, em português:

- **Situação:** ACEITA NA VALIDAÇÃO, ACEITA (nada a aplicar) ou RECUSADA;
- **Erros:** o que impede (chave apagada, referência mudada, endereço de internet, deriva…);
- **Avisos:** ficha faltando, texto longo (pode ser cópia de norma), arquivo ignorado;
- **O que mudou:** cada valor, "era X, ficou Y", com o caminho no arquivo e o nome do item.

Recusada: devolva o relatório ao revisor (`--relatorio relatorio.md` grava o texto) ou corrija você mesmo no ZIP e valide de novo.

## 3. Aplicar numa branch

Com a árvore do Git limpa (`git status` sem nada; se tiver, faça commit ou `git stash` antes):

    python ferramentas/validar_devolucao.py devolucao-kit-sbn-2026-11-15-Rafaella.zip --kits "<pasta dos kits>" --aplicar --relatorio relatorio-sbn.md

O que acontece:

1. cria a branch `revisao/sbn-<data de hoje>` a partir da branch atual (se já existir, `-2`, `-3`…);
2. grava as mudanças **mantendo a formatação do arquivo** (só a linha do valor muda; o diff fica pequeno);
3. roda o que o arquivo pede, nesta ordem: metodologia → copia para `sistema/physis-metodologia.js`; bases e programas embutidos no painel (plantas, certificações, equipamentos, fatores, evidências, inglês, metodologia, `sistema/*.js` com troca de texto) → `ferramentas/embutir_bases.py`; casos do AVAC → refaz `teste-avac.html`; troca de texto num programa HTML → `ferramentas/sincronizar.py`; e, sempre que o painel mudou → `demos/gerar_demos.py` (as demos são cópias do painel);
4. roda os testes do módulo e a suíte inteira (`python -m unittest discover -s tests` em `physis-hub`);
5. faz um commit **na branch** e volta para a branch de antes. Nunca faz push.

Saída 0 = testes OK; 2 = aplicado na branch, mas teste falhou (a mensagem do commit diz "não juntar"); 1 = recusado ou interrompido (nesse caso nada fica mudado e a branch é apagada).

## 4. Ler a mudança e decidir

    git diff main...revisao/sbn-2026-11-20
    git log -1 revisao/sbn-2026-11-20

Confira com a `FICHA_REVISAO.md`: cada mudança tem motivo e fonte? Valor com cara de inventado (sem fonte) volta para o revisor. Se o teste falhou, veja no relatório qual: em geral é um valor que o teste confere contra outra base (por exemplo, o fator da rede igual em `physis-premissas.json` e no núcleo). Corrija na própria branch ou devolva ao revisor.

## 5. Juntar

    git switch main
    git merge --no-ff revisao/sbn-2026-11-20 -m "Revisão SbN (Rafaella)"
    cd physis-hub && python -m unittest discover -s tests

## 6. Refazer pacotes e demonstrações

Depois do merge, com os testes verdes:

    python ferramentas/embutir_bases.py
    python ferramentas/sincronizar.py
    python demos/gerar_demos.py
    cd physis-hub && python montar.py ...        # pacotes, como de costume

Rode os testes de novo e faça um commit "Pacotes e demos refeitos depois da revisão".

## 7. Marcar a versão

    git tag -a revisao-sbn-2026-11-20 -m "Revisão SbN incorporada (kit-sbn-2026-11-15)"

Anote no documento 18 o item como feito (com data) e, se a revisão mudou a situação de um cálculo, confira que `status` e `o_que_falta` em `sistema/physis-metodologia.json` foram atualizados.

## Desfazer (rollback)

- Ainda não juntou: `git branch -D revisao/sbn-2026-11-20`. Nada mais muda.
- Já juntou: `git revert -m 1 <commit do merge>` (cria um commit que desfaz; o histórico fica). Depois refaça pacotes e demonstrações (passo 6).
- Pacote já instalado num cliente: instale de novo o pacote da tag anterior.

## Conflito (o arquivo mudou no sistema depois do kit)

O validador compara a "impressão digital" de cada **parte** do arquivo que estava no kit com a do sistema hoje. Se a parte do módulo mudou (outra devolução entrou antes, ou alguém mexeu no código), ele para: aplicar por cima perderia uma das mudanças. Mudança em outra parte do mesmo arquivo (por exemplo, outro módulo na metodologia) não atrapalha.

Para juntar à mão (junção em 3 vias):

1. Veja o que mudou no sistema desde o kit: `git log <commit do manifesto>..HEAD -- <arquivo>` e `git diff <commit do manifesto> HEAD -- <arquivo>`.
2. Abra o arquivo devolvido e o do sistema lado a lado. Leve para o arquivo do sistema, numa branch `revisao/...` criada à mão, só os valores que o revisor mudou (a lista "O que mudou" do relatório ajuda).
3. Rode os testes e siga do passo 4.

Alternativa mais simples quando a revisão é grande: gere um kit novo do módulo (`--modulo <id>`) e peça ao revisor para passar as mudanças para ele.

## Trocas de texto (`trocas-de-texto.json`)

Cada troca é aplicada ao pé da letra (`antes` → `depois`) no arquivo indicado, só se o `antes` aparece exatamente uma vez. O validador recusa sinal de código (`< > { } ` + "`" + ` ; =>`, `script`, `javascript:`, `http`), quebra de linha, mais de 400 caracteres, aspas diferentes entre `antes` e `depois` e arquivo fora da lista (só telas `.js`/`.html` e documentos `.md`; nunca Python, firmware, dados nem `physis-metodologia.js`). Texto achado na plataforma (`painel.html`) dentro de um programa embutido vai para o arquivo de origem em `sistema/`; dentro de uma base embutida, é recusado (muda pela base). Se a frase tem tradução em `physis-i18n-modulos.json`, o relatório avisa: a chave em português precisa ser trocada lá também. Mudança de conta, regra ou comportamento não entra por aqui: vem na ficha e é feita por quem mexe no código.

## Parâmetros dos aparelhos (pluviômetro, pulseira, caixinha de remédios)

`firmware/pluviometro/parametros.json`, `firmware/saude/parametros-pulseira.json` e `firmware/saude/parametros-caixinha.json` são a fonte única dos valores de cada aparelho. O validador confere a `faixa_aceita` de cada parâmetro e recusa mudança nos blocos `aparelho` e `ble` (contrato com o hub e com o `physis-ble.js`; o teste `test_kits_revisao` confere que as UUIDs batem com o `BLE_PERFIL.md` e o `physis-ble.js`, e que tolerância, antecedência, bateria baixa e mm por basculada batem com `saude.py` e `robos.py`).

Como o firmware lê os valores, na montagem:

- **Pluviômetro (ESPHome):** o robô Pluviômetro (`physis_hub/robos.py`) recebe `mm_por_pulso`, `intervalo_s` e `pino` — passe os valores `mm_por_basculada`, `intervalo_envio_s` e `pino_gpio` do arquivo — e escreve o YAML. O `debounce_ms` é o filtro do `pulse_counter` (hoje 50 ms fixo no YAML gerado). Os limites de alerta (`alerta_mm_*`) são do hub (painel municipal e alertas de clima), não do aparelho.
- **Pulseira e caixinha (ESP32, PlatformIO):** um passo antes da compilação (`extra_scripts = pre:gerar_parametros.py` no `platformio.ini`) lê o JSON e escreve `include/parametros.h` com um `#define PARAM_<ID> <valor>` por parâmetro; valor `null` vira `#error`, como o `secrets.h`, para nunca sair aparelho sem limite clínico. **Esse script e o firmware ainda não existem no repositório** (`firmware/saude/` só tem o perfil BLE): escrever junto com o firmware. Depois de instalado, `LIMBPM` e `TOL` também mudam pelo comando BLE.
- Se um parâmetro mudar depois do merge, regrave o firmware (ou gere de novo o YAML pelo robô) e anote no documento 18.

## Arquivos de texto (firmware, `.yaml`, `.env.exemplo`)

Nos kits de hardware e do servidor, os editáveis são de texto. O validador mostra as linhas mudadas, recusa linha com senha ou chave e avisa sobre endereços (que devem ser da rede local). Segredos nunca entram: ficam em `secrets.h`, `secrets.yaml` ou variáveis de ambiente, fora do Git.

## Mudar o mapa dos kits

Responsável novo, arquivo novo ou módulo novo: edite `ferramentas/kits/modulos.json` e rode `python -m unittest tests.test_kits_revisao` em `physis-hub`. O teste confere que todo arquivo citado existe, que nenhum segredo entra e que os responsáveis são os confirmados pela direção (mude a lista do teste junto, com a decisão registrada).
