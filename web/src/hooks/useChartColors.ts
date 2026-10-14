import { useThemeVersion } from '../lib/theme'

/** The theme's colours as values: recharts writes them into SVG attributes,
 *  where CSS variables do not resolve. Read on every render (a handful of
 *  property reads); `useThemeVersion` re-renders when the theme or the
 *  system's light/dark setting changes. */
export function useChartColors() {
  useThemeVersion()
  const css = getComputedStyle(document.documentElement)
  const v = (name: string) => css.getPropertyValue(name).trim()
  return {
    fg: v('--fg'),
    muted: v('--muted'),
    line: v('--line'),
    panel: v('--panel'),
    bg: v('--bg'),
    series: [1, 2, 3, 4, 5, 6].map((i) => v(`--chart-${i}`)),
  }
}

export type ChartColors = ReturnType<typeof useChartColors>
