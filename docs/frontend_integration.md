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
3. Either:
   - write config file and call `/validate` + `/jobs`, or
   - submit inline config using `/jobs/from-config`.
4. Poll `/jobs/{job_id}` until `completed` or `failed`.
5. Download `/jobs/{job_id}/artifact` when complete.

## Frontend stack used

- Vue 3
- TypeScript
- Tailwind CSS

The frontend app in `frontend/` already implements:
- video upload flow,
- per-racer crop center selection,
- preview and final job submission,
- live job list polling,
- artifact preview panel.

## Notes on countdown/victory effects

- Backend render pipeline includes:
  - stylized countdown overlay (top HUD),
  - winner overlay card,
  - countdown + victory SFX.
- SFX can be supplied as files via config:
  - `audio.countdown_sfx_path`
  - `audio.victory_sfx_path`
  (otherwise synthesized defaults are used).
