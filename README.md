# SongRacer

SongRacer generates an autonomous **9:16 singer race video** and exports a final **MP4**.

Each racer is a circular video avatar that falls through a configurable obstacle course.
At every frame, the bottom-most racer is the active singer:

- their video playhead advances,
- their audio is audible,
- all non-leaders stay frozen.

The top featured circle mirrors the current leader, the camera scrolls down the level, a stylized countdown (`3,2,1,GO`) plays with SFX, and a winner sequence closes the race.

## Features

- Fully configurable race settings via JSON:
  - duration, FPS, and output resolution (defaults portrait 1080x1920)
  - world height + camera-follow behavior
  - auto-finish winner rules
  - physics tuning
  - racer count and video inputs
  - per-racer crop center (`crop_center_x`, `crop_center_y`)
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
- Countdown and victory SFX mixed into output audio.
- Anti-stuck racer boosts to prevent deadlocks.
- Vue 3 + TypeScript + Tailwind frontend for uploads, crop-center selection, preview/final jobs.

## Quick Start

### 1) Install

```bash
python3 -m pip install -e ".[dev]"
```

### 2) Generate demo singer videos

```bash
python3 scripts/generate_demo_media.py --count 5 --duration 30 --with-background --with-sfx
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
  - optional file-based SFX:
    - `audio.countdown_sfx_path`
    - `audio.victory_sfx_path`
  - if SFX paths are omitted, synthesized fallback SFX are used.
- Race timing:
  - `countdown_seconds` added before race simulation starts.

See:
- `configs/demo_5_racers.json` (full obstacle set)
- `configs/demo_gradient_background.json`
- `configs/demo_image_background.json`
- `configs/demo_auto_finish.json` (winner auto-end showcase)

## API (frontend-ready scaffold)

Run API:

```bash
uvicorn songracer.api:app --host 0.0.0.0 --port 8080
```

Endpoints:

- `GET /health`
- `POST /uploads` (multipart video upload)
- `POST /validate` with `{ "config_path": "..." }`
- `POST /render` with
  `{ "config_path": "...", "output_path": "...", "preview_scale": 1.0 }`
- `POST /jobs` with
  `{ "config_path": "...", "output_path": "...", "preview_scale": 1.0 }`
- `POST /jobs/from-config` with inline config JSON payload
- `GET /jobs`
- `GET /jobs/{job_id}`
- `GET /jobs/{job_id}/artifact`

Integration contract details: `docs/frontend_integration.md`

## Frontend (Vue + TypeScript + Tailwind)

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL (usually `http://localhost:5173`), set API base to `http://localhost:8080`, upload singer videos, click each preview to set face center, then submit preview/final jobs.

## Testing

```bash
pytest -q
```

Frontend build check:

```bash
cd frontend
npm run build
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
