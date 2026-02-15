from __future__ import annotations

from pathlib import Path
import subprocess

import numpy as np

from songracer.config import RaceConfig, RacerConfig, RenderConfig, AudioConfig, PhysicsConfig
from songracer.simulation import simulate_race, timeline_hash


def _make_video(path: Path, freq: int = 330, duration: float = 2.0) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size=180x320:rate=30:duration={duration}",
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


def _basic_config(tmp_path: Path) -> RaceConfig:
    v1 = tmp_path / "a.mp4"
    v2 = tmp_path / "b.mp4"
    _make_video(v1, freq=300)
    _make_video(v2, freq=520)
    return RaceConfig(
        render=RenderConfig(width=240, height=426, fps=30, duration_seconds=1.5, countdown_seconds=0),
        physics=PhysicsConfig(gravity=1200, damping=0.995, restitution=0.5, max_speed=1300, substeps=2),
        audio=AudioConfig(sample_rate=48000, channels=2, switch_crossfade_ms=0),
        racers=[
            RacerConfig(name="A", video_path=str(v1), x=80, y=80, radius=30),
            RacerConfig(name="B", video_path=str(v2), x=150, y=120, radius=30),
        ],
    )


def test_playheads_advance_only_active_leader(tmp_path: Path) -> None:
    cfg = _basic_config(tmp_path)
    sim = simulate_race(cfg)

    deltas = np.diff(sim.playheads, axis=0)
    for frame in range(deltas.shape[0]):
        active = int(sim.active_leaders[frame])
        for racer_idx, delta in enumerate(deltas[frame]):
            if racer_idx == active:
                assert delta > 0
            else:
                assert delta == 0


def test_simulation_deterministic_hash(tmp_path: Path) -> None:
    cfg = _basic_config(tmp_path)
    sim1 = simulate_race(cfg)
    sim2 = simulate_race(cfg)
    assert timeline_hash(sim1) == timeline_hash(sim2)
