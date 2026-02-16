from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import time

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
        templates = client.get("/templates/obstacles")
        assert templates.status_code == 200
        templates_body = templates.json()
        assert "templates" in templates_body
        assert set(templates_body["templates"].keys()) >= {"starter", "rings", "gates"}
        assert str(templates_body["version"]).startswith("sha256:")
        assert int(templates_body["template_count"]) >= 3
        capabilities = client.get("/builder/capabilities")
        assert capabilities.status_code == 200
        cap_body = capabilities.json()
        assert cap_body["preview"]["sample_fps"]["min"] == 4
        assert cap_body["generator"]["count"]["max"] >= 100
        assert cap_body["generator"]["safe_target_max_risk"]["max"] == 100
        assert cap_body["generator"]["safe_max_attempts"]["max"] >= 16
        bootstrap = client.get("/builder/bootstrap")
        assert bootstrap.status_code == 200
        bootstrap_body = bootstrap.json()
        assert "capabilities" in bootstrap_body
        assert "obstacle_types" in bootstrap_body
        assert "templates" in bootstrap_body
        assert str(bootstrap_body["bootstrap_version"]).startswith("sha256:")
        bootstrap_payload = {
            "capabilities": bootstrap_body["capabilities"],
            "obstacle_types": bootstrap_body["obstacle_types"],
            "templates": bootstrap_body["templates"],
        }
        bootstrap_payload_raw = json.dumps(
            bootstrap_payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        expected_bootstrap_version = (
            f"sha256:{hashlib.sha256(bootstrap_payload_raw).hexdigest()[:16]}"
        )
        assert bootstrap_body["bootstrap_version"] == expected_bootstrap_version
        assert bootstrap_body["capabilities"] == cap_body
        assert bootstrap_body["templates"]["version"] == templates_body["version"]
        assert bootstrap_body["templates"]["template_count"] == templates_body["template_count"]
        obstacle_types = client.get("/templates/obstacle-types")
        assert obstacle_types.status_code == 200
        types_body = obstacle_types.json()
        assert "types" in types_body
        assert any(t["type"] == "ring_gap" for t in types_body["types"])
        assert any(t["label"] == "Ring Gap" for t in types_body["types"])
        assert bootstrap_body["obstacle_types"] == types_body["types"]
        generated = client.post(
            "/templates/obstacles/generate",
            json={"count": 6, "start_y": 950, "spacing": 240, "width": 1080, "seed": 99},
        )
        assert generated.status_code == 200
        generated_body = generated.json()
        assert generated_body["count"] == 6
        assert len(generated_body["obstacles"]) == 6
        generated2 = client.post(
            "/templates/obstacles/generate",
            json={"count": 6, "start_y": 950, "spacing": 240, "width": 1080, "seed": 99},
        )
        assert generated2.status_code == 200
        assert generated2.json()["obstacles"] == generated_body["obstacles"]
        generated_safe = client.post(
            "/templates/obstacles/generate-safe",
            json={
                "count": 6,
                "start_y": 950,
                "spacing": 240,
                "width": 1080,
                "seed": 99,
                "target_max_risk": 100,
                "max_attempts": 5,
            },
        )
        assert generated_safe.status_code == 200
        generated_safe_body = generated_safe.json()
        assert generated_safe_body["count"] == 6
        assert generated_safe_body["attempts"] >= 1
        assert generated_safe_body["attempts"] <= 5
        assert "risk_score" in generated_safe_body
        assert generated_safe_body["target_max_risk"] == 100
        assert generated_safe_body["accepted"] is True
        assert generated_safe_body["warning_count"] == len(generated_safe_body["warnings"])
        assert isinstance(generated_safe_body["warnings"], list)
        assert generated_safe_body["accepted"] == (
            generated_safe_body["risk_score"] <= generated_safe_body["target_max_risk"]
        )

        generated_safe_strict = client.post(
            "/templates/obstacles/generate-safe",
            json={
                "count": 6,
                "start_y": 950,
                "spacing": 240,
                "width": 1080,
                "seed": 99,
                "target_max_risk": 0,
                "max_attempts": 3,
            },
        )
        assert generated_safe_strict.status_code == 200
        generated_safe_strict_body = generated_safe_strict.json()
        assert generated_safe_strict_body["count"] == 6
        assert 1 <= generated_safe_strict_body["attempts"] <= 3
        assert generated_safe_strict_body["target_max_risk"] == 0
        assert generated_safe_strict_body["warning_count"] == len(
            generated_safe_strict_body["warnings"]
        )
        assert generated_safe_strict_body["accepted"] == (
            generated_safe_strict_body["risk_score"] <= generated_safe_strict_body["target_max_risk"]
        )
        generated_safe_strict_repeat = client.post(
            "/templates/obstacles/generate-safe",
            json={
                "count": 6,
                "start_y": 950,
                "spacing": 240,
                "width": 1080,
                "seed": 99,
                "target_max_risk": 0,
                "max_attempts": 3,
            },
        )
        assert generated_safe_strict_repeat.status_code == 200
        assert generated_safe_strict_repeat.json() == generated_safe_strict_body

        inline_valid = client.post("/validate/config", json={"config": payload_config})
        assert inline_valid.status_code == 200
        assert inline_valid.json()["valid"] is True

        inline_invalid = client.post(
            "/validate/config",
            json={"config": {"render": {"width": 200, "height": 320}, "racers": [], "obstacles": []}},
        )
        assert inline_invalid.status_code == 400

        analysis = client.post(
            "/analyze/config",
            json={
                "config": {
                    "render": {"width": 180, "height": 320},
                    "obstacles": [
                        {"type": "rect", "x": 90, "y": 120, "width": 170},
                        {"type": "rect", "x": 90, "y": 140, "width": 160},
                    ],
                }
            },
        )
        assert analysis.status_code == 200
        analysis_body = analysis.json()
        assert analysis_body["warning_count"] > 0
        assert any(
            ("obstacle_index" in w) or ("obstacle_indices" in w)
            for w in analysis_body.get("warnings", [])
        )

        info = client.get("/system/info")
        assert info.status_code == 200
        assert "db_path" in info.json()

        created = client.post(
            "/projects",
            json={"name": "My Project", "config": payload_config},
        )
        assert created.status_code == 200
        project_id = created.json()["id"]

        listed_plain = client.get("/projects")
        assert listed_plain.status_code == 200
        plain_projects = listed_plain.json()["projects"]
        assert any(p["id"] == project_id for p in plain_projects)
        plain_project = next(p for p in plain_projects if p["id"] == project_id)
        assert "risk_score" not in plain_project
        assert "warning_count" not in plain_project

        listed = client.get("/projects?include_analysis=true")
        assert listed.status_code == 200
        listed_projects = listed.json()["projects"]
        assert any(p["id"] == project_id for p in listed_projects)
        listed_project = next(p for p in listed_projects if p["id"] == project_id)
        assert "risk_score" in listed_project
        assert "warning_count" in listed_project

        fetched = client.get(f"/projects/{project_id}")
        assert fetched.status_code == 200
        assert fetched.json()["name"] == "My Project"

        exported = client.get(f"/projects/{project_id}/export")
        assert exported.status_code == 200
        assert exported.json()["name"] == "My Project"
        assert exported.json()["config"]["render"]["fps"] == 20

        imported = client.post(
            "/projects/import",
            json={"name": "Imported Copy", "config": exported.json()["config"]},
        )
        assert imported.status_code == 200
        imported_id = imported.json()["id"]
        assert imported_id != project_id

        updated_config = json.loads(json.dumps(payload_config))
        updated_config["render"]["duration_seconds"] = 2.2
        updated = client.put(
            f"/projects/{project_id}",
            json={"name": "Updated Project", "config": updated_config},
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Updated Project"
        assert updated.json()["config"]["render"]["duration_seconds"] == 2.2

        project_analysis = client.get(f"/projects/{project_id}/analyze")
        assert project_analysis.status_code == 200
        project_analysis_body = project_analysis.json()
        assert project_analysis_body["id"] == project_id
        assert "risk_score" in project_analysis_body
        assert "warning_count" in project_analysis_body

        wave = client.post(
            "/waveform",
            json={"video_path": str(video), "sample_rate": 8000, "points": 120},
        )
        assert wave.status_code == 200
        body = wave.json()
        assert len(body["samples"]) == 120
        assert body["duration_seconds"] > 2.0

        render_resp = client.post(
            f"/projects/{project_id}/render",
            json={"preview_scale": 0.5},
        )
        assert render_resp.status_code == 200
        job_id = render_resp.json()["job_id"]
        final_state = "queued"
        for _ in range(250):
            poll = client.get(f"/jobs/{job_id}")
            assert poll.status_code == 200
            final_state = poll.json()["state"]
            if final_state in {"completed", "failed"}:
                break
            time.sleep(0.03)
        assert final_state == "completed"

        sync_resp = client.post(
            f"/projects/{project_id}/sync",
            json={"sample_rate": 12000, "max_shift_seconds": 2.0, "apply_duration_cap": True},
        )
        assert sync_resp.status_code == 200
        sync_body = sync_resp.json()
        assert "sync" in sync_body
        assert "trim_start_seconds" in sync_body["sync"]

        deleted = client.delete(f"/projects/{project_id}")
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] is True
        deleted_imported = client.delete(f"/projects/{imported_id}")
        assert deleted_imported.status_code == 200

        missing = client.get(f"/projects/{project_id}")
        assert missing.status_code == 404
