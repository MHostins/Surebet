"""Read-only odds comparison between Betfair Exchange and Matchbook."""

from __future__ import annotations

import argparse
import logging
from pprint import pformat

from clients.betfair_client import BetfairClient
from clients.matchbook_br_client import MatchbookBRClient
from clients.matchbook_client import MatchbookClient
from clients.the_odds_api_client import TheOddsAPIClient
from config.settings import settings
from services.alias_suggestion_service import AliasSuggestionService
from services.arbitrage_analyzer import ArbitrageAnalyzer
from services.arbitrage_calculator import ArbitrageCalculator
from services.comparison_service import ComparisonService
from services.config_checker import ConfigChecker
from services.diagnostic_runner import DiagnosticRunner
from services.market_discovery_service import MarketDiscoveryService
from services.market_mapper import MarketMapper
from services.matchbook_market_discovery_service import MatchbookMarketDiscoveryService
from services.moneyline_comparison_service import MoneylineComparisonService
from services.moneyline_discovery_service import MoneylineDiscoveryService
from services.moneyline_arbitrage_service import MoneylineArbitrageService
from services.multi_bookmaker_comparison_service import MultiBookmakerComparisonService
from services.moneyline_opportunity_scanner import MoneylineOpportunityScanner
from services.opportunity_scanner import OpportunityScanner
from services.report_generator import ReportGenerator


def configure_logging(diagnostic: bool = False) -> None:
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if diagnostic:
        handlers.append(logging.FileHandler(settings.output_dir / "diagnostic.log", mode="w", encoding="utf-8"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=handlers,
        force=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only odds comparison and diagnostics.")
    parser.add_argument(
        "--mode",
        choices=["arbitrage", "diagnostic", "check-config", "compare", "suggest-aliases", "scan-opportunities", "analyze-arbitrage", "watch", "market-discovery", "matchbook-market-discovery", "moneyline-discovery", "compare-moneyline", "scan-moneyline-opportunities", "analyze-moneyline-arbitrage", "watch-moneyline", "odds-api-bookmakers", "odds-api-usage", "compare-multi-bookmakers", "watch-multi-bookmakers"],
        default="arbitrage",
        help="Execution mode. Use diagnostic, check-config, compare, suggest-aliases, scan-opportunities, analyze-arbitrage, watch, market-discovery, matchbook-market-discovery, moneyline-discovery, compare-moneyline, scan-moneyline-opportunities, analyze-moneyline-arbitrage, watch-moneyline, odds-api-bookmakers, odds-api-usage, compare-multi-bookmakers, or watch-multi-bookmakers.",
    )
    parser.add_argument(
        "--api",
        choices=["betfair", "matchbook", "matchbook-br", "betfair-matchbook-br", "both"],
        default="both",
        help="API target for diagnostic or compare mode.",
    )
    return parser.parse_args()


def run_check_config() -> None:
    checker = ConfigChecker(settings)
    checker.print_report(checker.run())


def run_diagnostic(api_target: str) -> None:
    logger = logging.getLogger("main")
    logger.info("Starting read-only diagnostic mode for target=%s", api_target)
    report = DiagnosticRunner(settings).run(api_target)
    print("\nDiagnostic report saved to outputs/diagnostic_report.json")
    print("Diagnostic log saved to outputs/diagnostic.log")
    print(pformat(report, sort_dicts=False))


def run_compare(api_target: str) -> None:
    if api_target != "betfair-matchbook-br":
        raise ValueError("Compare mode currently supports only --api betfair-matchbook-br")

    logger = logging.getLogger("main")
    logger.info("Starting read-only comparison for Betfair x Matchbook Brasil. No bets will be placed.")
    betfair_rows = BetfairClient(settings).fetch_future_football_markets()
    matchbook_br_rows = MatchbookBRClient(settings).get_normalized_odds()
    report = ComparisonService(
        output_dir=settings.output_dir,
        max_start_delta_minutes=settings.max_start_time_delta_minutes,
        min_event_match_confidence=settings.min_event_match_confidence,
        aliases_path=settings.team_aliases_path,
    ).compare_betfair_matchbook_br(betfair_rows, matchbook_br_rows)
    print("\nComparison report saved to outputs/comparison_report.json")
    print("Comparison CSV saved to outputs/comparison_report.csv")
    print(
        pformat(
            {
                "total_events_betfair": report["total_events_betfair"],
                "total_events_matchbook_br": report["total_events_matchbook_br"],
                "paired_events_count": report["paired_events_count"],
                "unpaired_events_count": report["unpaired_events_count"],
                "paired_selections_count": report["paired_selections_count"],
                "biggest_odds_difference": report["biggest_odds_difference"],
            },
            sort_dicts=False,
        )
    )

def run_suggest_aliases() -> None:
    logger = logging.getLogger("main")
    logger.info("Starting alias suggestion from unpaired event CSVs. No aliases will be applied automatically.")
    report = AliasSuggestionService(
        output_dir=settings.output_dir,
        max_start_delta_minutes=settings.max_start_time_delta_minutes,
        min_score=0.75,
    ).suggest()
    print("\nSuggested aliases saved to outputs/suggested_team_aliases.json")
    print("Suggested event pairs saved to outputs/suggested_event_pairs.csv")
    print(
        pformat(
            {
                "suggested_event_pairs_count": report["suggested_event_pairs_count"],
                "suggested_aliases_count": report["suggested_aliases_count"],
                "min_score": report["min_score"],
            },
            sort_dicts=False,
        )
    )

def run_scan_opportunities() -> None:
    logger = logging.getLogger("main")
    logger.info("Starting read-only opportunity scan from comparison_report.json. No stakes, arbitrage, alerts or bets will be calculated.")
    report = OpportunityScanner(
        output_dir=settings.output_dir,
        min_match_confidence=0.90,
        min_difference_percent=settings.min_odds_difference_percent,
        min_liquidity_betfair=settings.min_liquidity_betfair,
        min_liquidity_matchbook_br=settings.min_liquidity_matchbook_br,
        betfair_commission=settings.commissions.betfair,
        matchbook_br_commission=settings.commissions.matchbook_br,
        limit=50,
    ).scan()
    print("\nOpportunities saved to outputs/opportunities.json")
    print("Opportunities CSV saved to outputs/opportunities.csv")
    print(
        pformat(
            {
                "total_compared_selections": report["total_compared_selections"],
                "total_candidates_after_filters": report["total_candidates_after_filters"],
                "min_match_confidence": report["min_match_confidence"],
                "min_difference_percent": report["min_difference_percent"],
                "min_liquidity_betfair": report["min_liquidity_betfair"],
                "min_liquidity_matchbook_br": report["min_liquidity_matchbook_br"],
                "top_opportunities": report["top_opportunities"][:10],
            },
            sort_dicts=False,
        )
    )

def run_analyze_arbitrage() -> None:
    logger = logging.getLogger("main")
    logger.info("Starting read-only arbitrage analysis from opportunities.json. No bets will be placed.")
    report = ArbitrageAnalyzer(
        output_dir=settings.output_dir,
        min_liquidity_betfair=settings.min_liquidity_betfair,
        min_liquidity_matchbook_br=settings.min_liquidity_matchbook_br,
        betfair_commission=settings.commissions.betfair,
        matchbook_br_commission=settings.commissions.matchbook_br,
    ).analyze()
    print("\nArbitrage analysis saved to outputs/arbitrage_analysis.json")
    print("Arbitrage analysis CSV saved to outputs/arbitrage_analysis.csv")

    results = report.get("results", [])
    possible_count = report.get("total_possible_arbitrages", 0)
    print(f"\nTotal evaluated opportunities: {report.get('total_evaluated', 0)}")
    print(f"Total possible arbitrage opportunities: {possible_count}")

    if results:
        print("\n--- Top Opportunities Rank ---")
        header = f"{'Event':<45} | {'Selection':<15} | {'Back Src':<12} | {'Lay Src':<12} | {'Back Net':<8} | {'Lay Net':<8} | {'Gap %':<10} | {'Reason'}"
        print(header)
        print("-" * len(header))
        for row in results[:15]:
            gap_str = "ARBITRAGE" if row['possible_arbitrage'] else (f"{row['gap_to_arbitrage_percent']:.4f}%" if row['gap_to_arbitrage_percent'] is not None else "N/A")
            back_net_str = f"{row['current_back_net_odds']:.4f}" if row['current_back_net_odds'] is not None else "N/A"
            lay_net_str = f"{row['current_lay_net_odds']:.4f}" if row['current_lay_net_odds'] is not None else "N/A"
            event_trunc = row['event'][:45] if row['event'] else ""
            print(f"{event_trunc:<45} | {row['selection']:<15} | {row['back_source'] or 'N/A':<12} | {row['lay_source'] or 'N/A':<12} | {back_net_str:<8} | {lay_net_str:<8} | {gap_str:<10} | {row['reason']}")


def run_watch() -> None:
    import time
    import json
    from datetime import datetime, timezone

    logger = logging.getLogger("main")
    logger.info("Starting read-only watch mode. Interval=%s seconds, Max Cycles=%s",
                settings.watch_interval_seconds, settings.watch_max_cycles)

    cycle = 0
    history_path = settings.output_dir / "watch_history.jsonl"

    try:
        while True:
            cycle += 1
            cycle_start_time = time.time()
            started_at_str = datetime.now(timezone.utc).isoformat()

            logger.info("--- Watch Cycle %s Start ---", cycle)
            print(f"\n[Ciclo {cycle}] Iniciando coleta e análise...")

            status = "success"
            error_message = None

            total_compared = None
            total_candidates = None
            total_possible = None
            best_gap_percent = None
            best_event = None
            best_selection = None
            best_back_src = None
            best_lay_src = None

            try:
                # 1. Compare
                bf_client = BetfairClient(settings)
                betfair_rows = bf_client.fetch_future_football_markets()
                if not betfair_rows and bf_client.errors:
                    raise RuntimeError("Failed to fetch football markets from Betfair: " + "; ".join(bf_client.errors))

                mb_client = MatchbookBRClient(settings)
                matchbook_br_rows = mb_client.get_normalized_odds()
                if not matchbook_br_rows and mb_client.errors:
                    raise RuntimeError("Failed to fetch football markets from Matchbook BR: " + "; ".join(mb_client.errors))

                ComparisonService(
                    output_dir=settings.output_dir,
                    max_start_delta_minutes=settings.max_start_time_delta_minutes,
                    min_event_match_confidence=settings.min_event_match_confidence,
                    aliases_path=settings.team_aliases_path,
                ).compare_betfair_matchbook_br(betfair_rows, matchbook_br_rows)

                # 2. Scan
                scan_report = OpportunityScanner(
                    output_dir=settings.output_dir,
                    min_match_confidence=0.90,
                    min_difference_percent=settings.min_odds_difference_percent,
                    min_liquidity_betfair=settings.min_liquidity_betfair,
                    min_liquidity_matchbook_br=settings.min_liquidity_matchbook_br,
                    betfair_commission=settings.commissions.betfair,
                    matchbook_br_commission=settings.commissions.matchbook_br,
                    limit=50,
                ).scan()

                # 3. Analyze
                analyzer_report = ArbitrageAnalyzer(
                    output_dir=settings.output_dir,
                    min_liquidity_betfair=settings.min_liquidity_betfair,
                    min_liquidity_matchbook_br=settings.min_liquidity_matchbook_br,
                    betfair_commission=settings.commissions.betfair,
                    matchbook_br_commission=settings.commissions.matchbook_br,
                ).analyze()

                # Extract metrics
                total_compared = scan_report.get("total_compared_selections", 0)
                total_candidates = scan_report.get("total_candidates_after_filters", 0)
                total_possible = analyzer_report.get("total_possible_arbitrages", 0)

                results = analyzer_report.get("results", [])
                if results:
                    best_item = results[0]
                    best_event = best_item.get("event")
                    best_selection = best_item.get("selection")
                    best_back_src = best_item.get("back_source")
                    best_lay_src = best_item.get("lay_source")
                    if best_item.get("possible_arbitrage"):
                        best_gap_percent = 0.0
                    else:
                        best_gap_percent = best_item.get("gap_to_arbitrage_percent")

            except Exception as exc:
                status = "failed"
                error_message = str(exc)
                logger.exception("Error in watch cycle %s", cycle)
                print(f"[Ciclo {cycle}] Falhou: {error_message}")

            finished_at_str = datetime.now(timezone.utc).isoformat()
            duration_seconds = round(time.time() - cycle_start_time, 2)

            history_entry = {
                "timestamp": started_at_str,
                "cycle_number": cycle,
                "started_at": started_at_str,
                "finished_at": finished_at_str,
                "duration_seconds": duration_seconds,
                "status": status,
                "error_message": error_message,
                "total_compared_selections": total_compared,
                "total_candidates_after_filters": total_candidates,
                "total_possible_arbitrage": total_possible,
                "best_gap_to_arbitrage_percent": best_gap_percent,
                "best_event": best_event,
                "best_selection": best_selection,
                "best_back_source": best_back_src,
                "best_lay_source": best_lay_src,
            }

            # Save history entry
            try:
                settings.output_dir.mkdir(parents=True, exist_ok=True)
                with history_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(history_entry, ensure_ascii=False) + "\n")
            except Exception as io_err:
                logger.error("Failed to write to watch_history.jsonl: %s", io_err)

            # Print simple summary to terminal
            if status == "success":
                print(f"[Ciclo {cycle} OK] Duração: {duration_seconds}s | Comparados: {total_compared} | Candidatos: {total_candidates} | Surebets: {total_possible}")
                if best_event:
                    opp_type = "SUREBET!" if total_possible > 0 else f"Gap: {best_gap_percent}%"
                    print(f"  Melhor Oportunidade: {best_event} ({best_selection}) | Back: {best_back_src} | Lay: {best_lay_src} | {opp_type}")
                else:
                    print("  Nenhuma oportunidade candidata encontrada.")
            else:
                print(f"[Ciclo {cycle} ERRO] Duração: {duration_seconds}s | Status: {status} | Erro: {error_message}")

            # Check max cycles limit
            if settings.watch_max_cycles > 0 and cycle >= settings.watch_max_cycles:
                logger.info("Reached WATCH_MAX_CYCLES=%s. Stopping watch mode.", settings.watch_max_cycles)
                print(f"\nLimite de ciclos alcançado ({settings.watch_max_cycles}). Parando watch.")
                break

            # Calculate sleep
            elapsed = time.time() - cycle_start_time
            sleep_time = max(0.0, settings.watch_interval_seconds - elapsed)
            if sleep_time > 0:
                logger.info("Sleeping for %.2f seconds until next cycle...", sleep_time)
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        logger.info("Watch loop interrupted by user.")
        print("\nWatch encerrado pelo usuário.")


def run_market_discovery() -> None:
    logger = logging.getLogger("main")
    logger.info("Starting read-only market and sport discovery mode. No bets or arbitrage will be calculated.")
    betfair_client = BetfairClient(settings)
    matchbook_br_client = MatchbookBRClient(settings)
    catalog = MarketDiscoveryService(
        output_dir=settings.output_dir,
        betfair_client=betfair_client,
        matchbook_br_client=matchbook_br_client,
    ).discover()

    print("\nSports catalog saved to outputs/sports_catalog.json")
    print("Market types catalog saved to outputs/market_types_catalog.json")

    # Print summary for Betfair
    bf_sports = catalog["sports"]["betfair"]
    print("\n=== BETFAIR ACTIVE SPORTS ===")
    header = f"{'Sport Name (ID)':<30} | {'Active Events':<15} | {'Market Types Count':<20} | {'Selections Count'}"
    print(header)
    print("-" * len(header))
    for sp in bf_sports:
        # Show sports with active events or total markets
        if sp.get("event_count", 0) > 0 or sp.get("total_markets_on_exchange", 0) > 0:
            sport_label = f"{sp['sport_name']} ({sp['sport_id']})"
            types_count = len(sp.get("market_types", []))
            print(f"{sport_label:<30} | {sp.get('event_count', 0):<15} | {types_count:<20} | {sp.get('selection_count', 0)}")

    # Print summary for Matchbook BR
    mb_sports = catalog["sports"]["matchbook_br"]
    print("\n=== MATCHBOOK BR ACTIVE SPORTS ===")
    print(header)
    print("-" * len(header))
    for sp in mb_sports:
        if sp.get("event_count", 0) > 0:
            sport_label = f"{sp['sport_name']} ({sp['sport_id']})"
            types_count = len(sp.get("market_types", []))
            print(f"{sport_label:<30} | {sp.get('event_count', 0):<15} | {types_count:<20} | {sp.get('selection_count', 0)}")


def run_matchbook_market_discovery() -> None:
    logger = logging.getLogger("main")
    logger.info("Starting read-only Matchbook BR regional market and sport discovery mode. No bets, cookies or Telegram will be used.")
    client = MatchbookBRClient(settings)
    catalog = MatchbookMarketDiscoveryService(
        output_dir=settings.output_dir,
        client=client,
    ).discover()

    print("\nMatchbook BR Navigation Tree saved to outputs/matchbook_navigation_tree.json")
    print("Matchbook BR Sports catalog saved to outputs/matchbook_sports_catalog.json")
    print("Matchbook BR Market catalog saved to outputs/matchbook_market_catalog.json")
    print("Matchbook BR Market Types summary saved to outputs/matchbook_market_types_summary.json")

    # Print summary for Matchbook BR sports
    mb_sports = catalog["sports"]
    print("\n=== MATCHBOOK BR ACTIVE SPORTS ===")
    header = f"{'Sport Name (ID)':<30} | {'Active Events':<15} | {'Market Count':<15} | {'Selections Count'}"
    print(header)
    print("-" * len(header))
    for sp in mb_sports:
        if sp.get("event_count", 0) > 0:
            sport_label = f"{sp['sport_name']} ({sp['sport_id']})"
            print(f"{sport_label:<30} | {sp.get('event_count', 0):<15} | {sp.get('market_count', 0):<15} | {sp.get('selection_count', 0)}")

    # Print summary for Matchbook BR market types
    print("\n=== MATCHBOOK BR MARKET TYPES FOUND ===")
    header_mt = f"{'Market Type':<30} | {'Count'}"
    print(header_mt)
    print("-" * len(header_mt))
    for mt_name, mt_count in catalog["market_types_summary"].items():
        print(f"{mt_name:<30} | {mt_count}")


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


def run_arbitrage() -> None:
    logger = logging.getLogger("main")
    logger.info("Starting read-only odds comparison. Real betting is not implemented in this version.")

    betfair_client = BetfairClient(settings)
    matchbook_client = MatchbookClient(settings)

    betfair_rows = betfair_client.fetch_future_football_markets()
    matchbook_rows = matchbook_client.fetch_future_football_markets()
    logger.info("Normalized rows: Betfair=%s Matchbook=%s", len(betfair_rows), len(matchbook_rows))

    mapper = MarketMapper(max_start_delta_minutes=settings.max_start_time_delta_minutes)
    matched_rows = mapper.match_markets(betfair_rows, matchbook_rows)
    logger.info("Equivalent pairs found: %s", len(matched_rows))

    calculator = ArbitrageCalculator(
        commissions={
            "betfair": settings.commissions.betfair,
            "matchbook": settings.commissions.matchbook,
        },
        stake_total=settings.stake_total,
        min_margin=settings.min_margin,
    )
    opportunities = calculator.find_opportunities(matched_rows)

    if opportunities:
        print("\nSimulated surebets found:")
        for opportunity in opportunities:
            print(pformat(opportunity, sort_dicts=False))
    else:
        print("\nNo simulated surebet found with the current filters.")

    ReportGenerator(settings.output_dir).save(opportunities)


def main() -> None:
    args = parse_args()
    configure_logging(diagnostic=args.mode == "diagnostic")
    if args.mode == "check-config":
        run_check_config()
    elif args.mode == "diagnostic":
        run_diagnostic(args.api)
    elif args.mode == "compare":
        run_compare(args.api)
    elif args.mode == "suggest-aliases":
        run_suggest_aliases()
    elif args.mode == "scan-opportunities":
        run_scan_opportunities()
    elif args.mode == "analyze-arbitrage":
        run_analyze_arbitrage()
    elif args.mode == "watch":
        run_watch()
    elif args.mode == "market-discovery":
        run_market_discovery()
    elif args.mode == "matchbook-market-discovery":
        run_matchbook_market_discovery()
    elif args.mode == "moneyline-discovery":
        run_moneyline_discovery()
    elif args.mode == "compare-moneyline":
        run_compare_moneyline()
    elif args.mode == "scan-moneyline-opportunities":
        run_scan_moneyline_opportunities()
    elif args.mode == "analyze-moneyline-arbitrage":
        run_analyze_moneyline_arbitrage()
    elif args.mode == "watch-moneyline":
        run_watch_moneyline()
    elif args.mode == "odds-api-bookmakers":
        run_odds_api_bookmakers()
    elif args.mode == "odds-api-usage":
        run_odds_api_usage()
    elif args.mode == "compare-multi-bookmakers":
        run_compare_multi_bookmakers()
    elif args.mode == "watch-multi-bookmakers":
        run_watch_multi_bookmakers()
    else:
        run_arbitrage()


if __name__ == "__main__":
    main()





