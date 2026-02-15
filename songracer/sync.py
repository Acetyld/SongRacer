from __future__ import annotations

import json
from pathlib import Path
import subprocess

import numpy as np


class SyncError(RuntimeError):
    pass


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
) -> list[float]:
    if not video_paths:
        raise SyncError("At least one video path is required for sync")
    for path in video_paths:
        if not Path(path).exists():
            raise SyncError(f"Video path for sync not found: {path}")

    signals = [_decode_mono_pcm(path, sample_rate=sample_rate) for path in video_paths]
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
    return offsets


def apply_offsets_to_config_json(
    config_path: str | Path,
    offsets: list[float],
    output_path: str | Path | None = None,
) -> Path:
    in_path = Path(config_path).expanduser().resolve()
    obj = json.loads(in_path.read_text())
    racers = obj.get("racers", [])
    if len(racers) != len(offsets):
        raise SyncError(
            f"Offset count {len(offsets)} does not match racer count {len(racers)}"
        )
    for idx, racer in enumerate(racers):
        racer["sync_offset_seconds"] = round(float(offsets[idx]), 5)
    out = (
        Path(output_path).expanduser().resolve()
        if output_path is not None
        else in_path
    )
    out.write_text(json.dumps(obj, indent=2))
    return out
