from __future__ import annotations


def build_household_onboarding_handler(*, onboard_fn):
    def _handler(context):
        metadata = dict(getattr(context, "metadata", {}) or {})
        household_id = int(metadata.get("household_id", 0) or 0)
        if household_id <= 0:
            return {
                "operations": (),
                "summary": {
                    "handled": False,
                    "reason": "missing_household_id",
                },
            }

        summary = onboard_fn(
            active_household_id=household_id,
            refresh_marker_cache=bool(metadata.get("refresh_marker_cache", False)),
            teen_sign_seed_mode=str(metadata.get("teen_sign_seed_mode", "current_sky") or "current_sky"),
        ) or {}
        return {
            "operations": (),
            "summary": {
                "handled": True,
                **dict(summary),
            },
        }

    return _handler
