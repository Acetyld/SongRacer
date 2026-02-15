# SongRacer

SongRacer generates an autonomous **9:16 singer race video** and exports a final **MP4**.

Each racer is a circular video avatar that falls through a configurable obstacle course.
At every frame, the bottom-most racer is the active singer:

- their video playhead advances,
- their audio is audible,
- all non-leaders stay frozen.

The top featured circle mirrors the current leader and a countdown (`3,2,1,GO`) is rendered before the race starts.

## Features

- Fully configurable race settings via JSON:
  - duration, FPS, and output resolution (defaults portrait 1080x1920)
  - physics tuning
  - racer count and video inputs
  - background mode/colors/image
  - obstacle styling/colors
- Multiple obstacle types:
  - `rect`
  - `circle`
  - `ring_gap` (rotating ring with hole)
  - `moving_rect`
  - `pendulum`
  - `one_way_gate`
  - `spinner`
- Single active audio source with configurable micro crossfade on leader switches.
- CLI renderer + minimal FastAPI endpoints for future frontend integration.

## Quick Start

### 1) Install

```bash
python3 -m pip install -e ".[dev]"
```

### 2) Generate demo singer videos

```bash
python3 scripts/generate_demo_media.py --count 5 --duration 30 --with-background
```

This creates synthetic demo assets in `assets/demo`.

### 3) Validate config

```bash
python3 -m songracer validate --config configs/demo_5_racers.json
```

### 4) Render

```bash
python3 -m songracer render \
  --config configs/demo_5_racers.json \
  --output outputs/demo_5_racers.mp4
```

Preview faster at reduced scale:

```bash
python3 -m songracer render \
  --config configs/demo_5_racers.json \
  --output outputs/demo_preview.mp4 \
  --preview-scale 0.5
```

## Config Notes

- Background:
  - `background.mode`: `sky` | `solid` | `gradient` | `image`
  - color fields are hex strings (`#RRGGBB`)
  - image mode uses `background.image_path` and optional `background.image_opacity` (0..1)
- Obstacle color/style:
  - per-obstacle `fill_color`, `stroke_color`, `opacity`
- Audio:
  - `switch_crossfade_ms` smooths audio on leader changes.
- Race timing:
  - `countdown_seconds` added before race simulation starts.

See:
- `configs/demo_5_racers.json` (full obstacle set)
- `configs/demo_gradient_background.json`
- `configs/demo_image_background.json`

## API (frontend-ready scaffold)

Run API:

```bash
uvicorn songracer.api:app --host 0.0.0.0 --port 8080
```

Endpoints:

- `GET /health`
- `POST /validate` with `{ "config_path": "..." }`
- `POST /render` with
  `{ "config_path": "...", "output_path": "...", "preview_scale": 1.0 }`

Integration contract details: `docs/frontend_integration.md`

## Testing

```bash
pytest -q
```

## Troubleshooting

- **Config validates but render fails quickly**:
  - ensure `ffmpeg` and `ffprobe` are installed and available in PATH.
- **Image background errors**:
  - verify `background.image_path` points to a real file; paths in config can be relative to the config file.
- **Input videos are very long/high-res and slow down render**:
  - use `--preview-scale 0.5` while iterating.
- **Audio crackles on rapid leader changes**:
  - increase `audio.switch_crossfade_ms` slightly (e.g. 12 -> 20).
