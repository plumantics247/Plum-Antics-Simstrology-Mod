"""Modal natal chart readout dialogs for social chart-reading interactions."""

from __future__ import annotations

import logging
from typing import Mapping, Optional


log = logging.getLogger("cosmic_engine.chart_read_dialogs")

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

_BODY_ORDER = (
    "Sun",
    "Moon",
    "Mercury",
    "Venus",
    "Mars",
    "Jupiter",
    "Saturn",
)

_FULL_BODY_ORDER = _BODY_ORDER + (
    "Uranus",
    "Neptune",
    "Pluto",
    "Chiron",
)


def _raw_text(value):
    from sims4.localization import LocalizationHelperTuning  # type: ignore

    return LocalizationHelperTuning.get_raw_text(str(value))


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
    for candidate in (
        response,
        getattr(response, "name", None),
        str(response) if response is not None else None,
    ):
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
        log.exception("Failed to show chart readout dialog.")
        return False


def _sign_name_from_index(sign_index) -> str:
    try:
        return _SIGNS[int(sign_index) % len(_SIGNS)]
    except Exception:
        return "Unknown"


def _house_label_from_index(house_index) -> str:
    try:
        return _HOUSES[int(house_index) % len(_HOUSES)]
    except Exception:
        return "Unknown House"


def _subject_first_name(subject_name: str) -> str:
    text = str(subject_name or "").strip()
    if not text:
        return "this Sim"
    return text.split()[0]


def _screen_one_text(subject_name: str, payload: Mapping[str, object]) -> str:
    subject_name = _subject_first_name(subject_name)
    sun_sign = _sign_name_from_index(payload.get("sun_sign_index"))
    rising_sign = _sign_name_from_index(payload.get("rising_sign_index"))
    moon_sign = _sign_name_from_index(payload.get("moon_sign_index"))
    return (
        "After taking a closer look at {0}'s chart, the core of it comes into focus.\n\n"
        "{0}'s Sun is in {1}, shaping the central tone of the chart.\n"
        "{0}'s Rising sign is {2}, influencing the way they come across.\n"
        "{0}'s Moon is in {3}, revealing the emotional side of the chart."
    ).format(subject_name or "this Sim", sun_sign, rising_sign, moon_sign)


def _screen_two_text(payload: Mapping[str, object]) -> str:
    house_sign_by_index = dict(payload.get("house_sign_by_index") or {})
    lines = ["The houses of the chart unfold in this order:"]
    for house_index in range(12):
        sign_index = house_sign_by_index.get(house_index)
        lines.append(
            "The {0} opens in {1}.".format(
                _house_label_from_index(house_index),
                _sign_name_from_index(sign_index),
            )
        )
    return "\n".join(lines)


def _screen_three_text(payload: Mapping[str, object]) -> str:
    house_by_body = dict(payload.get("house_by_body") or {})
    house_sign_by_index = dict(payload.get("house_sign_by_index") or {})
    lines = ["The planets settle into the chart like this:"]
    for body_name in _FULL_BODY_ORDER:
        house_index = house_by_body.get(body_name)
        if house_index is None:
            continue
        house_label = _house_label_from_index(house_index)
        sign_name = _sign_name_from_index(house_sign_by_index.get(house_index))
        lines.append(
            "{0} rests in the {1}, in {2}.".format(body_name, house_label, sign_name)
        )
    return "\n".join(lines)


def show_chart_readout_dialog_sequence(
    owner,
    *,
    subject_name: str,
    payload: Mapping[str, object],
) -> bool:
    if owner is None or not isinstance(payload, Mapping):
        return False

    subject_name = _subject_first_name(subject_name)
    screen_one_title = "A Natal Reading: {0}".format(str(subject_name or "Sim"))
    screen_two_title = "House Placements: {0}".format(str(subject_name or "Sim"))
    screen_three_title = "Planetary Placements: {0}".format(str(subject_name or "Sim"))

    def _show_screen_three():
        def _on_response(dialog):
            _response_accepted(dialog)

        return _show_ok_cancel_dialog(
            owner,
            title=screen_three_title,
            text=_screen_three_text(payload),
            ok_text="Amazing!",
            cancel_text="Close",
            on_response=_on_response,
        )

    def _show_screen_two():
        def _on_response(dialog):
            if _response_accepted(dialog):
                _show_screen_three()

        return _show_ok_cancel_dialog(
            owner,
            title=screen_two_title,
            text=_screen_two_text(payload),
            ok_text="Where Are The Planets?",
            cancel_text="Close",
            on_response=_on_response,
        )

    def _on_screen_one_response(dialog):
        if _response_accepted(dialog):
            _show_screen_two()

    return _show_ok_cancel_dialog(
        owner,
        title=screen_one_title,
        text=_screen_one_text(str(subject_name or "this Sim"), payload),
        ok_text="Tell Me About The Houses",
        cancel_text="Close",
        on_response=_on_screen_one_response,
    )


def chart_readout_available(payload: Optional[Mapping[str, object]]) -> bool:
    if not isinstance(payload, Mapping):
        return False

    return bool(
        payload.get("sun_sign_index") is not None
        and payload.get("moon_sign_index") is not None
        and payload.get("rising_sign_index") is not None
        and isinstance(payload.get("house_sign_by_index"), Mapping)
        and isinstance(payload.get("house_by_body"), Mapping)
    )
