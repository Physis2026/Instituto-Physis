# Alertas de clima por e-mail e WhatsApp (`physis_hub/alertas_clima.py`)

Os mesmos alertas que a plataforma mostra na tela (Início → "Para o seu negócio" e Resiliência climática)
agora também **chegam às pessoas**, por e-mail e, se ligado, por WhatsApp. O hub avalia a cada 15 minutos com
o que já tem guardado (não chama a internet para avaliar).

## 1. Regras (iguais às do painel, agora com dois níveis)

| Regra | Para quem | Atenção | Alerta |
|---|---|---|---|
| `geada_cafe` | café | mínima < 3 °C | < 1 °C |
| `chuva_colheita` | café, grãos (maio a setembro) | ≥ 10 mm | ≥ 30 mm |
| `calor_rebanho` | gado, gado de leite | máxima ≥ 30 °C | ≥ 35 °C |
| `chuva_irrigacao` | irrigação (hoje e amanhã) | ≥ 5 mm | — |
| `chuva_modelo` | irrigação, hortifrúti | modelo local (aprendizado.py) ≥ 70 % | — |
| `horta` | hortifrúti | ≥ 30 mm, < 4 °C ou ≥ 34 °C | ≥ 50 mm, < 2 °C ou ≥ 37 °C |
| `hospedagem_chuva` | hospedagem | ≥ 30 mm | ≥ 50 mm |
| `deslizamento` | todos | CEMADEN 24 h ≥ 40 mm ou 72 h ≥ 60 mm | 24 h ≥ 80 mm ou 72 h ≥ 120 mm |

Os níveis "alerta" acima dos limites do painel são premissa Physis (a confirmar pela equipe técnica). Encostas:
referência de planejamento; a pessoa sempre é lembrada de seguir a Defesa Civil.

## 2. Assinatura (LGPD)
- Só com `consentimento: true` (guarda a data e a versão do termo; o registro do lugar ganha só o id e os canais).
- A pessoa escolhe canais (`email`, `whatsapp`), alertas, atividades, nível mínimo e horário de silêncio
  (padrão 22:00–06:00; "alerta" fura o silêncio, a menos que `alerta_fura_silencio: false`).
- Sair (`acao: "sair"`): desativa e **apaga e-mail, telefone e apikey**. O histórico (texto do alerta, canal,
  situação) fica 90 dias, sem telefone.
- Mesmo alerta (regra + dia do evento) sai **uma vez por dia** por pessoa; só sai de novo se subir de atenção para alerta.

## 3. Canais
- **E-mail**: vai para a fila `email_saida` (ref `alerta-<id>`); o `correio.py` envia pelo servidor de e-mail da Physis.
- **WhatsApp** (opcional): `PHYSIS_WHATSAPP_PROVEDOR=callmebot` usa a mesma API do receptor de campo
  (`firmware/receptor-v6/src/whatsapp.cpp`): `GET https://api.callmebot.com/whatsapp.php?phone=+55...&text=...&apikey=...`,
  tempo máximo 10 s, texto cortado em 700 caracteres. Cada pessoa ativa o CallMeBot no próprio WhatsApp e informa a apikey.
  `PHYSIS_WHATSAPP_PROVEDOR=business` é o lugar reservado para a API oficial do WhatsApp Business (ainda não feita).
  Sem a variável, o WhatsApp fica registrado como "falhou: não configurado".

**Risco (aceito e documentado):** a apikey do CallMeBot precisa ir em texto na chamada, então não dá para guardar
só um resumo dela; com só a biblioteca padrão do Python não há cifra de verdade. Ela fica no banco do hub como
está: proteja o arquivo (`physis-hub.db`) com permissões e disco cifrado; a apikey nunca aparece nas listagens
(só os 3 últimos caracteres) e é apagada quando a pessoa sai. O CallMeBot é um serviço de terceiros: o texto do
alerta (sem dados pessoais além do número de destino) passa por ele. Para produção, preferir a API oficial.

## 4. Rotas (colar em `servidor.py`)

Topo: `from . import alertas_clima as alertas_mod`. Em `criar_manipulador` (depois de criar `aprendizado`, ver APRENDIZADO.md):

```python
    alertas = alertas_mod.AlertasClima(hub, aprendizado=aprendizado)
```

`do_GET`:

```python
            if u.path in ("/api/alertas/assinaturas", "/api/alertas/historico"):
                q = self._sessao_ou_401()
                if not q:
                    return
                quem = None if q["papel"] == "administrador" else q["usuario"]   # a direção vê todas
                if u.path.endswith("/historico"):
                    return self._json(200, {"ok": True, "historico": alertas.historico(quem=quem)})
                return self._json(200, {"ok": True, "assinaturas": alertas.assinaturas(quem),
                                        "regras": {k: v[0] for k, v in alertas_mod.REGRAS.items()},
                                        "atividades": list(alertas_mod.ATIVIDADES), "finalidade": alertas_mod.FINALIDADE,
                                        "whatsapp": bool(alertas.whatsapp), "agora": alertas.alertas_agora()})
```

`do_POST`:

```python
            if u.path == "/api/alertas/assinaturas":
                q = self._sessao_ou_401()
                if not q:
                    return
                try:
                    d = json.loads(corpo or "{}")
                except ValueError:
                    return self._json(400, {"ok": False, "erro": "json invalido"})
                if not isinstance(d, dict):
                    return self._json(400, {"ok": False, "erro": "json invalido"})
                admin = q["papel"] == "administrador"
                if d.get("acao") == "sair":
                    r = alertas.sair(int(d.get("id") or 0), q["usuario"], admin=admin)
                else:
                    d.pop("_admin", None)
                    if admin:
                        d["_admin"] = True
                    r = alertas.assinar(d, q["usuario"])
                return self._json(r.pop("codigo", 200 if r["ok"] else 400), r)
```

`main()` (depois da thread do aprendizado):

```python
    alertas_fundo = alertas_mod.AlertasClima(hub, aprendizado=apr_fundo)
    threading.Thread(target=alertas_mod.rodar, args=(alertas_fundo, parar),
                     kwargs={"enviar": lambda: alertas_mod.enviar_emails(hub, correio.enviar_fila)}, daemon=True).start()
```

## 5. Tela
Painel → **Resiliência climática** (e Monitoramento verde → Previsão): cartão "Receber estes avisos" com e-mail,
WhatsApp (+ apikey do CallMeBot, com o passo a passo de ativação), atividades (pré-marcadas com
`perfilLer().aprendido.atividades`), alertas, nível mínimo, horário de silêncio, a `finalidade` e a caixa de
consentimento (obrigatória). Abaixo, "Avisos enviados" (`/api/alertas/historico`) e o botão "Parar de receber".
Gestão → **Direção**: lista de assinaturas (sem apikey) e o histórico.
