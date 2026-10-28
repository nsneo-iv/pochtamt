// Журнал аудита: GET /audit с пагинацией limit/offset
import { http } from './client'
import type { AuditPage, AuditQuery } from './types'

export function listAudit(query: AuditQuery): Promise<AuditPage> {
  return http.get<AuditPage>('/audit', {
    limit: query.limit,
    offset: query.offset,
    actor: query.actor,
    object: query.object,
  })
}
