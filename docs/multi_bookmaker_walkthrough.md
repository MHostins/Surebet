# Walkthrough - Integração Multi-Bookmaker e Histórico SQLite (POC)

Implementamos a integração com a **The Odds API**, a persistência de histórico em banco de dados SQLite e o comparador de discrepâncias entre **Pinnacle** e **Matchbook BR** para MMA, Beisebol e Basquete.

---

## Modificações Realizadas

### 1. Configurações do Projeto
* **[settings.py](file:///c:/Projetos/Surebet/config/settings.py)**: Adicionadas variáveis de controle `THE_ODDS_API_KEY`, `THE_ODDS_API_BASE_URL`, `THE_ODDS_API_REGIONS`, `THE_ODDS_API_BOOKMAKERS` e `ODDS_HISTORY_DB_PATH`.
* **[.env.example](file:///c:/Projetos/Surebet/.env.example)**: Adicionados placeholders das configurações acima com valores padrão recomendados.

### 2. Cliente de Integração (Correção The Odds API)
* **[the_odds_api_client.py](file:///c:/Projetos/Surebet/clients/the_odds_api_client.py)**: Novo cliente oficial de integração com a The Odds API (v4).
  * Removido o endpoint `/v4/bookmakers` (que retornava 404).
  * Implementada a consulta de odds decimais de moneyline (`/v4/sports/{sport}/odds`) retornando também o status code HTTP.
  * Adicionado o método `discover_bookmakers(sports_list)` que realiza a descoberta de casas de apostas extraindo o campo `event["bookmakers"]` a partir de uma lista de esportes consultados, mapeando as casas encontradas e comparando com a lista de desejadas.

### 3. Histórico de Odds no Banco de Dados
* **[odds_history_service.py](file:///c:/Projetos/Surebet/services/odds_history_service.py)**: Novo serviço para gerenciar a inicialização e inserção em lote na tabela SQLite `odds_history`. Inclui dados de controle refinados:
  * `collected_at`: Data e hora exata da coleta (UTC ISO).
  * `event_start_time`: Data e hora de início do evento (UTC ISO).
  * `source_type`: Natureza da fonte (`exchange`, `bookmaker` ou `odds_feed`).
  * `source_provider`: Provedor do feed (`matchbook-br` ou `the-odds-api`).
  * `bookmaker`: Nome simplificado da casa (`pinnacle` ou `matchbook-br`).

### 4. Comparador de Discrepâncias e Valor
* **[multi_bookmaker_comparison_service.py](file:///c:/Projetos/Surebet/services/multi_bookmaker_comparison_service.py)**: Novo serviço responsável pelo fluxo da POC:
  * Carrega dados da Matchbook BR (via requisições diretas aos esportes configurados) e da Pinnacle.
  * Restringe a análise a Basquete, Beisebol e MMA (Moneyline).
  * Realiza o pareamento de eventos (delta de horário e confiança de nomes de times) e runners.
  * Calcula as divergências de odds (net) e marca possíveis oportunidades de valor (`[ARB]`).
  * **Proteções**: Se a Pinnacle não retornar odds, o script abortar sem sobrescrever dados anteriores válidos.
  * **Persistência**: Grava automaticamente todas as odds brutas capturadas no banco SQLite.
  * Salva os resultados em `outputs/multi_bookmaker_discrepancy_report.json` e `.csv`.

### 5. CLI e Roteamento
* **[main.py](file:///c:/Projetos/Surebet/main.py)**: Adicionados e roteados os novos modos de linha de comando:
  * `py main.py --mode odds-api-bookmakers`
  * `py main.py --mode compare-multi-bookmakers`
  * `py main.py --mode watch-multi-bookmakers`
  * `py main.py --mode odds-api-usage`
* Adicionado tratamento robusto e amigável caso a chave `THE_ODDS_API_KEY` esteja ausente no `.env`.

### 6. Auditoria de Pareamentos e Suporte a event_id (Tarefa 1 e 4)
* **[clients/the_odds_api_client.py](file:///c:/Projetos/Surebet/clients/the_odds_api_client.py)**: Atualizado o dicionário retornado por `get_normalized_odds` para propagar o `event_id` da Pinnacle.
* **[services/multi_bookmaker_comparison_service.py](file:///c:/Projetos/Surebet/services/multi_bookmaker_comparison_service.py)**:
  * Propagado o `event_id` na normalização do Matchbook BR.
  * Modificada a lógica de comparação para rastrear anomalias de pareamento com discrepâncias superiores a 20%, gerando o arquivo `outputs/matching_audit_report.json`.
* **[services/odds_history_service.py](file:///c:/Projetos/Surebet/services/odds_history_service.py)**:
  * Implementada a migração automática via `ALTER TABLE` para incluir a coluna `event_id` caso ela não exista no banco.
  * Atualizado o fluxo de gravação em lote para incluir a persistência do `event_id` no banco de dados SQLite.

---

## Resultados das Validações

### 1. Compilação
```powershell
py -m py_compile main.py clients/the_odds_api_client.py services/odds_history_service.py services/multi_bookmaker_comparison_service.py
```
* **Resultado:** Compilado com sucesso sem avisos ou erros de sintaxe/importação.

### 2. Validação da Descoberta de Bookmakers
Ao rodar:
```powershell
py main.py --mode odds-api-bookmakers
```
* **Resultado:** O script consultou com sucesso a The Odds API v4 (endpoints de odds) para `upcoming`, `basketball_nba`, `baseball_mlb` e `mma_mixed_martial_arts`, extraiu os bookmakers ativos por evento e identificou que a **Pinnacle** (`pinnacle`) está ativa e disponível. Gerou o relatório `outputs/the_odds_api_bookmakers.json` corretamente.

### 3. Validação do Modo Comparação
Ao rodar:
```powershell
py main.py --mode compare-multi-bookmakers
```
* **Resultado:** O script pareou 56 seleções de MMA, Beisebol e Basquete entre Matchbook BR e Pinnacle. Salvou os relatórios de discrepância (JSON/CSV) e gravou 180 registros no SQLite com metadados detalhados de auditoria.
* **Validação do SQLite:** Consulta de contagem retornou:
   * 116 registros de `matchbook-br`.
   * 64 registros de `the-odds-api` (Pinnacle).
   * Todas as inserções bem-sucedidas.

### 4. Validação do Modo Monitoramento Contínuo (Watch)
Ao rodar:
```powershell
$env:WATCH_MULTI_BOOKMAKER_INTERVAL_SECONDS="5"; $env:WATCH_MULTI_BOOKMAKER_MAX_CYCLES="2"; py main.py --mode watch-multi-bookmakers
```
* **Resultado:** O script executou os 2 ciclos configurados com sucesso. No Ciclo 1 coletou 116 registros da Matchbook BR, 66 da Pinnacle e pareou 56 seleções com discrepância máxima de 4.18%. No Ciclo 2 repetiu a coleta.
* **Saída Gerada:** Adicionadas com sucesso as 2 entradas correspondentes no arquivo `outputs/multi_bookmaker_watch_history.jsonl`, contendo as colunas solicitadas: `timestamp`, `cycle_number`, `duration_seconds`, `status`, `total_matchbook_rows`, `total_pinnacle_rows`, `total_paired_selections`, `best_discrepancy_percent`, `best_event`, `best_selection`, `best_matchbook_side`, `best_matchbook_net_odds`, `best_pinnacle_net_odds` e `error_message`.
* **Banco SQLite:** O log do histórico inseriu com sucesso as odds de cada ciclo no banco `outputs/odds_history.db`.

### 5. Validação do Modo Auditoria de Consumo (Odds API Usage)
Ao rodar:
```powershell
py main.py --mode odds-api-usage
```
* **Resultado:** O script leu com sucesso o arquivo de histórico gerado automaticamente nas chamadas anteriores e exibiu um resumo legível e formatado no terminal sem consumir novos créditos da API.
* **Saída Gerada:** Registros adicionados no arquivo `outputs/the_odds_api_usage_history.jsonl` com o timestamp, créditos usados (`x-requests-used`), créditos restantes (`x-requests-remaining`) e custo da última requisição (`x-requests-last`).

### 6. Validação da Auditoria de Pareamentos e event_id no SQLite (Tarefa 1 e 4)
Ao rodar:
```powershell
py main.py --mode compare-multi-bookmakers
```
* **Resultado:** O script detectou automaticamente a ausência da coluna `event_id` no banco SQLite `outputs/odds_history.db`, disparando e executando a migração do banco com sucesso.
* **Saída Gerada**:
  * O arquivo `outputs/matching_audit_report.json` foi gerado (vazio `[]` no teste, atestando que não houve discrepâncias acima de 20% na amostragem).
  * Todos os novos registros gravados na tabela `odds_history` tanto para `matchbook-br` quanto para `pinnacle` passaram a ter a coluna `event_id` corretamente preenchida com os identificadores numéricos e hashes únicos das APIs originais.
