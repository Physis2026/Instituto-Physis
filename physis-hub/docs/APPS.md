# Apps no celular (PWA) — primeira versão

Decisão de 14/11/2026: a plataforma do cliente e a Gestão viram "apps" **instalados pelo navegador**
(PWA). App de loja (Play Store / App Store) só depois, e só para o que precisa de Bluetooth
(sensores ligados direto no celular).

## O que é, em uma frase

O navegador do celular lê um "cartão de identidade" do site (o **manifesto**: nome, ícone, cor) e um
"ajudante" que fica no celular (o **service worker**), que guarda a casca do app para ela abrir mesmo
sem internet. Com os dois, o Chrome/Edge oferecem "Instalar app" e o iPhone oferece
"Adicionar à Tela de Início".

## Arquivos

| Arquivo | Para quê |
|---|---|
| `web/app/manifest-plataforma.webmanifest` | App "Physis" do cliente; abre em `/` |
| `web/app/manifest-gestao.webmanifest` | App da Gestão (equipe); abre em `/gestao/`; `id` diferente, então os dois se instalam lado a lado |
| `web/app/sw.js` | Service worker (cache da casca, regras da API) |
| `web/app/icone-192.png`, `icone-512.png`, `icone-maskable-512.png` | Ícones: árvore do logo, clara sobre o verde #33512F |
| `physis_hub/app_pwa.py` | Lista fechada de `/app/*`, tipos MIME, versão do `sw.js`, gerador dos ícones |
| `tests/test_pwa.py` | Testes (manifestos, ícones, `sw.js`, rota `/app/`) |

Regerar os ícones depois de trocar o logo do painel: `python -m physis_hub.app_pwa`.

## O que fica guardado no celular (e o que não fica)

| Pedido | Estratégia | Guardado? |
|---|---|---|
| `/`, `/painel.html` (e `/demo`, `/loja`, que são o mesmo arquivo) | cache primeiro, atualiza por trás | sim |
| `/planejador/` | cache primeiro, atualiza por trás | sim, se a instalação tem o Planejador |
| `/gestao/` | rede primeiro; cache só sem rede | sim, só a tela (nunca a página de entrar, que vem com `no-store`) |
| `/vendor/*` (mapa; BIM na primeira vez que for usado) | cache primeiro | sim |
| `/app/*` (manifestos, ícones) | cache primeiro | sim (`sw.js` nunca) |
| `GET /api/clima`, `GET /api/gis/*` | rede primeiro; sem rede, a última resposta | sim (até 80 respostas) |
| qualquer outra `/api/*` (dados pessoais, sessão, gestão, loja…) | direto para a rede | **nunca** |
| POST, PUT, DELETE | direto | **nunca** |
| `/mapas/*` (PMTiles, pedidos com Range) e outras origens | direto | nunca |

Os caches se chamam `physis-casca-<versão>` e `physis-dados-<versão>`. A versão é a impressão digital
das telas e bibliotecas (`app_pwa.versao`), posta no `sw.js` pelo servidor. Mudou uma tela →
muda o `sw.js` → o celular instala o novo e apaga os caches antigos.

Ao **sair da conta**, a tela deve avisar o service worker para apagar o que é da sessão (a cópia da
Gestão e os dados de clima/GIS):

```js
if (navigator.serviceWorker && navigator.serviceWorker.controller) navigator.serviceWorker.controller.postMessage({ tipo: "sair" });
```

## Segurança

- Nada de fora do servidor: o `sw.js` não tem endereço externo (teste garante) e funciona com a
  política atual (`worker-src 'self'`; o manifesto cai em `default-src 'self'`).
- `/app/` entrega só os 6 arquivos da lista (`app_pwa.ARQUIVOS`), sem login (o celular precisa deles
  antes de entrar). Nenhum deles tem dado de cliente.
- Service worker só funciona em **HTTPS** (ou `localhost`). Em rede local sem HTTPS o site abre
  normalmente, só não vira app instalável.

## Como instalar

- **Android (Chrome/Edge)**: abrir o endereço da plataforma → menu ⋮ → "Instalar app".
- **iPhone (Safari)**: Compartilhar → "Adicionar à Tela de Início".
- **Gestão**: abrir `/gestao/` e instalar do mesmo jeito (fica como um segundo app).

## Limites desta versão

- Sem notificações push e sem Bluetooth (fica para o app de loja).
- Sem rede, a casca abre, mas telas que dependem de `/api/*` (exceto clima e GIS) mostram o que a
  própria tela faz quando o servidor não responde.
