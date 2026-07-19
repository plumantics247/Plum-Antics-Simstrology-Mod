"""Assignment mode constants and parsing helpers for universe_engine.v2."""

from dataclasses import dataclass


AGE_INFANT = "INFANT"
AGE_TODDLER = "TODDLER"
AGE_CHILD = "CHILD"
AGE_TEEN = "TEEN"
AGE_YOUNG_ADULT = "YOUNGADULT"
AGE_ADULT = "ADULT"
AGE_ELDER = "ELDER"


SUN_MODE_AUTO = "auto"
SUN_MODE_SKIP = "skip"
SUN_MODE_SEASON = "season"
SUN_MODE_PERSONALITY = "personality"

MOON_MODE_AUTO = "auto"
MOON_MODE_SKIP = "skip"
MOON_MODE_LUNAR_PHASE = "lunar_phase"
MOON_MODE_RANDOM = "random"
MOON_MODE_NATAL = "natal"

RISING_MODE_AUTO = "auto"
RISING_MODE_SKIP = "skip"
RISING_MODE_SUN_TIME = "sun_time"
RISING_MODE_RANDOM = "random"


SUN_MODES = (
    SUN_MODE_AUTO,
    SUN_MODE_SKIP,
    SUN_MODE_SEASON,
    SUN_MODE_PERSONALITY,
)
MOON_MODES = (
    MOON_MODE_AUTO,
    MOON_MODE_SKIP,
    MOON_MODE_LUNAR_PHASE,
    MOON_MODE_RANDOM,
    MOON_MODE_NATAL,
)
RISING_MODES = (
    RISING_MODE_AUTO,
    RISING_MODE_SKIP,
    RISING_MODE_SUN_TIME,
    RISING_MODE_RANDOM,
)


@dataclass
class AssignmentRequest:
    """Requested assignment modes for one sim."""

    sun_mode: str = SUN_MODE_AUTO
    moon_mode: str = MOON_MODE_AUTO
    rising_mode: str = RISING_MODE_AUTO
    overwrite_existing: bool = False


def normalize_age_name(age_name):
    if age_name is None:
        return None
    text = str(age_name).strip().upper()
    if "." in text:
        text = text.split(".")[-1]
    return text or None


def is_childhood_age(age_name):
    token = normalize_age_name(age_name)
    return token in (AGE_INFANT, AGE_TODDLER, AGE_CHILD)


def is_teen_plus_age(age_name):
    token = normalize_age_name(age_name)
    return token in (AGE_TEEN, AGE_YOUNG_ADULT, AGE_ADULT, AGE_ELDER)


def _normalize_mode(value, supported_modes, default_mode):
    text = str(value).strip().lower() if value is not None else ""
    if text in supported_modes:
        return text
    return str(default_mode)


def normalize_assignment_request(request, defaults=None):
    if not isinstance(request, AssignmentRequest):
        request = AssignmentRequest()

    defaults = defaults or {}
    sun_default = defaults.get("sun_mode", SUN_MODE_AUTO)
    moon_default = defaults.get("moon_mode", MOON_MODE_AUTO)
    rising_default = defaults.get("rising_mode", RISING_MODE_AUTO)

    return AssignmentRequest(
        sun_mode=_normalize_mode(request.sun_mode, SUN_MODES, sun_default),
        moon_mode=_normalize_mode(request.moon_mode, MOON_MODES, moon_default),
        rising_mode=_normalize_mode(request.rising_mode, RISING_MODES, rising_default),
        overwrite_existing=bool(request.overwrite_existing),
    )
