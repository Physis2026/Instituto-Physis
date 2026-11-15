# Integridade dos dados para registro em blockchain

Princípio do núcleo do sistema, decidido em 15/11/2026 (documento 01, seção 0.1):

- **A Physis entrega** o mapeamento e a integridade dos dados.
- **O parceiro entrega** a camada de blockchain, os tokens e a custódia.
- O valor da Physis não está no blockchain, e sim em garantir que os dados que entram nele sejam **corretos, rastreáveis, auditáveis e no formato que o parceiro consome**.

A Physis não emite tokens, não guarda chaves de carteira, não faz custódia, não opera nem escolhe a rede. Nenhum nome de parceiro aparece no código ou nos documentos.

## Divisão de responsabilidades

| Etapa | Physis | Parceiro |
|---|---|---|
| Medir no campo | Aparelho com ID e chave próprias, calibração registrada | — |
| Validar | Faixas de validade, dado suspeito marcado, falhas de envio registradas | — |
| Calcular | Metodologia, normas e fatores versionados (17_Metodologia_e_Normas) | — |
| Mapear | Dicionário de dados: cada campo com nome, unidade, origem e definição | Informa o esquema que consome |
| Fechar o lote | Lote imutável com resumo SHA-256 e a trilha de origem | — |
| Registrar | Entrega o lote e o resumo | Grava na rede, emite tokens e faz a custódia |
| Auditar | Guarda o lote original; qualquer um refaz a conta e confere o resumo | Mostra o registro na rede |

## O que cada registro leva (proposta, Fase 2)

- `origem`: aparelho (ID), local (lote, setor ou ponto), firmware, data e hora (UTC e local).
- `calibracao`: data e responsável da última calibração do sensor.
- `metodo`: versão da metodologia, das normas e dos fatores de emissão usados.
- `qualidade`: válido, suspeito ou corrigido; se corrigido, quem, quando, por quê e o valor anterior.
- `evidencias`: referências aos documentos e fotos guardados na plataforma.
- `lote`: identificador, período coberto, quantidade de registros e resumo SHA-256 do conteúdo.

Nada é apagado: uma correção gera um registro novo que aponta para o anterior. O lote fechado não muda; um erro achado depois entra num lote de correção.

## O que já existe e o que falta

**Já existe:**
- aparelho com chave própria (SEGURANCA.md);
- metodologia e normas versionadas (METODOLOGIA.md);
- evidências da certificação (EVIDENCIAS.md);
- inventário GHG (CARBONO_GHG.md);
- exportação em formato aberto (EXPORTACAO.md).

**Feito em 15/11/2026:** `physis_hub/integridade.py`, com testes em `tests/test_integridade.py`.
- `fechar_lote` recusa registro incompleto, id repetido e dado suspeito, e grava o resumo SHA-256 do lote e de cada registro.
- `conferir_lote` refaz os resumos.
- `corrigir` cria a correção sem apagar o registro anterior.

**Falta (Fase 2):**
1. Ligar o lote aos dados reais: Monitoramento, Carbono, SbN e Certificações.
2. Criar a rota no servidor e o botão "Fechar lote" na tela.
3. Fazer o esquema de exportação no formato que o parceiro informar.
4. Conferir a ida e volta: o resumo calculado pela Physis tem de bater com o que o parceiro registrou.

Depende do parceiro informar o formato e o tipo de dado de cada token (crédito de carbono, área de SbN, água, energia).
