export const BAR_EMPHASIS = { itemStyle: { borderColor: '#000', borderWidth: 1 } }

// A zero-height rectangle can still draw a border when highlighted.
export function barValue(value: number) { return value > 0 ? value : null }

export function activeBarItems<T extends { value: unknown }>(items: T[]): (T & { value: number })[] {
  return items.filter((item): item is T & { value: number } =>
    typeof item.value === 'number' && Number.isFinite(item.value) && item.value > 0)
}
