from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from .config import RaceConfig, load_config, validate_config
from .pipeline import render_race


def _scaled_config(cfg: RaceConfig, scale: float) -> RaceConfig:
    if scale >= 0.999:
        return cfg
    out = copy.deepcopy(cfg)
    out.render.width = max(16, int(round(cfg.render.width * scale)))
    out.render.height = max(16, int(round(cfg.render.height * scale)))
    out.top_circle.diameter = max(20, int(round(cfg.top_circle.diameter * scale)))
    out.top_circle.y = int(round(cfg.top_circle.y * scale))
    out.label_style.offset_y = max(2, int(round(cfg.label_style.offset_y * scale)))

    for racer in out.racers:
        racer.x *= scale
        racer.y *= scale
        racer.radius = max(6.0, racer.radius * scale)
        racer.border_width = max(1, int(round(racer.border_width * scale)))
    for obs in out.obstacles:
        obs.x *= scale
        obs.y *= scale
        if obs.width is not None:
            obs.width *= scale
        if obs.height is not None:
            obs.height *= scale
        if obs.radius is not None:
            obs.radius *= scale
        obs.thickness = max(2.0, obs.thickness * scale)
        obs.amplitude *= scale
        obs.length *= scale
        if obs.pivot_x is not None:
            obs.pivot_x *= scale
        if obs.pivot_y is not None:
            obs.pivot_y *= scale
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="songracer", description="Generate autonomous singer race MP4s."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    render_p = sub.add_parser("render", help="Render MP4 race from config")
    render_p.add_argument("--config", required=True, help="Path to JSON config")
    render_p.add_argument("--output", required=True, help="Output MP4 path")
    render_p.add_argument(
        "--preview-scale",
        type=float,
        default=1.0,
        help="Scale all coordinates and resolution (0,1].",
    )

    val_p = sub.add_parser("validate", help="Validate config file")
    val_p.add_argument("--config", required=True, help="Path to JSON config")
    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "validate":
        cfg = load_config(args.config)
        validate_config(cfg)
        print("Config valid.")
        return

    if args.cmd == "render":
        cfg = load_config(args.config)
        if not 0 < args.preview_scale <= 1.0:
            raise SystemExit("--preview-scale must be in (0, 1]")
        cfg = _scaled_config(cfg, args.preview_scale)
        validate_config(cfg)
        stats = render_race(cfg, args.output)
        print(
            json.dumps(
                {
                    "output_path": stats.output_path,
                    "total_frames": stats.total_frames,
                    "leaders_switches": stats.leaders_switches,
                    "timeline_hash": stats.timeline_hash,
                },
                indent=2,
            )
        )
        return

    raise SystemExit(f"Unknown command: {args.cmd}")
