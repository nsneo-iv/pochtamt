<script setup lang="ts">
// Вкладка «Сводка» фильтра: счётчики Rspamd, текущие пороги и состояние антивируса
import { onBeforeUnmount, onMounted, ref } from 'vue'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import Message from 'primevue/message'
import Skeleton from 'primevue/skeleton'
import * as api from '@/api/filter'
import type { FilterOverview } from '@/api/types'
import { useNotify } from '@/composables/useNotify'
import { formatDateTime, formatNumber } from '@/utils/format'
import RspamdStatsCards from '@/components/RspamdStatsCards.vue'

const notify = useNotify()

const overview = ref<FilterOverview | null>(null)
const loading = ref(false)
const updating = ref(false)
let refreshTimer: ReturnType<typeof setTimeout> | undefined

async function load(): Promise<void> {
  loading.value = true
  try {
    overview.value = await api.getFilterOverview()
  } catch (e) {
    notify.error(e, 'Не удалось загрузить сводку фильтра')
  } finally {
    loading.value = false
  }
}

/** Запрос обновления баз ClamAV; состояние перечитываем через 5 с, когда freshclam успеет отработать */
async function updateDatabases(): Promise<void> {
  updating.value = true
  try {
    await api.requestAntivirusUpdate()
    notify.info('Обновление баз антивируса запрошено, состояние обновится через несколько секунд')
    clearTimeout(refreshTimer)
    refreshTimer = setTimeout(async () => {
      try {
        if (overview.value) overview.value.antivirus = await api.getAntivirus()
      } catch (e) {
        notify.error(e)
      } finally {
        updating.value = false
      }
    }, 5000)
  } catch (e) {
    updating.value = false
    notify.error(e)
  }
}

onMounted(load)
onBeforeUnmount(() => clearTimeout(refreshTimer))
</script>

<template>
  <div>
    <div class="toolbar">
      <a href="/rspamd/" target="_blank" rel="noopener">
        Интерфейс Rspamd <i class="pi pi-external-link" style="font-size: 0.75rem" />
      </a>
      <div class="toolbar__spacer" />
      <Button label="Обновить" icon="pi pi-refresh" severity="secondary" outlined :loading="loading" @click="load" />
    </div>

    <template v-if="loading && !overview">
      <div class="stat-grid">
        <Skeleton v-for="i in 8" :key="i" height="4.5rem" border-radius="8px" />
      </div>
    </template>

    <template v-else-if="overview">
      <RspamdStatsCards v-if="overview.stats" :stats="overview.stats" />
      <Message v-else severity="warn" :closable="false">Статистика Rspamd недоступна</Message>

      <div class="dash-grid">
        <!-- Пороги -->
        <div class="card">
          <h2 class="card__title"><i class="pi pi-sliders-h" /> Пороги баллов</h2>
          <div class="kv">
            <span>Greylist</span><strong>{{ overview.actions.greylist }}</strong>
            <span>Пометить спамом (Junk)</span><strong>{{ overview.actions.add_header }}</strong>
            <span>Отклонить на SMTP</span><strong>{{ overview.actions.reject }}</strong>
          </div>
          <p class="form__hint">Изменить пороги можно на вкладке «Пороги».</p>
        </div>

        <!-- Антивирус -->
        <div class="card">
          <h2 class="card__title">
            <i class="pi pi-shield" /> Антивирус ClamAV
            <span class="toolbar__spacer" />
            <Tag
              :severity="overview.antivirus.daemon_active ? 'success' : 'danger'"
              :value="overview.antivirus.daemon_active ? 'Демон работает' : 'Демон остановлен'"
            />
          </h2>
          <Message v-if="!overview.antivirus.available" severity="warn" :closable="false" style="margin-bottom: 0.75rem">
            Антивирус недоступен{{ overview.antivirus.detail ? `: ${overview.antivirus.detail}` : '' }}
          </Message>
          <div class="kv">
            <span>Версия движка</span><strong>{{ overview.antivirus.engine_version || '—' }}</strong>
            <span>Версия баз</span><strong>{{ overview.antivirus.db_version || '—' }}</strong>
            <span>Дата баз</span><strong>{{ formatDateTime(overview.antivirus.db_date) }}</strong>
            <span>Сигнатур</span><strong>{{ formatNumber(overview.antivirus.signatures) }}</strong>
            <span>Вес CLAMAV</span>
            <strong>
              {{ overview.antivirus.virus_score ?? '—' }}
              <span v-if="overview.antivirus.virus_score !== null && overview.antivirus.virus_score < overview.actions.reject" class="form__hint" style="color: var(--p-orange-500)">
                ниже порога reject — заражённые письма не отклоняются
              </span>
            </strong>
          </div>
          <div class="dialog-actions" style="margin-top: 0.75rem">
            <Button label="Проверить обновления баз" icon="pi pi-download" size="small" severity="secondary" outlined :loading="updating" :disabled="!overview.antivirus.available" @click="updateDatabases" />
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
