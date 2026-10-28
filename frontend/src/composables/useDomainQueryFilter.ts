// Фильтр по домену, синхронизированный с query-параметром ?domain= текущего маршрута:
// дашборд домена открывает списки с готовым фильтром, а выбор в Select попадает в адрес страницы.
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

export function useDomainQueryFilter() {
  const route = useRoute()
  const router = useRouter()

  function fromQuery(): string | null {
    const value = route.query.domain
    return typeof value === 'string' && value ? value : null
  }

  const filterDomain = ref<string | null>(fromQuery())

  // Выбор в фильтре → адрес страницы (без записи в историю)
  watch(filterDomain, (value) => {
    if (value === fromQuery()) return
    void router.replace({ query: { ...route.query, domain: value || undefined } })
  })

  // Адрес страницы → фильтр (переход по ссылке с другим доменом)
  watch(
    () => route.query.domain,
    () => {
      const value = fromQuery()
      if (value !== filterDomain.value) filterDomain.value = value
    },
  )

  return filterDomain
}
