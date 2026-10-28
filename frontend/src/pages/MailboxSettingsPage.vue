<script setup lang="ts">
// Настройки ящика в админке: режим, автоответ, пересылка, BCC, правила Sieve.
// В PUT уходят только изменённые секции; 422 по Sieve показываем под полем правил.
import { computed, ref, watch } from 'vue'
import Button from 'primevue/button'
import Select from 'primevue/select'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Skeleton from 'primevue/skeleton'
import * as api from '@/api/mailboxes'
import { ApiError } from '@/api/client'
import type { MailboxSettings, MailboxSettingsUpdate } from '@/api/types'
import { useNotify } from '@/composables/useNotify'
import { changedKeys } from '@/utils/diff'
import { formatDateTime, isEmail } from '@/utils/format'
import { mailboxModeHint, mailboxModeOptions } from '@/utils/mailboxMode'
import AutoreplyForm from '@/components/settings/AutoreplyForm.vue'
import ForwardForm from '@/components/settings/ForwardForm.vue'
import SieveForm from '@/components/settings/SieveForm.vue'

const props = defineProps<{ address: string }>()

const notify = useNotify()

const original = ref<MailboxSettings | null>(null)
const form = ref<MailboxSettings | null>(null)
const loading = ref(false)
const saving = ref(false)
const sieveError = ref<string | null>(null)

const SECTIONS = ['mode', 'autoreply', 'forward', 'sieve_custom', 'bcc_address'] as const

const changes = computed<MailboxSettingsUpdate>(() =>
  original.value && form.value ? changedKeys(original.value, form.value, SECTIONS) : {},
)
const dirty = computed(() => Object.keys(changes.value).length > 0)
const domain = computed(() => props.address.split('@')[1] ?? '')

const bcc = computed({
  get: () => form.value?.bcc_address ?? '',
  set: (v: string) => {
    if (form.value) form.value.bcc_address = v.trim() || null
  },
})

/** Глубокая копия, чтобы правки формы не трогали оригинал */
function clone(settings: MailboxSettings): MailboxSettings {
  return JSON.parse(JSON.stringify(settings)) as MailboxSettings
}

async function load(): Promise<void> {
  loading.value = true
  sieveError.value = null
  try {
    const settings = await api.getMailboxSettings(props.address)
    original.value = settings
    form.value = clone(settings)
  } catch (e) {
    notify.error(e, 'Не удалось загрузить настройки ящика')
  } finally {
    loading.value = false
  }
}

async function save(): Promise<void> {
  if (!form.value || !dirty.value) return
  const bad = form.value.forward.targets.find((t) => !isEmail(t))
  if (bad) {
    notify.error(new Error(`Некорректный адрес пересылки: ${bad}`))
    return
  }
  if (form.value.bcc_address && !isEmail(form.value.bcc_address)) {
    notify.error(new Error('Некорректный адрес для скрытой копии'))
    return
  }
  saving.value = true
  sieveError.value = null
  const payload = changes.value
  try {
    const saved = await api.updateMailboxSettings(props.address, payload)
    original.value = saved
    form.value = clone(saved)
    if (saved.sieve_error) notify.info('Настройки сохранены, но скрипт Sieve не применён', 'Внимание')
    else notify.success('Настройки ящика сохранены')
  } catch (e) {
    // 422 при изменённых правилах — ошибка проверки Sieve, показываем под полем
    if (e instanceof ApiError && e.status === 422 && 'sieve_custom' in payload) sieveError.value = e.message
    else notify.error(e)
  } finally {
    saving.value = false
  }
}

function reset(): void {
  if (original.value) form.value = clone(original.value)
  sieveError.value = null
}

watch(() => props.address, load, { immediate: true })
</script>

<template>
  <div>
    <div class="toolbar">
      <h1 class="page-title" style="margin: 0">Настройки ящика <span class="mono" style="font-size: 1.2rem">{{ props.address }}</span></h1>
      <div class="toolbar__spacer" />
      <RouterLink :to="{ name: 'mailboxes', query: { domain } }">
        <Button label="К списку ящиков" icon="pi pi-arrow-left" severity="secondary" outlined />
      </RouterLink>
      <Button label="Отменить" severity="secondary" outlined :disabled="!dirty" @click="reset" />
      <Button label="Сохранить" icon="pi pi-save" :loading="saving" :disabled="!dirty" @click="save" />
    </div>

    <Message v-if="original?.sieve_error" severity="warn" :closable="false" style="margin-bottom: 1rem">
      Настройки сохранены, но скрипт не применён: {{ original.sieve_error }}
    </Message>

    <div v-if="loading || !form" class="dash-grid" style="margin-top: 0">
      <div v-for="i in 4" :key="i" class="card skeleton-block">
        <Skeleton width="40%" height="1.2rem" />
        <Skeleton v-for="j in 3" :key="j" height="2.2rem" />
      </div>
    </div>

    <div v-else class="dash-grid" style="margin-top: 0">
      <!-- Режим и BCC -->
      <div class="card">
        <h2 class="card__title"><i class="pi pi-sliders-h" /> Режим работы</h2>
        <div class="form">
          <div class="form__field">
            <label for="ms-mode">Режим</label>
            <Select id="ms-mode" v-model="form.mode" :options="mailboxModeOptions" option-label="label" option-value="value" fluid>
              <template #option="{ option }">
                <div>
                  <div>{{ option.label }}</div>
                  <div class="form__hint">{{ option.hint }}</div>
                </div>
              </template>
            </Select>
            <span class="form__hint">{{ mailboxModeHint(form.mode) }}</span>
          </div>
          <div class="form__field">
            <label for="ms-bcc">Скрытая копия (BCC)</label>
            <InputText id="ms-bcc" v-model="bcc" placeholder="archive@example.com" fluid />
            <span class="form__hint">Копия всех писем ящика на указанный адрес. Пусто — не копировать.</span>
          </div>
        </div>
      </div>

      <!-- Автоответ -->
      <div class="card">
        <h2 class="card__title"><i class="pi pi-reply" /> Автоответ</h2>
        <AutoreplyForm v-model="form.autoreply" />
      </div>

      <!-- Пересылка -->
      <div class="card">
        <h2 class="card__title"><i class="pi pi-send" /> Пересылка</h2>
        <ForwardForm v-model="form.forward" />
      </div>

      <!-- Sieve -->
      <div class="card">
        <h2 class="card__title">
          <i class="pi pi-code" /> Пользовательские правила Sieve
          <span class="toolbar__spacer" />
          <span v-if="original?.sieve_synced_at" class="form__hint">применён {{ formatDateTime(original.sieve_synced_at) }}</span>
        </h2>
        <SieveForm v-model="form.sieve_custom" :error="sieveError" />
      </div>
    </div>
  </div>
</template>
