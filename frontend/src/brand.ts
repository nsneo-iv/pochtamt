// Брендинг сборки: заголовок панели и ссылка на веб-почту задаются при сборке (frontend/.env, см. .env.example)
export const APP_TITLE: string = import.meta.env.VITE_APP_TITLE?.trim() || 'Почтамт'
/** Адрес веб-почты для ссылок в личном кабинете; пусто — ссылка не показывается */
export const WEBMAIL_URL: string = import.meta.env.VITE_WEBMAIL_URL?.trim() || ''
