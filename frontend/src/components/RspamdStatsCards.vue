<script setup lang="ts">
// Карточки счётчиков Rspamd — используются на общей сводке и на вкладке «Сводка» фильтра
import { computed } from 'vue'
import type { RspamdStats } from '@/api/types'
import { formatNumber, formatUptime } from '@/utils/format'

const props = defineProps<{ stats: RspamdStats }>()

const cards = computed(() => {
  const r = props.stats
  return [
    { key: 'scanned', label: 'Проверено писем', icon: 'pi pi-search', value: formatNumber(r.scanned) },
    { key: 'ham', label: 'Не спам', icon: 'pi pi-check-circle', value: formatNumber(r.ham) },
    { key: 'spam', label: 'Спам', icon: 'pi pi-exclamation-circle', value: formatNumber(r.spam) },
    { key: 'reject', label: 'Отклонено', icon: 'pi pi-ban', value: formatNumber(r.reject) },
    { key: 'add_header', label: 'В карантин', icon: 'pi pi-flag', value: formatNumber(r.add_header) },
    { key: 'greylist', label: 'Greylist', icon: 'pi pi-clock', value: formatNumber(r.greylist) },
    { key: 'learned', label: 'Обучено', icon: 'pi pi-book', value: formatNumber(r.learned) },
    { key: 'uptime', label: 'Аптайм Rspamd', icon: 'pi pi-power-off', value: formatUptime(r.uptime) },
  ]
})
</script>

<template>
  <div class="stat-grid">
    <div v-for="card in cards" :key="card.key" class="stat-card stat-card--small">
      <i :class="[card.icon, 'stat-card__icon']" />
      <div>
        <div class="stat-card__value">{{ card.value }}</div>
        <div class="stat-card__label">{{ card.label }}</div>
      </div>
    </div>
  </div>
</template>
