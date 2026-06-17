# Plano de Implementação Ajustado - Integração Multi-Bookmaker e Histórico de Odds

Este plano descreve as alterações necessárias para implementar o suporte multi-bookmaker de forma segura e incremental durante o lockout da Betfair, incorporando todas as diretrizes e restrições solicitadas.

---

## Novos Ajustes e Escopo

### 1. Novo Modo de Consulta de Casas (Odds API Bookmakers)
Antes de construir a comparação avançada, criaremos um modo diagnóstico simples para verificar as chaves reais de bookmakers suportadas pela conta:
* **Comando:** `py main.py --mode odds-api-bookmakers`
* **Objetivo:** Consultar odds por esporte em `/v4/sports/{sport}/odds`, extrair as casas presentes em `event["bookmakers"]` e listar de forma amigável quais das casas desejadas (`pinnacle`, `betano`, `sportingbet`, `novibet`, `bet365`) estão disponíveis. O endpoint `/v4/bookmakers` foi evitado porque retornou `404` no plano v4 usado no projeto.
* **Saída:** `outputs/the_odds_api_bookmakers.json`

---

### 2. Escopo Limitado da Primeira POC
A comparação inicial no modo `compare-multi-bookmakers` será restrita a:
* **Origens:** **Pinnacle** (via The Odds API) vs. **Matchbook BR**.
* **Esportes:** MMA, Baseball e Basketball.
* **Mercado:** `h2h` / `money_line`.
* **Relatórios:** Renomeados para refletir discrepâncias brutas e de valor relativo, e não "surebet" definitiva:
  * `outputs/multi_bookmaker_discrepancy_report.json`
  * `outputs/multi_bookmaker_discrepancy_report.csv`
* **Proteção de Dados:** Se a Pinnacle não retornar odds ou se a consulta falhar, o script abortará amigavelmente sem sobrescrever relatórios anteriores com arquivos vazios.

---

### 3. Histórico com Metadados de Origem (SQLite)
A tabela `odds_history` no banco `outputs/odds_history.db` incluirá colunas adicionais para identificar com precisão a natureza e os momentos dos dados persistidos:
* `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
* `collected_at` (TEXT) - Data/hora da coleta (UTC ISO)
* `event_start_time` (TEXT) - Data/hora de início do evento (UTC ISO)
* `event_name` (TEXT)
* `sport` (TEXT)
* `market_type` (TEXT)
* `selection` (TEXT)
* `side` (TEXT)
* `odds` (REAL)
* `available_liquidity` (REAL, nulo para casas tradicionais)
* `source_type` (TEXT) - `exchange`, `bookmaker` ou `odds_feed`
* `source_provider` (TEXT) - `matchbook-br` ou `the-odds-api`
* `bookmaker` (TEXT) - `pinnacle`, `matchbook-br`, etc.

---

### 4. Proteções de Token / Chaves de API
* Se a chave `THE_ODDS_API_KEY` não estiver configurada no `.env`:
  * A execução exibirá um aviso claro e amigável.
  * O script **não deve quebrar** (lançar exceções não tratadas).
  * O script **não deve sobrescrever** relatórios anteriores válidos com arquivos vazios.

---

## Mudanças Propostas nos Componentes

### 1. Configurações

#### [MODIFY] [settings.py](file:///c:/Projetos/Surebet/config/settings.py)
* Adicionar novas chaves de configuração:
  * `the_odds_api_key`: string (carregada de `THE_ODDS_API_KEY`).
  * `the_odds_api_base_url`: string (`THE_ODDS_API_BASE_URL`, padrão `https://api.the-odds-api.com/v4`).
  * `the_odds_api_regions`: string (`THE_ODDS_API_REGIONS`, padrão `eu`).
  * `the_odds_api_bookmakers`: lista/string (`THE_ODDS_API_BOOKMAKERS`, padrão `pinnacle,betano,sportingbet,novibet,bet365`).
  * `odds_history_db_path`: string (`ODDS_HISTORY_DB_PATH`, padrão `outputs/odds_history.db`).

#### [MODIFY] [.env.example](file:///c:/Projetos/Surebet/.env.example)
* Adicionar os placeholders correspondentes.

---

### 2. Clientes e Serviços

#### [NEW] [the_odds_api_client.py](file:///c:/Projetos/Surebet/clients/the_odds_api_client.py)
* Métodos:
  * `discover_bookmakers(sports_list)`: consulta `/v4/sports/{sport}/odds` e extrai bookmakers das respostas.
  * `fetch_odds(sport: str)`: consulta `/v4/sports/{sport}/odds` para obter odds decimais de moneyline.
  * `get_normalized_odds(sport: str)`: extrai e normaliza as odds da Pinnacle no formato do Surebet.

#### [NEW] [odds_history_service.py](file:///c:/Projetos/Surebet/services/odds_history_service.py)
* Classe responsável pela inicialização do banco SQLite e pela gravação em lote de odds históricas com as colunas de metadados (`collected_at`, `event_start_time`, `source_type`, `source_provider`, `bookmaker`).

#### [NEW] [multi_bookmaker_comparison_service.py](file:///c:/Projetos/Surebet/services/multi_bookmaker_comparison_service.py)
* Carrega odds da Matchbook BR e da Pinnacle (via The Odds API).
* Filtra os esportes MMA, Baseball e Basketball.
* Realiza o pareamento de eventos e seleções.
* Calcula os gaps de divergência (ex: Pinnacle Back vs. Matchbook Lay).
* Salva os resultados nos relatórios `multi_bookmaker_discrepancy_report` (JSON/CSV) e grava no SQLite.

---

### 3. CLI

#### [MODIFY] [main.py](file:///c:/Projetos/Surebet/main.py)
* Adicionar suporte aos modos:
  * `odds-api-bookmakers`
  * `compare-multi-bookmakers`
* Implementar a lógica de tratamento amigável de chaves ausentes ou de falhas de autenticação sem corromper relatórios existentes.

---

## Plano de Verificação

### Compilação de Sintaxe
```powershell
py -m py_compile main.py clients/the_odds_api_client.py services/odds_history_service.py services/multi_bookmaker_comparison_service.py
```

### Validação Manual
1. Executar `py main.py --mode odds-api-bookmakers` sem chave `.env` para atestar o tratamento de erros.
2. Repetir o teste com chave configurada e analisar o arquivo `outputs/the_odds_api_bookmakers.json`.
3. Executar a comparação multi-bookmaker via `compare-multi-bookmakers` e validar a integridade dos relatórios de discrepância e da gravação no banco SQLite `odds_history.db`.
