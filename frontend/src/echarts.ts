import { use, init } from 'echarts/core'
import { BarChart, CustomChart, PieChart } from 'echarts/charts'
import { GraphicComponent, GridComponent, LegendComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([BarChart, CustomChart, PieChart, GraphicComponent, GridComponent, LegendComponent, TitleComponent, TooltipComponent, CanvasRenderer])

export { init }
export type { ECharts, EChartsOption } from 'echarts'
