#!/usr/bin/env python3
"""Revisão visual do SustainKit (T18), sem tocar em nenhuma conta.

    python ferramentas/revisar_sustainkit.py

O que muda (só aparência):
1. Cores: cada cor própria do SustainKit vira a cor equivalente da paleta Physis (tabela CORES).
2. Emojis: saem das abas e dos títulos de seção. Ficam nos rótulos de status ("✅ Atende"...),
   porque o código compara esses textos (são chaves da lógica das certificações).
3. Títulos de seção no verde Physis (#33512F).

Como provar que as contas não mudaram: sistema/_sk_ouro.html roda 10 cenários de entrada
no arquivo antes e depois e compara todo o texto dos resultados (sem emojis). Têm de ser iguais.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ARQ = Path(__file__).resolve().parent.parent / "sistema" / "SustainKit_Definitivo.html"

# cor do SustainKit -> cor da paleta Physis (docs/PALETA.md)
CORES = {
    "#074031": "#33512F",  # verde escuro dos títulos e destaques -> verde ação
    "#1C2B22": "#1C2B21",  # texto
    "#6B7F6E": "#4A4F44",  # texto secundário
    "#D4E8D0": "#C9D2C4",  # linhas e bordas
    "#F4F7F4": "#F4F6F1",  # fundo
    "#51774B": "#4B7547",  # verde marca
    "#81A969": "#4B7547",  # verde claro de destaque -> verde marca (contraste AA)
    "#81C784": "#4B7547",
    "#EEF8EB": "#EEF4EA",  # fundo verde suave
    "#E8F5E9": "#EEF4EA",
    "#C8E6C9": "#DCEBD8",  # fundo "atende"
    "#2E7D32": "#1F4A1C",  # texto "atende"
    "#1B5E20": "#1F4A1C",
    "#FFE0B2": "#F6EAD0",  # fundo "parcial"
    "#FFF8E1": "#F6EAD0",
    "#FFF9C4": "#F6EAD0",
    "#FFB74D": "#8A6410",
    "#E65100": "#8A6410",  # texto "atenção"
    "#FFCDD2": "#F5E2D7",  # fundo "não atende"
    "#FCE4EC": "#F5E2D7",
    "#B71C1C": "#7A2214",  # texto "alerta"
    "#DBEAFE": "#F4F1EA",  # fundos azuis -> informação
    "#E3F2FD": "#F4F1EA",
    "#EFF6FF": "#F4F1EA",
    "#BFDBFE": "#F4F1EA",
    "#1565C0": "#2F7D5B",  # textos azuis -> informação
    "#1976D2": "#2F7D5B",
    "#0D47A1": "#2F7D5B",
    "#1E40AF": "#2F7D5B",
    "#2196F3": "#2F7D5B",
    "#0288D1": "#2F7D5B",
    "#EDE7F6": "#EFE8D6",  # roxos -> areia
    "#F3E5F5": "#EFE8D6",
    "#6A1B9A": "#4A4F44",
    "#374151": "#4A4F44",
}
RGBA = {"rgba(7,64,49,": "rgba(51,81,47,", "rgba(129,169,105,": "rgba(75,117,71,"}
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⬀-⯿️‍]+\\s*")


def revisar(t: str) -> str:
    # O verde-claro #81A969 era TEXTO sobre o fundo verde-escuro: lá ele vira verde-claro da paleta (#DCEBD8),
    # para manter o contraste. Nas bordas sobre fundo claro, vira o verde da marca (tabela CORES).
    t = re.sub(r"color:\s*#81A969", "color:#DCEBD8", t, flags=re.I)
    t = re.sub(r"'#81A969'", "'#DCEBD8'", t, flags=re.I)
    t = t.replace("rgba(129,169,105,", "rgba(220,235,216,")
    # Campos de digitar no padrão Physis: fundo branco, borda #8A9284, texto escuro (antes: azuis).
    t = t.replace("input[type=number],select{padding:7px 9px;border:2px solid #BFDBFE;border-radius:7px;font-family:inherit;outline:none;background:#EFF6FF;font-size:14px;font-weight:700;color:#1E40AF}",
                  "input[type=number],select{padding:7px 9px;border:1px solid #8A9284;border-radius:8px;font-family:inherit;outline:none;background:#FFFFFF;font-size:14px;font-weight:700;color:#1C2B21;min-height:40px}input[type=number]:focus-visible,select:focus-visible{outline:3px solid #33512F;outline-offset:2px}")
    # Um título só: o nome repetido na faixa de cima fica oculto (o cabeçalho já mostra "Physis SustainKit").
    t = t.replace('<span style="color:#81A969;font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase">Physis SustainKit — </span>',
                  '<span style="display:none">Physis SustainKit — </span>')
    t = t.replace('<span style="color:#DCEBD8;font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase">Physis SustainKit — </span>',
                  '<span style="display:none">Physis SustainKit — </span>')
    t = re.sub(r"#[0-9A-Fa-f]{6}\b", lambda m: CORES.get(m.group(0).upper(), m.group(0)), t)
    for a, b in RGBA.items():
        t = t.replace(a, b)
    # emojis só nas abas e nos títulos de seção
    t = re.sub(r'(<button class="tab-btn[^"]*"[^>]*>)([^<]*)(</button>)', lambda m: m.group(1) + EMOJI.sub("", m.group(2)).strip() + m.group(3), t)
    t = re.sub(r'(<div class="sec-title"[^>]*>)([^<]*)(</div>)', lambda m: m.group(1) + EMOJI.sub("", m.group(2)).replace(" + ", " + ").strip() + m.group(3), t)
    return t


def main() -> int:
    antes = ARQ.read_text(encoding="utf-8")
    depois = revisar(antes)
    if depois == antes:
        print("nada a mudar"); return 0
    ARQ.write_text(depois, encoding="utf-8", newline="\n")
    sobram = sorted({m.upper() for m in re.findall(r"#[0-9A-Fa-f]{6}\b", depois)} - set(CORES.values()) - {"#DCEBD8", "#8A9284", "#FFFFFF"})
    print("revisado:", ARQ.name, "| cores fora da paleta que sobraram:", sobram or "nenhuma")
    return 0


if __name__ == "__main__":
    sys.exit(main())
