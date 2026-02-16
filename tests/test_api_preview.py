from __future__ import annotations

from fastapi.testclient import TestClient

from songracer.api import app


def test_preview_simulate_returns_timeline_payload() -> None:
    payload = {
        "seed": 11,
        "render": {
            "width": 320,
            "height": 560,
            "world_height": 1400,
            "fps": 30,
            "duration_seconds": 3.0,
            "countdown_seconds": 0.6,
            "camera_follow": True,
        },
        "racers": [
            {"name": "A", "x": 100, "y": 90, "radius": 24},
            {"name": "B", "x": 220, "y": 95, "radius": 24},
        ],
        "obstacles": [
            {"type": "rect", "x": 160, "y": 240, "width": 170, "height": 22, "angle_deg": 8},
            {"type": "ring_gap", "x": 160, "y": 520, "radius": 70, "thickness": 20},
        ],
        "sample_fps": 12,
        "max_frames": 90,
    }
    with TestClient(app) as client:
        resp = client.post("/preview/simulate", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["world"]["width"] == 320
        assert body["world"]["height"] == 560
        assert len(body["frame_indices"]) > 5
        assert len(body["positions"]) == len(body["frame_indices"])
        assert len(body["leaders"]) == len(body["frame_indices"])
        assert len(body["camera_y"]) == len(body["frame_indices"])
        assert len(body["states"]) == len(body["frame_indices"])
        assert len(body["obstacle_visuals"]) == len(body["frame_indices"])
        assert len(body["positions"][0]) == 2
        assert isinstance(body["winner_index"], int)
        assert isinstance(body["winner_frame"], int)
        assert isinstance(body["truncated"], bool)
        assert body["cache_hit"] is False
        assert body["sample_step_frames"] >= 1
        assert body["sample_interval_seconds"] > 0
        assert body["total_sample_frames"] >= len(body["frame_indices"])


def test_preview_simulate_rejects_invalid_obstacle_type() -> None:
    payload = {
        "render": {"width": 320, "height": 560, "world_height": 1400, "duration_seconds": 1.2},
        "racers": [{"name": "A", "x": 100, "y": 90, "radius": 24}],
        "obstacles": [{"type": "alien_gate", "x": 10, "y": 10}],
    }
    with TestClient(app) as client:
        resp = client.post("/preview/simulate", json=payload)
        assert resp.status_code == 400
        assert "Invalid obstacle type" in str(resp.json().get("detail"))


def test_preview_simulate_respects_max_frames_cap() -> None:
    payload = {
        "render": {
            "width": 320,
            "height": 560,
            "world_height": 1800,
            "fps": 30,
            "duration_seconds": 8.0,
            "countdown_seconds": 0.0,
        },
        "racers": [{"name": "A", "x": 140, "y": 90, "radius": 24}],
        "obstacles": [{"type": "rect", "x": 160, "y": 300, "width": 180, "height": 24}],
        "sample_fps": 24,
        "max_frames": 40,
    }
    with TestClient(app) as client:
        resp = client.post("/preview/simulate", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["frame_indices"]) <= 40
        assert len(body["positions"]) == len(body["frame_indices"])
        assert body["truncated"] is True
        assert body["total_sample_frames"] > len(body["frame_indices"])
        assert body["sample_step_frames"] >= 1


def test_preview_simulate_cache_hit_on_repeat_payload() -> None:
    payload = {
        "render": {"width": 300, "height": 540, "world_height": 1400, "duration_seconds": 2.0},
        "racers": [{"name": "A", "x": 140, "y": 90, "radius": 24}],
        "obstacles": [{"type": "rect", "x": 150, "y": 240, "width": 160, "height": 22}],
        "sample_fps": 10,
        "max_frames": 120,
    }
    with TestClient(app) as client:
        cleared_initial = client.post("/preview/cache/clear")
        assert cleared_initial.status_code == 200
        assert cleared_initial.json()["size"] == 0
        before = client.get("/preview/cache")
        assert before.status_code == 200
        assert before.json()["size"] == 0
        first = client.post("/preview/simulate", json=payload)
        second = client.post("/preview/simulate", json=payload)
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["cache_hit"] is False
        assert second.json()["cache_hit"] is True
        after = client.get("/preview/cache")
        assert after.status_code == 200
        assert after.json()["size"] >= 1
        assert after.json()["size"] >= before.json()["size"]
        clear = client.post("/preview/cache/clear")
        assert clear.status_code == 200
        assert clear.json()["cleared"] == after.json()["size"]
        assert clear.json()["size"] == 0
        assert clear.json()["max_size"] >= 1
        third = client.post("/preview/simulate", json=payload)
        assert third.status_code == 200
        assert third.json()["cache_hit"] is False
