from __future__ import annotations

from pathlib import Path
import subprocess

from songracer.cli import _scaled_config
from songracer.config import RaceConfig, RacerConfig


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
            "testsrc=size=120x200:rate=24:duration=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=1",
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


def test_scaled_config_forces_even_video_dimensions(tmp_path: Path) -> None:
    v = tmp_path / "v.mp4"
    _make_video(v)
    cfg = RaceConfig(
        racers=[RacerConfig(name="A", video_path=str(v), x=50, y=50, radius=20)],
        obstacles=[],
    )
    scaled = _scaled_config(cfg, 0.16)
    assert scaled.render.width % 2 == 0
    assert scaled.render.height % 2 == 0
