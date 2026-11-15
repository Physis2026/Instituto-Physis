"""Mostra as abas e as primeiras linhas de uma planilha .xlsx (só biblioteca padrão)."""
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def abrir(caminho):
    z = zipfile.ZipFile(caminho)
    ss = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            ss.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    alvo = {r.get("Id"): r.get("Target") for r in rels}
    abas = []
    for s in wb.find("m:sheets", NS):
        rid = s.get("{%s}id" % NS["r"])
        abas.append((s.get("name"), "xl/" + alvo[rid].lstrip("/").replace("xl/", "")))
    return z, ss, abas


def linhas(z, ss, arq):
    raiz = ET.fromstring(z.read(arq))
    for row in raiz.iter("{%s}row" % NS["m"]):
        vals = {}
        for c in row.findall("m:c", NS):
            ref = c.get("r"); col = re.match(r"[A-Z]+", ref).group(0)
            v = c.find("m:v", NS); t = c.get("t")
            if t == "s" and v is not None:
                vals[col] = ss[int(v.text)]
            elif t == "inlineStr":
                vals[col] = "".join(x.text or "" for x in c.iter("{%s}t" % NS["m"]))
            elif v is not None:
                vals[col] = v.text
        yield int(row.get("r")), vals


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    z, ss, abas = abrir(sys.argv[1])
    print([a for a, _ in abas])
    nome = sys.argv[2] if len(sys.argv) > 2 else abas[0][0]
    arq = dict(abas)[nome]
    for n, (r, v) in enumerate(linhas(z, ss, arq)):
        if n >= int(sys.argv[3] if len(sys.argv) > 3 else 8):
            break
        print(r, v)
