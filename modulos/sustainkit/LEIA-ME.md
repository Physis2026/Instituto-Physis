# SustainKit — pacote de código (snapshot de 13/11/2026)

Physis Engineering Ltda. · Responsável: Erick Lopes

## Qual é a versão mais atual?
**`01_HTML_versao_atual/SustainKit_Definitivo.html`** é a versão mais completa e a referência.
Abre com duplo clique no Chrome ou Firefox (não Brave), sem instalar nada, funciona offline.
Tem 10 abas: Energia+Água, Materiais, Orientação Solar, Certificações, Acabamentos, Checklist,
Modelos de Negócio, Agro Solar, **Carbono** e **Preços**, mais o botão "Modo Apresentação".

## O que tem em cada pasta
| Pasta | Conteúdo | Situação |
|---|---|---|
| 01_HTML_versao_atual | Definitivo (completo), Apresentacao (5 abas pré-preenchidas, para demo), Demo (4 abas, versão simples anterior) | Definitivo e Apresentacao = atuais |
| 02_Modulos_React_JSX | Energy, Water, Materials, Cert, Agro (módulos separados), Completo_Demo e Demo_Physis | **Defasados em relação ao HTML** (ver abaixo) |
| 03_Projeto_Vite | Projetos para build (npm install / npm run build / npx serve dist) | **Defasados** (App.jsx de 20/08) |
| 04_Planilhas_Excel | Physis_Integrado_v9, ChaleVerde_v8, SustainKit_v8 e módulos Energy/Water/Materials/Cert (v1), Agro (v2) | Base técnica LEED v5; sem a aba de Carbono |

## Atenção — o que está defasado
- As abas **Carbono** e **Preços** e o **Modo Apresentação** existem **só no HTML Definitivo**.
  Os JSX, os projetos Vite e as planilhas ainda não têm essas partes.
- Não existe `SustainKit_v9.xlsx`; a planilha mais nova é `Physis_Integrado_v9.xlsx`.
- O banner de posicionamento do Definitivo cita "LEED, EDGE e WELL", mas **WELL ainda não está implementado**.

## Dados ainda por levantar (não estão no app)
WELL Building Standard (critérios por conceito) · PRONAF Verde / ABC Agro (elegibilidade) ·
EUDR (UE 2023/1115) · EPDs verificáveis dos materiais · ASHRAE 90.1 por tipologia.

## Dados e premissas
- Preços (módulos, CAPEX, ROI) são **provisórios**; referência: memória de cálculo Physis, Abril/2025, Petrópolis.
- Irradiação por cidade (HPS) está fixa no código (PVGIS ERA5), sem chamada à API.
- Fatores de carbono: rede SIN 0,0289 tCO₂/MWh · diesel 0,74 kgCO₂e/kWh · biogás 2,75 kgCO₂e/m³.
- Inventário não é crédito de carbono; a verificação externa (ISO 14065) continua necessária.

## Correção feita hoje
O `SustainKit_Apresentacao.html` enviado antes tinha erro de JavaScript (aspas quebradas) e não calculava nada.
Foi corrigido e testado em navegador simulado: Definitivo e Apresentacao rodam sem erros.

## Fora do pacote de propósito
`SustainKit_Demo_FISIS.jsx` (nome errado e versão antiga) e `SustainKit_Completo_Online.html` (versão de agosto, substituída).
