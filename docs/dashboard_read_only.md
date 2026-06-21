# Dashboard Read-Only

## Objetivo

A Fase 3.5 adiciona uma dashboard local em Streamlit para visualizar alertas, oportunidades calculadas e historico. Ela e uma camada de leitura: nao chama APIs externas, nao executa watcher, nao recalcula oportunidades e nao altera arquivos.

## Arquivos Lidos

```text
outputs/opportunity_alerts.json
outputs/opportunity_alerts.csv
outputs/opportunity_alert_history.jsonl
outputs/opportunity_quality_review.json
outputs/calculated_opportunities.json
```

Se algum arquivo estiver ausente, vazio ou invalido, a dashboard mostra um aviso amigavel no painel "Estado dos arquivos".

## Comando de Execucao

```powershell
streamlit run dashboard_app.py
```

Execute esse comando na raiz do projeto:

```text
C:\Projetos\Surebet
```

## O Que A Dashboard Mostra

Painel principal:

- `total_alerts`
- `total_surebet_alerts`
- `total_near_miss_alerts`
- `best_roi_percent`
- `best_event`
- `closest_distance_to_surebet_percent`

Tabelas:

- surebets;
- near-misses;
- historico de alertas por execucao.

Filtros:

- sport;
- alert_type;
- bookmaker_pair.

## Limitacoes

- Nao atualiza dados automaticamente.
- Nao executa o watcher.
- Nao executa calculos.
- Nao chama Matchbook, Pinnacle, Novibet, Betfair ou qualquer API externa.
- Nao grava historico.
- Nao envia Telegram.
- Nao abre links de casas.

## Seguranca Read-Only

A dashboard nao possui botoes de aposta, botoes de ordem, botoes de clique em bookmaker, preenchimento de stake ou qualquer automacao operacional. Ela apenas le arquivos locais ja gerados por modos anteriores.

## Proximos Passos

Depois de observar alguns ciclos de `opportunity_alert_history.jsonl`, a dashboard pode ajudar a decidir:

- quais metricas merecem destaque;
- se vale adicionar graficos;
- se alertas por Telegram fazem sentido;
- quais esportes e pares de casas devem virar foco operacional.
