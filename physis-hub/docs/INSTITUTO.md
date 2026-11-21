# Instituto Physis: repositório e instalação próprios

Versão de 18/11/2026 (antes: 15/11/2026, "gêmeo do servidor").

## Em uma frase

O Instituto Physis (pesquisa, cursos, projetos sociais e o Physis 3D) tem **repositório próprio**
(`C:\physis\instituto-physis`), separado do Sistema Physis da Physis Engineering por decisão de 18/11/2026. Começou do
mesmo código (commit `e31aa7f` da Physis, com o histórico), mas é **outra instalação**: outro banco, outra marca, outro
suporte e outro catálogo. A única ligação com a Physis é o **intercâmbio** (`docs/INTERCAMBIO.md`): cada lado guarda o
seu banco e só recebe os conjuntos combinados depois que a direção aprova. Dados de saúde nunca passam pelo intercâmbio.

## O que é separado

| O quê | Physis | Instituto | Onde se define |
|---|---|---|---|
| Configuração | `instancia.json` do pacote `physis-physis-site` | `instancia.json` do pacote `physis-instituto-physis` | `montar.py`, ficha em `clientes/clientes.json` |
| Banco (contas, sessões, loja, chamados, cursos, dados do cliente) | `physis-hub.db` | `physis-instituto.db` | `"banco"` no `instancia.json` (na pasta dele) ou `PHYSIS_BANCO` |
| Marca nas telas | Physis Engineering | `"marca": {nome, logo_texto, cores}` | ficha `instituto-physis`; cores **só** da `PALETA.md` (o `montar.py` recusa outras) |
| Suporte (e-mail e WhatsApp) | `suporte` geral do `clientes.json` | `suporte` da própria ficha | `suporte_email` / `suporte_whatsapp` no `instancia.json`, ou `PHYSIS_SUPORTE_EMAIL` / `PHYSIS_SUPORTE_WHATSAPP` no serviço |
| Catálogo da loja | tabela `loja_item` do banco da Physis | tabela `loja_item` do banco do Instituto | cada banco tem o seu; a equipe do Instituto revisa e publica o dela |
| Módulos | os da ficha | `gestao, cursos, sbn, resiliencia, carbono, certificacoes, impressao3d` (Physis 3D, só do Instituto), `circular` (Economia circular: pesquisa, oficinas e trilhas), `medicamentos, pulseira` (Saúde e suporte TEA; consentimento do responsável legal para menores), com `pesquisa: true` | ficha `instituto-physis` |
| Código | repositório da Physis | repositório do Instituto | separação de 18/11/2026; troca de dados só pelo intercâmbio |
| Endereço | `hub.physis…` | `instituto.physis…` (a definir) | proxy (Caddy/nginx) |

`/api/instancia` devolve `"instalacao": "instituto"` e `"marca"` para as telas mostrarem o nome e as cores certas.

## Montar o pacote

```
cd physis-hub
python montar_clientes.py --saida ../pacotes --so instituto-physis
```

Ou à mão:

```
python montar.py --org instituto-physis --lugar sede-instituto --modulos gestao,cursos,sbn,resiliencia,carbono,certificacoes,impressao3d,circular,medicamentos,pulseira \
                 --pesquisa --nome "Instituto Physis" --instalacao instituto --banco physis-instituto.db \
                 --suporte-email <e-mail> --suporte-whatsapp <número> --marca marca-instituto.json --saida ../pacotes
```

## Rodar os dois na mesma máquina

Cada um na sua pasta, como serviço próprio, em porta própria e só em `127.0.0.1`; o proxy com HTTPS escolhe pelo nome
(`Host`). Nada é compartilhado: o pacote da Physis sai do repositório da Physis e o do Instituto sai deste repositório.
Depois de instalar, cada direção cadastra a outra em Minha conta → "Intercâmbio com outras plataformas" (`docs/INTERCAMBIO.md`).

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
exemplo): a variável vence o `instancia.json` e os dois passariam a usar o mesmo banco ou o mesmo suporte. Também não
use o mesmo arquivo de chaves do intercâmbio (`PHYSIS_INTERCAMBIO_CHAVES`) nos dois.

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

- Nome jurídico: "Instituto Physis" (D62 do Physis M&V), a confirmar depois do registro e do CNPJ (previsto para
  fev/2027, kit de abertura 17). E-mail e WhatsApp de suporte (na ficha estão como `[MARCADOR]`; enquanto isso, o suporte
  registra o chamado mas não envia e-mail, porque o endereço não é válido).
- Cores da marca: verde `#4A8A5A` e `#1F4A1C` (tipo C do guia de identidade, 20/11/2026; sem azul; logos aguardam a D43) e o texto do logo: esperam o sistema
  de marcas do M&V (D43).
- Endereço público: subdomínio da Physis (D64), domínio exato a confirmar; conta de e-mail (SMTP) do Instituto.
- Gestão: o Instituto terá a **sua própria** Gestão (cópia da Gestão Physis, com banco e tarefas próprios: Fase 0 pelo
  kit 17 e as 22 tarefas tiradas do sistema da Physis). Próxima etapa, depois dos templates e logos do M&V.
- Propriedade intelectual dos projetos e quem vende os produtos (peças 3D, cosméticos): esperam o advogado e a D37.
- Global South Alliance: só entra aqui depois da cessão do contrato ao CNPJ do Instituto (D67).
- As telas ainda não leem `marca` de `/api/instancia` (tarefa da integração das telas).
