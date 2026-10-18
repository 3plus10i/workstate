export const EMPTY_CELL_COLOR = '#eee'

export function heatmapCellStyle(color: string, recorded: number | undefined, current: boolean) {
  const missing = recorded === 0
  return {
    fill: missing ? 'transparent' : color,
    stroke: missing ? EMPTY_CELL_COLOR : current ? '#007bff' : undefined,
    lineWidth: missing || current ? 1 : 0,
  }
}

export function heatmapActivityLabel(active: number, recorded: number | undefined): string {
  if (active > 0) return `活跃 ${active} 分钟`
  return recorded === 0 ? '无记录' : '无活动'
}

export const HEATMAP_TOOLTIP = {
  trigger: 'item' as const,
  backgroundColor: 'rgba(51, 51, 51, 0.7)',
  borderWidth: 0,
  textStyle: { fontSize: 14, color: '#fff' },
  padding: [4, 8],
  borderRadius: 4,
  appendToBody: true,
  transitionDuration: 0,
  position: (point: number[]) => [point[0] + 10, point[1] + 10],
}
