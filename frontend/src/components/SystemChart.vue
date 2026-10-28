<script setup lang="ts">
// Обёртка над PrimeVue Chart (Chart.js): цвета линий, сетки и подписей берутся из CSS-переменных
// темы PrimeVue через getComputedStyle и пересчитываются при переключении светлой/тёмной темы.
import { computed, nextTick, ref, watch } from 'vue'
import Chart from 'primevue/chart'
import { useThemeStore } from '@/stores/theme'

export interface ChartSeries {
  label: string
  data: (number | null)[]
  /** Имя CSS-переменной цвета, например --p-blue-500 */
  color: string
  /** Правая ось (для графиков с двумя шкалами) */
  rightAxis?: boolean
  /** Заливка под линией */
  fill?: boolean
}

const props = withDefaults(
  defineProps<{
    type?: 'line' | 'bar'
    labels: string[]
    series: ChartSeries[]
    /** Шкала в процентах 0–100 */
    percent?: boolean
    /** Стековые столбцы/области */
    stacked?: boolean
    /** Подпись правой оси, если есть серии с rightAxis */
    rightAxisLabel?: string
    /** Правая ось в процентах */
    rightPercent?: boolean
    height?: string
  }>(),
  { type: 'line', percent: false, stacked: false, rightAxisLabel: '', rightPercent: false, height: '220px' },
)

const theme = useThemeStore()
/** Счётчик перерисовок: меняется после смены темы, когда новые CSS-переменные уже применены */
const redraw = ref(0)
watch(
  () => theme.isDark,
  async () => {
    await nextTick()
    redraw.value += 1
  },
)

function cssVar(name: string, fallback: string): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}

/** Цвет с прозрачностью для заливки: поддерживаем hex и rgb() */
function withAlpha(color: string, alpha: number): string {
  const hex = color.match(/^#([0-9a-f]{6})$/i)
  if (hex) {
    const n = parseInt(hex[1] ?? '0', 16)
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`
  }
  const rgb = color.match(/^rgba?\(([^)]+)\)$/)
  if (rgb) {
    const parts = (rgb[1] ?? '').split(',').slice(0, 3).map((p) => p.trim())
    return `rgba(${parts.join(', ')}, ${alpha})`
  }
  return color
}

const chartData = computed(() => {
  void redraw.value
  return {
    labels: props.labels,
    datasets: props.series.map((s) => {
      const color = cssVar(s.color, '#3b82f6')
      return {
        label: s.label,
        data: s.data,
        borderColor: color,
        backgroundColor: props.type === 'bar' || s.fill ? withAlpha(color, props.type === 'bar' ? 0.7 : 0.15) : color,
        fill: props.type === 'line' ? !!s.fill : undefined,
        yAxisID: s.rightAxis ? 'y1' : 'y',
        tension: 0.3,
        pointRadius: 0,
        pointHitRadius: 8,
        borderWidth: props.type === 'bar' ? 0 : 2,
        spanGaps: true,
      }
    }),
  }
})

const chartOptions = computed(() => {
  void redraw.value
  const text = cssVar('--p-text-color', '#334155')
  const muted = cssVar('--p-text-muted-color', '#64748b')
  const grid = cssVar('--p-content-border-color', '#e2e8f0')
  const hasRight = props.series.some((s) => s.rightAxis)
  const scales: Record<string, unknown> = {
    x: { ticks: { color: muted, maxTicksLimit: 8, maxRotation: 0 }, grid: { color: grid }, stacked: props.stacked },
    y: {
      beginAtZero: true,
      min: props.percent ? 0 : undefined,
      max: props.percent ? 100 : undefined,
      ticks: { color: muted, callback: (v: unknown) => (props.percent ? `${v}%` : v) },
      grid: { color: grid },
      stacked: props.stacked,
    },
  }
  if (hasRight) {
    scales.y1 = {
      position: 'right',
      beginAtZero: true,
      min: props.rightPercent ? 0 : undefined,
      max: props.rightPercent ? 100 : undefined,
      ticks: { color: muted, callback: (v: unknown) => (props.rightPercent ? `${v}%` : v) },
      grid: { drawOnChartArea: false },
      title: { display: !!props.rightAxisLabel, text: props.rightAxisLabel, color: muted },
    }
  }
  return {
    maintainAspectRatio: false,
    animation: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { labels: { color: text, boxWidth: 12, usePointStyle: true } },
      tooltip: { backgroundColor: cssVar('--p-content-background', '#fff'), titleColor: text, bodyColor: text, borderColor: grid, borderWidth: 1 },
    },
    scales,
  }
})
</script>

<template>
  <Chart :key="redraw" :type="type" :data="chartData" :options="chartOptions" :style="{ height }" />
</template>
