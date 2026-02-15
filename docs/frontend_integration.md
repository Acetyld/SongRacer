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

## Expected Frontend Workflow

1. Upload user videos to a server-side asset folder.
2. Build JSON config referencing those server-side paths.
3. Call `/validate`.
4. Call `/jobs` to create render.
5. Poll `/jobs/{job_id}` until `completed` or `failed`.
6. Download `/jobs/{job_id}/artifact` when complete.
