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
        assert body["returned_sample_frames"] == len(body["frame_indices"])
        assert body["requested_sample_fps"] == payload["sample_fps"]
        assert body["requested_max_frames"] == payload["max_frames"]
        assert body["returned_sample_frames"] <= body["requested_max_frames"]
        assert len(body["positions"]) == len(body["frame_indices"])
        assert len(body["leaders"]) == len(body["frame_indices"])
        assert len(body["camera_y"]) == len(body["frame_indices"])
        assert len(body["states"]) == len(body["frame_indices"])
        assert len(body["obstacle_visuals"]) == len(body["frame_indices"])
        assert len(body["positions"][0]) == 2
        assert body["frame_indices"][0] == 0
        assert body["frame_indices"] == sorted(body["frame_indices"])
        assert len(body["frame_indices"]) == len(set(body["frame_indices"]))
        assert isinstance(body["winner_index"], int)
        assert isinstance(body["winner_frame"], int)
        assert (body["winner_index"] >= 0) == (body["winner_frame"] >= 0)
        assert body["truncated"] is False
        assert body["cache_hit"] is False
        expected_step = max(1, int(math.ceil(payload["render"]["fps"] / payload["sample_fps"])))
        assert body["sample_step_frames"] == expected_step
        assert all(
            (b - a) == expected_step
            for a, b in zip(body["frame_indices"], body["frame_indices"][1:])
        )
        assert abs(body["sample_fps"] - (payload["render"]["fps"] / expected_step)) < 1e-9
        assert abs(body["sample_interval_seconds"] - (expected_step / payload["render"]["fps"])) < 1e-9
        assert body["sample_fps"] <= payload["sample_fps"]
        assert body["total_sample_frames"] >= len(body["frame_indices"])
        assert body["total_sample_frames"] == len(body["frame_indices"])


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


def test_preview_simulate_rejects_out_of_range_sampling_limits() -> None:
    payload = {
        "render": {"width": 320, "height": 560, "world_height": 1400, "duration_seconds": 1.2},
        "racers": [{"name": "A", "x": 100, "y": 90, "radius": 24}],
        "obstacles": [],
        "sample_fps": 2,
        "max_frames": 20,
    }
    with TestClient(app) as client:
        resp = client.post("/preview/simulate", json=payload)
        assert resp.status_code == 422
        detail = str(resp.json().get("detail"))
        assert "sample_fps" in detail
        assert "max_frames" in detail


def test_preview_simulate_sampling_bounds_follow_capabilities_contract() -> None:
    base = {
        "render": {"width": 320, "height": 560, "world_height": 1400, "duration_seconds": 1.2},
        "racers": [{"name": "A", "x": 100, "y": 90, "radius": 24}],
        "obstacles": [],
    }
    with TestClient(app) as client:
        caps_resp = client.get("/builder/capabilities")
        assert caps_resp.status_code == 200
        caps = caps_resp.json()["preview"]
        min_fps = int(caps["sample_fps"]["min"])
        max_fps = int(caps["sample_fps"]["max"])
        min_frames = int(caps["max_frames"]["min"])
        max_frames = int(caps["max_frames"]["max"])

        valid_low = {
            **base,
            "sample_fps": min_fps,
            "max_frames": max_frames,
        }
        valid_high = {
            **base,
            "sample_fps": max_fps,
            "max_frames": min_frames,
        }
        assert client.post("/preview/simulate", json=valid_low).status_code == 200
        assert client.post("/preview/simulate", json=valid_high).status_code == 200

        invalid_low_fps = {**base, "sample_fps": min_fps - 1, "max_frames": min_frames}
        invalid_high_fps = {**base, "sample_fps": max_fps + 1, "max_frames": min_frames}
        invalid_low_frames = {**base, "sample_fps": min_fps, "max_frames": min_frames - 1}
        invalid_high_frames = {**base, "sample_fps": min_fps, "max_frames": max_frames + 1}
        assert client.post("/preview/simulate", json=invalid_low_fps).status_code == 422
        assert client.post("/preview/simulate", json=invalid_high_fps).status_code == 422
        assert client.post("/preview/simulate", json=invalid_low_frames).status_code == 422
        assert client.post("/preview/simulate", json=invalid_high_frames).status_code == 422


def test_preview_simulate_reports_no_winner_with_negative_fields() -> None:
    payload = {
        "seed": 22,
        "render": {
            "width": 320,
            "height": 560,
            "world_height": 12000,
            "fps": 30,
            "duration_seconds": 1.0,
            "countdown_seconds": 0.0,
            "goal_margin": 120,
            "camera_follow": True,
            "auto_end_on_winner": True,
        },
        "racers": [{"name": "A", "x": 140, "y": 90, "radius": 24}],
        "obstacles": [],
        "sample_fps": 10,
        "max_frames": 120,
    }
    with TestClient(app) as client:
        resp = client.post("/preview/simulate", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["winner_index"] == -1
        assert body["winner_frame"] == -1


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
        assert body["requested_sample_fps"] == default_sample_fps
        assert body["requested_max_frames"] == default_max_frames
        expected_step = max(1, int(math.ceil(payload["render"]["fps"] / default_sample_fps)))
        assert body["sample_step_frames"] == expected_step
        assert abs(body["sample_fps"] - (payload["render"]["fps"] / expected_step)) < 1e-9
        assert body["sample_fps"] <= default_sample_fps
        assert len(body["frame_indices"]) <= default_max_frames
        assert body["returned_sample_frames"] == len(body["frame_indices"])
        assert body["returned_sample_frames"] <= body["requested_max_frames"]
        assert body["truncated"] is False
        assert body["total_sample_frames"] == len(body["frame_indices"])


def test_preview_simulate_defaulted_request_cache_hit_consistency() -> None:
    payload = {
        "render": {
            "width": 320,
            "height": 560,
            "world_height": 1600,
            "fps": 30,
            "duration_seconds": 2.0,
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

        cleared = client.post("/preview/cache/clear")
        assert cleared.status_code == 200
        first = client.post("/preview/simulate", json=payload)
        second = client.post("/preview/simulate", json=payload)
        assert first.status_code == 200
        assert second.status_code == 200
        first_body = first.json()
        second_body = second.json()
        assert first_body["cache_hit"] is False
        assert second_body["cache_hit"] is True
        assert first_body["requested_sample_fps"] == default_sample_fps
        assert second_body["requested_sample_fps"] == default_sample_fps
        assert first_body["requested_max_frames"] == default_max_frames
        assert second_body["requested_max_frames"] == default_max_frames
        normalized_first = {k: v for k, v in first_body.items() if k != "cache_hit"}
        normalized_second = {k: v for k, v in second_body.items() if k != "cache_hit"}
        assert normalized_first == normalized_second


def test_preview_cache_key_treats_omitted_sampling_fields_as_defaults() -> None:
    payload_omitted = {
        "render": {
            "width": 320,
            "height": 560,
            "world_height": 1600,
            "fps": 30,
            "duration_seconds": 2.0,
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
        payload_explicit_defaults = {
            **payload_omitted,
            "sample_fps": default_sample_fps,
            "max_frames": default_max_frames,
        }

        cleared = client.post("/preview/cache/clear")
        assert cleared.status_code == 200
        first = client.post("/preview/simulate", json=payload_omitted)
        second = client.post("/preview/simulate", json=payload_explicit_defaults)
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["cache_hit"] is False
        assert second.json()["cache_hit"] is True


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
        assert body["requested_max_frames"] == payload["max_frames"]
        assert len(body["frame_indices"]) <= 40
        assert body["returned_sample_frames"] == len(body["frame_indices"])
        assert body["returned_sample_frames"] == body["requested_max_frames"]
        assert len(body["frame_indices"]) == 40
        assert len(body["positions"]) == len(body["frame_indices"])
        assert body["truncated"] is True
        assert body["total_sample_frames"] > len(body["frame_indices"])
        assert body["sample_step_frames"] == 2
        assert body["frame_indices"][-1] == 78


def test_preview_simulate_effective_fps_never_exceeds_request() -> None:
    payload = {
        "render": {
            "width": 320,
            "height": 560,
            "world_height": 1800,
            "fps": 30,
            "duration_seconds": 3.0,
            "countdown_seconds": 0.0,
        },
        "racers": [{"name": "A", "x": 140, "y": 90, "radius": 24}],
        "obstacles": [{"type": "rect", "x": 160, "y": 300, "width": 180, "height": 24}],
        "sample_fps": 14,
        "max_frames": 300,
    }
    with TestClient(app) as client:
        resp = client.post("/preview/simulate", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["sample_step_frames"] == 3
        assert abs(body["sample_fps"] - 10.0) < 1e-9
        assert body["sample_fps"] <= payload["sample_fps"]


def test_preview_simulate_effective_fps_capped_by_render_fps() -> None:
    payload = {
        "render": {
            "width": 320,
            "height": 560,
            "world_height": 1800,
            "fps": 24,
            "duration_seconds": 3.0,
            "countdown_seconds": 0.0,
        },
        "racers": [{"name": "A", "x": 140, "y": 90, "radius": 24}],
        "obstacles": [{"type": "rect", "x": 160, "y": 300, "width": 180, "height": 24}],
        "sample_fps": 60,
        "max_frames": 300,
    }
    with TestClient(app) as client:
        resp = client.post("/preview/simulate", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["requested_sample_fps"] == payload["sample_fps"]
        assert body["requested_max_frames"] == payload["max_frames"]
        assert body["sample_step_frames"] == 1
        assert abs(body["sample_fps"] - payload["render"]["fps"]) < 1e-9
        assert body["sample_fps"] <= body["requested_sample_fps"]


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
        first_body = first.json()
        second_body = second.json()
        assert first_body["cache_hit"] is False
        assert second_body["cache_hit"] is True
        assert first_body["requested_sample_fps"] == payload["sample_fps"]
        assert second_body["requested_sample_fps"] == payload["sample_fps"]
        assert first_body["requested_max_frames"] == payload["max_frames"]
        assert second_body["requested_max_frames"] == payload["max_frames"]
        assert first_body["returned_sample_frames"] == len(first_body["frame_indices"])
        assert second_body["returned_sample_frames"] == len(second_body["frame_indices"])
        normalized_first = {k: v for k, v in first_body.items() if k != "cache_hit"}
        normalized_second = {k: v for k, v in second_body.items() if k != "cache_hit"}
        assert normalized_first == normalized_second
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
        first_body = first.json()
        second_body = second.json()
        assert first_body["cache_hit"] is False
        assert second_body["cache_hit"] is True
        assert first_body["requested_sample_fps"] == payload["sample_fps"]
        assert second_body["requested_sample_fps"] == payload["sample_fps"]
        assert first_body["requested_max_frames"] == payload["max_frames"]
        assert second_body["requested_max_frames"] == payload["max_frames"]
        assert first_body["returned_sample_frames"] == len(first_body["frame_indices"])
        assert second_body["returned_sample_frames"] == len(second_body["frame_indices"])
        normalized_first = {k: v for k, v in first_body.items() if k != "cache_hit"}
        normalized_second = {k: v for k, v in second_body.items() if k != "cache_hit"}
        assert normalized_first == normalized_second
