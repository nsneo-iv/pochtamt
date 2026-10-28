// Синхронизация с AD: предпросмотр и применение
import { http } from './client'
import type { AdSyncResult } from './types'

/** Что будет создано / обновлено / отключено, без изменений в базе */
export function previewAdSync(): Promise<AdSyncResult> {
  return http.get<AdSyncResult>('/ad/sync/preview')
}

/** Применяет синхронизацию; возвращает то, что было применено */
export function applyAdSync(): Promise<AdSyncResult> {
  return http.post<AdSyncResult>('/ad/sync')
}
