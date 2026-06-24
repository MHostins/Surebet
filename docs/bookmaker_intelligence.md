# Bookmaker Intelligence Layer

## Objetivo

A Fase 3.7 gera inteligência operacional a partir do banco SQLite do Bookmaker Discovery.

Ela é read-only sobre:

```text
outputs/bookmaker_discovery/bookmaker_discovery.db
```

Não interfere no Discovery, Opportunity Engine, Alert Layer, Dashboard, watchers ou scheduler.

## Comando

```powershell
py main.py --mode bookmaker-intelligence
```

Launcher opcional:

```powershell
py scripts\run_bookmaker_intelligence.py
```

## Saídas

Os relatórios são gerados em:

```text
outputs/bookmaker_intelligence/
```

Arquivos:

- `bookmaker_intelligence_report.json`
- `bookmaker_by_sport.csv`
- `bookmaker_by_market.csv`
- `bookmaker_by_hour.csv`
- `bookmaker_pair_strength.csv`
- `bookmaker_consistency.csv`
- `bookmaker_context_notes.json`

## Métricas

### Ranking por esporte

- bookmaker
- sport
- appearances
- unique_opportunities
- avg_profit_percent
- max_profit_percent

### Ranking por mercado

- bookmaker
- market_family
- appearances
- unique_opportunities
- avg_profit_percent
- max_profit_percent

### Ranking por horário

- hour_bucket
- bookmaker
- appearances
- avg_profit_percent
- max_profit_percent

### Força dos pares

- bookmaker_pair
- appearances
- unique_opportunities
- avg_profit_percent
- max_profit_percent
- persistence_score

`persistence_score` usa `seen_count` dividido pela quantidade de oportunidades únicas do par.

### Consistência por bookmaker

- appearances
- unique_opportunities
- avg_profit_percent
- median_profit_percent
- p95_profit_percent
- max_profit_percent
- active_span_hours
- consistency_score

## Market Family

Classificação simples por palavras-chave:

- `over_under`
- `handicap`
- `dnb`
- `match_winner`
- `player_props`
- `sets_games`
- `corners_throwins_cards`
- `other`

## Contexto Esportivo

O relatório registra a observação:

> Os dados coletados durante a Copa do Mundo devem ser interpretados com cautela, pois as principais ligas de futebol estão paralisadas, alterando a distribuição normal de esportes, mercados e oportunidades.

## Robustez

Se o banco não existir ou estiver vazio, os relatórios são gerados vazios sem quebrar.

## Segurança

Esta fase não chama APIs externas, não coleta novas odds, não abre navegador e não executa apostas. Ela apenas lê o SQLite local e grava relatórios analíticos.
