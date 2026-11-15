# SbN — lógica de seleção de plantas e consórcios

Arquivos:

- `sistema/physis-plantas.json` — base (dados). Números `n` 1–234 mantidos; 122 espécies novas (n 235–356).
- `sistema/physis-sbn.js` — lógica pura + fragmentos de tela. Expõe `window.SBN_LOGICA`. Sem DOM ao carregar, sem internet.
- `ferramentas/conferir-sbn.html` — conferência no navegador (10 cenários + combinações, filtros, GIS, UCs, terreno, mapa).
  Rodar: `python -m http.server 8765` na raiz do repositório e abrir `http://127.0.0.1:8765/ferramentas/conferir-sbn.html`
  (o título da aba vira `SBN OK n` ou `SBN FALHOU n`). Sem servidor, escolha o JSON no campo da página.
- `physis-hub/tests/test_sbn.py` — confere a base (esquema, reciprocidade, nativas por bioma) e o módulo (sem URLs externas, UTF-8, LF).

## Campos novos da base (compatíveis com os antigos)

| Campo | O que é |
|---|---|
| `espacamento` | `{entre_plantas_m, entre_linhas_m, forma: "cova (muda)" \| "linha (semeadura direta)", fonte, confianca}` — plantio solteiro, referências Embrapa/literatura |
| `antagonistas` | números `n`, recíprocos, com `antagonistas_fonte` |
| `nativa_de` / `cultivavel_em` | biomas onde é nativa / onde o cultivo é viável (`nativa_de ⊆ cultivavel_em`); `biomas` = união (compatibilidade); `nativa_br = nativa_de não vazio` |
| `clima` | `{tmin_tolerada_c, geada: tolera\|sensivel, chuva_mm_ano [min,max] sem irrigar, meses_secos_max, temp_media_c [min,max], perfil, irrigacao, fonte, confianca}` |
| `altitude_m` + `altitude_fonte` | faixa usual no Brasil (da espécie ou do perfil climático; o clima filtra melhor) |
| `solo.textura` | `argiloso \| médio \| arenoso` (como o GIS); `solo.pedregoso` separado |
| `grupo_restauracao` | `preenchimento \| diversidade` (APP 50/50) |
| `madeira` | espécie de madeira, lenha ou estaca (fora de `funcoes`, que segue as 14 das planilhas) |
| `item_viveiro` / `especie` | bandejas 199–203 (`item_viveiro: true`, fora das listas de espécies) |
| `item_grupo` + `repete` | Citros (13) agrupa 114, 121, 129 (fica só para as combinações antigas) |
| `variedade_de` | outro grupo de cultivares da mesma espécie (Brassica 98/226 → 82; uva 206 → 116; 142 → 83; 151 → 94; 160 → 57; 100 → 84) |
| `conferir` | `true` quando `a_conferir` tem itens para especialista (Flora e Funga do Brasil, Hórus) |
| `obs` | observação curta (espécies novas) |

Companheiras: recíprocas, sem invasoras, sem bandejas, sem antagonistas, máximo 12. Contagem atual de nativas por bioma:
Mata Atlântica 131, Cerrado 95, Amazônia 74, Pampa 50, Caatinga 47, Pantanal 32.

## API (`window.SBN_LOGICA`)

- `carregar(baseJson)` — guarda a base (todas as funções aceitam `plantas` explícito também).
- `filtrar(plantas, criterios)` / `avaliar(planta, criterios) → [motivos]`. Critérios: `bioma` ("" ou "todas" = sem filtro, as plantas sem bioma aparecem),
  `uf`, `regiao` (Norte, Nordeste, Centro-Oeste, Sudeste, Sul; usados quando não há bioma), `somenteNativas`, `zonaAmortecimento`,
  `incluirInvasoras`, `incluirViveiro`, `altitude_m`, `irrigacao`, `luz`, `solo {textura, umido, seco, acido, acido_estrito}`,
  `clima {tmin_c, geada, chuva_mm_ano, meses_secos, temp_media_c}`, `estrato`, `ciclo`, `funcoes[]`, `madeira`, `app`, `txt`.
- `criteriosDoLugar({zonas, solo, lugar, biomaAprox})` — de `ui.gisX.zonas` (bioma IBGE, Köppen, clima IBGE, vegetação original) e `ui.gisX.solo`.
  Geada: média do mês mais frio < 14 °C; mínima absoluta ≈ média do mês mais frio − 15 °C (estimativa, dita na nota).
- `montarConsorcio({objetivo, area_m2, bioma, uf, solo, clima, luz, altitude_m, irrigacao, nativas_pct, densidade, vegetacao})` →
  `{itens[{n, nome, estrato, ciclo, mudas, unidade, espacamento, cobertura_pct, grupo, motivo}], estratos, sucessao, explicacao[], violacoes[], total_mudas, nativas_pct_*}`.
  Objetivos: `agrofloresta` (5 estratos com cobertura alvo 20/40/50/60/70%, −30% no clima seco; as 4 fases da sucessão; uma adubadeira;
  companheiras somam, antagonistas e invasoras saem, gêneros repetidos perdem pontos), `horta` (65% da área em canteiro; trepadeira,
  bordadura, aromática; folha/raiz/fruto/grão), `pomar`, `restauracao_app` (só nativas do bioma, 50% preenchimento × 50% diversidade,
  grade 3 × 2 m, nenhuma espécie > 20%, aviso em vegetação campestre), `jardim_chuva` (centro alagável, borda alaga-e-seca).
- `verificar(resultado, plantas, criterios)` — regras: invasora, antagonistas, filtros, cobertura por estrato, sucessão, nativas, proporção da APP.
- `mudas(planta, area_m2, densidade?)` → número; `mudasInfo(...)` → detalhe.
- `corrigirCombinacao(texto, plantas)` → `{itens [[n, qtd]], modulos, nao_achados, avisos}`; `acharPlanta(nome, plantas)` (sem "começa com").
- `lerTerreno(localStorage "physis.terreno.v1")` → `[{id, nome, tipo, area_m2, app, area_app_m2, objetivo, forma, x, y, w, d, rot}]`
  (horta/pomar, gramado/jardim, mata, vala/jardim de infiltração; APP de declividade > 100% calculada dos pontos cotados). `contextoTerreno(...)`.
- `ucsDoLugar({uf, regiao, bioma, lat, lon})`, `apropriadaZA(planta, bioma)`, `REGRAS_UC`.
- Mapa: `estadoMapa(terrenoJson, salvoJson)`, `gradePlantio(area, resultado)`, `telaSbnMapa(ctx)`, `ligarMapa(el, ctx, aoMudar)`, `abrirMapaGis(container, ctx)`.
- Conferência: `itensConferencia({plano, consorcios, lugar, plantas})`, `conferenciaCsv(itens, estado)`, `telaSbnConferencia(ctx)`, `ligarConferencia(el, ctx, aoMudar)`.
- Telas (HTML, um `h2` por seção, tabelas com `caption`): `telaSbnConsorcio({resultado} | {opcoes})`, `telaSbnAreas({terreno})`, `telaSbnConferencia(ctx)`,
  `telaSbnUcs({uf, bioma, plantas})`, `telaSbnMapa({estado, consorcios})`. Usam `esc`/`n2` da plataforma se existirem na hora da chamada.

## Ligação no painel (physis-hub/web/painel.html)

1. Embutir `sistema/physis-sbn.js` como `<script>` (mesmo caminho das outras bases embutidas) e, logo depois de `const SBN = …`,
   chamar `SBN_LOGICA.carregar(SBN)`. Rodar `ferramentas/embutir_bases.py` para a cópia nova do JSON entrar no painel.
2. `sbnCombinar(texto)` passa a ser `return SBN_LOGICA.corrigirCombinacao(texto, SBN.plantas).itens;`. No clique `data-sbn-comb`,
   quando `itens` vier vazio e houver `modulos`, gravar a observação como hoje.
3. Seletor: trocar o `SBN.plantas.filter(...)` (o teste `!Array.isArray(p.biomas)` deixava passar planta sem bioma) por
   `SBN_LOGICA.filtrar(SBN.plantas, { bioma: f.bioma, uf, regiao: f.regiao, somenteNativas: f.nativa, zonaAmortecimento: f.za,
   incluirInvasoras: !f.semInv, luz: f.luz, altitude_m, clima, solo: { textura: f.textura, umido: f.solo === "umido", seco: f.solo === "seco",
   acido: f.solo === "acido", acido_estrito: f.solo === "acido" }, estrato: f.estrato, ciclo: f.ciclo, funcoes: f.fun, app: f.app, madeira: f.madeira, txt: f.txt })`.
   Acrescentar ao select de bioma a opção `todas`; novos selects: região, UF, textura, "zona de amortecimento", "madeira", geada/chuva/meses secos.
4. Valores do lugar: `const c = SBN_LOGICA.criteriosDoLugar({ zonas: (ui.gisX||{}).zonas, solo: (ui.gisX||{}).solo, lugar: { uf, altitude_m }, biomaAprox: biomaDoLugar() })`;
   preencher `f.bioma` com `c.bioma` (IBGE antes das caixas) e usar `c.clima`, `c.solo`, `c.altitude_m`, `c.vegetacao` nos filtros e no consórcio; mostrar `c.notas`.
5. Nova sub-aba "Consórcio": formulário (objetivo, área, % de nativas) e `SBN_LOGICA.telaSbnConsorcio({ opcoes: { ...c, objetivo, area_m2, nativas_pct } })`.
   O botão `data-sbn-cons-plano` leva os `itens` ao plano com `sbnAcrescentar(n, mudas, espaco)`.
6. "Espaços e agrofloresta": antes da lista, `SBN_LOGICA.telaSbnAreas({ terreno: localStorage.getItem("physis.terreno.v1") })`;
   o botão `data-sbn-area` (com `data-sbn-obj` e `data-sbn-m2`) monta o consórcio da área.
7. Mapa: um `<div data-sbn-mapa-host>` e, depois de `desenhar`, `SBN_LOGICA.ligarMapa(host, ctx, (estado, acao, id) => { localStorage.setItem("physis.sbn.mapa",
   JSON.stringify({ areas: estado.areas, sel: estado.sel, grade: estado.grade })); if (acao === "consorcio") { const a = estado.areas.find(x => x.id === id);
   ctx.consorcios[id] = SBN_LOGICA.montarConsorcio({ ...c, objetivo: a.objetivo, area_m2: SBN_LOGICA.areaDaArea(a) }); SBN_LOGICA.ligarMapa(host, ctx); } })`,
   com `ctx = { estado: SBN_LOGICA.estadoMapa(localStorage.getItem("physis.terreno.v1"), localStorage.getItem("physis.sbn.mapa")), consorcios: {} }`.
   Se `window.maplibregl` existir: `SBN_LOGICA.abrirMapaGis(host.querySelector("[data-sbn-m-gis]"), ctx)` (sem fundo externo).
8. UCs: `SBN_LOGICA.telaSbnUcs({ uf, bioma: f.bioma, lat, lon, plantas: SBN.plantas })` na sub-aba do seletor.
9. Conferência (item de planejamento): acrescentar `["conferencia","Conferência"]` a `SBN_SUB` e, nessa sub-aba,
   `corpo = SBN_LOGICA.telaSbnConferencia({ plano: s.plano, consorcios: ui.sbnConsorcios || [], lugar: c, plantas: SBN.plantas, estado: s.conferencia || {} })`;
   depois de `desenhar`, `SBN_LOGICA.ligarConferencia(el, { plano: s.plano, consorcios: ui.sbnConsorcios || [], lugar: c, plantas: SBN.plantas,
   estado: s.conferencia || {}, gravar: est => { const t = sbnLer(); t.conferencia = est; sbnGravar(t); } })` (usar `sbnGravar` respeita o modo `ui.vazia`;
   sem `gravar`, o módulo grava direto em `localStorage["physis-sbn"].conferencia`). Itens: espécies do plano com `a_conferir`, invasora,
   espaçamento de confiança baixa, clima/altitude de perfil; avisos e erros dos consórcios; dados do lugar que faltam (bioma, textura, chuva,
   meses secos, frio, altitude). Cada item: situação (a conferir / conferido / ajustado), responsável, data, observação; botão exporta CSV (`;`, UTF-8).
   `sbnLer` já preserva a chave nova porque faz `Object.assign` sobre o objeto gravado.

## Limites conhecidos

- Dados ecológicos e de clima vêm de conhecimento geral e de perfis por grupo (`clima.confianca` baixa/média); itens com `conferir: true` pedem especialista.
- A base de UCs não tem coordenadas: a lista é por UF/região e a distância (raio de 3 km) só é calculada se `lat/lon` forem acrescentados.
- O Planejador grava metros locais: x leste, y norte a partir de `lat0/lon0` (**confirmado pela direção em 15/11/2026**).
- A declividade usa grade de 40 células (o Planejador usa 110): a área de APP é aproximada.
- Fotos (campo `imagem`) ficam para a fase 2.
- Os dados foram gerados uma vez por script de migração a partir da base v88 (fora do repositório); edições futuras são diretas no JSON.
