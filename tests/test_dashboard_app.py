from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dashboard_app import filter_alerts, load_json_file, load_jsonl_file, normalize_alert_rows


class DashboardAppTests(unittest.TestCase):
    def test_load_json_file_returns_payload_for_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.json"
            path.write_text(json.dumps({"summary": {"total_alerts": 2}}), encoding="utf-8")

            payload, status = load_json_file(path)

            self.assertEqual(payload["summary"]["total_alerts"], 2)
            self.assertEqual(status["state"], "ok")

    def test_load_json_file_handles_missing_file(self) -> None:
        payload, status = load_json_file(Path("missing-file.json"))

        self.assertEqual(payload, {})
        self.assertEqual(status["state"], "missing")

    def test_load_jsonl_file_ignores_invalid_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "history.jsonl"
            path.write_text('{"total_alerts": 1}\nnot-json\n{"total_alerts": 2}\n', encoding="utf-8")

            rows, status = load_jsonl_file(path)

            self.assertEqual([row["total_alerts"] for row in rows], [1, 2])
            self.assertEqual(status["state"], "ok")
            self.assertEqual(status["invalid_lines"], 1)

    def test_filter_alerts_by_type_sport_and_bookmaker_pair(self) -> None:
        alerts = [
            {"alert_type": "surebet", "sport": "baseball", "bookmaker_pair": ["pinnacle", "matchbook-br"]},
            {"alert_type": "near_miss", "sport": "mma", "bookmaker_pair": ["pinnacle", "pinnacle"]},
            {"alert_type": "near_miss", "sport": "baseball", "bookmaker_pair": ["pinnacle", "matchbook-br"]},
        ]

        filtered = filter_alerts(alerts, alert_type="near_miss", sport="baseball", bookmaker_pair="pinnacle x matchbook-br")

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["alert_type"], "near_miss")
        self.assertEqual(filtered[0]["sport"], "baseball")

    def test_normalize_alert_rows_keeps_display_only_shape(self) -> None:
        rows = normalize_alert_rows([
            {
                "alert_type": "surebet",
                "event_name": "Boston Red Sox at Seattle Mariners",
                "sport": "baseball",
                "market_type": "Money Line",
                "start_time": "2026-06-20T02:10:00Z",
                "bookmaker_pair": ["pinnacle", "matchbook-br"],
                "implied_sum": 0.999,
                "roi_percent": 0.075,
                "guaranteed_profit": 0.075,
                "stake_plan": {"stake_total": 100.0},
            }
        ])

        self.assertEqual(rows[0]["bookmaker_pair"], "pinnacle x matchbook-br")
        self.assertEqual(rows[0]["stake_plan"], '{"stake_total": 100.0}')
        self.assertNotIn("click", rows[0])
        self.assertNotIn("place_bet", rows[0])


if __name__ == "__main__":
    unittest.main()
