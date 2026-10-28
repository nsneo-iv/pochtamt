<script setup lang="ts">
// Алиасы и пересылки: фильтры, catch-all (@domain), получатели списком чипов
import { computed, onMounted, reactive, ref, watch } from 'vue'
import Button from 'primevue/button'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import ToggleSwitch from 'primevue/toggleswitch'
import Checkbox from 'primevue/checkbox'
import Chip from 'primevue/chip'
import Tag from 'primevue/tag'
import Message from 'primevue/message'
import AutoComplete from 'primevue/autocomplete'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import * as api from '@/api/aliases'
import type { Alias } from '@/api/types'
import { useNotify } from '@/composables/useNotify'
import { useDomains } from '@/composables/useDomains'
import { useDomainQueryFilter } from '@/composables/useDomainQueryFilter'
import { formatDateTime, isEmail, isLocalPart } from '@/utils/format'

const notify = useNotify()
const { options: domainOptions } = useDomains()

// ---- Список и фильтры ----

const aliases = ref<Alias[]>([])
const loading = ref(false)
// Фильтр по домену читается из ?domain= и пишется обратно в адрес страницы
const filterDomain = useDomainQueryFilter()
const search = ref('')

async function load(): Promise<void> {
  loading.value = true
  try {
    aliases.value = await api.listAliases({ domain: filterDomain.value ?? undefined, q: search.value.trim() || undefined })
  } catch (e) {
    notify.error(e, 'Не удалось загрузить алиасы')
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(filterDomain, load)

let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(search, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(load, 400)
})

/** Catch-all: адрес начинается с @ */
function isCatchAll(address: string): boolean {
  return address.startsWith('@')
}

// ---- Создание / редактирование ----

const editVisible = ref(false)
const editing = ref<Alias | null>(null)
const saving = ref(false)
const formError = ref<string | null>(null)
const form = reactive({
  catchAll: false,
  local: '',
  domain: null as string | null,
  targets: [] as string[],
  description: '',
  active: true,
})

const fullAddress = computed(() => {
  if (!form.domain) return ''
  if (form.catchAll) return `@${form.domain}`
  const local = form.local.trim().toLowerCase()
  return local ? `${local}@${form.domain}` : ''
})

function openCreate(): void {
  editing.value = null
  form.catchAll = false
  form.local = ''
  form.domain = filterDomain.value ?? domainOptions.value[0]?.value ?? null
  form.targets = []
  form.description = ''
  form.active = true
  formError.value = null
  editVisible.value = true
}

function openEdit(alias: Alias): void {
  editing.value = alias
  form.catchAll = isCatchAll(alias.address)
  const [local, domain] = alias.address.split('@')
  form.local = local ?? ''
  form.domain = domain ?? alias.domain
  form.targets = [...alias.targets]
  form.description = alias.description ?? ''
  form.active = alias.active
  formError.value = null
  editVisible.value = true
}

/** Нормализация получателей: обрезаем пробелы, убираем дубли */
function normalizeTargets(values: string[]): string[] {
  return [...new Set(values.map((v) => v.trim().toLowerCase()).filter(Boolean))]
}

function validate(): string | null {
  if (!editing.value) {
    if (!form.domain) return 'Выберите домен'
    if (!form.catchAll && !isLocalPart(form.local)) return 'Укажите адрес алиаса (часть до @)'
  }
  const targets = normalizeTargets(form.targets)
  if (targets.length === 0) return 'Добавьте хотя бы одного получателя'
  const bad = targets.find((t) => !isEmail(t))
  if (bad) return `Некорректный адрес получателя: ${bad}`
  return null
}

async function save(): Promise<void> {
  formError.value = validate()
  if (formError.value) return
  saving.value = true
  const targets = normalizeTargets(form.targets)
  try {
    if (editing.value) {
      await api.updateAlias(editing.value.address, {
        targets,
        description: form.description.trim() || null,
        active: form.active,
      })
      notify.success(`Алиас ${editing.value.address} обновлён`)
    } else {
      await api.createAlias({
        address: fullAddress.value,
        targets,
        description: form.description.trim() || null,
        active: form.active,
      })
      notify.success(`Алиас ${fullAddress.value} создан`)
    }
    editVisible.value = false
    await load()
  } catch (e) {
    notify.error(e)
  } finally {
    saving.value = false
  }
}

function remove(alias: Alias): void {
  notify.confirmDelete(`Удалить алиас ${alias.address}?`, async () => {
    try {
      await api.deleteAlias(alias.address)
      notify.success(`Алиас ${alias.address} удалён`)
      await load()
    } catch (e) {
      notify.error(e)
    }
  })
}

async function toggleActive(alias: Alias, value: boolean): Promise<void> {
  try {
    await api.updateAlias(alias.address, { active: value })
    alias.active = value
    notify.success(`Алиас ${alias.address} ${value ? 'включён' : 'отключён'}`)
  } catch (e) {
    notify.error(e)
  }
}
</script>

<template>
  <div>
    <div class="toolbar">
      <h1 class="page-title" style="margin: 0">Алиасы и пересылки</h1>
      <div class="toolbar__spacer" />
      <Select v-model="filterDomain" :options="domainOptions" option-label="label" option-value="value" placeholder="Все домены" show-clear style="min-width: 14rem" />
      <IconField>
        <InputIcon class="pi pi-search" />
        <InputText v-model="search" placeholder="Поиск по адресу" style="min-width: 16rem" />
      </IconField>
      <Button label="Обновить" icon="pi pi-refresh" severity="secondary" outlined :loading="loading" @click="load" />
      <Button label="Создать алиас" icon="pi pi-plus" @click="openCreate" />
    </div>

    <DataTable :value="aliases" :loading="loading" data-key="address" striped-rows size="small" paginator :rows="25" :rows-per-page-options="[25, 50, 100]" sort-field="address" :sort-order="1">
      <Column field="address" header="Адрес" sortable>
        <template #body="{ data }">
          <span class="mono">{{ data.address }}</span>
          <Tag v-if="isCatchAll(data.address)" value="catch-all" severity="warn" style="margin-left: 0.5rem" />
        </template>
      </Column>
      <Column field="targets" header="Получатели">
        <template #body="{ data }">
          <div class="chips">
            <Chip v-for="t in data.targets" :key="t" :label="t" />
          </div>
        </template>
      </Column>
      <Column field="description" header="Описание">
        <template #body="{ data }">{{ data.description || '—' }}</template>
      </Column>
      <Column field="active" header="Активен" style="width: 6rem">
        <template #body="{ data }">
          <ToggleSwitch :model-value="data.active" @update:model-value="toggleActive(data, $event)" />
        </template>
      </Column>
      <Column field="created_at" header="Создан" sortable>
        <template #body="{ data }">{{ formatDateTime(data.created_at) }}</template>
      </Column>
      <Column header="" style="width: 7rem">
        <template #body="{ data }">
          <div class="row-actions">
            <Button v-tooltip.top="'Изменить'" icon="pi pi-pencil" text rounded severity="secondary" @click="openEdit(data)" />
            <Button v-tooltip.top="'Удалить'" icon="pi pi-trash" text rounded severity="danger" @click="remove(data)" />
          </div>
        </template>
      </Column>
      <template #empty>Алиасов не найдено</template>
    </DataTable>

    <Dialog v-model:visible="editVisible" modal :header="editing ? `Алиас ${editing.address}` : 'Новый алиас'" :style="{ width: '34rem' }">
      <form class="form" @submit.prevent="save">
        <Message v-if="formError" severity="error" :closable="false">{{ formError }}</Message>
        <div v-if="!editing" class="form__check">
          <Checkbox v-model="form.catchAll" input-id="a-catchall" binary />
          <label for="a-catchall">Catch-all: принимать всю почту домена на несуществующие адреса</label>
        </div>
        <div class="form__row">
          <div v-if="!form.catchAll" class="form__field">
            <label for="a-local">Адрес</label>
            <InputText id="a-local" v-model="form.local" :disabled="editing !== null" placeholder="info" fluid />
          </div>
          <div class="form__field">
            <label for="a-domain">Домен</label>
            <Select id="a-domain" v-model="form.domain" :options="domainOptions" option-label="label" option-value="value" :disabled="editing !== null" placeholder="Домен" fluid />
          </div>
        </div>
        <div v-if="fullAddress" class="form__hint">Итоговый адрес: <span class="mono">{{ fullAddress }}</span></div>
        <div class="form__field">
          <label for="a-targets">Получатели</label>
          <AutoComplete id="a-targets" v-model="form.targets" multiple :typeahead="false" placeholder="адрес и Enter" fluid />
          <span class="form__hint">Введите адрес и нажмите Enter. Можно указывать внешние адреса — так настраивается пересылка.</span>
        </div>
        <div class="form__field">
          <label for="a-desc">Описание</label>
          <InputText id="a-desc" v-model="form.description" fluid />
        </div>
        <div class="form__check">
          <ToggleSwitch v-model="form.active" input-id="a-active" />
          <label for="a-active">Алиас активен</label>
        </div>
        <div class="dialog-actions">
          <Button type="button" label="Отмена" severity="secondary" outlined @click="editVisible = false" />
          <Button type="submit" :label="editing ? 'Сохранить' : 'Создать'" :loading="saving" />
        </div>
      </form>
    </Dialog>
  </div>
</template>
