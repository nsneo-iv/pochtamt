// Личный кабинет пользователя: вход по адресу ящика, свои настройки. Токен отдельного типа (typ=user).
import { http } from './client'
import type { MailboxSettings, Me, MeLoginRequest, MeLoginResponse, MeSettingsUpdate } from './types'

export function meLogin(data: MeLoginRequest): Promise<MeLoginResponse> {
  return http.post<MeLoginResponse>('/me/login', data)
}

export function getMe(): Promise<Me> {
  return http.get<Me>('/me')
}

/** Только для auth=local */
export function setMePassword(currentPassword: string, password: string): Promise<void> {
  return http.post<void>('/me/password', { current_password: currentPassword, password })
}

export function getMeSettings(): Promise<MailboxSettings> {
  return http.get<MailboxSettings>('/me/settings')
}

/** Отправлять только изменённые секции */
export function updateMeSettings(data: MeSettingsUpdate): Promise<MailboxSettings> {
  return http.put<MailboxSettings>('/me/settings', data)
}
