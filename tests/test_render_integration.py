from __future__ import annotations

from pathlib import Path
import subprocess

from songracer.config import (
    AudioConfig,
    BackgroundConfig,
    ObstacleConfig,
    RaceConfig,
    RacerConfig,
    RenderConfig,
)
from songracer.pipeline import render_race


def _make_video(path: Path, freq: int, duration: float = 4.0) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size=240x426:rate=30:duration={duration}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency={freq}:sample_rate=48000:duration={duration}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(path),
    ]
    subprocess.run(cmd, check=True)


def test_render_short_mp4(tmp_path: Path) -> None:
    v1 = tmp_path / "s1.mp4"
    v2 = tmp_path / "s2.mp4"
    _make_video(v1, freq=240)
    _make_video(v2, freq=520)

    cfg = RaceConfig(
        render=RenderConfig(width=270, height=480, fps=24, duration_seconds=2.0, countdown_seconds=1.0),
        audio=AudioConfig(sample_rate=48000, channels=2, switch_crossfade_ms=8),
        background=BackgroundConfig(mode="solid", solid_color="#7CCBFF"),
        racers=[
            RacerConfig(name="P1", video_path=str(v1), x=100, y=120, radius=38),
            RacerConfig(name="P2", video_path=str(v2), x=170, y=120, radius=38),
        ],
        obstacles=[
            ObstacleConfig(
                type="spinner",
                x=130,
                y=260,
                length=120,
                thickness=14,
                angle_deg=10,
                spin_speed_deg=170,
                fill_color="#1A2034",
                stroke_color="#090D18",
                opacity=0.95,
            )
        ],
    )

    output = tmp_path / "race.mp4"
    stats = render_race(cfg, output)
    assert output.exists()
    assert output.stat().st_size > 0
    assert stats.total_frames == int(round((2.0 + 1.0) * 24))

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    duration = float(probe.stdout.strip())
    assert 2.7 <= duration <= 3.3


def test_render_honors_sync_common_window_cap(tmp_path: Path) -> None:
    v1 = tmp_path / "c1.mp4"
    _make_video(v1, freq=300, duration=5.0)
    cfg = RaceConfig(
        sync_common_window_seconds=1.25,
        render=RenderConfig(width=240, height=426, fps=20, duration_seconds=6.0, countdown_seconds=0.5),
        background=BackgroundConfig(mode="solid", solid_color="#89CEFF"),
        racers=[
            RacerConfig(
                name="Only",
                video_path=str(v1),
                x=120,
                y=100,
                radius=36,
                sync_trim_start_seconds=0.4,
            )
        ],
        obstacles=[],
    )
    output = tmp_path / "sync_cap.mp4"
    stats = render_race(cfg, output)
    expected_frames = int(round((0.5 + 1.25) * 20))
    assert stats.total_frames == expected_frames
