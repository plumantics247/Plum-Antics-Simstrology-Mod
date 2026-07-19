from __future__ import annotations


def _metadata_for_context(context):
    return dict(getattr(context, "metadata", {}) or {})


def _has_runtime_tick_trigger(metadata):
    return bool(
        metadata.get("movement_trigger")
        or metadata.get("count_trigger")
        or metadata.get("periodic_trigger")
    )


def build_visible_sign_tick_handler(*, sync_visible_signs_fn):
    def _handler(context):
        metadata = _metadata_for_context(context)
        if not _has_runtime_tick_trigger(metadata):
            return {"operations": (), "summary": {"handled": False, "reason": "no_runtime_tick_trigger"}}

        summary = sync_visible_signs_fn() or {}
        return {"operations": (), "summary": {"handled": True, **dict(summary)}}

    return _handler


def build_solar_boost_tick_handler(*, sync_solar_boosts_fn):
    def _handler(context):
        metadata = _metadata_for_context(context)
        if not _has_runtime_tick_trigger(metadata):
            return {"operations": (), "summary": {"handled": False, "reason": "no_runtime_tick_trigger"}}
        if not bool(metadata.get("shared_runtime_enabled", False)):
            return {"operations": (), "summary": {"handled": False, "reason": "shared_runtime_disabled"}}

        summary = sync_solar_boosts_fn() or {}
        return {"operations": (), "summary": {"handled": True, **dict(summary)}}

    return _handler


def build_solar_return_tick_handler(*, sync_solar_return_fn):
    def _handler(context):
        metadata = _metadata_for_context(context)
        if not _has_runtime_tick_trigger(metadata):
            return {"operations": (), "summary": {"handled": False, "reason": "no_runtime_tick_trigger"}}
        if not bool(metadata.get("shared_runtime_enabled", False)):
            return {"operations": (), "summary": {"handled": False, "reason": "shared_runtime_disabled"}}

        summary = sync_solar_return_fn(
            show_notifications=bool(metadata.get("show_notifications", True))
        ) or {}
        return {"operations": (), "summary": {"handled": True, **dict(summary)}}

    return _handler


def build_retrograde_tick_handler(*, sync_markers_fn, sync_consequences_fn):
    def _handler(context):
        metadata = _metadata_for_context(context)
        if not _has_runtime_tick_trigger(metadata):
            return {"operations": (), "summary": {"handled": False, "reason": "no_runtime_tick_trigger"}}
        if not bool(metadata.get("retrogrades_enabled", False)):
            return {"operations": (), "summary": {"handled": False, "reason": "retrogrades_disabled"}}

        reason = str(metadata.get("reason", "runtime.periodic") or "runtime.periodic")
        marker_summary = sync_markers_fn() or {}
        consequence_summary = sync_consequences_fn(reason=reason) or {}
        return {
            "operations": (),
            "summary": {
                "handled": True,
                "marker_summary": dict(marker_summary),
                "consequence_summary": dict(consequence_summary),
            },
        }

    return _handler
