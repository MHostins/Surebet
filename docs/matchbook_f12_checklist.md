# Checklist F12 - Matchbook Brasil

Objetivo: observar o fluxo real usado pela Matchbook Brasil no navegador e comparar com o cliente read-only atual do Surebet.

Importante: nao copie senha, token completo, cookie completo ou qualquer segredo para arquivos do projeto. Quando precisar registrar um valor sensivel, use mascara, por exemplo `****abcd`.

## Preparacao

1. Abra uma janela anonima/privada do navegador.
2. Acesse `https://matchbook.bet.br/b/exchange`.
3. Abra o DevTools com `F12`.
4. Va para a aba `Network`.
5. Marque `Preserve log`.
6. Marque `Disable cache`, se estiver disponivel.
7. Filtre por `Fetch/XHR` quando quiser ver apenas chamadas de API.
8. Limpe o log da aba Network antes de iniciar o login.

## Login

Durante o login, observe e anote:

- URL chamada no login.
- Metodo HTTP usado (`POST`, `GET`, etc.).
- Status HTTP retornado (`200`, `302`, `401`, `403`, etc.).
- `Content-Type` da resposta.
- Headers principais enviados:
  - `content-type`
  - `accept`
  - `origin`
  - `referer`
  - `user-agent`
  - qualquer header customizado relevante
- Payload enviado:
  - formato (`JSON`, `form-urlencoded`, multipart, outro)
  - nomes dos campos, sem copiar senha real
- Cookies criados ou alterados:
  - nomes dos cookies
  - dominio
  - flags relevantes (`HttpOnly`, `Secure`, `SameSite`)
  - nao copie valores completos
- Se existe algum token na resposta, no storage ou em headers:
  - `session-token`
  - `Authorization: Bearer ...`
  - token em cookie
  - token em `localStorage` ou `sessionStorage`

## Depois do login

Depois de entrar na tela `/b/exchange`, ainda com o Network aberto:

1. Clique em futebol/soccer.
2. Abra uma partida futura, nao ao vivo.
3. Abra mercados Match Odds e Over/Under 2.5, se aparecerem.
4. Observe as chamadas disparadas.

Anote:

- Endpoints acessados apos entrar em `/b/exchange`.
- Se as chamadas de odds/eventos usam API JSON ou retornam HTML.
- URL de eventos.
- URL de mercados.
- URL de odds/prices.
- Metodo HTTP de cada chamada.
- Query params relevantes, especialmente:
  - `include-prices`
  - `odds-type`
  - `exchange-type`
  - ids de esporte/evento/mercado
- Headers de autenticacao usados nas chamadas:
  - cookie
  - `session-token`
  - `Authorization`
  - outro header
- Status HTTP das chamadas.
- `Content-Type` das respostas.

## Como salvar evidencias com seguranca

Preferir preencher `docs/matchbook_f12_findings.example.json` com dados resumidos.

Se copiar algum trecho de request/response:

- remova senha;
- remova token completo;
- remova cookie completo;
- mantenha apenas os ultimos 4 caracteres de tokens quando necessario;
- nao salve capturas contendo dados pessoais desnecessarios.

## Perguntas para responder

- O login real usa `https://api.matchbook.com/bpapi/rest/security/session` ou outro endpoint regional?
- O navegador recebe JSON no login ou usa cookies de sessao?
- As chamadas de odds usam `session-token`, bearer token ou apenas cookies?
- Existe endpoint JSON para eventos/mercados no dominio `matchbook.bet.br`?
- O endpoint global `api.matchbook.com` e redirecionado para a UI brasileira para esta conta/regiao?
