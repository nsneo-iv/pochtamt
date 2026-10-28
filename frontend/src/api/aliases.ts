// Алиасы и пересылки: /aliases (catch-all — address "@domain")
import { http, seg } from './client'
import type { Alias, AliasCreate, AliasFilter, AliasUpdate } from './types'

export function listAliases(filter: AliasFilter = {}): Promise<Alias[]> {
  return http.get<Alias[]>('/aliases', { domain: filter.domain, q: filter.q })
}

export function createAlias(data: AliasCreate): Promise<Alias> {
  return http.post<Alias>('/aliases', data)
}

export function getAlias(address: string): Promise<Alias> {
  return http.get<Alias>(`/aliases/${seg(address)}`)
}

export function updateAlias(address: string, data: AliasUpdate): Promise<Alias> {
  return http.put<Alias>(`/aliases/${seg(address)}`, data)
}

export function deleteAlias(address: string): Promise<void> {
  return http.delete(`/aliases/${seg(address)}`)
}
