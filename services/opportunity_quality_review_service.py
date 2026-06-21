"""Quality review for already calculated read-only opportunities."""

from __future__ import annotations

import csv
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CALCULATED_OPPORTUNITIES_NAME = "calculated_opportunities.json"
HISTORY_NAME = "opportunity_watch_history.jsonl"
REVIEW_JSON_NAME = "opportunity_quality_review.json"
REVIEW_CSV_NAME = "opportunity_quality_review.csv"


class OpportunityQualityReviewService:
    """Analyzes calculated opportunity outputs without changing the calculation pipeline."""

    def __init__(self, output_dir: Path, ranking_limit: int = 20) -> None:
        self.output_dir = output_dir
        self.ranking_limit = ranking_limit

    def review(self) -> dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).isoformat()
        calculated_path = self.output_dir / CALCULATED_OPPORTUNITIES_NAME
        history_path = self.output_dir / HISTORY_NAME

        calculated = self._read_json(calculated_path)
        opportunities = self._clean_opportunities(calculated.get("opportunities", []) if calculated else [])
        history_rows = self._read_jsonl(history_path)

        surebets = [row for row in opportunities if row["is_surebet"]]
        near_misses = [row for row in opportunities if not row["is_surebet"]]
        cross_candidates = [row for row in opportunities if row["is_cross_bookmaker"]]
        cross_surebets = [row for row in surebets if row["is_cross_bookmaker"]]
        distances = [row["distance_to_surebet_percent"] for row in opportunities]
        surebet_rois = [row["roi_percent"] for row in surebets]

        report = {
            "timestamp": timestamp,
            "source_calculated_opportunities": str(calculated_path),
            "source_history": str(history_path),
            "total_candidates": len(opportunities),
            "total_supported": self._int_value(calculated.get("total_supported") if calculated else None, len(opportunities)),
            "total_surebets": len(surebets),
            "surebet_rate_percent": self._percent(len(surebets), len(opportunities)),
            "best_roi_percent": max(surebet_rois, default=None),
            "best_event": self._best_surebet(surebets).get("event_name") if surebets else None,
            "best_market": self._best_surebet(surebets).get("market_type") if surebets else None,
            "best_guaranteed_profit": self._best_surebet(surebets).get("guaranteed_profit") if surebets else None,
            "closest_distance_to_surebet_percent": min(distances, default=None),
            "total_cross_bookmaker_candidates": len(cross_candidates),
            "total_cross_bookmaker_surebets": len(cross_surebets),
            "cross_bookmaker_surebet_rate_percent": self._percent(len(cross_surebets), len(cross_candidates)),
            "average_distance_to_surebet_percent": self._average(distances),
            "median_distance_to_surebet_percent": self._median(distances),
            "min_distance_to_surebet_percent": min(distances, default=None),
            "max_distance_to_surebet_percent": max(distances, default=None),
            "average_roi_percent_for_surebets": self._average(surebet_rois),
            "max_roi_percent_for_surebets": max(surebet_rois, default=None),
            "top_surebets": [self._ranking_row(row) for row in sorted(surebets, key=lambda item: item["roi_percent"], reverse=True)[: self.ranking_limit]],
            "top_near_misses": [self._ranking_row(row) for row in sorted(near_misses, key=lambda item: item["distance_to_surebet_percent"])[: self.ranking_limit]],
            "top_cross_bookmaker_near_misses": [
                self._ranking_row(row)
                for row in sorted(
                    [row for row in near_misses if row["is_cross_bookmaker"]],
                    key=lambda item: item["distance_to_surebet_percent"],
                )[: self.ranking_limit]
            ],
            "by_sport": self._group_analysis(opportunities, "sport", "sport"),
            "by_bookmaker_pair": self._group_analysis(opportunities, "bookmaker_pair_label", "bookmaker_pair"),
            "historical_analysis": self._history_analysis(history_rows),
        }

        self._write_outputs(report)
        return report

    def _read_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(payload, dict):
                        rows.append(payload)
        except OSError:
            return []
        return rows

    def _clean_opportunities(self, raw_rows: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_rows, list):
            return []
        rows: list[dict[str, Any]] = []
        for raw in raw_rows:
            if not isinstance(raw, dict):
                continue
            pair = raw.get("bookmaker_pair") or []
            if not isinstance(pair, list):
                pair = [str(pair)]
            pair = [str(item) for item in pair]
            is_surebet = bool(raw.get("is_surebet"))
            row = {
                "event_name": str(raw.get("event_name") or ""),
                "sport": str(raw.get("sport") or "unknown"),
                "market_type": str(raw.get("market_type") or ""),
                "start_time": raw.get("start_time"),
                "bookmaker_pair": pair,
                "bookmaker_pair_label": self._pair_label(pair),
                "is_cross_bookmaker": bool(raw.get("is_cross_bookmaker", len(set(pair)) > 1)),
                "implied_sum": self._float_value(raw.get("implied_sum") or raw.get("total_implied_probability")),
                "roi_percent": self._float_value(raw.get("roi_percent")),
                "distance_to_surebet_percent": self._float_value(raw.get("distance_to_surebet_percent")),
                "guaranteed_profit": self._float_value(raw.get("guaranteed_profit")),
                "worst_case_profit": self._float_value(raw.get("worst_case_profit")),
                "is_surebet": is_surebet,
            }
            rows.append(row)
        return rows

    def _group_analysis(self, opportunities: list[dict[str, Any]], key: str, output_key: str) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in opportunities:
            groups.setdefault(str(row.get(key) or "unknown"), []).append(row)

        analysis: list[dict[str, Any]] = []
        for group_key, rows in groups.items():
            distances = [row["distance_to_surebet_percent"] for row in rows]
            surebets = [row for row in rows if row["is_surebet"]]
            analysis.append(
                {
                    output_key: group_key,
                    "total_candidates": len(rows),
                    "total_surebets": len(surebets),
                    "average_distance_to_surebet_percent": self._average(distances),
                    "best_roi_percent": max((row["roi_percent"] for row in surebets), default=None),
                    "closest_distance_to_surebet_percent": min(distances, default=None),
                }
            )
        return sorted(analysis, key=lambda row: (-row["total_candidates"], str(row[output_key])))

    def _history_analysis(self, history_rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not history_rows:
            return {
                "total_history_rows": 0,
                "latest_history_timestamp": None,
                "history_best_roi_percent": None,
                "history_total_surebets_sum": 0,
                "history_best_event": None,
                "trend_last_rows": [],
            }
        best = max(
            history_rows,
            key=lambda row: self._float_value(row.get("best_roi_percent")),
        )
        return {
            "total_history_rows": len(history_rows),
            "latest_history_timestamp": history_rows[-1].get("timestamp"),
            "history_best_roi_percent": self._none_if_zero_when_missing(best.get("best_roi_percent")),
            "history_total_surebets_sum": sum(self._int_value(row.get("total_surebets"), 0) for row in history_rows),
            "history_best_event": best.get("best_event"),
            "trend_last_rows": history_rows[-10:],
        }

    def _write_outputs(self, report: dict[str, Any]) -> None:
        json_path = self.output_dir / REVIEW_JSON_NAME
        csv_path = self.output_dir / REVIEW_CSV_NAME
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        self._write_csv(csv_path, report)

    def _write_csv(self, csv_path: Path, report: dict[str, Any]) -> None:
        fieldnames = [
            "rank_type",
            "event_name",
            "sport",
            "market_type",
            "start_time",
            "bookmaker_pair",
            "is_cross_bookmaker",
            "implied_sum",
            "roi_percent",
            "distance_to_surebet_percent",
            "guaranteed_profit",
            "worst_case_profit",
        ]
        rows: list[dict[str, Any]] = []
        for rank_type in ("top_surebets", "top_near_misses", "top_cross_bookmaker_near_misses"):
            for item in report.get(rank_type, []):
                rows.append({"rank_type": rank_type, **item})

        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    def _ranking_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "event_name": row["event_name"],
            "sport": row["sport"],
            "market_type": row["market_type"],
            "start_time": row["start_time"],
            "bookmaker_pair": row["bookmaker_pair_label"],
            "is_cross_bookmaker": row["is_cross_bookmaker"],
            "implied_sum": row["implied_sum"],
            "roi_percent": row["roi_percent"],
            "distance_to_surebet_percent": row["distance_to_surebet_percent"],
            "guaranteed_profit": row["guaranteed_profit"],
            "worst_case_profit": row["worst_case_profit"],
        }

    def _best_surebet(self, surebets: list[dict[str, Any]]) -> dict[str, Any]:
        return max(surebets, key=lambda row: row["roi_percent"], default={})

    def _pair_label(self, pair: list[str]) -> str:
        return " x ".join(pair) if pair else "unknown"

    def _percent(self, numerator: int, denominator: int) -> float:
        if denominator <= 0:
            return 0.0
        return (numerator / denominator) * 100.0

    def _average(self, values: list[float]) -> float | None:
        if not values:
            return None
        return sum(values) / len(values)

    def _median(self, values: list[float]) -> float | None:
        if not values:
            return None
        return float(statistics.median(values))

    def _float_value(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _int_value(self, value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _none_if_zero_when_missing(self, value: Any) -> float | None:
        if value is None:
            return None
        return self._float_value(value)
