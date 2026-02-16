from __future__ import annotations

from contextlib import asynccontextmanager
from collections import OrderedDict
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import threading
from typing import Any

from fastapi import File
from fastapi import FastAPI, HTTPException
from fastapi import UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .analyze import analyze_config_risk
from .cli import _scaled_config
from .config import (
    ConfigError,
    ObstacleConfig,
    PhysicsConfig,
    RaceConfig,
    RacerConfig,
    RenderConfig,
    load_config,
    load_config_obj,
    validate_config,
)
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
from .simulation import simulate_race
from .storage import resolve_writable_dir
from .templates import (
    generate_obstacle_stream,
    obstacle_templates_payload,
    obstacle_type_catalog,
)
from .sync import (
    SyncError,
    apply_analysis_to_config_obj,
    estimate_video_sync_offsets,
    extract_waveform_preview,
)


job_manager = JobManager(max_workers=2)
_preview_cache_lock = threading.Lock()
_preview_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
_PREVIEW_CACHE_MAX_ITEMS = 8


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


class ValidateConfigPayload(BaseModel):
    config: dict[str, Any]


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


class PreviewRacerPayload(BaseModel):
    name: str = Field("Racer")
    x: float
    y: float
    radius: float = Field(80.0, gt=1.0)


class PreviewRenderPayload(BaseModel):
    width: int = Field(1080, ge=128, le=2160)
    height: int = Field(1920, ge=128, le=3840)
    world_height: int = Field(6200, ge=256, le=20000)
    fps: int = Field(30, ge=10, le=120)
    duration_seconds: float = Field(12.0, gt=0.2, le=60.0)
    countdown_seconds: float = Field(0.0, ge=0.0, le=10.0)
    goal_margin: float = Field(130.0, ge=0.0, le=4000.0)
    camera_follow: bool = True
    camera_lead_ratio: float = Field(0.35, ge=0.0, le=1.0)
    auto_end_on_winner: bool = True
    winner_hold_seconds: float = Field(2.0, ge=0.0, le=10.0)
    obstacle_stream_spacing: float = Field(0.0, ge=0.0, le=10000.0)
    obstacle_stream_jitter_x: float = Field(0.0, ge=0.0, le=2000.0)
    obstacle_stream_repeats: int = Field(1, ge=0, le=20)


class PreviewPhysicsPayload(BaseModel):
    gravity: float = Field(1800.0, ge=0.0, le=8000.0)
    damping: float = Field(0.997, gt=0.0, le=1.0)
    restitution: float = Field(0.6, ge=0.0, le=1.0)
    max_speed: float = Field(1800.0, gt=10.0, le=12000.0)
    substeps: int = Field(2, ge=1, le=8)
    leader_hysteresis_px: float = Field(3.0, ge=0.0, le=100.0)
    stuck_window_frames: int = Field(45, ge=0, le=500)
    stuck_speed_threshold: float = Field(46.0, ge=0.0, le=1200.0)
    stuck_boost_y: float = Field(420.0, ge=0.0, le=6000.0)
    stuck_nudge_x: float = Field(110.0, ge=0.0, le=2000.0)


class PreviewSimRequest(BaseModel):
    seed: int = 13
    render: PreviewRenderPayload = Field(default_factory=PreviewRenderPayload)
    physics: PreviewPhysicsPayload = Field(default_factory=PreviewPhysicsPayload)
    racers: list[PreviewRacerPayload]
    obstacles: list[dict[str, Any]] = Field(default_factory=list)
    sample_fps: int = Field(15, ge=4, le=60)
    max_frames: int = Field(300, ge=30, le=1500)


class TemplateGenerateRequest(BaseModel):
    count: int = Field(8, ge=1, le=200)
    start_y: float = Field(900.0, ge=0.0, le=100000.0)
    spacing: float = Field(260.0, ge=40.0, le=4000.0)
    width: float = Field(1080.0, ge=200.0, le=4000.0)
    seed: int = Field(13, ge=0, le=2_000_000_000)


def _build_preview_cfg(payload: PreviewSimRequest) -> RaceConfig:
    render = RenderConfig(
        width=payload.render.width,
        height=payload.render.height,
        world_height=max(payload.render.height, payload.render.world_height),
        fps=payload.render.fps,
        duration_seconds=payload.render.duration_seconds,
        countdown_seconds=payload.render.countdown_seconds,
        goal_margin=payload.render.goal_margin,
        camera_follow=payload.render.camera_follow,
        camera_lead_ratio=payload.render.camera_lead_ratio,
        auto_end_on_winner=payload.render.auto_end_on_winner,
        winner_hold_seconds=payload.render.winner_hold_seconds,
        obstacle_stream_spacing=payload.render.obstacle_stream_spacing,
        obstacle_stream_jitter_x=payload.render.obstacle_stream_jitter_x,
        obstacle_stream_repeats=payload.render.obstacle_stream_repeats,
    )
    physics = PhysicsConfig(
        gravity=payload.physics.gravity,
        damping=payload.physics.damping,
        restitution=payload.physics.restitution,
        max_speed=payload.physics.max_speed,
        substeps=payload.physics.substeps,
        leader_hysteresis_px=payload.physics.leader_hysteresis_px,
        stuck_window_frames=payload.physics.stuck_window_frames,
        stuck_speed_threshold=payload.physics.stuck_speed_threshold,
        stuck_boost_y=payload.physics.stuck_boost_y,
        stuck_nudge_x=payload.physics.stuck_nudge_x,
    )
    racers = [
        RacerConfig(
            name=r.name,
            video_path="__preview__.mp4",
            x=r.x,
            y=r.y,
            radius=r.radius,
        )
        for r in payload.racers
    ]
    obstacles: list[ObstacleConfig] = []
    allowed_types = {
        "rect",
        "circle",
        "ring_gap",
        "moving_rect",
        "pendulum",
        "one_way_gate",
        "spinner",
    }
    for idx, obs in enumerate(payload.obstacles):
        if not isinstance(obs, dict):
            raise HTTPException(status_code=400, detail=f"Invalid obstacle at index {idx}")
        obs_type = str(obs.get("type", ""))
        if obs_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid obstacle type '{obs_type}' at index {idx}",
            )
        try:
            obstacles.append(ObstacleConfig(**obs))
        except TypeError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid obstacle at index {idx}: {exc}"
            ) from exc
    return RaceConfig(
        seed=payload.seed,
        render=render,
        physics=physics,
        racers=racers,
        obstacles=obstacles,
    )


def _preview_cache_key(payload: PreviewSimRequest) -> str:
    body = payload.model_dump(mode="json")
    return json.dumps(body, sort_keys=True, separators=(",", ":"))


def _preview_cache_get(key: str) -> dict[str, Any] | None:
    with _preview_cache_lock:
        cached = _preview_cache.get(key)
        if cached is None:
            return None
        _preview_cache.move_to_end(key)
        return dict(cached)


def _preview_cache_set(key: str, value: dict[str, Any]) -> None:
    with _preview_cache_lock:
        _preview_cache[key] = dict(value)
        _preview_cache.move_to_end(key)
        while len(_preview_cache) > _PREVIEW_CACHE_MAX_ITEMS:
            _preview_cache.popitem(last=False)


def _preview_cache_info() -> dict[str, int]:
    with _preview_cache_lock:
        return {"size": len(_preview_cache), "max_size": _PREVIEW_CACHE_MAX_ITEMS}


def _preview_cache_clear() -> int:
    with _preview_cache_lock:
        size = len(_preview_cache)
        _preview_cache.clear()
        return size


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


@app.get("/templates/obstacles")
def templates_obstacles() -> dict[str, Any]:
    return obstacle_templates_payload()


@app.get("/templates/obstacle-types")
def templates_obstacle_types() -> dict[str, Any]:
    return {"types": obstacle_type_catalog()}


@app.post("/templates/obstacles/generate")
def templates_obstacles_generate(payload: TemplateGenerateRequest) -> dict[str, Any]:
    obstacles = generate_obstacle_stream(
        count=payload.count,
        start_y=payload.start_y,
        spacing=payload.spacing,
        width=payload.width,
        seed=payload.seed,
    )
    return {"seed": payload.seed, "count": len(obstacles), "obstacles": obstacles}


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


@app.post("/validate/config")
def validate_config_inline(payload: ValidateConfigPayload) -> dict[str, Any]:
    try:
        cfg = load_config_obj(payload.config, base_dir=JOB_CONFIG_DIR)
        validate_config(cfg)
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"valid": True, "racers": len(cfg.racers), "obstacles": len(cfg.obstacles)}


@app.post("/analyze/config")
def analyze_config(payload: AnalyzeConfigPayload) -> dict[str, Any]:
    return analyze_config_risk(payload.config)


@app.post("/preview/simulate")
def preview_simulate(payload: PreviewSimRequest) -> dict[str, Any]:
    if not payload.racers:
        raise HTTPException(status_code=400, detail="At least one racer is required")
    cache_key = _preview_cache_key(payload)
    cached = _preview_cache_get(cache_key)
    if cached is not None:
        cached["cache_hit"] = True
        return cached
    cfg = _build_preview_cfg(payload)
    sim = simulate_race(cfg)
    step = max(1, int(round(cfg.render.fps / max(1, payload.sample_fps))))
    full_frame_ids = list(range(0, sim.positions.shape[0], step))
    frame_ids = full_frame_ids
    if len(frame_ids) > payload.max_frames:
        frame_ids = frame_ids[: payload.max_frames]
    truncated = len(full_frame_ids) > len(frame_ids)

    positions: list[list[list[float]]] = []
    leaders: list[int] = []
    camera_y: list[float] = []
    states: list[int] = []
    obstacle_visuals: list[list[dict[str, Any]]] = []
    for frame in frame_ids:
        positions.append(sim.positions[frame].tolist())
        leaders.append(int(sim.leaders[frame]))
        camera_y.append(float(sim.camera_y[frame]))
        states.append(int(sim.states[frame]))
        if frame < cfg.countdown_frames:
            sim_time = 0.0
        else:
            sim_time = float((frame - cfg.countdown_frames) / cfg.render.fps)
        obstacle_visuals.append([obs.visual(sim_time) for obs in sim.obstacles])

    effective_sample_fps = cfg.render.fps / step
    result = {
        "world": {
            "width": cfg.render.width,
            "height": cfg.render.height,
            "world_height": cfg.render.world_height,
        },
        "fps": cfg.render.fps,
        "sample_fps": effective_sample_fps,
        "sample_step_frames": step,
        "sample_interval_seconds": step / cfg.render.fps,
        "frame_indices": frame_ids,
        "total_sample_frames": len(full_frame_ids),
        "truncated": truncated,
        "countdown_frames": cfg.countdown_frames,
        "winner_index": int(sim.winner_index),
        "winner_frame": int(sim.winner_frame),
        "goal_y": float(sim.goal_y),
        "positions": positions,
        "leaders": leaders,
        "camera_y": camera_y,
        "states": states,
        "obstacle_visuals": obstacle_visuals,
        "cache_hit": False,
    }
    _preview_cache_set(cache_key, result)
    return result


@app.get("/preview/cache")
def preview_cache_info() -> dict[str, int]:
    return _preview_cache_info()


@app.post("/preview/cache/clear")
def preview_cache_clear() -> dict[str, int]:
    cleared = _preview_cache_clear()
    info = _preview_cache_info()
    return {"cleared": cleared, **info}


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
    output_path = payload.output_path or str(OUTPUT_DIR / f"job_{ts}.mp4")
    try:
        # upfront validation for immediate error feedback before writing config artifact
        cfg = load_config_obj(payload.config, base_dir=JOB_CONFIG_DIR)
        cfg = _scaled_config(cfg, payload.preview_scale)
        validate_config(cfg)
        config_path.write_text(json.dumps(payload.config, indent=2))
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
def projects_list(include_analysis: bool = False) -> dict[str, list[dict[str, Any]]]:
    projects = list_projects(include_config=include_analysis)
    if include_analysis:
        for item in projects:
            cfg = item.pop("config", {})
            if isinstance(cfg, dict):
                risk = analyze_config_risk(cfg)
                item["risk_score"] = risk["risk_score"]
                item["warning_count"] = risk["warning_count"]
            else:
                item["risk_score"] = 0
                item["warning_count"] = 0
    return {"projects": projects}


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


@app.get("/projects/{project_id}/analyze")
def projects_analyze(project_id: int) -> dict[str, Any]:
    try:
        record = get_project(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    if not isinstance(record.config, dict):
        raise HTTPException(status_code=400, detail="Project config is not an object")
    risk = analyze_config_risk(record.config)
    return {
        "id": record.id,
        "name": record.name,
        "risk_score": risk["risk_score"],
        "warning_count": risk["warning_count"],
        "warnings": risk["warnings"],
        "updated_at": record.updated_at,
    }


def run_dev_server() -> None:
    import uvicorn

    uvicorn.run("songracer.api:app", host="0.0.0.0", port=8080, reload=False)
