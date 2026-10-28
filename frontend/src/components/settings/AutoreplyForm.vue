<script setup lang="ts">
// Форма автоответа: общая для админских настроек ящика и личного кабинета.
// Работает через v-model: каждое изменение поля отдаёт новый объект Autoreply.
import { computed } from 'vue'
import ToggleSwitch from 'primevue/toggleswitch'
import InputText from 'primevue/inputtext'
import Textarea from 'primevue/textarea'
import DatePicker from 'primevue/datepicker'
import type { Autoreply } from '@/api/types'

const props = defineProps<{ modelValue: Autoreply; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: Autoreply] }>()

function patch(changes: Partial<Autoreply>): void {
  emit('update:modelValue', { ...props.modelValue, ...changes })
}

/** YYYY-MM-DD → Date (локальная полночь) */
function parseDate(value: string | null): Date | null {
  if (!value) return null
  const [y, m, d] = value.split('-').map(Number)
  if (!y || !m || !d) return null
  return new Date(y, m - 1, d)
}

/** Date → YYYY-MM-DD */
function formatDate(value: Date | null | undefined): string | null {
  if (!value) return null
  const mm = String(value.getMonth() + 1).padStart(2, '0')
  const dd = String(value.getDate()).padStart(2, '0')
  return `${value.getFullYear()}-${mm}-${dd}`
}

const enabled = computed({ get: () => props.modelValue.enabled, set: (v: boolean) => patch({ enabled: v }) })
const subject = computed({ get: () => props.modelValue.subject ?? '', set: (v: string) => patch({ subject: v || null }) })
const body = computed({ get: () => props.modelValue.body ?? '', set: (v: string) => patch({ body: v || null }) })
const dateFrom = computed({
  get: () => parseDate(props.modelValue.date_from),
  set: (v: Date | null) => patch({ date_from: formatDate(v) }),
})
const dateTo = computed({
  get: () => parseDate(props.modelValue.date_to),
  set: (v: Date | null) => patch({ date_to: formatDate(v) }),
})
</script>

<template>
  <div class="form">
    <div class="form__check">
      <ToggleSwitch v-model="enabled" input-id="ar-enabled" :disabled="disabled" />
      <label for="ar-enabled">Автоответ включён</label>
    </div>
    <div class="form__field">
      <label for="ar-subject">Тема ответа</label>
      <InputText id="ar-subject" v-model="subject" placeholder="Я в отпуске" :disabled="disabled" fluid />
    </div>
    <div class="form__field">
      <label for="ar-body">Текст ответа</label>
      <Textarea id="ar-body" v-model="body" rows="5" auto-resize :disabled="disabled" fluid />
    </div>
    <div class="form__row">
      <div class="form__field">
        <label for="ar-from">Действует с</label>
        <DatePicker v-model="dateFrom" input-id="ar-from" date-format="dd.mm.yy" show-icon show-button-bar :disabled="disabled" fluid />
      </div>
      <div class="form__field">
        <label for="ar-to">Действует по</label>
        <DatePicker v-model="dateTo" input-id="ar-to" date-format="dd.mm.yy" show-icon show-button-bar :disabled="disabled" fluid />
      </div>
    </div>
    <span class="form__hint">Даты можно не указывать — тогда автоответ действует, пока включён.</span>
  </div>
</template>
