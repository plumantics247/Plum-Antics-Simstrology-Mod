from __future__ import annotations


def build_childhood_age_transition_handler(*, repair_fn, lookup_sim_info):
    def _handler(context):
        metadata = dict(getattr(context, "metadata", {}) or {})
        event = metadata.get("event")
        age_from = str(getattr(event, "age_from", "") or "").strip().lower()
        age_to = str(getattr(event, "age_to", "") or "").strip().lower()
        if age_from != "child" or age_to != "teen":
            return {
                "operations": (),
                "summary": {
                    "handled": False,
                    "reason": "age_not_child_to_teen",
                },
            }

        sim_id = int(getattr(event, "sim_id", 0) or 0)
        sim_info = None if sim_id <= 0 else lookup_sim_info(sim_id)
        if sim_info is None:
            return {
                "operations": (),
                "summary": {
                    "handled": False,
                    "reason": "missing_sim",
                },
            }

        repair_summary = repair_fn(sim_info) or {}
        return {
            "operations": (),
            "summary": {
                "handled": True,
                "reason": "childhood_handoff",
                "repair_summary": dict(repair_summary),
            },
        }

    return _handler
