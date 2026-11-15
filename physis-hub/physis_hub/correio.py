"""Envio dos e-mails da fila (email_saida) pelo servidor de e-mail PRÓPRIO da Physis.

Nada de serviço de terceiros: o Hub fala SMTP direto com o servidor da Physis (por
exemplo Stalwart ou Mailcow, instalado pelo Eric Oliveira). As credenciais vêm de
variáveis de ambiente do servidor, nunca do código:

    PHYSIS_SMTP_HOST       endereço do servidor de e-mail (sem ele, nada é enviado)
    PHYSIS_SMTP_PORTA      587 (STARTTLS, padrão) ou 465 (TLS direto)
    PHYSIS_SMTP_USUARIO    conta que envia
    PHYSIS_SMTP_SENHA      senha dessa conta
    PHYSIS_SMTP_REMETENTE  endereço que aparece como remetente (padrão: o usuário)

Sem servidor configurado, o e-mail fica "pendente" na fila e a equipe o envia pela
Gestão (copiar e marcar como enviado). A conexão sempre usa TLS; sem TLS, não envia.
"""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage


def configurado() -> bool:
    return bool(os.environ.get("PHYSIS_SMTP_HOST"))


def enviar(para: str, assunto: str, corpo: str) -> tuple[bool, str]:
    host = os.environ.get("PHYSIS_SMTP_HOST")
    if not host:
        return False, "servidor de e-mail ainda nao configurado"
    porta = int(os.environ.get("PHYSIS_SMTP_PORTA", "587"))
    usuario = os.environ.get("PHYSIS_SMTP_USUARIO", "")
    senha = os.environ.get("PHYSIS_SMTP_SENHA", "")
    remetente = os.environ.get("PHYSIS_SMTP_REMETENTE", usuario)
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = remetente, para, assunto
    msg.set_content(corpo)
    ctx = ssl.create_default_context()
    try:
        if porta == 465:
            with smtplib.SMTP_SSL(host, porta, context=ctx, timeout=20) as s:
                if usuario:
                    s.login(usuario, senha)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, porta, timeout=20) as s:
                s.starttls(context=ctx)         # sem TLS, levanta erro e nada é enviado
                if usuario:
                    s.login(usuario, senha)
                s.send_message(msg)
        return True, ""
    except Exception as e:                       # o motivo vai para a fila; a senha nunca entra na mensagem
        return False, type(e).__name__ + ": " + str(e)[:200]


def enviar_fila(hub, ref: str | None = None) -> int:
    """Envia os pendentes (de uma instalação, se ref for dado). Devolve quantos saíram."""
    if not configurado():
        return 0
    n = 0
    for e in hub.emails("pendente"):
        if ref and e["ref"] != ref:
            continue
        ok, erro = enviar(e["para"], e["assunto"], e["corpo"])
        hub.email_marcar(e["id"], "enviado" if ok else "falhou", erro)
        n += ok
    return n
