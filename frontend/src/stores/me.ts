// Стор личного кабинета: отдельный токен (typ=user) под своим ключом localStorage и данные пользователя
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import * as meApi from '@/api/me'
import type { Me } from '@/api/types'

const TOKEN_KEY = 'pochtamt.me.token'

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

export const useMeStore = defineStore('me', () => {
  const token = ref<string | null>(readToken())
  const me = ref<Me | null>(null)

  const isAuthenticated = computed(() => token.value !== null)

  async function login(address: string, password: string): Promise<Me> {
    const result = await meApi.meLogin({ address, password })
    token.value = result.token
    writeToken(result.token)
    me.value = result.me
    return result.me
  }

  /** Перечитывает карточку пользователя (после входа по сохранённому токену или смены настроек) */
  async function fetchMe(): Promise<Me> {
    me.value = await meApi.getMe()
    return me.value
  }

  function logout(): void {
    token.value = null
    me.value = null
    writeToken(null)
  }

  return { token, me, isAuthenticated, login, fetchMe, logout }
})
