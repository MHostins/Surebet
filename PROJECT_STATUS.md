# PROJECT STATUS - Surebet

Ultima atualizacao: 2026-06-17
Projeto: `C:\Projetos\Surebet`

## Objetivo Atual

Sistema Python read-only para comparar odds entre Betfair Exchange Brasil, Matchbook Brasil e, no fluxo multi-bookmaker mais recente, Pinnacle via The Odds API. O foco atual se divide entre o fluxo original de futebol `Match Odds` e o pivot multi-bookmaker para Moneyline/H2H em MMA, MLB e WNBA.

O projeto ainda nao executa apostas reais, nao envia Telegram e nao possui dashboard. Os fluxos de analise permanecem somente leitura e geram relatorios locais.

## Arquitetura Atual

```text
C:\Projetos\Surebet
  clients/
    betfair_client.py
    matchbook_client.py
    matchbook_br_client.py
    the_odds_api_client.py
  config/
    settings.py
    team_aliases.json
  docs/
    matchbook_f12_checklist.md
    matchbook_f12_findings.example.json
  services/
    alias_suggestion_service.py
    arbitrage_calculator.py
    comparison_service.py
    config_checker.py
    diagnostic_runner.py
    market_mapper.py
    opportunity_scanner.py
    multi_bookmaker_comparison_service.py
    odds_history_service.py
    report_generator.py
  outputs/
    diagnostic_report.json
    diagnostic.log
    comparison_report.json
    comparison_report.csv
    unpaired_events_betfair.csv
    unpaired_events_matchbook_br.csv
    suggested_team_aliases.json
    suggested_event_pairs.csv
    opportunities.json
    opportunities.csv
    matchbook_br_raw_sample.json
    matchbook_br_normalized_sample.json
  main.py
  .env
  .env.example
  README.md
  requirements.txt
```

## Comandos Disponiveis

```powershell
py main.py --mode check-config
py main.py --mode diagnostic --api betfair
py main.py --mode diagnostic --api matchbook
py main.py --mode diagnostic --api matchbook-br
py main.py --mode diagnostic --api both
py main.py --mode compare --api betfair-matchbook-br
py main.py --mode suggest-aliases
py main.py --mode scan-opportunities
py main.py --mode analyze-arbitrage
py main.py --mode watch
py main.py --mode moneyline-discovery
py main.py --mode compare-moneyline
py main.py --mode scan-moneyline-opportunities
py main.py --mode analyze-moneyline-arbitrage
py main.py --mode watch-moneyline
py main.py --mode odds-api-bookmakers
py main.py --mode odds-api-usage
py main.py --mode compare-multi-bookmakers
py main.py --mode watch-multi-bookmakers
py main.py
```

Observacao: `py main.py` ainda executa o fluxo legado de arbitragem simulada usando Betfair + Matchbook global. O fluxo operacional mais estavel no momento e `compare-multi-bookmakers` / `watch-multi-bookmakers`, que compara Matchbook BR x Pinnacle via The Odds API e respeita a auditoria de cota.

## Arquivos Principais

- `main.py`: roteamento dos modos CLI.
- `config/settings.py`: leitura de variaveis `.env`.
- `config/team_aliases.json`: aliases manuais para melhorar pareamento de times/selecoes.
- `clients/betfair_client.py`: login certificado Betfair Brasil e leitura REST read-only.
- `clients/matchbook_client.py`: cliente Matchbook global documentado. Atualmente falha por redirect regional.
- `clients/matchbook_br_client.py`: cliente experimental read-only para API regional `mexchange-api.matchbook.bet.br`.
- `services/diagnostic_runner.py`: diagnosticos por API.
- `services/comparison_service.py`: compara Betfair x Matchbook Brasil em `Match Odds`.
- `services/alias_suggestion_service.py`: sugere aliases a partir de eventos nao pareados, sem aplicar automaticamente.
- `services/opportunity_scanner.py`: scanner preliminar de discrepancias com filtros de confianca, liquidez e comissao.
- `clients/the_odds_api_client.py`: cliente read-only da The Odds API, com auditoria de consumo de creditos.
- `services/multi_bookmaker_comparison_service.py`: compara Matchbook BR x Pinnacle via The Odds API.
- `services/odds_history_service.py`: persistencia SQLite local em `outputs/odds_history.db`.
- `services/arbitrage_calculator.py`: calculadora antiga/simulada, ainda nao e o fluxo principal atual.

## Fluxo Multi-Bookmaker Atual

O pivot criado apos o bloqueio temporario da Betfair usa:

- Matchbook BR regional via `GET /api/events`, sem cookies.
- Pinnacle via The Odds API `/v4/sports/{sport}/odds`.
- Esportes configurados: MMA, MLB e WNBA.
- Mercado: H2H/Moneyline.
- Persistencia historica: `outputs/odds_history.db`.
- Auditoria de cota The Odds API: `outputs/the_odds_api_usage_history.jsonl`.

Comandos principais:

```powershell
py main.py --mode odds-api-bookmakers
py main.py --mode odds-api-usage
py main.py --mode compare-multi-bookmakers
py main.py --mode watch-multi-bookmakers
```

Resultados recentes observados em 2026-06-17:

- `multi_bookmaker_discrepancy_report.json`: `status=success`, `total_matchbook_rows=124`, `total_pinnacle_rows=74`, `paired_comparisons_count=48`.
- `multi_bookmaker_watch_history.jsonl`: 44 linhas validas, 44 ciclos `success`.
- `the_odds_api_usage_history.jsonl`: ultimo registro com `x-requests-used=165`, `x-requests-remaining=335`.
- `odds_history.db`: 8814 linhas, com `event_id` presente; fontes principais `matchbook-br` e `the-odds-api/pinnacle`.

## Configuracoes .env

Principais variaveis:

```env
BETFAIR_USERNAME=
BETFAIR_PASSWORD=
BETFAIR_APP_KEY=
BETFAIR_CERT_FILE=C:\Projetos\API-Betfair\certs\client.crt
BETFAIR_KEY_FILE=C:\Projetos\API-Betfair\certs\client.key
BETFAIR_API_BASE_URL=https://api.betfair.bet.br/exchange/betting/rest/v1.0
BETFAIR_CERT_LOGIN_URL=https://identitysso-cert.betfair.bet.br/api/certlogin
BETFAIR_COMMISSION=0.05

MATCHBOOK_USERNAME=
MATCHBOOK_PASSWORD=
MATCHBOOK_API_BASE_URL=https://api.matchbook.com
MATCHBOOK_COMMISSION=0.02

MATCHBOOK_BR_API_BASE_URL=https://mexchange-api.matchbook.bet.br
MATCHBOOK_BR_COOKIE=
MATCHBOOK_BR_COMMISSION=0.02

STAKE_TOTAL=100
MIN_ARBITRAGE_MARGIN=0.01
MAX_START_TIME_DELTA_MINUTES=90
MIN_EVENT_MATCH_CONFIDENCE=0.85
MIN_ODDS_DIFFERENCE_PERCENT=5
MIN_LIQUIDITY_BETFAIR=50
MIN_LIQUIDITY_MATCHBOOK_BR=50
TEAM_ALIASES_PATH=config/team_aliases.json
REQUEST_TIMEOUT=20
OUTPUT_DIR=outputs
```

Seguranca: `.env.example` deve manter placeholders. O `.env` real pode conter credenciais locais, mas nao deve ser compartilhado.

## Fluxo Betfair

Fluxo validado com base no projeto funcional `C:\Projetos\API-Betfair`.

- SSO: `https://identitysso-cert.betfair.bet.br/api/certlogin`
- Metodo: `POST`
- Payload: `application/x-www-form-urlencoded` com `username` e `password`
- Headers: `Accept: application/json`, `X-Application`, `Content-Type: application/x-www-form-urlencoded`
- Certificado: sim, par `.crt/.key`
- Token: guardado em memoria em `self.session_token`
- Chamada read-only: `listMarketCatalogue/`
- Chamada read-only: `listMarketBook/` em lotes de ate 40 mercados
- Mercados iniciais: `MATCH_ODDS` e `OVER_UNDER_25`

Resultado Betfair ja validado anteriormente:

- Autenticacao: `success`
- Eventos futuros: `101`
- Match Odds: `100`
- Over/Under 2.5: `100`
- Amostra com liquidez: presente
- Erros API: `[]`

## Fluxo Matchbook Global

Cliente: `clients/matchbook_client.py`

Fluxo implementado conforme documentacao global:

- Login: `POST https://api.matchbook.com/bpapi/rest/security/session`
- Token esperado: header `session-token`
- Eventos: `/edge/rest/events` com `include-prices=true`, `odds-type=DECIMAL`, `exchange-type=back-lay`

Resultado observado:

- A URL global redireciona para `https://matchbook.bet.br/b/exchange`
- O login global retorna HTML/redirect em vez de JSON com `session-token`
- Mantido apenas para referencia; nao e o fluxo regional funcional atual.

## Fluxo Matchbook Brasil

Cliente: `clients/matchbook_br_client.py`

Endpoint observado por F12 e validado em modo read-only:

```text
GET https://mexchange-api.matchbook.bet.br/api/events
```

Headers usados:

```text
accept: application/json
origin: https://mexchange.matchbook.bet.br
referer: https://mexchange.matchbook.bet.br/
```

Query inicial:

```text
offset=0
per-page=100
sort-by=start
sort-direction=asc
sport-ids=15
market-types=one_x_two,money_line,to_qualify
markets-limit=30
```

Cookies:

- O suporte atual nao usa cookie.
- `MATCHBOOK_BR_COOKIE` existe para experimento, mas o cliente atual nao deve salvar cookies reais no codigo.
- Ultima validacao funcional ocorreu com `cookie_sent=false`.

Normalizacao Matchbook Brasil:

- Evento: `event.name`
- Horario: `event.start`
- Mercado: `market.name` ou `market-type`
- Selecao: `runner.name`
- Odds: `runner.prices[].decimal-odds` ou `odds`
- Side: `runner.prices[].side`
- Liquidez: `runner.prices[].available-amount`

## Resultados Dos Diagnosticos

Ultimo `outputs/diagnostic_report.json` registrado para `matchbook-br`:

- Target: `matchbook-br`
- Status HTTP: `200`
- Content-Type: `application/json`
- Eventos: `100`
- Tem mercados: `true`
- Tem precos: `true`
- Odds normalizadas: `581`
- Mercados por tipo: `Match Odds: 100`, `To Qualify: 1`
- Cookie enviado: `false`
- Erros: `[]`

Arquivos de amostra gerados:

- `outputs/matchbook_br_raw_sample.json`
- `outputs/matchbook_br_normalized_sample.json`

## Resultados Do Compare

Comando:

```powershell
py main.py --mode compare --api betfair-matchbook-br
```

Ultimo resultado em `outputs/comparison_report.json`:

- Mercado: `Match Odds`
- `MIN_EVENT_MATCH_CONFIDENCE`: `0.85`
- Eventos Betfair: `99`
- Eventos Matchbook Brasil: `98`
- Eventos pareados: `31`
- Eventos nao pareados: `135`
- Selecoes pareadas: `144`
- Percentual de eventos pareados: `31.31%`
- Percentual de selecoes pareadas: `24.74%`

Arquivos gerados:

- `outputs/comparison_report.json`
- `outputs/comparison_report.csv`
- `outputs/unpaired_events_betfair.csv`
- `outputs/unpaired_events_matchbook_br.csv`

Pareamento:

- Remove acentos.
- Remove hifens.
- Padroniza `v`, `vs`, `x`.
- Remove espacos duplicados.
- Usa `config/team_aliases.json`.
- Gera `match_confidence` de `0` a `1`.

## Resultados Do Scanner

Comando:

```powershell
py main.py --mode scan-opportunities
```

Ultimo resultado em `outputs/opportunities.json`:

- Fonte: `outputs/comparison_report.json`
- Mercado: `Match Odds`
- Confianca minima: `0.90`
- Diferenca liquida minima: `5%`
- Liquidez minima Betfair: `50`
- Liquidez minima Matchbook BR: `50`
- Comissao Betfair: `0.05`
- Comissao Matchbook BR: `0.02`
- Selecoes comparadas: `144`
- Candidatos apos filtros: `7`

Top sinal atual:

- Evento: `Stromsgodset v Raufoss`
- Selecao: `The Draw`
- Side: `lay`
- Betfair odds: `8.4`
- Matchbook BR odds: `10.0`
- Betfair net odds: `8.03`
- Matchbook BR net odds: `9.82`
- Diferenca liquida: `22.291407%`
- Liquidez Betfair: `294.49`
- Liquidez Matchbook BR: `752.3676`
- `liquidity_status`: `ok`

Arquivos gerados:

- `outputs/opportunities.json`
- `outputs/opportunities.csv`

Importante: o scanner nao calcula stake, nao calcula surebet final e nao recomenda entrada. Ele apenas ranqueia discrepancias filtradas.

## Sugestao De Aliases

Comando:

```powershell
py main.py --mode suggest-aliases
```

Ultimo resultado:

- Pares de eventos sugeridos: `10`
- Aliases sugeridos: `14`
- Score minimo: `0.75`

Arquivos:

- `outputs/suggested_team_aliases.json`
- `outputs/suggested_event_pairs.csv`

Nada e aplicado automaticamente. Revise manualmente antes de copiar para `config/team_aliases.json`.

## Proximos Passos Recomendados

1. Revisar `outputs/suggested_team_aliases.json` e aplicar manualmente apenas aliases confiaveis em `config/team_aliases.json`.
2. Rodar novamente:

```powershell
py main.py --mode compare --api betfair-matchbook-br
py main.py --mode scan-opportunities
```

3. Melhorar pareamento de selecoes para clubes com prefixos/sufixos regionais, por exemplo `CA`, `FC`, `SK`, `IL`, nomes com cidade/estado.
4. Adicionar filtro de evento ao vivo: a Matchbook BR retornou eventos com `in-running-flag`; decidir se o fluxo inicial deve excluir ao vivo para ficar alinhado com Betfair.
5. Criar um relatorio de auditoria por oportunidade com origem dos dados e timestamp de coleta.
6. Depois, e somente depois, desenhar calculo de surebet completo com stake simulada, comissoes, liquidez e limites.
7. Telegram/dashboard devem vir depois da estabilidade dos dados e do pareamento.

## Restricoes De Seguranca

- Nao implementar apostas reais.
- Nao implementar `placeBet`, `placeOrder`, `placeInstruction`, `sendOrder`, `place_orders` ou similares.
- Nao calcular ou enviar ordens.
- Nao salvar cookies reais em codigo.
- Nao imprimir senhas, tokens, app keys completas ou cookies completos.
- `.env` real deve permanecer local.
- O fluxo Matchbook BR atual deve continuar read-only.
- O scanner atual nao calcula stake e nao calcula surebet final.
- Telegram e dashboard ainda nao devem ser adicionados antes de validar dados/pareamento.

## Validacao Tecnica Recente

Compilacao usada recorrentemente:

```powershell
py -m py_compile main.py clients\betfair_client.py clients\matchbook_client.py clients\matchbook_br_client.py config\settings.py services\market_mapper.py services\arbitrage_calculator.py services\comparison_service.py services\alias_suggestion_service.py services\opportunity_scanner.py services\config_checker.py services\diagnostic_runner.py services\report_generator.py
```

Busca de seguranca usada:

```powershell
rg -n "def .*place|place_bet|place_order|place_instruction|send_order|execute_bet|bet_instruction|placeBet|placeOrder|placeInstruction|sendOrder|place_orders|place_instruction" C:\Projetos\Surebet\clients C:\Projetos\Surebet\services C:\Projetos\Surebet\main.py C:\Projetos\Surebet\README.md C:\Projetos\Surebet\docs
```

A busca so encontrou termos proibidos em secoes documentais de seguranca do README.
