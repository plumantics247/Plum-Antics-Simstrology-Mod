from __future__ import annotations

import hashlib
import json
import pathlib
import zlib
from typing import Dict, Iterable, Tuple


ROOT = pathlib.Path(__file__).resolve().parents[1]
TRAIT_DIR = ROOT / "src" / "OuterPlanets" / "Trait"
BUFF_DIR = ROOT / "src" / "OuterPlanets" / "Buff"
STRING_TABLE_PATH = ROOT / "src" / "String" / "SimstrologicalMod_English.stbl.json"

ALL_HOUSES: Tuple[Tuple[str, int, str], ...] = (
    ("First", 1, "1st"),
    ("Second", 2, "2nd"),
    ("Third", 3, "3rd"),
    ("Fourth", 4, "4th"),
    ("Fifth", 5, "5th"),
    ("Sixth", 6, "6th"),
    ("Seventh", 7, "7th"),
    ("Eighth", 8, "8th"),
    ("Ninth", 9, "9th"),
    ("Tenth", 10, "10th"),
    ("Eleventh", 11, "11th"),
    ("Twelfth", 12, "12th"),
)
VISIBLE_HOUSES = ("First", "Fourth", "Tenth")
OUTER_BODIES = ("Uranus", "Neptune", "Pluto", "Chiron")
AGES_XML = """    <L n="ages">
        <E>INFANT</E>
        <E>TODDLER</E>
        <E>CHILD</E>
        <E>TEEN</E>
        <E>YOUNGADULT</E>
        <E>ADULT</E>
        <E>ELDER</E>
    </L>"""
AGES_SIMDATA = """      <L name="ages">
        <T type="Int64">128</T>
        <T type="Int64">2</T>
        <T type="Int64">4</T>
        <T type="Int64">8</T>
        <T type="Int64">16</T>
        <T type="Int64">32</T>
        <T type="Int64">64</T>
      </L>"""
VISIBLE_ICON_XML_BY_BODY = {
    "Uranus": "2f7d0004:00000000:a8f7344c2d7b91e1",
    "Neptune": "2f7d0004:00000000:b61c9d4f7ae20358",
    "Pluto": "2f7d0004:00000000:c4e8a91b5fd07236",
    "Chiron": "2f7d0004:00000000:c4e8a91b5fd07236",
}
VISIBLE_ICON_SIMDATA_BY_BODY = {
    "Uranus": "2F7D0004-00000000-A8F7344C2D7B91E1",
    "Neptune": "2F7D0004-00000000-B61C9D4F7AE20358",
    "Pluto": "2F7D0004-00000000-C4E8A91B5FD07236",
    "Chiron": "2F7D0004-00000000-C4E8A91B5FD07236",
}
BUFF_AUDIO_ADD_XML = "39b2aa4a:00000000:8af8b916cf64c646"
BUFF_AUDIO_REMOVE_XML = "39b2aa4a:00000000:3bf33216a25546ea"
BUFF_AUDIO_ADD_SIMDATA = "FD04E3BE-00000000-8AF8B916CF64C646"
BUFF_AUDIO_REMOVE_SIMDATA = "FD04E3BE-00000000-3BF33216A25546EA"
BODY_MOODS = {
    "Uranus": ("15799275429558895056", "1"),
    "Neptune": ("9986929074150603838", "1"),
    "Pluto": ("15435392828079855046", "2"),
    "Chiron": ("16174400495578286549", "1"),
}
VISIBLE_COPY = {
    ("First", "Uranus"): (
        "Uranus Transiting The 1st House: Wild Card Aura",
        "You're harder to pin down; reinvention feels easier than repetition.",
    ),
    ("Fourth", "Uranus"): (
        "Uranus Transiting The 4th House: Restless Nest",
        "Home life wants fresh air, rearrangement, and one unexpected detour.",
    ),
    ("Tenth", "Uranus"): (
        "Uranus Transiting The 10th House: Career Plot Twist",
        "Your public path starts zigging where everyone expected a zag.",
    ),
    ("First", "Neptune"): (
        "Neptune Transiting The 1st House: Soft Focus Persona",
        "You come across dreamier, more porous, and slightly harder to read.",
    ),
    ("Fourth", "Neptune"): (
        "Neptune Transiting The 4th House: Private Fog Bank",
        "Home becomes a retreat, a daydream, or a place to drift for a while.",
    ),
    ("Tenth", "Neptune"): (
        "Neptune Transiting The 10th House: Mythmaking Season",
        "Your reputation takes on glamour, mystery, or projection from others.",
    ),
    ("First", "Pluto"): (
        "Pluto Transiting The 1st House: Rebuild the Self",
        "Something in your presentation is shedding skin; the old mask feels too small.",
    ),
    ("Fourth", "Pluto"): (
        "Pluto Transiting The 4th House: Basement Excavation",
        "Home life pulls up buried feelings, old power dynamics, and necessary repairs.",
    ),
    ("Tenth", "Pluto"): (
        "Pluto Transiting The 10th House: Power Climb",
        "Ambition sharpens, stakes rise, and your public role starts feeling more consequential.",
    ),
    ("First", "Chiron"): (
        "Chiron Transiting The 1st House: Tender Edges",
        "Old insecurities sit closer to the surface, but so does the chance to own them.",
    ),
    ("Fourth", "Chiron"): (
        "Chiron Transiting The 4th House: Ancestral Ache",
        "Home stirs older hurts, making care, repair, and honesty harder to avoid.",
    ),
    ("Tenth", "Chiron"): (
        "Chiron Transiting The 10th House: Public Bruise, Public Lesson",
        "Career pressure exposes a sore spot, but it also shows where growth has to happen.",
    ),
}


def _instance_id(name: str) -> int:
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF


def _xml_localized(key: str, value: str) -> str:
    return "{0}<!--{1}-->".format(_normalize_localization_key(key), value)


def _house_number_label(house_name: str) -> str:
    for name, _, ordinal in ALL_HOUSES:
        if name == house_name:
            return ordinal
    raise KeyError(house_name)


def _stable_string_key(token: str, used_keys: Dict[str, str]) -> str:
    seed = int(zlib.crc32(token.encode("utf-8")) & 0xFFFFFFFF)
    for offset in range(0, 10000):
        candidate = "0x{0:08X}".format((seed + offset) & 0xFFFFFFFF)
        current = used_keys.get(candidate)
        if current is None or current == token:
            return candidate
    raise RuntimeError("Unable to allocate unique STBL key for {0}".format(token))


def _normalize_localization_key(key: str) -> str:
    text = str(key)
    if text.lower().startswith("0x"):
        return "0x" + text[2:].upper()
    return text.upper()


def _load_string_table():
    payload = json.loads(STRING_TABLE_PATH.read_text(encoding="utf-8"))
    entries = list(payload.get("entries", ()))
    key_to_value = {_normalize_localization_key(entry["key"]): str(entry["value"]) for entry in entries}
    value_to_key = {str(entry["value"]): _normalize_localization_key(entry["key"]) for entry in entries}
    return payload, entries, key_to_value, value_to_key


def _ensure_string_value(
    value: str,
    *,
    token: str,
    entries: list,
    key_to_value: Dict[str, str],
    value_to_key: Dict[str, str],
) -> str:
    existing = value_to_key.get(value)
    if existing is not None:
        return existing
    key = _stable_string_key(token, key_to_value)
    key_to_value[key] = value
    value_to_key[value] = key
    entries.append({"key": key, "value": value})
    return key


def _trait_xml(
    name: str,
    *,
    display_name_key: str,
    display_name_text: str,
    description_key: str | None = None,
    description_text: str | None = None,
    visible: bool,
    icon_xml: str | None = None,
) -> str:
    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<I c="Trait" i="trait" m="traits.traits" n="{0}" s="{1}">'.format(name, _instance_id(name)),
        AGES_XML,
        '    <T n="display_name">{0}</T>'.format(_xml_localized(display_name_key, display_name_text)),
        '    <T n="display_name_gender_neutral">{0}</T>'.format(_xml_localized(display_name_key, display_name_text)),
    ]
    if visible:
        parts.append('        <T n="icon">{0}</T>'.format(icon_xml))
        parts.append('    <T n="trait_description">{0}</T>'.format(_xml_localized(description_key or "0x00000000", description_text or "")))
        parts.append('<E n="trait_type">GAMEPLAY</E>')
    else:
        parts.append('    <E n="trait_type">HIDDEN</E>')
    parts.append("</I>")
    return "\n".join(parts) + "\n"


def _trait_simdata(
    name: str,
    *,
    display_name_key: str,
    description_key: str,
    trait_type: str,
    icon_key: str,
) -> str:
    return """<?xml version="1.0" encoding="utf-8"?>
<SimData version="0x00000101" u="0x00000000">
  <Instances>
    <I name="{name}" schema="Trait" type="Object">
{ages}
      <L name="bb_filter_styles"/>
      <L name="bb_filter_tags"/>
      <T name="cas_allowed_pack">0</T>
      <T name="cas_idle_asm_key">00000000-00000000-0000000000000000</T>
      <T name="cas_idle_asm_state">None</T>
      <T name="cas_selected_icon">00000000-00000000-0000000000000000</T>
      <T name="cas_trait_asm_param">None</T>
      <T name="cas_trait_hidden">0</T>
      <T name="cas_trait_vfx"></T>
      <L name="conflicting_traits"/>
      <T name="display_name">{display_name_key}</T>
      <T name="display_name_gender_neutral">{display_name_key}</T>
      <L name="display_overrides"/>
      <L name="genders"/>
      <T name="icon">{icon_key}</T>
      <L name="occults"/>
      <T name="refresh_sim_thumbnail">0</T>
      <L name="species"/>
      <L name="tags"/>
      <T name="thumbnail_type_asm_param"></T>
      <T name="trait_description">{description_key}</T>
      <T name="trait_origin_description">0x00000000</T>
      <T name="trait_type">{trait_type}</T>
      <V name="ui_category" variant="0x603EAA6C">
        <T type="Int64">0</T>
      </V>
    </I>
  </Instances>
  <Schemas>
    <Schema name="Trait" schema_hash="0x236FC540">
      <Columns>
        <Column name="ages" type="Vector" flags="0x00000000"/>
        <Column name="bb_filter_styles" type="Vector" flags="0x00000000"/>
        <Column name="bb_filter_tags" type="Vector" flags="0x00000000"/>
        <Column name="cas_allowed_pack" type="Int64" flags="0x00000000"/>
        <Column name="cas_idle_asm_key" type="ResourceKey" flags="0x00000000"/>
        <Column name="cas_idle_asm_state" type="String" flags="0x00000000"/>
        <Column name="cas_selected_icon" type="ResourceKey" flags="0x00000000"/>
        <Column name="cas_trait_asm_param" type="String" flags="0x00000000"/>
        <Column name="cas_trait_hidden" type="Boolean" flags="0x00000000"/>
        <Column name="cas_trait_vfx" type="String" flags="0x00000000"/>
        <Column name="conflicting_traits" type="Vector" flags="0x00000000"/>
        <Column name="display_name" type="LocalizationKey" flags="0x00000000"/>
        <Column name="display_name_gender_neutral" type="LocalizationKey" flags="0x00000000"/>
        <Column name="display_overrides" type="Vector" flags="0x00000000"/>
        <Column name="genders" type="Vector" flags="0x00000000"/>
        <Column name="icon" type="ResourceKey" flags="0x00000000"/>
        <Column name="occults" type="Vector" flags="0x00000000"/>
        <Column name="refresh_sim_thumbnail" type="Boolean" flags="0x00000000"/>
        <Column name="species" type="Vector" flags="0x00000000"/>
        <Column name="tags" type="Vector" flags="0x00000000"/>
        <Column name="thumbnail_type_asm_param" type="String" flags="0x00000000"/>
        <Column name="trait_description" type="LocalizationKey" flags="0x00000000"/>
        <Column name="trait_origin_description" type="LocalizationKey" flags="0x00000000"/>
        <Column name="trait_type" type="Int64" flags="0x00000000"/>
        <Column name="ui_category" type="Variant" flags="0x00000000"/>
      </Columns>
    </Schema>
  </Schemas>
</SimData>
""".format(
        name=name,
        ages=AGES_SIMDATA,
        display_name_key=_normalize_localization_key(display_name_key),
        description_key=_normalize_localization_key(description_key),
        trait_type=trait_type,
        icon_key=icon_key,
    )


def _buff_xml(name: str, *, buff_name_key: str, buff_name_text: str, buff_description_key: str, buff_description_text: str, mood_type: str, mood_weight: str, icon_xml: str) -> str:
    return """<?xml version="1.0" encoding="utf-8"?>
<I c="Buff" s="{instance_id}" i="buff" m="buffs.buff" n="{name}">
  <T n="audio_sting_on_add" p="InGame\\Audio\\Stings\\sting_buff_gain.propx">{audio_add}</T>
  <T n="audio_sting_on_remove" p="InGame\\Audio\\Stings\\sting_buff_loss.propx">{audio_remove}</T>
  <T n="buff_description">{buff_description}</T>
  <T n="icon">{icon}</T>
  <T n="buff_name">{buff_name}</T>
  <T n="mood_type">{mood_type}</T>
  <T n="mood_weight">{mood_weight}</T>
  <V n="_temporary_commodity_info" t="disabled" />
</I>
""".format(
        instance_id=_instance_id(name),
        name=name,
        audio_add=BUFF_AUDIO_ADD_XML,
        audio_remove=BUFF_AUDIO_REMOVE_XML,
        buff_description=_xml_localized(buff_description_key, buff_description_text),
        icon=icon_xml,
        buff_name=_xml_localized(buff_name_key, buff_name_text),
        mood_type=mood_type,
        mood_weight=mood_weight,
    )


def _buff_simdata(name: str, *, buff_name_key: str, buff_description_key: str, mood_type: str, mood_weight: str, icon_key: str) -> str:
    return """<?xml version="1.0" encoding="utf-8"?>
<SimData version="0x00000101" u="0x0000000A">
  <Instances>
    <I name="{name}" schema="Buff" type="Object">
      <T name="audio_sting_on_add">{audio_add}</T>
      <T name="audio_sting_on_remove">{audio_remove}</T>
      <T name="buff_description">{buff_description_key}</T>
      <T name="buff_name">{buff_name_key}</T>
      <T name="icon">{icon}</T>
      <T name="mood_type">{mood_type}</T>
      <T name="mood_weight">{mood_weight}</T>
      <T name="timeout_string">0x00000000</T>
      <T name="ui_sort_order">1</T>
    </I>
  </Instances>
  <Schemas>
    <Schema name="Buff" schema_hash="0x71722956">
      <Columns>
        <Column name="audio_sting_on_add" type="ResourceKey" flags="0x00000000"/>
        <Column name="audio_sting_on_remove" type="ResourceKey" flags="0x00000000"/>
        <Column name="buff_description" type="LocalizationKey" flags="0x00000000"/>
        <Column name="buff_name" type="LocalizationKey" flags="0x00000000"/>
        <Column name="icon" type="ResourceKey" flags="0x00000000"/>
        <Column name="mood_type" type="TableSetReference" flags="0x00000000"/>
        <Column name="mood_weight" type="Int32" flags="0x00000000"/>
        <Column name="timeout_string" type="LocalizationKey" flags="0x00000000"/>
        <Column name="ui_sort_order" type="Int32" flags="0x00000000"/>
      </Columns>
    </Schema>
  </Schemas>
</SimData>
""".format(
        name=name,
        audio_add=BUFF_AUDIO_ADD_SIMDATA,
        audio_remove=BUFF_AUDIO_REMOVE_SIMDATA,
        buff_description_key=_normalize_localization_key(buff_description_key),
        buff_name_key=_normalize_localization_key(buff_name_key),
        icon=icon_key,
        mood_type=mood_type,
        mood_weight=mood_weight,
    )


def _write_text(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _iter_expected_trait_names() -> Iterable[str]:
    for house_name, _, _ in ALL_HOUSES:
        for body in OUTER_BODIES:
            yield "PlumAntics_CosmicEngineHouses_{0}House_{1}Hidden".format(house_name, body)
    for house_name in VISIBLE_HOUSES:
        for body in OUTER_BODIES:
            yield "PlumAntics_CosmicEngineHouses_{0}House_{1}TransitMarker".format(house_name, body)


def _iter_expected_buff_names() -> Iterable[str]:
    for house_name in VISIBLE_HOUSES:
        for body in OUTER_BODIES:
            yield "PlumAntics_CosmicEngineHouses_{0}House_{1}TransitBuff".format(house_name, body)


def _cleanup_generated_assets() -> None:
    expected_traits = {name + ".xml" for name in _iter_expected_trait_names()}
    expected_traits.update({name + ".SimData.xml" for name in _iter_expected_trait_names()})
    expected_buffs = {name + ".xml" for name in _iter_expected_buff_names()}
    expected_buffs.update({name + ".SimData.xml" for name in _iter_expected_buff_names()})

    if TRAIT_DIR.exists():
        for path in TRAIT_DIR.glob("PlumAntics_CosmicEngineHouses_*"):
            if path.name not in expected_traits:
                path.unlink()
    if BUFF_DIR.exists():
        for path in BUFF_DIR.glob("PlumAntics_CosmicEngineHouses_*"):
            if path.name not in expected_buffs:
                path.unlink()


def main() -> None:
    payload, entries, key_to_value, value_to_key = _load_string_table()
    _cleanup_generated_assets()

    zero_key = _ensure_string_value(
        "",
        token="outer-planets/blank",
        entries=entries,
        key_to_value=key_to_value,
        value_to_key=value_to_key,
    )

    for house_name, _, _ in ALL_HOUSES:
        for body in OUTER_BODIES:
            name = "PlumAntics_CosmicEngineHouses_{0}House_{1}Hidden".format(house_name, body)
            display_value = name
            display_key = _ensure_string_value(
                display_value,
                token="outer-planets/trait-display/{0}".format(name),
                entries=entries,
                key_to_value=key_to_value,
                value_to_key=value_to_key,
            )
            _write_text(
                TRAIT_DIR / (name + ".xml"),
                _trait_xml(
                    name,
                    display_name_key=display_key,
                    display_name_text=display_value,
                    visible=False,
                ),
            )
            _write_text(
                TRAIT_DIR / (name + ".SimData.xml"),
                _trait_simdata(
                    name,
                    display_name_key=display_key,
                    description_key=zero_key,
                    trait_type="4",
                    icon_key="00000000-00000000-0000000000000000",
                ),
            )

    for house_name in VISIBLE_HOUSES:
        ordinal = _house_number_label(house_name)
        for body in OUTER_BODIES:
            visible_name, visible_desc = VISIBLE_COPY[(house_name, body)]
            marker_name = "PlumAntics_CosmicEngineHouses_{0}House_{1}TransitMarker".format(house_name, body)
            buff_name = "PlumAntics_CosmicEngineHouses_{0}House_{1}TransitBuff".format(house_name, body)

            marker_display_key = _ensure_string_value(
                visible_name,
                token="outer-planets/marker-display/{0}".format(marker_name),
                entries=entries,
                key_to_value=key_to_value,
                value_to_key=value_to_key,
            )
            marker_desc_key = _ensure_string_value(
                visible_desc,
                token="outer-planets/marker-desc/{0}".format(marker_name),
                entries=entries,
                key_to_value=key_to_value,
                value_to_key=value_to_key,
            )
            _write_text(
                TRAIT_DIR / (marker_name + ".xml"),
                _trait_xml(
                    marker_name,
                    display_name_key=marker_display_key,
                    display_name_text=visible_name,
                    description_key=marker_desc_key,
                    description_text=visible_desc,
                    visible=True,
                    icon_xml=VISIBLE_ICON_XML_BY_BODY[body],
                ),
            )
            _write_text(
                TRAIT_DIR / (marker_name + ".SimData.xml"),
                _trait_simdata(
                    marker_name,
                    display_name_key=marker_display_key,
                    description_key=marker_desc_key,
                    trait_type="1",
                    icon_key=VISIBLE_ICON_SIMDATA_BY_BODY[body],
                ),
            )

            buff_name_key = _ensure_string_value(
                visible_name,
                token="outer-planets/buff-name/{0}".format(buff_name),
                entries=entries,
                key_to_value=key_to_value,
                value_to_key=value_to_key,
            )
            buff_desc_key = _ensure_string_value(
                visible_desc,
                token="outer-planets/buff-desc/{0}".format(buff_name),
                entries=entries,
                key_to_value=key_to_value,
                value_to_key=value_to_key,
            )
            mood_type, mood_weight = BODY_MOODS[body]
            _write_text(
                BUFF_DIR / (buff_name + ".xml"),
                _buff_xml(
                    buff_name,
                    buff_name_key=buff_name_key,
                    buff_name_text=visible_name,
                    buff_description_key=buff_desc_key,
                    buff_description_text=visible_desc,
                    mood_type=mood_type,
                    mood_weight=mood_weight,
                    icon_xml=VISIBLE_ICON_XML_BY_BODY[body],
                ),
            )
            _write_text(
                BUFF_DIR / (buff_name + ".SimData.xml"),
                _buff_simdata(
                    buff_name,
                    buff_name_key=buff_name_key,
                    buff_description_key=buff_desc_key,
                    mood_type=mood_type,
                    mood_weight=mood_weight,
                    icon_key=VISIBLE_ICON_SIMDATA_BY_BODY[body],
                ),
            )

    payload["entries"] = entries
    with STRING_TABLE_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, indent=4) + "\n")

    print("Generated outer-planets house assets.")
    print("Traits: {0}".format(len(list(_iter_expected_trait_names()))))
    print("Buffs: {0}".format(len(list(_iter_expected_buff_names()))))


if __name__ == "__main__":
    main()
