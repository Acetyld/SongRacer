from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess

import numpy as np


class SyncError(RuntimeError):
    pass


@dataclass(slots=True)
class SyncAnalysis:
    offsets_seconds: list[float]
    trim_start_seconds: list[float]
    common_window_seconds: float
    durations_seconds: list[float]


def _decode_mono_pcm(video_path: str, sample_rate: int) -> np.ndarray:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        video_path,
        "-f",
        "s16le",
        "-acodec",
        "pcm_s16le",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        raise SyncError(
            f"Failed decoding audio for sync from {video_path}: "
            f"{proc.stderr.decode('utf-8', errors='ignore')}"
        )
    pcm = np.frombuffer(proc.stdout, dtype=np.int16)
    if pcm.size == 0:
        return np.zeros((0,), dtype=np.float32)
    return pcm.astype(np.float32) / 32768.0


def _duration_seconds(video_path: str) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise SyncError(f"Failed reading duration for {video_path}: {proc.stderr.strip()}")
    try:
        return float(proc.stdout.strip())
    except ValueError as exc:
        raise SyncError(f"Invalid duration value for {video_path}") from exc


def _prepare_envelope(signal: np.ndarray, sample_rate: int) -> tuple[np.ndarray, int]:
    if signal.size == 0:
        return np.zeros((0,), dtype=np.float32), 200
    x = signal - float(np.mean(signal))
    env = np.abs(x)
    kernel_size = max(4, int(round(sample_rate * 0.03)))
    kernel = np.ones((kernel_size,), dtype=np.float32) / float(kernel_size)
    smooth = np.convolve(env, kernel, mode="same")
    target_rate = 200
    hop = max(1, int(round(sample_rate / target_rate)))
    down = smooth[::hop]
    down = down - float(np.mean(down))
    denom = float(np.std(down))
    if denom > 1e-8:
        down = down / denom
    return down.astype(np.float32), int(round(sample_rate / hop))


def estimate_offset_seconds_from_signals(
    reference: np.ndarray,
    target: np.ndarray,
    sample_rate: int,
    max_shift_seconds: float = 8.0,
) -> float:
    ref_env, env_rate = _prepare_envelope(reference, sample_rate)
    tgt_env, _ = _prepare_envelope(target, sample_rate)
    if ref_env.size == 0 or tgt_env.size == 0:
        return 0.0

    corr = np.correlate(tgt_env, ref_env, mode="full")
    lags = np.arange(-(ref_env.size - 1), tgt_env.size, dtype=np.int32)
    max_lag = int(round(max_shift_seconds * env_rate))
    mask = np.abs(lags) <= max_lag
    if not np.any(mask):
        return 0.0
    masked_corr = corr[mask]
    masked_lags = lags[mask]
    best_lag = int(masked_lags[int(np.argmax(masked_corr))])
    return float(best_lag / env_rate)


def estimate_video_sync_offsets(
    video_paths: list[str],
    sample_rate: int = 16000,
    max_shift_seconds: float = 8.0,
) -> SyncAnalysis:
    if not video_paths:
        raise SyncError("At least one video path is required for sync")
    for path in video_paths:
        if not Path(path).exists():
            raise SyncError(f"Video path for sync not found: {path}")

    signals = [_decode_mono_pcm(path, sample_rate=sample_rate) for path in video_paths]
    durations = [_duration_seconds(path) for path in video_paths]
    ref = signals[0]
    offsets = [0.0]
    for signal in signals[1:]:
        lag = estimate_offset_seconds_from_signals(
            reference=ref,
            target=signal,
            sample_rate=sample_rate,
            max_shift_seconds=max_shift_seconds,
        )
        offsets.append(float(lag))
    common_anchor = max(offsets)
    trims = [float(common_anchor - offset) for offset in offsets]
    avail = [max(0.0, durations[idx] - trims[idx]) for idx in range(len(video_paths))]
    common_window = min(avail) if avail else 0.0
    return SyncAnalysis(
        offsets_seconds=offsets,
        trim_start_seconds=trims,
        common_window_seconds=float(max(0.0, common_window)),
        durations_seconds=durations,
    )


def apply_offsets_to_config_json(
    config_path: str | Path,
    analysis: SyncAnalysis,
    output_path: str | Path | None = None,
    apply_duration_cap: bool = True,
) -> Path:
    in_path = Path(config_path).expanduser().resolve()
    obj = json.loads(in_path.read_text())
    racers = obj.get("racers", [])
    if len(racers) != len(analysis.offsets_seconds):
        raise SyncError(
            f"Offset count {len(analysis.offsets_seconds)} does not match racer count {len(racers)}"
        )
    obj["sync_common_window_seconds"] = round(analysis.common_window_seconds, 5)
    for idx, racer in enumerate(racers):
        racer["sync_offset_seconds"] = round(float(analysis.offsets_seconds[idx]), 5)
        racer["sync_trim_start_seconds"] = round(float(analysis.trim_start_seconds[idx]), 5)
    if apply_duration_cap and "render" in obj and isinstance(obj["render"], dict):
        current = obj["render"].get("duration_seconds")
        if isinstance(current, (float, int)):
            obj["render"]["duration_seconds"] = min(
                float(current), float(analysis.common_window_seconds)
            )
    out = (
        Path(output_path).expanduser().resolve()
        if output_path is not None
        else in_path
    )
    out.write_text(json.dumps(obj, indent=2))
    return out
