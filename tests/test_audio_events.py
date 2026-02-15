from __future__ import annotations

from pathlib import Path
import subprocess

import numpy as np

from songracer.config import AudioConfig, RaceConfig, RacerConfig, RenderConfig
from songracer.media import open_sources
from songracer.pipeline import _compose_audio
from songracer.simulation import simulate_race


def _make_video(path: Path, duration: float = 3.0) -> None:
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
            f"testsrc=size=180x320:rate=24:duration={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=330:sample_rate=48000:duration={duration}",
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


def test_countdown_and_victory_sfx_are_mixed(tmp_path: Path) -> None:
    video = tmp_path / "racer.mp4"
    _make_video(video, duration=4.0)

    cfg = RaceConfig(
        render=RenderConfig(
            width=240,
            height=426,
            world_height=650,
            fps=24,
            duration_seconds=6.0,
            countdown_seconds=2.0,
            goal_margin=80.0,
            auto_end_on_winner=True,
            winner_hold_seconds=1.2,
        ),
        audio=AudioConfig(
            sample_rate=48000,
            channels=2,
            switch_crossfade_ms=6,
            countdown_silence=True,
            singer_volume=0.0,
            countdown_sfx_enabled=True,
            countdown_sfx_volume=0.6,
            victory_sfx_enabled=True,
            victory_sfx_volume=0.7,
        ),
        racers=[
            RacerConfig(
                name="Solo",
                video_path=str(video),
                x=120,
                y=120,
                radius=34,
                crop_center_x=0.5,
                crop_center_y=0.45,
            )
        ],
        obstacles=[],
    )

    sim = simulate_race(cfg)
    sources = open_sources(
        [cfg.racers[0].video_path],
        fps=cfg.render.fps,
        square_size=128,
        sample_rate=cfg.audio.sample_rate,
        channels=cfg.audio.channels,
        crop_centers=[(cfg.racers[0].crop_center_x, cfg.racers[0].crop_center_y)],
    )
    try:
        audio = _compose_audio(cfg, sim, sources)
    finally:
        for source in sources:
            source.close()

    assert audio.dtype == np.int16
    assert audio.shape[0] > 1000
    countdown_window = audio[: int(cfg.audio.sample_rate * 0.5)]
    assert np.max(np.abs(countdown_window)) > 0

    assert sim.winner_frame >= 0
    winner_sample = int(round((sim.winner_frame / cfg.render.fps) * cfg.audio.sample_rate))
    victory_window = audio[winner_sample : winner_sample + int(0.4 * cfg.audio.sample_rate)]
    assert victory_window.size > 0
    assert np.max(np.abs(victory_window)) > 0
