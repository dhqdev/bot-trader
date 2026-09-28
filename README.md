# Bot Trader

Sistema pessoal de trading automatizado na **OKX** (Spot), com painel web de **4 abas** (Painel, Automático, Robôs e Configurações). No **modo automático** você só liga: a IA escolhe as moedas e as estratégias, testa no histórico, liga os robôs, acompanha se está ganhando ou perdendo e troca quem vai mal. Se preferir escolher, para criar um robô você só responde três perguntas: **qual moeda**, **quanto usar** e **qual volatilidade**. O sistema testa todos os robôs no histórico real da moeda, mostra do melhor ao pior, e a IA (**Claude ou GPT**, você escolhe) recomenda o que faz mais sentido. Automático ou manual: é um ou outro. Depois, a IA de cada robô continua testando e aplicando melhorias sozinha, e a IA **aprende o tempo todo**: anota o que cada estratégia promete e confere depois o que ela entregou no mercado. As notícias, o sentimento do mercado e a tendência do Bitcoin travam compras em momentos ruins. Login com verificação em duas etapas e chaves criptografadas.

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
3. **Automático → escolha o valor simulado → Ligar no simulado.** Pronto: a IA faz o resto (ver "Modo automático" abaixo). Ela opera no mercado real da OKX (preços ao vivo, taxa da sua conta e slippage) com esse valor de mentira, sem gastar dinheiro. Quando estiver confiante, toque em **Usar dinheiro real**.
4. Ou, se quiser escolher você mesmo (é um ou outro: com o automático ligado, o Novo robô fica bloqueado; com robôs seus ligados, o automático não liga): **Robôs → Novo robô**, escolha a moeda, o valor por operação e a volatilidade, e toque em **Usar** no robô do ranking.
5. Acompanhe pelo **Painel**.

O botão **Sistema ligado/desligado**, no topo, para ou retoma todos os robôs de uma vez. Desligar não vende as posições.

## O que tem em cada tela

- **Automático:** um botão para ligar. Depois mostra o resultado da IA (total, em % do valor, hoje, realizado e em aberto), os robôs que ela opera com o motivo de cada escolha e o que o teste prometia, **o que a IA aprendeu** e o histórico do que ela fez em cada dia.
- **Painel:** resultado total (realizado + em aberto), hoje, taxa de acerto, curva de resultado acumulado, resultado por dia, robôs, resultado por estratégia, carteira da OKX, humor do mercado com as notícias fortes do momento, últimas operações e atividade. Separa **Real** de **Simulado**.
- **Robôs:** um cartão por robô com a chave de ligar/desligar, o resultado e o que ele está fazendo agora. **Novo robô** abre o assistente:
  1. **Moeda:** as mais negociadas entre as **liberadas na sua conta da OKX** (a lista vem da própria OKX, pela sua chave), com preço e variação do dia, ou qualquer outra liberada pela busca. Sem chave cadastrada, a lista pública.
  2. **Valor:** quanto cada compra usa, em USDT, com o seu saldo livre na OKX ao lado (se a chave estiver cadastrada) e quanto a moeda costuma oscilar por dia. Com a chave **Valor simulado** ligada (padrão), é dinheiro de mentira: o robô opera no mercado real da OKX, com os preços ao vivo, sem usar o seu saldo.
  3. **Volatilidade:** baixa, média ou alta (ver "Volatilidade e ranking" abaixo).
  4. **Robôs:** todos os robôs daquela volatilidade testados na moeda, do melhor ao pior, com quanto o valor escolhido teria virado, a queda máxima, o resultado recente e a comparação com só segurar a moeda. A recomendação da IA vem no topo; um toque em **Usar** cria o robô (simulado ou real) e já liga.
- **Detalhe do robô:** gráfico de candles com compras e vendas, **o que o robô está esperando** para comprar ou vender, posição aberta, operações, atividade, a **IA do robô** (ajustar sozinha, só sugerir ou nada) e os detalhes técnicos para quem quiser conferir. O lápis edita nome, valor por operação e modo.
- **Configurações:** chave da OKX (com conferência das permissões na própria OKX e o IP do servidor para vincular), qual IA usar (Claude ou GPT, e o modelo do GPT), verificação em duas etapas, sessões abertas e atividade recente da conta.

## Modo automático (a IA faz tudo)

Você não escolhe nada além do valor: digite o **valor simulado** e toque em **Ligar no simulado** (ou **Usar dinheiro real**, que pede o valor total, sua senha e o código de 2 etapas). Ao ligar, e depois uma vez por dia:

1. **Testa** todas as estratégias, nas volatilidades baixa e média, nas 8 moedas mais negociadas da OKX **que a sua conta pode negociar** (moedas estáveis ficam de fora), no histórico real e com taxas. A volatilidade alta não entra: nos testes, as taxas comeram o lucro de todas as estratégias de minutos.
2. **Aprova** só robôs com lucro no período todo **e** no período recente, com operações suficientes, já descontando a **taxa real da sua conta** (ver "Taxa da OKX" abaixo). Na ordem, robô com poucas operações pesa menos (+300% em 4 operações numa alta forte pode ter sido sorte) e vale o peso que a IA aprendeu (ver "A IA que aprende").
3. **Acompanha** os robôs que ela opera: encerra quem perdeu 10% do valor que recebeu (conferido a cada minuto) ou quem deixou de passar nos testes (só depois de 3 dias, porque cada troca custa taxas). Robô encerrado por ir mal não volta pelos 14 dias seguintes.
4. **Escolhe**: a IA (Claude ou GPT) escolhe entre os aprovados, no máximo um robô por moeda, e pode deixar o dinheiro parado em USDT se o mercado estiver ruim. Ela nunca escolhe um robô reprovado. Sem chave de IA, vale a ordem do ranking.
5. **Liga** os robôs, dividindo o valor total em até 3 partes iguais (pelo menos 5 USDT cada: com 9 USDT, por exemplo, vai tudo num robô só). A IA de cada robô continua ajustando stop, trailing e parâmetros.

Proteções:

- Robô encerrado que ainda tem uma compra aberta não compra de novo: ele vende pela regra normal (sinal, stop ou alvo) e então para. O modo automático nunca vende na hora nem tira o stop.
- Se o resultado total desde que foi ligado chegar a **−20%** do valor, todos os robôs são encerrados e nada novo é criado até você tocar em **Retomar**.
- Desligar funciona do mesmo jeito: os robôs param de comprar e fecham as posições pela regra normal.
- Com dinheiro real, o valor não pode passar do seu saldo livre de USDT na OKX.
- **É um ou outro:** com o automático ligado, você não cria nem liga robôs manuais; com robôs escolhidos por você ligados, o automático não liga. Robô manual segue sempre a estratégia que você escolheu.

## A IA que aprende (o tempo todo)

Teste bonito no histórico nem sempre se repete. Por isso a IA confere as próprias previsões:

1. **Anota:** toda semana, nas 8 moedas mais negociadas da sua conta, guarda o que cada robô das volatilidades baixa e média prometia no teste, com o modo automático ligado ou não.
2. **Confere:** passados 30 dias (candles de 1h e 2h), 60 dias (4h) ou 120 dias (diário, que opera pouco), mede o que o robô fez de verdade nesse período novo, com os candles reais que chegaram depois. É um teste no futuro, que não dá para "decorar".
3. **Pesa:** para cada estratégia e tempo de candle, compara o prometido com o entregue. Quem cumpre ganha peso na escolha do modo automático; quem promete e não entrega perde peso e, com muitas conferências ruins, deixa de ser escolhida. Com poucas conferências, o peso fica perto de 1: um mês ruim não condena ninguém.
4. **Começa sabendo:** na primeira vez, faz o mesmo exercício em datas passadas (de 1 a 8 meses atrás), então o aprendizado já nasce com centenas de conferências.

O resultado aparece no cartão **O que a IA aprendeu**, na aba Automático, e vai junto para o Claude/GPT na decisão diária. Não gasta tokens: é conta com os dados do mercado, a cada 6 horas.

## IA: Claude ou GPT

Cadastre a chave de um dos dois (ou dos dois) em **Configurações**. A chave cadastrada por último passa a ser a usada, e dá para alternar a qualquer momento. A IA trabalha nos bastidores, sem conversa: **recomenda o robô** a partir do ranking, do humor do mercado e das notícias (ela só pode escolher entre os robôs testados); **classifica as notícias**; e **melhora cada robô** (ver "IA do robô"). Sem chave, tudo funciona do mesmo jeito, com a recomendação seguindo o ranking.

| | Claude (Anthropic) | GPT (OpenAI) |
|---|---|---|
| Recomendação e IA do robô | `claude-opus-5` | `gpt-6-sol` (padrão; dá para escolher `gpt-6-astra`, mais capaz e ~5× mais caro, ou `gpt-6-luna`) |
| Classificação das notícias | `claude-haiku-4-5` | `gpt-6-luna` |
| Onde criar a chave | console.anthropic.com | platform.openai.com → API keys |

Ao salvar a chave da OpenAI, o sistema confere a chave e o modelo na própria OpenAI (a consulta não gasta créditos). Os modelos também podem ser trocados pelas variáveis `BT_AI_MODEL`, `BT_AI_FAST_MODEL`, `BT_OPENAI_MODEL` e `BT_OPENAI_FAST_MODEL`.

## Estratégias

Todas são long-only (só compram) e avaliadas **apenas em candles fechados**. O sinal do backtest é exatamente o mesmo da operação real, e isso é testado. Você não precisa escolher estratégia: o assistente testa todas e mostra a melhor para a moeda. Nos testes, candles de 4 horas (volatilidade baixa) foram os mais consistentes; 1 hora ou menos perdeu em quase todas por causa do ruído e das taxas.

| Estratégia | Estilo | Como funciona |
|---|---|---|
| **Squeeze: compressão e rompimento** (nova, recomendada) | rompimento | Espera o preço ficar comprimido (Bollinger dentro do Keltner) por 8+ candles e compra quando a compressão se desfaz com momentum para cima. Sai quando o preço perde a média do canal. |
| **Candle de ignição** (nova) | momentum | Compra o candle que "acende" o movimento: alta de 1,5× o ATR, volume 1,5× a média e fechamento perto da máxima. Sai ao perder a EMA 20. |
| **Momentum ajustado à volatilidade** (nova) | momentum | Compra quando o retorno dos últimos 30 candles, dividido pela volatilidade esperada, passa de 1 desvio (z-score). Sai quando a força some. |
| Confluência de tendência | tendência | EMA 9 cruzando a 21 há até 10 candles, acima da EMA 200, com 4 de 5 confirmações (Supertrend, MACD, RSI, ADX, volume). |
| Rompimento Donchian (Tartarugas) | rompimento | Compra na máxima de 20 candles com volume e ADX; vende na mínima de 10. |
| HiLo + RSI (ChiloRSI v2) | tendência | Evolução da estratégia que o bot antigo usava: entra logo após o HiLo (55) virar, com filtros de RSI, tendência e ATR%. |

Cada robô do assistente é uma estratégia com um tempo de candle e regras de risco (stop, trailing, alvos e filtro de sentimento) já validadas para aquele tempo. Há também o **Repique RSI**, que compra quedas exageradas nos candles de minutos.

### Volatilidade e ranking

A volatilidade escolhida define o tempo de candle, quanto dura cada operação e quanto histórico entra no teste:

| Volatilidade | Candles | Cada operação dura | Histórico testado |
|---|---|---|---|
| **Baixa** | 4 h e diário | dias a semanas | 2 anos |
| **Média** | 1 h e 2 h | horas | 1 ano |
| **Alta** | 5 e 15 min | minutos | 45 dias |

Para a moeda escolhida, o sistema roda as 7 estratégias nos 2 tempos de candle (14 robôs), com taxa, slippage, stop e filtro de sentimento, e ordena pelo resultado no período todo **e** no terço mais recente, descontando metade da maior queda de cada um. Robôs com menos de 4 operações ficam no fim: pode ter sido sorte. O resultado fica guardado por 30 minutos (**Testar de novo** refaz na hora), e o histórico das moedas mais populares é baixado de antemão, então o ranking costuma sair em segundos.

A pesquisa que escolheu as estratégias e as regras de cada tempo de candle (dados reais de 14 pares, taxa de 0,1% e slippage) deu estes resultados típicos:

| Volatilidade | Robô | Candle | Cada operação dura | Resultado típico | Casos com lucro |
|---|---|---|---|---|---|
| **Alta** (experimental) | Repique RSI | 5 min | ~46 min | −2,6% em 45 dias | 7% |
| | Ignição | 15 min | ~1,5 h | −8,4% em 4 meses | 4% |
| **Média** | Ignição | 1 h | ~17 h | +8,3% em 6 meses | 62% |
| | HiLo com trailing | 2 h | ~21 h | +4,3% em 8 meses | 64% |
| **Baixa** | **Squeeze** | 4 h | ~3 dias | +23,3% em 1 ano | 73% |
| | Confluência | diário | ~3 semanas | +23,1% em 18 meses | 77% |

Os números já incluem o **filtro de sentimento** (ver abaixo), medido com o Índice de Medo e Ganância real de cada dia.

**Sobre a volatilidade alta:** nos testes, **nenhuma** estratégia de minutos lucrou depois dos custos. Foram 9 estratégias, 3 regras de risco, candles de 5 e 15 minutos e 14 pares. Cada operação paga cerca de 0,3% entre taxa e slippage, e os movimentos de poucos minutos costumam ser menores que isso. Ela existe porque você pode querer testá-la; usá-la com dinheiro real exige marcar uma confirmação.

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

**Removidas por desempenho fraco:** Supertrend (−3,5% fora da amostra), Cruzamento de EMAs (−4,0%), Momentum MACD (−4,2%) e Reversão Bollinger (quase não operava: ~2 operações por período). Robôs que usavam alguma delas são migrados automaticamente para a substituta, com um aviso na atividade.

O que isso significa:

- **Em 4h, as 3 novas lideram**, e a Squeeze tem o menor drawdown e o melhor pior caso.
- **Em alta forte, segurar a moeda ganha.** No período mais antigo (alta forte), o buy & hold superou todas. As estratégias ganham principalmente **protegendo nas quedas**, porque ficam em USDT boa parte do tempo.
- **O Momentum/volatilidade tem o maior drawdown.** Se usar, prefira posições menores.
- A configuração antiga do bot (ChiloRSI + stop 5%, trailing 3%, alvos 5/10/20%) teve mediana entre −14% e −19% nos mesmos tipos de teste.
- **Nada disso é garantia.** Rode em modo simulado antes do real.

### Revisão com a taxa real (set/2026)

Refeita com a taxa de 0,4% por ordem, 14 moedas (7 de design e 7 de validação) e o mesmo método do sistema: escolhe o robô num período e mede no período seguinte, que ele não viu. Uma mudança só entrou se melhorou **nos dois grupos**.

| Volatilidade | O que mudou | Antes → depois |
|---|---|---|
| **Baixa** (4h e diário) | Só compra com o **Bitcoin acima da média de 100 dias** (último diário fechado). Quando o BTC cai, quase todas caem junto. | Robô escolhido, média por período: design +5,5% → +1,6%; validação −3,1% → +1,7%. Passou a ficar positivo nos dois grupos. |
| **Média** (1h e 2h) | Só compra se o candle costuma andar **1,5× o custo de ida e volta** (2 × (taxa + slippage)). | Robô típico, a cada 4 meses: −5,5% / −6,6% → −1,4% / 0%. As taxas comiam o resultado. |
| Alta (minutos) | Nada. | |

Também foram testados e **descartados** (não melhoraram nos dois grupos): tendência de fundo de 20 e 60 dias na própria moeda, pausa 3× maior depois de vender, trailing stop nos robôs lentos, stop mais largo e o filtro de custo na volatilidade baixa. Com 0,4% por ordem, a média opera pouco e quase não tem vantagem: o filtro serve para não perder. A baixa segue a melhor opção.

### Gerenciamento de risco (por bot)

- **Tamanho:** valor fixo por compra, % do saldo, ou % de risco até o stop.
- **Stop:** por volatilidade (padrão: 3× ATR, no mínimo 0,5%) ou percentual.
- **Opcionais:** break-even, trailing stop (ATR ou %), até 5 alvos parciais.
- **Disciplina:** pausa após saída e perda diária máxima (bloqueia novas compras no dia).
- **Sentimento do mercado:** filtro de compras pelo Índice de Medo e Ganância (ver abaixo).
- **Notícias:** trava de compras (e, se quiser, venda da posição) com notícia grave sobre a moeda.
- **Custo da operação:** só compra se o candle costuma andar N vezes o custo de ida e volta (padrão 1,5× na volatilidade média).
- **Tendência do Bitcoin:** só compra com o último diário do BTC acima da média de N dias (padrão 100 na volatilidade baixa).
- Stops e alvos são conferidos a cada ~15 s com o preço atual, não só no fechamento do candle.
- Cada bot só vende o que ele mesmo comprou; ativos que já estão na sua carteira não são tocados.

## Chave da OKX

1. Na OKX (Perfil → **API** → Criar chave de API V5), dê um nome, crie uma **passphrase** (guarde: a OKX pede junto com a chave) e marque só **Leitura** e **Negociação**. **Nunca** marque Saque.
2. Em "Endereço IP", vincule o IP do servidor, que aparece no cartão da OKX em Configurações. Sem IP vinculado a chave funciona, mas a OKX pode apagar chaves de negociação que ficam muitos dias sem uso.
3. Deixe a conta no modo **Spot** (a OKX chama de modo de conta "Spot"): o sistema opera sem margem.
   Os robôs compram com **USDT**: compre USDT com seus reais (PIX ou P2P) e **transfira da conta de financiamento (Funding) para a conta de negociação (Trading)**. O sistema só enxerga o saldo da conta de negociação. Não precisa comprar a moeda antes.
4. No Bot Trader, em Configurações → **OKX**, cole a API key, a Secret key e a passphrase, escolha a região (Brasil = Global) e confirme com sua senha. O sistema confere tudo na OKX antes de salvar.
5. Para testar sem dinheiro, crie chaves no **Demo Trading** da OKX e marque "Chaves do Demo Trading".

### Taxa da OKX

A taxa muda por conta, nível e região. Contas do Brasil no nível **Lv1**, por exemplo, pagam **0,1%** em ordens limitadas e **0,4%** em ordens a mercado, que são as que os robôs usam. Uma compra e venda custa ~0,85%. Com a chave cadastrada, o sistema lê a taxa da sua conta na própria OKX e usa essa taxa nos testes do ranking, na escolha do modo automático e no simulado. Sem chave, usa 0,1%. A pesquisa abaixo foi feita com 0,1%: com a taxa real, menos robôs passam (num teste de set/2026, 55 de 217 contra 89 com 0,1%).

Tudo usa a OKX: preços ao vivo, ordens, saldo, a lista de pares e o histórico dos testes do ranking e da IA do robô. O histórico baixado fica guardado no banco, então só a primeira consulta de cada par demora alguns segundos. Os robôs criados antes da mudança (quando o sistema usava a Binance) foram migrados sozinhos: os simulados seguem rodando com preços da OKX; os reais foram desligados para você conferir as chaves e religar.

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
- Notícias boas **não** disparam compras: comprar na euforia da manchete costuma ser comprar no topo. Elas entram na recomendação da IA.
- As notícias fortes do momento aparecem no **Painel**, no cartão "Mercado agora".
- Não existe histórico de manchetes para backtest, então a trava de notícias não entra no ranking. O filtro de sentimento entra.

## IA do robô (o sistema que se aperfeiçoa sozinho)

A cada ciclo (por padrão: todo dia nos robôs de volatilidade alta, a cada 3 dias na média e toda semana na baixa, ou pelo botão **Testar melhorias agora** no robô), para cada robô ligado:

1. **Diagnóstico ("backlog"):** lê as operações, stops, sinais ignorados e erros do bot e aponta os problemas (ex.: muitos stops logo após a compra, resultado real abaixo do backtest, ordens abaixo do mínimo).
2. **Candidatas:** variações de **uma coisa por vez**: cada parâmetro da estratégia um pouco para cima e para baixo, stop, trailing, alvo, break-even, pausa, filtro de sentimento, filtro de custo, tendência do Bitcoin, a configuração anterior e as ideias da IA. Ela **nunca troca a estratégia**: o robô segue a que você (ou o modo automático) escolheu.
3. **Validação honesta:** o histórico (2 anos) é dividido em duas partes. A escolha usa só os 2/3 mais antigos; o 1/3 mais recente, que a escolha não viu, serve de confirmação. A candidata também não pode piorar em BTC e ETH.
4. **Decisão:** só muda se melhorar nas duas partes, sem aumentar a queda máxima, com operações suficientes. No máximo uma mudança a cada 5 dias por bot. Nunca mexe no par, no tempo de candle, no modo (simulado/real) nem no valor das ordens, e nunca tira o stop.
5. **Aprendizado:** cada ciclo fica registrado, junto com o resultado real depois da mudança. Com uma chave de IA (Claude ou GPT), a IA escreve a análise, guarda lições e propõe ideias novas, que passam pelas mesmas regras. No ciclo seguinte ela recebe esse histórico.

No cartão **IA do robô**, escolha: **Ajustar sozinha** (padrão nos simulados; num robô com dinheiro real pede sua senha e o código de 2 etapas), **Só sugerir** (a sugestão aparece com os botões Aplicar e Recusar) ou **Nada**.

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
- Rode **um único processo** (já configurado). O motor dos robôs roda dentro da API, e mais workers duplicariam as ordens.
- Com HTTPS, mantenha `BT_COOKIE_SECURE=true`. Sem HTTPS (só para teste), use `false`.
- Para atualizar: `git pull && docker compose --profile https up -d --build`. Os robôs que estavam ligados voltam sozinhos (vale também para o Portainer).

## Segurança

- **Chave da OKX:** só **Leitura e Negociação**, **nunca Saque**, com o **IP do servidor vinculado**. Ao salvar, o sistema confere as permissões na própria OKX e **recusa chaves com saque**; avisa se faltar o IP vinculado ou se a conta não estiver no modo Spot.
- **Criptografia:** as chaves ficam criptografadas (Fernet) com uma chave derivada de `BT_SECRET_KEY`; a interface só mostra as pontas (`ABCD••••WXYZ`). A IA nunca recebe chaves.
- **Verificação em duas etapas (TOTP):** com qualquer app autenticador, com QR code, 10 códigos de recuperação de uso único e proteção contra reuso do mesmo código.
- **Confirmação de ações sensíveis:** trocar as chaves, desligar o 2FA, gerar códigos de recuperação e deixar a IA ajustar sozinha um robô com dinheiro real pedem a senha (e o código de 2 etapas). Quem pegar uma sessão aberta não consegue fazer isso.
- **Sessões:** cookie httpOnly, `SameSite=Strict` e `Secure` em HTTPS. "Sair dos outros aparelhos" e a troca de senha derrubam as outras sessões na hora.
- **Tentativas de login:** limite por IP e por conta; e-mail inexistente responde igual a senha errada, no mesmo tempo.
- **Proteção do site:** CSP restrita (só scripts do próprio site), HSTS, `X-Frame-Options: DENY`, `Permissions-Policy`, COOP/CORP, bloqueio de requisições que mudam dados vindas de outros sites (inclusive subdomínios), limite de tamanho das requisições e `Cache-Control: no-store` na API.
- **Registro de atividade:** logins, falhas, trocas de senha e de chaves, 2FA e autorizações ficam registrados com IP e aparelho (Configurações → Atividade recente).
- **Notícias** vêm de sites externos: o XML é lido com proteção contra ataques (defusedxml) e o texto é tratado como dado, nunca como instrução para a IA. As ideias da IA passam pelos limites dos parâmetros e pelos mesmos testes de qualquer mudança, e a recomendação dela só pode apontar um dos robôs testados. A IA nunca envia ordens.
- O arquivo `.env` antigo na raiz ainda tem suas chaves em texto puro. Depois de cadastrá-las pela interface, **apague esse arquivo**. A Binance não é mais usada: apague também as chaves de API antigas no site da Binance.

## Estrutura

```
backend/
  app/
    core/            indicadores, estratégias, risco, backtest, exchange, motor, sentimento, trava de notícias
    api/             rotas REST (auth, segurança, robôs e ranking, bots, painel, mercado, backtest, piloto, notícias)
    services/        estatísticas, backtests, ranking de robôs, IA (Claude/GPT), notícias, piloto, agendador
    models.py        tabelas (SQLAlchemy): usuários, chaves, bots, posições, ordens, eventos, relatórios,
                     2FA/sessões, atividade, notícias, medo e ganância, ciclos do piloto, lições da IA
  tests/             testes: indicadores, ausência de look-ahead, risco, backtest, motor, API, OKX,
                     ranking de robôs, IA, segurança (CSRF, 2FA, sessões), notícias, sentimento e piloto
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
