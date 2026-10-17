import assert from 'node:assert/strict'
import test from 'node:test'
import { init, use } from 'echarts/core.js'
import { BarChart } from 'echarts/charts.js'
import { GridComponent } from 'echarts/components.js'
import { SVGRenderer } from 'echarts/renderers.js'
import { BAR_EMPHASIS, barValue } from '../src/barStyle.ts'

use([BarChart, GridComponent, SVGRenderer])

test('legend highlighting gives the actual bar element a thin black outline', () => {
  const chart = init(null, undefined, { renderer: 'svg', ssr: true, width: 800, height: 400 })
  try {
    chart.setOption({ animation: false, xAxis: { data: ['today'] }, yAxis: {}, series: [
      { name: 'Editor', type: 'bar', data: [60], itemStyle: { borderColor: '#fff', borderWidth: 1 }, emphasis: BAR_EMPHASIS },
    ] })
    chart.dispatchAction({ type: 'highlight', seriesName: 'Editor' })
    chart.getZr().animation.update()
    const element = chart.getModel().getSeriesByIndex(0).getData().getItemGraphicEl(0)
    assert.equal(element.currentStates.includes('emphasis'), true)
    assert.equal(element.states.emphasis.style.stroke, '#000')
    assert.equal(element.states.emphasis.style.lineWidth, 1)
    chart.dispatchAction({ type: 'downplay', seriesName: 'Editor' })
    chart.getZr().animation.update()
    assert.equal(element.currentStates.includes('emphasis'), false)
  } finally { chart.dispose() }
})

test('legend highlighting skips missing segments and completely empty ticks', () => {
  const chart = init(null, undefined, { renderer: 'svg', ssr: true, width: 800, height: 400 })
  try {
    chart.setOption({ animation: false, xAxis: { data: ['both', 'browser only', 'editor only', 'empty'] }, yAxis: {}, series: [
      { name: 'Editor', type: 'bar', stack: 'total', data: [60, 0, 40, 0].map(barValue), emphasis: BAR_EMPHASIS },
      { name: 'Browser', type: 'bar', stack: 'total', data: [20, 30, 0, 0].map(barValue), emphasis: BAR_EMPHASIS },
      { name: 'Other', type: 'bar', stack: 'total', data: [0, 0, 0, 0].map(barValue), emphasis: BAR_EMPHASIS },
    ] })
    chart.dispatchAction({ type: 'highlight', seriesName: 'Editor' })
    chart.getZr().animation.update()
    const editor = chart.getModel().getSeriesByIndex(0).getData()
    const browser = chart.getModel().getSeriesByIndex(1).getData()
    for (const index of [0, 2]) {
      const element = editor.getItemGraphicEl(index)
      assert.equal(element.currentStates.includes('emphasis'), true)
      assert.equal(element.states.emphasis.style.stroke, '#000')
      assert.equal(element.states.emphasis.style.lineWidth, 1)
    }
    for (const index of [1, 3]) assert.equal(editor.getItemGraphicEl(index), undefined)
    assert.equal(browser.getItemGraphicEl(1).currentStates.includes('emphasis'), false)
    assert.equal(browser.getItemGraphicEl(3), undefined)
    chart.dispatchAction({ type: 'highlight', seriesName: 'Other' })
    chart.getZr().animation.update()
    const other = chart.getModel().getSeriesByIndex(2).getData()
    for (let index = 0; index < 4; index++) assert.equal(other.getItemGraphicEl(index), undefined)
  } finally { chart.dispose() }
})
