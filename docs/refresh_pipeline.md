# Refresh Pipeline Manual

## Objetivo

O Refresh Pipeline Manual executa, em uma unica chamada, a cadeia analitica local que transforma o ultimo relatorio de discrepancias em oportunidades calculadas, revisao de qualidade e alertas.

Ele e exclusivamente read-only. Nao chama APIs externas, nao coleta odds novas, nao altera watcher, nao altera scheduler, nao grava em `odds_history.db` e nao executa apostas.

## Comando

```powershell
py main.py --mode refresh-pipeline
```

## Etapas Executadas

O fluxo roda sempre nesta ordem:

```text
OpportunityEngineService
OpportunityQualityReviewService
OpportunityAlertService
```

Cada etapa usa apenas arquivos existentes em `outputs/`.

## Arquivos de Entrada

Principal entrada:

```text
outputs/multi_bookmaker_discrepancy_report.json
```

Os servicos tambem podem ler arquivos locais gerados por etapas anteriores, como:

```text
outputs/calculated_opportunities.json
outputs/opportunity_quality_review.json
outputs/opportunity_watch_history.jsonl
```

## Arquivos Gerados

O pipeline atualiza:

```text
outputs/calculated_opportunities.json
outputs/calculated_opportunities.csv
outputs/opportunity_quality_review.json
outputs/opportunity_quality_review.csv
outputs/opportunity_alerts.json
outputs/opportunity_alerts.csv
outputs/latest_pipeline_summary.json
outputs/pipeline_refresh_history.jsonl
```

`pipeline_refresh_history.jsonl` e append-only.

## Summary

`latest_pipeline_summary.json` contem:

```json
{
  "timestamp": "...",
  "candidates": 0,
  "supported": 0,
  "surebets": 0,
  "alerts": 0,
  "near_misses": 0,
  "best_roi_percent": null,
  "best_event": null
}
```

## Robustez

Se algum arquivo esperado estiver ausente ou invalido, os servicos retornam relatorios vazios quando possivel. Falhas inesperadas em uma etapa sao registradas como warnings no resultado do pipeline, e as demais etapas ainda sao tentadas.

## Limitacoes

- Nao atualiza odds.
- Nao chama Matchbook, Pinnacle, Betfair, The Odds API ou SureBet.com.
- Nao inicia watcher.
- Nao integra novas casas.
- Nao calcula Middles.
- Nao envia Telegram.
- Nao altera layout da dashboard.

## Segurança Read-only

Esta fase nao contem nenhum metodo de aposta, clique, preenchimento de stake, envio de ordem ou abertura de casa externa. Ela apenas orquestra calculos locais e grava relatorios analiticos em `outputs/`.
