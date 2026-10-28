<script setup lang="ts">
// Страница входа: логин админа (локальный пароль или доменная учётка AD, если AD настроен) и пароль
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Password from 'primevue/password'
import Message from 'primevue/message'
import { useAuthStore } from '@/stores/auth'
import { homeRoute } from '@/router'
import { errorMessage } from '@/composables/useNotify'
import ThemeSwitch from '@/components/ThemeSwitch.vue'
import { APP_TITLE } from '@/brand'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const login = ref('')
const password = ref('')
const loading = ref(false)
const error = ref<string | null>(null)

onMounted(() => void auth.ensureConfig())

async function submit(): Promise<void> {
  if (!login.value.trim() || !password.value) {
    error.value = 'Укажите логин и пароль'
    return
  }
  loading.value = true
  error.value = null
  try {
    await auth.login(login.value.trim(), password.value)
    // Возврат на страницу, с которой увело на вход (только внутренние пути)
    const redirect = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/')
      ? route.query.redirect
      : homeRoute(auth)
    await router.replace(redirect)
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
      <p class="muted">Вход для администраторов.<template v-if="auth.adEnabled"> Можно использовать доменную учётную запись.</template></p>
      <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
      <div class="form__field">
        <label for="login">Логин</label>
        <InputText id="login" v-model="login" :placeholder="auth.loginHint || 'admin'" autocomplete="username" autofocus fluid />
      </div>
      <div class="form__field">
        <label for="password">Пароль</label>
        <Password
          id="password"
          v-model="password"
          :feedback="false"
          toggle-mask
          autocomplete="current-password"
          fluid
          input-class="w-full"
        />
      </div>
      <Button type="submit" label="Войти" icon="pi pi-sign-in" :loading="loading" fluid />
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
