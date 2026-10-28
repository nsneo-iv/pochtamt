// Типы объектов контракта REST API (docs/api.md). Поля названы строго как в контракте.

/** Роль администратора: superadmin — все домены, domain_admin — только свои (поле domains) */
export type Role = 'superadmin' | 'domain_admin'

export interface User {
  login: string
  display_name: string
  role: Role
  /** Домены, которыми управляет domain_admin; у superadmin отсутствует */
  domains?: string[]
}

export interface LoginRequest {
  login: string
  password: string
}

/** GET /auth/config — возможности сервера, без авторизации */
export interface AuthConfig {
  /** Настроен ли Active Directory: вход доменной учёткой, ящики auth=ad, синхронизация */
  ad_enabled: boolean
  /** Подсказка в поле логина */
  login_hint: string
}

export interface LoginResponse {
  token: string
  user: User
}

// ---- Домены ----

export interface Domain {
  name: string
  description: string | null
  max_mailboxes: number | null
  max_quota_mb: number | null
  active: boolean
  created_at: string
}

export interface DomainStats {
  mailboxes: number
  aliases: number
  used_mb: number
}

/** GET /domains/{name} дополнительно отдаёт статистику */
export interface DomainDetail extends Domain {
  stats: DomainStats
}

export interface DomainCreate {
  name: string
  description?: string | null
  max_mailboxes?: number | null
  max_quota_mb?: number | null
  active?: boolean
}

export type DomainUpdate = Omit<DomainCreate, 'name'>

export interface Dkim {
  selector: string
  /** Имя TXT-записи: <selector>._domainkey.<domain> */
  dns_name: string
  /** Готовое значение TXT-записи */
  dns_value: string
  created_at: string
}

export interface DkimCreate {
  /** Селектор, по умолчанию mail */
  selector?: string
}

// ---- Дашборд домена ----

/** Статус DNS-записи: ok — всё верно, warn — есть замечания, missing — записи нет, error — ошибка проверки */
export type DnsStatus = 'ok' | 'warn' | 'missing' | 'error'

export interface DnsCheck {
  status: DnsStatus
  /** Найденная запись (одна) */
  record?: string | null
  /** Найденные записи (несколько, например MX) */
  records?: string[] | null
  /** Ожидаемое/рекомендуемое значение, если своего нет или оно неверно */
  expected?: string | null
  /** Имя записи (для DKIM: <selector>._domainkey.<domain>) */
  name?: string | null
  /** Запись найдена в DNS */
  found?: boolean | null
  /** Для DKIM: ключ в DNS совпадает с ключом сервера */
  matches?: boolean | null
  /** Пояснение от бэкенда */
  detail?: string | null
}

export interface DomainDashboardStats {
  mailboxes: number
  mailboxes_active: number
  mailboxes_ad: number
  aliases: number
  lists: number
  used_mb: number
  /** Сумма квот ящиков с лимитом, МБ */
  quota_mb: number
  /** Ящиков без лимита */
  unlimited: number
}

export interface TopMailbox {
  address: string
  name: string
  used_mb: number
  quota_mb: number | null
  /** Процент заполнения квоты; null — лимита нет */
  percent: number | null
  active: boolean
}

export interface DomainDashboard {
  domain: Domain
  stats: DomainDashboardStats
  dkim: Dkim | null
  dns: {
    mx: DnsCheck
    spf: DnsCheck
    dkim: DnsCheck
    dmarc: DnsCheck
  }
  /** До 10 ящиков по занятому месту */
  top_mailboxes: TopMailbox[]
  /** Последние 10 действий по объектам домена */
  recent_audit: AuditItem[]
}

// ---- Ящики ----

/** local — пароль в базе, ad — пароль проверяет Dovecot в AD по ad_upn */
export type MailboxAuth = 'local' | 'ad'

export interface Mailbox {
  address: string
  domain: string
  name: string
  auth: MailboxAuth
  ad_upn: string | null
  quota_mb: number | null
  used_mb: number
  active: boolean
  created_at: string
}

export interface MailboxCreate {
  address: string
  name: string
  auth: MailboxAuth
  password?: string
  ad_upn?: string | null
  quota_mb?: number | null
  active?: boolean
}

export interface MailboxUpdate {
  name?: string
  quota_mb?: number | null
  active?: boolean
  auth?: MailboxAuth
  ad_upn?: string | null
}

export interface MailboxFilter {
  domain?: string
  q?: string
}

export interface PasswordChange {
  password: string
}

// ---- Алиасы ----

export interface Alias {
  /** Catch-all: "@domain"; пересылка с ящика — адрес ящика */
  address: string
  domain: string
  targets: string[]
  description: string | null
  active: boolean
  created_at: string
}

export interface AliasCreate {
  address: string
  targets: string[]
  description?: string | null
  active?: boolean
}

export interface AliasUpdate {
  targets?: string[]
  description?: string | null
  active?: boolean
}

export type AliasFilter = MailboxFilter

// ---- Доменные алиасы ----

export interface DomainAlias {
  alias_domain: string
  target_domain: string
  active: boolean
}

export interface DomainAliasCreate {
  alias_domain: string
  target_domain: string
}

// ---- Рассылки (группы) ----

export interface MailingList {
  address: string
  domain: string
  name: string
  members: string[]
  /** DN группы AD; если задан — состав обновляется синхронизацией и вручную не правится */
  ad_group: string | null
  active: boolean
  synced_at: string | null
}

export interface MailingListCreate {
  address: string
  name: string
  members: string[]
  ad_group?: string | null
  active?: boolean
}

export interface MailingListUpdate {
  name?: string
  members?: string[]
  ad_group?: string | null
  active?: boolean
}

// ---- Синхронизация с AD ----

/** Элементы списков синхронизации: точный состав определяет бэкенд, показываем как есть */
export type AdSyncItem = string | Record<string, unknown>

export interface AdSyncResult {
  create: AdSyncItem[]
  update: AdSyncItem[]
  disable: AdSyncItem[]
  lists: AdSyncItem[]
}

// ---- Очередь Postfix ----

export interface QueueItem {
  id: string
  sender: string
  recipients: string[]
  /** Размер письма в байтах */
  size: number
  arrival: string
  reason: string | null
}

// ---- Аудит и сводка ----

export interface AuditItem {
  ts: string
  actor: string
  action: string
  object: string
  details: unknown
}

export interface AuditPage {
  items: AuditItem[]
  total: number
}

export interface AuditQuery {
  limit: number
  offset: number
  actor?: string
  object?: string
}

/** Счётчики Rspamd с момента запуска; uptime в секундах */
export interface RspamdStats {
  scanned: number
  ham: number
  spam: number
  reject: number
  /** Помечено как спам (в карантин) */
  add_header: number
  greylist: number
  no_action: number
  learned: number
  connections: number
  uptime: number
}

// ---- Спам-фильтр и антивирус (только суперадмин) ----

/** Пороги баллов: до greylist проходит, от add_header — в Junk, от reject — отказ на SMTP */
export interface FilterActions {
  greylist: number
  add_header: number
  reject: number
}

export interface FilterSymbol {
  name: string
  score: number
  description: string | null
  group: string | null
  /** Частота срабатывания */
  frequency: number | null
}

export interface FilterSymbolUpdate {
  name: string
  score: number
}

/** whitelist_from / blacklist_from — адрес или домен; whitelist_ip / blacklist_ip — адрес или CIDR */
export type FilterListId = 'whitelist_from' | 'blacklist_from' | 'whitelist_ip' | 'blacklist_ip'

export interface FilterList {
  id: FilterListId
  title: string
  description: string | null
  entries: string[]
  count: number
  /** false — карта не найдена в Rspamd, редактирование недоступно */
  available: boolean
}

export type FilterHistoryAction = 'no action' | 'greylist' | 'add header' | 'reject' | 'soft reject'

export interface FilterHistorySymbol {
  name: string
  score: number
}

export interface FilterHistoryRow {
  /** Unix-время в секундах */
  time: number
  ip: string | null
  user: string | null
  sender: string | null
  recipients: string[]
  subject: string | null
  score: number
  required_score: number
  action: FilterHistoryAction
  size: number
  /** Отсортированы по модулю балла */
  symbols: FilterHistorySymbol[]
  scan_time: number | null
  message_id: string | null
}

export interface FilterHistoryQuery {
  limit?: number
  action?: FilterHistoryAction
  q?: string
}

export interface Antivirus {
  /** ClamAV настроен и доступен */
  available: boolean
  daemon_active: boolean
  engine_version: string | null
  db_version: string | null
  db_date: string | null
  signatures: number | null
  /** Вес символа CLAMAV */
  virus_score: number | null
  detail?: string | null
}

export interface FilterOverview {
  stats: RspamdStats | null
  actions: FilterActions
  antivirus: Antivirus
}

// ---- Настройки домена ----

export interface DomainSettings {
  /** smtp:[host]:port — relay на другой сервер; null — локальная доставка */
  transport: string | null
  /** Скрытая копия всех писем домена */
  bcc_address: string | null
  /** false — пользователи домена пишут только на адреса этого сервера */
  outbound_allowed: boolean
}

// ---- Настройки ящика и личный кабинет ----

/** normal — обычный, receive_only — не может отправлять, send_only — не принимает, internal — пишет только внутрь сервера */
export type MailboxMode = 'normal' | 'receive_only' | 'send_only' | 'internal'

export interface Autoreply {
  enabled: boolean
  subject: string | null
  body: string | null
  /** Дата YYYY-MM-DD или null */
  date_from: string | null
  date_to: string | null
}

export interface Forward {
  targets: string[]
  keep_copy: boolean
}

export interface MailboxSettings {
  address: string
  mode: MailboxMode
  autoreply: Autoreply
  forward: Forward
  /** Пользовательские правила Sieve (текст) */
  sieve_custom: string | null
  bcc_address: string | null
  sieve_synced_at: string | null
  /** Заполнен, если скрипт не удалось залить через ManageSieve; остальное сохранено */
  sieve_error: string | null
}

/** PUT /mailboxes/{address}/settings — только изменённые секции */
export interface MailboxSettingsUpdate {
  mode?: MailboxMode
  autoreply?: Autoreply
  forward?: Forward
  sieve_custom?: string | null
  bcc_address?: string | null
}

/** PUT /me/settings — пользователь не меняет режим и BCC */
export type MeSettingsUpdate = Pick<MailboxSettingsUpdate, 'autoreply' | 'forward' | 'sieve_custom'>

export interface Me {
  address: string
  name: string
  domain: string
  auth: MailboxAuth
  quota_mb: number | null
  used_mb: number
  messages: number
  mode: MailboxMode
}

export interface MeLoginRequest {
  address: string
  password: string
}

export interface MeLoginResponse {
  token: string
  me: Me
}

// ---- Настройки сервера (только суперадмин) ----

export interface Smarthost {
  enabled: boolean
  host: string | null
  port: number | null
  user: string | null
  /** Пароль в ответе не отдаётся, только признак */
  password_set: boolean
}

export interface SmarthostUpdate {
  enabled: boolean
  host: string | null
  port: number | null
  user: string | null
  /** Опущен = не менять */
  password?: string
}

export type TlsPolicyName = 'none' | 'may' | 'encrypt' | 'dane' | 'dane-only' | 'verify' | 'secure'

export interface TlsPolicy {
  domain: string
  policy: TlsPolicyName
  /** Доп. параметры Postfix, например match=.example.com */
  params: string | null
  comment: string | null
  updated_at: string | null
}

export type TlsPolicyUpdate = Omit<TlsPolicy, 'updated_at'>

export type AccessRuleKind = 'client' | 'sender' | 'recipient'
export type AccessRuleAction = 'OK' | 'REJECT' | 'DISCARD'

export interface AccessRule {
  id: number
  kind: AccessRuleKind
  /** client — IP или префикс сети (10.0.5); sender/recipient — адрес или домен */
  pattern: string
  action: AccessRuleAction
  /** Текст отказа (только для REJECT) */
  message: string | null
  comment: string | null
  active: boolean
}

export type AccessRuleCreate = Omit<AccessRule, 'id'>

export type ServerParamType = 'int' | 'enum' | 're'

export interface ServerParam {
  key: string
  value: string
  service: string
  type: ServerParamType
  label: string
  group: string
  /** Для enum — допустимые значения */
  values?: string[]
  min?: number
  max?: number
}

// ---- Состояние сервера (только суперадмин) ----

export interface SystemHost {
  hostname: string
  uptime_s: number
  /** load average за 1, 5 и 15 минут */
  load: [number, number, number] | number[]
  cpu_count: number
  cpu_percent: number
  /** Байты */
  mem: { total: number; used: number; available: number; swap_total: number; swap_used: number }
  disks: { mount: string; total: number; used: number; free: number }[]
}

/** Состояние systemd-службы: active | inactive | failed | … */
export type ServiceState = string

export interface SystemOverview {
  /** null, если агент недоступен (agent_ok=false) */
  host: SystemHost | null
  services: Record<string, ServiceState>
  queue: { active: number; deferred: number; hold: number; incoming: number; total: number } | null
  sessions: { imap: number; users: number; by_proto: Record<string, number> } | null
  /** Счётчики по логу Postfix за hours часов */
  mail: { delivered: number; sent_out: number; bounced: number; deferred: number; rejected: number; hours: number } | null
  cert: { subject: string; not_after: string; days_left: number } | null
  fail2ban: Record<string, { banned: number; total: number }> | null
  db: { size_bytes: number; mailboxes: number; messages_total: number }
  redis: { used_memory: number; keys: number; uptime_s: number } | null
  rspamd: RspamdStats | null
  /** false — метрики хоста недоступны, detail объясняет почему */
  agent_ok: boolean
  detail?: string | null
}

/** Выборка таймера (раз в 5 минут) */
export interface SystemSample {
  ts: string
  load1: number | null
  cpu_percent: number | null
  mem_used: number | null
  mem_total: number | null
  disk_used: number | null
  disk_total: number | null
  vmail_used: number | null
  vmail_total: number | null
  queue_active: number | null
  queue_deferred: number | null
  sessions_imap: number | null
  delivered_1h: number | null
  sent_out_1h: number | null
  bounced_1h: number | null
  deferred_1h: number | null
  rejected_1h: number | null
  rspamd_scanned: number | null
  rspamd_spam: number | null
}

export interface SystemHistory {
  points: SystemSample[]
}

export interface Stats {
  domains: number
  mailboxes: number
  aliases: number
  lists: number
  queue: number
  used_mb: number
  /** Только суперадмину; null, если Rspamd недоступен */
  rspamd: RspamdStats | null
}
