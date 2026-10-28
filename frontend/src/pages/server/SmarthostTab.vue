<script setup lang="ts">
// Вкладка «Исходящая почта»: релей (smarthost). Пароль отправляется только если введён.
import { computed, onMounted, reactive, ref } from 'vue'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import InputNumber from 'primevue/inputnumber'
import Password from 'primevue/password'
import ToggleSwitch from 'primevue/toggleswitch'
import Message from 'primevue/message'
import Tag from 'primevue/tag'
import * as api from '@/api/server'
import type { Smarthost } from '@/api/types'
import { useNotify } from '@/composables/useNotify'

const notify = useNotify()

const original = ref<Smarthost | null>(null)
const loading = ref(false)
const saving = ref(false)
const form = reactive({
  enabled: false,
  host: '',
  port: 587 as number | null,
  user: '',
  password: '',
})

function apply(s: Smarthost): void {
  original.value = s
  form.enabled = s.enabled
  form.host = s.host ?? ''
  form.port = s.port
  form.user = s.user ?? ''
  form.password = ''
}

const dirty = computed(() => {
  const o = original.value
  if (!o) return false
  return (
    form.enabled !== o.enabled ||
    (form.host.trim() || null) !== o.host ||
    form.port !== o.port ||
    (form.user.trim() || null) !== o.user ||
    form.password.length > 0
  )
})

const validationError = computed<string | null>(() => {
  if (!form.enabled) return null
  if (!form.host.trim()) return 'Укажите адрес релея'
  if (!form.port || form.port < 1 || form.port > 65535) return 'Укажите порт от 1 до 65535'
  return null
})

async function load(): Promise<void> {
  loading.value = true
  try {
    apply(await api.getSmarthost())
  } catch (e) {
    notify.error(e, 'Не удалось загрузить настройки релея')
  } finally {
    loading.value = false
  }
}

async function save(): Promise<void> {
  if (validationError.value) return
  saving.value = true
  try {
    apply(
      await api.updateSmarthost({
        enabled: form.enabled,
        host: form.host.trim() || null,
        port: form.port,
        user: form.user.trim() || null,
        // Пароль только если пользователь ввёл новый; иначе на сервере остаётся прежний
        ...(form.password ? { password: form.password } : {}),
      }),
    )
    notify.success('Настройки исходящей почты сохранены')
  } catch (e) {
    notify.error(e)
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="card" style="max-width: 640px">
    <h2 class="card__title">
      <i class="pi pi-send" /> Релей исходящей почты (smarthost)
      <span class="toolbar__spacer" />
      <Tag v-if="original" :severity="original.enabled ? 'success' : 'secondary'" :value="original.enabled ? 'Включён' : 'Выключен'" />
    </h2>
    <p class="muted" style="margin-top: 0">
      Если релей включён, вся исходящая почта сервера отправляется через указанный хост (например, SMTP провайдера),
      а не напрямую получателям. Полезно, когда у сервера нет прямого доступа к 25 порту или плохая репутация IP.
    </p>
    <form class="form" @submit.prevent="save">
      <div class="form__check">
        <ToggleSwitch v-model="form.enabled" input-id="sh-enabled" :disabled="loading" />
        <label for="sh-enabled">Отправлять через релей</label>
      </div>
      <div class="form__row">
        <div class="form__field" style="flex: 3">
          <label for="sh-host">Хост релея</label>
          <InputText id="sh-host" v-model="form.host" placeholder="smtp.provider.ru" :disabled="loading" fluid />
        </div>
        <div class="form__field">
          <label for="sh-port">Порт</label>
          <InputNumber id="sh-port" v-model="form.port" :min="1" :max="65535" :use-grouping="false" :disabled="loading" fluid />
        </div>
      </div>
      <div class="form__field">
        <label for="sh-user">Пользователь</label>
        <InputText id="sh-user" v-model="form.user" placeholder="пусто — без авторизации" autocomplete="off" :disabled="loading" fluid />
      </div>
      <div class="form__field">
        <label for="sh-password">Пароль</label>
        <Password id="sh-password" v-model="form.password" toggle-mask :feedback="false" autocomplete="new-password" :disabled="loading" fluid />
        <span class="form__hint">
          <template v-if="original?.password_set">Пароль задан. Оставьте поле пустым, чтобы не менять.</template>
          <template v-else>Пароль не задан.</template>
        </span>
      </div>
      <Message v-if="dirty && validationError" severity="error" :closable="false">{{ validationError }}</Message>
      <div class="dialog-actions">
        <Button type="button" label="Отменить" severity="secondary" outlined :disabled="!dirty" @click="original && apply(original)" />
        <Button type="submit" label="Сохранить" icon="pi pi-save" :loading="saving" :disabled="!dirty || validationError !== null" />
      </div>
    </form>
  </div>
</template>
