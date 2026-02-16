from __future__ import annotations

import hashlib
import json
import random
from typing import Any


def obstacle_templates() -> dict[str, list[dict[str, Any]]]:
    return {
        "starter": [
            {
                "type": "rect",
                "x": 280,
                "y": 980,
                "width": 300,
                "height": 30,
                "angle_deg": -22,
                "fill_color": "#182037",
            },
            {
                "type": "moving_rect",
                "x": 760,
                "y": 1120,
                "width": 290,
                "height": 30,
                "angle_deg": 18,
                "amplitude": 120,
                "frequency_hz": 0.24,
                "axis": "x",
                "fill_color": "#182037",
            },
            {
                "type": "ring_gap",
                "x": 540,
                "y": 1380,
                "radius": 160,
                "thickness": 32,
                "rotation_speed_deg": 90,
                "gap_center_deg": 270,
                "gap_size_deg": 64,
                "fill_color": "#182037",
            },
            {
                "type": "spinner",
                "x": 540,
                "y": 1680,
                "length": 340,
                "thickness": 24,
                "spin_speed_deg": 160,
                "fill_color": "#182037",
            },
            {
                "type": "one_way_gate",
                "x": 540,
                "y": 1940,
                "width": 620,
                "height": 24,
                "one_way": "down",
                "fill_color": "#182037",
            },
        ],
        "rings": [
            {
                "type": "ring_gap",
                "x": 350,
                "y": 980,
                "radius": 126,
                "thickness": 32,
                "gap_center_deg": 250,
                "gap_size_deg": 62,
                "fill_color": "#182037",
            },
            {
                "type": "ring_gap",
                "x": 730,
                "y": 1210,
                "radius": 130,
                "thickness": 32,
                "gap_center_deg": 200,
                "gap_size_deg": 58,
                "fill_color": "#182037",
            },
            {
                "type": "ring_gap",
                "x": 420,
                "y": 1460,
                "radius": 142,
                "thickness": 32,
                "gap_center_deg": 280,
                "gap_size_deg": 60,
                "fill_color": "#182037",
            },
            {
                "type": "ring_gap",
                "x": 700,
                "y": 1730,
                "radius": 132,
                "thickness": 32,
                "gap_center_deg": 245,
                "gap_size_deg": 58,
                "fill_color": "#182037",
            },
            {
                "type": "spinner",
                "x": 540,
                "y": 2060,
                "length": 320,
                "thickness": 24,
                "spin_speed_deg": 150,
                "fill_color": "#182037",
            },
        ],
        "gates": [
            {
                "type": "rect",
                "x": 260,
                "y": 940,
                "width": 320,
                "height": 30,
                "angle_deg": -18,
                "fill_color": "#182037",
            },
            {
                "type": "one_way_gate",
                "x": 540,
                "y": 1120,
                "width": 640,
                "height": 24,
                "one_way": "down",
                "fill_color": "#182037",
            },
            {
                "type": "one_way_gate",
                "x": 540,
                "y": 1270,
                "width": 640,
                "height": 24,
                "one_way": "up",
                "fill_color": "#182037",
            },
            {
                "type": "moving_rect",
                "x": 740,
                "y": 1510,
                "width": 320,
                "height": 30,
                "angle_deg": 14,
                "axis": "x",
                "amplitude": 100,
                "frequency_hz": 0.24,
                "fill_color": "#182037",
            },
            {
                "type": "pendulum",
                "x": 540,
                "y": 1820,
                "pivot_x": 540,
                "pivot_y": 1820,
                "length": 290,
                "angle_deg": 15,
                "amplitude": 56,
                "frequency_hz": 0.45,
                "thickness": 18,
                "fill_color": "#182037",
            },
        ],
    }


def obstacle_templates_payload() -> dict[str, Any]:
    templates = obstacle_templates()
    digest = hashlib.sha256(
        json.dumps(templates, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "templates": templates,
        "version": f"sha256:{digest[:16]}",
        "template_count": len(templates),
    }


def generate_obstacle_stream(
    *,
    count: int,
    start_y: float,
    spacing: float,
    width: float,
    seed: int,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    x_min = max(120.0, width * 0.18)
    x_max = max(x_min + 20.0, width - x_min)
    out: list[dict[str, Any]] = []
    for idx in range(max(0, count)):
        y = start_y + idx * spacing
        kind = rng.choice(
            [
                "rect",
                "moving_rect",
                "ring_gap",
                "spinner",
                "one_way_gate",
            ]
        )
        x = rng.uniform(x_min, x_max)
        if kind == "rect":
            out.append(
                {
                    "type": "rect",
                    "x": round(x, 1),
                    "y": round(y, 1),
                    "width": round(rng.uniform(width * 0.2, width * 0.34), 1),
                    "height": 28,
                    "angle_deg": round(rng.uniform(-30, 30), 1),
                    "fill_color": "#182037",
                }
            )
        elif kind == "moving_rect":
            out.append(
                {
                    "type": "moving_rect",
                    "x": round(x, 1),
                    "y": round(y, 1),
                    "width": round(rng.uniform(width * 0.22, width * 0.36), 1),
                    "height": 28,
                    "angle_deg": round(rng.uniform(-22, 22), 1),
                    "amplitude": round(rng.uniform(70, 140), 1),
                    "frequency_hz": round(rng.uniform(0.15, 0.35), 3),
                    "axis": "x",
                    "fill_color": "#182037",
                }
            )
        elif kind == "ring_gap":
            out.append(
                {
                    "type": "ring_gap",
                    "x": round(x, 1),
                    "y": round(y, 1),
                    "radius": round(rng.uniform(108, 168), 1),
                    "thickness": round(rng.uniform(24, 36), 1),
                    "rotation_speed_deg": round(rng.uniform(45, 130), 1),
                    "gap_center_deg": round(rng.uniform(180, 320), 1),
                    "gap_size_deg": round(rng.uniform(52, 74), 1),
                    "fill_color": "#182037",
                }
            )
        elif kind == "spinner":
            out.append(
                {
                    "type": "spinner",
                    "x": round(x, 1),
                    "y": round(y, 1),
                    "length": round(rng.uniform(width * 0.2, width * 0.34), 1),
                    "thickness": round(rng.uniform(18, 28), 1),
                    "spin_speed_deg": round(rng.uniform(80, 190), 1),
                    "fill_color": "#182037",
                }
            )
        else:
            out.append(
                {
                    "type": "one_way_gate",
                    "x": round(width * 0.5, 1),
                    "y": round(y, 1),
                    "width": round(rng.uniform(width * 0.45, width * 0.68), 1),
                    "height": 24,
                    "one_way": rng.choice(["down", "up"]),
                    "fill_color": "#182037",
                }
            )
    return out
