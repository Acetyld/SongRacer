from __future__ import annotations

from dataclasses import replace
from dataclasses import dataclass

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
    camera_y: np.ndarray  # [frame]
    states: np.ndarray  # [frame] 0=countdown,1=race,2=winner_hold
    winner_index: int
    winner_frame: int
    goal_y: float
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
    return p, v


def _expand_obstacle_configs(cfg: RaceConfig) -> list:
    if (
        cfg.render.obstacle_stream_repeats <= 1
        or cfg.render.obstacle_stream_spacing <= 0
        or not cfg.obstacles
    ):
        return list(cfg.obstacles)

    rng = np.random.default_rng(cfg.seed + 911)
    expanded = []
    for repeat_idx in range(cfg.render.obstacle_stream_repeats):
        y_off = repeat_idx * cfg.render.obstacle_stream_spacing
        for obs in cfg.obstacles:
            clone = replace(obs)
            clone.y = obs.y + y_off
            if clone.pivot_y is not None:
                clone.pivot_y = clone.pivot_y + y_off
            if repeat_idx > 0 and cfg.render.obstacle_stream_jitter_x > 0:
                clone.x = clone.x + float(
                    rng.uniform(
                        -cfg.render.obstacle_stream_jitter_x,
                        cfg.render.obstacle_stream_jitter_x,
                    )
                )
                if clone.pivot_x is not None:
                    clone.pivot_x = clone.pivot_x + float(
                        rng.uniform(
                            -cfg.render.obstacle_stream_jitter_x * 0.4,
                            cfg.render.obstacle_stream_jitter_x * 0.4,
                        )
                    )
            expanded.append(clone)
    return expanded


def _camera_for_frame(cfg: RaceConfig, leader_y: float) -> float:
    if not cfg.render.camera_follow:
        return 0.0
    target = leader_y - cfg.render.height * cfg.render.camera_lead_ratio
    max_cam = max(0.0, cfg.render.world_height - cfg.render.height)
    if target < 0:
        return 0.0
    if target > max_cam:
        return max_cam
    return float(target)


def simulate_race(cfg: RaceConfig) -> SimulationResult:
    fps = cfg.render.fps
    dt = 1.0 / fps
    max_race_frames = cfg.race_frames
    countdown_frames = cfg.countdown_frames
    racer_count = len(cfg.racers)
    expanded_obstacles = _expand_obstacle_configs(cfg)
    obstacles = build_obstacles(expanded_obstacles)
    goal_y = cfg.render.world_height - cfg.render.goal_margin

    positions_race: list[np.ndarray] = []
    leaders_race: list[int] = []
    camera_race: list[float] = []
    states_race: list[int] = []

    pos = [Vec2(r.x, r.y) for r in cfg.racers]
    vel = [Vec2(0.0, 0.0) for _ in cfg.racers]
    prev_leader: int | None = None
    best_y = [r.y for r in cfg.racers]
    stuck_frames = [0 for _ in cfg.racers]
    rng = np.random.default_rng(cfg.seed + 101)

    substeps = max(1, cfg.physics.substeps)
    sub_dt = dt / substeps

    winner_idx = -1
    winner_race_frame = -1
    camera_prev = 0.0

    for frame in range(max_race_frames):
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
                    cfg.physics.restitution,
                )

                for obstacle in obstacles:
                    p, v = obstacle.resolve(p, v, racer.radius, t, cfg.physics)

                pos[i] = p
                vel[i] = v

        frame_positions = np.zeros((racer_count, 2), dtype=np.float32)
        for i, p in enumerate(pos):
            frame_positions[i, 0] = p.x
            frame_positions[i, 1] = p.y
            if p.y > (best_y[i] + 1.0):
                best_y[i] = p.y
                stuck_frames[i] = 0
            else:
                if abs(vel[i].y) < cfg.physics.stuck_speed_threshold:
                    stuck_frames[i] += 1
                else:
                    stuck_frames[i] = max(0, stuck_frames[i] - 1)
            if (
                cfg.physics.stuck_window_frames > 0
                and stuck_frames[i] >= cfg.physics.stuck_window_frames
                and p.y < (goal_y - cfg.racers[i].radius)
            ):
                vel[i] = Vec2(
                    vel[i].x + float(rng.uniform(-cfg.physics.stuck_nudge_x, cfg.physics.stuck_nudge_x)),
                    vel[i].y + cfg.physics.stuck_boost_y,
                )
                stuck_frames[i] = 0

        ys = frame_positions[:, 1]
        leader = _leader_for_y(ys, prev_leader, cfg.physics.leader_hysteresis_px)
        positions_race.append(frame_positions)
        leaders_race.append(leader)
        camera_now = _camera_for_frame(cfg, float(ys[leader]))
        if camera_now < camera_prev:
            camera_now = camera_prev
        camera_prev = camera_now
        camera_race.append(camera_now)
        states_race.append(1)
        prev_leader = leader

        if winner_race_frame < 0:
            reached = np.where(ys >= goal_y)[0]
            if reached.size > 0:
                winner_idx = int(reached[np.argmax(ys[reached])])
                winner_race_frame = frame
                if cfg.render.auto_end_on_winner:
                    hold_frames = int(round(cfg.render.winner_hold_seconds * fps))
                    for _ in range(hold_frames):
                        positions_race.append(frame_positions.copy())
                        leaders_race.append(winner_idx)
                        camera_race.append(camera_race[-1])
                        states_race.append(2)
                    break

    race_frames_used = len(positions_race)
    total_frames = countdown_frames + race_frames_used
    positions_total = np.zeros((total_frames, racer_count, 2), dtype=np.float32)
    leaders_total = np.zeros((total_frames,), dtype=np.int32)
    active_total = np.zeros((total_frames,), dtype=np.int32)
    camera_total = np.zeros((total_frames,), dtype=np.float32)
    states_total = np.zeros((total_frames,), dtype=np.int32)
    playheads = np.zeros((total_frames, racer_count), dtype=np.float32)

    start_positions = np.array([[r.x, r.y] for r in cfg.racers], dtype=np.float32)
    start_y = start_positions[:, 1]
    init_leader = _leader_for_y(start_y, None, 0.0)
    for f in range(total_frames):
        if f < countdown_frames:
            positions_total[f] = start_positions
            leaders_total[f] = init_leader
            active_total[f] = -1 if cfg.audio.countdown_silence else init_leader
            camera_total[f] = 0.0
            states_total[f] = 0
        else:
            race_idx = f - countdown_frames
            positions_total[f] = positions_race[race_idx]
            leaders_total[f] = leaders_race[race_idx]
            active_total[f] = leaders_race[race_idx]
            camera_total[f] = camera_race[race_idx]
            states_total[f] = states_race[race_idx]

    dt = 1.0 / fps
    current = np.zeros((racer_count,), dtype=np.float32)
    for f in range(total_frames):
        playheads[f] = current
        active = active_total[f]
        if active >= 0:
            current[active] += dt

    winner_total_frame = countdown_frames + winner_race_frame if winner_race_frame >= 0 else -1

    return SimulationResult(
        positions=positions_total,
        leaders=leaders_total,
        active_leaders=active_total,
        playheads=playheads,
        camera_y=camera_total,
        states=states_total,
        winner_index=winner_idx,
        winner_frame=winner_total_frame,
        goal_y=goal_y,
        obstacles=obstacles,
    )


def timeline_hash(sim: SimulationResult) -> str:
    import hashlib

    digest = hashlib.sha256()
    digest.update(sim.positions.tobytes())
    digest.update(sim.leaders.tobytes())
    return digest.hexdigest()
