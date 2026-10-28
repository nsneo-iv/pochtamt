// Домены и DKIM-ключи: /domains, /domains/{name}/dkim
import { http, seg } from './client'
import type { Dkim, DkimCreate, Domain, DomainCreate, DomainDashboard, DomainDetail, DomainSettings, DomainUpdate } from './types'

export function getDomainSettings(name: string): Promise<DomainSettings> {
  return http.get<DomainSettings>(`/domains/${seg(name)}/settings`)
}

/** Только суперадмин */
export function updateDomainSettings(name: string, data: DomainSettings): Promise<DomainSettings> {
  return http.put<DomainSettings>(`/domains/${seg(name)}/settings`, data)
}

export function listDomains(): Promise<Domain[]> {
  return http.get<Domain[]>('/domains')
}

export function createDomain(data: DomainCreate): Promise<Domain> {
  return http.post<Domain>('/domains', data)
}

/** Домен со статистикой (stats: ящики, алиасы, занято МБ) */
export function getDomain(name: string): Promise<DomainDetail> {
  return http.get<DomainDetail>(`/domains/${seg(name)}`)
}

export function updateDomain(name: string, data: DomainUpdate): Promise<Domain> {
  return http.put<Domain>(`/domains/${seg(name)}`, data)
}

/** 409 — если в домене есть ящики */
export function deleteDomain(name: string): Promise<void> {
  return http.delete(`/domains/${seg(name)}`)
}

/** Сводка домена: статистика, DKIM, проверка DNS (до ~8 с), топ ящиков, последние действия */
export function getDomainDashboard(name: string): Promise<DomainDashboard> {
  return http.get<DomainDashboard>(`/domains/${seg(name)}/dashboard`)
}

/** null — ключ не создан */
export function getDkim(name: string): Promise<Dkim | null> {
  return http.get<Dkim | null>(`/domains/${seg(name)}/dkim`)
}

export function createDkim(name: string, data: DkimCreate = {}): Promise<Dkim> {
  return http.post<Dkim>(`/domains/${seg(name)}/dkim`, data)
}

export function deleteDkim(name: string): Promise<void> {
  return http.delete(`/domains/${seg(name)}/dkim`)
}
