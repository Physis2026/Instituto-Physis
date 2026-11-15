# Painel municipal de resiliência

Para Defesa Civil e prefeituras. Um município por hub (código IBGE, nome e UF). Página própria em `/municipio`
(`web/municipio.html`), lógica em `physis_hub/municipio.py`, testes em `tests/test_municipio.py`.

## O que mostra

| Parte | De onde vem |
|---|---|
| Chuva medida por estação (1 h, 24 h, 72 h) | CEMADEN, todas as estações do município (o serviço é por UF; o mesmo do `clima.py`). Só vale estação com dado nas últimas 3 h; `-` = 0 mm |
| Nível de deslizamento | Limiares em `config.limiares`. Padrão = os do `alertas_clima.py`: atenção 40 mm/24 h ou 60 mm/72 h; alerta 80 mm/24 h ou 120 mm/72 h. A Defesa Civil troca pelos seus na tela do operador |
| Avisos do INMET | Avisos ativos que citam o código IBGE (`PHYSIS_MUN_INMET_AVISOS_URL`, padrão `https://apiprevmet3.inmet.gov.br/avisos/ativos`). **[VERIFICAR]** o formato na primeira instalação: o leitor aceita lista ou `{hoje, futuro}`, com `geocodes` ou `municipios`; severidade "Perigo Potencial" = atenção, "Perigo"/"Grande Perigo" = alerta |
| Previsão combinada e chance aprendida | `clima.estado()["combinada"]` e `aprendizado.previsao_chuva()`. São do lugar do hub: a tela avisa quando o lugar do hub não é o município |
| Rios | `gis.GisExtra.rio` (GloFAS) nos pontos de rio configurados; atenção acima do p90, alerta acima do p99 do histórico 2000–2024 |
| Mapa de risco | Bairros (polígono ou ponto) com classe R1 a R4 (setorização do SGB/CPRM). Mapa SVG desenhado na página, sem internet; tabela equivalente para leitor de tela |
| Pluviômetros Physis | Linhas V6 `TIPO:PLUV` (soma de `CHI` por janela). Hoje o hub ainda recusa `TIPO:PLUV` (ver `docs/ROBOS.md`): aparece quando o protocolo aceitar |
| Alertas por bairro | Chuva: estações do bairro e pluviômetros Physis nele; sem nenhum, a maior chuva do município (marcado). Rio: o ponto ligado ao bairro. INMET: município inteiro. Cada alerta guarda início, atualização, fim e o nível máximo |
| CSV | `alertas`, `chuva`, `bairros`; separador `;`, UTF-8 com BOM |

## Dois modos

- **Público** (`/api/municipio/publico`, sem conta): sem dado pessoal. Pluviômetro da Physis só aparece se
  marcado `publico` (pode estar em propriedade particular) e sem o número do nó. Sem configuração nem erros.
- **Operador** (`/api/municipio`, equipe): tudo + configuração, erros das consultas, edição de bairros,
  importação, limiares e "Atualizar agora". Toda mudança vai para a cadeia de registro (só metadados).

## Importar bairros

GeoJSON `FeatureCollection` (Polygon, MultiPolygon ou Point; propriedades `nome`/`name`/`bairro` e
`risco`/`classe`/`grau`/`risk` com R1–R4, 1–4, baixo/médio/alto/muito alto) ou CSV `nome;risco;lat;lon`.
Até 500 bairros, 5.000 vértices por bairro e 100.000 no total (simplifique antes no QGIS). Bairro sem classe entra
como R1 e volta na lista "revisar". A estação do CEMADEN de cada bairro é escolhida pelo nome (o serviço não
traz coordenadas).

## Rotas para o `servidor.py` (colar)

No `criar_manipulador`, depois de `alertas = ...`:

```python
from . import municipio as municipio_mod          # (no topo, com os outros imports)
municipio = municipio_mod.Municipio(hub, clima=clima, aprendizado=aprendizado)
```

No `do_GET`:

```python
if u.path in ("/municipio", "/municipio/"):
    return self._arquivo(WEB / "municipio.html", "text/html; charset=utf-8")
if u.path == "/api/municipio/publico":
    return self._json(200, municipio.estado(operador=False))
if u.path == "/api/municipio":
    if not self._exigir(seg.EQUIPE):
        return
    return self._json(200, municipio.estado(operador=True))
if u.path == "/api/municipio/exportar":
    q_ = self._quem()
    oper = bool(q_ and seg.pode(q_, seg.EQUIPE))
    tipo = q.get("tipo", ["alertas"])[0]
    if tipo not in ("alertas", "chuva", "bairros"):
        return self._json(400, {"ok": False, "erro": "tipo: alertas, chuva ou bairros"})
    corpo = municipio.exportar_csv(tipo, operador=oper).encode("utf-8")
    self.send_response(200)
    self.send_header("Content-Type", "text/csv; charset=utf-8")
    self.send_header("Content-Disposition", f'attachment; filename="municipio-{tipo}.csv"')
    self.send_header("Content-Length", str(len(corpo)))
    self.send_header("Cache-Control", "no-store")
    self.end_headers()
    self.wfile.write(corpo)
    return
```

No `do_POST`, **antes** da linha `corpo = self._corpo()` genérica (a importação passa de 64 KB):

```python
if u.path == "/api/municipio/bairros/importar":
    q_ = self._exigir(seg.EQUIPE)
    if not q_:
        return
    dados = self._corpo_grande(municipio_mod.IMPORTAR_MAX_BYTES)
    if dados is None:
        return self._recusar_corpo("arquivo vazio ou maior que 5 MB")
    try:
        lista = municipio_mod.ler_importacao(dados, self.headers.get("Content-Type") or "")
    except ValueError as exc:
        return self._json(400, {"ok": False, "erro": str(exc)})
    r = municipio.importar(lista, q_["usuario"], substituir=parse_qs(u.query).get("substituir", [""])[0] == "1")
    return self._json(200 if r["ok"] else 400, r)
```

E depois do `corpo = self._corpo()`:

```python
if u.path in ("/api/municipio/config", "/api/municipio/bairro", "/api/municipio/atualizar"):
    q_ = self._exigir(seg.EQUIPE)
    if not q_:
        return
    try:
        d = seg.carregar_json(corpo or "{}")
    except ValueError:
        return self._json(400, {"ok": False, "erro": "json invalido"})
    if u.path.endswith("/atualizar"):
        if self._limitado("publico"):          # cada clique chama CEMADEN, INMET e GloFAS
            return
        return self._json(200, municipio.consultar())
    r = municipio.definir_config(d, q_["usuario"]) if u.path.endswith("/config") else municipio.editar_bairro(d, q_["usuario"])
    return self._json(200 if r["ok"] else 400, r)
```

Laço de fundo no `main()` (como o do clima, respeitando `PHYSIS_CLIMA=0`):

```python
from . import municipio as municipio_mod
mun_fundo = municipio_mod.Municipio(hub, clima=clima, aprendizado=apr_fundo)
if os.environ.get("PHYSIS_CLIMA", "1") != "0":
    threading.Thread(target=municipio_mod.rodar, args=(mun_fundo, parar), daemon=True).start()
```

A página pega o token CSRF em `/api/instancia` e manda em `X-Physis-CSRF`.

## Tela

Um `h1` só ("Resiliência municipal"), PT/EN (botão; guarda em `physis-idioma`), tema claro/escuro (botão;
guarda em `physis-pref-tema`, como a barra de preferências), só cores da `PALETA.md`, tabelas com `caption` e
`th scope`, mapa com `title`/`desc`, sem rolagem lateral (tabelas rolam dentro da caixa). Atualiza sozinha a cada
5 min (não enquanto o operador está num campo).

## Limites conhecidos

- O formato dos avisos do INMET não foi conferido contra o serviço real ([VERIFICAR]).
- Estações do CEMADEN sem coordenadas: não aparecem no mapa; ligação ao bairro é por nome.
- Previsão é a do lugar do hub, não do centro do município.
- Pluviômetro Physis depende de o hub aceitar `TIPO:PLUV` (proposta em `docs/ROBOS.md`).
- Não envia aviso a cidadão (e-mail/WhatsApp): só mostra. Ligar ao `alertas_clima.py` é o próximo passo.
