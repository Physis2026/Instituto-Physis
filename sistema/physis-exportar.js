/* physis-exportar.js v1 · 14/11/2026
 *
 * Baixar a tela em Word (.docx), Excel (.xlsx) e PDF, e encaminhar a colegas.
 * Sem dependência externa e sem internet: os três arquivos são montados aqui.
 * A mesma biblioteca vai embutida na Gestão Physis, no Hub Physis e nos protótipos.
 *
 * Uso:  PhysisExportar.barra({ raiz: function () { return elemento; },
 *                              titulo: function () { return "Propostas"; },
 *                              encaminhar: { pessoas: [...], enviar: function (id, nota, link) {...} } })
 */
(function (g) {
  "use strict";
  var EN = /^en/i.test((g.navigator && g.navigator.language) || "pt");
  var TX = EN ? { baixar: "Download this screen", word: "Word", pdf: "PDF", excel: "Excel", enc: "Forward to colleagues",
      para: "To", nota: "Note (optional)", link: "Link to this screen", enviar: "Send notice", copiar: "Copy link and note",
      copiado: "Copied.", semCopia: "Select the text and copy it.", baixado: function (n) { return n + " saved."; },
      falha: "The download could not be started.", vazio: "There is nothing on this screen to export.",
      semServidor: "Without the Physis server the notice cannot be delivered straight to a colleague. Copy the link and the note and send them.",
      gerado: "Generated on", escolha: "Choose who", cancelado: "The download was cancelled." }
    : { baixar: "Baixar esta tela", word: "Word", pdf: "PDF", excel: "Excel", enc: "Encaminhar a colegas",
      para: "Para", nota: "Recado (opcional)", link: "Link desta tela", enviar: "Enviar aviso", copiar: "Copiar link e recado",
      copiado: "Copiado.", semCopia: "Selecione o texto e copie.", baixado: function (n) { return n + " baixado."; },
      falha: "Não foi possível iniciar o download.", vazio: "Não há nada nesta tela para exportar.",
      semServidor: "Sem o servidor Physis, o aviso não chega direto ao colega. Copie o link e o recado e envie.",
      gerado: "Gerado em", escolha: "Escolha para quem", cancelado: "O download foi cancelado." };

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
        var cel = function (t, negrito) { return '<w:tc><w:tcPr><w:tcW w:w="0" w:type="auto"/></w:tcPr><w:p><w:r>' + (negrito ? "<w:rPr><w:b/></w:rPr>" : "") + '<w:t xml:space="preserve">' + xml(t) + "</w:t></w:r></w:p></w:tc>"; };
        var lin = function (l, cab) { var s = "<w:tr>" + (cab ? "<w:trPr><w:tblHeader/></w:trPr>" : ""); for (var i = 0; i < cols; i++) s += cel(l[i] == null ? "" : l[i], cab); return s + "</w:tr>"; };
        corpo += '<w:tbl><w:tblPr><w:tblStyle w:val="Grade"/><w:tblW w:w="5000" w:type="pct"/><w:tblLook w:firstRow="1"/></w:tblPr>' + (b.tabela.cab.length ? lin(b.tabela.cab, true) : "") + b.tabela.linhas.map(function (l) { return lin(l, false); }).join("") + "</w:tbl>" + par("", null);
      } else corpo += par(b.t, b.lista ? "Lista" : null);
    });
    var doc = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document ' + W + "><w:body>" + corpo + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr></w:body></w:document>';
    var est = function (id, nome, tam, negrito, cor, antes, extra) { return '<w:style w:type="paragraph" w:styleId="' + id + '"><w:name w:val="' + nome + '"/><w:basedOn w:val="Normal"/>' + (extra || "") + '<w:pPr><w:spacing w:before="' + antes + '" w:after="120"/></w:pPr><w:rPr>' + (negrito ? "<w:b/>" : "") + '<w:color w:val="' + cor + '"/><w:sz w:val="' + tam + '"/></w:rPr></w:style>'; };
    var estilos = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles ' + W + '><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="22"/><w:lang w:val="' + (EN ? "en-GB" : "pt-BR") + '"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="300" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>' +
      '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>' +
      est("Title", "Title", 40, true, "33512F", 0) + est("Subtle", "Subtitle", 18, false, "4A4F44", 0) +
      est("Heading1", "heading 1", 30, true, "1C2B21", 360, '<w:next w:val="Normal"/>').replace("</w:pPr>", '<w:keepNext/><w:outlineLvl w:val="0"/></w:pPr>') +
      est("Heading2", "heading 2", 26, true, "1C2B21", 280, '<w:next w:val="Normal"/>').replace("</w:pPr>", '<w:keepNext/><w:outlineLvl w:val="1"/></w:pPr>') +
      est("Heading3", "heading 3", 23, true, "33512F", 200, '<w:next w:val="Normal"/>').replace("</w:pPr>", '<w:keepNext/><w:outlineLvl w:val="2"/></w:pPr>') +
      '<w:style w:type="paragraph" w:styleId="Lista"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="360"/></w:pPr></w:style>' +
      '<w:style w:type="table" w:styleId="Grade"><w:name w:val="Table Grid"/><w:tblPr><w:tblBorders><w:top w:val="single" w:sz="4" w:color="8A9284"/><w:left w:val="single" w:sz="4" w:color="8A9284"/><w:bottom w:val="single" w:sz="4" w:color="8A9284"/><w:right w:val="single" w:sz="4" w:color="8A9284"/><w:insideH w:val="single" w:sz="4" w:color="8A9284"/><w:insideV w:val="single" w:sz="4" w:color="8A9284"/></w:tblBorders><w:tblCellMar><w:left w:w="80" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style></w:styles>';
    return zip([
      { nome: "[Content_Types].xml", dados: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>' },
      { nome: "_rels/.rels", dados: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>' },
      { nome: "docProps/core.xml", dados: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>' + xml(titulo) + "</dc:title><dc:creator>Physis Engineering</dc:creator><dc:language>" + (EN ? "en-GB" : "pt-BR") + "</dc:language></cp:coreProperties>" },
      { nome: "word/_rels/document.xml.rels", dados: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>' },
      { nome: "word/document.xml", dados: doc }, { nome: "word/styles.xml", dados: estilos }]);
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
    linhas.push([{ v: titulo, e: 2 }]); linhas.push([{ v: TX.gerado + " " + agora(), e: 0 }]); linhas.push([]);
    var larg = [];
    blocos.forEach(function (b) {
      if (b.h) { linhas.push([]); linhas.push([{ v: b.t, e: 1 }]); }
      else if (b.tabela) { if (b.tabela.cab.length) linhas.push(b.tabela.cab.map(function (c) { return { v: c, e: 1 }; }));
        b.tabela.linhas.forEach(function (l) { linhas.push(l.map(function (c) { var dt = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(limpo(c));
          if (dt) return { v: Math.round((Date.UTC(+dt[3], +dt[2] - 1, +dt[1]) - Date.UTC(1899, 11, 30)) / 86400000), e: 5, n: true, larg: 12 };
          var n = numero(c); return n === null ? { v: c, e: 0 } : { v: n, e: /R\$/.test(c) ? 3 : /%\s*$/.test(c) ? 4 : 0, n: true, larg: /R\$/.test(c) ? Math.max(14, limpo(c).length + 4) : 10 }; })); }); linhas.push([]); }
      else linhas.push([{ v: b.t, e: 0 }]);
    });
    var dados = linhas.map(function (l, i) {
      return '<row r="' + (i + 1) + '">' + l.map(function (c, j) { var t = String(c.v == null ? "" : c.v); larg[j] = Math.max(larg[j] || 12, c.larg || Math.min(60, (i < 2 || (l.length === 1 && j === 0) ? 12 : t.length) + 2));
        var ref = col(j) + (i + 1); if (t === "") return "";
        return c.n ? '<c r="' + ref + '" s="' + c.e + '"><v>' + c.v + "</v></c>" : '<c r="' + ref + '" s="' + c.e + '" t="inlineStr"><is><t xml:space="preserve">' + xml(t) + "</t></is></c>"; }).join("") + "</row>";
    }).join("");
    var M = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"';
    var folha = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet ' + M + "><cols>" + larg.map(function (w, j) { return '<col min="' + (j + 1) + '" max="' + (j + 1) + '" width="' + (w || 10) + '" customWidth="1"/>'; }).join("") + "</cols><sheetData>" + dados + "</sheetData></worksheet>";
    if (!larg.length) folha = folha.replace("<cols></cols>", "");
    var estilos = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet ' + M + '><numFmts count="1"><numFmt numFmtId="164" formatCode="&quot;R$&quot;\\ #,##0.00"/></numFmts><fonts count="3"><font><sz val="10"/><name val="Arial"/></font><font><b/><sz val="10"/><name val="Arial"/></font><font><b/><sz val="14"/><name val="Arial"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="6"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/><xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/><xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="10" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="14" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>';
    var aba = xml(String(titulo || "Physis").replace(/[\\\/\?\*\[\]:]/g, " ").slice(0, 31)) || "Physis";
    return zip([
      { nome: "[Content_Types].xml", dados: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>' },
      { nome: "_rels/.rels", dados: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>' },
      { nome: "xl/workbook.xml", dados: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook ' + M + ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="' + aba + '" sheetId="1" r:id="rId1"/></sheets></workbook>' },
      { nome: "xl/_rels/workbook.xml.rels", dados: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>' },
      { nome: "xl/worksheets/sheet1.xml", dados: folha }, { nome: "xl/styles.xml", dados: estilos }]);
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
    var LW = 595, LH = 842, M = 48, util = LW - 2 * M, paginas = [], cur = [], y = LH - M;
    var nova = function () { if (cur.length) paginas.push(cur); cur = []; y = LH - M; };
    var texto = function (linha, fonte, tam, x, cor) { cur.push("BT /" + fonte + " " + tam + " Tf " + (cor || "0.11 0.17 0.13") + " rg " + (x || M).toFixed(1) + " " + y.toFixed(1) + " Td " + pdfStr(linha) + " Tj ET"); };
    var escrever = function (t, fonte, tam, larg, antes, depois, cor, recuo) {
      var passo = tam * 1.38, max = Math.max(8, Math.floor((util - (recuo || 0)) / (tam * larg))), ls = quebrar(latin(t), max);
      y -= antes; ls.forEach(function (l) { if (y - passo < M) nova(); y -= passo; texto(l, fonte, tam, M + (recuo || 0), cor); }); y -= depois;
    };
    escrever(titulo, "F2", 18, 0.56, 0, 2, "0.2 0.32 0.18");
    escrever(TX.gerado + " " + agora() + " - Physis Engineering", "F1", 9, 0.5, 0, 10, "0.29 0.31 0.27");
    blocos.forEach(function (b) {
      if (b.h) { if (y < M + 70) nova(); escrever(b.t, "F2", b.h <= 2 ? 14 : 12, 0.56, 10, 3); }
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
          for (var k = 0; k < alt; k++) { y -= passo; var x = M; cels.forEach(function (c, j) { if (c[k]) texto(c[k], i === 0 && b.tabela.cab.length ? "F4" : "F3", tam, x); x += (quer[j] + 2) * cw; }); }
          y -= 3; cur.push((i === 0 && b.tabela.cab.length ? "0.8" : "0.3") + " w 0.54 0.57 0.52 RG " + M + " " + y.toFixed(1) + " m " + (LW - M) + " " + y.toFixed(1) + " l S"); y -= 2;
        });
        y -= 8;
      } else escrever((b.lista ? "- " : "") + b.t, "F1", 10.5, 0.5, 0, 4, null, b.lista ? 10 : 0);
    });
    nova();
    var objs = [], add = function (s) { objs.push(s); return objs.length; };
    var fonte = function (n) { return add("<< /Type /Font /Subtype /Type1 /BaseFont /" + n + " /Encoding /WinAnsiEncoding >>"); };
    var f1 = fonte("Helvetica"), f2 = fonte("Helvetica-Bold"), f3 = fonte("Courier"), f4 = fonte("Courier-Bold");
    var pagsId = objs.length + 1 + paginas.length * 2, kids = [];
    paginas.forEach(function (p, i) {
      var rod = "BT /F1 8 Tf 0.29 0.31 0.27 rg " + M + " 28 Td " + pdfStr(latin(titulo).slice(0, 70) + " - " + (i + 1) + "/" + paginas.length) + " Tj ET";
      var conteudo = p.join("\n") + "\n" + rod, c = add("<< /Length " + conteudo.length + " >>\nstream\n" + conteudo + "\nendstream");
      kids.push(add("<< /Type /Page /Parent " + pagsId + " 0 R /MediaBox [0 0 " + LW + " " + LH + "] /Contents " + c + " 0 R /Resources << /Font << /F1 " + f1 + " 0 R /F2 " + f2 + " 0 R /F3 " + f3 + " 0 R /F4 " + f4 + " 0 R >> >> >>"));
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
  var BLOCO = /^(DIV|P|TABLE|UL|OL|SECTION|ARTICLE|FIELDSET|H1|H2|H3|H4|H5|DL|DETAILS|PRE|LABEL|INPUT|SELECT|TEXTAREA|LI|DT|DD|FORM|MAIN|HEADER|FOOTER|ASIDE|NAV|SUMMARY|LEGEND|OUTPUT)$/;
  function some(el) { if (el.hidden || el.getAttribute("aria-hidden") === "true" || /\b(so-leitor|px-exportar|px-fora)\b/.test(el.className || "")) return true; var s = g.getComputedStyle(el); return s.display === "none" || s.visibility === "hidden"; }
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
    var id = "px-exp-" + (++seq), aberto = false, el = document.createElement("section");
    el.className = "px-exportar"; el.setAttribute("aria-label", TX.baixar);
    el.style.cssText = "margin:18px 0 0;padding:12px 14px;border:1px solid #D6DBCF;border-radius:10px;background:transparent;display:flex;flex-direction:column;gap:10px;font:inherit";
    var bt = "font:inherit;font-weight:600;min-height:44px;padding:0 14px;border-radius:8px;border:1px solid currentColor;background:transparent;color:inherit;cursor:pointer";
    var pessoas = op.encaminhar && op.encaminhar.pessoas, semEnc = op.encaminhar === false;   // encaminhar a colegas só existe na gestão interna
    var pinta = function () {
      el.innerHTML = '<div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center"><strong id="' + id + '-t" style="margin-right:4px">' + TX.baixar + '</strong>' +
        ["docx", "pdf", "xlsx"].map(function (f) { return '<button type="button" data-px-f="' + f + '" aria-describedby="' + id + '-t" style="' + bt + '">' + TX[f === "docx" ? "word" : f === "xlsx" ? "excel" : "pdf"] + "</button>"; }).join("") +
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
    el.addEventListener("click", function (ev) {
      var b = ev.target.closest("button"); if (!b) return;
      if (b.dataset.pxF) { var r = gerar(b.dataset.pxF, op.titulo(), op.raiz()); if (!r) return dizer(TX.vazio);
        baixar(r.nome, r.dados, r.mime).then(function () { dizer(TX.baixado(r.nome)); }, function (e) { dizer(e && /cancel|declin|not_granted/i.test(String(e.code || e.message || e)) ? TX.cancelado : TX.falha); }); return; }
      if (b.dataset.pxEnc) { aberto = !aberto; pinta(); var f = el.querySelector(pessoas ? "[data-px-para]" : "[data-px-nota]"); if (aberto && f) f.focus(); else el.querySelector("[data-px-enc]").focus(); return; }
      if (b.dataset.pxEnv) { var nota = el.querySelector("[data-px-nota]").value.trim(), link = el.querySelector("[data-px-link]").value;
        if (pessoas) { var para = el.querySelector("[data-px-para]").value; if (!para) { dizer(TX.escolha + "."); el.querySelector("[data-px-para]").focus(); return; } dizer(op.encaminhar.enviar(para, nota, link, op.titulo()) || ""); return; }
        var txt = op.titulo() + (nota ? "\n" + nota : "") + "\n" + link;
        var falhou = function () { var i = el.querySelector("[data-px-link]"); i.focus(); i.select(); dizer(TX.semCopia); };
        if (g.navigator.clipboard && g.navigator.clipboard.writeText) g.navigator.clipboard.writeText(txt).then(function () { dizer(TX.copiado); }, falhou); else falhou(); }
    });
    return el;
  }

  g.PhysisExportar = { docx: docx, xlsx: xlsx, pdf: pdf, extrair: extrair, gerar: gerar, baixar: baixar, barra: barra, zip: zip, numero: numero };
})(typeof window !== "undefined" ? window : this);
