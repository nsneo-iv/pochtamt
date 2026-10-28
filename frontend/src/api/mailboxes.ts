// Почтовые ящики: /mailboxes
import { http, seg } from './client'
import type { Mailbox, MailboxCreate, MailboxFilter, MailboxSettings, MailboxSettingsUpdate, MailboxUpdate, PasswordChange } from './types'

export function getMailboxSettings(address: string): Promise<MailboxSettings> {
  return http.get<MailboxSettings>(`/mailboxes/${seg(address)}/settings`)
}

/** Отправлять только изменённые секции; 422 — ошибка в правилах Sieve */
export function updateMailboxSettings(address: string, data: MailboxSettingsUpdate): Promise<MailboxSettings> {
  return http.put<MailboxSettings>(`/mailboxes/${seg(address)}/settings`, data)
}

export function listMailboxes(filter: MailboxFilter = {}): Promise<Mailbox[]> {
  return http.get<Mailbox[]>('/mailboxes', { domain: filter.domain, q: filter.q })
}

export function createMailbox(data: MailboxCreate): Promise<Mailbox> {
  return http.post<Mailbox>('/mailboxes', data)
}

export function getMailbox(address: string): Promise<Mailbox> {
  return http.get<Mailbox>(`/mailboxes/${seg(address)}`)
}

export function updateMailbox(address: string, data: MailboxUpdate): Promise<Mailbox> {
  return http.put<Mailbox>(`/mailboxes/${seg(address)}`, data)
}

/** Только для auth=local */
export function setMailboxPassword(address: string, data: PasswordChange): Promise<void> {
  return http.post<void>(`/mailboxes/${seg(address)}/password`, data)
}

export function deleteMailbox(address: string): Promise<void> {
  return http.delete(`/mailboxes/${seg(address)}`)
}
