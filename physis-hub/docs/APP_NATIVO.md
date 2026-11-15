# App nativo (Android e iPhone) — fase 2

Versão 0.1 · 15/11/2026 · **preparado, não compilado** (esta máquina não tem Node, Android Studio nem Xcode).

Decisão: o app é **a mesma plataforma** do PWA (`docs/APPS.md`), embrulhada com **Capacitor 6**, só para ganhar
**Bluetooth (BLE)** para a Saúde (caixinha de remédios ESP32 e pulseira) e, depois, avisos (notificações).
Independência (regra 11): código aberto, nenhum serviço de terceiros obrigatório (sem Firebase por padrão), os dados
ficam no servidor do cliente ou da Physis. LGPD: dado de saúde é sensível — consentimento, mínimo de dados, cifra no celular.

## 1. Em uma frase (para explicar a quem não é da área)

O Capacitor é uma "moldura" de app: dentro dela roda a mesma página da plataforma, guardada no celular; a moldura
só acrescenta o que o navegador não dá (Bluetooth com a tela apagada, avisos, ícone na loja). A página conversa com
o servidor que a pessoa digita no primeiro uso.

## 2. Arquivos

| Arquivo | Para quê |
|---|---|
| `app-nativo/package.json` | Capacitor 6 (core, cli, android, ios), bluetooth-le, preferences, local-notifications, serviço em primeiro plano. Versões fixas — **conferir versões ao instalar** (`npm view <pacote> versions`) |
| `app-nativo/capacitor.config.json` | `appId br.com.physisengineering.app` (**confirmar**: depois de publicado na loja não muda), `appName Physis`, `webDir www`, sem `server.url` (nada remoto), `allowNavigation: []`, `cleartext: false`, CapacitorHttp e CapacitorCookies ligados, textos do seletor BLE em português |
| `app-nativo/scripts/preparar_www.py` | Monta `www/` a partir de `physis-hub/web` ou de um pacote do `montar.py` (pasta ou .zip); sem Gestão; sem `sw.js`; põe CSP + `physis-nativo.js` + `physis-ble.js` |
| `app-nativo/www-extra/physis-nativo.js` | `window.PHYSIS_NATIVO = true`; manda para o primeiro uso; leva `api/…` e `/api/…` para o servidor escolhido; serviço em primeiro plano da pulseira |
| `app-nativo/www-extra/primeiro-uso.html` + `.js` | Tela de primeiro uso (seção 5) |
| `app-nativo/scripts/aplicar_plataformas.py` | Depois de `npx cap add`: permissões Android, textos iOS, mínimos de versão, manifesto de privacidade |
| `app-nativo/plataformas/android/AndroidManifest.trecho.xml` | Permissões BLE, avisos, serviço `connectedDevice`, sem backup na nuvem |
| `app-nativo/plataformas/ios/Info.trecho.plist`, `PrivacyInfo.xcprivacy` | Textos de permissão em PT, `bluetooth-central`, manifesto de privacidade da Apple |
| `app-nativo/scripts/gerar_icones.py` | Ícones e telas de abertura de todos os tamanhos, da árvore do logo (reaproveita `physis_hub/app_pwa.py`) |
| `app-nativo/site/baixar.html` | Página "Baixar o app" (PT/EN): Google Play, App Store, APK direto com SHA-256, instalar pelo navegador, requisitos, privacidade |
| `app-nativo/scripts/publicar_baixar.py` + `qr.py` | Preenche a página para publicar: endereços, SHA-256, QR em SVG gerado aqui (sem serviço de fora) |
| `sistema/physis-ble.js` | Biblioteca BLE única (app nativo / Web Bluetooth / indisponível), fila cifrada, envio ao hub |
| `firmware/saude/BLE_PERFIL.md` | Perfil GATT dos aparelhos (UUIDs, comandos, segurança, consumo, testes) |
| `tests/test_app_nativo.py` | Testes (seção 13) |

## 3. Como a página fala com o servidor dentro do app

- A página é servida de dentro do app: Android `https://localhost`, iPhone `capacitor://localhost`.
- `physis-nativo.js` troca `api/…` e `/api/…` por `<servidor>/api/…`.
- **CapacitorHttp** (ligado no `capacitor.config.json`) faz o pedido pelo lado nativo: **sem CORS** e sem cabeçalho
  `Origin`; **CapacitorCookies** guarda o cookie `physis_sessao` (HttpOnly, SameSite=Strict) no próprio app.
- CSRF (`docs/SEGURANCA.md`): sem `Origin`/`Referer` o hub não recusa; com `PHYSIS_CSRF_ESTRITO=1` a plataforma
  precisa mandar `X-Physis-CSRF` (o token vem de `/api/instancia`) — o mesmo trabalho que já é preciso no site.
- Se um dia o CapacitorHttp for desligado (fetch do WebView), o hub precisaria de CORS com credenciais para
  `https://localhost` e `capacitor://localhost` **e** dessas origens em `PHYSIS_ORIGENS`. Hoje não é preciso.
- A CSP do app (meta, posta pelo `preparar_www.py`) é a do servidor mais as origens do Capacitor; `connect-src`
  aceita só `https:` (ou só o servidor dado em `--hub`, para um app de um cliente só).

## 4. Bluetooth: `sistema/physis-ble.js`

API: `PhysisBLE.disponivel()`, `procurar({tipo:"med"|"pul"})`, `conectar(id)`, `inscrever(cb)`, `escrever(cmd)`,
`desconectar()`, mais `configurar({hub, chaves})`, `pendentes()`, `enviarPendentes()`, `texto(chave, "pt"|"en")`.

1. **App nativo** (`window.Capacitor.isNativePlatform()`): plugin `BluetoothLe` (lista do sistema, pareamento, fundo).
2. **Web Bluetooth** (`navigator.bluetooth`): Chrome/Edge no Android, Windows, macOS, Linux, ChromeOS, só em HTTPS.
3. **Nenhum**: mensagem clara (PT/EN) dizendo o que fazer.

O que chega é a linha V6 MED/PUL (`physis_hub/saude.py`), em pedaços terminados por `\n`. A biblioteca remonta,
confere (ID 1–99, TIPO MED/PUL, ≤ 240, TIPO do aparelho), põe o `TS` do celular se o aparelho não tem relógio,
guarda na fila **IndexedDB cifrada com AES-GCM** (chave por sessão de aparelho, derivada por HKDF de uma
chave-mestra não exportável) e envia `POST /api/saude/linha` com `X-Physis-Chave` (uma chave por aparelho, criada em
`POST /api/dispositivos/chaves` com `no`), `credentials: "omit"`. Sem rede: tenta de novo com espera crescente
(até 5 min) e quando a rede volta. Linhas PUL (com local) com mais de 30 dias saem da fila sem envio (como no hub).

**A plataforma ainda não embute a biblioteca** (o integrador faz): no app ela já entra pelo `preparar_www.py`;
no site, servir `sistema/physis-ble.js` e ligar a aba Saúde (`physis-saude.js`) aos botões "Procurar caixinha" /
"Procurar pulseira" com `PhysisBLE.procurar` → `conectar` → `inscrever` (mostrar `ev.texto` numa região `role="status"`).

### O Web Bluetooth já resolve o Android pelo PWA?

**Em boa parte, sim**: no Chrome do Android (6.0+), em HTTPS, o PWA instalado já procura, pareia e recebe da
caixinha com a mesma `physis-ble.js`. **Limites**: só com a tela do app aberta (sem fundo — não serve para
monitorar a pulseira o dia todo), a pessoa escolhe o aparelho a cada sessão (o `getDevices()` para reconectar ainda
está atrás de opção em várias versões), não funciona em rede local sem HTTPS, nem no Firefox, nem em **nenhum
navegador do iPhone** (todos usam o motor do Safari, sem Web Bluetooth). Então: caixinha no Android = PWA já serve;
pulseira contínua e qualquer coisa no iPhone = app nativo.

## 5. Tela de primeiro uso (especificação)

Arquivo `www-extra/primeiro-uso.html`. Um título (`Bem-vindo ao Physis`, serifada, verde #33512F), duas partes:

1. **Endereço do servidor** — campo `type=url` com rótulo, só `https://` (o app não aceita tráfego aberto).
   "Conferir" faz `GET <servidor>/api/instancia` (10 s) e mostra o nome do cliente para a pessoa confirmar.
   Erro em `role=status`, foco volta ao campo.
2. **Consentimento** (aparece depois de conferir) — o que o app faz com os dados, em linguagem simples; link para
   termos/privacidade (`[MARCADOR]` rota no servidor); versão do termo `1` (**provisória, a revisar pelo jurídico**);
   caixa obrigatória "Li e concordo"; caixas **separadas e opcionais** para Bluetooth e avisos (consentimento por
   finalidade). Guardado no celular `{versao, aceito, quando, bluetooth, avisos}` (localStorage + Preferences).
3. **Entrar** — não há tela de login nova: abre a plataforma, que mostra a entrada dela (e o consentimento da conta
   no servidor, `PHYSIS_TERMOS_VERSAO`). O consentimento da **Saúde** continua sendo o do `saude.py` (por pessoa
   acompanhada, com responsável legal para menor).

Mudou a versão do termo → o app volta para esta tela. "Sair e apagar deste celular" (`PhysisNativo.esquecer()`)
apaga servidor, consentimento e a fila BLE. Alvos de 44 px, foco visível, sem rolagem lateral a 320 px.

## 6. Android

Permissões (o `aplicar_plataformas.py` põe no `AndroidManifest.xml`):

| Permissão | Por quê |
|---|---|
| `BLUETOOTH_SCAN` com `usesPermissionFlags="neverForLocation"` | procurar aparelhos (Android 12+) declarando que **não** usa para localização |
| `BLUETOOTH_CONNECT` | conectar e parear (Android 12+) |
| `BLUETOOTH`, `BLUETOOTH_ADMIN`, `ACCESS_COARSE/FINE_LOCATION` com `maxSdkVersion="30"` | só Android 11 ou antes, onde o sistema exige localização para procurar BLE |
| `POST_NOTIFICATIONS` | avisos (Android 13+) |
| `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_CONNECTED_DEVICE` | monitorar a pulseira com a tela apagada; serviço tipo `connectedDevice` (Android 14+) com notificação fixa "Physis: pulseira conectada" |
| `uses-feature bluetooth_le required=false` | o app instala em celular sem BLE |

Também: `allowBackup="false"` (dado de saúde não vai para o backup do Google), `usesCleartextTraffic="false"`,
`minSdkVersion 26` (Android 8.0). O Capacitor 6 já usa `targetSdk 34` (conferir a exigência da Play no ano).

## 7. iPhone

`Info.plist` (o script põe): `NSBluetoothAlwaysUsageDescription` e `NSBluetoothPeripheralUsageDescription` em português,
`UIBackgroundModes = bluetooth-central` (pulseira em segundo plano), `CFBundleDevelopmentRegion pt-BR`,
`ITSAppUsesNonExemptEncryption = false` (só HTTPS e AES-GCM padrão — **confirmar** na exportação).
iOS mínimo **15.0** (Podfile e projeto). `PrivacyInfo.xcprivacy`: sem rastreamento; dados de saúde, local exato e
e-mail "ligados à pessoa, só para o app funcionar"; `UserDefaults` motivo `CA92.1` (plugin Preferences).
**Acrescentar o `PrivacyInfo.xcprivacy` ao alvo App no Xcode** (o script só copia).

## 8. Montar (com Node, Android Studio e Xcode)

```
cd app-nativo
npm install                         # conferir versões; npm view @capacitor/core versions
python scripts/preparar_www.py      # ou --origem ../pacotes/<pacote>.zip  [--hub https://servidor-do-cliente]
npx cap add android                 # uma vez
npx cap add ios                     # uma vez (só no Mac)
python scripts/aplicar_plataformas.py
python scripts/gerar_icones.py --aplicar
npx cap sync
npx cap open android                # Android Studio: Run num celular de verdade (BLE não funciona no emulador)
npx cap open ios                    # Xcode: escolher o Team, Run num iPhone de verdade
```

Depois de mudar a plataforma: `python scripts/preparar_www.py && npx cap sync`.

## 9. Publicar no Android

1. **Chave de assinatura** (uma vez, guardar para sempre — perder a chave = não conseguir atualizar o APK direto):
   ```
   keytool -genkeypair -v -keystore physis-release.jks -alias physis -keyalg RSA -keysize 4096 -validity 10000
   ```
   Guardar o `.jks` e a senha em cofre (duas cópias, fora do Git; `.gitignore` já recusa `*.jks`). Na Play, usar
   **Play App Signing** (a Google guarda a chave do app; a nossa vira a "chave de upload", que dá para trocar).
   O APK direto é assinado com a **nossa** chave: ele e o da Play têm assinaturas diferentes e um não atualiza o outro
   (dizer isso na página de download).
2. `android/app/build.gradle`: `versionCode` (inteiro, sobe 1 a cada envio) e `versionName` ("0.1.0").
   Senhas do `signingConfigs` por variável de ambiente ou `keystore.properties` (fora do Git).
3. Play (AAB): `cd android && ./gradlew bundleRelease` → `app/build/outputs/bundle/release/app-release.aab`.
4. APK direto: `./gradlew assembleRelease` → `app/build/outputs/apk/release/app-release.apk`;
   conferir: `apksigner verify --verbose --print-certs app-release.apk` (anotar o SHA-256 do certificado).
5. Play Console: conta de desenvolvedor (taxa única), app novo, **teste interno** → teste fechado (contas novas
   pessoais exigem teste fechado com testadores antes da produção — conferir a regra vigente) → produção.
6. **Data safety** (Segurança dos dados): coleta "Saúde e condicionamento → informações de saúde", "Local → local
   exato" (pulseira), "Informações pessoais → nome, e-mail" (conta); **não** compartilhado com terceiros;
   criptografado em trânsito; a pessoa pode pedir exclusão; finalidade: funcionalidade do app. Questionário de
   **apps de saúde** (Health apps declaration) e permissões sensíveis: explicar `connectedDevice` com vídeo curto.
   Política de privacidade com endereço público (`[MARCADOR]`). Classificação de conteúdo. País: Brasil.
7. Página de download: `python scripts/publicar_baixar.py --apk … --versao … --url-base https://… --certificado …`.

### Download direto e F-Droid (independência)

- O APK assinado fica no próprio servidor (rota da seção 12) com SHA-256 publicado e o SHA-256 do certificado.
- **F-Droid**: o repositório oficial exige compilação reprodutível só com software livre (o Capacitor e o plugin BLE
  são MIT; serve). Caminho mais simples e independente: um **repositório F-Droid próprio** da Physis
  (`fdroidserver`, `fdroid update` publica um índice assinado numa pasta servida pelo hub); o cliente adiciona o
  endereço no app F-Droid e recebe atualizações sem Google. `[MARCADOR]` decidir se vale na fase 2.

## 10. Publicar no iPhone

1. **Apple Developer Program** (pago, anual), no nome da empresa (exige D-U-N-S).
2. Xcode → Signing & Capabilities: Team, Bundle ID `br.com.physisengineering.app`, "Automatically manage signing"
   (o Xcode cria certificado e perfil de provisionamento); capability **Background Modes → Uses Bluetooth LE accessories**.
3. Versão: `MARKETING_VERSION` (0.1.0) e `CURRENT_PROJECT_VERSION` (sobe a cada envio).
4. Product → **Archive** → Distribute App → App Store Connect → **TestFlight** (beta interno, depois externo, que passa por revisão).
5. App Store Connect: ficha em português, capturas, **rótulos de privacidade** (iguais ao `PrivacyInfo.xcprivacy`:
   Saúde, Local exato, E-mail; ligados à pessoa; sem rastreamento), URL da política de privacidade.
6. **Notas para a revisão**: conta de demonstração num servidor de teste (`[MARCADOR]`), explicar que o Bluetooth é
   para a caixinha/pulseira da própria Physis (enviar vídeo, porque o revisor não tem o aparelho), que o app não faz
   diagnóstico nem é dispositivo médico (`[MARCADOR]` confirmar com o jurídico/ANVISA), e por que usa `bluetooth-central`
   em segundo plano (alerta de crise da pulseira). Diretriz 5.1.1 (dados), 5.1.3 (saúde): dado de saúde não vai para
   publicidade nem para o iCloud.
7. **Sem download direto no iPhone**: o iOS não permite instalar app por arquivo fora da App Store (exceto lojas
   alternativas na União Europeia, que não valem para o Brasil). O caminho gratuito é o **PWA** (Safari → Compartilhar
   → Adicionar à Tela de Início), sem Bluetooth.

## 11. Avisos (notificações) — depois

- **Locais** (`@capacitor/local-notifications`, já na lista): o próprio celular avisa a hora do remédio com os
  horários que vêm do hub. Nada passa por terceiros.
- **Push remoto** é **opcional**: no Android exige FCM (Google) e no iPhone APNs (Apple). Se usado, a mensagem não
  leva dado de saúde (só "há um aviso novo"; o app busca o detalhe no servidor). Alternativa independente no Android:
  UnifiedPush (por exemplo ntfy hospedado pela Physis). Nada disso entra por padrão.

## 12. Rota proposta no hub: `/app/baixar` e `/app/android.apk` (para quem mexe no servidor)

Não mexi no `servidor.py`. Trecho sugerido (junto da rota `/app/`, sem login, pois o celular precisa antes de entrar):

```python
# physis_hub/app_pwa.py (ou servidor.py): download do app nativo. Pasta em PHYSIS_APP_DOWNLOAD
# (padrão: <raiz>/app-download), onde o publicar_baixar.py deixa baixar.html, android.apk e android.apk.sha256.
APK_MIME = "application/vnd.android.package-archive"

def resposta_download(caminho: str, pasta: Path) -> tuple[bytes, dict[str, str]] | None:
    nomes = {"/app/baixar": ("baixar.html", "text/html; charset=utf-8"),
             "/app/android.apk": ("android.apk", APK_MIME),
             "/app/android.apk.sha256": ("android.apk.sha256", "text/plain; charset=utf-8")}
    if caminho not in nomes:
        return None
    nome, tipo = nomes[caminho]
    p = pasta / nome                                 # lista fechada: nada vindo do pedido vira caminho
    if not p.is_file():
        return None
    dados = p.read_bytes()
    cab = {"Content-Type": tipo, "X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"}
    if nome == "android.apk":
        cab["Content-Disposition"] = 'attachment; filename="physis.apk"'
        cab["Digest"] = "sha-256=" + base64.b64encode(hashlib.sha256(dados).digest()).decode()
    return dados, cab

# no do_GET, antes da rota /app/<arquivo>:
#   r = app_pwa.resposta_download(u.path, Path(os.environ.get("PHYSIS_APP_DOWNLOAD") or (WEB.parent / "app-download")))
#   if r: dados, cab = r; self.send_response(200); [self.send_header(k, v) for k, v in cab.items()]; ...
```

APK de dezenas de MB: ler inteiro na memória é aceitável no começo; depois, enviar em blocos. A página usa o mesmo
estilo e a mesma CSP do site (sem nada de fora; os QR são SVG embutidos).

## 13. Testes (`tests/test_app_nativo.py`)

JSON válido do `package.json` (versões fixas, Capacitor 6) e do `capacitor.config.json` (appId, webDir, sem
`server.url`, sem cleartext); permissões Android e textos iOS presentes; nenhum segredo nos arquivos; `physis-ble.js`
sem endereço externo, sem `eval`/`new Function`, com a API inteira; UUIDs do `BLE_PERFIL.md` = constantes do JS;
ações de comando iguais nos dois; `preparar_www.py` monta `www/` sem Gestão e sem `sw.js`, com a CSP e os scripts;
`aplicar_plataformas.py` num manifesto e num Info.plist de exemplo (e não duplica); página de download com um `h1`,
PT/EN, só cores da paleta, sem endereço externo; QR com bits de formato/versão e Reed-Solomon conferidos.

## 14. O que a fase 2 precisa (fora deste repositório)

- **Node.js 18+** (LTS) e npm; **Android Studio** (SDK 34, JDK 17) em qualquer computador; **Mac com Xcode 15+** para o iPhone.
- **Aparelhos**: pelo menos um Android 8–10 (permissão antiga de localização), um Android 12+ e um iPhone com iOS 15+;
  protótipos ESP32 da caixinha e da pulseira com o perfil `firmware/saude/BLE_PERFIL.md` (o firmware ainda não existe).
- **Contas**: Google Play Console (taxa única) e Apple Developer Program (anual), no nome da empresa; D-U-N-S para a Apple.
- **Jurídico**: termo de consentimento (versão 1 é provisória), política de privacidade com endereço público,
  enquadramento ANVISA (o app não diagnostica), textos de Data safety e rótulos de privacidade.
- **Integração**: embutir `physis-ble.js` na aba Saúde; servir `/app/baixar` e `/app/android.apk`; decidir o `appId` final.
- Conferir no primeiro `npm install` as versões fixadas no `package.json`.
