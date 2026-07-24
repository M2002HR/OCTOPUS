from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _integer(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _window_name(minutes: int) -> str:
    if minutes == 10_080:
        return "Weekly limit"
    if minutes and minutes % 1_440 == 0:
        return f"{minutes // 1_440}-day limit"
    if minutes and minutes % 60 == 0:
        return f"{minutes // 60}-hour limit"
    return f"{minutes}-minute limit" if minutes else "Usage limit"


def _reset_time(timestamp: object, timezone_name: str) -> str:
    seconds = _integer(timestamp)
    if not seconds:
        return "unknown"
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        timezone = ZoneInfo("UTC")
    return datetime.fromtimestamp(seconds, tz=timezone).strftime(
        f"%Y-%m-%d %H:%M {timezone.key}"
    )


def format_codex_account_limits(
    payload: object,
    *,
    timezone_name: str,
) -> str:
    data = payload if isinstance(payload, dict) else {}
    by_id = data.get("rateLimitsByLimitId")
    snapshots: list[dict[str, Any]] = []
    if isinstance(by_id, dict):
        snapshots.extend(
            value for value in by_id.values() if isinstance(value, dict)
        )
    if not snapshots and isinstance(data.get("rateLimits"), dict):
        snapshots.append(data["rateLimits"])
    if not snapshots:
        return "Codex account usage is temporarily unavailable."

    lines = ["Codex account usage"]
    for index, snapshot in enumerate(snapshots):
        if index:
            lines.append("")
        limit_name = str(
            snapshot.get("limitName")
            or snapshot.get("limitId")
            or f"Limit {index + 1}"
        )
        plan = str(snapshot.get("planType") or "unknown").replace("_", " ").title()
        lines.extend([f"Meter: {limit_name}", f"Plan: {plan}"])
        windows = [
            window
            for window in (snapshot.get("primary"), snapshot.get("secondary"))
            if isinstance(window, dict)
        ]
        for window in windows:
            used = min(100, _integer(window.get("usedPercent")))
            remaining = max(0, 100 - used)
            duration = _integer(window.get("windowDurationMins"))
            filled = min(10, used // 10)
            bar = "█" * filled + "░" * (10 - filled)
            lines.extend(
                [
                    f"{_window_name(duration)}:",
                    f"{bar} {used}% used · {remaining}% remaining",
                    f"Resets: {_reset_time(window.get('resetsAt'), timezone_name)}",
                ]
            )
        credits = snapshot.get("credits")
        if isinstance(credits, dict):
            if bool(credits.get("unlimited")):
                lines.append("Credits: unlimited")
            elif bool(credits.get("hasCredits")):
                lines.append(f"Credit balance: {credits.get('balance') or '0'}")
        reached = snapshot.get("rateLimitReachedType")
        if reached:
            lines.append(f"Limit status: {str(reached).replace('_', ' ')}")

    reset_credits = data.get("rateLimitResetCredits")
    if isinstance(reset_credits, dict):
        available = _integer(reset_credits.get("availableCount"))
        lines.append(f"Available reset credits: {available}")
    return "\n".join(lines)
