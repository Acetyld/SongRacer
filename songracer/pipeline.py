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
    total_samples = int(round((sim.positions.shape[0] / cfg.render.fps) * sr))
    out = np.zeros((total_samples, channels), dtype=np.int32)
    fade_n = int(round(sr * cfg.audio.switch_crossfade_ms / 1000.0))
    prev_active = -1

    for frame in range(sim.positions.shape[0]):
        start = int(round(frame * sr / cfg.render.fps))
        end = int(round((frame + 1) * sr / cfg.render.fps))
        count = max(0, end - start)
        if count <= 0:
            continue

        active = int(sim.active_leaders[frame])
        if active < 0:
            prev_active = active
            continue

        playhead = float(sim.playheads[frame, active] + cfg.racers[active].sync_offset_seconds)
        src_start = int(round(playhead * sr))
        seg = (
            sources[active].audio_slice_samples(src_start, count).astype(np.float32)
            * cfg.audio.singer_volume
        ).astype(np.int32)

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

    _mix_sfx(cfg, sim, out, sr)
    return np.clip(out, -32768, 32767).astype(np.int16)


def _mix_tone(
    out: np.ndarray,
    sample_rate: int,
    start_sample: int,
    duration_seconds: float,
    frequency: float,
    volume: float,
) -> None:
    count = int(round(duration_seconds * sample_rate))
    if count <= 0 or start_sample >= out.shape[0]:
        return
    end = min(out.shape[0], start_sample + count)
    count = end - start_sample
    t = np.arange(count, dtype=np.float32) / float(sample_rate)
    env = np.ones((count,), dtype=np.float32)
    fade = min(count // 4, int(0.012 * sample_rate))
    if fade > 1:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        env[:fade] *= ramp
        env[-fade:] *= ramp[::-1]
    tone = np.sin(2.0 * math.pi * frequency * t) * env
    amp = float(14000.0 * volume)
    wave = (tone * amp).astype(np.int32).reshape((-1, 1))
    out[start_sample:end] += wave


def _load_audio_clip(path: str, sample_rate: int, channels: int) -> np.ndarray:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        path,
        "-f",
        "s16le",
        "-acodec",
        "pcm_s16le",
        "-ac",
        str(channels),
        "-ar",
        str(sample_rate),
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Failed decoding SFX '{path}': {proc.stderr.decode('utf-8', errors='ignore')}"
        )
    pcm = np.frombuffer(proc.stdout, dtype=np.int16)
    if pcm.size == 0:
        return np.zeros((0, channels), dtype=np.int16)
    return pcm.reshape((-1, channels))


def _mix_pcm_clip(
    out: np.ndarray,
    clip: np.ndarray,
    start_sample: int,
    volume: float,
) -> None:
    if clip.size == 0 or start_sample >= out.shape[0]:
        return
    if start_sample < 0:
        clip = clip[-start_sample:]
        start_sample = 0
    if clip.size == 0:
        return
    end = min(out.shape[0], start_sample + clip.shape[0])
    out[start_sample:end] += (clip[: end - start_sample].astype(np.float32) * volume).astype(
        np.int32
    )


def _mix_sfx(cfg: RaceConfig, sim: SimulationResult, out: np.ndarray, sample_rate: int) -> None:
    # Countdown beeps (3,2,1 + GO tone).
    if cfg.audio.countdown_sfx_enabled and cfg.countdown_frames > 0:
        if cfg.audio.countdown_sfx_path:
            clip = _load_audio_clip(
                cfg.audio.countdown_sfx_path,
                sample_rate=sample_rate,
                channels=out.shape[1],
            )
            _mix_pcm_clip(out, clip, 0, cfg.audio.countdown_sfx_volume)
        else:
            max_tick = max(0, int(math.ceil(cfg.render.countdown_seconds)))
            for tick in range(max_tick):
                start = int(round(tick * sample_rate))
                _mix_tone(
                    out,
                    sample_rate,
                    start,
                    duration_seconds=0.13,
                    frequency=750.0 - tick * 35.0,
                    volume=cfg.audio.countdown_sfx_volume,
                )
            go_start = int(round(cfg.render.countdown_seconds * sample_rate))
            _mix_tone(
                out,
                sample_rate,
                go_start,
                duration_seconds=0.24,
                frequency=1020.0,
                volume=cfg.audio.countdown_sfx_volume * 1.1,
            )
            _mix_tone(
                out,
                sample_rate,
                go_start + int(round(0.1 * sample_rate)),
                duration_seconds=0.2,
                frequency=1320.0,
                volume=cfg.audio.countdown_sfx_volume * 0.8,
            )

    # Winner jingle.
    if cfg.audio.victory_sfx_enabled and sim.winner_frame >= 0:
        start = int(round((sim.winner_frame / cfg.render.fps) * sample_rate))
        if cfg.audio.victory_sfx_path:
            clip = _load_audio_clip(
                cfg.audio.victory_sfx_path,
                sample_rate=sample_rate,
                channels=out.shape[1],
            )
            _mix_pcm_clip(out, clip, start, cfg.audio.victory_sfx_volume)
        else:
            notes = [660.0, 880.0, 1100.0]
            note_len = 0.15
            for idx, note in enumerate(notes):
                _mix_tone(
                    out,
                    sample_rate,
                    start + int(round(idx * note_len * sample_rate)),
                    duration_seconds=note_len,
                    frequency=note,
                    volume=cfg.audio.victory_sfx_volume,
                )


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
        total_frames = sim.positions.shape[0]
        for frame in range(total_frames):
            if frame % cfg.render.fps == 0:
                print(f"rendering frame {frame}/{total_frames}")

            frame_playheads = sim.playheads[frame]
            racer_frames = [
                sources[idx].frame_at(
                    float(frame_playheads[idx] + cfg.racers[idx].sync_offset_seconds)
                )
                for idx in range(len(cfg.racers))
            ]
            if frame < cfg.countdown_frames:
                sim_time = 0.0
            else:
                sim_time = (frame - cfg.countdown_frames) / cfg.render.fps
            obstacle_visuals = [obs.visual(sim_time) for obs in sim.obstacles]
            winner_text = None
            if sim.winner_frame >= 0 and frame >= sim.winner_frame and sim.winner_index >= 0:
                winner_text = racer_names[sim.winner_index]
            canvas = compositor.render(
                frame_index=frame,
                sim_time=sim_time,
                positions=sim.positions[frame],
                racer_frames=racer_frames,
                racer_names=racer_names,
                racer_radii=racer_radii,
                leader=int(sim.leaders[frame]),
                obstacle_visuals=obstacle_visuals,
                camera_y=float(sim.camera_y[frame]),
                countdown_text=_countdown_text(cfg, frame),
                winner_text=winner_text,
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
        crop_centers=[(r.crop_center_x, r.crop_center_y) for r in cfg.racers],
    )
    try:
        _render_video_with_audio(cfg, sim, sources, output)
    finally:
        for source in sources:
            source.close()

    return RenderStats(
        output_path=str(output),
        total_frames=sim.positions.shape[0],
        leaders_switches=_count_switches(sim.active_leaders),
        timeline_hash=timeline_hash(sim),
    )
