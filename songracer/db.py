from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _db_path() -> Path:
    env = os.environ.get("SONGRACER_DB_PATH", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return PROJECT_ROOT / "songracer.db"


@dataclass(slots=True)
class ProjectRecord:
    id: int
    name: str
    config: dict[str, Any]
    created_at: str
    updated_at: str


def _conn() -> sqlite3.Connection:
    db_path = _db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        db_path.touch()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                config_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_project(name: str, config: dict[str, Any]) -> ProjectRecord:
    ts = _utc_now()
    payload = json.dumps(config, separators=(",", ":"))
    with _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO projects (name, config_json, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (name, payload, ts, ts),
        )
        project_id = int(cur.lastrowid)
        conn.commit()
    return get_project(project_id)


def list_projects() -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, name, created_at, updated_at FROM projects ORDER BY updated_at DESC"
        ).fetchall()
    return [
        {
            "id": int(r["id"]),
            "name": str(r["name"]),
            "created_at": str(r["created_at"]),
            "updated_at": str(r["updated_at"]),
        }
        for r in rows
    ]


def get_project(project_id: int) -> ProjectRecord:
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, name, config_json, created_at, updated_at FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    if row is None:
        raise KeyError(project_id)
    return ProjectRecord(
        id=int(row["id"]),
        name=str(row["name"]),
        config=json.loads(str(row["config_json"])),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def update_project(project_id: int, name: str, config: dict[str, Any]) -> ProjectRecord:
    ts = _utc_now()
    payload = json.dumps(config, separators=(",", ":"))
    with _conn() as conn:
        cur = conn.execute(
            """
            UPDATE projects
            SET name = ?, config_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (name, payload, ts, project_id),
        )
        if cur.rowcount == 0:
            raise KeyError(project_id)
        conn.commit()
    return get_project(project_id)


def delete_project(project_id: int) -> None:
    with _conn() as conn:
        cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        if cur.rowcount == 0:
            raise KeyError(project_id)
        conn.commit()
