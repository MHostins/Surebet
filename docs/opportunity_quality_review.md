# Opportunity Quality Review

## Objetivo da Fase 3.3

A Fase 3.3 cria uma camada de analise sobre oportunidades ja calculadas. Ela nao altera o `OpportunityCalculator`, nao muda o `OpportunityEngineService` e nao recalcula odds. O objetivo e entender qualidade, frequencia, distancia ate arbitragem e comportamento historico das oportunidades.

O fluxo permanece read-only e trabalha apenas com arquivos locais em `outputs/`.

## Entradas

```text
outputs/calculated_opportunities.json
outputs/opportunity_watch_history.jsonl
```

Se um arquivo estiver ausente, vazio ou parcialmente invalido, o servico gera um relatorio vazio ou parcial sem quebrar. Linhas invalidas no JSONL sao ignoradas.

## Saidas

```text
outputs/opportunity_quality_review.json
outputs/opportunity_quality_review.csv
```

O JSON contem resumo geral, analise de oportunidades, rankings, agrupamentos por esporte, agrupamentos por par de casas e analise historica. O CSV contem uma tabela plana com os rankings principais.

## Comando CLI

```powershell
py main.py --mode review-opportunity-quality
```

O comando:

1. le os outputs calculados locais;
2. gera a revisao de qualidade;
3. salva JSON e CSV;
4. imprime um resumo curto;
5. nao chama APIs externas;
6. nao altera watcher, scheduler, banco ou calculadora.

## Surebet Rate

`surebet_rate_percent` mede a proporcao de oportunidades calculadas que sao surebets:

```text
surebet_rate_percent = total_surebets / total_candidates * 100
```

Exemplo: 1 surebet em 19 candidatos resulta em aproximadamente `5.26%`.

Essa taxa ajuda a acompanhar se os filtros e fontes estao produzindo oportunidades reais com frequencia ou apenas quase-oportunidades.

## Distance To Surebet

`distance_to_surebet_percent` mede o quanto uma oportunidade ainda esta distante da fronteira de arbitragem:

```text
distance_to_surebet_percent = max(0, (implied_sum - 1) * 100)
```

Quando a distancia e `0`, a oportunidade esta na zona de surebet (`implied_sum < 1`). Quanto menor a distancia positiva, mais perto a oportunidade ficou de virar arbitragem.

## Rankings

`top_surebets` lista as oportunidades lucrativas ordenadas por maior `roi_percent`.

`top_near_misses` lista oportunidades ainda nao lucrativas ordenadas pela menor distancia ate surebet.

`top_cross_bookmaker_near_misses` aplica o mesmo criterio, mas apenas para pares cross-bookmaker. Esse ranking e util porque oportunidades entre casas diferentes sao mais relevantes para arbitragem operacional do que validacoes mesma-casa.

Cada item inclui:

- `event_name`
- `sport`
- `market_type`
- `start_time`
- `bookmaker_pair`
- `is_cross_bookmaker`
- `implied_sum`
- `roi_percent`
- `distance_to_surebet_percent`
- `guaranteed_profit`
- `worst_case_profit`

## Agrupamentos

A analise por esporte mostra onde estao surgindo candidatos e surebets. A analise por par de casas mostra quais combinacoes geram mais oportunidades e quais chegam mais perto da arbitragem.

Campos principais:

- `total_candidates`
- `total_surebets`
- `average_distance_to_surebet_percent`
- `best_roi_percent`
- `closest_distance_to_surebet_percent`

## Analise Historica

A partir de `opportunity_watch_history.jsonl`, o relatorio calcula:

- `total_history_rows`
- `latest_history_timestamp`
- `history_best_roi_percent`
- `history_total_surebets_sum`
- `history_best_event`
- `trend_last_rows`

Isso ajuda a observar se a qualidade esta melhorando, piorando ou apenas oscilando entre ciclos.

## Como Ajuda nos Proximos Passos

Esta revisao ajuda a decidir:

- se ja vale iniciar um dashboard;
- quais esportes merecem prioridade;
- quais pares de casas estao mais promissores;
- se novos mercados devem ser adicionados;
- se novas casas devem ser integradas;
- se o motor precisa de filtros de qualidade antes de alertas.

## Limites de Seguranca

Esta fase nao automatiza apostas, nao clica, nao preenche stakes, nao envia ordens, nao acessa casas de apostas e nao escreve no banco SQLite. Ela apenas le arquivos locais e grava os dois outputs da revisao.
