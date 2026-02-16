from __future__ import annotations

import math

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
        expected_step = max(1, int(math.ceil(payload["render"]["fps"] / payload["sample_fps"])))
        assert body["sample_step_frames"] == expected_step
        assert abs(body["sample_fps"] - (payload["render"]["fps"] / expected_step)) < 1e-9
        assert abs(body["sample_interval_seconds"] - (expected_step / payload["render"]["fps"])) < 1e-9
        assert body["sample_fps"] <= payload["sample_fps"]
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


def test_preview_simulate_defaults_align_with_builder_capabilities() -> None:
    payload = {
        "render": {
            "width": 320,
            "height": 560,
            "world_height": 1600,
            "fps": 30,
            "duration_seconds": 6.0,
            "countdown_seconds": 0.0,
        },
        "racers": [{"name": "A", "x": 140, "y": 90, "radius": 24}],
        "obstacles": [{"type": "rect", "x": 160, "y": 300, "width": 180, "height": 24}],
    }
    with TestClient(app) as client:
        capabilities = client.get("/builder/capabilities")
        assert capabilities.status_code == 200
        caps = capabilities.json()
        default_sample_fps = int(caps["preview"]["sample_fps"]["default"])
        default_max_frames = int(caps["preview"]["max_frames"]["default"])

        resp = client.post("/preview/simulate", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        expected_step = max(1, int(math.ceil(payload["render"]["fps"] / default_sample_fps)))
        assert body["sample_step_frames"] == expected_step
        assert abs(body["sample_fps"] - (payload["render"]["fps"] / expected_step)) < 1e-9
        assert body["sample_fps"] <= default_sample_fps
        assert len(body["frame_indices"]) <= default_max_frames


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
        assert after.json()["max_size"] == before.json()["max_size"]
        clear = client.post("/preview/cache/clear")
        assert clear.status_code == 200
        assert clear.json()["cleared"] == after.json()["size"]
        assert clear.json()["size"] == 0
        assert clear.json()["max_size"] == before.json()["max_size"]
        clear_again = client.post("/preview/cache/clear")
        assert clear_again.status_code == 200
        assert clear_again.json()["cleared"] == 0
        assert clear_again.json()["size"] == 0
        assert clear_again.json()["max_size"] == clear.json()["max_size"]
        third = client.post("/preview/simulate", json=payload)
        assert third.status_code == 200
        assert third.json()["cache_hit"] is False
        payload_variant = dict(payload)
        payload_variant["sample_fps"] = 11
        variant = client.post("/preview/simulate", json=payload_variant)
        assert variant.status_code == 200
        assert variant.json()["cache_hit"] is False
        cache_after_variant = client.get("/preview/cache")
        assert cache_after_variant.status_code == 200
        assert cache_after_variant.json()["size"] >= 2


def test_preview_cache_key_is_order_insensitive_for_json_payload() -> None:
    payload = {
        "seed": 21,
        "render": {
            "width": 300,
            "height": 540,
            "world_height": 1400,
            "duration_seconds": 2.0,
        },
        "racers": [{"name": "A", "x": 140, "y": 90, "radius": 24}],
        "obstacles": [{"type": "rect", "x": 150, "y": 240, "width": 160, "height": 22}],
        "sample_fps": 10,
        "max_frames": 120,
    }
    reordered_payload = {
        "max_frames": 120,
        "sample_fps": 10,
        "obstacles": [{"height": 22, "width": 160, "y": 240, "x": 150, "type": "rect"}],
        "racers": [{"radius": 24, "y": 90, "x": 140, "name": "A"}],
        "render": {
            "duration_seconds": 2.0,
            "world_height": 1400,
            "height": 540,
            "width": 300,
        },
        "seed": 21,
    }
    with TestClient(app) as client:
        cleared = client.post("/preview/cache/clear")
        assert cleared.status_code == 200
        first = client.post("/preview/simulate", json=payload)
        second = client.post("/preview/simulate", json=reordered_payload)
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["cache_hit"] is False
        assert second.json()["cache_hit"] is True
