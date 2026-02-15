from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(slots=True)
class Vec2:
    x: float
    y: float

    def __add__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> "Vec2":
        return Vec2(self.x * scalar, self.y * scalar)

    def dot(self, other: "Vec2") -> float:
        return self.x * other.x + self.y * other.y

    def length(self) -> float:
        return math.hypot(self.x, self.y)

    def normalized(self) -> "Vec2":
        d = self.length()
        if d < 1e-8:
            return Vec2(0.0, -1.0)
        return Vec2(self.x / d, self.y / d)


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def rotate(v: Vec2, angle_rad: float) -> Vec2:
    c = math.cos(angle_rad)
    s = math.sin(angle_rad)
    return Vec2(v.x * c - v.y * s, v.x * s + v.y * c)


def angle_of(v: Vec2) -> float:
    return math.atan2(v.y, v.x)


def wrap_angle_pi(a: float) -> float:
    while a <= -math.pi:
        a += 2 * math.pi
    while a > math.pi:
        a -= 2 * math.pi
    return a


def angle_in_gap(angle: float, center: float, size: float) -> bool:
    """
    All angles are radians.
    """
    delta = wrap_angle_pi(angle - center)
    return abs(delta) <= size * 0.5
