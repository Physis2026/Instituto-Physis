# Suporte remoto com prazo ("Permitir suporte")

Pedido em `LISTA-DE-MODIFICACOES.md` §3 (15/11/2026). Código: `physis_hub/suporte_remoto.py` (servidor) e
`sistema/physis-suporte-remoto.js` (tela, na área de conta e segurança). Testes: `tests/test_suporte_remoto.py`.

## Como funciona

1. A **direção** da instalação (papel administrador) abre "Permitir suporte", confirma a senha (reautenticação),
   escolhe o prazo (2 h, 8 h, 1 dia ou 3 dias), uma nota opcional e, se quiser, **só ver**.
2. O servidor cria a concessão (início, fim, quem liberou) e mostra **uma vez** um código aleatório. O banco guarda só o
   resumo SHA-256 do código.
3. A equipe da Physis entra pela **VPN** com o código e a conta da equipe (lista em `PHYSIS_SUPORTE_CONTAS`). Pedido de
   endereço fora de `PHYSIS_SUPORTE_REDES` é recusado mesmo com o código certo. 5 erros seguidos do mesmo endereço
   bloqueiam por 60 s.
4. A sessão de suporte tem o papel **equipe** (operador) na instalação; com "só ver", só leitura (GET/HEAD).
5. A direção revoga quando quiser; o prazo encerra sozinho (no máximo 8 h por sessão, nunca além da concessão).
6. Tudo vai para o registro encadeado do hub (`hub.registrar`, tipo `suporte_remoto`) e para a lista que o cliente vê:
   concessão, entrada, cada rota chamada (método e caminho, **sem** consulta nem corpo), recusas, revogação, vencimento.
   O código e o token nunca são registrados em texto.

LGPD: o suporte vê o que a equipe da instalação vê. Nada é copiado para a Physis por este recurso. O aviso está no botão.

## Para o Eric: contas da equipe e VPN (doc 10, item 0.3)

`PHYSIS_SUPORTE_CONTAS` é a lista (vírgula) das contas da equipe Physis que podem usar um código de suporte nesta
instalação, por exemplo `suporte@physis.example,eric@physis.example`. A instalação do cliente não guarda contas da Physis:
a conta só identifica quem entrou (vai para o registro e para a lista do cliente); o consentimento é o código que a
direção do cliente gera, e a barreira de rede é a VPN. Tirar alguém da equipe = tirar da lista e reiniciar o serviço.
Sem a lista (ou sem `PHYSIS_SUPORTE_REDES`), ninguém entra como suporte.

**Decisão D23 (15/11/2026): por enquanto, nenhuma conta da Physis.** O padrão de `PHYSIS_SUPORTE_CONTAS` é **vazio** e
fica vazio nas instalações: com a lista vazia, ninguém consegue entrar com o código, e a tela "Permitir suporte" avisa isso à
direção do cliente. A conta do Eric fica prevista para a **fase 2** (não configurar antes).

## Transporte: VPN (montada pelo Eric, doc 10, item 0.3)

A Physis **não hospeda túnel** aqui. O servidor do cliente (Linux) entra numa VPN da Physis; o painel e o SSH só
respondem pela interface da VPN.

WireGuard (exemplo, rede 10.8.0.0/24, interface `wg0`):

    sudo apt install wireguard
    wg genkey | tee /etc/wireguard/privada | wg pubkey > /etc/wireguard/publica
    sudo systemctl enable --now wg-quick@wg0
    sudo wg show

Tailscale (rede 100.64.0.0/10 e fd7a:115c:a1e0::/48):

    curl -fsSL https://tailscale.com/install.sh | sh     # [CONFERIR] método de instalação da distribuição
    sudo tailscale up
    tailscale ip -4

Configuração do servidor Physis (variáveis de ambiente do serviço systemd):

    PHYSIS_SUPORTE_REDES="10.8.0.0/24"               # ou "100.64.0.0/10 fd7a:115c:a1e0::/48" no Tailscale
    PHYSIS_SUPORTE_CONTAS=""                          # D23: vazio por enquanto (ninguém entra); Eric na fase 2

Firewall: painel (porta do hub) e SSH só pela VPN.

ufw:

    sudo ufw default deny incoming
    sudo ufw allow in on wg0 to any port 22 proto tcp
    sudo ufw allow in on wg0 to any port 8700 proto tcp
    sudo ufw enable

nftables (trecho):

    table inet physis {
      chain entrada { type filter hook input priority 0; policy drop;
        ct state established,related accept
        iif "lo" accept
        iifname "wg0" tcp dport { 22, 8700 } accept
      }
    }

O IP de quem chama vem de `seguranca.ip_do_cliente` (respeita `PHYSIS_PROXIES` quando há proxy reverso). Sem
`PHYSIS_SUPORTE_REDES`, ninguém entra como suporte.

Linux e portabilidade: só biblioteca padrão (`ipaddress`, `secrets`, `hashlib`, `sqlite3`); nenhuma API exclusiva do
Windows; arquivos em UTF-8 com fim de linha LF.

## Integração (aplicada em 15/11/2026)

Testes pela rede: `tests/test_suporte_remoto_rotas.py`. O resumo abaixo fica como referência.

`physis_hub/servidor.py`:

    from . import suporte_remoto as suporte_mod
    # na criação do servidor, junto dos outros módulos:
    suporte = suporte_mod.SuporteRemoto(hub)

    # _quem(): sem sessão normal, tenta a de suporte (cookie physis_suporte)
    if not q:
        q = suporte.sessao(self._cookie("physis_suporte"), self._ip())
    # antes de executar qualquer rota com sessão de suporte:
    if q and q.get("suporte"):
        if not suporte.pode_metodo(q, self.command):
            suporte.uso(q, self.command, u.path, self._ip(), recusado=True)
            return self._json(403, {"ok": False, "erro": "Acesso de suporte só para ver."})
        suporte.uso(q, self.command, u.path, self._ip())

    # GET
    if u.path == "/api/suporte-remoto":
        r = suporte.listar(self._quem()); return self._json(r.pop("codigo", 200), r)
    # POST
    if u.path == "/api/suporte-remoto/conceder":
        r = suporte.conceder(self._quem(), d.get("duracao", ""), d.get("nota", ""), bool(d.get("so_ver")), self._ip())
        return self._json(r.pop("codigo", 200), r)
    if u.path == "/api/suporte-remoto/revogar":
        r = suporte.revogar(self._quem(), str(d.get("id", "")), self._ip()); return self._json(r.pop("codigo", 200), r)
    if u.path == "/api/suporte-remoto/entrar":      # público; o módulo confere a VPN, o código e a conta da equipe
        r = suporte.entrar(d.get("codigo", ""), d.get("equipe", ""), self._ip(), self.headers.get("User-Agent", ""))
        # se ok: Set-Cookie physis_suporte=<token>; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=<expira-agora>
    if u.path == "/api/suporte-remoto/sair":
        suporte.sair(self._cookie("physis_suporte"), q, self._ip())

Tabelas: criadas pelo próprio módulo (`suporte_remoto.ESQUEMA`, `CREATE TABLE IF NOT EXISTS`); não precisa mexer
em `hub.ESQUEMA`.

`ferramentas/embutir_bases.py`, em `MODULOS`:

    "mod-suporte-remoto": S / "physis-suporte-remoto.js",   # "Permitir suporte" (conta e segurança)

`physis-hub/web/painel.html`, na tela "Minha conta" da direção (depois do bloco de verificação em duas etapas):

    ${seg.pode && window.PhysisSuporteRemoto && ehDirecao() ? '<div id="sr-raiz"></div>' : ""}
    // depois de desenhar:
    const sr = el("sr-raiz"); if (sr) PhysisSuporteRemoto.ligar(sr, { idioma: () => lang, pedir: PhysisConta.pedir });

A reautenticação usa a ponte existente de `physis-conta.js` (`403 {reautenticar:true}` pede a senha e repete o pedido).
