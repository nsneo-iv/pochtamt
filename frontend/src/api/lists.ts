// Рассылки (группы): /lists
import { http, seg } from './client'
import type { MailingList, MailingListCreate, MailingListUpdate } from './types'

export function listMailingLists(domain?: string): Promise<MailingList[]> {
  return http.get<MailingList[]>('/lists', { domain })
}

export function createMailingList(data: MailingListCreate): Promise<MailingList> {
  return http.post<MailingList>('/lists', data)
}

export function updateMailingList(address: string, data: MailingListUpdate): Promise<MailingList> {
  return http.put<MailingList>(`/lists/${seg(address)}`, data)
}

export function deleteMailingList(address: string): Promise<void> {
  return http.delete(`/lists/${seg(address)}`)
}
