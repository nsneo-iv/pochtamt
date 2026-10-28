// Сводка для главной страницы: GET /stats
import { http } from './client'
import type { Stats } from './types'

export function getStats(): Promise<Stats> {
  return http.get<Stats>('/stats')
}
