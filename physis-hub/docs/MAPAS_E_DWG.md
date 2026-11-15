# Mapa de fundo da região e conversão de DWG (servidor)

Os dois são opcionais. Sem eles o Planejador funciona: o mapa mostra só o terreno, e o DWG pede DXF.

## 1. Mapa de fundo da região (OpenStreetMap, sem internet no dia a dia)

O Planejador procura `/mapas/regiao.pmtiles`. O servidor entrega por partes (Range) a partir da
pasta `mapas/` ao lado de `physis_hub/` (ou da pasta em `PHYSIS_MAPAS`).

1. Instale o programa `pmtiles` (código aberto, Protomaps): https://github.com/protomaps/go-pmtiles/releases
2. Recorte a região do cliente do mapa mundial do Protomaps. Basta fazer isso uma vez por cliente
   e repetir só para atualizar. O `--bbox` é: oeste, sul, leste, norte.

       pmtiles extract https://build.protomaps.com/<AAAAMMDD>.pmtiles mapas/regiao.pmtiles --bbox=-43.30,-22.60,-43.05,-22.40 --maxzoom=15

3. Pronto. No Planejador, em Terreno, use "Abrir o mapa": rios, ruas e quadras aparecem sob o terreno.

Dados © colaboradores do OpenStreetMap (licença ODbL). A atribuição deve aparecer no rodapé do mapa
quando o fundo estiver instalado.

## 2. Conversão de DWG para DXF (LibreDWG)

O Planejador envia o DWG para `POST /api/converter/dwg`. O servidor usa o `dwg2dxf` do LibreDWG
(código aberto, GPL). Ele roda como programa separado, e por isso a licença do sistema não muda.

- Debian/Ubuntu: `sudo apt install libredwg-tools`
- Ou indique o caminho em `PHYSIS_DWG2DXF=/caminho/dwg2dxf`.

Sem o programa, a resposta é 501, com o pedido de exportar em DXF. A leitura de DWG muito novo
pode falhar (o LibreDWG ainda não lê tudo). Nesse caso a resposta é 422, também pedindo DXF.
