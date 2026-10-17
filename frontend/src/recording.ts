import dayjs from 'dayjs'

export const PAUSE_OPTIONS = [
  { key: '5', label: '暂停 5 分钟' },
  { key: '60', label: '暂停 1 小时' },
  { key: '240', label: '暂停 4 小时' },
  { key: '1440', label: '暂停 1 天' },
]

export function resumeTimeLabel(resumeAt: string | null, now: string) {
  if (!resumeAt) return '已暂停'
  const end = dayjs(resumeAt)
  return `已暂停 · 预计 ${end.format(end.isSame(dayjs(now), 'day') ? 'HH:mm' : 'MM-DD HH:mm')} 恢复`
}
