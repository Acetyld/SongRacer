from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Any

from fastapi import File
from fastapi import FastAPI, HTTPException
from fastapi import UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .analyze import analyze_config_risk
from .cli import _scaled_config
from .config import ConfigError, load_config, validate_config
from .db import (
    create_project,
    delete_project,
    get_db_path,
    get_project,
    init_db,
    list_projects,
    update_project,
)
from .jobs import JobManager
from .pipeline import render_race
from .storage import resolve_writable_dir
from .sync import (
    SyncError,
    apply_analysis_to_config_obj,
    estimate_video_sync_offsets,
    extract_waveform_preview,
)


job_manager = JobManager(max_workers=2)


@asynccontextmanager
async def _lifespan(_: FastAPI):
    try:
        init_db()
        yield
    finally:
        job_manager.shutdown()


app = FastAPI(title="SongRacer API", version="0.1.0", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STORAGE_ROOT = resolve_writable_dir(
    env_var="SONGRACER_STORAGE_DIR",
    preferred_dir=PROJECT_ROOT,
    fallback_name="songracer/storage",
)
UPLOAD_DIR = STORAGE_ROOT / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
JOB_CONFIG_DIR = STORAGE_ROOT / "job_configs"
JOB_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR = STORAGE_ROOT / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class ValidateRequest(BaseModel):
    config_path: str = Field(..., description="Path to SongRacer JSON config")


class RenderRequest(BaseModel):
    config_path: str = Field(..., description="Path to SongRacer JSON config")
    output_path: str = Field(..., description="Path for output MP4")
    preview_scale: float = Field(1.0, ge=0.01, le=1.0)


class JobSubmitResponse(BaseModel):
    job_id: str
    state: str


class InlineJobRequest(BaseModel):
    config: dict[str, Any]
    output_path: str | None = None
    preview_scale: float = Field(1.0, ge=0.01, le=1.0)


class AudioSyncRequest(BaseModel):
    video_paths: list[str]
    sample_rate: int = Field(16000, ge=4000, le=96000)
    max_shift_seconds: float = Field(8.0, ge=0.0, le=30.0)


class SyncPreviewRequest(BaseModel):
    video_paths: list[str]
    sample_rate: int = Field(16000, ge=4000, le=96000)
    max_shift_seconds: float = Field(8.0, ge=0.0, le=30.0)
    waveform_sample_rate: int = Field(8000, ge=4000, le=96000)
    waveform_points: int = Field(220, ge=16, le=2000)


class WaveformRequest(BaseModel):
    video_path: str
    sample_rate: int = Field(8000, ge=4000, le=96000)
    points: int = Field(320, ge=16, le=2000)


class ProjectPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    config: dict[str, Any]


class ProjectImportPayload(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    config: dict[str, Any]


class ProjectRenderPayload(BaseModel):
    preview_scale: float = Field(1.0, ge=0.01, le=1.0)
    output_path: str | None = None


class ProjectSyncPayload(BaseModel):
    sample_rate: int = Field(16000, ge=4000, le=96000)
    max_shift_seconds: float = Field(8.0, ge=0.0, le=30.0)
    apply_duration_cap: bool = True


class AnalyzeConfigPayload(BaseModel):
    config: dict[str, Any]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/system/info")
def system_info() -> dict[str, Any]:
    db_path = get_db_path()
    return {
        "storage_root": str(STORAGE_ROOT),
        "upload_dir": str(UPLOAD_DIR),
        "job_config_dir": str(JOB_CONFIG_DIR),
        "output_dir": str(OUTPUT_DIR),
        "db_path": str(db_path),
    }


@app.post("/uploads")
def upload_video(file: UploadFile = File(...)) -> dict[str, str]:
    suffix = Path(file.filename or "upload.mp4").suffix or ".mp4"
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    out_path = UPLOAD_DIR / f"{ts}{suffix}"
    with out_path.open("wb") as fp:
        shutil.copyfileobj(file.file, fp)
    return {"path": str(out_path), "filename": out_path.name}


@app.post("/sync/audio")
def sync_audio(payload: AudioSyncRequest) -> dict[str, Any]:
    try:
        analysis = estimate_video_sync_offsets(
            payload.video_paths,
            sample_rate=payload.sample_rate,
            max_shift_seconds=payload.max_shift_seconds,
        )
    except SyncError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "offsets_seconds": analysis.offsets_seconds,
        "trim_start_seconds": analysis.trim_start_seconds,
        "common_window_seconds": analysis.common_window_seconds,
    }


@app.post("/sync/preview")
def sync_preview(payload: SyncPreviewRequest) -> dict[str, Any]:
    try:
        analysis = estimate_video_sync_offsets(
            payload.video_paths,
            sample_rate=payload.sample_rate,
            max_shift_seconds=payload.max_shift_seconds,
        )
        waveforms = [
            extract_waveform_preview(
                video_path=path,
                sample_rate=payload.waveform_sample_rate,
                points=payload.waveform_points,
            )
            for path in payload.video_paths
        ]
    except SyncError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "offsets_seconds": analysis.offsets_seconds,
        "trim_start_seconds": analysis.trim_start_seconds,
        "common_window_seconds": analysis.common_window_seconds,
        "waveforms": waveforms,
    }


@app.post("/waveform")
def waveform(payload: WaveformRequest) -> dict[str, Any]:
    try:
        return extract_waveform_preview(
            payload.video_path, sample_rate=payload.sample_rate, points=payload.points
        )
    except SyncError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/validate")
def validate(payload: ValidateRequest) -> dict[str, Any]:
    try:
        cfg = load_config(payload.config_path)
        validate_config(cfg)
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"valid": True, "racers": len(cfg.racers), "obstacles": len(cfg.obstacles)}


@app.post("/analyze/config")
def analyze_config(payload: AnalyzeConfigPayload) -> dict[str, Any]:
    return analyze_config_risk(payload.config)


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


@app.post("/jobs/from-config", response_model=JobSubmitResponse)
def create_job_from_config(payload: InlineJobRequest) -> JobSubmitResponse:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    config_path = JOB_CONFIG_DIR / f"job_{ts}.json"
    config_path.write_text(json.dumps(payload.config, indent=2))
    output_path = payload.output_path or str(OUTPUT_DIR / f"job_{ts}.mp4")
    try:
        # upfront validation for immediate error feedback
        cfg = load_config(config_path)
        cfg = _scaled_config(cfg, payload.preview_scale)
        validate_config(cfg)
        job = job_manager.submit(
            config_path=str(config_path),
            output_path=output_path,
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


@app.get("/projects")
def projects_list() -> dict[str, list[dict[str, Any]]]:
    return {"projects": list_projects()}


@app.post("/projects")
def projects_create(payload: ProjectPayload) -> dict[str, Any]:
    record = create_project(payload.name, payload.config)
    return {
        "id": record.id,
        "name": record.name,
        "config": record.config,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


@app.post("/projects/import")
def projects_import(payload: ProjectImportPayload) -> dict[str, Any]:
    name = payload.name or "Imported Project"
    record = create_project(name, payload.config)
    return {
        "id": record.id,
        "name": record.name,
        "config": record.config,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


@app.get("/projects/{project_id}")
def projects_get(project_id: int) -> dict[str, Any]:
    try:
        record = get_project(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    return {
        "id": record.id,
        "name": record.name,
        "config": record.config,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


@app.get("/projects/{project_id}/export")
def projects_export(project_id: int) -> dict[str, Any]:
    try:
        record = get_project(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    return {
        "name": record.name,
        "config": record.config,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }


@app.put("/projects/{project_id}")
def projects_update(project_id: int, payload: ProjectPayload) -> dict[str, Any]:
    try:
        record = update_project(project_id, payload.name, payload.config)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    return {
        "id": record.id,
        "name": record.name,
        "config": record.config,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


@app.delete("/projects/{project_id}")
def projects_delete(project_id: int) -> dict[str, bool]:
    try:
        delete_project(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    return {"deleted": True}


@app.post("/projects/{project_id}/render", response_model=JobSubmitResponse)
def projects_render(project_id: int, payload: ProjectRenderPayload) -> JobSubmitResponse:
    try:
        record = get_project(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    config_path = JOB_CONFIG_DIR / f"project_{project_id}_{ts}.json"
    config_path.write_text(json.dumps(record.config, indent=2))
    output_path = payload.output_path or str(OUTPUT_DIR / f"project_{project_id}_{ts}.mp4")
    try:
        cfg = load_config(config_path)
        cfg = _scaled_config(cfg, payload.preview_scale)
        validate_config(cfg)
        job = job_manager.submit(
            config_path=str(config_path),
            output_path=output_path,
            preview_scale=payload.preview_scale,
        )
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JobSubmitResponse(job_id=job.job_id, state=job.state)


@app.post("/projects/{project_id}/sync")
def projects_sync(project_id: int, payload: ProjectSyncPayload) -> dict[str, Any]:
    try:
        record = get_project(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    config = record.config
    racers = config.get("racers")
    if not isinstance(racers, list) or not racers:
        raise HTTPException(status_code=400, detail="Project has no racers")
    try:
        video_paths = [str(r["video_path"]) for r in racers]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Invalid racer video_path fields") from exc
    try:
        analysis = estimate_video_sync_offsets(
            video_paths=video_paths,
            sample_rate=payload.sample_rate,
            max_shift_seconds=payload.max_shift_seconds,
        )
        updated_config = apply_analysis_to_config_obj(
            config_obj=config,
            analysis=analysis,
            apply_duration_cap=payload.apply_duration_cap,
        )
        record = update_project(project_id, record.name, updated_config)
    except SyncError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "id": record.id,
        "name": record.name,
        "sync": {
            "offsets_seconds": analysis.offsets_seconds,
            "trim_start_seconds": analysis.trim_start_seconds,
            "common_window_seconds": analysis.common_window_seconds,
        },
        "updated_at": record.updated_at,
    }


def run_dev_server() -> None:
    import uvicorn

    uvicorn.run("songracer.api:app", host="0.0.0.0", port=8080, reload=False)
