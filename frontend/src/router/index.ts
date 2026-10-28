// Маршруты панели. Страницы под MainLayout требуют авторизации;
// meta.roles ограничивает доступ по роли (пусто = любая роль).
import { createRouter, createWebHistory } from 'vue-router'
import type { RouteLocationRaw, RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useMeStore } from '@/stores/me'
import type { Role } from '@/api/types'
import { APP_TITLE } from '@/brand'

declare module 'vue-router' {
  interface RouteMeta {
    /** Заголовок страницы и подпись в меню */
    title?: string
    /** Иконка primeicons для меню */
    icon?: string
    /** Нужна авторизация */
    requiresAuth?: boolean
    /** Роли, которым доступна страница; пусто = всем */
    roles?: Role[]
    /** Не показывать в левом меню (вложенные страницы) */
    hidden?: boolean
    /** Личный кабинет: нужен токен кабинета (стор me), а не админский */
    me?: boolean
    /** Страница имеет смысл только при настроенном Active Directory */
    requiresAd?: boolean
  }
}

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/pages/LoginPage.vue'),
    meta: { title: 'Вход' },
  },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    meta: { requiresAuth: true },
    redirect: { name: 'dashboard' },
    children: [
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('@/pages/DashboardPage.vue'),
        meta: { title: 'Сводка', icon: 'pi pi-home' },
      },
      {
        path: 'domains',
        name: 'domains',
        component: () => import('@/pages/DomainsPage.vue'),
        meta: { title: 'Домены', icon: 'pi pi-globe' },
      },
      {
        path: 'domains/:name',
        name: 'domain-dashboard',
        component: () => import('@/pages/DomainDashboardPage.vue'),
        props: true,
        meta: { title: 'Дашборд домена', icon: 'pi pi-chart-bar', hidden: true },
      },
      {
        path: 'mailboxes',
        name: 'mailboxes',
        component: () => import('@/pages/MailboxesPage.vue'),
        meta: { title: 'Ящики', icon: 'pi pi-inbox' },
      },
      {
        path: 'mailboxes/:address/settings',
        name: 'mailbox-settings',
        component: () => import('@/pages/MailboxSettingsPage.vue'),
        props: true,
        meta: { title: 'Настройки ящика', icon: 'pi pi-cog', hidden: true },
      },
      {
        path: 'aliases',
        name: 'aliases',
        component: () => import('@/pages/AliasesPage.vue'),
        meta: { title: 'Алиасы', icon: 'pi pi-directions' },
      },
      {
        path: 'domain-aliases',
        name: 'domain-aliases',
        component: () => import('@/pages/DomainAliasesPage.vue'),
        meta: { title: 'Доменные алиасы', icon: 'pi pi-clone', roles: ['superadmin'] },
      },
      {
        path: 'lists',
        name: 'lists',
        component: () => import('@/pages/ListsPage.vue'),
        meta: { title: 'Рассылки', icon: 'pi pi-users' },
      },
      {
        path: 'queue',
        name: 'queue',
        component: () => import('@/pages/QueuePage.vue'),
        meta: { title: 'Очередь', icon: 'pi pi-list', roles: ['superadmin'] },
      },
      {
        path: 'filter',
        name: 'filter',
        component: () => import('@/pages/FilterPage.vue'),
        meta: { title: 'Фильтр', icon: 'pi pi-shield', roles: ['superadmin'] },
      },
      {
        path: 'system',
        name: 'system',
        component: () => import('@/pages/SystemPage.vue'),
        meta: { title: 'Состояние', icon: 'pi pi-server', roles: ['superadmin'] },
      },
      {
        path: 'server',
        name: 'server',
        component: () => import('@/pages/ServerPage.vue'),
        meta: { title: 'Сервер', icon: 'pi pi-cog', roles: ['superadmin'] },
      },
      {
        path: 'audit',
        name: 'audit',
        component: () => import('@/pages/AuditPage.vue'),
        meta: { title: 'Аудит', icon: 'pi pi-history' },
      },
      {
        path: 'ad-sync',
        name: 'ad-sync',
        component: () => import('@/pages/AdSyncPage.vue'),
        meta: { title: 'Синхронизация AD', icon: 'pi pi-sync', roles: ['superadmin'], requiresAd: true },
      },
    ],
  },
  // Личный кабинет пользователя: отдельный лейаут и отдельный токен
  {
    path: '/me/login',
    name: 'me-login',
    component: () => import('@/pages/me/MeLoginPage.vue'),
    meta: { title: 'Вход в кабинет' },
  },
  {
    path: '/me',
    component: () => import('@/layouts/MeLayout.vue'),
    meta: { me: true },
    children: [
      {
        path: '',
        name: 'me',
        component: () => import('@/pages/me/MePage.vue'),
        meta: { title: 'Мой ящик' },
      },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: { name: 'dashboard' } },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

/** Пункты левого меню: дочерние маршруты лейаута с заголовком, кроме скрытых */
export const menuRoutes = (routes.find((r) => r.path === '/')?.children ?? []).filter((r) => !r.meta?.hidden)

/** Стартовая страница: domain_admin — дашборд его первого домена, иначе общая сводка */
export function homeRoute(auth: ReturnType<typeof useAuthStore>): RouteLocationRaw {
  const first = auth.ownDomains[0]
  if (auth.role === 'domain_admin' && first) return { name: 'domain-dashboard', params: { name: first } }
  return { name: 'dashboard' }
}

router.beforeEach(async (to) => {
  // Личный кабинет живёт отдельно: свой токен, свой вход, никаких админских запросов
  if (to.matched.some((r) => r.meta.me) || to.name === 'me-login') {
    const me = useMeStore()
    if (to.name === 'me-login') return me.isAuthenticated ? { name: 'me' } : true
    if (!me.isAuthenticated) return { name: 'me-login' }
    return true
  }

  const auth = useAuthStore()
  const requiresAuth = to.matched.some((r) => r.meta.requiresAuth)

  if (!requiresAuth) {
    // Авторизованному на странице входа делать нечего
    if (to.name === 'login' && auth.isAuthenticated) return homeRoute(auth)
    return true
  }

  if (!auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  // После перезагрузки страницы пользователь ещё не загружен — запрашиваем /auth/me
  if (!auth.user) {
    try {
      await auth.fetchUser()
    } catch {
      auth.logout()
      return { name: 'login', query: { redirect: to.fullPath } }
    }
  }

  // Страница недоступна для роли — уводим на стартовую
  const roles = to.matched.flatMap((r) => r.meta.roles ?? [])
  if (roles.length > 0 && !auth.hasRole(roles)) return homeRoute(auth)

  // Разделы AD без настроенного AD не показываем
  if (to.matched.some((r) => r.meta.requiresAd)) {
    await auth.ensureConfig()
    if (!auth.adEnabled) return homeRoute(auth)
  }

  // Для domain_admin стартовая страница — дашборд его первого домена вместо общей сводки
  if (to.name === 'dashboard' && auth.role === 'domain_admin' && auth.ownDomains.length > 0) return homeRoute(auth)

  return true
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} — ${APP_TITLE}` : APP_TITLE
})

export default router
