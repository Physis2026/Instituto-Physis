# Sistema Physis · guia para o Claude Code

Leia este arquivo antes de qualquer mudança. Os detalhes estão em `physis-hub/docs/`.

## Pastas

| Pasta | O que tem |
|---|---|
| `physis-hub/` | Servidor, loja e plataforma do cliente, testes e documentos |
| `sistema/` | Os quatro programas internos e as duas bibliotecas |
| `desenhos/` | Rascunhos aprovados e ainda não construídos |
| `demos/` | As três demonstrações da Physis, como foram enviadas |
| `pacotes/` | Três pacotes prontos para ligar: simplificado, completo e servidor da Physis (gerados; fora do Git) |
| `firmware/` | Receptor V6, Transmissor V6, Caixinha (ESPHome), animais (SmartColar, AutoFeeder). Segredos em `secrets.h`, fora do Git |
| `modulos/` | SustainKit (HTML, React e planilhas) e Planejador, ainda fora da plataforma |

## O que é

Três sistemas separados, com pouca ligação entre eles:

| Sistema | Arquivo principal | Para quem |
|---|---|---|
| Site (loja) e plataforma do cliente | `physis-hub/web/painel.html` | Cliente |
| Gestão Physis (interna) | `sistema/gestao-interna-physis.html` (servida em `/gestao/`) | Direção e administrativo |
| Central de clientes | só desenho, em `desenhos/` | Equipe técnica |

Programas da Physis que a plataforma abre: `SustainKit_Definitivo.html`, `physis-scada-demo.html`, `physis-tela-cliente.html`.
O servidor é `physis-hub/physis_hub/` (Python 3.10, sem dependências).

## Regras que não se quebram

1. Não inventar preço, limite técnico, texto legal, nome de cliente nem número. O que falta vira `[MARCADOR]`.
2. Não mudar função nem conta dos programas da Physis. Neles, só aparência, pela folha `TEMPLATE_PROG`.
3. Na água, nenhum limite vem de fábrica, e limite provisório não gera alerta.
4. Toda conta que existe na tela e no servidor é espelho: muda nos dois, com teste (`ph_eletrodo.py`, `agua.py`, `investimento.py`, `protocolo.py`).
5. Acessibilidade: teclado, foco visível, nome em cada controle, contraste AA, alvos de 44 px (36 px nas ferramentas do cabeçalho), sem rolagem lateral a 320 px.
6. Só cores de `physis-hub/docs/PALETA.md`. Sem tema escuro. Sem internet nas telas.
7. A seleção de módulos existe só na loja.
8. Nome, CPF ou CNPJ, e-mail e telefone são obrigatórios só no pagamento e no pedido de projeto personalizado.
9. Plataforma, Gestão Physis e Central de clientes não se misturam.
10. Um título só por tela: árvore + serifada (Fraunces, Georgia), no verde `#33512F`. Nada de cabeçalho repetido.
11. Independência: nada pode depender de serviço de terceiros para funcionar. Software aberto, hospedado pela Physis ou pelo cliente; arquivos em ODF e PDF/A; IA e bots com modelo aberto no próprio servidor. Serviço externo (WhatsApp, Power BI, GitHub) só como opção ou espelho, nunca como único caminho.
12. Segredos (senhas, chaves, tokens, números pessoais) nunca no código: `secrets.h` ou variáveis de ambiente, fora do Git.

## Comandos

    cd physis-hub
    python3 -m unittest discover -s tests     # 54 testes
    python3 estresse.py                        # 10 cenários
    python3 -m physis_hub.servidor             # sobe o servidor (porta 8700)
    python3 montar.py --org <nome> --modulos monitoramento,agua,sustainkit[,supervisao,gestao] --sustainkit <arquivo> [--supervisao <arquivo>]

## Onde ler

| Documento | Para quê |
|---|---|
| `physis-hub/docs/MEMO-CLAUDE-CODE.md` | Tarefas numeradas, com onde mexer e critério de aceite. Comece pelas seções 8 a 11. |
| `physis-hub/docs/CHECKLIST.md` | Tudo o que foi pedido e a situação de cada item. |
| `physis-hub/docs/LISTA-DE-MODIFICACOES.md` | O que mudou nas últimas rodadas e a separação dos três sistemas. |
| `physis-hub/docs/ROADMAP.md` | Ordem das etapas. |
| `physis-hub/docs/PALETA.md` | Cores aceitas. |
| `physis-hub/docs/PROTOCOLO.md` | Linhas V6 (reconstruído do firmware). |

## Antes de entregar

Rodar os testes, dizer o que não foi verificado e não marcar como pronto o que só foi desenhado.
