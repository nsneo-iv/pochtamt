<script setup lang="ts">
// Общий лейаут: левое меню (пункты зависят от роли), переключатель темы, блок пользователя, область страницы
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'
import Button from 'primevue/button'
import { homeRoute, menuRoutes } from '@/router'
import { useAuthStore } from '@/stores/auth'
import ThemeSwitch from '@/components/ThemeSwitch.vue'
import { APP_TITLE } from '@/brand'

const auth = useAuthStore()
const router = useRouter()

/** Подписи ролей для блока пользователя */
const roleLabels: Record<string, string> = {
  superadmin: 'Суперадминистратор',
  domain_admin: 'Администратор домена',
}

interface MenuItem {
  name: string
  title: string
  icon: string
  to: RouteLocationRaw
}

/** Пункты меню, доступные текущей роли; «Сводка» у domain_admin ведёт на дашборд его домена */
const menu = computed<MenuItem[]>(() =>
  menuRoutes
    .filter((r) => r.meta?.title && auth.hasRole(r.meta.roles) && (!r.meta?.requiresAd || auth.adEnabled))
    .map((r) => {
      const name = String(r.name)
      return {
        name,
        title: r.meta?.title ?? '',
        icon: r.meta?.icon ?? 'pi pi-circle',
        to: name === 'dashboard' ? homeRoute(auth) : { name },
      }
    }),
)

const roleLabel = computed(() => (auth.role ? roleLabels[auth.role] ?? auth.role : ''))

function logout(): void {
  auth.logout()
  void router.push({ name: 'login' })
}
</script>

<template>
  <div class="layout">
    <aside class="layout__sidebar">
      <div class="layout__brand">
        <i class="pi pi-envelope" />
        <span>{{ APP_TITLE }}</span>
      </div>
      <ul class="layout__menu">
        <li v-for="item in menu" :key="item.name">
          <RouterLink :to="item.to">
            <i :class="item.icon" />
            <span>{{ item.title }}</span>
          </RouterLink>
        </li>
      </ul>
      <div class="layout__user">
        <div class="layout__user-name" :title="auth.user?.login">{{ auth.user?.display_name || auth.user?.login }}</div>
        <div class="layout__user-role">{{ roleLabel }}</div>
        <div v-if="!auth.isSuperadmin && auth.ownDomains.length" class="layout__user-role">
          {{ auth.ownDomains.join(', ') }}
        </div>
        <div class="layout__user-actions">
          <ThemeSwitch />
          <Button v-tooltip.top="'Выйти'" icon="pi pi-sign-out" severity="secondary" size="small" outlined aria-label="Выйти" @click="logout" />
        </div>
      </div>
    </aside>
    <main class="layout__content">
      <RouterView />
    </main>
  </div>
</template>
