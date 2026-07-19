"""Config-first mapping loader for the Big 3 private runtime."""

import copy
import fnmatch
import os
from ..core.types import (
    ACTION_RUN_LOOT,
    ACTION_RUN_WEIGHTED_LOOT_TABLE,
    ACTION_SET_COMMODITY,
)
from .yaml_lite import load_yaml_or_json_file, load_yaml_or_json_package_resource


class MappingRepository(object):
    """Loads and resolves signal/action mappings from external files."""

    def __init__(self, base_engine):
        self._engine = base_engine
        self._root = None
        self._package_name = self._resolve_package_name()
        self._config = self._engine.config.get("v2", {}) if isinstance(self._engine.config, dict) else {}

        self._signals_to_buffs_doc = {}
        self._signals_to_loots_doc = {}
        self._flare_schedule_doc = {}
        self._priorities_doc = {}
        self._debug_doc = {}

        self._signal_buff_rules = {}
        self._signal_loot_rules = {}
        self._default_loot_rule = {"on_enter": [], "on_exit": []}
        self._flare_rules = []
        self._priority_rules = []
        self._debug_flags = {}

        # Packaged gameplay runtime always loads mapping data from packaged
        # resources. Avoid filesystem testbed probing here so the ts4script
        # does not perform unnecessary disk access during normal play.
        self._root = None
        self.refresh()

    def _resolve_package_name(self):
        module_name = getattr(self.__class__, "__module__", "") or ""
        if "." in module_name:
            return module_name.split(".", 1)[0]
        if module_name:
            return module_name
        return "plumantics_big3_runtime"

    def _mapping_files_config(self):
        default_files = {
            "signals_to_buffs": "rules/v2/signals_to_buffs.yaml",
            "signals_to_loots": "rules/v2/signals_to_loots.yaml",
            "flare_schedule": "rules/v2/flare_schedule.yaml",
            "priorities": "rules/v2/priorities.yaml",
            "debug_flags": "rules/v2/debug_flags.yaml",
        }
        raw = self._config.get("mapping_files", {})
        if not isinstance(raw, dict):
            return default_files
        merged = dict(default_files)
        for key, value in raw.items():
            text = str(value).strip() if value is not None else ""
            if text:
                merged[str(key)] = text
        return merged

    def _load_doc(self, relative_path):
        normalized = str(relative_path).replace("\\", "/").lstrip("/")
        if self._engine.testbed_root is not None:
            path = os.path.join(self._engine.testbed_root, normalized.replace("/", os.sep))
            return load_yaml_or_json_file(path)
        resource_path = "data/{0}".format(normalized)
        return load_yaml_or_json_package_resource(self._package_name, resource_path)

    def refresh(self):
        files = self._mapping_files_config()
        self._signals_to_buffs_doc = self._load_doc(files["signals_to_buffs"])
        self._signals_to_loots_doc = self._load_doc(files["signals_to_loots"])
        self._flare_schedule_doc = self._load_doc(files["flare_schedule"])
        self._priorities_doc = self._load_doc(files["priorities"])
        self._debug_doc = self._load_doc(files["debug_flags"])

        self._signal_buff_rules = self._expand_signal_rules(self._signals_to_buffs_doc, is_loot=False)
        self._signal_loot_rules = self._expand_signal_rules(self._signals_to_loots_doc, is_loot=True)
        self._default_loot_rule = self._normalize_loot_rule(
            self._signals_to_loots_doc.get("defaults", {}) if isinstance(self._signals_to_loots_doc, dict) else {}
        )
        self._flare_rules = self._normalize_flare_rules(self._flare_schedule_doc)
        self._priority_rules = self._normalize_priority_rules(self._priorities_doc)
        self._debug_flags = self._normalize_debug_flags(self._debug_doc)

    def _expand_signal_rules(self, doc, is_loot=False):
        if not isinstance(doc, dict):
            return {}

        expanded = {}
        templates = doc.get("templates", [])
        if isinstance(templates, list):
            for template in templates:
                if not isinstance(template, dict):
                    continue
                key_template = str(template.get("key_template", "")).strip()
                if not key_template:
                    continue
                if "{SIGN}" in key_template:
                    for sign in self._engine.zodiac_order():
                        sign_token = str(sign).strip().upper()
                        key = key_template.replace("{SIGN}", sign_token)
                        rule = self._materialize_template_rule(
                            template, sign_token=sign_token, is_loot=is_loot
                        )
                        if rule is not None:
                            expanded[key] = rule
                else:
                    rule = self._materialize_template_rule(
                        template, sign_token=None, is_loot=is_loot
                    )
                    if rule is not None:
                        expanded[key_template] = rule

        explicit = doc.get("signals", {})
        if isinstance(explicit, dict):
            for key, rule in explicit.items():
                signal_key = str(key).strip()
                if not signal_key:
                    continue
                if is_loot:
                    expanded[signal_key] = self._normalize_loot_rule(rule)
                else:
                    expanded[signal_key] = self._normalize_buff_rule(rule)
        return expanded

    def _materialize_template_rule(self, template, sign_token=None, is_loot=False):
        rule = copy.deepcopy(template)
        rule.pop("key_template", None)
        if is_loot:
            return self._normalize_loot_rule(rule)

        source_map_name = rule.pop("buff_source_map", None)
        if source_map_name is not None and sign_token is not None:
            source_map = self._engine.ids.get(str(source_map_name), {})
            if not isinstance(source_map, dict):
                source_map = {}
            if sign_token in source_map:
                rule["buff_id"] = source_map.get(sign_token)
        return self._normalize_buff_rule(rule)

    def _normalize_buff_rule(self, rule):
        if not isinstance(rule, dict):
            return {}
        normalized = copy.deepcopy(rule)

        buff_id = normalized.get("buff_id")
        if buff_id is not None:
            resolved = self._resolve_tuning_id(buff_id, kind="buff")
            normalized["buff_id"] = resolved

        duration = normalized.get("duration_sim_minutes", 0)
        try:
            normalized["duration_sim_minutes"] = int(duration)
        except Exception:
            normalized["duration_sim_minutes"] = 0

        intensity = normalized.get("intensity", 1.0)
        try:
            normalized["intensity"] = float(intensity)
        except Exception:
            normalized["intensity"] = 1.0

        scope = normalized.get("scope", "sim")
        normalized["scope"] = str(scope).strip().lower() or "sim"

        effect_group = normalized.get("effect_group", "default")
        normalized["effect_group"] = str(effect_group).strip().lower() or "default"

        stacking = normalized.get("stacking_policy", "REPLACE")
        normalized["stacking_policy"] = str(stacking).strip().upper() or "REPLACE"
        return normalized

    def _normalize_loot_rule(self, rule):
        if not isinstance(rule, dict):
            return {"on_enter": [], "on_exit": []}
        normalized = copy.deepcopy(rule)
        normalized["on_enter"] = self._normalize_action_list(normalized.get("on_enter", []))
        normalized["on_exit"] = self._normalize_action_list(normalized.get("on_exit", []))
        return normalized

    def _normalize_action_list(self, raw_actions):
        if not isinstance(raw_actions, list):
            return []
        actions = []
        for raw in raw_actions:
            action = self._normalize_action(raw)
            if action is not None:
                actions.append(action)
        return actions

    def _normalize_action(self, raw):
        if not isinstance(raw, dict):
            return None

        action_type = str(raw.get("type", raw.get("action", ""))).strip().upper()
        if action_type not in (
            ACTION_RUN_LOOT,
            ACTION_RUN_WEIGHTED_LOOT_TABLE,
            ACTION_SET_COMMODITY,
        ):
            return None

        normalized = {"type": action_type}

        if action_type == ACTION_RUN_LOOT:
            tuning_id = self._resolve_tuning_id(raw.get("loot_id"), kind="loot")
            if tuning_id is None:
                return None
            normalized["tuning_id"] = tuning_id
            return normalized

        if action_type == ACTION_RUN_WEIGHTED_LOOT_TABLE:
            tuning_id = self._resolve_tuning_id(raw.get("table_id"), kind="loot")
            if tuning_id is None:
                return None
            normalized["tuning_id"] = tuning_id
            weights = raw.get("weights", {})
            if isinstance(weights, dict):
                clean = {}
                for key, value in weights.items():
                    try:
                        clean[str(key)] = float(value)
                    except Exception:
                        continue
                normalized["weights"] = clean
            else:
                normalized["weights"] = {}
            return normalized

        if action_type == ACTION_SET_COMMODITY:
            tuning_id = self._resolve_tuning_id(raw.get("commodity_id"), kind="commodity")
            if tuning_id is None:
                return None
            normalized["tuning_id"] = tuning_id
            value = raw.get("value", raw.get("delta"))
            try:
                normalized["value"] = float(value)
            except Exception:
                normalized["value"] = 0.0
            return normalized
        return None

    def _resolve_tuning_id(self, raw_value, kind):
        if raw_value is None:
            return None
        try:
            return int(raw_value)
        except Exception:
            pass

        token = str(raw_value).strip()
        if not token:
            return None
        try:
            return int(token)
        except Exception:
            pass

        ids = self._engine.ids if isinstance(self._engine.ids, dict) else {}
        lookup_groups = []
        if kind == "buff":
            lookup_groups = [
                "buffs",
                "moon_base_buffs",
                "sun_base_buffs",
                "rising_base_buffs",
                "moon_phase_buffs",
            ]
        elif kind == "commodity":
            lookup_groups = ["stats", "commodities"]
        else:
            lookup_groups = ["loot", "loots", "actions"]

        for group in lookup_groups:
            values = ids.get(group, {})
            if not isinstance(values, dict):
                continue
            if token in values:
                try:
                    return int(values[token])
                except Exception:
                    continue
        return None

    def _normalize_flare_rules(self, doc):
        if not isinstance(doc, dict):
            return []
        raw_flares = doc.get("flares", [])
        rules = []
        if isinstance(raw_flares, dict):
            for flare_id, payload in raw_flares.items():
                if not isinstance(payload, dict):
                    continue
                merged = dict(payload)
                merged["id"] = str(flare_id)
                rules.append(self._normalize_one_flare_rule(merged))
        elif isinstance(raw_flares, list):
            for payload in raw_flares:
                if isinstance(payload, dict):
                    rules.append(self._normalize_one_flare_rule(payload))
        return [rule for rule in rules if rule is not None]

    def _normalize_one_flare_rule(self, raw):
        flare_id = str(raw.get("id", "")).strip()
        signal_template = str(raw.get("signal_template", "")).strip()
        if not flare_id or not signal_template:
            return None

        try:
            start_hour = int(raw.get("start_hour", 8)) % 24
        except Exception:
            start_hour = 8
        try:
            duration = int(raw.get("duration_sim_minutes", 120))
        except Exception:
            duration = 120
        duration = max(1, duration)
        try:
            cooldown = int(raw.get("cooldown_sim_minutes", 1440))
        except Exception:
            cooldown = 1440

        try:
            intensity = float(raw.get("intensity", 1.0))
        except Exception:
            intensity = 1.0

        return {
            "id": flare_id,
            "enabled": bool(raw.get("enabled", True)),
            "signal_template": signal_template,
            "source": str(raw.get("source", "SUN_SIGN")).strip().upper(),
            "start_hour": start_hour,
            "duration_sim_minutes": duration,
            "cooldown_sim_minutes": max(0, cooldown),
            "scope": str(raw.get("scope", "sim")).strip().lower() or "sim",
            "effect_group": str(raw.get("effect_group", "flare")).strip().lower() or "flare",
            "intensity": intensity,
        }

    def _normalize_priority_rules(self, doc):
        if not isinstance(doc, dict):
            return []
        raw_rules = doc.get("rules", [])
        if not isinstance(raw_rules, list):
            return []
        normalized = []
        for raw in raw_rules:
            if not isinstance(raw, dict):
                continue
            higher_prefix = str(raw.get("higher_prefix", "")).strip()
            lower_prefix = str(raw.get("lower_prefix", "")).strip()
            if not higher_prefix or not lower_prefix:
                continue
            normalized.append(
                {
                    "id": str(raw.get("id", "priority_rule")).strip(),
                    "enabled": bool(raw.get("enabled", True)),
                    "higher_prefix": higher_prefix,
                    "lower_prefix": lower_prefix,
                    "same_effect_group_only": bool(raw.get("same_effect_group_only", False)),
                }
            )
        return normalized

    def _normalize_debug_flags(self, doc):
        if not isinstance(doc, dict):
            return {}
        flags = dict(doc)
        normalized = {}
        for key, value in flags.items():
            normalized[str(key)] = bool(value)
        return normalized

    def _find_rule(self, signal_key, rules):
        if signal_key in rules:
            return copy.deepcopy(rules[signal_key])
        pattern_matches = []
        for pattern, rule in rules.items():
            if "*" not in pattern:
                continue
            if fnmatch.fnmatch(signal_key, pattern):
                pattern_matches.append((len(pattern), pattern, rule))
        if not pattern_matches:
            return None
        pattern_matches.sort(key=lambda value: (value[0], value[1]), reverse=True)
        return copy.deepcopy(pattern_matches[0][2])

    def signal_buff_rule(self, signal_key):
        signal = str(signal_key).strip()
        if not signal:
            return None
        return self._find_rule(signal, self._signal_buff_rules)

    def signal_loot_rule(self, signal_key):
        signal = str(signal_key).strip()
        if not signal:
            return None
        rule = self._find_rule(signal, self._signal_loot_rules)
        if rule is None:
            return copy.deepcopy(self._default_loot_rule)
        return rule

    def action_defs_for_signal(self, signal_key, edge):
        rule = self.signal_loot_rule(signal_key)
        if not isinstance(rule, dict):
            return []
        edge_key = "on_enter" if str(edge).strip().lower() == "enter" else "on_exit"
        actions = rule.get(edge_key, [])
        if not isinstance(actions, list):
            return []
        return copy.deepcopy(actions)

    def flare_rules(self):
        return copy.deepcopy(self._flare_rules)

    def priority_rules(self):
        return copy.deepcopy(self._priority_rules)

    def debug_flags(self):
        return dict(self._debug_flags)
