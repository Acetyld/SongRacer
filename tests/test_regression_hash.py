from __future__ import annotations

from songracer.config import ObstacleConfig, PhysicsConfig, RaceConfig, RacerConfig, RenderConfig
from songracer.simulation import simulate_race, timeline_hash


def test_regression_timeline_hash_stable() -> None:
    cfg = RaceConfig(
        seed=123,
        render=RenderConfig(
            width=320,
            height=568,
            fps=30,
            duration_seconds=2.0,
            countdown_seconds=0.0,
        ),
        physics=PhysicsConfig(
            gravity=1500.0,
            damping=0.996,
            restitution=0.55,
            max_speed=1600.0,
            substeps=2,
            leader_hysteresis_px=2.0,
        ),
        racers=[
            RacerConfig(name="A", video_path="/tmp/a.mp4", x=100, y=80, radius=22),
            RacerConfig(name="B", video_path="/tmp/b.mp4", x=180, y=82, radius=22),
            RacerConfig(name="C", video_path="/tmp/c.mp4", x=260, y=78, radius=22),
        ],
        obstacles=[
            ObstacleConfig(type="rect", x=120, y=240, width=140, height=18, angle_deg=-20),
            ObstacleConfig(
                type="spinner",
                x=220,
                y=330,
                length=140,
                thickness=14,
                spin_speed_deg=150,
            ),
            ObstacleConfig(
                type="ring_gap",
                x=160,
                y=430,
                radius=70,
                thickness=18,
                gap_size_deg=70,
                rotation_speed_deg=90,
            ),
        ],
    )

    sim = simulate_race(cfg)
    assert timeline_hash(sim) == "e7595cf84971d7e4971d6779e613892f6010ca5d5f5400b6e0bddb1a910a0f5c"
