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
- Audio-wave auto sync across racers using overlap-window trimming (`sync_trim_start_seconds`) via CLI/API/frontend.
- Vue 3 + TypeScript + Tailwind frontend for uploads, crop-center selection, preview/final jobs.
- Realtime frontend parkour builder with drag-and-drop obstacle editing and live simulation preview.

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

### 5) Auto-sync racers by waveform (optional)

```bash
python3 -m songracer sync --config configs/snaptik_2_racers.json --write
```

This estimates:
- relative `sync_offset_seconds` (diagnostic),
- per-racer `sync_trim_start_seconds` (used at render time),
- `sync_common_window_seconds` (common overlap duration).

With `--write`, it updates the config and caps `render.duration_seconds` to the common overlap by default.

### 6) Analyze obstacle layout risk (optional)

```bash
python3 -m songracer analyze --config configs/demo_5_racers.json
```

Returns a heuristic risk score and warnings for trap-prone obstacle patterns (for example tight blocker rows or tiny ring gaps).

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
  - `sync_trim_start_seconds` on each racer trims to a shared aligned start.
  - `sync_common_window_seconds` can cap race duration to the shared overlap window.
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
- `GET /system/info` (resolved writable storage + DB paths)
- `GET /builder/capabilities` (builder/UI limits for preview and procedural generation)
- `GET /builder/bootstrap` (combined builder capabilities + obstacle types + templates + deterministic bootstrap version hash)
- `GET /templates/obstacle-types` (obstacle type catalog + labels in stable order for builder palette)
- `GET /templates/obstacles` (preset obstacle layouts for builder)
- `POST /templates/obstacles/generate` (procedural obstacle stream generator; capability-bound validated)
- `POST /templates/obstacles/generate-safe` (risk-targeted generator with deterministic sequential-seed retries; capability-bound validated)
  - both generator endpoints accept omitted fields and apply capability default values
  - explicit default values are equivalent to omitted fields
- `POST /uploads` (multipart video upload)
- `POST /sync/audio` with `{ "video_paths": [...], "sample_rate": 16000, "max_shift_seconds": 8 }`
- `POST /sync/preview` (sync analysis + waveform arrays in one call)
- `POST /waveform` with `{ "video_path": "...", "sample_rate": 8000, "points": 320 }`
- `POST /analyze/config` with `{ "config": { ... } }` to get obstacle risk warnings
- `POST /preview/simulate` for lightweight trajectory+camera live preview (builder)
  - `sample_fps`/`max_frames` are validated against capability bounds (out-of-range -> HTTP 422)
- `GET /preview/cache` and `POST /preview/cache/clear` for preview-cache diagnostics
- `POST /validate` with `{ "config_path": "..." }`
- `POST /validate/config` with inline `{ "config": { ... } }`
- `POST /render` with
  `{ "config_path": "...", "output_path": "...", "preview_scale": 1.0 }`
- `POST /jobs` with
  `{ "config_path": "...", "output_path": "...", "preview_scale": 1.0 }`
- `POST /jobs/from-config` with inline config JSON payload
- `GET /jobs`
- `GET /jobs/{job_id}`
- `GET /jobs/{job_id}/artifact`
- `GET /projects` (optional `?include_analysis=true`) / `POST /projects` / `GET|PUT|DELETE /projects/{id}` (SQLite project CRUD)
- `POST /projects/{id}/render` to submit async render directly from saved DB project
- `POST /projects/{id}/sync` to re-run waveform sync and persist trims/common window
- `GET /projects/{id}/analyze` to score obstacle safety of saved project config

Integration contract details: `docs/frontend_integration.md`

## Frontend (Vue + TypeScript + Tailwind)

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL (usually `http://localhost:5173`), set API base to `http://localhost:8080`, upload singer videos, click each preview to set face center, then submit preview/final jobs.

The Render Controls panel also includes a **Parkour Builder**:
- drag obstacle types onto the canvas,
- move and edit obstacles in-place,
- play live simulation preview (racers + camera) without full MP4 rendering,
- apply starter presets,
- lock/hide obstacles and reorder layers while editing (hidden obstacles are immediately excluded from preview/risk requests),
- shift-click multi-select + bulk delete,
- drag one selected handle to move the entire selected group,
- keyboard shortcuts for fast editing (delete/duplicate/select all/nudge),
- undo/redo history controls with keyboard shortcuts,
- copy/paste obstacle groups from clipboard (toolbar and keyboard),
- adjustable snap size and quick alignment actions (Align X / Align Y),
- obstacle-only JSON import/export directly from builder toolbar,
- copy a shareable builder URL embedding obstacle JSON (`Copy Builder Link`),
- quick clear/reset action for current obstacle layout,
- focus helpers (`Focus Selected`, `Fit Camera`) for large courses,
- malformed numeric obstacle fields are sanitized to safe defaults in builder import/parsing flow,
- preset courses are loaded from backend template catalog with local fallback when offline,
- procedural obstacle-stream generation (append/replace) from seed/count/spacing in builder,
- safe procedural stream generation mode (target risk + retry attempts),
- stream generator now mixes additional obstacle variants (including circles and pendulums),
- quick random-seed action available for procedural stream exploration,
- risk warning entries are clickable to focus linked obstacle(s) in builder canvas and show linked obstacle indices,
- safe generation result badge shows seed/risk/warnings/attempts + accepted/best-effort outcome, and auto-clears when layout visibility/geometry changes,
- tune live preview sampling (sample FPS + frame cap) and optionally disable auto-preview,
- live preview scrub row shows requested→effective sampled fps, frame-step, and requested frame-cap metadata from backend,
- live preview scrub row also shows sampled frame count (`returned_sample_frames/total_sample_frames`),
- live preview scrub row also shows full source-frame count (`total_source_frames`),
- live preview scrub row shows sampled-window span (`returned_sample_duration_seconds/total_sample_duration_seconds`),
- preview API response includes both requested and effective sampling metadata for diagnostics,
- preview API includes explicit `returned_sample_frames` for quick sampled-length checks,
- preview API includes returned/total sampled-window durations for timeline diagnostics,
- preview API includes `total_source_frames` so sampled timelines can be related back to full simulated frame count,
- preview metadata includes resolved goal line position (`goal_y`) used for winner detection,
- if preview returns a single sample frame, sampled-window duration is `0s`,
- preview response guarantees `returned_sample_frames <= requested_max_frames`,
- effective preview sampling rate is bounded by both requested sample-fps and render fps,
- when preview is not truncated, `total_sample_frames` equals returned sampled frame count,
- truncation warning includes shown/total sampled frames plus requested frame-cap value,
- preview cache diagnostics/clear controls available via API and builder toolbar,
- preview cache hits occur for semantically identical preview JSON payloads (key order ignored); changing knobs/layout recomputes simulation,
- omitted preview sampling fields and explicitly sent default values resolve to the same cache key,
- cache-hit preview responses match fresh payloads except for `cache_hit=true`,
- sampled-length metadata (`returned_sample_frames`) remains identical between fresh/cache-hit responses,
- sampled-duration metadata (`returned_sample_duration_seconds`) remains identical between fresh/cache-hit responses,
- preview endpoint includes lightweight cache-hit metadata for rapid repeated edits,
- preview winner metadata uses `winner_index=-1` and `winner_frame=-1` when no finisher is reached,
- builder UI preferences (grid/snap/preview tuning) persist locally in browser storage,
- builder UI surfaces capability limits fetched from backend contract.
- keep raw obstacle JSON synchronized for full-control edits.

Live preview in builder is simulation-only and intentionally sampled/capped for responsiveness.
Use render jobs for final authoritative output.

Builder keyboard shortcuts:
- `Delete/Backspace`: delete selection
- `Ctrl/Cmd + Z`: undo
- `Ctrl/Cmd + Shift + Z` (or `Ctrl/Cmd + Y`): redo
- `Ctrl/Cmd + D`: duplicate selected obstacle
- `Ctrl/Cmd + A`: select all obstacles
- `Ctrl/Cmd + C`: copy selected obstacles as JSON
- `Ctrl/Cmd + V`: paste obstacles from clipboard
- `Esc`: clear selection
- `Arrow keys`: nudge selection (`Shift` for larger nudge)

If frontend shows backend offline / connection refused, start API first:

```bash
python3 -m uvicorn songracer.api:app --host 0.0.0.0 --port 8080 --reload
```

Optional storage env vars:

- `SONGRACER_STORAGE_DIR` (uploads/job configs/outputs root)
- `SONGRACER_DB_PATH` (SQLite database file)

When unset or unwritable, backend falls back to a writable temp directory.

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
- **Preview render failed with x264 dimension error**:
  - latest CLI auto-rounds scaled dimensions to even numbers; update to latest code.
- **Audio crackles on rapid leader changes**:
  - increase `audio.switch_crossfade_ms` slightly (e.g. 12 -> 20).
