from __future__ import annotations

from dataclasses import dataclass
import math
import subprocess
from pathlib import Path

import numpy as np


class MediaError(RuntimeError):
    pass


def _run_ffprobe_json(video_path: str) -> dict:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        video_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise MediaError(f"ffprobe failed for {video_path}: {proc.stderr.strip()}")
    import json

    return json.loads(proc.stdout)


def _best_video_stream(streams: list[dict]) -> dict:
    for s in streams:
        if s.get("codec_type") == "video":
            return s
    raise MediaError("No video stream found")


@dataclass(slots=True)
class VideoSource:
    path: str
    fps: int
    square_size: int
    audio_sample_rate: int
    audio_channels: int
    crop_center_x: float = 0.5
    crop_center_y: float = 0.5
    _video_proc: subprocess.Popen | None = None
    _frame_index: int = -1
    _last_frame: np.ndarray | None = None
    _video_eof: bool = False
    audio_pcm: np.ndarray | None = None

    def __post_init__(self) -> None:
        if not Path(self.path).exists():
            raise MediaError(f"Video file not found: {self.path}")
        self._start_video_stream()
        self.audio_pcm = self._load_audio_pcm()
        if self._last_frame is None:
            self._last_frame = np.zeros(
                (self.square_size, self.square_size, 3), dtype=np.uint8
            )

    def _start_video_stream(self) -> None:
        cx = max(0.0, min(1.0, float(self.crop_center_x)))
        cy = max(0.0, min(1.0, float(self.crop_center_y)))
        vf = (
            "crop='min(iw,ih)':'min(iw,ih)':"
            f"'(iw-min(iw,ih))*{cx}':'(ih-min(iw,ih))*{cy}',"
            f"scale={self.square_size}:{self.square_size},fps={self.fps}"
        )
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            self.path,
            "-vf",
            vf,
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ]
        self._video_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def _read_next_frame(self) -> np.ndarray | None:
        if self._video_proc is None or self._video_proc.stdout is None:
            return None
        nbytes = self.square_size * self.square_size * 3
        raw = self._video_proc.stdout.read(nbytes)
        if raw is None or len(raw) != nbytes:
            self._video_eof = True
            return None
        arr = np.frombuffer(raw, dtype=np.uint8).reshape(
            (self.square_size, self.square_size, 3)
        )
        return arr

    def frame_at(self, playhead_seconds: float) -> np.ndarray:
        if self._video_eof:
            return self._last_frame.copy()

        target = max(0, int(math.floor(playhead_seconds * self.fps)))
        while self._frame_index < target:
            frame = self._read_next_frame()
            if frame is None:
                break
            self._frame_index += 1
            self._last_frame = frame

        return self._last_frame.copy()

    def _load_audio_pcm(self) -> np.ndarray:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            self.path,
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ac",
            str(self.audio_channels),
            "-ar",
            str(self.audio_sample_rate),
            "-",
        ]
        proc = subprocess.run(cmd, capture_output=True, check=False)
        if proc.returncode != 0:
            raise MediaError(
                f"ffmpeg audio decode failed for {self.path}: "
                f"{proc.stderr.decode('utf-8', errors='ignore')}"
            )
        pcm = np.frombuffer(proc.stdout, dtype=np.int16)
        if pcm.size == 0:
            return np.zeros((0, self.audio_channels), dtype=np.int16)
        return pcm.reshape((-1, self.audio_channels))

    def audio_slice(self, start_seconds: float, duration_seconds: float) -> np.ndarray:
        if self.audio_pcm is None:
            return np.zeros((0, self.audio_channels), dtype=np.int16)
        start = max(0, int(round(start_seconds * self.audio_sample_rate)))
        count = max(0, int(round(duration_seconds * self.audio_sample_rate)))
        return self.audio_slice_samples(start, count)

    def audio_slice_samples(self, start: int, count: int) -> np.ndarray:
        if self.audio_pcm is None:
            return np.zeros((count, self.audio_channels), dtype=np.int16)
        out = np.zeros((count, self.audio_channels), dtype=np.int16)
        if count == 0:
            return out
        src_start = start
        dst_start = 0
        if src_start < 0:
            dst_start = min(count, -src_start)
            src_start = 0
        if dst_start >= count:
            return out
        end = min(self.audio_pcm.shape[0], src_start + (count - dst_start))
        if end > src_start:
            out[dst_start : dst_start + (end - src_start)] = self.audio_pcm[src_start:end]
        return out

    def close(self) -> None:
        if self._video_proc is None:
            return
        if self._video_proc.stdout is not None:
            self._video_proc.stdout.close()
        if self._video_proc.stderr is not None:
            self._video_proc.stderr.close()
        self._video_proc.terminate()
        self._video_proc.wait(timeout=2)


def open_sources(
    video_paths: list[str],
    fps: int,
    square_size: int,
    sample_rate: int,
    channels: int,
    crop_centers: list[tuple[float, float]] | None = None,
) -> list[VideoSource]:
    centers = crop_centers or [(0.5, 0.5) for _ in video_paths]
    return [
        VideoSource(
            path=p,
            fps=fps,
            square_size=square_size,
            audio_sample_rate=sample_rate,
            audio_channels=channels,
            crop_center_x=centers[idx][0],
            crop_center_y=centers[idx][1],
        )
        for idx, p in enumerate(video_paths)
    ]
