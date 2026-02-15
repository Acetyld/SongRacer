from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .cli import _scaled_config
from .config import ConfigError, load_config, validate_config
from .jobs import JobManager
from .pipeline import render_race


job_manager = JobManager(max_workers=2)


@asynccontextmanager
async def _lifespan(_: FastAPI):
    try:
        yield
    finally:
        job_manager.shutdown()


app = FastAPI(title="SongRacer API", version="0.1.0", lifespan=_lifespan)


class ValidateRequest(BaseModel):
    config_path: str = Field(..., description="Path to SongRacer JSON config")


class RenderRequest(BaseModel):
    config_path: str = Field(..., description="Path to SongRacer JSON config")
    output_path: str = Field(..., description="Path for output MP4")
    preview_scale: float = Field(1.0, ge=0.01, le=1.0)


class JobSubmitResponse(BaseModel):
    job_id: str
    state: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/validate")
def validate(payload: ValidateRequest) -> dict[str, Any]:
    try:
        cfg = load_config(payload.config_path)
        validate_config(cfg)
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"valid": True, "racers": len(cfg.racers), "obstacles": len(cfg.obstacles)}


@app.post("/render")
def render(payload: RenderRequest) -> dict[str, Any]:
    try:
        cfg = load_config(payload.config_path)
        cfg = _scaled_config(cfg, payload.preview_scale)
        validate_config(cfg)
        stats = render_race(cfg, payload.output_path)
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "output_path": stats.output_path,
        "total_frames": stats.total_frames,
        "leaders_switches": stats.leaders_switches,
        "timeline_hash": stats.timeline_hash,
    }


@app.post("/jobs", response_model=JobSubmitResponse)
def create_job(payload: RenderRequest) -> JobSubmitResponse:
    try:
        job = job_manager.submit(
            config_path=payload.config_path,
            output_path=payload.output_path,
            preview_scale=payload.preview_scale,
        )
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JobSubmitResponse(job_id=job.job_id, state=job.state)


@app.get("/jobs")
def list_jobs() -> dict[str, list[dict[str, Any]]]:
    return {"jobs": [job.to_dict() for job in job_manager.list_jobs()]}


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@app.get("/jobs/{job_id}/artifact")
def get_job_artifact(job_id: str) -> FileResponse:
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.state != "completed":
        raise HTTPException(status_code=409, detail=f"Job not completed (state={job.state})")
    if job.stats is None:
        raise HTTPException(status_code=500, detail="Job completed without stats")
    artifact_path = job.stats.output_path
    return FileResponse(artifact_path, media_type="video/mp4", filename="songracer.mp4")


def run_dev_server() -> None:
    import uvicorn

    uvicorn.run("songracer.api:app", host="0.0.0.0", port=8080, reload=False)
