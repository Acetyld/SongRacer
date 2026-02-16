from __future__ import annotations

from pathlib import Path

from songracer.storage import resolve_writable_dir, resolve_writable_file


def test_resolve_writable_dir_falls_back_when_env_unwritable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SONGRACER_STORAGE_DIR", "/proc/definitely_unwritable_songracer")
    preferred = Path("/proc/also_unwritable_songracer")
    out = resolve_writable_dir(
        env_var="SONGRACER_STORAGE_DIR",
        preferred_dir=preferred,
        fallback_name="songracer_test_storage",
        fallback_root=tmp_path,
    )
    assert out.exists()
    assert str(out).startswith(str(tmp_path))


def test_resolve_writable_file_falls_back_when_env_unwritable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SONGRACER_DB_PATH", "/proc/unwritable/songracer.db")
    preferred = Path("/proc/unwritable_preferred/songracer.db")
    out = resolve_writable_file(
        env_var="SONGRACER_DB_PATH",
        preferred_file=preferred,
        fallback_name="songracer_test_db/songracer.db",
        fallback_root=tmp_path,
    )
    assert out.exists()
    assert str(out).startswith(str(tmp_path))
