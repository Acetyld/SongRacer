from __future__ import annotations

from dataclasses import dataclass
import math
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import wave

from .compositor import FrameCompositor
from .config import RaceConfig, load_config
from .media import VideoSource, open_sources
from .simulation import SimulationResult, simulate_race, timeline_hash


@dataclass(slots=True)
class RenderStats:
    output_path: str
    total_frames: int
    leaders_switches: int
    timeline_hash: str


def _count_switches(active_leaders: np.ndarray) -> int:
    switches = 0
    prev = int(active_leaders[0]) if active_leaders.size else -1
    for idx in range(1, active_leaders.size):
        cur = int(active_leaders[idx])
        if cur != prev and cur >= 0:
            switches += 1
        prev = cur
    return switches


def _countdown_text(cfg: RaceConfig, frame_index: int) -> str | None:
    if frame_index >= cfg.countdown_frames or cfg.countdown_frames == 0:
        return None
    t = frame_index / cfg.render.fps
    remain = cfg.render.countdown_seconds - t
    if remain <= 0.5:
        return "GO"
    return str(max(1, math.ceil(remain)))


def _compose_audio(
    cfg: RaceConfig,
    sim: SimulationResult,
    sources: list[VideoSource],
) -> np.ndarray:
    sr = cfg.audio.sample_rate
    channels = cfg.audio.channels
    total_samples = int(round(cfg.total_seconds * sr))
    out = np.zeros((total_samples, channels), dtype=np.int32)
    fade_n = int(round(sr * cfg.audio.switch_crossfade_ms / 1000.0))
    prev_active = -1

    for frame in range(cfg.total_frames):
        start = int(round(frame * sr / cfg.render.fps))
        end = int(round((frame + 1) * sr / cfg.render.fps))
        count = max(0, end - start)
        if count <= 0:
            continue

        active = int(sim.active_leaders[frame])
        if active < 0:
            prev_active = active
            continue

        playhead = float(sim.playheads[frame, active])
        src_start = int(round(playhead * sr))
        seg = sources[active].audio_slice_samples(src_start, count).astype(np.int32)

        if prev_active >= 0 and active != prev_active and fade_n > 0:
            cross = min(fade_n, count, start)
            if cross > 0:
                alpha = np.linspace(0.0, 1.0, cross, dtype=np.float32).reshape((-1, 1))
                old = out[start - cross : start].astype(np.float32)
                new = seg[:cross].astype(np.float32)
                blended = old * (1.0 - alpha) + new * alpha
                out[start - cross : start] = blended.astype(np.int32)
                out[start : end] = 0
                if count > cross:
                    out[start : start + (count - cross)] = seg[cross:]
            else:
                out[start:end] = seg
        else:
            out[start:end] = seg

        prev_active = active

    return np.clip(out, -32768, 32767).astype(np.int16)


def _write_wav(path: Path, audio: np.ndarray, sample_rate: int, channels: int) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())


def _render_video_with_audio(
    cfg: RaceConfig,
    sim: SimulationResult,
    sources: list[VideoSource],
    output_path: Path,
) -> None:
    compositor = FrameCompositor(cfg)

    with tempfile.TemporaryDirectory(prefix="songracer_") as td:
        td_path = Path(td)
        wav_path = td_path / "audio.wav"
        audio = _compose_audio(cfg, sim, sources)
        _write_wav(wav_path, audio, cfg.audio.sample_rate, cfg.audio.channels)

        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{cfg.render.width}x{cfg.render.height}",
            "-r",
            str(cfg.render.fps),
            "-i",
            "-",
            "-i",
            str(wav_path),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(output_path),
        ]
        proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)
        if proc.stdin is None:
            raise RuntimeError("Failed to open ffmpeg stdin for raw frames")

        racer_names = [r.name for r in cfg.racers]
        racer_radii = [r.radius for r in cfg.racers]
        for frame in range(cfg.total_frames):
            if frame % cfg.render.fps == 0:
                print(f"rendering frame {frame}/{cfg.total_frames}")

            frame_playheads = sim.playheads[frame]
            racer_frames = [
                sources[idx].frame_at(float(frame_playheads[idx]))
                for idx in range(len(cfg.racers))
            ]
            if frame < cfg.countdown_frames:
                sim_time = 0.0
            else:
                sim_time = (frame - cfg.countdown_frames) / cfg.render.fps
            obstacle_visuals = [obs.visual(sim_time) for obs in sim.obstacles]
            canvas = compositor.render(
                frame_index=frame,
                sim_time=sim_time,
                positions=sim.positions[frame],
                racer_frames=racer_frames,
                racer_names=racer_names,
                racer_radii=racer_radii,
                leader=int(sim.leaders[frame]),
                obstacle_visuals=obstacle_visuals,
                countdown_text=_countdown_text(cfg, frame),
            )
            proc.stdin.write(canvas.tobytes())

        proc.stdin.close()
        ret = proc.wait()
        if ret != 0:
            raise RuntimeError(f"ffmpeg encoding failed with exit code {ret}")


def render_race(config: RaceConfig | str | Path, output_path: str | Path) -> RenderStats:
    cfg = load_config(config) if not isinstance(config, RaceConfig) else config
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    sim = simulate_race(cfg)
    max_circle = max(int(cfg.top_circle.diameter), int(max(r.radius for r in cfg.racers) * 2))
    decode_size = max(128, max_circle)
    sources = open_sources(
        [r.video_path for r in cfg.racers],
        fps=cfg.render.fps,
        square_size=decode_size,
        sample_rate=cfg.audio.sample_rate,
        channels=cfg.audio.channels,
    )
    try:
        _render_video_with_audio(cfg, sim, sources, output)
    finally:
        for source in sources:
            source.close()

    return RenderStats(
        output_path=str(output),
        total_frames=cfg.total_frames,
        leaders_switches=_count_switches(sim.active_leaders),
        timeline_hash=timeline_hash(sim),
    )
