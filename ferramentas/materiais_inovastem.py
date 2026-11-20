"""Rascunhos dos materiais para download do site da InovaSTEM (versão de teste v0, PARA APROVAÇÃO da direção).

Gera em ODF plano (FODP/FODT) e o converter.py do modelo de identidade faz ODP/ODT + PDF/A:
  1. Apresentação da rede e da plataforma (slides)
  2. Patrocínio: tabela única (texto)
  3. Ecossistema (texto)
Conteúdo: só os textos já aprovados no site (web/inovastem.html) e nos docs 37, 40 e 41 e no Caderno de Patrocínio v2.
Nada de número novo; o que falta fica [MARCADOR] e o que vem de documento em revisão fica [CONFERIR]. Sem contato pessoal.

Usa o gerador do modelo v0 de C:\\physis\\identidade\\gerar_docs (odf.py) SEM alterá-lo: troca só, neste processo,
o logo (recorte fiel do guia de 19/11/2026, InovaSTEM opção 2), o fundo claro (#FFF7ED da InovaSTEM), o verde-floresta da
Physis Engineering pelo verde profundo do guia e a assinatura do rodapé; rótulos pequenos em Lora, caixa normal
(decisão de 20/11/2026: Josefin só em títulos grandes). Uso:
    python ferramentas/materiais_inovastem.py <pasta de saída>
    python C:\\physis\\identidade\\gerar_docs\\converter.py <pasta de saída>
"""
from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

IDENT = Path(r"C:\physis\identidade")
sys.path.insert(0, str(IDENT / "gerar_docs"))
import odf  # noqa: E402

GUIA = Path(__file__).resolve().parent.parent / "physis-hub" / "web" / "inovastem.html"
SAIDA = Path(sys.argv[1])
SAIDA.mkdir(parents=True, exist_ok=True)
FAIXA = "Rascunho v0 · para aprovação da direção · não publicar"


def logos_do_site() -> tuple[Path, Path]:
    """Os mesmos recortes do guia que o site usa (WebP embutido), regravados em PNG dentro de um SVG para o LibreOffice."""
    import re
    html = GUIA.read_text(encoding="utf-8")
    webp = re.findall(r'src="data:image/webp;base64,([A-Za-z0-9+/=]+)"', html)[:2]
    try:
        from PIL import Image
    except ImportError:
        sys.exit("precisa do Pillow (pip install pillow) para regravar o logo em PNG")
    out = []
    for nome, dado in zip(("clara", "escura"), webp):
        im = Image.open(io.BytesIO(base64.b64decode(dado))).convert("RGB")
        b = io.BytesIO(); im.save(b, "PNG")
        svg = (f'<?xml version="1.0" encoding="UTF-8"?>\n<!-- InovaSTEM {nome}: recorte fiel do guia de identidade (19/11/2026), sem alteração -->\n'
               f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 {im.width} {im.height}" '
               f'width="{im.width}" height="{im.height}"><image width="{im.width}" height="{im.height}" '
               f'xlink:href="data:image/png;base64,{base64.b64encode(b.getvalue()).decode()}"/></svg>')
        p = SAIDA / f"_logo_inovastem_{nome}.svg"
        p.write_text(svg, encoding="utf-8")
        out.append(p)
    return out[0], out[1]


odf.LOGO, odf.LOGO_ESCURA = logos_do_site()
odf.FAIXA = FAIXA
odf.COR.update({"floresta": "#0B3D2E", "creme": "#FFF7ED"})


def ajustar(xml: str) -> str:
    """Assinatura da InovaSTEM e rótulos pequenos em Lora, caixa normal (aparência só destes documentos)."""
    xml = xml.replace("Physis Engineering · [MARCADOR: CNPJ, endereço e contato]",
                      "InovaSTEM · uma iniciativa PHYSIS · [MARCADOR: contato da InovaSTEM]")
    xml = xml.replace("<meta:initial-creator>Physis Engineering</meta:initial-creator>", "<meta:initial-creator>InovaSTEM (Physis Engineering)</meta:initial-creator>")
    for nome in ("Rotulo", "pRot", "pRotE", "TabCab", "Cabec", "pTCab"):
        i = xml.find(f'style:name="{nome}"')
        if i < 0:
            continue
        j = xml.find("</style:style>", i)
        trecho = xml[i:j].replace('style:font-name="Josefin Sans"', 'style:font-name="Lora"').replace(' fo:text-transform="uppercase"', "")
        xml = xml[:i] + trecho + xml[j:]
    return xml


def salvar(nome: str, xml: str):
    (SAIDA / nome).write_text(ajustar(xml), encoding="utf-8")
    print("gerado:", nome)


def gerar():
    # ── 1. Apresentação da rede e da plataforma (slides) ──
    s = odf.Slides("InovaSTEM · Apresentação da rede e da plataforma", "Apresentação da rede e da plataforma")
    s.capa("InovaSTEM", "Rede aberta de troca de informações, parcerias e desafios de modelagem com códigos abertos. Versão beta, lançamento em 26/11/2026.",
           "uma iniciativa PHYSIS")
    s.duas("Missão e visão",
           ["Conectar pessoas, organizações e projetos para trocar informações, formar parcerias e resolver desafios de modelagem com códigos abertos."],
           ["Ser referência na América Latina em troca aberta de conhecimento e desafios de modelagem para a transição justa."],
           "Quem somos", "Missão", "Visão 2031")
    s.duas("Duas redes, um só lugar",
           ["Aberta a todas as pessoas e organizações: troca de informações, parcerias e desafios de modelagem com códigos abertos.",
            "Laboratório vivo de pesquisa, desenvolvimento e inovação: conexão e trocas abertas para o desenvolvimento tecnológico."],
           ["Rede dedicada a mulheres (jovens, cis e trans) que lideram em STEM: formação, acolhimento entre pares, rodas de conversa e mentoria.",
            "Rede de apoio entre pares; não oferece atendimento psicológico nem clínico."],
           "As redes", "InovaSTEM", "InovaSTEM Delas")
    s.topicos("O laboratório vivo online",
              ["**Modelagem online:** GIS e mapas, BIM (IFC) e modelos 3D no navegador.",
               "**Simulação (Fase 1):** calor, estrutura, ventilação, terreno, incerteza, biogás e otimização QUBO, com método, hipóteses e limites em cada resultado.",
               "**Desafios e projetos abertos:** desafios reais publicados pela equipe e projetos sugeridos pela comunidade.",
               "**Fórum com moderação:** tudo o que é publicado passa pela equipe antes de aparecer.",
               "**Hackathon de cibersegurança:** março de 2027, online, só em ambiente próprio e isolado (CTF)."],
              "A plataforma", "Simulação Fase 2 e gêmeo digital: em desenvolvimento.")
    s.tabela("Modelagem online", ["Ferramenta", "O que faz", "Situação"],
             [["GIS e mapas", "Desenhar e analisar áreas no mapa, camadas e terreno", "Funciona"],
              ["BIM (IFC)", "Abrir e ler modelos IFC de edificações", "Funciona"],
              ["Simulação (Fase 1)", "Contas leves no navegador, iguais às do servidor", "Funciona"],
              ["Physis 3D", "Abrir, medir, ajustar e fatiar peças de plástico reciclado", "Em desenvolvimento"],
              ["Simulação (Fase 2)", "Resolvedores abertos em servidor, comparados com referência", "Em desenvolvimento"],
              ["Gêmeo digital", "Modelo virtual ligado a dados medidos", "Em desenvolvimento"]],
             [5.5, 13.5, 5.8], "A plataforma", "Resultados de cálculo servem para aprender: não substituem projeto assinado por profissional habilitado.")
    s.topicos("Como participar",
              ["**Cadastro de interesse:** nome, e-mail e o que te interessa. Rápido, sem senha.",
               "**Conta da plataforma:** para escrever no fórum e publicar.",
               "**Idade:** a partir de 16 anos; de 16 a 17 anos, com o responsável legal [CONFERIR com o advogado].",
               "**Sugira um projeto aberto** ou acompanhe os desafios.",
               "**Endereço:** inovastem.physisengineering.com [CONFERIR]"],
              "Participar")
    salvar("01_InovaSTEM_Apresentacao_rede_e_plataforma.fodp", s.xml())

    # ── 2. Patrocínio: tabela única ──
    t = odf.Texto("Patrocínio da InovaSTEM", "Tabela única de cotas", "Patrocínio")
    t.p("A InovaSTEM é uma rede aberta de troca de informações, parcerias e desafios de modelagem com códigos abertos; a InovaSTEM "
        "Delas forma e acolhe mulheres em STEM. A cota Amigo é só para pessoa física; empresas a partir de R$ 1.000.")
    t.h1("Cotas")
    t.tabela(["Cota", "Para quem", "Faixa anual", "Contrapartidas"],
             [["Amigo", "Só pessoa física", "R$ 750", "[MARCADOR: contrapartidas da cota Amigo]"],
              ["Apoiador", "Empresas e organizações", "R$ 1.000 a R$ 4.999", "Nome no site e no relatório anual, certificado de apoio, eventos abertos"],
              ["Parceiro", "Empresas e organizações", "R$ 5.000 a R$ 14.999", "Logo nos materiais, grupo de trabalho, relatório de impacto"],
              ["Patrocinador", "Empresas e organizações", "R$ 15.000 a R$ 29.999", "Desafio real ou trilha associada à marca, fala em evento, relatório dedicado"],
              ["Patrocinador master", "Empresas e organizações", "R$ 30.000 a R$ 50.000", "Convite para o comitê, co-branding, prioridade em desafios e projetos, destaque na mostra anual"]],
             [3.2, 3.6, 3.6, 6.6])
    t.nota("Valores do Caderno de Patrocínio v2, em revisão [CONFERIR].")
    t.h1("Regras")
    t.lista(["Patrocínio não compra decisões nem dá acesso a dados pessoais.",
             "Toda cota de empresa vem com um compromisso de entrevistas ou vagas de estágio para as egressas [CONFERIR].",
             "Quem recebe e presta contas dos recursos: [MARCADOR: entidade, até a definição da organização parceira]."])
    t.h1("Contato")
    t.p("[MARCADOR: contato da InovaSTEM]")
    salvar("02_InovaSTEM_Patrocinio_tabela_unica.fodt", t.xml())

    # ── 3. Ecossistema ──
    t = odf.Texto("Ecossistema", "Onde a InovaSTEM se encaixa", "Ecossistema")
    t.p("A InovaSTEM é uma iniciativa da Physis Engineering, empresa de engenharia de sustentabilidade de Petrópolis (RJ), com "
        "liderança feminina. Cada frente tem uma missão própria.")
    t.tabela(["Frente", "Missão"],
             [["Physis Engineering", "Acelerar a transição justa com engenharia de precisão e dados verificáveis, para que cada ganho de energia, água e carbono possa ser medido, comprovado e compartilhado."],
              ["Casa Physis", "Oferecer hospedagem, alimentação e produtos de baixo impacto que mostram na prática, e com dados, como viver bem na Mata Atlântica e fortalecer a economia local."],
              ["InovaSTEM", "Conectar pessoas, organizações e projetos para trocar informações, formar parcerias e resolver desafios de modelagem com códigos abertos."],
              ["InovaSTEM Delas", "Formar, acolher e fortalecer mulheres em STEM, com redes de apoio entre pares, mentoria e projetos aplicados à sustentabilidade."]],
             [4.2, 12.8])
    t.h1("Dois living labs")
    t.lista(["**Casa Physis:** instalação física em Petrópolis (RJ), sistema conectado, projeto vitrine.",
             "**InovaSTEM:** living lab de pesquisa, desenvolvimento e inovação online: fórum, trocas, desafios, eventos e cursos.",
             "A Physis Engineering mede os resultados com M&V transparente e auditável."])
    salvar("03_InovaSTEM_Ecossistema.fodt", t.xml())


if __name__ == "__main__":
    gerar()
