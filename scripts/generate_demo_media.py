#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        raise SystemExit(f"Command failed ({proc.returncode}): {' '.join(cmd)}")


def create_demo_video(out_path: Path, duration: float, freq: int, hue_deg: int) -> None:
    vf = (
        "testsrc2=size=540x960:rate=30:duration={dur},"
        "hue=h={hue}:s=1,"
        "drawbox=x='mod(t*140,iw)':y='ih*0.78':w='iw/4':h=48:color=white@0.75:t=fill"
    ).format(dur=duration, hue=hue_deg)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        vf,
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency={freq}:sample_rate=48000:duration={duration}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(out_path),
    ]
    run(cmd)


def create_background_image(out_path: Path, width: int = 1080, height: int = 1920) -> None:
    vf = (
        f"testsrc2=size={width}x{height}:rate=1:duration=1,"
        "hue=h=210:s=0.4,"
        "boxblur=4:2"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        vf,
        "-frames:v",
        "1",
        str(out_path),
    ]
    run(cmd)


def create_sfx_countdown(out_path: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=760:sample_rate=48000:duration=0.14",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=700:sample_rate=48000:duration=0.14",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=640:sample_rate=48000:duration=0.14",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=1080:sample_rate=48000:duration=0.35",
        "-filter_complex",
        "[0:a]adelay=0|0[a0];"
        "[1:a]adelay=1000|1000[a1];"
        "[2:a]adelay=2000|2000[a2];"
        "[3:a]adelay=3000|3000[a3];"
        "[a0][a1][a2][a3]amix=inputs=4:normalize=0[out]",
        "-map",
        "[out]",
        "-c:a",
        "pcm_s16le",
        str(out_path),
    ]
    run(cmd)


def create_sfx_victory(out_path: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=660:sample_rate=48000:duration=0.16",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=880:sample_rate=48000:duration=0.16",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=1120:sample_rate=48000:duration=0.22",
        "-filter_complex",
        "[0:a]adelay=0|0[a0];"
        "[1:a]adelay=160|160[a1];"
        "[2:a]adelay=320|320[a2];"
        "[a0][a1][a2]amix=inputs=3:normalize=0[out]",
        "-map",
        "[out]",
        "-c:a",
        "pcm_s16le",
        str(out_path),
    ]
    run(cmd)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic demo singer videos")
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--output-dir", default="assets/demo")
    parser.add_argument(
        "--with-background",
        action="store_true",
        help="Also generate assets/demo/background.png for image background mode.",
    )
    parser.add_argument(
        "--with-sfx",
        action="store_true",
        help="Also generate assets/demo/countdown.wav and assets/demo/victory.wav.",
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    base_freq = 220
    for idx in range(args.count):
        out_path = out_dir / f"singer_{idx + 1}.mp4"
        freq = base_freq + idx * 60
        hue = (idx * 55) % 360
        print(f"Generating {out_path.name} freq={freq} hue={hue}")
        create_demo_video(out_path, args.duration, freq, hue)

    if args.with_background:
        bg_path = out_dir / "background.png"
        print(f"Generating {bg_path.name}")
        create_background_image(bg_path)
    if args.with_sfx:
        countdown = out_dir / "countdown.wav"
        victory = out_dir / "victory.wav"
        print(f"Generating {countdown.name}")
        create_sfx_countdown(countdown)
        print(f"Generating {victory.name}")
        create_sfx_victory(victory)

    print(f"Done. Generated {args.count} demo files in {out_dir}")


if __name__ == "__main__":
    main()
