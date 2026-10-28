// Состояние сервера (только суперадмин): текущие метрики и история выборок
import { http } from './client'
import type { SystemHistory, SystemOverview } from './types'

export function getSystemOverview(): Promise<SystemOverview> {
  return http.get<SystemOverview>('/system/overview')
}

/** hours — 1..168 (по умолчанию 24); точки по порядку времени, выборка раз в 5 минут */
export function getSystemHistory(hours: number): Promise<SystemHistory> {
  return http.get<SystemHistory>('/system/history', { hours })
}
