# vendor/ — bibliotecas de terceiros guardadas dentro do sistema

O sistema roda sem internet. O que antes vinha de CDN fica aqui e é embutido nos programas por
`ferramentas/embutir_bibliotecas.py`. Não edite estes arquivos à mão.

| Arquivo | Origem | Licença | Conferência |
|---|---|---|---|
| jszip.min.js | JSZip 3.10.1 (cdnjs) | MIT ou GPLv3 (aviso no cabeçalho do arquivo) | SHA-512 igual ao publicado pelo cdnjs (14/11/2026) |
| pdf.min.js | pdf.js 3.11.174, Mozilla (cdnjs) | Apache 2.0 (aviso no cabeçalho) | SHA-512 igual ao publicado pelo cdnjs (14/11/2026) |
| pdf.worker.min.js | pdf.js 3.11.174, Mozilla (cdnjs) | Apache 2.0 (aviso no cabeçalho) | SHA-512 igual ao publicado pelo cdnjs (14/11/2026) |
| fontes/lexend-latin-{300,400,500,600}-normal.woff2 | @fontsource/lexend 5.2.11 | SIL OFL 1.1 (fontes/LICENSE-Lexend-OFL.txt) | — |
| fontes/atkinson-hyperlegible-latin-{400,700}-normal.woff2 | @fontsource/atkinson-hyperlegible 5.2.8 | SIL OFL 1.1 (fontes/LICENSE-Atkinson-OFL.txt) | — |

Para atualizar uma versão: baixe a nova, confira o SHA-512 com o publicado pela fonte, troque o
arquivo aqui, atualize esta tabela e rode `python ferramentas/embutir_bibliotecas.py`.
