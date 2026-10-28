<script setup lang="ts">
// Ящики: фильтр по домену и поиску, создание (auth local/ad), редактирование, смена пароля, квота, активность
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Button from 'primevue/button'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import InputNumber from 'primevue/inputnumber'
import Password from 'primevue/password'
import Select from 'primevue/select'
import SelectButton from 'primevue/selectbutton'
import ToggleSwitch from 'primevue/toggleswitch'
import ProgressBar from 'primevue/progressbar'
import Tag from 'primevue/tag'
import Message from 'primevue/message'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import * as api from '@/api/mailboxes'
import type { Mailbox, MailboxAuth } from '@/api/types'
import { useNotify } from '@/composables/useNotify'
import { useAuthStore } from '@/stores/auth'
import { useDomains } from '@/composables/useDomains'
import { useDomainQueryFilter } from '@/composables/useDomainQueryFilter'
import { formatDateTime, formatQuota, isLocalPart, quotaPercent } from '@/utils/format'

const notify = useNotify()
const { options: domainOptions } = useDomains()

const auth = useAuthStore()

/** Способы проверки пароля; Active Directory — только если он настроен на сервере */
const authOptions = computed<{ label: string; value: MailboxAuth }[]>(() => [
  { label: 'Локальный пароль', value: 'local' },
  ...(auth.adEnabled ? [{ label: 'Active Directory', value: 'ad' as MailboxAuth }] : []),
])

// ---- Список и фильтры ----

const mailboxes = ref<Mailbox[]>([])
const loading = ref(false)
// Фильтр по домену читается из ?domain= и пишется обратно в адрес страницы; поиск — из ?q= (ссылки с дашборда)
const filterDomain = useDomainQueryFilter()
const route = useRoute()
const router = useRouter()
const search = ref(typeof route.query.q === 'string' ? route.query.q : '')

async function load(): Promise<void> {
  loading.value = true
  try {
    mailboxes.value = await api.listMailboxes({ domain: filterDomain.value ?? undefined, q: search.value.trim() || undefined })
  } catch (e) {
    notify.error(e, 'Не удалось загрузить ящики')
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(filterDomain, load)

// Поиск с задержкой, чтобы не дёргать бэкенд на каждый символ
let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(search, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(load, 400)
})

// ---- Создание / редактирование ----

const editVisible = ref(false)
const editing = ref<Mailbox | null>(null)
const saving = ref(false)
const formError = ref<string | null>(null)
const form = reactive({
  local: '',
  domain: null as string | null,
  name: '',
  auth: 'local' as MailboxAuth,
  password: '',
  ad_upn: '',
  quota_mb: null as number | null,
  active: true,
})

const fullAddress = computed(() => (form.local && form.domain ? `${form.local.trim().toLowerCase()}@${form.domain}` : ''))

function openCreate(): void {
  editing.value = null
  form.local = ''
  form.domain = filterDomain.value ?? domainOptions.value[0]?.value ?? null
  form.name = ''
  form.auth = 'local'
  form.password = ''
  form.ad_upn = ''
  form.quota_mb = null
  form.active = true
  formError.value = null
  editVisible.value = true
}

function openEdit(mailbox: Mailbox): void {
  editing.value = mailbox
  const [local, domain] = mailbox.address.split('@')
  form.local = local ?? mailbox.address
  form.domain = domain ?? mailbox.domain
  form.name = mailbox.name
  form.auth = mailbox.auth
  form.password = ''
  form.ad_upn = mailbox.ad_upn ?? ''
  form.quota_mb = mailbox.quota_mb
  form.active = mailbox.active
  formError.value = null
  editVisible.value = true
}

function validate(): string | null {
  if (!editing.value) {
    if (!isLocalPart(form.local)) return 'Укажите имя ящика (часть адреса до @): латиница, цифры, точки, дефис'
    if (!form.domain) return 'Выберите домен'
    if (form.auth === 'local' && form.password.length < 8) return 'Пароль не короче 8 символов'
  }
  if (!form.name.trim()) return 'Укажите отображаемое имя'
  if (form.auth === 'ad' && !form.ad_upn.trim()) return 'Для авторизации через AD укажите UPN (user@corp.local)'
  return null
}

async function save(): Promise<void> {
  formError.value = validate()
  if (formError.value) return
  saving.value = true
  try {
    if (editing.value) {
      await api.updateMailbox(editing.value.address, {
        name: form.name.trim(),
        quota_mb: form.quota_mb,
        active: form.active,
        auth: form.auth,
        ad_upn: form.auth === 'ad' ? form.ad_upn.trim() : null,
      })
      notify.success(`Ящик ${editing.value.address} обновлён`)
    } else {
      await api.createMailbox({
        address: fullAddress.value,
        name: form.name.trim(),
        auth: form.auth,
        password: form.auth === 'local' ? form.password : undefined,
        ad_upn: form.auth === 'ad' ? form.ad_upn.trim() : undefined,
        quota_mb: form.quota_mb,
        active: form.active,
      })
      notify.success(`Ящик ${fullAddress.value} создан`)
    }
    editVisible.value = false
    await load()
  } catch (e) {
    notify.error(e)
  } finally {
    saving.value = false
  }
}

function remove(mailbox: Mailbox): void {
  notify.confirmDelete(`Удалить ящик ${mailbox.address} вместе с письмами?`, async () => {
    try {
      await api.deleteMailbox(mailbox.address)
      notify.success(`Ящик ${mailbox.address} удалён`)
      await load()
    } catch (e) {
      notify.error(e)
    }
  })
}

/** Быстрое включение/выключение ящика из таблицы */
async function toggleActive(mailbox: Mailbox, value: boolean): Promise<void> {
  try {
    await api.updateMailbox(mailbox.address, { active: value })
    mailbox.active = value
    notify.success(`Ящик ${mailbox.address} ${value ? 'включён' : 'отключён'}`)
  } catch (e) {
    notify.error(e)
  }
}

// ---- Смена пароля (только auth=local) ----

const passwordVisible = ref(false)
const passwordTarget = ref<Mailbox | null>(null)
const newPassword = ref('')
const newPassword2 = ref('')
const passwordError = ref<string | null>(null)
const passwordSaving = ref(false)

function openPassword(mailbox: Mailbox): void {
  passwordTarget.value = mailbox
  newPassword.value = ''
  newPassword2.value = ''
  passwordError.value = null
  passwordVisible.value = true
}

async function savePassword(): Promise<void> {
  if (!passwordTarget.value) return
  if (newPassword.value.length < 8) {
    passwordError.value = 'Пароль не короче 8 символов'
    return
  }
  if (newPassword.value !== newPassword2.value) {
    passwordError.value = 'Пароли не совпадают'
    return
  }
  passwordError.value = null
  passwordSaving.value = true
  try {
    await api.setMailboxPassword(passwordTarget.value.address, { password: newPassword.value })
    notify.success(`Пароль ящика ${passwordTarget.value.address} изменён`)
    passwordVisible.value = false
  } catch (e) {
    notify.error(e)
  } finally {
    passwordSaving.value = false
  }
}
</script>

<template>
  <div>
    <div class="toolbar">
      <h1 class="page-title" style="margin: 0">Ящики</h1>
      <div class="toolbar__spacer" />
      <Select v-model="filterDomain" :options="domainOptions" option-label="label" option-value="value" placeholder="Все домены" show-clear style="min-width: 14rem" />
      <IconField>
        <InputIcon class="pi pi-search" />
        <InputText v-model="search" placeholder="Поиск по адресу или имени" style="min-width: 16rem" />
      </IconField>
      <Button label="Обновить" icon="pi pi-refresh" severity="secondary" outlined :loading="loading" @click="load" />
      <Button label="Создать ящик" icon="pi pi-plus" @click="openCreate" />
    </div>

    <DataTable :value="mailboxes" :loading="loading" data-key="address" striped-rows size="small" paginator :rows="25" :rows-per-page-options="[25, 50, 100]" sort-field="address" :sort-order="1">
      <Column field="address" header="Адрес" sortable>
        <template #body="{ data }"><span class="mono">{{ data.address }}</span></template>
      </Column>
      <Column field="name" header="Имя" sortable />
      <Column field="auth" header="Авторизация">
        <template #body="{ data }">
          <Tag :severity="data.auth === 'ad' ? 'info' : 'secondary'" :value="data.auth === 'ad' ? 'AD' : 'Локальная'" />
          <div v-if="data.auth === 'ad' && data.ad_upn" class="form__hint mono">{{ data.ad_upn }}</div>
        </template>
      </Column>
      <Column field="used_mb" header="Квота" sortable style="min-width: 12rem">
        <template #body="{ data }">
          <div>{{ formatQuota(data.used_mb, data.quota_mb) }}</div>
          <ProgressBar v-if="quotaPercent(data.used_mb, data.quota_mb) !== null" :value="quotaPercent(data.used_mb, data.quota_mb) ?? 0" :show-value="false" style="height: 6px; margin-top: 4px" />
        </template>
      </Column>
      <Column field="active" header="Активен" style="width: 6rem">
        <template #body="{ data }">
          <ToggleSwitch :model-value="data.active" @update:model-value="toggleActive(data, $event)" />
        </template>
      </Column>
      <Column field="created_at" header="Создан" sortable>
        <template #body="{ data }">{{ formatDateTime(data.created_at) }}</template>
      </Column>
      <Column header="" style="width: 11rem">
        <template #body="{ data }">
          <div class="row-actions">
            <Button v-tooltip.top="'Изменить'" icon="pi pi-pencil" text rounded severity="secondary" @click="openEdit(data)" />
            <Button v-tooltip.top="'Настройки: режим, автоответ, пересылка, Sieve'" icon="pi pi-cog" text rounded severity="secondary" @click="router.push({ name: 'mailbox-settings', params: { address: data.address } })" />
            <Button v-if="data.auth === 'local'" v-tooltip.top="'Сменить пароль'" icon="pi pi-lock" text rounded severity="secondary" @click="openPassword(data)" />
            <Button v-tooltip.top="'Удалить'" icon="pi pi-trash" text rounded severity="danger" @click="remove(data)" />
          </div>
        </template>
      </Column>
      <template #empty>Ящиков не найдено</template>
    </DataTable>

    <!-- Создание / редактирование ящика -->
    <Dialog v-model:visible="editVisible" modal :header="editing ? `Ящик ${editing.address}` : 'Новый ящик'" :style="{ width: '32rem' }">
      <form class="form" @submit.prevent="save">
        <Message v-if="formError" severity="error" :closable="false">{{ formError }}</Message>
        <div class="form__row">
          <div class="form__field">
            <label for="m-local">Адрес</label>
            <InputText id="m-local" v-model="form.local" :disabled="editing !== null" placeholder="ivanov" fluid />
          </div>
          <div class="form__field">
            <label for="m-domain">Домен</label>
            <Select id="m-domain" v-model="form.domain" :options="domainOptions" option-label="label" option-value="value" :disabled="editing !== null" placeholder="Домен" fluid />
          </div>
        </div>
        <div class="form__field">
          <label for="m-name">Отображаемое имя</label>
          <InputText id="m-name" v-model="form.name" placeholder="Иванов Иван" fluid />
        </div>
        <div class="form__field">
          <label>Авторизация</label>
          <SelectButton v-model="form.auth" :options="authOptions" option-label="label" option-value="value" :allow-empty="false" />
        </div>
        <div v-if="form.auth === 'local' && !editing" class="form__field">
          <label for="m-password">Пароль</label>
          <Password id="m-password" v-model="form.password" toggle-mask :feedback="false" autocomplete="new-password" fluid />
          <span class="form__hint">Не короче 8 символов. Сменить потом можно кнопкой «Сменить пароль».</span>
        </div>
        <div v-if="form.auth === 'ad'" class="form__field">
          <label for="m-upn">UPN в Active Directory</label>
          <InputText id="m-upn" v-model="form.ad_upn" placeholder="user@corp.local" fluid />
          <span class="form__hint">Пароль проверяет Dovecot в AD; локальный пароль не используется.</span>
        </div>
        <div class="form__field">
          <label for="m-quota">Квота, МБ</label>
          <InputNumber id="m-quota" v-model="form.quota_mb" :min="0" :use-grouping="false" placeholder="без лимита" fluid />
        </div>
        <div class="form__check">
          <ToggleSwitch v-model="form.active" input-id="m-active" />
          <label for="m-active">Ящик активен</label>
        </div>
        <div class="dialog-actions">
          <Button type="button" label="Отмена" severity="secondary" outlined @click="editVisible = false" />
          <Button type="submit" :label="editing ? 'Сохранить' : 'Создать'" :loading="saving" />
        </div>
      </form>
    </Dialog>

    <!-- Смена пароля -->
    <Dialog v-model:visible="passwordVisible" modal :header="`Пароль: ${passwordTarget?.address ?? ''}`" :style="{ width: '26rem' }">
      <form class="form" @submit.prevent="savePassword">
        <Message v-if="passwordError" severity="error" :closable="false">{{ passwordError }}</Message>
        <div class="form__field">
          <label for="p-new">Новый пароль</label>
          <Password id="p-new" v-model="newPassword" toggle-mask :feedback="false" autocomplete="new-password" fluid />
        </div>
        <div class="form__field">
          <label for="p-new2">Повторите пароль</label>
          <Password id="p-new2" v-model="newPassword2" toggle-mask :feedback="false" autocomplete="new-password" fluid />
        </div>
        <div class="dialog-actions">
          <Button type="button" label="Отмена" severity="secondary" outlined @click="passwordVisible = false" />
          <Button type="submit" label="Сменить" :loading="passwordSaving" />
        </div>
      </form>
    </Dialog>
  </div>
</template>
