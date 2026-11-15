# Dados da nota fiscal de serviço

Documento interno para conferência. A nota é emitida no provedor de NF (Fase 2: Asaas, doc 21) com estes dados,
depois da aprovação.

## Prestador

- Razão social: {{prestador.razao_social}}
- CNPJ: {{prestador.cnpj}}
- Inscrição municipal: {{prestador.inscricao_municipal}}
- Município: {{prestador.municipio}}

## Tomador

- Nome ou razão social: {{cliente.nome}}
- CPF ou CNPJ: {{cliente.documento}}
- E-mail: {{cliente.email}}
- Endereço: {{cliente.endereco}}

## Serviço

- Código do serviço (lista municipal): {{servico.codigo}}
- Alíquota de ISS: {{servico.aliquota_iss}}
- Descrição: {{servico.descricao}}
- Competência: {{nf.competencia}}

{{itens_tabela}}

**Valor total: {{nf.valor_total}}**

Pedido {{pedido.numero}} · recibo {{pedido.recibo}} · fatura {{pedido.fatura}}
