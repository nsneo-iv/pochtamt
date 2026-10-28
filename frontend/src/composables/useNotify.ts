// Уведомления (Toast) и диалоги подтверждения удаления в едином стиле
import { useToast } from 'primevue/usetoast'
import { useConfirm } from 'primevue/useconfirm'
import { ApiError } from '@/api/client'

/** Текст ошибки для показа пользователю */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Неизвестная ошибка'
}

export function useNotify() {
  const toast = useToast()
  const confirm = useConfirm()

  function success(detail: string, summary = 'Готово'): void {
    toast.add({ severity: 'success', summary, detail, life: 3000 })
  }

  function info(detail: string, summary = 'Сведения'): void {
    toast.add({ severity: 'info', summary, detail, life: 4000 })
  }

  function error(err: unknown, summary = 'Ошибка'): void {
    toast.add({ severity: 'error', summary, detail: errorMessage(err), life: 6000 })
  }

  /** Диалог подтверждения удаления; accept вызывается только после «Удалить» */
  function confirmDelete(message: string, accept: () => void | Promise<void>, header = 'Удаление'): void {
    confirm.require({
      message,
      header,
      icon: 'pi pi-exclamation-triangle',
      rejectLabel: 'Отмена',
      acceptLabel: 'Удалить',
      rejectProps: { severity: 'secondary', outlined: true },
      acceptProps: { severity: 'danger' },
      accept: () => {
        void accept()
      },
    })
  }

  /** Диалог подтверждения произвольного действия */
  function confirmAction(
    message: string,
    accept: () => void | Promise<void>,
    options: { header?: string; acceptLabel?: string } = {},
  ): void {
    confirm.require({
      message,
      header: options.header ?? 'Подтверждение',
      icon: 'pi pi-question-circle',
      rejectLabel: 'Отмена',
      acceptLabel: options.acceptLabel ?? 'Продолжить',
      rejectProps: { severity: 'secondary', outlined: true },
      accept: () => {
        void accept()
      },
    })
  }

  return { success, info, error, confirmDelete, confirmAction }
}
