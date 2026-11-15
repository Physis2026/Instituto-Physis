# Servidor verde (EM DESENVOLVIMENTO)

Situação: **em desenvolvimento** (responsável: Eric Oliveira). Item da loja com estado `dev` (interno, não aparece
no site público); aparece na Casa Physis e nas telas internas com o selo “Em desenvolvimento”. Ainda **sem linha
pública de consultoria**. A tela tira o selo só quando a plataforma marcar `window.SERVIDOR_VERDE_PRONTO = true`.

Explicação simples: a partir do que o sistema precisa fazer (usuários, sensores, mapas, IA), escolhe e confere a
máquina e os programas, e calcula disco, internet, energia (com nobreak e solar), calor da sala, carbono e custos.
Serve para qualquer projeto: Casa Physis, clientes e terceiros.

## Arquivos

| Arquivo | O que faz |
|---|---|
| `sistema/physis-servidor-verde.js` | Tela (`telaServidorVerde()`), contas, projetos, relatório. `window.SERVIDOR_VERDE`, `window.SERVIDOR_VERDE_I18N` |
| `sistema/physis-servidor-catalogo.json` | Catálogo de módulos: hardware por classe genérica, programas abertos, modelos, perfis, curvas 80 PLUS |
| `physis_hub/servidor_verde.py` | Espelho das contas e das conferências em Python |
| `tests/test_servidor_verde.py` | Regras de mesa, espelho com a tela, catálogo, conferências e contrato da tela |

## Projetos

Cada projeto tem nome, perfil, parâmetros (`p`) e seleção de módulos (`sel`). Criar (a partir de um perfil),
duplicar, renomear, apagar (com confirmação), exportar e importar JSON. Guardado em `localStorage`
`"physis-servidor-verde"` = `{v:1, atual, projetos:[{id, nome, perfil, criado, p, sel}]}`.

Perfis de partida (todos “verificar”): Casa Physis (hub + IA 2×8 GB; alternativa em estudo 4×16 GB),
Pequena empresa / fazenda, Escritório com BI e mapas, Servidor de IA (GPU), Datacenter/colocation, Personalizado.
Nada fica preso a um lugar: sol, fator da rede e tarifa vêm do lugar do projeto (latitude e longitude → sol da
NASA POWER guardado no servidor, `api/gis/irradiacao`; ou digitado).

## Subabas

1. **Seleção de módulos** (primeiro passo): filtros, busca, quantidades de hardware, programas, modelo de IA,
   perfil pronto; somas (núcleos, memória, vídeo, disco, W parado e pico) e conferências ao vivo.
2. **Cargas de trabalho**: instalações, usuários, sensores × leituras, retenção, pedidos, BI, mapas, cálculos, documentos, IA.
3. **Computação**: núcleos, memória, memória de vídeo (parâmetros × bytes × 1,2), placas, configuração atual × alternativa, faixa recomendada.
4. **Armazenamento e cópias**: crescimento do banco, arquivos, mapas, modelos, RAID, fotos do disco, cópia 3-2-1 fora do lugar, tempo de restauração.
5. **Rede**: subida e descida, cópia por noite, latência, VPN, link reserva.
6. **Energia**: componentes (ou a seleção), fonte 80 PLUS (curva pela carga), kWh por dia e mês, nobreak (VA, Wh, Ah, lítio × chumbo), solar (kWp e bateria para a noite e dias nublados), IA nas horas de sol.
7. **Térmico e ambiente**: W → BTU/h e TR, ar-condicionado (COP) ou ventilação com ar de fora, PUE, faixa ASHRAE TC 9.9 (classe A1), rack, poeira, ruído.
8. **Carbono e custos**: operação com o fator do lugar, sem solar, em datacenter; fabricação (escopo 3, cat. 2); custo de energia, investimento solar, retorno (`analiseInvest` quando existe).
9. **Resultado**: relatório do projeto (identidade Physis, data, perfil), lista de materiais (custos `[MARCADOR]` sem orçamento), boas práticas, comparação com a medição real (`/api/servidor/pegada`), imprimir, exportar e importar.

## Conferências da seleção

Placa de vídeo sem encaixe x16 (Raspberry Pi e mini PC) · mais placas que encaixes · vLLM sem placa ou fora do x86 ·
Proxmox fora do x86 · Raspberry Pi OS sem Raspberry · processador sem plataforma do mesmo encaixe (e o contrário) ·
formato da memória · memória sem ECC em servidor (aviso) · memória acima do máximo · memória menor que a soma dos
programas (+ o modelo, quando a placa não comporta) · threads menores que os programas (aviso) · modelo maior que a
memória de vídeo (erro com vLLM; aviso com Ollama e llama.cpp) · fonte menor que o pico × 1,3 · nobreak menor que o
pico na tomada · disco menor que o crescimento + programas · dependências (PostGIS, TimescaleDB e Superset pedem PostgreSQL).

## Regras de mesa (testes)

| Caso | Resultado |
|---|---|
| Modelo 7B em 4 bits | 4,2 GB de vídeo; 70B: 42 GB (3 placas de 16 GB; 4 com 30% de folga) |
| 60 sensores, 1 leitura/min, 200 B, 10 anos | 63,1 GB |
| Nobreak 600 W pico, 500 W médio, 30 min, lítio | 833 VA; 309 Wh |
| 3,6 kWh/dia, 4,5 h de sol, PR 0,75 | 1,07 kWp |
| 1.000 W | 3.412 BTU/h = 0,284 TR |
| TI 10 kW, ar 3 kW, perdas 0,5, luz 0,1 | PUE 1,36 |
| Casa Physis (seleção do perfil, sol 4,5) | 151 W médios, 464 W pico, fonte 83% (750 W com pouca carga), 110 kWh/mês, 1,07 kWp, 0,149 tCO₂e/ano de fabricação |

## Falta (fase 2)

- Curadoria Eric: faixas de potência e TFLOPS por classe, regra de núcleos e memória por serviço, tokens por segundo medidos.
- Medir a Casa Physis e calibrar o dimensionado com a pegada real.
- Inglês: `SERVIDOR_VERDE_I18N` cobre títulos e botões; frases de ajuda ainda só em português.
