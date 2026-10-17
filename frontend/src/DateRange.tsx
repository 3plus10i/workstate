import dayjs from 'dayjs'
import type { Dayjs } from 'dayjs'
import { DatePicker } from 'antd'

export type Range = [Dayjs, Dayjs]

export function DateRange({ value, onChange, label = '日期区间' }: { value: Range; onChange: (range: Range) => void; label?: string }) {
  const today = dayjs().startOf('day')
  return <DatePicker.RangePicker
    aria-label={label}
    value={value}
    allowClear={false}
    format="YYYY-MM-DD"
    disabledDate={date => date.isAfter(today, 'day')}
    onChange={dates => { if (dates?.[0] && dates[1]) onChange([dates[0].startOf('day'), dates[1].startOf('day')]) }}
    presets={[
      { label: '今天', value: [today, today] },
      { label: '昨天', value: [today.subtract(1,'day'),today.subtract(1,'day')] },
      { label: '最近 7 天', value: [today.subtract(6,'day'),today] },
      { label: '最近 30 天', value: [today.subtract(29,'day'),today] },
      { label: '本月', value: [today.startOf('month'),today] },
    ]}
  />
}
