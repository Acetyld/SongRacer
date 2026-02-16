from __future__ import annotations

import os
from pathlib import Path
import tempfile
import uuid


def _can_write_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / f".write_probe_{uuid.uuid4().hex}"
        probe.write_text("ok")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def resolve_writable_dir(
    env_var: str,
    preferred_dir: Path,
    fallback_name: str,
    fallback_root: Path | None = None,
) -> Path:
    candidates: list[Path] = []
    env = os.environ.get(env_var, "").strip()
    if env:
        candidates.append(Path(env).expanduser().resolve())
    candidates.append(preferred_dir.expanduser().resolve())
    root = fallback_root or Path(tempfile.gettempdir())
    candidates.append((root / fallback_name).expanduser().resolve())

    seen: set[str] = set()
    for c in candidates:
        key = str(c)
        if key in seen:
            continue
        seen.add(key)
        if _can_write_dir(c):
            return c
    raise RuntimeError(f"No writable directory candidates for env var {env_var}")


def resolve_writable_file(
    env_var: str,
    preferred_file: Path,
    fallback_name: str,
    fallback_root: Path | None = None,
) -> Path:
    env = os.environ.get(env_var, "").strip()
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env).expanduser().resolve())
    candidates.append(preferred_file.expanduser().resolve())

    root = fallback_root or Path(tempfile.gettempdir())
    candidates.append((root / fallback_name).expanduser().resolve())

    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        parent = path.parent
        if not _can_write_dir(parent):
            continue
        try:
            if not path.exists():
                path.touch()
            probe = path.with_name(path.name + f".probe.{uuid.uuid4().hex}")
            probe.write_text("ok")
            probe.unlink(missing_ok=True)
            return path
        except OSError:
            continue
    raise RuntimeError(f"No writable file path candidates for env var {env_var}")
