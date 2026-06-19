# Novibet Read-Only Integration

## Objetivo

A Fase 3.2 adiciona uma integracao inicial read-only da Novibet via Playwright. O objetivo e inspecionar paginas publicas, salvar amostras pequenas e preparar um parser conservador para catalogo e odds visiveis.

Esta fase nao integra a Novibet ao watcher multi-bookmaker, ao Opportunity Engine, ao banco SQLite ou a qualquer fluxo de aposta.

## Modo Read-Only

O cliente Novibet:

- nao usa login;
- nao le credenciais;
- nao salva cookies;
- nao clica em odds;
- nao abre ou manipula cupom de apostas;
- nao preenche stakes;
- nao envia ordens;
- nao executa apostas reais.

O Playwright e usado apenas para abrir a pagina publica configurada e ler HTML/texto visivel.

## Configuracao

Variaveis opcionais no `.env`:

```text
NOVIBET_PUBLIC_URL=https://www.novibet.bet.br/apostas-esportivas
NOVIBET_HEADLESS=true
NOVIBET_NAVIGATION_TIMEOUT_MS=30000
NOVIBET_POST_LOAD_WAIT_MS=3000
```

Dependencia Python:

```text
playwright>=1.45.0
```

Se o Chromium do Playwright ainda nao estiver instalado no ambiente, execute manualmente:

```powershell
py -m playwright install chromium
```

## Comando CLI

```powershell
py main.py --mode inspect-novibet
```

O comando:

1. abre a URL publica configurada;
2. aguarda o carregamento inicial;
3. coleta HTML e texto visivel;
4. roda o parser conservador;
5. salva os outputs locais;
6. fecha o navegador.

## Outputs

```text
outputs/novibet_raw_sample.json
outputs/novibet_normalized_sample.json
outputs/novibet_inspection_report.json
```

Campos normalizados desejados:

- `bookmaker`
- `sport`
- `league`
- `event_name`
- `start_time`
- `market_type`
- `selection`
- `odds`
- `source_url`
- `scraped_at`
- `side`
- `available_liquidity`

## Parser Atual

O parser atual e propositalmente conservador. Ele consegue extrair eventos de HTML/fixtures com atributos estruturados como:

- `data-novibet-event`
- `data-sport`
- `data-league`
- `data-event`
- `data-start`
- `data-novibet-market`
- `data-market`
- `data-selection`
- `data-odds`

Ele normaliza mercados comuns:

- `Resultado Final`, `1x2`, `Money Line` -> `Match Odds`
- `Total de Gols`, `Mais/Menos`, `Over/Under` -> `Over/Under`
- `Handicap` -> `Handicap`

Se a pagina real renderizar dados sem atributos estaveis, o modo de inspecao ainda salva o texto visivel e o relatorio, mas pode retornar `normalized_odds_count = 0`. Isso e preferivel a criar um parser fragil que invente odds.

## Seguranca Contra Automacao de Apostas

O cliente contem seletores de risco relacionados a betslip/cupom/stake/place bet apenas para deteccao em relatorio. Ele nao interage com esses seletores.

Protecoes explicitas:

- `login_used = false`
- `cookies_saved = false`
- `betting_actions_performed = false`
- nenhuma funcao de click em odd;
- nenhuma funcao de preenchimento de stake;
- nenhuma funcao de submit/place bet.

## Limitacoes Atuais

- A integracao ainda nao possui parser robusto para todas as estruturas dinamicas da Novibet.
- Nao ha login e nao ha coleta autenticada.
- Nao ha paginacao.
- Nao ha descoberta completa por esporte/liga.
- Nao ha integracao com Matchbook/Pinnacle.
- Nao ha escrita em `odds_history.db`.
- Nao ha uso no watcher.

## Proximos Passos

1. Rodar `inspect-novibet` e analisar `novibet_raw_sample.json`.
2. Identificar se a pagina publica expoe dados em HTML, JSON embutido ou chamadas XHR.
3. Criar fixtures locais anonimizadas com a estrutura real observada.
4. Expandir o parser com testes antes de integrar qualquer coleta.
5. So depois avaliar uma comparacao manual Novibet x fontes atuais.
