from __future__ import annotations

from dataclasses import dataclass
import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .config import RaceConfig


def _hex_to_rgba(color: str, alpha: float = 1.0) -> tuple[int, int, int, int]:
    c = color.strip()
    if c.startswith("#"):
        c = c[1:]
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if len(c) != 6:
        return (255, 255, 255, int(255 * alpha))
    r = int(c[0:2], 16)
    g = int(c[2:4], 16)
    b = int(c[4:6], 16)
    a = max(0, min(255, int(round(255 * alpha))))
    return (r, g, b, a)


@dataclass(slots=True)
class Cloud:
    x: float
    y: float
    w: float
    h: float


class FrameCompositor:
    def __init__(self, cfg: RaceConfig) -> None:
        self.cfg = cfg
        self.width = cfg.render.width
        self.height = cfg.render.height
        self.font = ImageFont.load_default()
        self._circle_masks: dict[int, Image.Image] = {}
        self._background_base = self._build_background()

    def _build_background(self) -> Image.Image:
        bg_mode = self.cfg.background.mode
        base = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 255))
        draw = ImageDraw.Draw(base, "RGBA")

        if bg_mode == "solid":
            draw.rectangle(
                [(0, 0), (self.width, self.height)],
                fill=_hex_to_rgba(self.cfg.background.solid_color, 1.0),
            )
            return base

        if bg_mode == "gradient":
            top = _hex_to_rgba(self.cfg.background.gradient_top, 1.0)
            bottom = _hex_to_rgba(self.cfg.background.gradient_bottom, 1.0)
            for y in range(self.height):
                t = y / max(1, self.height - 1)
                row = (
                    int(top[0] * (1 - t) + bottom[0] * t),
                    int(top[1] * (1 - t) + bottom[1] * t),
                    int(top[2] * (1 - t) + bottom[2] * t),
                    255,
                )
                draw.line([(0, y), (self.width, y)], fill=row, width=1)
            return base

        # sky preset default
        top = _hex_to_rgba(self.cfg.background.gradient_top, 1.0)
        bottom = _hex_to_rgba(self.cfg.background.gradient_bottom, 1.0)
        for y in range(self.height):
            t = y / max(1, self.height - 1)
            row = (
                int(top[0] * (1 - t) + bottom[0] * t),
                int(top[1] * (1 - t) + bottom[1] * t),
                int(top[2] * (1 - t) + bottom[2] * t),
                255,
            )
            draw.line([(0, y), (self.width, y)], fill=row, width=1)

        rng = random.Random(self.cfg.seed + 51)
        cloud_color = _hex_to_rgba(self.cfg.background.cloud_color, 0.9)
        clouds = []
        for _ in range(self.cfg.background.cloud_count):
            w = rng.uniform(self.width * 0.08, self.width * 0.2)
            h = w * rng.uniform(0.45, 0.72)
            x = rng.uniform(-w * 0.3, self.width - w * 0.7)
            y = rng.uniform(self.height * 0.02, self.height * 0.95)
            clouds.append(Cloud(x, y, w, h))
        for cloud in clouds:
            self._draw_cloud(draw, cloud, cloud_color)
        return base

    @staticmethod
    def _draw_cloud(
        draw: ImageDraw.ImageDraw,
        cloud: Cloud,
        color: tuple[int, int, int, int],
    ) -> None:
        x, y, w, h = cloud.x, cloud.y, cloud.w, cloud.h
        draw.ellipse((x, y, x + w * 0.5, y + h), fill=color)
        draw.ellipse((x + w * 0.2, y - h * 0.25, x + w * 0.8, y + h * 0.95), fill=color)
        draw.ellipse((x + w * 0.5, y, x + w, y + h), fill=color)

    def _circle_mask(self, diameter: int) -> Image.Image:
        m = self._circle_masks.get(diameter)
        if m is not None:
            return m
        mask = Image.new("L", (diameter, diameter), 0)
        d = ImageDraw.Draw(mask)
        d.ellipse((0, 0, diameter - 1, diameter - 1), fill=255)
        self._circle_masks[diameter] = mask
        return mask

    def _draw_obstacles(self, draw: ImageDraw.ImageDraw, obstacle_visuals: list[dict]) -> None:
        for o in obstacle_visuals:
            fill = _hex_to_rgba(o.get("fill_color", "#111111"), o.get("opacity", 1.0))
            stroke = _hex_to_rgba(o.get("stroke_color", "#000000"), o.get("opacity", 1.0))
            t = o.get("type")
            if t in {"rect", "moving_rect", "one_way_gate"}:
                self._draw_rotated_rect(
                    draw,
                    o["x"],
                    o["y"],
                    o["width"],
                    o["height"],
                    math.radians(o.get("angle_deg", 0.0)),
                    fill,
                    stroke,
                )
            elif t == "circle":
                x = o["x"]
                y = o["y"]
                r = o["radius"]
                draw.ellipse((x - r, y - r, x + r, y + r), fill=fill, outline=stroke, width=3)
            elif t == "ring_gap":
                self._draw_ring_gap(draw, o, fill, stroke)
            elif t == "pendulum":
                draw.line(
                    (o["x0"], o["y0"], o["x1"], o["y1"]),
                    fill=fill,
                    width=max(2, int(o["thickness"])),
                )
                draw.ellipse(
                    (o["x0"] - 8, o["y0"] - 8, o["x0"] + 8, o["y0"] + 8),
                    fill=stroke,
                )

    @staticmethod
    def _draw_rotated_rect(
        draw: ImageDraw.ImageDraw,
        cx: float,
        cy: float,
        w: float,
        h: float,
        angle: float,
        fill: tuple[int, int, int, int],
        stroke: tuple[int, int, int, int],
    ) -> None:
        hx, hy = w * 0.5, h * 0.5
        corners = [(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)]
        pts = []
        c = math.cos(angle)
        s = math.sin(angle)
        for x, y in corners:
            px = cx + x * c - y * s
            py = cy + x * s + y * c
            pts.append((px, py))
        draw.polygon(pts, fill=fill, outline=stroke)

    @staticmethod
    def _draw_ring_gap(
        draw: ImageDraw.ImageDraw,
        o: dict,
        fill: tuple[int, int, int, int],
        stroke: tuple[int, int, int, int],
    ) -> None:
        x, y = o["x"], o["y"]
        radius = o["radius"]
        thickness = max(2, int(o["thickness"]))
        gap_center = o["gap_center_deg"]
        gap_size = o["gap_size_deg"]
        start = gap_center + gap_size * 0.5
        end = gap_center + 360.0 - gap_size * 0.5
        box = (x - radius, y - radius, x + radius, y + radius)
        draw.arc(box, start=start, end=end, fill=fill, width=thickness)
        draw.arc(box, start=start, end=end, fill=stroke, width=2)

    def render(
        self,
        frame_index: int,
        sim_time: float,
        positions: np.ndarray,
        racer_frames: list[np.ndarray],
        racer_names: list[str],
        racer_radii: list[float],
        leader: int,
        obstacle_visuals: list[dict],
        countdown_text: str | None = None,
    ) -> np.ndarray:
        canvas = self._background_base.copy()
        draw = ImageDraw.Draw(canvas, "RGBA")

        self._draw_obstacles(draw, obstacle_visuals)

        # Top featured leader circle.
        top_d = self.cfg.top_circle.diameter
        top_mask = self._circle_mask(top_d)
        top_x = self.width // 2 - top_d // 2
        top_y = self.cfg.top_circle.y - top_d // 2
        top_frame = Image.fromarray(racer_frames[leader], mode="RGB").resize(
            (top_d, top_d), resample=Image.Resampling.BILINEAR
        )
        canvas.paste(top_frame, (top_x, top_y), mask=top_mask)
        draw.ellipse(
            (top_x, top_y, top_x + top_d, top_y + top_d),
            outline=_hex_to_rgba(self.cfg.top_circle.border_color, 1.0),
            width=self.cfg.top_circle.border_width,
        )
        leader_name = racer_names[leader]
        tw = draw.textlength(leader_name, font=self.font)
        tx = (self.width - tw) * 0.5
        ty = top_y + top_d + 10
        draw.text(
            (tx, ty),
            leader_name,
            font=self.font,
            fill=_hex_to_rgba(self.cfg.label_style.color, 1.0),
            stroke_width=self.cfg.label_style.stroke_width,
            stroke_fill=_hex_to_rgba(self.cfg.label_style.stroke_color, 1.0),
        )

        for i, (pos, radius) in enumerate(zip(positions, racer_radii)):
            diam = int(round(radius * 2))
            x = int(round(pos[0] - radius))
            y = int(round(pos[1] - radius))
            if diam < 4:
                continue

            frame_img = Image.fromarray(racer_frames[i], mode="RGB").resize(
                (diam, diam), resample=Image.Resampling.BILINEAR
            )
            mask = self._circle_mask(diam)
            canvas.paste(frame_img, (x, y), mask=mask)
            draw.ellipse(
                (x, y, x + diam, y + diam),
                outline=_hex_to_rgba(self.cfg.racers[i].border_color, 1.0),
                width=self.cfg.racers[i].border_width,
            )

            name = racer_names[i]
            tw = draw.textlength(name, font=self.font)
            tx = pos[0] - tw / 2
            ty = pos[1] - radius - self.cfg.label_style.offset_y
            draw.text(
                (tx, ty),
                name,
                font=self.font,
                fill=_hex_to_rgba(self.cfg.label_style.color, 1.0),
                stroke_width=self.cfg.label_style.stroke_width,
                stroke_fill=_hex_to_rgba(self.cfg.label_style.stroke_color, 1.0),
            )

        if countdown_text:
            text = countdown_text
            tw = draw.textlength(text, font=self.font)
            tx = (self.width - tw) * 0.5
            ty = self.height * 0.45
            draw.text(
                (tx, ty),
                text,
                font=self.font,
                fill=_hex_to_rgba("#ffffff", 1.0),
                stroke_width=4,
                stroke_fill=_hex_to_rgba("#111111", 1.0),
            )

        return np.array(canvas.convert("RGB"), dtype=np.uint8)
