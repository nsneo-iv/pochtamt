<script setup lang="ts">
import { APP_TITLE } from '@/brand'
// Лейаут личного кабинета: шапка с адресом, переключателем темы и выходом. Никаких админских запросов.
import { useRouter } from 'vue-router'
import Button from 'primevue/button'
import { useMeStore } from '@/stores/me'
import ThemeSwitch from '@/components/ThemeSwitch.vue'

const me = useMeStore()
const router = useRouter()

function logout(): void {
  me.logout()
  void router.push({ name: 'me-login' })
}
</script>

<template>
  <div class="me">
    <header class="me__header">
      <div class="me__brand">
        <i class="pi pi-envelope" />
        <span>{{ APP_TITLE }}</span>
        <span class="me__sep">·</span>
        <span class="muted">личный кабинет</span>
      </div>
      <div class="me__user">
        <span v-if="me.me" class="mono" :title="me.me.name">{{ me.me.address }}</span>
        <ThemeSwitch />
        <Button v-tooltip.bottom="'Выйти'" icon="pi pi-sign-out" severity="secondary" size="small" outlined aria-label="Выйти" @click="logout" />
      </div>
    </header>
    <main class="me__content">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.me {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.me__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.75rem 1.5rem;
  background: var(--app-card-bg);
  border-bottom: 1px solid var(--app-card-border);
  flex-wrap: wrap;
}

.me__brand {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  font-size: 1.05rem;
}

.me__brand .pi {
  color: var(--p-primary-color);
}

.me__sep {
  color: var(--p-text-muted-color);
}

.me__user {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.me__content {
  flex: 1;
  width: 100%;
  max-width: 1100px;
  margin: 0 auto;
  padding: 1.5rem 1rem;
}
</style>
