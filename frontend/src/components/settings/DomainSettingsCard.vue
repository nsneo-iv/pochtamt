<script setup lang="ts">
// Карточка «Настройки домена» на дашборде: transport, BCC, исходящая почта. Сохраняет только суперадмин.
import { computed, ref, watch } from 'vue'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import ToggleSwitch from 'primevue/toggleswitch'
import Skeleton from 'primevue/skeleton'
import * as api from '@/api/domains'
import type { DomainSettings } from '@/api/types'
import { useNotify } from '@/composables/useNotify'
import { useAuthStore } from '@/stores/auth'
import { isEmail } from '@/utils/format'
import { sameValue } from '@/utils/diff'

const props = defineProps<{ name: string }>()

const notify = useNotify()
const auth = useAuthStore()

const original = ref<DomainSettings | null>(null)
const form = ref<DomainSettings>({ transport: null, bcc_address: null, outbound_allowed: true })
const loading = ref(false)
const saving = ref(false)

const canEdit = computed(() => auth.isSuperadmin)
const dirty = computed(() => !!original.value && !sameValue(original.value, form.value))

const transport = computed({
  get: () => form.value.transport ?? '',
  set: (v: string) => {
    form.value.transport = v.trim() || null
  },
})
const bcc = computed({
  get: () => form.value.bcc_address ?? '',
  set: (v: string) => {
    form.value.bcc_address = v.trim() || null
  },
})

async function load(): Promise<void> {
  loading.value = true
  original.value = null
  try {
    const settings = await api.getDomainSettings(props.name)
    original.value = settings
    form.value = { ...settings }
  } catch (e) {
    notify.error(e, 'Не удалось загрузить настройки домена')
  } finally {
    loading.value = false
  }
}

async function save(): Promise<void> {
  if (form.value.bcc_address && !isEmail(form.value.bcc_address)) {
    notify.error(new Error('Некорректный адрес для скрытой копии'))
    return
  }
  saving.value = true
  try {
    const saved = await api.updateDomainSettings(props.name, form.value)
    original.value = saved
    form.value = { ...saved }
    notify.success('Настройки домена сохранены')
  } catch (e) {
    notify.error(e)
  } finally {
    saving.value = false
  }
}

function reset(): void {
  if (original.value) form.value = { ...original.value }
}

watch(() => props.name, load, { immediate: true })
</script>

<template>
  <div class="card">
    <h2 class="card__title"><i class="pi pi-cog" /> Настройки домена</h2>
    <div v-if="loading" class="skeleton-block">
      <Skeleton v-for="i in 3" :key="i" height="2.5rem" />
    </div>
    <form v-else-if="original" class="form" @submit.prevent="save">
      <div class="form__field">
        <label for="ds-transport">Доставка (transport)</label>
        <InputText id="ds-transport" v-model="transport" placeholder="smtp:[mail.example.com]:25" :disabled="!canEdit" fluid />
        <span class="form__hint">Relay почты домена на другой сервер в формате <span class="mono">smtp:[host]:port</span>. Пусто — локальная доставка.</span>
      </div>
      <div class="form__field">
        <label for="ds-bcc">Скрытая копия всех писем (BCC)</label>
        <InputText id="ds-bcc" v-model="bcc" placeholder="archive@example.com" :disabled="!canEdit" fluid />
        <span class="form__hint">Копия каждого входящего и исходящего письма домена. Пусто — не копировать.</span>
      </div>
      <div class="form__check">
        <ToggleSwitch v-model="form.outbound_allowed" input-id="ds-outbound" :disabled="!canEdit" />
        <label for="ds-outbound">Разрешена внешняя исходящая почта</label>
      </div>
      <span class="form__hint">Если выключено, пользователи домена пишут только на адреса этого сервера.</span>
      <div v-if="canEdit" class="dialog-actions">
        <Button type="button" label="Отменить" severity="secondary" outlined size="small" :disabled="!dirty" @click="reset" />
        <Button type="submit" label="Сохранить" icon="pi pi-save" size="small" :loading="saving" :disabled="!dirty" />
      </div>
      <span v-else class="form__hint">Изменять настройки домена может только суперадминистратор.</span>
    </form>
  </div>
</template>
