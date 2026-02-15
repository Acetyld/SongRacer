from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .config import RaceConfig
from .math2d import Vec2
from .obstacles import Obstacle, build_obstacles


@dataclass(slots=True)
class SimulationResult:
    positions: np.ndarray  # [frame, racer, xy]
    leaders: np.ndarray  # [frame]
    active_leaders: np.ndarray  # [frame], -1 indicates silence
    playheads: np.ndarray  # [frame, racer]
    obstacles: list[Obstacle]


def _leader_for_y(y_values: np.ndarray, prev_leader: int | None, hysteresis: float) -> int:
    candidate = int(np.argmax(y_values))
    if prev_leader is None:
        return candidate
    if candidate == prev_leader:
        return candidate
    if (y_values[candidate] - y_values[prev_leader]) < hysteresis:
        return prev_leader
    return candidate


def _enforce_world_bounds(
    position: Vec2,
    velocity: Vec2,
    radius: float,
    width: int,
    height: int,
    restitution: float,
) -> tuple[Vec2, Vec2]:
    p = position
    v = velocity
    if p.x < radius:
        p = Vec2(radius, p.y)
        if v.x < 0:
            v = Vec2(-v.x * restitution, v.y)
    elif p.x > width - radius:
        p = Vec2(width - radius, p.y)
        if v.x > 0:
            v = Vec2(-v.x * restitution, v.y)

    if p.y < radius:
        p = Vec2(p.x, radius)
        if v.y < 0:
            v = Vec2(v.x, -v.y * restitution)
    elif p.y > height - radius:
        p = Vec2(p.x, height - radius)
        if v.y > 0:
            v = Vec2(v.x, -v.y * restitution)
    return p, v


def simulate_race(cfg: RaceConfig) -> SimulationResult:
    fps = cfg.render.fps
    dt = 1.0 / fps
    race_frames = cfg.race_frames
    total_frames = cfg.total_frames
    countdown_frames = cfg.countdown_frames
    racer_count = len(cfg.racers)
    obstacles = build_obstacles(cfg.obstacles)

    positions_race = np.zeros((race_frames, racer_count, 2), dtype=np.float32)
    leaders_race = np.zeros((race_frames,), dtype=np.int32)

    pos = [Vec2(r.x, r.y) for r in cfg.racers]
    vel = [Vec2(0.0, 0.0) for _ in cfg.racers]
    prev_leader: int | None = None

    substeps = max(1, cfg.physics.substeps)
    sub_dt = dt / substeps

    for frame in range(race_frames):
        t_frame = frame * dt
        for sub in range(substeps):
            t = t_frame + sub * sub_dt
            for i, racer in enumerate(cfg.racers):
                v = vel[i]
                p = pos[i]
                v = Vec2(v.x, v.y + cfg.physics.gravity * sub_dt)
                v = Vec2(v.x * cfg.physics.damping, v.y * cfg.physics.damping)
                speed = v.length()
                if speed > cfg.physics.max_speed:
                    scale = cfg.physics.max_speed / max(1e-6, speed)
                    v = v * scale
                p = p + v * sub_dt

                p, v = _enforce_world_bounds(
                    p,
                    v,
                    racer.radius,
                    cfg.render.width,
                    cfg.render.height,
                    cfg.physics.restitution,
                )

                for obstacle in obstacles:
                    p, v = obstacle.resolve(p, v, racer.radius, t, cfg.physics)

                pos[i] = p
                vel[i] = v

        for i, p in enumerate(pos):
            positions_race[frame, i, 0] = p.x
            positions_race[frame, i, 1] = p.y

        ys = positions_race[frame, :, 1]
        leader = _leader_for_y(ys, prev_leader, cfg.physics.leader_hysteresis_px)
        leaders_race[frame] = leader
        prev_leader = leader

    positions_total = np.zeros((total_frames, racer_count, 2), dtype=np.float32)
    leaders_total = np.zeros((total_frames,), dtype=np.int32)
    active_total = np.zeros((total_frames,), dtype=np.int32)
    playheads = np.zeros((total_frames, racer_count), dtype=np.float32)

    start_positions = np.array([[r.x, r.y] for r in cfg.racers], dtype=np.float32)
    start_y = start_positions[:, 1]
    init_leader = _leader_for_y(start_y, None, 0.0)
    for f in range(total_frames):
        if f < countdown_frames:
            positions_total[f] = start_positions
            leaders_total[f] = init_leader
            active_total[f] = -1 if cfg.audio.countdown_silence else init_leader
        else:
            race_idx = min(race_frames - 1, f - countdown_frames)
            positions_total[f] = positions_race[race_idx]
            leaders_total[f] = leaders_race[race_idx]
            active_total[f] = leaders_race[race_idx]

    dt = 1.0 / fps
    current = np.zeros((racer_count,), dtype=np.float32)
    for f in range(total_frames):
        playheads[f] = current
        active = active_total[f]
        if active >= 0:
            current[active] += dt

    return SimulationResult(
        positions=positions_total,
        leaders=leaders_total,
        active_leaders=active_total,
        playheads=playheads,
        obstacles=obstacles,
    )


def timeline_hash(sim: SimulationResult) -> str:
    import hashlib

    digest = hashlib.sha256()
    digest.update(sim.positions.tobytes())
    digest.update(sim.leaders.tobytes())
    return digest.hexdigest()
