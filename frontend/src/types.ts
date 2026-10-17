export interface Settings {
  dayStartHour: number
  idleSeconds: number
  expandContexts: boolean
  detailThreshold: number
  splitIde: boolean
  splitDocuments: boolean
  splitSites: boolean
  ideProcesses: string[]
  documentProcesses: string[]
  browserProcesses: string[]
  excludedProcesses: string[]
  siteNames: string[]
  displayNames: Record<string, string>
}
export interface Status {
  demo: boolean
  paused: boolean
  resumeAt: string | null
  collecting: boolean
  active: boolean
  error: string | null
  lastMinute: number | null
  now: string
  version: string
}
export interface Storage {
  directory: string
  databaseBytes: number
  recordCount: number
  firstMinute: number | null
  lastMinute: number | null
}
export interface Application {
  key: string
  app: string
  context: string
  kind: 'app' | 'site' | 'project' | 'document'
  minutes: number
}
export interface Day {
  date: string
  active: number
  observed: number
  slots: number[]
  coverage: number[]
  hourly: Record<string, number>[]
}
export interface Report {
  start: string
  end: string
  dayStartHour: number
  expanded: boolean
  threshold: number
  days: Day[]
  apps: Application[]
  summary: {
    activeMinutes: number
    observedMinutes: number
    idleMinutes: number
    dailyAverage: number
    recordedDays: number
    peakHour: number | null
    topApp: Application | null
  }
}
export interface Bootstrap { settings: Settings; programDefaults: Pick<Settings, 'ideProcesses' | 'documentProcesses' | 'browserProcesses'>; storage: Storage; status: Status; startup: boolean }
export interface ExportResult { cancelled?: boolean; content?: string; filename: string; count: number }

export interface RecentRow { minute: number; time: string; active: boolean; process: string; title: string }
export interface Recent { start: string; end: string; endMinute: number; page: number; pageSize: number; total: number; rows: RecentRow[] }

export type CleanupSelection = { mode: 'range'; start: string; end: string } | { mode: 'before'; before: string }
export type CleanupPreview = CleanupSelection & { count: number; token: string | null }
export interface CleanupResult { deletedRows: number; compacted: boolean; storage: Storage }

export interface LegacySummary { filename: string; total: number; firstMinute: number; lastMinute: number; fallbackCount: number }
export interface LegacyPreview extends LegacySummary { token: string; duplicates: number; newRecords: number }
export interface LegacyResult extends LegacySummary { imported: number; duplicates: number; storage: Storage }

export interface UpdateStatus {
  phase: 'idle' | 'checking' | 'available' | 'latest' | 'unpublished' | 'downloading' | 'ready' | 'installing' | 'error'
  supported: boolean
  version: string | null
  notes: string
  source: 'github' | 'ghproxy' | null
  received: number
  total: number
  error: string
}
