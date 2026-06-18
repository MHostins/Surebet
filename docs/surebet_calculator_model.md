# Modelo De Calculadora De Surebet

Este documento descreve formulas publicas e independentes para uma calculadora propria do projeto Surebet. Ele nao replica codigo, payload, interface, IDs ou regra privada da SureBet.com.

## Premissas

Uma surebet simples exige que os resultados sejam:

- mutuamente exclusivos;
- coletivamente exaustivos;
- liquidados no mesmo evento/mercado;
- sem void parcial, push ou meia vitoria/perda.

Exemplos suportados inicialmente:

- mercado de 2 resultados: `Time A` ou `Time B`;
- mercado de 3 resultados: `Casa`, `Empate`, `Fora`.

Nao aplicar a formula simples diretamente a:

- handicap asiatico;
- totais com push;
- linhas fracionadas como `2.25`, `2.75`, `3.75`;
- mercados condicionais;
- mercados de periodo combinados;
- dutching com void/meia vitoria/meia perda;
- back/lay sem modelar liability;
- mercados onde as pontas nao cobrem todos os cenarios.

## Odd Liquida

Para uma aposta Back em casa ou exchange com comissao sobre lucro:

```text
net_odd = 1 + (raw_odd - 1) * (1 - commission)
```

Exemplo:

```text
raw_odd = 2.00
commission = 0.05
net_odd = 1 + (2.00 - 1) * 0.95 = 1.95
```

Para casa tradicional sem comissao:

```text
net_odd = raw_odd
```

## Surebet De 2 Resultados

Odds liquidas:

```text
O1, O2
```

Probabilidade implicita total:

```text
S = 1/O1 + 1/O2
```

Condicao de surebet:

```text
S < 1
```

ROI:

```text
ROI = (1/S - 1) * 100
```

Distribuicao de stake para stake total `T`:

```text
stake_1 = T * (1/O1) / S
stake_2 = T * (1/O2) / S
```

Retorno por cenario:

```text
return_i = stake_i * Oi
```

Lucro garantido:

```text
profit = min(return_1, return_2) - T
```

Em uma distribuicao ideal, os retornos sao iguais salvo arredondamento.

## Surebet De 3 Resultados

Odds liquidas:

```text
O1, O2, O3
```

Probabilidade implicita total:

```text
S = 1/O1 + 1/O2 + 1/O3
```

Condicao de surebet:

```text
S < 1
```

ROI:

```text
ROI = (1/S - 1) * 100
```

Distribuicao de stake:

```text
stake_1 = T * (1/O1) / S
stake_2 = T * (1/O2) / S
stake_3 = T * (1/O3) / S
```

Retorno por cenario:

```text
return_i = stake_i * Oi
```

Lucro garantido:

```text
profit = min(return_1, return_2, return_3) - T
```

## Exemplos Validados Na Auditoria

Exemplo publico anterior:

```text
O1 = 2.02
O2 = 2.02
S = 1/2.02 + 1/2.02 = 0.990099
ROI = (1/0.990099 - 1) * 100 = 1.00%
```

Exemplo autenticado com `EsportivaBet (BR)` e `Novibet (BR)`:

```text
O1 = 3.80
O2 = 1.85
S = 1/3.80 + 1/1.85 = 0.803698
ROI = (1/0.803698 - 1) * 100 = 24.4248%
```

Com stake total `T = 100`:

```text
stake_1 = 32.74
stake_2 = 67.26
retorno_por_cenario = 124.42
lucro_garantido = 24.42
```

Esse resultado corresponde ao lucro exibido de `24,4%`.

Segundo exemplo autenticado:

```text
O1 = 1.36
O2 = 4.00
S = 1/1.36 + 1/4.00 = 0.985294
ROI = (1/0.985294 - 1) * 100 = 1.4925%
```

Com stake total `T = 100`:

```text
stake_1 = 74.63
stake_2 = 25.37
retorno_por_cenario = 101.49
lucro_garantido = 1.49
```

Esse resultado corresponde ao lucro exibido de `1,49%`.

## Arredondamento

Na pratica, casas aceitam stakes com granularidade limitada. A calculadora deve:

1. Calcular stake ideal.
2. Aplicar stake minima e incremento permitido por casa.
3. Recalcular retorno por cenario.
4. Exibir pior cenario.
5. Marcar a oportunidade como invalida se o arredondamento destruir a margem.

Campos recomendados:

```text
ideal_stake
rounded_stake
rounding_delta
return_by_outcome
worst_case_profit
worst_case_roi
rounding_warning
```

## Liquidez

Para casas tradicionais, liquidez pode ser desconhecida e deve ser tratada como limite operacional configuravel.

Para exchanges:

```text
stake_i <= available_liquidity_i
```

Para Lay:

```text
liability = lay_stake * (lay_odd - 1)
```

Back/Lay deve ser calculado por payoff por cenario, descontando comissao apenas no cenario em que houver lucro sujeito a comissao.

## Matriz De Payoff

Para mercados complexos, representar cada ponta como vetor de resultado:

```text
payoff_matrix[leg][outcome]
```

Depois resolver stakes para maximizar o menor lucro:

```text
maximize min(outcome_profit)
subject to:
  sum(stakes) = total_stake
  stake_i >= minimum_stake_i
  stake_i <= max_liquidity_i
```

Essa abordagem e necessaria para:

- linhas asiaticas;
- handicap com push;
- totais com linhas diferentes;
- combinacoes `Over/Under` em thresholds distintos;
- mercados correlacionados com void parcial.

## Campos Para Relatorio

Adicionar aos relatorios futuros:

```text
calculation_model
result_count
raw_odds
net_odds
commission
implied_probability_by_leg
total_implied_probability
roi_percent
stake_total
stake_plan
return_by_outcome
guaranteed_profit
worst_case_profit
worst_case_roi
minimum_stake
stake_increment
rounding_policy
liquidity_status
calculation_warnings
```

## Regra De Seguranca

A calculadora deve ser somente read-only/simulacao. Ela nao deve conter:

- envio de aposta;
- criacao de ordem;
- instrucao de aposta;
- deep-link automatico com stake preenchida;
- automacao de clique em casas;
- qualquer funcao chamada `place_bet`, `place_order`, `send_order` ou equivalente.
