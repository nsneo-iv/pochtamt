// Точка входа: Vue 3 + Pinia + vue-router + PrimeVue (тема Aura)
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import PrimeVue from 'primevue/config'
import Aura from '@primevue/themes/aura'
import ToastService from 'primevue/toastservice'
import ConfirmationService from 'primevue/confirmationservice'
import Tooltip from 'primevue/tooltip'

import 'primeicons/primeicons.css'
import '@/assets/main.css'

import App from './App.vue'
import router from '@/router'
import { ruLocale } from '@/locale/ru'
import { useThemeStore } from '@/stores/theme'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
// Тему применяем до монтирования, чтобы страница не мигала светлым фоном
useThemeStore(pinia)
app.use(router)
app.use(PrimeVue, {
  theme: {
    preset: Aura,
    options: {
      // Тёмная тема включается классом .app-dark на <html>; по умолчанию светлая
      darkModeSelector: '.app-dark',
      cssLayer: false,
    },
  },
  locale: ruLocale,
})
app.use(ToastService)
app.use(ConfirmationService)
app.directive('tooltip', Tooltip)

app.mount('#app')
