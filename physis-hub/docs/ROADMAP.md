# Roteiro do Sistema Physis

Situação em 14/11/2026. As etapas estão na ordem em que destravam umas às outras. Não há datas: elas dependem de
decisões e de equipe que a Physis ainda vai definir.

## Onde estamos

Versão de teste pronta, sem cobrar e sem equipamento ligado:

- **Loja (site):** 35 soluções em cartões, compra de teste, recibo numerado a partir de 0000, pedido de projeto personalizado com arquivos.
- **Plataforma do cliente:** Início, Monitoramento verde, Qualidade da água, SustainKit, SCADA, Gestão e Resumo.
- **Gestão interna:** propostas com revisão da equipe, contratos emitidos sozinhos, consultores, financeiro com comprovantes, fornecedores e alertas.
- **Servidor local:** liga a loja à gestão; 42 testes.

## Etapa 1 · Fechar a versão de teste

Objetivo: você aprovar tela por tela, sem dado inventado.

1. Conferir o quadro de revisão.
2. Responder às decisões abertas (memo, seção 5).
3. Conferir os campos novos do Início e da Gestão do cliente.
4. Fechar a paridade do Monitoramento verde com o painel original (T14).
5. Template de design completo nos programas (T18).

Sai desta etapa: uma versão que pode ser mostrada a um cliente de confiança, sem cobrar.

## Etapa 2 · Primeiro piloto com equipamento

Depende de: correções de rádio e segurança (T01 a T03) e de alguém com os aparelhos.

1. Roteiro de 12 passos no hardware.
2. Entrada das leituras de pH e os limites (T16).
3. Calibração do sensor de solo.
4. Dados do Início e das calibrações no servidor (T11, T17).

Sai desta etapa: um lugar real medindo, com histórico baixável.

## Etapa 3 · Vender de verdade

Depende de: provedor de pagamento, hospedagem com HTTPS, textos legais e preços confirmados.

1. Pagamento real e nota fiscal (T40).
2. E-mail de pedidos e avisos (T41).
3. Página pública da loja com as demos (T45).
4. Contrato com cláusulas revisadas (T52).
5. Senha por pessoa na gestão interna (T31).

Sai desta etapa: a primeira venda sem intervenção manual.

## Etapa 4 · Atender e crescer

1. Envio dos dados do cliente ao servidor Physis (T42).
2. Página de suporte à distância (T43) e canal de barreira (T44).
3. Resumo com números de todos os programas (T13).
4. Telas em inglês (T21).
5. Testes com leitor de tela, pessoas neurodivergentes e PcD (T60, T61).

## Cursos

Ainda não existe nada de cursos. A decisão registrada é começar numa plataforma de cursos pronta.

1. Escolher a plataforma de cursos.
2. Pôr os cursos na loja, com a mesma conta da plataforma de sistemas (T70).
3. Aba “Cursos” na plataforma do cliente, abrindo o curso comprado.
4. Depois de um ciclo de uso, decidir se o conteúdo vem para dentro do sistema.

## Inclusão dos 28 projetos

Na ordem do roteiro de informações. Um projeto só muda de “sob consulta” para “disponível” depois de responder às
oito perguntas e de ter tela aprovada.

| Fase | Projetos | O que falta primeiro |
|---|---|---|
| 1 · Teste | P2 SustainKit, P1 Kit Monitoramento, P6 Qualidade da água | Validade do preço; preço do kit; sensores e limites da água |
| 2 · Software com ESP32 | P3, P4, P8, P5, P9, P10, P15, P18, P22, P24 | Ficha de cada um; firmware onde existir |
| 3 · Somente software | P12 Calculadora de carbono, P13 Planejador | Se o P12 é o mesmo cálculo do SustainKit |
| 4 · ESP32 opcional | P7, P14, P20, P23, P26, P27, P28 | Se entram na loja e como são vendidos |
| 5 · Sem eletrônica | P11, P16, P17, P19, P21, P25 | Se entram na loja; P25 exige checar registro sanitário |

## Próximas revisões já mapeadas

- **Depois de cada etapa:** regressão completa e atualização do quadro, da checklist e deste roteiro.
- **Antes da Etapa 2:** revisão técnica das quatro dúvidas do pH e do protocolo reconstruído contra o original.
- **Antes da Etapa 3:** revisão jurídica (LGPD, contratos, Anatel) e revisão de preços.
- **Antes de abrir ao público:** auditoria de acessibilidade com pessoas.
