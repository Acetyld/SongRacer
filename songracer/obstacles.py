from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol

from .config import ObstacleConfig, PhysicsConfig
from .math2d import Vec2, angle_in_gap, angle_of, clamp, rotate


def _bounce(velocity: Vec2, normal: Vec2, restitution: float) -> Vec2:
    vn = velocity.dot(normal)
    if vn >= 0:
        return velocity
    return velocity - normal * ((1.0 + restitution) * vn)


class Obstacle(Protocol):
    fill_color: str
    stroke_color: str
    opacity: float

    def resolve(
        self,
        position: Vec2,
        velocity: Vec2,
        racer_radius: float,
        t: float,
        physics: PhysicsConfig,
    ) -> tuple[Vec2, Vec2]:
        ...

    def visual(self, t: float) -> dict:
        ...


@dataclass(slots=True)
class RectObstacle:
    x: float
    y: float
    width: float
    height: float
    angle_deg: float
    fill_color: str
    stroke_color: str
    opacity: float

    def center_at(self, t: float) -> Vec2:
        _ = t
        return Vec2(self.x, self.y)

    def angle_rad_at(self, t: float) -> float:
        _ = t
        return math.radians(self.angle_deg)

    def resolve(
        self,
        position: Vec2,
        velocity: Vec2,
        racer_radius: float,
        t: float,
        physics: PhysicsConfig,
    ) -> tuple[Vec2, Vec2]:
        center = self.center_at(t)
        angle = self.angle_rad_at(t)
        local = rotate(position - center, -angle)

        hx = self.width * 0.5
        hy = self.height * 0.5
        closest = Vec2(clamp(local.x, -hx, hx), clamp(local.y, -hy, hy))
        delta = local - closest
        dist = delta.length()
        if dist >= racer_radius:
            return position, velocity

        if dist < 1e-6:
            px = hx - abs(local.x)
            py = hy - abs(local.y)
            if px < py:
                normal_local = Vec2(1.0 if local.x >= 0 else -1.0, 0.0)
                penetration = racer_radius + px
            else:
                normal_local = Vec2(0.0, 1.0 if local.y >= 0 else -1.0)
                penetration = racer_radius + py
        else:
            normal_local = delta.normalized()
            penetration = racer_radius - dist

        corrected_local = local + normal_local * penetration
        corrected_world = center + rotate(corrected_local, angle)
        normal_world = rotate(normal_local, angle).normalized()
        reflected = _bounce(velocity, normal_world, physics.restitution)
        return corrected_world, reflected

    def visual(self, t: float) -> dict:
        c = self.center_at(t)
        return {
            "type": "rect",
            "x": c.x,
            "y": c.y,
            "width": self.width,
            "height": self.height,
            "angle_deg": math.degrees(self.angle_rad_at(t)),
            "fill_color": self.fill_color,
            "stroke_color": self.stroke_color,
            "opacity": self.opacity,
        }


@dataclass(slots=True)
class MovingRectObstacle(RectObstacle):
    amplitude: float = 80.0
    frequency_hz: float = 0.2
    axis: str = "x"

    def center_at(self, t: float) -> Vec2:
        offset = self.amplitude * math.sin(2 * math.pi * self.frequency_hz * t)
        if self.axis == "y":
            return Vec2(self.x, self.y + offset)
        return Vec2(self.x + offset, self.y)

    def visual(self, t: float) -> dict:
        v = super().visual(t)
        v["type"] = "moving_rect"
        return v


@dataclass(slots=True)
class CircleObstacle:
    x: float
    y: float
    radius: float
    fill_color: str
    stroke_color: str
    opacity: float

    def resolve(
        self,
        position: Vec2,
        velocity: Vec2,
        racer_radius: float,
        t: float,
        physics: PhysicsConfig,
    ) -> tuple[Vec2, Vec2]:
        _ = t
        center = Vec2(self.x, self.y)
        delta = position - center
        dist = delta.length()
        min_dist = self.radius + racer_radius
        if dist >= min_dist:
            return position, velocity
        normal = delta.normalized()
        corrected = center + normal * min_dist
        reflected = _bounce(velocity, normal, physics.restitution)
        return corrected, reflected

    def visual(self, t: float) -> dict:
        _ = t
        return {
            "type": "circle",
            "x": self.x,
            "y": self.y,
            "radius": self.radius,
            "fill_color": self.fill_color,
            "stroke_color": self.stroke_color,
            "opacity": self.opacity,
        }


@dataclass(slots=True)
class RingGapObstacle:
    x: float
    y: float
    radius: float
    thickness: float
    rotation_speed_deg: float
    gap_center_deg: float
    gap_size_deg: float
    fill_color: str
    stroke_color: str
    opacity: float

    def resolve(
        self,
        position: Vec2,
        velocity: Vec2,
        racer_radius: float,
        t: float,
        physics: PhysicsConfig,
    ) -> tuple[Vec2, Vec2]:
        center = Vec2(self.x, self.y)
        rel = position - center
        dist = rel.length()
        if dist < 1e-6:
            rel = Vec2(0.0, -1.0)
            dist = 1.0

        ring_outer = self.radius + self.thickness * 0.5
        ring_inner = self.radius - self.thickness * 0.5
        if ring_inner < 1.0:
            ring_inner = 1.0

        ang = angle_of(rel)
        gap_center = math.radians(self.gap_center_deg + self.rotation_speed_deg * t)
        gap_size = math.radians(self.gap_size_deg)
        if angle_in_gap(ang, gap_center, gap_size):
            return position, velocity

        overlaps_annulus = (dist + racer_radius > ring_inner) and (
            dist - racer_radius < ring_outer
        )
        if not overlaps_annulus:
            return position, velocity

        push_to_outer = (ring_outer - dist + racer_radius) < (
            dist + racer_radius - ring_inner
        )
        radial = rel.normalized()
        if push_to_outer:
            target_dist = ring_outer + racer_radius
            normal = radial
        else:
            target_dist = max(1.0, ring_inner - racer_radius)
            normal = radial * -1.0
        corrected = center + radial * target_dist
        reflected = _bounce(velocity, normal, physics.restitution)
        return corrected, reflected

    def visual(self, t: float) -> dict:
        return {
            "type": "ring_gap",
            "x": self.x,
            "y": self.y,
            "radius": self.radius,
            "thickness": self.thickness,
            "gap_center_deg": self.gap_center_deg + self.rotation_speed_deg * t,
            "gap_size_deg": self.gap_size_deg,
            "fill_color": self.fill_color,
            "stroke_color": self.stroke_color,
            "opacity": self.opacity,
        }


@dataclass(slots=True)
class PendulumObstacle:
    pivot_x: float
    pivot_y: float
    length: float
    thickness: float
    angle_deg: float
    amplitude_deg: float
    frequency_hz: float
    fill_color: str
    stroke_color: str
    opacity: float

    def _segment(self, t: float) -> tuple[Vec2, Vec2]:
        angle = math.radians(self.angle_deg) + math.radians(self.amplitude_deg) * math.sin(
            2 * math.pi * self.frequency_hz * t
        )
        p0 = Vec2(self.pivot_x, self.pivot_y)
        p1 = p0 + rotate(Vec2(0.0, self.length), angle)
        return p0, p1

    def resolve(
        self,
        position: Vec2,
        velocity: Vec2,
        racer_radius: float,
        t: float,
        physics: PhysicsConfig,
    ) -> tuple[Vec2, Vec2]:
        p0, p1 = self._segment(t)
        seg = p1 - p0
        seg_len2 = max(1e-6, seg.dot(seg))
        proj = clamp((position - p0).dot(seg) / seg_len2, 0.0, 1.0)
        closest = p0 + seg * proj
        delta = position - closest
        dist = delta.length()
        min_dist = racer_radius + self.thickness * 0.5
        if dist >= min_dist:
            return position, velocity
        normal = delta.normalized()
        corrected = closest + normal * min_dist
        reflected = _bounce(velocity, normal, physics.restitution)
        return corrected, reflected

    def visual(self, t: float) -> dict:
        p0, p1 = self._segment(t)
        return {
            "type": "pendulum",
            "x0": p0.x,
            "y0": p0.y,
            "x1": p1.x,
            "y1": p1.y,
            "thickness": self.thickness,
            "fill_color": self.fill_color,
            "stroke_color": self.stroke_color,
            "opacity": self.opacity,
        }


@dataclass(slots=True)
class OneWayGateObstacle(RectObstacle):
    one_way: str = "down"

    def resolve(
        self,
        position: Vec2,
        velocity: Vec2,
        racer_radius: float,
        t: float,
        physics: PhysicsConfig,
    ) -> tuple[Vec2, Vec2]:
        if self.one_way == "down":
            # Lets racers pass while falling downward, blocks upward rebounds.
            if velocity.y >= 0:
                return position, velocity
        elif self.one_way == "up":
            # Blocks downward movement, lets upward pass.
            if velocity.y <= 0:
                return position, velocity
        return super().resolve(position, velocity, racer_radius, t, physics)

    def visual(self, t: float) -> dict:
        v = super().visual(t)
        v["type"] = "one_way_gate"
        return v


def build_obstacles(obstacles: list[ObstacleConfig]) -> list[Obstacle]:
    out: list[Obstacle] = []
    for obs in obstacles:
        if obs.type == "rect":
            out.append(
                RectObstacle(
                    x=obs.x,
                    y=obs.y,
                    width=obs.width or 220,
                    height=obs.height or 34,
                    angle_deg=obs.angle_deg,
                    fill_color=obs.fill_color,
                    stroke_color=obs.stroke_color,
                    opacity=obs.opacity,
                )
            )
        elif obs.type == "moving_rect":
            out.append(
                MovingRectObstacle(
                    x=obs.x,
                    y=obs.y,
                    width=obs.width or 240,
                    height=obs.height or 32,
                    angle_deg=obs.angle_deg,
                    amplitude=obs.amplitude,
                    frequency_hz=obs.frequency_hz,
                    axis=obs.axis,
                    fill_color=obs.fill_color,
                    stroke_color=obs.stroke_color,
                    opacity=obs.opacity,
                )
            )
        elif obs.type == "circle":
            out.append(
                CircleObstacle(
                    x=obs.x,
                    y=obs.y,
                    radius=obs.radius or 64,
                    fill_color=obs.fill_color,
                    stroke_color=obs.stroke_color,
                    opacity=obs.opacity,
                )
            )
        elif obs.type == "ring_gap":
            out.append(
                RingGapObstacle(
                    x=obs.x,
                    y=obs.y,
                    radius=obs.radius or 120,
                    thickness=obs.thickness,
                    rotation_speed_deg=obs.rotation_speed_deg,
                    gap_center_deg=obs.gap_center_deg,
                    gap_size_deg=obs.gap_size_deg,
                    fill_color=obs.fill_color,
                    stroke_color=obs.stroke_color,
                    opacity=obs.opacity,
                )
            )
        elif obs.type == "pendulum":
            out.append(
                PendulumObstacle(
                    pivot_x=obs.pivot_x if obs.pivot_x is not None else obs.x,
                    pivot_y=obs.pivot_y if obs.pivot_y is not None else obs.y,
                    length=obs.length,
                    thickness=obs.thickness,
                    angle_deg=obs.angle_deg,
                    amplitude_deg=max(1.0, obs.amplitude),
                    frequency_hz=obs.frequency_hz,
                    fill_color=obs.fill_color,
                    stroke_color=obs.stroke_color,
                    opacity=obs.opacity,
                )
            )
        elif obs.type == "one_way_gate":
            out.append(
                OneWayGateObstacle(
                    x=obs.x,
                    y=obs.y,
                    width=obs.width or 220,
                    height=obs.height or 24,
                    angle_deg=obs.angle_deg,
                    one_way=obs.one_way,
                    fill_color=obs.fill_color,
                    stroke_color=obs.stroke_color,
                    opacity=obs.opacity,
                )
            )
    return out
