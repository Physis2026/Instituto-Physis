# Comunidade aberta do Instituto Physis

Versão de 19/11/2026 (etapa 1 do site do Instituto e da Rede InovaSTEM). Código: `physis_hub/comunidade.py`, com
leitura aberta e moderação prévia do Physis 3D em `physis_hub/impressao3d.py`. Testes: `tests/test_comunidade.py`.

## Em uma frase

Qualquer pessoa **lê** o site, o fórum e a biblioteca do Physis 3D **sem conta**. Para **publicar**, a pessoa faz o
próprio cadastro, aceita os termos (LGPD) e o que ela escreve só aparece **depois que a equipe aprova**.

## Regras (decisões de 19/11/2026)

| Regra | Como funciona |
|---|---|
| Leitura aberta | `GET /api/publico/...` nunca usa a sessão: mostra só o que está publicado e aprovado |
| Cadastro próprio | `POST /api/publico/cadastro`, só com `"cadastro_aberto": true` no `instancia.json` (o pacote do Instituto liga). Vira participante (papel `cliente`). Limite por IP de `PHYSIS_LIMITE_ENTRAR` |
| Aceite LGPD | obrigatório no cadastro (`consentimento: {aceito, versao}`); fica registrado como o das outras contas |
| Menor de 18 anos | informa nome e e-mail do responsável legal; navega, mas só publica depois que a equipe registra a autorização |
| Moderação prévia | tópico, resposta, peça 3D, tópico e mensagem do fórum 3D ficam "aguardando moderação"; o autor vê o próprio item; a recusa pede motivo. Liga com `"moderacao_previa": true` |
| InovaSTEM Delas | categoria só para mulheres (cis e trans) por autodeclaração voluntária (política 29). Só a própria pessoa e a direção sabem quem se declarou; a autodeclaração não vai para o registro encadeado nem para a fila de moderação |
| Sair (LGPD) | `POST /api/comunidade/sair` ou apagar a conta: o nome vira "Participante removido"; responsável e autodeclaração são apagados; o que foi publicado segue sem nome |

## Rotas

| Rota | Quem | Para quê |
|---|---|---|
| `GET /api/publico/comunidade/categorias` | todos | categorias do fórum (Geral, Rede InovaSTEM, InovaSTEM Delas, Physis 3D, Eventos, Parcerias) |
| `GET /api/publico/comunidade/forum?categoria=` · `/forum/<id>` | todos | tópicos e mensagens publicados (Delas: 403) |
| `GET /api/publico/3d/pecas` · `/pecas/<id>` · `/pecas/<id>/memorial` · `/forum` · `/forum/<id>` · `/arquivo/<sha256>` · `/materiais` | todos | biblioteca aberta do Physis 3D |
| `POST /api/publico/cadastro` | todos (limite por IP) | cadastro próprio |
| `GET /api/comunidade/eu` · `/forum` · `/forum/<id>` | participante | situação, fórum com Delas e os próprios pendentes |
| `POST /api/comunidade/forum` · `/forum/<id>` · `/delas` · `/participante` · `/sair` | participante (CSRF) | publicar, responder, autodeclarar, nome público, sair |
| `GET /api/comunidade/moderacao` · `POST /api/comunidade/moderar` | equipe | fila única: fórum, menores e Physis 3D (`tipo`: topico, mensagem, menor, p3d_peca, p3d_topico, p3d_mensagem) |

## Site (etapa 2, 19/11/2026)

`web/site.html`, servido pelo hub do Instituto em `/` (a plataforma, com login, passa para `/plataforma/`; nas outras
instalações `/` continua sendo a plataforma). Abas: Início, Rede InovaSTEM, InovaSTEM Delas, Physis 3D (biblioteca aberta,
fórum e quadro de modelagem: o que funciona e o que está em desenvolvimento), Parcerias e projetos, Eventos, Longo prazo e
Participar (cadastro, autodeclaração Delas, sair e, para a equipe, a fila de moderação). Português e inglês, tema claro e
escuro, barra única de preferências, um título só, sem internet. Números vindos dos documentos levam `[CONFERIR]`; o que
falta é `[MARCADOR]`. Testes: `tests/test_site.py`; conferência no navegador em `ferramentas/testes-navegador/telas.html`.

## Agenda de eventos e oportunidades (etapa 3, 19/11/2026)

`physis_hub/agenda.py`. Quatro tipos mapeados, mais os eventos do próprio Instituto: hackathons de segurança e computação
quântica; modelos virtuais e gêmeo digital; feiras e eventos de outras redes; desafios abertos e chamadas.

| Origem | Como entra |
|---|---|
| Equipe | `POST /api/agenda/criar`: publicado na hora (a equipe é a moderação) |
| Participante | `POST /api/agenda/sugerir`: "sugerido", vai para a fila única de moderação (`tipo: evento`) |
| Coletor de eventos (`editais.py`) | `POST /api/agenda/importar` (equipe): só os itens dos quatro tipos, como "sugerido"; o mesmo item nunca entra duas vezes. O coletor passou a reconhecer hackathon, CTF, desafio, challenge, maratona e competição |

`GET /api/publico/agenda?categoria=` mostra só o publicado que ainda não terminou (ou sem data, "data a confirmar"); a equipe vê
tudo em `GET /api/agenda`. Link só `https://`; data `AAAA-MM-DD`; o que o coletor não achou fica vazio. Novas fontes de
hackathons e desafios entram pela lista de fontes do coletor (a equipe acrescenta e confere cada endereço). Testes:
`tests/test_agenda.py`.

## O que ainda falta (próximas etapas)

- Fontes públicas de hackathons e desafios no coletor: a equipe escolhe e confere os endereços (nenhuma foi acrescentada
  sem conferência).
- Aviso por e-mail ao responsável legal e à pessoa quando a moderação decidir (hoje fica só no registro).
- Marca, logo e cores do Instituto, da InovaSTEM e da InovaSTEM Delas: esperam o M&V (D43).
