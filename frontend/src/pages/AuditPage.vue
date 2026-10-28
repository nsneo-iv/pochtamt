<script setup lang="ts">
// Журнал аудита: серверная пагинация limit/offset, фильтры по актору и объекту
import { onMounted, ref } from 'vue'
import Button from 'primevue/button'
import DataTable from 'primevue/datatable'
import type { DataTablePageEvent } from 'primevue/datatable'
import Column from 'primevue/column'
import InputText from 'primevue/inputtext'
import * as api from '@/api/audit'
import type { AuditItem } from '@/api/types'
import { useNotify } from '@/composables/useNotify'
import { formatDateTime } from '@/utils/format'

const notify = useNotify()

const items = ref<AuditItem[]>([])
const total = ref(0)
const loading = ref(false)
const rows = ref(50)
const first = ref(0)
const actor = ref('')
const object = ref('')

async function load(): Promise<void> {
  loading.value = true
  try {
    const page = await api.listAudit({
      limit: rows.value,
      offset: first.value,
      actor: actor.value.trim() || undefined,
      object: object.value.trim() || undefined,
    })
    items.value = page.items
    total.value = page.total
  } catch (e) {
    notify.error(e, 'Не удалось загрузить журнал')
  } finally {
    loading.value = false
  }
}

onMounted(load)

function onPage(event: DataTablePageEvent): void {
  first.value = event.first
  rows.value = event.rows
  void load()
}

/** Применить фильтры — с первой страницы */
function applyFilters(): void {
  first.value = 0
  void load()
}

function resetFilters(): void {
  actor.value = ''
  object.value = ''
  applyFilters()
}

/** Подробности могут быть строкой или объектом — показываем компактно */
function formatDetails(details: unknown): string {
  if (details === null || details === undefined || details === '') return '—'
  if (typeof details === 'string') return details
  try {
    return JSON.stringify(details)
  } catch {
    return String(details)
  }
}
</script>

<template>
  <div>
    <div class="toolbar">
      <h1 class="page-title" style="margin: 0">Аудит</h1>
      <div class="toolbar__spacer" />
      <InputText v-model="actor" placeholder="Кто (логин)" style="min-width: 12rem" @keyup.enter="applyFilters" />
      <InputText v-model="object" placeholder="Объект (адрес, домен)" style="min-width: 14rem" @keyup.enter="applyFilters" />
      <Button label="Найти" icon="pi pi-search" @click="applyFilters" />
      <Button label="Сбросить" icon="pi pi-times" severity="secondary" outlined @click="resetFilters" />
      <Button label="Обновить" icon="pi pi-refresh" severity="secondary" outlined :loading="loading" @click="load" />
    </div>

    <DataTable
      :value="items"
      :loading="loading"
      lazy
      paginator
      :rows="rows"
      :first="first"
      :total-records="total"
      :rows-per-page-options="[25, 50, 100, 200]"
      striped-rows
      size="small"
      @page="onPage"
    >
      <Column field="ts" header="Время" style="width: 11rem">
        <template #body="{ data }">{{ formatDateTime(data.ts) }}</template>
      </Column>
      <Column field="actor" header="Кто" style="width: 14rem" />
      <Column field="action" header="Действие" style="width: 12rem">
        <template #body="{ data }"><span class="mono">{{ data.action }}</span></template>
      </Column>
      <Column field="object" header="Объект">
        <template #body="{ data }"><span class="mono">{{ data.object }}</span></template>
      </Column>
      <Column field="details" header="Подробности">
        <template #body="{ data }"><span class="mono muted">{{ formatDetails(data.details) }}</span></template>
      </Column>
      <template #empty>Записей нет</template>
    </DataTable>
  </div>
</template>
