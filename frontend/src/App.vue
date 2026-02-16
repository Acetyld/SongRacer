<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import ParkourBuilder from './components/ParkourBuilder.vue'

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
  waveformSamples?: number[]
  waveformDurationSeconds?: number
}

type JobRow = {
  job_id: string
  state: string
  created_at?: string
  output_path?: string
  error?: string | null
}

type ProjectRow = {
  id: number
  name: string
  created_at?: string
  updated_at?: string
  risk_score?: number
  warning_count?: number
  config?: Record<string, unknown>
}

type SystemInfo = {
  storage_root?: string
  upload_dir?: string
  job_config_dir?: string
  output_dir?: string
  db_path?: string
}

type RangeCaps = {
  min: number
  max: number
  default: number
}

const apiBase = ref('http://localhost:8080')
const title = ref('SongRacer Job')
const duration = ref(24)
const countdown = ref(3)
const winnerHold = ref(3)
const backgroundColor = ref('#6EC6FF')
const previewScale = ref(0.32)
const finalScale = ref(1.0)
const outputPathInput = ref('')
const worldHeight = ref(7600)
const worldHeightCaps = ref<RangeCaps>({ min: 256, max: 20000, default: 6200 })
const syncCommonWindowSeconds = ref(0)
const isBusy = ref(false)
const racers = ref<RacerForm[]>([])
const jobs = ref<JobRow[]>([])
const statusMessage = ref('')
const previewArtifactUrl = ref<string | null>(null)
const backendOnline = ref(true)
const loadingWaveforms = ref(false)
const projects = ref<ProjectRow[]>([])
const projectNameInput = ref('My SongRacer Project')
const activeProjectId = ref<number | null>(null)
const systemInfo = ref<SystemInfo>({})
const riskScore = ref<number | null>(null)
const riskWarnings = ref<Array<{ level: string; code: string; message: string }>>([])
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
const builderPreviewRacers = computed(() => {
  if (racers.value.length > 0) {
    return racers.value.map((r, idx) => ({
      name: r.name || `Singer ${idx + 1}`,
      x: 220 + idx * 150,
      y: 420 + (idx % 2) * 40,
      radius: 96,
    }))
  }
  return Array.from({ length: 5 }).map((_, idx) => ({
    name: `Singer ${idx + 1}`,
    x: 220 + idx * 150,
    y: 420 + (idx % 2) * 40,
    radius: 96,
  }))
})

function pointsForWaveform(samples: number[] | undefined, width = 220, height = 56): string {
  if (!samples || samples.length === 0) {
    return `0,${height / 2} ${width},${height / 2}`
  }
  return samples
    .map((s, idx) => {
      const x = (idx / (samples.length - 1 || 1)) * width
      const y = height - Math.max(0, Math.min(1, s)) * height
      return `${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(' ')
}

function trimMarkerX(racer: RacerForm, width = 220): number {
  const duration = racer.waveformDurationSeconds || 0
  if (duration <= 0) return 0
  return Math.max(0, Math.min(width, (racer.syncTrimStartSeconds / duration) * width))
}

function normalizeRangeCaps(raw: unknown, fallback: RangeCaps): RangeCaps {
  const obj = raw as Record<string, unknown> | null
  const minCandidate = Number(obj?.min)
  const maxCandidate = Number(obj?.max)
  const defaultCandidate = Number(obj?.default)
  let min = Number.isFinite(minCandidate) ? minCandidate : fallback.min
  let max = Number.isFinite(maxCandidate) ? maxCandidate : fallback.max
  if (max < min) {
    const swap = min
    min = max
    max = swap
  }
  const fallbackDefault = Math.max(min, Math.min(max, fallback.default))
  const safeDefault = Number.isFinite(defaultCandidate) ? defaultCandidate : fallbackDefault
  return {
    min,
    max,
    default: Math.max(min, Math.min(max, safeDefault)),
  }
}

function normalizeWorldHeight(value: number, fallback = worldHeightCaps.value.default): number {
  const base = Number.isFinite(value) ? value : fallback
  const rounded = Math.round(base)
  return Math.max(worldHeightCaps.value.min, Math.min(worldHeightCaps.value.max, rounded))
}

function waveformColor(idx: number): string {
  const palette = ['#22D3EE', '#A78BFA', '#34D399', '#F472B6', '#FBBF24', '#60A5FA']
  return palette[idx % palette.length] ?? '#22D3EE'
}

function syncOverlayWindowSeconds(): number {
  if (syncCommonWindowSeconds.value > 0.01) {
    return syncCommonWindowSeconds.value
  }
  let best = 0
  for (const r of racers.value) {
    const d = (r.waveformDurationSeconds || 0) - r.syncTrimStartSeconds
    if (d > best) best = d
  }
  return Math.max(1, best)
}

function alignedWavePoints(racer: RacerForm, width = 320, height = 110): string {
  const samples = racer.waveformSamples
  if (!samples || samples.length <= 1) {
    return `0,${height / 2} ${width},${height / 2}`
  }
  const duration = racer.waveformDurationSeconds || 0
  if (duration <= 0) {
    return `0,${height / 2} ${width},${height / 2}`
  }
  const winSec = syncOverlayWindowSeconds()
  const pts: string[] = []
  for (let idx = 0; idx < samples.length; idx++) {
    const tRaw = (idx / (samples.length - 1)) * duration
    const tAligned = tRaw - racer.syncTrimStartSeconds
    if (tAligned < 0 || tAligned > winSec) continue
    const x = (tAligned / winSec) * width
    const sample = samples[idx] ?? 0
    const y = height - Math.max(0, Math.min(1, sample)) * height
    pts.push(`${x.toFixed(2)},${y.toFixed(2)}`)
  }
  if (pts.length < 2) {
    return `0,${height / 2} ${width},${height / 2}`
  }
  return pts.join(' ')
}

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
      world_height: normalizeWorldHeight(worldHeight.value),
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
    const payload: Record<string, unknown> = {
      config: buildInlineConfig(),
      preview_scale: isPreview ? previewScale.value : finalScale.value,
    }
    if (outputPathInput.value.trim()) {
      payload.output_path = outputPathInput.value.trim()
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
    const resp = await fetch(`${apiBase.value}/sync/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        video_paths: videoPaths,
        sample_rate: 16000,
        max_shift_seconds: 8.0,
        waveform_sample_rate: 8000,
        waveform_points: 220,
      }),
    })
    if (!resp.ok) {
      throw new Error(await resp.text())
    }
    const payload = await resp.json()
    const offsets: number[] = payload.offsets_seconds || []
    const trims: number[] = payload.trim_start_seconds || []
    const commonWindow = Number(payload.common_window_seconds || 0)
    const waveforms: Array<{ samples?: number[]; duration_seconds?: number }> =
      payload.waveforms || []
    racers.value.forEach((racer, idx) => {
      racer.syncOffsetSeconds = Number(offsets[idx] ?? 0)
      racer.syncTrimStartSeconds = Number(trims[idx] ?? 0)
      const wf = waveforms[idx]
      if (wf) {
        racer.waveformSamples = wf.samples || []
        racer.waveformDurationSeconds = Number(wf.duration_seconds || 0)
      }
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

async function analyzeCourseRisk() {
  try {
    const resp = await fetch(`${apiBase.value}/analyze/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ config: buildInlineConfig() }),
    })
    if (!resp.ok) throw new Error(await resp.text())
    const body = await resp.json()
    riskScore.value = Number(body.risk_score ?? 0)
    riskWarnings.value = Array.isArray(body.warnings) ? body.warnings : []
    statusMessage.value = `Course analysis done. Risk score ${riskScore.value}.`
    backendOnline.value = true
  } catch (err) {
    backendOnline.value = false
    statusMessage.value = `Course analysis failed: ${String(err)}`
  }
}

async function validateCurrentConfig() {
  try {
    const resp = await fetch(`${apiBase.value}/validate/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ config: buildInlineConfig() }),
    })
    if (!resp.ok) throw new Error(await resp.text())
    const body = await resp.json()
    statusMessage.value = `Config valid (${body.racers} racers, ${body.obstacles} obstacles).`
    backendOnline.value = true
  } catch (err) {
    backendOnline.value = false
    statusMessage.value = `Config validation failed: ${String(err)}`
  }
}

async function loadWaveforms() {
  if (!uploadedReady.value) {
    statusMessage.value = 'Upload videos before waveform preview.'
    return
  }
  loadingWaveforms.value = true
  try {
    await Promise.all(
      racers.value.map(async (racer) => {
        const resp = await fetch(`${apiBase.value}/waveform`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            video_path: racer.uploadedPath,
            sample_rate: 8000,
            points: 220,
          }),
        })
        if (!resp.ok) throw new Error(await resp.text())
        const body = await resp.json()
        racer.waveformSamples = body.samples || []
        racer.waveformDurationSeconds = Number(body.duration_seconds || 0)
      }),
    )
    backendOnline.value = true
    statusMessage.value = 'Waveforms loaded.'
  } catch (err) {
    backendOnline.value = false
    statusMessage.value = `Waveform preview failed: ${String(err)}`
  } finally {
    loadingWaveforms.value = false
  }
}

async function refreshProjects() {
  try {
    const resp = await fetch(`${apiBase.value}/projects?include_analysis=true`)
    if (!resp.ok) {
      backendOnline.value = false
      return
    }
    const body = await resp.json()
    projects.value = body.projects || []
    backendOnline.value = true
  } catch (_err) {
    backendOnline.value = false
  }
}

async function refreshSystemInfo() {
  try {
    const resp = await fetch(`${apiBase.value}/system/info`)
    if (!resp.ok) {
      backendOnline.value = false
      return
    }
    systemInfo.value = await resp.json()
    backendOnline.value = true
  } catch (_err) {
    backendOnline.value = false
  }
}

async function refreshBuilderCapabilities() {
  try {
    const resp = await fetch(`${apiBase.value}/builder/capabilities`)
    if (!resp.ok) {
      backendOnline.value = false
      return
    }
    const body = await resp.json()
    worldHeightCaps.value = normalizeRangeCaps(
      (body as Record<string, any>)?.preview?.world_height,
      worldHeightCaps.value,
    )
    worldHeight.value = normalizeWorldHeight(worldHeight.value)
    backendOnline.value = true
  } catch (_err) {
    backendOnline.value = false
  }
}

async function saveProject() {
  isBusy.value = true
  try {
    const payload = {
      name: projectNameInput.value || 'SongRacer Project',
      config: buildInlineConfig(),
    }
    const resp = await fetch(
      activeProjectId.value ? `${apiBase.value}/projects/${activeProjectId.value}` : `${apiBase.value}/projects`,
      {
        method: activeProjectId.value ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
    )
    if (!resp.ok) throw new Error(await resp.text())
    const body = await resp.json()
    activeProjectId.value = Number(body.id)
    projectNameInput.value = String(body.name)
    await refreshProjects()
    backendOnline.value = true
    statusMessage.value = 'Project saved to database.'
  } catch (err) {
    backendOnline.value = false
    statusMessage.value = `Save project failed: ${String(err)}`
  } finally {
    isBusy.value = false
  }
}

function applyConfigToForm(cfg: Record<string, any>) {
  const render = cfg.render || {}
  const bg = cfg.background || {}
  duration.value = Number(render.duration_seconds ?? duration.value)
  countdown.value = Number(render.countdown_seconds ?? countdown.value)
  winnerHold.value = Number(render.winner_hold_seconds ?? winnerHold.value)
  worldHeight.value = normalizeWorldHeight(Number(render.world_height ?? worldHeight.value))
  backgroundColor.value = String(bg.solid_color ?? backgroundColor.value)
  syncCommonWindowSeconds.value = Number(cfg.sync_common_window_seconds ?? 0)
  obstacleJson.value = JSON.stringify(cfg.obstacles || [], null, 2)
  const loadedRacers = Array.isArray(cfg.racers) ? cfg.racers : []
  racers.value = loadedRacers.map((r: any, idx: number) => ({
    id: `${Date.now()}_${idx}_${Math.random().toString(16).slice(2)}`,
    name: String(r.name ?? `Singer${idx + 1}`),
    uploadedPath: String(r.video_path ?? ''),
    cropCenterX: Number(r.crop_center_x ?? 0.5),
    cropCenterY: Number(r.crop_center_y ?? 0.5),
    syncTrimStartSeconds: Number(r.sync_trim_start_seconds ?? 0),
    syncOffsetSeconds: Number(r.sync_offset_seconds ?? 0),
  }))
}

async function loadProject(projectId: number) {
  isBusy.value = true
  try {
    const resp = await fetch(`${apiBase.value}/projects/${projectId}`)
    if (!resp.ok) throw new Error(await resp.text())
    const body = await resp.json()
    activeProjectId.value = Number(body.id)
    projectNameInput.value = String(body.name)
    applyConfigToForm(body.config || {})
    backendOnline.value = true
    statusMessage.value = `Loaded project #${projectId}.`
  } catch (err) {
    backendOnline.value = false
    statusMessage.value = `Load project failed: ${String(err)}`
  } finally {
    isBusy.value = false
  }
}

async function removeProject(projectId: number) {
  try {
    const resp = await fetch(`${apiBase.value}/projects/${projectId}`, { method: 'DELETE' })
    if (!resp.ok) throw new Error(await resp.text())
    if (activeProjectId.value === projectId) {
      activeProjectId.value = null
    }
    await refreshProjects()
    statusMessage.value = `Deleted project #${projectId}.`
    backendOnline.value = true
  } catch (err) {
    backendOnline.value = false
    statusMessage.value = `Delete project failed: ${String(err)}`
  }
}

function updateProjectRiskLocal(projectId: number, score: number, count: number) {
  projects.value = projects.value.map((p) =>
    p.id === projectId ? { ...p, risk_score: score, warning_count: count } : p,
  )
}

async function analyzeSavedProject(projectId: number) {
  isBusy.value = true
  statusMessage.value = `Analyzing project #${projectId} obstacle safety...`
  try {
    const resp = await fetch(`${apiBase.value}/projects/${projectId}/analyze`)
    if (!resp.ok) throw new Error(await resp.text())
    const body = await resp.json()
    const score = Number(body.risk_score ?? 0)
    const count = Number(body.warning_count ?? 0)
    updateProjectRiskLocal(projectId, score, count)
    statusMessage.value = `Project #${projectId} risk ${score} (${count} warnings).`
    backendOnline.value = true
  } catch (err) {
    backendOnline.value = false
    statusMessage.value = `Project analysis failed: ${String(err)}`
  } finally {
    isBusy.value = false
  }
}

async function exportProject(projectId: number) {
  try {
    const resp = await fetch(`${apiBase.value}/projects/${projectId}/export`)
    if (!resp.ok) throw new Error(await resp.text())
    const payload = await resp.json()
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `songracer_project_${projectId}.json`
    anchor.click()
    URL.revokeObjectURL(url)
    statusMessage.value = `Exported project #${projectId}.`
  } catch (err) {
    statusMessage.value = `Export project failed: ${String(err)}`
  }
}

async function importProjectFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    const raw = await file.text()
    const parsed = JSON.parse(raw)
    const name = String(parsed?.name || `Imported ${new Date().toISOString()}`)
    const config = parsed?.config ?? parsed
    const resp = await fetch(`${apiBase.value}/projects/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, config }),
    })
    if (!resp.ok) throw new Error(await resp.text())
    const body = await resp.json()
    await refreshProjects()
    await loadProject(body.id)
    statusMessage.value = `Imported project #${body.id}.`
    backendOnline.value = true
  } catch (err) {
    backendOnline.value = false
    statusMessage.value = `Import project failed: ${String(err)}`
  } finally {
    input.value = ''
  }
}

async function renderSavedProject(projectId: number, isPreview: boolean) {
  isBusy.value = true
  statusMessage.value = isPreview
    ? `Submitting preview render for project #${projectId}...`
    : `Submitting final render for project #${projectId}...`
  try {
    const payload: Record<string, unknown> = {
      preview_scale: isPreview ? previewScale.value : finalScale.value,
    }
    if (outputPathInput.value.trim()) {
      payload.output_path = outputPathInput.value.trim()
    }
    const resp = await fetch(`${apiBase.value}/projects/${projectId}/render`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!resp.ok) throw new Error(await resp.text())
    const body = await resp.json()
    statusMessage.value = `Project render job submitted (${body.job_id.slice(0, 8)}...).`
    backendOnline.value = true
    await refreshJobs()
  } catch (err) {
    backendOnline.value = false
    statusMessage.value = `Project render failed: ${String(err)}`
  } finally {
    isBusy.value = false
  }
}

async function syncSavedProject(projectId: number) {
  isBusy.value = true
  statusMessage.value = `Syncing project #${projectId} by waveform...`
  try {
    const resp = await fetch(`${apiBase.value}/projects/${projectId}/sync`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sample_rate: 16000,
        max_shift_seconds: 8.0,
        apply_duration_cap: true,
      }),
    })
    if (!resp.ok) throw new Error(await resp.text())
    const body = await resp.json()
    const common = Number(body?.sync?.common_window_seconds ?? 0)
    statusMessage.value = `Project #${projectId} synced. Common overlap ${common.toFixed(2)}s.`
    backendOnline.value = true
    if (activeProjectId.value === projectId) {
      await loadProject(projectId)
    } else {
      await refreshProjects()
    }
  } catch (err) {
    backendOnline.value = false
    statusMessage.value = `Project sync failed: ${String(err)}`
  } finally {
    isBusy.value = false
  }
}

onMounted(() => {
  refreshJobs()
  refreshProjects()
  refreshSystemInfo()
  refreshBuilderCapabilities()
  pollHandle = window.setInterval(refreshJobs, 2000)
})

watch(
  () => apiBase.value,
  () => {
    refreshBuilderCapabilities()
  },
)

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
                <div class="mt-2 rounded border border-slate-700 bg-slate-900/60 p-1">
                  <svg viewBox="0 0 220 56" class="h-14 w-full">
                    <polyline
                      :points="pointsForWaveform(racer.waveformSamples)"
                      fill="none"
                      stroke="#22D3EE"
                      stroke-width="1.3"
                    />
                    <line
                      :x1="trimMarkerX(racer)"
                      y1="0"
                      :x2="trimMarkerX(racer)"
                      y2="56"
                      stroke="#FACC15"
                      stroke-width="1.5"
                    />
                  </svg>
                  <p class="text-[10px] text-slate-500">
                    Waveform preview
                    <span v-if="racer.waveformDurationSeconds">
                      ({{ racer.waveformDurationSeconds.toFixed(2) }}s)
                    </span>
                  </p>
                </div>
              </article>
            </div>
          </div>

          <div class="rounded-2xl border border-slate-700 bg-slate-900/80 p-5">
            <h2 class="mb-3 text-xl font-semibold text-slate-100">Sync Waveform Overlay</h2>
            <svg viewBox="0 0 320 110" class="h-28 w-full rounded border border-slate-700 bg-slate-950/80">
              <polyline
                v-for="(racer, idx) in racers"
                :key="`overlay_${racer.id}`"
                :points="alignedWavePoints(racer)"
                fill="none"
                :stroke="waveformColor(idx)"
                stroke-width="1.4"
              />
            </svg>
            <p class="mt-2 text-xs text-slate-400">
              Overlay aligned by trim-start. Window: {{ syncOverlayWindowSeconds().toFixed(2) }}s
            </p>
            <div class="mt-2 flex flex-wrap gap-2">
              <span
                v-for="(racer, idx) in racers"
                :key="`legend_${racer.id}`"
                class="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-[11px] text-slate-200"
              >
                <span class="mr-1 inline-block h-2 w-2 rounded-full" :style="{ backgroundColor: waveformColor(idx) }"></span>
                {{ racer.name || `Singer ${idx + 1}` }} · trim {{ racer.syncTrimStartSeconds.toFixed(2) }}s
              </span>
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
                Output path (optional)
                <input
                  v-model="outputPathInput"
                  placeholder="backend default if empty"
                  class="mt-1 w-full rounded-md border border-slate-600 bg-slate-900 px-2 py-1.5 text-slate-100"
                />
              </label>
              <label class="text-sm text-slate-300">
                Duration (cap seconds)
                <input v-model.number="duration" type="number" min="1" class="mt-1 w-full rounded-md border border-slate-600 bg-slate-900 px-2 py-1.5 text-slate-100" />
              </label>
              <label class="text-sm text-slate-300">
                World Height
                <input
                  v-model.number="worldHeight"
                  type="number"
                  :min="worldHeightCaps.min"
                  :max="worldHeightCaps.max"
                  class="mt-1 w-full rounded-md border border-slate-600 bg-slate-900 px-2 py-1.5 text-slate-100"
                  @blur="worldHeight = normalizeWorldHeight(worldHeight)"
                />
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
                class="rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-400 disabled:opacity-50"
                :disabled="!uploadedReady || isBusy || loadingWaveforms"
                @click="loadWaveforms"
              >
                {{ loadingWaveforms ? 'Loading waveforms...' : 'Load Waveform Preview' }}
              </button>
              <button
                class="rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-amber-400 disabled:opacity-50"
                :disabled="isBusy"
                @click="analyzeCourseRisk"
              >
                Analyze Course Safety
              </button>
              <button
                class="rounded-lg bg-teal-600 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-500 disabled:opacity-50"
                :disabled="isBusy"
                @click="validateCurrentConfig"
              >
                Validate Config
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
              <ParkourBuilder
                v-model="obstacleJson"
                :api-base="apiBase"
                :world-height="worldHeight"
                :duration="duration"
                :countdown="countdown"
                :winner-hold="winnerHold"
                :racers="builderPreviewRacers"
                :background-color="backgroundColor"
              />
            </div>
            <div class="mt-4">
              <label class="mb-1 block text-sm text-slate-300">Obstacle JSON (full control)</label>
              <textarea
                v-model="obstacleJson"
                rows="10"
                class="w-full rounded-md border border-slate-600 bg-slate-950 px-2 py-2 text-xs text-slate-100"
              />
            </div>
            <div class="mt-3 rounded-lg border border-slate-700 bg-slate-950/60 p-3">
              <p class="text-sm text-slate-200">
                Risk score:
                <span class="font-semibold" :class="(riskScore ?? 0) > 55 ? 'text-rose-300' : (riskScore ?? 0) > 28 ? 'text-amber-300' : 'text-emerald-300'">
                  {{ riskScore ?? 'N/A' }}
                </span>
              </p>
              <ul class="mt-2 max-h-28 space-y-1 overflow-auto text-[11px] text-slate-400">
                <li v-if="riskWarnings.length === 0">No warnings yet.</li>
                <li v-for="(w, idx) in riskWarnings" :key="`${w.code}_${idx}`">
                  <span class="uppercase" :class="w.level === 'high' ? 'text-rose-300' : w.level === 'medium' ? 'text-amber-300' : 'text-sky-300'">
                    {{ w.level }}
                  </span>
                  · {{ w.message }}
                </li>
              </ul>
            </div>
            <p class="mt-3 text-sm text-slate-300">{{ statusMessage }}</p>
          </div>
        </div>

        <aside class="space-y-6">
          <div class="rounded-2xl border border-slate-700 bg-slate-900/80 p-5">
            <h2 class="mb-3 text-xl font-semibold text-slate-100">Projects (DB CRUD)</h2>
            <label class="mb-2 block text-sm text-slate-300">
              Project name
              <input
                v-model="projectNameInput"
                class="mt-1 w-full rounded-md border border-slate-600 bg-slate-900 px-2 py-1.5 text-slate-100"
              />
            </label>
            <div class="mb-3 flex flex-wrap gap-2">
              <button
                class="rounded bg-cyan-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-cyan-500 disabled:opacity-50"
                :disabled="isBusy || racers.length === 0"
                @click="saveProject"
              >
                {{ activeProjectId ? 'Update Project' : 'Save Project' }}
              </button>
              <button
                class="rounded bg-slate-700 px-3 py-1.5 text-xs font-semibold hover:bg-slate-600"
                :disabled="isBusy"
                @click="refreshProjects"
              >
                Refresh List
              </button>
              <label
                class="cursor-pointer rounded bg-violet-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-violet-600"
              >
                Import Project JSON
                <input type="file" accept="application/json" class="hidden" @change="importProjectFile" />
              </label>
            </div>
            <div class="mb-3 rounded border border-slate-700 bg-slate-950/60 p-2 text-[11px] text-slate-400">
              <p><span class="text-slate-200">DB:</span> {{ systemInfo.db_path || 'unknown' }}</p>
              <p><span class="text-slate-200">Storage:</span> {{ systemInfo.storage_root || 'unknown' }}</p>
            </div>
            <div class="max-h-56 space-y-2 overflow-auto pr-1">
              <article
                v-for="p in projects"
                :key="p.id"
                class="rounded border border-slate-700 bg-slate-800/70 p-2"
              >
                <p class="text-sm font-semibold text-slate-100">
                  {{ p.name }}
                  <span
                    v-if="activeProjectId === p.id"
                    class="ml-1 rounded bg-emerald-700/70 px-1.5 py-0.5 text-[10px] text-emerald-100"
                  >
                    active
                  </span>
                </p>
                <p class="text-[10px] text-slate-400">#{{ p.id }} · {{ p.updated_at }}</p>
                <p
                  v-if="typeof p.risk_score === 'number'"
                  class="text-[10px]"
                  :class="(p.risk_score ?? 0) > 55 ? 'text-rose-300' : (p.risk_score ?? 0) > 28 ? 'text-amber-300' : 'text-emerald-300'"
                >
                  Risk {{ p.risk_score ?? 0 }} · {{ p.warning_count ?? 0 }} warnings
                </p>
                <div class="mt-2 flex gap-2">
                  <button
                    class="rounded bg-indigo-600 px-2 py-1 text-[11px] font-medium text-white hover:bg-indigo-500"
                    @click="loadProject(p.id)"
                  >
                    Load
                  </button>
                  <button
                    class="rounded bg-slate-600 px-2 py-1 text-[11px] font-medium text-white hover:bg-slate-500"
                    :disabled="isBusy"
                    @click="exportProject(p.id)"
                  >
                    Export
                  </button>
                  <button
                    class="rounded bg-cyan-600 px-2 py-1 text-[11px] font-medium text-white hover:bg-cyan-500"
                    :disabled="isBusy"
                    @click="renderSavedProject(p.id, true)"
                  >
                    Preview
                  </button>
                  <button
                    class="rounded bg-amber-600 px-2 py-1 text-[11px] font-medium text-slate-950 hover:bg-amber-500"
                    :disabled="isBusy"
                    @click="analyzeSavedProject(p.id)"
                  >
                    Analyze
                  </button>
                  <button
                    class="rounded bg-fuchsia-600 px-2 py-1 text-[11px] font-medium text-white hover:bg-fuchsia-500"
                    :disabled="isBusy"
                    @click="syncSavedProject(p.id)"
                  >
                    Sync
                  </button>
                  <button
                    class="rounded bg-emerald-600 px-2 py-1 text-[11px] font-medium text-white hover:bg-emerald-500"
                    :disabled="isBusy"
                    @click="renderSavedProject(p.id, false)"
                  >
                    Final
                  </button>
                  <button
                    class="rounded bg-rose-700 px-2 py-1 text-[11px] font-medium text-white hover:bg-rose-600"
                    @click="removeProject(p.id)"
                  >
                    Delete
                  </button>
                </div>
              </article>
              <p v-if="projects.length === 0" class="text-sm text-slate-400">No saved projects.</p>
            </div>
          </div>

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
