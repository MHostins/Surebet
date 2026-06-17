"""Local configuration checks with secret-safe output."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from config.settings import Settings


class ConfigChecker:
    """Validates environment configuration without calling external APIs."""

    REQUIRED_VARIABLES = {
        "BETFAIR_USERNAME": "betfair_username",
        "BETFAIR_PASSWORD": "betfair_password",
        "BETFAIR_APP_KEY": "betfair_app_key",
        "MATCHBOOK_USERNAME": "matchbook_username",
        "MATCHBOOK_PASSWORD": "matchbook_password",
        "MATCHBOOK_API_BASE_URL": "matchbook_api_base_url",
    }
    PASSWORD_VARIABLES = {"BETFAIR_PASSWORD", "MATCHBOOK_PASSWORD"}
    PARTIAL_SECRET_VARIABLES = {"BETFAIR_APP_KEY"}

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def run(self) -> dict[str, Any]:
        checks: dict[str, Any] = {
            "variables": {},
            "paths": {},
            "ok": True,
        }

        for env_name, attr_name in self.REQUIRED_VARIABLES.items():
            value = getattr(self.settings, attr_name)
            status = self._format_value(env_name, value)
            checks["variables"][env_name] = status
            if not value:
                checks["ok"] = False

        cert_status = self._check_betfair_certificates()
        checks["paths"].update(cert_status)
        if any(item.get("status") in {"ausente", "informado mas nao encontrado"} for item in cert_status.values()):
            checks["ok"] = False

        output_status = self._ensure_output_dir(self.settings.output_dir)
        checks["paths"]["OUTPUT_DIR"] = output_status
        if output_status.get("status") not in {"existe", "criado"}:
            checks["ok"] = False

        return checks

    def print_report(self, report: dict[str, Any]) -> None:
        print("\nCheck local de configuracao (sem chamadas externas de API):")
        for name, status in report["variables"].items():
            print(f"{name}: {status}")
        for name, status in report["paths"].items():
            detail = status.get("detail")
            suffix = f" ({detail})" if detail else ""
            print(f"{name}: {status['status']}{suffix}")
        print(f"CONFIG_STATUS: {'ok' if report['ok'] else 'pendente'}")

    def _format_value(self, name: str, value: str | None) -> str:
        if name in self.PASSWORD_VARIABLES:
            return "preenchido" if value else "ausente"
        if name in self.PARTIAL_SECRET_VARIABLES:
            return self._format_partial_secret(value)
        return "preenchido" if value else "ausente"

    def _format_partial_secret(self, value: str | None) -> str:
        if not value:
            return "ausente"
        if len(value) <= 4:
            return "preenchido parcialmente ****"
        return f"preenchido parcialmente ****{value[-4:]}"

    def _check_betfair_certificates(self) -> dict[str, dict[str, str]]:
        if self.settings.betfair_cert_file or self.settings.betfair_key_file:
            return {
                "BETFAIR_CERT_FILE": self._check_single_path(self.settings.betfair_cert_file),
                "BETFAIR_KEY_FILE": self._check_single_path(self.settings.betfair_key_file),
            }

        if self.settings.betfair_cert_path:
            return {"BETFAIR_CERT_PATH": self._check_cert_path(self.settings.betfair_cert_path)}

        return {
            "BETFAIR_CERT_FILE": {"status": "ausente"},
            "BETFAIR_KEY_FILE": {"status": "ausente"},
        }

    def _check_single_path(self, path_value: str | None) -> dict[str, str]:
        if not path_value:
            return {"status": "ausente"}
        if Path(path_value).is_file():
            return {"status": "existe", "detail": path_value}
        return {"status": "informado mas nao encontrado", "detail": path_value}

    def _check_cert_path(self, cert_path: str | None) -> dict[str, str]:
        if not cert_path:
            return {"status": "ausente"}

        parts = [part.strip() for part in cert_path.split(",") if part.strip()]
        missing = [part for part in parts if not Path(part).is_file()]
        if missing:
            return {
                "status": "informado mas nao encontrado",
                "detail": ", ".join(missing),
            }
        return {"status": "existe", "detail": cert_path}

    def _ensure_output_dir(self, output_dir: Path) -> dict[str, str]:
        try:
            existed = output_dir.exists()
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return {"status": "erro ao criar", "detail": str(exc)}
        return {"status": "existe" if existed else "criado", "detail": str(output_dir)}
