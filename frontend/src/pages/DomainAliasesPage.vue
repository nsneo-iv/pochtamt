<script setup lang="ts">
// Доменные алиасы: почта на alias_domain доставляется в target_domain (только superadmin)
import { onMounted, reactive, ref } from 'vue'
import Button from 'primevue/button'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import Message from 'primevue/message'
import * as api from '@/api/domainAliases'
import type { DomainAlias } from '@/api/types'
import { useNotify } from '@/composables/useNotify'
import { useDomains } from '@/composables/useDomains'
import { isDomainName } from '@/utils/format'

const notify = useNotify()
const { options: domainOptions } = useDomains()

const items = ref<DomainAlias[]>([])
const loading = ref(false)

async function load(): Promise<void> {
  loading.value = true
  try {
    items.value = await api.listDomainAliases()
  } catch (e) {
    notify.error(e, 'Не удалось загрузить доменные алиасы')
  } finally {
    loading.value = false
  }
}

onMounted(load)

const createVisible = ref(false)
const saving = ref(false)
const formError = ref<string | null>(null)
const form = reactive({
  alias_domain: '',
  target_domain: null as string | null,
})

function openCreate(): void {
  form.alias_domain = ''
  form.target_domain = domainOptions.value[0]?.value ?? null
  formError.value = null
  createVisible.value = true
}

async function save(): Promise<void> {
  const aliasDomain = form.alias_domain.trim().toLowerCase()
  if (!isDomainName(aliasDomain)) {
    formError.value = 'Укажите корректное имя домена-алиаса'
    return
  }
  if (!form.target_domain) {
    formError.value = 'Выберите целевой домен'
    return
  }
  if (aliasDomain === form.target_domain) {
    formError.value = 'Домен-алиас и целевой домен совпадают'
    return
  }
  formError.value = null
  saving.value = true
  try {
    await api.createDomainAlias({ alias_domain: aliasDomain, target_domain: form.target_domain })
    notify.success(`Доменный алиас ${aliasDomain} → ${form.target_domain} создан`)
    createVisible.value = false
    await load()
  } catch (e) {
    notify.error(e)
  } finally {
    saving.value = false
  }
}

function remove(item: DomainAlias): void {
  notify.confirmDelete(`Удалить доменный алиас ${item.alias_domain} → ${item.target_domain}?`, async () => {
    try {
      await api.deleteDomainAlias(item.alias_domain)
      notify.success(`Доменный алиас ${item.alias_domain} удалён`)
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
      <h1 class="page-title" style="margin: 0">Доменные алиасы</h1>
      <div class="toolbar__spacer" />
      <Button label="Обновить" icon="pi pi-refresh" severity="secondary" outlined :loading="loading" @click="load" />
      <Button label="Создать" icon="pi pi-plus" @click="openCreate" />
    </div>
    <p class="muted" style="margin-top: 0">Вся почта на адреса домена-алиаса доставляется в одноимённые ящики целевого домена.</p>

    <DataTable :value="items" :loading="loading" data-key="alias_domain" striped-rows size="small" sort-field="alias_domain" :sort-order="1">
      <Column field="alias_domain" header="Домен-алиас" sortable>
        <template #body="{ data }"><span class="mono">{{ data.alias_domain }}</span></template>
      </Column>
      <Column field="target_domain" header="Целевой домен" sortable>
        <template #body="{ data }"><span class="mono">{{ data.target_domain }}</span></template>
      </Column>
      <Column field="active" header="Статус">
        <template #body="{ data }">
          <Tag :severity="data.active ? 'success' : 'secondary'" :value="data.active ? 'Активен' : 'Отключён'" />
        </template>
      </Column>
      <Column header="" style="width: 5rem">
        <template #body="{ data }">
          <div class="row-actions">
            <Button v-tooltip.top="'Удалить'" icon="pi pi-trash" text rounded severity="danger" @click="remove(data)" />
          </div>
        </template>
      </Column>
      <template #empty>Доменных алиасов нет</template>
    </DataTable>

    <Dialog v-model:visible="createVisible" modal header="Новый доменный алиас" :style="{ width: '28rem' }">
      <form class="form" @submit.prevent="save">
        <Message v-if="formError" severity="error" :closable="false">{{ formError }}</Message>
        <div class="form__field">
          <label for="da-alias">Домен-алиас</label>
          <InputText id="da-alias" v-model="form.alias_domain" placeholder="example.com" fluid />
        </div>
        <div class="form__field">
          <label for="da-target">Целевой домен</label>
          <Select id="da-target" v-model="form.target_domain" :options="domainOptions" option-label="label" option-value="value" placeholder="Домен" fluid />
        </div>
        <div class="dialog-actions">
          <Button type="button" label="Отмена" severity="secondary" outlined @click="createVisible = false" />
          <Button type="submit" label="Создать" :loading="saving" />
        </div>
      </form>
    </Dialog>
  </div>
</template>
