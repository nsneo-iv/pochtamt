// Стор авторизации: JWT в localStorage, текущий пользователь и его роль
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import * as authApi from '@/api/auth'
import type { AuthConfig, Role, User } from '@/api/types'

const TOKEN_KEY = 'pochtamt.token'

/** Безопасное чтение localStorage (в приватном режиме доступ может бросать исключение) */
function readToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

function writeToken(value: string | null): void {
  try {
    if (value) localStorage.setItem(TOKEN_KEY, value)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    // Хранилище недоступно — сессия проживёт до перезагрузки страницы
  }
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(readToken())
  const user = ref<User | null>(null)
  /** Возможности сервера (GET /auth/config): настроен ли AD. До загрузки считаем, что настроен */
  const features = ref<AuthConfig | null>(null)
  const adEnabled = computed(() => features.value?.ad_enabled ?? true)
  const loginHint = computed(() => features.value?.login_hint ?? '')

  const isAuthenticated = computed(() => token.value !== null)
  const role = computed<Role | null>(() => user.value?.role ?? null)
  const isSuperadmin = computed(() => role.value === 'superadmin')
  /** Домены domain_admin; для superadmin — пустой список (доступны все) */
  const ownDomains = computed(() => user.value?.domains ?? [])

  /** Загружает /auth/config один раз; ошибка не мешает работе (разделы AD просто остаются видимыми) */
  async function ensureConfig(): Promise<void> {
    if (features.value) return
    try {
      features.value = await authApi.config()
    } catch {
      // сервер недоступен — покажет страница входа
    }
  }

  /** Вход по логину (локальный пароль или учётка AD); сохраняет токен и пользователя */
  async function login(loginName: string, password: string): Promise<User> {
    const result = await authApi.login({ login: loginName, password })
    token.value = result.token
    writeToken(result.token)
    user.value = result.user
    return result.user
  }

  /** Подгружает пользователя по сохранённому токену (после перезагрузки страницы) */
  async function fetchUser(): Promise<User> {
    const result = await authApi.me()
    user.value = result
    return result
  }

  function logout(): void {
    token.value = null
    user.value = null
    writeToken(null)
  }

  /** Проверка доступа по списку ролей; пустой список = доступно всем авторизованным */
  function hasRole(roles: readonly Role[] | undefined): boolean {
    if (!roles || roles.length === 0) return true
    return role.value !== null && roles.includes(role.value)
  }

  return {
    token, user, features, adEnabled, loginHint, isAuthenticated, role, isSuperadmin, ownDomains,
    ensureConfig, login, fetchUser, logout, hasRole,
  }
})
