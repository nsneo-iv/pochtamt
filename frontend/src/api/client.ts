// Обёртка над fetch для REST API бэкенда (docs/api.md).
// Подставляет Bearer-токен (админский — из стора auth, для путей /me/* — из стора кабинета),
// разбирает ошибки `{detail}`, при 401 разлогинивает и отправляет на страницу входа.

import { useAuthStore } from '@/stores/auth'
import { useMeStore } from '@/stores/me'
import router from '@/router'

/** Префикс API: VITE_API_BASE (по умолчанию пусто = тот же origin) + /api/v1 */
const API_PREFIX = `${(import.meta.env.VITE_API_BASE ?? '').replace(/\/+$/, '')}/api/v1`

/** Ошибка API: HTTP-статус и текст из поля detail (или общее описание) */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

type HttpMethod = 'GET' | 'POST' | 'PUT' | 'DELETE'

/** Параметры строки запроса; пустые значения не отправляются */
export type QueryParams = Record<string, string | number | boolean | null | undefined>

interface RequestOptions {
  params?: QueryParams
  body?: unknown
}

/** Пути личного кабинета: токен и разлогин — из стора кабинета */
function isMePath(path: string): boolean {
  return path === '/me' || path.startsWith('/me/')
}

/** Собирает строку запроса, пропуская пустые значения */
function buildQuery(params?: QueryParams): string {
  if (!params) return ''
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

/** Вытаскивает человекочитаемый текст ошибки из тела ответа (`{detail}`) */
async function extractErrorMessage(response: Response): Promise<string> {
  const fallback = `Ошибка ${response.status}${response.statusText ? `: ${response.statusText}` : ''}`
  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    return fallback
  }
  if (!payload || typeof payload !== 'object' || !('detail' in payload)) return fallback
  const detail = (payload as { detail: unknown }).detail
  if (typeof detail === 'string') return detail
  // FastAPI при ошибке валидации отдаёт массив {loc, msg, type}
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => {
      if (item && typeof item === 'object' && 'msg' in item) {
        const loc = Array.isArray((item as { loc?: unknown }).loc)
          ? ((item as { loc: unknown[] }).loc.filter((p) => p !== 'body').join('.') + ': ')
          : ''
        return loc + String((item as { msg: unknown }).msg)
      }
      return String(item)
    })
    return parts.join('; ') || fallback
  }
  return fallback
}

/** Разлогинивает (админа или пользователя кабинета) и отправляет на соответствующую страницу входа */
function handleUnauthorized(me: boolean): void {
  const current = router.currentRoute.value
  if (me) {
    useMeStore().logout()
    if (current.name !== 'me-login') void router.push({ name: 'me-login' })
    return
  }
  useAuthStore().logout()
  if (current.name !== 'login') {
    void router.push({ name: 'login', query: { redirect: current.fullPath } })
  }
}

/** Базовый запрос; при 204 возвращает undefined */
async function request<T>(method: HttpMethod, path: string, options: RequestOptions = {}): Promise<T> {
  const me = isMePath(path)
  const token = me ? useMeStore().token : useAuthStore().token
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'

  let response: Response
  try {
    response = await fetch(`${API_PREFIX}${path}${buildQuery(options.params)}`, {
      method,
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    })
  } catch {
    throw new ApiError(0, 'Сервер недоступен: проверьте соединение')
  }

  if (response.status === 401) {
    // Неверный пароль при входе — обычная ошибка; просроченный токен — разлогин
    const isLogin = path.startsWith('/auth/login') || path.startsWith('/me/login')
    if (!isLogin) handleUnauthorized(me)
    throw new ApiError(401, await extractErrorMessage(response))
  }
  if (!response.ok) {
    throw new ApiError(response.status, await extractErrorMessage(response))
  }
  if (response.status === 204) return undefined as T
  const text = await response.text()
  return (text ? JSON.parse(text) : undefined) as T
}

export const http = {
  get<T>(path: string, params?: QueryParams): Promise<T> {
    return request<T>('GET', path, { params })
  },
  post<T>(path: string, body?: unknown): Promise<T> {
    return request<T>('POST', path, { body })
  },
  put<T>(path: string, body?: unknown): Promise<T> {
    return request<T>('PUT', path, { body })
  },
  delete<T = void>(path: string): Promise<T> {
    return request<T>('DELETE', path)
  },
}

/** Кодирует сегмент пути (адрес ящика, имя домена) */
export function seg(value: string): string {
  return encodeURIComponent(value)
}
