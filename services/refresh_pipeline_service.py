"""Manual read-only refresh pipeline for analytical opportunity reports."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.opportunity_alert_service import OpportunityAlertService
from services.opportunity_engine_service import OpportunityEngineService
from services.opportunity_quality_review_service import OpportunityQualityReviewService

LOGGER = logging.getLogger(__name__)

PIPELINE_HISTORY_NAME = "pipeline_refresh_history.jsonl"
LATEST_SUMMARY_NAME = "latest_pipeline_summary.json"


class RefreshPipelineService:
    """Runs the local analytics chain without calling external APIs."""

    def __init__(
        self,
        output_dir: Path,
        stake_total: float,
        near_miss_threshold_percent: float,
        *,
        engine_factory: Callable[[], Any] | None = None,
        review_factory: Callable[[], Any] | None = None,
        alert_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.output_dir = output_dir
        self.stake_total = stake_total
        self.near_miss_threshold_percent = near_miss_threshold_percent
        self.engine_factory = engine_factory or (
            lambda: OpportunityEngineService(output_dir=self.output_dir, stake_total=self.stake_total)
        )
        self.review_factory = review_factory or (
            lambda: OpportunityQualityReviewService(output_dir=self.output_dir)
        )
        self.alert_factory = alert_factory or (
            lambda: OpportunityAlertService(
                output_dir=self.output_dir,
                near_miss_threshold_percent=self.near_miss_threshold_percent,
            )
        )

    def run(self) -> dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).isoformat()
        errors: list[dict[str, str]] = []

        engine_report = self._run_step("opportunity_engine", lambda: self.engine_factory().calculate(), errors)
        review_report = self._run_step("opportunity_quality_review", lambda: self.review_factory().review(), errors)
        alert_report = self._run_step("opportunity_alerts", lambda: self.alert_factory().generate(), errors)

        summary = self._build_summary(timestamp, engine_report, review_report, alert_report)
        status = "success" if not errors else "partial_success"
        report = {
            "timestamp": timestamp,
            "status": status,
            "summary": summary,
            "errors": errors,
            "generated_files": [
                "calculated_opportunities.json",
                "opportunity_quality_review.json",
                "opportunity_alerts.json",
                LATEST_SUMMARY_NAME,
                PIPELINE_HISTORY_NAME,
            ],
        }
        self._write_summary(summary)
        self._append_history(status, summary)
        return report

    def _run_step(
        self,
        step_name: str,
        callback: Callable[[], dict[str, Any]],
        errors: list[dict[str, str]],
    ) -> dict[str, Any]:
        try:
            report = callback()
        except Exception as exc:
            LOGGER.debug("Refresh pipeline step failed: %s: %s", step_name, exc)
            errors.append({"step": step_name, "error": str(exc)})
            return {}
        return report if isinstance(report, dict) else {}

    def _build_summary(
        self,
        timestamp: str,
        engine_report: dict[str, Any],
        review_report: dict[str, Any],
        alert_report: dict[str, Any],
    ) -> dict[str, Any]:
        alert_summary = alert_report.get("summary", {}) if isinstance(alert_report.get("summary"), dict) else {}
        return {
            "timestamp": timestamp,
            "candidates": self._int_value(engine_report.get("total_candidates"), 0),
            "supported": self._int_value(engine_report.get("total_supported"), 0),
            "surebets": self._int_value(engine_report.get("total_surebets"), 0),
            "alerts": self._int_value(alert_summary.get("total_alerts"), 0),
            "near_misses": self._int_value(alert_summary.get("total_near_miss_alerts"), 0),
            "best_roi_percent": self._first_present(
                engine_report.get("best_roi_percent"),
                review_report.get("best_roi_percent"),
            ),
            "best_event": self._first_present(
                engine_report.get("best_event"),
                review_report.get("best_event"),
            ),
        }

    def _write_summary(self, summary: dict[str, Any]) -> None:
        (self.output_dir / LATEST_SUMMARY_NAME).write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _append_history(self, status: str, summary: dict[str, Any]) -> None:
        entry = {
            "timestamp": summary["timestamp"],
            "status": status,
            "total_candidates": summary["candidates"],
            "total_supported": summary["supported"],
            "total_surebets": summary["surebets"],
            "total_alerts": summary["alerts"],
            "total_near_miss_alerts": summary["near_misses"],
            "best_roi_percent": summary["best_roi_percent"],
            "best_event": summary["best_event"],
        }
        with (self.output_dir / PIPELINE_HISTORY_NAME).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _int_value(self, *values: Any) -> int:
        for value in values:
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return 0

    def _first_present(self, *values: Any) -> Any:
        for value in values:
            if value is not None:
                return value
        return None
