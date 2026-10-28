<script setup lang="ts">
// Вход в личный кабинет: адрес ящика и пароль (POST /me/login)
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Password from 'primevue/password'
import Message from 'primevue/message'
import { useMeStore } from '@/stores/me'
import { errorMessage } from '@/composables/useNotify'
import { isEmail } from '@/utils/format'
import ThemeSwitch from '@/components/ThemeSwitch.vue'
import { APP_TITLE, WEBMAIL_URL } from '@/brand'

const me = useMeStore()
const router = useRouter()

const address = ref('')
const password = ref('')
const loading = ref(false)
const error = ref<string | null>(null)

async function submit(): Promise<void> {
  const addr = address.value.trim().toLowerCase()
  if (!isEmail(addr) || !password.value) {
    error.value = 'Укажите адрес ящика и пароль'
    return
  }
  loading.value = true
  error.value = null
  try {
    await me.login(addr, password.value)
    await router.replace({ name: 'me' })
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login">
    <div class="login__theme"><ThemeSwitch /></div>
    <form class="login__card card" @submit.prevent="submit">
      <div class="login__brand">
        <i class="pi pi-envelope" />
        <span>{{ APP_TITLE }}</span>
      </div>
      <p class="muted">Личный кабинет: автоответ, пересылка, пароль и правила вашего ящика.</p>
      <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
      <div class="form__field">
        <label for="me-address">Адрес ящика</label>
        <InputText id="me-address" v-model="address" placeholder="user@example.com" autocomplete="username" autofocus fluid />
      </div>
      <div class="form__field">
        <label for="me-password">Пароль</label>
        <Password id="me-password" v-model="password" :feedback="false" toggle-mask autocomplete="current-password" fluid />
      </div>
      <Button type="submit" label="Войти" icon="pi pi-sign-in" :loading="loading" fluid />
      <p v-if="WEBMAIL_URL" class="form__hint" style="text-align: center; margin: 0">
        Веб-почта: <a :href="WEBMAIL_URL" target="_blank" rel="noopener">{{ WEBMAIL_URL.replace(/^https?:\/\//, '') }}</a>
      </p>
    </form>
  </div>
</template>

<style scoped>
.login {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  position: relative;
}

.login__theme {
  position: absolute;
  top: 1rem;
  right: 1rem;
}

.login__card {
  width: 100%;
  max-width: 380px;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.login__brand {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  font-size: 1.3rem;
  font-weight: 600;
}

.login__brand .pi {
  color: var(--p-primary-color);
}
</style>
