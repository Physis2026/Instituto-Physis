# Metodologia e normas

Cada conta da plataforma diz **como é feita**, **qual norma segue** (número e item, com redação própria) e **em que situação está** em relação à norma. A mesma informação aparece em cada aba, numa seção fechada "Metodologia e normas".

Validação preliminar: não substitui projeto com ART. Normas citadas só pelo número e pelo item; consulte a versão oficial vigente. Nenhum trecho de norma entra no sistema (direito autoral da ABNT e da ISO).

## Arquivos

| Arquivo | O que tem |
|---|---|
| `sistema/physis-metodologia.json` | A fonte: módulos (um por aba), cálculos, catálogo de normas e lista de adequações |
| `sistema/physis-metodologia.js` | Cópia dos dados (`window.PHYSIS_METODOLOGIA`) e a função `metodologiaHtml(modulo, opcoes)` |
| `physis-hub/tests/test_metodologia.py` | Formato, cobertura das abas, normas no catálogo, premissas existentes, sem texto de norma, JS igual ao JSON, sem internet |
| `17_Metodologia_e_Normas.md` (pasta de documentos do Sistema Physis) | Versão para ler: tabela cálculo × norma × situação e lista priorizada |

## Formato de um cálculo

| Campo | O que é |
|---|---|
| `id` | `<aba>.<nome>`, único |
| `nome`, `o_que_calcula` | Em palavras simples |
| `formula.texto`, `formula.variaveis[]` | A conta e cada variável com unidade |
| `premissas[]` | Ids de `sistema/physis-premissas.json` (o teste confere se existem) |
| `normas[]` | `{codigo, edicao, item, como_e_usada}`; o código tem de estar em `normas` do JSON; sem norma → código `sem norma aplicável` e o método de referência em `como_e_usada` |
| `limites_de_validade`, `fonte_de_dados`, `onde` | Quando vale, de onde vêm os dados, arquivo e função |
| `status` | `conforme` (selo `ok`) · `simplificado` (`at`) · `só citado` (`in`) · `falta implementar` (`al`) |
| `o_que_falta` | Obrigatório quando não está conforme: a adequação exata (fórmula, limite ou tabela) |

`adequacoes[]` traz a lista priorizada: `quem` = `software` (dá para fazer só com código) ou `engenharia` (precisa de curadoria), com critério de aceite.

## Como ligar numa aba

1. Embutir `sistema/physis-metodologia.js` no `<head>` do painel, como já é feito com `physis-avac.js` (ferramentas/embutir_bases.py).
2. No fim do HTML de cada tela, acrescentar a seção:

       return `<h1>Energia solar</h1>…${ent}${res}${tab}` + (typeof metodologiaHtml === "function" ? metodologiaHtml("solar") : "");

3. O id é o mesmo da lista `ABAS` (`solar`, `avac`, `turbinas`, `agua`, `sbn`, `circular`, `carbono`, `resiliencia`, `planejador`, `sustainkit`, `certificacoes`, `gestao`…). Há também `geral` (acessibilidade digital, para o rodapé ou a página de acessibilidade).
4. Dentro de uma seção que já tem `<h2>` (ex.: quadro elétrico na Caixinha), use `metodologiaHtml("zonas", { nivel: 3 })`.
5. Programas abertos em quadro (SustainKit, Planejador) não mudam (regra 2): a seção vai na aba da plataforma que os abre, fora do quadro.

O HTML é uma `<section class="cartao metodologia">` com título, um `<details>` fechado, tabelas com `<caption>` e `scope`, selos `selo ok|at|in|al` e o aviso. Sem `<h1>`, sem endereço de internet, sem cor nova.

## Como mudar

1. Edite `sistema/physis-metodologia.json`.
2. Copie os dados para o JS (troca só o bloco entre `/*DADOS-INICIO*/` e `/*DADOS-FIM*/`):

       python -c "import json,re,io;d=json.load(io.open('sistema/physis-metodologia.json',encoding='utf-8'));p='sistema/physis-metodologia.js';t=io.open(p,encoding='utf-8').read();t=re.sub(r'(/\*DADOS-INICIO\*/\s*const DADOS = ).*?(;\s*/\*DADOS-FIM\*/)',lambda m:m.group(1)+json.dumps(d,ensure_ascii=False,indent=1)+m.group(2),t,flags=re.S);io.open(p,'w',encoding='utf-8',newline='\n').write(t)"

   (rodar na raiz do repositório)
3. Rode `python -m unittest tests.test_metodologia` em `physis-hub`.
4. Quando uma conta mudar no código, mude o `status` e o `o_que_falta` aqui no mesmo commit; quando uma norma for conferida no catálogo oficial, troque `situacao` de "conferir" para "vigente" e anote na `nota` a data e quem conferiu.
