from telegram_codex_agent.codex_usage import format_codex_account_limits


def test_formats_weekly_codex_account_limit() -> None:
    output = format_codex_account_limits(
        {
            "rateLimits": {
                "limitId": "codex",
                "limitName": "Codex",
                "planType": "plus",
                "primary": {
                    "usedPercent": 14,
                    "windowDurationMins": 300,
                    "resetsAt": 1_800_000_000,
                },
                "secondary": {
                    "usedPercent": 92,
                    "windowDurationMins": 10_080,
                    "resetsAt": 1_800_003_600,
                },
                "credits": {"hasCredits": False, "unlimited": False},
            },
            "rateLimitResetCredits": {"availableCount": 1},
        },
        timezone_name="UTC",
    )

    assert "Codex account usage" in output
    assert "Plan: Plus" in output
    assert "5-hour limit" in output
    assert "Weekly limit" in output
    assert "92% used · 8% remaining" in output
    assert "Resets:" in output
    assert "Available reset credits: 1" in output


def test_formats_rate_limits_by_identifier() -> None:
    output = format_codex_account_limits(
        {
            "rateLimitsByLimitId": {
                "codex": {
                    "limitId": "codex",
                    "planType": "team",
                    "primary": {
                        "usedPercent": 0,
                        "windowDurationMins": 10_080,
                        "resetsAt": 1_800_000_000,
                    },
                }
            }
        },
        timezone_name="Invalid/Timezone",
    )

    assert "Meter: codex" in output
    assert "Plan: Team" in output
    assert "0% used · 100% remaining" in output
    assert "UTC" in output


def test_formats_unavailable_payload() -> None:
    assert (
        format_codex_account_limits({}, timezone_name="UTC")
        == "Codex account usage is temporarily unavailable."
    )
