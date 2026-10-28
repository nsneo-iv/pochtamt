// Копирование текста в буфер обмена с запасным вариантом для http без clipboard API

export async function copyToClipboard(text: string): Promise<void> {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text)
    return
  }
  // Запасной вариант: скрытое текстовое поле + execCommand
  const area = document.createElement('textarea')
  area.value = text
  area.setAttribute('readonly', '')
  area.style.position = 'fixed'
  area.style.opacity = '0'
  document.body.appendChild(area)
  area.select()
  try {
    if (!document.execCommand('copy')) throw new Error('Буфер обмена недоступен')
  } finally {
    document.body.removeChild(area)
  }
}
