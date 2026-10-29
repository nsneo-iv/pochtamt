<script setup lang="ts">
// Состояние сервера (только суперадмин): плитки метрик, службы, почта за сутки, fail2ban, Rspamd и графики истории
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Button from 'primevue/button'
import ToggleSwitch from 'primevue/toggleswitch'
import SelectButton from 'primevue/selectbutton'
import ProgressBar from 'primevue/progressbar'
import Tag from 'primevue/tag'
import Message from 'primevue/message'
import Skeleton from 'primevue/skeleton'
import * as api from '@/api/system'
import type { SystemHistory, SystemOverview } from '@/api/types'
import { useNotify } from '@/composables/useNotify'
import { formatBytes, formatDateTime, formatNumber, formatUptime } from '@/utils/format'
import RspamdStatsCards from '@/components/RspamdStatsCards.vue'
import SystemChart from '@/components/SystemChart.vue'
import type { ChartSeries } from '@/components/SystemChart.vue'

const notify = useNotify()

// ---- Сводка ----

const overview = ref<SystemOverview | null>(null)
const loading = ref(false)
const updatedAt = ref<Date | null>(null)
const autoRefresh = ref(true)

async function load(): Promise<void> {
  loading.value = true
  try {
    overview.value = await api.getSystemOverview()
    updatedAt.value = new Date()
  } catch (e) {
    notify.error(e, 'Не удалось загрузить состояние сервера')
  } finally {
    loading.value = false
  }
}

let refreshTimer: ReturnType<typeof setInterval> | undefined
function applyAutoRefresh(): void {
  clearInterval(refreshTimer)
  if (autoRefresh.value) refreshTimer = setInterval(() => void load(), 30000)
}
watch(autoRefresh, applyAutoRefresh)

/** Процент заполнения */
function pct(used: number, total: number): number {
  return total > 0 ? Math.round((used / total) * 100) : 0
}

/** Цвет ProgressBar по заполнению: warn >80 %, danger >90 % */
function fillClass(percent: number): string {
  if (percent > 90) return 'bar-danger'
  if (percent > 80) return 'bar-warn'
  return ''
}

const memPercent = computed(() => (overview.value?.host ? pct(overview.value.host.mem.used, overview.value.host.mem.total) : 0))

function certSeverity(days: number): 'success' | 'warn' | 'danger' {
  if (days < 14) return 'danger'
  if (days < 30) return 'warn'
  return 'success'
}

// ---- Службы ----

const serviceLabels: Record<string, string> = {
  postfix: 'Postfix (MTA)',
  dovecot: 'Dovecot (IMAP)',
  rspamd: 'Rspamd (антиспам)',
  'clamav-daemon': 'ClamAV',
  'clamav-freshclam': 'Базы ClamAV',
  'redis-server': 'Redis',
  postgresql: 'PostgreSQL',
  nginx: 'nginx',
  unbound: 'DNS-резолвер',
  fail2ban: 'fail2ban',
  nftables: 'Файрвол',
  'mail-backend': 'Бэкенд панели',
  'mail-agent': 'Агент',
  sogo: 'SOGo (календарь, веб-почта)',
}

const stateLabels: Record<string, string> = {
  active: 'работает',
  inactive: 'остановлена',
  failed: 'ошибка',
  activating: 'запускается',
  deactivating: 'останавливается',
}

function serviceSeverity(state: string): 'success' | 'danger' | 'secondary' {
  if (state === 'active') return 'success'
  if (state === 'failed') return 'danger'
  return 'secondary'
}

const services = computed(() =>
  Object.entries(overview.value?.services ?? {}).map(([name, state]) => ({
    name,
    label: serviceLabels[name] ?? name,
    state,
    stateLabel: stateLabels[state] ?? state,
  })),
)

const fail2ban = computed(() =>
  Object.entries(overview.value?.fail2ban ?? {}).map(([jail, v]) => ({ jail, banned: v.banned, total: v.total })),
)

// ---- История ----

const hours = ref(24)
const hoursOptions = [
  { label: '6 ч', value: 6 },
  { label: '24 ч', value: 24 },
  { label: '7 дней', value: 168 },
]
const history = ref<SystemHistory | null>(null)
const historyLoading = ref(false)

async function loadHistory(): Promise<void> {
  historyLoading.value = true
  try {
    history.value = await api.getSystemHistory(hours.value)
  } catch (e) {
    notify.error(e, 'Не удалось загрузить историю')
  } finally {
    historyLoading.value = false
  }
}
watch(hours, loadHistory)

const points = computed(() => history.value?.points ?? [])
const hasPoints = computed(() => points.value.length > 0)

/** Подписи оси X: для суток — время, для недели — день и время */
const labels = computed(() =>
  points.value.map((p) => {
    const d = new Date(p.ts)
    if (Number.isNaN(d.getTime())) return p.ts
    return hours.value > 24
      ? d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
      : d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  }),
)

function percentSeries(used: keyof typeof points.value[number], total: keyof typeof points.value[number]): (number | null)[] {
  return points.value.map((p) => {
    const u = p[used]
    const t = p[total]
    return typeof u === 'number' && typeof t === 'number' && t > 0 ? Math.round((u / t) * 1000) / 10 : null
  })
}

function series(key: keyof typeof points.value[number]): (number | null)[] {
  return points.value.map((p) => {
    const v = p[key]
    return typeof v === 'number' ? v : null
  })
}

const loadSeries = computed<ChartSeries[]>(() => [
  { label: 'Load average (1 мин)', data: series('load1'), color: '--p-blue-500' },
  { label: 'CPU, %', data: series('cpu_percent'), color: '--p-orange-500', rightAxis: true },
])
const memSeries = computed<ChartSeries[]>(() => [{ label: 'Память, %', data: percentSeries('mem_used', 'mem_total'), color: '--p-purple-500', fill: true }])
const diskSeries = computed<ChartSeries[]>(() => [
  { label: 'Система, %', data: percentSeries('disk_used', 'disk_total'), color: '--p-teal-500' },
  { label: 'Почта (vmail), %', data: percentSeries('vmail_used', 'vmail_total'), color: '--p-indigo-500' },
])
const queueSeries = computed<ChartSeries[]>(() => [
  { label: 'Активные', data: series('queue_active'), color: '--p-green-500' },
  { label: 'Отложенные', data: series('queue_deferred'), color: '--p-orange-500' },
])
const mailSeries = computed<ChartSeries[]>(() => [
  { label: 'Доставлено', data: series('delivered_1h'), color: '--p-green-500' },
  { label: 'Отправлено наружу', data: series('sent_out_1h'), color: '--p-blue-500' },
  { label: 'Отложено', data: series('deferred_1h'), color: '--p-yellow-500' },
  { label: 'Bounced', data: series('bounced_1h'), color: '--p-orange-500' },
  { label: 'Отклонено', data: series('rejected_1h'), color: '--p-red-500' },
])
const sessionsSeries = computed<ChartSeries[]>(() => [{ label: 'Сессии IMAP', data: series('sessions_imap'), color: '--p-cyan-500', fill: true }])

const charts = computed(() => [
  { key: 'load', title: 'Нагрузка', type: 'line' as const, series: loadSeries.value, rightAxisLabel: 'CPU, %', rightPercent: true },
  { key: 'mem', title: 'Память', type: 'line' as const, series: memSeries.value, percent: true },
  { key: 'disk', title: 'Диски', type: 'line' as const, series: diskSeries.value, percent: true },
  { key: 'queue', title: 'Очередь Postfix', type: 'line' as const, series: queueSeries.value },
  { key: 'mail', title: 'Почта в час', type: 'bar' as const, series: mailSeries.value, stacked: true },
  { key: 'sessions', title: 'Сессии IMAP', type: 'line' as const, series: sessionsSeries.value },
])

onMounted(() => {
  void load()
  void loadHistory()
  applyAutoRefresh()
})
onBeforeUnmount(() => clearInterval(refreshTimer))
</script>

<template>
  <div>
    <div class="toolbar">
      <h1 class="page-title" style="margin: 0">Состояние сервера</h1>
      <span v-if="overview?.host" class="muted mono">{{ overview.host.hostname }}</span>
      <div class="toolbar__spacer" />
      <label class="form__check" style="font-size: 0.9rem">
        <ToggleSwitch v-model="autoRefresh" />
        <span>Автообновление (30 с)</span>
      </label>
      <span v-if="updatedAt" class="form__hint">обновлено {{ updatedAt.toLocaleTimeString('ru-RU') }}</span>
      <Button label="Обновить" icon="pi pi-refresh" severity="secondary" outlined :loading="loading" @click="load" />
    </div>

    <Message v-if="overview && !overview.agent_ok" severity="error" :closable="false" style="margin-bottom: 1rem">
      Агент на хосте недоступен — метрики хоста, службы и очередь не получены{{ overview.detail ? `: ${overview.detail}` : '' }}.
    </Message>

    <div v-if="loading && !overview" class="stat-grid">
      <Skeleton v-for="i in 8" :key="i" height="6rem" border-radius="8px" />
    </div>

    <template v-else-if="overview">
      <!-- Плитки -->
      <div class="tiles">
        <div v-if="overview.host" class="card tile">
          <div class="tile__title"><i class="pi pi-microchip" /> CPU</div>
          <div class="tile__value">{{ overview.host.cpu_percent.toFixed(0) }}%</div>
          <div class="form__hint">load {{ overview.host.load.map((l) => l.toFixed(2)).join(' / ') }} · ядер: {{ overview.host.cpu_count }}</div>
          <ProgressBar :value="Math.min(100, Math.round(overview.host.cpu_percent))" :show-value="false" :class="fillClass(overview.host.cpu_percent)" class="tile__bar" />
        </div>

        <div v-if="overview.host" class="card tile">
          <div class="tile__title"><i class="pi pi-server" /> Память</div>
          <div class="tile__value">{{ memPercent }}%</div>
          <div class="form__hint">{{ formatBytes(overview.host.mem.used) }} из {{ formatBytes(overview.host.mem.total) }} · swap {{ formatBytes(overview.host.mem.swap_used) }} / {{ formatBytes(overview.host.mem.swap_total) }}</div>
          <ProgressBar :value="memPercent" :show-value="false" :class="fillClass(memPercent)" class="tile__bar" />
        </div>

        <div v-if="overview.host" class="card tile">
          <div class="tile__title"><i class="pi pi-database" /> Диски</div>
          <div v-for="d in overview.host.disks" :key="d.mount" class="tile__disk">
            <div class="tile__disk-head">
              <span class="mono">{{ d.mount }}</span>
              <span class="form__hint">{{ formatBytes(d.used) }} / {{ formatBytes(d.total) }} ({{ pct(d.used, d.total) }}%)</span>
            </div>
            <ProgressBar :value="pct(d.used, d.total)" :show-value="false" :class="fillClass(pct(d.used, d.total))" class="tile__bar" />
          </div>
        </div>

        <div v-if="overview.host" class="card tile">
          <div class="tile__title"><i class="pi pi-clock" /> Аптайм</div>
          <div class="tile__value">{{ formatUptime(overview.host.uptime_s) }}</div>
          <div class="form__hint mono">{{ overview.host.hostname }}</div>
        </div>

        <div v-if="overview.cert" class="card tile">
          <div class="tile__title">
            <i class="pi pi-verified" /> Сертификат
            <span class="toolbar__spacer" />
            <Tag :severity="certSeverity(overview.cert.days_left)" :value="`${overview.cert.days_left} дн.`" />
          </div>
          <div class="tile__value" style="font-size: 1.1rem">{{ overview.cert.subject }}</div>
          <div class="form__hint">действует до {{ formatDateTime(overview.cert.not_after) }}</div>
        </div>

        <div v-if="overview.queue" class="card tile">
          <div class="tile__title">
            <i class="pi pi-list" /> Очередь Postfix
            <span class="toolbar__spacer" />
            <RouterLink :to="{ name: 'queue' }" style="font-size: 0.85rem; font-weight: 400">открыть</RouterLink>
          </div>
          <div class="tile__value">{{ overview.queue.total }}</div>
          <div class="form__hint">активных {{ overview.queue.active }} · отложенных {{ overview.queue.deferred }} · hold {{ overview.queue.hold }} · входящих {{ overview.queue.incoming }}</div>
        </div>

        <div v-if="overview.sessions" class="card tile">
          <div class="tile__title"><i class="pi pi-users" /> Сессии IMAP</div>
          <div class="tile__value">{{ overview.sessions.imap }}</div>
          <div class="form__hint">пользователей: {{ overview.sessions.users }}<template v-for="(n, proto) in overview.sessions.by_proto" :key="proto"> · {{ proto }}: {{ n }}</template></div>
        </div>

        <div class="card tile">
          <div class="tile__title"><i class="pi pi-table" /> База данных</div>
          <div class="tile__value">{{ formatBytes(overview.db.size_bytes) }}</div>
          <div class="form__hint">ящиков {{ formatNumber(overview.db.mailboxes) }} · писем {{ formatNumber(overview.db.messages_total) }}</div>
        </div>

        <div class="card tile">
          <div class="tile__title"><i class="pi pi-bolt" /> Redis</div>
          <template v-if="overview.redis">
            <div class="tile__value">{{ formatBytes(overview.redis.used_memory) }}</div>
            <div class="form__hint">ключей {{ formatNumber(overview.redis.keys) }} · аптайм {{ formatUptime(overview.redis.uptime_s) }}</div>
          </template>
          <div v-else class="muted">недоступен</div>
        </div>
      </div>

      <div class="dash-grid">
        <!-- Службы -->
        <div class="card">
          <h2 class="card__title"><i class="pi pi-cog" /> Службы</h2>
          <div v-if="services.length" class="chips">
            <Tag v-for="s in services" :key="s.name" :severity="serviceSeverity(s.state)" :value="`${s.label}: ${s.stateLabel}`" v-tooltip.top="s.name" />
          </div>
          <p v-else class="muted" style="margin: 0">Состояние служб недоступно</p>
        </div>

        <!-- Почта за сутки -->
        <div class="card">
          <h2 class="card__title"><i class="pi pi-envelope" /> Почта за {{ overview.mail?.hours ?? 24 }} ч</h2>
          <div v-if="overview.mail" class="counters">
            <div><span class="counters__value" style="color: var(--p-green-500)">{{ formatNumber(overview.mail.delivered) }}</span><span class="form__hint">доставлено</span></div>
            <div><span class="counters__value" style="color: var(--p-blue-500)">{{ formatNumber(overview.mail.sent_out) }}</span><span class="form__hint">наружу</span></div>
            <div><span class="counters__value" style="color: var(--p-red-500)">{{ formatNumber(overview.mail.rejected) }}</span><span class="form__hint">отклонено</span></div>
            <div><span class="counters__value" style="color: var(--p-yellow-500)">{{ formatNumber(overview.mail.deferred) }}</span><span class="form__hint">отложено</span></div>
            <div><span class="counters__value" style="color: var(--p-orange-500)">{{ formatNumber(overview.mail.bounced) }}</span><span class="form__hint">bounced</span></div>
          </div>
          <p v-else class="muted" style="margin: 0">Статистика по логу недоступна</p>

          <h3 style="margin: 1rem 0 0.5rem; font-size: 0.95rem">Баны fail2ban</h3>
          <table v-if="fail2ban.length" class="f2b">
            <thead><tr><th>Jail</th><th>Сейчас</th><th>Всего</th></tr></thead>
            <tbody>
              <tr v-for="j in fail2ban" :key="j.jail">
                <td class="mono">{{ j.jail }}</td>
                <td>{{ j.banned }}</td>
                <td>{{ j.total }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else class="muted" style="margin: 0">Нет данных fail2ban</p>
        </div>
      </div>

      <!-- Антиспам -->
      <div class="card" style="margin-top: 1rem">
        <h2 class="card__title">
          <i class="pi pi-shield" /> Антиспам
          <span class="toolbar__spacer" />
          <RouterLink :to="{ name: 'filter' }" style="font-size: 0.9rem; font-weight: 400">Фильтр</RouterLink>
        </h2>
        <RspamdStatsCards v-if="overview.rspamd" :stats="overview.rspamd" />
        <p v-else class="muted" style="margin: 0">Rspamd недоступен</p>
      </div>
    </template>

    <!-- Графики -->
    <div class="toolbar" style="margin-top: 1.5rem">
      <h2 style="margin: 0; font-size: 1.2rem">История</h2>
      <div class="toolbar__spacer" />
      <SelectButton v-model="hours" :options="hoursOptions" option-label="label" option-value="value" :allow-empty="false" size="small" />
      <Button icon="pi pi-refresh" severity="secondary" outlined :loading="historyLoading" aria-label="Обновить графики" @click="loadHistory" />
    </div>
    <p v-if="!historyLoading && !hasPoints" class="muted">Данных пока нет, выборки копятся раз в 5 минут.</p>
    <div v-else class="dash-grid" style="margin-top: 0">
      <div v-for="c in charts" :key="c.key" class="card">
        <h3 class="card__title" style="font-size: 0.95rem">{{ c.title }}</h3>
        <Skeleton v-if="historyLoading && !hasPoints" height="220px" />
        <SystemChart
          v-else
          :type="c.type"
          :labels="labels"
          :series="c.series"
          :percent="c.percent"
          :stacked="c.stacked"
          :right-axis-label="c.rightAxisLabel"
          :right-percent="c.rightPercent"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 1rem;
}

.tile {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  min-width: 0;
}

.tile__title {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
  font-weight: 600;
  color: var(--p-text-muted-color);
  font-size: 0.9rem;
  min-width: 0;
}

.tile .form__hint,
.tile__disk-head {
  overflow-wrap: anywhere;
  min-width: 0;
}

.tile__title .pi {
  color: var(--p-primary-color);
}

.tile__value {
  font-size: 1.5rem;
  font-weight: 600;
  line-height: 1.2;
  word-break: break-word;
}

.tile__bar {
  height: 6px;
  margin-top: 0.25rem;
}

.tile__disk {
  margin-top: 0.25rem;
}

.tile__disk-head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.25rem 0.5rem;
  font-size: 0.85rem;
}

.counters {
  display: flex;
  flex-wrap: wrap;
  gap: 1.25rem;
}

.counters > div {
  display: flex;
  flex-direction: column;
}

.counters__value {
  font-size: 1.4rem;
  font-weight: 600;
  line-height: 1.1;
}

.f2b {
  border-collapse: collapse;
  font-size: 0.9rem;
  width: 100%;
}

.f2b th {
  text-align: left;
  color: var(--p-text-muted-color);
  font-weight: 500;
  padding: 0.25rem 1rem 0.25rem 0;
  border-bottom: 1px solid var(--app-card-border);
}

.f2b td {
  padding: 0.3rem 1rem 0.3rem 0;
  border-bottom: 1px solid var(--app-card-border);
}
</style>

<style>
/* Цвет заполнения ProgressBar по уровню (глобально: PrimeVue ставит класс на корневой элемент) */
.p-progressbar.bar-warn .p-progressbar-value {
  background: var(--p-orange-500);
}

.p-progressbar.bar-danger .p-progressbar-value {
  background: var(--p-red-500);
}
</style>
