# Comparador de Odds Betfair x Matchbook

Projeto Python para comparar odds entre Betfair Exchange API e Matchbook API, com foco exclusivo em leitura de dados e simulacao de surebets.

Esta versao e segura por padrao: nao existe funcao de aposta real, criacao de ordem, `place bet`, `place order`, `place instruction`, `send order` ou similares.

## Estrutura

```text
clients/
  betfair_client.py
  matchbook_client.py
services/
  market_mapper.py
  arbitrage_calculator.py
  config_checker.py
  diagnostic_runner.py
  report_generator.py
config/
  settings.py
docs/
  matchbook_f12_checklist.md
  matchbook_f12_findings.example.json
main.py
.env.example
requirements.txt
README.md
```

## Fluxo Betfair

A autenticacao Betfair foi alinhada ao projeto funcional `C:\Projetos\API-Betfair`.

- SSO em uso: `https://identitysso-cert.betfair.bet.br/api/certlogin`
- Metodo: `POST`
- Payload: form-urlencoded com `username` e `password`
- Headers: `Accept: application/json`, `X-Application: <app key>`, `Content-Type: application/x-www-form-urlencoded`
- Certificado: sim, usando `BETFAIR_CERT_FILE` e `BETFAIR_KEY_FILE`
- Token: armazenado em memoria em `self.session_token` e enviado como `X-Authentication`
- Chamadas read-only: `listMarketCatalogue/` e `listMarketBook/` no REST Brasil

## Matchbook Brasil

O cliente Matchbook atual segue a API global documentada:

- Login: `POST https://api.matchbook.com/bpapi/rest/security/session`
- Header esperado apos login: `session-token: <token>`
- Eventos/odds: `include-prices=true`, `odds-type=DECIMAL`, `exchange-type=back-lay`

No diagnostico local, a URL global pode redirecionar para `https://matchbook.bet.br/b/exchange`, indicando que a Matchbook Brasil pode usar um fluxo regional diferente da API global publica.

Na investigacao F12, apareceu uma chamada regional de eventos semelhante a:

```text
GET https://mexchange-api.matchbook.bet.br/api/events?offset=0&per-page=100&sort-by=start&sort-direction=asc&sport-ids=...&market-types=one_x_two,money_line,to_qualify&before=...&markets-limit=30
```

Essa chamada retornou `200 OK` com `Content-Type: application/json` no navegador. O suporte experimental `matchbook-br` usa esse endpoint apenas em modo read-only, sem cookies, e transforma `events -> markets -> runners -> prices` no formato comum do projeto.

Para diagnosticar e gerar amostras:

```powershell
py main.py --mode diagnostic --api matchbook-br
```

Arquivos gerados pelo diagnostico regional:

```text
outputs/diagnostic_report.json
outputs/diagnostic.log
outputs/matchbook_br_raw_sample.json
outputs/matchbook_br_normalized_sample.json
```

O relatorio regional informa `normalized_odds_count`, `markets_by_type` e `first_10_normalized_odds`. Antes de usar esses dados em comparacao automatica, revise a checklist manual em [docs/matchbook_f12_checklist.md](docs/matchbook_f12_checklist.md) e uma copia preenchida de [docs/matchbook_f12_findings.example.json](docs/matchbook_f12_findings.example.json).

## Instalacao

```powershell
cd C:\Projetos\Surebet
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Configuracao do .env

Copie o arquivo de exemplo:

```powershell
Copy-Item .env.example .env
```

Preencha as variaveis obrigatorias:

```env
BETFAIR_USERNAME=
BETFAIR_PASSWORD=
BETFAIR_APP_KEY=
BETFAIR_CERT_FILE=C:\Projetos\API-Betfair\certs\client.crt
BETFAIR_KEY_FILE=C:\Projetos\API-Betfair\certs\client.key
MATCHBOOK_USERNAME=
MATCHBOOK_PASSWORD=
MATCHBOOK_API_BASE_URL=https://api.matchbook.com
```

Tambem e aceito o formato legado em uma unica variavel:

```env
BETFAIR_CERT_PATH=C:\caminho\client.crt,C:\caminho\client.key
```

Endpoints Betfair Brasil padrao:

```env
BETFAIR_API_BASE_URL=https://api.betfair.bet.br/exchange/betting/rest/v1.0
BETFAIR_CERT_LOGIN_URL=https://identitysso-cert.betfair.bet.br/api/certlogin
```

## Validar configuracao local

Antes de chamar qualquer API, rode:

```powershell
py main.py --mode check-config
```

Esse comando nao faz chamada externa. Ele verifica variaveis obrigatorias, mascara senhas e app keys, valida certificados e cria `OUTPUT_DIR` se a pasta ainda nao existir.

## Rodar diagnostico

O modo diagnostico e 100% read-only. Ele autentica, consulta eventos futuros de futebol e gera um resumo da qualidade inicial dos dados.

Diagnostico somente Betfair:

```powershell
py main.py --mode diagnostic --api betfair
```

Diagnostico somente Matchbook:

```powershell
py main.py --mode diagnostic --api matchbook
```

Diagnostico das duas APIs:

```powershell
py main.py --mode diagnostic --api both
```

Arquivos gerados:

```text
outputs/diagnostic_report.json
outputs/diagnostic.log
```

## Interpretar o diagnostic_report.json

Cada exchange aparece dentro de `exchanges` com os seguintes campos:

- `authentication_status`: `success` ou `failed`. Se falhar, veja `api_errors` e `outputs/diagnostic.log`.
- `response_time_seconds`: tempo total da autenticacao e consulta inicial.
- `future_events_found`: quantidade de eventos futuros de futebol encontrados.
- `match_odds_markets`: quantidade de mercados Match Odds encontrados.
- `over_under_25_markets`: quantidade de mercados Over/Under 2.5 Goals encontrados.
- `sample_events`: amostra de ate 10 eventos com nome e horario.
- `sample_odds_with_liquidity`: amostra de ate 10 odds normalizadas com liquidez maior que zero.
- `api_errors`: erros capturados durante autenticacao ou chamadas HTTP/API.


## Comparacao Inicial Betfair x Matchbook Brasil

Para comparar odds normalizadas das duas fontes, apenas em `Match Odds`, rode:

```powershell
py main.py --mode compare --api betfair-matchbook-br
```

Esse modo e read-only e ainda nao calcula surebet final. Ele gera um relatorio de discrepancias com:

- total de eventos Betfair;
- total de eventos Matchbook Brasil;
- eventos pareados;
- eventos nao pareados;
- selecoes pareadas;
- maior diferenca de odds por selecao;
- percentual de eventos pareados;
- percentual de selecoes pareadas;
- 20 melhores pares por confianca;
- 20 piores pares aceitos.

Arquivos gerados:

```text
outputs/comparison_report.json
outputs/comparison_report.csv
outputs/unpaired_events_betfair.csv
outputs/unpaired_events_matchbook_br.csv
```

O pareamento usa nomes dos times e horario de inicio, respeitando `MAX_START_TIME_DELTA_MINUTES`. A normalizacao remove acentos, hifens, espacos duplicados e padroniza `v`, `vs` e `x`. Aliases manuais ficam em `config/team_aliases.json` e podem ser trocados por `TEAM_ALIASES_PATH`.

Configuracoes relevantes:

```env
MAX_START_TIME_DELTA_MINUTES=90
MIN_EVENT_MATCH_CONFIDENCE=0.85
TEAM_ALIASES_PATH=config/team_aliases.json
```

## Sugerir Aliases

Depois de rodar a comparacao, os eventos nao pareados ficam em:

```text
outputs/unpaired_events_betfair.csv
outputs/unpaired_events_matchbook_br.csv
```

Para sugerir aliases automaticamente, sem aplicar nada no arquivo oficial, rode:

```powershell
py main.py --mode suggest-aliases
```

Esse modo compara eventos nao pareados por horario proximo, similaridade textual e nomes parciais dos clubes. Apenas sugestoes com score `>= 0.75` sao salvas.

Arquivos gerados:

```text
outputs/suggested_team_aliases.json
outputs/suggested_event_pairs.csv
```

Revise manualmente as sugestoes antes de copiar qualquer alias para `config/team_aliases.json`.

## Scanner de Oportunidades

Depois de rodar a comparacao Betfair x Matchbook Brasil, use o scanner para listar discrepancias relevantes em `Match Odds`:

```powershell
py main.py --mode scan-opportunities
```

Esse modo usa `outputs/comparison_report.json`, considera apenas eventos pareados com `match_confidence >= 0.90`, aplica liquidez minima por fonte e compara odds liquidas aproximadas apos comissao.

Configuracoes principais:

```env
MIN_ODDS_DIFFERENCE_PERCENT=5
MIN_LIQUIDITY_BETFAIR=50
MIN_LIQUIDITY_MATCHBOOK_BR=50
BETFAIR_COMMISSION=0.05
MATCHBOOK_BR_COMMISSION=0.02
```

Arquivos gerados:

```text
outputs/opportunities.json
outputs/opportunities.csv
```

O ranking mostra as Top 50 maiores diferencas percentuais liquidas com evento, selecao, odds brutas, odds liquidas, diferenca percentual liquida, liquidez em cada fonte e `liquidity_status`.

Este scanner nao calcula stake, nao calcula arbitragem final, nao envia Telegram, nao cria dashboard e nao executa apostas.

## Pré-Cálculo de Arbitragem e Diagnóstico de Gap

Depois de rodar o scanner de oportunidades, use o modo `analyze-arbitrage` para avaliar se as discrepâncias encontradas podem formar uma arbitragem teórica entre Back e Lay (sem calcular stake exata ou sugerir valores de aposta) e diagnosticar o "gap" para aquelas que ainda não são arbitragem:

```powershell
py main.py --mode analyze-arbitrage
```

Esse modo carrega `outputs/opportunities.json` e busca as odds correspondentes do lado oposto no `comparison_report.json` para realizar a avaliação:
- **Para oportunidades do tipo `back`:** Busca o `lay` menor na outra fonte e compara se `back_net_odds > lay_net_odds`.
- **Para oportunidades do tipo `lay`:** Busca o `back` maior na outra fonte e compara se `back_net_odds > lay_net_odds`.

### Métricas Calculadas
- **`arbitrage_score`**: Margem percentual teórica líquida de lucro (apenas quando `back_net_odds > lay_net_odds`):
$$\text{arbitrage\_score} = \left( \frac{\text{back\_net\_odds}}{\text{lay\_net\_odds}} - 1 \right) \times 100$$
- **`gap_to_arbitrage`**: Diferença absoluta necessária para atingir a paridade: `current_lay_net_odds - current_back_net_odds`.
- **`gap_to_arbitrage_percent`**: Percentual que falta para a odd de Back atingir a odd de Lay:
$$\text{gap\_to\_arbitrage\_percent} = \left( \frac{\text{current\_lay\_net\_odds}}{\text{current\_back\_net\_odds}} - 1 \right) \times 100$$
- Se as odds líquidas calculadas forem inválidas ($\le 0$), a oportunidade é marcada com o motivo `invalid_net_odds` e o gap não é calculado.

### Relatórios e Rankings
O sistema gera dois relatórios na pasta de saídas:
1. **Relatório Geral (`outputs/arbitrage_analysis.json` e `.csv`)**: Lista completa das oportunidades avaliadas.
2. **Relatório de Diagnóstico de Gap (`outputs/arbitrage_gap_report.json` e `.csv`)**: Ranking `closest_to_arbitrage` ordenado pelo menor `gap_to_arbitrage_percent` (as mais próximas de se tornarem arbitragem vêm no topo). Inclui informações de suporte para avaliação posterior, tais como `raw_back_odd`, `raw_lay_odd`, liquidez e `match_confidence`.

Nesta etapa, nenhum cálculo de stake, responsabilidade financeira ou simulação de aposta real é realizado.

## Modo de Observação Contínua (Watch)

Para monitorar continuamente as exchanges e observar se alguma oportunidade vira ou se aproxima de uma arbitragem teórica ao longo do tempo, use o modo `watch`:

```powershell
py main.py --mode watch
```

Esse modo executa as etapas de comparação, varredura de oportunidades e análise de arbitragem em ciclos contínuos de execução.

### Configurações Relacionadas
As seguintes configurações no `.env` (ou variáveis de ambiente) controlam o comportamento do loop:
- `WATCH_INTERVAL_SECONDS`: Tempo de espera (em segundos) entre o término de um ciclo e o início do próximo (padrão `300`).
- `WATCH_MAX_CYCLES`: Número máximo de ciclos de execução. Se definido como `0`, o loop rodará indefinidamente (padrão `0`).

### Proteções e Resiliência
- **Erros isolados por ciclo**: Se ocorrer uma falha de conexão ou erro de API em um ciclo, o erro será registrado no log e no histórico, mas o programa continuará rodando normalmente para o ciclo seguinte.
- **Encerramento Limpo**: Você pode finalizar a observação a qualquer momento usando a combinação de teclas `Ctrl+C`. O programa intercepta a interrupção e finaliza de forma limpa.

### Histórico de Observação
A cada ciclo concluído (com sucesso ou falha), o sistema adiciona uma linha com os resultados agregados em formato JSON Lines no arquivo:
```text
outputs/watch_history.jsonl
```

Cada entrada contém informações sobre a execução do ciclo (`cycle_number`, `started_at`, `finished_at`, `duration_seconds`, `status`, `error_message`) e métricas da melhor oportunidade avaliada (`best_gap_to_arbitrage_percent`, `best_event`, `best_selection`, etc.).

## Rodar simulacao de arbitragem

```powershell
py main.py
```

Esse modo compara as odds normalizadas, procura possiveis combinacoes `back` x `lay`, imprime oportunidades simuladas no terminal e salva relatorios em:

```text
outputs/surebets_YYYYMMDD_HHMMSS.json
outputs/surebets_YYYYMMDD_HHMMSS.csv
```

## Descoberta de Esportes e Mercados (Market Discovery)

Para catalogar todos os esportes, tipos de mercado e seleções ativas que as exchanges oferecem, use o modo `market-discovery`:

```powershell
py main.py --mode market-discovery
```

Esse modo é 100% read-only, não calcula arbitragem e não realiza apostas. Ele consulta os catálogos globais e eventos futuros para mapear a oferta das plataformas.

Arquivos gerados:
- **`outputs/sports_catalog.json`**: Mapeamento de esportes disponíveis, contendo ID do esporte, nome, contagem de eventos ativos observados, tipos de mercado identificados e total de seleções (runners).
- **`outputs/market_types_catalog.json`**: Lista de tipos de mercado disponíveis em cada exchange com a respectiva contagem de mercados ativos.

## Descoberta de Mercados Matchbook Brasil (Matchbook Market Discovery)

Para realizar uma varredura aprofundada dos esportes, eventos, mercados e seleções oferecidos especificamente na API regional da Matchbook Brasil (sem utilizar cookies, apostar ou enviar alertas), use o modo `matchbook-market-discovery`:

```powershell
py main.py --mode matchbook-market-discovery
```

Esse modo mapeia a árvore de navegação completa e consulta os eventos de cada esporte individualmente.

Arquivos gerados:
- **`outputs/matchbook_navigation_tree.json`**: Árvore estruturada de navegação completa retornada pelo endpoint `/api/navigation`.
- **`outputs/matchbook_sports_catalog.json`**: Lista com todos os esportes identificados, trazendo o ID do esporte, nome do esporte, total de eventos ativos, total de mercados, contagem de seleções e lista de tipos de mercado encontrados.
- **`outputs/matchbook_market_catalog.json`**: Mapeamento completo e aninhado por Esporte -> Evento -> Mercado -> Seleções ativas.
- **`outputs/matchbook_market_types_summary.json`**: Resumo de contagem global de mercados por tipo de mercado (ex.: `one_x_two`, `money_line`, `outright`, etc.).

## Descoberta e Pareamento de Moneyline (Moneyline Discovery)

Para avaliar a compatibilidade de pareamento entre os mercados regionais de `money_line` da Matchbook Brasil e os mercados equivalentes `MATCH_ODDS` da Betfair Exchange para esportes além do futebol (Tênis, Basquete, Beisebol, MMA e Futebol Americano), rode:

```powershell
py main.py --mode moneyline-discovery
```

Esse modo é 100% read-only, não realiza apostas, não calcula arbitragem e não envia alertas. Ele busca todos os eventos de `money_line` ativos na Matchbook Brasil para os esportes configurados, consulta os equivalentes na Betfair e realiza o pareamento por nome e horário de início.

### Comportamento e Proteções
- **Estrutura Extensível**: A estrutura de mapeamento de esportes é modular e configurável na classe `MoneylineDiscoveryService`, facilitando a inclusão de futebol ou outros esportes futuramente.
- **Registro de Anomalias/Notas**: Caso a Betfair não retorne mercados para algum esporte (o que pode sugerir a necessidade de testar outros códigos como `MONEY_LINE`, `WINNER`, ou `MATCH_ODDS_LO_TIE`), o relatório grava um aviso no campo `notes` do esporte.

### Arquivos Gerados
- **`outputs/moneyline_pairing_report.json`**: Contém o resumo por esporte, a lista detalhada de eventos pareados com seu grau de confiança (`match_confidence`), e listas de eventos de ambas as plataformas que não puderam ser pareados (útil para identificação de novos aliases).

## Comparação de Odds Moneyline (Moneyline Comparison)

Para comparar as odds de `money_line` da Matchbook BR contra os mercados equivalentes na Betfair para esportes com alto índice de pareamento (Basquete, Beisebol e MMA), rode:

```powershell
py main.py --mode compare-moneyline
```

Esse modo é 100% read-only, não realiza apostas, não calcula arbitragem e não envia alertas. Ele carrega os eventos pareados gerados pela etapa de descoberta e extrai as odds e a liquidez atualizadas em tempo real nas duas plataformas para cada runner.

### Comportamento e Proteções
- **Autogeração do Relatório**: Se o arquivo `outputs/moneyline_pairing_report.json` estiver ausente ou tiver sido gerado há mais de 1 hora, o sistema automaticamente executa a etapa de descoberta antes de prosseguir com a comparação.
- **Escopo Inicial Rígido**: Apenas Basquete, Beisebol e MMA são processados nesta etapa. Tênis e Futebol Americano permanecem fora de escopo.

### Arquivos Gerados
- **`outputs/moneyline_comparison_report.json`**: Detalhamento em formato JSON de todas as seleções comparadas.
- **`outputs/moneyline_comparison_report.csv`**: Tabela em CSV contendo os campos: `sport_name`, `market_type`, `event_name_matchbook`, `event_name_betfair`, `start_time_matchbook`, `start_time_betfair`, `selection_matchbook`, `selection_betfair`, `side`, `odd_matchbook`, `odd_betfair`, `liquidity_matchbook`, `liquidity_betfair`, `absolute_difference`, `percentage_difference`, `event_pair_confidence` e `selection_match_confidence`.

## Scanner de Oportunidades Moneyline (Moneyline Opportunity Scanner)

Para filtrar discrepâncias de odds qualificadas em mercados `money_line` (Basquete, Beisebol e MMA) aplicando filtros de liquidez e discrepância percentual, rode:

```powershell
py main.py --mode scan-moneyline-opportunities
```

Esse modo é 100% read-only, não realiza apostas, não calcula arbitragem e não envia alertas. Ele carrega os dados brutos de `moneyline_comparison_report.json` e filtra apenas os runners que possuem:
- Diferença de odds bruta mínima configurada em `MIN_ODDS_DIFFERENCE_PERCENT`
- Liquidez disponível na Betfair configurada em `MIN_LIQUIDITY_BETFAIR`
- Liquidez disponível na Matchbook BR configurada em `MIN_LIQUIDITY_MATCHBOOK_BR`

As oportunidades filtradas são ordenadas de forma decrescente pela diferença líquida percentual pós-comissão (`net_difference_percent`).

### Comportamento e Proteções
- **Autogeração em Cadeia**: Se o relatório de comparação estiver ausente/stale, ele é recalculado, o que por sua vez aciona a autogeração do relatório de pareamento se este também estiver em falta.
- **Cálculo de Odds Líquidas Estimadas**: Para fins informativos, o scanner estima o retorno líquido utilizando a comissão de cada exchange. A fórmula aplicada é:
  `net_odds = 1 + (odds - 1) * (1 - commission)`
  > [!NOTE]
  > Esse cálculo é uma estimativa simplificada do retorno líquido de Back para comparação direta. Esta etapa **ainda não realiza o cálculo real de arbitragem teórica Back/Lay** (surebet de duas pontas), o qual será introduzido em etapas futuras.

### Arquivos Gerados
- **`outputs/moneyline_opportunities.json`**: JSON estruturado com metadados do scan e a lista ordenada de oportunidades filtradas.
- **`outputs/moneyline_opportunities.csv`**: CSV contendo os mesmos campos ordenados, incluindo `better_source`, `worse_source`, `betfair_net_odds`, `matchbook_net_odds`, `net_difference_percent`, além dos graus de confiança (`selection_match_confidence` e `event_pair_confidence`).

## Análise de Arbitragem Moneyline (Moneyline Arbitrage Analyzer)

Para avaliar se as oportunidades filtradas de moneyline podem formar arbitragem teórica de duas pontas (Back/Lay) entre a Betfair e a Matchbook BR, rode:

```powershell
py main.py --mode analyze-moneyline-arbitrage
```

Esse modo é 100% read-only, não calcula stakes ou sugere valores de apostas e não envia ordens. Ele cruza cada oportunidade do scanner com as odds do lado oposto no relatório de comparação completo para estimar a arbitragem líquida matemática.

### Restrição Cross-Exchange (Arbitragem entre Diferentes Plataformas)
A arbitragem buscada deve ser obrigatoriamente **cross-exchange** (entre exchanges diferentes).
- Se `back_source == lay_source` (por exemplo, ambas as pontas na Betfair), a oportunidade **não** é considerada uma arbitragem cross-exchange válida.
- Nesses casos, a oportunidade é classificada como `possible_arbitrage = False` com o motivo (`reason`) `"same_source_back_lay_not_cross_exchange_arbitrage"`.

### Matemática da Arbitragem Líquida (Back/Lay)
Para a seleção/runner avaliada:
- **Odds Líquidas de Back (`back_net_odds`)**: Escolhe a maior odd líquida de Back disponível entre as exchanges:
  `back_net_odds = 1.0 + (raw_back_odd - 1.0) * (1.0 - commission)`
- **Odds Líquidas de Lay (`lay_net_odds`)**: Escolhe a menor odd líquida de Lay disponível (liability multiplier) entre as exchanges:
  `lay_net_odds = 1.0 + (raw_lay_odd - 1.0) / (1.0 - commission)`
- **Condição de Arbitragem**: Um sinal de arbitragem teórica existe se:
  `back_net_odds > lay_net_odds` e `back_source != lay_source` (cross-exchange).
  Nesse caso, a margem de lucro estimada (`arbitrage_score`) é:
  `arbitrage_score = ((back_net_odds / lay_net_odds) - 1.0) * 100`

### Comportamento e Proteções
- **Autogeração em Cadeia**: Se o arquivo `outputs/moneyline_opportunities.json` estiver ausente/stale, ele é recalculado, disparando as atualizações das etapas anteriores se necessário.
- **Proteção contra Falta de Dados**: Se a seleção correspondente não possuir registros para ambos os lados (Back e Lay) na comparação, ela é marcada com `possible_arbitrage = False` e motivo `"missing_back_or_lay_side"`.
- **Ranking**: O ranking principal no terminal e nos arquivos de saída prioriza as combinações cross-exchange primeiro (`is_cross_exchange = True`), depois as oportunidades de arbitragem válidas (`possible_arbitrage == True`) e, por fim, as ordena pelo menor gap percentual líquido (`gap_to_arbitrage_percent`).

### Arquivos Gerados
- **`outputs/moneyline_arbitrage_analysis.json`**: JSON contendo o relatório completo e estatísticas globais de arbitragem, incluindo o campo `is_cross_exchange`.
- **`outputs/moneyline_arbitrage_analysis.csv`**: Tabela em CSV com os mesmos campos ordenados, incluindo: `sport_name`, `back_source`, `lay_source`, `is_cross_exchange`, `back_raw_odd`, `lay_raw_odd`, `back_net_odds`, `lay_net_odds`, `back_liquidity`, `lay_liquidity`, `possible_arbitrage`, `arbitrage_score`, `gap_to_arbitrage`, `gap_to_arbitrage_percent`, `event_pair_confidence` e `selection_match_confidence`.

## Monitoramento Contínuo Moneyline (Watch Moneyline)

Para monitorar de forma contínua em tempo real as odds e arbitragem líquida de moneyline em Basquete, Beisebol e MMA, rode:

```powershell
py main.py --mode watch-moneyline
```

Esse modo é 100% read-only e executa ciclicamente as seguintes etapas:
1. `compare-moneyline`: Atualiza a comparação de odds.
2. `scan-moneyline-opportunities`: Varre e filtra discrepâncias qualificadas.
3. `analyze-moneyline-arbitrage`: Avalia a arbitragem teórica e calcula gaps de arbitragem.

### Configurações de Loop
Controladas pelas seguintes variáveis no `.env`:
- `WATCH_MONEYLINE_INTERVAL_SECONDS`: Tempo de espera (em segundos) entre ciclos (padrão `300`).
- `WATCH_MONEYLINE_MAX_CYCLES`: Quantidade máxima de ciclos (use `0` para rodar indefinidamente).

### Arquivos Gerados
- **`outputs/moneyline_watch_history.jsonl`**: Histórico detalhado em formato JSON Lines contendo as seguintes métricas por ciclo:
  - `timestamp`: Data/hora de início do ciclo.
  - `cycle_number`: Índice numérico do ciclo.
  - `duration_seconds`: Tempo total gasto na execução do ciclo.
  - `status` e `error_message`: Sucesso ou mensagem de falha caso ocorra erro.
  - `schema_version`: Versão do formato do registro.
  - `total_comparisons`: Total de runners pareados e comparados.
  - `total_moneyline_comparisons`: Alias de compatibilidade para históricos antigos.
  - `total_filtered_opportunities`: Total de oportunidades identificadas no scan.
  - `total_cross_exchange_candidates`: Quantidade de candidatos de arbitragem cross-exchange avaliados.
  - `total_possible_arbitrage`: Total de surebets cross-exchange encontradas.
  - `best_gap_to_arbitrage_percent`: Menor gap percentual para virar arbitragem entre as opções cross-exchange.
  - `best_cross_exchange_gap`: Alias de compatibilidade para históricos antigos.
  - `best_event` e `best_selection`: Nome do evento e seleção com o melhor gap cross-exchange.

## Diagnóstico de Bookmakers (The Odds API)

Para descobrir quais bookmakers estão ativas na sua conta e verificar os códigos exatos aceitos pela The Odds API, execute:

```powershell
py main.py --mode odds-api-bookmakers
```

Esse modo é 100% read-only. Como `/v4/bookmakers` retornou `404` no plano v4 usado no projeto, a descoberta consulta `/v4/sports/{sport}/odds` para os esportes configurados e extrai as casas presentes em `event["bookmakers"]`. O resultado consolidado é salvo em:
- **`outputs/the_odds_api_bookmakers.json`**

Ele exibe uma tabela de diagnóstico no terminal listando todas as casas disponíveis em sua região e destacando a presença das casas desejadas (`pinnacle`, `betano`, `sportingbet`, `novibet`, `bet365`).

## Auditoria de Consumo da The Odds API (Odds API Usage)

Para monitorar de forma econômica o consumo da sua cota mensal de créditos (500 no plano Starter da The Odds API) sem fazer nenhuma requisição adicional, execute:

```powershell
py main.py --mode odds-api-usage
```

Esse modo é 100% read-only offline. Ele lê o histórico de consumo acumulado das requisições já executadas e exibe um resumo no terminal:
- Total de créditos usados.
- Total de créditos restantes.
- Autonomia disponível e porcentagem restante.
- Histórico das últimas 5 requisições de consumo.

### Arquivos Gerados
- **`outputs/the_odds_api_usage_history.jsonl`**: Histórico atualizado automaticamente a cada chamada de API real feita à The Odds API, registrando o timestamp e as informações extraídas dos headers HTTP (`x-requests-remaining`, `x-requests-used`, `x-requests-last`).

## Comparação Multi-Bookmaker (Pinnacle x Matchbook BR)

Para rodar a comparação entre as odds de Back da Pinnacle (via The Odds API) e as odds de Back/Lay da Matchbook BR, execute:

```powershell
py main.py --mode compare-multi-bookmakers
```

Esse modo é 100% read-only, não realiza apostas e foca em encontrar discrepâncias de preço.
* **Escopo atual (POC):** Restrito aos esportes MMA, Baseball e Basketball, mercado H2H/Moneyline.
* **Cálculo de Discrepância:**
  - Para seleções do tipo **Back** na Matchbook: Compara a odd de Back líquida da Matchbook com a odd de Back líquida da Pinnacle.
  - Para seleções do tipo **Lay** na Matchbook: Compara a odd de Lay líquida da Matchbook com a odd de Back líquida da Pinnacle. Se a odd de Back da Pinnacle for superior, o sistema sinaliza a diferença como uma possível oportunidade de valor (`[ARB]`).
* **Proteções:** Se a Pinnacle não retornar odds ou se a chave de API estiver ausente, o programa aborta a execução graciosamente sem sobrescrever relatórios anteriores válidos.

### Arquivos Gerados
- **`outputs/multi_bookmaker_discrepancy_report.json`**: JSON estruturado com os dados comparados.
- **`outputs/multi_bookmaker_discrepancy_report.csv`**: Tabela ordenada de maior discrepância contendo o esporte, evento, odds e os respectivos gaps.

## Monitoramento Contínuo Multi-Bookmaker (Watch Multi-Bookmaker)

Para monitorar de forma contínua em tempo real as odds, discrepâncias e acumular histórico local em SQLite entre Pinnacle (via The Odds API) e Matchbook BR, execute:

```powershell
py main.py --mode watch-multi-bookmakers
```

Esse modo é 100% read-only, não calcula stakes ou realiza apostas e roda em ciclos contínuos de execução.

### Configurações de Loop
Controladas pelas seguintes variáveis no `.env` (ou variáveis de ambiente):
- `WATCH_MULTI_BOOKMAKER_INTERVAL_SECONDS`: Tempo de espera (em segundos) entre ciclos (padrão `300`).
- `WATCH_MULTI_BOOKMAKER_MAX_CYCLES`: Quantidade máxima de ciclos (use `0` para rodar indefinidamente).

### Proteções e Resiliência
- **Erros isolados por ciclo**: Se ocorrer uma falha de conexão ou erro na API em um ciclo, o erro será registrado no log e no histórico de execução, mas o programa continuará rodando normalmente no ciclo seguinte.
- **Não Sobrescrever Dados Bons**: Se a API falhar ou não retornar dados, os relatórios JSON e CSV de discrepância anteriores válidos são preservados.

### Arquivos Gerados
- **`outputs/multi_bookmaker_watch_history.jsonl`**: Histórico detalhado em formato JSON Lines contendo as seguintes métricas por ciclo:
  - `timestamp`: Data/hora de início do ciclo.
  - `cycle_number`: Índice numérico do ciclo.
  - `duration_seconds`: Tempo total gasto na execução do ciclo.
  - `status` e `error_message`: Sucesso ou mensagem de falha caso ocorra erro.
  - `total_matchbook_rows`: Total de linhas normalizadas da Matchbook BR.
  - `total_pinnacle_rows`: Total de linhas normalizadas da Pinnacle.
  - `total_paired_selections`: Total de seleções pareadas entre as fontes.
  - `best_discrepancy_percent`: Maior discrepância percentual líquida encontrada.
  - `best_event` e `best_selection`: Nome do evento e seleção com o maior gap de discrepância.
  - `best_matchbook_side`: O lado da Matchbook correspondente à melhor discrepância (`back` ou `lay`).
  - `best_matchbook_net_odds` e `best_pinnacle_net_odds`: As odds líquidas das duas casas para a melhor seleção.

## Histórico de Odds (SQLite)

Todas as odds normalizadas consultadas de qualquer origem (seja Matchbook BR ou The Odds API) são persistidas automaticamente em lote no banco de dados local:
- **`outputs/odds_history.db`**

O banco SQLite contém a tabela `odds_history` com os seguintes metadados cruciais para análise histórica e descoberta de padrões:
* `collected_at`: Data/hora da coleta (UTC ISO)
* `event_start_time`: Data/hora de início do evento (UTC ISO)
* `event_name`: Nome do evento
* `sport`: Esporte da partida
* `market_type`: Tipo de mercado
* `selection`: Nome da seleção
* `side`: Lado da odd (back/lay)
* `odds`: Valor decimal da odd
* `available_liquidity`: Liquidez disponível (nulo para casas tradicionais)
* `source_type`: Natureza da fonte (`exchange`, `bookmaker`, `odds_feed`)
* `source_provider`: Provedor dos dados (`matchbook-br`, `the-odds-api`)
* `bookmaker`: Identificador da casa de aposta (`pinnacle`, `matchbook-br`, etc.)

## Bookmaker Discovery Research

Para observar a pagina autenticada da SureBet.com em modo read-only e descobrir quais casas aparecem com maior frequencia e maior lucro:

```powershell
py main.py --mode bookmaker-discovery
```

Para regenerar os rankings sem abrir navegador:

```powershell
py main.py --mode bookmaker-discovery-report
```

Configure `SUREBET_USERNAME`, `SUREBET_PASSWORD` e as variaveis `SUREBET_DISCOVERY_*` no `.env`. A primeira versao usa `SUREBET_DISCOVERY_HEADLESS=false` para permitir confirmar visualmente o login. Betano e Bet365 sao excluidas totalmente dos dados e rankings por restricao do usuario.

Relatorios e banco SQLite ficam em `outputs/bookmaker_discovery/`. Veja detalhes em `docs/bookmaker_discovery.md`.

## Garantia de seguranca

Este projeto nao contem nenhum metodo para enviar apostas reais. Nao ha implementacao de:

- `placeBet`
- `placeOrder`
- `placeInstruction`
- `sendOrder`
- envio de ordens
- execucao automatica de apostas

Toda oportunidade encontrada e apenas simulada, impressa no terminal e salva em CSV/JSON.







