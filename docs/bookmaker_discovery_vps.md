# Bookmaker Discovery na VPS Linux

## Objetivo

Rodar o Bookmaker Discovery continuamente em uma VPS Linux, sem depender do Windows local. O runner continua estritamente read-only: apenas abre a SureBet.com autenticada, observa oportunidades visiveis e grava estatisticas locais.

## Requisitos

- Python 3.11+ recomendado.
- Chromium via Playwright.
- Projeto em `/opt/surebet` ou ajuste `SUREBET_PROJECT_DIR`.
- `.env` configurado na raiz do projeto.

## Instalação Playwright/Chromium

```bash
python -m playwright install chromium
python -m playwright install-deps chromium
```

Em VPS, use:

```env
SUREBET_DISCOVERY_HEADLESS=true
```

## Variáveis `.env`

Obrigatórias:

```env
SUREBET_USERNAME=
SUREBET_PASSWORD=
SUREBET_BASE_URL=https://pt.surebet.com
SUREBET_DISCOVERY_POLL_SECONDS=5
SUREBET_DISCOVERY_MAX_CYCLES=0
SUREBET_DISCOVERY_HEADLESS=true
SUREBET_DISCOVERY_OUTPUT_DIR=outputs/bookmaker_discovery
SUREBET_DISCOVERY_MIN_PROFIT_CHANGE=0.05
SUREBET_DISCOVERY_ODDS_CHANGE_EPSILON=0.01
```

Não salve cookies, tokens ou credenciais fora do `.env`.

## Script Linux

O script:

```bash
scripts/run_bookmaker_discovery_linux.sh
```

usa:

```bash
python3 main.py --mode bookmaker-discovery
```

e grava logs em:

```text
outputs/bookmaker_discovery/logs/bookmaker_discovery.log
```

Se sua VPS tiver outro binario Python, configure:

```bash
export PYTHON_BIN=/caminho/python
```

## Serviço systemd

Exemplo:

```text
deploy/systemd/surebet-bookmaker-discovery.service
```

Instalação típica:

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin surebet
sudo mkdir -p /opt/surebet
sudo chown -R surebet:surebet /opt/surebet
sudo chmod +x /opt/surebet/scripts/run_bookmaker_discovery_linux.sh
sudo cp deploy/systemd/surebet-bookmaker-discovery.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable surebet-bookmaker-discovery
sudo systemctl start surebet-bookmaker-discovery
```

Status e logs:

```bash
sudo systemctl status surebet-bookmaker-discovery
tail -f /opt/surebet/outputs/bookmaker_discovery/logs/bookmaker_discovery.log
```

Reinício manual:

```bash
sudo systemctl restart surebet-bookmaker-discovery
```

Parar:

```bash
sudo systemctl stop surebet-bookmaker-discovery
```

## Segurança

- O serviço não executa apostas.
- Não abre casas externas.
- Não preenche stakes.
- Não usa endpoints de place bet/place order.
- Reinicia automaticamente apenas em falha do processo.

## Windows Local

O comando local Windows permanece igual:

```powershell
py main.py --mode bookmaker-discovery
```
