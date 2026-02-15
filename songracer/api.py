from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .cli import _scaled_config
from .config import ConfigError, load_config, validate_config
from .pipeline import render_race


app = FastAPI(title="SongRacer API", version="0.1.0")


class ValidateRequest(BaseModel):
    config_path: str = Field(..., description="Path to SongRacer JSON config")


class RenderRequest(BaseModel):
    config_path: str = Field(..., description="Path to SongRacer JSON config")
    output_path: str = Field(..., description="Path for output MP4")
    preview_scale: float = Field(1.0, ge=0.01, le=1.0)


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


def run_dev_server() -> None:
    import uvicorn

    uvicorn.run("songracer.api:app", host="0.0.0.0", port=8080, reload=False)
