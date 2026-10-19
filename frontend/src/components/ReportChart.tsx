import { memo, useMemo } from 'react'
import dayjs from 'dayjs'
import type { Report } from '../types'
import { chartData, dailyDateLabel, duration } from '../chartData'
import { HeatmapChart } from './HeatmapChart'
import { MultiDayHeatmapChart } from './MultiDayHeatmapChart'
import { AppPieChart } from './AppPieChart'
import { MultiDayPieChart } from './MultiDayPieChart'
import { AppBarChart } from './AppBarChart'
import { MultiDayBarChart } from './MultiDayBarChart'

export const ReportChart = memo(function ReportChart({ report, chart, page, today }: { report: Report; chart: 'heatmap' | 'pie' | 'bar'; page: number; today: string }) {
  const data = useMemo(() => chartData(report), [report])
  const start = (page - 1) * 31
  const days = useMemo(() => data.days.slice(start, start + 31), [data, start])
  const slots = useMemo(() => data.hourlyActivity.slice(start, start + 31), [data, start])
  const hourly = useMemo(() => data.hourlyAppData.slice(start, start + 31), [data, start])
  const coverage = useMemo(() => report.days.slice(start, start + 31).map(day => day.coverage), [report, start])
  const dailyHeatmaps = useMemo(() => report.days.length <= 3
    ? report.days.map(day => ({ day, selectedDate: dayjs(day.date).toDate() }))
    : [], [report.days])
  const single = report.days.length === 1
  const dateCaption = single ? <figcaption className="chart-date-caption">{dailyDateLabel(report.days[0].date, today)}</figcaption> : null
  return <div className={`chart-stage${chart === 'heatmap' ? ' heatmap-stage' : ''}${chart === 'heatmap' && dailyHeatmaps.length ? ' daily-heatmap-stage' : ''}`}>
    {chart === 'heatmap' && (dailyHeatmaps.length
      ? <div className="daily-heatmaps">{dailyHeatmaps.map(({ day, selectedDate }) => <figure className="daily-heatmap" key={day.date}>
          <HeatmapChart values={day.slots} coverage={day.coverage} dayStartHour={report.dayStartHour} selectedDate={selectedDate}/>
          <figcaption className="chart-date-caption">{dailyDateLabel(day.date, today)}<br/>日活跃时长 {duration(day.active)}</figcaption>
        </figure>)}</div>
      : <MultiDayHeatmapChart hourlyActivity={slots} coverage={coverage} days={days} dayStartHour={report.dayStartHour}/>)}
    {chart === 'pie' && <figure className="chart-figure wide-chart">{single ? <AppPieChart appData={data.appTotals}/> : <MultiDayPieChart appTotals={data.appTotals} numDays={report.days.length}/>} {dateCaption}</figure>}
    {chart === 'bar' && <figure className="chart-figure wide-chart">{single ? <AppBarChart hourlyAppData={data.hourlyAppData[0]} dayStartHour={report.dayStartHour}/> : <MultiDayBarChart hourlyAppData={hourly} days={days} appTotals={data.appTotals} dayStartHour={report.dayStartHour}/>} {dateCaption}</figure>}
  </div>
})
