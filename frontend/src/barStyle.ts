export const BAR_EMPHASIS = { itemStyle: { borderColor: '#000', borderWidth: 1 } }

// A zero-height rectangle can still draw a border when highlighted.
export function barValue(value: number) { return value > 0 ? value : null }
