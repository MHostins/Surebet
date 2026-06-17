"""CSV and JSON report writer."""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)


class ReportGenerator:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save(self, opportunities: list[dict[str, Any]]) -> tuple[Path, Path]:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = self.output_dir / f"surebets_{timestamp}.json"
        csv_path = self.output_dir / f"surebets_{timestamp}.csv"

        json_path.write_text(json.dumps(opportunities, indent=2, ensure_ascii=False), encoding="utf-8")
        self._write_csv(csv_path, opportunities)
        LOGGER.info("Relatórios salvos em %s e %s", json_path, csv_path)
        return json_path, csv_path

    def _write_csv(self, path: Path, rows: list[dict[str, Any]]) -> None:
        fieldnames = sorted({key for row in rows for key in row.keys()})
        if not fieldnames:
            fieldnames = ["message"]
            rows = [{"message": "Nenhuma surebet encontrada"}]

        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
