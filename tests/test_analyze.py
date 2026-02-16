from __future__ import annotations

from songracer.analyze import analyze_config_risk


def test_analyze_config_risk_detects_trap_patterns() -> None:
    cfg = {
        "render": {"width": 1080, "height": 1920},
        "obstacles": [
            {"type": "rect", "x": 540, "y": 800, "width": 920},
            {"type": "rect", "x": 540, "y": 860, "width": 910},
            {"type": "ring_gap", "x": 540, "y": 1100, "radius": 180, "gap_size_deg": 28},
            {"type": "spinner", "x": 540, "y": 1300, "length": 840},
        ],
    }
    out = analyze_config_risk(cfg)
    assert out["warning_count"] == len(out["warnings"])
    assert out["warning_count"] >= 3
    assert 0 <= out["risk_score"] <= 100
    assert out["risk_score"] > 0
    codes = {w["code"] for w in out["warnings"]}
    assert "blocker_too_wide" in codes
    assert "rows_too_close" in codes
    assert "ring_gap_too_small" in codes
    blocker_warning = next(w for w in out["warnings"] if w["code"] == "blocker_too_wide")
    assert blocker_warning["obstacle_index"] == 0
    row_warning = next(w for w in out["warnings"] if w["code"] == "rows_too_close")
    assert set(row_warning["obstacle_indices"]) == {0, 1}
