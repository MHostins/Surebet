# Reavaliacao Tecnica - 2026-06-17

## Contexto

O projeto foi continuado pelo Antigravity apos a restricao operacional no Codex. A arquitetura atual contem o fluxo original Betfair x Matchbook BR e um pivot multi-bookmaker mais recente usando Matchbook BR x Pinnacle via The Odds API.

Tudo permanece read-only. Nao foram encontrados metodos de envio de aposta real no codigo de `clients/`, `services/` ou `main.py`.

## Estado Atual Observado

- `py_compile` passa em todos os arquivos principais.
- `py main.py --mode check-config` retorna `CONFIG_STATUS: ok`.
- `py main.py --mode odds-api-usage` le apenas historico local e nao consome creditos.
- `outputs/multi_bookmaker_watch_history.jsonl`: 44 ciclos validos, todos `success`.
- `outputs/multi_bookmaker_discrepancy_report.json`: ultimo resultado com 124 linhas Matchbook BR, 74 linhas Pinnacle e 48 selecoes pareadas.
- `outputs/the_odds_api_usage_history.jsonl`: ultimo estado com 165 creditos usados e 335 restantes.
- `outputs/odds_history.db`: 8814 linhas historicas, com coluna `event_id` presente.

## Correcoes Aplicadas

1. `services/multi_bookmaker_comparison_service.py`
   - Corrigida a leitura de `outputs/the_odds_api_bookmakers.json`.
   - O codigo agora le corretamente `bookmakers_found` antes de verificar se `pinnacle` aparece como suportada.

2. `main.py`
   - `scan-moneyline-opportunities`, `analyze-moneyline-arbitrage` e `watch-moneyline` passaram a respeitar:
     - `MIN_ODDS_DIFFERENCE_PERCENT`
     - `MIN_LIQUIDITY_BETFAIR`
     - `MIN_LIQUIDITY_MATCHBOOK_BR`
   - O historico novo de `watch-moneyline` agora grava `schema_version=2`.
   - Mantidos aliases de compatibilidade:
     - `total_moneyline_comparisons`
     - `best_cross_exchange_gap`

3. `.env.example`
   - Adicionadas variaveis de loop que ja existiam no `settings.py`:
     - `WATCH_MONEYLINE_INTERVAL_SECONDS`
     - `WATCH_MONEYLINE_MAX_CYCLES`
     - `WATCH_INTERVAL_SECONDS`
     - `WATCH_MAX_CYCLES`

4. `README.md`
   - Corrigida a documentacao do scanner moneyline para citar os nomes reais de configuracao.
   - Corrigida a documentacao do `watch-moneyline` para usar `WATCH_MONEYLINE_*`.
   - Corrigida a documentacao de `odds-api-bookmakers`: o fluxo atual nao usa `/v4/bookmakers`; ele consulta `/v4/sports/{sport}/odds` e extrai `event["bookmakers"]`.

5. `PROJECT_STATUS.md`
   - Atualizado para refletir o pivot multi-bookmaker e os resultados recentes.

6. `docs/multi_bookmaker_implementation_plan.md`
   - Atualizado para nao orientar o uso futuro do endpoint `/v4/bookmakers`.

## Riscos Ainda Abertos

- `main.py` esta grande demais e concentra muitos modos CLI; futuras mudancas deveriam extrair cada modo para comandos/servicos dedicados.
- O pareamento multi-bookmaker ainda depende de similaridade textual e horario. Mesmo com `matching_audit_report.json`, discrepancias altas devem ser auditadas manualmente.
- The Odds API tem cota limitada. Evitar rodar `compare-multi-bookmakers` em loop curto sem checar `odds-api-usage`.
- O fluxo Betfair ainda pode sofrer indisponibilidade por lockout/credenciais, entao o pivot multi-bookmaker e o caminho mais estavel no momento.

## Proximos Passos Recomendados

1. Criar um modo offline para analisar `outputs/odds_history.db` sem consumir APIs.
2. Criar relatorio de qualidade de pareamento por esporte no fluxo multi-bookmaker.
3. Persistir tambem os pares aceitos/rejeitados em tabela SQLite separada.
4. Extrair os modos de `main.py` para modulos em `services/commands/`.
5. Criar testes unitarios para normalizacao de nomes, pareamento e calculo de comissao.
6. Manter a restricao: nada de apostas reais, envio de ordens, cookies reais em codigo ou impressao de segredos.
