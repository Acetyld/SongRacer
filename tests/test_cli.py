from __future__ import annotations

import json
from pathlib import Path
import subprocess

from songracer.cli import _scaled_config, main
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


def test_analyze_command_reports_warnings(tmp_path: Path, capsys) -> None:
    cfg_path = tmp_path / "course.json"
    cfg_path.write_text(
        json.dumps(
            {
                "render": {"width": 1080, "height": 1920},
                "obstacles": [
                    {"type": "rect", "x": 540, "y": 800, "width": 900},
                    {"type": "rect", "x": 540, "y": 860, "width": 900},
                ],
            }
        )
    )
    main(["analyze", "--config", str(cfg_path)])
    out = capsys.readouterr().out
    body = json.loads(out)
    assert body["warning_count"] >= 1
    codes = {item["code"] for item in body["warnings"]}
    assert "rows_too_close" in codes
