# Exportação em formato aberto (ODF, PDF/A) e documento para comentários

Regra 11 (independência): arquivos em ODF e PDF/A, sem serviço de terceiros. Este documento cobre:

1. `sistema/physis-odf.js` — ODT e ODS no navegador (sem internet, sem biblioteca externa).
2. `physis_hub/documentos.py` — o mesmo ODT/ODS no servidor, a conversão para PDF/A-2b e o
   documento publicado como página para comentários.
3. `web/documento.html` — a página de revisão (equipe e revisor externo por convite).
4. `ferramentas/conferir-odf.html` — gera no navegador, confere a estrutura e baixa para abrir no LibreOffice.

Testes: `tests/test_odf.py` (pacote, XML, estilos, células tipadas, PDF/A com LibreOffice simulado, espelho do JS)
e `tests/test_documentos.py` (limpeza do HTML, versões, comentários, permissões, convites, prazo, limite por IP, LGPD).

## 1. ODT e ODS

### Estrutura (igual no JS e no Python)

| Arquivo do pacote | O que tem |
|---|---|
| `mimetype` | primeiro arquivo, **sem compressão e sem campo extra** (bytes 30.. do arquivo = `mimetype` + tipo) |
| `content.xml` | corpo: `text:h` com `text:outline-level`, `text:p`, `text:list` (marcadores `Lista_20_Physis` e numerada `Lista_20_Numerada`), `table:table` com `table:table-header-rows`, `draw:frame`/`draw:image` com `svg:title` (texto alternativo) |
| `styles.xml` | fontes (Fraunces nos títulos, Inter no texto), estilos `Title`, `Heading_20_1..3` (verde `#33512F`), `Text_20_body`, `Tabela_20_cabecalho`, página A4; cabeçalho com a árvore (`Pictures/logo-physis.png`) e o nome do sistema; **marca d'água** `MarcaDaguaPhysis` ("PHYSIS" a 45°, verde-claro sólido `#DCEBD8`, atrás do texto, presa ao cabeçalho: repete em toda página); rodapé "Documento gerado pelo Sistema Physis · Physis Engineering · Gerado em …" e "Página X de Y" |
| `meta.xml` | `dc:title`, `meta:initial-creator`/`dc:creator` = Physis Engineering, `meta:generator` = Sistema Physis/physis-odf 1.0, datas, idioma |
| `Pictures/*.png` (e `*.svg`) | logo e imagens; guardados sem compressão |
| `META-INF/manifest.xml` | `manifest:version="1.3"`, a raiz `/` com o tipo e cada arquivo com o seu tipo |

ODF 1.3 (`office:version="1.3"`). ZIP: `mimetype` guardado; o resto com deflate (`CompressionStream("deflate-raw")`
no navegador; quando não existe, tudo guardado — continua válido).

ODS: uma folha por tabela (nome da legenda/título anterior, até 31 caracteres, sem `[]*?:/\'`, sem repetir); faixa no alto
(nome do sistema, título, "Gerado em … · Documento gerado pelo Sistema Physis"; `faixa:false` tira); linha de cabeçalho
`ceCab` (verde `#4B7547`, negrito branco) repetida na impressão; cabeçalho/rodapé de impressão "PHYSIS ENGINEERING" e página X de Y.
O ODS não tem marca d'água de verdade: a faixa e o cabeçalho de impressão fazem esse papel (como no Excel).

Células (`interpretar` no JS = `interpretar_celula` no Python):

| Texto | Vira |
|---|---|
| `1.234,56`, `42`, `−3,5`, `0,5` | `float` (`office:value="1234.56"`), mostra o texto original |
| `R$ 1.050,00` | `currency` BRL |
| `12,5%` | `percentage` 0.125 |
| `15/11/2026`, `2026-11-15` | `date` (data inválida fica texto) |
| `01234-567`, `0800`, `1.5`, `12 kWh` | texto (CEP/código com zero à esquerda; `1.5` é ambíguo em pt-BR) |

Diferença consciente em relação ao `PhysisExportar.numero` do Excel: lá `1.5` vira 15; aqui fica texto.

### Uso no navegador

```js
PhysisODF.odt(document.getElementById("tela"), { titulo: "Propostas" }).then(u8 => PhysisODF.baixar("x.odt", u8, PhysisODF.MIME.odt));
PhysisODF.odt({ titulo: "Relatório", blocos: [{ h: 1, t: "Resumo" }, { t: "texto" }, { t: "item", lista: "ol" },
  { tabela: { cab: ["A", "B"], linhas: [["1", "2"]] } }] }, { logo: false, idioma: "en-GB" });
PhysisODF.ods(document.getElementById("tela"), { titulo: "Consumo" });           // as tabelas visíveis da tela
PhysisODF.ods([{ nome: "Dados", cab: ["Mês", "kWh"], linhas: [["Jan", "1.234,5"]] }], { titulo: "Consumo" });
```

Da tela: só o visível (sem `hidden`, `aria-hidden`, `.so-leitor`, `.px-exportar`); campos saem como "rótulo: valor";
`h1..h6` viram nível `n-1` (o h1 da tela é o título do documento); SVG, `canvas` e `img` viram PNG (SVG desenhado num
canvas com os estilos calculados; `svgEmbutido:true` guarda também o SVG, com o PNG de reserva).

### Uso no servidor

```python
from physis_hub import documentos
dados = documentos.odt("Relatório ESG", blocos, sistema="Sistema Physis")       # bytes .odt
dados = documentos.ods("Consumo 2026", [{"nome": "Água", "cab": [...], "linhas": [...]}])
```
Valores Python `int/float/date/bool` entram já tipados.

### Barra única: Documento, PDF e Planilha (decisão de 15/11/2026)

O formato oficial da Physis é o do LibreOffice (ODF). Os nomes "Word" e "Excel" eram só para facilitar; a barra passou a ter
**uma linha** com **Documento**, **PDF** e **Planilha** (sem a segunda linha "Formatos abertos"):

| Botão | Com `physis-odf.js` acoplado | Sem ele (página só com o exportador) |
|---|---|---|
| Documento | `.odt` | `.docx` |
| PDF | PDF/A pelo servidor (`pdfa: true`); sem servidor, o PDF do navegador com aviso | PDF do navegador |
| Planilha | `.ods` (uma folha por tabela; tela sem tabela vira uma folha de uma coluna) | `.xlsx` |

Como funciona: o exportador desenha os três botões; o `acoplar` põe `barra.pxFormato(f, botão, dizer)`, que gera o formato
aberto e devolve `true` (ou `false` para cair no padrão). A dica de cada botão diz "abre no LibreOffice e no Word/Excel".
A linha própria do `acoplar` ficou só para "Compartilhar para comentários" (escondida quando `compartilhar` é falso).
As funções `PhysisExportar.docx/xlsx/planilha/csvParaXlsx` continuam disponíveis para quem precisar.

### Ganchos (como acoplar em cada tela)

`physis-odf.js` precisa estar na página (como o exportador). Para sincronizar como o exportador, acrescente-o ao
`ferramentas/sincronizar.py` (bloco que começa em `/* physis-odf.js v` e termina em `})(typeof window !== "undefined" ? window : this);`).
Enquanto isso, inclua o arquivo com `<script src=...>` onde houver servidor, ou cole o conteúdo num `<script>`.

**painel.html** — na linha que cria a barra (`var b=PhysisExportar.barra({...}); ... r.parentNode.insertBefore(b, r.nextSibling);`), logo depois de `insertBefore`:

```js
if (window.PhysisODF) PhysisODF.acoplar(b, {
  raiz: function () { return document.getElementById("tela"); },
  titulo: function () { return document.title || "Hub Physis"; },
  pdfa: true,                                                     // só funciona com o servidor e o LibreOffice; sem eles, explica
  compartilhar: function () { return !!(window.ui && ui.papel && /^(operador|administrador)$/.test(ui.papel)); },   // só equipe
  origem: function () { return location.pathname + location.hash; }
});
```
(ajuste `ui.papel` ao lugar onde o painel guarda o papel vindo de `/api/instancia`; o servidor recusa cliente de qualquer forma).
A linha nova fica dentro da própria barra (`.px-exportar`), então o `mostraBaixar()` que esconde a barra esconde os botões juntos.

**gestao-interna-physis.html** — onde a Gestão chama `PhysisExportar.barra({...})` (com `encaminhar`), guarde a barra numa
variável e chame `PhysisODF.acoplar(barra, { raiz: ..., titulo: ..., pdfa: true, compartilhar: true })` com as mesmas funções `raiz` e `titulo`.
A barra da Gestão se redesenha ao abrir "Encaminhar"; o `acoplar` repõe a linha sozinho (MutationObserver).

O botão "Compartilhar para comentários" publica a tela (controles viram texto, gráficos viram PNG), mostra o link e "Copiar link".
Convites para revisores de fora são criados na própria página do documento (painel "Revisores externos e documento").

## 2. PDF/A

Hoje o PDF sai de `PhysisExportar.pdf` (PDF 1.4 montado à mão, fontes padrão Type1 **não embutidas**, transparência na marca
d'água, sem XMP) ou de `window.print`. Nada disso é PDF/A. O que o PDF/A-2b exige e por que não dá para fazer só com a biblioteca padrão:

| Exigência PDF/A-2b | Situação |
|---|---|
| Todas as fontes embutidas (subconjunto), com `ToUnicode` | precisa ler TTF/OTF e gerar subconjunto — sem biblioteca, inviável com qualidade |
| Metadados XMP (`pdfaid:part=2`, `pdfaid:conformance=B`) iguais ao Info | fácil |
| `OutputIntent` com perfil ICC (sRGB) embutido | precisa do arquivo ICC (aberto, ~3 KB) |
| Sem criptografia, sem JavaScript, sem referência externa | já atendido |
| Transparência permitida (PDF/A-2), com grupo de transparência coerente | marca d'água ODT foi feita em cor sólida para evitar o problema |

**Caminho escolhido: LibreOffice sem tela no servidor** (software aberto, roda no servidor da Physis ou do cliente):

    soffice --headless --norestore -env:UserInstallation=file:///tmp/perfil-physis \
      --convert-to 'pdf:writer_pdf_Export:{"SelectPdfVersion":{"type":"long","value":"2"},"UseTaggedPDF":{"type":"boolean","value":"true"}}' \
      --outdir /tmp/saida documento.odt

(planilha: `calc_pdf_Export`). `documentos.converter_pdfa(odt_bytes)` faz exatamente isso (perfil próprio em pasta temporária,
tempo limite de 120 s). Sem o programa responde `codigo: 501` e a tela orienta: "baixe o ODT e exporte em PDF/A pelo LibreOffice".
O programa é procurado em `PHYSIS_SOFFICE`, depois `soffice`/`libreoffice` no PATH.

Instalação no servidor (Debian/Ubuntu): `apt install --no-install-recommends libreoffice-writer-nogui libreoffice-calc-nogui fonts-dejavu`
e as fontes da plataforma em TTF em `/usr/local/share/fonts/physis/` (Fraunces e Inter, licença OFL) + `fc-cache -f`; sem elas o
LibreOffice troca por outra fonte, e o PDF/A embute a substituta (continua válido, só muda a aparência).
Conferir a conformidade com o **veraPDF** (aberto): `verapdf --flavour 2b saida.pdf`. Ainda não verificado nesta máquina (sem LibreOffice instalado).

## 3. Documento como página para comentários

### Como funciona

- A equipe publica (botão "Compartilhar para comentários" ou `POST /api/documentos`). O servidor limpa o HTML
  (`sanitizar_html`): lista fechada de etiquetas e atributos; saem `script`, `style`, `iframe`, `object`, `embed`, `svg`, `math`,
  formulários, `on*`, `style=`, `class`, `id`, links que não sejam `#âncora` (viram texto), imagens que não sejam `data:` PNG/JPEG/GIF/WebP
  com conteúdo conferido; limite de 2 MB por imagem e 8 MB no total, 12 MB de HTML. `h1` vira `h2` (a página tem um único `h1`, o título).
  Cada bloco ganha `data-paragrafo="pN"` (âncora dos comentários). O que foi tirado aparece para a equipe como aviso.
- Link: `/documento/<id>` com id de 144 bits (`secrets.token_urlsafe(18)`). O link sozinho não abre nada: precisa de sessão da
  equipe ou de convite.
- Versões: `POST .../versoes`; HTML igual não cria versão. Comentários guardam a versão e o parágrafo.
- Comentários: por parágrafo ou "geral"; respostas numa conversa de um nível; resolver/reabrir (equipe); editar/apagar o próprio
  (a direção apaga qualquer; apagar tira o texto e deixa a conversa); sugestão de texto (parágrafo, título, item...) que a equipe
  aceita (gera nova versão com o trecho trocado e resolve) ou recusa.
- Revisor externo: convite com nome, e-mail opcional (só a equipe vê), prazo de 1 h a 30 dias, "só ler" ou "comentar". O código
  vai **depois do `#`** (`/documento/<id>#convite=<código>`): não chega ao servidor na abertura, não fica em registro nem em Referer;
  a página o guarda só na aba (`sessionStorage`), tira da barra de endereço e o manda no cabeçalho `X-Physis-Convite`. No banco fica
  só o resumo SHA-256. Convite vence, pode ser revogado, e cai quando o documento é arquivado. Revisor externo não resolve, não
  convida, não publica versão. Pedidos com convite não precisam de CSRF: o cabeçalho próprio não pode ser mandado por outro site
  sem CORS (que o servidor não abre).
- Limites por IP (em `Documentos`, além dos do servidor): `PHYSIS_LIMITE_CONVITE` (padrão `240/600`) para qualquer pedido com
  convite e `PHYSIS_LIMITE_CONVITE_ERRO` (padrão `20/600`) para convites errados/vencidos; estourou → 429 com `espera`.
- LGPD: a página mostra o que é guardado (aviso diferente para equipe e revisor). `Documentos.retencao()` troca nome e e-mail do
  revisor externo por "Revisor externo" (convite e comentários) `PHYSIS_DOC_RETENCAO_DIAS` (padrão 180) dias depois do fim do convite;
  rodar junto da retenção diária do servidor. A direção apaga o documento inteiro (`POST .../apagar`). Publicar, nova versão,
  convite, revogar e apagar entram na cadeia de registros (`hub.registrar("documento", ...)`), só com os 8 primeiros caracteres do id.
- Página: um `h1`, link "Pular para o documento", foco visível, botões de 44 px (36 px os pequenos), tabelas em região rolável
  com nome, botões "Comentar" com o trecho no nome acessível (fora dos títulos), status em `role=status`, faixa verde e cabeçalho
  Physis, Fraunces/Lexend-Inter vindas de `/documento/fontes.css` (tiradas do `painel.html`, nada da internet), português e inglês
  (botão no cabeçalho ou `?lang=en`), sem rolagem lateral a 320 px, sem tema escuro, impressão sem o painel.

### Tabelas (SQLite, no mesmo banco do hub; criadas por `Documentos(hub)`)

`doc(id, titulo, origem, criado_por, criado_em, atualizado_em, versao_atual, arquivado)` ·
`doc_versao(doc_id, versao, html, resumo, paragrafos, avisos, nota, criado_por, criado_em)` ·
`doc_comentario(id, doc_id, versao, paragrafo, pai, autor, autor_tipo, autor_ref, texto, sugestao, sugestao_estado, estado, criado_em, editado_em, resolvido_por, resolvido_em, apagado)` ·
`doc_convite(id, doc_id, resumo, nome, email, pode_comentar, criado_por, criado_em, expira, revogado, usado, acessos)`.

### API

| Rota | Quem | O quê |
|---|---|---|
| `GET /api/documentos` | equipe | lista (com conversas abertas) |
| `POST /api/documentos` `{titulo, html, origem?, nota?}` | equipe | publica; devolve `id`, `link`, `avisos` |
| `GET /api/documentos/<id>[?versao=N]` | equipe ou convite | documento, versões, comentários, `eu` (o que pode) |
| `POST .../versoes` `{html, nota?}` | equipe | nova versão |
| `GET/POST .../comentarios` `{paragrafo|"geral", texto, sugestao?, versao?}` ou `{pai, texto}` | quem pode comentar | lista / comenta / responde |
| `POST .../comentarios/<n>/editar` `{texto}` · `/apagar` | autor (apagar: também direção) | |
| `POST .../comentarios/<n>/resolver` `{resolvido}` · `/sugestao` `{aceitar}` | equipe | |
| `GET/POST .../convites` `{nome, email?, dias, pode_comentar}` · `POST .../convites/<n>/revogar` | equipe | o código volta uma vez só |
| `POST .../arquivar` `{arquivado}` · `POST .../apagar` | equipe · direção | |
| `POST /api/documentos/pdfa` (corpo = ODT) | qualquer conta | PDF/A-2b ou 501 |

### Ligação no `servidor.py` (exata; o resto está no módulo)

> **Aplicado em 15/11/2026** (`servidor.py`: `_rotas_novas_get` e `_rotas_novas_post_grandes`). Diferenças do trecho abaixo:
> `/documento` sem id também abre a página; o corpo de cada POST passa por `seg.ESQUEMAS` (`doc_*`, estrito) antes do módulo;
> sem sessão nem convite, 401 sem ler o corpo grande; `/api/documentos/pdfa` aceita ODS (`Content-Type` de planilha) e usa o
> serviço de documentos (`documentos_cliente`) quando não há `soffice`; a retenção roda uma vez por dia (`rodar_diario`).
> Testes: `tests/test_rotas_novas.py` (classe `Documento`).

Import, junto dos outros:

```python
from . import documentos as documentos_mod
```

Em `criar_manipulador`, depois de `alertas = alertas_mod.AlertasClima(...)`:

```python
    docs = documentos_mod.Documentos(hub)          # documento como página para comentários (docs/EXPORTACAO.md)
```

Métodos novos no `Manipulador` (perto de `_exigir`):

```python
        def _conta_doc(self) -> dict | None:
            """Conta da sessão para as rotas de documento; sem o aceite dos termos atuais (modo estrito), não vale (o convite vale)."""
            q = self._quem()
            if q and seg.consentimento_estrito() and seg.consentimento_pendente(q):
                return None
            return q

        def _doc_resposta(self, r) -> None:
            codigo, obj = r
            if codigo == 429:
                return self._recusar(429, obj, {"Retry-After": str(obj.get("espera", 60))})
            return self._json(codigo, obj)
```

`do_GET`, logo depois do bloco de `/api/instancia` (antes de qualquer `_barrado`, porque o revisor externo não tem sessão):

```python
            # ── Documento para comentários: a página não tem dado; a API decide (equipe com sessão ou convite) ──
            if u.path == "/documento/fontes.css":
                css = documentos_mod.fontes_css().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/css; charset=utf-8")
                self.send_header("Content-Length", str(len(css)))
                self.send_header("Cache-Control", "max-age=86400")
                self.end_headers()
                self.wfile.write(css)
                return
            if re.fullmatch(r"/documento/[A-Za-z0-9_-]{16,64}/?", u.path):
                return self._arquivo(WEB / "documento.html", "text/html; charset=utf-8")
            if u.path.startswith("/api/documentos"):
                r = docs.rota("GET", u.path, self._conta_doc(), None, convite=self.headers.get("X-Physis-Convite"),
                              ip=self._ip(), base=url_publica, consulta=q)
                if r:
                    return self._doc_resposta(r)
```

`do_POST`, logo depois de `if self._csrf_barrado(): return`:

```python
            if u.path == "/api/documentos/pdfa":
                if not self._exigir(seg.CLIENTE):
                    return
                if self._limitado("arquivo"):                 # LibreOffice é pesado: 10 por 10 min por IP
                    return
                odt = self._corpo_grande(documentos_mod.CORPO_MAX)
                if odt is None:
                    return self._recusar_corpo("documento vazio ou grande demais")
                r = documentos_mod.converter_pdfa(odt)
                if not r["ok"]:
                    return self._json(r.pop("codigo"), r)
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", 'attachment; filename="physis-documento.pdf"')
                self.send_header("Content-Length", str(len(r["pdf"])))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(r["pdf"])
                return
            if u.path.startswith("/api/documentos"):
                corpo = self._corpo_grande(documentos_mod.CORPO_MAX) if int(self.headers.get("Content-Length") or 0) > 0 else b""
                if corpo is None:
                    return self._recusar_corpo("documento grande demais (máx. 16 MB)")
                r = docs.rota("POST", u.path, self._conta_doc(), corpo, convite=self.headers.get("X-Physis-Convite"),
                              ip=self._ip(), base=url_publica)
                if r:
                    return self._doc_resposta(r)
```

Retenção: onde o servidor roda `seg.rodar_retencao`, rodar também `docs.retencao()` uma vez por dia (ou numa thread igual).

Observação: `seguranca.py` não precisa mudar. Se quiserem os limites do convite junto dos outros, acrescentar
`"convite"` em `LIMITES_PADRAO` e trocar o `Limitador` interno de `Documentos` pelo de lá.

## O que falta / não verificado

- Abrir os arquivos no LibreOffice e no Word (aparência da marca d'água, logo no cabeçalho, quebra de página da tabela). A
  estrutura foi conferida por Python (`zipfile` + XML) e no navegador (`ferramentas/conferir-odf.html`, 31 conferências OK no Chromium).
- PDF/A: sem LibreOffice nesta máquina; o comando e a rota estão prontos e testados com o programa simulado; falta o veraPDF num servidor real.
- ~~Teste de ponta a ponta pela rota HTTP do `servidor.py`~~: feito em 15/11/2026 (`tests/test_rotas_novas.py`).
- `physis-odf.js` ainda não entra no `sincronizar.py` nem nas telas (ganchos acima).
- Aviso por e-mail ao revisor (o link é copiado e enviado pela equipe); dá para usar `correio` depois.
