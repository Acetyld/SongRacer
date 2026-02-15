from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Literal
from uuid import uuid4

from .cli import _scaled_config
from .config import ConfigError, load_config, validate_config
from .pipeline import RenderStats, render_race


JobState = Literal["queued", "running", "completed", "failed"]


@dataclass(slots=True)
class RenderJob:
    job_id: str
    config_path: str
    output_path: str
    preview_scale: float
    state: JobState = "queued"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    stats: RenderStats | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "job_id": self.job_id,
            "config_path": self.config_path,
            "output_path": self.output_path,
            "preview_scale": self.preview_scale,
            "state": self.state,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
        }
        if self.stats is not None:
            payload["stats"] = {
                "output_path": self.stats.output_path,
                "total_frames": self.stats.total_frames,
                "leaders_switches": self.stats.leaders_switches,
                "timeline_hash": self.stats.timeline_hash,
            }
        return payload


class JobManager:
    def __init__(self, max_workers: int = 2) -> None:
        self.max_workers = max_workers
        self._lock = threading.Lock()
        self._jobs: dict[str, RenderJob] = {}
        self._futures: dict[str, Future[None]] = {}
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="songracer")
        self._shutdown = False

    def submit(self, config_path: str, output_path: str, preview_scale: float) -> RenderJob:
        if not (0 < preview_scale <= 1):
            raise ConfigError("preview_scale must be in (0,1]")
        job_id = uuid4().hex
        job = RenderJob(
            job_id=job_id,
            config_path=str(Path(config_path).expanduser().resolve()),
            output_path=str(Path(output_path).expanduser().resolve()),
            preview_scale=preview_scale,
        )
        with self._lock:
            if self._shutdown:
                self._executor = ThreadPoolExecutor(
                    max_workers=self.max_workers, thread_name_prefix="songracer"
                )
                self._shutdown = False
            self._jobs[job_id] = job
            future = self._executor.submit(self._run_job, job_id)
            self._futures[job_id] = future
        return job

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.state = "running"
            job.started_at = datetime.now(timezone.utc).isoformat()
        try:
            cfg = load_config(job.config_path)
            cfg = _scaled_config(cfg, job.preview_scale)
            validate_config(cfg)
            stats = render_race(cfg, job.output_path)
            with self._lock:
                job.state = "completed"
                job.stats = stats
                job.finished_at = datetime.now(timezone.utc).isoformat()
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                job.state = "failed"
                job.error = str(exc)
                job.finished_at = datetime.now(timezone.utc).isoformat()

    def get(self, job_id: str) -> RenderJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self) -> list[RenderJob]:
        with self._lock:
            return list(self._jobs.values())

    def shutdown(self) -> None:
        with self._lock:
            self._shutdown = True
            self._executor.shutdown(wait=False, cancel_futures=False)
