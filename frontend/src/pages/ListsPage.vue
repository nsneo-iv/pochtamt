<script setup lang="ts">
// Рассылки (группы): участники чипами; при заданной группе AD состав только для чтения
import { computed, onMounted, reactive, ref, watch } from 'vue'
import Button from 'primevue/button'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import ToggleSwitch from 'primevue/toggleswitch'
import Chip from 'primevue/chip'
import Tag from 'primevue/tag'
import Message from 'primevue/message'
import AutoComplete from 'primevue/autocomplete'
import * as api from '@/api/lists'
import type { MailingList } from '@/api/types'
import { useNotify } from '@/composables/useNotify'
import { useAuthStore } from '@/stores/auth'
import { useDomains } from '@/composables/useDomains'
import { useDomainQueryFilter } from '@/composables/useDomainQueryFilter'
import { formatDateTime, isEmail, isLocalPart } from '@/utils/format'

const notify = useNotify()
const auth = useAuthStore()
const { options: domainOptions } = useDomains()

/** Сколько участников показывать в таблице до «+N» */
const PREVIEW_MEMBERS = 5

const lists = ref<MailingList[]>([])
const loading = ref(false)
// Фильтр по домену читается из ?domain= и пишется обратно в адрес страницы
const filterDomain = useDomainQueryFilter()

async function load(): Promise<void> {
  loading.value = true
  try {
    lists.value = await api.listMailingLists(filterDomain.value ?? undefined)
  } catch (e) {
    notify.error(e, 'Не удалось загрузить рассылки')
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(filterDomain, load)

// ---- Создание / редактирование ----

const editVisible = ref(false)
const editing = ref<MailingList | null>(null)
const saving = ref(false)
const formError = ref<string | null>(null)
const form = reactive({
  local: '',
  domain: null as string | null,
  name: '',
  members: [] as string[],
  ad_group: '',
  active: true,
})

const fullAddress = computed(() => (form.local && form.domain ? `${form.local.trim().toLowerCase()}@${form.domain}` : ''))
/** Состав управляется синхронизацией с AD — вручную не правим */
const membersReadonly = computed(() => form.ad_group.trim().length > 0)

function openCreate(): void {
  editing.value = null
  form.local = ''
  form.domain = filterDomain.value ?? domainOptions.value[0]?.value ?? null
  form.name = ''
  form.members = []
  form.ad_group = ''
  form.active = true
  formError.value = null
  editVisible.value = true
}

function openEdit(list: MailingList): void {
  editing.value = list
  const [local, domain] = list.address.split('@')
  form.local = local ?? ''
  form.domain = domain ?? list.domain
  form.name = list.name
  form.members = [...list.members]
  form.ad_group = list.ad_group ?? ''
  form.active = list.active
  formError.value = null
  editVisible.value = true
}

function normalizeMembers(values: string[]): string[] {
  return [...new Set(values.map((v) => v.trim().toLowerCase()).filter(Boolean))]
}

function validate(): string | null {
  if (!editing.value) {
    if (!form.domain) return 'Выберите домен'
    if (!isLocalPart(form.local)) return 'Укажите адрес рассылки (часть до @)'
  }
  if (!form.name.trim()) return 'Укажите название рассылки'
  if (!membersReadonly.value) {
    const bad = normalizeMembers(form.members).find((m) => !isEmail(m))
    if (bad) return `Некорректный адрес участника: ${bad}`
  }
  return null
}

async function save(): Promise<void> {
  formError.value = validate()
  if (formError.value) return
  saving.value = true
  const adGroup = form.ad_group.trim() || null
  try {
    if (editing.value) {
      await api.updateMailingList(editing.value.address, {
        name: form.name.trim(),
        // При заданной группе AD состав не отправляем — его обновит синхронизация
        members: membersReadonly.value ? undefined : normalizeMembers(form.members),
        ad_group: adGroup,
        active: form.active,
      })
      notify.success(`Рассылка ${editing.value.address} обновлена`)
    } else {
      await api.createMailingList({
        address: fullAddress.value,
        name: form.name.trim(),
        members: membersReadonly.value ? [] : normalizeMembers(form.members),
        ad_group: adGroup,
        active: form.active,
      })
      notify.success(`Рассылка ${fullAddress.value} создана`)
    }
    editVisible.value = false
    await load()
  } catch (e) {
    notify.error(e)
  } finally {
    saving.value = false
  }
}

function remove(list: MailingList): void {
  notify.confirmDelete(`Удалить рассылку ${list.address}?`, async () => {
    try {
      await api.deleteMailingList(list.address)
      notify.success(`Рассылка ${list.address} удалена`)
      await load()
    } catch (e) {
      notify.error(e)
    }
  })
}

async function toggleActive(list: MailingList, value: boolean): Promise<void> {
  try {
    await api.updateMailingList(list.address, { active: value })
    list.active = value
    notify.success(`Рассылка ${list.address} ${value ? 'включена' : 'отключена'}`)
  } catch (e) {
    notify.error(e)
  }
}

// ---- Просмотр полного состава ----

const membersVisible = ref(false)
const membersTarget = ref<MailingList | null>(null)

function showMembers(list: MailingList): void {
  membersTarget.value = list
  membersVisible.value = true
}
</script>

<template>
  <div>
    <div class="toolbar">
      <h1 class="page-title" style="margin: 0">Рассылки</h1>
      <div class="toolbar__spacer" />
      <Select v-model="filterDomain" :options="domainOptions" option-label="label" option-value="value" placeholder="Все домены" show-clear style="min-width: 14rem" />
      <Button label="Обновить" icon="pi pi-refresh" severity="secondary" outlined :loading="loading" @click="load" />
      <Button label="Создать рассылку" icon="pi pi-plus" @click="openCreate" />
    </div>

    <DataTable :value="lists" :loading="loading" data-key="address" striped-rows size="small" paginator :rows="25" :rows-per-page-options="[25, 50, 100]" sort-field="address" :sort-order="1">
      <Column field="address" header="Адрес" sortable>
        <template #body="{ data }"><span class="mono">{{ data.address }}</span></template>
      </Column>
      <Column field="name" header="Название" sortable />
      <Column field="members" header="Участники">
        <template #body="{ data }">
          <div class="chips">
            <Chip v-for="m in data.members.slice(0, PREVIEW_MEMBERS)" :key="m" :label="m" />
            <Tag v-if="data.members.length > PREVIEW_MEMBERS" :value="`+${data.members.length - PREVIEW_MEMBERS}`" severity="secondary" style="cursor: pointer" @click="showMembers(data)" />
            <span v-if="data.members.length === 0" class="muted">нет участников</span>
          </div>
        </template>
      </Column>
      <Column field="ad_group" header="Группа AD">
        <template #body="{ data }">
          <template v-if="data.ad_group">
            <span class="mono" :title="data.ad_group">{{ data.ad_group }}</span>
            <div class="form__hint">синхронизировано: {{ formatDateTime(data.synced_at) }}</div>
          </template>
          <span v-else class="muted">—</span>
        </template>
      </Column>
      <Column field="active" header="Активна" style="width: 6rem">
        <template #body="{ data }">
          <ToggleSwitch :model-value="data.active" @update:model-value="toggleActive(data, $event)" />
        </template>
      </Column>
      <Column header="" style="width: 7rem">
        <template #body="{ data }">
          <div class="row-actions">
            <Button v-tooltip.top="'Изменить'" icon="pi pi-pencil" text rounded severity="secondary" @click="openEdit(data)" />
            <Button v-tooltip.top="'Удалить'" icon="pi pi-trash" text rounded severity="danger" @click="remove(data)" />
          </div>
        </template>
      </Column>
      <template #empty>Рассылок не найдено</template>
    </DataTable>

    <Dialog v-model:visible="editVisible" modal :header="editing ? `Рассылка ${editing.address}` : 'Новая рассылка'" :style="{ width: '36rem' }">
      <form class="form" @submit.prevent="save">
        <Message v-if="formError" severity="error" :closable="false">{{ formError }}</Message>
        <div class="form__row">
          <div class="form__field">
            <label for="l-local">Адрес</label>
            <InputText id="l-local" v-model="form.local" :disabled="editing !== null" placeholder="all" fluid />
          </div>
          <div class="form__field">
            <label for="l-domain">Домен</label>
            <Select id="l-domain" v-model="form.domain" :options="domainOptions" option-label="label" option-value="value" :disabled="editing !== null" placeholder="Домен" fluid />
          </div>
        </div>
        <div class="form__field">
          <label for="l-name">Название</label>
          <InputText id="l-name" v-model="form.name" placeholder="Все сотрудники" fluid />
        </div>
        <div v-if="auth.adEnabled" class="form__field">
          <label for="l-group">Группа AD (DN)</label>
          <InputText id="l-group" v-model="form.ad_group" placeholder="CN=Сотрудники,OU=Группы,DC=corp,DC=local" fluid />
          <span class="form__hint">Если задана, состав берётся из AD при синхронизации и вручную не правится.</span>
        </div>
        <div class="form__field">
          <label for="l-members">Участники</label>
          <template v-if="membersReadonly">
            <div class="chips">
              <Chip v-for="m in form.members" :key="m" :label="m" />
              <span v-if="form.members.length === 0" class="muted">состав появится после синхронизации с AD</span>
            </div>
          </template>
          <template v-else>
            <AutoComplete id="l-members" v-model="form.members" multiple :typeahead="false" placeholder="адрес и Enter" fluid />
            <span class="form__hint">Введите адрес и нажмите Enter.</span>
          </template>
        </div>
        <div class="form__check">
          <ToggleSwitch v-model="form.active" input-id="l-active" />
          <label for="l-active">Рассылка активна</label>
        </div>
        <div class="dialog-actions">
          <Button type="button" label="Отмена" severity="secondary" outlined @click="editVisible = false" />
          <Button type="submit" :label="editing ? 'Сохранить' : 'Создать'" :loading="saving" />
        </div>
      </form>
    </Dialog>

    <Dialog v-model:visible="membersVisible" modal :header="`Участники: ${membersTarget?.address ?? ''}`" :style="{ width: '36rem' }">
      <div class="chips">
        <Chip v-for="m in membersTarget?.members ?? []" :key="m" :label="m" />
      </div>
    </Dialog>
  </div>
</template>
