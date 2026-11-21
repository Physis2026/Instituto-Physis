"""Monta physis-hub/web/inovastem-lab.html: a Modelagem Physis 3D da InovaSTEM, servida em /laboratorio, rodando no
navegador, sem internet (D94; estrutura aprovada pela dona em 20/11/2026, com os acréscimos do mesmo dia).

A Modelagem Physis 3D é a bancada de desenvolvimento da InovaSTEM, aberta a qualquer assunto. O Planejador é outra ferramenta
(relacionada, mas separada; dona, 20/11/2026) e não aparece no site da InovaSTEM.
Oito subabas, nesta ordem (hash da página), que leem e gravam um PROJETO COMUM (JSON "inovastem-projeto/1" no navegador,
com Exportar/Importar arquivo; seções lugar, edificacao, montagem, pecas, resultados, arquivos e passos). Fluxo visível
no topo: Enviar arquivo → Lugar ou Modelos BIM → Montagens → Peças 3D → Simulação → Fila de impressão → Galeria. Todo
caminho termina em "Pedir impressão" (STL ou 3MF gerado aqui vai para a fila; physis_hub/inovastem.py).
  #arquivo      Enviar arquivo: foto → escala de cinza, suavização, limiar automático (Otsu) e manual, ruído e fundo →
                contorno vetorizado (SVG, DXF) → extrusão (STL, 3MF), lado a lado; malhas vão para Peças 3D; PDF e
                STEP/IGES: próxima etapa (sistema/physis-imagem-3d.js)
  #lugar        Lugar (GIS): importa o lugar no contrato physis-geometria-lugar/1 (Mapeamento)
  #edificacao   Modelos BIM (CAD e IFC): IFC com geometria (web-ifc) e vista 3D (three.js) de /vendor/, árvore por tipo
                e pavimento, modelagem direta com ferramentas no estilo do SketchUp e formas paramétricas; DXF 2D;
                saída SVG, DXF, STL, 3MF e IFC4 (sistema/physis-modelagem.js)
  #montagem     Montagens: várias peças (posição, giro, material, cor), colisão por caixas, STL e 3MF; programas mapeados
  #pecas        Peças 3D: a tela telaPhysis3D() do motor sistema/physis-3d.js (sem mudar função nem conta)
  #simulacao    Simulação: um bloco por fenômeno, rodando os exemplos pelo motor window.SIMULACAO (rodarCaso, desenhoCaso)
  #fila         Fila de impressão: rotas /api/inovastem/impressao* (peça da biblioteca ou arquivo do laboratório), com conta
  #galeria      Galeria: peças publicadas (/api/publico/3d/pecas), só licenças abertas
(#3d abre Peças 3D; #escaneamento, que saiu por enquanto, abre Enviar arquivo.) Português e inglês: T.pt e T.en com as
mesmas chaves, trocados ao vivo pela barra de preferências (Delas = "Hers").

A página é um arquivo único, como as outras telas do sistema. Ela leva CÓPIAS IGUAIS de:
  sistema/physis-turbinas.js, sistema/simulacao-exemplos/casos.js, sistema/physis-simulacao.js, sistema/physis-3d.js,
  sistema/physis-imagem-3d.js, sistema/physis-modelagem.js, sistema/physis-3d-premissas.json e sistema/physis-preferencias.js
e o cabeçalho, os logos e os estilos de physis-hub/web/inovastem.html (Guia de Identidade de 19/11/2026). three.js e
web-ifc (vendor/, MIT e MPL-2.0) NÃO vão embutidos: o servidor entrega em /vendor/ (o pacote inovastem leva VENDOR_LAB).
Os motores não mudam (regra 2): só a APARÊNCIA do que eles desenham é trocada para as cores do guia na hora de mostrar
(sem azul; roxo só na Delas). Teste: physis-hub/tests/test_inovastem.py.

Uso (depois de mudar qualquer um dos arquivos acima):
    python ferramentas/montar_lab_inovastem.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SIS = RAIZ / "sistema"
WEB = RAIZ / "physis-hub" / "web"
SAIDA = WEB / "inovastem-lab.html"

# blocos copiados sem mudar nada: (id do <script>, arquivo)
BLOCOS = [("lab-turbinas", SIS / "physis-turbinas.js"), ("lab-casos", SIS / "simulacao-exemplos" / "casos.js"),
          ("lab-simulacao", SIS / "physis-simulacao.js"), ("lab-3d", SIS / "physis-3d.js"),
          ("lab-imagem3d", SIS / "physis-imagem-3d.js"), ("lab-modelagem", SIS / "physis-modelagem.js")]
# bibliotecas grandes de vendor/ que o laboratório carrega do próprio servidor (/vendor/) quando a subaba precisa
VENDOR_LAB = ("three.min.js", "web-ifc-api-iife.js", "web-ifc.wasm")

# troca de cor só na tela (aparência): azuis → sequência creme→verde profundo do guia; vermelho e ocre → laranjas do guia
CORES = {"#DBE7F1": "#F4F1EA", "#B8D0E0": "#D9D3C2", "#7FA9C4": "#8A9284", "#546A7B": "#4A5A47", "#3D6E8F": "#4A5A47",
         "#2C5A6E": "#0B3D2E", "#1C3550": "#1B1F23", "#7A2214": "#C2410C", "#A63A28": "#C2410C", "#A85432": "#C2410C",
         "#C9A227": "#F97316", "#C08A1E": "#C2410C"}

# subabas (dona, 20 e 21/11/2026): "Enviar arquivo" primeiro; "Edificação" virou "Modelos BIM (CAD e IFC)" (a chave interna
# continua "edificacao"); "Montagens" logo depois; "Escaneamento" saiu por enquanto (volta depois; #escaneamento abre Enviar arquivo)
SUBABAS = [("arquivo", "Enviar arquivo"), ("lugar", "Lugar (GIS)"), ("edificacao", "Modelos BIM (CAD e IFC)"), ("montagem", "Montagens"),
           ("pecas", "Peças 3D"), ("simulacao", "Simulação"), ("fila", "Fila de impressão"), ("galeria", "Galeria")]
ESQUEMA_PROJETO = "inovastem-projeto/1"

CASCA_CSS = """/* Modelagem Physis 3D (casca do laboratório): classes que os motores usam (cartao, faixa in/al/at, t2), nas cores do guia */
.faixa.in{background:var(--suave);color:var(--texto)}
.faixa.al{background:var(--al-f);color:var(--al-t)}
.faixa.at{background:var(--at-f);color:var(--at-t)}
#lab button:not(.botao),#lab input[type=file],.lab-projeto input[type=file]{font:700 1rem/1.2 var(--fonte);min-height:44px;padding:6px 14px;border-radius:8px;border:2px solid var(--sec);background:transparent;color:var(--sec);cursor:pointer;max-width:100%}
#lab figure{margin:10px 0;max-width:100%;overflow-x:auto}
#lab svg{max-width:100%;height:auto}
#lab canvas{max-width:100%}
#lab textarea{font-family:ui-monospace,Consolas,monospace;font-size:.9rem}
#lab pre{white-space:pre-wrap;overflow-wrap:anywhere}
#lab code,.lab-projeto code{overflow-wrap:anywhere}
.lab-intro{margin:16px 0 0}
.lab-abas{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0;padding:0}
.lab-abas [role=tab]{display:inline-flex;align-items:center;min-height:44px;padding:6px 14px;border-radius:8px;border:2px solid var(--sec);color:var(--sec);background:transparent;text-decoration:none;font:700 1rem/1.2 var(--fonte)}
.lab-abas [role=tab][aria-selected=true]{background:var(--acao);border-color:var(--acao);color:var(--sobre-acao)}
.lab-projeto{border:1px solid var(--linha);border-left:6px solid var(--semente);border-radius:12px;background:var(--sup);padding:10px 14px;margin:12px 0}
.lab-projeto p{margin:0}
.lab-projeto ul{list-style:none;padding:0;margin:8px 0 0;display:grid;gap:4px 16px;grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}
.lab-projeto label{margin-top:0}
.lab-arq{display:flex;flex-direction:column;gap:4px;max-width:100%}
#lab:focus-visible{outline:3px solid var(--link);outline-offset:4px}
#lab .cartao{margin:14px 0}
#lab .cartao h3{font:700 1.15rem/1.3 var(--fonte)}
dl.lab-ficha{display:grid;grid-template-columns:minmax(0,11em) minmax(0,1fr);gap:6px 14px;margin:8px 0}
dl.lab-ficha dt{font-weight:700}
dl.lab-ficha dd{margin:0}
@media (max-width:560px){dl.lab-ficha{grid-template-columns:minmax(0,1fr)}dl.lab-ficha dd{margin-bottom:6px}}
.lab-indice{list-style:none;display:flex;flex-wrap:wrap;gap:6px;padding:0;margin:10px 0}
.lab-res{margin-top:10px}
.lab-fluxo{list-style:none;padding:0;margin:10px 0 0;display:grid;gap:4px 14px;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));border-top:1px solid var(--linha);padding-top:8px}
.lab-fluxo li{display:flex;flex-wrap:wrap;align-items:center;gap:2px 6px}
.lab-fluxo a{display:inline-flex;align-items:center;min-height:44px;font-weight:700}
.lab-fluxo a[aria-current=step]{text-decoration-thickness:3px;text-decoration-color:var(--semente)}
.lab-fluxo .lab-feito{flex-basis:100%;margin-top:-8px}
#lab h4{font:700 1.02rem/1.3 var(--fonte);margin:0 0 4px}
#lab input[type=file]{width:100%}
#lab summary{padding:9px 0;cursor:pointer}
#lab .rolagem table{overflow-wrap:normal}
#lab .rolagem td .botao{white-space:nowrap}
.lab-fen{scroll-margin-top:12px}
.so-leitor{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.lab-lado{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));align-items:start}
.lab-lado figure{margin:0;border:1px solid var(--linha);border-radius:10px;padding:8px;background:var(--sup);min-width:0}
.lab-lado figcaption{font-weight:700;margin:0 0 6px}
.lab-foto,.lab-cad{display:block;width:100%;height:auto;max-height:340px;object-fit:contain;color:var(--texto)}
.lab-vista-lugar{min-height:240px;width:100%;border:1px solid var(--linha);border-radius:10px;background:var(--sup);overflow:hidden}
canvas.lab-vista{display:block;width:100%;touch-action:none}
canvas.lab-vista:focus-visible{outline:3px solid var(--link);outline-offset:-3px}
.lab-ferr{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
#lab .lab-icone{display:inline-flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;min-width:72px;min-height:56px;padding:6px 8px;font:700 .78rem/1.1 var(--fonte)}
#lab .lab-icone[aria-pressed=true]{background:var(--acao);border-color:var(--acao);color:var(--sobre-acao)}
#lab .lab-icone[disabled]{opacity:.55;cursor:not-allowed}
.lab-modelo{display:grid;gap:12px;grid-template-columns:minmax(0,2fr) minmax(0,1fr);align-items:start;margin-top:8px}
@media (max-width:820px){.lab-modelo{grid-template-columns:minmax(0,1fr)}}
.lab-lateral{min-width:0}
.lab-arvore{max-height:360px;overflow:auto;border:1px solid var(--linha);border-radius:10px;padding:4px 8px;background:var(--sup)}
ul.lista-limpa{list-style:none;padding:0;margin:4px 0}
ul.lista-limpa li{display:flex;gap:4px;align-items:center;flex-wrap:wrap}
#lab .lab-item{flex:1 1 auto;text-align:left;border-width:1px;font-weight:600;min-height:44px}
#lab .lab-item.sel,#lab .lab-item[aria-pressed=true]{background:var(--acao);border-color:var(--acao);color:var(--sobre-acao)}
#lab .lab-mini{min-height:44px;padding:4px 8px;font-size:.85rem}
.lab-pronto{border-left:6px solid var(--semente)}
"""

CASCA_JS = r""""use strict";
/* Casca da Modelagem Physis 3D: subabas em fluxo, projeto comum (inovastem-projeto/1), enviar arquivo (foto → CAD 2D →
   3D), modelos BIM (CAD e IFC) com modelagem direta, montagens, peças 3D, simulação por fenômeno, fila de impressão e
   galeria, em português e inglês (função t com a chave, como o site). Gerada por ferramentas/montar_lab_inovastem.py. Os motores
   (SIMULACAO, telaPhysis3D) não mudam: a casca só chama as funções deles e troca as cores do desenho para as do guia. */
const CORES = __CORES__;
const SUBABAS = __SUBABAS__;
const ANTIGAS = { "3d": "pecas", "escaneamento": "arquivo" };          // endereços antigos (Escaneamento saiu em 21/11/2026)
const ESQ_PROJETO = "__ESQ_PROJETO__", ESQ_LUGAR = "physis-geometria-lugar/1", CHAVE_PROJ = "inovastem-projeto";
const ARQ_MAX = 20 * 1024 * 1024;                           // o mesmo limite dos arquivos do Mapeamento e da fila (20 MB)

/* ════════ textos: português e inglês com as mesmas chaves (teste em tests/test_inovastem.py) ════════ */
const T = {
  pt: {
    pular: "Pular para o conteúdo", endosso_a: "uma iniciativa", endosso_b: "", nav: "Seções do site", nav_delas: "InovaSTEM Delas", nav_desafios: "Desafios e projetos",
    nav_forum: "Fórum", nav_modelagem: "Modelagem Physis 3D", nav_hackathon: "Hackathon", nav_materiais: "Materiais", inscreva: "Inscreva-se",
    sub: "Modelagem Physis 3D · roda no seu navegador", beta: "versão beta", titulo: "Modelagem Physis 3D",
    intro: "O laboratório aberto da InovaSTEM para modelar qualquer coisa: peças mecânicas, edificações, terrenos ou protótipos. Transforme uma ideia, uma foto ou um arquivo em modelo 3D, direto no navegador e com códigos abertos: envie o arquivo, ajuste a geometria, monte as peças, teste numa simulação e mande imprimir. Cada etapa grava no mesmo projeto, em formatos abertos (SVG, DXF, STL, 3MF e IFC), para a rede aprender, melhorar e reaproveitar o que foi feito; o resultado pode ir para a galeria.",
    faixa: "Em desenvolvimento (Fase 1). Pré-dimensionamento para aprender e testar ideias: não aprova projeto, não substitui norma nem ensaio. Os exemplos usam dados fictícios. O que você abre ou envia aqui fica no seu computador; só vai para o servidor da InovaSTEM quando você pede (pedir impressão, enviar peça à Biblioteca).",
    abas_rot: "Subabas da Modelagem Physis 3D", proj_rot: "Projeto comum",
    rodape_realiza: "InovaSTEM · uma iniciativa PHYSIS", rodape_entidade: "Physis Engineering · CNPJ [MARCADOR] · Petrópolis (RJ) · Contato: [MARCADOR]",
    rodape_beta: "Versão beta: termos e aviso de privacidade em revisão jurídica.", termos: "Termos de uso (beta)", privacidade: "Privacidade (beta)", acessibilidade: "Acessibilidade",
    abas: { arquivo: "Enviar arquivo", lugar: "Lugar (GIS)", edificacao: "Modelos BIM (CAD e IFC)", montagem: "Montagens", pecas: "Peças 3D", simulacao: "Simulação", fila: "Fila de impressão", galeria: "Galeria" },
    // barra do projeto e fluxo
    proj_titulo: "Projeto comum", proj_guardado: "guardado neste navegador · atualizado em", vazio: "vazio", arquivos: "Arquivos", ultimo: "último",
    lugar: "Lugar", modelo_bim: "Modelo BIM", pecas: "Peças", montagem: "Montagem", resultados: "Resultados", de: "de", elementos: "elementos", objetos: "objetos", itens: "itens",
    proj_exportar: "Exportar o projeto (.json)", proj_importar: "Importar um projeto (.json)", proj_limpar: "Começar outro projeto", proj_confirmar: "Confirmar: apagar o projeto deste navegador",
    proj_confirmar_msg: "Clique de novo para confirmar: o projeto deste navegador será apagado (exporte antes, se quiser guardar).", proj_novo: "Projeto novo começado.",
    proj_baixado: "Arquivo do projeto baixado.", proj_importado: "Projeto importado:", proj_nao: "Este arquivo não é um projeto", proj_falha_guardar: "Atenção: não deu para guardar neste navegador (espaço cheio ou navegação privada). Exporte o arquivo do projeto para não perder.",
    fluxo_rot: "Fluxo da Modelagem Physis 3D", ainda_nao: "ainda não", ou: "ou",
    fluxo: [["arquivo", "Enviar arquivo", ""], ["lugar", "Lugar ou Modelos BIM", "se for território, edificação ou peça mecânica"], ["montagem", "Montagens", "se tiver várias peças"],
            ["pecas", "Peças 3D", ""], ["simulacao", "Simulação", ""], ["fila", "Fila de impressão", ""], ["galeria", "Galeria", ""]],
    // comuns
    escolha_arquivo: "Escolha um arquivo.", grande: "Arquivo grande demais (máximo 20 MB).", json_invalido: "O arquivo não é um JSON válido.", sem_hub: "Sem ligação com o servidor da InovaSTEM.",
    carregando: "Carregando…", lendo: "Lendo…", baixado: "Arquivo baixado.", tirar: "Tirar", acao: "Ação", nome: "Nome", tamanho: "Tamanho", volume: "Volume", triangulos: "Triângulos",
    malha: "Malha", fechada: "fechada", aberta: "com arestas abertas ou não manifold (confira em Peças 3D)", baixar_svg: "Baixar SVG", baixar_dxf: "Baixar DXF", baixar_stl: "Baixar STL",
    baixar_3mf: "Baixar 3MF", baixar_ifc: "Baixar IFC", pedir_impressao: "Pedir impressão", enviar_pecas: "Enviar para Peças 3D", abrir_pecas: "Abrir em Peças 3D",
    sem_modulos: "Os módulos de imagem, modelagem e do Physis 3D não carregaram.", sem_three: "A vista 3D não carregou (three.js em /vendor/).",
    // 1. enviar arquivo
    ar_t: "Enviar arquivo", ar_passo_t: "O primeiro passo do fluxo",
    ar_intro: "Envie qualquer arquivo, de qualquer assunto. Foto ou imagem (PNG, JPG, WebP) e SVG viram CAD 2D (contorno vetorizado, em SVG e DXF) e modelo 3D (extrusão do contorno, em STL e 3MF), que você ajusta antes de mandar para Peças 3D ou pedir impressão. DXF 2D e IFC abrem em Modelos BIM (CAD e IFC). Malhas STL, OBJ e 3MF vão direto para Peças 3D. O arquivo é lido no seu navegador; o projeto comum guarda só o nome, o tipo e o tamanho.",
    ar_rot: "Arquivo", ar_lida: "Imagem lida: o limiar automático (Otsu) já foi aplicado. Ajuste e confira a foto, o CAD 2D e o 3D lado a lado.",
    ar_svg_lido: "SVG lido: os caminhos vão direto para o CAD 2D; o 3D sai das formas preenchidas.", ar_malha_rec: "Malha recebida: abra em Peças 3D ou peça a impressão.",
    ar_pdf_rec: "PDF recebido: veja abaixo o que fazer.", ar_registrado: "Arquivo registrado no projeto.", ar_nao_leu: "Não deu para ler o arquivo.",
    ar_malha_t: "Malha", ar_malha_txt: "STL, OBJ e 3MF são lidos pelo Physis 3D.", ar_pdf_t: "PDF",
    ar_pdf_txt: "Sem uma biblioteca de fora, o navegador não consegue ler o desenho de dentro de um PDF aqui. Exporte a página como imagem (PNG ou JPG) ou como SVG ou DXF e envie de novo. A leitura direta de PDF fica como próxima etapa [MARCADOR: decidir a leitura de PDF].",
    ar_pdf_reg: "O PDF ficou registrado no projeto (nome, tipo e tamanho).", ar_cad_txt: "DXF e IFC são abertos e modelados na subaba Modelos BIM (CAD e IFC).", ar_abrir_bim: "Abrir em Modelos BIM (CAD e IFC)",
    ar_step_txt: "STEP e IGES precisam de um núcleo de CAD (OpenCascade, pelo FreeCAD) rodando no servidor: é a próxima etapa [MARCADOR]. Por enquanto, exporte do seu CAD em STL, 3MF, DXF ou IFC.",
    ar_outro_txt: "Este tipo de arquivo ficou registrado no projeto, mas ainda não é transformado aqui. Para virar CAD 2D e 3D, envie uma foto ou imagem (PNG, JPG, WebP), um SVG, um DXF ou uma malha (STL, OBJ, 3MF).",
    ar_ajustar: "Ajustar", ar_auto: "Limiar automático (Otsu)", ar_limiar: "Limiar (0 a 255)", ar_limiar_d: "Com o automático ligado, o campo mostra o valor que o Otsu achou.",
    ar_inverter: "Inverter (o claro vira material)", ar_suav: "Suavização (0 a 5)", ar_suav_d: "Tira o granulado da foto antes do limiar e arredonda o contorno.",
    ar_ruido: "Ruído: área mínima (células)", ar_ruido_d: "Manchas e furinhos menores que isto somem.", ar_fundo: "Tirar o fundo que encosta na borda da foto", ar_maior: "Ficar só com a maior peça",
    ar_res: "Resolução (células na maior medida, 10 a 250)", ar_largura: "Escala: largura final (mm)", ar_altura: "Extrusão: altura (mm)", ar_base: "Espessura da base (mm; 0 = sem base)",
    ar_atualizar: "Atualizar a prévia", ar_svg_nota: "SVG: o CAD 2D usa os caminhos do arquivo direto (os ajustes de foto só mudam o 3D).",
    ar_lado: "Foto, CAD 2D e 3D", ar_foto: "Foto", ar_foto_alt: "A imagem enviada", ar_cad: "CAD 2D", ar_3d: "3D (girar: arrastar ou setas; aproximar: roda ou + e −)",
    ar_contornos: "contornos", ar_celulas: "Células de material", ar_de: "de", ar_cada: "cada", ar_otsu: "limiar usado", ar_vista_dica: "Para editar a forma com as ferramentas, use \"Editar em Modelos BIM\".",
    ar_editar_bim: "Editar em Modelos BIM (CAD e IFC)",
    // peças de teste
    tp_t: "Arquivos de teste para impressão", tp_txt: "Gerados aqui mesmo, pelo motor do Physis 3D (sem conta e sem nada copiado de terceiros). Baixe em STL, abra em Peças 3D ou peça a impressão.",
    tp_observar: "O que observar:",
    // 2. lugar
    lg_t: "Lugar (GIS)", lg_o_t: "O que é",
    lg_o: "O lugar é o terreno do projeto e o que está em volta: relevo em grade, edificações e superfícies com a orientação e o sol que recebem. Ele vem do Mapeamento da plataforma ou de arquivo; aqui ele entra no projeto comum para as outras subabas lerem (a Simulação usa o terreno no bloco Terreno e água).",
    lg_i_t: "Levar o lugar para o projeto", lg_i: "O arquivo do lugar segue o contrato physis-geometria-lugar/1 (docs/MAPEAMENTO.md): terreno em grade (x para o leste, y para o norte, cotas Z), caixas das edificações, superfícies com orientação e irradiação e os materiais dos elementos BIM. Só dados: nenhuma conta é feita aqui.",
    lg_arq: "Arquivo do lugar (.json)", lg_nav: "Ler o lugar que o Mapeamento gravou neste navegador",
    lg_nav_d: "O Mapeamento da plataforma grava este contrato no navegador quando você envia o sol nas superfícies para a Solar e o AVAC; se você usou o Mapeamento neste mesmo endereço e navegador, o botão acima lê o lugar.",
    lg_nao_contrato: "Este arquivo não segue o contrato physis-geometria-lugar/1 (esquema, terreno em grade com nx × ny cotas Z, listas de edificações, superfícies e elementos BIM).",
    lg_guardado: "Lugar guardado no projeto.", lg_nenhum: "Nenhum lugar gravado pelo Mapeamento neste navegador.", lg_tirado: "Lugar tirado do projeto.", lg_tirar: "Tirar o lugar do projeto",
    lg_no_proj: "Lugar no projeto", lg_resumo: "Resumo do lugar (só o que está no arquivo)", lg_contrato: "Contrato", lg_origem: "Origem (latitude, longitude)", lg_sem_origem: "não informada no arquivo",
    lg_terreno: "Terreno", lg_sem_terreno: "sem terreno no arquivo", lg_celulas: "células de", lg_cotas: "cotas de", lg_a: "a", lg_edif: "Edificações", lg_sup: "Superfícies (orientação e irradiação)",
    lg_bim: "Elementos BIM com materiais", lg_fonte: "Fonte", lg_gerado: "Gerado em", lg_levado: "Levado ao projeto", lg_nav_origem: "Mapeamento (gravado neste navegador)", lg_arquivo_origem: "arquivo",
    // 3. modelos BIM (CAD e IFC)
    bim_t: "Modelos BIM (CAD e IFC)", bim_o_t: "Abrir, ver e modelar",
    bim_o: "Abra um IFC (edificação ou peça mecânica) e veja a geometria 3D, com a árvore de elementos por tipo e pavimento; ou abra um DXF 2D (linhas e polilinhas fechadas viram contornos que podem ser extrudados). Modele com as ferramentas: selecionar, mover, girar, escalar, empurrar/puxar, linha, retângulo, círculo, medir/cota, desfazer e refazer; acrescente formas paramétricas com medidas editáveis. Tudo roda no navegador (web-ifc e three.js guardados no próprio servidor) e sai em formatos abertos: SVG, DXF, STL, 3MF, IFC e o JSON do projeto.",
    bim_arq: "Arquivo IFC ou DXF", bim_step: "STEP e IGES precisam de OpenCascade (FreeCAD) no servidor: próxima etapa [MARCADOR]. Exporte do seu CAD em IFC, DXF, STL ou 3MF.",
    bim_ifc_lido: "IFC aberto no navegador:", bim_dxf_lido: "DXF lido:", bim_contornos: "contornos fechados", bim_linhas: "linhas abertas", bim_dxf_unid: "Unidade declarada no DXF:", bim_dxf_sem_unid: "O DXF não diz a unidade: tratado como milímetros [CONFERIR].",
    bim_carregando: "Carregando o leitor IFC (web-ifc) e a vista 3D…", bim_erro_ifc: "Não deu para abrir o IFC:", bim_vazio: "Abra um arquivo, desenhe com as ferramentas ou acrescente uma forma paramétrica.",
    bim_ferr: "Ferramentas", bim_ferr_rot: "Ferramentas de modelagem",
    ferr: { selecionar: "Selecionar", mover: "Mover", girar: "Girar", escalar: "Escalar", puxar: "Empurrar/puxar", linha: "Linha", retangulo: "Retângulo", circulo: "Círculo", medir: "Medir/cota", desfazer: "Desfazer", refazer: "Refazer", enquadrar: "Enquadrar tudo" },
    ferr_dica: { selecionar: "Clique num objeto para selecionar; arraste no vazio para girar a vista.", mover: "Arraste o objeto pelo chão (encaixa na grade).", girar: "Arraste para os lados para girar em torno do eixo vertical.",
      escalar: "Arraste para cima ou para baixo para aumentar ou diminuir.", puxar: "Arraste para cima ou para baixo para mudar a altura da forma (extrusão).",
      linha: "Clique ponto a ponto no chão; clique no primeiro ponto para fechar a forma; Enter ou clique duplo termina a linha aberta; Esc cancela.",
      retangulo: "Clique em dois cantos opostos.", circulo: "Clique no centro e depois num ponto da borda.", medir: "Clique em dois pontos: a cota fica no desenho e vai para o DXF." },
    bim_teclado: "Na vista: setas giram a câmera; Shift + setas aplicam a ferramenta (mover, girar, escalar ou puxar) no selecionado, Alt multiplica o passo por 10; + e − aproximam; 0 enquadra; Delete apaga; Ctrl+Z desfaz; Ctrl+Y refaz.",
    bim_grade: "Grade (mm)", bim_altura_nova: "Altura das formas novas (mm)", bim_vista_rot: "Vista 3D do modelo",
    bim_arvore: "Elementos", bim_arvore_rot: "Árvore de elementos por tipo e pavimento", bim_sem_pav: "Sem pavimento", bim_desenho: "Desenho e formas", bim_selecionado: "Selecionado",
    bim_nada_sel: "Nada selecionado: escolha na árvore ou clique na vista.", bim_x: "X (mm)", bim_y: "Y (mm)", bim_z: "Z (mm)", bim_rx: "Giro X (°)", bim_ry: "Giro Y (°)", bim_rz: "Giro Z (°)",
    bim_esc: "Escala", bim_altura: "Altura da extrusão (mm)", bim_cor: "Cor", bim_aplicar: "Aplicar as medidas", bim_apagar: "Apagar o selecionado", bim_duplicar: "Duplicar",
    bim_mostrar: "Mostrar", bim_esconder: "Esconder", bim_medida: "Medida",
    bim_prim_t: "Acrescentar forma paramétrica", bim_prim: "Forma", prim: { caixa: "Caixa", cilindro: "Cilindro", chapa: "Chapa com furo", perfil: "Perfil extrudado" },
    bim_prim_w: "Largura (mm)", bim_prim_d: "Profundidade (mm)", bim_prim_h: "Altura ou comprimento (mm)", bim_prim_diam: "Diâmetro (mm)", bim_prim_furo: "Diâmetro do furo (mm)",
    bim_prim_tipo: "Perfil", bim_prim_a: "Aba a (mm)", bim_prim_b: "Aba b (mm)", bim_prim_e: "Espessura (mm)", bim_prim_add: "Acrescentar",
    bim_exp_t: "Exportar e seguir", bim_exp_txt: "STL e 3MF pelo motor do Physis 3D; IFC4 com a geometria do que foi modelado aqui (malha triangulada; as propriedades e a estrutura do IFC original não vão junto); DXF e SVG com os contornos vistos de cima.",
    bim_so_sel: "Só o selecionado", bim_conjunto: "Tudo o que está visível", bim_ifc_nota: "Gravar de volta no IFC original (mudando as colocações dos elementos dentro dele) ainda não é seguro aqui: próxima etapa [MARCADOR].",
    bim_para_montagem: "Levar para Montagens", bim_nada: "Nada para exportar: abra ou desenhe algo primeiro.", bim_guardado: "Modelo guardado no projeto.", bim_resumo: "Resumo do modelo",
    bim_esquema: "Esquema", bim_por_tipo: "Elementos por tipo", bim_pavs: "Pavimentos", bim_leitor: "Leitor",
    bim_sem_geo: "sem geometria de corpo que o leitor gere (por exemplo, só a caixa IfcBoundingBox): aparecem na árvore, sem malha", bim_info: "sem geometria",
    // 4. montagens
    mo_t: "Montagens", mo_o_t: "Juntar peças",
    mo_o: "Junte várias peças numa montagem: posição, giro, material e cor por peça; confira colisões simples (pelas caixas de cada peça) e exporte o conjunto em STL ou em 3MF (uma peça por objeto, com a cor), ou peça a impressão.",
    mo_add_t: "Acrescentar peça", mo_de_proj: "Peça guardada no projeto", mo_de_aberta: "A peça aberta em Peças 3D", mo_de_bim: "O modelo de Modelos BIM (visível)", mo_de_teste: "Peça de teste",
    mo_de_arq: "Arquivo de malha (STL, OBJ ou 3MF)", mo_add: "Acrescentar", mo_sem_geo: "sem a geometria neste navegador (abra de novo em Peças 3D e guarde)", mo_nenhuma: "Nenhuma peça na montagem ainda.",
    mo_lista: "Peças da montagem", mo_material: "Material", mo_cor: "Cor", mo_col_t: "Colisões (pelas caixas)", mo_col_ok: "Nenhuma peça cruza a caixa de outra.", mo_col: "cruzam as caixas",
    mo_col_nota: "Conferência simples, pelas caixas que envolvem cada peça: uma peça curva ou vazada pode aparecer cruzando sem cruzar de verdade.",
    mo_exp_t: "Exportar a montagem", mo_prog_t: "Programas de modelagem mecânica e de simulação mapeados",
    mo_prog_txt: "Programas abertos já mapeados nos documentos do sistema (docs/PHYSIS_3D.md, docs/SIMULACAO.md e o catálogo de software aberto). Nenhum deles roda dentro do navegador: os de servidor são a Fase 2.",
    mo_prog_cols: ["Programa", "O que faz", "Entrada e saída", "Licença", "Situação"], mo_sem_proj_geo: "As peças guardadas no projeto levam a geometria neste navegador (IndexedDB); o arquivo .json do projeto não leva a malha.",
    // 5. peças 3D
    pc_t: "Peças 3D", pc_no_proj: "Peças no projeto",
    pc_txt: "Abra a peça no Physis 3D logo abaixo (STL, OBJ ou 3MF). Depois guarde no projeto comum (as medidas no projeto e a malha neste navegador), leve para a modelagem ou peça a impressão.",
    pc_guardar: "Guardar a peça aberta no projeto", pc_dica: "Abra um arquivo de peça primeiro.", pc_guardada: "Peça guardada no projeto:", pc_tirada: "Peça tirada do projeto.",
    pc_editar: "Editar em Modelos BIM (CAD e IFC)", pc_guardadas: "Peças guardadas no projeto", pc_biblioteca: "Biblioteca", pc_quando: "Guardada em", pc_aberto: "aberto no Physis 3D. Confira as medidas e guarde no projeto.",
    pc_escolha_campo: "Escolha o arquivo no campo do Physis 3D abaixo",
    // 6. simulação
    si_t: "Simulação", si_txt: "Contas leves da Fase 1 que rodam aqui mesmo, sem internet, pelo motor da simulação (o mesmo do servidor, com paridade conferida). Um bloco por fenômeno: o que faz, o que entra, o que sai, os limites de validade e os exemplos daquele fenômeno.",
    si_faixa: "Pré-dimensionamento para aprender e testar ideias, para revisão do engenheiro: não aprova projeto, não substitui norma nem ensaio.", si_ir: "Ir para o bloco do fenômeno",
    si_faz: "O que faz", si_entra: "Entradas", si_sai: "O que sai", si_lim: "Limites de validade", si_exemplo: "Exemplo deste fenômeno", si_teste_conf: "(teste de conferência)",
    si_ficticio: "Exemplo com dados fictícios.", si_conf: "Teste de conferência: o resultado é conhecido (conta analítica).", si_usar_lugar: "Usar o terreno do lugar do projeto",
    si_lugar_troca: "O terreno do lugar troca a grade do exemplo.", si_lugar_mais: "Este exemplo pede mais que a grade (usos do solo ou ponto de visada): use D8, USLE ou declividade.",
    si_sem_terreno: "O projeto ainda não tem terreno (subaba Lugar).", si_entrada_t: "Entrada (JSON): mude e rode de novo", si_entrada: "Entrada do exemplo", si_rodar: "Rodar",
    si_repor: "Voltar ao exemplo", si_guardar: "Guardar no projeto", si_dica: "Rode o exemplo para poder guardar o resultado.", si_metodo_t: "Método, hipóteses e premissas", si_metodo: "Método:",
    si_malha: "Malha ou grade:", si_prem: "Premissas usadas:", si_lim_motor: "Limites de validade (do motor):", si_guardados: "Resultados guardados no projeto", si_nenhum: "Nenhum resultado guardado ainda.",
    si_cols: ["Caso", "Fenômeno", "Origem", "Guardado em", "Ação"], si_ex: "exemplo (dados fictícios)", si_bench: "teste de conferência", si_mudada: "entrada mudada", si_do_lugar: "terreno do lugar",
    si_sem_motor: "O motor da simulação não carregou.", si_json_inv: "Entrada inválida (JSON):", si_sem_terr_proj: "O projeto não tem terreno: importe o lugar na subaba Lugar (GIS).",
    si_pronto: "Pronto:", si_do_lugar_msg: "(terreno do lugar do projeto)", si_nao_rodou: "Não deu para rodar:", si_rode_antes: "Rode o exemplo antes de guardar.", si_res_guardado: "Resultado guardado no projeto:",
    si_reposto: "Entrada do exemplo de volta.", si_sem_ex: "Exemplos não carregados.",
    // 7. fila
    fi_t: "Fila de impressão", fi_como_t: "Como funciona",
    fi_como: ["Com a sua conta, peça a impressão: de uma peça da Biblioteca do Physis 3D (sua ou publicada) ou de um arquivo gerado aqui no laboratório (STL ou 3MF de Enviar arquivo, Modelos BIM, Montagens ou Peças 3D).",
      "A equipe aprova ou recusa (sempre com motivo) e muda a situação: pendente, aprovada, imprimindo, pronta.", "Na oficina, a equipe baixa o arquivo e abre no próprio computador, no CrealityPrint ou no HALOT."],
    fi_nada: "Nada é instalado nem chamado pelo navegador: o arquivo só é baixado; quem abre o CrealityPrint ou o HALOT é a pessoa, no computador dela.",
    fi_impressoras: "Impressoras da oficina: [MARCADOR: modelos exatos das impressoras]. Materiais: os perfis de plástico reciclado do Physis 3D (valores \"conferir\").",
    fi_entre_t: "Entre com a sua conta", fi_entre: "Para pedir impressão, entre com a sua conta ou crie uma em Participar. O arquivo preparado continua aqui enquanto a página estiver aberta.",
    fi_entrar: "Entrar ou criar conta", fi_ja_entrei: "Já entrei: atualizar", fi_arq_t: "Arquivo do laboratório pronto para a fila", fi_arq_de: "vindo de", fi_arq_priv: "O arquivo vai só para o servidor da InovaSTEM, fica privado (só você e a equipe baixam), com limite de 20 MB; o servidor confere se é mesmo uma malha STL ou 3MF.",
    fi_arq_pedir: "Pedir impressão deste arquivo", fi_arq_descartar: "Descartar este arquivo", fi_bib_t: "Pedir impressão de uma peça da Biblioteca", fi_peca: "Peça (id da Biblioteca do Physis 3D)",
    fi_peca_n: "Número da peça na Biblioteca do Physis 3D", fi_sem_pecas: "Nenhuma peça com arquivo na Biblioteca ainda. Use um arquivo do laboratório (acima) ou, em Peças 3D → Biblioteca, crie a peça e envie uma revisão.",
    fi_minha: "(minha)", fi_peca_rot: "Peça", fi_material: "Material", fi_equipe_escolhe: "A equipe escolhe", fi_obs: "Observação (opcional)", fi_meus: "Meus pedidos", fi_meus_cap: "Meus pedidos de impressão",
    fi_cols: ["Pedido", "Peça ou arquivo", "Material", "Situação", "Pedido em"], fi_revisao: "revisão", fi_do_lab: "arquivo do laboratório", fi_nenhum: "Você ainda não pediu impressão.", fi_atualizar: "Atualizar",
    fi_equipe_t: "Fila da equipe", fi_equipe_erro: "Não deu para ler a fila.", fi_pedido: "Pedido", fi_situacao: "situação", fi_obs_rot: "Observação:", fi_baixar: "Baixar o arquivo",
    fi_motivo: "Motivo da recusa (pedido", fi_vazia: "Nenhum pedido na fila.", fi_escolha: "Escolha a peça.", fi_enviado: "enviado: pendente, esperando a equipe.", fi_nao_pediu: "Não deu para pedir agora.",
    fi_nao_mudou: "Não deu para mudar a situação.", fi_enviando: "Enviando o arquivo…", fi_motivo_rot: "motivo",
    estados: { pendente: "Pendente", aprovada: "Aprovada", imprimindo: "Imprimindo", pronta: "Pronta", recusada: "Recusada" },
    passos_rot: { aprovada: "Aprovar", recusada: "Recusar", imprimindo: "Começar a imprimir", pronta: "Marcar como pronta" },
    // 8. galeria
    ga_t: "Galeria", ga_o_t: "Peças da comunidade", ga_o: "Peças publicadas na Biblioteca do Physis 3D, cada uma com a licença escolhida por quem fez e o memorial de desenvolvimento (o que se tentou, o que deu errado e o que mudou).",
    ga_lic: "Só licenças abertas. \"Todos os direitos reservados\" não entra na galeria.", ga_lic_aceitas: "Licenças aceitas:",
    ga_enviar_txt: "Para enviar: com a sua conta, em Peças 3D → Biblioteca, crie a peça, envie o arquivo e publique com uma licença aberta. Tudo passa pela moderação da equipe antes de aparecer.",
    ga_enviar: "Enviar uma peça (Peças 3D)", ga_erro: "Não deu para ler a galeria agora.", ga_nenhuma: "Nenhuma peça publicada ainda.", ga_licenca: "licença", ga_revisoes: "revisões", ga_curada: "curada pela equipe",
    ga_arquivos: "Arquivos", ga_memorial: "Memorial", ga_revisao: "Revisão", ga_baixar: "baixar", ga_resultado: "resultado", ga_nao_abriu: "Não deu para abrir a peça."
  },
  en: {
    pular: "Skip to content", endosso_a: "a", endosso_b: "initiative", nav: "Site sections", nav_delas: "InovaSTEM Hers", nav_desafios: "Challenges and projects",
    nav_forum: "Forum", nav_modelagem: "Physis 3D modelling", nav_hackathon: "Hackathon", nav_materiais: "Materials", inscreva: "Join",
    sub: "Physis 3D modelling · runs in your browser", beta: "beta version", titulo: "Physis 3D modelling",
    intro: "InovaSTEM's open lab for modelling anything: mechanical parts, buildings, terrain or prototypes. Turn an idea, a photo or a file into a 3D model, right in the browser and with open code: upload the file, adjust the geometry, assemble the parts, test it in a simulation and send it to print. Every step is saved in the same project, in open formats (SVG, DXF, STL, 3MF and IFC), so the network can learn from, improve and reuse what was made; the result can go to the gallery.",
    faixa: "In development (Phase 1). Preliminary sizing to learn and test ideas: it does not approve designs and does not replace standards or tests. Examples use fictitious data. What you open or upload here stays on your computer; it only goes to the InovaSTEM server when you ask (print request, sending a part to the Library).",
    abas_rot: "Physis 3D modelling sub-tabs", proj_rot: "Shared project",
    rodape_realiza: "InovaSTEM · a PHYSIS initiative", rodape_entidade: "Physis Engineering · CNPJ [MARCADOR] · Petrópolis (RJ), Brazil · Contact: [MARCADOR]",
    rodape_beta: "Beta version: terms and privacy notice under legal review.", termos: "Terms of use (beta)", privacidade: "Privacy (beta)", acessibilidade: "Accessibility",
    abas: { arquivo: "Upload a file", lugar: "Site (GIS)", edificacao: "BIM models (CAD and IFC)", montagem: "Assemblies", pecas: "3D parts", simulacao: "Simulation", fila: "Print queue", galeria: "Gallery" },
    proj_titulo: "Shared project", proj_guardado: "kept in this browser · updated on", vazio: "empty", arquivos: "Files", ultimo: "latest",
    lugar: "Site", modelo_bim: "BIM model", pecas: "Parts", montagem: "Assembly", resultados: "Results", de: "from", elementos: "elements", objetos: "objects", itens: "items",
    proj_exportar: "Export the project (.json)", proj_importar: "Import a project (.json)", proj_limpar: "Start another project", proj_confirmar: "Confirm: delete the project from this browser",
    proj_confirmar_msg: "Click again to confirm: the project in this browser will be deleted (export it first if you want to keep it).", proj_novo: "New project started.",
    proj_baixado: "Project file downloaded.", proj_importado: "Project imported:", proj_nao: "This file is not a project", proj_falha_guardar: "Warning: it could not be saved in this browser (storage full or private browsing). Export the project file so you do not lose it.",
    fluxo_rot: "Physis 3D modelling flow", ainda_nao: "not yet", ou: "or",
    fluxo: [["arquivo", "Upload a file", ""], ["lugar", "Site or BIM models", "for land, buildings or mechanical parts"], ["montagem", "Assemblies", "if there are several parts"],
            ["pecas", "3D parts", ""], ["simulacao", "Simulation", ""], ["fila", "Print queue", ""], ["galeria", "Gallery", ""]],
    escolha_arquivo: "Choose a file.", grande: "File too large (20 MB maximum).", json_invalido: "The file is not valid JSON.", sem_hub: "No connection to the InovaSTEM server.",
    carregando: "Loading…", lendo: "Reading…", baixado: "File downloaded.", tirar: "Remove", acao: "Action", nome: "Name", tamanho: "Size", volume: "Volume", triangulos: "Triangles",
    malha: "Mesh", fechada: "closed", aberta: "with open or non-manifold edges (check in 3D parts)", baixar_svg: "Download SVG", baixar_dxf: "Download DXF", baixar_stl: "Download STL",
    baixar_3mf: "Download 3MF", baixar_ifc: "Download IFC", pedir_impressao: "Request a print", enviar_pecas: "Send to 3D parts", abrir_pecas: "Open in 3D parts",
    sem_modulos: "The image, modelling and Physis 3D modules did not load.", sem_three: "The 3D view did not load (three.js in /vendor/).",
    ar_t: "Upload a file", ar_passo_t: "The first step of the flow",
    ar_intro: "Upload any file, on any subject. A photo or image (PNG, JPG, WebP) and SVG become 2D CAD (vectorised outline, in SVG and DXF) and a 3D model (extruded outline, in STL and 3MF), which you adjust before sending it to 3D parts or requesting a print. 2D DXF and IFC open in BIM models (CAD and IFC). STL, OBJ and 3MF meshes go straight to 3D parts. The file is read in your browser; the shared project keeps only its name, type and size.",
    ar_rot: "File", ar_lida: "Image read: the automatic threshold (Otsu) has been applied. Adjust it and check the photo, the 2D CAD and the 3D side by side.",
    ar_svg_lido: "SVG read: its paths go straight to the 2D CAD; the 3D comes from the filled shapes.", ar_malha_rec: "Mesh received: open it in 3D parts or request a print.",
    ar_pdf_rec: "PDF received: see below what to do.", ar_registrado: "File recorded in the project.", ar_nao_leu: "The file could not be read.",
    ar_malha_t: "Mesh", ar_malha_txt: "STL, OBJ and 3MF are read by Physis 3D.", ar_pdf_t: "PDF",
    ar_pdf_txt: "Without an external library, the browser cannot read the drawing inside a PDF here. Export the page as an image (PNG or JPG), as SVG or as DXF and upload it again. Reading PDFs directly is a next step [MARCADOR: decide on PDF reading].",
    ar_pdf_reg: "The PDF was recorded in the project (name, type and size).", ar_cad_txt: "DXF and IFC are opened and modelled in the BIM models (CAD and IFC) sub-tab.", ar_abrir_bim: "Open in BIM models (CAD and IFC)",
    ar_step_txt: "STEP and IGES need a CAD kernel (OpenCascade, through FreeCAD) running on the server: that is the next step [MARCADOR]. For now, export from your CAD as STL, 3MF, DXF or IFC.",
    ar_outro_txt: "This type of file was recorded in the project, but it is not transformed here yet. To get 2D CAD and 3D, upload a photo or image (PNG, JPG, WebP), an SVG, a DXF or a mesh (STL, OBJ, 3MF).",
    ar_ajustar: "Adjust", ar_auto: "Automatic threshold (Otsu)", ar_limiar: "Threshold (0 to 255)", ar_limiar_d: "With automatic on, the field shows the value Otsu found.",
    ar_inverter: "Invert (light becomes material)", ar_suav: "Smoothing (0 to 5)", ar_suav_d: "Removes photo grain before the threshold and rounds the outline.",
    ar_ruido: "Noise: minimum area (cells)", ar_ruido_d: "Specks and small holes smaller than this disappear.", ar_fundo: "Remove the background touching the photo edge", ar_maior: "Keep only the largest part",
    ar_res: "Resolution (cells along the largest side, 10 to 250)", ar_largura: "Scale: final width (mm)", ar_altura: "Extrusion: height (mm)", ar_base: "Base thickness (mm; 0 = no base)",
    ar_atualizar: "Update the preview", ar_svg_nota: "SVG: the 2D CAD uses the file's paths directly (the photo settings only change the 3D).",
    ar_lado: "Photo, 2D CAD and 3D", ar_foto: "Photo", ar_foto_alt: "The uploaded image", ar_cad: "2D CAD", ar_3d: "3D (rotate: drag or arrow keys; zoom: wheel or + and −)",
    ar_contornos: "outlines", ar_celulas: "Material cells", ar_de: "of", ar_cada: "each", ar_otsu: "threshold used", ar_vista_dica: "To edit the shape with the tools, use \"Edit in BIM models\".",
    ar_editar_bim: "Edit in BIM models (CAD and IFC)",
    tp_t: "Test print files", tp_txt: "Generated right here by the Physis 3D engine (no account needed and nothing copied from third parties). Download as STL, open in 3D parts or request a print.",
    tp_observar: "What to look for:",
    lg_t: "Site (GIS)", lg_o_t: "What it is",
    lg_o: "The site is the project's land and its surroundings: terrain grid, buildings and surfaces with their orientation and the sun they receive. It comes from the platform's Mapping or from a file; here it joins the shared project for the other sub-tabs to read (Simulation uses the terrain in the Terrain and water block).",
    lg_i_t: "Bring the site into the project", lg_i: "The site file follows the physis-geometria-lugar/1 contract (docs/MAPEAMENTO.md): terrain grid (x east, y north, Z heights), building boxes, surfaces with orientation and irradiation, and the materials of the BIM elements. Data only: no calculation is done here.",
    lg_arq: "Site file (.json)", lg_nav: "Read the site Mapping saved in this browser",
    lg_nav_d: "The platform's Mapping saves this contract in the browser when you send the sun on surfaces to Solar and HVAC; if you used Mapping at this same address and browser, the button above reads the site.",
    lg_nao_contrato: "This file does not follow the physis-geometria-lugar/1 contract (schema, terrain grid with nx × ny Z heights, lists of buildings, surfaces and BIM elements).",
    lg_guardado: "Site saved in the project.", lg_nenhum: "No site saved by Mapping in this browser.", lg_tirado: "Site removed from the project.", lg_tirar: "Remove the site from the project",
    lg_no_proj: "Site in the project", lg_resumo: "Site summary (only what is in the file)", lg_contrato: "Contract", lg_origem: "Origin (latitude, longitude)", lg_sem_origem: "not given in the file",
    lg_terreno: "Terrain", lg_sem_terreno: "no terrain in the file", lg_celulas: "cells of", lg_cotas: "heights from", lg_a: "to", lg_edif: "Buildings", lg_sup: "Surfaces (orientation and irradiation)",
    lg_bim: "BIM elements with materials", lg_fonte: "Source", lg_gerado: "Generated on", lg_levado: "Brought into the project", lg_nav_origem: "Mapping (saved in this browser)", lg_arquivo_origem: "file",
    bim_t: "BIM models (CAD and IFC)", bim_o_t: "Open, view and model",
    bim_o: "Open an IFC (a building or a mechanical part) and see its 3D geometry, with the element tree by type and storey; or open a 2D DXF (closed lines and polylines become outlines you can extrude). Model with the tools: select, move, rotate, scale, push/pull, line, rectangle, circle, measure/dimension, undo and redo; add parametric shapes with editable sizes. Everything runs in the browser (web-ifc and three.js kept on our own server) and comes out in open formats: SVG, DXF, STL, 3MF, IFC and the project JSON.",
    bim_arq: "IFC or DXF file", bim_step: "STEP and IGES need OpenCascade (FreeCAD) on the server: next step [MARCADOR]. Export from your CAD as IFC, DXF, STL or 3MF.",
    bim_ifc_lido: "IFC opened in the browser:", bim_dxf_lido: "DXF read:", bim_contornos: "closed outlines", bim_linhas: "open lines", bim_dxf_unid: "Unit stated in the DXF:", bim_dxf_sem_unid: "The DXF does not state its unit: treated as millimetres [CONFERIR].",
    bim_carregando: "Loading the IFC reader (web-ifc) and the 3D view…", bim_erro_ifc: "The IFC could not be opened:", bim_vazio: "Open a file, draw with the tools or add a parametric shape.",
    bim_ferr: "Tools", bim_ferr_rot: "Modelling tools",
    ferr: { selecionar: "Select", mover: "Move", girar: "Rotate", escalar: "Scale", puxar: "Push/pull", linha: "Line", retangulo: "Rectangle", circulo: "Circle", medir: "Measure/dimension", desfazer: "Undo", refazer: "Redo", enquadrar: "Zoom to fit" },
    ferr_dica: { selecionar: "Click an object to select it; drag on empty space to rotate the view.", mover: "Drag the object along the ground (snaps to the grid).", girar: "Drag sideways to rotate around the vertical axis.",
      escalar: "Drag up or down to make it bigger or smaller.", puxar: "Drag up or down to change the shape's height (extrusion).",
      linha: "Click point by point on the ground; click the first point to close the shape; Enter or a double click ends an open line; Esc cancels.",
      retangulo: "Click two opposite corners.", circulo: "Click the centre and then a point on the edge.", medir: "Click two points: the dimension stays in the drawing and goes into the DXF." },
    bim_teclado: "In the view: arrow keys rotate the camera; Shift + arrows apply the tool (move, rotate, scale or pull) to the selection, Alt multiplies the step by 10; + and − zoom; 0 fits all; Delete removes; Ctrl+Z undoes; Ctrl+Y redoes.",
    bim_grade: "Grid (mm)", bim_altura_nova: "Height of new shapes (mm)", bim_vista_rot: "3D view of the model",
    bim_arvore: "Elements", bim_arvore_rot: "Element tree by type and storey", bim_sem_pav: "No storey", bim_desenho: "Drawing and shapes", bim_selecionado: "Selected",
    bim_nada_sel: "Nothing selected: choose in the tree or click in the view.", bim_x: "X (mm)", bim_y: "Y (mm)", bim_z: "Z (mm)", bim_rx: "Rotation X (°)", bim_ry: "Rotation Y (°)", bim_rz: "Rotation Z (°)",
    bim_esc: "Scale", bim_altura: "Extrusion height (mm)", bim_cor: "Colour", bim_aplicar: "Apply the values", bim_apagar: "Delete the selection", bim_duplicar: "Duplicate",
    bim_mostrar: "Show", bim_esconder: "Hide", bim_medida: "Measurement",
    bim_prim_t: "Add a parametric shape", bim_prim: "Shape", prim: { caixa: "Box", cilindro: "Cylinder", chapa: "Plate with a hole", perfil: "Extruded profile" },
    bim_prim_w: "Width (mm)", bim_prim_d: "Depth (mm)", bim_prim_h: "Height or length (mm)", bim_prim_diam: "Diameter (mm)", bim_prim_furo: "Hole diameter (mm)",
    bim_prim_tipo: "Profile", bim_prim_a: "Flange a (mm)", bim_prim_b: "Flange b (mm)", bim_prim_e: "Thickness (mm)", bim_prim_add: "Add",
    bim_exp_t: "Export and continue", bim_exp_txt: "STL and 3MF through the Physis 3D engine; IFC4 with the geometry of what was modelled here (triangulated mesh; the properties and structure of the original IFC do not go along); DXF and SVG with the outlines seen from above.",
    bim_so_sel: "Selection only", bim_conjunto: "Everything visible", bim_ifc_nota: "Writing back into the original IFC (changing the element placements inside it) is not safe here yet: next step [MARCADOR].",
    bim_para_montagem: "Take to Assemblies", bim_nada: "Nothing to export: open or draw something first.", bim_guardado: "Model saved in the project.", bim_resumo: "Model summary",
    bim_esquema: "Schema", bim_por_tipo: "Elements by type", bim_pavs: "Storeys", bim_leitor: "Reader",
    bim_sem_geo: "without body geometry the reader can generate (for example, only an IfcBoundingBox): they appear in the tree, without a mesh", bim_info: "no geometry",
    mo_t: "Assemblies", mo_o_t: "Put parts together",
    mo_o: "Put several parts together in an assembly: position, rotation, material and colour per part; check simple collisions (by each part's box) and export the whole as STL or 3MF (one object per part, with its colour), or request a print.",
    mo_add_t: "Add a part", mo_de_proj: "Part saved in the project", mo_de_aberta: "The part open in 3D parts", mo_de_bim: "The BIM models model (visible)", mo_de_teste: "Test part",
    mo_de_arq: "Mesh file (STL, OBJ or 3MF)", mo_add: "Add", mo_sem_geo: "without its geometry in this browser (open it again in 3D parts and save)", mo_nenhuma: "No parts in the assembly yet.",
    mo_lista: "Assembly parts", mo_material: "Material", mo_cor: "Colour", mo_col_t: "Collisions (by boxes)", mo_col_ok: "No part crosses another part's box.", mo_col: "boxes cross",
    mo_col_nota: "A simple check, using the box around each part: a curved or hollow part may show as crossing without really crossing.",
    mo_exp_t: "Export the assembly", mo_prog_t: "Mechanical modelling and simulation programs already mapped",
    mo_prog_txt: "Open programs already mapped in the system documents (docs/PHYSIS_3D.md, docs/SIMULACAO.md and the open software catalogue). None of them runs inside the browser: the server ones are Phase 2.",
    mo_prog_cols: ["Program", "What it does", "Input and output", "Licence", "Status"], mo_sem_proj_geo: "Parts saved in the project keep their geometry in this browser (IndexedDB); the project .json file does not carry the mesh.",
    pc_t: "3D parts", pc_no_proj: "Parts in the project",
    pc_txt: "Open the part in Physis 3D just below (STL, OBJ or 3MF). Then save it in the shared project (measurements in the project and the mesh in this browser), take it to modelling or request a print.",
    pc_guardar: "Save the open part in the project", pc_dica: "Open a part file first.", pc_guardada: "Part saved in the project:", pc_tirada: "Part removed from the project.",
    pc_editar: "Edit in BIM models (CAD and IFC)", pc_guardadas: "Parts saved in the project", pc_biblioteca: "Library", pc_quando: "Saved on", pc_aberto: "opened in Physis 3D. Check the measurements and save it in the project.",
    pc_escolha_campo: "Choose the file in the Physis 3D field below",
    si_t: "Simulation", si_txt: "Light Phase 1 calculations that run right here, offline, through the simulation engine (the same as the server's, with checked parity). One block per phenomenon: what it does, inputs, outputs, validity limits and that phenomenon's examples.",
    si_faixa: "Preliminary sizing to learn and test ideas, for an engineer's review: it does not approve designs and does not replace standards or tests.", si_ir: "Go to the phenomenon block",
    si_faz: "What it does", si_entra: "Inputs", si_sai: "Outputs", si_lim: "Validity limits", si_exemplo: "Example for this phenomenon", si_teste_conf: "(verification test)",
    si_ficticio: "Example with fictitious data.", si_conf: "Verification test: the result is known (analytical calculation).", si_usar_lugar: "Use the terrain from the project's site",
    si_lugar_troca: "The site's terrain replaces the example grid.", si_lugar_mais: "This example needs more than the grid (land uses or viewpoint): use D8, USLE or slope.",
    si_sem_terreno: "The project has no terrain yet (Site sub-tab).", si_entrada_t: "Input (JSON): change it and run again", si_entrada: "Example input", si_rodar: "Run",
    si_repor: "Back to the example", si_guardar: "Save in the project", si_dica: "Run the example to be able to save the result.", si_metodo_t: "Method, assumptions and premises", si_metodo: "Method:",
    si_malha: "Mesh or grid:", si_prem: "Premises used:", si_lim_motor: "Validity limits (from the engine):", si_guardados: "Results saved in the project", si_nenhum: "No results saved yet.",
    si_cols: ["Case", "Phenomenon", "Origin", "Saved on", "Action"], si_ex: "example (fictitious data)", si_bench: "verification test", si_mudada: "input changed", si_do_lugar: "site terrain",
    si_sem_motor: "The simulation engine did not load.", si_json_inv: "Invalid input (JSON):", si_sem_terr_proj: "The project has no terrain: import the site in the Site (GIS) sub-tab.",
    si_pronto: "Done:", si_do_lugar_msg: "(terrain from the project's site)", si_nao_rodou: "Could not run:", si_rode_antes: "Run the example before saving.", si_res_guardado: "Result saved in the project:",
    si_reposto: "Example input restored.", si_sem_ex: "Examples not loaded.",
    fi_t: "Print queue", fi_como_t: "How it works",
    fi_como: ["With your account, request a print: of a part from the Physis 3D Library (yours or published) or of a file generated here in the lab (STL or 3MF from Upload a file, BIM models, Assemblies or 3D parts).",
      "The team approves or rejects it (always with a reason) and updates its status: pending, approved, printing, ready.", "In the workshop, the team downloads the file and opens it on its own computer, in CrealityPrint or HALOT."],
    fi_nada: "Nothing is installed or launched by the browser: the file is only downloaded; whoever opens CrealityPrint or HALOT does it on their own computer.",
    fi_impressoras: "Workshop printers: [MARCADOR: exact printer models]. Materials: the Physis 3D recycled-plastic profiles (values to be checked).",
    fi_entre_t: "Sign in with your account", fi_entre: "To request a print, sign in or create an account under Join. The prepared file stays here while the page is open.",
    fi_entrar: "Sign in or create an account", fi_ja_entrei: "I have signed in: refresh", fi_arq_t: "Lab file ready for the queue", fi_arq_de: "from", fi_arq_priv: "The file goes only to the InovaSTEM server and stays private (only you and the team can download it), with a 20 MB limit; the server checks that it really is an STL or 3MF mesh.",
    fi_arq_pedir: "Request a print of this file", fi_arq_descartar: "Discard this file", fi_bib_t: "Request a print of a Library part", fi_peca: "Part (Physis 3D Library id)",
    fi_peca_n: "Part number in the Physis 3D Library", fi_sem_pecas: "No part with a file in the Library yet. Use a lab file (above) or, in 3D parts → Library, create the part and upload a revision.",
    fi_minha: "(mine)", fi_peca_rot: "Part", fi_material: "Material", fi_equipe_escolhe: "The team chooses", fi_obs: "Note (optional)", fi_meus: "My requests", fi_meus_cap: "My print requests",
    fi_cols: ["Request", "Part or file", "Material", "Status", "Requested on"], fi_revisao: "revision", fi_do_lab: "lab file", fi_nenhum: "You have not requested a print yet.", fi_atualizar: "Refresh",
    fi_equipe_t: "Team queue", fi_equipe_erro: "The queue could not be read.", fi_pedido: "Request", fi_situacao: "status", fi_obs_rot: "Note:", fi_baixar: "Download the file",
    fi_motivo: "Reason for rejection (request", fi_vazia: "No requests in the queue.", fi_escolha: "Choose the part.", fi_enviado: "sent: pending, waiting for the team.", fi_nao_pediu: "The request could not be made now.",
    fi_nao_mudou: "The status could not be changed.", fi_enviando: "Uploading the file…", fi_motivo_rot: "reason",
    estados: { pendente: "Pending", aprovada: "Approved", imprimindo: "Printing", pronta: "Ready", recusada: "Rejected" },
    passos_rot: { aprovada: "Approve", recusada: "Reject", imprimindo: "Start printing", pronta: "Mark as ready" },
    ga_t: "Gallery", ga_o_t: "Community parts", ga_o: "Parts published in the Physis 3D Library, each with the licence chosen by its author and the development log (what was tried, what went wrong and what changed).",
    ga_lic: "Open licences only. \"All rights reserved\" does not go into the gallery.", ga_lic_aceitas: "Accepted licences:",
    ga_enviar_txt: "To send one: with your account, in 3D parts → Library, create the part, upload the file and publish it with an open licence. Everything goes through team moderation before it appears.",
    ga_enviar: "Send a part (3D parts)", ga_erro: "The gallery could not be read now.", ga_nenhuma: "No parts published yet.", ga_licenca: "licence", ga_revisoes: "revisions", ga_curada: "curated by the team",
    ga_arquivos: "Files", ga_memorial: "Development log", ga_revisao: "Revision", ga_baixar: "download", ga_resultado: "result", ga_nao_abriu: "The part could not be opened."
  }
};
let lang = "pt";
try { lang = (localStorage.getItem("physis-idioma") === "en") ? "en" : "pt"; } catch (e) {}
const t = k => T[lang][k] != null ? T[lang][k] : T.pt[k];
let abaLab = "arquivo", desenhado = false, proj = null, inst = null;
const lab = { proj: null, limpar: false, lugar: null, ed: null, peca: null, sim: {}, fila: null, filaMsg: null, filaArq: null, gal: null, arq: null, arqMsg: null, testes: null,
  bimMsg: null, moMsg: null, bimArv: null, prim: "caixa" };

const escL = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));
const nf = (v, c) => (typeof v === "number" && isFinite(v)) ? v.toLocaleString(lang === "en" ? "en-GB" : "pt-BR", { minimumFractionDigits: c, maximumFractionDigits: c }) : "—";
const quando = iso => { try { const d = new Date(typeof iso === "number" ? iso * 1000 : iso); return isNaN(d) ? String(iso || "") : d.toLocaleString(lang === "en" ? "en-GB" : "pt-BR"); } catch (e) { return String(iso || ""); } };
const agora = () => new Date().toISOString();
const msgHtml = (id, m) => `<p class="msg${m && m.erro ? " erro" : ""}" role="status" id="${id}">${escL(m ? m.texto : "")}</p>`;
const tabela = (cap, linhas) => `<div class="rolagem"><table><caption>${escL(cap)}</caption><tbody>${linhas.map(l => `<tr><th scope="row">${escL(l[0])}</th><td>${l[1]}</td></tr>`).join("")}</tbody></table></div>`;
const numL = (v, d) => { const x = Number(String(v == null ? "" : v).trim().replace(",", ".")); return isFinite(x) ? x : d; };
const campo = (id, rot, val, extra) => `<div><label for="${id}">${escL(rot)}</label><input id="${id}" type="text" inputmode="decimal" value="${escL(val)}"${extra || ""}></div>`;
function recolorir(h) { return h.replace(/#[0-9A-Fa-f]{6}\b/g, c => CORES[c.toUpperCase()] || c); }

/* ════════ projeto comum (inovastem-projeto/1): no navegador, com try/catch, e em arquivo ════════ */
function projetoVazio() { const a = agora(); return { esquema: ESQ_PROJETO, criado: a, atualizado: a, lugar: null, edificacao: null, montagem: null, pecas: [], resultados: [], arquivos: [], passos: [] }; }
function lugarValido(g) {
  if (!g || typeof g !== "object" || g.esquema !== ESQ_LUGAR) return false;
  const te = g.terreno;
  if (te != null && (typeof te !== "object" || !Number.isInteger(te.nx) || !Number.isInteger(te.ny) || te.nx < 1 || te.ny < 1
      || !(typeof te.cs === "number" && te.cs > 0) || !Array.isArray(te.Z) || te.Z.length !== te.nx * te.ny)) return false;
  return ["edificacoes", "superficies", "elementos_bim"].every(k => g[k] == null || Array.isArray(g[k]));
}
function resumoIfcValido(r) { return !!(r && typeof r === "object" && typeof r.esquema === "string" && r.elementos_por_tipo && typeof r.elementos_por_tipo === "object"); }
function projetoValido(o) {
  if (!o || typeof o !== "object" || o.esquema !== ESQ_PROJETO) return null;
  const p = projetoVazio();
  if (typeof o.criado === "string") p.criado = o.criado.slice(0, 40);
  if (typeof o.atualizado === "string") p.atualizado = o.atualizado.slice(0, 40);
  if (o.lugar && typeof o.lugar === "object" && lugarValido(o.lugar.dados)) p.lugar = o.lugar;
  if (o.edificacao && typeof o.edificacao === "object" && (resumoIfcValido(o.edificacao.resumo) || Array.isArray(o.edificacao.objetos))) p.edificacao = o.edificacao;
  if (o.montagem && typeof o.montagem === "object" && Array.isArray(o.montagem.itens)) p.montagem = o.montagem;
  ["pecas", "resultados"].forEach(k => { p[k] = Array.isArray(o[k]) ? o[k].filter(x => x && typeof x === "object").slice(0, 200) : []; });
  p.arquivos = Array.isArray(o.arquivos) ? o.arquivos.filter(x => x && typeof x === "object").slice(-200) : [];
  p.passos = Array.isArray(o.passos) ? o.passos.filter(x => x && typeof x === "object" && typeof x.passo === "string").slice(-200) : [];
  return p;
}
function lerProjeto() { try { return projetoValido(JSON.parse(localStorage.getItem(CHAVE_PROJ) || "null")) || projetoVazio(); } catch (e) { return projetoVazio(); } }
function gravarProjeto(texto, naBarra) {          // a mensagem vai para a barra só nas ações do projeto (ou se falhar)
  proj.atualizado = agora();
  let ok = false;
  try { localStorage.setItem(CHAVE_PROJ, JSON.stringify(proj)); ok = true; } catch (e) {}
  lab.proj = ok ? (naBarra ? { texto } : null) : { texto: texto + " " + t("proj_falha_guardar"), erro: true };
  return ok;
}
/* malhas das peças guardadas: IndexedDB deste navegador (o JSON do projeto leva só as medidas) */
function bancoMalhas() { return new Promise(ok => { try { const r = indexedDB.open("inovastem-malhas", 1);
  r.onupgradeneeded = () => r.result.createObjectStore("malhas"); r.onsuccess = () => ok(r.result); r.onerror = () => ok(null); } catch (e) { ok(null); } }); }
async function guardarMalha(id, T) { const db = await bancoMalhas(); if (!db) return false;
  return new Promise(ok => { try { const tx = db.transaction("malhas", "readwrite"); tx.objectStore("malhas").put(T.buffer.slice(T.byteOffset, T.byteOffset + T.byteLength), id); tx.oncomplete = () => ok(true); tx.onerror = () => ok(false); } catch (e) { ok(false); } }); }
async function lerMalhaGuardada(id) { const db = await bancoMalhas(); if (!db) return null;
  return new Promise(ok => { try { const q = db.transaction("malhas").objectStore("malhas").get(id); q.onsuccess = () => ok(q.result ? new Float32Array(q.result) : null); q.onerror = () => ok(null); } catch (e) { ok(null); } }); }
function baixar(nome, dados, tipo) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([dados], { type: tipo }));
  a.download = nome; document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}
async function lerArquivoJson(f) {
  if (!f) throw new Error(t("escolha_arquivo"));
  if (f.size > ARQ_MAX) throw new Error(t("grande"));
  try { return JSON.parse(await f.text()); } catch (e) { throw new Error(t("json_invalido")); }
}
const deOnde = x => x ? `${t("de")}: ${escL(x.origem)}${x.arquivo ? " (" + escL(x.arquivo) + ")" : ""}, ${escL(quando(x.importado_em))}` : "";
function barraProjeto() {
  const L = proj.lugar, Ed = proj.edificacao, Mo = proj.montagem, vazio = `<span class="t2">${escL(t("vazio"))}</span>`, fen = {};
  proj.resultados.forEach(r => { const k = r.fenomeno_nome || r.fenomeno || "?"; fen[k] = (fen[k] || 0) + 1; });
  const tl = L && L.dados.terreno;
  return `<p><strong>${escL(t("proj_titulo"))}</strong> <span class="t2 pq">(<code>${ESQ_PROJETO}</code>, ${escL(t("proj_guardado"))} ${escL(quando(proj.atualizado))})</span></p>
    <ul><li><strong>${escL(t("arquivos"))}:</strong> ${proj.arquivos.length ? proj.arquivos.length + " · " + escL(t("ultimo")) + ": " + escL(proj.arquivos[proj.arquivos.length - 1].nome) : vazio}</li>
      <li><strong>${escL(t("lugar"))}:</strong> ${L ? (tl ? escL(tl.nx + " × " + tl.ny) : "—") + " · " + deOnde(L) : vazio}</li>
      <li><strong>${escL(t("modelo_bim"))}:</strong> ${Ed ? escL(((Ed.resumo && Ed.resumo.elementos) || (Ed.objetos || []).length || 0) + " " + t("objetos") + (Ed.resumo ? " · " + Ed.resumo.esquema : "")) + " · " + deOnde(Ed) : vazio}</li>
      <li><strong>${escL(t("montagem"))}:</strong> ${Mo && Mo.itens.length ? escL(Mo.itens.length + " " + t("itens")) : vazio}</li>
      <li><strong>${escL(t("pecas"))}:</strong> ${proj.pecas.length ? proj.pecas.length : vazio}</li>
      <li><strong>${escL(t("resultados"))}:</strong> ${proj.resultados.length ? proj.resultados.length + " (" + Object.keys(fen).map(k => escL(k) + " " + fen[k]).join(", ") + ")" : vazio}</li></ul>
    <div class="acoes"><button class="botao sec" type="button" id="proj-exportar" data-lab="proj-exportar">${escL(t("proj_exportar"))}</button>
      <span class="lab-arq"><label for="proj-importar">${escL(t("proj_importar"))}</label><input id="proj-importar" type="file" accept=".json,application/json" data-lab-arq="projeto"></span>
      <button class="botao sec" type="button" id="proj-limpar" data-lab="proj-limpar">${escL(t(lab.limpar ? "proj_confirmar" : "proj_limpar"))}</button></div>
    ${msgHtml("proj-msg", lab.proj)}${fluxoHtml()}`;
}

/* ════════ servidor da InovaSTEM (mesma origem; nada de fora) ════════ */
async function getJ(url) {
  try { const r = await fetch(url, { credentials: "same-origin", cache: "no-store" }); let j = {}; try { j = await r.json(); } catch (e) {}
    if (j.ok == null) j.ok = r.ok; j._status = r.status; return j; } catch (e) { return { ok: false, erro: t("sem_hub") }; }
}
async function instancia(renovar) { if (!inst || renovar) { const j = await getJ("/api/instancia"); inst = j && j.org !== undefined ? j : null; } return inst; }
async function postJ(url, corpo) {
  const i = await instancia(), op = { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) };
  if (i && i.csrf) op.headers["X-Physis-CSRF"] = i.csrf;
  try { const r = await fetch(url, op); let j = {}; try { j = await r.json(); } catch (e) {} if (j.ok == null) j.ok = r.ok; return j; }
  catch (e) { return { ok: false, erro: t("sem_hub") }; }
}
async function postBytes(url, dados, nome) {
  const i = await instancia(), op = { method: "POST", credentials: "same-origin", body: dados, headers: { "Content-Type": "application/octet-stream", "X-Physis-Nome": encodeURIComponent(nome) } };
  if (i && i.csrf) op.headers["X-Physis-CSRF"] = i.csrf;
  try { const r = await fetch(url, op); let j = {}; try { j = await r.json(); } catch (e) {} if (j.ok == null) j.ok = r.ok; return j; }
  catch (e) { return { ok: false, erro: t("sem_hub") }; }
}
const ehEquipe = i => !!(i && (i.papel === "operador" || i.papel === "administrador"));

/* ════════ fluxo e passos do projeto ════════ */
function registrarPasso(passo, detalhe) { proj.passos.push({ passo, detalhe: String(detalhe || "").slice(0, 200), quando: agora() }); if (proj.passos.length > 200) proj.passos.splice(0, proj.passos.length - 200); }
function ultimoPasso(nomes) { for (let i = proj.passos.length - 1; i >= 0; i--) if (nomes.indexOf(proj.passos[i].passo) >= 0) return proj.passos[i]; return null; }
const NOMES_FLUXO = { arquivo: ["arquivo"], lugar: ["lugar", "edificacao"], montagem: ["montagem"], pecas: ["pecas"], simulacao: ["simulacao"], fila: ["fila"], galeria: ["galeria"] };
function fluxoHtml() {
  return `<nav aria-label="${escL(t("fluxo_rot"))}"><ol class="lab-fluxo">${t("fluxo").map(([k, nome, quandoUsar], i) => {
    const nomes = NOMES_FLUXO[k], u = ultimoPasso(nomes), atual = nomes.indexOf(abaLab) >= 0, cur = a => abaLab === a ? ' aria-current="step"' : "";
    const links = k === "lugar" ? `<a href="#lugar"${cur("lugar")}>${escL(t("abas").lugar)}</a> ${escL(t("ou"))} <a href="#edificacao"${cur("edificacao")}>${escL(t("abas").edificacao)}</a>`
      : `<a href="#${k}"${atual ? ' aria-current="step"' : ""}>${escL(nome)}</a>`;
    return `<li${atual ? ' class="atual"' : ""}><span class="lab-n">${i + 1}.</span> ${links}${quandoUsar ? ` <span class="t2 pq">(${escL(quandoUsar)})</span>` : ""}
      <span class="t2 pq lab-feito">${u ? "✓ " + escL(quando(u.quando)) + (u.detalhe ? ": " + escL(u.detalhe) : "") : escL(t("ainda_nao"))}</span></li>`; }).join("")}</ol></nav>`;
}
function irPara(aba) { abaLab = aba; try { history.pushState(null, "", "#" + aba); } catch (e) {} aoEntrar(); desenhar(); }

/* ════════ caminho único para a fila: qualquer STL/3MF gerado aqui vira "Pedir impressão" ════════ */
function pedirImpressaoDe(nome, dados, origem) {
  const bytes = dados instanceof Uint8Array ? dados : new Uint8Array(dados);
  lab.filaArq = { nome, bytes, origem, tamanho: bytes.length };
  lab.filaMsg = null; registrarPasso("fila", (origem || "") + ": " + nome); gravarProjeto("");
  irPara("fila"); focar("fi-arq-h");
}
const stlDe = (T, nome) => new Uint8Array(PHYSIS3D.escreverSTL(T, nome));

/* ════════ 1. Enviar arquivo: foto → CAD 2D → 3D (sistema/physis-imagem-3d.js + motor PHYSIS3D, sem mudar) ════════ */
const RX_IMG = /\.(png|jpe?g|webp)$/i, RX_MALHA = /\.(stl|obj|3mf)$/i, RX_SVG = /\.svg$/i, RX_PDF = /\.pdf$/i, RX_CAD = /\.(dxf|ifc)$/i, RX_STEP = /\.(step|stp|iges|igs)$/i;
const PAR_PADRAO = { auto: true, limiar: 128, inverter: false, suavizar: 1, areaMin: 20, fundo: true, maior: false, res: 120, largura: 60, altura: 3, base: 0 };   // pontos de partida da tela, ajustáveis
const SVG_FORMAS = ["path", "rect", "circle", "ellipse", "polygon", "polyline", "line"];
const SVG_ATRIBUTOS = ["d", "x", "y", "width", "height", "rx", "ry", "cx", "cy", "r", "points", "x1", "y1", "x2", "y2", "transform", "stroke-width", "fill-rule"];
function tipoDe(f) {
  const n = f.name || "", ty = f.type || "";
  return RX_MALHA.test(n) ? "malha" : (RX_SVG.test(n) || ty === "image/svg+xml") ? "svg" : (RX_PDF.test(n) || ty === "application/pdf") ? "pdf"
    : RX_CAD.test(n) ? "cad" : RX_STEP.test(n) ? "step" : (RX_IMG.test(n) || /^image\/(png|jpeg|webp)$/.test(ty)) ? "imagem" : "outro";
}
/* SVG: só as formas geométricas e os atributos de geometria (nada de script, link, estilo ou evento), refeitas aqui */
function svgLimpo(texto) {
  const doc = new DOMParser().parseFromString(texto, "image/svg+xml"), raiz = doc.documentElement;
  if (!raiz || raiz.nodeName.toLowerCase() !== "svg" || doc.getElementsByTagName("parsererror").length) throw new Error("SVG?");
  let vb = (raiz.getAttribute("viewBox") || "").trim().split(/[\s,]+/).map(Number);
  if (vb.length !== 4 || vb.some(v => !isFinite(v)) || !(vb[2] > 0 && vb[3] > 0)) vb = [0, 0, numL(raiz.getAttribute("width"), 0), numL(raiz.getAttribute("height"), 0)];
  if (!(vb[2] > 0 && vb[3] > 0)) throw new Error("SVG: viewBox?");
  const partes = [];
  SVG_FORMAS.forEach(tag => Array.from(raiz.getElementsByTagName(tag)).forEach(el => {
    const at = SVG_ATRIBUTOS.filter(a => el.hasAttribute(a)).map(a => `${a}="${escL(el.getAttribute(a))}"`).join(" ");
    partes.push(`<${tag} ${at}/>`);
  }));
  if (!partes.length) throw new Error("SVG: 0");
  return { vb, formas: partes.join(""), n: partes.length };
}
const svgDe = (s, w, h, cor) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${s.vb.join(" ")}" width="${w}" height="${h}"><g fill="${cor}" stroke="${cor}">${s.formas}</g></svg>`;
function lacosDoSvg(s, largura) {
  const caixa = document.createElement("div");
  caixa.setAttribute("aria-hidden", "true");
  caixa.style.cssText = "position:fixed;left:-20000px;top:0;visibility:hidden;pointer-events:none";
  caixa.innerHTML = svgDe(s, s.vb[2], s.vb[3], "none");
  document.body.appendChild(caixa);
  const lacos = [], esc_ = largura / s.vb[2], alt = s.vb[3];
  try {
    const raiz = caixa.firstChild, inv = raiz.getScreenCTM().inverse();
    raiz.querySelectorAll(SVG_FORMAS.join(",")).forEach(el => {
      if (typeof el.getTotalLength !== "function") return;
      const L = el.getTotalLength(); if (!(L > 0)) return;
      const n = Math.max(8, Math.min(2000, Math.ceil(L / (Math.hypot(s.vb[2], s.vb[3]) / 600)))), passo = L / n, m = inv.multiply(el.getScreenCTM());
      let atual = [], ant = null;
      for (let k = 0; k <= n; k++) {
        const p = el.getPointAtLength(Math.min(L, k * passo)).matrixTransform(m), q = [(p.x - s.vb[0]) * esc_, (alt - (p.y - s.vb[1])) * esc_];
        if (ant && Math.hypot(q[0] - ant[0], q[1] - ant[1]) > 3 * passo * esc_ + 1e-9) { if (atual.length >= 2) lacos.push(atual); atual = []; }
        atual.push(q); ant = q;
      }
      if (atual.length >= 2) lacos.push(atual);
    });
  } finally { caixa.remove(); }
  return lacos;
}
async function imagemDe(f, fonte) {
  if (fonte === "svg") {
    const s = svgLimpo(await f.text()), lado = 1000, w = s.vb[2] >= s.vb[3] ? lado : Math.max(1, Math.round(lado * s.vb[2] / s.vb[3])), h = s.vb[3] > s.vb[2] ? lado : Math.max(1, Math.round(lado * s.vb[3] / s.vb[2]));
    const url = URL.createObjectURL(new Blob([svgDe(s, w, h, "black")], { type: "image/svg+xml" })), im = new Image();
    try { im.src = url; await im.decode(); } finally { setTimeout(() => URL.revokeObjectURL(url), 1000); }
    return { img: im, w, h, svg: s };
  }
  if (typeof createImageBitmap === "function") { const b = await createImageBitmap(f); return { img: b, w: b.width, h: b.height }; }
  const url = URL.createObjectURL(f), im = new Image();
  try { im.src = url; await im.decode(); } finally { setTimeout(() => URL.revokeObjectURL(url), 1000); }
  return { img: im, w: im.naturalWidth, h: im.naturalHeight };
}
function processarArquivo() {
  const a = lab.arq; if (!a || !a.img) return;
  const p = a.par, I = window.PhysisImagem3D;
  a.r = null;
  try {
    if (!I || !window.PHYSIS3D) throw new Error(t("sem_modulos"));
    const asp = a.w / a.h, nx = asp >= 1 ? p.res : Math.max(2, Math.round(p.res * asp)), ny = asp >= 1 ? Math.max(2, Math.round(p.res / asp)) : p.res;
    const cv = document.createElement("canvas"); cv.width = nx; cv.height = ny;
    const cx = cv.getContext("2d"); cx.clearRect(0, 0, nx, ny); cx.drawImage(a.img, 0, 0, nx, ny);
    const pf = I.processarFoto(cx.getImageData(0, 0, nx, ny).data, nx, ny, { limiar: p.auto ? null : p.limiar, inverter: p.inverter, suavizar: p.suavizar, areaMin: p.areaMin, fundo: p.fundo, maior: p.maior });
    if (p.auto) p.limiar = Math.round(pf.limiar);
    const cel = p.largura / nx, tol = 0.5 + 0.25 * p.suavizar;
    const lacos = a.svg ? lacosDoSvg(a.svg, p.largura) : I.contornos(pf.M, nx, ny, cel, tol);
    const T = I.relevo(pf.M, nx, ny, cel, p.altura, p.base);
    a.r = { nx, ny, cel, lacos, T, med: PHYSIS3D.medir(T), larg: nx * cel, alt: ny * cel, celulas: pf.M.reduce((s, v) => s + v, 0), otsu: pf.otsu, M: pf.M };
  } catch (e) { a.r = { erro: String(e && e.message || e) }; }
}
async function receberArquivo(f) {
  if (!f) return { texto: t("escolha_arquivo"), erro: true };
  if (f.size > ARQ_MAX) return { texto: t("grande"), erro: true };
  const fonte = tipoDe(f), base = (f.name || "arquivo").replace(/\.[^.]+$/, "");
  if (lab.arq && lab.arq.url) URL.revokeObjectURL(lab.arq.url);
  lab.arq = { nome: f.name, base, tipo: f.type || "", tamanho: f.size, fonte, arquivo: f, par: Object.assign({}, PAR_PADRAO), r: null };
  proj.arquivos.push({ nome: String(f.name).slice(0, 160), tipo: String(f.type || "").slice(0, 80), tamanho: f.size, fonte, recebido_em: agora() });
  if (proj.arquivos.length > 200) proj.arquivos.splice(0, proj.arquivos.length - 200);
  registrarPasso("arquivo", f.name);
  gravarProjeto(t("ar_registrado"));
  if (fonte === "imagem" || fonte === "svg") {
    try { Object.assign(lab.arq, await imagemDe(f, fonte)); if (fonte === "imagem") lab.arq.url = URL.createObjectURL(f); }
    catch (e) { lab.arq.r = { erro: t("ar_nao_leu") + " " + (e && e.message || "") }; return { texto: t("ar_nao_leu"), erro: true }; }
    processarArquivo();
    return { texto: t(fonte === "svg" ? "ar_svg_lido" : "ar_lida") };
  }
  return { texto: t(fonte === "malha" ? "ar_malha_rec" : fonte === "pdf" ? "ar_pdf_rec" : "ar_registrado") };
}
function lerParametros() {
  const a = lab.arq, v = id => (document.getElementById(id) || {}).value, ch = id => !!(document.getElementById(id) || {}).checked, lim = (x, a_, b) => Math.max(a_, Math.min(b, x));
  const auto = ch("ar-auto"), lmanual = Math.round(numL(v("ar-limiar"), a.par.limiar));
  a.par = { auto, limiar: lim(lmanual, 0, 255), inverter: ch("ar-inverter"), suavizar: lim(Math.round(numL(v("ar-suav"), a.par.suavizar)), 0, 5),
    areaMin: lim(Math.round(numL(v("ar-ruido"), a.par.areaMin)), 0, 100000), fundo: ch("ar-fundo"), maior: ch("ar-maior"),
    res: lim(Math.round(numL(v("ar-res"), a.par.res)), 10, 250), largura: lim(numL(v("ar-largura"), a.par.largura), 1, 1000),
    altura: lim(numL(v("ar-altura"), a.par.altura), 0, 500), base: lim(numL(v("ar-base"), a.par.base), 0, 100) };
}
function previa2d(r) {
  const d = r.lacos.map(l => "M" + l.map(p => (+p[0]).toFixed(3) + " " + (r.alt - p[1]).toFixed(3)).join(" L") + (l.length > 2 ? " Z" : "")).join(" ");
  return `<svg viewBox="0 0 ${r.larg.toFixed(3)} ${r.alt.toFixed(3)}" role="img" aria-label="${escL(t("ar_cad"))}: ${r.lacos.length} ${escL(t("ar_contornos"))}, ${nf(r.larg, 1)} × ${nf(r.alt, 1)} mm" class="lab-cad">
    <path d="${d}" fill="currentColor" fill-opacity="0.25" fill-rule="evenodd" stroke="currentColor" stroke-width="${(r.larg / 250).toFixed(3)}"/></svg>`;
}
function telaArquivo() {
  const a = lab.arq, ck = (id, rot, v) => `<label class="opcao"><input type="checkbox" id="${id}" data-lab-par="1"${v ? " checked" : ""}> ${escL(rot)}</label>`;
  const f = (n, rot, val, dica) => `<div><label for="ar-${n}">${escL(rot)}</label><input id="ar-${n}" type="text" inputmode="decimal" value="${escL(val)}" data-lab-par="1"${dica ? ` aria-describedby="ar-${n}-d"` : ""}>${dica ? `<p class="t2 pq" id="ar-${n}-d">${escL(dica)}</p>` : ""}</div>`;
  let h = `<h2>${escL(t("ar_t"))}</h2>
  <section class="cartao" aria-labelledby="ar-o-h"><h3 id="ar-o-h">${escL(t("ar_passo_t"))}</h3><p>${escL(t("ar_intro"))}</p>
    <label for="ar-arq">${escL(t("ar_rot"))}</label><input id="ar-arq" type="file" data-lab-arq="enviar">
    ${msgHtml("ar-msg", lab.arqMsg)}</section>`;
  if (!a) return h + cartaoTestes();
  if (a.fonte === "malha") return h + `<section class="cartao" aria-labelledby="ar-m-h"><h3 id="ar-m-h">${escL(t("ar_malha_t"))}: ${escL(a.nome)}</h3><p>${escL(t("ar_malha_txt"))}</p>
    <div class="acoes"><button class="botao" type="button" id="ar-abrir-malha" data-lab="arq-malha">${escL(t("abrir_pecas"))}</button>
    <button class="botao sec" type="button" id="ar-imp-malha" data-lab="arq-malha-imp">${escL(t("pedir_impressao"))}</button></div></section>` + cartaoTestes();
  if (a.fonte === "pdf") return h + `<section class="cartao" aria-labelledby="ar-p-h"><h3 id="ar-p-h">${escL(t("ar_pdf_t"))}: ${escL(a.nome)}</h3>
    <p class="faixa" role="note">${escL(t("ar_pdf_txt"))}</p><p class="t2">${escL(t("ar_pdf_reg"))}</p></section>`;
  if (a.fonte === "cad") return h + `<section class="cartao" aria-labelledby="ar-c-h"><h3 id="ar-c-h">${escL(a.nome)}</h3><p>${escL(t("ar_cad_txt"))}</p>
    <div class="acoes"><button class="botao" type="button" id="ar-abrir-bim" data-lab="arq-bim">${escL(t("ar_abrir_bim"))}</button></div></section>`;
  if (a.fonte === "step") return h + `<section class="cartao" aria-labelledby="ar-s-h"><h3 id="ar-s-h">${escL(a.nome)}</h3><p class="faixa" role="note">${escL(t("ar_step_txt"))}</p></section>`;
  if (a.fonte === "outro") return h + `<section class="cartao" aria-labelledby="ar-x-h"><h3 id="ar-x-h">${escL(a.nome)}</h3><p>${escL(t("ar_outro_txt"))}</p></section>`;
  const p = a.par, r = a.r || {};
  h += `<section class="cartao" aria-labelledby="ar-e-h"><h3 id="ar-e-h">${escL(t("ar_ajustar"))}: ${escL(a.nome)}</h3>
    <form id="ar-form" novalidate>${ck("ar-auto", t("ar_auto"), p.auto)}<div class="campos">
      ${f("limiar", t("ar_limiar"), p.limiar, t("ar_limiar_d"))}${f("suav", t("ar_suav"), p.suavizar, t("ar_suav_d"))}${f("ruido", t("ar_ruido"), p.areaMin, t("ar_ruido_d"))}
      ${f("res", t("ar_res"), p.res, "")}${f("largura", t("ar_largura"), nf(p.largura, 1), "")}${f("altura", t("ar_altura"), nf(p.altura, 1), "")}${f("base", t("ar_base"), nf(p.base, 1), "")}</div>
      ${ck("ar-inverter", t("ar_inverter"), p.inverter)}${ck("ar-fundo", t("ar_fundo"), p.fundo)}${ck("ar-maior", t("ar_maior"), p.maior)}
      <div class="acoes"><button class="botao sec" type="submit" id="ar-atualizar">${escL(t("ar_atualizar"))}</button></div></form>
    ${a.svg ? `<p class="t2 pq">${escL(t("ar_svg_nota"))}</p>` : ""}</section>`;
  if (r.erro) return h + `<p class="faixa erro" role="alert">${escL(r.erro)}</p>`;
  if (!r.T) return h;
  const m = r.med;
  h += `<section class="cartao" aria-labelledby="ar-r-h"><h3 id="ar-r-h">${escL(t("ar_lado"))}</h3>
    <div class="lab-lado">
      <figure><figcaption>${escL(t("ar_foto"))}</figcaption>${a.url ? `<img src="${escL(a.url)}" alt="${escL(t("ar_foto_alt"))}: ${escL(a.nome)}" class="lab-foto">` : ""}</figure>
      <figure><figcaption>${escL(t("ar_cad"))} · ${r.lacos.length} ${escL(t("ar_contornos"))}${a.svg ? "" : " · " + escL(t("ar_otsu")) + " " + Math.round(p.limiar)}</figcaption>${previa2d(r)}</figure>
      <figure><figcaption>${escL(t("ar_3d"))}</figcaption><div id="ar-vista" class="lab-vista-lugar"></div></figure></div>
    ${tabela(t("ar_3d"), [[t("tamanho"), m.tamanho.map(v => nf(v, 1)).join(" × ") + " mm"], [t("volume"), nf(m.volume_mm3 / 1000, 2) + " cm³"],
      [t("triangulos"), nf(m.triangulos, 0)], [t("ar_celulas"), nf(r.celulas, 0) + " " + t("ar_de") + " " + nf(r.nx * r.ny, 0) + " (" + r.nx + " × " + r.ny + ", " + nf(r.cel, 3) + " mm " + t("ar_cada") + ")"],
      [t("malha"), escL(t(m.arestas && m.arestas.fechada ? "fechada" : "aberta"))]])}
    <p class="t2">${escL(t("ar_vista_dica"))}</p>
    <div class="acoes"><button class="botao" type="button" id="ar-imp" data-lab="arq-imp">${escL(t("pedir_impressao"))}</button>
      <button class="botao sec" type="button" id="ar-enviar" data-lab="arq-enviar">${escL(t("enviar_pecas"))}</button>
      <button class="botao sec" type="button" id="ar-editar" data-lab="arq-editar">${escL(t("ar_editar_bim"))}</button>
      <button class="botao sec" type="button" id="ar-svg" data-lab="arq-svg">${escL(t("baixar_svg"))}</button><button class="botao sec" type="button" id="ar-dxf" data-lab="arq-dxf">${escL(t("baixar_dxf"))}</button>
      <button class="botao sec" type="button" id="ar-stl" data-lab="arq-stl">${escL(t("baixar_stl"))}</button><button class="botao sec" type="button" id="ar-3mf" data-lab="arq-3mf">${escL(t("baixar_3mf"))}</button></div></section>`;
  return h + cartaoTestes();
}
/* vista 3D pequena do Enviar arquivo (three.js, carregada só quando precisa) */
function posArquivo() {
  const a = lab.arq, lugar = document.getElementById("ar-vista"); if (!a || !a.r || !a.r.T || !lugar) return;
  window.PhysisModelagem.carregar(["three"]).then(() => {
    if (!document.getElementById("ar-vista")) return;
    if (!lab.vistaArq) lab.vistaArq = window.PhysisModelagem.Vista();
    const v = lab.vistaArq; document.getElementById("ar-vista").appendChild(v.cv); v.cv.setAttribute("aria-label", t("ar_3d"));
    if (!v._ligada) { v._ligada = true; let arr = null;
      v.cv.addEventListener("pointerdown", e => { arr = e; v.cv.focus(); }); v.cv.addEventListener("pointerup", () => { arr = null; });
      v.cv.addEventListener("pointermove", e => { if (arr) v.orbitar(e.movementX || 0, e.movementY || 0); });
      v.cv.addEventListener("wheel", e => { e.preventDefault(); v.aproximar(e.deltaY > 0 ? 1.12 : 1 / 1.12); }, { passive: false });
      v.cv.addEventListener("keydown", e => { const d = { ArrowLeft: [-20, 0], ArrowRight: [20, 0], ArrowUp: [0, -20], ArrowDown: [0, 20] }[e.key];
        if (d) { e.preventDefault(); v.orbitar(d[0], d[1]); } else if (e.key === "+" || e.key === "=") v.aproximar(0.85); else if (e.key === "-") v.aproximar(1 / 0.85); }); }
    v.tamanho(); v.limparMalhas(new Set(["arq"])); v.malha("arq", a.r.T, window.PhysisImagem3D.CORES_PECA[1][3], false);
    if (v._T !== a.r.T) { v._T = a.r.T; v.gradeChao(Math.max(a.r.larg, a.r.alt) * 1.5); v.enquadrar(window.PhysisImagem3D.caixaDe(a.r.T)); } else v.desenhar();
  }).catch(() => {});
}
/* entrega um arquivo ao Physis 3D pela própria tela dele (campo de abrir), sem mudar o motor */
function abrirEmPecas(f, rotulo) {
  if (typeof ui !== "undefined") ui.p3dSub = "modelo";
  abaLab = "pecas";
  try { history.pushState(null, "", "#pecas"); } catch (e) {}
  desenhar();
  const x = document.getElementById("p3d-arquivo");
  if (!x || typeof DataTransfer === "undefined") { lab.peca = { texto: t("pc_escolha_campo") + " (" + f.name + ").", erro: true }; desenhar(); return; }
  const dt = new DataTransfer(); dt.items.add(f); x.files = dt.files;
  x.dispatchEvent(new Event("change", { bubbles: true }));
  registrarPasso("pecas", (rotulo || "") + ": " + f.name);
  gravarProjeto("");
  lab.peca = { texto: f.name + " " + t("pc_aberto") };
  focar("tab-pecas");
}
function testesProntos() { if (!lab.testes && window.PhysisImagem3D) lab.testes = PhysisImagem3D.testes(); return lab.testes || []; }
function cartaoTestes() {
  const ts = testesProntos(), tx = (x, k) => lang === "en" && x.en ? x.en[k] : x[k];
  return `<section class="cartao" aria-labelledby="tp-h"><h3 id="tp-h">${escL(t("tp_t"))}</h3><p>${escL(t("tp_txt"))}</p>
    ${ts.map(x => `<div class="item"><h4 id="tp-${x.id}-h">${escL(tx(x, "nome"))}</h4><p>${escL(tx(x, "medidas"))}</p><p class="t2"><strong>${escL(t("tp_observar"))}</strong> ${escL(tx(x, "observar"))}</p>
      <div class="acoes"><button class="botao sec" type="button" id="tp-${x.id}-b" data-lab="teste-baixar" data-id="${x.id}" aria-describedby="tp-${x.id}-h">${escL(t("baixar_stl"))}</button>
        <button class="botao sec" type="button" id="tp-${x.id}-a" data-lab="teste-abrir" data-id="${x.id}" aria-describedby="tp-${x.id}-h">${escL(t("abrir_pecas"))}</button>
        <button class="botao sec" type="button" id="tp-${x.id}-i" data-lab="teste-imp" data-id="${x.id}" aria-describedby="tp-${x.id}-h">${escL(t("pedir_impressao"))}</button></div></div>`).join("")}</section>`;
}

/* ════════ 2. Lugar (GIS) ════════ */
function importarLugar(g, origem, arquivo) {
  if (!lugarValido(g)) return { texto: t("lg_nao_contrato"), erro: true };
  proj.lugar = { origem, arquivo: arquivo || "", importado_em: agora(), dados: g };
  registrarPasso("lugar", arquivo || origem);
  gravarProjeto(t("lg_guardado"));
  return { texto: t("lg_guardado") };
}
function tabelaLugar(L) {
  const g = L.dados, te = g.terreno, o = g.origem || {};
  let zmin = null, zmax = null;
  if (te) te.Z.forEach(z => { if (typeof z === "number" && isFinite(z)) { zmin = zmin == null ? z : Math.min(zmin, z); zmax = zmax == null ? z : Math.max(zmax, z); } });
  const linhas = [[t("lg_contrato"), `<code>${escL(g.esquema)}</code>`],
    [t("lg_origem"), typeof o.lat === "number" && typeof o.lon === "number" ? nf(o.lat, 5) + ", " + nf(o.lon, 5) : escL(t("lg_sem_origem"))],
    [t("lg_terreno"), te ? `${te.nx} × ${te.ny} ${escL(t("lg_celulas"))} ${nf(te.cs, 2)} m · ${escL(t("lg_cotas"))} ${nf(zmin, 1)} ${escL(t("lg_a"))} ${nf(zmax, 1)} m` : escL(t("lg_sem_terreno"))],
    [t("lg_edif"), String((g.edificacoes || []).length)], [t("lg_sup"), String((g.superficies || []).length)], [t("lg_bim"), String((g.elementos_bim || []).length)]];
  if (typeof g.fonte === "string") linhas.push([t("lg_fonte"), escL(g.fonte)]);
  if (typeof g.atualizado === "string") linhas.push([t("lg_gerado"), escL(quando(g.atualizado))]);
  linhas.push([t("lg_levado"), deOnde(L)]);
  return tabela(t("lg_resumo"), linhas);
}
function telaLugar() {
  const L = proj.lugar;
  return `<h2>${escL(t("lg_t"))}</h2>
  <section class="cartao" aria-labelledby="lg-o-h"><h3 id="lg-o-h">${escL(t("lg_o_t"))}</h3><p>${escL(t("lg_o"))}</p></section>
  <section class="cartao" aria-labelledby="lg-i-h"><h3 id="lg-i-h">${escL(t("lg_i_t"))}</h3><p>${escL(t("lg_i"))}</p>
    <label for="lg-arq">${escL(t("lg_arq"))}</label><input id="lg-arq" type="file" accept=".json,application/json" data-lab-arq="lugar">
    <div class="acoes"><button class="botao sec" type="button" id="lg-nav" data-lab="lugar-navegador">${escL(t("lg_nav"))}</button></div>
    <p class="t2 pq">${escL(t("lg_nav_d"))}</p>${msgHtml("lg-msg", lab.lugar)}</section>
  ${L ? `<section class="cartao" aria-labelledby="lg-r-h"><h3 id="lg-r-h">${escL(t("lg_no_proj"))}</h3>${tabelaLugar(L)}
    <div class="acoes"><button class="botao sec" type="button" id="lg-tirar" data-lab="lugar-tirar">${escL(t("lg_tirar"))}</button></div></section>` : ""}`;
}

/* ════════ 3. Modelos BIM (CAD e IFC): sistema/physis-modelagem.js (web-ifc e three.js de /vendor/) ════════ */
const ICONES = {   // ícones próprios (SVG embutido, traço na cor do texto)
  selecionar: '<path d="M5 3l14 8-6 1.5L10 19z"/>', mover: '<path d="M12 2v20M2 12h20M12 2l-3 3M12 2l3 3M12 22l-3-3M12 22l3-3M2 12l3-3M2 12l3 3M22 12l-3-3M22 12l-3 3"/>',
  girar: '<path d="M19 12a7 7 0 1 1-2-5"/><path d="M17 3v4h-4"/>', escalar: '<path d="M4 20h10V10H4z"/><path d="M14 10l6-6M15 4h5v5"/>',
  puxar: '<path d="M4 14h16v6H4z"/><path d="M12 12V3M9 6l3-3 3 3"/>', linha: '<path d="M4 20L20 4"/><circle cx="4" cy="20" r="1.5"/><circle cx="20" cy="4" r="1.5"/>',
  retangulo: '<rect x="4" y="6" width="16" height="12"/>', circulo: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="1"/>',
  medir: '<path d="M3 17L17 3l4 4L7 21z"/><path d="M7 13l2 2M10 10l2 2M13 7l2 2"/>', desfazer: '<path d="M9 14L4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
  refazer: '<path d="M15 14l5-5-5-5"/><path d="M20 9H9a5 5 0 0 0 0 10h3"/>', enquadrar: '<path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5"/>' };
const icone = k => `<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONES[k]}</svg>`;
let edBim = null, edMo = null;
function editorBim() {
  if (!edBim) edBim = window.PhysisModelagem.editor({ rotulo: t("bim_vista_rot"), aoMudar: motivo => { if (lab.lote) return; if (["selecionar", "adicionar", "apagar", "desfazer", "refazer", "limpar", "alterar", "mover", "girar", "escalar", "puxar", "esc"].indexOf(motivo) >= 0) { guardarBimNoProjeto(); if (abaLab === "edificacao") desenharSemVista(); } },
    aoMedir: m => { lab.bimMsg = { texto: t("bim_medida") + ": " + nf(m, 3) + " mm" }; } });
  return edBim;
}
function guardarBimNoProjeto() {
  if (!edBim) return;
  const ed = proj.edificacao || { origem: "Modelos BIM", arquivo: "", importado_em: agora() };
  ed.objetos = edBim.json(); proj.edificacao = ed; gravarProjeto("");
}
async function abrirCad(f) {
  if (!f) return { texto: t("escolha_arquivo"), erro: true };
  if (f.size > ARQ_MAX) return { texto: t("grande"), erro: true };
  if (RX_STEP.test(f.name)) return { texto: t("bim_step"), erro: true };
  const E = editorBim(), I = window.PhysisImagem3D;
  if (/\.ifc$/i.test(f.name)) {
    try {
      const { objetos, resumo } = await window.PhysisModelagem.lerIfc(await f.arrayBuffer());
      E.guardar(); lab.lote = true; try { objetos.forEach(o => E.adicionar(o, true)); } finally { lab.lote = false; } E.sel = null; E._enq = false; await anexarVista("bim-vista", E, true);
      proj.edificacao = { origem: "IFC (web-ifc)", arquivo: f.name, importado_em: agora(), resumo, objetos: E.json() };
      registrarPasso("edificacao", f.name); gravarProjeto(t("bim_guardado"));
      return { texto: t("bim_ifc_lido") + " " + f.name + " · " + resumo.elementos + " " + t("elementos") + " · " + resumo.esquema + (resumo.sem_geometria ? " · " + resumo.sem_geometria + " " + t("bim_sem_geo") : ""), erro: !resumo.com_geometria && !!resumo.sem_geometria };
    } catch (e) { return { texto: t("bim_erro_ifc") + " " + (e && e.message || e), erro: true }; }
  }
  if (/\.dxf$/i.test(f.name)) {
    const d = I.lerDxf(await f.text());
    E.guardar(); lab.lote = true;
    try { d.lacos.length && E.adicionar({ nome: f.name.replace(/\.[^.]+$/, ""), tipo: "perfil", lacos: d.lacos, altura: E.alturaNova, origem: "dxf" }, true);
    d.linhas.forEach((l, i) => E.adicionar({ nome: t("bim_linhas") + " " + (i + 1), tipo: "linha", pts: l.map(p => [p[0], p[1], 0]), origem: "dxf" }, true)); } finally { lab.lote = false; }
    E._enq = false; await anexarVista("bim-vista", E, true);
    registrarPasso("edificacao", f.name); guardarBimNoProjeto();
    return { texto: t("bim_dxf_lido") + " " + d.lacos.length + " " + t("bim_contornos") + ", " + d.linhas.length + " " + t("bim_linhas") + ". " + (d.unidade ? t("bim_dxf_unid") + " " + d.unidade : t("bim_dxf_sem_unid")) + (d.avisos.length ? " · " + d.avisos.join("; ") : "") };
  }
  return { texto: t("bim_step"), erro: true };
}
async function anexarVista(idLugar, E, enquadrar) {
  if (!window.THREE) { try { await window.PhysisModelagem.carregar(["three"]); } catch (e) { return false; } }
  const lugar = document.getElementById(idLugar); if (!lugar) return false;
  E.anexar(lugar); if (enquadrar) E.enquadrar(); return true;
}
function barraFerramentas(E, pre, lista) {
  return `<div class="lab-ferr" role="toolbar" aria-label="${escL(t("bim_ferr_rot"))}">${lista.map(k => {
      const ehF = E.ferramentas.indexOf(k) >= 0, ativo = ehF && E.ferramenta === k, des = (k === "desfazer" && !E.hist.length) || (k === "refazer" && !E.futuro.length);
      return `<button type="button" class="lab-icone" id="${pre}-f-${k}" data-lab="${pre}-ferr" data-f="${k}"${ehF ? ` aria-pressed="${ativo}"` : ""}${des ? " disabled" : ""} title="${escL(t("ferr")[k])}">${icone(k)}<span>${escL(t("ferr")[k])}</span></button>`; }).join("")}</div>
    <p class="t2 pq" id="${pre}-dica" role="status">${escL((t("ferr_dica")[E.ferramenta]) || "")}</p>`;
}
function painelSelecionado(E, pre) {
  const o = E.obj(E.sel); if (!o) return `<p class="t2">${escL(t("bim_nada_sel"))}</p>`;
  const cores = window.PhysisImagem3D.CORES_PECA, ehSol = o.tipo === "perfil" || o.tipo === "malha";
  return `<form id="${pre}-sel-form" novalidate><h4>${escL(t("bim_selecionado"))}: ${escL(o.nome)}</h4>
    ${o.tipo === "cota" ? `<p>${escL(t("bim_medida"))}: <strong>${nf(o.medida, 3)} mm</strong></p>` : ""}
    ${ehSol ? `<div class="campos">${campo(pre + "-sx", t("bim_x"), nf(o.pos[0], 2))}${campo(pre + "-sy", t("bim_y"), nf(o.pos[1], 2))}${campo(pre + "-sz", t("bim_z"), nf(o.pos[2], 2))}
      ${campo(pre + "-rx", t("bim_rx"), nf(o.rot[0], 1))}${campo(pre + "-ry", t("bim_ry"), nf(o.rot[1], 1))}${campo(pre + "-rz", t("bim_rz"), nf(o.rot[2], 1))}
      ${campo(pre + "-esc", t("bim_esc"), nf(o.esc, 3))}${o.tipo === "perfil" ? campo(pre + "-alt", t("bim_altura"), nf(o.altura, 2)) : ""}
      <div><label for="${pre}-cor">${escL(t("bim_cor"))}</label><select id="${pre}-cor">${cores.map(c => `<option value="${c[3]}"${c[3] === o.cor ? " selected" : ""}>${escL(lang === "en" ? c[2] : c[1])}</option>`).join("")}</select></div></div>
      <div class="acoes"><button class="botao sec" type="submit" id="${pre}-aplicar">${escL(t("bim_aplicar"))}</button>` : `<div class="acoes">`}
      <button class="botao sec" type="button" id="${pre}-dup" data-lab="${pre}-dup">${escL(t("bim_duplicar"))}</button>
      <button class="botao sec" type="button" id="${pre}-apagar" data-lab="${pre}-apagar">${escL(t("bim_apagar"))}</button></div></form>`;
}
function aplicarSelecionado(E, pre) {
  const o = E.obj(E.sel); if (!o) return; const v = id => (document.getElementById(id) || {}).value;
  const c = { pos: [numL(v(pre + "-sx"), o.pos[0]), numL(v(pre + "-sy"), o.pos[1]), numL(v(pre + "-sz"), o.pos[2])], rot: [numL(v(pre + "-rx"), o.rot[0]), numL(v(pre + "-ry"), o.rot[1]), numL(v(pre + "-rz"), o.rot[2])],
    esc: Math.max(0.001, numL(v(pre + "-esc"), o.esc)), cor: v(pre + "-cor") || o.cor };
  if (o.tipo === "perfil") c.altura = Math.max(0.01, numL(v(pre + "-alt"), o.altura));
  E.alterar(o.id, c);
}
function arvoreBim(E) {
  const grupos = {};
  E.objetos.forEach(o => { const chave = o.origem === "ifc" ? (o.pavimento || t("bim_sem_pav")) + " · " + (o.ifcTipo || "IFC") : t("bim_desenho"); (grupos[chave] = grupos[chave] || []).push(o); });
  const ks = Object.keys(grupos).sort();
  if (!ks.length) return `<p class="t2">${escL(t("bim_vazio"))}</p>`;
  return `<div class="lab-arvore" role="group" aria-label="${escL(t("bim_arvore_rot"))}">${ks.map((k, gi) => `<details${ks.length < 6 || grupos[k].some(o => o.id === E.sel) ? " open" : ""}><summary>${escL(k)} (${grupos[k].length})</summary><ul class="lista-limpa">
    ${grupos[k].slice(0, 400).map(o => `<li><button type="button" class="lab-item${o.id === E.sel ? " sel" : ""}" id="bim-it-${o.id}" data-lab="bim-sel" data-id="${o.id}" aria-pressed="${o.id === E.sel}">${escL(o.nome)}${o.semGeometria ? " (" + escL(t("bim_info")) + ")" : ""}</button>
      <button type="button" class="lab-mini" id="bim-vis-${o.id}" data-lab="bim-vis" data-id="${o.id}" aria-label="${escL(t(o.visivel === false ? "bim_mostrar" : "bim_esconder"))}: ${escL(o.nome)}">${escL(t(o.visivel === false ? "bim_mostrar" : "bim_esconder"))}</button></li>`).join("")}</ul></details>`).join("")}</div>`;
}
function formPrimitiva() {
  const p = lab.prim, c = (id, rot, v) => campo("pr-" + id, rot, v);
  const campos = p === "caixa" ? c("w", t("bim_prim_w"), 40) + c("d", t("bim_prim_d"), 30) + c("h", t("bim_prim_h"), 20)
    : p === "cilindro" ? c("diam", t("bim_prim_diam"), 30) + c("h", t("bim_prim_h"), 20)
    : p === "chapa" ? c("w", t("bim_prim_w"), 60) + c("d", t("bim_prim_d"), 40) + c("h", t("bim_prim_h"), 4) + c("furo", t("bim_prim_furo"), 10)
    : `<div><label for="pr-tipo">${escL(t("bim_prim_tipo"))}</label><select id="pr-tipo"><option>L</option><option>U</option><option>T</option></select></div>` + c("a", t("bim_prim_a"), 30) + c("b", t("bim_prim_b"), 30) + c("e", t("bim_prim_e"), 3) + c("h", t("bim_prim_h"), 100);
  return `<form id="pr-form" novalidate><div><label for="pr-forma">${escL(t("bim_prim"))}</label><select id="pr-forma" data-lab-prim="1">${Object.keys(t("prim")).map(k => `<option value="${k}"${k === p ? " selected" : ""}>${escL(t("prim")[k])}</option>`).join("")}</select></div>
    <div class="campos">${campos}</div><div class="acoes"><button class="botao sec" type="submit" id="pr-add">${escL(t("bim_prim_add"))}</button></div></form>`;
}
function acrescentarPrimitiva() {
  const E = editorBim(), I = window.PhysisImagem3D, v = id => numL((document.getElementById("pr-" + id) || {}).value, NaN), p = lab.prim;
  try {
    let lacos, h = v("h"), nome, forma;
    if (p === "caixa") { lacos = I.PRIM.retangulo(v("w"), v("d")); forma = { tipo: p, w: v("w"), d: v("d"), h }; nome = t("prim").caixa + " " + v("w") + " × " + v("d") + " × " + h; }
    else if (p === "cilindro") { lacos = I.PRIM.circulo(v("diam"), 48); forma = { tipo: p, d: v("diam"), h }; nome = t("prim").cilindro + " Ø" + v("diam") + " × " + h; }
    else if (p === "chapa") { lacos = I.PRIM.chapaComFuro(v("w"), v("d"), v("furo")); forma = { tipo: p, w: v("w"), d: v("d"), furo: v("furo"), h }; nome = t("prim").chapa + " " + v("w") + " × " + v("d") + " × " + h; }
    else { const tp = (document.getElementById("pr-tipo") || {}).value || "L"; lacos = I.PRIM.perfil(tp, v("a"), v("b"), v("e")); forma = { tipo: p, perfil: tp, a: v("a"), b: v("b"), e: v("e"), h }; nome = t("prim").perfil + " " + tp + " " + v("a") + " × " + v("b") + " × " + v("e") + " × " + h; }
    if (![h].concat(Object.values(forma).filter(x => typeof x === "number")).every(x => x > 0)) throw new Error(t("bim_prim_h") + "?");
    E.adicionar({ nome, tipo: "perfil", lacos, altura: h, forma, origem: "parametrica" });
    lab.bimMsg = { texto: nome };
  } catch (e) { lab.bimMsg = { texto: String(e && e.message || e), erro: true }; }
}
function exportarBotoes(pre, imp) {
  return `<div class="acoes"><button class="botao" type="button" id="${pre}-imp" data-lab="${pre}-exp" data-fmt="imp">${escL(t("pedir_impressao"))}</button>
    <button class="botao sec" type="button" id="${pre}-pecas" data-lab="${pre}-exp" data-fmt="pecas">${escL(t("enviar_pecas"))}</button>
    <button class="botao sec" type="button" id="${pre}-stl" data-lab="${pre}-exp" data-fmt="stl">${escL(t("baixar_stl"))}</button>
    <button class="botao sec" type="button" id="${pre}-3mf" data-lab="${pre}-exp" data-fmt="3mf">${escL(t("baixar_3mf"))}</button>
    ${pre === "bim" ? `<button class="botao sec" type="button" id="bim-ifc" data-lab="bim-exp" data-fmt="ifc">${escL(t("baixar_ifc"))}</button>
    <button class="botao sec" type="button" id="bim-dxf" data-lab="bim-exp" data-fmt="dxf">${escL(t("baixar_dxf"))}</button>
    <button class="botao sec" type="button" id="bim-svg" data-lab="bim-exp" data-fmt="svg">${escL(t("baixar_svg"))}</button>
    <button class="botao sec" type="button" id="bim-mo" data-lab="bim-exp" data-fmt="montagem">${escL(t("bim_para_montagem"))}</button>` : ""}</div>${imp || ""}`;
}
function telaBim() {
  const E = window.PhysisModelagem ? editorBim() : null, Ed = proj.edificacao;
  if (!E) return `<h2>${escL(t("bim_t"))}</h2><p class="faixa erro" role="alert">${escL(t("sem_modulos"))}</p>`;
  const res = Ed && Ed.resumo ? tabela(t("bim_resumo"), [[t("bim_esquema"), escL(Ed.resumo.esquema)], [t("elementos"), nf(Ed.resumo.elementos, 0)],
      [t("bim_por_tipo"), escL(Object.keys(Ed.resumo.elementos_por_tipo).map(k => k + " " + Ed.resumo.elementos_por_tipo[k]).join(", "))],
      [t("bim_pavs"), escL((Ed.resumo.pavimentos || []).map(p => p.nome).join(", ") || "—")], [t("bim_leitor"), escL(Ed.resumo.leitor || "")], [t("lg_levado"), deOnde(Ed)]]) : "";
  return `<h2>${escL(t("bim_t"))}</h2>
  <section class="cartao" aria-labelledby="bim-o-h"><h3 id="bim-o-h">${escL(t("bim_o_t"))}</h3><p>${escL(t("bim_o"))}</p>
    <label for="bim-arq">${escL(t("bim_arq"))}</label><input id="bim-arq" type="file" accept=".ifc,.dxf,.step,.stp,.iges,.igs" data-lab-arq="bim">
    <p class="t2 pq">${escL(t("bim_step"))}</p>${msgHtml("bim-msg", lab.bimMsg)}</section>
  <section class="cartao" aria-labelledby="bim-f-h"><h3 id="bim-f-h">${escL(t("bim_ferr"))}</h3>
    ${barraFerramentas(E, "bim", ["selecionar", "mover", "girar", "escalar", "puxar", "linha", "retangulo", "circulo", "medir", "desfazer", "refazer", "enquadrar"])}
    <div class="campos">${campo("bim-grade", t("bim_grade"), nf(E.passo, 2), ' data-lab-cfg="bim"')}${campo("bim-alt-nova", t("bim_altura_nova"), nf(E.alturaNova, 2), ' data-lab-cfg="bim"')}</div>
    <div class="lab-modelo"><div id="bim-vista" class="lab-vista-lugar"><p class="t2" id="bim-vista-carregando">${escL(t("bim_carregando"))}</p></div>
      <div class="lab-lateral"><h4>${escL(t("bim_arvore"))}</h4>${arvoreBim(E)}<div id="bim-sel">${painelSelecionado(E, "bim")}</div></div></div>
    <p class="t2 pq">${escL(t("bim_teclado"))}</p></section>
  <section class="cartao" aria-labelledby="bim-p-h"><h3 id="bim-p-h">${escL(t("bim_prim_t"))}</h3>${formPrimitiva()}</section>
  <section class="cartao" aria-labelledby="bim-e-h"><h3 id="bim-e-h">${escL(t("bim_exp_t"))}</h3><p>${escL(t("bim_exp_txt"))}</p>
    <label class="opcao"><input type="checkbox" id="bim-so-sel"${lab.bimSoSel ? " checked" : ""} data-lab-chk2="bim"> ${escL(t("bim_so_sel"))}</label>
    ${exportarBotoes("bim", `<p class="t2 pq">${escL(t("bim_ifc_nota"))}</p>`)}${res}</section>`;
}
function exportarDe(E, fmt, pre, nomeBase) {
  const so = pre === "bim" && lab.bimSoSel && E.sel, ids = so ? [E.sel] : null, I = window.PhysisImagem3D, nome = nomeBase || "modelo";
  if (fmt === "dxf") { baixar(nome + ".dxf", E.dxfTexto(), "application/dxf"); return { texto: t("baixado") }; }
  if (fmt === "svg") { baixar(nome + ".svg", E.svgTexto(), "image/svg+xml"); return { texto: t("baixado") }; }
  const sol = E.solidos(ids); if (!sol.length) return { texto: t("bim_nada"), erro: true };
  if (fmt === "ifc") { baixar(nome + ".ifc", I.escreverIfc(sol.map(o => ({ nome: o.nome, descricao: o.ifcTipo || o.origem || "", T: E.mundo(o) })), nome), "application/x-step"); return { texto: t("baixado") }; }
  if (fmt === "montagem") { sol.forEach(o => montagemAdd({ nome: o.nome, T: E.mundo(o), origem: "bim", cor: o.cor })); irPara("montagem"); return "fica"; }
  const T = E.conjunto(ids);
  if (fmt === "stl") { baixar(nome + ".stl", PHYSIS3D.escreverSTL(T, nome), "model/stl"); return { texto: t("baixado") }; }
  if (fmt === "3mf") { baixar(nome + ".3mf", pre === "mo" ? I.escrever3MFMontagem(montagemItens()) : PHYSIS3D.escrever3MF(T), "model/3mf"); return { texto: t("baixado") }; }
  if (fmt === "pecas") { abrirEmPecas(new File([stlDe(T, nome)], nome + ".stl", { type: "model/stl" }), t("abas")[pre === "mo" ? "montagem" : "edificacao"]); return "fica"; }
  if (fmt === "imp") { if (pre === "mo") pedirImpressaoDe(nome + ".3mf", I.escrever3MFMontagem(montagemItens()), t("abas").montagem); else pedirImpressaoDe(nome + ".stl", stlDe(T, nome), t("abas").edificacao); return "fica"; }
}

/* ════════ 4. Montagens ════════ */
function editorMo() {
  if (!edMo) edMo = window.PhysisModelagem.editor({ rotulo: t("mo_t"), ferramentas: ["selecionar", "mover", "girar", "escalar"],
    aoMudar: () => { if (lab.lote) return; guardarMoNoProjeto(); if (abaLab === "montagem") desenharSemVista(); } });
  return edMo;
}
function montagemAdd(item) {
  const E = editorMo(), c = window.PhysisImagem3D.caixaDe(item.T), dx = E.objetos.length ? (window.PhysisImagem3D.caixaDe(E.conjunto()).max[0] + 10 - c.min[0]) : 0;
  E.adicionar({ nome: item.nome, tipo: "malha", T: item.T, origem: item.origem || "", cor: item.cor || window.PhysisImagem3D.CORES_PECA[E.objetos.length % 7][3], material: item.material || "", pos: [dx, 0, -c.min[2]] });
  E._enq = false;
}
function montagemItens() { const E = editorMo(); return E.solidos().map(o => ({ nome: o.nome, T: E.mundo(o), cor: o.cor, material: o.material ? nomeMat(o.material) : o.nome })); }
function guardarMoNoProjeto() { if (!edMo) return; proj.montagem = { itens: edMo.objetos.map(o => ({ nome: o.nome, origem: o.origem, pos: o.pos, rot: o.rot, esc: o.esc, cor: o.cor, material: o.material || "" })), atualizado: agora() }; gravarProjeto(""); }
function telaMontagem() {
  const E = window.PhysisModelagem ? editorMo() : null;
  if (!E) return `<h2>${escL(t("mo_t"))}</h2><p class="faixa erro" role="alert">${escL(t("sem_modulos"))}</p>`;
  const itens = E.solidos(), col = itens.length > 1 ? window.PhysisImagem3D.colisoes(itens.map(o => ({ nome: o.nome, T: E.mundo(o) }))) : [];
  const mats = window.PHYSIS3D && PHYSIS3D.materiais ? PHYSIS3D.materiais() : {}, cores = window.PhysisImagem3D.CORES_PECA;
  const linhas = E.objetos.map(o => `<tr><th scope="row"><button type="button" class="lab-item${o.id === E.sel ? " sel" : ""}" id="mo-it-${o.id}" data-lab="mo-sel" data-id="${o.id}" aria-pressed="${o.id === E.sel}">${escL(o.nome)}</button></th>
      <td>${o.pos.map(v => nf(v, 1)).join("; ")}</td><td>${o.rot.map(v => nf(v, 0)).join("; ")}°</td>
      <td><label class="so-leitor" for="mo-mat-${o.id}">${escL(t("mo_material"))}: ${escL(o.nome)}</label><select id="mo-mat-${o.id}" data-lab-momat="${o.id}"><option value="">—</option>${Object.keys(mats).map(k => `<option value="${escL(k)}"${k === o.material ? " selected" : ""}>${escL(mats[k].nome || k)}</option>`).join("")}</select></td>
      <td><label class="so-leitor" for="mo-cor-${o.id}">${escL(t("mo_cor"))}: ${escL(o.nome)}</label><select id="mo-cor-${o.id}" data-lab-mocor="${o.id}">${cores.map(c => `<option value="${c[3]}"${c[3] === o.cor ? " selected" : ""}>${escL(lang === "en" ? c[2] : c[1])}</option>`).join("")}</select></td>
      <td><button class="botao sec" type="button" id="mo-tirar-${o.id}" data-lab="mo-tirar" data-id="${o.id}" aria-label="${escL(t("tirar"))}: ${escL(o.nome)}">${escL(t("tirar"))}</button></td></tr>`).join("");
  const fontes = `<option value="aberta">${escL(t("mo_de_aberta"))}</option><option value="bim">${escL(t("mo_de_bim"))}</option>`
    + proj.pecas.map((p, i) => `<option value="proj-${i}">${escL(t("mo_de_proj"))}: ${escL(p.nome)}</option>`).join("")
    + testesProntos().map(x => `<option value="teste-${x.id}">${escL(t("mo_de_teste"))}: ${escL(lang === "en" && x.en ? x.en.nome : x.nome)}</option>`).join("");
  return `<h2>${escL(t("mo_t"))}</h2>
  <section class="cartao" aria-labelledby="mo-o-h"><h3 id="mo-o-h">${escL(t("mo_o_t"))}</h3><p>${escL(t("mo_o"))}</p>${msgHtml("mo-msg", lab.moMsg)}</section>
  <section class="cartao" aria-labelledby="mo-a-h"><h3 id="mo-a-h">${escL(t("mo_add_t"))}</h3>
    <form id="mo-add-form" novalidate><label for="mo-fonte">${escL(t("mo_add_t"))}</label><select id="mo-fonte">${fontes}</select>
      <div class="acoes"><button class="botao sec" type="submit" id="mo-add">${escL(t("mo_add"))}</button></div></form>
    <label for="mo-arq">${escL(t("mo_de_arq"))}</label><input id="mo-arq" type="file" accept=".stl,.obj,.3mf" data-lab-arq="montagem">
    <p class="t2 pq">${escL(t("mo_sem_proj_geo"))}</p></section>
  <section class="cartao" aria-labelledby="mo-l-h"><h3 id="mo-l-h">${escL(t("mo_lista"))}</h3>
    ${barraFerramentas(E, "mo", ["selecionar", "mover", "girar", "escalar", "desfazer", "refazer", "enquadrar"])}
    <div class="lab-modelo"><div id="mo-vista" class="lab-vista-lugar"></div><div class="lab-lateral"><div id="mo-sel">${painelSelecionado(E, "mo")}</div></div></div>
    <p class="t2 pq">${escL(t("bim_teclado"))}</p>
    ${E.objetos.length ? `<div class="rolagem"><table><caption>${escL(t("mo_lista"))}</caption><thead><tr><th scope="col">${escL(t("nome"))}</th><th scope="col">${escL(t("bim_x"))}; Y; Z</th><th scope="col">${escL(t("bim_rz"))}</th><th scope="col">${escL(t("mo_material"))}</th><th scope="col">${escL(t("mo_cor"))}</th><th scope="col">${escL(t("acao"))}</th></tr></thead><tbody>${linhas}</tbody></table></div>`
      : `<p class="t2">${escL(t("mo_nenhuma"))}</p>`}</section>
  <section class="cartao" aria-labelledby="mo-c-h"><h3 id="mo-c-h">${escL(t("mo_col_t"))}</h3>
    ${col.length ? `<ul class="lista">${col.map(c => `<li>${escL(itens[c.a].nome)} × ${escL(itens[c.b].nome)}: ${escL(t("mo_col"))} (${nf(c.volume_mm3 / 1000, 2)} cm³)</li>`).join("")}</ul>` : `<p>${escL(t("mo_col_ok"))}</p>`}
    <p class="t2 pq">${escL(t("mo_col_nota"))}</p></section>
  <section class="cartao" aria-labelledby="mo-e-h"><h3 id="mo-e-h">${escL(t("mo_exp_t"))}</h3>${exportarBotoes("mo", "")}</section>
  <section class="cartao" aria-labelledby="mo-p-h"><h3 id="mo-p-h">${escL(t("mo_prog_t"))}</h3><p>${escL(t("mo_prog_txt"))}</p>
    <div class="rolagem"><table><caption>${escL(t("mo_prog_t"))}</caption><thead><tr>${t("mo_prog_cols").map(c => `<th scope="col">${escL(c)}</th>`).join("")}</tr></thead>
    <tbody>${PROGRAMAS.map(p => `<tr><th scope="row">${escL(p[0])}</th>${p.slice(1).map(c => `<td>${escL(lang === "en" ? c[1] : c[0])}</td>`).join("")}</tr>`).join("")}</tbody></table></div></section>`;
}
/* programas mapeados nos documentos (docs/PHYSIS_3D.md, docs/SIMULACAO.md, Sistema Physis/23b_Catalogo_Software_Aberto.md); o que não está neles é [MARCADOR] */
const EM_DEV = ["Fase 2, em servidor: em desenvolvimento", "Phase 2, on the server: in development"];
const PROGRAMAS = [
  ["FreeCAD", ["CAD 3D paramétrico; a bancada BIM faz paredes e lajes", "Parametric 3D CAD; the BIM workbench makes walls and slabs"], ["Saída: STEP e IFC (catálogo); outros formatos [MARCADOR]", "Output: STEP and IFC (catalogue); other formats [MARCADOR]"], ["LGPL-2.1", "LGPL-2.1"], ["Mapeado no catálogo; não ligado ao laboratório: em desenvolvimento", "Mapped in the catalogue; not connected to the lab: in development"]],
  ["CadQuery", ["CAD por código Python (B-rep do OpenCascade)", "CAD as Python code (OpenCascade B-rep)"], ["[MARCADOR]", "[MARCADOR]"], ["Apache-2.0", "Apache-2.0"], ["Mapeado no catálogo; não ligado ao laboratório: em desenvolvimento", "Mapped in the catalogue; not connected to the lab: in development"]],
  ["OpenSCAD", ["CAD paramétrico por código", "Parametric CAD as code"], ["[MARCADOR]", "[MARCADOR]"], ["[MARCADOR: não consta do catálogo 23b]", "[MARCADOR: not in catalogue 23b]"], ["[MARCADOR: ainda não mapeado nos documentos]", "[MARCADOR: not yet mapped in the documents]"]],
  ["Gmsh", ["Gerador de malha 2D e 3D", "2D and 3D mesh generator"], ["Entrada: STL (malha de volume a partir do STL); saída [MARCADOR]", "Input: STL (volume mesh from the STL); output [MARCADOR]"], ["GPL-2.0+ com exceção de linkagem", "GPL-2.0+ with linking exception"], EM_DEV],
  ["CalculiX", ["Elementos finitos: tração, compressão, flexão, flambagem e calor", "Finite elements: tension, compression, bending, buckling and heat"], ["Entrada no formato tipo Abaqus; saída [MARCADOR]", "Abaqus-like input format; output [MARCADOR]"], ["GPL-2.0+", "GPL-2.0+"], EM_DEV],
  ["OpenFOAM", ["Escoamento (CFD), pressão e calor em fluidos", "Flow (CFD), pressure and heat in fluids"], ["[MARCADOR]", "[MARCADOR]"], ["GPL-3.0", "GPL-3.0"], EM_DEV],
  ["FEniCSx", ["Equações (PDE) escritas em Python e resolvidas por elementos finitos", "Equations (PDEs) written in Python and solved by finite elements"], ["[MARCADOR]", "[MARCADOR]"], ["LGPL-3.0 (partes MIT)", "LGPL-3.0 (parts MIT)"], EM_DEV],
  ["PrusaSlicer", ["Fatiador: transforma a peça em G-code (serviço fatiador do servidor)", "Slicer: turns the part into G-code (server slicer service)"], ["Entrada: STL; saída: G-code", "Input: STL; output: G-code"], ["AGPL-3.0", "AGPL-3.0"], ["Serviço em contêiner escrito, ainda não construído: em desenvolvimento", "Container service written, not built yet: in development"]]];
async function acrescentarNaMontagem(fonte) {
  if (fonte === "aberta") { const st = (typeof ui !== "undefined" && ui.p3d) || {}; if (!st.T) return { texto: t("pc_dica"), erro: true };
    montagemAdd({ nome: String(st.nome || "peça"), T: st.T, origem: "pecas" }); return { texto: String(st.nome || "") }; }
  if (fonte === "bim") { if (!edBim || !edBim.solidos().length) return { texto: t("bim_nada"), erro: true };
    edBim.solidos().forEach(o => montagemAdd({ nome: o.nome, T: edBim.mundo(o), origem: "bim", cor: o.cor })); return { texto: t("mo_de_bim") }; }
  if (fonte.indexOf("proj-") === 0) { const p = proj.pecas[+fonte.slice(5)]; if (!p) return null; const T = p.malha_id ? await lerMalhaGuardada(p.malha_id) : null;
    if (!T) return { texto: p.nome + ": " + t("mo_sem_geo"), erro: true }; montagemAdd({ nome: p.nome, T, origem: "projeto" }); return { texto: p.nome }; }
  if (fonte.indexOf("teste-") === 0) { const x = testesProntos().filter(q => q.id === fonte.slice(6))[0]; if (!x) return null;
    montagemAdd({ nome: lang === "en" && x.en ? x.en.nome : x.nome, T: x.T, origem: "teste" }); return { texto: x.nome }; }
  return null;
}

/* ════════ 5. Peças 3D (motor sistema/physis-3d.js, sem mudar) ════════ */
function telaPecas() {
  const st = (typeof ui !== "undefined" && ui.p3d) || {}, m = st.med, pode = !!(st.T && m);
  const linhas = proj.pecas.map((p, i) => `<tr><th scope="row">${escL(p.nome)}</th><td>${Array.isArray(p.tamanho_mm) ? p.tamanho_mm.map(v => nf(v, 1)).join(" × ") + " mm" : "—"}</td>
      <td>${nf(p.volume_mm3 / 1000, 2)} cm³</td><td>${p.biblioteca_id ? escL(p.biblioteca_id) : "—"}</td><td>${escL(quando(p.guardado_em))}</td>
      <td><button class="botao sec" type="button" id="pc-tirar-${i}" data-lab="peca-tirar" data-i="${i}" aria-label="${escL(t("tirar"))}: ${escL(p.nome)}">${escL(t("tirar"))}</button></td></tr>`).join("");
  const dis = pode ? "" : ' disabled aria-describedby="pc-guardar-dica"';
  return `<h2>${escL(t("pc_t"))}</h2>
  <section class="cartao" aria-labelledby="pc-h"><h3 id="pc-h">${escL(t("pc_no_proj"))}</h3><p class="t2">${escL(t("pc_txt"))}</p>
    <div class="acoes"><button class="botao" type="button" id="pc-imp" data-lab="peca-imp"${dis}>${escL(t("pedir_impressao"))}</button>
      <button class="botao sec" type="button" id="pc-guardar" data-lab="peca-guardar"${dis}>${escL(t("pc_guardar"))}</button>
      <button class="botao sec" type="button" id="pc-editar" data-lab="peca-editar"${dis}>${escL(t("pc_editar"))}</button></div>
    ${pode ? "" : `<p class="t2 pq" id="pc-guardar-dica">${escL(t("pc_dica"))}</p>`}
    ${msgHtml("pc-msg", lab.peca)}
    ${proj.pecas.length ? `<div class="rolagem"><table><caption>${escL(t("pc_guardadas"))}</caption><thead><tr><th scope="col">${escL(t("nome"))}</th><th scope="col">${escL(t("tamanho"))}</th><th scope="col">${escL(t("volume"))}</th><th scope="col">${escL(t("pc_biblioteca"))}</th><th scope="col">${escL(t("pc_quando"))}</th><th scope="col">${escL(t("acao"))}</th></tr></thead><tbody>${linhas}</tbody></table></div>` : ""}</section>
  ${telaPhysis3D()}
  ${cartaoTestes()}`;
}
async function guardarPeca() {
  const st = (typeof ui !== "undefined" && ui.p3d) || {}, m = st.med;
  if (!st.T || !m) return { texto: t("pc_dica"), erro: true };
  const bib = st.peca && st.peca.ok && st.peca.peca ? st.peca.peca.id : null, id = "peca-" + Date.now();
  const ok = await guardarMalha(id, st.T instanceof Float32Array ? st.T : new Float32Array(st.T));
  proj.pecas.push({ nome: String(st.nome || "peça"), origem: "Physis 3D", tamanho_mm: (m.tamanho || []).slice(0, 3),
    volume_mm3: m.volume_mm3, area_mm2: m.area_mm2, triangulos: m.triangulos, biblioteca_id: bib, malha_id: ok ? id : null, guardado_em: agora() });
  registrarPasso("pecas", String(st.nome || "peça"));
  gravarProjeto(t("pc_guardada"));
  return { texto: t("pc_guardada") + " " + String(st.nome || "peça") + "." };
}

/* ════════ 6. Simulação: um bloco por fenômeno (motor window.SIMULACAO, sem mudar contas) ════════ */
const FEN = [
  { id: "calor", prefixos: ["termica."], pt: { nome: "Calor",
    faz: "Transmitância (U) de parede ou cobertura, a parede ao longo do dia (atraso térmico e amortecimento) e o corte 2D (ponte térmica, corte de peça impressa).",
    entra: "Camadas ou composição da base de materiais, resistências superficiais de premissa, temperaturas e sol ao longo do dia; no corte 2D, a máscara do corte.",
    sai: "U, capacidade térmica e carbono por m²; atraso e amortecimento; campo de temperatura e fluxos de calor.",
    limites: "Condução em 1D ou 2D com propriedades da base de materiais; convecção e radiação por coeficientes de premissa. Cada resultado traz o limite do motor." },
    en: { nome: "Heat", faz: "Thermal transmittance (U) of walls or roofs, the wall over the day (thermal lag and damping) and the 2D section (thermal bridge, printed-part section).",
    entra: "Layers or build-up from the materials base, assumed surface resistances, temperatures and sun over the day; for the 2D section, the section mask.",
    sai: "U, thermal capacity and carbon per m²; lag and damping; temperature field and heat flows.",
    limites: "1D or 2D conduction with properties from the materials base; convection and radiation by assumed coefficients. Each result carries the engine's limit." } },
  { id: "estrutura", prefixos: ["estrutura."], pt: { nome: "Estrutura",
    faz: "Treliça e pórtico 2D e 3D, flambagem de Euler, verificação de tensão e chapa 2D com triângulos (peças impressas).",
    entra: "Nós, barras, apoios, cargas nos nós, carga distribuída e peso próprio; seção e material (módulo E; resistência fy de ensaio, sem ela vira [MARCADOR]).",
    sai: "Deslocamentos, reações, esforços (normal, cortante, momento, torção), tensões e a verificação de cada elemento.",
    limites: "Estrutura linear (pequenos deslocamentos, material elástico). Vento só pela pressão dinâmica, com coeficientes digitados [CONFERIR NA NORMA]." },
    en: { nome: "Structure", faz: "2D and 3D trusses and frames, Euler buckling, stress check and 2D plates with triangles (printed parts).",
    entra: "Nodes, bars, supports, nodal loads, distributed load and self-weight; section and material (modulus E; tested strength fy, otherwise [MARCADOR]).",
    sai: "Displacements, reactions, internal forces (axial, shear, moment, torsion), stresses and each element's check.",
    limites: "Linear structure (small displacements, elastic material). Wind only by dynamic pressure, with typed coefficients [CONFERIR NA NORMA]." } },
  { id: "ventilacao", prefixos: ["fluidos."], pt: { nome: "Ventilação e vento",
    faz: "Ventilação natural (chaminé e vento), escoamento do ar num corte (Lattice-Boltzmann D2Q9, qualitativo) e energia de turbina pela série de vento.",
    entra: "Aberturas, alturas e temperaturas; grade e obstáculo do corte; série de vento e curva da turbina.",
    sai: "Vazão e trocas de ar por hora; campo de velocidade qualitativo; energia pela série e pela Weibull ajustada.",
    limites: "Coeficientes de descarga e de pressão de premissa. O escoamento LBM é qualitativo (Fase 1): mostra esteira e aceleração, nunca número de projeto." },
    en: { nome: "Ventilation and wind", faz: "Natural ventilation (stack and wind), airflow in a section (Lattice-Boltzmann D2Q9, qualitative) and turbine energy from a wind series.",
    entra: "Openings, heights and temperatures; section grid and obstacle; wind series and turbine curve.",
    sai: "Flow rate and air changes per hour; qualitative velocity field; energy from the series and from the fitted Weibull.",
    limites: "Assumed discharge and pressure coefficients. The LBM flow is qualitative (Phase 1): it shows wakes and acceleration, never a design number." } },
  { id: "terreno", prefixos: ["terreno."], pt: { nome: "Terreno e água",
    faz: "Declividade e aspecto, caminho da água (D8) e acumulação, enxurrada de um evento (SCS-CN), perda de solo (USLE) e visada.",
    entra: "Grade de cotas (a do exemplo ou o terreno do lugar do projeto, contrato physis-geometria-lugar/1); chuva e CN por uso do solo; R, K, C e P digitados na USLE.",
    sai: "Acumulação de fluxo, volume de enxurrada acumulado, perda de solo por célula e células visíveis.",
    limites: "Evento isolado e bacias pequenas no SCS-CN (sem vazão de pico nem hidrograma); fatores da USLE digitados. Cada resultado traz o limite do motor." },
    en: { nome: "Terrain and water", faz: "Slope and aspect, water path (D8) and accumulation, runoff from one event (SCS-CN), soil loss (USLE) and line of sight.",
    entra: "Height grid (the example's or the project site's terrain, physis-geometria-lugar/1 contract); rainfall and CN by land use; typed R, K, C and P for USLE.",
    sai: "Flow accumulation, accumulated runoff volume, soil loss per cell and visible cells.",
    limites: "Single event and small catchments for SCS-CN (no peak flow or hydrograph); typed USLE factors. Each result carries the engine's limit." } },
  { id: "incerteza", prefixos: ["incerteza."], pt: { nome: "Incerteza",
    faz: "Monte Carlo: sorteia as entradas (normal, uniforme, triangular, lognormal) e mostra a média e os percentis do resultado.",
    entra: "Cada entrada com a sua distribuição; o modelo (carbono, solar, payback ou biogás); número de sorteios e semente.",
    sai: "Média e percentis (faixa) do resultado do modelo.",
    limites: "A faixa vale para as distribuições digitadas; o gerador tem semente fixa para repetir o resultado." },
    en: { nome: "Uncertainty", faz: "Monte Carlo: samples the inputs (normal, uniform, triangular, lognormal) and shows the mean and percentiles of the result.",
    entra: "Each input with its distribution; the model (carbon, solar, payback or biogas); number of samples and seed.",
    sai: "Mean and percentiles (range) of the model result.",
    limites: "The range holds for the typed distributions; the generator has a fixed seed to repeat the result." } },
  { id: "biogas", prefixos: ["biogas."], pt: { nome: "Biogás",
    faz: "Produção de biogás por substrato, com cinética de primeira ordem dependente da temperatura e tempo de retenção.",
    entra: "Substratos e quantidades, volume ou tempo de retenção, regime de temperatura e a temperatura mensal do local (sem local, a conta para: nunca usa um padrão).",
    sai: "Biogás e metano por dia e por mês, volume, carga orgânica, energia, GLP equivalente, gerador (P, Q, S e fator de potência), CO₂e evitado, digestato e avisos.",
    limites: "Propriedades dos substratos de premissa \"conferir\"; substrato sem valor vira [MARCADOR]. Cada resultado traz o limite do motor." },
    en: { nome: "Biogas", faz: "Biogas production per substrate, with first-order kinetics depending on temperature and retention time.",
    entra: "Substrates and amounts, volume or retention time, temperature regime and the site's monthly temperature (without a site, the calculation stops: it never uses a default).",
    sai: "Biogas and methane per day and per month, volume, organic load, energy, LPG equivalent, generator (P, Q, S and power factor), avoided CO₂e, digestate and warnings.",
    limites: "Substrate properties are assumptions \"to be checked\"; a substrate without a value becomes [MARCADOR]. Each result carries the engine's limit." } },
  { id: "qubo", prefixos: ["qubo."], pt: { nome: "Otimização QUBO",
    faz: "Problemas pequenos escritos como QUBO: placas sob sombra, caminho de tubo na grade e topologia grossa de peça 2D, resolvidos agora no clássico.",
    entra: "Posições, sombras, grade e custos do problema; penalidade de premissa.",
    sai: "A solução clássica (exata até 20 variáveis ou recozimento simulado) e a energia do QUBO.",
    limites: "A trilha quântica é pesquisa (P&D): precisa dar o mesmo ótimo do clássico e nunca entra em relatório nem certificação." },
    en: { nome: "QUBO optimisation", faz: "Small problems written as QUBO: panels under shade, pipe path on a grid and coarse topology of a 2D part, solved classically for now.",
    entra: "Positions, shading, grid and problem costs; assumed penalty.",
    sai: "The classical solution (exact up to 20 variables or simulated annealing) and the QUBO energy.",
    limites: "The quantum track is research (R&D): it must reach the same optimum as the classical one and never goes into reports or certification." } }];
const fx = f => f[lang] || f.pt;
const TERRENO_DO_LUGAR = ["terreno.escoamento", "terreno.usle", "terreno.declividade_aspecto"];   // casos que só pedem a grade
function casosDe(f) {
  const cs = ((window.SIMULACAO_CASOS || {}).casos || []).filter(c => f.prefixos.some(p => String(c.solver).indexOf(p) === 0));
  return cs.filter(c => c.exemplo).concat(cs.filter(c => !c.exemplo));
}
function estSim(f) {
  const cs = casosDe(f), st = lab.sim[f.id] = lab.sim[f.id] || { caso: null, entrada: null, res: null, c2: null, msg: null, usarLugar: false, aberta: false };
  const c = cs.filter(x => x.id === st.caso)[0] || cs[0];
  if (c && (st.caso !== c.id || st.entrada == null)) { st.caso = c.id; st.entrada = JSON.stringify(c.entrada, null, 1); st.res = null; st.c2 = null; }
  return { st, c, cs };
}
function rodarFen(f) {
  const { st, c } = estSim(f);
  if (!c) return;
  const ta = document.getElementById("sim-ent-" + f.id);
  if (ta) { st.entrada = ta.value; const det = ta.closest("details"); st.aberta = !!(det && det.open); }
  st.res = null; st.c2 = null; st.doLugar = false;
  if (!window.SIMULACAO) { st.msg = { texto: t("si_sem_motor"), erro: true }; return; }
  let e;
  try { e = JSON.parse(st.entrada); } catch (x) { st.msg = { texto: t("si_json_inv") + " " + x.message, erro: true }; st.aberta = true; return; }
  if (st.usarLugar && TERRENO_DO_LUGAR.indexOf(c.solver) >= 0) {
    if (!(proj.lugar && proj.lugar.dados.terreno)) { st.msg = { texto: t("si_sem_terr_proj"), erro: true }; return; }
    try { e = Object.assign({}, e, { grade: SIMULACAO.terreno.gradeDaGeometria(proj.lugar.dados) }); st.doLugar = true; }
    catch (x) { st.msg = { texto: String(x && x.message || x), erro: true }; return; }
  }
  const c2 = Object.assign({}, c, { entrada: e });
  try { st.res = SIMULACAO.rodarCaso(c2); st.c2 = c2; st.msg = { texto: t("si_pronto") + " " + c.nome + (st.doLugar ? " " + t("si_do_lugar_msg") : "") + "." }; }
  catch (x) { st.msg = { texto: (x && x.faltaDado ? "" : t("si_nao_rodou") + " ") + (x && x.message || x), erro: true }; }
}
function escalares(r) {
  const o = {}, n = v => typeof v === "number" && isFinite(v);
  Object.keys(r).forEach(k => {
    const v = r[k];
    if (["metodo", "limites_validade", "aviso", "fase"].indexOf(k) >= 0) return;
    if (n(v) || typeof v === "boolean") o[k] = v;
    else if (typeof v === "string" && v.length <= 200) o[k] = v;
    else if (v && typeof v === "object" && !Array.isArray(v)) { const ks = Object.keys(v); if (ks.length && ks.length <= 20 && ks.every(x => n(v[x]) || typeof v[x] === "string" && v[x].length <= 80)) o[k] = v; }
  });
  return o;
}
function guardarResultado(f) {
  const { st, c } = estSim(f);
  if (!st.res || !st.c2) return { texto: t("si_rode_antes"), erro: true };
  const original = JSON.stringify(c.entrada, null, 1), mudou = st.entrada !== original;
  const r = { fenomeno: f.id, fenomeno_nome: f.pt.nome, caso: c.id, nome: c.nome, solver: c.solver, exemplo_dados_ficticios: !!c.exemplo,
    entrada_mudada: mudou, terreno_do_lugar: !!st.doLugar, metodo: st.res.metodo || "", limites_validade: st.res.limites_validade || "",
    aviso: st.res.aviso || "", avisos: (st.res.avisos || []).slice(0, 20), valores: escalares(st.res), guardado_em: agora() };
  if (mudou && st.entrada.length <= 20000) r.entrada = st.entrada;
  proj.resultados.push(r);
  registrarPasso("simulacao", f.pt.nome + ": " + c.nome);
  gravarProjeto(t("si_res_guardado"));
  return { texto: t("si_res_guardado") + " " + c.nome + "." };
}
function envelope(r) {
  if (!r) return "";
  const prem = (r.premissas_usadas || []).map(p => `<li><code>${escL(p.id)}</code> (${escL(p.status)})</li>`).join("");
  return `<details><summary>${escL(t("si_metodo_t"))}</summary>${r.metodo ? `<p><strong>${escL(t("si_metodo"))}</strong> ${escL(r.metodo)}</p>` : ""}
      ${r.malha != null ? `<p><strong>${escL(t("si_malha"))}</strong> ${escL(JSON.stringify(r.malha))}</p>` : ""}
      ${(r.hipoteses || []).length ? `<ul class="lista">${r.hipoteses.map(h => `<li>${escL(h)}</li>`).join("")}</ul>` : ""}
      ${prem ? `<p><strong>${escL(t("si_prem"))}</strong></p><ul class="lista">${prem}</ul>` : ""}</details>
    ${r.limites_validade ? `<p><strong>${escL(t("si_lim_motor"))}</strong> ${escL(r.limites_validade)}</p>` : ""}
    ${(r.avisos || []).length ? `<div class="faixa at" role="note"><ul class="lista">${r.avisos.map(a => `<li>${escL(a)}</li>`).join("")}</ul></div>` : ""}
    ${r.aviso ? `<p class="faixa in" role="note">${escL(r.aviso)}</p>` : ""}`;
}
function blocoFen(f, n) {
  const { st, c, cs } = estSim(f), x = fx(f);
  if (!c) return `<section class="cartao lab-fen" id="fen-${f.id}" tabindex="-1" aria-labelledby="fen-${f.id}-h"><h3 id="fen-${f.id}-h">${n}. ${escL(x.nome)}</h3><p class="faixa in" role="note">${escL(t("si_sem_ex"))}</p></section>`;
  const temLugar = f.id === "terreno", pode = TERRENO_DO_LUGAR.indexOf(c.solver) >= 0, terr = !!(proj.lugar && proj.lugar.dados.terreno);
  let res = "";
  if (st.res && st.c2) { try { res = SIMULACAO.desenhoCaso(st.c2, st.res, "sim-fig-" + f.id); } catch (e) { res = ""; } res += envelope(st.res); }
  return `<section class="cartao lab-fen" id="fen-${f.id}" tabindex="-1" aria-labelledby="fen-${f.id}-h"><h3 id="fen-${f.id}-h">${n}. ${escL(x.nome)}</h3>
    <dl class="lab-ficha"><dt>${escL(t("si_faz"))}</dt><dd>${escL(x.faz)}</dd><dt>${escL(t("si_entra"))}</dt><dd>${escL(x.entra)}</dd><dt>${escL(t("si_sai"))}</dt><dd>${escL(x.sai)}</dd><dt>${escL(t("si_lim"))}</dt><dd>${escL(x.limites)}</dd></dl>
    <label for="sim-sel-${f.id}">${escL(t("si_exemplo"))}</label>
    <select id="sim-sel-${f.id}" data-lab-sel="${f.id}">${cs.map(q => `<option value="${escL(q.id)}"${q.id === c.id ? " selected" : ""}>${escL(q.nome)}${q.exemplo ? "" : " " + escL(t("si_teste_conf"))}</option>`).join("")}</select>
    <p class="t2 pq">${escL(c.descricao || "")} ${c.exemplo ? (/fictíci/i.test(c.descricao || "") ? "" : escL(t("si_ficticio"))) : escL(t("si_conf"))}</p>
    ${temLugar ? `<label class="opcao"><input type="checkbox" id="sim-lugar-${f.id}" data-lab-chk="${f.id}"${st.usarLugar ? " checked" : ""}${terr && pode ? "" : " disabled"}> ${escL(t("si_usar_lugar"))}</label>
      <p class="t2 pq">${escL(t(terr ? (pode ? "si_lugar_troca" : "si_lugar_mais") : "si_sem_terreno"))}</p>` : ""}
    <details${st.aberta ? " open" : ""}><summary>${escL(t("si_entrada_t"))}</summary><label for="sim-ent-${f.id}">${escL(t("si_entrada"))}</label>
      <textarea id="sim-ent-${f.id}" rows="8" style="width:100%" spellcheck="false">${escL(st.entrada)}</textarea></details>
    <div class="acoes"><button class="botao" type="button" id="sim-rodar-${f.id}" data-lab="sim-rodar" data-fen="${f.id}">${escL(t("si_rodar"))}: ${escL(x.nome.toLowerCase())}</button>
      <button class="botao sec" type="button" id="sim-repor-${f.id}" data-lab="sim-repor" data-fen="${f.id}">${escL(t("si_repor"))}</button>
      <button class="botao sec" type="button" id="sim-guardar-${f.id}" data-lab="sim-guardar" data-fen="${f.id}"${st.res ? "" : ' disabled aria-describedby="sim-dica-' + f.id + '"'}>${escL(t("si_guardar"))}</button></div>
    ${st.res ? "" : `<p class="t2 pq" id="sim-dica-${f.id}">${escL(t("si_dica"))}</p>`}
    ${msgHtml("sim-msg-" + f.id, st.msg)}
    <div class="lab-res">${res}</div></section>`;
}
function telaSimulacaoBlocos() {
  const guardados = proj.resultados.map((r, i) => `<tr><th scope="row">${escL(r.nome)}</th><td>${escL(r.fenomeno_nome)}</td><td>${escL(t(r.exemplo_dados_ficticios ? "si_ex" : "si_bench"))}${r.entrada_mudada ? ", " + escL(t("si_mudada")) : ""}${r.terreno_do_lugar ? ", " + escL(t("si_do_lugar")) : ""}</td>
      <td>${escL(quando(r.guardado_em))}</td><td><button class="botao sec" type="button" id="res-tirar-${i}" data-lab="res-tirar" data-i="${i}" aria-label="${escL(t("tirar"))}: ${escL(r.nome)}">${escL(t("tirar"))}</button></td></tr>`).join("");
  return `<h2>${escL(t("si_t"))}</h2><p>${escL(t("si_txt"))}</p><p class="faixa" role="note">${escL(t("si_faixa"))}</p>
  <ul class="lab-indice" aria-label="${escL(t("si_ir"))}">${FEN.map((f, i) => `<li><button class="botao sec" type="button" id="sim-ir-${f.id}" data-lab="sim-ir" data-fen="${f.id}">${i + 1}. ${escL(fx(f).nome)}</button></li>`).join("")}</ul>
  ${FEN.map((f, i) => blocoFen(f, i + 1)).join("")}
  <section class="cartao" aria-labelledby="sim-proj-h"><h3 id="sim-proj-h">${escL(t("si_guardados"))}</h3>
    ${proj.resultados.length ? `<div class="rolagem"><table><caption>${escL(t("si_guardados"))}</caption><thead><tr>${t("si_cols").map(c => `<th scope="col">${escL(c)}</th>`).join("")}</tr></thead><tbody>${guardados}</tbody></table></div>` : `<p class="t2">${escL(t("si_nenhum"))}</p>`}</section>`;
}

/* ════════ 7. Fila de impressão (physis_hub/inovastem.py: /api/inovastem/impressao*) ════════ */
async function carregarFila() {
  lab.fila = { carregando: true };
  const i = await instancia(true), f = { inst: i, minhas: null, equipe: null, pecas: null };
  if (i && i.autenticado) {
    f.minhas = await getJ("/api/inovastem/impressao/minhas");
    f.pecas = await getJ("/api/3d/pecas");
    if (ehEquipe(i)) f.equipe = await getJ("/api/inovastem/impressao/fila");
  }
  lab.fila = f;
}
const nomeMat = k => { try { const M = window.PHYSIS3D && PHYSIS3D.materiais ? PHYSIS3D.materiais() : {}; return (M[k] && M[k].nome) || k; } catch (e) { return k; } };
function telaFila() {
  const f = lab.fila, situacao = x => escL(t("estados")[x.estado] || x.estado) + (x.motivo ? " · " + escL(t("fi_motivo_rot")) + ": " + escL(x.motivo) : ""), A = lab.filaArq;
  const nomeP = x => x.origem === "laboratorio" ? escL(x.arquivo_nome) + " (" + escL(t("fi_do_lab")) + ")" : escL(x.peca_nome || t("fi_peca_rot") + " " + x.peca) + " (" + escL(t("fi_revisao")) + " " + (+x.revisao) + ")";
  let h = `<h2>${escL(t("fi_t"))}</h2>
  <section class="cartao" aria-labelledby="fi-o-h"><h3 id="fi-o-h">${escL(t("fi_como_t"))}</h3><ol class="lista">${t("fi_como").map(x => `<li>${escL(x)}</li>`).join("")}</ol>
    <p class="faixa" role="note">${escL(t("fi_nada"))}</p><p class="t2 pq">${escL(t("fi_impressoras"))}</p></section>`;
  const mats = (f && f.minhas && f.minhas.materiais) || ["rpetg", "rpp", "rhdpe", "rabs", "rpla"];
  const matSel = id => `<label for="${id}">${escL(t("fi_material"))}</label><select id="${id}"><option value="">${escL(t("fi_equipe_escolhe"))}</option>${mats.map(m => `<option value="${escL(m)}">${escL(nomeMat(m))}</option>`).join("")}</select>`;
  if (A) h += `<section class="cartao lab-pronto" aria-labelledby="fi-arq-h"><h3 id="fi-arq-h" tabindex="-1">${escL(t("fi_arq_t"))}</h3>
    <p><strong>${escL(A.nome)}</strong> · ${nf(A.tamanho / 1024, 0)} kB · ${escL(t("fi_arq_de"))} ${escL(A.origem || "")}</p><p class="t2 pq">${escL(t("fi_arq_priv"))}</p>
    ${f && f.inst && f.inst.autenticado ? `<form id="fila-arq-form" novalidate>${matSel("fa-mat")}<label for="fa-obs">${escL(t("fi_obs"))}</label><textarea id="fa-obs" maxlength="1000" rows="3"></textarea>
      <div class="acoes"><button class="botao" type="submit" id="fa-enviar">${escL(t("fi_arq_pedir"))}</button><button class="botao sec" type="button" id="fa-descartar" data-lab="fila-descartar">${escL(t("fi_arq_descartar"))}</button></div></form>` : ""}
    </section>`;
  if (!f || f.carregando) return h + `<p class="t2" role="status">${escL(t("carregando"))}</p>`;
  if (!f.inst) return h + `<p class="faixa erro" role="alert">${escL(t("sem_hub"))}</p>`;
  if (!f.inst.autenticado) return h + `<section class="cartao" aria-labelledby="fi-c-h"><h3 id="fi-c-h">${escL(t("fi_entre_t"))}</h3><p>${escL(t("fi_entre"))}</p>
    <div class="acoes"><a class="botao" href="/#participar">${escL(t("fi_entrar"))}</a><button class="botao sec" type="button" id="fi-recarregar" data-lab="fila-recarregar">${escL(t("fi_ja_entrei"))}</button></div>${msgHtml("fi-msg", lab.filaMsg)}</section>`;
  const pecas = f.pecas && f.pecas.ok ? (f.pecas.pecas || []).filter(p => p.revisoes > 0) : null;
  h += `<section class="cartao" aria-labelledby="fi-p-h"><h3 id="fi-p-h">${escL(t("fi_bib_t"))}</h3><form id="fila-form" novalidate>
    ${pecas ? (pecas.length ? `<label for="fi-peca">${escL(t("fi_peca"))}</label><select id="fi-peca" required>${pecas.map(p => `<option value="${+p.id}">${escL(t("fi_peca_rot"))} ${+p.id}: ${escL(p.nome)}${p.minha ? " " + escL(t("fi_minha")) : ""}</option>`).join("")}</select>`
        : `<p class="t2">${escL(t("fi_sem_pecas"))}</p>`)
      : `<label for="fi-peca">${escL(t("fi_peca_n"))}</label><input id="fi-peca" type="text" inputmode="numeric" required>`}
    ${matSel("fi-mat")}<label for="fi-obs">${escL(t("fi_obs"))}</label><textarea id="fi-obs" maxlength="1000" rows="3"></textarea>
    <div class="acoes"><button class="botao" type="submit" id="fi-enviar"${pecas && !pecas.length ? " disabled" : ""}>${escL(t("pedir_impressao"))}</button></div></form>
    ${msgHtml("fi-msg", lab.filaMsg)}</section>`;
  const minhas = f.minhas && f.minhas.ok ? f.minhas.itens : [];
  h += `<section class="cartao" aria-labelledby="fi-m-h"><h3 id="fi-m-h">${escL(t("fi_meus"))}</h3>${minhas.length ? `<div class="rolagem"><table><caption>${escL(t("fi_meus_cap"))}</caption><thead><tr>${t("fi_cols").map(c => `<th scope="col">${escL(c)}</th>`).join("")}</tr></thead><tbody>
    ${minhas.map(x => `<tr><th scope="row">${+x.id}</th><td>${nomeP(x)}</td><td>${escL(x.material ? nomeMat(x.material) : t("fi_equipe_escolhe"))}</td><td>${situacao(x)}</td><td>${escL(quando(x.criado))}</td></tr>`).join("")}</tbody></table></div>`
    : `<p class="t2">${escL(t("fi_nenhum"))}</p>`}<div class="acoes"><button class="botao sec" type="button" id="fi-recarregar" data-lab="fila-recarregar">${escL(t("fi_atualizar"))}</button></div></section>`;
  if (f.equipe) {
    const it = f.equipe.ok ? f.equipe.itens : [];
    h += `<section class="cartao" aria-labelledby="fi-e-h"><h3 id="fi-e-h">${escL(t("fi_equipe_t"))}</h3>${f.equipe.ok ? "" : `<p class="faixa erro" role="alert">${escL(f.equipe.erro || t("fi_equipe_erro"))}</p>`}
      ${it.length ? it.map(x => `<div class="item"><h4 id="fe-h-${+x.id}">${escL(t("fi_pedido"))} ${+x.id}: ${nomeP(x)}</h4>
        <p>${escL(x.nome_publico || "")} · ${escL(x.material ? nomeMat(x.material) : t("fi_equipe_escolhe"))} · ${escL(t("fi_situacao"))}: <strong>${situacao(x)}</strong> · ${escL(quando(x.criado))}</p>
        ${x.observacao ? `<p class="t2">${escL(t("fi_obs_rot"))} ${escL(x.observacao)}</p>` : ""}
        <div class="acoes"><a class="botao sec" href="${escL(x.arquivo_url)}" download aria-describedby="fe-h-${+x.id}">${escL(t("fi_baixar"))} (${escL(x.arquivo_nome)})</a>
          ${x.proximos.map(e => `<button class="botao${e === "recusada" ? " sec" : ""}" type="button" id="fe-${+x.id}-${e}" data-lab="fila-estado" data-id="${+x.id}" data-estado="${e}" aria-describedby="fe-h-${+x.id}">${escL(t("passos_rot")[e] || e)}</button>`).join("")}</div>
        ${x.proximos.indexOf("recusada") >= 0 ? `<label for="fe-mot-${+x.id}">${escL(t("fi_motivo"))} ${+x.id})</label><input id="fe-mot-${+x.id}" type="text" maxlength="400">` : ""}</div>`).join("")
        : `<p class="t2">${escL(t("fi_vazia"))}</p>`}</section>`;
  }
  return h;
}

/* ════════ 8. Galeria (peças publicadas, só licenças abertas) ════════ */
async function carregarGaleria() { lab.gal = { carregando: true }; const j = await getJ("/api/publico/3d/pecas"); lab.gal = { j, abertas: {} }; }
function telaGaleria() {
  const g = lab.gal;
  let h = `<h2>${escL(t("ga_t"))}</h2>
  <section class="cartao" aria-labelledby="ga-o-h"><h3 id="ga-o-h">${escL(t("ga_o_t"))}</h3><p>${escL(t("ga_o"))}</p>
    <p><strong>${escL(t("ga_lic"))}</strong>${g && g.j && g.j.licencas ? " " + escL(t("ga_lic_aceitas")) + " " + Object.keys(g.j.licencas).map(k => escL(g.j.licencas[k]) + " (" + escL(k) + ")").join("; ") + "." : ""}</p>
    <p>${escL(t("ga_enviar_txt"))}</p><div class="acoes"><a class="botao sec" href="#pecas">${escL(t("ga_enviar"))}</a></div></section>`;
  if (!g || g.carregando) return h + `<p class="t2" role="status">${escL(t("carregando"))}</p>`;
  if (!g.j.ok) return h + `<p class="faixa erro" role="alert">${escL(t("ga_erro"))}</p>`;
  const lic = g.j.licencas || {}, pecas = (g.j.pecas || []).filter(p => Object.prototype.hasOwnProperty.call(lic, p.licenca));
  if (!pecas.length) return h + `<p class="t2">${escL(t("ga_nenhuma"))}</p>`;
  return h + pecas.map(p => {
    const ab = g.abertas[p.id];
    const arqs = ab ? (ab.ok ? `<ul class="lista">${(ab.revisoes || []).map(r => `<li>${escL(t("ga_revisao"))} ${+r.numero}: <a href="/api/publico/3d/arquivo/${escL(r.arquivo_sha256)}" download>${escL(t("ga_baixar"))} ${escL(r.arquivo_nome)}</a>${r.resultado ? " · " + escL(t("ga_resultado")) + ": " + escL(r.resultado) : ""}</li>`).join("")}</ul>` : `<p class="msg erro">${escL(ab.erro || t("ga_nao_abriu"))}</p>`) : "";
    return `<section class="cartao" aria-labelledby="ga-${+p.id}-h"><h3 id="ga-${+p.id}-h">${escL(p.nome)}</h3>
      <p class="t2 pq">${escL(p.autor_nome)} · ${escL(t("ga_licenca"))}: ${escL(p.licenca_nome || p.licenca)} (${escL(p.licenca)}) · ${+p.revisoes} ${escL(t("ga_revisoes"))}${p.curada ? " · " + escL(t("ga_curada")) : ""}</p>
      ${p.descricao ? `<p>${escL(p.descricao)}</p>` : ""}
      <div class="acoes"><button class="botao sec" type="button" id="ga-ver-${+p.id}" data-lab="gal-ver" data-id="${+p.id}" aria-describedby="ga-${+p.id}-h" aria-expanded="${ab ? "true" : "false"}">${escL(t("ga_arquivos"))}</button>
        <a class="botao sec" href="/api/publico/3d/pecas/${+p.id}/memorial" aria-describedby="ga-${+p.id}-h">${escL(t("ga_memorial"))}</a></div>${arqs}</section>`;
  }).join("");
}

/* ════════ desenho, idioma, subabas e eventos ════════ */
const TELAS = { arquivo: telaArquivo, lugar: telaLugar, edificacao: telaBim, montagem: telaMontagem, pecas: telaPecas, simulacao: telaSimulacaoBlocos, fila: telaFila, galeria: telaGaleria };
function aplicarIdioma() {
  document.documentElement.lang = lang === "en" ? "en" : "pt-BR";
  document.querySelectorAll("[data-t]").forEach(el => { const v = t(el.getAttribute("data-t")); if (typeof v === "string") el.textContent = v; });
  document.querySelectorAll("[data-t-rot]").forEach(el => { const v = t(el.getAttribute("data-t-rot")); if (typeof v === "string") el.setAttribute("aria-label", v); });
  SUBABAS.forEach(([k], i) => { const e = document.getElementById("tab-" + k); if (e) e.textContent = (i + 1) + ". " + t("abas")[k]; });
}
function desenhar() {
  aplicarIdioma();
  const alvo = document.getElementById("lab");
  let h = (TELAS[abaLab] || telaArquivo)();
  h = h.replace(/<h1(\s[^>]*)?>/g, "<h2$1>").replace(/<\/h1>/g, "</h2>");      // um título só por tela: o logo
  alvo.innerHTML = recolorir(h);
  alvo.setAttribute("aria-labelledby", "tab-" + abaLab);
  document.getElementById("lab-proj").innerHTML = barraProjeto();
  SUBABAS.forEach(([k]) => { const e = document.getElementById("tab-" + k), sim = k === abaLab; e.setAttribute("aria-selected", String(sim)); e.tabIndex = sim ? 0 : -1; });
  document.title = "InovaSTEM · " + t("nav_modelagem") + " · " + t("abas")[abaLab];
  desenhado = true;
  posDesenho();
}
/* depois do HTML: as vistas 3D voltam para o lugar delas (o mesmo canvas, sem perder nada) */
function posDesenho() {
  if (abaLab === "arquivo") posArquivo();
  const tira = ok => { const c = document.getElementById("bim-vista-carregando"); if (c) { if (ok) c.remove(); else c.textContent = t("sem_three"); } };
  if (abaLab === "edificacao" && window.PhysisModelagem) { if (window.THREE) tira(editorBim().anexar(document.getElementById("bim-vista"))); else anexarVista("bim-vista", editorBim(), false).then(tira); }
  if (abaLab === "montagem" && window.PhysisModelagem) { if (window.THREE) editorMo().anexar(document.getElementById("mo-vista")); else anexarVista("mo-vista", editorMo(), false); }
}
/* durante a modelagem: redesenha a subaba e devolve o foco à vista (o canvas é o mesmo; volta para o lugar dele) */
function desenharSemVista() {
  const ativo = document.activeElement, eraVista = ativo && ativo.tagName === "CANVAS", y = window.scrollY;
  desenhar(); if (eraVista && ativo.isConnected) ativo.focus({ preventScroll: true }); window.scrollTo(0, y);
}
window.__p3dDesenhar = desenhar;
function focar(id) { const e = id && document.getElementById(id); if (e && !e.disabled) e.focus(); else document.getElementById("lab").focus(); }
function aoEntrar() {
  if (abaLab === "fila") carregarFila().then(() => { if (abaLab === "fila") { desenhar(); if (lab.filaArq) focar("fi-arq-h"); } });
  if (abaLab === "galeria" && (!lab.gal || !lab.gal.j || !lab.gal.j.ok)) carregarGaleria().then(() => { if (abaLab === "galeria") desenhar(); });
  if ((abaLab === "edificacao" || abaLab === "montagem" || abaLab === "arquivo") && window.PhysisModelagem) window.PhysisModelagem.carregar(["three"]).then(() => { if (desenhado) posDesenho(); }).catch(() => {});
}
function irLab() {
  const h = decodeURIComponent(location.hash.replace(/^#/, "")), alvo = ANTIGAS[h] || h;
  if (SUBABAS.some(s => s[0] === alvo)) {
    abaLab = alvo;
    if (ANTIGAS[h]) { try { history.replaceState(null, "", "#" + alvo); } catch (e) {} }
  } else if (desenhado) return;                    // "#conteudo" e outras âncoras: a subaba fica
  else abaLab = "arquivo";
  aoEntrar(); desenhar();
}
document.getElementById("lab-abas").addEventListener("keydown", ev => {
  const i = SUBABAS.findIndex(s => s[0] === abaLab), n = SUBABAS.length;
  const novo = ev.key === "ArrowRight" ? (i + 1) % n : ev.key === "ArrowLeft" ? (i - 1 + n) % n : ev.key === "Home" ? 0 : ev.key === "End" ? n - 1 : ev.key === " " ? i : null;
  if (novo == null) return;
  ev.preventDefault();
  const k = SUBABAS[novo][0];
  if (location.hash !== "#" + k) location.hash = "#" + k;
  focar("tab-" + k);
});
async function acao(a, b) {
  const fen = FEN.filter(f => f.id === b.getAttribute("data-fen"))[0];
  if (a === "proj-exportar") { baixar("inovastem-projeto-" + agora().slice(0, 10) + ".json", JSON.stringify(proj, null, 1), "application/json"); lab.proj = { texto: t("proj_baixado") }; return; }
  if (a === "proj-limpar") {
    if (!lab.limpar) { lab.limpar = true; lab.proj = { texto: t("proj_confirmar_msg") }; return; }
    lab.limpar = false; proj = projetoVazio(); if (edBim) edBim.limpar(); if (edMo) edMo.limpar(); gravarProjeto(t("proj_novo"), true); return;
  }
  lab.limpar = false;
  if (a === "lugar-navegador") { let g = null; try { g = JSON.parse(localStorage.getItem("physis-geometria-lugar") || "null"); } catch (e) {}
    lab.lugar = g ? importarLugar(g, t("lg_nav_origem"), "") : { texto: t("lg_nenhum"), erro: true }; return; }
  if (a === "lugar-tirar") { proj.lugar = null; gravarProjeto(t("lg_tirado")); lab.lugar = { texto: t("lg_tirado") }; return; }
  if (a === "peca-guardar") { lab.peca = await guardarPeca(); return; }
  if (a === "peca-tirar") { proj.pecas.splice(+b.getAttribute("data-i"), 1); gravarProjeto(t("pc_tirada")); lab.peca = { texto: t("pc_tirada") }; return; }
  if (a === "peca-imp" || a === "peca-editar") { const st = (typeof ui !== "undefined" && ui.p3d) || {}; if (!st.T) { lab.peca = { texto: t("pc_dica"), erro: true }; return; }
    const nome = String(st.nome || "peca").replace(/\.[^.]+$/, "");
    if (a === "peca-imp") { pedirImpressaoDe(nome + ".stl", stlDe(st.T, nome), t("abas").pecas); return "fica"; }
    editorBim().adicionar({ nome, tipo: "malha", T: st.T instanceof Float32Array ? st.T : new Float32Array(st.T), origem: "pecas" }); edBim._enq = false; irPara("edificacao"); return "fica"; }
  if (a === "res-tirar") { proj.resultados.splice(+b.getAttribute("data-i"), 1); gravarProjeto(t("si_res_guardado")); return; }
  if (a === "sim-rodar" && fen) { rodarFen(fen); return; }
  if (a === "sim-repor" && fen) { const st = estSim(fen).st; st.entrada = null; st.res = null; st.c2 = null; st.aberta = false; st.msg = { texto: t("si_reposto") }; return; }
  if (a === "sim-guardar" && fen) { estSim(fen).st.msg = guardarResultado(fen); return; }
  if (a === "fila-recarregar") { await carregarFila(); return; }
  if (a === "fila-descartar") { lab.filaArq = null; return; }
  if (a === "fila-estado") {
    const id = +b.getAttribute("data-id"), estado = b.getAttribute("data-estado"), mot = document.getElementById("fe-mot-" + id);
    const r = await postJ("/api/inovastem/impressao/estado", { id, estado, motivo: mot ? mot.value : "" });
    lab.filaMsg = r.ok ? { texto: t("fi_pedido") + " " + id + ": " + (t("estados")[r.estado] || r.estado) + "." } : { texto: r.erro || t("fi_nao_mudou"), erro: true };
    await carregarFila(); return;
  }
  if (a === "gal-ver") { const id = +b.getAttribute("data-id"); if (lab.gal.abertas[id]) { delete lab.gal.abertas[id]; return; }
    const j = lab.gal.abertas[id] = await getJ("/api/publico/3d/pecas/" + id);
    if (j.ok && j.peca) { registrarPasso("galeria", j.peca.nome); gravarProjeto(""); } return; }
  if (a === "arq-malha" && lab.arq && lab.arq.arquivo) { abrirEmPecas(lab.arq.arquivo, t("ar_malha_t")); return "fica"; }
  if (a === "arq-malha-imp" && lab.arq && lab.arq.arquivo) { const f = lab.arq.arquivo, buf = await f.arrayBuffer();
    if (/\.obj$/i.test(f.name)) pedirImpressaoDe(lab.arq.base + ".stl", stlDe(PHYSIS3D.lerMalha(buf, f.name), lab.arq.base), t("abas").arquivo);
    else pedirImpressaoDe(f.name, buf, t("abas").arquivo); return "fica"; }
  if (a === "arq-bim" && lab.arq && lab.arq.arquivo) { irPara("edificacao"); lab.bimMsg = { texto: t("lendo") }; desenhar(); lab.bimMsg = await abrirCad(lab.arq.arquivo); desenhar(); return "fica"; }
  if (/^arq-(svg|dxf|stl|3mf|enviar|imp|editar)$/.test(a) && lab.arq && lab.arq.r && lab.arq.r.T) {
    const r = lab.arq.r, nome = lab.arq.base;
    if (a === "arq-svg") baixar(nome + "-cad.svg", PhysisImagem3D.svg(r.lacos, r.larg, r.alt), "image/svg+xml");
    if (a === "arq-dxf") baixar(nome + "-cad.dxf", PhysisImagem3D.dxf(r.lacos), "application/dxf");
    if (a === "arq-stl") baixar(nome + ".stl", PHYSIS3D.escreverSTL(r.T, nome), "model/stl");
    if (a === "arq-3mf") baixar(nome + ".3mf", PHYSIS3D.escrever3MF(r.T), "model/3mf");
    if (a === "arq-enviar") { abrirEmPecas(new File([stlDe(r.T, nome)], nome + ".stl", { type: "model/stl" }), t("ar_t")); return "fica"; }
    if (a === "arq-imp") { pedirImpressaoDe(nome + ".stl", stlDe(r.T, nome), t("ar_t")); return "fica"; }
    if (a === "arq-editar") { const E = editorBim(), alt = lab.arq.par.altura + lab.arq.par.base;
      if (r.lacos.length && !lab.arq.par.base) E.adicionar({ nome, tipo: "perfil", lacos: r.lacos, altura: lab.arq.par.altura, origem: "imagem" });
      else E.adicionar({ nome, tipo: "malha", T: r.T, origem: "imagem" });
      E._enq = false; registrarPasso("edificacao", nome); irPara("edificacao"); return "fica"; }
    lab.arqMsg = { texto: t("baixado") }; return;
  }
  if (a === "teste-baixar" || a === "teste-abrir" || a === "teste-imp") { const tp = testesProntos().filter(x => x.id === b.getAttribute("data-id"))[0]; if (!tp) return;
    if (a === "teste-baixar") { baixar(tp.id + ".stl", PHYSIS3D.escreverSTL(tp.T, tp.id), "model/stl"); return; }
    if (a === "teste-imp") { pedirImpressaoDe(tp.id + ".stl", stlDe(tp.T, tp.id), t("tp_t")); return "fica"; }
    abrirEmPecas(new File([stlDe(tp.T, tp.id)], tp.id + ".stl", { type: "model/stl" }), t("tp_t")); return "fica"; }
  // ferramentas e painéis dos editores (Modelos BIM: bim-*, Montagens: mo-*)
  const m = /^(bim|mo)-(ferr|sel|vis|apagar|dup|exp|tirar)$/.exec(a);
  if (m) {
    const pre = m[1], E = pre === "bim" ? editorBim() : editorMo(), id = b.getAttribute("data-id");
    if (m[2] === "ferr") { const k = b.getAttribute("data-f");
      if (k === "desfazer") E.desfazer(); else if (k === "refazer") E.refazer(); else if (k === "enquadrar") E.enquadrar(); else { E.ferramenta = k; E.esboco = []; }
      return; }
    if (m[2] === "sel") { E.selecionar(id); return; }
    if (m[2] === "vis") { const o = E.obj(id); if (o) E.alterar(id, { visivel: o.visivel === false }); return; }
    if (m[2] === "apagar" && E.sel) { E.apagar(E.sel); return; }
    if (m[2] === "tirar") { E.apagar(id); return; }
    if (m[2] === "dup" && E.sel) { const o = E.obj(E.sel), c = Object.assign({}, o, { id: undefined, nome: o.nome + " (2)", pos: [o.pos[0] + 10 * E.passo, o.pos[1], o.pos[2]], rot: o.rot.slice(), _piv: null, _T: null });
      delete c.id; E.adicionar(c); return; }
    if (m[2] === "exp") { const r = exportarDe(E, b.getAttribute("data-fmt"), pre, pre === "mo" ? "montagem" : ((proj.edificacao && proj.edificacao.arquivo) || "modelo").replace(/\.[^.]+$/, ""));
      if (r === "fica") return "fica"; if (pre === "bim") lab.bimMsg = r; else lab.moMsg = r; return; }
  }
}
document.addEventListener("click", ev => {
  const b = ev.target && ev.target.closest ? ev.target.closest("[data-lab]") : null;
  if (!b || b.disabled) return;
  const a = b.getAttribute("data-lab");
  if (a === "sim-ir") { const s = document.getElementById("fen-" + b.getAttribute("data-fen")); if (s) { s.scrollIntoView(); s.focus(); } return; }
  const id = b.id;
  acao(a, b).then(fica => { if (fica === "fica") return; desenhar(); focar(id); });
});
document.addEventListener("change", async ev => {
  const tg = ev.target;
  if (!tg || !tg.getAttribute) return;
  const sel = tg.getAttribute("data-lab-sel"), chk = tg.getAttribute("data-lab-chk"), arq = tg.getAttribute("data-lab-arq");
  if (sel) { const st = estSim(FEN.filter(f => f.id === sel)[0]).st; st.caso = tg.value; st.entrada = null; st.res = null; st.c2 = null; st.msg = null; desenhar(); focar(tg.id); return; }
  if (chk) { estSim(FEN.filter(f => f.id === chk)[0]).st.usarLugar = tg.checked; desenhar(); focar(tg.id); return; }
  if (tg.getAttribute("data-lab-chk2")) { lab.bimSoSel = tg.checked; return; }
  if (tg.getAttribute("data-lab-par") && lab.arq) { lerParametros(); processarArquivo(); desenhar(); focar(tg.id); return; }
  if (tg.getAttribute("data-lab-prim")) { lab.prim = tg.value; desenhar(); focar(tg.id); return; }
  if (tg.getAttribute("data-lab-cfg")) { const E = editorBim(); E.passo = Math.max(0.01, numL((document.getElementById("bim-grade") || {}).value, E.passo));
    E.alturaNova = Math.max(0.01, numL((document.getElementById("bim-alt-nova") || {}).value, E.alturaNova)); return; }
  if (tg.getAttribute("data-lab-momat")) { editorMo().alterar(tg.getAttribute("data-lab-momat"), { material: tg.value }); desenhar(); focar(tg.id); return; }
  if (tg.getAttribute("data-lab-mocor")) { editorMo().alterar(tg.getAttribute("data-lab-mocor"), { cor: tg.value }); desenhar(); focar(tg.id); return; }
  if (!arq) return;
  const f = tg.files && tg.files[0], id = tg.id;
  if (arq === "enviar") { lab.arqMsg = { texto: t("lendo") }; desenhar(); lab.arqMsg = await receberArquivo(f); desenhar(); focar(id); return; }
  if (arq === "bim") { lab.bimMsg = { texto: t("bim_carregando") }; desenhar(); lab.bimMsg = await abrirCad(f); desenhar(); focar(id); return; }
  if (arq === "montagem") { try { if (!f) throw new Error(t("escolha_arquivo")); if (f.size > ARQ_MAX) throw new Error(t("grande"));
      montagemAdd({ nome: f.name.replace(/\.[^.]+$/, ""), T: PHYSIS3D.lerMalha(await f.arrayBuffer(), f.name), origem: "arquivo" }); registrarPasso("montagem", f.name); lab.moMsg = { texto: f.name }; }
    catch (e) { lab.moMsg = { texto: String(e && e.message || e), erro: true }; } desenhar(); focar(id); return; }
  let m;
  try {
    const o = await lerArquivoJson(f);
    if (arq === "projeto") { const p = projetoValido(o); if (!p) throw new Error(t("proj_nao") + " " + ESQ_PROJETO + ".");
      proj = p; if (edBim) { edBim.limpar(); if (p.edificacao && p.edificacao.objetos) edBim.deJson(p.edificacao.objetos); }
      gravarProjeto(t("proj_importado") + " " + f.name + ".", true); lab.limpar = false; }
    else if (arq === "lugar") { m = importarLugar(o, t("lg_arquivo_origem"), f.name); lab.lugar = m; }
  } catch (e) {
    m = { texto: String(e && e.message || e), erro: true };
    if (arq === "projeto") lab.proj = m; else lab.lugar = m;
  }
  desenhar(); focar(id);
});
document.addEventListener("submit", async ev => {
  const fm = ev.target; if (!fm || !fm.id) return;
  if (fm.id === "ar-form") { ev.preventDefault(); if (lab.arq) { lerParametros(); processarArquivo(); desenhar(); focar("ar-atualizar"); } return; }
  if (fm.id === "pr-form") { ev.preventDefault(); acrescentarPrimitiva(); desenhar(); focar("pr-add"); return; }
  if (fm.id === "bim-sel-form" || fm.id === "mo-sel-form") { ev.preventDefault(); const pre = fm.id.split("-")[0]; aplicarSelecionado(pre === "bim" ? editorBim() : editorMo(), pre); desenhar(); focar(pre + "-aplicar"); return; }
  if (fm.id === "mo-add-form") { ev.preventDefault(); lab.moMsg = await acrescentarNaMontagem((document.getElementById("mo-fonte") || {}).value || ""); if (lab.moMsg && !lab.moMsg.erro) registrarPasso("montagem", lab.moMsg.texto); desenhar(); focar("mo-add"); return; }
  if (fm.id === "fila-arq-form") { ev.preventDefault(); const A = lab.filaArq; if (!A) return;
    if (A.tamanho > ARQ_MAX) { lab.filaMsg = { texto: t("grande"), erro: true }; desenhar(); return; }
    lab.filaMsg = { texto: t("fi_enviando") }; desenhar();
    const up = await postBytes("/api/inovastem/impressao/arquivo", A.bytes, A.nome);
    let r = up;
    if (up.ok) r = await postJ("/api/inovastem/impressao", { arquivo: up.arquivo, material: (document.getElementById("fa-mat") || {}).value || "", observacao: (document.getElementById("fa-obs") || {}).value || "" });
    lab.filaMsg = r.ok ? { texto: t("fi_pedido") + " " + r.id + " " + t("fi_enviado") } : { texto: r.erro || t("fi_nao_pediu"), erro: true };
    if (r.ok) { registrarPasso("fila", t("fi_pedido") + " " + r.id + ": " + A.nome); gravarProjeto(""); lab.filaArq = null; }
    await carregarFila(); desenhar(); focar(r.ok ? "fi-msg" : "fa-enviar"); return; }
  if (fm.id !== "fila-form") return;
  ev.preventDefault();
  const v = i => (document.getElementById(i) || {}).value || "";
  const peca = parseInt(v("fi-peca"), 10);
  if (!(peca > 0)) { lab.filaMsg = { texto: t("fi_escolha"), erro: true }; desenhar(); focar("fi-peca"); return; }
  const r = await postJ("/api/inovastem/impressao", { peca, material: v("fi-mat"), observacao: v("fi-obs") });
  lab.filaMsg = r.ok ? { texto: t("fi_pedido") + " " + r.id + " " + t("fi_enviado") } : { texto: r.erro || t("fi_nao_pediu"), erro: true };
  if (r.ok) { registrarPasso("fila", t("fi_pedido") + " " + r.id); gravarProjeto(""); }
  await carregarFila(); desenhar(); focar(r.ok ? "fi-msg" : "fi-peca");
});
proj = lerProjeto();
window.addEventListener("hashchange", irLab);
irLab();
if (proj.edificacao && proj.edificacao.objetos && window.PhysisModelagem) { editorBim().deJson(proj.edificacao.objetos); }
if (proj.montagem && proj.montagem.itens && proj.montagem.itens.length) { /* as malhas da montagem não ficam no JSON: a lista volta vazia (exporte o 3MF para guardar) */ }
"""


def ler(p: Path) -> str:
    return p.read_text(encoding="utf-8").replace("\r\n", "\n")


def montar() -> str:
    site = ler(WEB / "inovastem.html")
    estilo = re.search(r"<style>\n(.*?)</style>", site, re.S).group(1)
    logo = re.search(r'(<h1 class="logo">.*?</h1>)', site, re.S).group(1)
    pref = ler(SIS / "physis-preferencias.js")
    prem3d = json.dumps(json.loads(ler(SIS / "physis-3d-premissas.json")), ensure_ascii=False)
    blocos = "\n".join(f'<script id="{i}">\n{ler(a)}</script>' for i, a in BLOCOS)
    casca = (CASCA_JS.replace("__CORES__", json.dumps(CORES)).replace("__ESQ_PROJETO__", ESQUEMA_PROJETO)
             .replace("__SUBABAS__", json.dumps([list(s) for s in SUBABAS], ensure_ascii=False)))
    abas = "\n    ".join(f'<a role="tab" id="tab-{k}" href="#{k}" aria-controls="lab" aria-selected="{"true" if i == 0 else "false"}" '
                         f'tabindex="{0 if i == 0 else -1}">{i + 1}. {n}</a>' for i, (k, n) in enumerate(SUBABAS))
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>InovaSTEM · Modelagem Physis 3D</title>
<meta name="description" content="Modelagem Physis 3D da InovaSTEM, aberta a qualquer assunto: enviar arquivo (foto para CAD 2D e 3D), lugar (GIS), modelos BIM (CAD e IFC), montagens, peças 3D, simulação por fenômeno, fila de impressão e galeria, com um projeto comum, no navegador. Versão beta.">
<!-- GERADO por ferramentas/montar_lab_inovastem.py. Não edite aqui: edite os originais e rode o gerador. -->
<script>(function(){{var r=document.documentElement,t=null,p=null;try{{p=JSON.parse(localStorage.getItem("physis-pref")||"null");t=p&&p.tema||localStorage.getItem("physis-pref-tema");}}catch(e){{}}if(t!=="claro"&&t!=="escuro"){{try{{t=matchMedia("(prefers-color-scheme: dark)").matches?"escuro":"claro";}}catch(e){{t="claro";}}}}r.setAttribute("data-tema",t);}})();</script>
<style>
{estilo}{CASCA_CSS}</style>
<script type="application/json" id="base-3d-premissas">{prem3d}</script>
</head>
<body>
<a class="pular" href="#conteudo" data-t="pular">Pular para o conteúdo</a>
<div class="endosso"><div class="in"><span data-t="endosso_a">uma iniciativa</span> <span class="marca-physis">Physis</span> <span data-t="endosso_b"></span></div></div>
<header>
  <div class="in">
    <div class="ferramentas" id="pp-lugar" data-physis-preferencias="lugar"></div>
    <div class="cabeca">
      {logo.replace('href="#inicio"', 'href="/"')}
      <nav class="abas" aria-label="Seções do site" data-t-rot="nav"><ul>
        <li><a href="/#delas" class="delas" data-t="nav_delas">InovaSTEM Delas</a></li><li><a href="/#desafios" data-t="nav_desafios">Desafios e projetos</a></li>
        <li><a href="/#forum" data-t="nav_forum">Fórum</a></li><li><a href="/#modelagem" aria-current="page" data-t="nav_modelagem">Modelagem Physis 3D</a></li>
        <li><a href="/#hackathon" data-t="nav_hackathon">Hackathon</a></li><li><a href="/#materiais" data-t="nav_materiais">Materiais</a></li></ul></nav>
      <a class="botao" href="/#participar" data-t="inscreva">Inscreva-se</a>
    </div>
    <p class="sub"><span data-t="sub">Modelagem Physis 3D · roda no seu navegador</span> <span class="beta" data-t="beta">versão beta</span></p>
  </div>
</header>
<main id="conteudo" class="in" tabindex="-1">
  <h2 class="lab-intro" data-t="titulo">Modelagem Physis 3D</h2>
  <p data-t="intro">A bancada de desenvolvimento da InovaSTEM, aberta a modelagens de qualquer assunto: subabas que leem e gravam um projeto comum, num fluxo do arquivo até a fila de impressão e a galeria.</p>
  <section class="lab-projeto" id="lab-proj" aria-label="Projeto comum" data-t-rot="proj_rot"></section>
  <div class="lab-abas" id="lab-abas" role="tablist" aria-label="Subabas da Modelagem Physis 3D" data-t-rot="abas_rot">
    {abas}
  </div>
  <p class="faixa" role="note" data-t="faixa">Em desenvolvimento (Fase 1). Pré-dimensionamento para aprender e testar ideias: não aprova projeto, não substitui norma nem ensaio. Os exemplos usam dados fictícios. O que você abre ou envia aqui fica no seu computador; só vai para o servidor da InovaSTEM quando você pede (pedir impressão, enviar peça à Biblioteca).</p>
  <div id="lab" role="tabpanel" tabindex="0" aria-labelledby="tab-arquivo"></div>
</main>
<footer><div class="in"><p><strong data-t="rodape_realiza">InovaSTEM · uma iniciativa PHYSIS</strong> · <span data-t="rodape_entidade">Physis Engineering · CNPJ [MARCADOR] · Petrópolis (RJ) · Contato: [MARCADOR]</span></p>
  <p data-t="rodape_beta">Versão beta: termos e aviso de privacidade em revisão jurídica.</p>
  <ul><li><a href="/#termos" data-t="termos">Termos de uso (beta)</a></li><li><a href="/#privacidade" data-t="privacidade">Privacidade (beta)</a></li><li><a href="/acessibilidade" data-t="acessibilidade">Acessibilidade</a></li></ul></div></footer>
<script>const ui = {{}};</script>
{blocos}
<script id="lab-inovastem">
{casca}</script>
<script id="physis-preferencias">
{pref}</script>
<script id="pp-site">
PxPref.iniciar({{ lugar:"#pp-lugar", conteudo:"#conteudo", tela:"lab-inovastem", aoMudar: () => desenhar(),
  idioma:{{ atual:() => lang, definir:v => {{ lang = v === "en" ? "en" : "pt"; try {{ localStorage.setItem("physis-idioma", lang); }} catch (e) {{}} desenhar(); }} }} }});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    SAIDA.write_text(montar(), encoding="utf-8", newline="\n")
    print(f"{SAIDA.relative_to(RAIZ)}: {SAIDA.stat().st_size // 1024} kB")
