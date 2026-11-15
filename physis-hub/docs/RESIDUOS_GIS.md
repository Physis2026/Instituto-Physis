# Economia circular: mapa dos destinos e painel de indicadores

Parte **Mapa e indicadores** da aba Economia circular.

| Arquivo | O que tem |
|---|---|
| `physis-hub/physis_hub/residuos_gis.py` | Busca na Overpass (OpenStreetMap), classificação, distâncias, grupos, importação manual, CO₂ do transporte, guarda no hub |
| `sistema/physis-circular-mapa.js` | `telaCircularMapa(dados)`: mapa SVG local, legenda, anéis, tabelas e painel de indicadores; MapLibre opcional |
| `physis-hub/tests/test_residuos_gis.py` | Respostas falsas da Overpass: leitura, grupos, distâncias, guarda, importação, CO₂ |

## Fonte automática: OpenStreetMap pela Overpass API

- Endpoint: `https://overpass-api.de/api/interpreter` (troca com `PHYSIS_OVERPASS_URL`, por exemplo para uma Overpass própria).
- Pedido educado: POST, `User-Agent: PhysisHub/1.0`, `[timeout:60]` na consulta e 90 s no cliente, no máximo 800 elementos, raio até 50 km.
- Etiquetas buscadas: `landuse=landfill`, `amenity=recycling` (`recycling_type=centre|container`), `amenity=waste_transfer_station`,
  `man_made=wastewater_plant`, `amenity=composting`, `industrial=scrap_yard|composting|recycling|waste_handling|construction_waste`,
  e `landuse=industrial` com nome de reciclagem, cooperativa, entulho, compostagem ou sucata.
- Categorias (`residuos_gis.CATEGORIAS`): aterro, aterro_controlado, lixao, transbordo, cooperativa, reciclagem, ecoponto, pev, sucata,
  compostagem, rcc, ete. O OpenStreetMap **não** diz se um aterro é sanitário, controlado ou lixão: vem do nome. Conferir licença ambiental e SINIR.
- Guarda: tabela `gis_cache`, chave `residuos:<lat 0,01°>:<lon 0,01°>:<raio arredondado a 5 km>`; uma busca de raio maior serve para um menor.
  Renova a cada 30 dias; se a Overpass falhar ou responder 429/503/504, entrega o guardado e só tenta de novo depois de 1 hora
  (chave `residuos_falha:...`). Depois da primeira busca, funciona sem internet.
- Atribuição obrigatória: "© colaboradores do OpenStreetMap" (ODbL) — a tela mostra.

## Bases nacionais: importação manual

Não há serviço aberto e estável por coordenada; entram por arquivo (`ResiduosGis.importar(pontos)`):

| Base | Onde | Como trazer |
|---|---|---|
| SINIR (MMA): unidades de destinação, relatórios municipais | sinir.gov.br | Baixar a planilha, georreferenciar e exportar CSV |
| IBGE: MUNIC (bloco de saneamento) e PNSB | ibge.gov.br | Dados por município (não por ponto): usar a sede municipal ou o endereço da unidade |
| Órgãos estaduais (CETESB, INEA, FEAM, IAT…) | site de cada órgão | Inventários de aterros e licenças, quando publicados |

Esquema (CSV com `,` ou `;`, decimal com `.` ou `,`; GeoJSON com as mesmas propriedades; polígono usa o centro da caixa):

| Coluna | Obrigatória | Exemplo |
|---|---|---|
| `nome` | não | Aterro Sanitário Regional |
| `categoria` | sim, uma das categorias acima | aterro |
| `lat`, `lon` | sim | -22.41, -43.20 |
| `fonte` | sim | SINIR 2024 |
| `municipio`, `uf`, `situacao`, `licenca`, `obs` | não | — |

Qualquer linha errada recusa o arquivo inteiro. Reimportar a mesma `fonte` substitui os pontos dela.

## Distâncias e grupos

- Haversine com R = 6.371,0088 km; rumo inicial em graus (0 = norte). Distâncias em **linha reta**.
- `agrupar()`: só os pontos dentro do raio, do mais perto ao mais longe; `grupos[categoria] = {rotulo, n, mais_proximo}`.
- `destinos`: o mais próximo para cada destino do plano (`CATEGORIAS_POR_DESTINO`): reciclagem → cooperativa, reciclagem, ecoponto, sucata, PEV;
  logística reversa → ecoponto, PEV, reciclagem; compostagem → compostagem; aterro (rejeito) → aterro, aterro controlado, transbordo.
  Na tela, entulho (tipo `rcc`) procura primeiro RCC. Classe I (aterro de perigosos, incineração) não tem destino no OpenStreetMap.

## CO₂ do transporte

`co2_transporte(kg_mes, dist_km, ...)` (espelho na tela):

1. Fator por t·km, se informado: `kg CO₂e = t · km · fator` (distância carregada, só ida).
2. Senão, viagens de caminhão: `viagens = ⌈t / carga⌉`, `litros = viagens · km · 2 (ida e volta) / consumo`,
   `kg CO₂e = litros · 2,671` (premissa `combustivel.diesel` de `sistema/physis-premissas.json`).
3. Sem fator nem consumo e carga: só t·km, sem CO₂ (o sistema não inventa o fator).

Sugestão para a base de premissas: acrescentar `transporte.fator_tkm` (kg CO₂e por t·km, com fonte e opções por tipo de caminhão);
até lá, o fator é do projeto. A tela tem um multiplicador estrada/linha reta (padrão 1) para quem tiver a distância real.

## Tela (`telaCircularMapa`)

- Mapa SVG próprio (sem fundo de terceiros): projeção local em volta do lugar (km = Δlon·111,32·cos φ, Δlat·110,574), anéis a ¼, ½, ¾ e 1 do raio,
  seta do norte, forma e cor por categoria (cores da PALETA), legenda com contagem.
- Teclado: os 60 pontos mais perto recebem foco (Tab), Enter ou espaço mostram os detalhes numa região `aria-live`; todos os pontos estão na tabela.
- Tabelas com `<caption>`: mais próximo de cada tipo; todos os pontos (recolhida); transporte por resíduo.
- Painel de indicadores (SVG em barras + tabela): kg/mês por destino; % de desvio do aterro com a meta de 90%; CO₂ do transporte por resíduo e total.
  O plano vem de `rcLer()` (`localStorage "physis-residuos-plano"`: lista de `{tipo, qtd, un, rota}`).
- Fluxo dos resíduos (SVG tipo Sankey + tabela): geração por tipo → separação (grupo do plano) → rota → destino
  (nome do destino mais próximo do tipo certo, distância e CO₂ do transporte; "no próprio lugar" para rotas internas).
- Seção recolhível "Metodologia e normas": NBR 10004 (classificação; ensaios NBR 10005/10006), NBR 10007 (amostragem),
  Lei 12.305/2010 e Decreto 10.936/2022 (ordem de prioridade, logística reversa, PGRS), MTR/CDF/DMR no SINIR
  (Portaria MMA 280/2020), CONAMA 307/2002 (RCC), CONAMA 358/2005 e RDC ANVISA 222/2018 (saúde). Redação própria.
- Opcional: botão "Abrir o mapa com fundo da região" carrega `/vendor/maplibre-gl.js` e `/vendor/pmtiles.js` do próprio servidor e usa
  `/mapas/regiao.pmtiles` se instalado (ver `MAPAS_E_DWG.md`). Sem os arquivos, avisa e o SVG continua valendo.
- Estado: `calcLer("rc-mapa")` (`raio, fator, consumo, carga, tort, ida`); filtro, seleção e fundo em `ui.rcmCat`, `ui.rcmSel`, `ui.rcmFundo`.
