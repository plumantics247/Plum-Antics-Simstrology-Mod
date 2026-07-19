"""Custom loot tuning bridge for the Big 3 private runtime."""

from __future__ import annotations

import logging
import time

from .integration.bridge import get_runtime
from .integration.mode_lock import is_big3_mode_active, set_mode_lock, sync_mode_lock_traits

try:
    from cosmic_engine.astrology_skill_gate import (
        get_simstrology_skill_level,
        simstrology_skill_meets,
    )
except Exception:  # pragma: no cover - local fallback

    def get_simstrology_skill_level(sim_info):
        return 0

    def simstrology_skill_meets(sim_info, required_level):
        return False


log = logging.getLogger("plumantics_big3_runtime.loot_actions")
_CHILD_ASSIGN_LAST_RUN_BY_SIM_ID = {}
_CHILD_ASSIGN_DEBOUNCE_SECONDS = 1.0
_CHART_CAPTURE_LAST_RUN_BY_SIM_ID = {}
_CHART_CAPTURE_DEBOUNCE_SECONDS = 1.0
_SIGNS = (
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
)
_HOUSES = (
    "1st House",
    "2nd House",
    "3rd House",
    "4th House",
    "5th House",
    "6th House",
    "7th House",
    "8th House",
    "9th House",
    "10th House",
    "11th House",
    "12th House",
)
_BIG3_VISIBLE_TO_OVERLAY_TRAITS = {
    3164395998: 810000000000000002,  # Aries Sun -> Aries SunOverlay
    4281780916: 810000000000000011,  # Taurus Sun -> Taurus SunOverlay
    3771207495: 810000000000000005,  # Gemini Sun -> Gemini SunOverlay
    2654235180: 810000000000000003,  # Cancer Sun -> Cancer SunOverlay
    2797810424: 810000000000000006,  # Leo Sun -> Leo SunOverlay
    3413939915: 810000000000000012,  # Virgo Sun -> Virgo SunOverlay
    3887839626: 810000000000000007,  # Libra Sun -> Libra SunOverlay
    2636947797: 810000000000000010,  # Scorpio Sun -> Scorpio SunOverlay
    3298769274: 810000000000000009,  # Sagittarius Sun -> Sagittarius SunOverlay
    3356986463: 810000000000000004,  # Capricorn Sun -> Capricorn SunOverlay
    4169897889: 810000000000000001,  # Aquarius Sun -> Aquarius SunOverlay
    2363848465: 810000000000000008,  # Pisces Sun -> Pisces SunOverlay
    2297406366: 820000000000000002,  # Aries Rising -> Aries RisingOverlay
    2588878312: 820000000000000011,  # Taurus Rising -> Taurus RisingOverlay
    4242808797: 820000000000000005,  # Gemini Rising -> Gemini RisingOverlay
    2154635568: 820000000000000003,  # Cancer Rising -> Cancer RisingOverlay
    3739357428: 820000000000000006,  # Leo Rising -> Leo RisingOverlay
    2665561705: 820000000000000012,  # Virgo Rising -> Virgo RisingOverlay
    3123976786: 820000000000000007,  # Libra Rising -> Libra RisingOverlay
    3923158167: 820000000000000010,  # Scorpio Rising -> Scorpio RisingOverlay
    2405249506: 820000000000000009,  # Sagittarius Rising -> Sagittarius RisingOverlay
    3178572581: 820000000000000004,  # Capricorn Rising -> Capricorn RisingOverlay
    2243949835: 820000000000000001,  # Aquarius Rising -> Aquarius RisingOverlay
    3588503643: 820000000000000008,  # Pisces Rising -> Pisces RisingOverlay
}
_LEGACY_BIG3_PLANET_TRAIT_IDS = frozenset((
    4208090340,  # PlumAntics_Big3Mod_Mercury
    3858955547,  # PlumAntics_Big3Mod_Mars
))


try:
    from interactions.utils.loot import LootActions  # type: ignore
except Exception:  # pragma: no cover - local fallback

    class LootActions(object):
        """Fallback shim for local syntax checks outside game runtime."""

        def apply_to_resolver(self, resolver, skip_test=False):
            return True


def _sim_info_from_candidate(candidate):
    if candidate is None:
        return None
    sim_info = getattr(candidate, "sim_info", None)
    if sim_info is not None:
        return sim_info
    if getattr(candidate, "trait_tracker", None) is not None:
        return candidate
    return None


def _resolve_actor_sim_info(resolver):
    if resolver is None:
        return None

    try:
        from interactions import ParticipantType  # type: ignore

        getter = getattr(resolver, "get_participant", None)
        if callable(getter):
            for participant_name in ("Actor", "Subject", "ActorSim"):
                participant_type = getattr(ParticipantType, participant_name, None)
                if participant_type is None:
                    continue
                try:
                    candidate = getter(participant_type)
                except Exception:
                    continue
                sim_info = _sim_info_from_candidate(candidate)
                if sim_info is not None:
                    return sim_info
    except Exception:
        pass

    for participant_name in ("Actor", "Object", "TargetSim", "PickedSim", "Target"):
        getter = getattr(resolver, "get_participant", None)
        if not callable(getter):
            continue
        try:
            candidate = getter(participant_name)
        except Exception:
            continue
        sim_info = _sim_info_from_candidate(candidate)
        if sim_info is not None:
            return sim_info

    for attr_name in ("_sim_info", "sim_info", "actor", "_actor"):
        candidate = getattr(resolver, attr_name, None)
        sim_info = _sim_info_from_candidate(candidate)
        if sim_info is not None:
            return sim_info
    return None


def _resolve_participant_sim_info(resolver, participant_names):
    if resolver is None:
        return None

    try:
        from interactions import ParticipantType  # type: ignore

        getter = getattr(resolver, "get_participant", None)
        if callable(getter):
            for participant_name in tuple(participant_names or ()):
                participant_type = getattr(ParticipantType, str(participant_name), None)
                if participant_type is None:
                    continue
                try:
                    candidate = getter(participant_type)
                except Exception:
                    continue
                sim_info = _sim_info_from_candidate(candidate)
                if sim_info is not None:
                    return sim_info
    except Exception:
        pass

    getter = getattr(resolver, "get_participant", None)
    if callable(getter):
        for participant_name in tuple(participant_names or ()):
            try:
                candidate = getter(participant_name)
            except Exception:
                continue
            sim_info = _sim_info_from_candidate(candidate)
            if sim_info is not None:
                return sim_info

    for attr_name in ("_target", "target", "target_sim", "_target_sim", "picked_sim", "_picked_sim", "obj", "_obj"):
        candidate = getattr(resolver, attr_name, None)
        sim_info = _sim_info_from_candidate(candidate)
        if sim_info is not None:
            return sim_info
    return None


def _sim_display_name(sim_info):
    first_name = getattr(sim_info, "first_name", None)
    last_name = getattr(sim_info, "last_name", None)
    if first_name or last_name:
        return "{0} {1}".format(first_name or "", last_name or "").strip()
    return str(getattr(sim_info, "full_name", None) or "Sim")


def _trait_manager():
    try:
        import services  # type: ignore
        import sims4.resources  # type: ignore

        return services.get_instance_manager(sims4.resources.Types.TRAIT)
    except Exception:
        return None


def _resolve_trait(trait_id):
    manager = _trait_manager()
    if manager is None:
        return None
    try:
        return manager.get(int(trait_id))
    except Exception:
        return None


def _equipped_traits(sim_info):
    trait_tracker = getattr(sim_info, "trait_tracker", None)
    if trait_tracker is None:
        return ()
    return tuple(getattr(trait_tracker, "equipped_traits", None) or ())


def _sim_has_trait(sim_info, trait_id):
    for trait in _equipped_traits(sim_info):
        guid = getattr(trait, "guid64", None)
        if guid is None:
            guid = getattr(trait, "guid", None)
        try:
            if int(guid) == int(trait_id):
                return True
        except Exception:
            continue
    return False


def _add_trait_if_missing(sim_info, trait_id):
    if _sim_has_trait(sim_info, trait_id):
        return False
    trait = _resolve_trait(trait_id)
    if trait is None:
        return False
    for owner in (getattr(sim_info, "trait_tracker", None), sim_info):
        add_fn = getattr(owner, "add_trait", None)
        if callable(add_fn):
            try:
                add_fn(trait)
                return True
            except Exception:
                continue
    return False


def _remove_trait_if_present(sim_info, trait_id):
    if not _sim_has_trait(sim_info, trait_id):
        return False
    trait = _resolve_trait(trait_id)
    if trait is None:
        for candidate in _equipped_traits(sim_info):
            guid = getattr(candidate, "guid64", None)
            if guid is None:
                guid = getattr(candidate, "guid", None)
            try:
                if int(guid) == int(trait_id):
                    trait = candidate
                    break
            except Exception:
                continue
    if trait is None:
        return False
    for owner in (getattr(sim_info, "trait_tracker", None), sim_info):
        remove_fn = getattr(owner, "remove_trait", None)
        if callable(remove_fn):
            try:
                remove_fn(trait)
                return True
            except Exception:
                continue
    return False


def _show_simple_notification(owner, title, text):
    try:
        from sims4.localization import LocalizationHelperTuning  # type: ignore
        from ui.ui_dialog_notification import UiDialogNotification  # type: ignore

        notification = UiDialogNotification.TunableFactory().default(
            owner,
            title=lambda *_, **__: LocalizationHelperTuning.get_raw_text(str(title)),
            text=lambda *_, **__: LocalizationHelperTuning.get_raw_text(str(text)),
        )
        notification.show_dialog()
        return True
    except Exception:
        return False


def _show_chart_skill_gate_notification(owner, required_level, actor_skill_level):
    title = "Chart Reading Not Ready"
    text = (
        "Read Natal Chart unlocks at Simstrology level {0}. "
        "Current level: {1}."
    ).format(int(required_level), int(actor_skill_level))
    return _show_simple_notification(owner, title, text)


def _sign_name_from_index(sign_index):
    try:
        return _SIGNS[int(sign_index) % len(_SIGNS)]
    except Exception:
        return "Unknown"


def _house_label_from_index(house_index):
    try:
        return _HOUSES[int(house_index) % len(_HOUSES)]
    except Exception:
        return "Unknown House"


def _resolve_chart_payload_for_read(runtime, sim_id, sim_info=None):
    payload = runtime.get_chart_record_payload(int(sim_id))
    try:
        from cosmic_engine.chart_records import should_refresh_outer_planets_chart_payload
    except Exception:
        should_refresh_outer_planets_chart_payload = None

    if (
        isinstance(payload, dict)
        and callable(should_refresh_outer_planets_chart_payload)
        and should_refresh_outer_planets_chart_payload(payload, include_outer_planets=True)
    ):
        payload = None

    if not isinstance(payload, dict) and sim_info is not None:
        capture_fn = getattr(runtime, "_store_chart_record_for_sim_info", None)
        if callable(capture_fn):
            payload = capture_fn(
                sim_info,
                metadata={
                    "assignment_reason": "chart_marker_sync",
                    "assignment_flow": "recover_from_existing_traits",
                },
                overwrite_existing=True,
            )

    return payload if isinstance(payload, dict) else None


class Big3ChildAutoAssignPythonLoot(LootActions):
    """Auto-assign Big 3 signs for childhood sims from tuning hooks."""

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)

        try:
            sim_info = _resolve_actor_sim_info(resolver)
            if sim_info is None:
                log.warning("Child auto-assign loot could not resolve actor sim_info.")
                return result

            sim_id = getattr(sim_info, "sim_id", None)
            if sim_id is None:
                sim_id = getattr(sim_info, "id", None)
            if sim_id is None:
                log.warning("Child auto-assign loot missing sim id.")
                return result
            sim_id = int(sim_id)

            now = time.monotonic()
            last_run = _CHILD_ASSIGN_LAST_RUN_BY_SIM_ID.get(sim_id)
            if last_run is not None and (now - float(last_run)) < _CHILD_ASSIGN_DEBOUNCE_SECONDS:
                return result

            _CHILD_ASSIGN_LAST_RUN_BY_SIM_ID[sim_id] = now
            get_runtime().auto_assign_child_for_sim_info(
                sim_info,
                reason="childhood_buff_hook",
            )
        except Exception:
            log.exception("Child auto-assign loot bridge failed.")

        return result


class Big3CaptureChartPythonLoot(LootActions):
    """Capture a Big 3 chart record from the sim's current sign traits."""

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)

        try:
            sim_info = _resolve_actor_sim_info(resolver)
            if sim_info is None:
                log.warning("Chart capture loot could not resolve actor sim_info.")
                return result

            sim_id = getattr(sim_info, "sim_id", None)
            if sim_id is None:
                sim_id = getattr(sim_info, "id", None)
            if sim_id is None:
                log.warning("Chart capture loot missing sim id.")
                return result
            sim_id = int(sim_id)

            now = time.monotonic()
            last_run = _CHART_CAPTURE_LAST_RUN_BY_SIM_ID.get(sim_id)
            if last_run is not None and (now - float(last_run)) < _CHART_CAPTURE_DEBOUNCE_SECONDS:
                return result

            _CHART_CAPTURE_LAST_RUN_BY_SIM_ID[sim_id] = now
            get_runtime().capture_chart_for_sim(
                sim_id=sim_id,
                reason="rising_trait_instance",
            )
        except Exception:
            log.exception("Big 3 chart capture loot bridge failed.")

        return result


class Big3AssignRisingSunTimePythonLoot(LootActions):
    """Assign Rising through the normalized runtime sun_time path."""

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)
        try:
            sim_info = _resolve_actor_sim_info(resolver)
            if sim_info is None:
                log.warning("Rising sun_time loot could not resolve actor sim_info.")
                return result
            get_runtime().assign_rising_sun_time_for_sim_info(
                sim_info,
                reason="loot_bridge:rising_sun_time",
            )
        except Exception:
            log.exception("Rising sun_time loot bridge failed.")
        return result


class Big3AssignRisingRandomPythonLoot(LootActions):
    """Assign Rising through the normalized runtime random path."""

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)
        try:
            sim_info = _resolve_actor_sim_info(resolver)
            if sim_info is None:
                log.warning("Rising random loot could not resolve actor sim_info.")
                return result
            get_runtime().assign_rising_random_for_sim_info(
                sim_info,
                reason="loot_bridge:rising_random",
            )
        except Exception:
            log.exception("Rising random loot bridge failed.")
        return result


class Big3AssignMoonLunarPhasePythonLoot(LootActions):
    """Assign Moon through the normalized runtime lunar-phase path."""

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)
        try:
            sim_info = _resolve_actor_sim_info(resolver)
            if sim_info is None:
                log.warning("Moon lunar-phase loot could not resolve actor sim_info.")
                return result
            get_runtime().assign_moon_lunar_phase_for_sim_info(
                sim_info,
                reason="loot_bridge:moon_lunar_phase",
            )
        except Exception:
            log.exception("Moon lunar-phase loot bridge failed.")
        return result


class Big3AssignMoonRandomPythonLoot(LootActions):
    """Assign Moon through the normalized runtime random path."""

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)
        try:
            sim_info = _resolve_actor_sim_info(resolver)
            if sim_info is None:
                log.warning("Moon random loot could not resolve actor sim_info.")
                return result
            get_runtime().assign_moon_random_for_sim_info(
                sim_info,
                reason="loot_bridge:moon_random",
            )
        except Exception:
            log.exception("Moon random loot bridge failed.")
        return result


class Big3EnsureLaneOverlaysPythonLoot(LootActions):
    """Ensure Big 3 Sun/Rising overlay traits are present in the Big 3 lane."""

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)

        try:
            if not is_big3_mode_active():
                return result

            sim_info = _resolve_actor_sim_info(resolver)
            if sim_info is None:
                log.warning("Overlay ensure loot could not resolve actor sim_info.")
                return result

            added_count = 0
            for visible_trait_id, overlay_trait_id in _BIG3_VISIBLE_TO_OVERLAY_TRAITS.items():
                if _sim_has_trait(sim_info, visible_trait_id) and _add_trait_if_missing(sim_info, overlay_trait_id):
                    added_count += 1

            removed_legacy_count = 0
            for trait_id in _LEGACY_BIG3_PLANET_TRAIT_IDS:
                if _remove_trait_if_present(sim_info, trait_id):
                    removed_legacy_count += 1

            if added_count or removed_legacy_count:
                log.debug(
                    "Ensured %s Big 3 overlay trait(s) and removed %s legacy planet trait(s) for sim %s.",
                    added_count,
                    removed_legacy_count,
                    getattr(sim_info, "sim_id", None) or getattr(sim_info, "id", None),
                )
        except Exception:
            log.exception("Big 3 overlay ensure loot bridge failed.")

        return result


class Big3SetModeLockPythonLoot(LootActions):
    """Persist the save-global lane choice when Big 3 onboarding starts."""

    def apply_to_resolver(self, resolver, skip_test=False):
        result = super().apply_to_resolver(resolver, skip_test=skip_test)
        try:
            set_mode_lock("big3", source="big3.onboarding")
            sync_mode_lock_traits()
        except Exception:
            log.exception("Big 3 mode-lock loot bridge failed.")
        return result
