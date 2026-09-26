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
3. **Laboratório:** teste estratégias no par que você quer operar. Use "Comparar todas as estratégias".
4. **Bots → Novo bot**, em modo **Simulado**. Ele usa preços reais, com taxa e slippage, sem gastar dinheiro.
5. Acompanhe pelo **Painel**. Quando estiver confiante, edite o bot e troque para **Real**.

O botão **Sistema ligado/desligado**, no topo, para ou retoma todos os bots de uma vez. Desligar não vende as posições.

## O que tem em cada tela

- **Painel:** resultado total (realizado + em aberto), hoje, taxa de acerto, curva de resultado acumulado, resultado por dia, bots, resultado por estratégia, últimas operações e atividade. Separa **Real** de **Simulado**.
- **Bots:** status, tempo de operação e resultado de cada bot.
- **Detalhe do bot:** gráfico de candles com indicadores, compras e vendas, linhas de entrada/stop/alvo, a lista de **condições da estratégia** (o que falta para comprar ou vender), posição aberta, operações, ordens e log de eventos. Tem os botões para ligar/parar, encerrar a posição e analisar com IA.
- **Laboratório:** backtest com taxa, slippage, stop e alvos; comparação contra o buy & hold; comparação entre estratégias; "Criar bot com esta configuração".
- **Análise IA:** chat com o Claude. Ele consulta seus bots, o mercado e **roda backtests** para embasar as respostas. Só lê dados: não envia ordens nem altera bots. Os relatórios ficam salvos.

## Estratégias

Todas são long-only (só compram), avaliadas **apenas em candles fechados**. O sinal do backtest é exatamente o mesmo da operação real, e isso é testado.

| Estratégia | Estilo | Resumo |
|---|---|---|
| **Confluência de tendência** (padrão) | tendência | Preço acima da EMA 200, EMA 9 cruzando a 21 há até 10 candles e 4 de 5 confirmações (Supertrend, MACD, RSI, ADX, volume). Sai quando a EMA 9 perde a 21 ou o Supertrend vira. |
| HiLo + RSI (ChiloRSI v2) | tendência | Evolução da estratégia que o bot antigo usava: entra logo após o HiLo (55) virar, com filtros de RSI, tendência e ATR%. |
| Supertrend + EMA | tendência | Evolução do UT Bot Alerts. |
| Cruzamento de EMAs + ADX | tendência | Evolução das médias móveis: só cruzamentos recentes, com ADX e volume. |
| Rompimento Donchian | rompimento | Sistema das Tartarugas (máxima de 20 / mínima de 10). |
| Momentum MACD | momentum | Cruzamento do MACD abaixo de zero com tendência. |
| Reversão Bollinger + RSI | reversão | Compra quedas exageradas em tendência de alta. Opera pouco e tem drawdown baixo. |

### Como os padrões foram escolhidos (e o que esperar)

Os padrões vieram de backtests com dados reais da Binance em 14 pares (BTC, ETH, SOL, BNB, XRP, LINK, ADA, DOGE, AVAX, DOT, LTC, TRX, NEAR, JUP), em candles de 1h (180 dias) e 4h (365 dias), com dois períodos seguidos. São 56 casos, com taxa de 0,1% e slippage de 0,05%:

| | Mediana (recente / anterior) | Casos com lucro | Bate o buy & hold | Pior caso |
|---|---|---|---|---|
| Configuração antiga (ChiloRSI + stop 5%, trailing 3%, alvos 5/10/20%) | −14,2% / −19,4% | 9 de 56 | 20 de 56 | −67,8% |
| **Confluência de tendência** | **+0,2% / +10,4%** | **29 de 56** | **37 de 56** | −43,0% |
| Buy & hold | −3,2% / −39,5% | | | |

O que isso significa:

- **A melhora sobre o bot antigo é grande e consistente**, e a maior parte do ganho vem da proteção em quedas.
- **Não é lucro garantido.** Nos pares que não foram usados para escolher os parâmetros (DOGE, AVAX, DOT, LTC, TRX, NEAR, JUP), a Confluência ficou em −17,9% / +2,6%, contra −1,1% / −50,8% do buy & hold.
- **O que mais pesou foi entrar cedo** (só logo após o gatilho) e **sair só na reversão**. Break-even cedo, trailing apertado e alvos curtos cortavam as tendências vencedoras, por isso vêm desligados. Continuam disponíveis no formulário de risco.
- **Teste cada par no Laboratório, em mais de um período, e rode em simulado antes do real.**

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
  tests/             68 testes: indicadores, ausência de look-ahead, risco, backtest, motor, API, IA
frontend/            React + Vite + TypeScript + Tailwind (lightweight-charts e Recharts)
legacy/              código antigo, preservado para consulta (pode apagar)
deploy/portainer-stack.yml   stack para o Portainer (usa a imagem do GHCR)
.github/workflows/ci.yml    testes + build e publicação da imagem
Dockerfile, docker-compose.yml, Caddyfile, start.ps1
```

API interativa (em desenvolvimento): http://localhost:8000/api/docs

## Licença

AGPL-3.0 (herdada do projeto original; ver `LICENSE`). Se oferecer o sistema como serviço a terceiros, a AGPL exige disponibilizar o código-fonte a eles.
