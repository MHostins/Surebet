"""Read-only alert layer for calculated opportunities."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CALCULATED_OPPORTUNITIES_NAME = "calculated_opportunities.json"
QUALITY_REVIEW_NAME = "opportunity_quality_review.json"
WATCH_HISTORY_NAME = "opportunity_watch_history.jsonl"
ALERTS_JSON_NAME = "opportunity_alerts.json"
ALERTS_CSV_NAME = "opportunity_alerts.csv"
ALERT_HISTORY_NAME = "opportunity_alert_history.jsonl"


class OpportunityAlertService:
    """Generates surebet and near-miss alerts from local calculated opportunity outputs."""

    def __init__(self, output_dir: Path, near_miss_threshold_percent: float = 2.0) -> None:
        self.output_dir = output_dir
        self.near_miss_threshold_percent = near_miss_threshold_percent

    def generate(self) -> dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).isoformat()

        calculated_path = self.output_dir / CALCULATED_OPPORTUNITIES_NAME
        quality_path = self.output_dir / QUALITY_REVIEW_NAME
        watch_history_path = self.output_dir / WATCH_HISTORY_NAME

        calculated = self._read_json(calculated_path)
        quality_review = self._read_json(quality_path)
        watch_history = self._read_jsonl(watch_history_path)
        opportunities = self._clean_opportunities(calculated.get("opportunities", []) if calculated else [])

        surebet_alerts = [
            self._build_alert(row, "surebet", timestamp, index)
            for index, row in enumerate(
                sorted(
                    [row for row in opportunities if row["is_surebet"]],
                    key=lambda item: item["roi_percent"],
                    reverse=True,
                ),
                start=1,
            )
        ]
        near_miss_alerts = [
            self._build_alert(row, "near_miss", timestamp, index)
            for index, row in enumerate(
                sorted(
                    [
                        row for row in opportunities
                        if not row["is_surebet"]
                        and row["distance_to_surebet_percent"] <= self.near_miss_threshold_percent
                    ],
                    key=lambda item: item["distance_to_surebet_percent"],
                ),
                start=1,
            )
        ]
        alerts = surebet_alerts + near_miss_alerts
        best_surebet = surebet_alerts[0] if surebet_alerts else None
        closest_near_miss = near_miss_alerts[0] if near_miss_alerts else None

        report = {
            "timestamp": timestamp,
            "mode": "read_only_opportunity_alerts",
            "near_miss_threshold_percent": self.near_miss_threshold_percent,
            "sources": {
                "calculated_opportunities": str(calculated_path),
                "quality_review": str(quality_path),
                "opportunity_watch_history": str(watch_history_path),
                "quality_review_available": bool(quality_review),
                "watch_history_rows": len(watch_history),
            },
            "summary": {
                "total_alerts": len(alerts),
                "total_surebet_alerts": len(surebet_alerts),
                "total_near_miss_alerts": len(near_miss_alerts),
                "best_surebet": best_surebet,
                "closest_near_miss": closest_near_miss,
            },
            "rankings": {
                "top_surebets": surebet_alerts,
                "top_near_misses": near_miss_alerts,
            },
            "alerts": alerts,
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
            rows.append(
                {
                    "event_name": str(raw.get("event_name") or ""),
                    "sport": str(raw.get("sport") or "unknown"),
                    "market_type": str(raw.get("market_type") or ""),
                    "start_time": raw.get("start_time"),
                    "bookmaker_pair": pair,
                    "is_cross_bookmaker": bool(raw.get("is_cross_bookmaker", len(set(pair)) > 1)),
                    "implied_sum": self._float_value(raw.get("implied_sum") or raw.get("total_implied_probability")),
                    "roi_percent": self._float_value(raw.get("roi_percent")),
                    "distance_to_surebet_percent": self._float_value(raw.get("distance_to_surebet_percent")),
                    "guaranteed_profit": self._float_value(raw.get("guaranteed_profit")),
                    "worst_case_profit": self._float_value(raw.get("worst_case_profit")),
                    "stake_plan": raw.get("stake_plan") if isinstance(raw.get("stake_plan"), dict) else {},
                    "calculation_model": str(raw.get("calculation_model") or ""),
                    "optimization_model": str(raw.get("optimization_model") or ""),
                    "is_surebet": bool(raw.get("is_surebet")),
                }
            )
        return rows

    def _build_alert(self, row: dict[str, Any], alert_type: str, timestamp: str, index: int) -> dict[str, Any]:
        return {
            "alert_id": f"{alert_type}-{index:04d}",
            "alert_type": alert_type,
            "timestamp": timestamp,
            "event_name": row["event_name"],
            "sport": row["sport"],
            "market_type": row["market_type"],
            "start_time": row["start_time"],
            "bookmaker_pair": row["bookmaker_pair"],
            "is_cross_bookmaker": row["is_cross_bookmaker"],
            "implied_sum": row["implied_sum"],
            "roi_percent": row["roi_percent"],
            "distance_to_surebet_percent": row["distance_to_surebet_percent"],
            "guaranteed_profit": row["guaranteed_profit"],
            "worst_case_profit": row["worst_case_profit"],
            "stake_plan": row["stake_plan"],
            "calculation_model": row["calculation_model"],
            "optimization_model": row["optimization_model"],
        }

    def _write_outputs(self, report: dict[str, Any]) -> None:
        json_path = self.output_dir / ALERTS_JSON_NAME
        csv_path = self.output_dir / ALERTS_CSV_NAME
        history_path = self.output_dir / ALERT_HISTORY_NAME

        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        self._write_csv(csv_path, report.get("alerts", []))
        with history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(self._history_entry(report), ensure_ascii=False) + "\n")

    def _write_csv(self, csv_path: Path, alerts: list[dict[str, Any]]) -> None:
        fieldnames = [
            "alert_type",
            "event_name",
            "sport",
            "market_type",
            "start_time",
            "bookmaker_pair",
            "is_cross_bookmaker",
            "roi_percent",
            "distance_to_surebet_percent",
            "guaranteed_profit",
            "worst_case_profit",
        ]
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for alert in alerts:
                writer.writerow({
                    **alert,
                    "bookmaker_pair": " x ".join(alert.get("bookmaker_pair", [])),
                })

    def _history_entry(self, report: dict[str, Any]) -> dict[str, Any]:
        summary = report["summary"]
        best = summary.get("best_surebet") or {}
        closest = summary.get("closest_near_miss") or {}
        return {
            "timestamp": report["timestamp"],
            "total_alerts": summary["total_alerts"],
            "total_surebet_alerts": summary["total_surebet_alerts"],
            "total_near_miss_alerts": summary["total_near_miss_alerts"],
            "best_roi_percent": best.get("roi_percent"),
            "best_event": best.get("event_name"),
            "closest_distance_to_surebet_percent": closest.get("distance_to_surebet_percent"),
        }

    def _float_value(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
