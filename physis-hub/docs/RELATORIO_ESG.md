# Relatório ESG e taxonomia

Explicação simples: um relatório pronto para mostrar a banco e investidor, montado com o que a organização
já registrou na plataforma. O que falta aparece escrito como lacuna, com o lugar onde preencher.

## Arquivo e contrato

`sistema/physis-relatorio-esg.js` define três funções globais:

- `relatorioEsgDados()` — junta os dados deste aparelho (leitores do painel quando existem; senão, localStorage);
- `relatorioEsgHtml(dados)` — devolve o HTML do relatório (títulos a partir de `h2`, para entrar dentro de uma aba);
- `telaRelatorioEsg()` — atalho: `relatorioEsgHtml(relatorioEsgDados())`.

O “Baixar esta tela” da plataforma exporta o HTML para Word, PDF ou Excel. Há regras de impressão
(`@media print`) para não quebrar seções no meio.

## Estrutura (metodologia IGEA, Physis)

A ordem segue a base de conteúdo da metodologia IGEA (Physis): identificação e limites → linha de base e
qualidade dos dados → indicadores → maturidade da gestão → medidas e investimento → prontidão para financiamento
→ conclusões.

1. Resumo executivo (principais números e metas)
2. Limites do relato e qualidade dos dados (cobertura das contas, parte medida, incerteza)
3. Ambiental: energia, água, resíduos, carbono por escopo e por gás, biodiversidade e SbN
4. Social: segurança do trabalho (rotina da Gestão e gap da ISO 45001), capacitação (cursos concluídos),
   acessibilidade, pessoas, diversidade
5. Governança: maturidade em 13 elementos (escala 1 a 5, ids `igea_01` a `igea_13` da base de certificações),
   certificações, sistemas de gestão, plano de ação, SBCE
6. Medidas, investimento e prontidão para financiamento (7 requisitos)
7. Taxonomia Sustentável Brasileira (contribuição substancial, não causar dano significativo, salvaguardas
   mínimas; atividades com indício nos dados — “verificar” nos cadernos publicados)
8. Correspondência com GRI, IFRS S1/S2 e CBPS 01/02 (só códigos)
9. Lacunas de dados (lista automática)
10. Nota metodológica

## Chaves lidas

`physis-perfil`, `physis-carbono` (via `PhysisCarbono.resumo()`), `physis-residuos-plano`, `physis-sbn`,
`physis-gestao-cliente`, `physis-cert-gap`, `physis-calc-solar`, `physis-curso-*`.

## Fase 2

- Registro de acidentes, horas trabalhadas e horas de treinamento (GRI 403-9, 404-1).
- Diagnóstico de acessibilidade do lugar (ABNT NBR 9050) e composição da equipe (GRI 405-1).
- Conferir a numeração dos parágrafos de IFRS S1/S2 e CBPS na versão vigente e os critérios técnicos de cada
  caderno da Taxonomia.
- Campos de financiamento (prazo, carência, reserva, análise de crédito) para fechar a prontidão.
