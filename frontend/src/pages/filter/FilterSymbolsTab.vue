<script setup lang="ts">
// Вкладка «Символы»: веса символов Rspamd с inline-редактированием; на сервер уходят только изменённые
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Button from 'primevue/button'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import InputText from 'primevue/inputtext'
import InputNumber from 'primevue/inputnumber'
import Tag from 'primevue/tag'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import * as api from '@/api/filter'
import type { FilterSymbol } from '@/api/types'
import { useNotify } from '@/composables/useNotify'

const notify = useNotify()

/** Символ с исходным весом, чтобы находить изменённые строки */
type Row = FilterSymbol & { original: number }

const rows = ref<Row[]>([])
const loading = ref(false)
const saving = ref(false)
const search = ref('')

const changed = computed(() => rows.value.filter((r) => r.score !== r.original))

async function load(): Promise<void> {
  loading.value = true
  try {
    const result = await api.listFilterSymbols(search.value.trim() || undefined)
    rows.value = result.map((s) => ({ ...s, original: s.score }))
  } catch (e) {
    notify.error(e, 'Не удалось загрузить символы')
  } finally {
    loading.value = false
  }
}

let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(search, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(load, 400)
})

async function save(): Promise<void> {
  if (changed.value.length === 0) return
  saving.value = true
  try {
    await api.updateFilterSymbols(changed.value.map((r) => ({ name: r.name, score: r.score })))
    notify.success(`Сохранено символов: ${changed.value.length}`)
    await load()
  } catch (e) {
    notify.error(e)
  } finally {
    saving.value = false
  }
}

function reset(): void {
  for (const row of rows.value) row.score = row.original
}

function rowClass(row: Row): string {
  return row.score !== row.original ? 'row-changed' : ''
}

function formatFrequency(value: number | null): string {
  if (value === null || value === undefined) return '—'
  return value.toLocaleString('ru-RU', { maximumFractionDigits: 3 })
}

onMounted(load)
onBeforeUnmount(() => clearTimeout(searchTimer))
</script>

<template>
  <div>
    <div class="toolbar">
      <IconField>
        <InputIcon class="pi pi-search" />
        <InputText v-model="search" placeholder="Имя или описание символа" style="min-width: 18rem" />
      </IconField>
      <Tag v-if="changed.length" :value="`изменено: ${changed.length}`" severity="warn" />
      <div class="toolbar__spacer" />
      <Button label="Обновить" icon="pi pi-refresh" severity="secondary" outlined :loading="loading" @click="load" />
      <Button label="Сбросить" icon="pi pi-undo" severity="secondary" outlined :disabled="changed.length === 0" @click="reset" />
      <Button label="Сохранить изменения" icon="pi pi-save" :loading="saving" :disabled="changed.length === 0" @click="save" />
    </div>

    <DataTable
      :value="rows"
      :loading="loading"
      data-key="name"
      :row-class="rowClass"
      striped-rows
      size="small"
      paginator
      :rows="50"
      :rows-per-page-options="[50, 100, 200]"
      sort-field="group"
      :sort-order="1"
      scrollable
    >
      <Column field="group" header="Группа" sortable style="width: 10rem">
        <template #body="{ data }">{{ data.group || '—' }}</template>
      </Column>
      <Column field="name" header="Символ" sortable>
        <template #body="{ data }"><span class="mono">{{ data.name }}</span></template>
      </Column>
      <Column field="description" header="Описание">
        <template #body="{ data }"><span class="muted">{{ data.description || '—' }}</span></template>
      </Column>
      <Column field="score" header="Вес" sortable style="width: 10rem">
        <template #body="{ data }">
          <InputNumber
            v-model="data.score"
            :min-fraction-digits="0"
            :max-fraction-digits="2"
            :step="0.1"
            size="small"
            fluid
            :input-style="{ width: '6rem' }"
          />
          <div v-if="data.score !== data.original" class="form__hint">было {{ data.original }}</div>
        </template>
      </Column>
      <Column field="frequency" header="Частота" sortable style="width: 7rem">
        <template #body="{ data }">{{ formatFrequency(data.frequency) }}</template>
      </Column>
      <template #empty>Символов не найдено</template>
    </DataTable>
  </div>
</template>

<style>
/* Подсветка изменённых строк (глобально: класс ставится DataTable на <tr>) */
.p-datatable .row-changed > td {
  background: color-mix(in srgb, var(--p-orange-500) 12%, transparent) !important;
}
</style>
