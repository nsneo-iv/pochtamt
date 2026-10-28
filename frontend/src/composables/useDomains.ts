// Список доменов для выпадающих фильтров и форм (ящики, алиасы, рассылки)
import { computed, onMounted, ref } from 'vue'
import { listDomains } from '@/api/domains'
import type { Domain } from '@/api/types'
import { useNotify } from './useNotify'

export function useDomains(autoload = true) {
  const notify = useNotify()
  const domains = ref<Domain[]>([])
  const loading = ref(false)

  /** Варианты для Select: только имена доменов */
  const options = computed(() => domains.value.map((d) => ({ label: d.name, value: d.name })))

  async function load(): Promise<void> {
    loading.value = true
    try {
      domains.value = await listDomains()
    } catch (e) {
      notify.error(e, 'Не удалось загрузить домены')
    } finally {
      loading.value = false
    }
  }

  if (autoload) onMounted(load)

  return { domains, options, loading, load }
}
