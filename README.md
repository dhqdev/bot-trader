# Bot Trader

Sistema pessoal de trading automatizado na Binance Spot, com painel web: login, chaves de API criptografadas, bots que você liga e desliga, gráficos de resultado, laboratório de backtest e análise com IA (Claude).

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
2. **Configurações:** cole as chaves da Binance (e, se quiser a IA, a chave da Anthropic). Elas são criptografadas no banco e nunca voltam para a tela.
3. **Laboratório:** teste estratégias no par que você quer operar, em candles de 4 horas. Use "Comparar todas as estratégias" e leia a análise automática do resultado.
4. **Bots → Novo bot**, em modo **Simulado**. Ele usa preços reais, com taxa e slippage, sem gastar dinheiro.
5. Acompanhe pelo **Painel**. Quando estiver confiante, edite o bot e troque para **Real**.

O botão **Sistema ligado/desligado**, no topo, para ou retoma todos os bots de uma vez. Desligar não vende as posições.

## O que tem em cada tela

- **Painel:** resultado total (realizado + em aberto), hoje, taxa de acerto, curva de resultado acumulado, resultado por dia, bots, resultado por estratégia, últimas operações e atividade. Separa **Real** de **Simulado**.
- **Bots:** status, tempo de operação e resultado de cada bot.
- **Detalhe do bot:** gráfico de candles com indicadores, compras e vendas, linhas de entrada/stop/alvo, a lista de **condições da estratégia** (o que falta para comprar ou vender), posição aberta, operações, ordens e log de eventos. Tem os botões para ligar/parar, encerrar a posição e analisar com IA.
- **Laboratório:** guia de uso, explicação de cada campo, backtest com taxa, slippage, stop e alvos, comparação contra o buy & hold e entre estratégias, leitura automática do resultado e "Criar bot com esta configuração".
- **Análise IA:** chat com o Claude. Ele consulta seus bots, o mercado e **roda backtests** para embasar as respostas. Só lê dados: não envia ordens nem altera bots. Os relatórios ficam salvos.

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

### Como foram escolhidas (e o que esperar)

Backtests com dados reais da Binance em 14 pares, em candles de 1h (180 dias) e 4h (365 dias), com 3 períodos seguidos (83 casos). Taxa de 0,1%, slippage de 0,05% e o risco padrão.

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
- Stops e alvos são conferidos a cada ~15 s com o preço atual, não só no fechamento do candle.
- Cada bot só vende o que ele mesmo comprou; ativos que já estão na sua carteira não são tocados.

## Produção

### Imagem Docker automática (GitHub Actions)

A cada push na `main`, o workflow [`.github/workflows/ci.yml`](.github/workflows/ci.yml) roda os testes (backend e frontend) e publica a imagem para amd64 e arm64 em:

```
ghcr.io/dhqdev/bot-trader:latest      # última versão da main
ghcr.io/dhqdev/bot-trader:sha-abc1234 # versão exata de um commit (para voltar atrás)
```

Uma tag `v1.2.3` publica também `:1.2.3` e `:1.2`.

### Portainer

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

- Na Binance, crie a chave de API **sem permissão de saque**, com **Spot Trading** habilitado e **restrita ao IP do servidor**.
- As chaves são criptografadas (Fernet) com uma chave derivada de `BT_SECRET_KEY`; a interface só mostra as pontas (`ABCD••••WXYZ`).
- A sessão fica num cookie httpOnly (SameSite=Lax); o login tem limite de tentativas.
- A IA só tem ferramentas de leitura e backtest.
- O arquivo `.env` antigo na raiz ainda tem suas chaves em texto puro. Depois de cadastrá-las pela interface, **apague esse arquivo** (ou gere chaves novas na Binance).

## Estrutura

```
backend/
  app/
    core/            indicadores, estratégias, risco, backtest, exchange (Binance/simulado), motor
    api/             rotas REST (auth, bots, painel, mercado, backtest, IA, configurações)
    services/        estatísticas, backtests, análise de mercado, agente de IA
    models.py        tabelas (SQLAlchemy): usuários, chaves, bots, posições, ordens, eventos, relatórios
  tests/             66 testes: indicadores, ausência de look-ahead, risco, backtest, motor, API, IA
frontend/            React + Vite + TypeScript + Tailwind (lightweight-charts e Recharts)
legacy/              código antigo, preservado para consulta (pode apagar)
deploy/portainer-stack.yml   stack para o Portainer (usa a imagem do GHCR)
.github/workflows/ci.yml    testes + build e publicação da imagem
Dockerfile, docker-compose.yml, Caddyfile, start.ps1
```

API interativa (em desenvolvimento): http://localhost:8000/api/docs

## Licença

AGPL-3.0 (herdada do projeto original; ver `LICENSE`). Se oferecer o sistema como serviço a terceiros, a AGPL exige disponibilizar o código-fonte a eles.
