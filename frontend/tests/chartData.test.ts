import assert from 'node:assert/strict'
import test from 'node:test'
import { chartData, chartDescription, escapeHtml } from '../src/chartData.ts'
import type { Application, Report } from '../src/types.ts'

function fixture(apps: Application[]): Report {
  const total = apps.reduce((sum,app) => sum+app.minutes,0)
  return {
    start:'2026-10-13',end:'2026-10-13',dayStartHour:4,expanded:false,threshold:10,
    apps,
    days:[{ date:'2026-10-13',active:total,observed:total,slots:[total],coverage:[total],hourly:[Object.fromEntries(apps.map(app => [app.key,app.minutes]))] }],
    summary:{ activeMinutes:total,observedMinutes:total,idleMinutes:0,dailyAverage:total,recordedDays:1,peakHour:4,topApp:apps[0] || null },
  }
}
const app = (key: string,minutes: number,name=key): Application => ({ key,minutes,app:name,context:'',kind:'app' })

test('duplicate display names are merged without losing minutes', () => {
  const data = chartData(fixture([app('first',40,'Editor'),app('second',30,'Editor'),app('third',30,'Browser')]))
  assert.equal(data.appTotals.Editor,70)
  assert.equal(data.hourlyAppData[0][0].Editor,70)
  assert.equal(Object.values(data.appTotals).reduce((a,b) => a+b,0),100)
})

test('90 percent consolidation conserves total and hourly data', () => {
  const data=chartData(fixture([app('main',90),app('small',6),app('tiny',4)]))
  assert.deepEqual(data.appTotals,{main:90,'其他':10})
  assert.deepEqual(data.hourlyAppData[0][0],data.appTotals)
})

test('at most twelve named items are kept', () => {
  const data=chartData(fixture(Array.from({length:15},(_,i) => app(`app-${i}`,10))))
  assert.equal(Object.keys(data.appTotals).length,13)
  assert.equal(data.appTotals['其他'],30)
})

test('workday average uses actual recorded workday totals', () => {
  const report=fixture([app('editor',120)])
  report.days.push({...report.days[0],date:'2026-10-17',active:0,observed:0,slots:[0],coverage:[0],hourly:[{}]})
  const text=chartDescription(report,'pie')
  assert.match(text.info,/日均 1h0m/)
  assert.match(text.info,/工作日均 2h0m/)
})

test('user titles are escaped for tooltip HTML', () => {
  assert.equal(escapeHtml('<img src=x onerror="bad"> &'), '&lt;img src=x onerror=&quot;bad&quot;&gt; &amp;')
})

test('single heatmap distinguishes illuminated duration from actual activity', () => {
  const report = fixture([app('editor',7)])
  report.days[0].slots = [2,5,...Array(286).fill(0)]
  assert.equal(chartDescription(report,'heatmap').info, '已点亮 2/288 格（1%），点亮时长 0h10m，活跃时长 7m')
})

test('all multi day charts start with the calendar range length', () => {
  const report = fixture([app('editor',120)])
  report.days.push({...report.days[0],date:'2026-10-14'})
  for (const kind of ['heatmap','pie','bar'] as const) {
    assert.match(chartDescription(report,kind).info,/^统计区间共 2 天，总计 2h0m/)
  }
})
