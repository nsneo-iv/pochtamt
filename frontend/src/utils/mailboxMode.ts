// Режимы ящика: подписи и пояснения для Select и карточек
import type { MailboxMode } from '@/api/types'

export const mailboxModeOptions: { value: MailboxMode; label: string; hint: string }[] = [
  { value: 'normal', label: 'Обычный', hint: 'Приём и отправка без ограничений' },
  { value: 'receive_only', label: 'Только приём', hint: 'Ящик принимает письма, но не может отправлять' },
  { value: 'send_only', label: 'Только отправка', hint: 'Ящик отправляет письма, но входящие не принимает' },
  { value: 'internal', label: 'Только внутрь сервера', hint: 'Отправка только на адреса этого сервера, внешняя почта запрещена' },
]

export function mailboxModeLabel(mode: MailboxMode | string): string {
  return mailboxModeOptions.find((o) => o.value === mode)?.label ?? mode
}

export function mailboxModeHint(mode: MailboxMode | string): string {
  return mailboxModeOptions.find((o) => o.value === mode)?.hint ?? ''
}
