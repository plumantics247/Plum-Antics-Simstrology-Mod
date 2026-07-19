#!/usr/bin/env python3
"""Build a .ts4script archive from the local `python/` folder.

Default output:
- out/<name>.source.ts4script   (contains .py files)

Optional:
- out/<name>.ts4script          (contains .pyc files compiled with a provided
  Python executable, ideally Python 3.7 for TS4 compatibility)
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import py_compile
import shutil
import subprocess
import sys
import tempfile
from typing import Iterable, List, Sequence, Tuple
import zipfile


def _iter_py_files(root: Path) -> List[Path]:
    files: List[Path] = []
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        files.append(path)
    files.sort()
    return files


def _iter_resource_files(root: Path) -> List[Path]:
    files: List[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts:
            continue
        if path.suffix.lower() == ".py":
            continue
        files.append(path)
    files.sort()
    return files


def _zip_files(zip_path: Path, files: Iterable[Tuple[Path, str]]) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for src_path, arcname in files:
            zf.write(src_path, arcname)


def _build_source_archive(source_root: Path, output_path: Path) -> int:
    py_files = _iter_py_files(source_root)
    resource_files = _iter_resource_files(source_root)
    rels = [(path, path.relative_to(source_root).as_posix()) for path in py_files]
    rels.extend((path, path.relative_to(source_root).as_posix()) for path in resource_files)
    _zip_files(output_path, rels)
    return len(rels)


def _python_version(py_exe: str) -> Tuple[int, int]:
    code = "import sys;print(f'{sys.version_info[0]}.{sys.version_info[1]}')"
    proc = subprocess.run(
        [py_exe, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )
    major_minor = proc.stdout.strip().split(".")
    return int(major_minor[0]), int(major_minor[1])


def _compile_pyc_tree(
    source_root: Path,
    compiled_root: Path,
    py_exe: str,
) -> List[Path]:
    py_files = _iter_py_files(source_root)
    if not py_files:
        return []

    script_lines = [
        "import py_compile",
        "from pathlib import Path",
        f"src_root = Path(r'''{source_root}''')",
        f"dst_root = Path(r'''{compiled_root}''')",
        "paths = [",
    ]
    for py in py_files:
        script_lines.append(f"    Path(r'''{py}'''),")
    script_lines.extend(
        [
            "]",
            "for src in paths:",
            "    rel = src.relative_to(src_root)",
            "    dst = (dst_root / rel).with_suffix('.pyc')",
            "    dst.parent.mkdir(parents=True, exist_ok=True)",
            "    py_compile.compile(str(src), cfile=str(dst), dfile=str(rel.as_posix()), doraise=True)",
        ]
    )
    code = "\n".join(script_lines)
    subprocess.run([py_exe, "-c", code], check=True)
    return sorted(compiled_root.rglob("*.pyc"))


def _build_pyc_archive(
    source_root: Path,
    output_path: Path,
    py_exe: str,
) -> int:
    with tempfile.TemporaryDirectory(prefix="simstrology_pyc_build_") as tmp:
        compiled_root = Path(tmp) / "compiled"
        compiled_files = _compile_pyc_tree(source_root, compiled_root, py_exe)
        resource_files = _iter_resource_files(source_root)
        rels = [(path, path.relative_to(compiled_root).as_posix()) for path in compiled_files]
        rels.extend((path, path.relative_to(source_root).as_posix()) for path in resource_files)
        _zip_files(output_path, rels)
        return len(rels)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build simstrology Engine .ts4script archives.")
    parser.add_argument(
        "--source-dir",
        default="python",
        help="Source directory containing Python files (default: python).",
    )
    parser.add_argument(
        "--output-dir",
        default="out",
        help="Output directory for ts4script archives (default: out).",
    )
    parser.add_argument(
        "--name",
        default="PlumAntics_Simstrology",
        help="Base filename for generated archives.",
    )
    parser.add_argument(
        "--pyc-python",
        default="",
        help="Path to Python executable used to compile .pyc archive (recommended: Python 3.7).",
    )
    parser.add_argument(
        "--allow-incompatible-pyc",
        action="store_true",
        help="Allow .pyc build even when provided Python is not 3.7.",
    )
    parser.add_argument(
        "--clean-output",
        action="store_true",
        help="Delete existing generated archives before writing new ones.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = _parse_args(argv)
    root = Path.cwd()
    source_root = (root / args.source_dir).resolve()
    output_dir = (root / args.output_dir).resolve()
    source_archive = output_dir / f"{args.name}.source.ts4script"
    pyc_archive = output_dir / f"{args.name}.ts4script"

    if not source_root.is_dir():
        print(f"ERROR: source dir not found: {source_root}")
        return 1

    if args.clean_output:
        for path in (source_archive, pyc_archive):
            if path.exists():
                path.unlink()

    source_count = _build_source_archive(source_root, source_archive)
    print(f"Built source archive: {source_archive} ({source_count} files)")

    pyc_python = args.pyc_python.strip()
    if pyc_python:
        pyc_python = os.path.expandvars(pyc_python)
        pyc_python = os.path.expanduser(pyc_python)
        if not Path(pyc_python).exists():
            print(f"ERROR: --pyc-python path not found: {pyc_python}")
            return 1

        try:
            major, minor = _python_version(pyc_python)
        except Exception as exc:
            print(f"ERROR: failed to check Python version for {pyc_python}: {exc}")
            return 1

        if (major, minor) != (3, 7) and not args.allow_incompatible_pyc:
            print(
                "ERROR: .pyc build requires Python 3.7 by default "
                f"(found {major}.{minor}). Use --allow-incompatible-pyc to override."
            )
            return 1

        try:
            pyc_count = _build_pyc_archive(source_root, pyc_archive, pyc_python)
        except subprocess.CalledProcessError as exc:
            print(f"ERROR: .pyc compile failed with exit code {exc.returncode}")
            return 1

        print(f"Built pyc archive:    {pyc_archive} ({pyc_count} files)")
    else:
        print(
            "Skipped .pyc archive. Provide --pyc-python <path-to-python37.exe> "
            "to build runtime .ts4script with compiled bytecode."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
