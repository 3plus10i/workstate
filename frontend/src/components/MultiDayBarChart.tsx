import { escapeHtml } from '../chartData'
import { BAR_EMPHASIS, barValue } from '../barStyle'
import { useEffect, useRef } from 'react'
import * as echarts from '../echarts'

interface MultiDayBarChartProps {
  hourlyAppData: Record<string, number>[][]
  days: string[]
  appTotals: Record<string, number>
  dayStartHour: number
}

export function MultiDayBarChart({ hourlyAppData, days, appTotals, dayStartHour }: MultiDayBarChartProps) {
  const chartRef = useRef<HTMLDivElement>(null)
  const chartInstanceRef = useRef<echarts.ECharts | null>(null)

  useEffect(() => () => {
    chartInstanceRef.current?.dispose()
    chartInstanceRef.current = null
  }, [])
  const numDays = days.length
  const compact = numDays <= 7

  useEffect(() => {
    if (!chartRef.current) return
    if (!chartInstanceRef.current) {
      chartInstanceRef.current = echarts.init(chartRef.current)
    }
    const chart = chartInstanceRef.current
    chartRef.current.dataset.renderCount = String(Number(chartRef.current.dataset.renderCount || 0) + 1)
    chart.clear()

    if (!hourlyAppData || hourlyAppData.length === 0) {
      chart.setOption({
        title: { text: '暂无应用数据', left: 'center', top: 'center', textStyle: { fontSize: 14, color: '#595959' } }
      })
      return
    }

    // appTotals 和 hourlyAppData 已在后端完成合并（≥90%累计占比 或 >12个应用）
    const apps = Object.keys(appTotals)
    const dailyAppTotals: Record<string, number>[] = hourlyAppData.map(dayHourlyData => {
      const dayTotals: Record<string, number> = {}
      dayHourlyData.forEach(hourData => {
        Object.entries(hourData).forEach(([app, minutes]) => {
          dayTotals[app] = (dayTotals[app] || 0) + minutes
        })
      })
      return dayTotals
    })
    const colors = ['#1890ff', '#52c41a', '#faad14', '#f5222d', '#722ed1', '#eb2f96', '#fa8c16', '#13c2c2', '#2f54eb', '#a0d911']

    const seriesData = apps.map((app, index) => {
      const data = dailyAppTotals.map(dt => barValue((dt[app] || 0) / 60))
      return {
        name: app, type: 'bar' as const, stack: 'day', data,
        emphasis: BAR_EMPHASIS,
        itemStyle: { color: colors[index % colors.length], borderColor: '#fff', borderWidth: 1 }
      }
    })

    const xAxisData = days.map(day => {
      const dateStr = day.replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3')
      const d = new Date(dateStr + 'T00:00:00')
      const weekDays = ['日', '一', '二', '三', '四', '五', '六']
      if (compact) {
        return `${d.getMonth() + 1}/${d.getDate()}\n${weekDays[d.getDay()]}`
      }
      return `${d.getMonth() + 1}/${d.getDate()}(${weekDays[d.getDay()]})`
    })

    chart.setOption({
      tooltip: {
        trigger: 'axis', appendToBody: true,
        axisPointer: { type: 'shadow' },
        backgroundColor: '#fff', borderColor: '#e8e8e8', borderWidth: 1,
        textStyle: { fontSize: 14, color: 'rgba(0,0,0,0.85)' },
        padding: [8, 12],
        formatter: (params: any) => {
          if (!params || !params.length) return ''
          const dayIndex = params[0].dataIndex
          const dayLabel = xAxisData[dayIndex]
          let totalHours = 0
          const appData: { app: string; hours: number; color: string }[] = []
          params.forEach((param: any) => {
            totalHours += param.value
            if (param.value > 0) {
              appData.push({ app: param.seriesName, hours: param.value, color: param.color })
            }
          })
          appData.sort((a, b) => b.hours - a.hours)
          let html = `<div style="font-weight:bold;margin-bottom:8px;">${dayLabel}</div>`
          html += `<div style="margin-bottom:4px;">总计: ${totalHours.toFixed(1)}h</div>`
          html += `<table style="border-collapse: collapse; width: 100%;">`
          appData.forEach(item => {
            const timeStr = item.hours >= 1 ? `${item.hours.toFixed(1)}h` : `${Math.round(item.hours * 60)}m`
            const pct = totalHours > 0 ? Math.round(item.hours / totalHours * 100) : 0
            html += `<tr style="border-bottom: 1px solid #f0f0f0;">`
            html += `<td style="padding: 3px 8px; text-align: left;">`
            html += `<span style="display:inline-block;width:10px;height:10px;background:${item.color};border-radius:2px;margin-right:6px;"></span>${escapeHtml(item.app)}</td>`
            html += `<td style="padding: 3px 8px; text-align: right; white-space: nowrap;">${timeStr} (${pct}%)</td>`
            html += `</tr>`
          })
          html += `</table>`
          return html
        }
      },
      legend: {
        orient: 'horizontal', top: 0, left: 'center',
        itemWidth: 12, itemHeight: 12,
        textStyle: { fontSize: 14, color: '#262626' }
      },
      grid: { left: 60, right: 20, top: 80, bottom: compact ? 60 : 70, containLabel: false },
      xAxis: {
        type: 'category', data: xAxisData,
        axisLabel: {
          fontSize: 14,
          color: '#262626',
          lineHeight: compact ? 16 : undefined,
          rotate: compact ? 0 : 45,
          interval: compact ? undefined : 0
        },
        axisLine: { lineStyle: { color: '#e8e8e8' } },
        axisTick: { lineStyle: { color: '#e8e8e8' } }
      },
      yAxis: {
        type: 'value', name: '小时',
        nameTextStyle: { fontSize: 14, color: '#262626' },
        axisLabel: { fontSize: 14, color: '#262626', formatter: (v: number) => v.toString() },
        axisLine: { lineStyle: { color: '#e8e8e8' } },
        axisTick: { lineStyle: { color: '#e8e8e8' } },
        splitLine: { lineStyle: { color: '#f0f0f0' } }
      },
      series: seriesData
    }, { notMerge: true })

    const handleResize = () => chart.resize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [hourlyAppData, days, appTotals, dayStartHour, compact])

  return (
    <div ref={chartRef} style={{
      width: compact ? '100%' : Math.max(numDays * 30, 800),
      height: '400px',
      margin: '0 auto',
      overflow: 'hidden'
    }} />
  )
}
