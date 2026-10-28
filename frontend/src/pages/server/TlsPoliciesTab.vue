<script setup lang="ts">
// Вкладка «TLS к получателям»: политики TLS Postfix по доменам получателей
import { onMounted, reactive, ref } from 'vue'
import Button from 'primevue/button'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import Message from 'primevue/message'
import * as api from '@/api/server'
import type { TlsPolicy, TlsPolicyName } from '@/api/types'
import { useNotify } from '@/composables/useNotify'
import { formatDateTime, isDomainName } from '@/utils/format'

const notify = useNotify()

const policyOptions: { value: TlsPolicyName; label: string; hint: string }[] = [
  { value: 'none', label: 'Без TLS', hint: 'Отправлять открытым текстом' },
  { value: 'may', label: 'Если возможно', hint: 'TLS при поддержке получателем, иначе без шифрования (по умолчанию)' },
  { value: 'encrypt', label: 'Обязательно', hint: 'Только по TLS, сертификат не проверяется' },
  { value: 'dane', label: 'DANE', hint: 'Проверка по TLSA-записям DNS, если они есть' },
  { value: 'dane-only', label: 'Только DANE', hint: 'Требовать TLSA-записи, иначе не отправлять' },
  { value: 'verify', label: 'С проверкой сертификата', hint: 'TLS и доверенный сертификат получателя' },
  { value: 'secure', label: 'Строгая проверка', hint: 'TLS, доверенный сертификат и совпадение имени' },
]

function policyLabel(value: string): string {
  return policyOptions.find((o) => o.value === value)?.label ?? value
}

function policySeverity(value: string): 'success' | 'info' | 'warn' | 'secondary' {
  if (value === 'none') return 'warn'
  if (value === 'may') return 'secondary'
  if (value === 'encrypt' || value === 'dane') return 'info'
  return 'success'
}

const items = ref<TlsPolicy[]>([])
const loading = ref(false)

async function load(): Promise<void> {
  loading.value = true
  try {
    items.value = await api.listTlsPolicies()
  } catch (e) {
    notify.error(e, 'Не удалось загрузить TLS-политики')
  } finally {
    loading.value = false
  }
}

onMounted(load)

// ---- Диалог ----

const dialogVisible = ref(false)
const editing = ref<TlsPolicy | null>(null)
const saving = ref(false)
const formError = ref<string | null>(null)
const form = reactive({
  domain: '',
  policy: 'encrypt' as TlsPolicyName,
  params: '',
  comment: '',
})

function openCreate(): void {
  editing.value = null
  form.domain = ''
  form.policy = 'encrypt'
  form.params = ''
  form.comment = ''
  formError.value = null
  dialogVisible.value = true
}

function openEdit(item: TlsPolicy): void {
  editing.value = item
  form.domain = item.domain
  form.policy = item.policy
  form.params = item.params ?? ''
  form.comment = item.comment ?? ''
  formError.value = null
  dialogVisible.value = true
}

async function save(): Promise<void> {
  const domain = form.domain.trim().toLowerCase()
  if (!editing.value && !isDomainName(domain.replace(/^\./, ''))) {
    formError.value = 'Укажите домен получателя, например example.com или .example.com (с поддоменами)'
    return
  }
  formError.value = null
  saving.value = true
  try {
    await api.putTlsPolicy({ domain, policy: form.policy, params: form.params.trim() || null, comment: form.comment.trim() || null })
    notify.success(`TLS-политика для ${domain} сохранена`)
    dialogVisible.value = false
    await load()
  } catch (e) {
    notify.error(e)
  } finally {
    saving.value = false
  }
}

function remove(item: TlsPolicy): void {
  notify.confirmDelete(`Удалить TLS-политику для ${item.domain}? Для домена будет действовать политика по умолчанию.`, async () => {
    try {
      await api.deleteTlsPolicy(item.domain)
      notify.success(`TLS-политика для ${item.domain} удалена`)
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
      <p class="muted" style="margin: 0">Требования к шифрованию при отправке писем в указанные домены (smtp_tls_policy_maps Postfix).</p>
      <div class="toolbar__spacer" />
      <Button label="Обновить" icon="pi pi-refresh" severity="secondary" outlined :loading="loading" @click="load" />
      <Button label="Добавить" icon="pi pi-plus" @click="openCreate" />
    </div>

    <DataTable :value="items" :loading="loading" data-key="domain" striped-rows size="small" sort-field="domain" :sort-order="1">
      <Column field="domain" header="Домен получателя" sortable>
        <template #body="{ data }"><span class="mono">{{ data.domain }}</span></template>
      </Column>
      <Column field="policy" header="Политика" sortable>
        <template #body="{ data }"><Tag :severity="policySeverity(data.policy)" :value="policyLabel(data.policy)" /> <span class="form__hint mono">{{ data.policy }}</span></template>
      </Column>
      <Column field="params" header="Параметры">
        <template #body="{ data }"><span class="mono">{{ data.params || '—' }}</span></template>
      </Column>
      <Column field="comment" header="Комментарий">
        <template #body="{ data }">{{ data.comment || '—' }}</template>
      </Column>
      <Column field="updated_at" header="Изменено" sortable>
        <template #body="{ data }">{{ formatDateTime(data.updated_at) }}</template>
      </Column>
      <Column header="" style="width: 7rem">
        <template #body="{ data }">
          <div class="row-actions">
            <Button v-tooltip.top="'Изменить'" icon="pi pi-pencil" text rounded severity="secondary" @click="openEdit(data)" />
            <Button v-tooltip.top="'Удалить'" icon="pi pi-trash" text rounded severity="danger" @click="remove(data)" />
          </div>
        </template>
      </Column>
      <template #empty>Политик нет — ко всем получателям применяется политика по умолчанию</template>
    </DataTable>

    <Dialog v-model:visible="dialogVisible" modal :header="editing ? `TLS-политика: ${editing.domain}` : 'Новая TLS-политика'" :style="{ width: '32rem' }">
      <form class="form" @submit.prevent="save">
        <Message v-if="formError" severity="error" :closable="false">{{ formError }}</Message>
        <div class="form__field">
          <label for="tls-domain">Домен получателя</label>
          <InputText id="tls-domain" v-model="form.domain" :disabled="editing !== null" placeholder="example.com" fluid />
          <span class="form__hint">Точка в начале (.example.com) — вместе с поддоменами.</span>
        </div>
        <div class="form__field">
          <label for="tls-policy">Политика</label>
          <Select id="tls-policy" v-model="form.policy" :options="policyOptions" option-label="label" option-value="value" fluid>
            <template #option="{ option }">
              <div>
                <div>{{ option.label }} <span class="form__hint mono">{{ option.value }}</span></div>
                <div class="form__hint">{{ option.hint }}</div>
              </div>
            </template>
          </Select>
        </div>
        <div class="form__field">
          <label for="tls-params">Дополнительные параметры</label>
          <InputText id="tls-params" v-model="form.params" placeholder="match=.example.com" fluid />
          <span class="form__hint">Параметры Postfix через пробел, например <span class="mono">match=.example.com ciphers=high</span>.</span>
        </div>
        <div class="form__field">
          <label for="tls-comment">Комментарий</label>
          <InputText id="tls-comment" v-model="form.comment" fluid />
        </div>
        <div class="dialog-actions">
          <Button type="button" label="Отмена" severity="secondary" outlined @click="dialogVisible = false" />
          <Button type="submit" :label="editing ? 'Сохранить' : 'Добавить'" :loading="saving" />
        </div>
      </form>
    </Dialog>
  </div>
</template>
