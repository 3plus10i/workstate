import assert from 'node:assert/strict'
import test from 'node:test'
import { heatmapActivityLabel } from '../src/heatmap.ts'

test('heatmap distinguishes missing records from recorded inactivity, including partial slots', () => {
  assert.equal(heatmapActivityLabel(0, 0), '无记录')
  assert.equal(heatmapActivityLabel(0, 1), '无活动')
  assert.equal(heatmapActivityLabel(0, 5), '无活动')
  assert.equal(heatmapActivityLabel(0, 60), '无活动')
})

test('active heatmap slots show actual minutes without a recording denominator', () => {
  assert.equal(heatmapActivityLabel(2, 5), '活跃 2 分钟')
  assert.equal(heatmapActivityLabel(1, 1), '活跃 1 分钟')
  assert.equal(heatmapActivityLabel(37, 60), '活跃 37 分钟')
})
