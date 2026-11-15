# Certificação assistida (evidências automáticas)

Para cada critério da base `sistema/physis-certificacoes.json`, o sistema procura evidência no que já guarda e
diz: **atendido**, **parcial** ou **sem evidência**, com valor, fonte, data e a tela onde conferir.
É apoio à auditoria: a decisão final é da certificadora.

| Arquivo | Papel |
|---|---|
| `sistema/physis-evidencias.json` | Mapa (dados): regras por critério, regras por `auto`, regra geral de documentos |
| `sistema/physis-evidencias.js` | Motor e tela na plataforma: `evidenciasPara(certId, dados?)`, `telaEvidencias(certId)` |
| `physis-hub/physis_hub/evidencias.py` | Espelho do motor (regra 4) + dados do servidor + anexos |
| `physis-hub/tests/test_evidencias.py` | Testes das regras, do mapa e do espelho |

Conferido em 15/11/2026: o JS e o Python dão o mesmo resultado em 24 combinações (8 certificações × 3 conjuntos
de dados), rodando o JS num navegador.

## Fontes

| Fonte | Lê | Atendido quando |
|---|---|---|
| `agua_contas` / `energia_hist` | `physis-perfil` → `historico[].m3` / `.kwh` | ≥ `min_meses` (12) |
| `medidor` | servidor: dias com `vazao`, `energia` ou `nivel` | ≥ `min_dias` (30) |
| `agua_cisterna` | servidor: dias de `nivel`; `physis-calc-agua.cisterna_m3` | nível medido ≥ 30 dias (só dimensionada = parcial) |
| `solar` | `physis-carbono.solar_kwh` e `.kwh`; `physis-calc-solar` | geração informada (só dimensionado = parcial) |
| `enpi` | servidor: modelo `consumo:*energia` do aprendizado; senão 12 contas ÷ `area_construida` | modelo treinado (indicador por área = parcial) |
| `residuos_desvio` / `residuos_plano` | `physis-residuos-plano` (+ `rcResumo` da plataforma) | desvio ≥ `meta` (0,5) / todos com rota |
| `carbono_inventario` | `physis-carbono` | escopos 1 e 2 preenchidos |
| `sbn_plano` | `physis-sbn.plano` | ≥ `min_especies` (sempre com teto parcial no mapa: é plano, não execução) |
| `acessibilidade` | `physis-pref` | nunca passa de parcial (digital ≠ NBR 9050) |
| `calibracao` | `physis-ph-calibracoes` + sensores do hub | todos os pontos com calibração e validade em dia |
| `documentos` | servidor: nomes de `gestao_arquivo` | nome do arquivo contém as `palavras` da regra ou o texto de `evidencia` do critério |
| `perfil`, `riscos`, `custos` | iguais ao `certSugestao` atual | sempre parcial |
| `risco_municipal` | servidor: classe do bairro (painel municipal) que contém o lugar do hub | R1 = atendido, R2 = parcial, R3/R4 = sem evidência (pede laudo) |
| anexo (embutida) | anexos do servidor e do aparelho | anexo do critério; vencido = parcial |

`teto` numa regra limita o status (ex.: contas de água não provam medição individualizada → `teto: parcial`).
Cobertura própria: LEED, EDGE, ISO 14001, ISO 50001, AQUA-HQE e Casa Azul (itens de água e energia e os demais
com `auto`); as outras certificações usam `por_auto` e a regra de documentos.

## Ligação na plataforma (integrador)

1. `ferramentas/embutir_bases.py`: em `BASES`, `"base-evidencias": RAIZ / "sistema" / "physis-evidencias.json"`;
   em `MODULOS`, `"mod-evidencias": RAIZ / "sistema" / "physis-evidencias.js"`. Rodar o script.
2. Em `telaCert()`, no bloco de cada certificação (`blocos = sel.map(x => …)`), acrescentar
   `${typeof telaEvidencias === "function" ? telaEvidencias(x.id) : ""}` depois da tabela de critérios.
3. Opcional: em `certSugestao`/`certAvalia`, usar `evidenciasPara(x.id).criterios[k.id].sugestao`
   ("atende"/"parcial"/null) como sugestão quando a pessoa não marcou nada.
4. O botão "Abrir" usa `irPara(tela)` com as telas do `TELAS` (`inicio`, `campo`, `solar`, `circular`, `carbono`,
   `sbn`, `resiliencia`, `custos`, `gestao`, `sustainkit`).

## Rotas para o `servidor.py` (colar)

```python
from . import evidencias as evidencias_mod          # topo
# do_GET
if u.path == "/api/evidencias/dados":
    q_ = self._exigir(seg.CLIENTE)
    if not q_:
        return
    # nomes de arquivos da Gestão só para a equipe
    return self._json(200, {"ok": True, "dados": evidencias_mod.dados_servidor(hub, incluir_arquivos=seg.pode(q_, seg.EQUIPE))})
# do_POST, depois de corpo = self._corpo()
if u.path in ("/api/evidencias/anexo", "/api/evidencias/anexo/remover"):
    q_ = self._exigir(seg.CLIENTE)
    if not q_:
        return
    try:
        d = seg.carregar_json(corpo or "{}")
    except ValueError:
        return self._json(400, {"ok": False, "erro": "json invalido"})
    if u.path.endswith("/remover"):
        try:
            r = evidencias_mod.remover(hub, int(d.get("id") or 0), q_["usuario"])
        except (TypeError, ValueError):
            return self._json(400, {"ok": False, "erro": "id invalido"})
    else:
        r = evidencias_mod.anexar(hub, d, q_["usuario"])
    return self._json(200 if r["ok"] else 400, r)
```

Sem servidor (arquivo aberto ou demonstração), o anexo fica no aparelho (`physis-evidencias-anexos`).

## Limites

- A cisterna do SustainKit não é guardada pelo programa (só é calculada na tela); a fonte lê
  `physis-calc-agua.cisterna_m3` quando existir e o nível medido pelo hub.
- O anexo guarda metadados; o arquivo em si fica na Gestão (`arquivo` = id de `gestao_arquivo`, opcional).
- Busca de documento é por nome de arquivo, não pelo conteúdo.
