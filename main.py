"""Read-only odds comparison between Betfair Exchange and Matchbook."""

from __future__ import annotations

import argparse
import logging
from pprint import pformat

from clients.betfair_client import BetfairClient
from clients.matchbook_br_client import MatchbookBRClient
from clients.matchbook_client import MatchbookClient
from bookmakers.novibet.novibet_client import NovibetClient
from config.settings import settings
from services.alias_suggestion_service import AliasSuggestionService
from services.arbitrage_analyzer import ArbitrageAnalyzer
from services.arbitrage_calculator import ArbitrageCalculator
from services.comparison_service import ComparisonService
from services.config_checker import ConfigChecker
from services.cli_moneyline import (
    run_analyze_moneyline_arbitrage,
    run_compare_moneyline,
    run_moneyline_discovery,
    run_scan_moneyline_opportunities,
    run_watch_moneyline,
)
from services.cli_multi_bookmaker import (
    run_compare_multi_bookmakers,
    run_odds_api_bookmakers,
    run_odds_api_usage,
    run_watch_multi_bookmakers,
)
from services.diagnostic_runner import DiagnosticRunner
from services.market_discovery_service import MarketDiscoveryService
from services.market_mapper import MarketMapper
from services.matchbook_market_discovery_service import MatchbookMarketDiscoveryService
from services.opportunity_engine_service import OpportunityEngineService
from services.opportunity_scanner import OpportunityScanner
from services.opportunity_quality_review_service import OpportunityQualityReviewService
from services.opportunity_alert_service import OpportunityAlertService
from services.novibet_catalog_service import NovibetCatalogService
from services.bookmaker_discovery_service import BookmakerDiscoveryService, DiscoveryConfig
from services.bookmaker_intelligence_service import BookmakerIntelligenceService
from services.refresh_pipeline_service import RefreshPipelineService
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
        choices=["arbitrage", "diagnostic", "check-config", "compare", "suggest-aliases", "scan-opportunities", "analyze-arbitrage", "calculate-opportunities", "review-opportunity-quality", "generate-opportunity-alerts", "refresh-pipeline", "inspect-novibet", "bookmaker-discovery", "bookmaker-discovery-debug", "bookmaker-discovery-report", "bookmaker-intelligence", "watch", "market-discovery", "matchbook-market-discovery", "moneyline-discovery", "compare-moneyline", "scan-moneyline-opportunities", "analyze-moneyline-arbitrage", "watch-moneyline", "odds-api-bookmakers", "odds-api-usage", "compare-multi-bookmakers", "watch-multi-bookmakers"],
        default="arbitrage",
        help="Execution mode. Use diagnostic, check-config, compare, suggest-aliases, scan-opportunities, analyze-arbitrage, calculate-opportunities, review-opportunity-quality, generate-opportunity-alerts, refresh-pipeline, inspect-novibet, bookmaker-discovery, bookmaker-discovery-debug, bookmaker-discovery-report, bookmaker-intelligence, watch, market-discovery, matchbook-market-discovery, moneyline-discovery, compare-moneyline, scan-moneyline-opportunities, analyze-moneyline-arbitrage, watch-moneyline, odds-api-bookmakers, odds-api-usage, compare-multi-bookmakers, or watch-multi-bookmakers.",
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


def run_calculate_opportunities() -> None:
    logger = logging.getLogger("main")
    logger.info("Starting read-only opportunity calculation from multi_bookmaker_discrepancy_report.json. No bets will be placed.")
    report = OpportunityEngineService(
        output_dir=settings.output_dir,
        stake_total=settings.stake_total,
    ).calculate()

    print(f"\nCalculated opportunities saved to {settings.output_dir / 'calculated_opportunities.json'}")
    print(f"Calculated opportunities CSV saved to {settings.output_dir / 'calculated_opportunities.csv'}")
    print(f"Opportunity history appended to {settings.output_dir / 'opportunity_watch_history.jsonl'}")
    print(
        pformat(
            {
                "status": report["status"],
                "total_candidates": report["total_candidates"],
                "total_supported": report["total_supported"],
                "total_surebets": report["total_surebets"],
                "best_roi_percent": report["best_roi_percent"],
                "best_event": report["best_event"],
                "best_market": report["best_market"],
                "best_guaranteed_profit": report["best_guaranteed_profit"],
            },
            sort_dicts=False,
        )
    )


def run_review_opportunity_quality() -> None:
    logger = logging.getLogger("main")
    logger.info("Starting read-only opportunity quality review from calculated local outputs.")
    report = OpportunityQualityReviewService(output_dir=settings.output_dir).review()

    print(f"\nOpportunity quality review saved to {settings.output_dir / 'opportunity_quality_review.json'}")
    print(f"Opportunity quality review CSV saved to {settings.output_dir / 'opportunity_quality_review.csv'}")
    print(
        pformat(
            {
                "total_candidates": report["total_candidates"],
                "total_surebets": report["total_surebets"],
                "surebet_rate_percent": report["surebet_rate_percent"],
                "best_roi_percent": report["best_roi_percent"],
                "best_event": report["best_event"],
                "closest_distance_to_surebet_percent": report["closest_distance_to_surebet_percent"],
                "total_cross_bookmaker_candidates": report["total_cross_bookmaker_candidates"],
                "total_cross_bookmaker_surebets": report["total_cross_bookmaker_surebets"],
                "history_rows": report["historical_analysis"]["total_history_rows"],
            },
            sort_dicts=False,
        )
    )


def run_generate_opportunity_alerts() -> None:
    logger = logging.getLogger("main")
    logger.info("Starting read-only opportunity alert generation from local calculated outputs.")
    report = OpportunityAlertService(
        output_dir=settings.output_dir,
        near_miss_threshold_percent=settings.alert_near_miss_distance_percent,
    ).generate()
    summary = report["summary"]

    print("\nAlerts generated:")
    print(f"Surebets: {summary['total_surebet_alerts']}")
    print(f"Near misses: {summary['total_near_miss_alerts']}")
    print(f"Total alerts: {summary['total_alerts']}")
    print(f"Near miss threshold: {report['near_miss_threshold_percent']}%")
    print(f"Alerts JSON saved to {settings.output_dir / 'opportunity_alerts.json'}")
    print(f"Alerts CSV saved to {settings.output_dir / 'opportunity_alerts.csv'}")
    print(f"Alert history appended to {settings.output_dir / 'opportunity_alert_history.jsonl'}")


def run_refresh_pipeline() -> None:
    logger = logging.getLogger("main")
    logger.info("Starting manual read-only refresh pipeline from local output files only.")
    report = RefreshPipelineService(
        output_dir=settings.output_dir,
        stake_total=settings.stake_total,
        near_miss_threshold_percent=settings.alert_near_miss_distance_percent,
    ).run()
    summary = report["summary"]

    print("\nPipeline completed" if report["status"] == "success" else "\nPipeline completed with warnings")
    print(f"\nCandidates: {summary['candidates']}")
    print(f"Supported: {summary['supported']}")
    print(f"Surebets: {summary['surebets']}")
    print(f"Near Misses: {summary['near_misses']}")
    print(f"\nBest ROI: {summary['best_roi_percent']}")
    print(f"Best Event: {summary['best_event']}")
    if report.get("errors"):
        print("\nWarnings:")
        for error in report["errors"]:
            print(f"- {error['step']}: {error['error']}")
    print("\nGenerated files:")
    print("- calculated_opportunities.json")
    print("- opportunity_quality_review.json")
    print("- opportunity_alerts.json")
    print("- latest_pipeline_summary.json")
    print("- pipeline_refresh_history.jsonl")


def run_inspect_novibet() -> None:
    logger = logging.getLogger("main")
    logger.info("Starting read-only Novibet public inspection. No login, clicks, stakes or bets will be performed.")
    report = NovibetCatalogService(
        output_dir=settings.output_dir,
        client=NovibetClient(settings),
    ).inspect()

    print(f"\nNovibet raw sample saved to {settings.output_dir / 'novibet_raw_sample.json'}")
    print(f"Novibet normalized sample saved to {settings.output_dir / 'novibet_normalized_sample.json'}")
    print(f"Novibet inspection report saved to {settings.output_dir / 'novibet_inspection_report.json'}")
    print(
        pformat(
            {
                "status": report["status"],
                "target_url": report["target_url"],
                "final_url": report.get("final_url"),
                "page_title": report.get("page_title"),
                "raw_events_count": report["raw_events_count"],
                "normalized_odds_count": report["normalized_odds_count"],
                "blocked_action_selectors_detected": report["blocked_action_selectors_detected"],
                "betting_actions_performed": report["betting_actions_performed"],
                "errors": report.get("errors", []),
            },
            sort_dicts=False,
        )
    )


def _bookmaker_discovery_config() -> DiscoveryConfig:
    return DiscoveryConfig(
        username=settings.surebet_username,
        password=settings.surebet_password,
        base_url=settings.surebet_base_url,
        output_dir=settings.surebet_discovery_output_dir,
        poll_seconds=settings.surebet_discovery_poll_seconds,
        max_cycles=settings.surebet_discovery_max_cycles,
        headless=settings.surebet_discovery_headless,
        min_profit_change=settings.surebet_discovery_min_profit_change,
        odds_change_epsilon=settings.surebet_discovery_odds_change_epsilon,
    )


def run_bookmaker_discovery() -> None:
    logger = logging.getLogger("main")
    logger.info("Starting read-only SureBet.com bookmaker discovery. No bets, betslip actions or bookmaker links will be opened.")
    service = BookmakerDiscoveryService(_bookmaker_discovery_config())
    report = service.run()
    top_five = report.get("recommended_top_5", [])[:5]
    print(f"\nBookmaker discovery database: {settings.surebet_discovery_output_dir / 'bookmaker_discovery.db'}")
    print(f"Bookmaker discovery report: {settings.surebet_discovery_output_dir / 'bookmaker_discovery_report.json'}")
    print("\nTop 5 provisional bookmakers:")
    if not top_five:
        print("No bookmakers ranked yet.")
    for index, row in enumerate(top_five, start=1):
        print(f"{index}. {row['bookmaker']} | score={row['score']} | appearances={row['appearances']} | avg_profit={row['avg_profit_percent']}% | max_profit={row['max_profit_percent']}%")


def run_bookmaker_discovery_report() -> None:
    logger = logging.getLogger("main")
    logger.info("Generating read-only SureBet.com bookmaker discovery reports from local SQLite only.")
    service = BookmakerDiscoveryService(_bookmaker_discovery_config())
    report = service.generate_report_only()
    top_five = report.get("recommended_top_5", [])[:5]
    print(f"\nBookmaker discovery report regenerated at {settings.surebet_discovery_output_dir / 'bookmaker_discovery_report.json'}")
    print("Top 5 provisional bookmakers:")
    if not top_five:
        print("No bookmakers ranked yet.")
    for index, row in enumerate(top_five, start=1):
        print(f"{index}. {row['bookmaker']} | score={row['score']} | appearances={row['appearances']} | avg_profit={row['avg_profit_percent']}% | max_profit={row['max_profit_percent']}%")


def run_bookmaker_discovery_debug() -> None:
    logger = logging.getLogger("main")
    logger.info("Starting read-only SureBet.com bookmaker discovery DOM debug mode.")
    service = BookmakerDiscoveryService(_bookmaker_discovery_config())
    summary = service.run_debug()
    debug_dir = settings.surebet_discovery_output_dir / "debug"
    print("\nBookmaker discovery debug snapshot saved:")
    print(f"- {debug_dir / 'page.html'}")
    print(f"- {debug_dir / 'page.png'}")
    print(f"- {debug_dir / 'dom_summary.json'}")
    print(f"- {debug_dir / 'visible_text.txt'}")
    print(
        pformat(
            {
                "url": summary.get("url"),
                "title": summary.get("title"),
                "looks_authenticated": summary.get("looks_authenticated"),
                "elements_containing_percent_count": summary.get("elements_containing_percent_count"),
                "elements_containing_known_bookmakers_count": summary.get("elements_containing_known_bookmakers_count"),
                "parser_dom_extracted_count": summary.get("parser_dom_extracted_count"),
                "parser_visible_text_extracted_count": summary.get("parser_visible_text_extracted_count"),
            },
            sort_dicts=False,
        )
    )


def run_bookmaker_intelligence() -> None:
    logger = logging.getLogger("main")
    logger.info("Starting read-only bookmaker intelligence from local Bookmaker Discovery SQLite.")
    discovery_db = settings.surebet_discovery_output_dir / "bookmaker_discovery.db"
    output_dir = settings.output_dir / "bookmaker_intelligence"
    report = BookmakerIntelligenceService(discovery_db, output_dir).generate()
    summary = report["summary"]
    print("\nBookmaker intelligence generated:")
    print(f"Source DB: {discovery_db}")
    print(f"Output dir: {output_dir}")
    print(f"Observations: {summary['total_observations']}")
    print(f"Bookmakers: {summary['total_bookmakers']}")
    print(f"Pairs: {summary['total_pairs']}")
    print("Generated files:")
    print("- bookmaker_intelligence_report.json")
    print("- bookmaker_by_sport.csv")
    print("- bookmaker_by_market.csv")
    print("- bookmaker_by_hour.csv")
    print("- bookmaker_pair_strength.csv")
    print("- bookmaker_consistency.csv")
    print("- bookmaker_context_notes.json")


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
    elif args.mode == "calculate-opportunities":
        run_calculate_opportunities()
    elif args.mode == "review-opportunity-quality":
        run_review_opportunity_quality()
    elif args.mode == "generate-opportunity-alerts":
        run_generate_opportunity_alerts()
    elif args.mode == "refresh-pipeline":
        run_refresh_pipeline()
    elif args.mode == "inspect-novibet":
        run_inspect_novibet()
    elif args.mode == "bookmaker-discovery":
        run_bookmaker_discovery()
    elif args.mode == "bookmaker-discovery-debug":
        run_bookmaker_discovery_debug()
    elif args.mode == "bookmaker-discovery-report":
        run_bookmaker_discovery_report()
    elif args.mode == "bookmaker-intelligence":
        run_bookmaker_intelligence()
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


