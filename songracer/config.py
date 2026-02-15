from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any


Color = str


@dataclass(slots=True)
class BackgroundConfig:
    mode: str = "sky"
    solid_color: Color = "#6ec6ff"
    gradient_top: Color = "#5EC8FF"
    gradient_bottom: Color = "#8AD8FF"
    cloud_color: Color = "#f4f7fb"
    cloud_count: int = 10
    image_path: str | None = None
    image_opacity: float = 0.5


@dataclass(slots=True)
class LabelStyleConfig:
    color: Color = "#FFFFFF"
    stroke_color: Color = "#1C2230"
    stroke_width: int = 3
    offset_y: int = 22


@dataclass(slots=True)
class TopCircleConfig:
    diameter: int = 260
    y: int = 210
    border_color: Color = "#111111"
    border_width: int = 6


@dataclass(slots=True)
class PhysicsConfig:
    gravity: float = 1800.0
    damping: float = 0.997
    restitution: float = 0.6
    max_speed: float = 1800.0
    substeps: int = 2
    leader_hysteresis_px: float = 3.0


@dataclass(slots=True)
class RenderConfig:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    duration_seconds: float = 30.0
    countdown_seconds: float = 3.0
    preview_scale: float = 1.0


@dataclass(slots=True)
class AudioConfig:
    sample_rate: int = 48000
    channels: int = 2
    switch_crossfade_ms: float = 12.0
    countdown_silence: bool = True


@dataclass(slots=True)
class RacerConfig:
    name: str
    video_path: str
    x: float
    y: float
    radius: float
    border_color: Color = "#101318"
    border_width: int = 4


@dataclass(slots=True)
class ObstacleConfig:
    type: str
    x: float
    y: float
    width: float | None = None
    height: float | None = None
    radius: float | None = None
    angle_deg: float = 0.0
    thickness: float = 16.0
    rotation_speed_deg: float = 0.0
    gap_center_deg: float = 270.0
    gap_size_deg: float = 55.0
    amplitude: float = 80.0
    frequency_hz: float = 0.2
    axis: str = "x"
    length: float = 220.0
    pivot_x: float | None = None
    pivot_y: float | None = None
    one_way: str = "down"
    spin_speed_deg: float = 120.0
    fill_color: Color = "#0d1220"
    stroke_color: Color = "#000000"
    opacity: float = 0.95


@dataclass(slots=True)
class RaceConfig:
    seed: int = 7
    render: RenderConfig = field(default_factory=RenderConfig)
    physics: PhysicsConfig = field(default_factory=PhysicsConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    background: BackgroundConfig = field(default_factory=BackgroundConfig)
    label_style: LabelStyleConfig = field(default_factory=LabelStyleConfig)
    top_circle: TopCircleConfig = field(default_factory=TopCircleConfig)
    racers: list[RacerConfig] = field(default_factory=list)
    obstacles: list[ObstacleConfig] = field(default_factory=list)

    @property
    def total_seconds(self) -> float:
        return self.render.countdown_seconds + self.render.duration_seconds

    @property
    def total_frames(self) -> int:
        return int(round(self.total_seconds * self.render.fps))

    @property
    def race_frames(self) -> int:
        return int(round(self.render.duration_seconds * self.render.fps))

    @property
    def countdown_frames(self) -> int:
        return int(round(self.render.countdown_seconds * self.render.fps))


class ConfigError(ValueError):
    pass


def _load_obj(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Config JSON parse error in {path}: {exc}") from exc


def _merge_dataclass(default_obj: Any, incoming: dict[str, Any]) -> Any:
    for k, v in incoming.items():
        if hasattr(default_obj, k):
            setattr(default_obj, k, v)
    return default_obj


def _require_positive(value: float, name: str) -> None:
    if value <= 0:
        raise ConfigError(f"{name} must be > 0, got {value}")


def load_config(path: str | Path) -> RaceConfig:
    config_path = Path(path).expanduser().resolve()
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    obj = _load_obj(config_path)
    cfg = RaceConfig()
    cfg.seed = int(obj.get("seed", cfg.seed))

    cfg.render = _merge_dataclass(cfg.render, obj.get("render", {}))
    cfg.physics = _merge_dataclass(cfg.physics, obj.get("physics", {}))
    cfg.audio = _merge_dataclass(cfg.audio, obj.get("audio", {}))
    cfg.background = _merge_dataclass(cfg.background, obj.get("background", {}))
    if cfg.background.image_path:
        image_path = Path(cfg.background.image_path)
        if not image_path.is_absolute():
            image_path = (config_path.parent / image_path).resolve()
        cfg.background.image_path = str(image_path)
    cfg.label_style = _merge_dataclass(cfg.label_style, obj.get("label_style", {}))
    cfg.top_circle = _merge_dataclass(cfg.top_circle, obj.get("top_circle", {}))

    cfg.racers = []
    for idx, racer in enumerate(obj.get("racers", [])):
        try:
            r = RacerConfig(**racer)
        except TypeError as exc:
            raise ConfigError(f"Invalid racer at index {idx}: {exc}") from exc
        video_path = Path(r.video_path)
        if not video_path.is_absolute():
            video_path = (config_path.parent / video_path).resolve()
        r.video_path = str(video_path)
        cfg.racers.append(r)

    cfg.obstacles = []
    for idx, obstacle in enumerate(obj.get("obstacles", [])):
        try:
            o = ObstacleConfig(**obstacle)
        except TypeError as exc:
            raise ConfigError(f"Invalid obstacle at index {idx}: {exc}") from exc
        cfg.obstacles.append(o)

    validate_config(cfg)
    return cfg


def validate_config(cfg: RaceConfig) -> None:
    _require_positive(cfg.render.width, "render.width")
    _require_positive(cfg.render.height, "render.height")
    _require_positive(cfg.render.fps, "render.fps")
    _require_positive(cfg.render.duration_seconds, "render.duration_seconds")
    if cfg.render.countdown_seconds < 0:
        raise ConfigError("render.countdown_seconds must be >= 0")
    if not 0 < cfg.render.preview_scale <= 1.0:
        raise ConfigError("render.preview_scale must be in (0, 1]")
    _require_positive(cfg.audio.sample_rate, "audio.sample_rate")
    if cfg.audio.channels not in (1, 2):
        raise ConfigError("audio.channels must be 1 or 2")
    if cfg.audio.switch_crossfade_ms < 0:
        raise ConfigError("audio.switch_crossfade_ms must be >= 0")
    _require_positive(cfg.physics.substeps, "physics.substeps")
    if cfg.background.mode not in {"sky", "solid", "gradient", "image"}:
        raise ConfigError("background.mode must be one of: sky, solid, gradient, image")
    if not 0 <= cfg.background.image_opacity <= 1:
        raise ConfigError("background.image_opacity must be in [0,1]")
    if cfg.background.mode == "image":
        if not cfg.background.image_path:
            raise ConfigError("background.image_path is required when background.mode='image'")
        if not Path(cfg.background.image_path).exists():
            raise ConfigError(
                f"background.image_path does not exist: {cfg.background.image_path}"
            )

    if not cfg.racers:
        raise ConfigError("At least one racer is required")
    for idx, racer in enumerate(cfg.racers):
        if not racer.name:
            raise ConfigError(f"Racer #{idx} name is required")
        if racer.radius <= 0:
            raise ConfigError(f"Racer #{idx} radius must be > 0")
        if not Path(racer.video_path).exists():
            raise ConfigError(f"Racer #{idx} video does not exist: {racer.video_path}")

    allowed_obstacles = {
        "rect",
        "circle",
        "ring_gap",
        "moving_rect",
        "pendulum",
        "one_way_gate",
        "spinner",
    }
    for idx, obs in enumerate(cfg.obstacles):
        if obs.type not in allowed_obstacles:
            raise ConfigError(
                f"Obstacle #{idx} has invalid type '{obs.type}'. "
                f"Allowed: {sorted(allowed_obstacles)}"
            )
