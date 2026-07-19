"""Zip-safe config helpers for the Big 3 runtime package."""

import json
import pkgutil

try:
    import importlib.resources as importlib_resources
except Exception:  # pragma: no cover - TS4 runtime fallback
    importlib_resources = None

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


def load_json_from_package(package_name, resource_path):
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
    return json.loads(data.decode("utf-8"))
