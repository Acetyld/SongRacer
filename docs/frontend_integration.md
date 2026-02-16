# Frontend Integration Contract (v0.1)

This document describes how a web frontend can integrate with SongRacer.

## Goals

- Upload N singer videos.
- Let users configure race/background/obstacle settings.
- Trigger render job.
- Retrieve generated MP4.

## Current API Endpoints

Base app: `songracer.api:app`

### `GET /health`
Healthcheck.

Response:

```json
{ "status": "ok" }
```

### `GET /system/info`
Resolved runtime storage locations (useful when writable fallback paths are selected).

### `GET /builder/capabilities`
Returns frontend-facing limits/defaults for builder controls (preview sampling + generator ranges).

Response:

```json
{
  "preview": {
    "sample_fps": { "min": 4, "max": 60, "default": 15 },
    "max_frames": { "min": 30, "max": 1500, "default": 300 }
  },
  "generator": {
    "count": { "min": 1, "max": 200, "default": 8 },
    "safe_target_max_risk": { "min": 0, "max": 100, "default": 35 },
    "safe_max_attempts": { "min": 1, "max": 64, "default": 8 }
  }
}
```

Each capability entry guarantees `min <= default <= max`.

### `GET /builder/bootstrap`
Combined builder bootstrap payload to reduce round-trips. Includes:
- `capabilities` (same as `/builder/capabilities`)
- `obstacle_types` (same as `/templates/obstacle-types`)
- `templates` (same as `/templates/obstacles`)
- `bootstrap_version` (deterministic content hash for cache/debug visibility; stable for unchanged payload)

### `GET /templates/obstacle-types`
Returns obstacle type catalog for builder palette rendering (stable order for deterministic UI palette layout).

Response:

```json
{
  "types": [
    { "type": "rect", "label": "Rect" },
    { "type": "ring_gap", "label": "Ring Gap" }
  ]
}
```

### `GET /templates/obstacles`
Returns preset obstacle layouts for the realtime parkour builder.

Response:

```json
{
  "version": "sha256:...",
  "template_count": 3,
  "templates": {
    "starter": [{ "... obstacle ..." }],
    "rings": [{ "... obstacle ..." }],
    "gates": [{ "... obstacle ..." }]
  }
}
```

### `POST /templates/obstacles/generate`
Generates a procedural obstacle stream for builder workflows.
Input bounds are validated against `/builder/capabilities` generator ranges (out-of-range -> HTTP 422).
All request fields are optional; omitted values default to `/builder/capabilities.generator.*.default`.

Request:

```json
{
  "count": 8,
  "start_y": 900,
  "spacing": 260,
  "width": 1080,
  "seed": 13
}
```

Response:

```json
{
  "seed": 13,
  "count": 8,
  "obstacles": [{ "... obstacle ..." }]
}
```

### `POST /templates/obstacles/generate-safe`
Generates multiple candidate streams across sequential seeds and returns the best (or accepted) stream using risk analysis.
Selection is deterministic for a fixed request: candidates are evaluated in seed order (`seed + attempt`), and the response is either the first candidate meeting `target_max_risk`, or the lowest-risk candidate across attempted seeds.
Input bounds (`count/start_y/spacing/width/seed/target_max_risk/max_attempts`) are validated against `/builder/capabilities` generator ranges (out-of-range -> HTTP 422).
All request fields are optional; omitted values default to `/builder/capabilities.generator.*.default`.
Providing explicit default values is equivalent to omitting the fields.

Request:

```json
{
  "count": 8,
  "start_y": 900,
  "spacing": 260,
  "width": 1080,
  "seed": 13,
  "target_max_risk": 35,
  "max_attempts": 8,
  "analysis_height": 1920
}
```

Response:

```json
{
  "seed": 15,
  "count": 8,
  "risk_score": 28,
  "warning_count": 3,
  "warnings": [{ "level": "medium", "code": "..." }],
  "attempts": 3,
  "accepted": true,
  "target_max_risk": 35,
  "obstacles": [{ "... obstacle ..." }]
}
```

### `POST /validate`
Validate config before rendering.

Request:

```json
{
  "config_path": "/abs/path/to/config.json"
}
```

Response:

```json
{
  "valid": true,
  "racers": 5,
  "obstacles": 7
}
```

### `POST /validate/config`
Validate inline config JSON (no server-side config file required).

Request:

```json
{
  "config": { "... full songracer config ..." }
}
```

Response:

```json
{
  "valid": true,
  "racers": 5,
  "obstacles": 7
}
```

### `POST /render`
Run a render job immediately (synchronous).

Request:

```json
{
  "config_path": "/abs/path/to/config.json",
  "output_path": "/abs/path/to/output.mp4",
  "preview_scale": 1.0
}
```

Response:

```json
{
  "output_path": "/abs/path/to/output.mp4",
  "total_frames": 630,
  "leaders_switches": 6,
  "timeline_hash": "..."
}
```

### `POST /jobs`
Create an asynchronous render job.

Request:

```json
{
  "config_path": "/abs/path/to/config.json",
  "output_path": "/abs/path/to/output.mp4",
  "preview_scale": 1.0
}
```

Response:

```json
{
  "job_id": "5f0e5d8f1f994166b5f4a0df4e7e933d",
  "state": "queued"
}
```

### `GET /jobs`
List current job records.

Response:

```json
{
  "jobs": [
    {
      "job_id": "...",
      "state": "running"
    }
  ]
}
```

### `GET /jobs/{job_id}`
Get a single job status and stats/error payload.

### `GET /jobs/{job_id}/artifact`
Download generated MP4 once job is `completed`.

### `POST /uploads`
Upload a singer video asset.

Request: multipart form-data (`file` field)

Response:

```json
{
  "path": "/workspace/uploads/20260215T....mp4",
  "filename": "20260215T....mp4"
}
```

### `POST /sync/audio`
Estimate audio-wave sync offsets for uploaded videos.

Request:

```json
{
  "video_paths": ["/workspace/uploads/a.mp4", "/workspace/uploads/b.mp4"],
  "sample_rate": 16000,
  "max_shift_seconds": 8.0
}
```

### `POST /sync/preview`
Returns sync analysis plus waveform previews for all provided videos.

Request:

```json
{
  "video_paths": ["/workspace/uploads/a.mp4", "/workspace/uploads/b.mp4"],
  "sample_rate": 16000,
  "max_shift_seconds": 8.0,
  "waveform_sample_rate": 8000,
  "waveform_points": 220
}
```

Response includes:
- `offsets_seconds`
- `trim_start_seconds`
- `common_window_seconds`
- `waveforms[]` (samples + duration per video)

### `POST /waveform`
Return downsampled waveform preview points for one video.

Request:

```json
{
  "video_path": "/workspace/uploads/a.mp4",
  "sample_rate": 8000,
  "points": 320
}
```

Response:

```json
{
  "samples": [0.02, 0.05, 0.18, "..."],
  "duration_seconds": 31.2
}
```

### `POST /analyze/config`
Analyze obstacle layout risk before render. Helpful to catch trap-prone courses.
Returns `risk_score` (0-100), `warning_count`, and `warnings[]` with structured obstacle references (`obstacle_index` / `obstacle_indices`). `warning_count` should equal `warnings.length`.

Request:

```json
{
  "config": { "... full songracer config ..." }
}
```

### `POST /preview/simulate`
Run a lightweight physics simulation preview for live builder playback (no media decode / no MP4 encoding).

Request:

```json
{
  "seed": 13,
  "render": {
    "width": 1080,
    "height": 1920,
    "world_height": 7600,
    "fps": 30,
    "duration_seconds": 12.0,
    "countdown_seconds": 0.0,
    "camera_follow": true
  },
  "racers": [
    { "name": "Singer 1", "x": 220, "y": 420, "radius": 96 },
    { "name": "Singer 2", "x": 370, "y": 460, "radius": 96 }
  ],
  "obstacles": [{ "... obstacle objects ..." }],
  "sample_fps": 15,
  "max_frames": 360
}
```

`sample_fps` and `max_frames` are optional; omitted values use backend defaults (also exposed via `/builder/capabilities`).
Out-of-range values are rejected with request-validation errors (HTTP 422), using the same bounds as `/builder/capabilities`.

Response includes sampled arrays for:
- `positions` (racer world coordinates),
- `leaders`,
- `camera_y`,
- `obstacle_visuals`,
- and metadata like `requested_sample_fps`, `requested_max_frames`, `sample_fps`, `sample_step_frames`, `sample_interval_seconds`, `total_source_frames`, `source_duration_seconds`, `goal_y`, `winner_index`, `winner_frame`, `returned_sample_frames`, `returned_last_sample_frame_index`, `sampling_coverage_ratio`, `sampled_coverage_ratio`, `returned_sample_duration_seconds`, `total_sample_frames`, `total_last_sample_frame_index`, `total_sample_duration_seconds`, `truncated`, `cache_hit`.
- winner fields use `-1`/`-1` when no winner is reached within simulated frames.

Sampling metadata note:
- `requested_sample_fps` / `requested_max_frames` reflect validated request values (explicit or defaults).
- `sample_step_frames` is integer frame-step size used internally.
- `sample_step_frames = ceil(render_fps / requested_sample_fps)`.
- returned `sample_fps` is the **effective** sampled rate (`render_fps / sample_step_frames`), so it can differ slightly but will not exceed requested `sample_fps`.
- when requested sample fps is above render fps, effective `sample_fps` equals render fps (`sample_step_frames = 1`).
- `frame_indices` are monotonically increasing sampled frame numbers starting at `0`, spaced by `sample_step_frames`.
- `returned_sample_frames = frame_indices.length`.
- `returned_last_sample_frame_index = frame_indices[-1]` (or `-1` when empty).
- `sampling_coverage_ratio = returned_sample_frames / total_source_frames`.
- `sampled_coverage_ratio = returned_sample_frames / total_sample_frames`.
- `returned_sample_duration_seconds = max(0, (returned_sample_frames - 1) * sample_interval_seconds)`.
- `total_last_sample_frame_index = (total_sample_frames - 1) * sample_step_frames`.
- `total_sample_duration_seconds = max(0, (total_sample_frames - 1) * sample_interval_seconds)`.
- `source_duration_seconds = max(0, (total_source_frames - 1) / fps)`.
- `total_sample_duration_seconds <= (total_source_frames - 1) / fps`.
- sampled durations can be shorter than source duration because sampling keeps every `sample_step_frames` frame.
- when only one sample frame is returned, `returned_sample_duration_seconds` is `0`.
- `returned_sample_frames <= requested_max_frames`.
- `truncated=false` means all sampled frames are returned (`total_sample_frames == frame_indices.length`).

Live preview notes:
- designed for interactive builder feedback (not final rendering),
- sampled output is capped by `sample_fps` + `max_frames`,
- frontend exposes sample-FPS / frame-cap controls and auto-preview toggle for responsiveness tuning,
- cache reuse applies to semantically identical request JSON (key ordering does not matter); changed preview knobs/layout produce fresh simulations,
- omitted sampling fields and explicitly provided default values map to the same cache identity,
- cache-hit responses keep the same payload content as fresh responses, except `cache_hit=true`,
- this includes stable sampled-length metadata (`returned_sample_frames`, `frame_indices.length`) across fresh/cache-hit responses,
- sampled-duration metadata (`returned_sample_duration_seconds`) is likewise stable across fresh/cache-hit responses,
- source-duration metadata (`source_duration_seconds`) is likewise stable across fresh/cache-hit responses,
- builder can read and clear preview-cache via `/preview/cache` + `/preview/cache/clear`,
- builder scrub row surfaces requested→effective sampled fps plus frame-step/requested-cap metadata (`sample_fps`, `sample_step_frames`, `requested_max_frames`),
- builder scrub row also shows sampled frame count (`returned_sample_frames/total_sample_frames`),
- builder scrub row also shows sampled coverage percentage (`returned_sample_frames / total_sample_frames`),
- builder scrub row also shows source coverage percentage (`returned_sample_frames / total_source_frames`),
- builder scrub row also shows full source timeline (`total_source_frames` / `source_duration_seconds`),
- builder scrub row also shows sampled time-window span (`returned_sample_duration_seconds/total_sample_duration_seconds`),
- truncation warning includes shown/total sampled frames plus requested frame cap (`requested_max_frames`) and sampled last-frame indices,
- use full render jobs for authoritative final video/audio output.

### `GET /preview/cache`
Returns current preview-cache usage:

```json
{
  "size": 3,
  "max_size": 8
}
```

### `POST /preview/cache/clear`
Clears preview-cache entries and returns counts:

```json
{
  "cleared": 3,
  "size": 0,
  "max_size": 8
}
```

If called again immediately, `cleared` should be `0` with `size` still `0` (idempotent clear behavior).

### Realtime Parkour Builder workflow

1. Drag obstacle types from palette onto the builder canvas.
2. Move obstacles by dragging handles; shift-click for multi-select.
3. Use layer panel to lock/hide entries and adjust ordering.
4. Use presets (`Starter`, `Rings`, `Gates`) for quick bootstrap.
5. Let auto-preview run (or click refresh manually) to inspect sampled simulation timeline.
6. Check integrated risk warnings and adjust layout.
7. Keep/inspect raw obstacle JSON (always synchronized).
8. Submit preview/final render jobs once satisfied.

Response:

```json
{
  "risk_score": 24,
  "warning_count": 2,
  "warnings": [
    {
      "level": "high",
      "code": "rows_too_close",
      "message": "Obstacle rows around y=980 and y=1060 are < 144px apart.",
      "obstacle_indices": [2, 3]
    }
  ]
}
```

### Project database CRUD

- `GET /projects` (use `?include_analysis=true` to include `risk_score` + `warning_count`)
- `POST /projects`
- `GET /projects/{project_id}`
- `PUT /projects/{project_id}`
- `DELETE /projects/{project_id}`
- `POST /projects/{project_id}/render`
- `POST /projects/{project_id}/sync`
- `GET /projects/{project_id}/analyze`

Backed by SQLite (`songracer.db`) for persistent frontend project storage.
Path can be overridden with `SONGRACER_DB_PATH`.

`GET /projects/{project_id}/analyze` returns the same risk payload as `/analyze/config` but for the currently saved project config.

Response:

```json
{
  "offsets_seconds": [0.0, -1.1],
  "trim_start_seconds": [0.0, 1.1],
  "common_window_seconds": 30.24
}
```

### `POST /jobs/from-config`
Create an async render job directly from inline config JSON (no pre-written config file needed).

Request:

```json
{
  "config": { "... full songracer config ..." },
  "output_path": "/workspace/outputs/my_job.mp4",
  "preview_scale": 0.35
}
```

Response:

```json
{
  "job_id": "abc123...",
  "state": "queued"
}
```

## Expected Frontend Workflow

1. Upload user videos to a server-side asset folder.
2. Build JSON config referencing those server-side paths.
3. Optionally call `/analyze/config` and adjust obstacle JSON if warnings are high-risk.
4. For realtime parkour editing, use drag-and-drop builder + `/preview/simulate` to iterate quickly.
5. Either:
   - write config file and call `/validate` + `/jobs`, or
   - submit inline config with optional preflight `/validate/config`, then `/jobs/from-config`.
6. Poll `/jobs/{job_id}` until `completed` or `failed`.
7. Download `/jobs/{job_id}/artifact` when complete.

## Frontend stack used

- Vue 3
- TypeScript
- Tailwind CSS

The frontend app in `frontend/` already implements:
- video upload flow,
- per-racer crop center selection,
- per-racer sync trims (+ one-click auto-sync via `/sync/audio`),
- per-racer waveform preview with trim marker (`/waveform`),
- realtime drag-and-drop parkour builder with live simulation preview (`/preview/simulate`),
- builder productivity controls: presets, lock/hide toggles, layer ordering, shift-select bulk delete, and keyboard shortcuts,
- hide toggles immediately refresh preview/risk using only currently visible obstacles,
- multi-select group drag (drag one selected handle to move full selection),
- builder history support (undo/redo buttons + keyboard shortcuts),
- clipboard copy/paste for obstacle groups,
- adjustable snap-size grid and align-X/align-Y helpers,
- obstacle JSON import/export actions scoped to builder layout,
- URL share action for builder layouts (obstacles encoded in query param),
- one-click clear/reset action for obstacle layout,
- camera focus helpers for selected obstacle and full-content fit,
- local browser persistence for builder tuning preferences (grid/snap/preview knobs),
- palette labels/types can be sourced from `/templates/obstacle-types`,
- preset buttons resolve from `/templates/obstacles` and gracefully fallback to local defaults,
- procedural stream generation is available via `/templates/obstacles/generate` (append/replace in UI),
- risk-targeted procedural generation is available via `/templates/obstacles/generate-safe`,
- generated stream mixes multiple obstacle families (rect/moving/rings/spinners/circles/pendulums/gates),
- UI includes one-click random seed for quick stream iteration,
- risk warning rows are clickable and focus linked obstacle(s) in the builder (with linked obstacle index hints),
- safe generation status badge summarizes returned risk/attempts/acceptance and is invalidated after subsequent layout/visibility edits,
- UI can display live min/max limits from `/builder/capabilities` for user guidance,
- project save/load/update/delete against backend DB CRUD,
- direct preview/final render submission from saved projects,
- preview and final job submission,
- live job list polling,
- artifact preview panel.

## Storage configuration

Backend paths:
- uploads/job configs/outputs root: `SONGRACER_STORAGE_DIR`
- SQLite DB file: `SONGRACER_DB_PATH`

If configured paths are not writable, backend uses writable temp fallbacks.

## Notes on countdown/victory effects

- Backend render pipeline includes:
  - stylized countdown overlay (top HUD),
  - winner overlay card,
  - countdown + victory SFX.
- SFX can be supplied as files via config:
  - `audio.countdown_sfx_path`
  - `audio.victory_sfx_path`
  (otherwise synthesized defaults are used).
