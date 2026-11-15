/* physis-exportar.js v3 · 15/11/2026
 *
 * Baixar a tela em Word (.docx), Excel (.xlsx) e PDF, e encaminhar a colegas.
 * Sem dependência externa e sem internet: os três arquivos são montados aqui.
 * A mesma biblioteca vai embutida na Gestão Physis, no Hub Physis e nos protótipos.
 * ORIGINAL ÚNICO: mude só este arquivo e rode `python ferramentas/sincronizar.py`.
 *
 * v2: todo documento sai com a identidade Physis (regra da Physis, 14/11/2026):
 *   Word  - cabeçalho "PHYSIS ENGINEERING", marca d'água "PHYSIS" na diagonal, rodapé com página X de Y,
 *           tabelas com cabeçalho verde e bordas da paleta.
 *   PDF   - faixa verde no topo, marca d'água diagonal suave em toda página, cabeçalho de tabela verde, rodapé com linha.
 *   Excel - faixa "PHYSIS ENGINEERING" no topo, cabeçalho de tabela verde, bordas da paleta e cabeçalho e rodapé de impressão.
 *           (O Excel não tem marca d'água de verdade; a faixa e o cabeçalho de impressão fazem esse papel.)
 * Paleta: verde ação #33512F, marca #4B7547, texto #1C2B21, secundário #4A4F44, linha #C9D2C4, areia #EFE8D6.
 *
 * v3 (15/11/2026, "todo cliente baixa os próprios dados em Word e Excel editáveis, em toda tela"):
 *   - programa aberto num quadro (iframe) da mesma origem: o conteúdo visível do quadro entra no arquivo;
 *   - planilha(titulo, cab, linhas, {decimal}) e csvParaXlsx(titulo, textoCsv, {decimal}): o mesmo Excel da barra
 *     para os lugares que baixavam só CSV; número vira número e data vira data (célula editável, não texto).
 *
 * Uso:  PhysisExportar.barra({ raiz: function () { return elemento; },
 *                              titulo: function () { return "Propostas"; },
 *                              idiomaTela: function () { return document.documentElement.lang; },   // opcional
 *                              encaminhar: { pessoas: [...], enviar: function (id, nota, link) {...} } })   // ou false
 *       PhysisExportar.baixarPlanilha("leituras", "Leituras", ["data","pH"], [["14/11/2026 08:00","6,8"]])
 */
(function (g) {
  "use strict";
  var EN = /^en/i.test((g.navigator && g.navigator.language) || "pt");
  /* Nomes dos botões (decisão da Physis, 15/11/2026): o formato oficial é o do LibreOffice (ODF). "Documento", "PDF" e
     "Planilha" no lugar de Word/Excel e da segunda linha "Formatos abertos". Com o physis-odf.js na página (acoplar),
     Documento = .odt, Planilha = .ods e PDF = PDF/A pelo servidor (sem servidor, o PDF do navegador). Sem ele, .docx/.xlsx. */
  var TX_EN = { baixar: "Download this screen", word: "Document", pdf: "PDF", excel: "Spreadsheet", enc: "Forward to colleagues",
      dicaDoc: "Open format (.odt): opens in LibreOffice and Word", dicaPlan: "Open format (.ods): opens in LibreOffice and Excel", dicaPdf: "PDF to read and print",
      para: "To", nota: "Note (optional)", link: "Link to this screen", enviar: "Send notice", copiar: "Copy link and note",
      copiado: "Copied.", semCopia: "Select the text and copy it.", baixado: function (n) { return n + " saved."; },
      falha: "The download could not be started.", vazio: "There is nothing on this screen to export.",
      semServidor: "Without the Physis server the notice cannot be delivered straight to a colleague. Copy the link and the note and send them.",
      gerado: "Generated on", escolha: "Choose who", cancelado: "The download was cancelled." };
  var TX_PT = { baixar: "Baixar esta tela", word: "Documento", pdf: "PDF", excel: "Planilha", enc: "Encaminhar a colegas",
      dicaDoc: "Formato aberto (.odt): abre no LibreOffice e no Word", dicaPlan: "Formato aberto (.ods): abre no LibreOffice e no Excel", dicaPdf: "PDF para ler e imprimir",
      para: "Para", nota: "Recado (opcional)", link: "Link desta tela", enviar: "Enviar aviso", copiar: "Copiar link e recado",
      copiado: "Copiado.", semCopia: "Selecione o texto e copie.", baixado: function (n) { return n + " baixado."; },
      falha: "Não foi possível iniciar o download.", vazio: "Não há nada nesta tela para exportar.",
      semServidor: "Sem o servidor Physis, o aviso não chega direto ao colega. Copie o link e o recado e envie.",
      gerado: "Gerado em", escolha: "Escolha para quem", cancelado: "O download foi cancelado." };
  /* idioma: o do navegador; a barra usa o da tela quando ela informa (op.idiomaTela, p. ex. SCADA e Gestão, que não traduzem o DOM) */
  var TX = EN ? TX_EN : TX_PT;

  function TX_PADRAO(op) { if (op && typeof op.idiomaTela === "function") { try { var q = String(op.idiomaTela() || ""); if (q) return /^en/i.test(q) ? TX_EN : TX_PT; } catch (e) {} } return EN ? TX_EN : TX_PT; }

  /* ───────── utilidades ───────── */
  function bytes(s) { return new TextEncoder().encode(s); }
  function xml(s) { return String(s == null ? "" : s).replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
  function limpo(s) { return String(s == null ? "" : s).replace(/\s+/g, " ").trim(); }
  function agora() { return new Date().toLocaleString(EN ? "en-GB" : "pt-BR", { dateStyle: "short", timeStyle: "short" }); }
  function arquivo(titulo) {
    var b = String(titulo || "physis").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 50) || "physis";
    var d = new Date(), p = function (n) { return String(n).padStart(2, "0"); };
    return "physis-" + b + "-" + d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate());
  }

  /* ───────── cabeçalho do sistema: logo e nome, tirados da própria tela ─────────
     O documento reproduz o cabeçalho do sistema de onde saiu: a árvore da Physis e o nome do sistema
     ("Gestão Physis", "Sistema Physis", "Loja Physis"...). A imagem vem do cabeçalho da página; quando a
     imagem é a marca larga (árvore + PHYSIS), só a árvore, à esquerda, é usada. Sem imagem, sai só o texto. */
  function nomeSistema() { var t = document.querySelector(".px-faixa .px-tit"); return limpo(t && t.textContent) || "Physis"; }
  var LOGO = null;
  function b64bytes(d) { var s = atob(d.split(",")[1]), u = new Uint8Array(s.length); for (var i = 0; i < s.length; i++) u[i] = s.charCodeAt(i); return u; }
  function logo() {
    if (LOGO !== null) return LOGO;
    LOGO = false;
    try {
      var img = document.querySelector(".px-faixa .px-id img, .px-faixa img");
      if (!img || !img.complete || !img.naturalWidth) return LOGO;
      var w = img.naturalWidth, h = img.naturalHeight, lado = Math.min(w, h), L = 160;
      var cv = document.createElement("canvas"); cv.width = L; cv.height = L; var cx = cv.getContext("2d");
      var fundo = function (cor) { cx.clearRect(0, 0, L, L); if (cor) { cx.fillStyle = cor; cx.fillRect(0, 0, L, L); } cx.drawImage(img, 0, (h - lado) / 2, lado, lado, 0, 0, L, L); };
      fundo(null); var png = b64bytes(cv.toDataURL("image/png"));
      fundo("#FFFFFF"); var jpg = b64bytes(cv.toDataURL("image/jpeg", 0.92));
      LOGO = { png: png, jpg: jpg, lado: L };
    } catch (e) { LOGO = false; }      // imagem de outra origem ou navegador sem canvas: segue sem logo
    return LOGO;
  }

  /* ───────── zip sem compressão (docx e xlsx são zips) ───────── */
  var TAB = null;
  function crc32(u8) {
    if (!TAB) { TAB = []; for (var n = 0; n < 256; n++) { var c = n; for (var k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; TAB[n] = c >>> 0; } }
    var crc = 0xFFFFFFFF; for (var i = 0; i < u8.length; i++) crc = TAB[(crc ^ u8[i]) & 0xFF] ^ (crc >>> 8); return (crc ^ 0xFFFFFFFF) >>> 0;
  }
  function zip(arqs) {
    var partes = [], central = [], pos = 0;
    var u16 = function (v) { return [v & 255, (v >>> 8) & 255]; }, u32 = function (v) { return [v & 255, (v >>> 8) & 255, (v >>> 16) & 255, (v >>> 24) & 255]; };
    arqs.forEach(function (a) {
      var nome = bytes(a.nome), dados = typeof a.dados === "string" ? bytes(a.dados) : a.dados, crc = crc32(dados);
      var cab = [].concat([0x50, 0x4B, 3, 4], u16(20), u16(0x0800), u16(0), u16(0), u16(0x21), u32(crc), u32(dados.length), u32(dados.length), u16(nome.length), u16(0));
      partes.push(new Uint8Array(cab), nome, dados);
      central.push({ nome: nome, crc: crc, tam: dados.length, pos: pos });
      pos += cab.length + nome.length + dados.length;
    });
    var ini = pos, tamC = 0;
    central.forEach(function (c) {
      var cab = [].concat([0x50, 0x4B, 1, 2], u16(20), u16(20), u16(0x0800), u16(0), u16(0), u16(0x21), u32(c.crc), u32(c.tam), u32(c.tam), u16(c.nome.length), u16(0), u16(0), u16(0), u16(0), u32(0), u32(c.pos));
      partes.push(new Uint8Array(cab), c.nome); tamC += cab.length + c.nome.length;
    });
    partes.push(new Uint8Array([].concat([0x50, 0x4B, 5, 6], u16(0), u16(0), u16(central.length), u16(central.length), u32(tamC), u32(ini), u16(0))));
    var total = partes.reduce(function (s, p) { return s + p.length; }, 0), out = new Uint8Array(total), o = 0;
    partes.forEach(function (p) { out.set(p, o); o += p.length; });
    return out;
  }

  /* ───────── Word ───────── */
  function docx(titulo, blocos) {
    var W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"';
    var par = function (txt, estilo) { return "<w:p>" + (estilo ? '<w:pPr><w:pStyle w:val="' + estilo + '"/></w:pPr>' : "") + '<w:r><w:t xml:space="preserve">' + xml(txt) + "</w:t></w:r></w:p>"; };
    var corpo = par(titulo, "Title") + par(TX.gerado + " " + agora(), "Subtle");
    blocos.forEach(function (b) {
      if (b.h) corpo += par(b.t, "Heading" + Math.min(3, Math.max(1, b.h - 1)));
      else if (b.tabela) {
        var cols = Math.max.apply(null, [b.tabela.cab.length].concat(b.tabela.linhas.map(function (l) { return l.length; })));
        var cel = function (t, negrito) { return '<w:tc><w:tcPr><w:tcW w:w="0" w:type="auto"/>' + (negrito ? '<w:shd w:val="clear" w:color="auto" w:fill="33512F"/>' : "") + '</w:tcPr><w:p><w:r>' + (negrito ? '<w:rPr><w:b/><w:color w:val="FFFFFF"/></w:rPr>' : "") + '<w:t xml:space="preserve">' + xml(t) + "</w:t></w:r></w:p></w:tc>"; };
        var lin = function (l, cab) { var s = "<w:tr>" + (cab ? "<w:trPr><w:tblHeader/></w:trPr>" : ""); for (var i = 0; i < cols; i++) s += cel(l[i] == null ? "" : l[i], cab); return s + "</w:tr>"; };
        corpo += '<w:tbl><w:tblPr><w:tblStyle w:val="Grade"/><w:tblW w:w="5000" w:type="pct"/><w:tblLook w:firstRow="1"/></w:tblPr>' + (b.tabela.cab.length ? lin(b.tabela.cab, true) : "") + b.tabela.linhas.map(function (l) { return lin(l, false); }).join("") + "</w:tbl>" + par("", null);
      } else corpo += par(b.t, b.lista ? "Lista" : null);
    });
    var R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"';
    var doc = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document ' + W + " " + R + "><w:body>" + corpo + '<w:sectPr><w:headerReference w:type="default" r:id="rId2"/><w:footerReference w:type="default" r:id="rId3"/><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1418" w:right="1134" w:bottom="1134" w:left="1134" w:header="567" w:footer="567" w:gutter="0"/></w:sectPr></w:body></w:document>';
    // Cabeçalho com a marca e marca d'água "PHYSIS" na diagonal (forma de texto padrão do Word, lida também pelo LibreOffice)
    var VML = 'xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office"';
    var dagua = '<w:r><w:pict><v:shapetype id="_x0000_t136" coordsize="21600,21600" o:spt="136" adj="10800" path="m@7,l@8,m@5,21600l@6,21600e"><v:formulas><v:f eqn="sum #0 0 10800"/><v:f eqn="prod #0 2 1"/><v:f eqn="sum 21600 0 @1"/><v:f eqn="sum 0 0 @2"/><v:f eqn="sum 21600 0 @3"/><v:f eqn="if @0 @3 0"/><v:f eqn="if @0 21600 @1"/><v:f eqn="if @0 0 @2"/><v:f eqn="if @0 @4 21600"/><v:f eqn="mid @5 @6"/><v:f eqn="mid @8 @5"/><v:f eqn="mid @7 @8"/><v:f eqn="mid @6 @7"/><v:f eqn="sum @6 0 @5"/></v:formulas><v:path textpathok="t" o:connecttype="custom" o:connectlocs="@9,0;@10,10800;@11,21600;@12,10800" o:connectangles="270,180,90,0"/><v:textpath on="t" fitshape="t"/><v:handles><v:h position="#0,bottomRight" xrange="6629,14971"/></v:handles><o:lock v:ext="edit" text="t" shapetype="t"/></v:shapetype>' +
      '<v:shape id="PhysisMarcaDagua" o:spid="_x0000_s2049" type="#_x0000_t136" style="position:absolute;margin-left:0;margin-top:0;width:440pt;height:110pt;rotation:315;z-index:-251654144;mso-position-horizontal:center;mso-position-horizontal-relative:margin;mso-position-vertical:center;mso-position-vertical-relative:margin" o:allowincell="f" fillcolor="#DCEBD8" stroked="f"><v:fill opacity=".55"/><v:textpath style="font-family:&quot;Arial&quot;;font-size:1pt;font-weight:bold" string="PHYSIS"/></v:shape></w:pict></w:r>';
    // Cabeçalho = réplica do cabeçalho do sistema: árvore + nome do sistema em serifada verde; título do documento à direita
    var lg = logo(), EMU = 457200;   // 1,27 cm
    var desenho = lg ? '<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="114300"><wp:extent cx="' + EMU + '" cy="' + EMU + '"/><wp:docPr id="1" name="Logo Physis" descr="Logo da Physis"/><a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:nvPicPr><pic:cNvPr id="0" name="logo-physis.png"/><pic:cNvPicPr/></pic:nvPicPr><pic:blipFill><a:blip r:embed="rIdLogo"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="' + EMU + '" cy="' + EMU + '"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>' : "";
    var cabec = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:hdr ' + W + " " + VML + ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"><w:p><w:pPr><w:pBdr><w:bottom w:val="single" w:sz="8" w:space="4" w:color="33512F"/></w:pBdr><w:tabs><w:tab w:val="right" w:pos="9638"/></w:tabs><w:spacing w:after="0"/></w:pPr>' + desenho +
      '<w:r><w:rPr><w:rFonts w:ascii="Georgia" w:hAnsi="Georgia" w:cs="Georgia"/><w:color w:val="33512F"/><w:position w:val="10"/><w:sz w:val="32"/></w:rPr><w:t xml:space="preserve">' + xml(nomeSistema()) + '</w:t></w:r><w:r><w:rPr><w:color w:val="4A4F44"/><w:position w:val="12"/><w:sz w:val="16"/></w:rPr><w:tab/><w:t xml:space="preserve">' + xml(titulo) + "</w:t></w:r>" + dagua + "</w:p></w:hdr>";
    var campo = function (instr) { return '<w:r><w:rPr><w:color w:val="4A4F44"/><w:sz w:val="16"/></w:rPr><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:rPr><w:color w:val="4A4F44"/><w:sz w:val="16"/></w:rPr><w:instrText xml:space="preserve"> ' + instr + ' </w:instrText></w:r><w:r><w:rPr><w:color w:val="4A4F44"/><w:sz w:val="16"/></w:rPr><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:rPr><w:color w:val="4A4F44"/><w:sz w:val="16"/></w:rPr><w:t>1</w:t></w:r><w:r><w:rPr><w:color w:val="4A4F44"/><w:sz w:val="16"/></w:rPr><w:fldChar w:fldCharType="end"/></w:r>'; };
    var cinza = function (t) { return '<w:r><w:rPr><w:color w:val="4A4F44"/><w:sz w:val="16"/></w:rPr><w:t xml:space="preserve">' + xml(t) + "</w:t></w:r>"; };
    var rodape = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr ' + W + '><w:p><w:pPr><w:pBdr><w:top w:val="single" w:sz="4" w:space="4" w:color="C9D2C4"/></w:pBdr><w:tabs><w:tab w:val="right" w:pos="9638"/></w:tabs></w:pPr>' + cinza("Physis Engineering · " + TX.gerado + " " + agora()) + '<w:r><w:tab/></w:r>' + cinza(EN ? "Page " : "Página ") + campo("PAGE") + cinza(EN ? " of " : " de ") + campo("NUMPAGES") + "</w:p></w:ftr>";
    var relsCab = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + (lg ? '<Relationship Id="rIdLogo" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/logo-physis.png"/>' : "") + "</Relationships>";
    var est = function (id, nome, tam, negrito, cor, antes, extra) { return '<w:style w:type="paragraph" w:styleId="' + id + '"><w:name w:val="' + nome + '"/><w:basedOn w:val="Normal"/>' + (extra || "") + '<w:pPr><w:spacing w:before="' + antes + '" w:after="120"/></w:pPr><w:rPr>' + (negrito ? "<w:b/>" : "") + '<w:color w:val="' + cor + '"/><w:sz w:val="' + tam + '"/></w:rPr></w:style>'; };
    var estilos = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles ' + W + '><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="22"/><w:lang w:val="' + (EN ? "en-GB" : "pt-BR") + '"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="300" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>' +
      '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>' +
      est("Title", "Title", 40, true, "33512F", 0) + est("Subtle", "Subtitle", 18, false, "4A4F44", 0) +
      est("Heading1", "heading 1", 30, true, "33512F", 360, '<w:next w:val="Normal"/>').replace("</w:pPr>", '<w:keepNext/><w:outlineLvl w:val="0"/></w:pPr>') +
      est("Heading2", "heading 2", 26, true, "33512F", 280, '<w:next w:val="Normal"/>').replace("</w:pPr>", '<w:keepNext/><w:outlineLvl w:val="1"/></w:pPr>') +
      est("Heading3", "heading 3", 23, true, "33512F", 200, '<w:next w:val="Normal"/>').replace("</w:pPr>", '<w:keepNext/><w:outlineLvl w:val="2"/></w:pPr>') +
      '<w:style w:type="paragraph" w:styleId="Lista"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="360"/></w:pPr></w:style>' +
      '<w:style w:type="table" w:styleId="Grade"><w:name w:val="Table Grid"/><w:tblPr><w:tblBorders><w:top w:val="single" w:sz="4" w:color="C9D2C4"/><w:left w:val="single" w:sz="4" w:color="C9D2C4"/><w:bottom w:val="single" w:sz="4" w:color="C9D2C4"/><w:right w:val="single" w:sz="4" w:color="C9D2C4"/><w:insideH w:val="single" w:sz="4" w:color="C9D2C4"/><w:insideV w:val="single" w:sz="4" w:color="C9D2C4"/></w:tblBorders><w:tblCellMar><w:top w:w="40" w:type="dxa"/><w:left w:w="100" w:type="dxa"/><w:bottom w:w="40" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style></w:styles>';
    return zip([
      { nome: "[Content_Types].xml", dados: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/><Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>' },
      { nome: "_rels/.rels", dados: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>' },
      { nome: "docProps/core.xml", dados: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>' + xml(titulo) + "</dc:title><dc:creator>Physis Engineering</dc:creator><dc:language>" + (EN ? "en-GB" : "pt-BR") + "</dc:language></cp:coreProperties>" },
      { nome: "word/_rels/document.xml.rels", dados: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/></Relationships>' },
      { nome: "word/document.xml", dados: doc }, { nome: "word/styles.xml", dados: estilos },
      { nome: "word/header1.xml", dados: cabec }, { nome: "word/footer1.xml", dados: rodape }, { nome: "word/_rels/header1.xml.rels", dados: relsCab }]
      .concat(lg ? [{ nome: "word/media/logo-physis.png", dados: lg.png }] : []));
  }

  /* ───────── Excel ───────── */
  function numero(t) {
    var s = limpo(t); if (!/^[+\-−]?\s*(R\$\s*)?[\d.]+(,\d+)?\s*%?$/.test(s) || !/\d/.test(s)) return null;
    if (/^0\d/.test(s.replace(/[^\d]/g, "")) && !/,/.test(s)) return null;          // CEP, código com zero à esquerda
    var neg = /^[\-−]/.test(s), n = Number(s.replace(/[^\d.,]/g, "").replace(/\./g, "").replace(",", "."));
    if (!isFinite(n)) return null; if (/%$/.test(s)) n = n / 100; return neg ? -n : n;
  }
  function xlsx(titulo, blocos) {
    var linhas = [], col = function (n) { var s = ""; n++; while (n > 0) { var r = (n - 1) % 26; s = String.fromCharCode(65 + r) + s; n = Math.floor((n - 1) / 26); } return s; };
    // faixa da marca no topo (o Excel não tem marca d'água; a faixa e o cabeçalho de impressão fazem esse papel)
    var lg = logo();
    linhas.push([{ v: nomeSistema(), e: 6 }]); linhas.push([{ v: titulo, e: 2 }]); linhas.push([{ v: TX.gerado + " " + agora(), e: 8 }]); linhas.push([]);
    var larg = [];
    blocos.forEach(function (b) {
      if (b.h) { linhas.push([]); linhas.push([{ v: b.t, e: 1 }]); }
      else if (b.tabela) { if (b.tabela.cab.length) linhas.push(b.tabela.cab.map(function (c) { return { v: c, e: 7 }; }));
        b.tabela.linhas.forEach(function (l) { linhas.push(l.map(function (c) {
          if (typeof c === "number") return isFinite(c) ? { v: c, e: 9, n: true, larg: 10 } : { v: "", e: 9 };
          if (ehData(c)) { var hr = c.getHours() || c.getMinutes() || c.getSeconds(); return { v: serial(c), e: hr ? 12 : 5, n: true, larg: hr ? 17 : 12 }; }
          if (c && typeof c === "object" && "s" in c) return { v: String(c.s == null ? "" : c.s), e: 9 };
          var dt = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(limpo(c));
          if (dt) return { v: Math.round((Date.UTC(+dt[3], +dt[2] - 1, +dt[1]) - Date.UTC(1899, 11, 30)) / 86400000), e: 5, n: true, larg: 12 };
          var n = numero(c); return n === null ? { v: c, e: 9 } : { v: n, e: /R\$/.test(c) ? 10 : /%\s*$/.test(c) ? 11 : 9, n: true, larg: /R\$/.test(c) ? Math.max(14, limpo(c).length + 4) : 10 }; })); }); linhas.push([]); }
      else linhas.push([{ v: b.t, e: 0 }]);
    });
    var dados = linhas.map(function (l, i) {
      return '<row r="' + (i + 1) + '">' + l.map(function (c, j) { var t = String(c.v == null ? "" : c.v); larg[j] = Math.max(larg[j] || 12, c.larg || Math.min(60, (i < 2 || (l.length === 1 && j === 0) ? 12 : t.length) + 2));
        var ref = col(j) + (i + 1); if (t === "" && c.e !== 6) return "";
        return c.n ? '<c r="' + ref + '" s="' + c.e + '"><v>' + c.v + "</v></c>" : '<c r="' + ref + '" s="' + c.e + '" t="inlineStr"><is><t xml:space="preserve">' + xml(t) + "</t></is></c>"; }).join("") + "</row>";
    }).join("");
    var M = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"';
    // a faixa da marca ocupa a largura de todas as colunas usadas
    var nCols = Math.max(1, larg.length), mescla = nCols > 1 ? '<mergeCells count="1"><mergeCell ref="A1:' + col(nCols - 1) + '1"/></mergeCells>' : "";
    dados = dados.replace('<row r="1">', '<row r="1" ht="34" customHeight="1">');
    var impressao = '<pageMargins left="0.6" right="0.6" top="0.9" bottom="0.8" header="0.4" footer="0.4"/><pageSetup paperSize="9" orientation="' + (nCols > 6 ? "landscape" : "portrait") + '" fitToWidth="1" fitToHeight="0"/>' +
      "<headerFooter><oddHeader>" + xml('&L&"Arial,Bold"&K33512FPHYSIS ENGINEERING&R&"Arial,Regular"&K4A4F44' + String(titulo || "").replace(/&/g, "&&")) + "</oddHeader><oddFooter>" + xml("&L&K4A4F44Physis Engineering&R&K4A4F44" + (EN ? "Page &P of &N" : "Página &P de &N")) + "</oddFooter></headerFooter>";
    var folha = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet ' + M + ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheetPr><pageSetUpPr fitToPage="1"/></sheetPr><sheetViews><sheetView workbookViewId="0" showGridLines="0"/></sheetViews><cols>' + larg.map(function (w, j) { return '<col min="' + (j + 1) + '" max="' + (j + 1) + '" width="' + (w || 10) + '" customWidth="1"/>'; }).join("") + "</cols><sheetData>" + dados + "</sheetData>" + mescla + impressao + (lg ? '<drawing r:id="rId1"/>' : "") + "</worksheet>";
    // a árvore da Physis no canto do cabeçalho, como nas telas
    var desenho = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><xdr:oneCellAnchor><xdr:from><xdr:col>0</xdr:col><xdr:colOff>57150</xdr:colOff><xdr:row>0</xdr:row><xdr:rowOff>47625</xdr:rowOff></xdr:from><xdr:ext cx="333375" cy="333375"/><xdr:pic><xdr:nvPicPr><xdr:cNvPr id="2" name="Logo Physis" descr="Logo da Physis"/><xdr:cNvPicPr><a:picLocks noChangeAspect="1"/></xdr:cNvPicPr></xdr:nvPicPr><xdr:blipFill><a:blip r:embed="rId1"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill><xdr:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="333375" cy="333375"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr></xdr:pic><xdr:clientData/></xdr:oneCellAnchor></xdr:wsDr>';
    if (!larg.length) folha = folha.replace("<cols></cols>", "");
    // estilos: 0 normal · 1 negrito · 2 título verde · 3 R$ · 4 % · 5 data · 6 faixa da marca · 7 cabeçalho de tabela · 8 nota cinza · 9 célula com borda · 10 R$ com borda · 11 % com borda · 12 data e hora com borda
    var estilos = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet ' + M + '><numFmts count="1"><numFmt numFmtId="164" formatCode="&quot;R$&quot;\\ #,##0.00"/></numFmts>' +
      '<fonts count="7"><font><sz val="10"/><color rgb="FF1C2B21"/><name val="Arial"/></font><font><b/><sz val="10"/><color rgb="FF1C2B21"/><name val="Arial"/></font><font><b/><sz val="14"/><color rgb="FF33512F"/><name val="Arial"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Arial"/></font><font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Arial"/></font><font><sz val="9"/><color rgb="FF4A4F44"/><name val="Arial"/></font><font><sz val="17"/><color rgb="FF33512F"/><name val="Georgia"/></font></fonts>' +
      '<fills count="5"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF33512F"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FF4B7547"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF4F6F1"/><bgColor indexed="64"/></patternFill></fill></fills>' +
      '<borders count="3"><border><left/><right/><top/><bottom/><diagonal/></border><border><left style="thin"><color rgb="FFC9D2C4"/></left><right style="thin"><color rgb="FFC9D2C4"/></right><top style="thin"><color rgb="FFC9D2C4"/></top><bottom style="thin"><color rgb="FFC9D2C4"/></bottom><diagonal/></border><border><left/><right/><top/><bottom style="medium"><color rgb="FF33512F"/></bottom><diagonal/></border></borders>' +
      '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="13">' +
      '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/><xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>' +
      '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="10" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="14" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>' +
      '<xf numFmtId="0" fontId="6" fillId="4" borderId="2" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center" indent="' + (lg ? 4 : 0) + '"/></xf><xf numFmtId="0" fontId="4" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"><alignment vertical="center" wrapText="1"/></xf>' +
      '<xf numFmtId="0" fontId="5" fillId="0" borderId="0" xfId="0" applyFont="1"/><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"><alignment vertical="top" wrapText="1"/></xf>' +
      '<xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/><xf numFmtId="10" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>' +
      '<xf numFmtId="22" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>' +
      '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>';
    var aba = xml(String(titulo || "Physis").replace(/[\\\/\?\*\[\]:]/g, " ").slice(0, 31)) || "Physis";
    return zip([
      { nome: "[Content_Types].xml", dados: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' + (lg ? '<Default Extension="png" ContentType="image/png"/><Override PartName="/xl/drawings/drawing1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>' : "") + '</Types>' },
      { nome: "_rels/.rels", dados: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>' },
      { nome: "xl/workbook.xml", dados: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook ' + M + ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="' + aba + '" sheetId="1" r:id="rId1"/></sheets></workbook>' },
      { nome: "xl/_rels/workbook.xml.rels", dados: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>' },
      { nome: "xl/worksheets/sheet1.xml", dados: folha }, { nome: "xl/styles.xml", dados: estilos }]
      .concat(lg ? [
        { nome: "xl/worksheets/_rels/sheet1.xml.rels", dados: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/></Relationships>' },
        { nome: "xl/drawings/drawing1.xml", dados: desenho },
        { nome: "xl/drawings/_rels/drawing1.xml.rels", dados: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/logo-physis.png"/></Relationships>' },
        { nome: "xl/media/logo-physis.png", dados: lg.png }] : []));
  }

  /* ───────── planilha a partir de linhas (os lugares que baixavam só CSV) ───────── */
  function ehData(c) { return Object.prototype.toString.call(c) === "[object Date]" && !isNaN(c.getTime()); }
  function serial(d) { return (Date.UTC(d.getFullYear(), d.getMonth(), d.getDate(), d.getHours(), d.getMinutes(), d.getSeconds()) - Date.UTC(1899, 11, 30)) / 86400000; }
  /* texto de uma célula -> número, data ou texto. decimal "," (padrão, pt-BR: 1.234,5) ou "." (7.125) */
  function tipar(v, decimal) {
    if (v == null) return { s: "" }; if (typeof v === "number" || ehData(v)) return v;
    var s = limpo(v), m; if (!s) return { s: "" };
    if ((m = /^(\d{2})\/(\d{2})\/(\d{4})(?:,?\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$/.exec(s))) return new Date(+m[3], +m[2] - 1, +m[1], +(m[4] || 0), +(m[5] || 0), +(m[6] || 0));
    if ((m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?$/.exec(s))) return new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0), +(m[6] || 0));
    if (/^[+\-−]?0\d/.test(s) && !/^[+\-−]?0[.,]\d/.test(s)) return { s: s };            // código com zero à esquerda (nó 03, CEP)
    var neg = /^[\-−]/.test(s), c = s.replace(/^[+\-−]/, ""), n = null;
    if (/^\d+$/.test(c)) n = Number(c);
    else if (decimal === ".") { if (/^\d+\.\d+$/.test(c)) n = Number(c); else if (/^\d{1,3}(,\d{3})+(\.\d+)?$/.test(c)) n = Number(c.replace(/,/g, "")); }
    else { if (/^\d+,\d+$/.test(c)) n = Number(c.replace(",", ".")); else if (/^\d{1,3}(\.\d{3})+(,\d+)?$/.test(c)) n = Number(c.replace(/\./g, "").replace(",", ".")); else if (/^\d+\.\d+$/.test(c)) n = Number(c); }
    if (n === null || !isFinite(n)) return /R\$|%\s*$/.test(s) ? s : { s: s };              // R$ e % ficam com o leitor do Excel da barra
    return neg ? -n : n;
  }
  function planilha(titulo, cab, linhas, op) {
    var dec = op && op.decimal === "." ? "." : ",";
    return xlsx(titulo, [{ tabela: { cab: (cab || []).map(function (c) { return limpo(c); }), linhas: (linhas || []).map(function (l) { return l.map(function (c) { return tipar(c, dec); }); }) } }]);
  }
  /* CSV (com ; ou ,) -> { cab, linhas } */
  function deCsv(texto) {
    texto = String(texto || "").replace(/^\uFEFF/, ""); var pl = texto.split(/\r?\n/)[0] || "", sep = (pl.match(/;/g) || []).length >= (pl.match(/,/g) || []).length ? ";" : ",";
    var linhas = [], l = [], cel = "", aspas = false;
    for (var i = 0; i < texto.length; i++) { var ch = texto[i];
      if (aspas) { if (ch === '"') { if (texto[i + 1] === '"') { cel += '"'; i++; } else aspas = false; } else cel += ch; continue; }
      if (ch === '"') aspas = true; else if (ch === sep) { l.push(cel); cel = ""; } else if (ch === "\n" || ch === "\r") { if (ch === "\r" && texto[i + 1] === "\n") i++; l.push(cel); cel = ""; if (l.some(function (x) { return x !== ""; })) linhas.push(l); l = []; } else cel += ch; }
    l.push(cel); if (l.some(function (x) { return x !== ""; })) linhas.push(l);
    return { cab: linhas.shift() || [], linhas: linhas, sep: sep };
  }
  function csvParaXlsx(titulo, texto, op) { var c = deCsv(texto); return planilha(titulo, c.cab, c.linhas, { decimal: op && op.decimal ? op.decimal : (c.sep === "," ? "." : ",") }); }
  function baixarPlanilha(nome, titulo, cab, linhas, op) {
    return baixar(String(nome || arquivo(titulo)).replace(/\.(csv|xlsx)$/i, "") + ".xlsx", planilha(titulo, cab, linhas, op), MIME.xlsx);
  }

  /* ───────── PDF (A4, texto e tabelas; fontes padrão, WinAnsi) ───────── */
  var TROCA = { "\u2018": "'", "\u2019": "'", "\u201C": '"', "\u201D": '"', "\u2013": "-", "\u2014": "-", "\u2212": "-", "\u2026": "...", "\u2022": "-", "\u203A": ">", "\u00D7": "x", "\u2192": "->", "\u2264": "<=", "\u2265": ">=", "\u00A0": " ", "\u2713": "x", "\u2715": "x" };
  function latin(s) { var o = ""; s = String(s == null ? "" : s); for (var i = 0; i < s.length; i++) { var ch = TROCA[s[i]] !== undefined ? TROCA[s[i]] : s[i]; for (var k = 0; k < ch.length; k++) { var c = ch.charCodeAt(k); o += c < 256 && (c >= 32 || c === 10) ? ch[k] : "?"; } } return o; }
  function pdfStr(s) { var o = "("; for (var i = 0; i < s.length; i++) { var c = s.charCodeAt(i); if (c === 40 || c === 41 || c === 92) o += "\\" + s[i]; else if (c > 126) o += "\\" + c.toString(8).padStart(3, "0"); else o += s[i]; } return o + ")"; }
  function quebrar(txt, max) {
    var out = []; String(txt).split("\n").forEach(function (par) {
      var linha = ""; par.split(" ").forEach(function (p) {
        while (p.length > max) { if (linha) { out.push(linha); linha = ""; } out.push(p.slice(0, max)); p = p.slice(max); }
        if (!linha) linha = p; else if ((linha + " " + p).length <= max) linha += " " + p; else { out.push(linha); linha = p; }
      }); out.push(linha);
    }); return out;
  }
  function pdf(titulo, blocos) {
    var LW = 595, LH = 842, M = 48, TOPO = 82, util = LW - 2 * M, paginas = [], cur = [], y = LH - TOPO;
    var nova = function () { if (cur.length) paginas.push(cur); cur = []; y = LH - TOPO; };
    var texto = function (linha, fonte, tam, x, cor) { cur.push("BT /" + fonte + " " + tam + " Tf " + (cor || "0.11 0.17 0.13") + " rg " + (x || M).toFixed(1) + " " + y.toFixed(1) + " Td " + pdfStr(linha) + " Tj ET"); };
    var escrever = function (t, fonte, tam, larg, antes, depois, cor, recuo) {
      var passo = tam * 1.38, max = Math.max(8, Math.floor((util - (recuo || 0)) / (tam * larg))), ls = quebrar(latin(t), max);
      y -= antes; ls.forEach(function (l) { if (y - passo < M) nova(); y -= passo; texto(l, fonte, tam, M + (recuo || 0), cor); }); y -= depois;
    };
    escrever(titulo, "F2", 18, 0.56, 0, 2, "0.2 0.32 0.18");
    escrever(TX.gerado + " " + agora() + " - Physis Engineering", "F1", 9, 0.5, 0, 10, "0.29 0.31 0.27");
    blocos.forEach(function (b) {
      if (b.h) { if (y < M + 70) nova(); escrever(b.t, "F2", b.h <= 2 ? 14 : 12, 0.56, 10, 3, "0.2 0.32 0.18"); }
      else if (b.tabela) {
        var tam = 8, cw = tam * 0.6, linhasT = (b.tabela.cab.length ? [b.tabela.cab] : []).concat(b.tabela.linhas), n = Math.max.apply(null, linhasT.map(function (l) { return l.length; }).concat([1]));
        var maxChars = Math.floor(util / cw) - (n - 1) * 2, quer = [];
        for (var j = 0; j < n; j++) quer[j] = Math.max.apply(null, linhasT.map(function (l) { return Math.min(60, latin(l[j] == null ? "" : l[j]).length); }).concat([3]));
        var soma = quer.reduce(function (a, c) { return a + c; }, 0);
        if (soma > maxChars) { var sobra = maxChars, fl = 0; quer = quer.map(function (w) { var v = Math.max(4, Math.floor(w * maxChars / soma)); fl += v; return v; }); if (fl > maxChars) quer[quer.indexOf(Math.max.apply(null, quer))] -= fl - maxChars; }
        y -= 4;
        linhasT.forEach(function (l, i) {
          var cels = quer.map(function (w, j) { return quebrar(latin(l[j] == null ? "" : l[j]), w); }), alt = Math.max.apply(null, cels.map(function (c) { return c.length; })), passo = tam * 1.35;
          if (y - alt * passo - 6 < M) nova();
          var eCab = i === 0 && b.tabela.cab.length;
          // cabeçalho da tabela: faixa verde Physis com texto branco
          if (eCab) cur.push("0.2 0.318 0.184 rg " + (M - 3) + " " + (y - alt * passo - 4).toFixed(1) + " " + (util + 6) + " " + (alt * passo + 5).toFixed(1) + " re f");
          for (var k = 0; k < alt; k++) { y -= passo; var x = M; cels.forEach(function (c, j) { if (c[k]) texto(c[k], eCab ? "F4" : "F3", tam, x, eCab ? "1 1 1" : null); x += (quer[j] + 2) * cw; }); }
          y -= 3; cur.push((eCab ? "0.8" : "0.4") + " w 0.79 0.82 0.77 RG " + M + " " + y.toFixed(1) + " m " + (LW - M) + " " + y.toFixed(1) + " l S"); y -= 2;
        });
        y -= 8;
      } else escrever((b.lista ? "- " : "") + b.t, "F1", 10.5, 0.5, 0, 4, null, b.lista ? 10 : 0);
    });
    nova();
    var objs = [], add = function (s) { objs.push(s); return objs.length; };
    var fonte = function (n) { return add("<< /Type /Font /Subtype /Type1 /BaseFont /" + n + " /Encoding /WinAnsiEncoding >>"); };
    var f1 = fonte("Helvetica"), f2 = fonte("Helvetica-Bold"), f3 = fonte("Courier"), f4 = fonte("Courier-Bold");
    var gs = add("<< /Type /ExtGState /ca 0.07 /CA 0.07 >>");     // transparência da marca d'água
    var f5 = fonte("Times-Roman");                                  // serifada do nome do sistema, como no cabeçalho das telas
    var lg = logo(), im = 0;
    if (lg) { var jb = ""; for (var q = 0; q < lg.jpg.length; q++) jb += String.fromCharCode(lg.jpg[q]);
      im = add("<< /Type /XObject /Subtype /Image /Width " + lg.lado + " /Height " + lg.lado + " /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length " + lg.jpg.length + " >>\nstream\n" + jb + "\nendstream"); }
    var sistema = latin(nomeSistema()).slice(0, 40);
    var pagsId = objs.length + 1 + paginas.length * 2, kids = [];
    paginas.forEach(function (p, i) {
      // marca d'água "PHYSIS" na diagonal, atrás do conteúdo, em verde Physis bem claro
      var agua = "q /GS1 gs 0.29 0.46 0.28 rg BT /F2 120 Tf 0.7071 0.7071 -0.7071 0.7071 150 210 Tm (PHYSIS) Tj ET Q";
      // réplica do cabeçalho do sistema: fundo claro, árvore, nome do sistema em serifada verde, título à direita, linha verde
      var xNome = lg ? M + 38 : M;
      var faixa = "0.957 0.965 0.945 rg 0 " + (LH - 56) + " " + LW + " 56 re f 1.2 w 0.2 0.318 0.184 RG 0 " + (LH - 56) + " m " + LW + " " + (LH - 56) + " l S" +
        (lg ? " q 30 0 0 30 " + M + " " + (LH - 44) + " cm /Im1 Do Q" : "") +
        " BT /F5 17 Tf 0.2 0.318 0.184 rg " + xNome + " " + (LH - 35) + " Td " + pdfStr(sistema) + " Tj ET" +
        " BT /F1 8.5 Tf 0.29 0.31 0.27 rg " + (LW - M - Math.min(60, latin(titulo).length) * 4.3).toFixed(1) + " " + (LH - 33) + " Td " + pdfStr(latin(titulo).slice(0, 60)) + " Tj ET";
      var rod = "0.4 w 0.79 0.82 0.77 RG " + M + " 40 m " + (LW - M) + " 40 l S BT /F1 8 Tf 0.29 0.31 0.27 rg " + M + " 28 Td " + pdfStr("Physis Engineering - " + latin(titulo).slice(0, 60)) + " Tj ET" +
        " BT /F1 8 Tf 0.29 0.31 0.27 rg " + (LW - M - 52) + " 28 Td " + pdfStr((EN ? "Page " : "Pagina ") + (i + 1) + "/" + paginas.length) + " Tj ET";
      var conteudo = agua + "\n" + faixa + "\n" + p.join("\n") + "\n" + rod, c = add("<< /Length " + conteudo.length + " >>\nstream\n" + conteudo + "\nendstream");
      kids.push(add("<< /Type /Page /Parent " + pagsId + " 0 R /MediaBox [0 0 " + LW + " " + LH + "] /Contents " + c + " 0 R /Resources << /Font << /F1 " + f1 + " 0 R /F2 " + f2 + " 0 R /F3 " + f3 + " 0 R /F4 " + f4 + " 0 R /F5 " + f5 + " 0 R >> /ExtGState << /GS1 " + gs + " 0 R >>" + (im ? " /XObject << /Im1 " + im + " 0 R >>" : "") + " >> >>"));
    });
    add("<< /Type /Pages /Kids [" + kids.map(function (k) { return k + " 0 R"; }).join(" ") + "] /Count " + kids.length + " >>");
    var cat = add("<< /Type /Catalog /Pages " + pagsId + " 0 R /Lang (" + (EN ? "en-GB" : "pt-BR") + ") /ViewerPreferences << /DisplayDocTitle true >> >>");
    var info = add("<< /Title " + pdfStr(latin(titulo)) + " /Author (Physis Engineering) /Producer (physis-exportar 1) >>");
    var out = "%PDF-1.4\n%\u00E2\u00E3\u00CF\u00D3\n", off = [];
    objs.forEach(function (o, i) { off.push(out.length); out += (i + 1) + " 0 obj\n" + o + "\nendobj\n"; });
    var xref = out.length; out += "xref\n0 " + (objs.length + 1) + "\n0000000000 65535 f \n" + off.map(function (o) { return String(o).padStart(10, "0") + " 00000 n \n"; }).join("") +
      "trailer\n<< /Size " + (objs.length + 1) + " /Root " + cat + " 0 R /Info " + info + " 0 R >>\nstartxref\n" + xref + "\n%%EOF\n";
    var u = new Uint8Array(out.length); for (var i = 0; i < out.length; i++) u[i] = out.charCodeAt(i) & 255; return u;
  }

  /* ───────── tirar da tela o que será exportado ───────── */
  var BLOCO = /^(DIV|P|TABLE|UL|OL|SECTION|ARTICLE|FIELDSET|H1|H2|H3|H4|H5|DL|DETAILS|PRE|LABEL|INPUT|SELECT|TEXTAREA|LI|DT|DD|FORM|MAIN|HEADER|FOOTER|ASIDE|NAV|SUMMARY|LEGEND|OUTPUT|IFRAME)$/;
  function some(el) { if (el.hidden || el.getAttribute("aria-hidden") === "true" || /\b(so-leitor|px-exportar|px-fora|px-pular|pp-pular|salto)\b/.test(el.className || "")) return true; var w = (el.ownerDocument && el.ownerDocument.defaultView) || g, s = w.getComputedStyle(el); return s.display === "none" || s.visibility === "hidden"; }
  /* programa num quadro da mesma origem (srcdoc ou mesmo servidor): o corpo do quadro; outra origem: nada (o navegador não deixa ler) */
  function corpoDoQuadro(f) { try { var d = f.contentDocument; return d && d.body ? d.body : null; } catch (e) { return null; } }
  function valorDe(c) {
    if (c.tagName === "SELECT") return c.selectedOptions[0] ? limpo(c.selectedOptions[0].textContent) : "";
    if (c.type === "checkbox" || c.type === "radio") return c.checked ? (EN ? "yes" : "sim") : null;
    if (c.type === "password" || c.type === "file" || c.type === "hidden") return null;
    return c.value;
  }
  function espacar(c) {
    c.querySelectorAll("br").forEach(function (b) { b.replaceWith(" · "); });
    c.querySelectorAll("span,strong,b,small,code,em,a,output,dt,dd,li,p,div").forEach(function (x) { x.after(" "); });
    return limpo(c.textContent).replace(/\s+·\s+/g, " · ").replace(/^·\s*|\s*·$/g, "").replace(/\s+([.,;:])/g, "$1");
  }
  function textoSemControles(el) { var c = el.cloneNode(true); c.querySelectorAll("input,select,textarea,button,script,style,.so-leitor,svg,.grafico").forEach(function (x) { x.remove(); }); return espacar(c); }
  function celula(td) {
    var cs = td.querySelectorAll("input,select,textarea"), v = [];
    cs.forEach(function (c) { var x = valorDe(c); if (x !== null && x !== "") v.push(x); });
    var c2 = td.cloneNode(true);
    c2.querySelectorAll("input,select,textarea,button,script,style,.so-leitor,svg,.grafico").forEach(function (x) { x.remove(); });
    var t = espacar(c2);
    return limpo((t ? t + (v.length ? " " : "") : "") + v.join(" "));
  }
  function extrair(raiz) {
    var out = [], feitos = new Set();
    var controle = function (c) { if (feitos.has(c)) return; feitos.add(c); var v = valorDe(c); if (v === null) return; var rot = c.labels && c.labels[0] ? textoSemControles(c.labels[0]) : (c.getAttribute("aria-label") || ""); if (c.type === "checkbox" || c.type === "radio") { if (rot) out.push({ t: rot, lista: true }); return; } if (!rot && !limpo(v)) return; String(v).split("\n").forEach(function (l, i) { if (i === 0) out.push({ t: (rot ? rot + ": " : "") + limpo(l) }); else if (limpo(l)) out.push({ t: limpo(l), lista: true }); }); };
    (function anda(el) {
      Array.prototype.forEach.call(el.children, function (f) {
        var tag = f.tagName; if (/^(SCRIPT|STYLE|BUTTON|NAV|SVG|svg|DATALIST|TEMPLATE)$/.test(tag) || some(f)) return;
        if (/^H[1-5]$/.test(tag)) { var t = limpo(f.innerText); if (t) out.push({ h: Number(tag[1]), t: t }); return; }
        if (tag === "LEGEND" || tag === "SUMMARY") { var tl = limpo(f.innerText); if (tl) out.push({ h: 3, t: tl }); return; }
        if (tag === "TABLE") {
          var cab = [], linhasT = [];
          f.querySelectorAll("thead tr").forEach(function (tr) { cab = Array.prototype.map.call(tr.children, celula); });
          f.querySelectorAll("tbody tr, table > tr").forEach(function (tr) { if (tr.closest("table") !== f) return; var l = Array.prototype.map.call(tr.children, celula); if (l.some(function (x) { return x; })) linhasT.push(l); });
          var n = Math.max(cab.length, Math.max.apply(null, linhasT.map(function (l) { return l.length; }).concat([0])));
          for (var j = n - 1; j >= 0; j--) { if (!(cab[j] || "") && linhasT.every(function (l) { return !(l[j] || ""); })) { if (cab.length > j) cab.splice(j, 1); linhasT.forEach(function (l) { if (l.length > j) l.splice(j, 1); }); } }
          if (cab.length || linhasT.length) out.push({ tabela: { cab: cab, linhas: linhasT } }); return;
        }
        if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return controle(f);
        if (tag === "IFRAME") { var cq = corpoDoQuadro(f); if (cq) anda(cq); return; }
        if (tag === "LABEL") { var c = f.control || f.querySelector("input,select,textarea"); if (c) return controle(c); }
        if (tag === "DETAILS" && !f.open) { var s = f.querySelector("summary"); return; }
        if (tag === "LI") { if (f.querySelector("ul,ol,table,input,select,textarea")) return anda(f); var tli = limpo(textoSemControles(f)); if (tli) out.push({ t: tli, lista: true }); return; }
        var temBloco = Array.prototype.some.call(f.querySelectorAll("*"), function (x) { return BLOCO.test(x.tagName); });
        if (temBloco) return anda(f);
        var tx = limpo(textoSemControles(f)); if (tx) out.push({ t: tx, lista: tag === "DD" });
      });
    })(raiz);
    return out;
  }

  /* ───────── baixar ───────── */
  var MIME = { docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", pdf: "application/pdf" };
  function baixar(nome, u8, mime) {
    var blob = new Blob([u8], { type: mime });
    var direto = function () { var u = URL.createObjectURL(blob), a = document.createElement("a"); a.href = u; a.download = nome; document.body.appendChild(a); a.click(); a.remove(); setTimeout(function () { URL.revokeObjectURL(u); }, 4000); return Promise.resolve(true); };
    if (g.claude && typeof g.claude.use === "function") return g.claude.use("downloads").then(function (d) { return d ? d.save({ filename: nome, data: blob }).then(function () { return true; }) : direto(); });
    return direto();
  }
  function gerar(formato, titulo, raiz) {
    var blocos = extrair(raiz); if (!blocos.length) return null;
    return { nome: arquivo(titulo) + "." + formato, mime: MIME[formato], dados: formato === "docx" ? docx(titulo, blocos) : formato === "xlsx" ? xlsx(titulo, blocos) : pdf(titulo, blocos), blocos: blocos };
  }

  /* ───────── a barra que aparece em cada tela ───────── */
  var seq = 0;
  function barra(op) {
    var TX = TX_PADRAO(op);
    var id = "px-exp-" + (++seq), aberto = false, el = document.createElement("section");
    el.className = "px-exportar"; el.setAttribute("aria-label", TX.baixar);
    el.style.cssText = "margin:18px 0 0;padding:12px 14px;border:1px solid #D6DBCF;border-radius:10px;background:transparent;display:flex;flex-direction:column;gap:10px;font:inherit";
    var bt = "font:inherit;font-weight:600;min-height:44px;padding:0 14px;border-radius:8px;border:1px solid currentColor;background:transparent;color:inherit;cursor:pointer";
    var pessoas = op.encaminhar && op.encaminhar.pessoas, semEnc = op.encaminhar === false;   // encaminhar a colegas só existe na gestão interna
    var pinta = function () {
      el.innerHTML = '<div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center"><strong id="' + id + '-t" style="margin-right:4px">' + TX.baixar + '</strong>' +
        ["docx", "pdf", "xlsx"].map(function (f) { var odf = typeof el.pxFormato === "function";
          var dica = f === "pdf" ? TX.dicaPdf : !odf ? "" : f === "docx" ? TX.dicaDoc : TX.dicaPlan;
          return '<button type="button" data-px-f="' + f + '" aria-describedby="' + id + '-t"' + (dica ? ' title="' + xml(dica) + '"' : "") + ' style="' + bt + '">' + TX[f === "docx" ? "word" : f === "xlsx" ? "excel" : "pdf"] + "</button>"; }).join("") +
        (semEnc ? "" : '<button type="button" data-px-enc="1" aria-expanded="' + aberto + '" aria-controls="' + id + '-enc" style="' + bt + '">' + TX.enc + "</button>") + "</div>" +
        (semEnc ? "" : '<div id="' + id + '-enc"' + (aberto ? "" : " hidden") + ' style="display:' + (aberto ? "grid" : "none") + ';gap:8px;max-width:640px">' +
        (pessoas ? '<label style="display:grid;gap:3px;font-weight:600">' + TX.para + '<select data-px-para="1" style="font:inherit;min-height:44px;padding:8px 10px;border:1px solid #8A9284;border-radius:8px;background:#fff;color:#1C2B21"><option value="">' + TX.escolha + "</option>" + pessoas.map(function (p) { return '<option value="' + xml(p.id) + '">' + xml(p.nome) + "</option>"; }).join("") + "</select></label>" : '<p style="margin:0">' + TX.semServidor + "</p>") +
        '<label style="display:grid;gap:3px;font-weight:600">' + TX.nota + '<textarea data-px-nota="1" rows="2" style="font:inherit;padding:8px 10px;border:1px solid #8A9284;border-radius:8px;background:#fff;color:#1C2B21"></textarea></label>' +
        '<label style="display:grid;gap:3px;font-weight:600">' + TX.link + '<input data-px-link="1" readonly value="' + xml(op.link ? op.link() : g.location.href) + '" style="font:inherit;min-height:44px;padding:8px 10px;border:1px solid #8A9284;border-radius:8px;background:#fff;color:#1C2B21"></label>' +
        '<div><button type="button" data-px-env="1" style="' + bt + '">' + (pessoas ? TX.enviar : TX.copiar) + "</button></div></div>") +
        '<div data-px-msg="1" role="status" style="min-height:1.2em;font-weight:600"></div>';
    };
    var dizer = function (t) { var m = el.querySelector("[data-px-msg]"); if (m) m.textContent = t; };
    pinta();
    /* tela que troca de idioma sem recarregar (SCADA): a barra acompanha o lang do <html> */
    if (typeof op.idiomaTela === "function" && g.MutationObserver) new MutationObserver(function () { var n = TX_PADRAO(op); if (n !== TX) { TX = n; el.setAttribute("aria-label", TX.baixar); pinta(); } }).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });
    el.addEventListener("click", function (ev) {
      var b = ev.target.closest("button"); if (!b) return;
      /* formato aberto (physis-odf.js acoplado): ele gera e diz o resultado; devolve false para cair no padrão */
      if (b.dataset.pxF && typeof el.pxFormato === "function" && el.pxFormato(b.dataset.pxF, b, dizer)) return;
      if (b.dataset.pxF) { var r = gerar(b.dataset.pxF, op.titulo(), op.raiz()); if (!r) return dizer(TX.vazio);
        baixar(r.nome, r.dados, r.mime).then(function () { dizer(TX.baixado(r.nome)); }, function (e) { dizer(e && /cancel|declin|not_granted/i.test(String(e.code || e.message || e)) ? TX.cancelado : TX.falha); }); return; }
      if (b.dataset.pxEnc) { aberto = !aberto; pinta(); var f = el.querySelector(pessoas ? "[data-px-para]" : "[data-px-nota]"); if (aberto && f) f.focus(); else el.querySelector("[data-px-enc]").focus(); return; }
      if (b.dataset.pxEnv) { var nota = el.querySelector("[data-px-nota]").value.trim(), link = el.querySelector("[data-px-link]").value;
        if (pessoas) { var para = el.querySelector("[data-px-para]").value; if (!para) { dizer(TX.escolha + "."); el.querySelector("[data-px-para]").focus(); return; } dizer(op.encaminhar.enviar(para, nota, link, op.titulo()) || ""); return; }
        var txt = op.titulo() + (nota ? "\n" + nota : "") + "\n" + link;
        var falhou = function () { var i = el.querySelector("[data-px-link]"); i.focus(); i.select(); dizer(TX.semCopia); };
        if (g.navigator.clipboard && g.navigator.clipboard.writeText) g.navigator.clipboard.writeText(txt).then(function () { dizer(TX.copiado); }, falhou); else falhou(); }
    });
    el.pxRepintar = pinta;   // o acoplar do physis-odf.js repinta para pôr as dicas de formato aberto
    return el;
  }

  g.PhysisExportar = { docx: docx, xlsx: xlsx, pdf: pdf, extrair: extrair, gerar: gerar, baixar: baixar, barra: barra, zip: zip, numero: numero,
    planilha: planilha, csvParaXlsx: csvParaXlsx, deCsv: deCsv, tipar: tipar, baixarPlanilha: baixarPlanilha };
})(typeof window !== "undefined" ? window : this);
