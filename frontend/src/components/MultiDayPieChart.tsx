import { escapeHtml } from '../chartData'
import { useEffect, useRef } from 'react'
import * as echarts from '../echarts'

interface MultiDayPieChartProps {
  appTotals: Record<string, number>
  numDays: number
}

function formatMinutes(minutes: number): string {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return h > 0 ? `${h}h${m}m` : `${m}m`
}

export function MultiDayPieChart({ appTotals, numDays }: MultiDayPieChartProps) {
  const chartRef = useRef<HTMLDivElement>(null)
  const chartInstanceRef = useRef<echarts.ECharts | null>(null)

  useEffect(() => () => {
    chartInstanceRef.current?.dispose()
    chartInstanceRef.current = null
  }, [])

  useEffect(() => {
    if (!chartRef.current) return
    if (!chartInstanceRef.current) {
      chartInstanceRef.current = echarts.init(chartRef.current)
    }
    const chart = chartInstanceRef.current
    chartRef.current.dataset.renderCount = String(Number(chartRef.current.dataset.renderCount || 0) + 1)
    chart.clear()

    if (!appTotals || Object.keys(appTotals).length === 0) {
      chart.setOption({
        title: { text: '暂无应用数据', left: 'center', top: 'center', textStyle: { fontSize: 14, color: '#595959' } }
      })
      return
    }

    const pieData = Object.entries(appTotals)
      .map(([app, minutes]) => ({ name: app, value: minutes }))
      .sort((a, b) => b.value - a.value)

    const totalMinutes = Object.values(appTotals).reduce((s, v) => s + v, 0)
    const avgMin = Math.round(totalMinutes / numDays)
    const centerText = `总计 ${formatMinutes(totalMinutes)}\n日均 ${formatMinutes(avgMin)}`

    const colors = ['#1890ff', '#52c41a', '#faad14', '#f5222d', '#722ed1', '#eb2f96', '#fa8c16', '#13c2c2', '#2f54eb', '#a0d911']

    chart.setOption({
      tooltip: {
        trigger: 'item',
        backgroundColor: '#fff',
        borderColor: '#e8e8e8',
        borderWidth: 1,
        textStyle: { fontSize: 14, color: 'rgba(0,0,0,0.85)' },
        padding: [8, 12],
        formatter: (params: any) => {
          return `${escapeHtml(params.name)}<br/>${formatMinutes(params.value)} (${params.percent}%)`
        }
      },
      graphic: totalMinutes > 0 ? [{
        type: 'text',
        left: 'center',
        top: 'center',
        style: {
          text: centerText,
          textAlign: 'center',
          fill: '#262626',
          fontSize: 14,
          lineHeight: 18
        }
      }] : undefined,
      series: [{
        name: '应用时长', type: 'pie',
        radius: ['35%', '65%'], center: ['50%', '50%'],
        avoidLabelOverlap: true,
        itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
        label: {
          show: true, position: 'outside',
          formatter: (params: any) => {
            return `${params.name}: ${formatMinutes(params.value)} (${params.percent}%)`
          },
          fontSize: 14, color: '#262626',
          distanceToLabelLine: 4
        },
        emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold' } },
        labelLine: {
          show: true,
          lineStyle: { color: 'rgba(0,0,0,0.25)' }
        },
        data: pieData, color: colors
      }]
    }, { notMerge: true })

    const handleResize = () => chart.resize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [appTotals, numDays])

  return <div ref={chartRef} style={{ width: '100%', height: '400px', overflow: 'hidden' }} />
}
