import dayjs from 'dayjs'
import type { Report } from './types'

const WEEK_DAYS = ['日', '一', '二', '三', '四', '五', '六']

export function dailyDateLabel(value: string, today: string): string {
  const date = dayjs(value).startOf('day')
  const ago = dayjs(today).startOf('day').diff(date, 'day')
  const relative = ['今天', '昨天', '前天'][ago]
  return `${date.format('YYYY-MM-DD')} (${WEEK_DAYS[date.day()]})${relative ? ` ${relative}` : ''}`
}

export function barDateLabel(value: string, compact: boolean): string {
  const date = dayjs(value.replace(/^(\d{4})(\d{2})(\d{2})$/, '$1-$2-$3'))
  return `${date.format('M/D')}${compact ? '\n' : ' '}（${WEEK_DAYS[date.day()]}）`
}

export function escapeHtml(value: unknown): string {
  return String(value).replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]!))
}

export function formatNumber(value: number): string {
  return String(Math.round(value * 10) / 10)
}

export function duration(minutes: number): string {
  const rounded = Math.round(minutes * 10) / 10
  return rounded >= 60 ? `${Math.floor(rounded / 60)}h${formatNumber(rounded % 60)}m` : `${formatNumber(rounded)}m`
}

// Presentation-only consolidation, matching the original 90% / 12-item rule.
export function chartData(report: Report) {
  const names = Object.fromEntries(report.apps.map(app => [app.key, app.context ? `${app.app} - ${app.context}` : app.app]))
  const totals: Record<string, number> = {}
  report.apps.forEach(app => { const name = names[app.key]; totals[name] = (totals[name] || 0) + app.minutes })
  const total = report.summary.activeMinutes
  const kept = new Set<string>()
  let cumulative = 0
  for (const [name, value] of Object.entries(totals).sort((a,b) => b[1]-a[1])) {
    if (kept.size >= 12 || cumulative >= total * .9) break
    kept.add(name); cumulative += value
  }
  const consolidate = (values: Record<string, number>, alreadyNamed = false) => {
    const result: Record<string, number> = {}
    Object.entries(values).forEach(([key, value]) => {
      const name = alreadyNamed ? key : names[key]
      const label = kept.has(name) ? name : '其他'
      result[label] = (result[label] || 0) + value
    })
    return result
  }
  return {
    days: report.days.map(day => day.date.replace(/-/g, '')),
    hourlyActivity: report.days.map(day => day.slots),
    hourlyAppData: report.days.map(day => day.hourly.map(hour => consolidate(hour))),
    appTotals: consolidate(totals, true),
  }
}

export function chartDescription(report: Report, kind: 'heatmap' | 'pie' | 'bar') {
  const count = report.days.length
  const single = count === 1
  const workdays = report.days.filter(day => ![0,6].includes(dayjs(day.date).day()))
  const workdayTotal = workdays.reduce((sum, day) => sum + day.active, 0)
  const total = report.summary.activeMinutes
  const averages = single ? '' : `，日均 ${duration(total / count)}${workdays.length ? `，工作日均 ${duration(workdayTotal / workdays.length)}` : ''}`
  const prefix = single ? '' : `统计区间共 ${count} 天，`
  const granularity = `活跃时长按${report.activityGranularity}分钟粒度统计。`
  if (kind === 'heatmap') {
    const slots = report.days.flatMap(day => day.slots)
    const active = slots.filter(value => value > 0).length
    return {
      info: single
        ? `已点亮 ${active}/${slots.length} 格（${Math.round(active / slots.length * 100)}%），点亮时长 ${Math.floor(active * 5 / 60)}h${active * 5 % 60}m，活跃时长 ${duration(total)}`
        : `${prefix}总计 ${duration(total)}${averages}`,
      explanation: `每格表示${count <= 3 ? '5分钟' : '1小时'}，颜色表示实际活跃程度。${single ? '' : `${workdays.length}个工作日。`}一天从${report.dayStartHour}时起算。${granularity}`,
    }
  }
  return {
    info: `${prefix}总计 ${duration(total)}${averages}`,
    explanation: `${kind === 'pie' ? '展示各应用活跃时长占比' : single ? '堆叠柱状图展示每小时的应用时长' : '堆叠柱状图展示每天的应用时长'}，${kind === 'bar' && single ? '保留前5项，其余归入“其他”' : '按累计占比达到90%或超过12项后归入“其他”'}。${granularity}`,
  }
}
