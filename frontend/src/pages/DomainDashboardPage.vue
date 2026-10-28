<script setup lang="ts">
// Дашборд домена: шапка со ссылками на списки, статистика, DNS-проверка (MX/SPF/DKIM/DMARC),
// DKIM-ключ, топ-10 ящиков по месту и последние действия. Запрос может идти до ~8 с из-за DNS,
// поэтому до ответа показываем скелетоны, а не блокируем страницу.
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import Button from 'primevue/button'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import ProgressBar from 'primevue/progressbar'
import Skeleton from 'primevue/skeleton'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import * as api from '@/api/domains'
import type { DnsCheck, DnsStatus, DomainDashboard } from '@/api/types'
import { useNotify } from '@/composables/useNotify'
import { useDomains } from '@/composables/useDomains'
import { useAuthStore } from '@/stores/auth'
import { formatDateTime, formatMb } from '@/utils/format'
import { copyToClipboard } from '@/utils/clipboard'
import DomainSettingsCard from '@/components/settings/DomainSettingsCard.vue'

const props = defineProps<{ name: string }>()

const notify = useNotify()
const router = useRouter()
const auth = useAuthStore()
const { options: domainOptions } = useDomains()

const dashboard = ref<DomainDashboard | null>(null)
const loading = ref(false)
const loadError = ref<string | null>(null)

/** Переключатель доменов показываем, когда доменов больше одного */
const showSwitcher = computed(() => domainOptions.value.length > 1)

async function load(): Promise<void> {
  loading.value = true
  loadError.value = null
  const requested = props.name
  try {
    const result = await api.getDomainDashboard(requested)
    // Пока ждали DNS, пользователь мог переключить домен — старый ответ не показываем
    if (requested === props.name) dashboard.value = result
  } catch (e) {
    if (requested === props.name) {
      dashboard.value = null
      loadError.value = e instanceof Error ? e.message : 'Не удалось загрузить дашборд'
    }
  } finally {
    if (requested === props.name) loading.value = false
  }
}

watch(() => props.name, load, { immediate: true })

function switchDomain(name: string | null): void {
  if (name && name !== props.name) void router.push({ name: 'domain-dashboard', params: { name } })
}

// ---- Статистика ----

const statCards = computed(() => {
  const s = dashboard.value?.stats
  if (!s) return []
  return [
    { key: 'mailboxes', label: 'Ящиков всего', icon: 'pi pi-inbox', value: s.mailboxes },
    { key: 'active', label: 'Активных ящиков', icon: 'pi pi-check-circle', value: s.mailboxes_active },
    { key: 'ad', label: 'Ящиков из AD', icon: 'pi pi-sitemap', value: s.mailboxes_ad },
    { key: 'aliases', label: 'Алиасов', icon: 'pi pi-directions', value: s.aliases },
    { key: 'lists', label: 'Рассылок', icon: 'pi pi-users', value: s.lists },
    { key: 'used', label: 'Занято', icon: 'pi pi-database', value: formatMb(s.used_mb) },
    { key: 'quota', label: 'Сумма квот', icon: 'pi pi-chart-pie', value: formatMb(s.quota_mb) },
    { key: 'unlimited', label: 'Без лимита', icon: 'pi pi-infinity', value: s.unlimited },
  ]
})

// ---- DNS ----

const dnsRows: { key: keyof DomainDashboard['dns']; title: string }[] = [
  { key: 'mx', title: 'MX' },
  { key: 'spf', title: 'SPF' },
  { key: 'dkim', title: 'DKIM' },
  { key: 'dmarc', title: 'DMARC' },
]

const statusLabels: Record<DnsStatus, string> = {
  ok: 'OK',
  warn: 'Замечание',
  missing: 'Нет записи',
  error: 'Ошибка',
}

const statusSeverity: Record<DnsStatus, 'success' | 'warn' | 'secondary' | 'danger'> = {
  ok: 'success',
  warn: 'warn',
  missing: 'secondary',
  error: 'danger',
}

/** Найденные записи (record и/или records) одним списком */
function foundRecords(check: DnsCheck): string[] {
  const list = [...(check.records ?? [])]
  if (check.record && !list.includes(check.record)) list.unshift(check.record)
  return list
}

// ---- DKIM-ключ ----

const selector = ref('mail')
const dkimBusy = ref(false)

async function createKey(): Promise<void> {
  if (!dashboard.value) return
  dkimBusy.value = true
  try {
    await api.createDkim(dashboard.value.domain.name, { selector: selector.value.trim() || 'mail' })
    notify.success('DKIM-ключ создан. Добавьте TXT-запись в DNS.')
    await load()
  } catch (e) {
    notify.error(e)
  } finally {
    dkimBusy.value = false
  }
}

function deleteKey(): void {
  const name = dashboard.value?.domain.name
  if (!name) return
  notify.confirmDelete(`Удалить DKIM-ключ домена ${name}? Исходящие письма перестанут подписываться.`, async () => {
    dkimBusy.value = true
    try {
      await api.deleteDkim(name)
      notify.success('DKIM-ключ удалён')
      await load()
    } catch (e) {
      notify.error(e)
    } finally {
      dkimBusy.value = false
    }
  })
}

async function copy(text: string): Promise<void> {
  try {
    await copyToClipboard(text)
    notify.success('Скопировано в буфер обмена')
  } catch (e) {
    notify.error(e, 'Не удалось скопировать')
  }
}

/** Подробности записи аудита одной строкой */
function formatDetails(details: unknown): string {
  if (details === null || details === undefined || details === '') return ''
  if (typeof details === 'string') return details
  try {
    return JSON.stringify(details)
  } catch {
    return String(details)
  }
}
</script>

<template>
  <div>
    <!-- Шапка -->
    <div class="toolbar">
      <h1 class="page-title" style="margin: 0; display: flex; align-items: center; gap: 0.75rem">
        <i class="pi pi-globe" style="color: var(--p-primary-color)" />
        <Select
          v-if="showSwitcher"
          :model-value="props.name"
          :options="domainOptions"
          option-label="label"
          option-value="value"
          style="min-width: 14rem"
          @update:model-value="switchDomain"
        />
        <span v-else>{{ props.name }}</span>
        <Tag
          v-if="dashboard"
          :severity="dashboard.domain.active ? 'success' : 'secondary'"
          :value="dashboard.domain.active ? 'Активен' : 'Отключён'"
        />
      </h1>
      <div class="toolbar__spacer" />
      <Button label="Ящики" icon="pi pi-inbox" severity="secondary" outlined @click="router.push({ name: 'mailboxes', query: { domain: props.name } })" />
      <Button label="Алиасы" icon="pi pi-directions" severity="secondary" outlined @click="router.push({ name: 'aliases', query: { domain: props.name } })" />
      <Button label="Рассылки" icon="pi pi-users" severity="secondary" outlined @click="router.push({ name: 'lists', query: { domain: props.name } })" />
      <Button label="Обновить" icon="pi pi-refresh" severity="secondary" outlined :loading="loading" @click="load" />
    </div>
    <p v-if="dashboard?.domain.description" class="muted" style="margin: -0.5rem 0 1rem">{{ dashboard.domain.description }}</p>

    <Message v-if="loadError" severity="error" :closable="false" style="margin-bottom: 1rem">
      {{ loadError }}
      <Button label="Повторить" link size="small" @click="load" />
    </Message>

    <!-- Скелетон, пока ждём ответ (DNS-проверка может идти до 8 с) -->
    <template v-if="loading && !dashboard">
      <div class="stat-grid">
        <Skeleton v-for="i in 8" :key="i" height="5rem" border-radius="8px" />
      </div>
      <div class="dash-grid">
        <div class="card skeleton-block">
          <Skeleton width="40%" height="1.2rem" />
          <Skeleton v-for="i in 4" :key="i" height="2.5rem" />
        </div>
        <div class="card skeleton-block">
          <Skeleton width="40%" height="1.2rem" />
          <Skeleton v-for="i in 6" :key="i" height="1.6rem" />
        </div>
      </div>
    </template>

    <template v-else-if="dashboard">
      <!-- Статистика -->
      <div class="stat-grid" :style="loading ? 'opacity: 0.6' : ''">
        <div v-for="card in statCards" :key="card.key" class="stat-card stat-card--small">
          <i :class="[card.icon, 'stat-card__icon']" />
          <div>
            <div class="stat-card__value">{{ card.value }}</div>
            <div class="stat-card__label">{{ card.label }}</div>
          </div>
        </div>
      </div>

      <div class="dash-grid">
        <!-- DNS -->
        <div class="card">
          <h2 class="card__title">
            <i class="pi pi-server" />
            DNS-записи
            <span class="toolbar__spacer" />
            <Button label="Проверить снова" icon="pi pi-refresh" size="small" severity="secondary" outlined :loading="loading" @click="load" />
          </h2>
          <div class="dns-table">
            <div v-for="row in dnsRows" :key="row.key" class="dns-row">
              <div class="dns-row__name">
                {{ row.title }}
                <div><Tag :severity="statusSeverity[dashboard.dns[row.key].status]" :value="statusLabels[dashboard.dns[row.key].status]" style="margin-top: 0.3rem" /></div>
              </div>
              <div class="dns-row__body">
                <div v-if="dashboard.dns[row.key].name" class="form__hint">Имя записи: <span class="mono">{{ dashboard.dns[row.key].name }}</span></div>
                <div v-for="rec in foundRecords(dashboard.dns[row.key])" :key="rec" class="dns-row__line">
                  <span class="mono">{{ rec }}</span>
                  <Button v-tooltip.top="'Копировать'" icon="pi pi-copy" text rounded size="small" severity="secondary" @click="copy(rec)" />
                </div>
                <div v-if="row.key === 'dkim' && dashboard.dns.dkim.matches === false && dashboard.dns.dkim.found" class="form__hint" style="color: var(--p-red-500)">
                  Ключ в DNS не совпадает с ключом сервера
                </div>
                <!-- Ожидаемую запись показываем, только если что-то не так -->
                <template v-if="dashboard.dns[row.key].expected && dashboard.dns[row.key].status !== 'ok'">
                  <div class="form__hint">Ожидается:</div>
                  <div class="dns-row__line">
                    <span class="mono">{{ dashboard.dns[row.key].expected }}</span>
                    <Button v-tooltip.top="'Копировать'" icon="pi pi-copy" text rounded size="small" severity="secondary" @click="copy(dashboard.dns[row.key].expected ?? '')" />
                  </div>
                </template>
                <div v-if="dashboard.dns[row.key].detail" class="form__hint">{{ dashboard.dns[row.key].detail }}</div>
                <div v-if="!foundRecords(dashboard.dns[row.key]).length && !dashboard.dns[row.key].expected && !dashboard.dns[row.key].detail" class="muted">—</div>
              </div>
            </div>
          </div>
        </div>

        <!-- DKIM-ключ -->
        <div class="card">
          <h2 class="card__title"><i class="pi pi-key" /> DKIM-ключ</h2>
          <template v-if="dashboard.dkim">
            <div class="dns-record">
              <div class="dns-record__label">Селектор</div>
              <div class="dns-record__value mono">{{ dashboard.dkim.selector }}</div>
              <div />
              <div class="dns-record__label">Имя записи</div>
              <div class="dns-record__value mono">{{ dashboard.dkim.dns_name }}</div>
              <Button v-tooltip.top="'Копировать'" icon="pi pi-copy" text rounded severity="secondary" @click="copy(dashboard.dkim.dns_name)" />
              <div class="dns-record__label">TXT-значение</div>
              <div class="dns-record__value mono">{{ dashboard.dkim.dns_value }}</div>
              <Button v-tooltip.top="'Копировать'" icon="pi pi-copy" text rounded severity="secondary" @click="copy(dashboard.dkim.dns_value)" />
            </div>
            <p class="form__hint">Создан: {{ formatDateTime(dashboard.dkim.created_at) }}. Добавьте TXT-запись в DNS домена, чтобы подпись проверялась.</p>
            <div v-if="auth.isSuperadmin" class="dialog-actions">
              <Button label="Удалить ключ" icon="pi pi-trash" severity="danger" outlined size="small" :loading="dkimBusy" @click="deleteKey" />
            </div>
          </template>
          <template v-else>
            <p class="muted" style="margin-top: 0">DKIM-ключ для домена не создан — исходящие письма не подписываются.</p>
            <div class="form__row">
              <div class="form__field">
                <label for="dkim-selector">Селектор</label>
                <InputText id="dkim-selector" v-model="selector" placeholder="mail" fluid />
              </div>
              <div style="flex: 0 0 auto">
                <Button label="Создать ключ" icon="pi pi-key" :loading="dkimBusy" @click="createKey" />
              </div>
            </div>
          </template>
        </div>

        <!-- Настройки домена: грузятся отдельным запросом, не ждут DNS -->
        <DomainSettingsCard :name="props.name" />

        <!-- Топ ящиков по месту -->
        <div class="card">
          <h2 class="card__title"><i class="pi pi-chart-bar" /> Топ ящиков по занятому месту</h2>
          <div v-if="dashboard.top_mailboxes.length" class="top-list">
            <div v-for="m in dashboard.top_mailboxes" :key="m.address">
              <div class="top-item__head">
                <span>
                  <RouterLink :to="{ name: 'mailboxes', query: { domain: props.name, q: m.address } }" class="mono">{{ m.address }}</RouterLink>
                  <span v-if="!m.active" class="muted"> (отключён)</span>
                  <span v-if="m.name" class="muted"> — {{ m.name }}</span>
                </span>
                <span style="white-space: nowrap">
                  {{ formatMb(m.used_mb) }}
                  <template v-if="m.quota_mb"> / {{ formatMb(m.quota_mb) }} ({{ m.percent ?? 0 }}%)</template>
                  <span v-else class="muted"> / —</span>
                </span>
              </div>
              <ProgressBar v-if="m.percent !== null && m.quota_mb" :value="Math.min(100, m.percent)" :show-value="false" style="height: 6px; margin-top: 4px" />
              <div v-else class="form__hint">без лимита</div>
            </div>
          </div>
          <p v-else class="muted" style="margin: 0">Ящиков пока нет</p>
        </div>

        <!-- Последние действия -->
        <div class="card">
          <h2 class="card__title">
            <i class="pi pi-history" /> Последние действия
            <span class="toolbar__spacer" />
            <RouterLink :to="{ name: 'audit' }" style="font-size: 0.9rem; font-weight: 400">Весь журнал</RouterLink>
          </h2>
          <ul v-if="dashboard.recent_audit.length" class="audit-list">
            <li v-for="(item, index) in dashboard.recent_audit" :key="index">
              <span class="muted">{{ formatDateTime(item.ts) }}</span>
              <span>
                <strong>{{ item.actor }}</strong> — <span class="mono">{{ item.action }}</span> <span class="mono">{{ item.object }}</span>
                <div v-if="formatDetails(item.details)" class="form__hint mono">{{ formatDetails(item.details) }}</div>
              </span>
            </li>
          </ul>
          <p v-else class="muted" style="margin: 0">Действий по домену пока не было</p>
        </div>
      </div>
    </template>
  </div>
</template>
