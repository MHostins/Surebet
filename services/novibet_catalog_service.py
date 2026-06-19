"""Service for read-only Novibet public page inspection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bookmakers.novibet.novibet_client import NovibetClient


class NovibetCatalogService:
    """Runs a controlled read-only Novibet inspection and writes local samples."""

    RAW_SAMPLE_NAME = "novibet_raw_sample.json"
    NORMALIZED_SAMPLE_NAME = "novibet_normalized_sample.json"
    INSPECTION_REPORT_NAME = "novibet_inspection_report.json"

    def __init__(self, output_dir: Path, client: NovibetClient) -> None:
        self.output_dir = output_dir
        self.client = client

    def inspect(self) -> dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        report = self.client.inspect_public_page()

        raw_sample = report.get("raw_sample", {})
        normalized = report.get("normalized_odds", [])

        raw_path = self.output_dir / self.RAW_SAMPLE_NAME
        normalized_path = self.output_dir / self.NORMALIZED_SAMPLE_NAME
        report_path = self.output_dir / self.INSPECTION_REPORT_NAME

        raw_path.write_text(json.dumps(raw_sample, indent=2, ensure_ascii=False), encoding="utf-8")
        normalized_path.write_text(json.dumps(normalized[:100], indent=2, ensure_ascii=False), encoding="utf-8")

        report_for_disk = {
            **report,
            "raw_sample_path": str(raw_path),
            "normalized_sample_path": str(normalized_path),
        }
        report_path.write_text(json.dumps(report_for_disk, indent=2, ensure_ascii=False), encoding="utf-8")
        return report_for_disk
