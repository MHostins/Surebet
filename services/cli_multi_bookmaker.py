"""CLI handlers for read-only multi-bookmaker workflows."""

from __future__ import annotations

import logging

from clients.the_odds_api_client import TheOddsAPIClient
from config.settings import settings
from services.multi_bookmaker_comparison_service import MultiBookmakerComparisonService


def run_odds_api_bookmakers() -> None:
    logger = logging.getLogger("main")
    logger.info("Starting The Odds API bookmakers discovery diagnostic...")

    if not settings.the_odds_api_key:
        print("\n[Aviso] THE_ODDS_API_KEY não está configurada no seu arquivo .env.")
        print("Por favor, adicione sua chave de API para habilitar as consultas da The Odds API.")
        return

    client = TheOddsAPIClient(settings)
    sports_to_check = [s.strip() for s in settings.the_odds_api_sports.split(",") if s.strip()]
    
    discovery_report = client.discover_bookmakers(sports_to_check)

    if discovery_report is None:
        print("\n[Erro] Falha de autenticação ou plano na The Odds API (401/403).")
        print("A chave de API configurada é inválida ou não possui permissão para acessar os endpoints.")
        if client.errors:
            print("Detalhes do erro:")
            for err in client.errors:
                print(f" - {err}")
        return

    if not discovery_report.get("bookmakers_found"):
        print("\n[Aviso] Nenhum bookmaker foi extraído das respostas da API.")
        print("Verifique se há eventos disponíveis no momento para os esportes consultados.")
        if client.errors:
            print("Erros registrados durante a consulta:")
            for err in client.errors:
                print(f" - {err}")
        return

    # Save to outputs/the_odds_api_bookmakers.json (only if we got valid data)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = settings.output_dir / "the_odds_api_bookmakers.json"
    import json
    try:
        out_path.write_text(json.dumps(discovery_report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nLista de bookmakers disponíveis salva com sucesso em: {out_path}")
    except Exception as exc:
        print(f"\nAviso: Não foi possível salvar o arquivo JSON: {exc}")

    # Analyze and print table
    print("\n" + "=" * 90)
    print(f"{'Key':<20} | {'Title':<30} | {'Esportes Observados':<35}")
    print("=" * 90)

    for bookie in discovery_report["bookmakers_found"]:
        key = bookie.get("key", "")
        title = bookie.get("title", "")
        sports_seen = ", ".join(bookie.get("sports_seen", []))
        # Truncate sports seen if too long
        if len(sports_seen) > 35:
            sports_seen = sports_seen[:32] + "..."
        print(f"{key:<20} | {title:<30} | {sports_seen:<35}")

    print("=" * 90)
    print("RESUMO DE CASAS DESEJADAS:")
    print(f" Desejadas: {', '.join(discovery_report['desired_bookmakers'])}")
    print(f" Encontradas: {', '.join(discovery_report['desired_found'])}")
    print(f" Ausentes: {', '.join(discovery_report['desired_missing'])}")
    print("=" * 90 + "\n")


def run_odds_api_usage() -> None:
    logger = logging.getLogger("main")
    logger.info("Reading The Odds API quota usage history...")

    usage_path = settings.output_dir / "the_odds_api_usage_history.jsonl"

    if not usage_path.exists():
        print("\n[Aviso] Nenhum histórico de consumo da The Odds API encontrado.")
        print(f"O arquivo {usage_path} ainda não foi criado.")
        print("Execute uma comparação primeiro usando o modo --mode compare-multi-bookmakers.")
        return

    import json
    entries = []
    try:
        with usage_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
    except Exception as exc:
        print(f"\n[Erro] Falha ao ler o arquivo de histórico: {exc}")
        return

    if not entries:
        print("\n[Aviso] O histórico de consumo está vazio.")
        print("Por favor, execute uma consulta à API primeiro.")
        return

    # Exibir resumo no terminal
    last_entry = entries[-1]
    
    print("\n" + "=" * 60)
    print("           RESUMO DE USO - THE ODDS API")
    print("=" * 60)
    print(f" Última Coleta:          {last_entry.get('timestamp')}")
    
    remaining = last_entry.get("x-requests-remaining")
    used = last_entry.get("x-requests-used")
    last_cost = last_entry.get("x-requests-last")
    
    remaining_str = str(remaining) if remaining is not None else "N/A"
    used_str = str(used) if used is not None else "N/A"
    last_cost_str = str(last_cost) if last_cost is not None else "N/A"
    
    print(f" Créditos Usados:        {used_str}")
    print(f" Créditos Restantes:     {remaining_str}")
    print(f" Custo da Última Request: {last_cost_str}")
    
    # Calcular autonomia se os limites padrão de 500 existirem
    if remaining is not None:
        total_quota = (remaining + used) if used is not None else 500
        percentage = (remaining / total_quota) * 100 if total_quota > 0 else 0
        print(f" Autonomia Disponível:   {percentage:.1f}% ({remaining_str} de {total_quota} créditos)")
        
        # Alertas de cota
        if remaining < 50:
            print(" [WARNING] Cota muito baixa! Considere diminuir a frequência ou pausar.")
        elif remaining < 150:
            print(" [NOTE] Cota moderada. Planeje suas coletas com cuidado.")
    
    print("=" * 60)
    
    # Exibir últimas 5 entradas
    print("\nÚltimas 5 entradas do histórico:")
    print(f" {'Data/Hora (UTC)':<30} | {'Usadas':<8} | {'Restantes':<10} | {'Custo last':<10}")
    print(" " + "-" * 67)
    for entry in entries[-5:]:
        ts = entry.get("timestamp", "")
        # Truncar milissegundos e fuso se for longo
        if len(ts) > 19:
            ts = ts[:19].replace("T", " ")
        rem = entry.get("x-requests-remaining")
        usd = entry.get("x-requests-used")
        lst = entry.get("x-requests-last")
        
        rem_s = str(rem) if rem is not None else "N/A"
        usd_s = str(usd) if usd is not None else "N/A"
        lst_s = str(lst) if lst is not None else "N/A"
        print(f" {ts:<30} | {usd_s:<8} | {rem_s:<10} | {lst_s:<10}")
    print("=" * 60 + "\n")


def run_compare_multi_bookmakers() -> None:
    logger = logging.getLogger("main")
    logger.info("Starting read-only multi-bookmaker comparison (Pinnacle vs Matchbook BR)...")

    if not settings.the_odds_api_key:
        print("\n[Aviso] THE_ODDS_API_KEY não está configurada no seu arquivo .env.")
        print("Por favor, adicione sua chave de API para habilitar as consultas da The Odds API.")
        return

    service = MultiBookmakerComparisonService(settings.output_dir, settings)
    result = service.compare()

    if result.get("status") == "error":
        print(f"\n[Aviso] Comparação abortada: {result.get('message')}")
        return

    comparisons = result.get("comparisons", []) or []
    print(f"\nComparação concluída com sucesso!")
    print(f"Total de registros Matchbook BR: {result.get('total_matchbook_rows')}")
    print(f"Total de registros Pinnacle: {result.get('total_pinnacle_rows')}")
    print(f"Total de seleções pareadas: {len(comparisons)}")
    print(f"Relatório JSON salvo em: {settings.output_dir / 'multi_bookmaker_discrepancy_report.json'}")
    print(f"Relatório CSV salvo em: {settings.output_dir / 'multi_bookmaker_discrepancy_report.csv'}")

    if not comparisons:
        print("\nNenhuma seleção pareada encontrada entre Matchbook BR e Pinnacle para exibir.")
        return

    # Sort comparisons: highest discrepancy_percent first
    sorted_comps = sorted(comparisons, key=lambda c: c.get("discrepancy_percent", 0.0), reverse=True)

    print("\n" + "=" * 115)
    print(f"{'Esporte':<10} | {'Evento (MB)':<30} | {'Seleção':<20} | {'Lado MB':<7} | {'Odd MB (Net)':<12} | {'Odd Pin (Net)':<13} | {'Discrepancy %':<15}")
    print("=" * 115)

    for c in sorted_comps[:20]:  # Show top 20
        sport = c.get("sport_name", "")
        event = c.get("event_name_matchbook", "")
        # Truncate event name if too long
        if len(event) > 30:
            event = event[:27] + "..."
        selection = c.get("selection_matchbook", "")
        if len(selection) > 20:
            selection = selection[:17] + "..."
        side = c.get("side_matchbook", "")
        odd_mb = c.get("net_odd_matchbook", 0.0)
        odd_pin = c.get("net_odd_pinnacle", 0.0)
        disc = c.get("discrepancy_percent", 0.0)

        # Highlight positive gaps (Pinnacle Back > Matchbook Lay)
        disc_str = f"{disc:.2f}%"
        if side == "lay" and disc > 0:
            disc_str += " [ARB]"

        print(f"{sport:<10} | {event:<30} | {selection:<20} | {side:<7} | {odd_mb:<12.2f} | {odd_pin:<13.2f} | {disc_str:<15}")

    print("=" * 115)
    if len(sorted_comps) > 20:
        print(f"Exibindo 20 de {len(sorted_comps)} seleções pareadas. Veja o relatório completo no CSV.")
    print("=" * 115 + "\n")


def run_watch_multi_bookmakers() -> None:
    import time
    import json
    from datetime import datetime, timezone

    logger = logging.getLogger("main")
    logger.info("Starting read-only watch-multi-bookmakers mode. Interval=%s seconds, Max Cycles=%s",
                settings.watch_multi_bookmaker_interval_seconds,
                settings.watch_multi_bookmaker_max_cycles)

    if not settings.the_odds_api_key:
        print("\n[Aviso] THE_ODDS_API_KEY não está configurada no seu arquivo .env.")
        print("Por favor, adicione sua chave de API para habilitar as consultas da The Odds API.")
        return

    history_path = settings.output_dir / "multi_bookmaker_watch_history.jsonl"
    cycle = 0

    try:
        while True:
            cycle += 1
            cycle_start_time = time.time()
            started_at_str = datetime.now(timezone.utc).isoformat()

            logger.info("--- Watch Multi-Bookmaker Cycle %s Start ---", cycle)
            print(f"\n[Ciclo {cycle}] Iniciando monitoramento multi-bookmaker...")

            status = "success"
            error_message = None

            total_matchbook_rows = 0
            total_pinnacle_rows = 0
            total_paired_selections = 0
            best_discrepancy_percent = None
            best_event = None
            best_selection = None
            best_matchbook_side = None
            best_matchbook_net_odds = None
            best_pinnacle_net_odds = None

            try:
                # Run compare
                service = MultiBookmakerComparisonService(settings.output_dir, settings)
                result = service.compare()

                if result.get("status") == "error":
                    raise ValueError(result.get("message"))

                total_matchbook_rows = result.get("total_matchbook_rows", 0)
                total_pinnacle_rows = result.get("total_pinnacle_rows", 0)
                comparisons = result.get("comparisons", []) or []
                total_paired_selections = len(comparisons)

                if comparisons:
                    # Find best discrepancy (highest discrepancy_percent)
                    sorted_comps = sorted(comparisons, key=lambda c: c.get("discrepancy_percent", 0.0), reverse=True)
                    best = sorted_comps[0]
                    best_discrepancy_percent = best.get("discrepancy_percent")
                    best_event = best.get("event_name_matchbook")
                    best_selection = best.get("selection_matchbook")
                    best_matchbook_side = best.get("side_matchbook")
                    best_matchbook_net_odds = best.get("net_odd_matchbook")
                    best_pinnacle_net_odds = best.get("net_odd_pinnacle")

            except Exception as exc:
                status = "failed"
                error_message = str(exc)
                logger.exception("Error in watch-multi-bookmakers cycle %s", cycle)
                print(f"[Ciclo {cycle}] Falhou: {error_message}")

            duration_seconds = round(time.time() - cycle_start_time, 2)

            history_entry = {
                "timestamp": started_at_str,
                "cycle_number": cycle,
                "duration_seconds": duration_seconds,
                "status": status,
                "total_matchbook_rows": total_matchbook_rows,
                "total_pinnacle_rows": total_pinnacle_rows,
                "total_paired_selections": total_paired_selections,
                "best_discrepancy_percent": best_discrepancy_percent,
                "best_event": best_event,
                "best_selection": best_selection,
                "best_matchbook_side": best_matchbook_side,
                "best_matchbook_net_odds": best_matchbook_net_odds,
                "best_pinnacle_net_odds": best_pinnacle_net_odds,
                "error_message": error_message,
            }

            # Save history entry
            try:
                settings.output_dir.mkdir(parents=True, exist_ok=True)
                with history_path.open("a", encoding="utf-8") as f:
                    import json
                    f.write(json.dumps(history_entry, ensure_ascii=False) + "\n")
            except Exception as io_err:
                logger.error("Failed to write to multi_bookmaker_watch_history.jsonl: %s", io_err)

            # Print summary to terminal
            if status == "success":
                best_disc_str = f"{best_discrepancy_percent:.2f}%" if best_discrepancy_percent is not None else "N/A"
                print(f"[Cycle {cycle} OK]")
                print(f"Matchbook Rows: {total_matchbook_rows}")
                print(f"Pinnacle Rows: {total_pinnacle_rows}")
                print(f"Paired Selections: {total_paired_selections}")
                print(f"Best Discrepancy: {best_disc_str}")
            else:
                print(f"[Cycle {cycle} Failed]")
                print(f"Error: {error_message}")

            # Check max cycles limit
            if settings.watch_multi_bookmaker_max_cycles > 0 and cycle >= settings.watch_multi_bookmaker_max_cycles:
                logger.info("Reached WATCH_MULTI_BOOKMAKER_MAX_CYCLES=%s. Stopping watch-multi-bookmakers mode.", settings.watch_multi_bookmaker_max_cycles)
                print(f"\nLimite de ciclos alcançado ({settings.watch_multi_bookmaker_max_cycles}). Parando watch-multi-bookmakers.")
                break

            # Calculate sleep
            elapsed = time.time() - cycle_start_time
            sleep_time = max(0.0, settings.watch_multi_bookmaker_interval_seconds - elapsed)
            if sleep_time > 0:
                logger.info("Sleeping for %.2f seconds until next cycle...", sleep_time)
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        logger.info("Watch-multi-bookmakers loop interrupted by user.")
        print("\nWatch-multi-bookmakers encerrado pelo usuário.")
