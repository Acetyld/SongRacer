from __future__ import annotations

import json
from pathlib import Path
import subprocess
import time

from fastapi.testclient import TestClient

from songracer.api import app


def _make_video(path: Path, freq: int, duration: float = 2.0) -> None:
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
            f"sine=frequency={freq}:sample_rate=48000:duration={duration}",
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


def test_async_render_job_lifecycle(tmp_path: Path) -> None:
    v1 = tmp_path / "v1.mp4"
    v2 = tmp_path / "v2.mp4"
    _make_video(v1, freq=320)
    _make_video(v2, freq=500)

    out_path = tmp_path / "api_job.mp4"
    cfg_path = tmp_path / "api_job_config.json"
    cfg_path.write_text(
        json.dumps(
            {
                "render": {
                    "width": 180,
                    "height": 320,
                    "fps": 18,
                    "duration_seconds": 1.2,
                    "countdown_seconds": 0.3,
                },
                "background": {"mode": "solid", "solid_color": "#78C4FF"},
                "racers": [
                    {
                        "name": "A",
                        "video_path": str(v1),
                        "x": 70,
                        "y": 80,
                        "radius": 30,
                    },
                    {
                        "name": "B",
                        "video_path": str(v2),
                        "x": 120,
                        "y": 84,
                        "radius": 30,
                    },
                ],
                "obstacles": [{"type": "spinner", "x": 90, "y": 180, "length": 70, "thickness": 10}],
            }
        )
    )

    with TestClient(app) as client:
        validate_resp = client.post("/validate", json={"config_path": str(cfg_path)})
        assert validate_resp.status_code == 200

        create_resp = client.post(
            "/jobs",
            json={
                "config_path": str(cfg_path),
                "output_path": str(out_path),
                "preview_scale": 1.0,
            },
        )
        assert create_resp.status_code == 200
        job_id = create_resp.json()["job_id"]

        final_state = None
        for _ in range(200):
            poll = client.get(f"/jobs/{job_id}")
            assert poll.status_code == 200
            payload = poll.json()
            final_state = payload["state"]
            if final_state in {"completed", "failed"}:
                break
            time.sleep(0.05)

        assert final_state == "completed"
        assert out_path.exists()
        assert out_path.stat().st_size > 0

        list_resp = client.get("/jobs")
        assert list_resp.status_code == 200
        assert any(j["job_id"] == job_id for j in list_resp.json()["jobs"])

        artifact = client.get(f"/jobs/{job_id}/artifact")
        assert artifact.status_code == 200
