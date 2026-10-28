<script setup lang="ts">
// Вкладка «Доступ SMTP»: правила Postfix по клиенту, отправителю и получателю — проверяются до антиспама
import { onMounted, reactive, ref, watch } from 'vue'
import Button from 'primevue/button'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import ToggleSwitch from 'primevue/toggleswitch'
import Tag from 'primevue/tag'
import Message from 'primevue/message'
import * as api from '@/api/server'
import type { AccessRule, AccessRuleAction, AccessRuleKind } from '@/api/types'
import { useNotify } from '@/composables/useNotify'

const notify = useNotify()

const kindOptions: { value: AccessRuleKind; label: string; hint: string; placeholder: string }[] = [
  { value: 'client', label: 'Клиент (IP)', hint: 'IP-адрес (192.0.2.10) или префикс сети (192.0.2) подключающегося сервера', placeholder: '192.0.2' },
  { value: 'sender', label: 'Отправитель', hint: 'Адрес (user@example.com) или домен (example.com) из MAIL FROM', placeholder: 'spam.example.com' },
  { value: 'recipient', label: 'Получатель', hint: 'Адрес или домен из RCPT TO', placeholder: 'old@example.com' },
]

const actionOptions: { value: AccessRuleAction; label: string; hint: string }[] = [
  { value: 'OK', label: 'Разрешить', hint: 'Принять, минуя остальные ограничения Postfix' },
  { value: 'REJECT', label: 'Отклонить', hint: 'Отказать с сообщением отправителю' },
  { value: 'DISCARD', label: 'Отбросить', hint: 'Принять и молча удалить' },
]

function kindLabel(value: string): string {
  return kindOptions.find((o) => o.value === value)?.label ?? value
}

function kindHint(value: AccessRuleKind): string {
  return kindOptions.find((o) => o.value === value)?.hint ?? ''
}

function kindPlaceholder(value: AccessRuleKind): string {
  return kindOptions.find((o) => o.value === value)?.placeholder ?? ''
}

function actionLabel(value: string): string {
  return actionOptions.find((o) => o.value === value)?.label ?? value
}

function actionSeverity(value: string): 'success' | 'danger' | 'warn' {
  if (value === 'OK') return 'success'
  if (value === 'REJECT') return 'danger'
  return 'warn'
}

const items = ref<AccessRule[]>([])
const loading = ref(false)
const filterKind = ref<AccessRuleKind | null>(null)

async function load(): Promise<void> {
  loading.value = true
  try {
    items.value = await api.listAccessRules(filterKind.value ?? undefined)
  } catch (e) {
    notify.error(e, 'Не удалось загрузить правила')
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(filterKind, load)

// ---- Диалог ----

const dialogVisible = ref(false)
const editing = ref<AccessRule | null>(null)
const saving = ref(false)
const formError = ref<string | null>(null)
const form = reactive({
  kind: 'client' as AccessRuleKind,
  pattern: '',
  action: 'REJECT' as AccessRuleAction,
  message: '',
  comment: '',
  active: true,
})

function openCreate(): void {
  editing.value = null
  form.kind = filterKind.value ?? 'client'
  form.pattern = ''
  form.action = 'REJECT'
  form.message = ''
  form.comment = ''
  form.active = true
  formError.value = null
  dialogVisible.value = true
}

function openEdit(rule: AccessRule): void {
  editing.value = rule
  form.kind = rule.kind
  form.pattern = rule.pattern
  form.action = rule.action
  form.message = rule.message ?? ''
  form.comment = rule.comment ?? ''
  form.active = rule.active
  formError.value = null
  dialogVisible.value = true
}

async function save(): Promise<void> {
  const pattern = form.pattern.trim()
  if (!pattern) {
    formError.value = 'Укажите шаблон правила'
    return
  }
  formError.value = null
  saving.value = true
  const payload = {
    kind: form.kind,
    pattern,
    action: form.action,
    message: form.action === 'REJECT' ? form.message.trim() || null : null,
    comment: form.comment.trim() || null,
    active: form.active,
  }
  try {
    if (editing.value) {
      await api.updateAccessRule(editing.value.id, payload)
      notify.success('Правило обновлено')
    } else {
      await api.createAccessRule(payload)
      notify.success('Правило добавлено')
    }
    dialogVisible.value = false
    await load()
  } catch (e) {
    notify.error(e)
  } finally {
    saving.value = false
  }
}

function remove(rule: AccessRule): void {
  notify.confirmDelete(`Удалить правило «${rule.pattern}» (${kindLabel(rule.kind)}, ${actionLabel(rule.action)})?`, async () => {
    try {
      await api.deleteAccessRule(rule.id)
      notify.success('Правило удалено')
      await load()
    } catch (e) {
      notify.error(e)
    }
  })
}

async function toggleActive(rule: AccessRule, value: boolean): Promise<void> {
  try {
    await api.updateAccessRule(rule.id, { kind: rule.kind, pattern: rule.pattern, action: rule.action, message: rule.message, comment: rule.comment, active: value })
    rule.active = value
    notify.success(`Правило ${value ? 'включено' : 'отключено'}`)
  } catch (e) {
    notify.error(e)
  }
}
</script>

<template>
  <div>
    <div class="toolbar">
      <Select v-model="filterKind" :options="kindOptions" option-label="label" option-value="value" placeholder="Все типы" show-clear style="min-width: 12rem" />
      <div class="toolbar__spacer" />
      <Button label="Обновить" icon="pi pi-refresh" severity="secondary" outlined :loading="loading" @click="load" />
      <Button label="Добавить правило" icon="pi pi-plus" @click="openCreate" />
    </div>
    <Message severity="info" :closable="false" style="margin-bottom: 1rem">
      Правила проверяются Postfix на этапе SMTP-сессии — до антиспама и антивируса. Разрешённое (OK) письмо
      всё равно проходит Rspamd, отклонённое (REJECT) получает отказ сразу, отброшенное (DISCARD) принимается и удаляется.
    </Message>

    <DataTable :value="items" :loading="loading" data-key="id" striped-rows size="small">
      <Column field="kind" header="Тип" style="width: 10rem">
        <template #body="{ data }">{{ kindLabel(data.kind) }}</template>
      </Column>
      <Column field="pattern" header="Шаблон">
        <template #body="{ data }"><span class="mono">{{ data.pattern }}</span></template>
      </Column>
      <Column field="action" header="Действие" style="width: 9rem">
        <template #body="{ data }"><Tag :severity="actionSeverity(data.action)" :value="actionLabel(data.action)" /></template>
      </Column>
      <Column field="message" header="Сообщение отказа">
        <template #body="{ data }"><span class="muted">{{ data.message || '—' }}</span></template>
      </Column>
      <Column field="comment" header="Комментарий">
        <template #body="{ data }">{{ data.comment || '—' }}</template>
      </Column>
      <Column field="active" header="Активно" style="width: 6rem">
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
      <template #empty>Правил нет</template>
    </DataTable>

    <Dialog v-model:visible="dialogVisible" modal :header="editing ? 'Правило доступа' : 'Новое правило доступа'" :style="{ width: '32rem' }">
      <form class="form" @submit.prevent="save">
        <Message v-if="formError" severity="error" :closable="false">{{ formError }}</Message>
        <div class="form__field">
          <label for="ar-kind">Тип</label>
          <Select id="ar-kind" v-model="form.kind" :options="kindOptions" option-label="label" option-value="value" fluid />
        </div>
        <div class="form__field">
          <label for="ar-pattern">Шаблон</label>
          <InputText id="ar-pattern" v-model="form.pattern" :placeholder="kindPlaceholder(form.kind)" fluid />
          <span class="form__hint">{{ kindHint(form.kind) }}</span>
        </div>
        <div class="form__field">
          <label for="ar-action">Действие</label>
          <Select id="ar-action" v-model="form.action" :options="actionOptions" option-label="label" option-value="value" fluid>
            <template #option="{ option }">
              <div>
                <div>{{ option.label }} <span class="form__hint mono">{{ option.value }}</span></div>
                <div class="form__hint">{{ option.hint }}</div>
              </div>
            </template>
          </Select>
        </div>
        <div v-if="form.action === 'REJECT'" class="form__field">
          <label for="ar-message">Сообщение отправителю</label>
          <InputText id="ar-message" v-model="form.message" placeholder="Mail from this domain is not accepted" fluid />
          <span class="form__hint">Текст в SMTP-ответе отказа; лучше на английском — его увидит чужой сервер.</span>
        </div>
        <div class="form__field">
          <label for="ar-comment">Комментарий</label>
          <InputText id="ar-comment" v-model="form.comment" fluid />
        </div>
        <div class="form__check">
          <ToggleSwitch v-model="form.active" input-id="ar-active" />
          <label for="ar-active">Правило активно</label>
        </div>
        <div class="dialog-actions">
          <Button type="button" label="Отмена" severity="secondary" outlined @click="dialogVisible = false" />
          <Button type="submit" :label="editing ? 'Сохранить' : 'Добавить'" :loading="saving" />
        </div>
      </form>
    </Dialog>
  </div>
</template>
