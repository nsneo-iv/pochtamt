<script setup lang="ts">
// Вкладка «История»: последние проверенные письма Rspamd с фильтрами и раскрытием символов
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Button from 'primevue/button'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import ToggleSwitch from 'primevue/toggleswitch'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import * as api from '@/api/filter'
import type { FilterHistoryAction, FilterHistoryRow } from '@/api/types'
import { useNotify } from '@/composables/useNotify'
import { formatBytes, formatDateTime } from '@/utils/format'

const notify = useNotify()

/** Строка истории с ключом для раскрытия (message_id может отсутствовать) */
type Row = FilterHistoryRow & { _key: string }

const rows = ref<Row[]>([])
const loading = ref(false)
const expandedRows = ref<Row[]>([])
const action = ref<FilterHistoryAction | null>(null)
const search = ref('')
const limit = ref(100)
const autoRefresh = ref(true)
const updatedAt = ref<Date | null>(null)

const actionOptions: { label: string; value: FilterHistoryAction }[] = [
  { label: 'Пропущено', value: 'no action' },
  { label: 'Greylist', value: 'greylist' },
  { label: 'Помечено спамом', value: 'add header' },
  { label: 'Отклонено', value: 'reject' },
  { label: 'Временный отказ', value: 'soft reject' },
]
const limitOptions = [50, 100, 200, 500].map((n) => ({ label: `${n} строк`, value: n }))

const actionLabels: Record<FilterHistoryAction, string> = {
  'no action': 'Пропущено',
  greylist: 'Greylist',
  'add header': 'Спам',
  reject: 'Отклонено',
  'soft reject': 'Временный отказ',
}

const actionSeverity: Record<FilterHistoryAction, 'success' | 'info' | 'warn' | 'danger' | 'secondary'> = {
  'no action': 'success',
  greylist: 'info',
  'add header': 'warn',
  reject: 'danger',
  'soft reject': 'secondary',
}

/** Цвет балла по действию (токены PrimeVue, работают в обеих темах) */
const scoreColor: Record<FilterHistoryAction, string> = {
  'no action': 'var(--p-green-500)',
  greylist: 'var(--p-blue-500)',
  'add header': 'var(--p-orange-500)',
  reject: 'var(--p-red-500)',
  'soft reject': 'var(--p-text-muted-color)',
}

function label(value: string): string {
  return (actionLabels as Record<string, string>)[value] ?? value
}

function severity(value: string) {
  return (actionSeverity as Record<string, 'success' | 'info' | 'warn' | 'danger' | 'secondary'>)[value] ?? 'secondary'
}

function color(value: string): string {
  return (scoreColor as Record<string, string>)[value] ?? 'inherit'
}

function formatUnix(seconds: number): string {
  return formatDateTime(new Date(seconds * 1000).toISOString())
}

function formatScore(value: number): string {
  return value.toLocaleString('ru-RU', { minimumFractionDigits: 1, maximumFractionDigits: 2 })
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const result = await api.listFilterHistory({
      limit: limit.value,
      action: action.value ?? undefined,
      q: search.value.trim() || undefined,
    })
    rows.value = result.map((row, index) => ({ ...row, _key: `${row.time}-${row.message_id ?? index}-${index}` }))
    updatedAt.value = new Date()
  } catch (e) {
    notify.error(e, 'Не удалось загрузить историю')
  } finally {
    loading.value = false
  }
}

watch([action, limit], load)

let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(search, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(load, 400)
})

// Автообновление раз в 30 с, пока включён переключатель и вкладка открыта
let refreshTimer: ReturnType<typeof setInterval> | undefined
function applyAutoRefresh(): void {
  clearInterval(refreshTimer)
  if (autoRefresh.value) refreshTimer = setInterval(load, 30000)
}
watch(autoRefresh, applyAutoRefresh)

onMounted(() => {
  void load()
  applyAutoRefresh()
})
onBeforeUnmount(() => {
  clearInterval(refreshTimer)
  clearTimeout(searchTimer)
})
</script>

<template>
  <div>
    <div class="toolbar">
      <Select v-model="action" :options="actionOptions" option-label="label" option-value="value" placeholder="Все действия" show-clear style="min-width: 12rem" />
      <IconField>
        <InputIcon class="pi pi-search" />
        <InputText v-model="search" placeholder="Отправитель, получатель, тема, IP" style="min-width: 18rem" />
      </IconField>
      <Select v-model="limit" :options="limitOptions" option-label="label" option-value="value" style="min-width: 8rem" />
      <div class="toolbar__spacer" />
      <label class="form__check" style="font-size: 0.9rem">
        <ToggleSwitch v-model="autoRefresh" />
        <span>Автообновление (30 с)</span>
      </label>
      <span v-if="updatedAt" class="form__hint">обновлено {{ updatedAt.toLocaleTimeString('ru-RU') }}</span>
      <Button label="Обновить" icon="pi pi-refresh" severity="secondary" outlined :loading="loading" @click="load" />
    </div>

    <DataTable v-model:expanded-rows="expandedRows" :value="rows" :loading="loading" data-key="_key" striped-rows size="small" scrollable>
      <Column expander style="width: 3rem" />
      <Column field="time" header="Время" style="width: 10rem">
        <template #body="{ data }">{{ formatUnix(data.time) }}</template>
      </Column>
      <Column field="sender" header="Отправитель">
        <template #body="{ data }"><span class="mono">{{ data.sender || '<>' }}</span></template>
      </Column>
      <Column field="recipients" header="Получатели">
        <template #body="{ data }"><span class="mono">{{ (data.recipients ?? []).join(', ') || '—' }}</span></template>
      </Column>
      <Column field="subject" header="Тема" style="max-width: 20rem">
        <template #body="{ data }">
          <span :title="data.subject ?? ''" style="display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap">{{ data.subject || '—' }}</span>
        </template>
      </Column>
      <Column field="score" header="Балл / порог" style="width: 8rem">
        <template #body="{ data }">
          <strong :style="{ color: color(data.action) }">{{ formatScore(data.score) }}</strong>
          <span class="muted"> / {{ formatScore(data.required_score) }}</span>
        </template>
      </Column>
      <Column field="action" header="Действие" style="width: 9rem">
        <template #body="{ data }"><Tag :severity="severity(data.action)" :value="label(data.action)" /></template>
      </Column>
      <Column field="size" header="Размер" style="width: 6rem">
        <template #body="{ data }">{{ formatBytes(data.size) }}</template>
      </Column>
      <Column field="ip" header="IP" style="width: 9rem">
        <template #body="{ data }"><span class="mono">{{ data.ip || '—' }}</span></template>
      </Column>
      <Column field="user" header="Пользователь">
        <template #body="{ data }">{{ data.user || '—' }}</template>
      </Column>
      <template #expansion="{ data }">
        <div style="padding: 0.5rem 1rem">
          <div class="form__hint" style="margin-bottom: 0.5rem">
            <span v-if="data.message_id">Message-ID: <span class="mono">{{ data.message_id }}</span></span>
            <span v-if="data.scan_time !== null && data.scan_time !== undefined"> · проверка {{ data.scan_time }} с</span>
          </div>
          <table v-if="data.symbols?.length" class="symbols-table">
            <tbody>
              <tr v-for="s in data.symbols" :key="s.name">
                <td class="mono">{{ s.name }}</td>
                <td :style="{ color: s.score > 0 ? 'var(--p-red-500)' : s.score < 0 ? 'var(--p-green-500)' : 'inherit', textAlign: 'right' }">
                  {{ s.score > 0 ? '+' : '' }}{{ formatScore(s.score) }}
                </td>
              </tr>
            </tbody>
          </table>
          <span v-else class="muted">Символы не сработали</span>
        </div>
      </template>
      <template #empty>Записей нет</template>
    </DataTable>
  </div>
</template>

<style scoped>
.symbols-table {
  border-collapse: collapse;
  font-size: 0.85rem;
}

.symbols-table td {
  padding: 0.15rem 1rem 0.15rem 0;
}
</style>
