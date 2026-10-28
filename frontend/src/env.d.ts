/// <reference types="vite/client" />

// Переменные окружения, доступные во фронтенде (см. .env.example)
interface ImportMetaEnv {
  /** Базовый адрес бэкенда; пусто = тот же origin */
  readonly VITE_API_BASE?: string
  /** Название панели в шапке, на странице входа и в заголовке вкладки; по умолчанию «Почтамт» */
  readonly VITE_APP_TITLE?: string
  /** Адрес веб-почты для ссылки в личном кабинете; пусто — без ссылки */
  readonly VITE_WEBMAIL_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, unknown>
  export default component
}
