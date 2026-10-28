// Настройки сервера (только суперадмин): smarthost, TLS-политики, правила доступа SMTP, параметры служб
import { http, seg } from './client'
import type {
  AccessRule,
  AccessRuleCreate,
  AccessRuleKind,
  ServerParam,
  Smarthost,
  SmarthostUpdate,
  TlsPolicy,
  TlsPolicyUpdate,
} from './types'

export function getSmarthost(): Promise<Smarthost> {
  return http.get<Smarthost>('/server/smarthost')
}

/** password опущен = не менять */
export function updateSmarthost(data: SmarthostUpdate): Promise<Smarthost> {
  return http.put<Smarthost>('/server/smarthost', data)
}

export function listTlsPolicies(): Promise<TlsPolicy[]> {
  return http.get<TlsPolicy[]>('/server/tls-policies')
}

/** Создание и изменение — один и тот же PUT по домену */
export function putTlsPolicy(data: TlsPolicyUpdate): Promise<TlsPolicy> {
  return http.put<TlsPolicy>(`/server/tls-policies/${seg(data.domain)}`, data)
}

export function deleteTlsPolicy(domain: string): Promise<void> {
  return http.delete(`/server/tls-policies/${seg(domain)}`)
}

export function listAccessRules(kind?: AccessRuleKind): Promise<AccessRule[]> {
  return http.get<AccessRule[]>('/server/access-rules', { kind })
}

export function createAccessRule(data: AccessRuleCreate): Promise<AccessRule> {
  return http.post<AccessRule>('/server/access-rules', data)
}

export function updateAccessRule(id: number, data: AccessRuleCreate): Promise<AccessRule> {
  return http.put<AccessRule>(`/server/access-rules/${id}`, data)
}

export function deleteAccessRule(id: number): Promise<void> {
  return http.delete(`/server/access-rules/${id}`)
}

export function listServerParams(): Promise<ServerParam[]> {
  return http.get<ServerParam[]>('/server/params')
}

/** Применяется сразу (reload службы); 422 — значение не прошло проверку */
export function updateServerParam(key: string, value: string): Promise<ServerParam> {
  return http.put<ServerParam>(`/server/params/${seg(key)}`, { value })
}
