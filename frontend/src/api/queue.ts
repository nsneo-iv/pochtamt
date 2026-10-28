// Очередь Postfix (через агент на хосте): /queue
import { http, seg } from './client'
import type { QueueItem } from './types'

export function listQueue(): Promise<QueueItem[]> {
  return http.get<QueueItem[]>('/queue')
}

/** Повторная попытка доставки всей очереди (postqueue -f) */
export function flushQueue(): Promise<void> {
  return http.post<void>('/queue/flush')
}

export function deleteQueueItem(id: string): Promise<void> {
  return http.delete(`/queue/${seg(id)}`)
}
