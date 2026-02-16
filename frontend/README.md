# SongRacer Frontend

Vue 3 + TypeScript + Tailwind control panel for SongRacer backend.

## Run

```bash
npm install
npm run dev
```

Set backend API base URL to `http://localhost:8080` in the UI.

If UI shows backend offline / connection refused, start backend:

```bash
python3 -m uvicorn songracer.api:app --host 0.0.0.0 --port 8080 --reload
```

## Features

- Upload singer videos (`/uploads`)
- Auto-sync singers by audio waveform with bundled waveform preview (`/sync/preview`)
- Waveform preview for each singer (`/waveform`)
- Set per-singer face center by clicking preview (crop center sent to backend)
- Save/load/update/delete projects using backend database CRUD (`/projects`)
- Trigger preview/final jobs directly from saved projects (`/projects/{id}/render`)
- Re-sync saved projects directly from DB project card (`/projects/{id}/sync`)
- Submit preview/final render jobs (`/jobs/from-config`)
- Poll and display async job states
- Open completed MP4 artifacts directly in app

## Build

```bash
npm run build
```
