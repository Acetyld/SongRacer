from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from songracer.sync import (
    SyncAnalysis,
    apply_offsets_to_config_json,
    estimate_offset_seconds_from_signals,
)


def test_estimate_offset_seconds_from_signals_bidirectional() -> None:
    sr = 1000
    ref = np.zeros((5000,), dtype=np.float32)
    ref[1100:1400] = 1.0

    delayed = np.zeros_like(ref)
    delayed[1450:1750] = 1.0
    lag_delayed = estimate_offset_seconds_from_signals(ref, delayed, sr, max_shift_seconds=1.0)
    assert 0.3 <= lag_delayed <= 0.4

    ahead = np.zeros_like(ref)
    ahead[900:1200] = 1.0
    lag_ahead = estimate_offset_seconds_from_signals(ref, ahead, sr, max_shift_seconds=1.0)
    assert -0.25 <= lag_ahead <= -0.15


def test_apply_offsets_to_config_json(tmp_path: Path) -> None:
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(
        json.dumps(
            {
                "racers": [
                    {"name": "A", "video_path": "/tmp/a.mp4", "x": 1, "y": 1, "radius": 1},
                    {"name": "B", "video_path": "/tmp/b.mp4", "x": 2, "y": 2, "radius": 1},
                ]
            }
        )
    )
    analysis = SyncAnalysis(
        offsets_seconds=[0.0, -0.123456],
        trim_start_seconds=[0.0, 0.123456],
        common_window_seconds=4.2,
        durations_seconds=[5.0, 4.5],
    )
    out = apply_offsets_to_config_json(cfg_path, analysis, output_path=None)
    obj = json.loads(out.read_text())
    assert obj["racers"][0]["sync_offset_seconds"] == 0.0
    assert obj["racers"][1]["sync_offset_seconds"] == -0.12346
    assert obj["racers"][1]["sync_trim_start_seconds"] == 0.12346
    assert obj["sync_common_window_seconds"] == 4.2
