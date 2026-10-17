import assert from 'node:assert/strict'
import test from 'node:test'
import dayjs from 'dayjs'
import { canExport } from '../src/dateRules.ts'

test('manual export includes a complete ordinary year or leap year', () => {
  assert.equal(canExport(dayjs('2025-01-01'), dayjs('2025-12-31')), true)
  assert.equal(canExport(dayjs('2024-01-01'), dayjs('2024-12-31')), true)
  assert.equal(canExport(dayjs('2024-01-01'), dayjs('2025-01-01')), false)
  assert.equal(canExport(dayjs('2025-01-01'), dayjs('2026-01-01')), false)
  assert.equal(canExport(dayjs('2025-01-02'), dayjs('2025-01-01')), false)
})

test('leap day export limit uses the same calendar anniversary as the backend', () => {
  assert.equal(canExport(dayjs('2024-02-29'), dayjs('2025-02-27')), true)
  assert.equal(canExport(dayjs('2024-02-29'), dayjs('2025-02-28')), false)
})
