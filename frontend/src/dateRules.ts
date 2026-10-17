import type { Dayjs } from 'dayjs'

export function canExport(start: Dayjs, end: Dayjs) {
  return !end.isBefore(start, 'day') && end.isBefore(start.add(1, 'year'), 'day')
}
