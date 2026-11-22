"""Gera o roteiro de instalação do Acer (doc 40b, Markdown) em ODT e PDF/A com a identidade da InovaSTEM
(logo vazada v2, paleta do guia, Lora e Josefin Sans), para enviar ao Eric Oliveira.

Uso:  python ferramentas/roteiro_eric_pdf.py <pasta de saída>
Depois: python C:\\physis\\identidade\\gerar_docs\\converter.py <pasta de saída>   (ODT + PDF/A pelo LibreOffice)

O Markdown do doc 40b é a fonte da verdade; este script só muda a aparência. Sem segredos: o roteiro não tem senha nem chave."""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
_SAIDA, _TMP = (sys.argv[1] if len(sys.argv) > 1 else "."), tempfile.mkdtemp(prefix="roteiro-logos-")
sys.argv[1:2] = [_TMP]        # materiais_inovastem grava os SVG do logo na pasta do argv[1]: vão para uma pasta temporária
import materiais_inovastem as mat  # noqa: E402  (logo, cores e assinatura da InovaSTEM no modelo)
sys.argv[1:2] = [_SAIDA]

odf = mat.odf
ROTEIRO = Path.home() / "OneDrive - Physis Engineering" / "Documents" / "Sistema Physis" / "40b_Roteiro_Acer_InovaSTEM_Eric.md"
odf.FAIXA = "Documento interno · roteiro técnico para o Eric Oliveira"

CODIGO = ('<style:style style:name="Codigo" style:family="paragraph"><style:paragraph-properties fo:margin-top="0cm" fo:margin-bottom="0cm" '
          'fo:margin-left="0.3cm" fo:padding="0.06cm" fo:background-color="#F4F1EA"/><style:text-properties style:font-name="Liberation Mono" '
          'fo:font-family="&apos;Liberation Mono&apos;" fo:font-size="8.5pt" fo:color="#1B1F23"/></style:style>')


def limpar(t: str) -> str:
    return t.replace("`", "")


def montar(md: str) -> str:
    linhas = md.splitlines()
    titulo = limpar(linhas[0].lstrip("# ").strip())
    doc = odf.Texto(titulo.split("·", 1)[-1].strip(), "Instalação da InovaSTEM no notebook Acer, com HTTPS, cópia de segurança e teste",
                    "Roteiro 40b · InovaSTEM")
    i, par, lista, numerada = 1, [], [], False

    def fechar():
        nonlocal par, lista
        if par:
            doc.p(limpar(" ".join(par)))
            par = []
        if lista:
            doc.lista([limpar(x) for x in lista], numerada)
            lista = []

    while i < len(linhas):
        l = linhas[i]
        s = l.strip()
        if s.startswith("```"):
            fechar()
            i += 1
            while i < len(linhas) and not linhas[i].strip().startswith("```"):
                doc.partes.append(f'<text:p text:style-name="Codigo">{odf.e(linhas[i]) or " "}</text:p>')
                i += 1
            i += 1
            continue
        if s.startswith("## "):
            fechar(); doc.h1(limpar(s[3:])); i += 1; continue
        if s.startswith("|"):
            fechar()
            tab = []
            while i < len(linhas) and linhas[i].strip().startswith("|"):
                cel = [limpar(c.strip()) for c in linhas[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cel):
                    tab.append(cel)
                i += 1
            n = len(tab[0])
            doc.tabela(tab[0], tab[1:], [17.0 / n] * n if n != 2 else [6.0, 11.0])
            continue
        m = re.match(r"^(\s*)(?:- \[ \] |- |(\d+)\. )(.*)$", l)
        if m:
            if par:
                fechar()
            recuo, num, txt = m.group(1), m.group(2), m.group(3)
            caixa = "☐ " if "- [ ] " in l else ""
            if lista and numerada != bool(num) and not recuo:
                fechar()
            if not lista:
                numerada = bool(num) and not recuo
            lista.append(("— " if recuo else "") + caixa + txt)
            i += 1
            while i < len(linhas) and linhas[i].startswith("      ") and linhas[i].strip() and not re.match(r"^\s*(- |\d+\. )", linhas[i]):
                lista[-1] += " " + linhas[i].strip()
                i += 1
            continue
        if not s:
            fechar(); i += 1; continue
        if lista and l.startswith("  "):
            lista[-1] += " " + s; i += 1; continue
        if lista:
            fechar()
        par.append(s)
        i += 1
    fechar()
    xml = doc.xml().replace("</office:styles>", CODIGO + "</office:styles>", 1)
    # cabeçalho curto (o título longo invadia o logo) e rodapé da InovaSTEM
    xml = re.sub(r"(</draw:frame>)[^<]*(</text:p></style:header>)", r"\1Roteiro 40b · documento interno\2", xml, count=1)
    xml = xml.replace("Physis Engineering · Petrópolis/RJ · [MARCADOR: CNPJ e contato]", "InovaSTEM · uma iniciativa PHYSIS · Petrópolis/RJ")
    return mat.ajustar(xml)


def main():
    saida = Path(sys.argv[1])
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "40b_Roteiro_Acer_InovaSTEM_Eric.fodt").write_text(montar(ROTEIRO.read_text(encoding="utf-8")), encoding="utf-8")
    print("gerado:", saida / "40b_Roteiro_Acer_InovaSTEM_Eric.fodt")


if __name__ == "__main__":
    main()
