from __future__ import annotations

from songracer.config import ObstacleConfig
from songracer.templates import (
    generate_obstacle_stream,
    obstacle_type_catalog,
    obstacle_templates,
    obstacle_templates_payload,
)


def test_obstacle_templates_are_parseable_configs() -> None:
    templates = obstacle_templates()
    assert {"starter", "rings", "gates"}.issubset(templates.keys())
    for name, items in templates.items():
        assert isinstance(items, list), f"{name} template must be a list"
        assert len(items) > 0, f"{name} template should not be empty"
        for idx, obstacle in enumerate(items):
            parsed = ObstacleConfig(**obstacle)
            assert parsed.type in {
                "rect",
                "circle",
                "ring_gap",
                "moving_rect",
                "pendulum",
                "one_way_gate",
                "spinner",
            }, f"{name}[{idx}] invalid type {parsed.type}"


def test_obstacle_templates_payload_has_version_and_count() -> None:
    payload = obstacle_templates_payload()
    assert payload["template_count"] >= 3
    assert str(payload["version"]).startswith("sha256:")
    assert "templates" in payload


def test_generate_obstacle_stream_deterministic_for_same_seed() -> None:
    a = generate_obstacle_stream(count=6, start_y=900, spacing=240, width=1080, seed=42)
    b = generate_obstacle_stream(count=6, start_y=900, spacing=240, width=1080, seed=42)
    c = generate_obstacle_stream(count=6, start_y=900, spacing=240, width=1080, seed=43)
    assert a == b
    assert a != c


def test_generate_obstacle_stream_includes_circle_variant() -> None:
    obstacles = generate_obstacle_stream(
        count=40,
        start_y=900,
        spacing=200,
        width=1080,
        seed=7,
    )
    kinds = {o["type"] for o in obstacles}
    assert "circle" in kinds


def test_obstacle_type_catalog_has_known_labels() -> None:
    catalog = obstacle_type_catalog()
    assert any(item["type"] == "rect" for item in catalog)
    assert any(item["label"] == "Ring Gap" for item in catalog)
