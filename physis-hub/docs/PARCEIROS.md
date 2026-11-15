# Marketplace de serviços (profissionais parceiros)

Instaladores e projetistas independentes, com registro no CREA/CAU/CFT e ART, com curadoria da Physis.
Servidor: `physis_hub/parceiros.py`; telas: `sistema/physis-parceiros.js`; testes: `tests/test_parceiros.py`.

## Fluxo

1. Candidatura pela loja ("Quero ser parceiro", com consentimento) ou cadastro pela equipe. Nasce **em análise**.
2. A equipe confere o registro no site do conselho (botão "Registro conferido") e registra os documentos com
   validade: ART/RRT modelo, seguro, NR-10, NR-35, certificados.
3. **Só a direção** muda a curadoria: aprovado / suspenso (com motivo) / em análise. Aprovar exige registro
   conferido e os documentos obrigatórios em dia (`REQUISITOS`).
4. A loja mostra só aprovados com documentos em dia, por especialidade (solar, AVAC, hidráulica, elétrica,
   SbN/paisagismo, automação) e região (município citado antes de "estado todo"; depois nota com média puxada
   para 3). Documento vencido tira o parceiro da loja até ser atualizado.
5. "Pedir orçamento" (com consentimento de quem pede) vira **pedido na Central** (`tipo=pedido`, `origem=parceiros`,
   número `PQ-AAMMDD-XXXXXX`). A Physis encaminha ao parceiro.
6. Pedido marcado concluído (`concluido`, `fechado`, `entregue` ou `atendido`) → quem pediu (ou a equipe) avalia de 1 a 5.

`REQUISITOS` é política inicial, **a direção confirma**: ART/RRT modelo e seguro para todos; NR-10 para solar,
elétrica, automação e AVAC; NR-35 para solar.

## LGPD

- Base legal: consentimento do parceiro (data e versão do termo guardadas) e de quem pede orçamento.
- Vitrine (pública): nome público, especialidades, regiões, conselho-UF (sem número), documentos "em dia" (sem
  número nem arquivo), nota média e quantas avaliações. Nada de CPF/CNPJ, telefone, e-mail ou comentários.
- Equipe: CPF/CNPJ mascarado; completo só para a direção (`?completo=1`, com senha recente).
- Eliminação: `apagar` remove parceiro, documentos e avaliações; a cadeia de registro só tem metadados.
- O CPF/CNPJ do parceiro é obrigatório (é para conferir o registro e o seguro); de quem pede orçamento, não.

## Rotas para o `servidor.py` (colar)

```python
from . import parceiros as parceiros_mod          # topo
parceiros = parceiros_mod.Parceiros(hub)          # em criar_manipulador
# do_GET
if u.path == "/api/parceiros":
    g = lambda k: q.get(k, [""])[0][:80]
    return self._json(200, parceiros.vitrine(g("servico"), g("uf"), g("municipio"), g("ibge")))
if u.path == "/api/parceiros/interno":
    q_ = self._exigir(seg.EQUIPE)
    if not q_:
        return
    completo = q.get("completo", [""])[0] == "1" and seg.pode(q_, seg.DIRECAO)
    if completo and not self._sensivel(q_):
        return
    return self._json(200, parceiros.interno(completo=completo))
# do_POST, depois de corpo = self._corpo()
if u.path.startswith("/api/parceiros"):
    try:
        d = seg.carregar_json(corpo or "{}")
    except ValueError:
        return self._json(400, {"ok": False, "erro": "json invalido"})
    if not isinstance(d, dict):
        return self._json(400, {"ok": False, "erro": "json invalido"})
    if u.path in ("/api/parceiros/cadastro", "/api/parceiros/orcamento"):      # públicas, com limite por IP
        if self._limitado("publico"):
            return
        q_ = self._quem()
        r = (parceiros.cadastrar(d, "site") if u.path.endswith("cadastro")
             else parceiros.pedir_orcamento(d, usuario=q_["usuario"] if q_ else ""))
        return self._json(200 if r["ok"] else 400, r)
    m_ = re.fullmatch(r"/api/parceiros/(\d+)/(editar|documento|documento/remover|conferir|curadoria|avaliacao|apagar)", u.path)
    if not m_:
        return self._json(404, {"ok": False, "erro": "rota desconhecida"})
    pid, acao = int(m_.group(1)), m_.group(2)
    if acao == "avaliacao":
        q_ = self._sessao_ou_401()
        if not q_:
            return
        r = parceiros.avaliar(pid, d, q_["usuario"], eh_equipe=seg.pode(q_, seg.EQUIPE))
    else:
        q_ = self._exigir(seg.DIRECAO if acao in ("curadoria", "apagar") else seg.EQUIPE)
        if not q_:
            return
        if acao == "apagar" and not self._sensivel(q_):
            return
        u_ = q_["usuario"]
        r = {"editar": lambda: parceiros.editar(pid, d, u_),
             "documento": lambda: parceiros.documento(pid, d, u_),
             "documento/remover": lambda: parceiros.remover_documento(pid, int(d.get("id") or 0), u_),
             "conferir": lambda: parceiros.conferir_registro(pid, u_),
             "curadoria": lambda: parceiros.curar(pid, d.get("status"), d.get("motivo"), u_, seg.pode(q_, seg.DIRECAO)),
             "apagar": lambda: parceiros.apagar(pid, u_)}[acao]()
    return self._json(r.pop("codigo", 200 if r["ok"] else 400), r)
```

## Telas (integrador)

- **Loja** (`painel.html`, área da loja): embutir `sistema/physis-parceiros.js` (em `MODULOS` do
  `embutir_bases.py`: `"mod-parceiros": RAIZ / "sistema" / "physis-parceiros.js"`), pôr
  `<div id="parceiros-loja"></div>` na vista "Profissionais parceiros" e chamar
  `PARCEIROS.montarLoja(document.getElementById("parceiros-loja"))` depois de desenhar (só uma vez por elemento).
  Só funciona com servidor (`ui.central`); sem servidor, esconder a vista.
- **Gestão** (`gestao-interna-physis.html`): nova aba "Parceiros" com `<div id="parceiros-curadoria"></div>` e
  `PARCEIROS.montarCuradoria(el)`. O botão de curadoria fica desligado para quem não é direção (o servidor também barra).
- Central: os pedidos `origem: "parceiros"` aparecem junto dos outros pedidos; para avaliar, a equipe marca o
  pedido como `concluido` (`hub.central_marcar`).

## Limites

- Os documentos são metadados (arquivo opcional por id de `gestao_arquivo`); a conferência é humana.
- O parceiro não tem conta própria nem vê os pedidos: a Physis encaminha (pelo e-mail/WhatsApp de sempre).
- Não há pagamento nem comissão no fluxo.
