from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class RiskWarning:
    level: str
    code: str
    message: str
    obstacle_index: int | None = None
    obstacle_indices: list[int] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "level": self.level,
            "code": self.code,
            "message": self.message,
        }
        if self.obstacle_index is not None:
            out["obstacle_index"] = self.obstacle_index
        if self.obstacle_indices is not None:
            out["obstacle_indices"] = list(self.obstacle_indices)
        return out


def analyze_config_risk(config_obj: dict[str, Any]) -> dict[str, Any]:
    render = config_obj.get("render", {}) if isinstance(config_obj, dict) else {}
    width = float(render.get("width", 1080))
    height = float(render.get("height", 1920))
    obstacles = config_obj.get("obstacles", []) if isinstance(config_obj, dict) else []
    if not isinstance(obstacles, list):
        obstacles = []

    warnings: list[RiskWarning] = []
    blocker_rows: list[tuple[int, float, float]] = []
    min_gap = max(110.0, height * 0.075)

    for idx, obs in enumerate(obstacles):
        if not isinstance(obs, dict):
            continue
        t = str(obs.get("type", ""))
        x = float(obs.get("x", width * 0.5))
        y = float(obs.get("y", 0.0))
        width_obs = float(obs.get("width", 0.0))
        length = float(obs.get("length", 0.0))
        radius = float(obs.get("radius", 0.0))

        if t in {"rect", "moving_rect", "one_way_gate"}:
            coverage = width_obs / max(1.0, width)
            blocker_rows.append((idx, y, width_obs))
            if coverage >= 0.78:
                warnings.append(
                    RiskWarning(
                        "high",
                        "blocker_too_wide",
                        f"Obstacle #{idx} ({t}) covers {coverage:.0%} of width; may trap racers.",
                        obstacle_index=idx,
                    )
                )
        elif t == "spinner":
            coverage = length / max(1.0, width)
            blocker_rows.append((idx, y, length))
            if coverage >= 0.72:
                warnings.append(
                    RiskWarning(
                        "medium",
                        "spinner_too_long",
                        f"Spinner #{idx} spans {coverage:.0%} of width; consider shortening.",
                        obstacle_index=idx,
                    )
                )
        elif t == "ring_gap":
            gap_size = float(obs.get("gap_size_deg", 55.0))
            if gap_size < 40:
                warnings.append(
                    RiskWarning(
                        "high",
                        "ring_gap_too_small",
                        f"Ring #{idx} gap_size_deg={gap_size} is very small and can deadlock.",
                        obstacle_index=idx,
                    )
                )
        elif t == "circle":
            if radius > width * 0.28:
                warnings.append(
                    RiskWarning(
                        "medium",
                        "circle_too_large",
                        f"Circle #{idx} radius={radius:.1f} is large relative to width.",
                        obstacle_index=idx,
                    )
                )

        if x < width * 0.06 or x > width * 0.94:
            warnings.append(
                RiskWarning(
                    "low",
                    "obstacle_near_edge",
                    f"Obstacle #{idx} is near screen edge; may push racers off-lane.",
                    obstacle_index=idx,
                )
            )

    blocker_rows.sort(key=lambda it: it[1])
    for i in range(1, len(blocker_rows)):
        prev_idx, prev_y, _ = blocker_rows[i - 1]
        cur_idx, cur_y, _ = blocker_rows[i]
        if (cur_y - prev_y) < min_gap:
            warnings.append(
                RiskWarning(
                    "high",
                    "rows_too_close",
                    f"Obstacle rows around y={prev_y:.0f} and y={cur_y:.0f} are < {min_gap:.0f}px apart.",
                    obstacle_indices=[prev_idx, cur_idx],
                )
            )

    level_weights = {"low": 1, "medium": 2, "high": 3}
    risk_score = min(100, sum(level_weights.get(w.level, 1) for w in warnings) * 6)
    return {
        "risk_score": risk_score,
        "warning_count": len(warnings),
        "warnings": [w.to_dict() for w in warnings],
    }
