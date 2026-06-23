from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.refresh_pipeline_service import RefreshPipelineService


class _FakeEngine:
    def __init__(self, calls: list[str], report: dict | None = None, fail: bool = False) -> None:
        self.calls = calls
        self.report = report or {
            "total_candidates": 3,
            "total_supported": 2,
            "total_surebets": 1,
            "best_roi_percent": 1.25,
            "best_event": "Team A x Team B",
        }
        self.fail = fail

    def calculate(self) -> dict:
        self.calls.append("engine")
        if self.fail:
            raise RuntimeError("engine failed")
        return self.report


class _FakeReview:
    def __init__(self, calls: list[str], report: dict | None = None, fail: bool = False) -> None:
        self.calls = calls
        self.report = report or {"total_candidates": 3, "total_surebets": 1}
        self.fail = fail

    def review(self) -> dict:
        self.calls.append("review")
        if self.fail:
            raise RuntimeError("review failed")
        return self.report


class _FakeAlerts:
    def __init__(self, calls: list[str], report: dict | None = None, fail: bool = False) -> None:
        self.calls = calls
        self.report = report or {
            "summary": {
                "total_alerts": 2,
                "total_surebet_alerts": 1,
                "total_near_miss_alerts": 1,
            }
        }
        self.fail = fail

    def generate(self) -> dict:
        self.calls.append("alerts")
        if self.fail:
            raise RuntimeError("alerts failed")
        return self.report


class RefreshPipelineServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.output_dir = Path(self.temp_dir.name)

    def service(self, *, engine_fail: bool = False, review_fail: bool = False, alerts_fail: bool = False) -> tuple[RefreshPipelineService, list[str]]:
        calls: list[str] = []
        service = RefreshPipelineService(
            output_dir=self.output_dir,
            stake_total=100.0,
            near_miss_threshold_percent=2.0,
            engine_factory=lambda: _FakeEngine(calls, fail=engine_fail),
            review_factory=lambda: _FakeReview(calls, fail=review_fail),
            alert_factory=lambda: _FakeAlerts(calls, fail=alerts_fail),
        )
        return service, calls

    def test_runs_pipeline_in_sequence(self) -> None:
        service, calls = self.service()

        report = service.run()

        self.assertEqual(calls, ["engine", "review", "alerts"])
        self.assertEqual(report["status"], "success")
        self.assertEqual(report["summary"]["candidates"], 3)
        self.assertEqual(report["summary"]["supported"], 2)
        self.assertEqual(report["summary"]["surebets"], 1)
        self.assertEqual(report["summary"]["alerts"], 2)
        self.assertEqual(report["summary"]["near_misses"], 1)

    def test_generates_summary_and_history(self) -> None:
        service, _ = self.service()

        service.run()

        summary_path = self.output_dir / "latest_pipeline_summary.json"
        history_path = self.output_dir / "pipeline_refresh_history.jsonl"
        self.assertTrue(summary_path.exists())
        self.assertTrue(history_path.exists())

        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(summary["candidates"], 3)
        self.assertEqual(summary["alerts"], 2)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["total_near_miss_alerts"], 1)

    def test_missing_files_are_handled_by_underlying_services(self) -> None:
        service = RefreshPipelineService(
            output_dir=self.output_dir,
            stake_total=100.0,
            near_miss_threshold_percent=2.0,
        )

        report = service.run()

        self.assertIn(report["status"], {"success", "partial_success"})
        self.assertEqual(report["summary"]["candidates"], 0)
        self.assertTrue((self.output_dir / "latest_pipeline_summary.json").exists())
        self.assertTrue((self.output_dir / "pipeline_refresh_history.jsonl").exists())

    def test_step_errors_are_recorded_without_crashing(self) -> None:
        service, calls = self.service(engine_fail=True)

        report = service.run()

        self.assertEqual(calls, ["engine", "review", "alerts"])
        self.assertEqual(report["status"], "partial_success")
        self.assertEqual(report["summary"]["candidates"], 0)
        self.assertEqual(report["summary"]["alerts"], 2)
        self.assertEqual(report["errors"][0]["step"], "opportunity_engine")


if __name__ == "__main__":
    unittest.main()
