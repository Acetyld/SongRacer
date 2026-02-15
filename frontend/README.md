# SongRacer Frontend

Vue 3 + TypeScript + Tailwind control panel for SongRacer backend.

## Run

```bash
npm install
npm run dev
```

Set backend API base URL to `http://localhost:8080` in the UI.

## Features

- Upload singer videos (`/uploads`)
- Set per-singer face center by clicking preview (crop center sent to backend)
- Submit preview/final render jobs (`/jobs/from-config`)
- Poll and display async job states
- Open completed MP4 artifacts directly in app

## Build

```bash
npm run build
```
