<script setup lang="ts">
// Вкладка «Списки»: белые и чёрные списки отправителей и IP — по карточке на список
import { onMounted, reactive, ref } from 'vue'
import Button from 'primevue/button'
import AutoComplete from 'primevue/autocomplete'
import Message from 'primevue/message'
import Tag from 'primevue/tag'
import * as api from '@/api/filter'
import type { FilterList, FilterListId } from '@/api/types'
import { useNotify } from '@/composables/useNotify'

const notify = useNotify()

const lists = ref<FilterList[]>([])
const loading = ref(false)
/** Редактируемые копии записей по id списка */
const drafts = reactive<Record<string, string[]>>({})
const saving = reactive<Record<string, boolean>>({})

const hints: Record<FilterListId, string> = {
  whitelist_from: 'Адрес отправителя (user@example.com) или домен (example.com). Письма из списка не проверяются на спам.',
  blacklist_from: 'Адрес отправителя или домен. Письма из списка отклоняются.',
  whitelist_ip: 'IP-адрес (203.0.113.5) или сеть CIDR (203.0.113.0/24). Письма с этих адресов не проверяются на спам.',
  blacklist_ip: 'IP-адрес или сеть CIDR. Письма с этих адресов отклоняются.',
}

const icons: Record<FilterListId, string> = {
  whitelist_from: 'pi pi-check-circle',
  blacklist_from: 'pi pi-ban',
  whitelist_ip: 'pi pi-check-circle',
  blacklist_ip: 'pi pi-ban',
}

function normalize(values: string[]): string[] {
  return [...new Set(values.map((v) => v.trim().toLowerCase()).filter(Boolean))]
}

function isDirty(list: FilterList): boolean {
  const draft = normalize(drafts[list.id] ?? [])
  const current = normalize(list.entries)
  return draft.length !== current.length || draft.some((v, i) => v !== current[i])
}

async function load(): Promise<void> {
  loading.value = true
  try {
    lists.value = await api.listFilterLists()
    for (const list of lists.value) drafts[list.id] = [...list.entries]
  } catch (e) {
    notify.error(e, 'Не удалось загрузить списки')
  } finally {
    loading.value = false
  }
}

async function save(list: FilterList): Promise<void> {
  saving[list.id] = true
  try {
    const updated = await api.updateFilterList(list.id, normalize(drafts[list.id] ?? []))
    const index = lists.value.findIndex((l) => l.id === list.id)
    if (index >= 0) lists.value[index] = updated
    drafts[list.id] = [...updated.entries]
    notify.success(`Список «${updated.title}» сохранён`)
  } catch (e) {
    notify.error(e)
  } finally {
    saving[list.id] = false
  }
}

function reset(list: FilterList): void {
  drafts[list.id] = [...list.entries]
}

onMounted(load)
</script>

<template>
  <div>
    <div class="toolbar">
      <p class="muted" style="margin: 0">Списки хранятся в картах Rspamd и применяются сразу после сохранения.</p>
      <div class="toolbar__spacer" />
      <Button label="Обновить" icon="pi pi-refresh" severity="secondary" outlined :loading="loading" @click="load" />
    </div>

    <div class="dash-grid" style="margin-top: 0">
      <div v-for="list in lists" :key="list.id" class="card">
        <h2 class="card__title">
          <i :class="icons[list.id]" />
          {{ list.title }}
          <Tag :value="String((drafts[list.id] ?? []).length)" severity="secondary" />
          <span class="toolbar__spacer" />
          <Tag v-if="isDirty(list)" value="не сохранено" severity="warn" />
        </h2>
        <p v-if="list.description" class="muted" style="margin-top: 0">{{ list.description }}</p>
        <Message v-if="!list.available" severity="warn" :closable="false" style="margin-bottom: 0.75rem">
          Карта не найдена в Rspamd — редактирование недоступно.
        </Message>
        <div class="form__field">
          <AutoComplete
            v-model="drafts[list.id]"
            multiple
            :typeahead="false"
            :disabled="!list.available"
            placeholder="запись и Enter"
            fluid
          />
          <span class="form__hint">{{ hints[list.id] }} Введите запись и нажмите Enter; удалить — крестиком на чипе.</span>
        </div>
        <div class="dialog-actions" style="margin-top: 0.75rem">
          <Button label="Отменить" severity="secondary" outlined size="small" :disabled="!isDirty(list)" @click="reset(list)" />
          <Button label="Сохранить" icon="pi pi-save" size="small" :loading="saving[list.id]" :disabled="!list.available || !isDirty(list)" @click="save(list)" />
        </div>
      </div>
    </div>
    <p v-if="!loading && lists.length === 0" class="muted">Списки не получены</p>
  </div>
</template>
