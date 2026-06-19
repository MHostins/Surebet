# Opportunity Engine

## Objetivo da Fase 3

O Opportunity Engine transforma discrepancias ja detectadas pelo fluxo multi-bookmaker em oportunidades calculadas pelo `OpportunityCalculator`.

Esta fase continua 100% read-only. Ela nao acessa casas de apostas, nao clica, nao preenche stakes e nao envia ordens. O motor apenas le um relatorio local, calcula cenarios simulados e grava arquivos de saida.

## Entrada

Arquivo esperado:

```text
outputs/multi_bookmaker_discrepancy_report.json
```

Se o arquivo nao existir, o servico nao falha. Ele cria um relatorio vazio com `status: missing_input`, CSV com cabecalho e uma linha de historico JSONL.

O formato atual usado pelo motor vem do comparador multi-bookmaker e inclui campos como:

- `sport_name`
- `market_type`
- `event_name_matchbook`
- `event_name_pinnacle`
- `start_time_matchbook`
- `start_time_pinnacle`
- `selection_matchbook`
- `selection_pinnacle`
- `side_matchbook`
- `odd_matchbook`
- `odd_pinnacle`
- `net_odd_matchbook`
- `net_odd_pinnacle`
- `liquidity_matchbook`

## Saidas

O motor grava:

```text
outputs/calculated_opportunities.json
outputs/calculated_opportunities.csv
outputs/opportunity_watch_history.jsonl
```

O JSON contem o resumo da execucao e a lista de oportunidades calculadas. O CSV contem os principais campos tabulares para auditoria. O JSONL e append-only e registra uma linha por execucao.

## Criterios Suportados

Nesta primeira integracao, o motor aceita somente:

- mercados simples de 2 resultados;
- odds Back/Back;
- odds tradicionais ou odds liquidas ja normalizadas;
- dois resultados distintos no mesmo evento e mercado;
- calculo `simple_2_way`.

Para cada selecao, o motor escolhe a melhor odd liquida entre Matchbook Brasil e Pinnacle dentro do relatorio de discrepancia. Depois monta uma `Opportunity` com duas legs e chama o `OpportunityCalculator`.

## Cross-Bookmaker Optimization

A otimizacao existe porque o relatorio de discrepancias pode conter odds equivalentes para o mesmo resultado em mais de uma casa. Antes da Fase 3.0.1, o motor podia acabar calculando oportunidades com as duas legs vindas da mesma casa, como Pinnacle x Pinnacle ou Matchbook Brasil x Matchbook Brasil. Isso ainda e matematicamente valido para auditoria, mas e menos util para procurar arbitragem operacional entre casas diferentes.

O fluxo atual faz o seguinte:

1. agrupa as linhas por esporte, evento, horario inicial e mercado;
2. ignora linhas Lay;
3. ignora mercados complexos antes do calculo;
4. coleta todas as odds Back disponiveis por selecao;
5. deduplica mantendo a melhor odd liquida de cada bookmaker por selecao;
6. avalia as combinacoes possiveis de duas selecoes;
7. escolhe a combinacao com menor soma implicita;
8. se duas combinacoes forem matematicamente equivalentes, prefere a cross-bookmaker.

O motor nao forca cross-bookmaker quando isso pioraria a soma implicita. Se a melhor combinacao real vier da mesma casa, ela e preservada como mesma-casa.

Campos adicionais:

- `optimization_model`: modelo usado na preparacao da oportunidade, atualmente `best_net_odds_per_selection`;
- `source_candidate_count`: quantidade de linhas Back usadas como fonte no grupo;
- `selected_best_odds`: bookmaker e odd liquida escolhidos por selecao;
- `bookmaker_pair`: par de bookmakers nas legs escolhidas;
- `is_cross_bookmaker`: `true` quando as duas legs vierem de bookmakers diferentes;
- `distance_to_surebet_percent`: distancia percentual ate a fronteira de surebet.

A distancia ate surebet e calculada assim:

```text
distance_to_surebet_percent = max(0, (implied_sum - 1) * 100)
```

Exemplo:

```text
implied_sum = 1.0172
distance_to_surebet_percent = 1.72
```

Quando `implied_sum < 1`, a distancia e `0` e a oportunidade pode ser marcada como surebet pelo `OpportunityCalculator`.

## Criterios de Exclusao

O motor nao considera nesta fase:

- Lay;
- mercados com mais ou menos de 2 resultados;
- handicap asiatico;
- linhas com push;
- mercados complexos;
- tempo extra quando nao houver equivalencia clara;
- odds invalidas;
- resultados duplicados.

Mercados unsupported sao ignorados nesta etapa e nao viram candidatos calculados.

## Campos do Relatorio

Cada oportunidade calculada inclui:

- `opportunity_id`
- `sport`
- `event_name`
- `start_time`
- `market_type`
- `result_count`
- `calculation_model`
- `optimization_model`
- `source_candidate_count`
- `selected_best_odds`
- `bookmaker_pair`
- `is_cross_bookmaker`
- `legs`
- `implied_sum`
- `total_implied_probability`
- `roi_percent`
- `stake_total`
- `stake_plan`
- `return_by_outcome`
- `guaranteed_profit`
- `worst_case_profit`
- `is_surebet`
- `distance_to_surebet_percent`
- `calculation_warnings`

O resumo inclui:

- `total_input_comparisons`
- `total_candidates`
- `total_supported`
- `total_surebets`
- `best_roi_percent`
- `best_event`
- `best_market`
- `best_guaranteed_profit`
- `closest_distance_to_surebet_percent`
- `cross_bookmaker_candidates`
- `cross_bookmaker_surebets`

## Historico JSONL

Cada linha de `outputs/opportunity_watch_history.jsonl` contem:

- `timestamp`
- `total_candidates`
- `total_supported`
- `total_surebets`
- `best_roi_percent`
- `best_event`
- `best_market`
- `best_guaranteed_profit`
- `closest_distance_to_surebet_percent`
- `cross_bookmaker_candidates`
- `cross_bookmaker_surebets`

Esse arquivo e append-only para permitir acompanhar a evolucao das oportunidades calculadas ao longo das execucoes.

## Modo CLI

Execute:

```powershell
py main.py --mode calculate-opportunities
```

O comando:

1. le `outputs/multi_bookmaker_discrepancy_report.json`;
2. monta oportunidades simples elegiveis;
3. chama o `OpportunityCalculator`;
4. salva JSON, CSV e historico;
5. imprime um resumo seguro no terminal.

## Limitacoes Atuais

- Ainda nao ha integracao com o watcher.
- Ainda nao ha calculo para mercados de 3 resultados neste servico, embora o `OpportunityCalculator` ja suporte `simple_3_way`.
- Ainda nao ha tratamento de Draw/empate vindo do relatorio multi-bookmaker.
- Pinnacle nao fornece liquidez no relatorio atual.
- O motor assume que `net_odd_*` ja representa a odd liquida quando disponivel.
- A preferencia cross-bookmaker so atua em empate matematico; ela nao troca uma odd melhor por uma odd pior apenas para diversificar casas.

## Garantia Read-Only

O `OpportunityEngineService` trabalha apenas com arquivos locais em `outputs/`. Ele nao usa clientes HTTP, nao chama APIs externas, nao abre navegador, nao acessa banco SQLite e nao possui qualquer funcao de aposta real.
