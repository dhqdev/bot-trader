# Bot Trader

Sistema pessoal de trading automatizado na **OKX** (Spot), com painel web: login com verificação em duas etapas, chaves de API criptografadas, bots que você liga e desliga, gráficos de resultado, laboratório de backtest, leitura de notícias e do sentimento do mercado, análise com IA (**Claude ou GPT**, você escolhe) e um **piloto automático** que testa e aplica melhorias nas estratégias sozinho.

> Uso por sua conta e risco. Nenhuma estratégia garante lucro. Comece sempre em modo **simulado**.

## Rodar localmente (Windows)

Pré-requisitos: Python 3.12 e Node.js 22 ou mais novo.

```powershell
.\start.ps1
```

Na primeira vez, o script cria o ambiente Python, instala tudo, compila o frontend e abre http://localhost:8000.
Se o PowerShell bloquear: `powershell -ExecutionPolicy Bypass -File .\start.ps1`.

| Comando | O que faz |
|---|---|
| `.\start.ps1` | Sistema completo em http://localhost:8000 |
| `.\start.ps1 -Dev` | Desenvolvimento: API com auto-reload + frontend com hot reload em http://localhost:5173 |
| `.\start.ps1 -Test` | Roda os testes do backend |

### Primeiro uso

1. **Crie sua conta.** O primeiro cadastro vira o dono do sistema; depois disso o cadastro fecha.
2. **Configurações:** ative a **verificação em duas etapas** e cadastre a chave de API da **OKX** (veja "Chave da OKX" abaixo) e, se quiser a IA, a chave do Claude/Anthropic ou do GPT/OpenAI. Tudo fica criptografado no banco e nunca volta para a tela; chaves da OKX com permissão de saque são recusadas.
3. **Laboratório:** teste estratégias no par que você quer operar, em candles de 4 horas. Use "Comparar todas as estratégias" e leia a análise automática do resultado.
4. **Bots → Novo bot**, em modo **Simulado**. Ele usa preços reais, com taxa e slippage, sem gastar dinheiro.
5. Acompanhe pelo **Painel**. Quando estiver confiante, edite o bot e troque para **Real**.

O botão **Sistema ligado/desligado**, no topo, para ou retoma todos os bots de uma vez. Desligar não vende as posições.

## O que tem em cada tela

- **Painel:** resultado total (realizado + em aberto), hoje, taxa de acerto, curva de resultado acumulado, resultado por dia, bots, resultado por estratégia, últimas operações e atividade. Separa **Real** de **Simulado**.
- **Bots:** status, tempo de operação e resultado de cada bot.
- **Detalhe do bot:** gráfico de candles com indicadores, compras e vendas, linhas de entrada/stop/alvo, a lista de **condições da estratégia** (o que falta para comprar ou vender), posição aberta, operações, ordens e log de eventos. Tem os botões para ligar/parar, encerrar a posição e analisar com IA.
- **Laboratório:** guia de uso, explicação de cada campo, backtest com taxa, slippage, stop e alvos, comparação contra o buy & hold e entre estratégias, leitura automática do resultado e "Criar bot com esta configuração".
- **Análise IA**, em três abas:
  - **Conversa:** chat com a IA escolhida (Claude ou GPT). Ela consulta seus bots, o mercado, as notícias, o diagnóstico do piloto e **roda backtests** para embasar as respostas. Só lê dados: não envia ordens nem altera bots. Os relatórios ficam salvos.
  - **Piloto automático:** o que foi diagnosticado, testado e mudado em cada bot, com os botões para aplicar, recusar ou desfazer, e as lições que a IA acumulou.
  - **Notícias e sentimento:** notícias classificadas (moedas afetadas, sentimento, impacto), o Índice de Medo e Ganância e quais bots estão com compras travadas agora.
- **Configurações:** chave da OKX (com conferência das permissões na própria OKX e o IP do servidor para vincular), qual IA usar (Claude ou GPT, e o modelo do GPT), verificação em duas etapas, sessões abertas e atividade recente da conta.

## IA: Claude ou GPT

Cadastre a chave de um dos dois (ou dos dois) em **Configurações**. A chave cadastrada por último passa a ser a usada, e dá para alternar a qualquer momento. Tudo que usa IA funciona com os dois: a conversa (com as mesmas ferramentas: portfólio, backtests, notícias, diagnóstico do piloto), a classificação das notícias e a análise do piloto automático.

| | Claude (Anthropic) | GPT (OpenAI) |
|---|---|---|
| Conversa e piloto automático | `claude-opus-5` | `gpt-6-sol` (padrão; dá para escolher `gpt-6-astra`, mais capaz e ~5× mais caro, ou `gpt-6-luna`) |
| Classificação das notícias | `claude-haiku-4-5` | `gpt-6-luna` |
| Onde criar a chave | console.anthropic.com | platform.openai.com → API keys |

Ao salvar a chave da OpenAI, o sistema confere a chave e o modelo na própria OpenAI (a consulta não gasta créditos). Os modelos também podem ser trocados pelas variáveis `BT_AI_MODEL`, `BT_AI_FAST_MODEL`, `BT_OPENAI_MODEL` e `BT_OPENAI_FAST_MODEL`.

## Estratégias

Todas são long-only (só compram) e avaliadas **apenas em candles fechados**. O sinal do backtest é exatamente o mesmo da operação real, e isso é testado. **Use candles de 4 horas**: nos testes, 1 hora ou menos perdeu em quase todas as estratégias por causa do ruído e das taxas.

| Estratégia | Estilo | Como funciona |
|---|---|---|
| **Squeeze: compressão e rompimento** (nova, recomendada) | rompimento | Espera o preço ficar comprimido (Bollinger dentro do Keltner) por 8+ candles e compra quando a compressão se desfaz com momentum para cima. Sai quando o preço perde a média do canal. |
| **Candle de ignição** (nova) | momentum | Compra o candle que "acende" o movimento: alta de 1,5× o ATR, volume 1,5× a média e fechamento perto da máxima. Sai ao perder a EMA 20. |
| **Momentum ajustado à volatilidade** (nova) | momentum | Compra quando o retorno dos últimos 30 candles, dividido pela volatilidade esperada, passa de 1 desvio (z-score). Sai quando a força some. |
| Confluência de tendência | tendência | EMA 9 cruzando a 21 há até 10 candles, acima da EMA 200, com 4 de 5 confirmações (Supertrend, MACD, RSI, ADX, volume). |
| Rompimento Donchian (Tartarugas) | rompimento | Compra na máxima de 20 candles com volume e ADX; vende na mínima de 10. |
| HiLo + RSI (ChiloRSI v2) | tendência | Evolução da estratégia que o bot antigo usava: entra logo após o HiLo (55) virar, com filtros de RSI, tendência e ATR%. |

Cada parâmetro tem, na tela, a explicação do que faz e a faixa aceita. O Laboratório tem um guia de uso e uma leitura automática do resultado.

### Níveis: Rápido, Médio e Lento

Ao criar um bot (ou no Laboratório), escolha um **perfil pronto**. Ele preenche o tempo do candle, a estratégia e o stop; o tamanho das compras continua o seu. Números medidos com o código de produção, dados reais de 14 pares, taxa de 0,1% e slippage:

| Nível | Perfil | Candle | Cada operação dura | Resultado típico | Casos com lucro |
|---|---|---|---|---|---|
| **Rápido** (risco alto, experimental) | Repique rápido | 5 min | ~46 min | −2,6% em 45 dias | 7% |
| | Ignição rápida | 15 min | ~1,5 h | −8,4% em 4 meses | 4% |
| **Médio** (risco médio) | Ignição 1h | 1 h | ~17 h | +8,3% em 6 meses | 62% |
| | HiLo 2h com trailing | 2 h | ~21 h | +4,3% em 8 meses | 64% |
| **Lento** (risco baixo) | **Squeeze 4h** (recomendado) | 4 h | ~3 dias | +23,3% em 1 ano | 73% |
| | Confluência diária | 1 dia | ~3 semanas | +23,1% em 18 meses | 77% |

Os números já incluem o **filtro de sentimento** de cada perfil (ver abaixo), medido com o Índice de Medo e Ganância real de cada dia.

**Sobre o nível Rápido:** nos testes, **nenhuma** estratégia de minutos lucrou depois dos custos. Foram 9 estratégias, 3 regras de risco, candles de 5 e 15 minutos e 14 pares. Cada operação paga cerca de 0,3% entre taxa e slippage, e os movimentos de poucos minutos costumam ser menores que isso. Mesmo com taxa reduzida (0,075%, como nos níveis VIP), a melhor ficou em −1,2%. O nível existe porque você pode querer testá-lo, mas começa no modo simulado, e usá-lo com dinheiro real exige uma confirmação explícita.

### Como foram escolhidas (e o que esperar)

Backtests com histórico real de 14 pares (pesquisa feita em set/2026 com o histórico da Binance; os preços na OKX são praticamente iguais: o Squeeze em SOL 4h deu +43,6%/+16,8% num e +44,3%/+16,7% no outro), em candles de 1h (180 dias) e 4h (365 dias), com 3 períodos seguidos (83 casos). Taxa de 0,1%, slippage de 0,05% e o risco padrão.

- **Design:** 7 pares (BTC, ETH, SOL, BNB, XRP, LINK, ADA) nos 2 períodos mais recentes. Foram testadas 14 ideias novas (KAMA, Squeeze, RSI(2), regressão linear, Ichimoku, Heikin-Ashi, momentum/volatilidade, OBV, pullback na tendência, candle de ignição, canal ATR, impulso de Elder, Aroon e StochRSI). Ficaram as 3 melhores.
- **Validação:** 7 pares que não participaram da escolha (DOGE, AVAX, DOT, LTC, TRX, NEAR, JUP), mais o período mais antigo dos 7 primeiros.

Resultado com todas as estratégias na mesma janela de teste:

| Estratégia | Mediana no 4h | Com lucro no 4h | Mediana (todos os casos) | Fora da amostra (mediana) | Pior caso |
|---|---|---|---|---|---|
| **Squeeze** | +20,9% | 71% | +8,9% | +4,0% | **−36,7%** |
| **Candle de ignição** | +20,5% | 71% | +8,4% | +4,5% | −40,5% |
| **Momentum/volatilidade** | +21,3% | 71% | +4,7% | +2,3% | −58,1% |
| Confluência | +17,7% | 73% | +8,3% | +2,8% | −45,1% |
| Donchian | +13,4% | 68% | +3,4% | **+7,6%** | −48,9% |
| HiLo + RSI | +12,0% | 61% | +0,5% | +1,0% | −39,7% |
| Buy & hold | +12,5% | | +10,7% | +19,4% | |

**Removidas por desempenho fraco:** Supertrend (−3,5% fora da amostra), Cruzamento de EMAs (−4,0%), Momentum MACD (−4,2%) e Reversão Bollinger (quase não operava: ~2 operações por período). Bots que usavam alguma delas são migrados automaticamente para a substituta, com um aviso no log.

O que isso significa:

- **Em 4h, as 3 novas lideram**, e a Squeeze tem o menor drawdown e o melhor pior caso.
- **Em alta forte, segurar a moeda ganha.** No período mais antigo (alta forte), o buy & hold superou todas. As estratégias ganham principalmente **protegendo nas quedas**, porque ficam em USDT boa parte do tempo.
- **O Momentum/volatilidade tem o maior drawdown.** Se usar, prefira posições menores.
- A configuração antiga do bot (ChiloRSI + stop 5%, trailing 3%, alvos 5/10/20%) teve mediana entre −14% e −19% nos mesmos tipos de teste.
- **Nada disso é garantia.** Teste o par no Laboratório em mais de um período e rode em modo simulado antes do real.

### Gerenciamento de risco (por bot)

- **Tamanho:** valor fixo por compra, % do saldo, ou % de risco até o stop.
- **Stop:** por volatilidade (padrão: 3× ATR, no mínimo 0,5%) ou percentual.
- **Opcionais:** break-even, trailing stop (ATR ou %), até 5 alvos parciais.
- **Disciplina:** pausa após saída e perda diária máxima (bloqueia novas compras no dia).
- **Sentimento do mercado:** filtro de compras pelo Índice de Medo e Ganância (ver abaixo).
- **Notícias:** trava de compras (e, se quiser, venda da posição) com notícia grave sobre a moeda.
- Stops e alvos são conferidos a cada ~15 s com o preço atual, não só no fechamento do candle.
- Cada bot só vende o que ele mesmo comprou; ativos que já estão na sua carteira não são tocados.

## Chave da OKX

1. Na OKX (Perfil → **API** → Criar chave de API V5), dê um nome, crie uma **passphrase** (guarde: a OKX pede junto com a chave) e marque só **Leitura** e **Negociação**. **Nunca** marque Saque.
2. Em "Endereço IP", vincule o IP do servidor, que aparece no cartão da OKX em Configurações. Sem IP vinculado a chave funciona, mas a OKX pode apagar chaves de negociação que ficam muitos dias sem uso.
3. Deixe a conta no modo **Spot** (a OKX chama de modo de conta "Spot"): o sistema opera sem margem.
4. No Bot Trader, em Configurações → **OKX**, cole a API key, a Secret key e a passphrase, escolha a região (Brasil = Global) e confirme com sua senha. O sistema confere tudo na OKX antes de salvar.
5. Para testar sem dinheiro, crie chaves no **Demo Trading** da OKX e marque "Chaves do Demo Trading".

Tudo usa a OKX: preços ao vivo, ordens, saldo, a lista de pares e o histórico dos backtests e do piloto automático. O histórico baixado fica guardado no banco, então só a primeira consulta de cada par demora alguns segundos. Os bots criados antes da mudança (quando o sistema usava a Binance) foram migrados sozinhos: os simulados seguem rodando com preços da OKX; os reais foram desligados para você conferir as chaves e religar.

## Sentimento do mercado e notícias

**Índice de Medo e Ganância** (alternative.me, diário, de 0 a 100). Testado como filtro de compras em 14 pares, com o valor real de cada dia e sem olhar o futuro:

| Filtro | O que faz | Nos testes |
|---|---|---|
| **Evitar medo extremo** (padrão) | Não compra com o índice ≤ 20 | Manteve ou melhorou todas as estratégias de 4 h, com quedas menores (Squeeze 4h: +20,9% → +23,3%; HiLo 2h: +0,7% → +4,3%) |
| **Sentimento subindo** | Só compra com o índice acima do de 7 dias antes | Ótimo em 1-2 h (Ignição 1h: +2,7% → +8,3%, queda média −19,8% → −15,9%), ruim em 4 h |
| Os dois | Junta as duas regras | Menos operações e quedas menores |

Evitar ganância alta e "só entre 25 e 75" foram testados e **descartados** (resultados inconsistentes entre os grupos de pares).

**Notícias:** a cada 15 minutos o sistema lê CoinDesk, Cointelegraph, Decrypt, The Block, CryptoSlate, Livecoins e Portal do Bitcoin, identifica as moedas citadas e classifica sentimento e impacto (por palavras-chave na hora e, com uma chave de IA, pelo Claude ou GPT a cada 30 minutos; notícia que parece grave é revisada pela IA na hora).

- **Trava de compras (padrão):** notícia grave e bem negativa sobre a moeda do bot, ou sobre o mercado todo (ex.: problema na OKX), impede compras por 12 horas. Vale a classificação da IA ou a mesma notícia grave em duas fontes, para evitar alarme falso.
- **Trava + venda (opcional):** também vende a posição se a notícia sair depois da compra e for confirmada pela IA.
- Notícias boas **não** disparam compras: comprar na euforia da manchete costuma ser comprar no topo. Elas entram na análise da IA.
- Não existe histórico de manchetes para backtest, então a trava de notícias não aparece nos resultados do Laboratório. O filtro de sentimento aparece.

## Piloto automático (o sistema que se aperfeiçoa sozinho)

A cada ciclo (por padrão: todo dia no nível Rápido, a cada 3 dias no Médio e toda semana no Lento, ou pelo botão **Otimizar agora**), para cada bot ligado:

1. **Diagnóstico ("backlog"):** lê as operações, stops, sinais ignorados e erros do bot e aponta os problemas (ex.: muitos stops logo após a compra, resultado real abaixo do backtest, ordens abaixo do mínimo).
2. **Candidatas:** variações de **uma coisa por vez**: cada parâmetro da estratégia um pouco para cima e para baixo, stop, trailing, alvo, break-even, pausa, filtro de sentimento, outras estratégias, a configuração anterior e as ideias da IA.
3. **Validação honesta:** o histórico (2 anos) é dividido em duas partes. A escolha usa só os 2/3 mais antigos; o 1/3 mais recente, que a escolha não viu, serve de confirmação. A candidata também não pode piorar em BTC e ETH.
4. **Decisão:** só muda se melhorar nas duas partes, sem aumentar a queda máxima, com operações suficientes. No máximo uma mudança a cada 5 dias por bot. Nunca mexe no par, no tempo de candle, no modo (simulado/real) nem no valor das ordens, e nunca tira o stop.
5. **Aprendizado:** cada ciclo fica registrado, junto com o resultado real depois da mudança. Com uma chave de IA (Claude ou GPT), a IA escreve a análise, guarda lições ("o que a IA aprendeu") e propõe ideias novas, que passam pelas mesmas regras. No ciclo seguinte ela recebe esse histórico.

Modos: **aplica sozinho nos simulados** (padrão), **só sugere**, **aplica sozinho também nos reais** (exige confirmar senha e 2FA; troca de estratégia em bot real sempre espera sua aprovação) ou desligado. Qualquer mudança pode ser desfeita com um clique.

## App no celular (PWA)

O Bot Trader pode ser instalado como app, com ícone na tela inicial e abrindo em tela cheia:

- **Android / Chrome / Edge:** botão **Instalar app** no topo (ou em Configurações → App no celular).
- **iPhone:** no Safari, **Compartilhar → Adicionar à Tela de Início**.

No celular, a navegação fica numa barra inferior, as tabelas viram listas e os campos não dão zoom ao tocar. A interface fica em cache e abre mesmo sem internet. Os **dados** (saldo, posições, ordens) nunca ficam em cache: vêm sempre ao vivo do servidor. Quando uma versão nova é publicada, aparece o aviso "Nova versão disponível".

## Produção

### Imagem Docker automática (GitHub Actions)

A cada push na `main`, o workflow [`.github/workflows/ci.yml`](.github/workflows/ci.yml) roda os testes (backend e frontend) e publica a imagem para amd64 e arm64 em:

```
ghcr.io/dhqdev/bot-trader:latest      # última versão da main
ghcr.io/dhqdev/bot-trader:sha-abc1234 # versão exata de um commit (para voltar atrás)
```

Uma tag `v1.2.3` publica também `:1.2.3` e `:1.2`.

### Portainer com Swarm + Traefik (trade.tekvosoft.com)

Use [`deploy/portainer-swarm-traefik.yml`](deploy/portainer-swarm-traefik.yml). Ele segue o mesmo padrão das outras stacks do servidor (`network_public`, `websecure`, `letsencryptresolver`) e não publica porta: o Traefik faz o HTTPS. Troque o `BT_SECRET_KEY` antes do deploy. Os passos de registro no GHCR são os mesmos do item 1 abaixo.

### Portainer (sem Traefik)

1. **Registries → Add registry → Custom registry.** URL `ghcr.io`, com o seu usuário do GitHub e um token (classic) com escopo `read:packages`. A imagem é privada porque o repositório é privado.
2. **Stacks → Add stack → Web editor.** Cole o conteúdo de [`deploy/portainer-stack.yml`](deploy/portainer-stack.yml).
3. Em **Environment variables**, defina:
   - `BT_SECRET_KEY`: obrigatória, com 32+ caracteres. Gere com `python -c "import secrets; print(secrets.token_urlsafe(48))"` e **guarde o valor**.
   - `APP_PORT` (padrão `8000`), `BT_COOKIE_SECURE` (`true` só se houver HTTPS na frente) e, se quiser, `BT_ANTHROPIC_API_KEY`.
4. **Deploy the stack** e acesse `http://IP-do-servidor:8000`.

Para atualizar depois de um push: abra a stack e use **Pull and redeploy**, marcando a opção de puxar a imagem. Para automatizar, crie um webhook no Portainer e cadastre a URL como secret `PORTAINER_WEBHOOK_URL` no repositório (Settings → Secrets and variables → Actions). O workflow chama esse webhook ao fim de cada build.

### Docker Compose (sem Portainer)

```bash
cp .env.production.example .env.production   # preencha BT_SECRET_KEY (e DOMAIN para HTTPS)
docker compose --profile https up -d --build  # HTTPS automático via Caddy (aponte o DNS antes)
# ou, sem domínio:  docker compose up -d --build   -> http://IP:8000
```

- Os dados (banco SQLite e segredo) ficam no volume `bot-data`. Faça backup dele.
- **Guarde o `BT_SECRET_KEY`.** Se ele mudar, as chaves salvas precisam ser cadastradas de novo.
- Rode **um único processo** (já configurado). O motor dos bots roda dentro da API, e mais workers duplicariam as ordens.
- Com HTTPS, mantenha `BT_COOKIE_SECURE=true`. Sem HTTPS (só para teste), use `false`.
- Para atualizar: `git pull && docker compose --profile https up -d --build`. Os bots que estavam ligados voltam sozinhos (vale também para o Portainer).

## Segurança

- **Chave da OKX:** só **Leitura e Negociação**, **nunca Saque**, com o **IP do servidor vinculado**. Ao salvar, o sistema confere as permissões na própria OKX e **recusa chaves com saque**; avisa se faltar o IP vinculado ou se a conta não estiver no modo Spot.
- **Criptografia:** as chaves ficam criptografadas (Fernet) com uma chave derivada de `BT_SECRET_KEY`; a interface só mostra as pontas (`ABCD••••WXYZ`). A IA nunca recebe chaves.
- **Verificação em duas etapas (TOTP):** com qualquer app autenticador, com QR code, 10 códigos de recuperação de uso único e proteção contra reuso do mesmo código.
- **Confirmação de ações sensíveis:** trocar as chaves, desligar o 2FA, gerar códigos de recuperação e liberar o piloto automático em bots reais pedem a senha (e o código de 2 etapas). Quem pegar uma sessão aberta não consegue fazer isso.
- **Sessões:** cookie httpOnly, `SameSite=Strict` e `Secure` em HTTPS. "Sair dos outros aparelhos" e a troca de senha derrubam as outras sessões na hora.
- **Tentativas de login:** limite por IP e por conta; e-mail inexistente responde igual a senha errada, no mesmo tempo.
- **Proteção do site:** CSP restrita (só scripts do próprio site), HSTS, `X-Frame-Options: DENY`, `Permissions-Policy`, COOP/CORP, bloqueio de requisições que mudam dados vindas de outros sites (inclusive subdomínios), limite de tamanho das requisições e `Cache-Control: no-store` na API.
- **Registro de atividade:** logins, falhas, trocas de senha e de chaves, 2FA e autorizações ficam registrados com IP e aparelho (Configurações → Atividade recente).
- **Notícias** vêm de sites externos: o XML é lido com proteção contra ataques (defusedxml) e o texto é tratado como dado, nunca como instrução para a IA. As ideias da IA passam pelos limites dos parâmetros e pelos mesmos testes de qualquer mudança.
- O arquivo `.env` antigo na raiz ainda tem suas chaves em texto puro. Depois de cadastrá-las pela interface, **apague esse arquivo**. A Binance não é mais usada: apague também as chaves de API antigas no site da Binance.

## Estrutura

```
backend/
  app/
    core/            indicadores, estratégias, risco, backtest, exchange, motor, sentimento, trava de notícias
    api/             rotas REST (auth, segurança, bots, painel, mercado, backtest, IA, piloto, notícias)
    services/        estatísticas, backtests, agente de IA, notícias, piloto automático, agendador
    models.py        tabelas (SQLAlchemy): usuários, chaves, bots, posições, ordens, eventos, relatórios,
                     2FA/sessões, atividade, notícias, medo e ganância, ciclos do piloto, lições da IA
  tests/             106 testes: indicadores, ausência de look-ahead, risco, backtest, motor, API, IA,
                     segurança (CSRF, 2FA, sessões), notícias, sentimento e piloto automático
frontend/            React + Vite + TypeScript + Tailwind (lightweight-charts e Recharts)
legacy/              código antigo, preservado para consulta (pode apagar)
deploy/portainer-swarm-traefik.yml   stack Swarm + Traefik (trade.tekvosoft.com)
deploy/portainer-stack.yml   stack para o Portainer sem Traefik (usa a imagem do GHCR)
.github/workflows/ci.yml    testes + build e publicação da imagem
Dockerfile, docker-compose.yml, Caddyfile, start.ps1
```

API interativa (em desenvolvimento): http://localhost:8000/api/docs

## Licença

AGPL-3.0 (herdada do projeto original; ver `LICENSE`). Se oferecer o sistema como serviço a terceiros, a AGPL exige disponibilizar o código-fonte a eles.
