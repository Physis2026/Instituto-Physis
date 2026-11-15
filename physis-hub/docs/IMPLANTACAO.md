# Implantação no cliente (Raspberry Pi, mini PC) e roteiro de campo

Scripts em `implantacao/` (raiz do repositório). Testes: `tests/test_implantacao.py`.
Serviços do servidor da Physis (Superset, GeoServer, Node-RED, motores de cálculo, IA): `docs/SERVICOS_ABERTOS.md`.

## Em uma frase

O pacote do cliente (`montar.py`) vira um serviço do sistema (`systemd` no Linux, serviço/tarefa no Windows) que
sobe sozinho ao ligar, guarda os dados numa pasta só dele, faz cópia cifrada todo dia e se confere com um comando.

## Onde fica cada coisa (Linux)

| O quê | Onde | Dono / permissão |
|---|---|---|
| Código (só leitura para o serviço) | `/opt/physis/versoes/<data>`, atalho `/opt/physis/atual` | root, 0755 |
| Banco, mapas, entregas, editais | `/var/lib/physis/` | `physis`, 0750 |
| Variáveis e segredos | `/etc/physis/physis.env` (modelo: `implantacao/physis.env.exemplo`) | root:physis, 0640 |
| Senhas MQTT dos nós | `/etc/physis/mqtt/<nó>.senha` | root, 0600 |
| Configuração da cópia | `/etc/physis/backup.env` (modelo: `implantacao/backup.env.exemplo`) | root, 0600 |
| Scripts | `/opt/physis/implantacao/` | root |
| Serviços | `physis-hub.service`, `physis-backup.timer` (02:30) | — |

O serviço roda como o usuário de sistema `physis`, sem privilégios e com o sistema de arquivos travado
(`NoNewPrivileges`, `ProtectSystem=strict`, só `/var/lib/physis` gravável, `PrivateTmp`, filtros de chamadas do sistema).

## Instalar (Raspberry Pi OS / Debian 12)

```
unzip physis-fazenda-x.zip            # ou copie a pasta do pacote
sudo implantacao/instalar.sh --pacote physis-fazenda-x.zip \
     --mosquitto --mqtt-no irrigacao-zona1 --caddy lan --ufw
sudo /opt/physis/implantacao/verificar.sh
```

Sem opções, o instalador pergunta o que é opcional; `--sim` não pergunta nada. Pode rodar de novo: o que já existe
fica (inclusive segredos e o `instancia.json` local). Opções principais:

| Opção | Efeito |
|---|---|
| `--mosquitto` | Instala o Mosquitto: sem anônimo, um usuário por nó ESPHome (mesmo nome do nó) e ACL `%u/#` (cada Caixinha só no próprio tópico). A senha do hub vai para `PHYSIS_MQTT_SENHA`; a de cada nó para `/etc/physis/mqtt/<nó>.senha` → copie para o `secrets.yaml` do ESPHome. Cadastre os nós no `instancia.json` (`docs/MQTT.md`). |
| `--caddy lan` | HTTPS na rede local com a CA própria do Caddy. O hub segue em `http://<pi>:8700` só para o receptor V6 (firewall: só rede local); pessoas entram por `https://<ip>/` (`PHYSIS_HTTPS=1` deixa o cookie sempre `Secure`). Instale o certificado raiz em cada aparelho (abaixo). |
| `--caddy dominio --dominio X --email Y` | Let's Encrypt. O hub passa a escutar só em `127.0.0.1`, `PHYSIS_EXPOSTO=1`, `PHYSIS_ACEITAR_SEM_CHAVE=0` (todo aparelho com chave). Precisa das portas 80/443 chegando ao aparelho. |
| `--ufw` | Firewall: SSH, hub, MQTT e HTTPS só da rede local (`--rede` ou detectada); no modo domínio, 80/443 abertas. |

**Certificado da rede local (`--caddy lan`).** Copie `/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt`
para cada celular/computador e instale como "certificado de autoridade confiável" (Android: Configurações → Segurança →
Instalar certificado → CA; iPhone: abrir o arquivo, instalar o perfil e ligar em Ajustes → Geral → Sobre → Confiança).
Depois disso o app instala no celular. O HSTS começa com 1 dia; suba para 1 ano em `/etc/caddy/Caddyfile` quando todos
os aparelhos tiverem o certificado.

## Cópia de segurança

1. Pendrive sempre montado no mesmo lugar (`/etc/fstab` com `UUID=... /media/physis-backup ext4 defaults,nofail 0 2`).
2. Chave `age` **fora do aparelho**: no computador da Physis, `age-keygen -o physis-backup-<cliente>.chave`
   (guarde no cofre). No Pi, só a chave pública (`age1...`) vai em `AGE_DESTINATARIO`. Quem rouba o Pi não lê as cópias.
3. `sudo apt install age`, `sudo cp /opt/physis/implantacao/backup.env.exemplo /etc/physis/backup.env`,
   `sudo chmod 600 /etc/physis/backup.env`, preencha e ligue: `sudo systemctl enable --now physis-backup.timer`.
4. Teste já: `sudo /opt/physis/implantacao/backup.sh --rotulo teste` e `sudo /opt/physis/implantacao/restaurar.sh --arquivo <cópia> --chave-age <chave> --so-conferir`.

Como funciona: cópia **com o hub ligado** (API de backup do SQLite / `sqlite3 .backup`, feita como o usuário `physis`),
`PRAGMA integrity_check`, pacote com `instancia.json` e `editais/`, cifra, `SHA-256` ao lado, giro **7 diárias,
4 semanais (domingo), 12 mensais**, e espelho opcional por `rsync` com chave SSH dedicada (`RSYNC_DESTINO`).
O `physis.env` (segredos) **não** vai na cópia: anote-o no cofre na instalação.

`openssl` (CIFRA=openssl) é a alternativa sem `age`: AES-256-CBC com PBKDF2 (600 mil voltas), mas a senha fica num
arquivo do próprio aparelho e o CBC não detecta adulteração (o `.sha256` ao lado ajuda só contra corrupção). Prefira `age`.

**Restaurar:** `sudo /opt/physis/implantacao/restaurar.sh --arquivo <cópia.age> --chave-age <chave>`. Confere o SHA-256 e a
integridade, para o serviço, guarda o banco atual como `physis-hub.db.antes-restauro-<data>`, põe a cópia, sobe e roda
o `verificar.sh`. O `instancia.json` da cópia fica ao lado (`instancia.json.da-copia`) para comparar.

## Atualizar em campo (pacote novo, mesmo banco)

```
sudo /opt/physis/implantacao/atualizar.sh --pacote physis-fazenda-x-v2.zip
```

1. Copia a versão nova para `/opt/physis/versoes/<data>` (a atual não é tocada; o `instancia.json` local é mantido).
2. Roda os testes rápidos da versão nova como `physis`, em pasta temporária (`--testes-completos` para todos). Falhou → nada muda.
3. Para o serviço, copia o banco (`physis-hub.db.pre-atualizacao` e, com `backup.env`, uma cópia cifrada avulsa).
4. Troca o atalho `atual` e sobe; **o hub migra o banco sozinho** ao abrir.
5. Espera `/api/instancia` e `/api/saude` com a cadeia do registro íntegra. Falhou → **volta sozinho**: código anterior e banco de antes.
6. Mantém as 3 versões mais novas.

## Conferir

`sudo /opt/physis/implantacao/verificar.sh` → serviço, porta, `/api/saude` (cadeia íntegra), disco (aviso 85 %, falha 95 %),
idade da última cópia (falha > 26 h), Mosquitto, Caddy, relógio sincronizado (o Pi não tem relógio com bateria) e
subtensão do Pi (`vcgencmd get_throttled`). Sai com 1 se houver falha (dá para pôr no cron/monitoramento).

## Windows (mini PC)

PowerShell como Administrador (scripts só ASCII, por causa do PowerShell 5.1):

```
powershell -ExecutionPolicy Bypass -File implantacao\instalar.ps1 -Pacote C:\entregas\physis-fazenda-x.zip -Firewall
```

- Python 3.10+ "para todos os usuários" (python.org). Código em `C:\Physis\versoes\<data>` (junção `C:\Physis\atual`);
  dados e `physis.env` em `%ProgramData%\Physis` (só Administradores, SYSTEM e LOCAL SERVICE).
- Serviço pelo **NSSM** (`nssm.exe` no PATH ou em `C:\Physis\`), ou, sem ele, **tarefa agendada** "ao ligar" com reinício
  a cada minuto. Os dois rodam como `LOCAL SERVICE` e leem o ambiente do `physis.env` (nada de segredo no registro).
- Firewall: porta do hub só para a sub-rede local no perfil Privado (marque a rede do cliente como Privada).
- Cópia: `backup.ps1` (tarefa diária 02:30 como SYSTEM; `age.exe` ou `openssl.exe` no PATH; mesmo `backup.env`, em
  `%ProgramData%\Physis\backup.env`). Conferir: `verificar.ps1`. Atualizar no Windows: ainda manual (rodar `instalar.ps1`
  com o pacote novo cria outra versão e troca a junção; antes, pare o serviço e faça `backup.ps1 -Rotulo pre-atualizacao`).
- Mosquitto e Caddy no Windows: não automatizados; prefira um Pi para o broker.

## Checklist de campo (imprimir)

Segue o roteiro do documento 16 (Fase 2).

**No escritório (com internet)**

- [ ] Pacote montado (`montar.py --org ... --modulos ...`) e anotado: versão, data, módulos.
- [ ] Cartão SD gravado (Raspberry Pi OS Lite 64 bits), SSH com chave, usuário próprio, `sudo apt full-upgrade`.
- [ ] `instalar.sh` rodado com as opções do lugar; `verificar.sh` sem FALHA.
- [ ] Cada tela aberta uma vez **com internet** (cache: clima, relevo, solo, rio, irradiação).
- [ ] Acesso do cliente criado (pela rede local) e chaves dos aparelhos (Gestão → dispositivos); cada chave gravada no firmware.
- [ ] Mosquitto: senha de cada nó no `secrets.yaml` do ESPHome; nós no `instancia.json`.
- [ ] `backup.env` preenchido, chave `age` privada no cofre, `backup.sh --rotulo teste` e `restaurar.sh --so-conferir` OK.
- [ ] `physis.env` anotado no cofre. `python3 -m unittest discover -s tests` na pasta do pacote.
- [ ] Mala: fonte oficial do Pi, nobreak, pendrive da cópia, soluções-padrão pH 4/7/10, cabos, etiquetas com ID (1 a 99) de cada placa.

**No lugar, dia 1**

- [ ] Pi e receptor ligados no nobreak; relógio sincronizado (`verificar.sh`).
- [ ] Sinal LoRa medido nos pontos planejados antes de fixar.
- [ ] 1 transmissor e 1 Caixinha instalados; leituras chegando na tela.
- [ ] Sensores calibrados (umidade seco/encharcado; pH) — data e responsável na Gestão → Manutenção.
- [ ] Certificado da CA local instalado nos celulares do cliente (se `--caddy lan`); app instalado.

**Dias 2 a 7 (todo dia)**

- [ ] Leituras chegando (meta: 95 % recebidas).
- [ ] Alertas: nó fora, bateria, chuva — chegando em menos de 5 min.
- [ ] Rega automática: nenhuma válvula aberta além do tempo máximo.
- [ ] E-mails na fila (ou enviados, se SMTP configurado).
- [ ] Cópia de segurança do dia (`verificar.sh`: "última cópia há ... h").
- [ ] Teste de queda de energia (com nobreak): nenhum dado perdido.

**Fim da semana**

- [ ] Relatório exportado ("Baixar esta tela"); previsão local × chuva medida.
- [ ] Falhas e pedidos do cliente anotados na Gestão.
- [ ] Critério de "passou" (doc. 16, item 5) marcado: ___ % leituras · válvulas OK · alertas < 5 min · sem perda.

## O que ainda não foi verificado

- Nenhum script rodou num Pi/mini PC de verdade: só checagem de sintaxe (`bash -n`, analisador do PowerShell) e os
  testes estáticos. Falta rodar `instalar.sh`, `backup.sh`, `restaurar.sh` e `atualizar.sh` num Pi 4/5 (TRL de bancada).
- O formato do arquivo de ACL e as permissões exigidas pelo Mosquitto 2.0.x do Debian (aviso de dono do arquivo).
- `montar.py` ainda não copia `implantacao/` para dentro do pacote: hoje use `--pacote` ou leve a pasta junto.
