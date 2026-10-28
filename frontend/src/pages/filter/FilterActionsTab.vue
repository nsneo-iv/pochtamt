<script setup lang="ts">
// Вкладка «Пороги»: три порога баллов Rspamd, проверка возрастания на клиенте
import { computed, onMounted, reactive, ref } from 'vue'
import Button from 'primevue/button'
import InputNumber from 'primevue/inputnumber'
import Message from 'primevue/message'
import * as api from '@/api/filter'
import type { FilterActions } from '@/api/types'
import { useNotify } from '@/composables/useNotify'

const notify = useNotify()

const loading = ref(false)
const saving = ref(false)
const form = reactive<{ greylist: number | null; add_header: number | null; reject: number | null }>({
  greylist: null,
  add_header: null,
  reject: null,
})
/** Значения с сервера — ref, чтобы computed dirty пересчитывался после загрузки */
const original = ref<FilterActions | null>(null)

const fields: { key: keyof FilterActions; label: string; hint: string }[] = [
  { key: 'greylist', label: 'Greylist', hint: 'Письма с баллом ниже этого порога проходят без задержки. От этого балла отправитель получает временный отказ и должен повторить попытку (greylisting).' },
  { key: 'add_header', label: 'Пометить спамом', hint: 'От этого балла письмо помечается как спам и попадает в папку Junk получателя.' },
  { key: 'reject', label: 'Отклонить', hint: 'От этого балла письмо отклоняется на этапе SMTP — отправитель получает отказ.' },
]

/** Ошибка проверки формы: все поля заполнены и пороги возрастают */
const validationError = computed<string | null>(() => {
  const { greylist, add_header, reject } = form
  if (greylist === null || add_header === null || reject === null) return 'Заполните все три порога'
  if (!(greylist < add_header)) return 'Порог «Пометить спамом» должен быть больше порога Greylist'
  if (!(add_header < reject)) return 'Порог «Отклонить» должен быть больше порога «Пометить спамом»'
  return null
})

const dirty = computed(() => {
  const o = original.value
  if (!o) return false
  return form.greylist !== o.greylist || form.add_header !== o.add_header || form.reject !== o.reject
})

function apply(actions: FilterActions): void {
  original.value = { ...actions }
  form.greylist = actions.greylist
  form.add_header = actions.add_header
  form.reject = actions.reject
}

async function load(): Promise<void> {
  loading.value = true
  try {
    apply(await api.getFilterActions())
  } catch (e) {
    notify.error(e, 'Не удалось загрузить пороги')
  } finally {
    loading.value = false
  }
}

async function save(): Promise<void> {
  if (validationError.value || form.greylist === null || form.add_header === null || form.reject === null) return
  saving.value = true
  try {
    apply(await api.updateFilterActions({ greylist: form.greylist, add_header: form.add_header, reject: form.reject }))
    notify.success('Пороги сохранены')
  } catch (e) {
    notify.error(e)
  } finally {
    saving.value = false
  }
}

function reset(): void {
  if (original.value) apply(original.value)
}

onMounted(load)
</script>

<template>
  <div class="card" style="max-width: 640px">
    <h2 class="card__title"><i class="pi pi-sliders-h" /> Пороги баллов</h2>
    <p class="muted" style="margin-top: 0">
      Rspamd суммирует баллы сработавших символов и сравнивает с порогами. Пороги должны возрастать:
      Greylist &lt; Пометить спамом &lt; Отклонить.
    </p>
    <form class="form" @submit.prevent="save">
      <div v-for="field in fields" :key="field.key" class="form__field">
        <label :for="`act-${field.key}`">{{ field.label }}</label>
        <InputNumber
          :id="`act-${field.key}`"
          v-model="form[field.key]"
          :min-fraction-digits="0"
          :max-fraction-digits="2"
          :step="0.5"
          show-buttons
          :disabled="loading"
          fluid
        />
        <span class="form__hint">{{ field.hint }}</span>
      </div>
      <Message v-if="dirty && validationError" severity="error" :closable="false">{{ validationError }}</Message>
      <div class="dialog-actions">
        <Button type="button" label="Сбросить" severity="secondary" outlined :disabled="!dirty" @click="reset" />
        <Button type="submit" label="Сохранить" icon="pi pi-save" :loading="saving" :disabled="!dirty || validationError !== null" />
      </div>
    </form>
  </div>
</template>
