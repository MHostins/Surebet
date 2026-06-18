# Opportunity Calculator

Este documento descreve o nucleo matematico read-only do projeto para calcular surebets simples de 2 e 3 resultados. Ele nao executa apostas, nao envia ordens, nao automatiza cliques e nao integra com o watcher nesta etapa.

## Modelo

### Opportunity

Representa uma oportunidade teorica de arbitragem.

Campos principais:

- `opportunity_id`
- `sport`
- `event_name`
- `start_time`
- `market_type`
- `result_count`
- `legs`
- `calculation_model`

Modelos suportados inicialmente:

- `simple_2_way`
- `simple_3_way`

### OpportunityLeg

Representa uma ponta da oportunidade.

Campos principais:

- `bookmaker`
- `selection`
- `odds`
- `commission`
- `net_odds`
- `side`
- `market_type`
- `liquidity`

Nesta versao, somente `side="back"` e suportado.

### StakePlan

Representa a distribuicao simulada de stake.

Campos:

- `stake_total`
- `stakes_by_selection`
- `stakes_by_bookmaker`

### CalculationResult

Resultado do calculo.

Campos principais:

- `total_implied_probability`
- `roi_percent`
- `stake_total`
- `stake_plan`
- `return_by_outcome`
- `guaranteed_profit`
- `worst_case_profit`
- `is_surebet`
- `calculation_warnings`

## Odd Liquida

Para apostas Back com comissao sobre lucro:

```text
net_odd = 1 + (raw_odd - 1) * (1 - commission)
```

Para bookmaker tradicional:

```text
commission = 0
net_odd = raw_odd
```

## Formula De Surebet Simples

Probabilidade implicita total:

```text
S = soma(1 / net_odd_i)
```

Condicao de surebet:

```text
S < 1
```

ROI:

```text
ROI = (1 / S - 1) * 100
```

Stake por ponta:

```text
stake_i = total_stake * (1 / net_odd_i) / S
```

Retorno por cenario:

```text
return_i = stake_i * net_odd_i
```

Lucro garantido:

```text
guaranteed_profit = min(return_by_outcome) - total_stake
```

## Exemplos

### Odds 2.02 / 2.02

```text
S = 1/2.02 + 1/2.02 = 0.990099
ROI = 1.00%
Stake total = 100
Stake por ponta = 50.00 / 50.00
Lucro garantido = 1.00
```

### Odds 3.80 / 1.85

```text
S = 1/3.80 + 1/1.85 = 0.803698
ROI = 24.4248%
Stake total = 100
Stake por ponta = 32.7434 / 67.2566
Lucro garantido = 24.4248
```

### Odds 1.36 / 4.00

```text
S = 1/1.36 + 1/4.00 = 0.985294
ROI = 1.4925%
Stake total = 100
Lucro garantido = 1.4925
```

### Mercado De 3 Resultados

Exemplo:

```text
odds = 3.40 / 3.50 / 3.60
S = 0.857610
ROI = 16.6032%
```

## Rejeicoes Conservadoras

A calculadora marca como unsupported ou invalido quando encontra:

- `calculation_model` diferente de `simple_2_way` ou `simple_3_way`;
- menos de 2 pontas;
- mais de 3 pontas;
- `result_count` diferente do numero de pontas;
- `side` diferente de `back`;
- odds ou net odds menores ou iguais a 1;
- comissao negativa ou maior/igual a 1;
- selecoes duplicadas;
- mercado com marcadores de complexidade, como `asian`, `handicap`, `push`, `tempo extra`, `extra time`, `overtime`, `complex` ou `matrix`.

Mercados rejeitados nao sao tratados como surebet, mesmo que os numeros parecam favoraveis.

## Limitacoes

Esta etapa nao suporta:

- back/lay;
- liability;
- handicap asiatico;
- linhas com push;
- tempo extra misturado com tempo regulamentar;
- mercados correlacionados;
- matriz de payoff;
- stake minima por casa;
- arredondamento por incremento real de stake;
- liquidez como limite de stake.

## Proximos Passos

1. Adicionar politica de arredondamento por bookmaker.
2. Adicionar stake minima e incremento minimo.
3. Criar matriz de payoff para mercados complexos.
4. Integrar o resultado ao compare multi-bookmaker somente depois de validar os modelos simples.
5. Criar relatorio separado de oportunidades calculadas, sem alterar o watcher.
