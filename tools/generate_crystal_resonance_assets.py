from __future__ import annotations

import json
import pathlib
import sys
import zlib
from typing import Dict


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


from cosmic_engine.crystal_resonance import (  # noqa: E402
    ATTUNEMENT_BUFF_ID_BY_CRYSTAL_KEY,
    PASSIVE_BUFF_ID_BY_CRYSTAL_KEY,
    PRIMARY_CRYSTAL_BY_SIGN,
)


BUFF_DIR = ROOT / "src" / "CrystalResonance" / "Buff"
STRING_TABLE_PATH = ROOT / "src" / "String" / "SimstrologicalMod_English.stbl.json"
VISIBLE_ICON_XML = "2f7d0004:00000000:b681e4a5e381494d"
VISIBLE_ICON_SIMDATA = "00B2D882-00000000-B681E4A5E381494D"
AUDIO_ADD_XML = "39b2aa4a:00000000:8af8b916cf64c646"
AUDIO_REMOVE_XML = "39b2aa4a:00000000:3bf33216a25546ea"
AUDIO_ADD_SIMDATA = "FD04E3BE-00000000-8AF8B916CF64C646"
AUDIO_REMOVE_SIMDATA = "FD04E3BE-00000000-3BF33216A25546EA"
AUDIO_ADD_SIMDATA_HIDDEN = "FD04E3BE-001407EC-8AF8B916CF64C646"
AUDIO_REMOVE_SIMDATA_HIDDEN = "FD04E3BE-001407EC-3BF33216A25546EA"
HAPPY_MOOD_ID = 14634
XML_RESOURCE_TYPE = "6017E896"
XML_RESOURCE_GROUP = "00000000"
SIMDATA_RESOURCE_TYPE = "545AC67A"
SIMDATA_RESOURCE_GROUP = "0017E8F6"

DISPLAY_LABEL_BY_CRYSTAL = {
    "Diamond": "Diamond",
    "Emerald": "Emerald",
    "Citrine": "Citrine",
    "Ruby": "Ruby",
    "Fire Opal": "Fire Opal",
    "Sapphire": "Sapphire",
    "Rose": "Rose Quartz",
    "Turquoise": "Turquoise",
    "Orange Topaz": "Orange Topaz",
    "Jet": "Jet",
    "Amethyst": "Amethyst",
    "Quartz": "Quartz",
}


def _normalize_localization_key(key: str) -> str:
    text = str(key)
    if text.lower().startswith("0x"):
        return "0x" + text[2:].upper()
    return text.upper()


def _stable_string_key(token: str, used_keys: Dict[str, str]) -> str:
    seed = int(zlib.crc32(token.encode("utf-8")) & 0xFFFFFFFF)
    for offset in range(0, 10000):
        candidate = "0x{0:08X}".format((seed + offset) & 0xFFFFFFFF)
        current = used_keys.get(candidate)
        if current is None or current == token:
            return candidate
    raise RuntimeError("Unable to allocate unique STBL key for {0}".format(token))


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


def _resource_comment(resource_type: str, resource_group: str, instance_id: int) -> str:
    return "<!-- S4TK Type: {0}, Group: {1}, Instance: {2:016X} -->".format(
        resource_type,
        resource_group,
        int(instance_id),
    )


def _simdata_xml_visible(name: str, *, instance_id: int, name_key: str, description_key: str, mood_weight: int) -> str:
    return """<?xml version="1.0" encoding="utf-8"?>
{comment}
<SimData version="0x00000101" u="0x0000000A">
  <Instances>
    <I name="{name}" schema="Buff" type="Object">
      <T name="audio_sting_on_add">{audio_add}</T>
      <T name="audio_sting_on_remove">{audio_remove}</T>
      <T name="buff_description">{description_key}</T>
      <T name="buff_name">{name_key}</T>
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
        comment=_resource_comment(SIMDATA_RESOURCE_TYPE, SIMDATA_RESOURCE_GROUP, instance_id),
        name=name,
        audio_add=AUDIO_ADD_SIMDATA,
        audio_remove=AUDIO_REMOVE_SIMDATA,
        description_key=description_key,
        name_key=name_key,
        icon=VISIBLE_ICON_SIMDATA,
        mood_type=HAPPY_MOOD_ID,
        mood_weight=int(mood_weight),
    )


def _simdata_xml_hidden(name: str, *, instance_id: int, name_key: str, description_key: str, mood_type: int, mood_weight: int) -> str:
    return """<?xml version="1.0" encoding="utf-8"?>
{comment}
<SimData version="0x00000101" u="0x00000000">
  <Instances>
    <I name="{name}" schema="Buff" type="Object">
      <T name="audio_sting_on_add">{audio_add}</T>
      <T name="audio_sting_on_remove">{audio_remove}</T>
      <T name="buff_description">{description_key}</T>
      <T name="buff_name">{name_key}</T>
      <T name="cas_vfx"></T>
      <T name="icon">{icon}</T>
      <T name="mood_type">{mood_type}</T>
      <T name="mood_weight">{mood_weight}</T>
      <T name="plumbob_vfx"></T>
      <T name="timeout_string">0x00000000</T>
      <T name="timeout_string_no_next_buff">0x00000000</T>
      <T name="ui_sort_order">1</T>
    </I>
  </Instances>
  <Schemas>
    <Schema name="Buff" schema_hash="0xDCE584D3">
      <Columns>
        <Column name="audio_sting_on_add" type="ResourceKey" flags="0x00000000"/>
        <Column name="audio_sting_on_remove" type="ResourceKey" flags="0x00000000"/>
        <Column name="buff_description" type="LocalizationKey" flags="0x00000000"/>
        <Column name="buff_name" type="LocalizationKey" flags="0x00000000"/>
        <Column name="cas_vfx" type="String" flags="0x00000000"/>
        <Column name="icon" type="ResourceKey" flags="0x00000000"/>
        <Column name="mood_type" type="TableSetReference" flags="0x00000000"/>
        <Column name="mood_weight" type="Int32" flags="0x00000000"/>
        <Column name="plumbob_vfx" type="String" flags="0x00000000"/>
        <Column name="timeout_string" type="LocalizationKey" flags="0x00000000"/>
        <Column name="timeout_string_no_next_buff" type="LocalizationKey" flags="0x00000000"/>
        <Column name="ui_sort_order" type="Int32" flags="0x00000000"/>
      </Columns>
    </Schema>
  </Schemas>
</SimData>
""".format(
        comment=_resource_comment(SIMDATA_RESOURCE_TYPE, SIMDATA_RESOURCE_GROUP, instance_id),
        name=name,
        audio_add=AUDIO_ADD_SIMDATA_HIDDEN,
        audio_remove=AUDIO_REMOVE_SIMDATA_HIDDEN,
        description_key=description_key,
        name_key=name_key,
        icon=VISIBLE_ICON_SIMDATA,
        mood_type=int(mood_type),
        mood_weight=int(mood_weight),
    )


def _buff_xml(
    name: str,
    *,
    instance_id: int,
    name_key: str,
    name_text: str,
    description_key: str,
    description_text: str,
    mood_weight: int,
    visible: bool,
) -> str:
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        _resource_comment(XML_RESOURCE_TYPE, XML_RESOURCE_GROUP, instance_id),
        '<I c="Buff" i="buff" m="buffs.buff" n="{0}" s="{1}">'.format(name, int(instance_id)),
        '  <T n="audio_sting_on_add">{0}</T>'.format(AUDIO_ADD_XML),
        '  <T n="audio_sting_on_remove">{0}</T>'.format(AUDIO_REMOVE_XML),
        '  <T n="buff_description">{0}<!--{1}--></T>'.format(description_key, description_text),
        '  <T n="icon">{0}</T>'.format(VISIBLE_ICON_XML),
        '  <T n="buff_name">{0}<!--{1}--></T>'.format(name_key, name_text),
        '  <T n="mood_type">{0}</T>'.format(HAPPY_MOOD_ID),
        '  <T n="mood_weight">{0}</T>'.format(int(mood_weight)),
        '  <T n="show_timeout">False</T>',
        '  <T n="visible">{0}</T>'.format("True" if visible else "False"),
        '  <V n="_temporary_commodity_info" t="disabled" />',
        '</I>',
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    BUFF_DIR.mkdir(parents=True, exist_ok=True)

    payload, entries, key_to_value, value_to_key = _load_string_table()
    sign_by_crystal = {crystal: sign for sign, crystal in PRIMARY_CRYSTAL_BY_SIGN.items()}

    for crystal_key, passive_id in PASSIVE_BUFF_ID_BY_CRYSTAL_KEY.items():
        label = DISPLAY_LABEL_BY_CRYSTAL[crystal_key]
        sign_name = sign_by_crystal[crystal_key]
        stem = crystal_key.replace(" ", "")

        passive_name = "{0} Resonance".format(label)
        passive_description = (
            "{0} resonates with the {1} signature in this Sim's Big 3, adding a quiet supportive charge."
        ).format(label, sign_name)
        passive_name_key = _ensure_string_value(
            passive_name,
            token="crystal_resonance_{0}_passive_name".format(stem.lower()),
            entries=entries,
            key_to_value=key_to_value,
            value_to_key=value_to_key,
        )
        passive_description_key = _ensure_string_value(
            passive_description,
            token="crystal_resonance_{0}_passive_desc".format(stem.lower()),
            entries=entries,
            key_to_value=key_to_value,
            value_to_key=value_to_key,
        )

        passive_tuning_name = "PlumAntics_CosmicEngineCrystalResonance_{0}_Passive".format(stem)
        (BUFF_DIR / (passive_tuning_name + ".xml")).write_text(
            _buff_xml(
                passive_tuning_name,
                instance_id=passive_id,
                name_key=passive_name_key,
                name_text=passive_name,
                description_key=passive_description_key,
                description_text=passive_description,
                mood_weight=1,
                visible=False,
            ),
            encoding="utf-8",
        )
        (BUFF_DIR / (passive_tuning_name + ".SimData.xml")).write_text(
            _simdata_xml_hidden(
                passive_tuning_name,
                instance_id=passive_id,
                name_key=passive_name_key,
                description_key=passive_description_key,
                mood_type=HAPPY_MOOD_ID,
                mood_weight=1,
            ),
            encoding="utf-8",
        )

    for crystal_key, attunement_id in ATTUNEMENT_BUFF_ID_BY_CRYSTAL_KEY.items():
        label = DISPLAY_LABEL_BY_CRYSTAL[crystal_key]
        sign_name = sign_by_crystal[crystal_key]
        stem = crystal_key.replace(" ", "")

        attunement_name = "{0} Attunement".format(label)
        attunement_description = (
            "A recently gifted {0} is fully attuned to the {1} signature in this Sim's Big 3, making the resonance feel stronger."
        ).format(label, sign_name)
        attunement_name_key = _ensure_string_value(
            attunement_name,
            token="crystal_resonance_{0}_attunement_name".format(stem.lower()),
            entries=entries,
            key_to_value=key_to_value,
            value_to_key=value_to_key,
        )
        attunement_description_key = _ensure_string_value(
            attunement_description,
            token="crystal_resonance_{0}_attunement_desc".format(stem.lower()),
            entries=entries,
            key_to_value=key_to_value,
            value_to_key=value_to_key,
        )

        attunement_tuning_name = "PlumAntics_CosmicEngineCrystalResonance_{0}_Attunement".format(stem)
        (BUFF_DIR / (attunement_tuning_name + ".xml")).write_text(
            _buff_xml(
                attunement_tuning_name,
                instance_id=attunement_id,
                name_key=attunement_name_key,
                name_text=attunement_name,
                description_key=attunement_description_key,
                description_text=attunement_description,
                mood_weight=2,
                visible=True,
            ),
            encoding="utf-8",
        )
        (BUFF_DIR / (attunement_tuning_name + ".SimData.xml")).write_text(
            _simdata_xml_visible(
                attunement_tuning_name,
                instance_id=attunement_id,
                name_key=attunement_name_key,
                description_key=attunement_description_key,
                mood_weight=2,
            ),
            encoding="utf-8",
        )

    payload["entries"] = entries
    STRING_TABLE_PATH.write_text(json.dumps(payload, indent=4) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
