from __future__ import annotations

from songracer.config import ObstacleConfig
from songracer.templates import obstacle_templates, obstacle_templates_payload


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
