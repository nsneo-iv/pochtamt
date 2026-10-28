<script setup lang="ts">
// Синхронизация с AD: предпросмотр изменений (create/update/disable/lists), затем применение
import { computed, ref } from 'vue'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import Message from 'primevue/message'
import * as api from '@/api/adSync'
import type { AdSyncItem, AdSyncResult } from '@/api/types'
import { useNotify } from '@/composables/useNotify'

const notify = useNotify()

const preview = ref<AdSyncResult | null>(null)
const applied = ref<AdSyncResult | null>(null)
const loading = ref(false)
const applying = ref(false)

/** Секции результата в порядке отображения */
const sections: { key: keyof AdSyncResult; title: string; icon: string; severity: 'success' | 'info' | 'warn' | 'secondary' }[] = [
  { key: 'create', title: 'Будут созданы', icon: 'pi pi-plus-circle', severity: 'success' },
  { key: 'update', title: 'Будут обновлены', icon: 'pi pi-pencil', severity: 'info' },
  { key: 'disable', title: 'Будут отключены', icon: 'pi pi-ban', severity: 'warn' },
  { key: 'lists', title: 'Рассылки из групп AD', icon: 'pi pi-users', severity: 'secondary' },
]

const totalChanges = computed(() => {
  const p = preview.value
  if (!p) return 0
  return p.create.length + p.update.length + p.disable.length + p.lists.length
})

/** Краткая подпись элемента: строка как есть, объект — по известным полям, иначе JSON */
function itemLabel(item: AdSyncItem): string {
  if (typeof item === 'string') return item
  for (const key of ['address', 'login', 'ad_upn', 'name', 'ad_group']) {
    const value = item[key]
    if (typeof value === 'string' && value) return value
  }
  return JSON.stringify(item)
}

/** Подробности объекта (без поля, вынесенного в подпись) */
function itemDetails(item: AdSyncItem): string | null {
  if (typeof item === 'string') return null
  const label = itemLabel(item)
  const rest = Object.fromEntries(Object.entries(item).filter(([, v]) => v !== label))
  return Object.keys(rest).length ? JSON.stringify(rest, null, 1) : null
}

async function loadPreview(): Promise<void> {
  loading.value = true
  applied.value = null
  try {
    preview.value = await api.previewAdSync()
    if (totalChanges.value === 0) notify.info('Изменений нет: база соответствует AD')
  } catch (e) {
    notify.error(e, 'Не удалось получить предпросмотр')
  } finally {
    loading.value = false
  }
}

function apply(): void {
  notify.confirmAction(
    `Применить синхронизацию с AD? Будет выполнено изменений: ${totalChanges.value}.`,
    async () => {
      applying.value = true
      try {
        applied.value = await api.applyAdSync()
        preview.value = null
        notify.success('Синхронизация с AD выполнена')
      } catch (e) {
        notify.error(e, 'Синхронизация не выполнена')
      } finally {
        applying.value = false
      }
    },
    { header: 'Синхронизация с AD', acceptLabel: 'Применить' },
  )
}

/** Что показывать: результат применения или предпросмотр */
const shown = computed(() => applied.value ?? preview.value)
</script>

<template>
  <div>
    <div class="toolbar">
      <h1 class="page-title" style="margin: 0">Синхронизация с AD</h1>
      <div class="toolbar__spacer" />
      <Button label="Предпросмотр" icon="pi pi-eye" severity="secondary" outlined :loading="loading" @click="loadPreview" />
      <Button label="Применить" icon="pi pi-sync" :loading="applying" :disabled="!preview || totalChanges === 0" @click="apply" />
    </div>
    <p class="muted" style="margin-top: 0">
      Сначала запросите предпросмотр: бэкенд сравнит пользователей и группы AD с базой и покажет, что изменится.
      Применение создаёт ящики, обновляет данные, отключает уволенных и обновляет состав рассылок с привязанной группой AD.
    </p>

    <Message v-if="applied" severity="success" :closable="false" style="margin-bottom: 1rem">
      Применено. Ниже — список выполненных изменений.
    </Message>
    <Message v-else-if="preview && totalChanges === 0" severity="info" :closable="false" style="margin-bottom: 1rem">
      Изменений нет: база соответствует AD.
    </Message>

    <div v-if="shown" class="sync-grid">
      <div v-for="section in sections" :key="section.key" class="card">
        <h3 style="margin: 0 0 0.75rem; display: flex; align-items: center; gap: 0.5rem">
          <i :class="section.icon" />
          {{ section.title }}
          <Tag :value="String(shown[section.key].length)" :severity="section.severity" />
        </h3>
        <ul class="sync-list">
          <li v-for="(item, index) in shown[section.key]" :key="index">
            <div class="mono">{{ itemLabel(item) }}</div>
            <pre v-if="itemDetails(item)" class="form__hint mono">{{ itemDetails(item) }}</pre>
          </li>
          <li v-if="shown[section.key].length === 0" class="muted">—</li>
        </ul>
      </div>
    </div>
    <div v-else-if="!loading" class="card muted">Нажмите «Предпросмотр», чтобы увидеть изменения.</div>
  </div>
</template>
