import { memo, useMemo } from 'react'
import dayjs from 'dayjs'
import type { Report } from '../types'
import { chartData } from '../chartData'
import { HeatmapChart } from './HeatmapChart'
import { MultiDayHeatmapChart } from './MultiDayHeatmapChart'
import { AppPieChart } from './AppPieChart'
import { MultiDayPieChart } from './MultiDayPieChart'
import { AppBarChart } from './AppBarChart'
import { MultiDayBarChart } from './MultiDayBarChart'

export const ReportChart = memo(function ReportChart({ report, chart, page }: { report: Report; chart: 'heatmap' | 'pie' | 'bar'; page: number }) {
  const data = useMemo(() => chartData(report), [report])
  const start = (page - 1) * 31
  const days = useMemo(() => data.days.slice(start, start + 31), [data, start])
  const slots = useMemo(() => data.hourlyActivity.slice(start, start + 31), [data, start])
  const hourly = useMemo(() => data.hourlyAppData.slice(start, start + 31), [data, start])
  const coverage = useMemo(() => report.days.slice(start, start + 31).map(day => day.coverage), [report, start])
  const selectedDate = useMemo(() => dayjs(report.start).toDate(), [report.start])
  const single = report.days.length === 1
  return <div className={`chart-stage ${chart === 'heatmap' ? 'heatmap-stage' : ''}`}>
    {chart === 'heatmap' && (single
      ? <HeatmapChart values={report.days[0].slots} coverage={report.days[0].coverage} dayStartHour={report.dayStartHour} selectedDate={selectedDate}/>
      : <MultiDayHeatmapChart hourlyActivity={slots} coverage={coverage} days={days} dayStartHour={report.dayStartHour}/>)}
    {chart === 'pie' && <div className="wide-chart">{single ? <AppPieChart appData={data.appTotals}/> : <MultiDayPieChart appTotals={data.appTotals} numDays={report.days.length}/>}</div>}
    {chart === 'bar' && <div className="wide-chart">{single ? <AppBarChart hourlyAppData={data.hourlyAppData[0]} dayStartHour={report.dayStartHour}/> : <MultiDayBarChart hourlyAppData={hourly} days={days} appTotals={data.appTotals} dayStartHour={report.dayStartHour}/>}</div>}
  </div>
})
