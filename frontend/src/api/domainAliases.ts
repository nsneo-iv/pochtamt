// Доменные алиасы: /domain-aliases
import { http, seg } from './client'
import type { DomainAlias, DomainAliasCreate } from './types'

export function listDomainAliases(): Promise<DomainAlias[]> {
  return http.get<DomainAlias[]>('/domain-aliases')
}

export function createDomainAlias(data: DomainAliasCreate): Promise<DomainAlias> {
  return http.post<DomainAlias>('/domain-aliases', data)
}

export function deleteDomainAlias(aliasDomain: string): Promise<void> {
  return http.delete(`/domain-aliases/${seg(aliasDomain)}`)
}
