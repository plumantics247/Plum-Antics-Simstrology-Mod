"""First-load lane chooser for the merged Simstrological mod."""

from __future__ import annotations

import logging
from .dirty_sync_queue import (
    SCOPE_MOON_RETURN,
    SCOPE_NATAL_SNAPSHOTS,
    SCOPE_PLANET_HOUSES,
    SCOPE_RETROGRADE_CONSEQUENCES,
    SCOPE_RETROGRADE_MARKERS,
    SCOPE_RISING_BUFFS,
    SCOPE_SOLAR_RETURN,
    SCOPE_VISIBLE_SIGN_BUFFS,
    mark_sim_dirty,
)
from .mode_lock import (
    get_mode_lock,
    get_onboarding_choice,
    has_startup_intro_been_seen,
    mark_startup_intro_seen,
    restore_mode_lock_from_traits,
    set_mode_lock,
    set_onboarding_choice,
    sync_mode_lock_traits,
)
from .sim_eligibility import sim_age_token, sim_info_is_teen, sim_info_is_teen_plus

log = logging.getLogger("cosmic_engine.first_load_chooser")

_STATE = {
    "zone_token": None,
    "prompt_shown": False,
    "prompt_open": False,
    "reminder_shown": False,
    "startup_shown": False,
    "progressed_sun_repair_run": False,
}

_MODE_BIG3 = "big3"
_MODE_COSMIC = "cosmic"
_BIG3_CHOOSE_SUN = "big3_choose_sun"
_BIG3_AUTO_SUN = "big3_auto_sun"
_COSMIC_CHOOSE_RISING = "cosmic_choose_rising"
_COSMIC_AUTO_RISING = "cosmic_auto_rising"
_COSMIC_RANDOM_RISING_LOOT_ID = 13736671501533187753  # PlumAntics_Big3ModCore_AssignRisingRandomPythonLoot
_COSMIC_POST_RISING_LOOT_IDS = (
    1004717949285038159,   # PlumAntics_CosmicEngineCore_LootApplyChartRulerFromRising
    11593030835386645003,  # PlumAntics_CosmicEngineHouses_AssignHouseSignMarkers_Router
    17129410494824426042,  # PlumAntics_CosmicEngineCore_NatalOnboardActiveHousehold_RandomSunMoon_Loot
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
_BIG3_OVERLAY_TRAIT_IDS = frozenset(_BIG3_VISIBLE_TO_OVERLAY_TRAITS.values())
_BIG3_VISIBLE_SIGN_TRAIT_IDS = frozenset(
    tuple(_BIG3_VISIBLE_TO_OVERLAY_TRAITS.keys())
    + (
        2783528558, 4080273607, 4264462837, 4251664764, 2968393124, 3468113049,
        2266439355, 2174778494, 3557938955, 2620839130, 3434935389, 3315030320,
    )
)
_CHILD_SIGN_TRAIT_IDS = frozenset((
    3783101473, 3842962216, 2244718878, 3458744911, 2371225943, 3601156450,
    2242137868, 4146504465, 2960173532, 2468678669, 3531629942, 2482632787,
    3140110952, 2256432599, 2486769629, 3745288030, 2193822502, 3427300985,
    4192947363, 3281776120, 2149482963, 4281931244, 2273572533, 3941651034,
    2556464803, 2876463128, 3659512874, 2163793645, 4183058533, 3959174614,
    3563105540, 3287451699, 3366999604, 2422000375, 3441966546, 2667776889,
))
_CHILDHOOD_TEEN_TRANSITION_LOOT_ID_BY_CHILD_TRAIT_ID = {
    3140110952: 15345425176956107593,  # Aquarius Moon Child -> Aquarius Moon ChildtoAdult
    2556464803: 16357693608118193232,  # Aquarius Rising Child -> Aquarius Rising ChildtoAdult
    3783101473: 10114584906899919534,  # Aquarius Sun Child -> Aquarius Sun ChildtoAdult
    2256432599: 11347478337950614972,  # Aries Moon Child -> Aries Moon ChildtoAdult
    2876463128: 16789095385617192121,  # Aries Rising Child -> Aries Rising ChildtoAdult
    3842962216: 16461971349823626041,  # Aries Sun Child -> Aries Sun ChildtoAdult
    2486769629: 15213496317711475522,  # Cancer Moon Child -> Cancer Moon ChildtoAdult
    3659512874: 16170870568227801491,  # Cancer Rising Child -> Cancer Rising ChildtoAdult
    2244718878: 10188800475263019983,  # Cancer Sun Child -> Cancer Sun ChildtoAdult
    3745288030: 11675490271077611871,  # Capricorn Moon Child -> Capricorn Moon ChildtoAdult
    2163793645: 17856089685486901490,  # Capricorn Rising Child -> Capricorn Rising ChildtoAdult
    3458744911: 14745513359153420612,  # Capricorn Sun Child -> Capricorn Sun ChildtoAdult
    2193822502: 15878407536200947159,  # Gemini Moon Child -> Gemini Moon ChildtoAdult
    4183058533: 13203855427479826362,  # Gemini Rising Child -> Gemini Rising ChildtoAdult
    2371225943: 11777392770927951772,  # Gemini Sun Child -> Gemini Sun ChildtoAdult
    3427300985: 14228236787154234646,  # Leo Moon Child -> Leo Moon ChildtoAdult
    3959174614: 16432387521705701895,  # Leo Rising Child -> Leo Rising ChildtoAdult
    3601156450: 9799069938883250859,   # Leo Sun Child -> Leo Sun ChildtoAdult
    4192947363: 12725787461719515264,  # Libra Moon Child -> Libra Moon ChildtoAdult
    3563105540: 9759706899784560189,   # Libra Rising Child -> Libra Rising ChildtoAdult
    2242137868: 14085478345712914117,  # Libra Sun Child -> Libra Sun ChildtoAdult
    3281776120: 17650263875298816729,  # Pisces Moon Child -> Pisces Moon ChildtoAdult
    3287451699: 15432358265917582560,  # Pisces Rising Child -> Pisces Rising ChildtoAdult
    4146504465: 12358806134265559070,  # Pisces Sun Child -> Pisces Sun ChildtoAdult
    2149482963: 11212330641633828144,  # Sagittarius Moon Child -> Sagittarius Moon ChildtoAdult
    3366999604: 15631493942480986349,  # Sagittarius Rising Child -> Sagittarius Rising ChildtoAdult
    2960173532: 9812947896367379541,   # Sagittarius Sun Child -> Sagittarius Sun ChildtoAdult
    4281931244: 9702324277103300597,   # Scorpio Moon Child -> Scorpio Moon ChildtoAdult
    2422000375: 18240109961547430060,  # Scorpio Rising Child -> Scorpio Rising ChildtoAdult
    2468678669: 18064778962782030946,  # Scorpio Sun Child -> Scorpio Sun ChildtoAdult
    2273572533: 16446177437283623642,  # Taurus Moon Child -> Taurus Moon ChildtoAdult
    3441966546: 16474036099307117851,  # Taurus Rising Child -> Taurus Rising ChildtoAdult
    3531629942: 10299129352156347104,  # Taurus Sun Child -> Taurus Sun ChildtoAdult
    3941651034: 13343565235242637875,  # Virgo Moon Child -> Virgo Moon ChildtoAdult
    2667776889: 14108969550490381126,  # Virgo Rising Child -> Virgo Rising ChildtoAdult
    2482632787: 15863064418527561040,  # Virgo Sun Child -> Virgo Sun ChildtoAdult
}
_CHILDHOOD_TEEN_TRANSITION_REFRESH_LOOT_ID = 13880462707991368211  # PlumAntics_Big3ModCore_SimstrologyRefreshContext_LifecycleRouter
_PROGRESSED_SUN_HIDDEN_TO_VISIBLE = {
    2430415371153613317: 5953957637810307587,    # Aquarius
    8960710436078173163: 13216465842102949165,   # Aries
    9482021035416149987: 7919214858024667693,    # Cancer
    12757816750258922783: 5897751160630956732,   # Capricorn
    3020418863475258838: 17089497667938906938,   # Gemini
    14016795132588088885: 2112115294144745887,   # Leo
    10569329109792809204: 14531976952067705793,  # Libra
    12963778258377165850: 16135404306587182352,  # Pisces
    11835246999168645709: 11076948783815627390,  # Sagittarius
    6149863072453466546: 17006511625883094722,   # Scorpio
    1637815211027082137: 380949979615310389,     # Taurus
    5224110435693224387: 1447257088555882719,    # Virgo
}
_PROGRESSED_SUN_HIDDEN_TRAIT_IDS = frozenset(_PROGRESSED_SUN_HIDDEN_TO_VISIBLE.keys())
_PROGRESSED_SUN_VISIBLE_TRAIT_IDS = frozenset(_PROGRESSED_SUN_HIDDEN_TO_VISIBLE.values())
_PROGRESSED_SUN_REPAIR_LOOT_ID = 5885820251439532618  # PlumAntics_Big3ModHousesProgressions_ProgressionsLootRouter
_PROGRESSED_SUN_NOTICE_BUFF_ID = 12138083489731341024  # PlumAntics_Big3Mod_ProgressedSunNotice_EvaluatedRecently
_POST_TEEN_HANDOFF_DIRTY_SCOPES = (
    SCOPE_PLANET_HOUSES,
    SCOPE_NATAL_SNAPSHOTS,
    SCOPE_VISIBLE_SIGN_BUFFS,
    SCOPE_RISING_BUFFS,
    SCOPE_MOON_RETURN,
    SCOPE_SOLAR_RETURN,
    SCOPE_RETROGRADE_MARKERS,
    SCOPE_RETROGRADE_CONSEQUENCES,
)


def reset_first_load_chooser_state(*, zone_token=None):
    _STATE["zone_token"] = zone_token
    _STATE["prompt_shown"] = False
    _STATE["prompt_open"] = False
    _STATE["reminder_shown"] = False
    _STATE["startup_shown"] = False
    _STATE["progressed_sun_repair_run"] = False


def _active_sim_info():
    try:
        import services  # type: ignore
    except Exception:
        return None
    try:
        client_manager = services.client_manager()
    except Exception:
        client_manager = None
    if client_manager is None:
        return None
    get_first_client = getattr(client_manager, "get_first_client", None)
    client = None
    if callable(get_first_client):
        try:
            client = get_first_client()
        except Exception:
            client = None
    if client is None:
        return None
    sim_info = getattr(client, "active_sim_info", None)
    if sim_info is not None:
        return sim_info
    active_sim = getattr(client, "active_sim", None)
    if active_sim is not None:
        return getattr(active_sim, "sim_info", None) or active_sim
    return None


def _raw_text(text):
    try:
        from sims4.localization import LocalizationHelperTuning  # type: ignore

        return LocalizationHelperTuning.get_raw_text(str(text))
    except Exception:
        return str(text)


def _show_notification(owner, title, text):
    try:
        from ui.ui_dialog_notification import UiDialogNotification  # type: ignore

        notification = UiDialogNotification.TunableFactory().default(
            owner,
            title=lambda *_, **__: _raw_text(title),
            text=lambda *_, **__: _raw_text(text),
        )
        notification.show_dialog()
        return True
    except Exception:
        return False


def _show_action_result(owner, *, ok, success_title, success_text, failure_text):
    if ok:
        _show_notification(owner, success_title, success_text)
        return True
    _show_notification(owner, success_title, failure_text)
    return False


def _run_loot_on_sim_info(sim_info, loot_id):
    try:
        import services  # type: ignore
        import sims4.resources  # type: ignore
    except Exception:
        return False

    if sim_info is None or loot_id is None:
        return False

    try:
        manager = services.get_instance_manager(sims4.resources.Types.ACTION)
    except Exception:
        manager = None
    if manager is None:
        return False

    try:
        tuning = manager.get(int(loot_id))
    except Exception:
        tuning = None
    if tuning is None:
        return False

    resolver_getter = getattr(sim_info, "get_resolver", None)
    if not callable(resolver_getter):
        return False
    try:
        resolver = resolver_getter()
    except Exception:
        resolver = None
    if resolver is None:
        return False

    for method_name in (
        "apply_to_resolver",
        "apply_to_resolver_and_get_result",
        "apply_to_single_resolver",
    ):
        method = getattr(tuning, method_name, None)
        if not callable(method):
            continue
        try:
            method(resolver)
            return True
        except Exception:
            continue
    return False


def _resolve_trait_tuning(trait_id):
    try:
        import services  # type: ignore
        import sims4.resources  # type: ignore
    except Exception:
        return None
    try:
        manager = services.get_instance_manager(sims4.resources.Types.TRAIT)
    except Exception:
        manager = None
    if manager is None:
        return None
    try:
        return manager.get(int(trait_id))
    except Exception:
        return None


def _sim_has_trait(sim_info, trait_id):
    trait_tracker = getattr(sim_info, "trait_tracker", None)
    if trait_tracker is None:
        return False
    equipped = getattr(trait_tracker, "equipped_traits", None) or ()
    for trait in equipped:
        guid = getattr(trait, "guid64", None)
        if guid is None:
            guid = getattr(trait, "guid", None)
        try:
            if int(guid) == int(trait_id):
                return True
        except Exception:
            continue
    return False


def _remove_trait_if_present(sim_info, trait_id):
    if not _sim_has_trait(sim_info, trait_id):
        return False
    trait = _resolve_trait_tuning(trait_id)
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


def _sim_has_any_trait(sim_info, trait_ids):
    for trait_id in tuple(trait_ids or ()):
        if _sim_has_trait(sim_info, trait_id):
            return True
    return False


def _collect_present_trait_ids(sim_info, trait_ids):
    return tuple(trait_id for trait_id in tuple(trait_ids or ()) if _sim_has_trait(sim_info, trait_id))


def _remove_traits_if_present(sim_info, trait_ids):
    changed = False
    for trait_id in tuple(trait_ids or ()):
        if _remove_trait_if_present(sim_info, trait_id):
            changed = True
    return changed


def _progressed_sun_state_is_consistent(hidden_trait_ids, visible_trait_ids):
    if len(tuple(hidden_trait_ids or ())) != 1 or len(tuple(visible_trait_ids or ())) != 1:
        return False
    hidden_trait_id = int(tuple(hidden_trait_ids)[0])
    visible_trait_id = int(tuple(visible_trait_ids)[0])
    return int(_PROGRESSED_SUN_HIDDEN_TO_VISIBLE.get(hidden_trait_id, -1)) == visible_trait_id


def repair_progressed_sun_state(sim_info):
    summary = {
        "ok": sim_info is not None,
        "sim_id": None,
        "age": "",
        "hidden_before": (),
        "visible_before": (),
        "hidden_after": (),
        "visible_after": (),
        "changed": False,
        "rerun_ok": False,
        "consistent_after": False,
        "reason": "",
    }

    if sim_info is None:
        summary["reason"] = "missing_sim"
        return summary

    summary["sim_id"] = getattr(sim_info, "sim_id", None) or getattr(sim_info, "id", None)
    summary["age"] = sim_age_token(sim_info)
    summary["hidden_before"] = _collect_present_trait_ids(sim_info, _PROGRESSED_SUN_HIDDEN_TRAIT_IDS)
    summary["visible_before"] = _collect_present_trait_ids(sim_info, _PROGRESSED_SUN_VISIBLE_TRAIT_IDS)

    if not summary["hidden_before"] and not summary["visible_before"]:
        summary["reason"] = "no_progressed_state"
        return summary

    if not _is_teen_or_older_sim(sim_info):
        removed = _remove_traits_if_present(
            sim_info,
            tuple(_PROGRESSED_SUN_HIDDEN_TRAIT_IDS) + tuple(_PROGRESSED_SUN_VISIBLE_TRAIT_IDS),
        )
        removed_notice = _remove_trait_if_present(sim_info, _PROGRESSED_SUN_NOTICE_BUFF_ID)
        summary["hidden_after"] = _collect_present_trait_ids(sim_info, _PROGRESSED_SUN_HIDDEN_TRAIT_IDS)
        summary["visible_after"] = _collect_present_trait_ids(sim_info, _PROGRESSED_SUN_VISIBLE_TRAIT_IDS)
        summary["changed"] = bool(removed or removed_notice)
        summary["consistent_after"] = not summary["hidden_after"] and not summary["visible_after"]
        summary["reason"] = "cleared_for_age"
        return summary

    if _progressed_sun_state_is_consistent(summary["hidden_before"], summary["visible_before"]):
        summary["hidden_after"] = summary["hidden_before"]
        summary["visible_after"] = summary["visible_before"]
        summary["consistent_after"] = True
        summary["reason"] = "already_consistent"
        return summary

    removed = _remove_traits_if_present(
        sim_info,
        tuple(_PROGRESSED_SUN_HIDDEN_TRAIT_IDS) + tuple(_PROGRESSED_SUN_VISIBLE_TRAIT_IDS),
    )
    removed_notice = _remove_trait_if_present(sim_info, _PROGRESSED_SUN_NOTICE_BUFF_ID)
    summary["rerun_ok"] = bool(_run_loot_on_sim_info(sim_info, _PROGRESSED_SUN_REPAIR_LOOT_ID))
    summary["hidden_after"] = _collect_present_trait_ids(sim_info, _PROGRESSED_SUN_HIDDEN_TRAIT_IDS)
    summary["visible_after"] = _collect_present_trait_ids(sim_info, _PROGRESSED_SUN_VISIBLE_TRAIT_IDS)
    summary["consistent_after"] = _progressed_sun_state_is_consistent(
        summary["hidden_after"],
        summary["visible_after"],
    )
    summary["changed"] = bool(
        removed
        or removed_notice
        or summary["hidden_before"] != summary["hidden_after"]
        or summary["visible_before"] != summary["visible_after"]
    )
    if summary["consistent_after"]:
        summary["reason"] = "repaired"
    elif summary["rerun_ok"]:
        summary["reason"] = "still_inconsistent"
    else:
        summary["reason"] = "rerun_failed"
    return summary


def _iter_household_sim_infos(household):
    if household is None:
        return ()
    seen_ids = set()
    out = []

    def _append_candidate(candidate):
        sim_info = getattr(candidate, "sim_info", None) or candidate
        if sim_info is None:
            return
        sim_id = getattr(sim_info, "sim_id", None) or getattr(sim_info, "id", None) or id(sim_info)
        if sim_id in seen_ids:
            return
        seen_ids.add(sim_id)
        out.append(sim_info)

    sim_info_gen = getattr(household, "sim_info_gen", None)
    if callable(sim_info_gen):
        try:
            for sim_info in sim_info_gen():
                _append_candidate(sim_info)
        except Exception:
            pass

    for attr_name in ("sim_infos", "_sim_infos", "members"):
        value = getattr(household, attr_name, None)
        if value is None:
            continue
        try:
            iterator = tuple(value() if callable(value) else value)
        except Exception:
            continue
        for candidate in iterator:
            _append_candidate(candidate)
    return tuple(out)


def _iter_active_household_sim_infos():
    owner = _active_sim_info()
    household = getattr(owner, "household", None)
    if household is None:
        try:
            import services  # type: ignore
        except Exception:
            services = None
        if services is not None:
            for attr_name in ("active_household", "owning_household_of_active_lot"):
                getter = getattr(services, attr_name, None)
                if not callable(getter):
                    continue
                try:
                    household = getter()
                except Exception:
                    household = None
                if household is not None:
                    break
    return _iter_household_sim_infos(household)


def maybe_repair_active_household_progressed_sun_state(*, force=False):
    if not force and _STATE.get("progressed_sun_repair_run"):
        return False
    sim_infos = tuple(_iter_active_household_sim_infos())
    if not sim_infos:
        return False
    changed = False
    for sim_info in sim_infos:
        summary = repair_progressed_sun_state(sim_info)
        changed = bool(changed or summary.get("changed"))
    _STATE["progressed_sun_repair_run"] = True
    return changed


def _is_teen_sim(sim_info):
    return sim_info_is_teen(sim_info)


def _is_teen_or_older_sim(sim_info):
    return sim_info_is_teen_plus(sim_info)


def _sim_needs_teen_handoff(sim_info):
    if sim_info is None or not _is_teen_sim(sim_info):
        return False
    return _sim_has_any_trait(sim_info, _CHILD_SIGN_TRAIT_IDS)


def _sim_has_any_teen_sign_state(sim_info):
    return _sim_has_any_trait(
        sim_info,
        tuple(_BIG3_VISIBLE_SIGN_TRAIT_IDS) + tuple(_BIG3_OVERLAY_TRAIT_IDS),
    )


def _matching_childhood_teen_transition_loot_ids(sim_info):
    if sim_info is None:
        return ()
    matching = []
    for child_trait_id, loot_id in _CHILDHOOD_TEEN_TRANSITION_LOOT_ID_BY_CHILD_TRAIT_ID.items():
        if _sim_has_trait(sim_info, int(child_trait_id)):
            matching.append(int(loot_id))
    return tuple(matching)


def _run_matching_childhood_teen_transition_loots(sim_info):
    loot_ids = _matching_childhood_teen_transition_loot_ids(sim_info)
    if not loot_ids:
        return ()

    executed = []
    for loot_id in loot_ids:
        if _run_loot_on_sim_info(sim_info, loot_id):
            executed.append(int(loot_id))

    if executed and _run_loot_on_sim_info(sim_info, _CHILDHOOD_TEEN_TRANSITION_REFRESH_LOOT_ID):
        executed.append(int(_CHILDHOOD_TEEN_TRANSITION_REFRESH_LOOT_ID))
    return tuple(executed)


def _run_childhood_teen_transition_catchup(sim_info):
    if sim_info is None or not _is_teen_sim(sim_info):
        return False
    had_child_sign_state = _sim_has_any_trait(sim_info, _CHILD_SIGN_TRAIT_IDS)
    if not had_child_sign_state:
        return False
    had_teen_sign_state = _sim_has_any_teen_sign_state(sim_info)
    _run_matching_childhood_teen_transition_loots(sim_info)
    has_child_sign_state = _sim_has_any_trait(sim_info, _CHILD_SIGN_TRAIT_IDS)
    has_teen_sign_state = _sim_has_any_teen_sign_state(sim_info)
    return had_child_sign_state and (
        had_child_sign_state != has_child_sign_state
        or had_teen_sign_state != has_teen_sign_state
    )


def repair_childhood_teen_handoff(sim_info):
    summary = {
        "ok": sim_info is not None,
        "sim_id": None,
        "age": "",
        "had_child_sign_state": False,
        "has_child_sign_state": False,
        "had_teen_sign_state": False,
        "has_teen_sign_state": False,
        "catchup_changed": False,
        "lane_changed": False,
        "active_mode": "",
        "changed": False,
        "reason": "",
    }

    if sim_info is None:
        summary["reason"] = "missing_sim"
        return summary

    summary["sim_id"] = getattr(sim_info, "sim_id", None) or getattr(sim_info, "id", None)
    summary["age"] = sim_age_token(sim_info)
    if not _is_teen_or_older_sim(sim_info):
        summary["reason"] = "age_not_teen_plus"
        return summary

    summary["had_child_sign_state"] = _sim_has_any_trait(sim_info, _CHILD_SIGN_TRAIT_IDS)
    summary["had_teen_sign_state"] = _sim_has_any_teen_sign_state(sim_info)

    if summary["had_child_sign_state"]:
        _run_matching_childhood_teen_transition_loots(sim_info)

    summary["has_child_sign_state"] = _sim_has_any_trait(sim_info, _CHILD_SIGN_TRAIT_IDS)
    summary["has_teen_sign_state"] = _sim_has_any_teen_sign_state(sim_info)
    summary["catchup_changed"] = bool(
        summary["had_child_sign_state"]
        and (
            summary["had_child_sign_state"] != summary["has_child_sign_state"]
            or summary["had_teen_sign_state"] != summary["has_teen_sign_state"]
        )
    )

    active_mode = get_mode_lock()
    if active_mode not in (_MODE_BIG3, _MODE_COSMIC):
        active_mode = restore_mode_lock_from_traits()
    summary["active_mode"] = str(active_mode or "")

    if active_mode in (_MODE_BIG3, _MODE_COSMIC):
        if summary["had_child_sign_state"] or summary["has_child_sign_state"] or summary["has_teen_sign_state"]:
            summary["lane_changed"] = bool(_apply_lane_handoff_state(sim_info, active_mode))

    summary["changed"] = bool(summary["catchup_changed"] or summary["lane_changed"])
    if summary["changed"]:
        mark_sim_dirty(
            sim_info,
            _POST_TEEN_HANDOFF_DIRTY_SCOPES,
            reason="childhood_teen_handoff",
        )
        summary["reason"] = "repaired"
    elif summary["had_child_sign_state"]:
        summary["reason"] = "no_change"
    else:
        summary["reason"] = "no_childhood_state"
    return summary


def repair_childhood_teen_handoff_for_lifecycle(sim_info):
    return repair_childhood_teen_handoff(sim_info)


def _apply_lane_handoff_state(owner, mode):
    if owner is None:
        return False
    changed = False
    if mode == _MODE_BIG3:
        for visible_trait_id, overlay_trait_id in _BIG3_VISIBLE_TO_OVERLAY_TRAITS.items():
            if _sim_has_trait(owner, visible_trait_id) and _add_trait_to_sim_info(owner, overlay_trait_id):
                changed = True
        return changed
    if mode == _MODE_COSMIC:
        for overlay_trait_id in _BIG3_OVERLAY_TRAIT_IDS:
            if _remove_trait_if_present(owner, overlay_trait_id):
                changed = True
        return changed
    return False


def _add_trait_to_sim_info(sim_info, trait_id):
    if sim_info is None or _sim_has_trait(sim_info, trait_id):
        return False
    trait = _resolve_trait_tuning(trait_id)
    if trait is None:
        return False
    trait_tracker = getattr(sim_info, "trait_tracker", None)
    for owner in (trait_tracker, sim_info):
        add_fn = getattr(owner, "add_trait", None)
        if not callable(add_fn):
            continue
        try:
            add_fn(trait)
            return True
        except Exception:
            continue
    return False


def _run_big3_auto_sun(owner):
    try:
        from plumantics_big3_runtime.integration import bridge
    except Exception:
        log.exception("Failed importing Big 3 runtime bridge for chooser auto-sun.")
        return False

    assign_fn = getattr(bridge, "big3_universe2_assign_big3_for_sim", None)
    if not callable(assign_fn):
        return False

    sim_id = getattr(owner, "sim_id", None)
    if sim_id is None:
        sim_id = getattr(owner, "id", -1)
    try:
        return bool(
            assign_fn(
                sim_id=int(sim_id) if sim_id is not None else -1,
                sun_mode="auto",
                moon_mode="skip",
                rising_mode="skip",
                overwrite_existing=0,
                _connection=None,
            )
        )
    except Exception:
        log.exception("Big 3 chooser auto-sun failed.")
        return False


def _run_cosmic_auto_rising(owner):
    if owner is None:
        return False
    if not _run_loot_on_sim_info(owner, _COSMIC_RANDOM_RISING_LOOT_ID):
        return False
    for loot_id in _COSMIC_POST_RISING_LOOT_IDS:
        if not _run_loot_on_sim_info(owner, loot_id):
            return False
    return True


def _response_accepted(dialog):
    if dialog is None:
        return False
    for attr_name in ("accepted",):
        value = getattr(dialog, attr_name, None)
        if isinstance(value, bool):
            return value
        if callable(value):
            try:
                resolved = value()
            except Exception:
                resolved = None
            if isinstance(resolved, bool):
                return resolved
    response = getattr(dialog, "response", None)
    for candidate in (response, getattr(response, "name", None), str(response) if response is not None else None):
        text = str(candidate or "").upper()
        if text in ("DIALOG_RESPONSE_OK", "OK", "YES", "ACCEPT"):
            return True
        if text in ("DIALOG_RESPONSE_CANCEL", "CANCEL", "NO"):
            return False
    return False


def _show_ok_cancel_dialog(owner, *, title, text, ok_text, cancel_text, on_response):
    try:
        from ui.ui_dialog import UiDialogOkCancel  # type: ignore

        kwargs = {
            "title": lambda *_, **__: _raw_text(title),
            "text": lambda *_, **__: _raw_text(text),
        }
        try:
            kwargs["text_ok"] = lambda *_, **__: _raw_text(ok_text)
            kwargs["text_cancel"] = lambda *_, **__: _raw_text(cancel_text)
        except Exception:
            pass
        dialog = UiDialogOkCancel.TunableFactory().default(owner, **kwargs)
        add_listener = getattr(dialog, "add_listener", None)
        if callable(add_listener):
            add_listener(on_response)
            dialog.show_dialog()
            return True
        dialog.show_dialog(on_response=on_response)
        return True
    except Exception:
        log.exception("Failed to show modal chooser dialog.")
        return False


def _show_followup_confirmation(owner, mode, onboarding_choice):
    if mode == _MODE_BIG3:
        if onboarding_choice == _BIG3_AUTO_SUN:
            text = (
                "Sun First is active. Use the Simstrology Hub to let the universe choose your Sun sign, "
                "then continue with Moon and Rising."
            )
        else:
            text = (
                "Sun First is active. Use the Simstrology Hub to choose your Sun sign first, "
                "then continue with Moon and Rising."
            )
    else:
        if onboarding_choice == _COSMIC_AUTO_RISING:
            text = (
                "Rising First is active. Use the Simstrology Hub to let the universe choose Rising, "
                "then the universe will build the rest of the chart."
            )
        else:
            text = (
                "Rising First is active. Use the Simstrology Hub to choose Rising, "
                "then the universe will build the rest of the chart."
            )
    _show_notification(owner, "Path Chosen", text)


def _show_mode_followup(owner, mode):
    if owner is None:
        return False

    if mode == _MODE_BIG3:
        title = "Sun First"
        text = (
            "Sun First lets you shape the chart step by step. "
            "Would you like to choose your Sun sign, or let the universe choose your Sun sign first?"
        )
        ok_text = "Choose Sun"
        cancel_text = "Let the Universe Choose Sun"

        def _on_response(dialog):
            _STATE["prompt_open"] = False
            accepted = _response_accepted(dialog)
            choice = _BIG3_CHOOSE_SUN if accepted else _BIG3_AUTO_SUN
            set_onboarding_choice(choice, source="chooser.big3")
            if choice == _BIG3_AUTO_SUN:
                ok = _run_big3_auto_sun(owner)
                _show_action_result(
                    owner,
                    ok=ok,
                    success_title="Sun First Active",
                    success_text=(
                        "Your Sun sign was chosen by the universe. "
                        "Use the Simstrology Hub to choose Moon and Rising next."
                    ),
                    failure_text=(
                        "Sun First is active, but universe-chosen Sun assignment did not complete. "
                        "Use the Simstrology Hub to choose Sun manually."
                    ),
                )
            else:
                _show_followup_confirmation(owner, _MODE_BIG3, choice)

        shown = _show_ok_cancel_dialog(
            owner,
            title=title,
            text=text,
            ok_text=ok_text,
            cancel_text=cancel_text,
            on_response=_on_response,
        )
        if shown:
            _STATE["prompt_open"] = True
        return bool(shown)

    title = "Rising First"
    text = (
        "Rising First uses Rising as the anchor, then the universe determines the rest. "
        "Would you like to choose Rising yourself, or let the universe choose Rising for you?"
    )
    ok_text = "Choose Rising"
    cancel_text = "Let the Universe Choose Rising"

    def _on_response(dialog):
        _STATE["prompt_open"] = False
        accepted = _response_accepted(dialog)
        choice = _COSMIC_CHOOSE_RISING if accepted else _COSMIC_AUTO_RISING
        set_onboarding_choice(choice, source="chooser.cosmic")
        if choice == _COSMIC_AUTO_RISING:
            ok = _run_cosmic_auto_rising(owner)
            _show_action_result(
                owner,
                ok=ok,
                success_title="Rising First Active",
                success_text=(
                    "Your Rising sign was chosen by the universe. "
                    "The Simstrology Hub now contains the shared chart readouts."
                ),
                failure_text=(
                    "Rising First is active, but universe-chosen Rising assignment did not complete. "
                    "Use the Simstrology Hub to choose Rising manually."
                ),
            )
        else:
            _show_followup_confirmation(owner, _MODE_COSMIC, choice)

    shown = _show_ok_cancel_dialog(
        owner,
        title=title,
        text=text,
        ok_text=ok_text,
        cancel_text=cancel_text,
        on_response=_on_response,
    )
    if shown:
        _STATE["prompt_open"] = True
    return bool(shown)


def _commit_mode_choice(owner, mode):
    if mode not in (_MODE_BIG3, _MODE_COSMIC):
        return False
    set_mode_lock(mode, source="chooser")
    sync_mode_lock_traits()
    _apply_lane_handoff_state(owner, mode)
    return _show_mode_followup(owner, mode)


def maybe_show_first_load_chooser(*, zone_token=None, force=False):
    if not force:
        if get_mode_lock() is not None:
            return False
        if get_onboarding_choice() is not None:
            return False
        if _STATE.get("prompt_shown"):
            return False
        if _STATE.get("prompt_open"):
            return False

    owner = _active_sim_info()
    if owner is None:
        return False
    if not _is_teen_or_older_sim(owner):
        return False

    title = "Choose Your Simstrology Path"
    text = (
        "Sun First lets you choose the chart step by step, beginning with Sun. "
        "Rising First begins with Rising and lets you either choose Rising by time or let the universe randomize the rest."
    )
    ok_text = "Sun First"
    cancel_text = "Rising First"

    def _on_response(dialog):
        _STATE["prompt_open"] = False
        accepted = _response_accepted(dialog)
        mode = _MODE_BIG3 if accepted else _MODE_COSMIC
        _commit_mode_choice(owner, mode)

    shown = _show_ok_cancel_dialog(
        owner,
        title=title,
        text=text,
        ok_text=ok_text,
        cancel_text=cancel_text,
        on_response=_on_response,
    )
    if not shown:
        _show_notification(
            owner,
            title,
            "Use the Simstrology Hub to begin with Sun First or Rising First.",
        )
        return False

    _STATE["zone_token"] = zone_token
    _STATE["prompt_shown"] = True
    _STATE["prompt_open"] = True
    return True


def maybe_show_first_load_reminder(*, force=False):
    owner = _active_sim_info()
    if owner is None:
        return False
    if not _is_teen_or_older_sim(owner):
        return False

    if not force:
        restored_mode = restore_mode_lock_from_traits()
        if restored_mode in (_MODE_BIG3, _MODE_COSMIC):
            sync_mode_lock_traits()
            return False
        if _sim_has_any_trait(
            owner,
            tuple(_BIG3_VISIBLE_SIGN_TRAIT_IDS) + tuple(_BIG3_OVERLAY_TRAIT_IDS),
        ):
            return False
        if get_mode_lock() is not None:
            return False
        if get_onboarding_choice() is not None:
            return False
        if _STATE.get("prompt_open"):
            return False
        if _STATE.get("reminder_shown"):
            return False

    shown = _show_notification(
        owner,
        "Choose Your Simstrology Path",
        (
            "This save has not chosen a Simstrology path yet. "
            "Use the Simstrology Hub to begin with Sun First or Rising First."
        ),
    )
    if shown:
        _STATE["reminder_shown"] = True
    return bool(shown)


def maybe_show_startup_intro(*, force=False):
    owner = _active_sim_info()
    if owner is None:
        return False

    if not force:
        if _STATE.get("startup_shown"):
            return False
        if has_startup_intro_been_seen():
            return False

    shown = _show_notification(
        owner,
        "Welcome to Simstrology",
        (
            "Simstrology is now active in this save. A universal Simstrological clock now keeps "
            "chart state, transits, retrogrades, and future add-ons synced across the save. Use "
            "your Simstrology Hub to begin with Sun First or Rising First."
        ),
    )
    if shown:
        _STATE["startup_shown"] = True
        mark_startup_intro_seen(source="startup_intro")
    return bool(shown)


def maybe_process_teen_handoff(*, force=False):
    owner = _active_sim_info()
    if owner is None or not _is_teen_sim(owner):
        return False

    active_mode = get_mode_lock()
    if active_mode not in (_MODE_BIG3, _MODE_COSMIC):
        active_mode = restore_mode_lock_from_traits()
    had_child_sign_state = _sim_has_any_trait(owner, _CHILD_SIGN_TRAIT_IDS)
    has_child_sign_state = _sim_has_any_trait(owner, _CHILD_SIGN_TRAIT_IDS)
    has_teen_sign_state = _sim_has_any_teen_sign_state(owner)

    # Trust the XML age-up handoff for the normal birthday path. If child traits
    # are still present, the transition is either still settling or needs a manual
    # repair pass, so avoid re-running the conversion loots from the clock hook.
    catchup_changed = False
    if force and had_child_sign_state and not has_teen_sign_state:
        catchup_changed = _run_childhood_teen_transition_catchup(owner)
        has_child_sign_state = _sim_has_any_trait(owner, _CHILD_SIGN_TRAIT_IDS)
        has_teen_sign_state = _sim_has_any_teen_sign_state(owner)

    if active_mode in (_MODE_BIG3, _MODE_COSMIC):
        if has_teen_sign_state and not has_child_sign_state:
            lane_changed = _apply_lane_handoff_state(owner, active_mode)
            return bool(catchup_changed or lane_changed)
        return bool(catchup_changed)

    if not has_teen_sign_state or has_child_sign_state:
        return bool(catchup_changed)

    if not force:
        if get_onboarding_choice() is not None:
            return bool(catchup_changed)
        if _STATE.get("prompt_shown") or _STATE.get("prompt_open"):
            return bool(catchup_changed)

    title = "Choose a Teen Simstrology Path"
    text = (
        "This Sim has reached the teen years and can now follow a full Simstrology lane. "
        "Choose Sun First to shape the chart step by step, or choose Rising First to build from Rising and complete the chart afterward."
    )
    ok_text = "Sun First"
    cancel_text = "Rising First"

    def _on_response(dialog):
        _STATE["prompt_open"] = False
        accepted = _response_accepted(dialog)
        mode = _MODE_BIG3 if accepted else _MODE_COSMIC
        _commit_mode_choice(owner, mode)

    shown = _show_ok_cancel_dialog(
        owner,
        title=title,
        text=text,
        ok_text=ok_text,
        cancel_text=cancel_text,
        on_response=_on_response,
    )
    if shown:
        _STATE["prompt_shown"] = True
        _STATE["prompt_open"] = True
    return bool(shown or catchup_changed)
