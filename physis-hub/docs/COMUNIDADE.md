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

## O que ainda falta (próximas etapas)

- Etapa 2: as páginas do site (Início, InovaSTEM, InovaSTEM Delas, Physis 3D, Parcerias e projetos, Eventos, Longo prazo),
  em português e inglês, com a barra de preferências e as regras de acessibilidade do `CLAUDE.md`.
- Etapa 3: agenda própria e coletor de oportunidades com hackathons (segurança, computação quântica, modelos virtuais e
  gêmeo digital, feiras, eventos de outras redes, desafios abertos e chamadas).
- Aviso por e-mail ao responsável legal e à pessoa quando a moderação decidir (hoje fica só no registro).
- Marca, logo e cores do Instituto, da InovaSTEM e da InovaSTEM Delas: esperam o M&V (D43).
