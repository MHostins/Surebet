"""CLI handlers for read-only moneyline workflows."""

from __future__ import annotations

import logging

from config.settings import settings
from services.moneyline_arbitrage_service import MoneylineArbitrageService
from services.moneyline_comparison_service import MoneylineComparisonService
from services.moneyline_discovery_service import MoneylineDiscoveryService
from services.moneyline_opportunity_scanner import MoneylineOpportunityScanner


def run_moneyline_discovery() -> None:
    logger = logging.getLogger("main")
    logger.info("Starting read-only moneyline pairing discovery mode. No bets, arbitrage, or alerts will be run.")
    service = MoneylineDiscoveryService(
        output_dir=settings.output_dir,
        settings=settings,
    )
    report = service.run_discovery()

    print("\nMoneyline pairing discovery completed.")
    print("Detailed report saved to outputs/moneyline_pairing_report.json\n")

    # Print summary table to terminal
    print("=== MONEYLINE PAIRING SUMMARY ===")
    header = f"{'Sport Name':<20} | {'Matchbook Events':<18} | {'Betfair Events':<16} | {'Paired Events':<15} | {'Pairing Rate (%)'}"
    print(header)
    print("-" * len(header))

    for summary in report.get("sports_summary", []):
        sport_name = summary.get("sport_name")
        mb_count = summary.get("matchbook_events_count", 0)
        bf_count = summary.get("betfair_events_count", 0)
        paired_count = summary.get("paired_events_count", 0)
        pairing_pct = summary.get("pairing_percentage", 0.0)

        print(f"{sport_name:<20} | {mb_count:<18} | {bf_count:<16} | {paired_count:<15} | {pairing_pct:.2f}%")

        notes = summary.get("notes", [])
        for note in notes:
            print(f"  * NOTE: {note}")
    print()


def run_compare_moneyline() -> None:
    logger = logging.getLogger("main")
    logger.info("Starting read-only moneyline comparison mode. No stakes, arbitrage or bets will be run.")
    service = MoneylineComparisonService(
        output_dir=settings.output_dir,
        settings=settings
    )
    report = service.compare()

    print("\nMoneyline comparison completed.")
    print("Detailed report saved to outputs/moneyline_comparison_report.json")
    print("CSV report saved to outputs/moneyline_comparison_report.csv\n")

    comparisons = report.get("comparisons", [])
    print(f"Total compared moneyline runners: {len(comparisons)}")

    if comparisons:
        print("\n=== MONEYLINE ODDS COMPARISON SUMMARY ===")
        # Print top 15 highest percentage difference comparison rows
        sorted_comps = sorted(comparisons, key=lambda x: x.get("percentage_difference", 0.0), reverse=True)

        header = f"{'Sport':<12} | {'Event (Matchbook)':<40} | {'Selection':<20} | {'Side':<5} | {'Odd MB':<8} | {'Odd BF':<8} | {'Diff %':<10}"
        print(header)
        print("-" * len(header))

        for row in sorted_comps[:15]:
            sport = row["sport_name"]
            event = row["event_name_matchbook"]
            selection = row["selection_matchbook"]
            side = row["side"]
            odd_mb = row["odd_matchbook"]
            odd_bf = row["odd_betfair"]
            diff_pct = row["percentage_difference"]

            event_trunc = event[:40] if event else ""
            selection_trunc = selection[:20] if selection else ""

            print(f"{sport:<12} | {event_trunc:<40} | {selection_trunc:<20} | {side:<5} | {odd_mb:<8.2f} | {odd_bf:<8.2f} | {diff_pct:.2f}%")
        print()


def run_scan_moneyline_opportunities() -> None:
    logger = logging.getLogger("main")
    logger.info("Starting read-only moneyline opportunity scanner. No stakes, arbitrage or bets will be run.")
    service = MoneylineOpportunityScanner(
        output_dir=settings.output_dir,
        settings=settings,
        min_difference_percent=settings.min_odds_difference_percent,
        min_liquidity_betfair=settings.min_liquidity_betfair,
        min_liquidity_matchbook_br=settings.min_liquidity_matchbook_br,
    )
    report = service.scan()

    print("\nMoneyline opportunities scanning completed.")
    print("Detailed report saved to outputs/moneyline_opportunities.json")
    print("CSV report saved to outputs/moneyline_opportunities.csv\n")

    opportunities = report.get("opportunities", [])
    print(f"Total opportunities matching criteria: {len(opportunities)}")

    if opportunities:
        print("\n=== MONEYLINE FILTERED OPPORTUNITIES (Ordered by Net Diff %) ===")
        header = f"{'Sport':<12} | {'Event':<40} | {'Selection':<20} | {'Side':<5} | {'Odd MB':<8} | {'Odd BF':<8} | {'Liq MB':<8} | {'Liq BF':<8} | {'Net Diff %':<10}"
        print(header)
        print("-" * len(header))

        for row in opportunities:
            sport = row["sport_name"]
            event = row["event_name_matchbook"] or row["event_name_betfair"]
            selection = row["selection_matchbook"] or row["selection_betfair"]
            side = row["side"]
            odd_mb = row["odd_matchbook"]
            odd_bf = row["odd_betfair"]
            liq_mb = row["liquidity_matchbook"]
            liq_bf = row["liquidity_betfair"]
            net_diff_pct = row["net_difference_percent"]

            event_trunc = event[:40] if event else ""
            selection_trunc = selection[:20] if selection else ""

            print(f"{sport:<12} | {event_trunc:<40} | {selection_trunc:<20} | {side:<5} | {odd_mb:<8.2f} | {odd_bf:<8.2f} | {liq_mb:<8.1f} | {liq_bf:<8.1f} | {net_diff_pct:.2f}%")
        print()


def run_analyze_moneyline_arbitrage() -> None:
    logger = logging.getLogger("main")
    logger.info("Starting read-only moneyline arbitrage analysis. No stakes, order creation or bets will be run.")
    service = MoneylineArbitrageService(
        output_dir=settings.output_dir,
        settings=settings,
        min_liquidity_betfair=settings.min_liquidity_betfair,
        min_liquidity_matchbook_br=settings.min_liquidity_matchbook_br,
    )
    report = service.analyze()

    print("\nMoneyline arbitrage analysis completed.")
    print("Detailed report saved to outputs/moneyline_arbitrage_analysis.json")
    print("CSV report saved to outputs/moneyline_arbitrage_analysis.csv\n")

    results = report.get("results", [])
    possible_count = report.get("total_possible_arbitrages", 0)
    print(f"Total evaluated moneyline opportunities: {report.get('total_evaluated', 0)}")
    print(f"Total possible arbitrage opportunities: {possible_count}")

    if results:
        print("\n=== MONEYLINE ARBITRAGE & GAP DIAGNOSTICS (Ranked) ===")
        header = f"{'Sport':<12} | {'Event':<40} | {'Selection':<20} | {'Back Src':<12} | {'Lay Src':<12} | {'Back Net':<8} | {'Lay Net':<8} | {'Gap % / Margin':<15} | {'Cross':<5} | {'Possible'}"
        print(header)
        print("-" * len(header))

        for row in results:
            sport = row["sport_name"]
            event = row["event_name_matchbook"] or row["event_name_betfair"]
            selection = row["selection_matchbook"] or row["selection_betfair"]
            back_src = row["back_source"] or "N/A"
            lay_src = row["lay_source"] or "N/A"

            back_net = row["back_net_odds"]
            lay_net = row["lay_net_odds"]
            back_net_str = f"{back_net:.2f}" if back_net is not None else "N/A"
            lay_net_str = f"{lay_net:.2f}" if lay_net is not None else "N/A"

            is_possible = "YES!" if row["possible_arbitrage"] else "No"
            is_cross = "Yes" if row.get("is_cross_exchange") else "No"

            if row["possible_arbitrage"]:
                margin_str = f"+{row['arbitrage_score']:.2f}% (Profit)"
            else:
                gap = row["gap_to_arbitrage_percent"]
                margin_str = f"{gap:.2f}% (Gap)" if gap is not None else "N/A"

            event_trunc = event[:40] if event else ""
            selection_trunc = selection[:20] if selection else ""

            print(f"{sport:<12} | {event_trunc:<40} | {selection_trunc:<20} | {back_src:<12} | {lay_src:<12} | {back_net_str:<8} | {lay_net_str:<8} | {margin_str:<15} | {is_cross:<5} | {is_possible}")
        print()


def run_watch_moneyline() -> None:
    import time
    import json
    from datetime import datetime, timezone

    logger = logging.getLogger("main")
    logger.info("Starting read-only watch-moneyline mode. Interval=%s seconds, Max Cycles=%s",
                settings.watch_moneyline_interval_seconds, settings.watch_moneyline_max_cycles)

    cycle = 0
    history_path = settings.output_dir / "moneyline_watch_history.jsonl"

    try:
        while True:
            cycle += 1
            cycle_start_time = time.time()
            started_at_str = datetime.now(timezone.utc).isoformat()

            logger.info("--- Watch Moneyline Cycle %s Start ---", cycle)
            print(f"\n[Ciclo {cycle}] Iniciando monitoramento moneyline...")

            status = "success"
            error_message = None

            total_comparisons = None
            total_filtered_opportunities = None
            total_cross_exchange_candidates = None
            total_possible = None
            best_gap = None
            best_event = None
            best_selection = None
            best_back_source = None
            best_lay_source = None

            try:
                # 1. Compare moneyline
                compare_service = MoneylineComparisonService(
                    output_dir=settings.output_dir,
                    settings=settings
                )
                comp_report = compare_service.compare()

                # 2. Scan moneyline opportunities
                scanner_service = MoneylineOpportunityScanner(
                    output_dir=settings.output_dir,
                    settings=settings,
                    min_difference_percent=settings.min_odds_difference_percent,
                    min_liquidity_betfair=settings.min_liquidity_betfair,
                    min_liquidity_matchbook_br=settings.min_liquidity_matchbook_br,
                )
                scan_report = scanner_service.scan()

                # 3. Analyze moneyline arbitrage
                arbitrage_service = MoneylineArbitrageService(
                    output_dir=settings.output_dir,
                    settings=settings,
                    min_liquidity_betfair=settings.min_liquidity_betfair,
                    min_liquidity_matchbook_br=settings.min_liquidity_matchbook_br,
                )
                arb_report = arbitrage_service.analyze()

                # Extract metrics
                total_comparisons = len(comp_report.get("comparisons", []) or [])
                total_filtered_opportunities = len(scan_report.get("opportunities", []) or [])
                
                results = arb_report.get("results", []) or []
                total_cross_exchange_candidates = sum(1 for x in results if x.get("is_cross_exchange"))
                total_possible = arb_report.get("total_possible_arbitrages", 0)

                # Find best cross-exchange candidate
                best_cross = None
                for item in results:
                    if item.get("is_cross_exchange"):
                        best_cross = item
                        break

                if best_cross:
                    best_gap = best_cross.get("gap_to_arbitrage_percent") if not best_cross.get("possible_arbitrage") else 0.0
                    best_event = best_cross.get("event_name_matchbook") or best_cross.get("event_name_betfair")
                    best_selection = best_cross.get("selection_matchbook") or best_cross.get("selection_betfair")
                    best_back_source = best_cross.get("back_source")
                    best_lay_source = best_cross.get("lay_source")

            except Exception as exc:
                status = "failed"
                error_message = str(exc)
                logger.exception("Error in watch-moneyline cycle %s", cycle)
                print(f"[Ciclo {cycle}] Falhou: {error_message}")

            finished_at_str = datetime.now(timezone.utc).isoformat()
            duration_seconds = round(time.time() - cycle_start_time, 2)

            history_entry = {
                "schema_version": 2,
                "timestamp": started_at_str,
                "cycle_number": cycle,
                "duration_seconds": duration_seconds,
                "status": status,
                "error_message": error_message,
                "total_comparisons": total_comparisons,
                "total_moneyline_comparisons": total_comparisons,
                "total_filtered_opportunities": total_filtered_opportunities,
                "total_cross_exchange_candidates": total_cross_exchange_candidates,
                "total_possible_arbitrage": total_possible,
                "best_gap_to_arbitrage_percent": best_gap,
                "best_cross_exchange_gap": best_gap,
                "best_event": best_event,
                "best_selection": best_selection,
                "best_back_source": best_back_source,
                "best_lay_source": best_lay_source
            }

            # Save history entry
            try:
                settings.output_dir.mkdir(parents=True, exist_ok=True)
                with history_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(history_entry, ensure_ascii=False) + "\n")
            except Exception as io_err:
                logger.error("Failed to write to moneyline_watch_history.jsonl: %s", io_err)

            # Print summary to terminal
            if status == "success":
                best_gap_str = f"{best_gap:.2f}%" if best_gap is not None else "N/A"
                print(f"[Cycle {cycle} OK]")
                print(f"Comparisons: {total_comparisons}")
                print(f"Filtered Opportunities: {total_filtered_opportunities}")
                print(f"Cross-Exchange Candidates: {total_cross_exchange_candidates}")
                print(f"Possible Arbitrage: {total_possible}")
                print(f"Best Gap: {best_gap_str}")
            else:
                print(f"[Cycle {cycle} Failed]")
                print(f"Error: {error_message}")

            # Check max cycles limit
            if settings.watch_moneyline_max_cycles > 0 and cycle >= settings.watch_moneyline_max_cycles:
                logger.info("Reached WATCH_MONEYLINE_MAX_CYCLES=%s. Stopping watch-moneyline mode.", settings.watch_moneyline_max_cycles)
                print(f"\nLimite de ciclos alcançado ({settings.watch_moneyline_max_cycles}). Parando watch-moneyline.")
                break

            # Calculate sleep
            elapsed = time.time() - cycle_start_time
            sleep_time = max(0.0, settings.watch_moneyline_interval_seconds - elapsed)
            if sleep_time > 0:
                logger.info("Sleeping for %.2f seconds until next cycle...", sleep_time)
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        logger.info("Watch-moneyline loop interrupted by user.")
        print("\nWatch-moneyline encerrado pelo usuário.")
