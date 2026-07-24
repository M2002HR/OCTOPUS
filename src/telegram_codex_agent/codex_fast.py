from __future__ import annotations

from typing import Any


def fast_service_tier(payload: object, model_name: str) -> str | None:
    """Return the App Server tier id advertised as Fast for one model."""

    data = payload if isinstance(payload, dict) else {}
    models = data.get("data")
    if not isinstance(models, list):
        return None
    requested = model_name.strip().casefold()
    for candidate in models:
        if not isinstance(candidate, dict):
            continue
        identifiers = {
            str(candidate.get("id") or "").casefold(),
            str(candidate.get("model") or "").casefold(),
        }
        if requested not in identifiers:
            continue
        tiers = candidate.get("serviceTiers")
        if not isinstance(tiers, list):
            return None
        for tier in tiers:
            if not isinstance(tier, dict):
                continue
            tier_id = str(tier.get("id") or "").strip()
            tier_name = str(tier.get("name") or "").strip().casefold()
            if tier_id and (tier_name == "fast" or tier_id.casefold() in {"fast", "priority"}):
                return tier_id
        return None
    return None


def model_catalog_has_data(payload: object) -> bool:
    data: dict[str, Any] = payload if isinstance(payload, dict) else {}
    return isinstance(data.get("data"), list)


def preference_enabled(value: object) -> bool:
    """Normalize persisted booleans, including legacy string values."""

    return value is True or str(value).strip().casefold() in {"1", "true", "yes", "on"}
