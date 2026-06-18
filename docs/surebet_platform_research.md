# Pesquisa Autenticada da Plataforma SureBet.com

Data da auditoria: 2026-06-18  
URL auditada: `https://pt.surebet.com/surebets`  
Modo: leitura, navegacao leve, sem apostas, sem alteracao de conta e sem coleta massiva.

## Status do Login

O login autenticado funcionou com as credenciais corrigidas no `.env`.

Evidencias tecnicas:

- apos o envio do formulario, a URL final foi `https://pt.surebet.com/surebets`;
- o titulo da pagina autenticada foi `Apostas seguras encontradas / SureBet - Apostas profissionais`;
- o link de login deixou de aparecer na tela principal;
- a pagina exibiu indicador de conta autenticada no topo;
- a tela autenticada mostrou `Encontrado 3 apostas seguras agora mesmo`.

Artefatos locais redigidos:

- `docs/surebet_research_artifacts_auth/01_surebets_authenticated.png`
- `docs/surebet_research_artifacts_auth/02_bookmakers_filter_expanded.png`
- `docs/surebet_research_artifacts_auth/03_after_first_opportunity_click.png`
- `docs/surebet_research_artifacts_auth/authenticated_research_redacted.json`

Os artefatos JSON foram higienizados para remover tokens CSRF, IDs internos longos, parametros rastreaveis, cookies, session ids e credenciais.

## Diferenca Em Relacao A Pagina Publica

Na auditoria publica anterior, a pagina exibia apenas exemplos limitados e a mensagem de plano para oportunidades acima de 1%.

Com sessao autenticada, a pagina exibiu oportunidades reais dentro dos filtros da conta. No momento da coleta, estavam selecionadas apenas duas casas:

- `EsportivaBet (BR)`
- `Novibet (BR)`

A pagina autenticada mostrou 3 oportunidades, incluindo uma de `24,4%`, que nao estava disponivel na visao publica. Isso confirma que a assinatura libera oportunidades mais amplas do que a pagina sem sessao.

## Estrutura Da Tela

A tela principal e uma listagem filtravel de surebets. A tabela observada tem colunas:

- `Lucro`: margem percentual e idade da oportunidade;
- `Casa de aposta`: bookmaker e esporte;
- `Evento`: data, horario, participantes e torneio;
- `Mercado`: identificador/descricao do mercado ou selecao;
- `Chance`: odd decimal;
- indicadores visuais de status da odd;
- links internos por bookmaker, evento e odd.

Oportunidades sao agrupadas por conjunto de pontas. Cada ponta corresponde a uma casa, evento normalizado, mercado/selecao e odd.

## Amostras Autenticadas

Amostra pequena observada com `EsportivaBet` e `Novibet`:

```text
Lucro: 24,4%
Idade: 27 min
Esporte: Tenis de mesa
Inicio: 18/06 09:35
Ponta 1: EsportivaBet (BR), mercado 11-2, odd 3.80
Ponta 2: Novibet (BR), mercado 21-2, odd 1.85
```

```text
Lucro: 1,49%
Idade: 18 h
Esporte: Basquete
Inicio: 18/06 15:30
Ponta 1: Novibet (BR), mercado 11-2 Tempo Extra, odd 1.36
Ponta 2: EsportivaBet (BR), mercado 21-2 Tempo Extra, odd 4.00
```

Uma terceira oportunidade apareceu parcialmente mascarada pela propria interface com campos `XXX`. Ela foi mantida fora dos calculos quantitativos.

## Filtros Observados

O filtro principal usa `GET /surebets` e inclui:

- tipo de produto: `Apostas seguras`;
- ordenacao: `Idade`, `Horario de inicio`, `Lucro`, `ROI`;
- numero de resultados: `2` marcado, `3` desmarcado;
- faixa de lucro min/max;
- ROI min/max;
- idade da oportunidade;
- janela de inicio do evento;
- apostas em jogadores e times;
- condicoes complexas;
- casas de apostas;
- esportes;
- torneios;
- mercados;
- opcoes avancadas.

Parametros estruturais observados, sem valores internos:

```text
selector[order]
selector[outcomes][]
selector[min_profit]
selector[max_profit]
selector[min_roi]
selector[max_roi]
selector[comb_created_at_period]
selector[settled_period]
selector[players_bets][]
selector[tournaments_categories]
selector[tournaments_action]
selector[tournaments]
```

## Calculadora

A pagina contem rotas e formularios de calculadora:

```text
GET /calculator/surebets
GET /calculator/surebet/<opportunity_id>
```

A coleta leve nao abriu uma tela completa de calculadora com campos editaveis, mas os links internos confirmam que existe uma calculadora por oportunidade. Pela tabela autenticada, as margens exibidas batem com a formula publica de arbitragem simples para mercados de 2 resultados.

Exemplo autenticado:

```text
odds = 3.80 e 1.85
S = 1/3.80 + 1/1.85 = 0.803698
ROI = (1/S - 1) * 100 = 24.4248%
```

Isso corresponde ao `24,4%` exibido.

Outro exemplo:

```text
odds = 1.36 e 4.00
S = 1/1.36 + 1/4.00 = 0.985294
ROI = (1/S - 1) * 100 = 1.4925%
```

Isso corresponde ao `1,49%` exibido.

## Padroes Tecnicos Observados

Durante a coleta autenticada leve, a pagina principal foi entregue majoritariamente como HTML renderizado pelo servidor. Nao foram capturados payloads JSON first-party relevantes para oportunidades.

Padroes seguros observados:

```text
GET  /surebets
GET  /users/sign_in
POST /users/sign_in
GET  /calculator/surebets
GET  /calculator/surebet/<opportunity_id>
GET  /nav/bookie/<bookmaker_slug>
GET  /nav/surebet/prong/<prong_index>/<opportunity_id>/if
POST /hiddes?...                  # acao de ocultar, nao usada
POST /hide_issue?...              # acao de feedback/ocultar, nao usada
```

As rotas `hiddes` e `hide_issue` sao mutacoes da conta/interface. Elas nao devem ser usadas por automacao do nosso projeto sem autorizacao explicita. A auditoria nao enviou apostas e nao alterou configuracoes criticas da conta.

## Modelo Conceitual Inferido

A plataforma modela cada surebet como um conjunto de pontas. Para o nosso sistema, a estrutura ideal seria:

```text
Opportunity
  sport
  event
  tournament
  start_time
  opportunity_age
  result_count
  roi_percent
  legs[]

OpportunityLeg
  bookmaker
  market
  selection
  odds
  link_reference
  status
```

O termo `prong` nas rotas internas reforca a ideia de que cada ponta da arbitragem deve ser uma entidade propria.

## Comparacao Com Nosso Sistema

Nosso projeto ja tem:

- coleta read-only;
- normalizacao de odds;
- comparacao multi-bookmaker;
- historico de watch;
- auditoria de discrepancias;
- filtros por liquidez, comissao e diferenca;
- processos de monitoramento em segundo plano.

Ainda falta em relacao ao modelo observado:

- modelo formal de `Opportunity` com multiplas pontas;
- suporte nativo a 2 e 3 resultados;
- calculo de `implied_sum`;
- calculo de ROI real de surebet;
- plano de stake por ponta;
- retorno por cenario;
- lucro garantido;
- idade da oportunidade;
- janela de inicio;
- separacao entre mercado simples e condicao complexa;
- filtros por esporte, torneio, mercado, resultado e idade;
- auditoria de arredondamento e stake minima.

## Recomendacoes

1. Implementar calculadora propria para mercados simples de 2 e 3 resultados.
2. Criar entidade `Opportunity` com lista de `OpportunityLeg`.
3. Calcular `implied_sum`, `roi_percent`, `stake_plan` e `guaranteed_profit`.
4. Marcar mercados complexos como `unsupported` ate existir matriz de payoff.
5. Adicionar filtros de idade, inicio do evento, numero de resultados, esporte, mercado e casas.
6. Adicionar relatorio de auditoria por oportunidade com warnings.
7. Nao integrar SureBet.com como fonte de dados do pipeline; usar a auditoria apenas como referencia de produto e matematica publica.

## Riscos E Restricoes

- Nao copiar interface, payloads, IDs internos ou regras privadas.
- Nao automatizar scraping da SureBet.com.
- Nao baixar volumes massivos.
- Nao burlar plano, captcha, rate limit ou autenticacao.
- Nao salvar credenciais, cookies, tokens ou session ids.
- Nao automatizar apostas.
- Nao tratar mercados asiaticos ou condicionais como surebets simples.

## Conclusao

O login autenticado mudou substancialmente a visao disponivel: com a assinatura ativa, a pagina exibiu oportunidades reais acima de 1% para as casas selecionadas. A principal licao para o nosso projeto e estrutural: parar de tratar discrepancia entre duas odds como produto final e evoluir para um modelo de oportunidade com pontas, ROI, stake, retorno por cenario e auditoria conservadora.
