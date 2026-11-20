"""Cartaz A4 do "lançamento 0" da InovaSTEM (evento da Rede Taças e Turbinas, 21/11/2026), com QR codes dos grupos.

RASCUNHO para revisão interna: nada é publicado nem enviado. Os QR só são gerados para convites https://chat.whatsapp.com/…
informados pela dona; sem link, o espaço do QR fica marcado [MARCADOR]. O site ainda não tem endereço público (D94: Acer e
DNS até 23/11), então o cartaz não traz QR do site.

Uso:
    python ferramentas/cartaz_lancamento0.py <pasta de saída> [--inovastem URL] [--delas URL]
    python C:\\physis\\identidade\\gerar_docs\\converter.py <pasta de saída>      (ODT + PDF/A)
Precisa de: segno (QR em Python puro) e Pillow (logo), e do modelo de C:\\physis\\identidade\\gerar_docs (não é alterado).
"""
from __future__ import annotations

import argparse
import base64
import io
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
ap = argparse.ArgumentParser()
ap.add_argument("saida", type=Path)
ap.add_argument("--inovastem", default="")
ap.add_argument("--delas", default="")
a = ap.parse_args()
sys.argv = [sys.argv[0], str(a.saida)]           # materiais_inovastem lê a pasta de saída de sys.argv[1]
import materiais_inovastem as mat  # noqa: E402  (configura o modelo: logo do guia, cores, rodapé da InovaSTEM)

odf = mat.odf
CONVITE = re.compile(r"https://chat\.whatsapp\.com/[A-Za-z0-9]{10,40}")


def qr_svg(url: str) -> bytes:
    import segno
    b = io.BytesIO()
    segno.make(url, error="m").save(b, kind="svg", scale=8, border=2, dark="#0B3D2E", light="#FFFFFF", xmldecl=True)
    return b.getvalue()


def bloco_qr(titulo: str, url: str, legenda: str) -> str:
    e = odf.e
    if url and CONVITE.fullmatch(url):
        img = (f'<draw:frame draw:style-name="fr" draw:name="{e(titulo)}" text:anchor-type="as-char" svg:width="5cm" svg:height="5cm">'
               f'<draw:image draw:mime-type="image/svg+xml"><office:binary-data>{base64.b64encode(qr_svg(url)).decode()}'
               f'</office:binary-data></draw:image></draw:frame>')
        alvo = e(url)
    else:
        img = "[MARCADOR: QR do convite do grupo]"
        alvo = "[MARCADOR: link https://chat.whatsapp.com/… do grupo]"
    return (f'<text:p text:style-name="H2">{e(titulo)}</text:p><text:p text:style-name="Corpo">{img}</text:p>'
            f'<text:p text:style-name="Corpo">{e(legenda)}</text:p><text:p text:style-name="Nota">{alvo}</text:p>')


t = odf.Texto("InovaSTEM · lançamento 0", "Rede aberta de troca de informações, parcerias e desafios de modelagem com códigos abertos",
              "Rede Taças e Turbinas · 21/11/2026")
t.p("Modelagem online (GIS, BIM, 3D e simulação), desafios e projetos abertos, fórum com moderação e o hackathon de "
    "cibersegurança em março de 2027. Versão beta; a plataforma abre em 26/11/2026.")
t.h1("Entre nos grupos")
t.partes.append(bloco_qr("InovaSTEM", a.inovastem, "Troca de informações, parcerias e desafios de modelagem."))
t.partes.append(bloco_qr("InovaSTEM Delas", a.delas, "Formação, acolhimento entre pares e mentoria para mulheres (jovens, cis e trans) em STEM."))
t.nota("O grupo de WhatsApp é opcional; o fórum da plataforma é o canal principal. A participação é a partir de 16 anos "
       "(de 16 a 17, com o responsável legal). Ao entrar num grupo, o seu número fica visível para quem está nele.")
(a.saida / "04_InovaSTEM_Cartaz_lancamento0.fodt").write_text(mat.ajustar(t.xml()), encoding="utf-8")
print("gerado: 04_InovaSTEM_Cartaz_lancamento0.fodt", "· QR InovaSTEM:", bool(CONVITE.fullmatch(a.inovastem or "")),
      "· QR Delas:", bool(CONVITE.fullmatch(a.delas or "")))
