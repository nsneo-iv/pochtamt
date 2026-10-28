<script setup lang="ts">
// Домены: таблица, диалог создания/редактирования, сведения (статистика) и DKIM-ключ
import { onMounted, reactive, ref } from 'vue'
import Button from 'primevue/button'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import InputNumber from 'primevue/inputnumber'
import ToggleSwitch from 'primevue/toggleswitch'
import Tag from 'primevue/tag'
import Message from 'primevue/message'
import * as api from '@/api/domains'
import type { Dkim, Domain, DomainDetail } from '@/api/types'
import { useNotify } from '@/composables/useNotify'
import { useAuthStore } from '@/stores/auth'
import { formatDateTime, formatMb, isDomainName } from '@/utils/format'
import { copyToClipboard } from '@/utils/clipboard'

const notify = useNotify()
const auth = useAuthStore()

const domains = ref<Domain[]>([])
const loading = ref(false)

async function load(): Promise<void> {
  loading.value = true
  try {
    domains.value = await api.listDomains()
  } catch (e) {
    notify.error(e, 'Не удалось загрузить домены')
  } finally {
    loading.value = false
  }
}

onMounted(load)

// ---- Создание / редактирование ----

const editVisible = ref(false)
const editing = ref<Domain | null>(null)
const saving = ref(false)
const form = reactive({
  name: '',
  description: '' as string,
  max_mailboxes: null as number | null,
  max_quota_mb: null as number | null,
  active: true,
})
const formError = ref<string | null>(null)

function openCreate(): void {
  editing.value = null
  form.name = ''
  form.description = ''
  form.max_mailboxes = null
  form.max_quota_mb = null
  form.active = true
  formError.value = null
  editVisible.value = true
}

function openEdit(domain: Domain): void {
  editing.value = domain
  form.name = domain.name
  form.description = domain.description ?? ''
  form.max_mailboxes = domain.max_mailboxes
  form.max_quota_mb = domain.max_quota_mb
  form.active = domain.active
  formError.value = null
  editVisible.value = true
}

async function save(): Promise<void> {
  const name = form.name.trim().toLowerCase()
  if (!editing.value && !isDomainName(name)) {
    formError.value = 'Укажите корректное имя домена, например example.ru'
    return
  }
  formError.value = null
  saving.value = true
  const payload = {
    description: form.description.trim() || null,
    max_mailboxes: form.max_mailboxes,
    max_quota_mb: form.max_quota_mb,
    active: form.active,
  }
  try {
    if (editing.value) {
      await api.updateDomain(editing.value.name, payload)
      notify.success(`Домен ${editing.value.name} обновлён`)
    } else {
      await api.createDomain({ name, ...payload })
      notify.success(`Домен ${name} создан`)
    }
    editVisible.value = false
    await load()
  } catch (e) {
    notify.error(e)
  } finally {
    saving.value = false
  }
}

function remove(domain: Domain): void {
  notify.confirmDelete(
    `Удалить домен ${domain.name}? Если в домене есть ящики, сервер откажет в удалении.`,
    async () => {
      try {
        await api.deleteDomain(domain.name)
        notify.success(`Домен ${domain.name} удалён`)
        await load()
      } catch (e) {
        notify.error(e)
      }
    },
  )
}

// ---- Сведения и DKIM ----

const detailVisible = ref(false)
const detail = ref<DomainDetail | null>(null)
const detailLoading = ref(false)
const dkim = ref<Dkim | null>(null)
const dkimLoaded = ref(false)
const dkimBusy = ref(false)
const selector = ref('mail')

async function openDetail(domain: Domain): Promise<void> {
  detail.value = null
  dkim.value = null
  dkimLoaded.value = false
  selector.value = 'mail'
  detailVisible.value = true
  detailLoading.value = true
  try {
    const [d, k] = await Promise.all([api.getDomain(domain.name), api.getDkim(domain.name)])
    detail.value = d
    dkim.value = k
    dkimLoaded.value = true
  } catch (e) {
    notify.error(e, 'Не удалось загрузить сведения о домене')
  } finally {
    detailLoading.value = false
  }
}

async function createKey(): Promise<void> {
  if (!detail.value) return
  dkimBusy.value = true
  try {
    dkim.value = await api.createDkim(detail.value.name, { selector: selector.value.trim() || 'mail' })
    notify.success('DKIM-ключ создан. Добавьте TXT-запись в DNS.')
  } catch (e) {
    notify.error(e)
  } finally {
    dkimBusy.value = false
  }
}

function deleteKey(): void {
  const name = detail.value?.name
  if (!name) return
  notify.confirmDelete(
    `Удалить DKIM-ключ домена ${name}? Исходящие письма перестанут подписываться.`,
    async () => {
      dkimBusy.value = true
      try {
        await api.deleteDkim(name)
        dkim.value = null
        notify.success('DKIM-ключ удалён')
      } catch (e) {
        notify.error(e)
      } finally {
        dkimBusy.value = false
      }
    },
  )
}

async function copy(text: string): Promise<void> {
  try {
    await copyToClipboard(text)
    notify.success('Скопировано в буфер обмена')
  } catch (e) {
    notify.error(e, 'Не удалось скопировать')
  }
}
</script>

<template>
  <div>
    <div class="toolbar">
      <h1 class="page-title" style="margin: 0">Домены</h1>
      <div class="toolbar__spacer" />
      <Button label="Обновить" icon="pi pi-refresh" severity="secondary" outlined :loading="loading" @click="load" />
      <Button v-if="auth.isSuperadmin" label="Создать домен" icon="pi pi-plus" @click="openCreate" />
    </div>

    <DataTable :value="domains" :loading="loading" data-key="name" striped-rows size="small" sort-field="name" :sort-order="1">
      <Column field="name" header="Домен" sortable>
        <template #body="{ data }">
          <RouterLink v-tooltip.top="'Открыть дашборд домена'" :to="{ name: 'domain-dashboard', params: { name: data.name } }">{{ data.name }}</RouterLink>
        </template>
      </Column>
      <Column field="description" header="Описание">
        <template #body="{ data }">{{ data.description || '—' }}</template>
      </Column>
      <Column field="max_mailboxes" header="Лимит ящиков">
        <template #body="{ data }">{{ data.max_mailboxes ?? 'без лимита' }}</template>
      </Column>
      <Column field="max_quota_mb" header="Лимит объёма">
        <template #body="{ data }">{{ data.max_quota_mb ? formatMb(data.max_quota_mb) : 'без лимита' }}</template>
      </Column>
      <Column field="active" header="Статус">
        <template #body="{ data }">
          <Tag :severity="data.active ? 'success' : 'secondary'" :value="data.active ? 'Активен' : 'Отключён'" />
        </template>
      </Column>
      <Column field="created_at" header="Создан" sortable>
        <template #body="{ data }">{{ formatDateTime(data.created_at) }}</template>
      </Column>
      <Column header="" style="width: 9rem">
        <template #body="{ data }">
          <div class="row-actions">
            <Button v-tooltip.top="'Сведения и DKIM'" icon="pi pi-key" text rounded severity="secondary" @click="openDetail(data)" />
            <Button v-tooltip.top="'Изменить'" icon="pi pi-pencil" text rounded severity="secondary" @click="openEdit(data)" />
            <Button
              v-if="auth.isSuperadmin"
              v-tooltip.top="'Удалить'"
              icon="pi pi-trash"
              text
              rounded
              severity="danger"
              @click="remove(data)"
            />
          </div>
        </template>
      </Column>
      <template #empty>Доменов пока нет</template>
    </DataTable>

    <!-- Диалог создания / редактирования -->
    <Dialog v-model:visible="editVisible" modal :header="editing ? `Домен ${editing.name}` : 'Новый домен'" :style="{ width: '30rem' }">
      <form class="form" @submit.prevent="save">
        <Message v-if="formError" severity="error" :closable="false">{{ formError }}</Message>
        <div class="form__field">
          <label for="d-name">Имя домена</label>
          <InputText id="d-name" v-model="form.name" :disabled="editing !== null" placeholder="example.ru" fluid />
        </div>
        <div class="form__field">
          <label for="d-desc">Описание</label>
          <InputText id="d-desc" v-model="form.description" fluid />
        </div>
        <div class="form__row">
          <div class="form__field">
            <label for="d-max">Лимит ящиков</label>
            <InputNumber id="d-max" v-model="form.max_mailboxes" :min="0" :use-grouping="false" placeholder="без лимита" fluid />
          </div>
          <div class="form__field">
            <label for="d-quota">Лимит объёма, МБ</label>
            <InputNumber id="d-quota" v-model="form.max_quota_mb" :min="0" :use-grouping="false" placeholder="без лимита" fluid />
          </div>
        </div>
        <div class="form__check">
          <ToggleSwitch v-model="form.active" input-id="d-active" />
          <label for="d-active">Домен активен</label>
        </div>
        <div class="dialog-actions">
          <Button type="button" label="Отмена" severity="secondary" outlined @click="editVisible = false" />
          <Button type="submit" :label="editing ? 'Сохранить' : 'Создать'" :loading="saving" />
        </div>
      </form>
    </Dialog>

    <!-- Сведения о домене и DKIM -->
    <Dialog v-model:visible="detailVisible" modal :header="detail ? `Домен ${detail.name}` : 'Домен'" :style="{ width: '44rem' }">
      <div v-if="detailLoading" class="muted"><i class="pi pi-spin pi-spinner" /> Загрузка…</div>
      <template v-else-if="detail">
        <div class="stat-grid" style="margin-bottom: 1.25rem">
          <div class="stat-card">
            <i class="pi pi-inbox stat-card__icon" />
            <div>
              <div class="stat-card__value">{{ detail.stats.mailboxes }}</div>
              <div class="stat-card__label">Ящиков</div>
            </div>
          </div>
          <div class="stat-card">
            <i class="pi pi-directions stat-card__icon" />
            <div>
              <div class="stat-card__value">{{ detail.stats.aliases }}</div>
              <div class="stat-card__label">Алиасов</div>
            </div>
          </div>
          <div class="stat-card">
            <i class="pi pi-database stat-card__icon" />
            <div>
              <div class="stat-card__value">{{ formatMb(detail.stats.used_mb) }}</div>
              <div class="stat-card__label">Занято</div>
            </div>
          </div>
        </div>

        <h3 style="margin: 0 0 0.75rem">DKIM</h3>
        <template v-if="dkim">
          <div class="dns-record">
            <div class="dns-record__label">Селектор</div>
            <div class="dns-record__value mono">{{ dkim.selector }}</div>
            <div />
            <div class="dns-record__label">Имя записи</div>
            <div class="dns-record__value mono">{{ dkim.dns_name }}</div>
            <Button v-tooltip.top="'Копировать'" icon="pi pi-copy" text rounded severity="secondary" @click="copy(dkim.dns_name)" />
            <div class="dns-record__label">TXT-значение</div>
            <div class="dns-record__value mono">{{ dkim.dns_value }}</div>
            <Button v-tooltip.top="'Копировать'" icon="pi pi-copy" text rounded severity="secondary" @click="copy(dkim.dns_value)" />
          </div>
          <p class="form__hint">Создан: {{ formatDateTime(dkim.created_at) }}. Добавьте TXT-запись в DNS домена, чтобы подпись проверялась.</p>
          <div class="dialog-actions">
            <Button label="Удалить ключ" icon="pi pi-trash" severity="danger" outlined :loading="dkimBusy" @click="deleteKey" />
          </div>
        </template>
        <template v-else-if="dkimLoaded">
          <p class="muted">DKIM-ключ для домена не создан.</p>
          <div class="form__row">
            <div class="form__field">
              <label for="dkim-selector">Селектор</label>
              <InputText id="dkim-selector" v-model="selector" placeholder="mail" fluid />
            </div>
            <div style="flex: 0 0 auto">
              <Button label="Создать ключ" icon="pi pi-key" :loading="dkimBusy" @click="createKey" />
            </div>
          </div>
        </template>
      </template>
    </Dialog>
  </div>
</template>
