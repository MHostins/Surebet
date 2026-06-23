# Bookmaker Discovery Research

## Objetivo

Esta fase observa a pagina autenticada da SureBet.com em modo estritamente read-only para descobrir quais bookmakers aparecem com maior frequencia, maior lucro medio, maior lucro maximo e melhores pares de surebet.

O objetivo e pesquisa estatistica. O sistema nao aposta, nao abre casas externas, nao clica em odds, nao preenche stakes e nao interage com cupom de aposta.

## Configuracao

Adicione as variaveis no `.env`:

```env
SUREBET_USERNAME=seu_login
SUREBET_PASSWORD=sua_senha
SUREBET_BASE_URL=https://pt.surebet.com
SUREBET_DISCOVERY_POLL_SECONDS=5
SUREBET_DISCOVERY_MAX_CYCLES=0
SUREBET_DISCOVERY_HEADLESS=false
SUREBET_DISCOVERY_OUTPUT_DIR=outputs/bookmaker_discovery
SUREBET_DISCOVERY_MIN_PROFIT_CHANGE=0.05
SUREBET_DISCOVERY_ODDS_CHANGE_EPSILON=0.01
```

Na primeira versao, `SUREBET_DISCOVERY_HEADLESS=false` deixa o navegador visivel para confirmar visualmente que o login funcionou.

## Comandos

Iniciar coleta continua:

```powershell
py main.py --mode bookmaker-discovery
```

Regenerar relatorios sem abrir navegador:

```powershell
py main.py --mode bookmaker-discovery-report
```

Tambem existe o launcher:

```powershell
py scripts\run_bookmaker_discovery.py
```

## Como Funciona

O coletor usa Playwright para abrir `https://pt.surebet.com/surebets`, fazer login com as credenciais do `.env` e manter a pagina aberta. A cada ciclo, ele le os blocos visiveis do DOM e tenta transformar as oportunidades em registros estruturados.

O script evita refresh completo da pagina. Ele so recarrega em casos de erro, timeout, sessao indisponivel ou DOM inacessivel.

Ao interromper com `CTRL+C`, o navegador e fechado, o banco permanece integro, um relatorio final e gerado e o top 5 provisorio e exibido no terminal.

## Dados Capturados

Cada oportunidade valida registra:

- timestamp da coleta;
- percentual de lucro;
- esporte;
- evento;
- mercado;
- bookmaker 1;
- bookmaker 2;
- odds;
- URL ou identificador, quando disponivel.

Betano e Bet365 sao excluidas totalmente por restricao operacional do usuario.

## Persistencia

Os dados ficam em:

```text
outputs/bookmaker_discovery/bookmaker_discovery.db
```

O banco SQLite tem uma tabela consolidada de observacoes e uma tabela append-only de eventos relevantes. Repeticoes sem mudanca relevante atualizam `last_seen_at` e `seen_count`; mudancas relevantes de lucro ou odds geram novo evento historico.

## Relatorios

Os relatorios sao gerados periodicamente durante a coleta quando ha novos dados relevantes e sempre ao encerrar:

- `bookmaker_discovery_report.json`
- `ranking_frequency.csv`
- `ranking_avg_profit.csv`
- `ranking_max_profit.csv`
- `ranking_pairs.csv`
- `top_opportunities.csv`
- `weighted_ranking.csv`

## Ranking Ponderado

O score combina:

```text
score = 0.50 * frequencia_normalizada
      + 0.30 * lucro_medio_normalizado
      + 0.20 * lucro_maximo_normalizado
```

O top 5 recomendado vem de `weighted_ranking.csv` e `bookmaker_discovery_report.json`.

## Segurança

Esta fase e read-only:

- login e a unica submissao permitida;
- cookies, tokens, session ids e senhas nao sao gravados;
- logs nao devem expor credenciais;
- popups e navegacoes externas sao ignorados;
- nao ha cliques em odds, casas, cupom, calculadora de apostas ou botoes de ocultar;
- nao ha automatizacao de apostas.

## Proximos Passos

Depois de um ou mais dias de coleta, usar os rankings para escolher ate 5 bookmakers candidatas para pesquisa posterior. A dashboard read-only pode receber uma aba futura para visualizar estes arquivos sem chamar APIs externas.
