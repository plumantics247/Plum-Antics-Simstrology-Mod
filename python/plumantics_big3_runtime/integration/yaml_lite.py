"""Minimal YAML/JSON loader used by universe_engine.v2.

The parser intentionally supports a small YAML subset:
- dictionaries (`key: value`)
- nested dictionaries via indentation
- lists (`- value`, `- key: value`)
- scalar values (bool/null/number/string)

This keeps packaging lightweight for Sims 4 runtime where PyYAML may not exist.
"""

import json
import pkgutil

try:
    import importlib.resources as importlib_resources
except Exception:  # pragma: no cover - TS4 runtime fallback
    importlib_resources = None


def _strip_inline_comment(text):
    in_single = False
    in_double = False
    result = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "'" and not in_double:
            in_single = not in_single
            result.append(char)
            index += 1
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            result.append(char)
            index += 1
            continue
        if char == "#" and (not in_single) and (not in_double):
            break
        result.append(char)
        index += 1
    return "".join(result).rstrip()


def _tokenize_yaml(text):
    lines = []
    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        cleaned = _strip_inline_comment(raw_line)
        if not cleaned.strip():
            continue
        indent = len(cleaned) - len(cleaned.lstrip(" "))
        content = cleaned.strip()
        lines.append((indent, content))
    return lines


def _parse_scalar(token):
    text = str(token).strip()
    if text == "":
        return ""

    lowered = text.lower()
    if lowered in ("true", "yes", "on"):
        return True
    if lowered in ("false", "no", "off"):
        return False
    if lowered in ("null", "none", "~"):
        return None

    if (text.startswith('"') and text.endswith('"')) or (
        text.startswith("'") and text.endswith("'")
    ):
        return text[1:-1]

    if text.startswith("{") or text.startswith("["):
        try:
            return json.loads(text)
        except Exception:
            pass

    try:
        if "." in text:
            return float(text)
        return int(text)
    except Exception:
        return text


def _parse_block(lines, index):
    if index >= len(lines):
        return None, index
    indent, content = lines[index]
    if content.startswith("- "):
        return _parse_list(lines, index, indent)
    return _parse_mapping(lines, index, indent)


def _parse_mapping(lines, index, base_indent):
    result = {}
    while index < len(lines):
        indent, content = lines[index]
        if indent < base_indent:
            break
        if indent > base_indent:
            # Nested blocks are handled by the parent key, so stop here.
            break
        if content.startswith("- "):
            break

        key, sep, remainder = content.partition(":")
        if sep != ":":
            raise ValueError("Invalid YAML mapping line: {0}".format(content))

        key = key.strip()
        remainder = remainder.strip()
        index += 1

        if remainder:
            result[key] = _parse_scalar(remainder)
            continue

        if index < len(lines) and lines[index][0] > indent:
            value, index = _parse_block(lines, index)
            result[key] = value
        else:
            result[key] = None
    return result, index


def _parse_list(lines, index, base_indent):
    result = []
    while index < len(lines):
        indent, content = lines[index]
        if indent < base_indent:
            break
        if indent != base_indent or not content.startswith("- "):
            break

        item_text = content[2:].strip()
        index += 1

        if not item_text:
            if index < len(lines) and lines[index][0] > indent:
                value, index = _parse_block(lines, index)
                result.append(value)
            else:
                result.append(None)
            continue

        if ":" in item_text:
            key, sep, remainder = item_text.partition(":")
            if sep == ":":
                mapping_item = {key.strip(): _parse_scalar(remainder.strip()) if remainder.strip() else None}

                if (not remainder.strip()) and index < len(lines) and lines[index][0] > indent:
                    child_value, index = _parse_block(lines, index)
                    mapping_item[key.strip()] = child_value

                while index < len(lines) and lines[index][0] > indent:
                    extra_indent = lines[index][0]
                    extra_map, index = _parse_mapping(lines, index, extra_indent)
                    if isinstance(extra_map, dict):
                        mapping_item.update(extra_map)
                result.append(mapping_item)
                continue

        result.append(_parse_scalar(item_text))
    return result, index


def parse_yaml_lite(text):
    lines = _tokenize_yaml(text)
    if not lines:
        return {}
    value, index = _parse_block(lines, 0)
    if index != len(lines):
        raise ValueError("Unexpected trailing YAML content at line index {0}".format(index))
    return value


def load_yaml_or_json_text(text):
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(text)
    return parse_yaml_lite(text)


def load_yaml_or_json_file(path):
    with open(path, "r", encoding="utf-8") as handle:
        return load_yaml_or_json_text(handle.read())


def _normalize_package_resource_path(package_name, resource_path):
    package_name = str(package_name or "").strip()
    resource_path = str(resource_path or "").replace("\\", "/").strip()
    if not package_name:
        raise RuntimeError("Package name is required for packaged resource loading.")
    if not resource_path:
        raise RuntimeError("Resource path is required for packaged resource loading.")

    while resource_path.startswith("./"):
        resource_path = resource_path[2:]

    package_prefix = package_name.replace(".", "/") + "/"
    absolute_package_marker = ".ts4script/" + package_prefix
    if absolute_package_marker in resource_path:
        resource_path = resource_path.split(absolute_package_marker, 1)[1]
    elif package_prefix in resource_path and (":/" in resource_path or resource_path.startswith("/")):
        resource_path = resource_path.split(package_prefix, 1)[1]

    resource_path = resource_path.lstrip("/")
    return package_name, resource_path


def load_yaml_or_json_package_resource(package_name, resource_path):
    package_name, resource_path = _normalize_package_resource_path(package_name, resource_path)
    try:
        data = pkgutil.get_data(package_name, resource_path)
    except Exception:
        data = None
    if data is None and importlib_resources is not None:
        try:
            data = importlib_resources.files(package_name).joinpath(*resource_path.split("/")).read_bytes()
        except Exception:
            data = None
    if data is None:
        raise RuntimeError(
            "Could not load resource '{0}' from package '{1}'".format(
                resource_path, package_name
            )
        )
    return load_yaml_or_json_text(data.decode("utf-8"))
