from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from songracer.config import (
    BackgroundConfig,
    ConfigError,
    ObstacleConfig,
    RaceConfig,
    RacerConfig,
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
