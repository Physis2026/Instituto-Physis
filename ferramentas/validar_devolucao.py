#!/usr/bin/env python3
"""Confere um kit de revisão devolvido e, se pedido, aplica numa ramificação (branch) separada do Git.

    python ferramentas/validar_devolucao.py <zip-ou-pasta-devolvida> [--manifesto <arq>] [--kits <pasta>]
                                            [--aplicar] [--relatorio <arquivo.md>] [--sem-testes]

O que confere (nada é aplicado se houver um erro):
  1. Só mudaram arquivos editáveis do kit (referência mudada, arquivo estranho ou _KIT.json trocado = recusa).
  2. O JSON abre, sem chave repetida, sem NaN; as chaves e os ids continuam os mesmos, os tipos também
     (número continua número; null e [MARCADOR] podem virar valor); registro novo só em lista de registros,
     com todos os campos do modelo; chaves novas só 'conferido', 'fonte', 'data' e 'nota'.
  3. Nenhum endereço de internet, script ou tag HTML entrou; textos dentro do limite.
  4. A parte do arquivo no sistema não mudou desde que o kit foi gerado (senão: junção em 3 vias, à mão).
Com --aplicar (só com a árvore do Git limpa): cria a branch revisao/<modulo>-<data> a partir da atual,
grava as mudanças mantendo a formatação do arquivo, roda o que o arquivo pede (copiar a metodologia
para o JS, embutir bases), roda os testes do módulo e a suíte inteira, faz um commit NA BRANCH e volta
para a branch de antes. Nunca mexe na main, nunca faz push. O Eric lê o relatório e decide o merge.

Saída: 0 = tudo certo; 1 = recusado ou erro; 2 = aplicado na branch, mas algum teste falhou.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import io
import json
import re
import subprocess
import sys
import zipfile
from json.decoder import scanstring
from json.scanner import NUMBER_RE
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gerar_kits_revisao import (ARQ_KIT, FORMATO, LIMITE_TROCA, PAINEL_REL, RAIZ, caminho_texto, git,  # noqa: E402
                                leia_extrato, leia_trocas, pegar, pode_trocar_texto, rotulo, sha256_bytes,
                                sha_canonico, trocar)

LIMITE_ENTRADAS = 5000
LIMITE_BYTES = 300 * 1024 * 1024
LIMITE_TEXTO = 1500
AVISO_TEXTO = 600
LIXO = re.compile(r"(^|/)(__MACOSX/|\.DS_Store$|Thumbs\.db$|desktop\.ini$|~\$[^/]*$)", re.I)
PROIBIDO = [
    (re.compile(r"<\s*/?\s*(script|iframe|object|embed|style|link|meta|img|svg|a|form|input|base|body|html)\b", re.I),
     "tag HTML ou script"),
    (re.compile(r"javascript\s*:|vbscript\s*:|data\s*:\s*text/html", re.I), "código escondido em endereço"),
    (re.compile(r"\bon[a-z]{3,}\s*=", re.I), "evento de script (on...=)"),
]
URL = re.compile(r"(https?|ftp)://[^\s\"'<>]+|\bwww\.[^\s\"'<>]+", re.I)
CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
SEGREDO = re.compile(r"(senha|password|passwd|pass|token|api_?key|apikey|secret|segredo)\w*\s*[:=]\s*[\"']?"
                     r"(?!\[|\$\{|<|!secret|exemplo|troque|CHANGE)[^\s\"'#]{4,}", re.I)
MARCADOR = re.compile(r"^\s*\[[^\]]+\]")
CHAVES_NOVAS = {"conferido", "fonte", "data", "nota"}
CODIGO_TROCA = re.compile(r"[<>{}`;]|=>|script|javascript\s*:|https?:|www\.|\\[nrtu]", re.I)


# ---------------------------------------------------------------- leitura do pacote

def ler_pacote(caminho: Path) -> dict:
    arquivos = {}
    if caminho.is_dir():
        for p in sorted(caminho.rglob("*")):
            if p.is_file():
                arquivos[p.relative_to(caminho).as_posix()] = p.read_bytes()
        return arquivos
    if not zipfile.is_zipfile(caminho):
        raise ValueError(f"{caminho} não é ZIP nem pasta")
    total = 0
    with zipfile.ZipFile(caminho) as z:
        infos = [i for i in z.infolist() if not i.is_dir()]
        if len(infos) > LIMITE_ENTRADAS:
            raise ValueError("ZIP com arquivos demais")
        for i in infos:
            nome = i.filename.replace("\\", "/")
            if nome.startswith("/") or re.match(r"^[A-Za-z]:", nome) or ".." in nome.split("/"):
                raise ValueError(f"caminho perigoso dentro do ZIP: {nome}")
            total += i.file_size
            if total > LIMITE_BYTES:
                raise ValueError("ZIP grande demais")
            arquivos[nome] = z.read(i)
    return arquivos


def separar(pacote: dict) -> dict:
    """Acha editaveis/, referencia/ e a ficha, qualquer que seja a pasta de cima do ZIP."""
    nomes = [n for n in pacote if not LIXO.search(n)]
    prefixos = sorted({n[:n.index("editaveis/")] for n in nomes if "editaveis/" in n and
                       (n.startswith("editaveis/") or n[n.index("editaveis/") - 1] == "/")}, key=len)
    if prefixos:
        pre = prefixos[0]
        ed_pre = pre + "editaveis/"
    else:
        # o revisor compactou o conteúdo de editaveis/ direto
        pre, ed_pre = "", ""
    out = {"editaveis": {}, "referencia": {}, "ficha": None, "manifesto": None, "outros": []}
    for n in nomes:
        if not n.startswith(pre):
            out["outros"].append(n)
            continue
        resto = n[len(pre):]
        base = n.rsplit("/", 1)[-1]
        if base == "FICHA_REVISAO.md":
            out["ficha"] = pacote[n]
        elif resto == "MANIFESTO.json":
            out["manifesto"] = pacote[n]
        elif resto == "LEIA-ME.md":
            continue
        elif resto.startswith("referencia/"):
            out["referencia"][resto] = pacote[n]
        elif n.startswith(ed_pre) and (ed_pre or not resto.startswith("referencia/")):
            out["editaveis"]["editaveis/" + n[len(ed_pre):]] = pacote[n]
        else:
            out["outros"].append(n)
    return out


def achar_manifesto(sep: dict, arg_manifesto: str | None, arg_kits: str | None, avisos: list) -> dict:
    if arg_manifesto:
        return json.loads(Path(arg_manifesto).read_text(encoding="utf-8"))
    kit = None
    marca = sep["editaveis"].get("editaveis/" + ARQ_KIT)
    if marca:
        try:
            kit = json.loads(marca.decode("utf-8-sig")).get("kit")
        except (ValueError, UnicodeDecodeError):
            kit = None
    if kit and arg_kits:
        for c in (Path(arg_kits) / "_manifestos" / f"{kit}.json", Path(arg_kits) / kit / "MANIFESTO.json"):
            if c.is_file():
                return json.loads(c.read_text(encoding="utf-8"))
    if sep["manifesto"]:
        avisos.append("Usei o MANIFESTO.json que veio junto com a devolução. Prefira o guardado na geração "
                      "(--kits <pasta dos kits> ou --manifesto <arquivo>): o que vem do revisor pode ter sido mudado.")
        return json.loads(sep["manifesto"].decode("utf-8-sig"))
    raise ValueError("Não achei o manifesto do kit. Use --kits <pasta onde os kits foram gerados> "
                     "ou --manifesto <arquivo>." + (f" (kit: {kit})" if kit else ""))


# ---------------------------------------------------------------- comparação de estrutura

def categoria(v) -> str:
    if v is None:
        return "nulo"
    if isinstance(v, bool):
        return "verdadeiro/falso"
    if isinstance(v, (int, float)):
        return "número"
    if isinstance(v, str):
        return "texto"
    if isinstance(v, list):
        return "lista"
    return "objeto"


def curto(v, n=70) -> str:
    t = json.dumps(v, ensure_ascii=False)
    return t if len(t) <= n else t[:n - 1] + "…"


def iguais(a, b) -> bool:
    return json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(b, sort_keys=True, ensure_ascii=False)


def chave_id(lista):
    if not lista or not all(isinstance(x, dict) for x in lista):
        return None
    for k in ("id", "n", "codigo"):
        vals = [x.get(k) for x in lista]
        if all(isinstance(v, (str, int)) and not isinstance(v, bool) for v in vals) and \
                len({str(v) for v in vals}) == len(vals):
            return k
    return None


class Contexto:
    def __init__(self, arquivo: str):
        self.arquivo = arquivo
        self.erros, self.avisos, self.mudancas = [], [], []

    def onde(self, cam):
        return f"{self.arquivo} › {caminho_texto(cam)}"


def checar_texto(novo: str, antigo: str, cam, ctx: Contexto):
    for padrao, nome in PROIBIDO:
        if padrao.search(novo) and not padrao.search(antigo or ""):
            ctx.erros.append(f"{ctx.onde(cam)}: entrou {nome}. Os valores são só texto, sem código.")
    urls_antes = {m.group(0) for m in URL.finditer(antigo or "")}
    for m in URL.finditer(novo):
        if m.group(0) not in urls_antes:
            ctx.erros.append(f"{ctx.onde(cam)}: entrou o endereço de internet {m.group(0)!r}. "
                             "Cite a fonte pelo nome (norma, tabela, edição, item), sem link.")
    if CONTROLE.search(novo):
        ctx.erros.append(f"{ctx.onde(cam)}: caractere invisível de controle no texto.")
    limite = max(LIMITE_TEXTO, 2 * len(antigo or "") + 200)
    if len(novo) > limite:
        ctx.erros.append(f"{ctx.onde(cam)}: texto longo demais ({len(novo)} caracteres; limite {limite}).")
    elif len(novo) > AVISO_TEXTO and novo != antigo:
        ctx.avisos.append(f"{ctx.onde(cam)}: texto longo ({len(novo)} caracteres): confira se não é cópia de norma.")


def checar_livre(v, cam, ctx: Contexto, antigo_texto=""):
    """Valor novo sem modelo para comparar (registro novo, null que virou objeto): só confere os textos."""
    if isinstance(v, str):
        checar_texto(v, antigo_texto, cam, ctx)
    elif isinstance(v, dict):
        for k, x in v.items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k):
                ctx.erros.append(f"{ctx.onde(cam)}: nome de chave estranho {k!r}.")
            checar_livre(x, cam + [k], ctx)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            checar_livre(x, cam + [i], ctx)
    elif isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
        ctx.erros.append(f"{ctx.onde(cam)}: número inválido.")


def checar_conferido(v, cam, ctx: Contexto):
    if not isinstance(v, dict):
        ctx.erros.append(f"{ctx.onde(cam)}: 'conferido' tem de ser {{\"por\": ..., \"em\": \"AAAA-MM-DD\", \"fonte\": ...}}.")
        return
    sobra = set(v) - {"por", "em", "fonte", "nota"}
    falta = {"por", "em", "fonte"} - {k for k in v if isinstance(v[k], str) and v[k].strip()}
    if sobra:
        ctx.erros.append(f"{ctx.onde(cam)}: 'conferido' com campo a mais: {', '.join(sorted(sobra))}.")
    if falta:
        ctx.erros.append(f"{ctx.onde(cam)}: 'conferido' sem {', '.join(sorted(falta))} (quem, quando e fonte).")
    if isinstance(v.get("em"), str) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v["em"].strip()):
        ctx.erros.append(f"{ctx.onde(cam)}: 'conferido.em' tem de ser data AAAA-MM-DD.")
    checar_livre(v, cam, ctx)


def checar_registro_novo(item, modelos: list, cam, ctx: Contexto):
    if not isinstance(item, dict):
        ctx.erros.append(f"{ctx.onde(cam)}: item novo tem de ser um registro igual aos outros.")
        return
    obrig = set.intersection(*(set(m) for m in modelos)) if modelos else set()
    aceitas = set.union(*(set(m) for m in modelos)) | CHAVES_NOVAS if modelos else set(item)
    falta, sobra = obrig - set(item), set(item) - aceitas
    if falta:
        ctx.erros.append(f"{ctx.onde(cam)}: registro novo sem os campos {', '.join(sorted(falta))}.")
    if sobra:
        ctx.erros.append(f"{ctx.onde(cam)}: registro novo com campos que o modelo não tem: {', '.join(sorted(sobra))}.")
    for k, v in item.items():
        tipos = {categoria(m[k]) for m in modelos if k in m}
        if k == "conferido":
            checar_conferido(v, cam + [k], ctx)
            continue
        if tipos and categoria(v) not in tipos and "nulo" not in tipos and categoria(v) != "nulo":
            ctx.erros.append(f"{ctx.onde(cam + [k])}: tipo {categoria(v)}, mas nos outros registros é "
                             f"{' ou '.join(sorted(tipos))}.")
        checar_livre(v, cam + [k], ctx)


def comparar(o, n, cam: list, ctx: Contexto):
    if iguais(o, n):
        return
    co, cn = categoria(o), categoria(n)
    if co == "objeto":
        if cn != "objeto":
            ctx.erros.append(f"{ctx.onde(cam)}: era um grupo de campos e virou {cn}.")
            return
        for k in o:
            if k not in n:
                ctx.erros.append(f"{ctx.onde(cam)}: a chave {k!r} foi apagada ou renomeada.")
        for k in n:
            if k in o:
                comparar(o[k], n[k], cam + [k], ctx)
            elif k in CHAVES_NOVAS:
                if k == "conferido":
                    checar_conferido(n[k], cam + [k], ctx)
                elif not isinstance(n[k], str):
                    ctx.erros.append(f"{ctx.onde(cam + [k])}: '{k}' novo tem de ser texto.")
                else:
                    checar_texto(n[k], "", cam + [k], ctx)
                ctx.mudancas.append(f"{ctx.onde(cam)}: acrescentado {k} = {curto(n[k], 120)}")
            else:
                ctx.erros.append(f"{ctx.onde(cam)}: chave nova {k!r} não é permitida "
                                 f"(só {', '.join(sorted(CHAVES_NOVAS))}).")
        return
    if co == "lista" and cn == "lista":
        k = chave_id(o)
        if k:
            if not all(isinstance(x, dict) for x in n):
                ctx.erros.append(f"{ctx.onde(cam)}: a lista de registros recebeu algo que não é registro.")
                return
            ids_n = [str(x.get(k)) for x in n]
            if len(ids_n) != len(set(ids_n)):
                ctx.erros.append(f"{ctx.onde(cam)}: {k} repetido na lista.")
                return
            por_id = {str(x[k]): x for x in n if x.get(k) is not None}
            for x in o:
                seg = f"{k}={x[k]}" + (f" ({rotulo(x)})" if rotulo(x) else "")
                if str(x[k]) not in por_id:
                    ctx.erros.append(f"{ctx.onde(cam + [seg])}: registro apagado ou com {k} trocado.")
                else:
                    comparar(x, por_id[str(x[k])], cam + [seg], ctx)
            velhos = {str(x[k]) for x in o}
            for x in n:
                if x.get(k) is None:
                    ctx.erros.append(f"{ctx.onde(cam)}: registro novo sem {k}.")
                elif str(x[k]) not in velhos:
                    seg = f"{k}={x[k]}"
                    checar_registro_novo(x, o, cam + [seg], ctx)
                    ctx.mudancas.append(f"{ctx.onde(cam)}: registro novo {seg}" +
                                        (f" ({rotulo(x)})" if rotulo(x) else ""))
            return
        if o and all(isinstance(x, dict) for x in o):
            if len(n) < len(o):
                ctx.erros.append(f"{ctx.onde(cam)}: itens apagados da lista ({len(o)} → {len(n)}).")
                return
            for i in range(len(o)):
                comparar(o[i], n[i], cam + [i], ctx)
            for i in range(len(o), len(n)):
                checar_registro_novo(n[i], o, cam + [i], ctx)
                ctx.mudancas.append(f"{ctx.onde(cam)}: item novo {curto(n[i], 100)}")
            return
        # lista de valores (números, textos, pares): troca livre, sem objeto dentro
        tipos = {categoria(x) for x in o}
        for i, x in enumerate(n):
            cx = categoria(x)
            if cx == "objeto" and "objeto" not in tipos:
                ctx.erros.append(f"{ctx.onde(cam + [i])}: entrou um grupo de campos numa lista de valores.")
            elif tipos and cx not in tipos and not (cx == "número" and "nulo" in tipos):
                ctx.erros.append(f"{ctx.onde(cam + [i])}: {cx} numa lista de {' e '.join(sorted(tipos))}.")
            antigos = [y for y in o if isinstance(y, str)]
            checar_livre(x, cam + [i], ctx, antigo_texto=x if x in antigos else "")
        ctx.mudancas.append(f"{ctx.onde(cam)}: era {curto(o)}, ficou {curto(n)}")
        return
    # valores simples
    pode = (co == cn or co == "nulo" or (co == "texto" and MARCADOR.match(o) and cn in ("número", "lista"))
            or (co == "número" and cn == "número"))
    if not pode:
        if cn == "nulo":
            ctx.erros.append(f"{ctx.onde(cam)}: valor apagado (virou null). Se não tem fonte, escreva \"[MARCADOR]\" "
                             "e explique na ficha.")
        else:
            ctx.erros.append(f"{ctx.onde(cam)}: tipo mudou de {co} para {cn} ({curto(o, 40)} → {curto(n, 40)}).")
        return
    if isinstance(n, str):
        checar_texto(n, o if isinstance(o, str) else "", cam, ctx)
    elif isinstance(n, (dict, list)):
        checar_livre(n, cam, ctx)
    elif isinstance(n, float) and (n != n or n in (float("inf"), float("-inf"))):
        ctx.erros.append(f"{ctx.onde(cam)}: número inválido.")
    ctx.mudancas.append(f"{ctx.onde(cam)}: era {curto(o)}, ficou {curto(n)}")


def carregar_json_estrito(b: bytes, ctx: Contexto):
    if b.startswith(b"\xef\xbb\xbf"):
        b = b[3:]
        ctx.avisos.append(f"{ctx.arquivo}: salvo com BOM (marca no início); tudo bem, foi ignorada.")
    try:
        t = b.decode("utf-8")
    except UnicodeDecodeError:
        ctx.erros.append(f"{ctx.arquivo}: não está em UTF-8. Salve de novo como UTF-8.")
        return None

    def pares(ps):
        d = {}
        for k, v in ps:
            if k in d:
                raise ValueError(f"chave repetida {k!r}")
            d[k] = v
        return d

    def constante(c):
        raise ValueError(f"valor {c} não é aceito")

    try:
        return json.loads(t, object_pairs_hook=pares, parse_constant=constante)
    except ValueError as e:
        ctx.erros.append(f"{ctx.arquivo}: o JSON não abre ({e}). Em geral é vírgula ou aspas faltando.")
        return None


# ---------------------------------------------------------------- aplicar mantendo a formatação

class No:
    __slots__ = ("ini", "fim", "tipo", "membros", "itens")

    def __init__(self, ini, tipo):
        self.ini, self.tipo, self.fim, self.membros, self.itens = ini, tipo, None, [], []


_WS = re.compile(r"[ \t\n\r]*")


def analisar(t: str) -> No:
    def ws(i):
        return _WS.match(t, i).end()

    def valor(i):
        i = ws(i)
        c = t[i]
        if c == "{":
            no = No(i, "o")
            i = ws(i + 1)
            if t[i] == "}":
                no.fim = i + 1
                return no, i + 1
            while True:
                i = ws(i)
                ki = i
                k, kf = scanstring(t, i + 1)
                i = ws(kf)
                if t[i] != ":":
                    raise ValueError("JSON inesperado")
                filho, i = valor(i + 1)
                no.membros.append((k, ki, kf, filho))
                i = ws(i)
                if t[i] == ",":
                    i += 1
                    continue
                no.fim = i + 1
                return no, i + 1
        if c == "[":
            no = No(i, "a")
            i = ws(i + 1)
            if t[i] == "]":
                no.fim = i + 1
                return no, i + 1
            while True:
                filho, i = valor(i)
                no.itens.append(filho)
                i = ws(i)
                if t[i] == ",":
                    i += 1
                    continue
                no.fim = i + 1
                return no, i + 1
        no = No(i, "v")
        if c == '"':
            _, no.fim = scanstring(t, i + 1)
        elif t.startswith(("true", "null"), i):
            no.fim = i + 4
        elif t.startswith("false", i):
            no.fim = i + 5
        else:
            m = NUMBER_RE.match(t, i)
            if not m:
                raise ValueError("JSON inesperado")
            no.fim = m.end()
        return no, no.fim

    no, _ = valor(0)
    return no


class Estilo:
    def __init__(self, t: str):
        m = re.search(r"\n([ \t]+)\S", t)
        self.unidade = m.group(1) if m else None
        self.ascii = all(ord(c) < 128 for c in t) and "\\u" in t
        self.nl = "\r\n" if "\r\n" in t else "\n"
        self.sep = (", ", ": ") if '": ' in t[:5000] else (",", ":")

    def em_linha(self, v) -> str:
        return json.dumps(v, ensure_ascii=self.ascii, separators=self.sep)

    def bloco(self, v, base: str) -> str:
        if self.unidade is None or not isinstance(v, (dict, list)) or not v:
            return self.em_linha(v)
        s = json.dumps(v, ensure_ascii=self.ascii, indent=self.unidade)
        return s.replace("\n", self.nl + base)


def _base_da_linha(t: str, pos: int) -> str:
    ini = t.rfind("\n", 0, pos) + 1
    return re.match(r"[ \t]*", t[ini:]).group(0)


def remendar(t: str, no: No, o, n, edicoes: list, est: Estilo):
    if iguais(o, n):
        return
    if isinstance(o, dict) and isinstance(n, dict) and no.tipo == "o":
        mapa = {k: (ki, kf, f) for k, ki, kf, f in no.membros}
        for k in o:
            if k not in n:
                raise ValueError(f"chave apagada {k!r}")
            remendar(t, mapa[k][2], o[k], n[k], edicoes, est)
        novos = [k for k in n if k not in o]
        if novos:
            if not no.membros:
                edicoes.append((no.ini, no.fim, est.bloco(n, _base_da_linha(t, no.ini))))
                return
            _, ki0, kf0, f0 = no.membros[0]
            ws = t[no.ini + 1:ki0]
            sep = t[kf0:f0.ini]
            base = ws.split("\n")[-1] if "\n" in ws else ""
            txt = "".join("," + ws + json.dumps(k, ensure_ascii=est.ascii) + sep +
                          (est.bloco(n[k], base) if "\n" in ws else est.em_linha(n[k])) for k in novos)
            edicoes.append((no.membros[-1][3].fim, no.membros[-1][3].fim, txt))
        return
    if isinstance(o, list) and isinstance(n, list) and no.tipo == "a" and o:
        k = chave_id(o)
        extras = []
        if k and all(isinstance(x, dict) for x in n):
            pos = {str(x[k]): i for i, x in enumerate(o)}
            for x in n:
                if str(x.get(k)) in pos:
                    i = pos[str(x[k])]
                    remendar(t, no.itens[i], o[i], x, edicoes, est)
                else:
                    extras.append(x)
        elif len(n) >= len(o) and (all(isinstance(x, dict) for x in o) or len(n) == len(o)):
            for i in range(len(o)):
                remendar(t, no.itens[i], o[i], n[i], edicoes, est)
            extras = n[len(o):]
        else:
            edicoes.append((no.ini, no.fim, est.bloco(n, _base_da_linha(t, no.ini))))
            return
        if extras:
            ws = t[no.ini + 1:no.itens[0].ini]
            base = ws.split("\n")[-1] if "\n" in ws else ""
            txt = "".join("," + ws + (est.bloco(x, base) if "\n" in ws else est.em_linha(x)) for x in extras)
            edicoes.append((no.itens[-1].fim, no.itens[-1].fim, txt))
        return
    edicoes.append((no.ini, no.fim, est.bloco(n, _base_da_linha(t, no.ini))))


def no_do_caminho(no: No, dados, caminho: list):
    for seg in caminho:
        if no.tipo == "o":
            no = {k: f for k, _, _, f in no.membros}[seg]
            dados = dados[seg]
        else:
            k, v = seg.split("=", 1) if isinstance(seg, str) else (None, None)
            i = seg if isinstance(seg, int) else next(j for j, x in enumerate(dados) if str(x.get(k)) == v)
            no, dados = no.itens[i], dados[i]
    return no, dados


def aplicar_no_texto(texto: str, atual, novo_completo, partes: list | None) -> str:
    raiz_no = analisar(texto)
    est = Estilo(texto)
    edicoes = []
    for cam in (partes if partes is not None else [[]]):
        no, o = no_do_caminho(raiz_no, atual, cam)
        remendar(texto, no, o, pegar(novo_completo, cam), edicoes, est)
    edicoes.sort(key=lambda e: (e[0], e[1]), reverse=True)
    saida = texto
    for ini, fim, txt in edicoes:
        saida = saida[:ini] + txt + saida[fim:]
    if not iguais(json.loads(saida), novo_completo):
        raise ValueError("a aplicação mantendo a formatação não deu o mesmo conteúdo")
    return saida


# ---------------------------------------------------------------- validação

def validar(pacote_path: Path, raiz: Path = RAIZ, manifesto: str | None = None, kits: str | None = None) -> dict:
    res = {"erros": [], "avisos": [], "mudancas": [], "plano": {}, "pos_aplicar": [], "manifesto": None,
           "revisor": "", "deriva": []}
    try:
        sep = separar(ler_pacote(pacote_path))
        man = achar_manifesto(sep, manifesto, kits, res["avisos"])
    except (ValueError, OSError, zipfile.BadZipFile) as e:
        res["erros"].append(str(e))
        return res
    res["manifesto"] = man
    if man.get("formato") != FORMATO:
        res["erros"].append(f"manifesto de formato desconhecido: {man.get('formato')}")
        return res
    # 1. arquivos que podem estar na devolução
    por_kit = {e["arquivo_kit"]: e for e in man["editaveis"]}
    marca = sep["editaveis"].pop("editaveis/" + ARQ_KIT, None)
    if marca is not None:
        if sha256_bytes(marca) != man["outros"].get("editaveis/" + ARQ_KIT):
            try:
                kit_marca = json.loads(marca.decode("utf-8-sig")).get("kit")
            except (ValueError, UnicodeDecodeError):
                kit_marca = None
            if kit_marca != man["kit"]:
                res["erros"].append(f"editaveis/{ARQ_KIT} é de outro kit ({kit_marca}); o manifesto é do {man['kit']}.")
            else:
                res["avisos"].append(f"editaveis/{ARQ_KIT} foi mexido (o kit confere).")
    else:
        res["avisos"].append(f"a devolução veio sem editaveis/{ARQ_KIT}; usei o manifesto indicado.")
    for nome in sep["editaveis"]:
        if nome not in por_kit:
            res["erros"].append(f"{nome}: não é arquivo editável deste kit (arquivo a mais ou com nome trocado).")
    ref = {r["arquivo_kit"]: r["sha256"] for r in man["referencia"]}
    for nome, b in sep["referencia"].items():
        if nome not in ref:
            res["erros"].append(f"{nome}: arquivo novo dentro de referencia/; a referência não muda.")
        elif sha256_bytes(b) != ref[nome]:
            res["erros"].append(f"{nome}: arquivo de referência foi mudado. A referência é só para ler; "
                                "descreva a mudança na ficha.")
    for nome in sep["outros"]:
        res["avisos"].append(f"{nome}: arquivo fora de editaveis/ que não é do kit; ignorado (não vai para o sistema).")
    # ficha
    if sep["ficha"] is None:
        res["avisos"].append("A devolução veio sem FICHA_REVISAO.md: peça a ficha (o que mudou, por quê, fonte) antes do merge.")
    elif sha256_bytes(sep["ficha"]) == man["outros"].get("FICHA_REVISAO.md"):
        res["avisos"].append("A FICHA_REVISAO.md veio sem preencher.")
    else:
        m = re.search(r"\*\*Revisor\(a\):\*\*[ \t]*(.+)", sep["ficha"].decode("utf-8", "replace"))
        res["revisor"] = m.group(1).strip() if m else ""
    # 2. cada editável
    for e in man["editaveis"]:
        nome = e["arquivo_kit"]
        b = sep["editaveis"].get(nome)
        if b is None:
            res["avisos"].append(f"{nome}: não veio na devolução (considerado sem mudança).")
            continue
        if sha256_bytes(b) == e["sha256_kit"]:
            continue
        ctx = Contexto(nome.split("/")[-1])
        if e["tipo"] == "trocas":
            validar_trocas(b, e, raiz, ctx, res)
            res["erros"] += ctx.erros
            res["avisos"] += ctx.avisos
            res["mudancas"] += ctx.mudancas
            continue
        fonte = raiz / e["fonte"]
        if not fonte.is_file():
            res["erros"].append(f"{e['fonte']}: não existe mais no sistema.")
            continue
        bruto = fonte.read_bytes()
        if e["tipo"] == "texto":
            validar_texto(b, bruto, e, ctx, res)
        else:
            validar_json(b, bruto, e, man, ctx, res)
        res["erros"] += ctx.erros
        res["avisos"] += ctx.avisos
        res["mudancas"] += ctx.mudancas
    if res["erros"]:
        res["plano"] = {}
    return res


def _deriva(res, e, detalhe):
    res["deriva"].append(e["fonte"])
    res["erros"].append(
        f"{e['fonte']}: o arquivo mudou no sistema depois que o kit foi gerado ({detalhe}). Não dá para aplicar "
        "por cima sem perder uma das mudanças: é preciso juntar em 3 vias (o que foi para o revisor, o que ele "
        "devolveu e o que está no sistema). Veja docs/INCORPORAR_REVISOES.md, seção 'Conflito'.")


def validar_json(b: bytes, bruto: bytes, e: dict, man: dict, ctx: Contexto, res: dict):
    novo = carregar_json_estrito(b, ctx)
    if novo is None:
        return
    atual = json.loads(bruto.decode("utf-8-sig"))
    if e["tipo"] == "json":
        if sha_canonico(atual) != e["hash_partes"][""]:
            _deriva(res, e, "arquivo inteiro")
            return
        if iguais(atual, novo):
            ctx.avisos.append(f"{ctx.arquivo}: só mudou a formatação; nada a aplicar.")
            return
        comparar(atual, novo, [], ctx)
        completo = novo
        partes = None
        checar_bloqueadas(atual, novo, e, ctx)
        checar_faixas(novo, [], ctx)
    else:
        if not isinstance(novo, dict) or set(novo) != {"_leia", "_arquivo", "partes"}:
            ctx.erros.append(f"{ctx.arquivo}: o arquivo de parte tem de manter só _leia, _arquivo e partes.")
            return
        if novo["_arquivo"] != e["fonte"] or novo["_leia"] != leia_extrato(e["fonte"], man["nome"]):
            ctx.erros.append(f"{ctx.arquivo}: _leia ou _arquivo foram mudados.")
        if not isinstance(novo["partes"], list) or len(novo["partes"]) != len(e["partes"]):
            ctx.erros.append(f"{ctx.arquivo}: a lista 'partes' perdeu ou ganhou itens.")
            return
        completo = json.loads(json.dumps(atual))
        for i, (p, cam) in enumerate(zip(novo["partes"], e["partes"])):
            if not isinstance(p, dict) or set(p) != {"caminho", "valor"} or p["caminho"] != cam:
                ctx.erros.append(f"{ctx.arquivo}: parte {i + 1} teve 'caminho' mudado ou campo a mais.")
                continue
            try:
                o = pegar(atual, cam)
            except KeyError:
                _deriva(res, e, f"a parte {caminho_texto(cam)} sumiu")
                continue
            if sha_canonico(o) != e["hash_partes"][json.dumps(cam, ensure_ascii=False)]:
                _deriva(res, e, f"parte {caminho_texto(cam)}")
                continue
            comparar(o, p["valor"], list(cam), ctx)
            checar_faixas(p["valor"], list(cam), ctx)
            trocar(completo, cam, p["valor"])
        partes = e["partes"]
        if iguais(atual, completo):
            if not ctx.erros:
                ctx.avisos.append(f"{ctx.arquivo}: só mudou a formatação; nada a aplicar.")
            return
    if ctx.erros or e["fonte"] in res["deriva"]:
        return
    texto = bruto.decode("utf-8")
    try:
        saida = aplicar_no_texto(texto, atual, completo, partes)
    except (ValueError, KeyError, StopIteration) as ex:
        ctx.erros.append(f"{e['fonte']}: não consegui aplicar mantendo a formatação ({ex}). Aplique à mão.")
        return
    res["plano"][e["fonte"]] = saida.encode("utf-8")
    res["pos_aplicar"] += [p for p in e.get("pos_aplicar", []) if p not in res["pos_aplicar"]]


def checar_bloqueadas(atual, novo, e: dict, ctx: Contexto):
    for cam in e.get("bloqueadas") or []:
        try:
            a, n = pegar(atual, cam), pegar(novo, cam)
        except KeyError:
            continue
        if not iguais(a, n):
            ctx.erros.append(f"{ctx.onde(list(cam))}: esta parte não pode mudar pelo kit (contrato do aparelho). "
                             "Descreva a mudança na ficha.")


def checar_faixas(valor, cam: list, ctx: Contexto):
    """Registro com 'valor' numérico e 'faixa_aceita' [mín, máx]: o valor tem de caber na faixa."""
    if isinstance(valor, dict):
        f, v = valor.get("faixa_aceita"), valor.get("valor")
        if (isinstance(f, list) and len(f) == 2 and all(isinstance(x, (int, float)) for x in f)
                and isinstance(v, (int, float)) and not isinstance(v, bool) and not f[0] <= v <= f[1]):
            nome = valor.get("id") or caminho_texto(cam)
            ctx.erros.append(f"{ctx.onde(cam)}: {nome} = {v} está fora da faixa aceita ({f[0]} a {f[1]}).")
        for k, x in valor.items():
            checar_faixas(x, cam + [k], ctx)
    elif isinstance(valor, list):
        for i, x in enumerate(valor):
            seg = i
            if isinstance(x, dict):
                for k in ("id", "n", "codigo"):
                    if k in x:
                        seg = f"{k}={x[k]}"
                        break
            checar_faixas(x, cam + [seg], ctx)


def _dentro_de_bloco_embutido(texto: str, pos: int) -> str | None:
    """Se a posição cai dentro de um <script id="mod-..."> ou de uma base embutida, devolve o id do bloco."""
    ini = texto.rfind("<script", 0, pos)
    if ini < 0 or texto.find("</script>", ini) < pos:
        return None
    m = re.match(r'<script(?: type="application/json")? id="((?:mod|base)-[\w-]+)"', texto[ini:ini + 80])
    return m.group(1) if m else None


def validar_trocas(b: bytes, e: dict, raiz: Path, ctx: Contexto, res: dict):
    dados = carregar_json_estrito(b, ctx)
    if dados is None:
        return
    if not isinstance(dados, dict) or set(dados) != {"_leia", "arquivos_permitidos", "trocas"}:
        ctx.erros.append(f"{ctx.arquivo}: mantenha só _leia, arquivos_permitidos e trocas.")
        return
    if dados["_leia"] != leia_trocas() or dados["arquivos_permitidos"] != e["arquivos_permitidos"]:
        ctx.erros.append(f"{ctx.arquivo}: _leia ou arquivos_permitidos foram mudados.")
    if not isinstance(dados["trocas"], list):
        ctx.erros.append(f"{ctx.arquivo}: 'trocas' tem de ser uma lista.")
        return
    i18n = set()
    arq_i18n = raiz / "sistema" / "physis-i18n-modulos.json"
    if arq_i18n.is_file():
        try:
            i18n = set(json.loads(arq_i18n.read_text(encoding="utf-8")).get("I18N", {}))
        except ValueError:
            i18n = set()
    textos, fontes_js = {}, None
    for n, tr in enumerate(dados["trocas"], 1):
        onde = f"{ctx.arquivo} › troca {n}"
        if not isinstance(tr, dict) or set(tr) != {"arquivo", "antes", "depois", "motivo"} or \
                not all(isinstance(tr[k], str) for k in tr):
            ctx.erros.append(f"{onde}: cada troca tem só arquivo, antes, depois e motivo (todos texto).")
            continue
        arq, antes, depois, motivo = tr["arquivo"], tr["antes"], tr["depois"], tr["motivo"].strip()
        if arq not in e["arquivos_permitidos"] or not pode_trocar_texto(arq):
            ctx.erros.append(f"{onde}: '{arq}' não está entre os arquivos permitidos deste kit.")
            continue
        erros_antes = len(ctx.erros)
        if not antes.strip() or not motivo:
            ctx.erros.append(f"{onde}: 'antes' e 'motivo' não podem ficar vazios.")
        if antes == depois:
            ctx.erros.append(f"{onde}: 'antes' e 'depois' são iguais.")
        for nome, s in (("antes", antes), ("depois", depois), ("motivo", motivo)):
            if len(s) > LIMITE_TROCA:
                ctx.erros.append(f"{onde}: '{nome}' passa de {LIMITE_TROCA} caracteres.")
            if "\n" in s or "\r" in s or CONTROLE.search(s):
                ctx.erros.append(f"{onde}: '{nome}' tem quebra de linha ou caractere de controle.")
        for nome, s in (("antes", antes), ("depois", depois)):
            m = CODIGO_TROCA.search(s)
            if m:
                ctx.erros.append(f"{onde}: '{nome}' tem sinal de código ({m.group(0)!r}). Troca de texto é só "
                                 "texto; mudança de código vai na ficha.")
        for c in ('"', "'", "\\"):
            if antes.count(c) != depois.count(c):
                ctx.erros.append(f"{onde}: o 'depois' tem de ter as mesmas aspas e barras do 'antes' ({c!r}).")
        checar_texto(motivo, "", [f"troca {n}", "motivo"], ctx)
        if len(ctx.erros) > erros_antes:
            continue
        caminho = raiz / arq
        if arq not in textos:
            if not caminho.is_file():
                ctx.erros.append(f"{onde}: {arq} não existe no sistema.")
                continue
            textos[arq] = caminho.read_bytes().decode("utf-8")
        atual = textos[arq]
        qtd = atual.count(antes)
        if qtd != 1:
            ctx.erros.append(f"{onde}: o texto de 'antes' aparece {qtd} vez(es) em {arq}; tem de aparecer exatamente "
                             "uma (copie um trecho maior, que seja único).")
            continue
        if arq == PAINEL_REL:
            bloco = _dentro_de_bloco_embutido(atual, atual.index(antes))
            if bloco and bloco.startswith("base-"):
                ctx.erros.append(f"{onde}: este texto é de uma base de dados embutida ({bloco}); mude pelo arquivo "
                                 "editável da base, não pela troca de texto.")
                continue
            if bloco:
                if fontes_js is None:
                    fontes_js = sorted((raiz / "sistema").glob("*.js"))
                donos = [p for p in fontes_js if p.read_text(encoding="utf-8", errors="replace").count(antes) == 1]
                if len(donos) != 1:
                    ctx.erros.append(f"{onde}: o texto está num programa embutido ({bloco}); não achei de qual "
                                     "arquivo de sistema/ ele vem. Indique o arquivo do programa.")
                    continue
                novo_arq = donos[0].relative_to(raiz).as_posix()
                ctx.avisos.append(f"{onde}: o texto vem de {novo_arq} (embutido no painel); a troca vai nesse arquivo.")
                arq = novo_arq
                if arq not in textos:
                    textos[arq] = donos[0].read_bytes().decode("utf-8")
                atual = textos[arq]
        textos[arq] = atual.replace(antes, depois, 1)
        if antes.strip() in i18n:
            ctx.avisos.append(f"{onde}: '{antes.strip()[:60]}' tem tradução na base de inglês; a chave em português "
                              "precisa ser trocada lá também (combine com quem revisa o inglês).")
        ctx.mudancas.append(f"{arq}: texto “{antes}” → “{depois}” (motivo: {motivo})")
    if ctx.erros:
        return
    for arq, novo in textos.items():
        if novo.encode("utf-8") != (raiz / arq).read_bytes():
            res["plano"][arq] = novo.encode("utf-8")
            acoes = []
            if arq.endswith(".js"):
                acoes.append("embutir_bases")
            if arq.endswith(".html") and arq.startswith(("sistema/", "physis-hub/web/")):
                acoes.append("sincronizar")
            if arq.endswith(".html") or arq.endswith(".js"):
                acoes.append("gerar_demos")
            res["pos_aplicar"] += [a for a in acoes if a not in res["pos_aplicar"]]


def validar_texto(b: bytes, bruto: bytes, e: dict, ctx: Contexto, res: dict):
    if sha256_bytes(bruto) != e["sha256_fonte"]:
        _deriva(res, e, "arquivo de texto")
        return
    try:
        novo, velho = b.decode("utf-8-sig"), bruto.decode("utf-8")
    except UnicodeDecodeError:
        ctx.erros.append(f"{ctx.arquivo}: não está em UTF-8.")
        return
    nl = "\r\n" if "\r\n" in velho else "\n"
    novo = novo.replace("\r\n", "\n").replace("\n", nl)
    if novo == velho:
        ctx.avisos.append(f"{ctx.arquivo}: só mudou o fim de linha; nada a aplicar.")
        return
    if len(novo) > 2 * len(velho) + 20000:
        ctx.erros.append(f"{ctx.arquivo}: cresceu demais ({len(velho)} → {len(novo)} caracteres).")
    if "\x00" in novo or CONTROLE.search(novo.replace("\t", "")):
        ctx.erros.append(f"{ctx.arquivo}: caractere de controle no texto.")
    linhas = list(difflib.unified_diff(velho.splitlines(), novo.splitlines(), lineterm="", n=0))
    novas = [ln[1:] for ln in linhas if ln.startswith("+") and not ln.startswith("+++")]
    for ln in novas:
        if SEGREDO.search(ln):
            ctx.erros.append(f"{ctx.arquivo}: linha nova parece ter senha ou chave ({ln.strip()[:40]}…). "
                             "Segredo fica em secrets.h / secrets.yaml, fora do Git.")
        for padrao, nome in PROIBIDO[:2]:
            if padrao.search(ln) and not e["fonte"].endswith((".h", ".cpp", ".ino")):
                ctx.erros.append(f"{ctx.arquivo}: entrou {nome}: {ln.strip()[:60]}")
        if URL.search(ln):
            ctx.avisos.append(f"{ctx.arquivo}: linha nova com endereço: {ln.strip()[:80]} (confira se é da rede local).")
    trecho = linhas[2:62]
    ctx.mudancas.append(f"{ctx.arquivo}: {len(novas)} linha(s) nova(s) ou mudada(s):\n" +
                        "\n".join("      " + ln for ln in trecho) + ("\n      …" if len(linhas) > 62 else ""))
    if not ctx.erros:
        res["plano"][e["fonte"]] = novo.encode("utf-8")


# ---------------------------------------------------------------- aplicar na branch

def copiar_metodologia_js(raiz: Path) -> str:
    d = json.loads((raiz / "sistema" / "physis-metodologia.json").read_text(encoding="utf-8"))
    p = raiz / "sistema" / "physis-metodologia.js"
    t = p.read_text(encoding="utf-8")
    novo, n = re.subn(r"(/\*DADOS-INICIO\*/\s*const DADOS = ).*?(;\s*/\*DADOS-FIM\*/)",
                      lambda m: m.group(1) + json.dumps(d, ensure_ascii=False, indent=1) + m.group(2), t, flags=re.S)
    if n != 1:
        raise RuntimeError("bloco DADOS não encontrado em sistema/physis-metodologia.js")
    p.write_text(novo, encoding="utf-8", newline="\n")
    return "metodologia copiada para sistema/physis-metodologia.js"


def rodar(cmd: list, cwd: Path, limite: int = 3600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=limite)


def pos_aplicar(acoes: list, arquivos: list, raiz: Path) -> list:
    out = []
    acoes = set(acoes)
    if "copiar_metodologia_js" in acoes:
        acoes.add("embutir_bases")             # o painel leva uma cópia do physis-metodologia.js
    if acoes & {"embutir_bases", "sincronizar"}:
        acoes.add("gerar_demos")               # as demonstrações são cópias do painel
    ordem = ["copiar_metodologia_js", "embutir_bases", "gerar_harness_avac", "sincronizar", "gerar_demos",
             "sincronizar_conferir"]
    acoes = sorted(acoes, key=lambda x: ordem.index(x) if x in ordem else len(ordem))
    for a in acoes:
        if a == "copiar_metodologia_js":
            out.append(copiar_metodologia_js(raiz))
        elif a == "embutir_bases":
            script = raiz / "ferramentas" / "embutir_bases.py"
            if not script.is_file():
                out.append("embutir_bases: ferramentas/embutir_bases.py não existe")
                continue
            r = rodar([sys.executable, str(script)], raiz)
            out.append("embutir_bases: " + ("ok" if r.returncode == 0 else "FALHOU " + r.stderr[-400:]))
        elif a == "gerar_harness_avac":
            script = raiz / "ferramentas" / "testes-navegador" / "gerar_harness.py"
            texto = script.read_text(encoding="utf-8") if script.is_file() else ""
            if str(raiz) not in texto:
                out.append("gerar_harness_avac: o script aponta para outra pasta; rode à mão depois do merge")
                continue
            r = rodar([sys.executable, str(script), str(raiz / "ferramentas" / "testes-navegador" / "teste-avac.html")], raiz)
            out.append("gerar_harness_avac: " + ("ok" if r.returncode == 0 else "FALHOU " + r.stderr[-400:]))
        elif a == "sincronizar":
            r = rodar([sys.executable, str(raiz / "ferramentas" / "sincronizar.py")], raiz)
            out.append("sincronizar: " + ("ok" if r.returncode == 0 else "FALHOU " + (r.stderr or r.stdout)[-400:]))
        elif a == "gerar_demos":
            script = raiz / "demos" / "gerar_demos.py"
            if not script.is_file():
                out.append("gerar_demos: demos/gerar_demos.py não existe")
                continue
            r = rodar([sys.executable, str(script)], raiz)
            out.append("gerar_demos: " + ("ok" if r.returncode == 0 else "FALHOU " + (r.stderr or r.stdout)[-400:]))
        elif a == "sincronizar_conferir":
            r = rodar([sys.executable, str(raiz / "ferramentas" / "sincronizar.py"), "--conferir"], raiz)
            out.append("sincronizar --conferir: " + ("ok" if r.returncode == 0 else "diferença: " + r.stdout[-400:]))
        else:
            out.append(f"{a}: ação desconhecida, ignorada")
    return out


def resumo_testes(r: subprocess.CompletedProcess) -> tuple[bool, str]:
    texto = (r.stderr or "") + (r.stdout or "")
    ran = re.findall(r"Ran \d+ tests? in [\d.]+s", texto)
    fim = re.findall(r"^(OK.*|FAILED.*)$", texto, re.M)
    ok = r.returncode == 0
    linha = f"{ran[-1] if ran else 'sem contagem'} · {fim[-1] if fim else ('OK' if ok else 'FALHOU')}"
    if not ok:
        linha += "\n" + "\n".join("      " + ln for ln in texto.strip().splitlines()[-40:])
    return ok, linha


def aplicar(res: dict, raiz: Path, testes: bool = True) -> dict:
    man = res["manifesto"]
    out = {"branch": None, "testes": [], "pos": [], "ok": False, "commit": None, "volta": None}
    if not git(raiz, "rev-parse", "--is-inside-work-tree").stdout.strip() == "true":
        raise RuntimeError(f"{raiz} não é um repositório Git")
    sujo = git(raiz, "status", "--porcelain").stdout.strip()
    if sujo:
        raise RuntimeError("Há mudanças não salvas no Git. Faça commit (ou stash) antes de aplicar uma revisão:\n"
                           + "\n".join("  " + ln for ln in sujo.splitlines()[:20]))
    volta = git(raiz, "rev-parse", "--abbrev-ref", "HEAD", checar=True).stdout.strip()
    if volta == "HEAD":
        raise RuntimeError("O Git está fora de uma branch (HEAD solto). Volte para a main antes.")
    out["volta"] = volta
    base = f"revisao/{man['modulo']}-{_dt.date.today().isoformat()}"
    nome, i = base, 2
    while git(raiz, "rev-parse", "--verify", "--quiet", f"refs/heads/{nome}").returncode == 0:
        nome, i = f"{base}-{i}", i + 1
    git(raiz, "switch", "-c", nome, checar=True)
    out["branch"] = nome
    try:
        for rel, conteudo in res["plano"].items():
            (raiz / rel).write_bytes(conteudo)
        out["pos"] = pos_aplicar(res["pos_aplicar"], list(res["plano"]), raiz)
        todos_ok = True
        if testes:
            hub = raiz / "physis-hub"
            mods = [f"tests.{t}" for t in man.get("testes", []) if (hub / "tests" / f"{t}.py").is_file()]
            if mods:
                ok, linha = resumo_testes(rodar([sys.executable, "-m", "unittest", *mods], hub))
                out["testes"].append(("testes do módulo", ok, linha))
                todos_ok &= ok
            ok, linha = resumo_testes(rodar([sys.executable, "-m", "unittest", "discover", "-s", "tests"], hub))
            out["testes"].append(("suíte inteira", ok, linha))
            todos_ok &= ok
        git(raiz, "add", "-A", checar=True)
        msg = (f"Revisão {man['nome']} ({res.get('revisor') or ', '.join(man['responsaveis'])}) · {man['kit']}"
               + ("" if todos_ok else " · TESTES FALHARAM, não juntar") +
               "\n\nAplicado por ferramentas/validar_devolucao.py. Arquivos: " + ", ".join(res["plano"]))
        git(raiz, "commit", "-m", msg, checar=True)
        out["commit"] = git(raiz, "rev-parse", "HEAD").stdout.strip()
        out["ok"] = todos_ok
    except Exception:
        git(raiz, "reset", "--hard", "HEAD")
        git(raiz, "switch", volta)
        git(raiz, "branch", "-D", nome)
        out["branch"] = None
        raise
    git(raiz, "switch", volta, checar=True)
    return out


def relatorio(res: dict, pacote: Path, ap: dict | None) -> str:
    man = res.get("manifesto") or {}
    situacao = "RECUSADA" if res["erros"] else ("ACEITA (nada a aplicar)" if not res["plano"] else "ACEITA NA VALIDAÇÃO")
    out = [f"# Validação da devolução · {man.get('nome', '?')}", "",
           f"- Pacote: `{pacote.name}`", f"- Kit: `{man.get('kit', '?')}` (commit {str(man.get('commit'))[:12]})",
           f"- Responsáveis: {', '.join(man.get('responsaveis', []))}",
           f"- Revisor(a) na ficha: {res.get('revisor') or '(não informado)'}",
           f"- Situação: **{situacao}**", ""]
    if res["erros"]:
        out += ["## Erros (precisam ser corrigidos pelo revisor ou pelo Eric)", ""] + [f"- {x}" for x in res["erros"]] + [""]
    if res["avisos"]:
        out += ["## Avisos", ""] + [f"- {x}" for x in res["avisos"]] + [""]
    out += ["## O que mudou", ""]
    out += [f"- {x}" for x in res["mudancas"]] or ["- Nada."]
    out.append("")
    if res["plano"]:
        out += ["Arquivos do sistema que mudam: " + ", ".join(f"`{p}`" for p in res["plano"]),
                "Depois de aplicar: " + (", ".join(res["pos_aplicar"]) or "nada a rodar"), ""]
    if ap:
        out += ["## Aplicação", "", f"- Branch: `{ap['branch']}` (a partir de `{ap['volta']}`), commit {str(ap['commit'])[:12]}"]
        out += [f"- {p}" for p in ap["pos"]]
        out += [f"- {nome}: {'OK' if ok else 'FALHOU'} · {linha}" for nome, ok, linha in ap["testes"]]
        out += ["", "Próximos passos (Eric):", "",
                f"    git diff {ap['volta']}...{ap['branch']}        # ver a mudança",
                f"    git merge --no-ff {ap['branch']}           # juntar, se aprovado" if ap["ok"] else
                "    # testes falharam: não juntar; corrija na branch ou devolva ao revisor",
                f"    git branch -D {ap['branch']}               # descartar", ""]
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Confere (e aplica numa branch) um kit de revisão devolvido.")
    ap.add_argument("pacote", help="ZIP ou pasta devolvida pelo revisor")
    ap.add_argument("--manifesto", help="MANIFESTO do kit (padrão: procura em --kits/_manifestos)")
    ap.add_argument("--kits", help="pasta onde os kits foram gerados (tem _manifestos/)")
    ap.add_argument("--raiz", default=str(RAIZ), help="raiz do repositório")
    ap.add_argument("--aplicar", action="store_true", help="aplica numa branch revisao/<modulo>-<data> e roda os testes")
    ap.add_argument("--sem-testes", action="store_true", help="com --aplicar, não roda os testes (não recomendado)")
    ap.add_argument("--relatorio", help="grava o relatório neste arquivo .md")
    a = ap.parse_args(argv)
    pacote, raiz = Path(a.pacote).resolve(), Path(a.raiz).resolve()
    res = validar(pacote, raiz, a.manifesto, a.kits)
    apl = None
    codigo = 1 if res["erros"] else 0
    if a.aplicar and not res["erros"] and res["plano"]:
        try:
            apl = aplicar(res, raiz, testes=not a.sem_testes)
            codigo = 0 if apl["ok"] else 2
        except (RuntimeError, OSError, subprocess.SubprocessError) as e:
            res["erros"].append(f"Aplicação interrompida, nada ficou mudado: {e}")
            codigo = 1
    texto = relatorio(res, pacote, apl)
    print(texto)
    if a.relatorio:
        Path(a.relatorio).write_text(texto, encoding="utf-8", newline="\n")
    return codigo


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
