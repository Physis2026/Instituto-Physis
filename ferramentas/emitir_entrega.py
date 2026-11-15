#!/usr/bin/env python3
"""Monta a entrega completa do Sistema Physis, tudo na MESMA versão (um commit), conforme o
documento 20 (checklist de envio):

  python ferramentas/emitir_entrega.py --docs "<pasta Documents/Sistema Physis>" [--saida <pasta>]

Antes de montar, confere:
- repositório sem mudanças fora do Git;
- testes passando;
- nenhum banco de teste, .env ou segredo nos arquivos de saída.

Tudo sai de um `git archive` do commit atual, nunca da pasta de trabalho, para que pacotes, módulos,
kits, memos e tarefas sejam a mesma versão. No fim grava `MANIFESTO.json` com o SHA-256 de cada arquivo.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
GIT = shutil.which("git") or r"C:\Program Files\Git\cmd\git.exe"
PY = sys.executable
SEGREDO = re.compile(r"(BEGIN [A-Z ]*PRIVATE KEY|phk_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[0-9A-Za-z-]{10,})")
PROIBIDOS = (".db", ".db-wal", ".db-shm", ".env", ".jks", ".keystore", ".pfx", ".p12")
DOCS_INICIAIS = re.compile(r"^(0\d|1\d|2\d)_.+\.(md|json)$")


def rodar(cmd, cwd=None, check=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise SystemExit(f"falhou: {' '.join(map(str, cmd))}\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    return r


def zipar(pasta: Path, destino: Path, raiz_nome: str | None = None):
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for arq in sorted(pasta.rglob("*")):
            if arq.is_file() and not arq.name.endswith(PROIBIDOS) and "__pycache__" not in arq.parts:
                z.write(arq, Path(raiz_nome or pasta.name) / arq.relative_to(pasta))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--docs", type=Path, required=True)
    ap.add_argument("--saida", type=Path)
    ap.add_argument("--sem-testes", action="store_true", help="só para ensaio: não roda a suíte")
    ap.add_argument("--intermediaria", action="store_true",
                    help="versão intermediária: sai da pasta de trabalho como está, substitui a saída e registra os testes sem bloquear")
    a = ap.parse_args()

    # 1. mesma versão: final = repositório limpo e um commit; intermediária = retrato da pasta de trabalho
    base = rodar([GIT, "rev-parse", "--short", "HEAD"], cwd=RAIZ).stdout.strip()
    sujo = rodar([GIT, "status", "--porcelain"], cwd=RAIZ).stdout.strip()
    if sujo and not a.intermediaria:
        raise SystemExit("há mudanças fora do Git. Faça o commit antes de emitir (ou use --intermediaria):\n" + sujo[:2000])
    commit = base + ("-intermediaria" if a.intermediaria else "")
    hoje = datetime.date.today().isoformat()
    saida = a.saida or a.docs / "sistema_physis_fase1"
    if saida.exists():
        if not a.intermediaria and not (saida / "MANIFESTO.json").is_file():
            raise SystemExit(f"{saida} existe e não é uma entrega; escolha outra --saida")
        shutil.rmtree(saida)          # mesma pasta, versão nova (a anterior é substituída)

    tmp = Path(tempfile.mkdtemp(prefix="physis-entrega-"))
    resultado_testes = "não rodados"
    try:
        rep = tmp / "repo"
        arq_zip = tmp / "repo.zip"
        if a.intermediaria:
            shutil.copytree(RAIZ, rep, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.db", "*.db-wal", "*.db-shm",
                                                                       "node_modules", "www", "*.env", "*.jks", "*.keystore"))
            zipar(rep, arq_zip, "sistema-physis")
        else:
            rodar([GIT, "archive", "--format=zip", "-o", str(arq_zip), "HEAD"], cwd=RAIZ)
            with zipfile.ZipFile(arq_zip) as z:
                z.extractall(rep)
        if not a.sem_testes:
            r = rodar([PY, "-m", "unittest", "discover", "-s", "tests"], cwd=rep / "physis-hub", check=False)
            resumo = [l for l in (r.stderr or "").splitlines() if l.startswith(("Ran ", "OK", "FAILED", "FAIL:", "ERROR:"))]
            resultado_testes = " · ".join(resumo[-6:]) or "sem resumo"
            if r.returncode != 0 and not a.intermediaria:
                raise SystemExit("os testes não passaram; nada foi emitido.\n" + r.stderr[-3000:])
        saida.mkdir(parents=True)
        P = lambda nome: (saida / nome).mkdir(parents=True, exist_ok=True) or saida / nome

        # 01 documentos: iniciais (00–2x), memos da Fase 2, tarefas da Gestão
        d = P("01_Documentos")
        for f in sorted(a.docs.iterdir()):
            if f.is_file() and DOCS_INICIAIS.match(f.name):
                shutil.copy2(f, d / f.name)
        if (a.docs / "19_Memos_Fase2").is_dir():
            shutil.copytree(a.docs / "19_Memos_Fase2", d / "19_Memos_Fase2")
        g = P("10_Gestao_tarefas_Fase2")
        if (a.docs / "18_Checklist_para_importar_na_Gestao.json").is_file():
            shutil.copy2(a.docs / "18_Checklist_para_importar_na_Gestao.json", g / "tarefas_fase2_importar_na_gestao.json")

        # 02 páginas completas (abrem direto no navegador)
        pg = P("02_Paginas_completas")
        paginas = {"physis-hub/web/painel.html": "site-loja-e-plataforma.html", "physis-hub/web/consultoria.html": "consultoria.html",
                   "sistema/gestao-interna-physis.html": "gestao-interna.html", "sistema/physis-scada-demo.html": "scada-supervisorio.html",
                   "sistema/SustainKit_Definitivo.html": "sustainkit.html", "modulos/planejador/planejador-physis.html": "planejador.html",
                   "physis-hub/web/municipio.html": "painel-municipal.html",
                   "physis-hub/web/documento.html": "documento-para-comentarios.html", "app-nativo/site/baixar.html": "baixar-o-app.html"}
        for orig, nome in paginas.items():
            if (rep / orig).is_file():
                shutil.copy2(rep / orig, pg / nome)
        (pg / "index.html").write_text(capa(sorted(p.name for p in pg.glob("*.html")), commit, hoje), encoding="utf-8")

        # 03 demos do site (dados simulados)
        if (rep / "demos").is_dir():
            dm = P("03_Demos_site")
            for f in (rep / "demos").glob("*.html"):
                shutil.copy2(f, dm / f.name)

        # 04 pacotes de instalação de cada cliente e do servidor da Physis/Instituto (montar_clientes)
        pc = P("04_Pacotes_instalacao")
        rodar([PY, "montar_clientes.py", "--saida", str(tmp / "pacotes")], cwd=rep / "physis-hub")
        for z in (tmp / "pacotes").glob("*.zip"):
            shutil.copy2(z, pc / z.name)

        # 05 pacote de cada módulo (código + dados + manuais + testes, só leitura)
        mapa = json.loads((rep / "ferramentas" / "kits" / "modulos.json").read_text(encoding="utf-8"))["modulos"]
        md = P("05_Modulos")
        for k in mapa:
            arqs = {e["arquivo"] if isinstance(e, dict) else e for e in k.get("editaveis", [])} | set(k.get("referencia", []))
            alvo = tmp / "mod" / f"modulo-{k['id']}"
            for rel in sorted(arqs):
                if (rep / rel).is_file():
                    (alvo / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(rep / rel, alvo / rel)
            if alvo.exists():
                (alvo / "LEIA-ME.txt").write_text(f"{k['nome']} · responsáveis: {', '.join(k['responsaveis'])} · versão {commit}\n"
                                                  "Cópia só para leitura. Para revisar e devolver, use o kit de revisão deste módulo.\n", encoding="utf-8")
                zipar(alvo, md / f"modulo-{k['id']}_{commit}.zip")

        # 06 kits de revisão (24) com manifestos
        kt = P("06_Kits_revisao")
        rodar([PY, str(rep / "ferramentas" / "gerar_kits_revisao.py"), "--saida", str(kt)], cwd=rep)

        # 07 implantação e serviços abertos · 08 app nativo · 09 código-fonte
        im = P("07_Implantacao_e_servicos")
        for nome in ("implantacao", "servicos"):
            if (rep / nome).is_dir():
                zipar(rep / nome, im / f"{nome}_{commit}.zip")
        if (rep / "app-nativo").is_dir():
            zipar(rep / "app-nativo", P("08_App_nativo") / f"app-nativo_{commit}.zip")
        shutil.copy2(arq_zip, P("09_Codigo_fonte") / f"sistema-physis_{commit}.zip")

        # verificação: nada proibido, nenhum segredo
        problemas = []
        for f in saida.rglob("*"):
            if f.is_file():
                if f.name.endswith(PROIBIDOS):
                    problemas.append(f"arquivo proibido: {f.relative_to(saida)}")
                if f.suffix == ".zip":
                    with zipfile.ZipFile(f) as z:
                        for n in z.namelist():
                            if n.endswith(PROIBIDOS):
                                problemas.append(f"{f.name}: contém {n}")
                elif f.suffix in (".md", ".html", ".json", ".txt", ".py", ".js") and SEGREDO.search(f.read_text("utf-8", "replace")):
                    problemas.append(f"possível segredo em {f.relative_to(saida)}")
        if problemas:
            raise SystemExit("entrega recusada:\n" + "\n".join(problemas[:50]))

        # manifesto e leia-me
        lista = {str(f.relative_to(saida)).replace("\\", "/"): hashlib.sha256(f.read_bytes()).hexdigest()
                 for f in sorted(saida.rglob("*")) if f.is_file()}
        (saida / "MANIFESTO.json").write_text(json.dumps({"commit": commit, "data": hoje, "intermediaria": a.intermediaria,
                                                          "testes": resultado_testes, "arquivos": lista}, ensure_ascii=False, indent=1), encoding="utf-8")
        aviso = ("\n> **Versão intermediária** (trabalho em andamento sobre a versão salva " + base + "). Testes: " + resultado_testes +
                 ". Será substituída pela versão final nesta mesma pasta.\n") if a.intermediaria else ""
        (saida / "LEIA-ME.md").write_text(LEIA.format(commit=commit, hoje=hoje, n=len(lista)) + aviso, encoding="utf-8")
        print(f"entrega pronta: {saida} ({len(lista)} arquivos, versão {commit})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


TELAS = [  # arquivo, nome, o que faz, para quem
    ("site-loja-e-plataforma.html", "Site, loja e plataforma", "A plataforma completa (mapear → modelar → checar → documentar) com a loja; abre em modo de demonstração quando aberta como arquivo.", "clientes e equipe"),
    ("consultoria.html", "Consultoria", "Serviços, fases, consultoria personalizada com equipe multidisciplinar, diárias, casos e pedido de proposta.", "site público"),
    ("planejador.html", "Planejador", "Terreno, GIS, BIM, relevo, APP e normas por bloco. Mapa e BIM completos só com o servidor.", "clientes e equipe"),
    ("sustainkit.html", "SustainKit", "Diagnóstico por blocos: energia, solar, água, resíduos, carbono, certificações, custos.", "clientes e equipe"),
    ("scada-supervisorio.html", "SCADA · supervisório", "Supervisão e controle de bombas, válvulas e energia, com histórico.", "operação"),
    ("gestao-interna.html", "Gestão interna Physis", "Atividades, propostas, contratos, financeiro, editais, eventos, marketing, e-mails, chamados, parceiros.", "só equipe Physis"),
    ("painel-municipal.html", "Painel municipal de resiliência", "Chuva medida, alertas por bairro, rio e risco para Defesa Civil e prefeituras.", "municípios"),
    ("documento-para-comentarios.html", "Documento para comentários", "Relatórios publicados para revisão com comentários por parágrafo.", "equipe e revisores"),
    ("baixar-o-app.html", "Baixar o app", "App para Android e iPhone, APK direto e instalação pelo navegador.", "clientes"),
]


def capa(arquivos, commit, hoje):
    import html as h
    cards = "".join(f'<a class="c" href="{h.escape(a)}"><strong>{h.escape(n)}</strong><span>{h.escape(o)}</span><em>{h.escape(q)}</em></a>'
                    for a, n, o, q in TELAS if a in arquivos)
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sistema Physis · todas as telas</title><style>
:root{{--f:#F4F6F1;--s:#fff;--t:#1C2B21;--t2:#4A5446;--v:#33512F;--l:#C9D2C4}}
@media (prefers-color-scheme:dark){{:root{{--f:#141B16;--s:#1C2620;--t:#E6EDE4;--t2:#B3C0AF;--v:#9CCB92;--l:#334236}}}}
body{{margin:0;background:var(--f);color:var(--t);font:16px/1.5 Lexend,system-ui,sans-serif}}
main{{max-width:1000px;margin:0 auto;padding:24px 16px}}h1{{font:600 2rem/1.2 Fraunces,Georgia,serif;color:var(--v);margin:0 0 6px}}
p{{color:var(--t2)}}.g{{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(260px,1fr))}}
.c{{display:grid;gap:6px;padding:16px;border:1px solid var(--l);border-radius:10px;background:var(--s);color:var(--t);text-decoration:none}}
.c:hover,.c:focus-visible{{border-color:var(--v);outline:3px solid var(--v);outline-offset:2px}}.c strong{{color:var(--v);font-size:1.1rem}}
.c span{{color:var(--t2)}}.c em{{font-style:normal;font-size:.85rem;color:var(--t2)}}</style></head><body><main>
<h1>Sistema Physis · todas as telas</h1><p>Fase 1 · versão {commit} · {hoje}. Cada cartão abre a página correspondente. As demonstrações do site estão na pasta 03_Demos_site.</p>
<div class="g">{cards}</div></main></body></html>"""


LEIA = """# Entrega do Sistema Physis · versão {commit} · {hoje}

Tudo nesta pasta é a **mesma versão** ({commit}). A conferência de cada arquivo (SHA-256) está em `MANIFESTO.json`. São {n} arquivos.

| Pasta | O que é | Para quem |
|---|---|---|
| 01_Documentos | Documentos iniciais (00 a 19) e memos da Fase 2 (um por bloco e um por pessoa) | Equipe toda. Só a lista do Eric (10) sai para fora. |
| 02_Paginas_completas | Site com loja e plataforma, consultoria, Gestão interna, SCADA, SustainKit, Planejador, Tela do cliente, painel municipal, documento para comentários, página do app | Equipe (Gestão interna: só uso interno) |
| 03_Demos_site | Versões reduzidas para o site, com "Demonstração · dados simulados" | Site público |
| 04_Pacotes_instalacao | Pacote de cada cliente, do servidor da Physis e do Instituto Physis | Eric (instalação) |
| 05_Modulos | Código, dados, manuais e testes de cada módulo, só leitura | Responsáveis dos módulos |
| 06_Kits_revisao | 24 kits para revisar e devolver (LEIA-ME, editáveis, prévia, ficha) | Cada responsável; o Eric valida e aplica |
| 07_Implantacao_e_servicos | Instalador do Raspberry Pi e mini PC, backup, serviços abertos | Eric |
| 08_App_nativo | Projeto do app Android e iPhone e página de download | Rafaella, Eric |
| 09_Codigo_fonte | Repositório completo desta versão | Eric |
| 10_Gestao_tarefas_Fase2 | Arquivo para importar na Gestão (Plano de ação → Importar → Substituir) | Rafaella |

Nenhum banco de teste, senha, chave ou arquivo `.env` vai nesta entrega.
"""

if __name__ == "__main__":
    main()
