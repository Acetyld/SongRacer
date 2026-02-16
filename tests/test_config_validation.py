from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from songracer.config import (
    BackgroundConfig,
    ConfigError,
    ObstacleConfig,
    RaceConfig,
    RacerConfig,
    load_config,
    validate_config,
)


def _make_video(path: Path) -> None:
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
            "testsrc=size=128x128:rate=24:duration=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=350:sample_rate=48000:duration=1",
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


def _base_cfg(tmp_path: Path) -> RaceConfig:
    video = tmp_path / "racer.mp4"
    _make_video(video)
    return RaceConfig(
        racers=[RacerConfig(name="R1", video_path=str(video), x=100, y=100, radius=30)],
        obstacles=[],
    )


def test_background_image_mode_requires_existing_file(tmp_path: Path) -> None:
    cfg = _base_cfg(tmp_path)
    cfg.background = BackgroundConfig(mode="image", image_path=str(tmp_path / "missing.png"))
    with pytest.raises(ConfigError):
        validate_config(cfg)


def test_spinner_obstacle_type_is_valid(tmp_path: Path) -> None:
    cfg = _base_cfg(tmp_path)
    cfg.obstacles = [ObstacleConfig(type="spinner", x=100, y=180, length=90, thickness=12)]
    validate_config(cfg)


def test_crop_center_bounds_validation(tmp_path: Path) -> None:
    cfg = _base_cfg(tmp_path)
    cfg.racers[0].crop_center_x = 1.2
    with pytest.raises(ConfigError):
        validate_config(cfg)


def test_audio_sfx_path_must_exist(tmp_path: Path) -> None:
    cfg = _base_cfg(tmp_path)
    cfg.audio.countdown_sfx_path = str(tmp_path / "missing_countdown.wav")
    with pytest.raises(ConfigError):
        validate_config(cfg)


def test_legacy_sync_offsets_are_normalized_to_trim_starts(tmp_path: Path) -> None:
    v1 = tmp_path / "a.mp4"
    v2 = tmp_path / "b.mp4"
    _make_video(v1)
    _make_video(v2)
    cfg_path = tmp_path / "sync_cfg.json"
    cfg_path.write_text(
        json.dumps(
            {
                "render": {"width": 240, "height": 426, "duration_seconds": 1.0, "countdown_seconds": 0},
                "racers": [
                    {"name": "A", "video_path": str(v1), "x": 80, "y": 80, "radius": 30, "sync_offset_seconds": 0.0},
                    {"name": "B", "video_path": str(v2), "x": 150, "y": 82, "radius": 30, "sync_offset_seconds": -0.5},
                ],
                "obstacles": [],
            }
        )
    )
    cfg = load_config(cfg_path)
    assert cfg.racers[0].sync_trim_start_seconds == pytest.approx(0.0)
    assert cfg.racers[1].sync_trim_start_seconds == pytest.approx(0.5)
