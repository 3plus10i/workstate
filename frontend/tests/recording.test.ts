import assert from 'node:assert/strict'
import test from 'node:test'
import { resumeTimeLabel } from '../src/recording.ts'

test('same-day pause status shows a readable resumption time', () => {
  assert.equal(resumeTimeLabel('2026-10-15T12:05:00', '2026-10-15T12:00:00'), '已暂停 · 预计 12:05 恢复')
})

test('overnight and next-year pauses include the resumption date', () => {
  assert.equal(resumeTimeLabel('2026-10-16T00:03:00', '2026-10-15T23:58:00'), '已暂停 · 预计 10-16 00:03 恢复')
  assert.equal(resumeTimeLabel('2027-01-01T12:00:00', '2026-12-31T12:00:00'), '已暂停 · 预计 01-01 12:00 恢复')
})
