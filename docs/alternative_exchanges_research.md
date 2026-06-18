# Relatório de Pesquisa Técnica: Provedores e APIs Alternativas à Betfair no Brasil

Este documento apresenta uma análise técnica e regulatória detalhada de potenciais candidatos a substituir temporariamente ou complementar a Betfair Exchange no projeto **Surebet**, considerando as restrições regulatórias do mercado brasileiro (SPA/MF/SIGAP) e a necessidade de integrações estáveis via APIs oficiais.

---

## 1. Contexto Regulatório no Brasil (Lei nº 14.790/2023)

A regulação brasileira de apostas de cota fixa, sob a supervisão da **Secretaria de Prêmios e Apostas do Ministério da Fazenda (SPA/MF)** e do sistema **SIGAP**, impõe que:
* Apenas operadores autorizados com domínios **`.bet.br`** podem operar legalmente em território nacional.
* A operação de plataformas *offshore* sem CNPJ local e sem a devida Portaria de Autorização da SPA/MF é ilegal.
* **Matchbook Brasil** e **Pinnacle Brasil** operam no Brasil sob a mesma licença corporativa da **A2FBR S.A.** (CNPJ nº 56.147.145/0001-74, Portaria SPA/MF nº 2.102 de 30/12/2024).

Portanto, qualquer alternativa temporária ou definitiva deve priorizar a conformidade com as diretrizes da SPA/MF.

---

## 2. Matriz de Integração (Integration Matrix)

A tabela abaixo resume a avaliação dos candidatos investigados:

| Provedor | Autorizado no Brasil (SPA/MF) | API Oficial | Modelo de Mercado | Suporta Back/Lay | Visibilidade de Liquidez | Score de Viabilidade (0-10) |
| :--- | :---: | :---: | :--- | :---: | :---: | :---: |
| **Matchbook Brasil** | Sim (A2FBR) | Sim | Exchange | Sim | Sim | **10/10** (Já Integrado) |
| **Pinnacle Brasil** | Sim (A2FBR) | Sim (Privada)* | Sharp Sportsbook | Não (Apenas Back) | Não | **8/10** (Via API ou Aggregator) |
| **The Odds API** | N/A (Aggregator) | Sim | Feed de Odds | Não (Apenas Back) | Não | **9/10** (Fácil acesso a Pinnacle) |
| **OpticOdds** | N/A (Aggregator) | Sim (Enterprise) | Feed de Odds | Não (Apenas Back) | Não | **7/10** (Custo alto de licença) |
| **Betdaq** | Não | Sim | Exchange | Sim | Sim | **3/10** (Ilegal no BR / Taxa £250) |
| **Smarkets** | Não | Sim | Exchange | Sim | Sim | **3/10** (Ilegal no BR / Taxa £150) |
| **BetInAsia** | Não (Offshore Broker) | Sim (MollyBet) | Broker / Agregador | Sim | Sim | **4/10** (Ilegal no BR / Giro €50k+) |
| **Bolsa de Aposta** | Sim (A2FBR) | Não | Exchange (Betfair WL) | Sim | Sim | **2/10** (Sem API pública) |
| **BetConnect** | Não | Sim | Hybrid Exchange | Sim | Não | **2/10** (UK-only) |
| **Orbit Exchange** | Não | Não | Exchange (Betfair WL) | Sim | Sim | **1/10** (Sem API pública) |
| **Soft Bookmakers** | Sim (Vários) | Não | Soft Sportsbook | Não | Não | **1/10** (Sem API / Risco de Ban) |

---

## 3. Análise Técnica dos Candidatos de Prioridade

### 3.1. Pinnacle Brasil (`pinnacle.bet.br`)
A Pinnacle é a maior casa de apostas "sharp" do mundo e opera legalmente no Brasil sob a licença da **A2FBR S.A.** (mesmo grupo da Matchbook Brasil). 
* **Modelo**: Sportsbook tradicional (sem Lay), mas com margens baixíssimas (2% a 4%) e limites muito altos.
* **Aposta e Arbitragem**: Ao contrário de casas "soft", a Pinnacle **não limita ou bane apostadores profissionais ou de arbitragem**. Ela aceita e encoraja o volume.
* **Status da API**: Oferece uma API REST JSON/XML extremamente robusta e estável. Contudo, desde julho de 2025, o acesso direto requer aprovação comercial (enviar e-mail para `api@pinnacle.com` descrevendo o projeto e fornecendo o ID da conta financiada).
* **Solução Alternativa via Agregadores**: Caso o acesso direto à API seja negado, é possível consumir as odds da Pinnacle Brasil de forma legal e estável via agregadores de dados como **The Odds API** ou **OpticOdds**.
* **Esportes Cobertos**: Futebol, Tênis, Basquete, Beisebol, MMA, Futebol Americano (cobertura excelente).

### 3.2. Smarkets e Betdaq
Ambas são exchanges puras que suportam o modelo Back/Lay e fornecem APIs de nível profissional (Smarkets com REST/Protobuf TCP Stream; Betdaq com WSDL/REST).
* **Conformidade regulatória**: **Nenhuma das duas obteve licença da SPA/MF no Brasil**. Operar nelas expõe o projeto a riscos legais de conformidade regulatória.
* **Barreiras Financeiras**: A Betdaq cobra uma taxa de ativação única de £250 para novos desenvolvedores de API; a Smarkets cobra £150 de taxa administrativa e restringe o onboarding de novos usuários de API.
* **Veredito**: Inviáveis e descartadas devido à ilegalidade sob as novas leis brasileiras de apostas.

### 3.3. BetInAsia (MollyBet API)
Broker asiático que consolida odds de várias exchanges (Betfair, Matchbook) e casas sharp (Pinnacle, SBObet).
* **Conformidade regulatória**: Não é regulamentada no Brasil. O acesso a brokers internacionais é considerado zona cinzenta sob a Lei nº 14.790/2023.
* **Requisitos Técnicos**: A API MollyBet é excelente (suporta pull JSON e push via sockets), mas exige um volume mínimo de giro mensal (geralmente €50.000+) ou taxas pesadas de setup para fornecer chaves de API.
* **Veredito**: Not recomendado para o escopo e orçamento atual do projeto.

### 3.4. Orbit Exchange & Bolsa de Aposta
Ambas utilizam a infraestrutura e liquidez de "white-label" da Betfair.
* **Orbit Exchange**: Não fornece nenhuma API oficial pública ou privada para integração de robôs ou coleta de dados. Descartada.
* **Bolsa de Aposta**: Operada no Brasil pela A2FBR S.A. (regularizada), mas não possui API pública para desenvolvedores externos, oferecendo apenas integração web via sua interface LayBack Web e robôs internos fechados.

### 3.5. Casas de Apostas Tradicionais "Soft" (Sportingbet, Novibet, BetMGM, Stake, 1xBet; Betano e Bet365 fora do escopo)
Todas possuem licença oficial ativa para operar no Brasil.
* **Modelo**: Sportsbooks focados em usuários recreativos.
* **Ausência de APIs**: Não oferecem APIs públicas para desenvolvedores de varejo.
* **Política de Arbitragem**: Banem e limitam contas que demonstrem comportamento de automação ou arbitragem de odds de forma extremamente rápida.
* **Veredito**: Descartadas.

---

## 4. Classificação Técnica (Technical Ranking)

Com base nos critérios regulatórios, de viabilidade técnica e compatibilidade com arbitragem:

1. **Pinnacle Brasil (Via The Odds API / OpticOdds)**: **Melhor opção viável.** Regulamentada, tolerante à arbitragem, odds de alta qualidade e fácil integração técnica via agregador.
2. **Pinnacle Brasil (API Direta)**: Excelente do ponto de vista técnico e de custos, mas depende de aprovação manual e discricionária do time de suporte da Pinnacle.
3. **BetInAsia (MollyBet API)**: Excelente para cobrir múltiplas fontes em um único feed, mas inviabilizado pela falta de regulação no Brasil e barreiras financeiras.
4. **Bolsa de Aposta**: Seria uma ótima exchange complementar, mas a falta de API oficial impede a integração programática read-only do Surebet.
5. **Betdaq / Smarkets**: Boas do ponto de vista técnico, mas descartadas por falta de licença no Brasil.
6. **Soft Bookmakers / Orbit**: Descartadas por falta de API ou intolerância à arbitragem.

---

## 5. Recomendações Estratégicas

### O que é o melhor substituto temporário para a Betfair?
A **Pinnacle Brasil** (via **The Odds API** ou via **API oficial direta**) é a única alternativa viável capaz de preencher a lacuna da Betfair durante o lockout de 30 dias. 
Como a Pinnacle é uma casa "sharp", ela não oferece a opção de apostas "Lay" (contra). No entanto, o projeto pode ser adaptado para realizar arbitragem do tipo **Back-Back** entre Matchbook Brasil e Pinnacle Brasil, ou arbitragem **Matchbook Lay** vs. **Pinnacle Back**.

### Qual é a melhor segunda fonte de longo prazo ao lado da Matchbook?
A **Pinnacle Brasil** deve ser mantida como segunda fonte definitiva do projeto Surebet mesmo após o retorno da Betfair. O triângulo **Matchbook Brasil (Exchange) - Betfair Brasil (Exchange) - Pinnacle Brasil (Sharp Bookmaker)** representa a infraestrutura ideal de arbitragem cross-market de alta liquidez no Brasil, pois todos são legalizados pela SPA/MF.

### Quais provedores merecem testes de Prova de Conceito (POC) imediatos?
1. **The Odds API**: Para validar a coleta de odds da Pinnacle Brasil e comparar a velocidade de atualização dos dados.
2. **Pinnacle API Direta**: Enviar e-mail de solicitação para `api@pinnacle.com` para tentar obter acesso direto oficial gratuito.

### Quais provedores devem ser descartados?
* **Smarkets, Betdaq, BetConnect, BetInAsia**: Descartados por falta de conformidade regulatória no Brasil.
* **Orbit Exchange, Bolsa de Aposta**: Descartados por ausência de APIs oficiais.
* **Soft Books**: Em geral descartados pelo alto risco de banimento de contas e falta de APIs. Betano e Bet365 tambem ficam explicitamente fora do escopo por restricao do usuario.

---

## 6. Roteiro de Implementação (Roadmap)

Após a aprovação desta pesquisa, os seguintes passos técnicos são recomendados:

1. **Etapa 1: Validação do Feed de Dados (Sem código de execução)**
   * Criar uma chave de testes gratuita em `the-odds-api.com`.
   * Desenvolver um cliente de diagnóstico experimental (`pinnacle_aggregator_client.py`) apenas para obter as odds da Pinnacle no mercado de Moneyline/Match Odds para futebol, basquete e beisebol.

2. **Etapa 2: Normalização e Mapeamento de Eventos**
   * Estender o `services/market_mapper.py` e o pareamento de times para a Pinnacle.
   * A Pinnacle costuma usar nomes padronizados em inglês (ex: "Sport Recife" em vez de "Sport"), o que exigirá aliases adicionais em `config/team_aliases.json`.

3. **Etapa 3: Expansão da Calculadora de Arbitragem**
   * Modificar o `services/arbitrage_calculator.py` para suportar cenários de arbitragem de duas vias "Back vs Back" (onde as duas seleções são Back em operadoras diferentes) e "Lay vs Back" (onde se aposta Lay na Matchbook e Back na Pinnacle).

4. **Etapa 4: Atualização da CLI e do Scanner**
   * Adicionar o modo `compare-pinnacle-matchbook` para analisar discrepâncias líquidas de odds.
   * Integrar a Pinnacle no modo `watch-moneyline` existente.
