import { useEffect, useRef, useMemo } from 'react'
import * as echarts from '../echarts'
import { formatDateToYYYYMMDD } from '../dataProcessor'
import { EMPTY_CELL_COLOR, HEATMAP_TOOLTIP, heatmapActivityLabel, heatmapCellStyle } from '../heatmap'

// ========== 图表常量 ==========
const COLS = 24                         // 小时列数
const COLOR_STEPS = 60                  // 色阶数量
const CORNER_RADIUS = 2                 // 普通格子圆角
const GAP = 2                          // 格子间距
const COL_GROUP = 4                    // 列分组（每4小时加宽间距）
const COL_GAP_X = GAP * 2             // 列分组额外间距
const WEEK_GAP = GAP * 3              // 周分组（周日/周一之间）额外间距
const TOP_LABEL_OFFSET = -20          // 顶部小时标签偏移
const TOP_MARGIN = 24                  // 顶部留白

// 小面板规格（1-7天）：格子较大，标签宽松
const DAYS_SMALL = 7
const SIZE_S = 20      // 格子尺寸 (px)
const PAD_S = 10       // 图表内边距
const LABEL_FONT_S = 14
const LABEL_LEFT_S = -74
const LABEL_W_S = 66
const MARGIN_LEFT_S = 84

// 中面板规格（8-14天）：格子适中，按周分组
const DAYS_MID = 14
const SIZE_M = 17
const PAD_M = 11
const LABEL_FONT_M = 14
const LABEL_LEFT_M = -74
const LABEL_W_M = 66
const MARGIN_LEFT_M = 84

// 大面板规格（15-30天）：格子紧凑，按周分组
const SIZE_L = 15
const PAD_L = 13
const LABEL_FONT_L = 14
const LABEL_LEFT_L = -74
const LABEL_W_L = 66
const MARGIN_LEFT_L = 84

// ========== 辅助函数 ==========
function interpolateColor(startColor: string, endColor: string, steps: number): string[] {
  const hex2rgb = (hex: string) => ({ r: parseInt(hex.slice(1, 3), 16), g: parseInt(hex.slice(3, 5), 16), b: parseInt(hex.slice(5, 7), 16) })
  const rgb2hex = (r: number, g: number, b: number) => `#${Math.round(r).toString(16).padStart(2, '0')}${Math.round(g).toString(16).padStart(2, '0')}${Math.round(b).toString(16).padStart(2, '0')}`
  const s = hex2rgb(startColor), e = hex2rgb(endColor)
  return Array.from({ length: steps }, (_, i) => {
    const t = i / (steps - 1)
    return rgb2hex(s.r + (e.r - s.r) * t, s.g + (e.g - s.g) * t, s.b + (e.b - s.b) * t)
  })
}

const COLORS = [EMPTY_CELL_COLOR, ...interpolateColor('#cce5ff', '#007bff', COLOR_STEPS)]

function calcPositions(count: number, size: number, gap: number, groupSize: number, groupGap: number): number[] {
  const positions = [0]
  let acc = size
  for (let i = 1; i < count; i++) {
    acc += (groupSize > 0 && i % groupSize === 0) ? groupGap : gap
    positions[i] = acc
    acc += size
  }
  return positions
}

function getDayOfWeek(dateStr: string): number {
  const normalized = dateStr.replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3')
  return new Date(normalized + 'T00:00:00').getDay()
}

/** 按实际周日→周一边界插入周间隙 */
function calcWeekPositions(days: string[], size: number, gap: number, weekGap: number): number[] {
  const positions = [0]
  let acc = size
  for (let i = 1; i < days.length; i++) {
    const isMonday = getDayOfWeek(days[i]) === 1  // 周一前面是周日，加宽间隙
    acc += isMonday ? weekGap : gap
    positions[i] = acc
    acc += size
  }
  return positions
}

function formatDateLabel(dateStr: string): string {
  const normalized = dateStr.replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3')
  const d = new Date(normalized + 'T00:00:00')
  const weekDays = ['日', '一', '二', '三', '四', '五', '六']
  return `${d.getMonth() + 1}/${d.getDate()}(${weekDays[d.getDay()]})`
}

interface MultiDayHeatmapChartProps {
  hourlyActivity: number[][]
  coverage?: number[][]
  days: string[]
  dayStartHour: number
}

export function MultiDayHeatmapChart({ hourlyActivity, coverage, days, dayStartHour }: MultiDayHeatmapChartProps) {
  const chartRef = useRef<HTMLDivElement>(null)
  const chartInstanceRef = useRef<echarts.ECharts | null>(null)

  useEffect(() => () => {
    chartInstanceRef.current?.dispose()
    chartInstanceRef.current = null
  }, [])
  const numDays = days.length

  const layout = useMemo(() => {
    const tier = numDays <= DAYS_SMALL ? 's' : numDays <= DAYS_MID ? 'm' : 'l'
    const size  = tier === 's' ? SIZE_S  : tier === 'm' ? SIZE_M  : SIZE_L
    const pad   = tier === 's' ? PAD_S   : tier === 'm' ? PAD_M   : PAD_L
    const font  = tier === 's' ? LABEL_FONT_S : tier === 'm' ? LABEL_FONT_M : LABEL_FONT_L
    const left  = tier === 's' ? LABEL_LEFT_S : tier === 'm' ? LABEL_LEFT_M : LABEL_LEFT_L
    const lw    = tier === 's' ? LABEL_W_S    : tier === 'm' ? LABEL_W_M    : LABEL_W_L
    const ml    = tier === 's' ? MARGIN_LEFT_S : tier === 'm' ? MARGIN_LEFT_M : MARGIN_LEFT_L
    const cellX = calcPositions(COLS, size, GAP, COL_GROUP, COL_GAP_X)
    const cellY = tier === 's'
      ? calcPositions(numDays, size, GAP, 0, 0)
      : calcWeekPositions(days, size, GAP, WEEK_GAP)
    return {
      size, pad, cellX, cellY,
      width: cellX[COLS - 1] + size + pad * 2,
      height: cellY[numDays - 1] + size + pad * 2,
      labelFontSize: font, labelLeft: left, labelWidth: lw, marginLeft: ml,
    }
  }, [numDays, days])

  useEffect(() => {
    if (!chartRef.current) return
    if (!chartInstanceRef.current) chartInstanceRef.current = echarts.init(chartRef.current)
    const chart = chartInstanceRef.current
    chartRef.current.dataset.renderCount = String(Number(chartRef.current.dataset.renderCount || 0) + 1)
    chart.clear()

    const { size, pad, cellX, cellY, width, height } = layout
    const now = new Date()
    const logicalNow = new Date(now)
    logicalNow.setHours(now.getHours() - dayStartHour)
    const currentDateStr = formatDateToYYYYMMDD(logicalNow)
    const isInRange = days.includes(currentDateStr)
    let curDay = -1, curHr = -1
    if (isInRange) {
      curDay = days.indexOf(currentDateStr)
      curHr = (now.getHours() - dayStartHour + 24) % 24
    }

    const data: any[] = []
    for (let d = 0; d < numDays; d++) {
      for (let h = 0; h < COLS; h++) {
        const activity = hourlyActivity[d]?.[h] || 0
        data.push({
          x: pad + cellX[h], y: pad + cellY[d],
          width: size, height: size,
          value: activity,
          recorded: coverage?.[d]?.[h],
          color: COLORS[Math.min(activity, COLOR_STEPS)] || COLORS[COLORS.length - 1],
          day: days[d],
          hour: (dayStartHour + h) % 24,
          hourIndex: h,
          isCurrent: isInRange && d === curDay && h === curHr
        })
      }
    }

    chart.setOption({
      grid: { left: 0, top: 0, right: 0, bottom: 0, containLabel: false },
      xAxis: { show: false, type: 'value', min: 0, max: width },
      yAxis: { show: false, type: 'value', min: 0, max: height, inverse: true },
      tooltip: {
        ...HEATMAP_TOOLTIP,
        formatter: (params: any) => {
          const item = params.data?.[0]
          if (!item) return ''
          const ds = item.day.replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3')
          const next = item.hourIndex >= (24 - dayStartHour) && dayStartHour > 0
          return `${ds} ${item.hour}:00 ${next ? '次日' : ''}<br/>${heatmapActivityLabel(item.value, item.recorded)}`
        }
      },
      series: [{
        type: 'custom', animation: false,
        renderItem: (_: any, api: any) => {
          const item = data[_.dataIndex]
          if (!item) return null
          const x = api.coord([item.x, item.y])[0], y = api.coord([item.x, item.y])[1]
          const w = api.size([item.width, item.height])[0], h = api.size([item.width, item.height])[1]
          return {
            type: 'rect',
            shape: { x: x - w / 2, y: y - h / 2, width: w, height: h, r: item.isCurrent ? size / 2 : CORNER_RADIUS },
            style: heatmapCellStyle(item.color, item.recorded, item.isCurrent),
            name: `${item.day}-${item.hour}`
          }
        },
        data: data.map(item => [item]),
      }]
    } as echarts.EChartsOption, { notMerge: true })

    chart.resize()
    const handleResize = () => chart.resize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [hourlyActivity, coverage, days, dayStartHour, layout, numDays])

  const { pad, cellX, cellY, width: cw, height: ch, labelFontSize, labelLeft, labelWidth, marginLeft } = layout

  return (
    <div style={{ position: 'relative', marginLeft, marginTop: TOP_MARGIN }}>
      {/* 顶部小时标签 */}
      {[0, 4, 8, 12, 16, 20].map(off => (
        <div key={off} style={{
          position: 'absolute', top: TOP_LABEL_OFFSET, left: pad + cellX[off],
          fontSize: 14, color: '#595959', transform: 'translateX(-50%)', whiteSpace: 'nowrap'
        }}>
          {(dayStartHour + off) % 24}时
        </div>
      ))}
      {/* 左侧日期标签 */}
      {days.map((day, i) => (
        <div key={day} style={{
          position: 'absolute',
          left: labelLeft, top: pad + cellY[i],
          fontSize: labelFontSize, color: '#595959',
          textAlign: 'right', width: labelWidth,
          transform: 'translateY(-50%)'
        }}>
          {formatDateLabel(day)}
        </div>
      ))}
      <div ref={chartRef} style={{ width: cw, height: ch, overflow: 'hidden' }} />
    </div>
  )
}
