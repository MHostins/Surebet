"""Local read-only Streamlit dashboard for Surebet outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


OUTPUT_DIR = Path("outputs")


def load_json_file(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if not path.exists():
        return {}, {"path": str(path), "state": "missing", "message": "Arquivo ausente."}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {}, {"path": str(path), "state": "error", "message": str(exc)}
    if not text.strip():
        return {}, {"path": str(path), "state": "empty", "message": "Arquivo vazio."}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return {}, {"path": str(path), "state": "invalid", "message": str(exc)}
    if not isinstance(payload, dict):
        return {}, {"path": str(path), "state": "invalid", "message": "JSON nao e objeto."}
    return payload, {"path": str(path), "state": "ok", "message": "OK"}


def load_jsonl_file(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.exists():
        return [], {"path": str(path), "state": "missing", "message": "Arquivo ausente.", "invalid_lines": 0}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [], {"path": str(path), "state": "error", "message": str(exc), "invalid_lines": 0}
    if not lines:
        return [], {"path": str(path), "state": "empty", "message": "Arquivo vazio.", "invalid_lines": 0}

    rows: list[dict[str, Any]] = []
    invalid_lines = 0
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            invalid_lines += 1
            continue
        if isinstance(payload, dict):
            rows.append(payload)
        else:
            invalid_lines += 1

    state = "ok" if rows else "empty"
    return rows, {
        "path": str(path),
        "state": state,
        "message": "OK" if rows else "Sem linhas validas.",
        "invalid_lines": invalid_lines,
    }


def pair_label(value: Any) -> str:
    if isinstance(value, list):
        return " x ".join(str(item) for item in value)
    if value is None:
        return ""
    return str(value)


def normalize_alert_rows(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for alert in alerts:
        row = dict(alert)
        row["bookmaker_pair"] = pair_label(row.get("bookmaker_pair"))
        stake_plan = row.get("stake_plan")
        if isinstance(stake_plan, dict):
            row["stake_plan"] = json.dumps(stake_plan, ensure_ascii=False)
        rows.append(row)
    return rows


def filter_alerts(
    alerts: list[dict[str, Any]],
    *,
    alert_type: str | None = None,
    sport: str | None = None,
    bookmaker_pair: str | None = None,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for alert in alerts:
        if alert_type and alert_type != "Todos" and alert.get("alert_type") != alert_type:
            continue
        if sport and sport != "Todos" and alert.get("sport") != sport:
            continue
        if bookmaker_pair and bookmaker_pair != "Todos" and pair_label(alert.get("bookmaker_pair")) != bookmaker_pair:
            continue
        filtered.append(alert)
    return filtered


def _file_paths(output_dir: Path = OUTPUT_DIR) -> dict[str, Path]:
    return {
        "alerts_json": output_dir / "opportunity_alerts.json",
        "alerts_csv": output_dir / "opportunity_alerts.csv",
        "alert_history": output_dir / "opportunity_alert_history.jsonl",
        "quality_review": output_dir / "opportunity_quality_review.json",
        "calculated_opportunities": output_dir / "calculated_opportunities.json",
    }


def _metric_value(summary: dict[str, Any], key: str) -> Any:
    return summary.get(key) if summary.get(key) is not None else "N/A"


def render_dashboard() -> None:
    import streamlit as st

    st.set_page_config(page_title="Surebet Monitor", layout="wide")
    st.title("Surebet Monitor")
    st.caption("Dashboard local read-only. Apenas visualiza arquivos existentes em outputs/.")

    paths = _file_paths()
    alerts_payload, alerts_status = load_json_file(paths["alerts_json"])
    quality_payload, quality_status = load_json_file(paths["quality_review"])
    calculated_payload, calculated_status = load_json_file(paths["calculated_opportunities"])
    history_rows, history_status = load_jsonl_file(paths["alert_history"])

    statuses = {
        "opportunity_alerts.json": alerts_status,
        "opportunity_alert_history.jsonl": history_status,
        "opportunity_quality_review.json": quality_status,
        "calculated_opportunities.json": calculated_status,
    }

    with st.expander("Estado dos arquivos", expanded=False):
        for name, status in statuses.items():
            if status["state"] == "ok":
                st.success(f"{name}: OK")
            else:
                st.warning(f"{name}: {status['message']}")

    summary = alerts_payload.get("summary", {}) if alerts_payload else {}
    best_surebet = summary.get("best_surebet") or {}
    closest_near_miss = summary.get("closest_near_miss") or {}
    alerts = alerts_payload.get("alerts", []) if isinstance(alerts_payload.get("alerts"), list) else []

    cols = st.columns(6)
    cols[0].metric("Total alerts", _metric_value(summary, "total_alerts"))
    cols[1].metric("Surebets", _metric_value(summary, "total_surebet_alerts"))
    cols[2].metric("Near misses", _metric_value(summary, "total_near_miss_alerts"))
    cols[3].metric("Best ROI %", best_surebet.get("roi_percent", "N/A"))
    cols[4].metric("Best event", best_surebet.get("event_name", "N/A"))
    cols[5].metric("Closest distance %", closest_near_miss.get("distance_to_surebet_percent", "N/A"))

    st.subheader("Filtros")
    sports = ["Todos"] + sorted({str(alert.get("sport")) for alert in alerts if alert.get("sport")})
    alert_types = ["Todos"] + sorted({str(alert.get("alert_type")) for alert in alerts if alert.get("alert_type")})
    pairs = ["Todos"] + sorted({pair_label(alert.get("bookmaker_pair")) for alert in alerts if alert.get("bookmaker_pair")})

    fcols = st.columns(3)
    selected_sport = fcols[0].selectbox("Sport", sports)
    selected_type = fcols[1].selectbox("Alert type", alert_types)
    selected_pair = fcols[2].selectbox("Bookmaker pair", pairs)
    filtered_alerts = filter_alerts(alerts, alert_type=selected_type, sport=selected_sport, bookmaker_pair=selected_pair)

    surebets = [alert for alert in filtered_alerts if alert.get("alert_type") == "surebet"]
    near_misses = [alert for alert in filtered_alerts if alert.get("alert_type") == "near_miss"]

    st.subheader("Surebets")
    surebet_columns = [
        "event_name", "sport", "market_type", "start_time", "bookmaker_pair",
        "implied_sum", "roi_percent", "guaranteed_profit", "stake_plan",
    ]
    st.dataframe(
        [{key: row.get(key) for key in surebet_columns} for row in normalize_alert_rows(surebets)],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Near-misses")
    near_miss_columns = [
        "event_name", "sport", "market_type", "start_time", "bookmaker_pair",
        "distance_to_surebet_percent", "worst_case_profit",
    ]
    st.dataframe(
        [{key: row.get(key) for key in near_miss_columns} for row in normalize_alert_rows(near_misses)],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Historico de alertas")
    history_columns = [
        "timestamp", "total_alerts", "total_surebet_alerts",
        "total_near_miss_alerts", "best_roi_percent",
    ]
    st.dataframe(
        [{key: row.get(key) for key in history_columns} for row in history_rows],
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("Quality review e oportunidades calculadas", expanded=False):
        st.json({
            "quality_review_summary": {
                "total_candidates": quality_payload.get("total_candidates"),
                "total_surebets": quality_payload.get("total_surebets"),
                "surebet_rate_percent": quality_payload.get("surebet_rate_percent"),
            },
            "calculated_opportunities_summary": {
                "total_candidates": calculated_payload.get("total_candidates"),
                "total_supported": calculated_payload.get("total_supported"),
                "total_surebets": calculated_payload.get("total_surebets"),
            },
        })


if __name__ == "__main__":
    render_dashboard()
