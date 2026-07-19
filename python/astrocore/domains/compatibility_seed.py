from __future__ import annotations


def build_household_compatibility_handler(*, seed_household_fn):
    def _handler(context):
        reason = str(dict(getattr(context, "metadata", {}) or {}).get("reason", "runtime.household_onboard"))
        summary = seed_household_fn(reason=reason) or {}
        return {"operations": (), "summary": dict(summary)}

    return _handler


def build_sim_age_transition_compatibility_handler(*, sync_sim_fn):
    def _handler(context):
        metadata = dict(getattr(context, "metadata", {}) or {})
        event = metadata.get("event")
        age_to = str(getattr(event, "age_to", "") or "").strip().lower()
        if age_to not in ("teen", "youngadult", "adult", "elder"):
            return {
                "operations": (),
                "summary": {
                    "handled": False,
                    "reason": "age_not_newly_eligible",
                },
            }

        summary = sync_sim_fn(
            int(getattr(event, "sim_id", 0) or 0),
            reason="runtime.age_transition",
        ) or {}
        return {
            "operations": (),
            "summary": {
                "handled": True,
                **dict(summary),
            },
        }

    return _handler
