<script setup lang="ts">
// Очередь Postfix: таблица писем, повторная отправка всей очереди, удаление письма
import { onMounted, ref } from 'vue'
import Button from 'primevue/button'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Chip from 'primevue/chip'
import * as api from '@/api/queue'
import type { QueueItem } from '@/api/types'
import { useNotify } from '@/composables/useNotify'
import { formatBytes, formatDateTime } from '@/utils/format'

const notify = useNotify()

const items = ref<QueueItem[]>([])
const loading = ref(false)
const flushing = ref(false)

async function load(): Promise<void> {
  loading.value = true
  try {
    items.value = await api.listQueue()
  } catch (e) {
    notify.error(e, 'Не удалось загрузить очередь')
  } finally {
    loading.value = false
  }
}

onMounted(load)

function flush(): void {
  notify.confirmAction(
    'Повторить доставку всех писем в очереди? Postfix попробует отправить их заново.',
    async () => {
      flushing.value = true
      try {
        await api.flushQueue()
        notify.success('Очередь отправлена на повторную доставку')
        await load()
      } catch (e) {
        notify.error(e)
      } finally {
        flushing.value = false
      }
    },
    { header: 'Повторная доставка', acceptLabel: 'Отправить' },
  )
}

function remove(item: QueueItem): void {
  notify.confirmDelete(`Удалить письмо ${item.id} от ${item.sender || '<>'} из очереди?`, async () => {
    try {
      await api.deleteQueueItem(item.id)
      notify.success(`Письмо ${item.id} удалено из очереди`)
      await load()
    } catch (e) {
      notify.error(e)
    }
  })
}
</script>

<template>
  <div>
    <div class="toolbar">
      <h1 class="page-title" style="margin: 0">Очередь Postfix</h1>
      <div class="toolbar__spacer" />
      <Button label="Обновить" icon="pi pi-refresh" severity="secondary" outlined :loading="loading" @click="load" />
      <Button label="Отправить очередь" icon="pi pi-send" :loading="flushing" :disabled="items.length === 0" @click="flush" />
    </div>

    <DataTable :value="items" :loading="loading" data-key="id" striped-rows size="small" paginator :rows="50" :rows-per-page-options="[50, 100, 200]" sort-field="arrival" :sort-order="-1">
      <Column field="id" header="ID" sortable>
        <template #body="{ data }"><span class="mono">{{ data.id }}</span></template>
      </Column>
      <Column field="sender" header="Отправитель" sortable>
        <template #body="{ data }"><span class="mono">{{ data.sender || '<>' }}</span></template>
      </Column>
      <Column field="recipients" header="Получатели">
        <template #body="{ data }">
          <div class="chips">
            <Chip v-for="r in data.recipients" :key="r" :label="r" />
          </div>
        </template>
      </Column>
      <Column field="size" header="Размер" sortable style="width: 7rem">
        <template #body="{ data }">{{ formatBytes(data.size) }}</template>
      </Column>
      <Column field="arrival" header="В очереди с" sortable>
        <template #body="{ data }">{{ formatDateTime(data.arrival) }}</template>
      </Column>
      <Column field="reason" header="Причина">
        <template #body="{ data }"><span class="muted">{{ data.reason || '—' }}</span></template>
      </Column>
      <Column header="" style="width: 5rem">
        <template #body="{ data }">
          <div class="row-actions">
            <Button v-tooltip.top="'Удалить из очереди'" icon="pi pi-trash" text rounded severity="danger" @click="remove(data)" />
          </div>
        </template>
      </Column>
      <template #empty>Очередь пуста</template>
    </DataTable>
  </div>
</template>
