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
type RiskWarningEntry = {
  level: string
  code: string
  message: string
  obstacle_index?: number
  obstacle_indices?: number[]
}

type PreviewData = {
  requested_sample_fps: number
  requested_max_frames: number
  sample_fps: number
  sample_step_frames: number
  sample_interval_seconds: number
  total_source_frames: number
  returned_last_sample_frame_index: number
  source_duration_seconds: number
  returned_sample_frames: number
  sampling_coverage_ratio: number
  sampled_coverage_ratio: number
  returned_sample_duration_seconds: number
  total_sample_duration_seconds: number
  total_last_sample_frame_index: number
  positions: number[][][]
  leaders: number[]
  camera_y: number[]
  states: number[]
  obstacle_visuals: PreviewFrameObstacle[][]
  winner_index: number
  winner_frame: number
  total_sample_frames: number
  truncated: boolean
  cache_hit: boolean
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
const courseViewportHeight = 1920
const viewportHeight = 980
const FALLBACK_PALETTE_TYPES: ObstacleType[] = [
  'rect',
  'moving_rect',
  'circle',
  'ring_gap',
  'spinner',
  'pendulum',
  'one_way_gate',
]
const paletteTypes = ref<ObstacleType[]>([...FALLBACK_PALETTE_TYPES])
const paletteLabelByType = ref<Record<string, string>>(
  Object.fromEntries(FALLBACK_PALETTE_TYPES.map((t) => [t, t.replace(/_/g, ' ')])),
)

const obstacles = ref<BuilderObstacle[]>([])
const parseError = ref('')
const selectedId = ref<string | null>(null)
const selectedIds = ref<string[]>([])
const lockedIds = ref<string[]>([])
const hiddenIds = ref<string[]>([])
const cameraY = ref(0)
const snapEnabled = ref(true)
const snapSize = ref(20)
const dragMode = ref<'none' | 'move'>('none')
const dragOffset = ref({ dx: 0, dy: 0 })
const dragPointerStart = ref<{ x: number; y: number } | null>(null)
const dragStartById = ref<Record<string, { x: number; y: number }>>({})
const previewData = ref<PreviewData | null>(null)
const previewFrame = ref(0)
const previewPlaying = ref(false)
const previewLoading = ref(false)
const autoPreview = ref(true)
const previewSampleFps = ref(15)
const previewMaxFrames = ref(360)
const previewCacheSize = ref(0)
const previewCacheMax = ref(0)
const previewError = ref('')
const followPreviewCamera = ref(true)
const showGrid = ref(true)
const riskScore = ref<number | null>(null)
const riskWarnings = ref<RiskWarningEntry[]>([])
const riskyObstacleIds = ref<Set<string>>(new Set())
const riskWarningTargetIds = ref<string[][]>([])
const clipboardStatus = ref('')
const templateCatalog = ref<Record<string, Array<Record<string, unknown>>>>({})
const templateSource = ref<'fallback' | 'api'>('fallback')
const templateVersion = ref('')
const bootstrapVersion = ref('')

function defaultBuilderCaps() {
  return {
    preview: {
      sample_fps: { min: 4, max: 60, default: 15 },
      max_frames: { min: 30, max: 1500, default: 300 },
    },
    generator: {
      count: { min: 1, max: 200, default: 8 },
      start_y: { min: 0, max: 100000, default: 900 },
      spacing: { min: 40, max: 4000, default: 260 },
      width: { min: 200, max: 4000, default: 1080 },
      seed: { min: 0, max: 2000000000, default: 13 },
      safe_target_max_risk: { min: 0, max: 100, default: 35 },
      safe_max_attempts: { min: 1, max: 64, default: 8 },
      safe_analysis_height: { min: 200, max: 8000, default: 1920 },
    },
  }
}

type CapRange = { min: number; max: number; default: number }

function normalizeCapRange(raw: unknown, fallback: CapRange): CapRange {
  const obj = raw as Record<string, unknown> | null
  const parsedMin = Number(obj?.min)
  const parsedMax = Number(obj?.max)
  const parsedDefault = Number(obj?.default)
  let min = Number.isFinite(parsedMin) ? parsedMin : fallback.min
  let max = Number.isFinite(parsedMax) ? parsedMax : fallback.max
  if (max < min) {
    const swap = min
    min = max
    max = swap
  }
  const fallbackDefaultClamped = Math.max(min, Math.min(max, fallback.default))
  const normalizedDefault = Number.isFinite(parsedDefault) ? parsedDefault : fallbackDefaultClamped
  return {
    min,
    max,
    default: Math.max(min, Math.min(max, normalizedDefault)),
  }
}

const builderCaps = ref(defaultBuilderCaps())
const historyStack = ref<string[]>([])
const historyIndex = ref(-1)
const applyingHistory = ref(false)
const generateCount = ref(8)
const generateSpacing = ref(260)
const generateSeed = ref(13)
const generateSafeTarget = ref(35)
const generateSafeAttempts = ref(8)
const lastSafeGeneration = ref<{
  seed: number
  risk: number
  attempts: number
  accepted: boolean
  warnings: number
  analysisHeight: number
} | null>(null)
const lastSafeGenerationSignature = ref<string | null>(null)

let suppressEmit = false
let previewDebounce: number | null = null
let playbackHandle: number | null = null
let riskDebounce: number | null = null
let historyDebounce: number | null = null
let previewRequestNonce = 0
const PREF_KEY = 'songracer_parkour_builder_prefs_v1'

function obstacleLabel(t: ObstacleType): string {
  return paletteLabelByType.value[t] || t.replace(/_/g, ' ')
}

function isObstacleType(value: string): value is ObstacleType {
  return FALLBACK_PALETTE_TYPES.includes(value as ObstacleType)
}

function applyRiskPayload(
  risk: number | null,
  warnings: RiskWarningEntry[],
) {
  riskScore.value = risk
  riskWarnings.value = warnings
  const idSet = new Set<string>()
  const targetIds: string[][] = []
  for (const w of warnings) {
    const ids: string[] = []
    if (typeof w.obstacle_index === 'number') {
      const id = visibleObstacles.value[w.obstacle_index]?.id
      if (id) ids.push(id)
    }
    if (Array.isArray(w.obstacle_indices)) {
      for (const idx of w.obstacle_indices) {
        if (typeof idx !== 'number') continue
        const id = visibleObstacles.value[idx]?.id
        if (id) ids.push(id)
      }
    }
    const uniq = [...new Set(ids)]
    for (const id of uniq) idSet.add(id)
    targetIds.push(uniq)
  }
  riskyObstacleIds.value = idSet
  riskWarningTargetIds.value = targetIds
}

function focusRiskWarningByIndex(index: number) {
  const ids = riskWarningTargetIds.value[index] ?? []
  if (ids.length === 0) return
  selectedIds.value = ids
  selectedId.value = ids[0] ?? null
  const first = obstacles.value.find((o) => o.id === selectedId.value) ?? null
  focusOnObstacle(first)
}

function uid(): string {
  return `${Date.now()}_${Math.random().toString(16).slice(2)}`
}

function snap(v: number): number {
  if (!snapEnabled.value) return v
  const grid = Math.max(1, Number(snapSize.value || 1))
  return Math.round(v / grid) * grid
}

function clampRounded(value: number, min: number, max: number): number {
  const rounded = Math.round(value)
  const lo = Math.min(min, max)
  const hi = Math.max(min, max)
  return Math.max(lo, Math.min(hi, rounded))
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

function cloneObstacleWithOffset(source: BuilderObstacle, offsetX: number, offsetY: number): BuilderObstacle {
  const copy: BuilderObstacle = {
    ...JSON.parse(JSON.stringify(source)),
    id: uid(),
    x: source.x + offsetX,
    y: source.y + offsetY,
  }
  if (copy.type === 'pendulum') {
    copy.pivot_x = Number(source.pivot_x ?? source.x) + offsetX
    copy.pivot_y = Number(source.pivot_y ?? source.y) + offsetY
  }
  moveObstacle(copy, copy.x, copy.y)
  return copy
}

function obstaclesToCompactJson(list: BuilderObstacle[]): string {
  return JSON.stringify(list.map((o) => obstacleToSerializable(o)))
}

function safeGenerationSignature(): string {
  return JSON.stringify({
    obstacles: obstacles.value.map((o) => obstacleToSerializable(o)),
    hidden_ids: [...hiddenIds.value].sort(),
    target_max_risk: Math.round(generateSafeTarget.value),
    max_attempts: Math.round(generateSafeAttempts.value),
    analysis_height: safeAnalysisHeightForRequest(),
  })
}

function invalidateSafeGenerationIfStale() {
  if (
    lastSafeGeneration.value &&
    lastSafeGenerationSignature.value &&
    lastSafeGenerationSignature.value !== safeGenerationSignature()
  ) {
    lastSafeGeneration.value = null
    lastSafeGenerationSignature.value = null
  }
}

function clearSafeGenerationStatus() {
  lastSafeGeneration.value = null
  lastSafeGenerationSignature.value = null
}

function parseObstacleJson(raw: string): BuilderObstacle[] {
  const num = (v: unknown, fallback: number): number => {
    const n = Number(v)
    return Number.isFinite(n) ? n : fallback
  }
  if (!raw.trim()) return []
  const parsed = JSON.parse(raw)
  if (!Array.isArray(parsed)) throw new Error('Obstacle JSON must be an array')
  return parsed.map((it, idx) => {
    if (!it || typeof it !== 'object') {
      throw new Error(`Obstacle #${idx} must be an object`)
    }
    const o = it as Record<string, any>
    if (!isObstacleType(String(o.type))) {
      throw new Error(`Obstacle #${idx} type is not supported in builder`)
    }
    return {
      id: uid(),
      type: String(o.type) as ObstacleType,
      x: num(o.x, 0),
      y: num(o.y, 0),
      width: o.width !== undefined ? num(o.width, 260) : undefined,
      height: o.height !== undefined ? num(o.height, 30) : undefined,
      radius: o.radius !== undefined ? num(o.radius, 60) : undefined,
      angle_deg: o.angle_deg !== undefined ? num(o.angle_deg, 0) : undefined,
      thickness: o.thickness !== undefined ? num(o.thickness, 22) : undefined,
      rotation_speed_deg:
        o.rotation_speed_deg !== undefined ? num(o.rotation_speed_deg, 0) : undefined,
      gap_center_deg: o.gap_center_deg !== undefined ? num(o.gap_center_deg, 270) : undefined,
      gap_size_deg: o.gap_size_deg !== undefined ? num(o.gap_size_deg, 58) : undefined,
      amplitude: o.amplitude !== undefined ? num(o.amplitude, 80) : undefined,
      frequency_hz: o.frequency_hz !== undefined ? num(o.frequency_hz, 0.2) : undefined,
      axis: o.axis === 'y' ? 'y' : 'x',
      length: o.length !== undefined ? num(o.length, 240) : undefined,
      pivot_x: o.pivot_x !== undefined ? num(o.pivot_x, num(o.x, 0)) : undefined,
      pivot_y: o.pivot_y !== undefined ? num(o.pivot_y, num(o.y, 0)) : undefined,
      one_way: o.one_way === 'up' ? 'up' : 'down',
      spin_speed_deg: o.spin_speed_deg !== undefined ? num(o.spin_speed_deg, 120) : undefined,
      fill_color: o.fill_color ? String(o.fill_color) : '#182037',
      stroke_color: o.stroke_color ? String(o.stroke_color) : '#000000',
      opacity: o.opacity !== undefined ? num(o.opacity, 0.95) : 0.95,
    }
  })
}

function syncFromModel(raw: string) {
  try {
    const parsed = parseObstacleJson(raw)
    suppressEmit = true
    obstacles.value = parsed
    const firstId = parsed[0]?.id ?? null
    selectedId.value = firstId
    selectedIds.value = firstId ? [firstId] : []
    lockedIds.value = []
    hiddenIds.value = []
    if (parsed.length > 0) {
      const sorted = parsed
        .map((o) => obstaclePosition(o).y)
        .sort((a, b) => a - b)
      const rawCamera = (sorted[0] ?? 0) - 180
      const maxCamera = Math.max(0, props.worldHeight - viewportHeight)
      cameraY.value = Math.max(0, Math.min(maxCamera, rawCamera))
    }
    resetHistoryWithCurrent()
    parseError.value = ''
  } catch (err) {
    parseError.value = `Builder parse failed: ${String(err)}`
  } finally {
    suppressEmit = false
  }
}

function resetHistoryWithCurrent() {
  const snapshot = obstaclesToCompactJson(obstacles.value)
  historyStack.value = [snapshot]
  historyIndex.value = 0
}

function canUndo(): boolean {
  return historyIndex.value > 0
}

function canRedo(): boolean {
  return historyIndex.value >= 0 && historyIndex.value < historyStack.value.length - 1
}

function pushHistorySnapshot() {
  if (suppressEmit || applyingHistory.value) return
  const snapshot = obstaclesToCompactJson(obstacles.value)
  const idx = historyIndex.value
  if (idx >= 0 && historyStack.value[idx] === snapshot) return
  const nextStack = historyStack.value.slice(0, idx + 1)
  nextStack.push(snapshot)
  if (nextStack.length > 140) {
    const trim = nextStack.length - 140
    historyStack.value = nextStack.slice(trim)
    historyIndex.value = historyStack.value.length - 1
  } else {
    historyStack.value = nextStack
    historyIndex.value = nextStack.length - 1
  }
}

function scheduleHistorySnapshot() {
  if (historyDebounce) {
    window.clearTimeout(historyDebounce)
    historyDebounce = null
  }
  historyDebounce = window.setTimeout(() => {
    pushHistorySnapshot()
  }, 120)
}

function applyHistorySnapshot(snapshot: string) {
  applyingHistory.value = true
  try {
    const parsed = parseObstacleJson(snapshot)
    suppressEmit = true
    obstacles.value = parsed
    suppressEmit = false
    const payload = JSON.stringify(
      parsed.map((o) => obstacleToSerializable(o)),
      null,
      2,
    )
    emit('update:modelValue', payload)
    const firstId = parsed[0]?.id ?? null
    selectedId.value = firstId
    selectedIds.value = firstId ? [firstId] : []
    schedulePreview()
    scheduleRiskAnalyze()
  } finally {
    suppressEmit = false
    applyingHistory.value = false
  }
}

function undoHistory() {
  if (!canUndo()) return
  const next = historyIndex.value - 1
  historyIndex.value = next
  const snapshot = historyStack.value[next]
  if (!snapshot) return
  applyHistorySnapshot(snapshot)
}

function redoHistory() {
  if (!canRedo()) return
  const next = historyIndex.value + 1
  historyIndex.value = next
  const snapshot = historyStack.value[next]
  if (!snapshot) return
  applyHistorySnapshot(snapshot)
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
    const idSet = new Set(obstacles.value.map((o) => o.id))
    selectedIds.value = selectedIds.value.filter((id) => idSet.has(id))
    lockedIds.value = lockedIds.value.filter((id) => idSet.has(id))
    hiddenIds.value = hiddenIds.value.filter((id) => idSet.has(id))
    if (selectedId.value && !idSet.has(selectedId.value)) {
      selectedId.value = selectedIds.value[0] ?? null
    }
    if (suppressEmit) return
    scheduleHistorySnapshot()
    const payload = JSON.stringify(
      obstacles.value.map((o) => obstacleToSerializable(o)),
      null,
      2,
    )
    emit('update:modelValue', payload)
    applyRiskPayload(null, [])
    schedulePreview()
    scheduleRiskAnalyze()
    invalidateSafeGenerationIfStale()
  },
  { deep: true },
)

watch(hiddenIds, () => {
  applyRiskPayload(null, [])
  schedulePreview()
  scheduleRiskAnalyze()
  invalidateSafeGenerationIfStale()
})

watch([generateSafeTarget, generateSafeAttempts, () => props.worldHeight], () => {
  invalidateSafeGenerationIfStale()
})

watch([previewSampleFps, previewMaxFrames], () => {
  schedulePreview()
})

watch(autoPreview, (enabled) => {
  if (enabled) {
    schedulePreview()
  }
})

watch(
  [
    autoPreview,
    previewSampleFps,
    previewMaxFrames,
    snapEnabled,
    snapSize,
    showGrid,
    followPreviewCamera,
    generateCount,
    generateSpacing,
    generateSeed,
    generateSafeTarget,
    generateSafeAttempts,
  ],
  () => {
    savePrefs()
  },
)

watch(
  () => props.apiBase,
  () => {
    clearSafeGenerationStatus()
    void (async () => {
      const ok = await loadBuilderBootstrap()
      if (!ok) {
        await Promise.all([loadBuilderCapabilities(), loadObstacleTypeCatalog(), loadPresetTemplates()])
      }
      await refreshPreviewCacheInfo()
      schedulePreview()
      scheduleRiskAnalyze()
    })()
  },
)

const selectedObstacle = computed(() =>
  obstacles.value.find((o) => o.id === selectedId.value) ?? null,
)

const visibleObstacles = computed(() =>
  obstacles.value.filter((o) => !hiddenIds.value.includes(o.id)),
)
const visibleObstacleIndexById = computed(() => {
  const out: Record<string, number> = {}
  visibleObstacles.value.forEach((o, idx) => {
    out[o.id] = idx + 1
  })
  return out
})
const riskWarningTargetLabels = computed(() =>
  riskWarningTargetIds.value.map((ids) =>
    ids
      .map((id) => visibleObstacleIndexById.value[id])
      .filter((n): n is number => Number.isFinite(n))
      .sort((a, b) => a - b),
  ),
)

function isSelected(id: string): boolean {
  return selectedIds.value.includes(id)
}

function isLocked(id: string): boolean {
  return lockedIds.value.includes(id)
}

function isHidden(id: string): boolean {
  return hiddenIds.value.includes(id)
}

function clampCamera(y: number): number {
  return Math.max(0, Math.min(cameraMax.value, y))
}

function selectedIdSet(): Set<string> {
  if (selectedIds.value.length > 0) return new Set(selectedIds.value)
  if (selectedId.value) return new Set([selectedId.value])
  return new Set()
}

function focusOnObstacle(obs: BuilderObstacle | null, offset = 220) {
  if (!obs) return
  const pos = obstaclePosition(obs)
  cameraY.value = clampCamera(pos.y - offset)
}

function selectObstacle(id: string, additive = false) {
  if (additive) {
    if (selectedIds.value.includes(id)) {
      selectedIds.value = selectedIds.value.filter((v) => v !== id)
    } else {
      selectedIds.value = [...selectedIds.value, id]
    }
    selectedId.value = selectedIds.value[selectedIds.value.length - 1] ?? null
    return
  }
  selectedIds.value = [id]
  selectedId.value = id
}

function clickObstacleHandle(obs: BuilderObstacle, ev: MouseEvent) {
  selectObstacle(obs.id, ev.shiftKey)
}

function clickLayerRow(id: string, ev: MouseEvent) {
  selectObstacle(id, ev.shiftKey)
}

function nudgeSelection(dx: number, dy: number) {
  const ids = selectedIdSet()
  if (ids.size === 0) return
  for (const obs of obstacles.value) {
    if (!ids.has(obs.id) || isLocked(obs.id)) continue
    moveObstacle(obs, obs.x + dx, obs.y + dy)
  }
}

function shouldIgnoreKeyboardShortcuts(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  if (!el) return false
  const tag = (el.tagName || '').toLowerCase()
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return true
  if (el.isContentEditable) return true
  return false
}

function onWindowKeyDown(ev: KeyboardEvent) {
  if (shouldIgnoreKeyboardShortcuts(ev.target)) return
  const step = ev.shiftKey ? 20 : 5
  if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'z' && !ev.shiftKey) {
    ev.preventDefault()
    undoHistory()
    return
  }
  if (
    (ev.ctrlKey || ev.metaKey) &&
    (ev.key.toLowerCase() === 'y' || (ev.key.toLowerCase() === 'z' && ev.shiftKey))
  ) {
    ev.preventDefault()
    redoHistory()
    return
  }
  if (ev.key === 'Delete' || ev.key === 'Backspace') {
    const ids = selectedIdSet()
    if (ids.size > 0) {
      ev.preventDefault()
      deleteSelected()
    }
    return
  }
  if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'd') {
    if (selectedObstacle.value && selectedIds.value.length <= 1) {
      ev.preventDefault()
      duplicateSelected()
    }
    return
  }
  if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'a') {
    ev.preventDefault()
    selectAll()
    return
  }
  if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'c') {
    ev.preventDefault()
    void copySelectionToClipboard()
    return
  }
  if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'v') {
    ev.preventDefault()
    void pasteObstaclesFromClipboard()
    return
  }
  if (ev.key === 'Escape') {
    ev.preventDefault()
    clearSelection()
    return
  }
  if (ev.key === 'ArrowLeft') {
    ev.preventDefault()
    nudgeSelection(-step, 0)
    return
  }
  if (ev.key === 'ArrowRight') {
    ev.preventDefault()
    nudgeSelection(step, 0)
    return
  }
  if (ev.key === 'ArrowUp') {
    ev.preventDefault()
    nudgeSelection(0, -step)
    return
  }
  if (ev.key === 'ArrowDown') {
    ev.preventDefault()
    nudgeSelection(0, step)
  }
}

function loadPrefs() {
  try {
    const raw = window.localStorage.getItem(PREF_KEY)
    if (!raw) return
    const obj = JSON.parse(raw) as Record<string, unknown>
    const caps = builderCaps.value
    if (typeof obj.autoPreview === 'boolean') autoPreview.value = obj.autoPreview
    if (typeof obj.previewSampleFps === 'number') {
      previewSampleFps.value = clampRounded(
        obj.previewSampleFps,
        caps.preview.sample_fps.min,
        caps.preview.sample_fps.max,
      )
    }
    if (typeof obj.previewMaxFrames === 'number') {
      previewMaxFrames.value = clampRounded(
        obj.previewMaxFrames,
        caps.preview.max_frames.min,
        caps.preview.max_frames.max,
      )
    }
    if (typeof obj.snapEnabled === 'boolean') snapEnabled.value = obj.snapEnabled
    if (typeof obj.snapSize === 'number') {
      snapSize.value = Math.max(1, Math.min(200, Math.round(obj.snapSize)))
    }
    if (typeof obj.showGrid === 'boolean') showGrid.value = obj.showGrid
    if (typeof obj.followPreviewCamera === 'boolean') {
      followPreviewCamera.value = obj.followPreviewCamera
    }
    if (typeof obj.generateCount === 'number') {
      generateCount.value = clampRounded(
        obj.generateCount,
        caps.generator.count.min,
        caps.generator.count.max,
      )
    }
    if (typeof obj.generateSpacing === 'number') {
      generateSpacing.value = clampRounded(
        obj.generateSpacing,
        caps.generator.spacing.min,
        caps.generator.spacing.max,
      )
    }
    if (typeof obj.generateSeed === 'number') {
      generateSeed.value = clampRounded(
        obj.generateSeed,
        caps.generator.seed.min,
        caps.generator.seed.max,
      )
    }
    if (typeof obj.generateSafeTarget === 'number') {
      generateSafeTarget.value = clampRounded(
        obj.generateSafeTarget,
        caps.generator.safe_target_max_risk.min,
        caps.generator.safe_target_max_risk.max,
      )
    }
    if (typeof obj.generateSafeAttempts === 'number') {
      generateSafeAttempts.value = clampRounded(
        obj.generateSafeAttempts,
        caps.generator.safe_max_attempts.min,
        caps.generator.safe_max_attempts.max,
      )
    }
  } catch (_err) {
    // ignore corrupt local prefs
  }
}

function savePrefs() {
  try {
    const payload = {
      autoPreview: autoPreview.value,
      previewSampleFps: previewSampleFps.value,
      previewMaxFrames: previewMaxFrames.value,
      snapEnabled: snapEnabled.value,
      snapSize: snapSize.value,
      showGrid: showGrid.value,
      followPreviewCamera: followPreviewCamera.value,
      generateCount: generateCount.value,
      generateSpacing: generateSpacing.value,
      generateSeed: generateSeed.value,
      generateSafeTarget: generateSafeTarget.value,
      generateSafeAttempts: generateSafeAttempts.value,
    }
    window.localStorage.setItem(PREF_KEY, JSON.stringify(payload))
  } catch (_err) {
    // ignore storage failures
  }
}

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
  const rawType = ev.dataTransfer.getData('text/songracer-obstacle-type')
  if (!isObstacleType(rawType)) return
  const type = rawType as ObstacleType
  if (!paletteTypes.value.includes(type)) return
  const container = ev.currentTarget as HTMLElement
  const pt = toCanvasXY(ev.clientX, ev.clientY, container)
  const obs = defaultObstacle(type, snap(pt.x), snap(pt.y))
  obstacles.value.push(obs)
  selectedIds.value = [obs.id]
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
  const nx = Math.max(0, Math.min(courseWidth, snap(x)))
  const ny = Math.max(0, Math.min(props.worldHeight, snap(y)))
  obs.x = nx
  obs.y = ny
  if (obs.type === 'pendulum') {
    obs.pivot_x = nx
    obs.pivot_y = ny
  }
}

function startDragObstacle(obs: BuilderObstacle, ev: PointerEvent) {
  if (isLocked(obs.id)) return
  if (ev.shiftKey) {
    selectObstacle(obs.id, true)
    return
  }
  if (!isSelected(obs.id)) {
    selectObstacle(obs.id, false)
  }
  selectedId.value = obs.id
  const container = (ev.currentTarget as HTMLElement).closest('[data-builder-canvas]') as HTMLElement | null
  if (!container) return
  const pt = toCanvasXY(ev.clientX, ev.clientY, container)
  dragPointerStart.value = { x: pt.x, y: pt.y }
  const ids = selectedIdSet()
  const startMap: Record<string, { x: number; y: number }> = {}
  for (const o of obstacles.value) {
    if (!ids.has(o.id) || isLocked(o.id)) continue
    const p = obstaclePosition(o)
    startMap[o.id] = { x: p.x, y: p.y }
  }
  if (Object.keys(startMap).length === 0) {
    const p = obstaclePosition(obs)
    startMap[obs.id] = { x: p.x, y: p.y }
  }
  dragStartById.value = startMap
  const anchor = dragStartById.value[obs.id] ?? obstaclePosition(obs)
  dragOffset.value = { dx: pt.x - anchor.x, dy: pt.y - anchor.y }
  dragMode.value = 'move'
}

function onCanvasPointerMove(ev: PointerEvent) {
  if (dragMode.value !== 'move' || !dragPointerStart.value) return
  const container = ev.currentTarget as HTMLElement
  const pt = toCanvasXY(ev.clientX, ev.clientY, container)
  const targetX = pt.x - dragOffset.value.dx
  const targetY = pt.y - dragOffset.value.dy
  const startAnchor = selectedObstacle.value
    ? dragStartById.value[selectedObstacle.value.id]
    : undefined
  const anchorStartX = startAnchor?.x ?? dragPointerStart.value.x - dragOffset.value.dx
  const anchorStartY = startAnchor?.y ?? dragPointerStart.value.y - dragOffset.value.dy
  const dx = targetX - anchorStartX
  const dy = targetY - anchorStartY
  for (const o of obstacles.value) {
    const base = dragStartById.value[o.id]
    if (!base) continue
    moveObstacle(o, base.x + dx, base.y + dy)
  }
}

function stopDrag() {
  dragMode.value = 'none'
  dragPointerStart.value = null
  dragStartById.value = {}
}

function duplicateSelected() {
  if (!selectedObstacle.value || selectedIds.value.length > 1) return
  const source = selectedObstacle.value
  const copy = cloneObstacleWithOffset(source, 48, 48)
  obstacles.value.push(copy)
  selectedIds.value = [copy.id]
  selectedId.value = copy.id
}

function deleteSelected() {
  const ids = selectedIdSet()
  if (ids.size === 0) return
  obstacles.value = obstacles.value.filter((o) => !ids.has(o.id))
  selectedIds.value = []
  selectedId.value = null
}

function selectAll() {
  const ids = obstacles.value.map((o) => o.id)
  selectedIds.value = ids
  selectedId.value = ids[0] ?? null
}

function clearSelection() {
  selectedIds.value = []
  selectedId.value = null
}

async function copySelectionToClipboard() {
  const ids = selectedIdSet()
  if (ids.size === 0) {
    clipboardStatus.value = 'Nothing selected to copy.'
    return
  }
  const selected = obstacles.value
    .filter((o) => ids.has(o.id))
    .map((o) => obstacleToSerializable(o))
  const payload = JSON.stringify(selected, null, 2)
  try {
    await navigator.clipboard.writeText(payload)
    clipboardStatus.value = `Copied ${selected.length} obstacle${selected.length === 1 ? '' : 's'}.`
  } catch (_err) {
    clipboardStatus.value = 'Clipboard copy blocked by browser.'
  }
}

async function pasteObstaclesFromClipboard() {
  try {
    const raw = await navigator.clipboard.readText()
    if (!raw.trim()) {
      clipboardStatus.value = 'Clipboard is empty.'
      return
    }
    const parsed = JSON.parse(raw)
    const arr = Array.isArray(parsed) ? parsed : [parsed]
    const inserted: BuilderObstacle[] = []
    for (const item of arr) {
      if (!item || typeof item !== 'object') continue
      const type = String((item as Record<string, unknown>).type || '')
      if (!isObstacleType(type)) continue
      const base = {
        ...(item as Record<string, unknown>),
      }
      delete (base as Record<string, unknown>).id
      const src = parseObstacleJson(JSON.stringify([base]))[0]
      if (!src) continue
      inserted.push(cloneObstacleWithOffset(src, 60, 60))
    }
    if (inserted.length === 0) {
      clipboardStatus.value = 'Clipboard JSON has no supported obstacles.'
      return
    }
    obstacles.value.push(...inserted)
    const ids = inserted.map((o) => o.id)
    selectedIds.value = ids
    selectedId.value = ids[0] ?? null
    clipboardStatus.value = `Pasted ${inserted.length} obstacle${inserted.length === 1 ? '' : 's'}.`
  } catch (_err) {
    clipboardStatus.value = 'Clipboard paste failed.'
  }
}

function exportObstaclesFile() {
  const payload = JSON.stringify(
    obstacles.value.map((o) => obstacleToSerializable(o)),
    null,
    2,
  )
  const blob = new Blob([payload], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `songracer_obstacles_${Date.now()}.json`
  anchor.click()
  URL.revokeObjectURL(url)
}

function copyBuilderLink() {
  try {
    const payload = {
      v: 1,
      obstacles: obstacles.value.map((o) => obstacleToSerializable(o)),
    }
    const encoded = encodeURIComponent(JSON.stringify(payload))
    const url = new URL(window.location.href)
    url.searchParams.set('builder', encoded)
    void navigator.clipboard.writeText(url.toString())
    clipboardStatus.value = 'Builder share link copied.'
  } catch (_err) {
    clipboardStatus.value = 'Failed to create builder share link.'
  }
}

function tryLoadBuilderShareFromUrl() {
  try {
    const url = new URL(window.location.href)
    const raw = url.searchParams.get('builder')
    if (!raw) return
    const parsed = JSON.parse(decodeURIComponent(raw))
    const source = Array.isArray(parsed?.obstacles) ? parsed.obstacles : []
    const loaded = parseObstacleJson(JSON.stringify(source))
    if (loaded.length > 0) {
      obstacles.value = loaded
      const first = loaded[0]?.id ?? null
      selectedId.value = first
      selectedIds.value = first ? [first] : []
      clipboardStatus.value = `Loaded ${loaded.length} obstacle${loaded.length === 1 ? '' : 's'} from builder link.`
    }
    url.searchParams.delete('builder')
    window.history.replaceState({}, '', url.toString())
  } catch (_err) {
    // ignore malformed share links
  }
}

async function importObstaclesFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    const raw = await file.text()
    const parsed = parseObstacleJson(raw)
    obstacles.value = parsed
    const first = parsed[0]?.id ?? null
    selectedId.value = first
    selectedIds.value = first ? [first] : []
    clipboardStatus.value = `Imported ${parsed.length} obstacle${parsed.length === 1 ? '' : 's'}.`
  } catch (_err) {
    clipboardStatus.value = 'Obstacle file import failed.'
  } finally {
    input.value = ''
  }
}

function toggleHiddenForSelection() {
  const ids = selectedIdSet()
  if (ids.size === 0) return
  for (const id of ids) {
    toggleHidden(id)
  }
}

function toggleLockForSelection() {
  const ids = selectedIdSet()
  if (ids.size === 0) return
  for (const id of ids) {
    toggleLock(id)
  }
}

function selectedUnlockedObstacles(): BuilderObstacle[] {
  const ids = selectedIdSet()
  if (ids.size === 0) return []
  return obstacles.value.filter((o) => ids.has(o.id) && !isLocked(o.id))
}

function alignSelection(axis: 'x' | 'y') {
  const list = selectedUnlockedObstacles()
  if (list.length < 2) return
  const anchor = list[0]
  if (!anchor) return
  if (axis === 'x') {
    const x = anchor.x
    for (const o of list.slice(1)) {
      moveObstacle(o, x, o.y)
    }
  } else {
    const y = anchor.y
    for (const o of list.slice(1)) {
      moveObstacle(o, o.x, y)
    }
  }
}

function fallbackPresetTemplate(
  preset: 'starter' | 'rings' | 'gates',
): Array<Record<string, unknown>> {
  const make = (type: ObstacleType, x: number, y: number) =>
    obstacleToSerializable(defaultObstacle(type, x, y))
  if (preset === 'starter') {
    return [
      { ...make('rect', 280, 980), angle_deg: -22, width: 300 },
      { ...make('moving_rect', 760, 1120), angle_deg: 18, width: 290, amplitude: 120 },
      { ...make('ring_gap', 540, 1380), radius: 160, gap_size_deg: 64 },
      { ...make('spinner', 540, 1680), length: 340, spin_speed_deg: 160 },
      { ...make('one_way_gate', 540, 1940), width: 620, one_way: 'down' },
    ]
  }
  if (preset === 'rings') {
    return [
      { ...make('ring_gap', 350, 980), radius: 126, gap_center_deg: 250, gap_size_deg: 62 },
      { ...make('ring_gap', 730, 1210), radius: 130, gap_center_deg: 200, gap_size_deg: 58 },
      { ...make('ring_gap', 420, 1460), radius: 142, gap_center_deg: 280, gap_size_deg: 60 },
      { ...make('ring_gap', 700, 1730), radius: 132, gap_center_deg: 245, gap_size_deg: 58 },
      { ...make('spinner', 540, 2060), length: 320, spin_speed_deg: 150 },
    ]
  }
  return [
    { ...make('rect', 260, 940), angle_deg: -18, width: 320 },
    { ...make('one_way_gate', 540, 1120), width: 640, one_way: 'down' },
    { ...make('one_way_gate', 540, 1270), width: 640, one_way: 'up' },
    { ...make('moving_rect', 740, 1510), angle_deg: 14, width: 320, axis: 'x' },
    { ...make('pendulum', 540, 1820), length: 290, angle_deg: 15, amplitude: 56 },
  ]
}

function applyPreset(preset: 'starter' | 'rings' | 'gates') {
  const fromApi = templateCatalog.value[preset]
  const raw = Array.isArray(fromApi) && fromApi.length > 0 ? fromApi : fallbackPresetTemplate(preset)
  try {
    obstacles.value = parseObstacleJson(JSON.stringify(raw))
  } catch (_err) {
    obstacles.value = parseObstacleJson(JSON.stringify(fallbackPresetTemplate(preset)))
  }
  const first = obstacles.value[0]?.id ?? null
  selectedId.value = first
  selectedIds.value = first ? [first] : []
}

function clearObstacles() {
  obstacles.value = []
  selectedId.value = null
  selectedIds.value = []
  lockedIds.value = []
  hiddenIds.value = []
}

async function generateObstacleStream(mode: 'replace' | 'append') {
  const existingYs = obstacles.value.map((o) => obstaclePosition(o).y)
  const maxY = existingYs.length > 0 ? Math.max(...existingYs) : 0
  const startY =
    mode === 'append' ? Math.max(900, maxY + generateSpacing.value) : Math.max(900, cameraY.value + 220)
  try {
    const resp = await fetch(`${props.apiBase}/templates/obstacles/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        count: Math.max(
          builderCaps.value.generator.count.min,
          Math.min(builderCaps.value.generator.count.max, Math.round(generateCount.value)),
        ),
        start_y: Math.max(
          builderCaps.value.generator.start_y.min,
          Math.min(builderCaps.value.generator.start_y.max, startY),
        ),
        spacing: Math.max(
          builderCaps.value.generator.spacing.min,
          Math.min(
            builderCaps.value.generator.spacing.max,
            Math.round(generateSpacing.value),
          ),
        ),
        width: Math.max(
          builderCaps.value.generator.width.min,
          Math.min(builderCaps.value.generator.width.max, courseWidth),
        ),
        seed: Math.max(
          builderCaps.value.generator.seed.min,
          Math.min(builderCaps.value.generator.seed.max, Math.round(generateSeed.value)),
        ),
      }),
    })
    if (!resp.ok) {
      throw new Error(await resp.text())
    }
    const body = await resp.json()
    const generatedRaw = Array.isArray(body?.obstacles) ? body.obstacles : []
    const generated = parseObstacleJson(JSON.stringify(generatedRaw))
    if (mode === 'replace') {
      obstacles.value = generated
    } else {
      obstacles.value = [...obstacles.value, ...generated]
    }
    const first = generated[0]?.id ?? obstacles.value[0]?.id ?? null
    selectedId.value = first
    selectedIds.value = first ? [first] : []
    generateSeed.value = Math.max(0, Math.round(Number(body?.seed ?? generateSeed.value) + 1))
    lastSafeGeneration.value = null
    lastSafeGenerationSignature.value = null
    clipboardStatus.value = `Generated ${generated.length} obstacle${generated.length === 1 ? '' : 's'} (${mode}).`
  } catch (_err) {
    lastSafeGeneration.value = null
    lastSafeGenerationSignature.value = null
    clipboardStatus.value = 'Failed to generate obstacle stream.'
  }
}

async function generateSafeObstacleStream(mode: 'replace' | 'append') {
  const existingYs = obstacles.value.map((o) => obstaclePosition(o).y)
  const maxY = existingYs.length > 0 ? Math.max(...existingYs) : 0
  const startY =
    mode === 'append' ? Math.max(900, maxY + generateSpacing.value) : Math.max(900, cameraY.value + 220)
  const safeAnalysisHeight = safeAnalysisHeightForRequest()
  try {
    const resp = await fetch(`${props.apiBase}/templates/obstacles/generate-safe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        count: Math.max(
          builderCaps.value.generator.count.min,
          Math.min(builderCaps.value.generator.count.max, Math.round(generateCount.value)),
        ),
        start_y: Math.max(
          builderCaps.value.generator.start_y.min,
          Math.min(builderCaps.value.generator.start_y.max, startY),
        ),
        spacing: Math.max(
          builderCaps.value.generator.spacing.min,
          Math.min(
            builderCaps.value.generator.spacing.max,
            Math.round(generateSpacing.value),
          ),
        ),
        width: Math.max(
          builderCaps.value.generator.width.min,
          Math.min(builderCaps.value.generator.width.max, courseWidth),
        ),
        seed: Math.max(
          builderCaps.value.generator.seed.min,
          Math.min(builderCaps.value.generator.seed.max, Math.round(generateSeed.value)),
        ),
        target_max_risk: Math.max(
          builderCaps.value.generator.safe_target_max_risk.min,
          Math.min(
            builderCaps.value.generator.safe_target_max_risk.max,
            Math.round(generateSafeTarget.value),
          ),
        ),
        max_attempts: Math.max(
          builderCaps.value.generator.safe_max_attempts.min,
          Math.min(
            builderCaps.value.generator.safe_max_attempts.max,
            Math.round(generateSafeAttempts.value),
          ),
        ),
        analysis_height: safeAnalysisHeight,
      }),
    })
    if (!resp.ok) {
      throw new Error(await resp.text())
    }
    const body = await resp.json()
    const generatedRaw = Array.isArray(body?.obstacles) ? body.obstacles : []
    const generated = parseObstacleJson(JSON.stringify(generatedRaw))
    if (mode === 'replace') {
      obstacles.value = generated
    } else {
      obstacles.value = [...obstacles.value, ...generated]
    }
    const first = generated[0]?.id ?? obstacles.value[0]?.id ?? null
    selectedId.value = first
    selectedIds.value = first ? [first] : []
    generateSeed.value = Math.max(0, Math.round(Number(body?.seed ?? generateSeed.value) + 1))
    const risk = Number(body?.risk_score ?? 0)
    const warnings = Array.isArray(body?.warnings) ? body.warnings : []
    applyRiskPayload(risk, warnings)
    const attempts = Number(body?.attempts ?? 1)
    const accepted = Boolean(body?.accepted)
    const resolvedAnalysisHeight =
      Number(body?.analysis_height) > 0 ? Math.round(Number(body.analysis_height)) : safeAnalysisHeight
    lastSafeGeneration.value = {
      seed: Number(body?.seed ?? generateSeed.value),
      risk,
      attempts,
      accepted,
      warnings: Number(body?.warning_count ?? warnings.length),
      analysisHeight: resolvedAnalysisHeight,
    }
    lastSafeGenerationSignature.value = safeGenerationSignature()
    clipboardStatus.value = `Generated ${generated.length} safe obstacle${generated.length === 1 ? '' : 's'} (${mode}) · risk ${risk} · attempts ${attempts} · analysis height ${resolvedAnalysisHeight}${accepted ? '' : ' (best effort)'}.`
  } catch (_err) {
    lastSafeGeneration.value = null
    lastSafeGenerationSignature.value = null
    clipboardStatus.value = 'Failed to generate safe obstacle stream.'
  }
}

function moveSelectedLayer(delta: -1 | 1) {
  if (!selectedId.value) return
  const idx = obstacles.value.findIndex((o) => o.id === selectedId.value)
  if (idx < 0) return
  const target = idx + delta
  if (target < 0 || target >= obstacles.value.length) return
  const next = obstacles.value.slice()
  const [item] = next.splice(idx, 1)
  if (!item) return
  next.splice(target, 0, item)
  obstacles.value = next
}

function toggleLock(id: string) {
  if (lockedIds.value.includes(id)) {
    lockedIds.value = lockedIds.value.filter((v) => v !== id)
  } else {
    lockedIds.value = [...lockedIds.value, id]
  }
}

function toggleHidden(id: string) {
  if (hiddenIds.value.includes(id)) {
    hiddenIds.value = hiddenIds.value.filter((v) => v !== id)
  } else {
    hiddenIds.value = [...hiddenIds.value, id]
  }
}

const cameraMax = computed(() => Math.max(0, props.worldHeight - viewportHeight))

watch(
  () => props.worldHeight,
  () => {
    cameraY.value = Math.max(0, Math.min(cameraY.value, cameraMax.value))
    schedulePreview()
    scheduleRiskAnalyze()
  },
)

watch(
  [() => props.duration, () => props.countdown, () => props.winnerHold],
  () => {
    schedulePreview()
  },
)

watch(
  () => props.racers,
  () => {
    schedulePreview()
  },
  { deep: true },
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

function applyBuilderCapabilities(body: unknown) {
  const obj = body as Record<string, any> | null
  const p = obj?.preview
  const g = obj?.generator
  if (!p || !g) return
  const fallback = defaultBuilderCaps()
  builderCaps.value = {
    preview: {
      sample_fps: normalizeCapRange(p.sample_fps, fallback.preview.sample_fps),
      max_frames: normalizeCapRange(p.max_frames, fallback.preview.max_frames),
    },
    generator: {
      count: normalizeCapRange(g.count, fallback.generator.count),
      start_y: normalizeCapRange(g.start_y, fallback.generator.start_y),
      spacing: normalizeCapRange(g.spacing, fallback.generator.spacing),
      width: normalizeCapRange(g.width, fallback.generator.width),
      seed: normalizeCapRange(g.seed, fallback.generator.seed),
      safe_target_max_risk: normalizeCapRange(
        g.safe_target_max_risk,
        fallback.generator.safe_target_max_risk,
      ),
      safe_max_attempts: normalizeCapRange(
        g.safe_max_attempts,
        fallback.generator.safe_max_attempts,
      ),
      safe_analysis_height: normalizeCapRange(
        g.safe_analysis_height,
        fallback.generator.safe_analysis_height,
      ),
    },
  }
  previewSampleFps.value = Math.max(
    builderCaps.value.preview.sample_fps.min,
    Math.min(builderCaps.value.preview.sample_fps.max, previewSampleFps.value),
  )
  previewMaxFrames.value = Math.max(
    builderCaps.value.preview.max_frames.min,
    Math.min(builderCaps.value.preview.max_frames.max, previewMaxFrames.value),
  )
  generateCount.value = Math.max(
    builderCaps.value.generator.count.min,
    Math.min(builderCaps.value.generator.count.max, generateCount.value),
  )
  generateSpacing.value = Math.max(
    builderCaps.value.generator.spacing.min,
    Math.min(builderCaps.value.generator.spacing.max, generateSpacing.value),
  )
  generateSeed.value = Math.max(
    builderCaps.value.generator.seed.min,
    Math.min(builderCaps.value.generator.seed.max, generateSeed.value),
  )
  generateSafeTarget.value = Math.max(
    builderCaps.value.generator.safe_target_max_risk.min,
    Math.min(builderCaps.value.generator.safe_target_max_risk.max, generateSafeTarget.value),
  )
  generateSafeAttempts.value = Math.max(
    builderCaps.value.generator.safe_max_attempts.min,
    Math.min(builderCaps.value.generator.safe_max_attempts.max, generateSafeAttempts.value),
  )
  invalidateSafeGenerationIfStale()
  scheduleRiskAnalyze()
}

function applyObstacleTypeCatalog(entriesInput: unknown) {
  const entries = Array.isArray(entriesInput) ? entriesInput : []
  const nextTypes: ObstacleType[] = []
  const labelMap: Record<string, string> = {}
  for (const item of entries) {
    if (!item || typeof item !== 'object') continue
    const t = String((item as Record<string, unknown>).type || '')
    if (!isObstacleType(t)) continue
    if (!nextTypes.includes(t)) {
      nextTypes.push(t)
    }
    const label = String((item as Record<string, unknown>).label || '').trim()
    if (label) {
      labelMap[t] = label
    }
  }
  if (nextTypes.length > 0) {
    paletteTypes.value = nextTypes
    paletteLabelByType.value = {
      ...Object.fromEntries(FALLBACK_PALETTE_TYPES.map((t) => [t, t.replace(/_/g, ' ')])),
      ...labelMap,
    }
  }
}

function applyTemplateCatalog(body: unknown) {
  const obj = body as Record<string, unknown> | null
  const t = obj?.templates
  if (!t || typeof t !== 'object') return
  const next: Record<string, Array<Record<string, unknown>>> = {}
  for (const [name, value] of Object.entries(t as Record<string, unknown>)) {
    if (Array.isArray(value)) {
      next[name] = value.filter((v) => !!v && typeof v === 'object') as Array<
        Record<string, unknown>
      >
    }
  }
  if (Object.keys(next).length > 0) {
    templateCatalog.value = next
    templateSource.value = 'api'
    templateVersion.value = String(obj?.version || '')
  }
}

async function loadBuilderBootstrap() {
  try {
    const resp = await fetch(`${props.apiBase}/builder/bootstrap`)
    if (!resp.ok) {
      bootstrapVersion.value = ''
      return false
    }
    const body = await resp.json()
    applyBuilderCapabilities((body as Record<string, unknown>).capabilities)
    applyObstacleTypeCatalog((body as Record<string, unknown>).obstacle_types)
    applyTemplateCatalog((body as Record<string, unknown>).templates)
    bootstrapVersion.value = String((body as Record<string, unknown>).bootstrap_version || '')
    return true
  } catch (_err) {
    bootstrapVersion.value = ''
    return false
  }
}

async function loadBuilderCapabilities() {
  try {
    const resp = await fetch(`${props.apiBase}/builder/capabilities`)
    if (!resp.ok) return
    const body = await resp.json()
    applyBuilderCapabilities(body)
  } catch (_err) {
    // keep defaults when capabilities endpoint unavailable
  }
}

async function loadObstacleTypeCatalog() {
  try {
    const resp = await fetch(`${props.apiBase}/templates/obstacle-types`)
    if (!resp.ok) return
    const body = await resp.json()
    applyObstacleTypeCatalog(body?.types)
  } catch (_err) {
    // ignore catalog load failure and keep fallback palette
  }
}

async function loadPresetTemplates() {
  try {
    const resp = await fetch(`${props.apiBase}/templates/obstacles`)
    if (!resp.ok) return
    const body = await resp.json()
    applyTemplateCatalog(body)
  } catch (_err) {
    // ignore template fetch failures and keep local fallback templates
    templateSource.value = 'fallback'
    templateVersion.value = ''
  }
}

async function refreshPreviewCacheInfo() {
  try {
    const resp = await fetch(`${props.apiBase}/preview/cache`)
    if (!resp.ok) return
    const body = await resp.json()
    previewCacheSize.value = Number(body.size || 0)
    previewCacheMax.value = Number(body.max_size || 0)
  } catch (_err) {
    // ignore cache diagnostics failures
  }
}

async function clearPreviewCache() {
  try {
    const resp = await fetch(`${props.apiBase}/preview/cache/clear`, { method: 'POST' })
    if (!resp.ok) return
    const body = await resp.json()
    previewCacheSize.value = Number(body.size || 0)
    previewCacheMax.value = Number(body.max_size || previewCacheMax.value || 0)
    clipboardStatus.value = `Cleared preview cache entries: ${Number(body.cleared || 0)}`
  } catch (_err) {
    clipboardStatus.value = 'Failed to clear preview cache.'
  }
}

async function requestPreview() {
  const req = ++previewRequestNonce
  previewLoading.value = true
  previewError.value = ''
  try {
    const resp = await fetch(`${props.apiBase}/preview/simulate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        seed: 13,
        render: {
          width: courseWidth,
          height: courseViewportHeight,
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
        obstacles: visibleObstacles.value.map((o) => obstacleToSerializable(o)),
        sample_fps: Math.max(
          builderCaps.value.preview.sample_fps.min,
          Math.min(
            builderCaps.value.preview.sample_fps.max,
            Math.round(previewSampleFps.value),
          ),
        ),
        max_frames: Math.max(
          builderCaps.value.preview.max_frames.min,
          Math.min(
            builderCaps.value.preview.max_frames.max,
            Math.round(previewMaxFrames.value),
          ),
        ),
      }),
    })
    if (!resp.ok) {
      throw new Error(await resp.text())
    }
    const body = await resp.json()
    if (req !== previewRequestNonce) {
      return
    }
    previewData.value = {
      requested_sample_fps: Number(body.requested_sample_fps ?? previewSampleFps.value),
      requested_max_frames: Number(body.requested_max_frames ?? previewMaxFrames.value),
      sample_fps: Number(body.sample_fps ?? 15),
      sample_step_frames: Number(body.sample_step_frames ?? 1),
      sample_interval_seconds: Number(body.sample_interval_seconds ?? 1 / 15),
      total_source_frames: Number(body.total_source_frames ?? 0),
      returned_last_sample_frame_index: Number(body.returned_last_sample_frame_index ?? -1),
      source_duration_seconds: Number(body.source_duration_seconds ?? 0),
      returned_sample_frames: Number(
        body.returned_sample_frames ??
          (Array.isArray(body.frame_indices) ? body.frame_indices.length : 0),
      ),
      sampling_coverage_ratio: Number(body.sampling_coverage_ratio ?? 0),
      sampled_coverage_ratio: Number(body.sampled_coverage_ratio ?? 0),
      returned_sample_duration_seconds: Number(body.returned_sample_duration_seconds ?? 0),
      total_sample_duration_seconds: Number(body.total_sample_duration_seconds ?? 0),
      total_last_sample_frame_index: Number(body.total_last_sample_frame_index ?? -1),
      positions: Array.isArray(body.positions) ? body.positions : [],
      leaders: Array.isArray(body.leaders) ? body.leaders : [],
      camera_y: Array.isArray(body.camera_y) ? body.camera_y : [],
      states: Array.isArray(body.states) ? body.states : [],
      obstacle_visuals: Array.isArray(body.obstacle_visuals) ? body.obstacle_visuals : [],
      winner_index: Number(body.winner_index ?? -1),
      winner_frame: Number(body.winner_frame ?? -1),
      total_sample_frames: Number(body.total_sample_frames ?? 0),
      truncated: Boolean(body.truncated),
      cache_hit: Boolean(body.cache_hit),
    }
    previewFrame.value = 0
    if (followPreviewCamera.value && previewData.value.camera_y.length > 0) {
      cameraY.value = Math.max(0, Math.min(cameraMax.value, Number(previewData.value.camera_y[0] ?? 0)))
    }
  } catch (err) {
    if (req !== previewRequestNonce) {
      return
    }
    previewError.value = String(err)
  } finally {
    if (req === previewRequestNonce) {
      previewLoading.value = false
      void refreshPreviewCacheInfo()
    }
  }
}

async function analyzeRisk() {
  const analysisHeight = safeAnalysisHeightForRequest()
  try {
    const resp = await fetch(`${props.apiBase}/analyze/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        config: {
          render: { width: courseWidth, height: analysisHeight },
          obstacles: visibleObstacles.value.map((o) => obstacleToSerializable(o)),
        },
      }),
    })
    if (!resp.ok) {
      throw new Error(await resp.text())
    }
    const body = await resp.json()
    applyRiskPayload(
      Number(body.risk_score ?? 0),
      Array.isArray(body.warnings) ? body.warnings : [],
    )
  } catch (_err) {
    applyRiskPayload(null, [])
  }
}

function schedulePreview() {
  if (!autoPreview.value) return
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

watch(previewFrame, (next) => {
  if (!previewData.value) return
  const max = Math.max(0, previewData.value.positions.length - 1)
  if (next < 0) {
    previewFrame.value = 0
    return
  }
  if (next > max) {
    previewFrame.value = max
    return
  }
  if (followPreviewCamera.value && previewData.value.camera_y?.length) {
    cameraY.value = clampCamera(
      Number(previewData.value.camera_y[Math.min(next, previewData.value.camera_y.length - 1)] ?? cameraY.value),
    )
  }
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
    return visibleObstacles.value.map((o) => {
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

function previewTimeText(): string {
  if (!previewData.value || previewData.value.positions.length === 0) return ''
  const i = Math.min(previewFrame.value, previewData.value.positions.length - 1)
  const current = i * Math.max(0, previewData.value.sample_interval_seconds || 0)
  const total = (previewData.value.positions.length - 1) * Math.max(0, previewData.value.sample_interval_seconds || 0)
  return `${current.toFixed(2)}s / ${total.toFixed(2)}s`
}

function previewTruncationText(): string {
  if (!previewData.value) return ''
  const shown = Number(previewData.value.returned_sample_frames || previewData.value.positions.length)
  const total = Number(previewData.value.total_sample_frames || shown)
  const cap = Number(previewData.value.requested_max_frames || shown)
  const shownLast = Number(previewData.value.returned_last_sample_frame_index ?? -1)
  const totalLast = Number(previewData.value.total_last_sample_frame_index ?? -1)
  const idxHint =
    shownLast >= 0 && totalLast >= shownLast ? ` last idx ${shownLast}/${totalLast}.` : ''
  return `Preview truncated to ${shown} / ${total} sampled frames (requested max ${cap}).${idxHint}`
}

function previewSampleCountText(): string {
  if (!previewData.value) return ''
  const shown = Number(previewData.value.returned_sample_frames || previewData.value.positions.length)
  const total = Number(previewData.value.total_sample_frames || shown)
  if (!Number.isFinite(shown) || shown <= 0) return ''
  if (!Number.isFinite(total) || total <= 0) return `${Math.round(shown)} samples`
  return `samples ${Math.round(shown)}/${Math.round(total)}`
}

function previewSampleIndexSpanText(): string {
  if (!previewData.value) return ''
  const shown = Number(previewData.value.returned_last_sample_frame_index ?? -1)
  const total = Number(previewData.value.total_last_sample_frame_index ?? -1)
  if (!Number.isFinite(shown) || !Number.isFinite(total) || shown < 0 || total < shown) return ''
  return `idx ${Math.round(shown)}/${Math.round(total)}`
}

function previewSampleCoverageText(): string {
  if (!previewData.value) return ''
  const ratio = Number(previewData.value.sampled_coverage_ratio ?? 0)
  if (!Number.isFinite(ratio) || ratio < 0) return ''
  const pct = Math.max(0, Math.min(100, ratio * 100))
  return `coverage ${pct.toFixed(1)}%`
}

function previewSourceCoverageText(): string {
  if (!previewData.value) return ''
  const ratio = Number(previewData.value.sampling_coverage_ratio ?? 0)
  if (!Number.isFinite(ratio) || ratio < 0) return ''
  const pct = Math.max(0, Math.min(100, ratio * 100))
  return `source cov ${pct.toFixed(1)}%`
}

function previewSourceFramesText(): string {
  if (!previewData.value) return ''
  const sourceFrames = Number(previewData.value.total_source_frames || 0)
  const sourceSeconds = Number(previewData.value.source_duration_seconds || 0)
  if (!Number.isFinite(sourceFrames) || sourceFrames <= 0) return ''
  if (!Number.isFinite(sourceSeconds) || sourceSeconds < 0) {
    return `source ${Math.round(sourceFrames)}f`
  }
  return `source ${Math.round(sourceFrames)}f / ${sourceSeconds.toFixed(2)}s`
}

function previewSampleWindowText(): string {
  if (!previewData.value) return ''
  const shown = Number(previewData.value.returned_sample_duration_seconds || 0)
  const totalFromApi = Number(previewData.value.total_sample_duration_seconds || 0)
  const totalFrames = Number(previewData.value.total_sample_frames || 0)
  const interval = Number(previewData.value.sample_interval_seconds || 0)
  if (!Number.isFinite(shown) || shown < 0) return ''
  if (Number.isFinite(totalFromApi) && totalFromApi >= 0) {
    return `window ${shown.toFixed(2)}s / ${totalFromApi.toFixed(2)}s`
  }
  if (
    !Number.isFinite(totalFrames) ||
    totalFrames <= 0 ||
    !Number.isFinite(interval) ||
    interval <= 0
  ) {
    return `window ${shown.toFixed(2)}s`
  }
  const total = Math.max(0, (totalFrames - 1) * interval)
  return `window ${shown.toFixed(2)}s / ${total.toFixed(2)}s`
}

function previewSamplingText(): string {
  if (!previewData.value) return ''
  const requested = Number(previewData.value.requested_sample_fps || 0)
  const requestedMaxFrames = Number(previewData.value.requested_max_frames || 0)
  const effective = Number(previewData.value.sample_fps || 0)
  const step = Number(previewData.value.sample_step_frames || 0)
  if (!Number.isFinite(effective) || effective <= 0) return ''
  const requestedText = Number.isFinite(requested) && requested > 0 ? `${requested}` : '?'
  const maxText =
    Number.isFinite(requestedMaxFrames) && requestedMaxFrames > 0
      ? `, max ${Math.round(requestedMaxFrames)}f`
      : ''
  if (!Number.isFinite(step) || step <= 0) {
    return `req ${requestedText} → ${effective.toFixed(2)} fps${maxText}`
  }
  return `req ${requestedText} → ${effective.toFixed(2)} fps (step ${step}f${maxText})`
}

function formatCapNumber(value: number): string {
  if (!Number.isFinite(value)) return '?'
  if (Math.abs(value - Math.round(value)) < 1e-9) return `${Math.round(value)}`
  return `${Number(value.toFixed(2))}`
}

function builderLimitsText(): string {
  const caps = builderCaps.value
  const effectiveSafeHeight = safeAnalysisHeightForRequest()
  return [
    `limits: preview fps ${formatCapNumber(caps.preview.sample_fps.min)}-${formatCapNumber(caps.preview.sample_fps.max)}`,
    `frames ${formatCapNumber(caps.preview.max_frames.min)}-${formatCapNumber(caps.preview.max_frames.max)}`,
    `gen count ${formatCapNumber(caps.generator.count.min)}-${formatCapNumber(caps.generator.count.max)}`,
    `safe risk ${formatCapNumber(caps.generator.safe_target_max_risk.min)}-${formatCapNumber(caps.generator.safe_target_max_risk.max)}`,
    `safe tries ${formatCapNumber(caps.generator.safe_max_attempts.min)}-${formatCapNumber(caps.generator.safe_max_attempts.max)}`,
    `safe height ${formatCapNumber(caps.generator.safe_analysis_height.min)}-${formatCapNumber(caps.generator.safe_analysis_height.max)}`,
    `using ${formatCapNumber(effectiveSafeHeight)}`,
  ].join(', ')
}

function safeAnalysisHeightForRequest(): number {
  const caps = builderCaps.value.generator.safe_analysis_height
  const requested = Number(props.worldHeight || caps.default)
  if (!Number.isFinite(requested) || requested <= 0) return Math.round(caps.default)
  return Math.round(Math.max(caps.min, Math.min(caps.max, requested)))
}

const previewFrameMax = computed(() => {
  const total = previewData.value?.positions.length ?? 0
  return Math.max(0, total - 1)
})

function previewStateLabel(): string {
  if (!previewData.value || previewData.value.states.length === 0) return ''
  const s = Number(previewData.value.states[Math.min(previewFrame.value, previewData.value.states.length - 1)] ?? 1)
  if (s === 0) return 'countdown'
  if (s === 2) return 'winner_hold'
  return 'racing'
}

function focusSelectedObstacle() {
  focusOnObstacle(selectedObstacle.value)
}

function fitCameraToContent() {
  if (obstacles.value.length === 0) {
    cameraY.value = 0
    return
  }
  const ys = obstacles.value.map((o) => obstaclePosition(o).y)
  const top = Math.min(...ys)
  cameraY.value = clampCamera(top - 140)
}

function randomizeGenerateSeed() {
  generateSeed.value = Math.floor(
    Math.random() * Math.max(1, builderCaps.value.generator.seed.max),
  )
}

function resetBuilderKnobsToDefaults() {
  previewSampleFps.value = Math.round(builderCaps.value.preview.sample_fps.default)
  previewMaxFrames.value = Math.round(builderCaps.value.preview.max_frames.default)
  generateCount.value = Math.round(builderCaps.value.generator.count.default)
  generateSpacing.value = Math.round(builderCaps.value.generator.spacing.default)
  generateSeed.value = Math.round(builderCaps.value.generator.seed.default)
  generateSafeTarget.value = Math.round(builderCaps.value.generator.safe_target_max_risk.default)
  generateSafeAttempts.value = Math.round(builderCaps.value.generator.safe_max_attempts.default)
  clipboardStatus.value = 'Builder knobs reset to capability defaults.'
}

onMounted(() => {
  loadPrefs()
  tryLoadBuilderShareFromUrl()
  void (async () => {
    const ok = await loadBuilderBootstrap()
    if (!ok) {
      await Promise.all([loadBuilderCapabilities(), loadObstacleTypeCatalog(), loadPresetTemplates()])
    }
    await refreshPreviewCacheInfo()
  })()
  void requestPreview()
  void analyzeRisk()
  window.addEventListener('keydown', onWindowKeyDown)
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
  if (historyDebounce) {
    window.clearTimeout(historyDebounce)
    historyDebounce = null
  }
  window.removeEventListener('keydown', onWindowKeyDown)
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
        :disabled="!selectedObstacle || selectedIds.length > 1"
        @click="duplicateSelected"
      >
        Duplicate
      </button>
      <button
        class="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-[11px] text-slate-100 hover:bg-slate-700"
        @click="selectAll"
      >
        Select All
      </button>
      <button
        class="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-[11px] text-slate-100 hover:bg-slate-700 disabled:opacity-40"
        :disabled="selectedIds.length === 0 && !selectedObstacle"
        @click="copySelectionToClipboard"
      >
        Copy
      </button>
      <button
        class="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-[11px] text-slate-100 hover:bg-slate-700"
        @click="pasteObstaclesFromClipboard"
      >
        Paste
      </button>
      <button
        class="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-[11px] text-slate-100 hover:bg-slate-700"
        @click="exportObstaclesFile"
      >
        Export Obstacles
      </button>
      <button
        class="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-[11px] text-slate-100 hover:bg-slate-700"
        @click="copyBuilderLink"
      >
        Copy Builder Link
      </button>
      <label class="cursor-pointer rounded border border-slate-600 bg-slate-800 px-2 py-1 text-[11px] text-slate-100 hover:bg-slate-700">
        Import Obstacles
        <input type="file" accept="application/json" class="hidden" @change="importObstaclesFile" />
      </label>
      <button
        class="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-[11px] text-slate-100 hover:bg-slate-700 disabled:opacity-40"
        :disabled="!canUndo()"
        @click="undoHistory"
      >
        Undo
      </button>
      <button
        class="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-[11px] text-slate-100 hover:bg-slate-700 disabled:opacity-40"
        :disabled="!canRedo()"
        @click="redoHistory"
      >
        Redo
      </button>
      <button
        class="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-[11px] text-slate-100 hover:bg-slate-700 disabled:opacity-40"
        :disabled="selectedIds.length === 0 && !selectedObstacle"
        @click="clearSelection"
      >
        Clear Selection
      </button>
      <button
        class="rounded border border-rose-600/50 bg-rose-900/40 px-2 py-1 text-[11px] text-rose-200 hover:bg-rose-800/50 disabled:opacity-40"
        :disabled="!selectedObstacle && selectedIds.length === 0"
        @click="deleteSelected"
      >
        Delete{{ selectedIds.length > 1 ? ` (${selectedIds.length})` : '' }}
      </button>
      <button
        class="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-[11px] text-slate-100 hover:bg-slate-700 disabled:opacity-40"
        :disabled="selectedIds.length === 0 && !selectedObstacle"
        @click="toggleLockForSelection"
      >
        Toggle Lock Selected
      </button>
      <button
        class="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-[11px] text-slate-100 hover:bg-slate-700 disabled:opacity-40"
        :disabled="selectedIds.length === 0 && !selectedObstacle"
        @click="toggleHiddenForSelection"
      >
        Toggle Hide Selected
      </button>
      <button
        class="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-[11px] text-slate-100 hover:bg-slate-700 disabled:opacity-40"
        :disabled="selectedIds.length < 2"
        @click="alignSelection('x')"
      >
        Align X
      </button>
      <button
        class="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-[11px] text-slate-100 hover:bg-slate-700 disabled:opacity-40"
        :disabled="selectedIds.length < 2"
        @click="alignSelection('y')"
      >
        Align Y
      </button>
      <button
        class="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-[11px] text-slate-100 hover:bg-slate-700 disabled:opacity-40"
        :disabled="!selectedObstacle"
        @click="moveSelectedLayer(-1)"
      >
        Layer Up
      </button>
      <button
        class="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-[11px] text-slate-100 hover:bg-slate-700 disabled:opacity-40"
        :disabled="!selectedObstacle"
        @click="moveSelectedLayer(1)"
      >
        Layer Down
      </button>
      <button
        class="rounded border border-cyan-600/50 bg-cyan-900/30 px-2 py-1 text-[11px] text-cyan-200 hover:bg-cyan-800/40"
        :disabled="previewLoading"
        @click="requestPreview"
      >
        {{ previewLoading ? 'Refreshing...' : 'Refresh Live Preview' }}
      </button>
      <button
        class="rounded border border-cyan-700/50 bg-cyan-950/40 px-2 py-1 text-[11px] text-cyan-200 hover:bg-cyan-900/40"
        @click="clearPreviewCache"
      >
        Clear Preview Cache
      </button>
      <span class="rounded border border-slate-700 px-2 py-1 text-[10px] text-slate-400">
        cache {{ previewCacheSize }}/{{ previewCacheMax || 0 }}
      </span>
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
      <span
        class="rounded border px-2 py-1 text-[10px]"
        :class="templateSource === 'api' ? 'border-emerald-500/50 text-emerald-300' : 'border-slate-600 text-slate-400'"
        :title="templateVersion || 'local fallback presets'"
      >
        Presets: {{ templateSource === 'api' ? `API catalog ${templateVersion}` : 'local fallback' }}
      </span>
      <span
        v-if="bootstrapVersion"
        class="rounded border border-slate-700 px-2 py-1 text-[10px] text-slate-400"
      >
        bootstrap {{ bootstrapVersion }}
      </span>
      <button
        class="rounded border border-rose-600/50 bg-rose-900/30 px-2 py-1 text-[11px] text-rose-200 hover:bg-rose-800/40 disabled:opacity-40"
        :disabled="obstacles.length === 0"
        @click="clearObstacles"
      >
        Clear Obstacles
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
      <button
        class="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-[11px] text-slate-100 hover:bg-slate-700 disabled:opacity-40"
        :disabled="!selectedObstacle"
        @click="focusSelectedObstacle"
      >
        Focus Selected
      </button>
      <button
        class="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-[11px] text-slate-100 hover:bg-slate-700"
        @click="fitCameraToContent"
      >
        Fit Camera
      </button>
    </div>

    <div class="flex flex-wrap items-center gap-2 text-[11px] text-slate-300">
      <span class="uppercase tracking-wide text-slate-400">Procedural stream</span>
      <label class="flex items-center gap-1">
        Count
        <input
          v-model.number="generateCount"
          type="number"
          :min="builderCaps.generator.count.min"
          :max="builderCaps.generator.count.max"
          class="w-14 rounded border border-slate-600 bg-slate-950 px-1 py-0.5"
        />
      </label>
      <label class="flex items-center gap-1">
        Spacing
        <input
          v-model.number="generateSpacing"
          type="number"
          :min="builderCaps.generator.spacing.min"
          :max="builderCaps.generator.spacing.max"
          class="w-16 rounded border border-slate-600 bg-slate-950 px-1 py-0.5"
        />
      </label>
      <label class="flex items-center gap-1">
        Seed
        <input
          v-model.number="generateSeed"
          type="number"
          :min="builderCaps.generator.seed.min"
          :max="builderCaps.generator.seed.max"
          class="w-20 rounded border border-slate-600 bg-slate-950 px-1 py-0.5"
        />
      </label>
      <label class="flex items-center gap-1">
        Safe risk
        <input
          v-model.number="generateSafeTarget"
          type="number"
          :min="builderCaps.generator.safe_target_max_risk.min"
          :max="builderCaps.generator.safe_target_max_risk.max"
          class="w-16 rounded border border-slate-600 bg-slate-950 px-1 py-0.5"
        />
      </label>
      <label class="flex items-center gap-1">
        Safe tries
        <input
          v-model.number="generateSafeAttempts"
          type="number"
          :min="builderCaps.generator.safe_max_attempts.min"
          :max="builderCaps.generator.safe_max_attempts.max"
          class="w-16 rounded border border-slate-600 bg-slate-950 px-1 py-0.5"
        />
      </label>
      <button
        class="rounded border border-fuchsia-800/50 bg-fuchsia-950/50 px-2 py-1 text-[11px] text-fuchsia-200 hover:bg-fuchsia-900/40"
        @click="randomizeGenerateSeed"
      >
        Random Seed
      </button>
      <button
        class="rounded border border-fuchsia-600/50 bg-fuchsia-900/30 px-2 py-1 text-[11px] text-fuchsia-200 hover:bg-fuchsia-800/40"
        @click="generateObstacleStream('append')"
      >
        Generate Append
      </button>
      <button
        class="rounded border border-fuchsia-700/50 bg-fuchsia-950/40 px-2 py-1 text-[11px] text-fuchsia-200 hover:bg-fuchsia-900/40"
        @click="generateObstacleStream('replace')"
      >
        Generate Replace
      </button>
      <button
        class="rounded border border-emerald-700/50 bg-emerald-900/30 px-2 py-1 text-[11px] text-emerald-200 hover:bg-emerald-800/40"
        @click="generateSafeObstacleStream('append')"
      >
        Generate Safe Append
      </button>
      <button
        class="rounded border border-emerald-800/50 bg-emerald-950/40 px-2 py-1 text-[11px] text-emerald-200 hover:bg-emerald-900/40"
        @click="generateSafeObstacleStream('replace')"
      >
        Generate Safe Replace
      </button>
      <button
        class="rounded border border-slate-600 bg-slate-900/50 px-2 py-1 text-[11px] text-slate-200 hover:bg-slate-800/60"
        @click="resetBuilderKnobsToDefaults"
      >
        Reset Knobs to Defaults
      </button>
      <span class="text-slate-500">
        {{ builderLimitsText() }}
      </span>
      <span
        v-if="lastSafeGeneration"
        class="rounded border px-2 py-1"
        :class="lastSafeGeneration.accepted ? 'border-emerald-500/50 text-emerald-300' : 'border-amber-500/50 text-amber-300'"
      >
        safe result: seed {{ lastSafeGeneration.seed }} · risk {{ lastSafeGeneration.risk }} ·
        warnings {{ lastSafeGeneration.warnings }} · tries {{ lastSafeGeneration.attempts }} ·
        height {{ lastSafeGeneration.analysisHeight }} ·
        {{ lastSafeGeneration.accepted ? 'accepted' : 'best effort' }}
      </span>
    </div>

    <div class="grid gap-3 lg:grid-cols-[2.1fr_1fr]">
      <div class="space-y-2">
        <div class="flex flex-wrap items-center gap-3 text-xs text-slate-300">
          <label class="flex items-center gap-1">
            <input v-model="autoPreview" type="checkbox" />
            Auto Preview
          </label>
          <label class="flex items-center gap-1">
            Sample FPS
            <input
              v-model.number="previewSampleFps"
              type="number"
              :min="builderCaps.preview.sample_fps.min"
              :max="builderCaps.preview.sample_fps.max"
              class="w-14 rounded border border-slate-600 bg-slate-950 px-1 py-0.5"
            />
          </label>
          <label class="flex items-center gap-1">
            Max frames
            <input
              v-model.number="previewMaxFrames"
              type="number"
              :min="builderCaps.preview.max_frames.min"
              :max="builderCaps.preview.max_frames.max"
              class="w-16 rounded border border-slate-600 bg-slate-950 px-1 py-0.5"
            />
          </label>
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
            Snap size
            <input
              v-model.number="snapSize"
              type="number"
              min="1"
              max="200"
              class="w-14 rounded border border-slate-600 bg-slate-950 px-1 py-0.5"
            />
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
        <div v-if="previewData && previewFrameMax > 0" class="flex items-center gap-2 text-xs text-slate-300">
          <span>Scrub</span>
          <input
            v-model.number="previewFrame"
            type="range"
            min="0"
            :max="previewFrameMax"
            step="1"
            class="w-56"
          />
          <span class="text-slate-400">{{ previewStateLabel() }}</span>
          <span class="text-slate-400">{{ previewTimeText() }}</span>
          <span class="text-slate-500">{{ previewSampleCountText() }}</span>
          <span class="text-slate-500">{{ previewSampleIndexSpanText() }}</span>
          <span class="text-slate-500">{{ previewSampleCoverageText() }}</span>
          <span class="text-slate-500">{{ previewSourceCoverageText() }}</span>
          <span class="text-slate-500">{{ previewSourceFramesText() }}</span>
          <span class="text-slate-500">{{ previewSampleWindowText() }}</span>
          <span class="text-slate-500">{{ previewSamplingText() }}</span>
          <span
            class="rounded border px-1.5 py-0.5 text-[10px]"
            :class="previewData.cache_hit ? 'border-emerald-500/40 text-emerald-300' : 'border-slate-600 text-slate-400'"
          >
            {{ previewData.cache_hit ? 'cache hit' : 'fresh sim' }}
          </span>
        </div>
        <p class="text-[11px] text-slate-500">
          Shortcuts: Delete=remove, Ctrl/Cmd+Z=undo, Ctrl/Cmd+Shift+Z or Ctrl/Cmd+Y=redo, Ctrl/Cmd+D=duplicate, Ctrl/Cmd+A=select all, Ctrl/Cmd+C=copy, Ctrl/Cmd+V=paste, Esc=clear, Arrows=move (Shift=20px).
        </p>
        <p
          v-if="previewData?.truncated"
          class="text-[11px] text-amber-300"
        >
          {{ previewTruncationText() }} Raise max frames for full timeline.
        </p>
        <p v-if="clipboardStatus" class="text-[11px] text-cyan-300">{{ clipboardStatus }}</p>

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
                v-if="isSelected(o.id)"
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
                :stroke="isLocked(o.id) ? '#f59e0b' : riskyObstacleIds.has(o.id) ? '#fb7185' : '#e2e8f0'"
                stroke-width="2"
                :class="isLocked(o.id) ? 'cursor-not-allowed' : 'cursor-move'"
                :opacity="isHidden(o.id) ? 0.45 : 1"
                @pointerdown.stop.prevent="startDragObstacle(o, $event)"
                @click.stop="clickObstacleHandle(o, $event)"
              />
              <text
                :x="obstaclePosition(o).x + 16"
                :y="obstacleScreenY(obstaclePosition(o).y) - 10"
                fill="#cbd5e1"
                font-size="14"
              >
                {{ idx + 1 }}{{ isLocked(o.id) ? ' 🔒' : '' }}{{ isHidden(o.id) ? ' 👁‍🗨' : '' }}
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
        <div class="mt-3 rounded border border-slate-700 bg-slate-950/60 p-2">
          <p class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-300">
            Obstacle layers (shift-click for multi-select)
          </p>
          <div class="max-h-40 space-y-1 overflow-auto pr-1 text-[11px] text-slate-200">
            <div
              v-for="(o, idx) in obstacles"
              :key="`row_${o.id}`"
              class="flex items-center gap-1 rounded border px-1.5 py-1"
              :class="isSelected(o.id) ? 'border-cyan-500/50 bg-cyan-900/20' : 'border-slate-700 bg-slate-900/60'"
            >
              <button
                class="rounded border border-slate-600 px-1.5 py-0.5 text-[10px] hover:bg-slate-700"
                @click="clickLayerRow(o.id, $event)"
              >
                #{{ idx + 1 }}
              </button>
              <span class="min-w-0 flex-1 truncate">{{ obstacleLabel(o.type) }}</span>
              <button
                class="rounded border border-slate-600 px-1.5 py-0.5 text-[10px] hover:bg-slate-700"
                :class="isHidden(o.id) ? 'text-amber-300' : 'text-slate-300'"
                @click="toggleHidden(o.id)"
              >
                {{ isHidden(o.id) ? 'Show' : 'Hide' }}
              </button>
              <button
                class="rounded border border-slate-600 px-1.5 py-0.5 text-[10px] hover:bg-slate-700"
                :class="isLocked(o.id) ? 'text-amber-300' : 'text-slate-300'"
                @click="toggleLock(o.id)"
              >
                {{ isLocked(o.id) ? 'Unlock' : 'Lock' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div v-if="riskWarnings.length > 0" class="rounded border border-slate-700 bg-slate-950/60 p-2">
      <p class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-300">
        Risk Warnings
      </p>
      <p class="mb-1 text-[10px] text-slate-500">
        Click a warning to focus linked obstacle(s).
      </p>
      <ul class="max-h-24 space-y-1 overflow-auto text-[11px] text-slate-400">
        <li v-for="(w, idx) in riskWarnings" :key="`${w.code}_${idx}`">
          <button
            type="button"
            class="w-full rounded border border-transparent px-1 py-0.5 text-left hover:border-slate-700 hover:bg-slate-900/60 disabled:cursor-default disabled:hover:border-transparent disabled:hover:bg-transparent"
            :disabled="(riskWarningTargetIds[idx]?.length ?? 0) === 0"
            @click="focusRiskWarningByIndex(idx)"
          >
            <span
              class="uppercase"
              :class="w.level === 'high' ? 'text-rose-300' : w.level === 'medium' ? 'text-amber-300' : 'text-sky-300'"
            >
              {{ w.level }}
            </span>
            · {{ w.message }}
            <span v-if="(riskWarningTargetIds[idx]?.length ?? 0) > 0" class="text-cyan-300">
              (focus {{ riskWarningTargetIds[idx]?.length ?? 0 }}
              <template v-if="(riskWarningTargetLabels[idx]?.length ?? 0) > 0">
                · #{{ (riskWarningTargetLabels[idx] || []).join(', #') }}
              </template>)
            </span>
          </button>
        </li>
      </ul>
    </div>
    <p v-if="parseError" class="text-xs text-rose-300">{{ parseError }}</p>
  </div>
</template>
