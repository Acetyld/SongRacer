from __future__ import annotations

import json
from pathlib import Path
import subprocess

from fastapi.testclient import TestClient

from songracer.api import app


def _make_video(path: Path, duration: float = 2.0) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size=180x320:rate=24:duration={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=48000:duration={duration}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
    )


def test_projects_crud_and_waveform_endpoint(tmp_path: Path) -> None:
    video = tmp_path / "w.mp4"
    _make_video(video, duration=2.4)

    payload_config = {
        "render": {"width": 180, "height": 320, "fps": 20, "duration_seconds": 1.5},
        "racers": [
            {"name": "A", "video_path": str(video), "x": 90, "y": 90, "radius": 30}
        ],
        "obstacles": [],
    }

    with TestClient(app) as client:
        created = client.post(
            "/projects",
            json={"name": "My Project", "config": payload_config},
        )
        assert created.status_code == 200
        project_id = created.json()["id"]

        listed = client.get("/projects")
        assert listed.status_code == 200
        assert any(p["id"] == project_id for p in listed.json()["projects"])

        fetched = client.get(f"/projects/{project_id}")
        assert fetched.status_code == 200
        assert fetched.json()["name"] == "My Project"

        updated_config = json.loads(json.dumps(payload_config))
        updated_config["render"]["duration_seconds"] = 2.2
        updated = client.put(
            f"/projects/{project_id}",
            json={"name": "Updated Project", "config": updated_config},
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Updated Project"
        assert updated.json()["config"]["render"]["duration_seconds"] == 2.2

        wave = client.post(
            "/waveform",
            json={"video_path": str(video), "sample_rate": 8000, "points": 120},
        )
        assert wave.status_code == 200
        body = wave.json()
        assert len(body["samples"]) == 120
        assert body["duration_seconds"] > 2.0

        deleted = client.delete(f"/projects/{project_id}")
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] is True

        missing = client.get(f"/projects/{project_id}")
        assert missing.status_code == 404
