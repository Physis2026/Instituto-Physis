"""Converte o documento 18 (checklist de implantação) num pacote physis/1 que a Gestão interna importa
(Plano de ação → Importar → Juntar): uma tarefa por pessoa responsável, no projeto "Implantação · <seção>"."""
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

doc = Path(sys.argv[1]).read_text(encoding="utf-8")
saida = Path(sys.argv[2])
IDS = {"Rafaella": "rafaella", "Laura": "laura", "Marzia": "marzia", "Arthur": "arthur", "Erick Lopes": "ericklopes",
       "Ryan": "ryan", "Emerson": "emerson", "Rafael": "rafael", "Eric Oliveira": "erickoliveira", "Eric": "erickoliveira",
       "Leonardo Macedo": "leonardomacedo"}
NOMES = {"rafaella": "Rafaella", "laura": "Laura", "marzia": "Marzia", "arthur": "Arthur", "ericklopes": "Erick Lopes",
         "ryan": "Ryan", "emerson": "Emerson", "rafael": "Rafael", "erickoliveira": "Eric Oliveira",
         "leonardomacedo": "Leonardo Macedo"}
TODOS = [i for i in NOMES if i != "leonardomacedo"]   # Leonardo entra só na revisão das páginas da consultoria
CENTRAL = ["arthur", "rafaella", "ericklopes", "rafael"]


def pessoas_de(txt, padrao):
    t = txt.lower()
    if "toda a equipe" in t:
        return TODOS
    if "os do hardware" in t:
        return ["arthur", "ericklopes", "rafael", "emerson", "erickoliveira"]
    if "central de clientes" in t and "equipe" in t:
        return CENTRAL
    achados = []
    for nome in sorted(IDS, key=len, reverse=True):
        if re.search(r"\b" + re.escape(nome) + r"\b", txt) and IDS[nome] not in achados:
            achados.append(IDS[nome])
            txt = re.sub(r"\b" + re.escape(nome) + r"\b", "", txt)
    return achados or padrao


tarefas, secao, padrao, projeto = [], "", [], ""
for linha in doc.splitlines():
    m = re.match(r"^## (\d+)\. (.+)", linha)
    if m:
        secao = m.group(2).split("(")[0].strip()
        projeto = f"Fase 2 · {m.group(1)}. {secao}"
        padrao = []
        continue
    m = re.match(r"^Responsáve(?:l|is)[^:]*: (.+)", linha)
    if m:
        padrao = pessoas_de(m.group(1), [])
        continue
    m = re.match(r"^\s*(?:\d+\.\s*)?- \[ \] (.+)", linha) or re.match(r"^\s*- \[ \] (.+)", linha)
    if m:
        texto = m.group(1)
        quem_txt = re.findall(r"\(([^()]*)\)\s*$", texto)
        quem = pessoas_de(quem_txt[-1], padrao) if quem_txt else padrao
        t = texto.lower()
        if ("automática" in t and "ia" in t) or re.search(r"autom[aá]tic[oa] pelo sistema", t):
            continue                                   # feito pelo sistema (enquete, manual do cliente): sem pessoa
        titulo = re.sub(r"\s*\(([^()]*)\)\s*$", "", texto) if quem_txt and pessoas_de(quem_txt[-1], []) else texto
        titulo = re.sub(r"\*\*|\*|`", "", titulo).strip()
        tarefas.append((projeto, titulo, quem or ["rafaella"]))
        continue
    m = re.match(r"^\| (?!Módulo|Aparelho|---)([^|]+) \| ([^|]+) \| ([^|]+)(?:\| ([^|]+))?(?:\| ([^|]+))?\|", linha)
    if m:
        item, resp = m.group(1).strip(), m.group(2).strip()
        quem = pessoas_de(resp, padrao)
        if m.group(4):              # hardware: antes de ir a campo / em campo
            tarefas.append((projeto, f"{item}: antes de ir a campo — {m.group(3).strip()}", quem))
            tarefas.append((projeto, f"{item}: em campo — {m.group(4).strip()}", quem))
        else:
            tarefas.append((projeto, f"Revisar {item}: {m.group(3).strip()}", quem))

ORG, agora = "physis", datetime.datetime.now(datetime.timezone.utc).isoformat()
proj_ids, tb_proj, tb_tar = {}, [], []
for projeto, titulo, quem in tarefas:
    pid = "imp-" + hashlib.sha1(projeto.encode()).hexdigest()[:8]
    if pid not in proj_ids:
        proj_ids[pid] = projeto
        tb_proj.append({"org_id": ORG, "projeto_id": pid, "nome": projeto, "extras": {"nomeEn": ""}})
    for p in quem:
        juntos = [NOMES[x] for x in quem if x != p]
        t = titulo + (f" (junto com {', '.join(juntos)})" if juntos else "")
        tid = "imp-" + hashlib.sha1((projeto + "|" + titulo + "|" + p).encode()).hexdigest()[:12]
        tb_tar.append({"org_id": ORG, "tarefa_id": tid, "titulo": t[:300], "pessoa_id": p, "projeto_id": pid,
                       "horizonte": "media", "peso": 3, "concluida": False, "concluida_em": None, "depende_de": None,
                       "extras": {"tituloEn": "", "projeto_nome": projeto}})
pessoas = [{"org_id": ORG, "pessoa_id": k, "nome": v, "papel": "", "idioma": "pt", "extras": {"admin": False, "papelEn": "", "arvore": ""}}
           for k, v in NOMES.items()]
pacote = {"_formato": "physis/1", "_gerado_em": agora, "_gerado_por": "checklist-implantacao", "_app": "gestao-physis",
          "org_id": ORG, "tabelas": {"pessoa": pessoas, "projeto": tb_proj, "tarefa": tb_tar},
          "fluxo_residuo": [], "requisito": [], "indicadores": None, "trilha_auditoria": [],
          "resumo": {"pessoas": len(pessoas), "projetos": len(tb_proj), "tarefas": len(tb_tar), "concluidas": 0, "bloqueadas": 0}}
saida.write_text(json.dumps(pacote, ensure_ascii=False, indent=1), encoding="utf-8")
por = {}
for t in tb_tar:
    por[t["pessoa_id"]] = por.get(t["pessoa_id"], 0) + 1
print(len(tarefas), "atividades ·", len(tb_tar), "tarefas ·", len(tb_proj), "projetos")
print({NOMES[k]: v for k, v in sorted(por.items(), key=lambda x: -x[1])})
