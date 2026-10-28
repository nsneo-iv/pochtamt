// Тема оформления: светлая / тёмная / как в системе. Режим хранится в localStorage,
// тёмная тема включается классом .app-dark на <html> (darkModeSelector в настройках PrimeVue).
import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'

export type ThemeMode = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'pochtamt.theme'
const DARK_CLASS = 'app-dark'

function readMode(): ThemeMode {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    if (value === 'light' || value === 'dark' || value === 'system') return value
  } catch {
    // Хранилище недоступно — используем значение по умолчанию
  }
  return 'system'
}

function writeMode(mode: ThemeMode): void {
  try {
    localStorage.setItem(STORAGE_KEY, mode)
  } catch {
    // Режим проживёт до перезагрузки страницы
  }
}

const media = window.matchMedia('(prefers-color-scheme: dark)')

export const useThemeStore = defineStore('theme', () => {
  const mode = ref<ThemeMode>(readMode())
  const systemDark = ref(media.matches)

  // Следим за системной темой, пока выбран режим «как в системе»
  media.addEventListener('change', (event) => {
    systemDark.value = event.matches
  })

  /** Фактически активна тёмная тема */
  const isDark = computed(() => (mode.value === 'system' ? systemDark.value : mode.value === 'dark'))

  function apply(): void {
    document.documentElement.classList.toggle(DARK_CLASS, isDark.value)
  }

  function setMode(value: ThemeMode): void {
    mode.value = value
    writeMode(value)
  }

  watch(isDark, apply, { immediate: true })

  return { mode, isDark, setMode }
})
