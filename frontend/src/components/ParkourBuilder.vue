<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

type ObstacleType =
  | 'rect'
  | 'moving_rect'
  | 'circle'
  | 'ring_gap'
  | 'pendulum'
  | 'one_way_gate'
  | 'spinner'

type BuilderObstacle = {
  id: string
  type: ObstacleType
  x: number
  y: number
  width?: number
  height?: number
  radius?: number
  angle_deg?: number
  thickness?: number
  rotation_speed_deg?: number
  gap_center_deg?: number
  gap_size_deg?: number
  amplitude?: number
  frequency_hz?: number
  axis?: 'x' | 'y'
  length?: number
  pivot_x?: number
  pivot_y?: number
  one_way?: 'up' | 'down'
  spin_speed_deg?: number
  fill_color?: string
  stroke_color?: string
  opacity?: number
}

type PreviewRacer = {
  name: string
  x: number
  y: number
  radius: number
}

type PreviewFrameObstacle = Record<string, any>

type PreviewData = {
  sample_fps: number
  positions: number[][][]
  leaders: number[]
  camera_y: number[]
  obstacle_visuals: PreviewFrameObstacle[][]
}

const props = defineProps<{
  modelValue: string
  apiBase: string
  worldHeight: number
  duration: number
  countdown: number
  winnerHold: number
  racers: PreviewRacer[]
  backgroundColor?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const courseWidth = 1080
const viewportHeight = 980
const paletteTypes: ObstacleType[] = [
  'rect',
  'moving_rect',
  'circle',
  'ring_gap',
  'spinner',
  'pendulum',
  'one_way_gate',
]

const obstacles = ref<BuilderObstacle[]>([])
const parseError = ref('')
const selectedId = ref<string | null>(null)
const cameraY = ref(0)
const snapEnabled = ref(true)
const dragMode = ref<'none' | 'move'>('none')
const dragOffset = ref({ dx: 0, dy: 0 })
const previewData = ref<PreviewData | null>(null)
const previewFrame = ref(0)
const previewPlaying = ref(false)
const previewLoading = ref(false)
const previewError = ref('')
const followPreviewCamera = ref(true)
const showGrid = ref(true)
const riskScore = ref<number | null>(null)
const riskWarnings = ref<Array<{ level: string; code: string; message: string }>>([])
const riskyObstacleIdx = ref<Set<number>>(new Set())

let suppressEmit = false
let previewDebounce: number | null = null
let playbackHandle: number | null = null
let riskDebounce: number | null = null

function obstacleLabel(t: ObstacleType): string {
  return t.replace(/_/g, ' ')
}

function uid(): string {
  return `${Date.now()}_${Math.random().toString(16).slice(2)}`
}

function snap(v: number, grid = 20): number {
  if (!snapEnabled.value) return v
  return Math.round(v / grid) * grid
}

function defaultObstacle(type: ObstacleType, x: number, y: number): BuilderObstacle {
  const base: BuilderObstacle = {
    id: uid(),
    type,
    x,
    y,
    fill_color: '#182037',
    stroke_color: '#000000',
    opacity: 0.95,
    angle_deg: 0,
    thickness: 22,
  }
  if (type === 'rect') {
    return { ...base, width: 280, height: 30 }
  }
  if (type === 'moving_rect') {
    return { ...base, width: 280, height: 30, amplitude: 100, frequency_hz: 0.24, axis: 'x' }
  }
  if (type === 'circle') {
    return { ...base, radius: 74 }
  }
  if (type === 'ring_gap') {
    return {
      ...base,
      radius: 130,
      thickness: 32,
      rotation_speed_deg: 90,
      gap_center_deg: 270,
      gap_size_deg: 58,
    }
  }
  if (type === 'spinner') {
    return { ...base, length: 300, thickness: 24, spin_speed_deg: 140 }
  }
  if (type === 'pendulum') {
    return {
      ...base,
      pivot_x: x,
      pivot_y: y,
      length: 260,
      thickness: 18,
      angle_deg: 25,
      amplitude: 50,
      frequency_hz: 0.45,
    }
  }
  return { ...base, width: 520, height: 24, one_way: 'down' }
}

function obstacleToSerializable(obs: BuilderObstacle): Record<string, unknown> {
  const { id: _id, ...raw } = obs
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(raw)) {
    if (v !== undefined) out[k] = v
  }
  return out
}

function parseObstacleJson(raw: string): BuilderObstacle[] {
  if (!raw.trim()) return []
  const parsed = JSON.parse(raw)
  if (!Array.isArray(parsed)) throw new Error('Obstacle JSON must be an array')
  return parsed.map((it, idx) => {
    if (!it || typeof it !== 'object') {
      throw new Error(`Obstacle #${idx} must be an object`)
    }
    const o = it as Record<string, any>
    if (!paletteTypes.includes(String(o.type) as ObstacleType)) {
      throw new Error(`Obstacle #${idx} type is not supported in builder`)
    }
    return {
      id: uid(),
      type: String(o.type) as ObstacleType,
      x: Number(o.x ?? 0),
      y: Number(o.y ?? 0),
      width: o.width !== undefined ? Number(o.width) : undefined,
      height: o.height !== undefined ? Number(o.height) : undefined,
      radius: o.radius !== undefined ? Number(o.radius) : undefined,
      angle_deg: o.angle_deg !== undefined ? Number(o.angle_deg) : undefined,
      thickness: o.thickness !== undefined ? Number(o.thickness) : undefined,
      rotation_speed_deg:
        o.rotation_speed_deg !== undefined ? Number(o.rotation_speed_deg) : undefined,
      gap_center_deg: o.gap_center_deg !== undefined ? Number(o.gap_center_deg) : undefined,
      gap_size_deg: o.gap_size_deg !== undefined ? Number(o.gap_size_deg) : undefined,
      amplitude: o.amplitude !== undefined ? Number(o.amplitude) : undefined,
      frequency_hz: o.frequency_hz !== undefined ? Number(o.frequency_hz) : undefined,
      axis: o.axis === 'y' ? 'y' : 'x',
      length: o.length !== undefined ? Number(o.length) : undefined,
      pivot_x: o.pivot_x !== undefined ? Number(o.pivot_x) : undefined,
      pivot_y: o.pivot_y !== undefined ? Number(o.pivot_y) : undefined,
      one_way: o.one_way === 'up' ? 'up' : 'down',
      spin_speed_deg: o.spin_speed_deg !== undefined ? Number(o.spin_speed_deg) : undefined,
      fill_color: o.fill_color ? String(o.fill_color) : '#182037',
      stroke_color: o.stroke_color ? String(o.stroke_color) : '#000000',
      opacity: o.opacity !== undefined ? Number(o.opacity) : 0.95,
    }
  })
}

function syncFromModel(raw: string) {
  try {
    const parsed = parseObstacleJson(raw)
    suppressEmit = true
    obstacles.value = parsed
    parseError.value = ''
  } catch (err) {
    parseError.value = `Builder parse failed: ${String(err)}`
  } finally {
    suppressEmit = false
  }
}

watch(
  () => props.modelValue,
  (next) => {
    const current = JSON.stringify(obstacles.value.map((o) => obstacleToSerializable(o)), null, 2)
    if (next.trim() === current.trim()) return
    syncFromModel(next)
  },
  { immediate: true },
)

watch(
  obstacles,
  () => {
    if (suppressEmit) return
    const payload = JSON.stringify(
      obstacles.value.map((o) => obstacleToSerializable(o)),
      null,
      2,
    )
    emit('update:modelValue', payload)
    schedulePreview()
    scheduleRiskAnalyze()
  },
  { deep: true },
)

const selectedObstacle = computed(() =>
  obstacles.value.find((o) => o.id === selectedId.value) ?? null,
)

function toCanvasXY(clientX: number, clientY: number, container: HTMLElement): { x: number; y: number } {
  const rect = container.getBoundingClientRect()
  const nx = (clientX - rect.left) / Math.max(1, rect.width)
  const ny = (clientY - rect.top) / Math.max(1, rect.height)
  return {
    x: Math.max(0, Math.min(courseWidth, nx * courseWidth)),
    y: cameraY.value + Math.max(0, Math.min(viewportHeight, ny * viewportHeight)),
  }
}

function onPaletteDragStart(ev: DragEvent, type: ObstacleType) {
  if (!ev.dataTransfer) return
  ev.dataTransfer.setData('text/songracer-obstacle-type', type)
  ev.dataTransfer.effectAllowed = 'copy'
}

function onCanvasDrop(ev: DragEvent) {
  if (!ev.dataTransfer) return
  const type = ev.dataTransfer.getData('text/songracer-obstacle-type') as ObstacleType
  if (!paletteTypes.includes(type)) return
  const container = ev.currentTarget as HTMLElement
  const pt = toCanvasXY(ev.clientX, ev.clientY, container)
  const obs = defaultObstacle(type, snap(pt.x), snap(pt.y))
  obstacles.value.push(obs)
  selectedId.value = obs.id
}

function obstaclePosition(obs: BuilderObstacle): { x: number; y: number } {
  if (obs.type === 'pendulum') {
    return {
      x: Number(obs.pivot_x ?? obs.x),
      y: Number(obs.pivot_y ?? obs.y),
    }
  }
  return { x: obs.x, y: obs.y }
}

function moveObstacle(obs: BuilderObstacle, x: number, y: number) {
  obs.x = snap(x)
  obs.y = snap(y)
  if (obs.type === 'pendulum') {
    obs.pivot_x = snap(x)
    obs.pivot_y = snap(y)
  }
}

function startDragObstacle(obs: BuilderObstacle, ev: PointerEvent) {
  selectedId.value = obs.id
  const container = (ev.currentTarget as HTMLElement).closest('[data-builder-canvas]') as HTMLElement | null
  if (!container) return
  const pt = toCanvasXY(ev.clientX, ev.clientY, container)
  const pos = obstaclePosition(obs)
  dragOffset.value = { dx: pt.x - pos.x, dy: pt.y - pos.y }
  dragMode.value = 'move'
}

function onCanvasPointerMove(ev: PointerEvent) {
  if (dragMode.value !== 'move' || !selectedObstacle.value) return
  const container = ev.currentTarget as HTMLElement
  const pt = toCanvasXY(ev.clientX, ev.clientY, container)
  moveObstacle(selectedObstacle.value, pt.x - dragOffset.value.dx, pt.y - dragOffset.value.dy)
}

function stopDrag() {
  dragMode.value = 'none'
}

function duplicateSelected() {
  if (!selectedObstacle.value) return
  const source = selectedObstacle.value
  const copy: BuilderObstacle = {
    ...JSON.parse(JSON.stringify(source)),
    id: uid(),
    x: source.x + 48,
    y: source.y + 48,
  }
  if (copy.type === 'pendulum') {
    copy.pivot_x = Number(copy.pivot_x ?? source.x) + 48
    copy.pivot_y = Number(copy.pivot_y ?? source.y) + 48
  }
  obstacles.value.push(copy)
  selectedId.value = copy.id
}

function deleteSelected() {
  if (!selectedId.value) return
  obstacles.value = obstacles.value.filter((o) => o.id !== selectedId.value)
  selectedId.value = null
}

function applyPreset(preset: 'starter' | 'rings' | 'gates') {
  const make = (type: ObstacleType, x: number, y: number) => defaultObstacle(type, x, y)
  if (preset === 'starter') {
    obstacles.value = [
      { ...make('rect', 280, 980), angle_deg: -22, width: 300 },
      { ...make('moving_rect', 760, 1120), angle_deg: 18, width: 290, amplitude: 120 },
      { ...make('ring_gap', 540, 1380), radius: 160, gap_size_deg: 64 },
      { ...make('spinner', 540, 1680), length: 340, spin_speed_deg: 160 },
      { ...make('one_way_gate', 540, 1940), width: 620, one_way: 'down' },
    ]
  } else if (preset === 'rings') {
    obstacles.value = [
      { ...make('ring_gap', 350, 980), radius: 126, gap_center_deg: 250, gap_size_deg: 62 },
      { ...make('ring_gap', 730, 1210), radius: 130, gap_center_deg: 200, gap_size_deg: 58 },
      { ...make('ring_gap', 420, 1460), radius: 142, gap_center_deg: 280, gap_size_deg: 60 },
      { ...make('ring_gap', 700, 1730), radius: 132, gap_center_deg: 245, gap_size_deg: 58 },
      { ...make('spinner', 540, 2060), length: 320, spin_speed_deg: 150 },
    ]
  } else {
    obstacles.value = [
      { ...make('rect', 260, 940), angle_deg: -18, width: 320 },
      { ...make('one_way_gate', 540, 1120), width: 640, one_way: 'down' },
      { ...make('one_way_gate', 540, 1270), width: 640, one_way: 'up' },
      { ...make('moving_rect', 740, 1510), angle_deg: 14, width: 320, axis: 'x' },
      { ...make('pendulum', 540, 1820), length: 290, angle_deg: 15, amplitude: 56 },
    ]
  }
  selectedId.value = obstacles.value[0]?.id ?? null
}

const cameraMax = computed(() => Math.max(0, props.worldHeight - viewportHeight))

watch(
  () => props.worldHeight,
  () => {
    cameraY.value = Math.max(0, Math.min(cameraY.value, cameraMax.value))
  },
)

function previewRacersPayload(): PreviewRacer[] {
  if (props.racers.length > 0) return props.racers
  return Array.from({ length: 5 }).map((_, idx) => ({
    name: `Singer ${idx + 1}`,
    x: 220 + idx * 150,
    y: 420 + (idx % 2) * 42,
    radius: 96,
  }))
}

async function requestPreview() {
  previewLoading.value = true
  previewError.value = ''
  try {
    const resp = await fetch(`${props.apiBase}/preview/simulate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        seed: 13,
        render: {
          width: 1080,
          height: 1920,
          world_height: props.worldHeight,
          fps: 30,
          duration_seconds: Math.max(1, Math.min(20, props.duration)),
          countdown_seconds: props.countdown,
          goal_margin: 150,
          camera_follow: true,
          camera_lead_ratio: 0.35,
          auto_end_on_winner: true,
          winner_hold_seconds: props.winnerHold,
          obstacle_stream_spacing: 0,
          obstacle_stream_jitter_x: 0,
          obstacle_stream_repeats: 1,
        },
        racers: previewRacersPayload(),
        obstacles: obstacles.value.map((o) => obstacleToSerializable(o)),
        sample_fps: 15,
        max_frames: 360,
      }),
    })
    if (!resp.ok) {
      throw new Error(await resp.text())
    }
    const body = await resp.json()
    previewData.value = {
      sample_fps: Number(body.sample_fps ?? 15),
      positions: Array.isArray(body.positions) ? body.positions : [],
      leaders: Array.isArray(body.leaders) ? body.leaders : [],
      camera_y: Array.isArray(body.camera_y) ? body.camera_y : [],
      obstacle_visuals: Array.isArray(body.obstacle_visuals) ? body.obstacle_visuals : [],
    }
    previewFrame.value = 0
    if (followPreviewCamera.value && previewData.value.camera_y.length > 0) {
      cameraY.value = Math.max(0, Math.min(cameraMax.value, Number(previewData.value.camera_y[0] ?? 0)))
    }
  } catch (err) {
    previewError.value = String(err)
  } finally {
    previewLoading.value = false
  }
}

async function analyzeRisk() {
  try {
    const resp = await fetch(`${props.apiBase}/analyze/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        config: {
          render: { width: 1080, height: 1920 },
          obstacles: obstacles.value.map((o) => obstacleToSerializable(o)),
        },
      }),
    })
    if (!resp.ok) {
      throw new Error(await resp.text())
    }
    const body = await resp.json()
    riskScore.value = Number(body.risk_score ?? 0)
    riskWarnings.value = Array.isArray(body.warnings) ? body.warnings : []
    const idxSet = new Set<number>()
    for (const w of riskWarnings.value) {
      const m = /Obstacle\s+#(\d+)/i.exec(String(w.message || ''))
      if (m) idxSet.add(Number(m[1]))
    }
    riskyObstacleIdx.value = idxSet
  } catch (_err) {
    riskScore.value = null
    riskWarnings.value = []
    riskyObstacleIdx.value = new Set()
  }
}

function schedulePreview() {
  if (previewDebounce) {
    window.clearTimeout(previewDebounce)
    previewDebounce = null
  }
  previewDebounce = window.setTimeout(() => {
    void requestPreview()
  }, 360)
}

function scheduleRiskAnalyze() {
  if (riskDebounce) {
    window.clearTimeout(riskDebounce)
    riskDebounce = null
  }
  riskDebounce = window.setTimeout(() => {
    void analyzeRisk()
  }, 450)
}

function togglePlayPreview() {
  previewPlaying.value = !previewPlaying.value
}

function resetPreview() {
  previewFrame.value = 0
  if (followPreviewCamera.value && previewData.value?.camera_y?.length) {
    cameraY.value = Math.max(
      0,
      Math.min(cameraMax.value, Number(previewData.value.camera_y[0] ?? cameraY.value)),
    )
  }
}

watch(previewPlaying, (play) => {
  if (playbackHandle) {
    clearInterval(playbackHandle)
    playbackHandle = null
  }
  if (!play || !previewData.value || previewData.value.positions.length <= 1) return
  const fps = Math.max(4, Number(previewData.value.sample_fps || 15))
  const ms = Math.round(1000 / fps)
  playbackHandle = window.setInterval(() => {
    const max = (previewData.value?.positions.length ?? 1) - 1
    previewFrame.value = max <= 0 ? 0 : (previewFrame.value + 1) % (max + 1)
    if (followPreviewCamera.value && previewData.value?.camera_y?.length) {
      cameraY.value = Math.max(
        0,
        Math.min(cameraMax.value, Number(previewData.value.camera_y[previewFrame.value] ?? cameraY.value)),
      )
    }
  }, ms)
})

const currentPreviewPositions = computed(() => {
  if (!previewData.value || previewData.value.positions.length === 0) return []
  return previewData.value.positions[Math.min(previewFrame.value, previewData.value.positions.length - 1)] || []
})

const currentPreviewLeader = computed(() => {
  if (!previewData.value || previewData.value.leaders.length === 0) return 0
  return Number(previewData.value.leaders[Math.min(previewFrame.value, previewData.value.leaders.length - 1)] || 0)
})

const currentVisuals = computed<PreviewFrameObstacle[]>(() => {
  if (!previewData.value || previewData.value.obstacle_visuals.length === 0) {
    return obstacles.value.map((o) => {
      if (o.type === 'rect' || o.type === 'moving_rect' || o.type === 'one_way_gate') {
        return {
          type: o.type,
          x: o.x,
          y: o.y,
          width: o.width || 260,
          height: o.height || 30,
          angle_deg: o.angle_deg || 0,
          fill_color: o.fill_color || '#182037',
          stroke_color: o.stroke_color || '#000000',
          opacity: o.opacity ?? 0.95,
        }
      }
      if (o.type === 'circle') {
        return {
          type: 'circle',
          x: o.x,
          y: o.y,
          radius: o.radius || 60,
          fill_color: o.fill_color || '#182037',
          stroke_color: o.stroke_color || '#000000',
          opacity: o.opacity ?? 0.95,
        }
      }
      if (o.type === 'ring_gap') {
        return {
          type: 'ring_gap',
          x: o.x,
          y: o.y,
          radius: o.radius || 120,
          thickness: o.thickness || 28,
          gap_center_deg: o.gap_center_deg || 270,
          gap_size_deg: o.gap_size_deg || 58,
          fill_color: o.fill_color || '#182037',
          stroke_color: o.stroke_color || '#000000',
          opacity: o.opacity ?? 0.95,
        }
      }
      if (o.type === 'spinner') {
        const half = (o.length || 260) * 0.5
        return {
          type: 'spinner',
          x0: o.x - half,
          y0: o.y,
          x1: o.x + half,
          y1: o.y,
          x: o.x,
          y: o.y,
          thickness: o.thickness || 20,
          fill_color: o.fill_color || '#182037',
          stroke_color: o.stroke_color || '#000000',
          opacity: o.opacity ?? 0.95,
        }
      }
      const pivotX = Number(o.pivot_x ?? o.x)
      const pivotY = Number(o.pivot_y ?? o.y)
      const angle = (Number(o.angle_deg ?? 0) * Math.PI) / 180
      const len = Number(o.length ?? 240)
      return {
        type: 'pendulum',
        x0: pivotX,
        y0: pivotY,
        x1: pivotX + Math.sin(angle) * len,
        y1: pivotY + Math.cos(angle) * len,
        thickness: o.thickness || 16,
        fill_color: o.fill_color || '#182037',
        stroke_color: o.stroke_color || '#000000',
        opacity: o.opacity ?? 0.95,
      }
    })
  }
  return (
    previewData.value.obstacle_visuals[
      Math.min(previewFrame.value, previewData.value.obstacle_visuals.length - 1)
    ] || []
  )
})

function obstacleScreenY(yWorld: number): number {
  return yWorld - cameraY.value
}

function previewProgressText(): string {
  const total = previewData.value?.positions.length ?? 0
  if (total <= 0) return 'No preview yet.'
  return `Frame ${previewFrame.value + 1} / ${total}`
}

onMounted(() => {
  void requestPreview()
  void analyzeRisk()
})

onUnmounted(() => {
  if (previewDebounce) {
    window.clearTimeout(previewDebounce)
    previewDebounce = null
  }
  if (playbackHandle) {
    clearInterval(playbackHandle)
    playbackHandle = null
  }
  if (riskDebounce) {
    window.clearTimeout(riskDebounce)
    riskDebounce = null
  }
})
</script>

<template>
  <div class="space-y-3 rounded-xl border border-slate-700 bg-slate-950/50 p-3">
    <div class="flex flex-wrap items-center gap-2">
      <span class="text-xs font-semibold uppercase tracking-wide text-slate-300">Parkour Builder</span>
      <button
        v-for="t in paletteTypes"
        :key="t"
        draggable="true"
        class="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-[11px] text-slate-100 hover:bg-slate-700"
        @dragstart="onPaletteDragStart($event, t)"
      >
        + {{ obstacleLabel(t) }}
      </button>
      <button
        class="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-[11px] text-slate-100 hover:bg-slate-700 disabled:opacity-40"
        :disabled="!selectedObstacle"
        @click="duplicateSelected"
      >
        Duplicate
      </button>
      <button
        class="rounded border border-rose-600/50 bg-rose-900/40 px-2 py-1 text-[11px] text-rose-200 hover:bg-rose-800/50 disabled:opacity-40"
        :disabled="!selectedObstacle"
        @click="deleteSelected"
      >
        Delete
      </button>
      <button
        class="rounded border border-cyan-600/50 bg-cyan-900/30 px-2 py-1 text-[11px] text-cyan-200 hover:bg-cyan-800/40"
        :disabled="previewLoading"
        @click="requestPreview"
      >
        {{ previewLoading ? 'Refreshing...' : 'Refresh Live Preview' }}
      </button>
      <button
        class="rounded border border-amber-600/50 bg-amber-900/30 px-2 py-1 text-[11px] text-amber-200 hover:bg-amber-800/40"
        @click="analyzeRisk"
      >
        Analyze Risk
      </button>
      <button
        class="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-[11px] text-slate-100 hover:bg-slate-700"
        @click="applyPreset('starter')"
      >
        Preset: Starter
      </button>
      <button
        class="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-[11px] text-slate-100 hover:bg-slate-700"
        @click="applyPreset('rings')"
      >
        Preset: Rings
      </button>
      <button
        class="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-[11px] text-slate-100 hover:bg-slate-700"
        @click="applyPreset('gates')"
      >
        Preset: Gates
      </button>
      <button
        class="rounded border border-violet-600/50 bg-violet-900/30 px-2 py-1 text-[11px] text-violet-200 hover:bg-violet-800/40 disabled:opacity-40"
        :disabled="!previewData || (previewData.positions?.length ?? 0) < 2"
        @click="togglePlayPreview"
      >
        {{ previewPlaying ? 'Pause' : 'Play' }}
      </button>
      <button
        class="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-[11px] text-slate-100 hover:bg-slate-700"
        @click="resetPreview"
      >
        Reset
      </button>
    </div>

    <div class="grid gap-3 lg:grid-cols-[2.1fr_1fr]">
      <div class="space-y-2">
        <div class="flex flex-wrap items-center gap-3 text-xs text-slate-300">
          <label class="flex items-center gap-1">
            Camera Y
            <input
              v-model.number="cameraY"
              type="range"
              min="0"
              :max="cameraMax"
              class="w-40"
            />
            <span class="w-14 text-right text-slate-400">{{ cameraY.toFixed(0) }}</span>
          </label>
          <label class="flex items-center gap-1">
            <input v-model="snapEnabled" type="checkbox" />
            Snap
          </label>
          <label class="flex items-center gap-1">
            <input v-model="showGrid" type="checkbox" />
            Grid
          </label>
          <label class="flex items-center gap-1">
            <input v-model="followPreviewCamera" type="checkbox" />
            Follow preview camera
          </label>
          <span class="text-slate-400">{{ previewProgressText() }}</span>
          <span
            v-if="riskScore !== null"
            class="rounded border px-2 py-0.5"
            :class="(riskScore ?? 0) > 55 ? 'border-rose-500/50 text-rose-300' : (riskScore ?? 0) > 28 ? 'border-amber-500/50 text-amber-300' : 'border-emerald-500/50 text-emerald-300'"
          >
            Risk {{ riskScore }}
          </span>
        </div>

        <div
          data-builder-canvas
          class="relative overflow-hidden rounded-lg border border-slate-700 bg-slate-900"
          @dragover.prevent
          @drop.prevent="onCanvasDrop"
          @pointermove="onCanvasPointerMove"
          @pointerup="stopDrag"
          @pointerleave="stopDrag"
        >
          <svg viewBox="0 0 1080 980" class="aspect-[11/10] w-full">
            <defs>
              <pattern id="grid" width="120" height="120" patternUnits="userSpaceOnUse">
                <path d="M 120 0 L 0 0 0 120" fill="none" stroke="#243045" stroke-width="1" />
              </pattern>
            </defs>
            <rect x="0" y="0" width="1080" height="980" :fill="backgroundColor || '#0f172a'" />
            <rect v-if="showGrid" x="0" y="0" width="1080" height="980" fill="url(#grid)" opacity="0.55" />
            <line
              x1="0"
              :y1="obstacleScreenY((worldHeight || 0) - 150)"
              x2="1080"
              :y2="obstacleScreenY((worldHeight || 0) - 150)"
              stroke="#fb7185"
              stroke-width="4"
              stroke-dasharray="16 10"
              opacity="0.7"
            />

            <g v-for="(o, idx) in currentVisuals" :key="`o_${idx}`">
              <g v-if="o.type === 'rect' || o.type === 'moving_rect' || o.type === 'one_way_gate'"
                :transform="`translate(${o.x}, ${obstacleScreenY(o.y)}) rotate(${o.angle_deg || 0})`">
                <rect
                  :x="-(o.width || 220) / 2"
                  :y="-(o.height || 30) / 2"
                  :width="o.width || 220"
                  :height="o.height || 30"
                  :fill="o.fill_color || '#152036'"
                  :stroke="o.stroke_color || '#000000'"
                  stroke-width="2"
                  rx="4"
                />
              </g>
              <circle
                v-else-if="o.type === 'circle'"
                :cx="o.x"
                :cy="obstacleScreenY(o.y)"
                :r="o.radius || 60"
                :fill="o.fill_color || '#152036'"
                :stroke="o.stroke_color || '#000000'"
                stroke-width="2"
              />
              <circle
                v-else-if="o.type === 'ring_gap'"
                :cx="o.x"
                :cy="obstacleScreenY(o.y)"
                :r="o.radius || 120"
                fill="none"
                :stroke="o.fill_color || '#152036'"
                :stroke-width="o.thickness || 24"
                :stroke-dasharray="`${Math.max(8, ((o.gap_size_deg || 58) / 360) * 680)} 1000`"
              />
              <g v-else-if="o.type === 'spinner'">
                <line
                  :x1="o.x0"
                  :y1="obstacleScreenY(o.y0)"
                  :x2="o.x1"
                  :y2="obstacleScreenY(o.y1)"
                  :stroke="o.fill_color || '#152036'"
                  :stroke-width="o.thickness || 20"
                  stroke-linecap="round"
                />
                <circle :cx="o.x" :cy="obstacleScreenY(o.y)" r="8" :fill="o.stroke_color || '#000000'" />
              </g>
              <g v-else-if="o.type === 'pendulum'">
                <line
                  :x1="o.x0"
                  :y1="obstacleScreenY(o.y0)"
                  :x2="o.x1"
                  :y2="obstacleScreenY(o.y1)"
                  :stroke="o.fill_color || '#152036'"
                  :stroke-width="o.thickness || 16"
                  stroke-linecap="round"
                />
                <circle :cx="o.x0" :cy="obstacleScreenY(o.y0)" r="7" :fill="o.stroke_color || '#000000'" />
              </g>
            </g>

            <g v-for="(o, idx) in obstacles" :key="o.id">
              <circle
                v-if="o.id === selectedId"
                :cx="obstaclePosition(o).x"
                :cy="obstacleScreenY(obstaclePosition(o).y)"
                r="18"
                fill="none"
                stroke="#67e8f9"
                stroke-width="3"
                stroke-dasharray="6 5"
              />
              <circle
                :cx="obstaclePosition(o).x"
                :cy="obstacleScreenY(obstaclePosition(o).y)"
                r="12"
                fill="#0f172a"
                :stroke="riskyObstacleIdx.has(idx) ? '#fb7185' : '#e2e8f0'"
                stroke-width="2"
                class="cursor-move"
                @pointerdown.stop.prevent="startDragObstacle(o, $event)"
                @click.stop="selectedId = o.id"
              />
              <text
                :x="obstaclePosition(o).x + 16"
                :y="obstacleScreenY(obstaclePosition(o).y) - 10"
                fill="#cbd5e1"
                font-size="14"
              >
                {{ idx + 1 }}
              </text>
            </g>

            <g v-for="(p, idx) in currentPreviewPositions" :key="`r_${idx}`">
              <circle
                :cx="p?.[0] || 0"
                :cy="obstacleScreenY(p?.[1] || 0)"
                :r="(racers[idx]?.radius || 96) * 0.35"
                :fill="idx === currentPreviewLeader ? '#22d3ee' : '#93c5fd'"
                :opacity="idx === currentPreviewLeader ? 0.95 : 0.65"
                stroke="#0b1020"
                stroke-width="2"
              />
            </g>
          </svg>
        </div>
        <p v-if="previewError" class="text-xs text-rose-300">Live preview failed: {{ previewError }}</p>
      </div>

      <div class="rounded-lg border border-slate-700 bg-slate-900/70 p-3">
        <p class="mb-2 text-xs uppercase tracking-wide text-slate-400">Selected obstacle</p>
        <p v-if="!selectedObstacle" class="text-sm text-slate-400">Select or drop an obstacle to edit.</p>
        <div v-else class="space-y-2 text-xs text-slate-200">
          <p class="font-semibold text-cyan-300">{{ obstacleLabel(selectedObstacle.type) }}</p>
          <div class="grid grid-cols-2 gap-2">
            <label>
              X
              <input v-model.number="selectedObstacle.x" type="number" class="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1" />
            </label>
            <label>
              Y
              <input v-model.number="selectedObstacle.y" type="number" class="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1" />
            </label>
            <label v-if="selectedObstacle.width !== undefined">
              Width
              <input v-model.number="selectedObstacle.width" type="number" class="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1" />
            </label>
            <label v-if="selectedObstacle.height !== undefined">
              Height
              <input v-model.number="selectedObstacle.height" type="number" class="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1" />
            </label>
            <label v-if="selectedObstacle.radius !== undefined">
              Radius
              <input v-model.number="selectedObstacle.radius" type="number" class="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1" />
            </label>
            <label v-if="selectedObstacle.length !== undefined">
              Length
              <input v-model.number="selectedObstacle.length" type="number" class="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1" />
            </label>
            <label v-if="selectedObstacle.thickness !== undefined">
              Thickness
              <input v-model.number="selectedObstacle.thickness" type="number" class="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1" />
            </label>
            <label v-if="selectedObstacle.angle_deg !== undefined">
              Angle
              <input v-model.number="selectedObstacle.angle_deg" type="number" class="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1" />
            </label>
            <label v-if="selectedObstacle.rotation_speed_deg !== undefined">
              Rotation speed
              <input v-model.number="selectedObstacle.rotation_speed_deg" type="number" class="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1" />
            </label>
            <label v-if="selectedObstacle.spin_speed_deg !== undefined">
              Spin speed
              <input v-model.number="selectedObstacle.spin_speed_deg" type="number" class="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1" />
            </label>
            <label v-if="selectedObstacle.amplitude !== undefined">
              Amplitude
              <input v-model.number="selectedObstacle.amplitude" type="number" class="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1" />
            </label>
            <label v-if="selectedObstacle.frequency_hz !== undefined">
              Frequency Hz
              <input v-model.number="selectedObstacle.frequency_hz" type="number" step="0.01" class="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1" />
            </label>
            <label v-if="selectedObstacle.gap_size_deg !== undefined">
              Gap size deg
              <input v-model.number="selectedObstacle.gap_size_deg" type="number" class="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1" />
            </label>
            <label v-if="selectedObstacle.gap_center_deg !== undefined">
              Gap center deg
              <input v-model.number="selectedObstacle.gap_center_deg" type="number" class="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1" />
            </label>
            <label v-if="selectedObstacle.axis !== undefined">
              Axis
              <select v-model="selectedObstacle.axis" class="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1">
                <option value="x">x</option>
                <option value="y">y</option>
              </select>
            </label>
            <label v-if="selectedObstacle.one_way !== undefined">
              One-way
              <select v-model="selectedObstacle.one_way" class="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1">
                <option value="down">down</option>
                <option value="up">up</option>
              </select>
            </label>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <label>
              Fill
              <input v-model="selectedObstacle.fill_color" type="color" class="mt-1 h-8 w-full rounded border border-slate-600 bg-slate-950 px-1" />
            </label>
            <label>
              Stroke
              <input v-model="selectedObstacle.stroke_color" type="color" class="mt-1 h-8 w-full rounded border border-slate-600 bg-slate-950 px-1" />
            </label>
          </div>
        </div>
      </div>
    </div>
    <div v-if="riskWarnings.length > 0" class="rounded border border-slate-700 bg-slate-950/60 p-2">
      <p class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-300">
        Risk Warnings
      </p>
      <ul class="max-h-24 space-y-1 overflow-auto text-[11px] text-slate-400">
        <li v-for="(w, idx) in riskWarnings" :key="`${w.code}_${idx}`">
          <span
            class="uppercase"
            :class="w.level === 'high' ? 'text-rose-300' : w.level === 'medium' ? 'text-amber-300' : 'text-sky-300'"
          >
            {{ w.level }}
          </span>
          · {{ w.message }}
        </li>
      </ul>
    </div>
    <p v-if="parseError" class="text-xs text-rose-300">{{ parseError }}</p>
  </div>
</template>
