<script setup lang="ts">
import { WEBMAIL_URL } from '@/brand'
// Личный кабинет: карточка ящика, смена пароля (только local), автоответ, пересылка, правила Sieve.
// Используются только эндпоинты /me/*; в PUT уходят только изменённые секции.
import { computed, onMounted, ref } from 'vue'
import Button from 'primevue/button'
import Password from 'primevue/password'
import ProgressBar from 'primevue/progressbar'
import Message from 'primevue/message'
import Skeleton from 'primevue/skeleton'
import Tag from 'primevue/tag'
import * as api from '@/api/me'
import { ApiError } from '@/api/client'
import type { MailboxSettings, MeSettingsUpdate } from '@/api/types'
import { useMeStore } from '@/stores/me'
import { useNotify } from '@/composables/useNotify'
import { changedKeys } from '@/utils/diff'
import { formatDateTime, formatMb, formatNumber, formatQuota, isEmail, quotaPercent } from '@/utils/format'
import { mailboxModeHint, mailboxModeLabel } from '@/utils/mailboxMode'
import AutoreplyForm from '@/components/settings/AutoreplyForm.vue'
import ForwardForm from '@/components/settings/ForwardForm.vue'
import SieveForm from '@/components/settings/SieveForm.vue'

const meStore = useMeStore()
const notify = useNotify()

const original = ref<MailboxSettings | null>(null)
const form = ref<MailboxSettings | null>(null)
const loading = ref(false)
const saving = ref(false)
const sieveError = ref<string | null>(null)

const SECTIONS = ['autoreply', 'forward', 'sieve_custom'] as const

const changes = computed<MeSettingsUpdate>(() =>
  original.value && form.value ? changedKeys(original.value, form.value, SECTIONS) : {},
)
const dirty = computed(() => Object.keys(changes.value).length > 0)
const me = computed(() => meStore.me)
const percent = computed(() => (me.value ? quotaPercent(me.value.used_mb, me.value.quota_mb) : null))

function clone(settings: MailboxSettings): MailboxSettings {
  return JSON.parse(JSON.stringify(settings)) as MailboxSettings
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const [, settings] = await Promise.all([meStore.fetchMe(), api.getMeSettings()])
    original.value = settings
    form.value = clone(settings)
  } catch (e) {
    notify.error(e, 'Не удалось загрузить настройки')
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
  saving.value = true
  sieveError.value = null
  const payload = changes.value
  try {
    const saved = await api.updateMeSettings(payload)
    original.value = saved
    form.value = clone(saved)
    if (saved.sieve_error) notify.info('Настройки сохранены, но скрипт не применён', 'Внимание')
    else notify.success('Настройки сохранены')
  } catch (e) {
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

// ---- Смена пароля (только auth=local) ----

const currentPassword = ref('')
const newPassword = ref('')
const newPassword2 = ref('')
const passwordError = ref<string | null>(null)
const passwordSaving = ref(false)

async function changePassword(): Promise<void> {
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
    await api.setMePassword(currentPassword.value, newPassword.value)
    currentPassword.value = ''
    newPassword.value = ''
    newPassword2.value = ''
    notify.success('Пароль изменён')
  } catch (e) {
    notify.error(e)
  } finally {
    passwordSaving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="toolbar">
      <h1 class="page-title" style="margin: 0">Мой ящик</h1>
      <div class="toolbar__spacer" />
      <a v-if="WEBMAIL_URL" :href="WEBMAIL_URL" target="_blank" rel="noopener">Веб-почта <i class="pi pi-external-link" style="font-size: 0.75rem" /></a>
      <Button label="Отменить" severity="secondary" outlined :disabled="!dirty" @click="reset" />
      <Button label="Сохранить" icon="pi pi-save" :loading="saving" :disabled="!dirty" @click="save" />
    </div>

    <Message v-if="original?.sieve_error" severity="warn" :closable="false" style="margin-bottom: 1rem">
      Настройки сохранены, но скрипт не применён: {{ original.sieve_error }}
    </Message>

    <div v-if="loading || !form || !me" class="dash-grid" style="margin-top: 0">
      <div v-for="i in 4" :key="i" class="card skeleton-block">
        <Skeleton width="40%" height="1.2rem" />
        <Skeleton v-for="j in 3" :key="j" height="2.2rem" />
      </div>
    </div>

    <div v-else class="dash-grid" style="margin-top: 0">
      <!-- Карточка ящика -->
      <div class="card">
        <h2 class="card__title"><i class="pi pi-inbox" /> {{ me.address }}</h2>
        <div class="kv">
          <span>Имя</span><strong>{{ me.name || '—' }}</strong>
          <span>Занято</span>
          <strong>
            {{ formatQuota(me.used_mb, me.quota_mb) }}
            <ProgressBar v-if="percent !== null" :value="percent" :show-value="false" style="height: 6px; margin-top: 4px" />
          </strong>
          <span>Писем</span><strong>{{ formatNumber(me.messages) }}</strong>
          <span>Режим</span>
          <strong>
            <Tag :value="mailboxModeLabel(me.mode)" :severity="me.mode === 'normal' ? 'success' : 'warn'" />
            <div class="form__hint">{{ mailboxModeHint(me.mode) }}</div>
          </strong>
          <span>Авторизация</span><strong>{{ me.auth === 'ad' ? 'Active Directory' : 'Локальный пароль' }}</strong>
        </div>
        <p v-if="me.quota_mb" class="form__hint">Квота {{ formatMb(me.quota_mb) }}. При заполнении новые письма перестанут приниматься.</p>
      </div>

      <!-- Пароль -->
      <div class="card">
        <h2 class="card__title"><i class="pi pi-lock" /> Пароль</h2>
        <form v-if="me.auth === 'local'" class="form" @submit.prevent="changePassword">
          <Message v-if="passwordError" severity="error" :closable="false">{{ passwordError }}</Message>
          <div class="form__field">
            <label for="me-pw0">Текущий пароль</label>
            <Password id="me-pw0" v-model="currentPassword" toggle-mask :feedback="false" autocomplete="current-password" fluid />
          </div>
          <div class="form__field">
            <label for="me-pw">Новый пароль</label>
            <Password id="me-pw" v-model="newPassword" toggle-mask :feedback="false" autocomplete="new-password" fluid />
          </div>
          <div class="form__field">
            <label for="me-pw2">Повторите пароль</label>
            <Password id="me-pw2" v-model="newPassword2" toggle-mask :feedback="false" autocomplete="new-password" fluid />
          </div>
          <div class="dialog-actions">
            <Button type="submit" label="Сменить пароль" size="small" :loading="passwordSaving" :disabled="!newPassword || !currentPassword" />
          </div>
        </form>
        <p v-else class="muted" style="margin: 0">Пароль меняется в Active Directory — обратитесь к администратору или смените его на рабочем компьютере.</p>
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
          <i class="pi pi-code" /> Правила обработки писем (Sieve)
          <span class="toolbar__spacer" />
          <span v-if="original?.sieve_synced_at" class="form__hint">применён {{ formatDateTime(original.sieve_synced_at) }}</span>
        </h2>
        <SieveForm v-model="form.sieve_custom" :error="sieveError" />
      </div>
    </div>
  </div>
</template>
