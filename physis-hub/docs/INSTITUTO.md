# Instituto Physis: o gêmeo do servidor

Versão de 15/11/2026.

## Em uma frase

O Instituto Physis (pesquisa, cursos e projetos sociais) usa **o mesmo código** do servidor da Physis, mas é **outra
instalação**: outro arquivo de configuração, outro banco, outra marca, outro suporte e outro catálogo. Os dados das
duas nunca se misturam, mesmo rodando na mesma máquina.

## O que é separado

| O quê | Physis | Instituto | Onde se define |
|---|---|---|---|
| Configuração | `instancia.json` do pacote `physis-physis-site` | `instancia.json` do pacote `physis-instituto-physis` | `montar.py`, ficha em `clientes/clientes.json` |
| Banco (contas, sessões, loja, chamados, cursos, dados do cliente) | `physis-hub.db` | `physis-instituto.db` | `"banco"` no `instancia.json` (na pasta dele) ou `PHYSIS_BANCO` |
| Marca nas telas | Physis Engineering | `"marca": {nome, logo_texto, cores}` | ficha `instituto-physis`; cores **só** da `PALETA.md` (o `montar.py` recusa outras) |
| Suporte (e-mail e WhatsApp) | `suporte` geral do `clientes.json` | `suporte` da própria ficha | `suporte_email` / `suporte_whatsapp` no `instancia.json`, ou `PHYSIS_SUPORTE_EMAIL` / `PHYSIS_SUPORTE_WHATSAPP` no serviço |
| Catálogo da loja | tabela `loja_item` do banco da Physis | tabela `loja_item` do banco do Instituto | cada banco tem o seu; a equipe do Instituto revisa e publica o dela |
| Módulos | os da ficha | `gestao, cursos, sbn, resiliencia, carbono, certificacoes`, com `pesquisa: true` | ficha `instituto-physis` |
| Endereço | `hub.physis…` | `instituto.physis…` (a definir) | proxy (Caddy/nginx) |

`/api/instancia` devolve `"instalacao": "instituto"` e `"marca"` para as telas mostrarem o nome e as cores certas.

## Montar o pacote

```
cd physis-hub
python montar_clientes.py --saida ../pacotes --so instituto-physis
```

Ou à mão:

```
python montar.py --org instituto-physis --lugar sede-instituto --modulos gestao,cursos,sbn,resiliencia,carbono,certificacoes \
                 --pesquisa --nome "Instituto Physis" --instalacao instituto --banco physis-instituto.db \
                 --suporte-email <e-mail> --suporte-whatsapp <número> --marca marca-instituto.json --saida ../pacotes
```

## Rodar os dois na mesma máquina

Cada um na sua pasta, como serviço próprio, em porta própria e só em `127.0.0.1`; o proxy com HTTPS escolhe pelo nome
(`Host`). Nada é compartilhado além do código (cada pasta tem a sua cópia).

```
/srv/physis/physis-physis-site/        PHYSIS_PORTA=8700  (banco physis-hub.db)
/srv/physis/physis-instituto-physis/   PHYSIS_PORTA=8701  (banco physis-instituto.db)
```

Variáveis de cada serviço (as de segurança de `SEGURANCA.md` valem para os dois):

```
# Physis                                   # Instituto
PHYSIS_ENDERECO=127.0.0.1                  PHYSIS_ENDERECO=127.0.0.1
PHYSIS_PORTA=8700                          PHYSIS_PORTA=8701
PHYSIS_PROXY_CONFIAVEL=127.0.0.1,::1       PHYSIS_PROXY_CONFIAVEL=127.0.0.1,::1
PHYSIS_EXPOSTO=1                           PHYSIS_EXPOSTO=1
PHYSIS_URL_PUBLICA=https://hub.exemplo     PHYSIS_URL_PUBLICA=https://instituto.exemplo
PHYSIS_SMTP_*  (conta da Physis)           PHYSIS_SMTP_*  (conta do Instituto)
```

Atenção: **não** defina `PHYSIS_BANCO` nem `PHYSIS_SUPORTE_*` em comum para os dois (num arquivo de ambiente global, por
exemplo): a variável vence o `instancia.json` e os dois passariam a usar o mesmo banco ou o mesmo suporte. Para rodar as
duas a partir de uma única cópia do código, aponte cada serviço para o seu arquivo com `PHYSIS_INSTANCIA=/caminho/instancia.json`
(o banco fica na pasta desse arquivo).

**Caddy**:

```
hub.exemplo.com.br {
    reverse_proxy 127.0.0.1:8700 {
        header_up X-Forwarded-For {remote_host}
    }
}
instituto.exemplo.com.br {
    reverse_proxy 127.0.0.1:8701 {
        header_up X-Forwarded-For {remote_host}
    }
}
```

**nginx**: dois blocos `server` iguais ao de `SEGURANCA.md`, um com `server_name hub…` e `proxy_pass http://127.0.0.1:8700`,
outro com `server_name instituto…` e `proxy_pass http://127.0.0.1:8701`.

Sem nome de domínio (rede interna): use as duas portas direto (`http://<ip>:8700/` e `http://<ip>:8701/`).

## Primeira conta e cópias de segurança

Cada servidor cria a **sua** primeira conta (que vira a direção dele): uma pessoa da direção da Physis não entra no
Instituto com a conta da Physis, e vice-versa. Faça a cópia de segurança dos dois bancos (`physis-hub.db` e
`physis-instituto.db`, mais os `-wal`) separadamente.

## O que ainda falta confirmar ([MARCADOR])

- Nome jurídico do Instituto, e-mail e WhatsApp de suporte (na ficha estão como `[MARCADOR]`; enquanto isso, o suporte
  registra o chamado mas não envia e-mail, porque o endereço não é válido).
- Cores da marca (hoje dois azuis da `PALETA.md`, `#2C5A6E` e `#1C3550`, a aprovar) e o texto do logo.
- Endereço público e conta de e-mail (SMTP) do Instituto.
- Se a Gestão do Instituto será a Gestão interna da Physis (hoje não: o pacote não leva `gestao-interna-physis.html`).
- As telas ainda não leem `marca` de `/api/instancia` (tarefa da integração das telas).
