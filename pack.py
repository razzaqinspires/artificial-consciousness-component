"""Utility script to package AC-Kernel NADI v2.1.0 into a clean distribution ZIP."""

from __future__ import annotations

import zipfile
from pathlib import Path

EXCLUDE_DIRS = {"__pycache__", ".git", ".pytest_cache", "nadi_state", "dist"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".zip"}


def build_zip(output_name: str = "AC-Kernel-NADI-v2.1.0.zip") -> Path:
    root = Path(__file__).resolve().parent
    out_path = root / output_name
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in sorted(root.rglob("*")):
            if item.is_dir():
                continue
            if any(part in EXCLUDE_DIRS for part in item.relative_to(root).parts):
                continue
            if item.suffix in EXCLUDE_SUFFIXES or item == out_path:
                continue
            arcname = f"AC-Kernel-NADI-v2.1.0/{item.relative_to(root).as_posix()}"
            zf.write(item, arcname=arcname)
    return out_path


if __name__ == "__main__":
    archive = build_zip()
    print(f"Packaged cleanly: {archive}")
