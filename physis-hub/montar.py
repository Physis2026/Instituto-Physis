#!/usr/bin/env python3
"""Monta a plataforma de um cliente só com os módulos comprados.

É o passo que roda depois da confirmação do pagamento. Gera uma pasta (e um .zip)
com o computador central, a tela, a documentação e um `instancia.json` que diz
quais módulos estão ativos e que o primeiro acesso exige cadastro e senha.

  python3 montar.py --org fazenda-boa-vista --modulos monitoramento,sustainkit \\
                    --sustainkit /caminho/SustainKit_Definitivo.html --saida /tmp/entrega

Módulos aceitos: monitoramento, zonas, animais, sustainkit, supervisao.
A plataforma sai ZERADA: sem simulador e sem dados. Quem recebe liga os próprios dispositivos.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
MODULOS = ("monitoramento", "agua", "zonas", "animais", "sustainkit", "supervisao", "gestao", "painel", "planejador")
LICENCA_PADRAO = "[LICENÇA A DEFINIR PELA PHYSIS]"

GUIA = """# Sua plataforma Physis

Organização: {org} · Lugar: {lugar} · Módulos: {modulos}
Montada em {quando}.

## 1. Ligar

Precisa só de Python 3.10 ou mais novo, num computador ou Raspberry Pi da sua rede.

    python3 -m physis_hub.servidor

Abra no navegador `http://<endereço deste computador>:8700/`.

## 2. Primeiro acesso

Na primeira abertura a tela pede o seu nome, um usuário e uma senha de pelo menos 10 caracteres.
Quem cria esse acesso passa a ser a pessoa administradora. A senha fica guardada só neste
computador, de forma protegida; ninguém na Physis a recebe. Se for esquecida, apague o arquivo
`physis-hub.db` para recomeçar (isso apaga também os dados guardados).

## 3. A plataforma chega zerada

Sem equipamento, não há dados. Para ligar os seus dispositivos:

- **Receptor V6 da Physis:** na configuração do receptor, informe o endereço deste computador
  e a porta 8700. Ele entrega as leituras em `/api/gateway/webhook`.
- **Dispositivo próprio com Wi-Fi:** envie uma linha por leitura para `/api/v6/linha`.
  O formato está em `docs/PROTOCOLO.md` e `docs/EXTENSAO_V6.md`.
- **Sem equipamento:** na tela "Teste e diagnóstico", injete uma linha de exemplo.
{sk}
## 4. Código aberto

Todo o código está nesta pasta e pode ser estudado e adaptado. Licença: {licenca}

## 5. Conferir a instalação

    python3 -m unittest discover -s tests
"""


def montar(org: str, lugar: str, modulos: list[str], saida: Path, sustainkit: Path | None, licenca: str,
           supervisao: Path | None = None, gestao: Path | None = None, planejador: Path | None = None,
           pesquisa: bool = False, nome: str = "") -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,63}", org):
        raise SystemExit("org: use de 2 a 64 letras minúsculas, números, ponto, hífen ou sublinhado")
    desconhecidos = [m for m in modulos if m not in MODULOS]
    if desconhecidos or not modulos:
        raise SystemExit(f"módulos aceitos: {', '.join(MODULOS)}; recebi: {', '.join(desconhecidos) or 'nenhum'}")
    if "sustainkit" in modulos and (sustainkit is None or not sustainkit.is_file()):
        raise SystemExit("o módulo sustainkit precisa de --sustainkit apontando para o arquivo HTML do SustainKit")
    if "supervisao" in modulos and (supervisao is None or not supervisao.is_file()):
        raise SystemExit("o módulo supervisao precisa de --supervisao apontando para o arquivo HTML da supervisão")
    if "planejador" in modulos and (planejador is None or not planejador.is_file()):
        raise SystemExit("o módulo planejador precisa de --planejador apontando para o arquivo HTML do Planejador")
    pasta = saida / f"physis-{org}"
    if pasta.exists():
        shutil.rmtree(pasta)
    (pasta / "web").mkdir(parents=True)
    shutil.copytree(AQUI / "physis_hub", pasta / "physis_hub", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(AQUI / "tests", pasta / "tests", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(AQUI / "docs", pasta / "docs")
    shutil.copy2(AQUI / "web" / "painel.html", pasta / "web" / "painel.html")
    if "sustainkit" in modulos:
        shutil.copy2(sustainkit, pasta / "web" / "sustainkit.html")
    if "supervisao" in modulos:
        shutil.copy2(supervisao, pasta / "web" / "supervisao.html")
    if "planejador" in modulos:
        shutil.copy2(planejador, pasta / "web" / "planejador.html")
    if gestao is not None and gestao.is_file():      # só o pacote interno da Physis leva o programa de gestão interna
        shutil.copy2(gestao, pasta / "web" / "gestao.html")
        # o servidor da Physis monta sozinho a plataforma de quem compra: leva o montador e os programas
        shutil.copy2(AQUI / "montar.py", pasta / "montar.py")
        (pasta / "programas").mkdir(exist_ok=True)
        for prog in (sustainkit, supervisao, planejador):
            if prog is not None and prog.is_file():
                shutil.copy2(prog, pasta / "programas" / prog.name)
    inst = {"org": org, "lugar": lugar, "modulos": modulos, "login": True, "licenca": licenca,
            "montada_em": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if nome:
        inst["nome"] = nome
    if pesquisa:      # instalação de pesquisa: mostra também o que está em desenvolvimento, marcado como tal
        inst["pesquisa"] = True
    (pasta / "instancia.json").write_text(json.dumps(inst, ensure_ascii=False, indent=2), encoding="utf-8")
    (pasta / "LICENSE").write_text(licenca + "\n", encoding="utf-8")
    sk = ("- **SustainKit:** já funciona, sem equipamento. Abra pela aba SustainKit.\n"
          if "sustainkit" in modulos else "")
    (pasta / "LEIA-ME.md").write_text(GUIA.format(org=org, lugar=lugar, modulos=", ".join(modulos),
                                                  quando=time.strftime("%d/%m/%Y"), sk=sk, licenca=licenca), encoding="utf-8")
    pacote = saida / f"physis-{org}.zip"
    with zipfile.ZipFile(pacote, "w", zipfile.ZIP_DEFLATED) as z:
        for arq in sorted(pasta.rglob("*")):
            if arq.is_file():
                z.write(arq, arq.relative_to(saida))
    return pacote


def main() -> None:
    ap = argparse.ArgumentParser(description="Monta a plataforma de um cliente com os módulos comprados.")
    ap.add_argument("--org", required=True)
    ap.add_argument("--lugar", default="lugar01")
    ap.add_argument("--modulos", required=True, help="lista separada por vírgula")
    ap.add_argument("--sustainkit", type=Path)
    ap.add_argument("--supervisao", type=Path, help="arquivo HTML da supervisão (physis-scada-demo.html)")
    ap.add_argument("--gestao", type=Path, help="arquivo HTML da gestão (gestao-physis.html)")
    ap.add_argument("--planejador", type=Path, help="arquivo HTML do Planejador Physis")
    ap.add_argument("--pesquisa", action="store_true", help="instalação de pesquisa: mostra também o que está em desenvolvimento")
    ap.add_argument("--nome", default="", help="nome do cliente para a tela")
    ap.add_argument("--licenca", default=LICENCA_PADRAO)
    ap.add_argument("--saida", type=Path, default=Path("entregas"))
    a = ap.parse_args()
    a.saida.mkdir(parents=True, exist_ok=True)
    pacote = montar(a.org, a.lugar, [m.strip() for m in a.modulos.split(",") if m.strip()], a.saida, a.sustainkit, a.licenca,
                    a.supervisao, a.gestao, a.planejador, a.pesquisa, a.nome)
    print(f"Montado: {pacote} ({pacote.stat().st_size // 1024} kB)")


if __name__ == "__main__":
    main()
