<script setup lang="ts">
// Сводка: счётчики из GET /stats и блок Rspamd (антиспам и антивирус)
import { computed, onMounted, ref } from 'vue'
import Button from 'primevue/button'
import { getStats } from '@/api/stats'
import type { Stats } from '@/api/types'
import { useNotify } from '@/composables/useNotify'
import { useAuthStore } from '@/stores/auth'
import { formatMb } from '@/utils/format'
import RspamdStatsCards from '@/components/RspamdStatsCards.vue'

const notify = useNotify()
const auth = useAuthStore()
const stats = ref<Stats | null>(null)
const loading = ref(false)

/** Карточки сводки; очередь показываем только superadmin (страница /queue ему же) */
const cards = computed(() => {
  const s = stats.value
  const items = [
    { key: 'domains', label: 'Домены', icon: 'pi pi-globe', value: s?.domains ?? '—', route: 'domains' },
    { key: 'mailboxes', label: 'Ящики', icon: 'pi pi-inbox', value: s?.mailboxes ?? '—', route: 'mailboxes' },
    { key: 'aliases', label: 'Алиасы', icon: 'pi pi-directions', value: s?.aliases ?? '—', route: 'aliases' },
    { key: 'lists', label: 'Рассылки', icon: 'pi pi-users', value: s?.lists ?? '—', route: 'lists' },
    { key: 'used', label: 'Занято места', icon: 'pi pi-database', value: s ? formatMb(s.used_mb) : '—', route: null },
  ]
  if (auth.isSuperadmin) {
    items.splice(4, 0, { key: 'queue', label: 'Писем в очереди', icon: 'pi pi-list', value: s?.queue ?? '—', route: 'queue' })
  }
  return items
})

async function load(): Promise<void> {
  loading.value = true
  try {
    stats.value = await getStats()
  } catch (e) {
    notify.error(e, 'Не удалось загрузить сводку')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="toolbar">
      <h1 class="page-title" style="margin: 0">Сводка</h1>
      <div class="toolbar__spacer" />
      <RouterLink v-if="auth.isSuperadmin" :to="{ name: 'system' }">
        <Button label="Состояние сервера" icon="pi pi-server" severity="secondary" outlined />
      </RouterLink>
      <Button label="Обновить" icon="pi pi-refresh" severity="secondary" outlined :loading="loading" @click="load" />
    </div>
    <div class="stat-grid">
      <component
        :is="card.route ? 'RouterLink' : 'div'"
        v-for="card in cards"
        :key="card.key"
        :to="card.route ? { name: card.route } : undefined"
        class="stat-card"
      >
        <i :class="[card.icon, 'stat-card__icon']" />
        <div>
          <div class="stat-card__value">{{ card.value }}</div>
          <div class="stat-card__label">{{ card.label }}</div>
        </div>
      </component>
    </div>

    <!-- Антиспам и антивирус: только когда бэкенд отдал stats.rspamd -->
    <div v-if="stats?.rspamd" class="card" style="margin-top: 1.5rem">
      <h2 class="card__title">
        <i class="pi pi-shield" />
        Антиспам и антивирус
        <span class="toolbar__spacer" />
        <RouterLink :to="{ name: 'filter' }" style="font-size: 0.9rem; font-weight: 400; margin-right: 1rem">Настройки фильтра</RouterLink>
        <a href="/rspamd/" target="_blank" rel="noopener" style="font-size: 0.9rem; font-weight: 400">
          Интерфейс Rspamd <i class="pi pi-external-link" style="font-size: 0.75rem" />
        </a>
      </h2>
      <p class="muted" style="margin: 0 0 1rem">Счётчики с момента запуска Rspamd.</p>
      <RspamdStatsCards :stats="stats.rspamd" />
    </div>
  </div>
</template>
