# Opportunity Alerts

## Objetivo

A Fase 3.4 adiciona uma camada read-only de alertas sobre oportunidades ja calculadas. Ela nao calcula odds novas, nao altera o `OpportunityCalculator`, nao altera o `OpportunityEngineService` e nao integra novas casas.

O objetivo e separar oportunidades acionaveis para observabilidade:

- surebets reais;
- near-misses que ficaram perto da fronteira de arbitragem.

## Entradas

```text
outputs/calculated_opportunities.json
outputs/opportunity_watch_history.jsonl
outputs/opportunity_quality_review.json
```

O arquivo principal para alertas e `calculated_opportunities.json`. Os demais entram como contexto de origem no relatorio. Se algum arquivo estiver ausente ou invalido, o comando gera relatorio vazio sem quebrar.

## Definicoes

Surebet alert:

```text
is_surebet == true
```

Near miss alert:

```text
is_surebet == false
distance_to_surebet_percent <= ALERT_NEAR_MISS_DISTANCE_PERCENT
```

O threshold inicial e `2.0%` e pode ser configurado no `.env`:

```text
ALERT_NEAR_MISS_DISTANCE_PERCENT=2.0
```

## Outputs

```text
outputs/opportunity_alerts.json
outputs/opportunity_alerts.csv
outputs/opportunity_alert_history.jsonl
```

`opportunity_alerts.json` contem:

- `summary`
- `rankings.top_surebets`
- `rankings.top_near_misses`
- `alerts`
- informacoes de origem

`opportunity_alerts.csv` e uma tabela plana para leitura rapida.

`opportunity_alert_history.jsonl` e append-only e registra uma linha por execucao.

## Estrutura do Alerta

Cada alerta contem:

- `alert_id`
- `alert_type`
- `timestamp`
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
- `stake_plan`
- `calculation_model`
- `optimization_model`

## Comando CLI

```powershell
py main.py --mode generate-opportunity-alerts
```

O comando gera JSON, CSV e atualiza o JSONL. Ele imprime um resumo curto:

```text
Alerts generated:
Surebets: X
Near misses: Y
```

## Limitacoes

- Nao envia Telegram.
- Nao cria dashboard.
- Nao executa aposta.
- Nao clica em odds.
- Nao preenche stakes.
- Nao chama APIs externas.
- Nao atualiza banco SQLite.
- Nao altera watcher ou scheduler.

## Seguranca Read-Only

Esta camada trabalha apenas com arquivos locais em `outputs/`. Ela nao tem nenhuma funcao de place bet, place order, click, submit ou preenchimento automatico.
