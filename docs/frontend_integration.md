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
Run a render job immediately (sync request in v0.1).

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

## Expected Frontend Workflow

1. Upload user videos to a server-side asset folder.
2. Build JSON config referencing those server-side paths.
3. Call `/validate`.
4. Call `/render`.
5. Serve/download resulting MP4.

## Recommended Next Step for Production

- Replace sync `/render` with async jobs:
  - `POST /jobs` -> returns `job_id`
  - `GET /jobs/{job_id}` -> status/progress
  - `GET /jobs/{job_id}/artifact` -> MP4 download

This avoids request timeouts for longer renders (e.g. 30s @ 1080x1920).
