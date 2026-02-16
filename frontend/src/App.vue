<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

type RacerForm = {
  id: string
  name: string
  localFile?: File
  localPreviewUrl?: string
  uploadedPath?: string
  cropCenterX: number
  cropCenterY: number
  syncTrimStartSeconds: number
  syncOffsetSeconds: number
}

type JobRow = {
  job_id: string
  state: string
  created_at?: string
  output_path?: string
  error?: string | null
}

const apiBase = ref('http://localhost:8080')
const title = ref('SongRacer Job')
const duration = ref(24)
const countdown = ref(3)
const winnerHold = ref(3)
const backgroundColor = ref('#6EC6FF')
const previewScale = ref(0.32)
const finalScale = ref(1.0)
const worldHeight = ref(7600)
const syncCommonWindowSeconds = ref(0)
const isBusy = ref(false)
const racers = ref<RacerForm[]>([])
const jobs = ref<JobRow[]>([])
const statusMessage = ref('')
const previewArtifactUrl = ref<string | null>(null)
const backendOnline = ref(true)
const obstacleJson = ref(
  JSON.stringify(
    [
      { type: 'rect', x: 260, y: 860, width: 320, height: 30, angle_deg: -22, fill_color: '#111A31' },
      { type: 'moving_rect', x: 760, y: 940, width: 310, height: 30, angle_deg: 18, amplitude: 120, frequency_hz: 0.23, axis: 'x', fill_color: '#1B2844' },
      { type: 'ring_gap', x: 540, y: 1260, radius: 165, thickness: 36, rotation_speed_deg: 80, gap_size_deg: 62, fill_color: '#09101F' },
      { type: 'spinner', x: 540, y: 1640, length: 320, thickness: 24, spin_speed_deg: 160, fill_color: '#151B30' },
      { type: 'one_way_gate', x: 540, y: 1880, width: 620, height: 26, one_way: 'down', fill_color: '#1B2A40' },
    ],
    null,
    2,
  ),
)

let pollHandle: number | null = null

const uploadedReady = computed(() => racers.value.length > 0 && racers.value.every((r) => !!r.uploadedPath))
const canRender = computed(() => uploadedReady.value && !isBusy.value)

function handleFiles(ev: Event) {
  const input = ev.target as HTMLInputElement
  const files = input.files
  if (!files) return
  for (const file of Array.from(files)) {
    const id = `${Date.now()}_${Math.random().toString(16).slice(2)}`
    racers.value.push({
      id,
      name: file.name.replace(/\.[^/.]+$/, ''),
      localFile: file,
      localPreviewUrl: URL.createObjectURL(file),
      cropCenterX: 0.5,
      cropCenterY: 0.45,
      syncTrimStartSeconds: 0,
      syncOffsetSeconds: 0,
    })
  }
  input.value = ''
}

async function uploadAll() {
  isBusy.value = true
  statusMessage.value = 'Uploading videos...'
  try {
    for (const racer of racers.value) {
      if (racer.uploadedPath || !racer.localFile) continue
      const form = new FormData()
      form.append('file', racer.localFile)
      const resp = await fetch(`${apiBase.value}/uploads`, {
        method: 'POST',
        body: form,
      })
      if (!resp.ok) {
        throw new Error(await resp.text())
      }
      const payload = await resp.json()
      racer.uploadedPath = payload.path
    }
    backendOnline.value = true
    statusMessage.value = 'Upload complete.'
  } catch (err) {
    backendOnline.value = false
    statusMessage.value = `Upload failed: ${String(err)}`
  } finally {
    isBusy.value = false
  }
}

function setCrop(racer: RacerForm, e: MouseEvent) {
  const target = e.currentTarget as HTMLElement
  const rect = target.getBoundingClientRect()
  const x = (e.clientX - rect.left) / rect.width
  const y = (e.clientY - rect.top) / rect.height
  racer.cropCenterX = Math.min(1, Math.max(0, x))
  racer.cropCenterY = Math.min(1, Math.max(0, y))
}

function buildInlineConfig() {
  let obstacles: unknown = []
  try {
    obstacles = JSON.parse(obstacleJson.value || '[]')
    if (!Array.isArray(obstacles)) {
      throw new Error('Obstacle JSON must be an array')
    }
  } catch (err) {
    throw new Error(`Invalid obstacle JSON: ${String(err)}`)
  }
  return {
    seed: 13,
    sync_common_window_seconds: syncCommonWindowSeconds.value,
    render: {
      width: 1080,
      height: 1920,
      world_height: worldHeight.value,
      fps: 30,
      duration_seconds: duration.value,
      countdown_seconds: countdown.value,
      goal_margin: 150,
      camera_follow: true,
      camera_lead_ratio: 0.35,
      auto_end_on_winner: true,
      winner_hold_seconds: winnerHold.value,
      obstacle_stream_spacing: 980,
      obstacle_stream_jitter_x: 135,
      obstacle_stream_repeats: 5,
    },
    background: {
      mode: 'solid',
      solid_color: backgroundColor.value,
    },
    racers: racers.value.map((r, idx) => ({
      name: r.name || `Singer${idx + 1}`,
      video_path: r.uploadedPath,
      x: 220 + idx * 150,
      y: 420 + (idx % 2) * 40,
      radius: 96,
      crop_center_x: r.cropCenterX,
      crop_center_y: r.cropCenterY,
      sync_offset_seconds: r.syncOffsetSeconds,
      sync_trim_start_seconds: r.syncTrimStartSeconds,
    })),
    obstacles,
  }
}

async function createJob(isPreview: boolean) {
  if (!canRender.value) return
  isBusy.value = true
  statusMessage.value = isPreview ? 'Submitting preview job...' : 'Submitting final job...'
  try {
    const ts = new Date().toISOString().replace(/[:.]/g, '-')
    const out = `/workspace/outputs/${title.value || 'songracer'}_${isPreview ? 'preview' : 'final'}_${ts}.mp4`
    const payload = {
      config: buildInlineConfig(),
      output_path: out,
      preview_scale: isPreview ? previewScale.value : finalScale.value,
    }
    const resp = await fetch(`${apiBase.value}/jobs/from-config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!resp.ok) {
      throw new Error(await resp.text())
    }
    backendOnline.value = true
    statusMessage.value = isPreview
      ? 'Preview job submitted.'
      : 'Final job submitted.'
    await refreshJobs()
  } catch (err) {
    backendOnline.value = false
    statusMessage.value = `Job submit failed: ${String(err)}`
  } finally {
    isBusy.value = false
  }
}

async function refreshJobs() {
  try {
    const resp = await fetch(`${apiBase.value}/jobs`)
    if (!resp.ok) {
      backendOnline.value = false
      return
    }
    const data = await resp.json()
    jobs.value = (data.jobs || []).slice().reverse()
    backendOnline.value = true
  } catch (_err) {
    backendOnline.value = false
  }
}

function openArtifact(job: JobRow) {
  previewArtifactUrl.value = `${apiBase.value}/jobs/${job.job_id}/artifact?ts=${Date.now()}`
}

async function autoSyncAudio() {
  if (!uploadedReady.value) {
    statusMessage.value = 'Upload videos before auto sync.'
    return
  }
  isBusy.value = true
  statusMessage.value = 'Analyzing waveform alignment...'
  try {
    const videoPaths = racers.value.map((r) => r.uploadedPath as string)
    const resp = await fetch(`${apiBase.value}/sync/audio`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        video_paths: videoPaths,
        sample_rate: 16000,
        max_shift_seconds: 8.0,
      }),
    })
    if (!resp.ok) {
      throw new Error(await resp.text())
    }
    const payload = await resp.json()
    const offsets: number[] = payload.offsets_seconds || []
    const trims: number[] = payload.trim_start_seconds || []
    const commonWindow = Number(payload.common_window_seconds || 0)
    racers.value.forEach((racer, idx) => {
      racer.syncOffsetSeconds = Number(offsets[idx] ?? 0)
      racer.syncTrimStartSeconds = Number(trims[idx] ?? 0)
    })
    syncCommonWindowSeconds.value = commonWindow
    if (commonWindow > 0) {
      duration.value = Math.min(duration.value, commonWindow)
    }
    backendOnline.value = true
    statusMessage.value = `Auto sync applied. Common overlap ${commonWindow.toFixed(2)}s.`
  } catch (err) {
    backendOnline.value = false
    statusMessage.value = `Auto sync failed: ${String(err)}`
  } finally {
    isBusy.value = false
  }
}

onMounted(() => {
  refreshJobs()
  pollHandle = window.setInterval(refreshJobs, 2000)
})

onUnmounted(() => {
  if (pollHandle) {
    clearInterval(pollHandle)
    pollHandle = null
  }
  for (const racer of racers.value) {
    if (racer.localPreviewUrl) URL.revokeObjectURL(racer.localPreviewUrl)
  }
})
</script>

<template>
  <main class="min-h-screen bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950 p-6">
    <div class="mx-auto max-w-7xl space-y-6">
      <header class="rounded-2xl border border-cyan-500/30 bg-slate-900/80 p-6 shadow-2xl shadow-cyan-900/20">
        <h1 class="text-3xl font-bold tracking-tight text-cyan-300">SongRacer Studio</h1>
        <p class="mt-2 text-slate-300">
          Vue + TypeScript + Tailwind frontend for uploads, crop-center control, preview renders, and async job management.
        </p>
        <p
          v-if="!backendOnline"
          class="mt-3 rounded-lg border border-rose-400/40 bg-rose-900/40 px-3 py-2 text-sm text-rose-200"
        >
          Backend offline at {{ apiBase }}. Start API and refresh jobs.
        </p>
      </header>

      <section class="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <div class="space-y-6">
          <div class="rounded-2xl border border-slate-700 bg-slate-900/80 p-5">
            <div class="mb-3 flex items-center justify-between">
              <h2 class="text-xl font-semibold text-slate-100">Singer Videos</h2>
              <label class="cursor-pointer rounded-lg bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-400">
                Add Videos
                <input type="file" class="hidden" multiple accept="video/*" @change="handleFiles" />
              </label>
            </div>

            <div v-if="racers.length === 0" class="rounded-lg border border-dashed border-slate-600 p-8 text-center text-slate-400">
              No videos selected yet.
            </div>

            <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              <article v-for="(racer, idx) in racers" :key="racer.id" class="rounded-xl border border-slate-700 bg-slate-800/70 p-3">
                <div class="mb-2 flex items-center justify-between">
                  <span class="text-xs text-slate-400">Singer {{ idx + 1 }}</span>
                  <span class="text-xs font-medium" :class="racer.uploadedPath ? 'text-emerald-300' : 'text-amber-300'">
                    {{ racer.uploadedPath ? 'Uploaded' : 'Pending upload' }}
                  </span>
                </div>
                <input
                  v-model="racer.name"
                  class="mb-3 w-full rounded-md border border-slate-600 bg-slate-900 px-2 py-1.5 text-sm text-slate-100 outline-none focus:border-cyan-400"
                />
                <div
                  class="relative mx-auto h-64 w-40 overflow-hidden rounded-xl border border-slate-600 bg-black"
                  @click="setCrop(racer, $event)"
                >
                  <video
                    v-if="racer.localPreviewUrl"
                    :src="racer.localPreviewUrl"
                    class="h-full w-full object-cover"
                    muted
                    autoplay
                    loop
                    playsinline
                  />
                  <div
                    class="pointer-events-none absolute h-6 w-6 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-cyan-300 shadow-lg shadow-cyan-400/40"
                    :style="{ left: `${racer.cropCenterX * 100}%`, top: `${racer.cropCenterY * 100}%` }"
                  />
                </div>
                <p class="mt-2 text-[11px] text-slate-400">
                  Click preview to set face center ({{ racer.cropCenterX.toFixed(2) }}, {{ racer.cropCenterY.toFixed(2) }})
                </p>
                <label class="mt-2 block text-[11px] text-slate-300">
                  Sync trim start (sec)
                  <input
                    v-model.number="racer.syncTrimStartSeconds"
                    type="number"
                    step="0.01"
                    class="mt-1 w-full rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs text-slate-100"
                  />
                </label>
                <p class="mt-1 text-[10px] text-slate-500">
                  Relative offset: {{ racer.syncOffsetSeconds.toFixed(2) }}s
                </p>
              </article>
            </div>
          </div>

          <div class="rounded-2xl border border-slate-700 bg-slate-900/80 p-5">
            <h2 class="mb-3 text-xl font-semibold text-slate-100">Render Controls</h2>
            <div class="grid gap-3 md:grid-cols-2">
              <label class="text-sm text-slate-300">
                API Base
                <input v-model="apiBase" class="mt-1 w-full rounded-md border border-slate-600 bg-slate-900 px-2 py-1.5 text-slate-100" />
              </label>
              <label class="text-sm text-slate-300">
                Job Title
                <input v-model="title" class="mt-1 w-full rounded-md border border-slate-600 bg-slate-900 px-2 py-1.5 text-slate-100" />
              </label>
              <label class="text-sm text-slate-300">
                Duration (cap seconds)
                <input v-model.number="duration" type="number" min="1" class="mt-1 w-full rounded-md border border-slate-600 bg-slate-900 px-2 py-1.5 text-slate-100" />
              </label>
              <label class="text-sm text-slate-300">
                World Height
                <input v-model.number="worldHeight" type="number" min="1920" class="mt-1 w-full rounded-md border border-slate-600 bg-slate-900 px-2 py-1.5 text-slate-100" />
              </label>
              <label class="text-sm text-slate-300">
                Countdown (seconds)
                <input v-model.number="countdown" type="number" min="0" class="mt-1 w-full rounded-md border border-slate-600 bg-slate-900 px-2 py-1.5 text-slate-100" />
              </label>
              <label class="text-sm text-slate-300">
                Winner Hold (seconds)
                <input v-model.number="winnerHold" type="number" min="0" class="mt-1 w-full rounded-md border border-slate-600 bg-slate-900 px-2 py-1.5 text-slate-100" />
              </label>
              <label class="text-sm text-slate-300">
                Preview Scale
                <input v-model.number="previewScale" type="number" min="0.05" max="1" step="0.01" class="mt-1 w-full rounded-md border border-slate-600 bg-slate-900 px-2 py-1.5 text-slate-100" />
              </label>
              <label class="text-sm text-slate-300">
                Final Scale
                <input v-model.number="finalScale" type="number" min="0.05" max="1" step="0.01" class="mt-1 w-full rounded-md border border-slate-600 bg-slate-900 px-2 py-1.5 text-slate-100" />
              </label>
              <label class="text-sm text-slate-300">
                Background Color
                <input v-model="backgroundColor" type="color" class="mt-1 h-10 w-full rounded-md border border-slate-600 bg-slate-900 px-1 py-1" />
              </label>
            </div>

            <div class="mt-4 flex flex-wrap gap-2">
              <button
                class="rounded-lg bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-400 disabled:opacity-50"
                :disabled="isBusy || racers.length === 0"
                @click="uploadAll"
              >
                Upload Videos
              </button>
              <button
                class="rounded-lg bg-fuchsia-500 px-4 py-2 text-sm font-semibold text-white hover:bg-fuchsia-400 disabled:opacity-50"
                :disabled="!uploadedReady || isBusy"
                @click="autoSyncAudio"
              >
                Auto Sync Audio
              </button>
              <button
                class="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-400 disabled:opacity-50"
                :disabled="!canRender"
                @click="createJob(true)"
              >
                Render Preview
              </button>
              <button
                class="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-50"
                :disabled="!canRender"
                @click="createJob(false)"
              >
                Render Final
              </button>
            </div>
            <div class="mt-4">
              <label class="mb-1 block text-sm text-slate-300">Obstacle JSON (full control)</label>
              <textarea
                v-model="obstacleJson"
                rows="10"
                class="w-full rounded-md border border-slate-600 bg-slate-950 px-2 py-2 text-xs text-slate-100"
              />
            </div>
            <p class="mt-3 text-sm text-slate-300">{{ statusMessage }}</p>
          </div>
        </div>

        <aside class="space-y-6">
          <div class="rounded-2xl border border-slate-700 bg-slate-900/80 p-5">
            <h2 class="mb-3 text-xl font-semibold text-slate-100">Jobs</h2>
            <div class="max-h-[420px] space-y-2 overflow-auto pr-1">
              <article v-for="job in jobs" :key="job.job_id" class="rounded-lg border border-slate-700 bg-slate-800/70 p-3">
                <p class="text-xs text-slate-400">{{ job.job_id.slice(0, 12) }}...</p>
                <p class="text-sm font-semibold" :class="job.state === 'completed' ? 'text-emerald-300' : job.state === 'failed' ? 'text-rose-300' : 'text-amber-300'">
                  {{ job.state }}
                </p>
                <p v-if="job.error" class="mt-1 text-xs text-rose-300">{{ job.error }}</p>
                <button
                  v-if="job.state === 'completed'"
                  class="mt-2 rounded bg-slate-700 px-3 py-1 text-xs hover:bg-slate-600"
                  @click="openArtifact(job)"
                >
                  Open Artifact
                </button>
              </article>
              <p v-if="jobs.length === 0" class="text-sm text-slate-400">No jobs yet.</p>
            </div>
          </div>

          <div class="rounded-2xl border border-slate-700 bg-slate-900/80 p-5">
            <h2 class="mb-3 text-xl font-semibold text-slate-100">Artifact Preview</h2>
            <video
              v-if="previewArtifactUrl"
              :src="previewArtifactUrl"
              controls
              class="aspect-[9/16] w-full rounded-lg border border-slate-600 bg-black"
            />
            <p v-else class="text-sm text-slate-400">Render a job and open its artifact to preview here.</p>
          </div>
        </aside>
      </section>
    </div>
  </main>
</template>
