import assert from 'node:assert/strict'
import test from 'node:test'
import { barDateLabel, chartData, chartDescription, dailyDateLabel, duration, escapeHtml, formatNumber } from '../src/chartData.ts'
import type { Application, Report } from '../src/types.ts'

function fixture(apps: Application[]): Report {
  const total = apps.reduce((sum,app) => sum+app.minutes,0)
  return {
    start:'2026-10-13',end:'2026-10-13',dayStartHour:4,activityGranularity:1,expanded:false,threshold:10,
    apps,
    days:[{ date:'2026-10-13',active:total,observed:total,slots:[total],coverage:[total],hourly:[Object.fromEntries(apps.map(app => [app.key,app.minutes]))] }],
    summary:{ activeMinutes:total,rawActiveMinutes:total,fiveMinuteActiveMinutes:Math.ceil(total/5)*5,observedMinutes:total,idleMinutes:0,dailyAverage:total,recordedDays:1,peakHour:4,topApp:apps[0] || null },
  }
}
const app = (key: string,minutes: number,name=key): Application => ({ key,minutes,app:name,context:'',kind:'app' })

test('fractional allocation stays precise until labels are formatted to at most one decimal', () => {
  const report = fixture([app('A',5/3),app('B',10/3)])
  report.activityGranularity = 5
  const data = chartData(report)
  assert.equal(data.appTotals.A,5/3)
  assert.equal(data.hourlyAppData[0][0].B,10/3)
  assert.equal(Object.values(data.appTotals).reduce((sum,value) => sum+value,0),5)
  assert.equal(duration(5/3),'1.7m')
  assert.equal(duration(200/3),'1h6.7m')
  assert.equal(duration(59.96),'1h0m')
  assert.equal(formatNumber(10/3),'3.3')
  assert.equal(formatNumber(100),'100')
  for (const kind of ['heatmap','pie','bar'] as const) assert.match(chartDescription(report,kind).explanation,/按5分钟粒度统计/)
})

test('daily captions mark only today, yesterday and the day before yesterday', () => {
  const today = '2026-10-18'
  assert.equal(dailyDateLabel('2026-10-18',today),'2026-10-18 (日) 今天')
  assert.equal(dailyDateLabel('2026-10-17',today),'2026-10-17 (六) 昨天')
  assert.equal(dailyDateLabel('2026-10-16',today),'2026-10-16 (五) 前天')
  assert.equal(dailyDateLabel('2026-10-15',today),'2026-10-15 (四)')
  assert.equal(dailyDateLabel('2026-10-19',today),'2026-10-19 (一)')
})

test('daily captions follow calendar boundaries across years and leap days', () => {
  assert.equal(dailyDateLabel('2026-12-31','2027-01-01'),'2026-12-31 (四) 昨天')
  assert.equal(dailyDateLabel('2026-12-30','2027-01-01'),'2026-12-30 (三) 前天')
  assert.equal(dailyDateLabel('2024-02-29','2024-03-01'),'2024-02-29 (四) 昨天')
  assert.equal(dailyDateLabel('2024-02-28','2024-03-01'),'2024-02-28 (三) 前天')
  assert.equal(dailyDateLabel('2026-10-17','2026-10-19'),'2026-10-17 (六) 前天')
})

test('multi-day bar ticks retain two lines and enclose weekdays in parentheses', () => {
  assert.equal(barDateLabel('20261012',true),'10/12\n（一）')
  assert.equal(barDateLabel('2026-10-18',true),'10/18\n（日）')
  assert.equal(barDateLabel('20261012',false),'10/12 （一）')
})

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

test('heatmap explanations use five-minute slots for up to three days and hours thereafter', () => {
  const report = fixture([app('editor',7)])
  for (let count = 1; count <= 4; count++) {
    report.days = Array.from({length:count}, (_,i) => ({...report.days[0], date:`2026-10-${13+i}`}))
    const text = chartDescription(report, 'heatmap')
    assert.match(text.explanation, count <= 3 ? /^每格表示5分钟/ : /^每格表示1小时/)
  }
})
