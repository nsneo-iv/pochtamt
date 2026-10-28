# Контракт REST API бэкенда

Базовый префикс: `/api/v1`. Формат: JSON. Ошибки: `{"detail": "текст"}` с кодом 4xx/5xx.
Авторизация: `Authorization: Bearer <JWT>`; токен выдаёт `POST /auth/login`.
Фронт в dev-режиме проксирует `/api` на `http://127.0.0.1:8000`.

## Авторизация

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| GET | `/auth/config` | — (без авторизации) | `{ad_enabled, login_hint}` — настроен ли AD; фронт прячет разделы AD |
| POST | `/auth/login` | `{login, password}` | `{token, user}`; 401 — неверно; 429 — слишком много неудач (15 мин) |
| GET | `/auth/me` | — | `user` |

`user = {login, display_name, role}`; `role` ∈ `superadmin` (все домены), `domain_admin` (домены из `domains: [..]`).
Логин — локальный (`admin`, пароль в `admins.password_hash`) или доменная учётка AD (`user@corp.local`,
`CORP\user`; пароль проверяет AD, если он настроен); роль берётся из таблицы `admins`.

## Домены

| Метод | Путь | Тело / параметры | Ответ |
|---|---|---|---|
| GET | `/domains` | — | `[domain]` |
| POST | `/domains` | `{name, description?, max_mailboxes?, max_quota_mb?, active?}` | `domain` |
| GET | `/domains/{name}` | — | `domain` (+ `stats: {mailboxes, aliases, used_mb}`) |
| PUT | `/domains/{name}` | любые поля кроме `name` | `domain` |
| DELETE | `/domains/{name}` | — | 204 (отказ 409, если есть ящики) |
| GET | `/domains/{name}/dkim` | — | `dkim \| null` |
| POST | `/domains/{name}/dkim` | `{selector?}` (по умолчанию `mail`) | `dkim` |
| DELETE | `/domains/{name}/dkim` | — | 204 |
| GET | `/domains/{name}/dashboard` | — | `dashboard` (сводка домена, см. ниже) |

`domain = {name, description, max_mailboxes, max_quota_mb, active, created_at}`
`dkim = {selector, dns_name, dns_value, created_at}` — `dns_name` = `<selector>._domainkey.<domain>`, `dns_value` = готовая TXT-запись.

### Дашборд домена

```
dashboard = {
  domain,                                   // объект domain
  stats: {mailboxes, mailboxes_active, mailboxes_ad, aliases, lists, used_mb, quota_mb, unlimited},
  dkim: dkim | null,
  dns: {mx, spf, dkim, dmarc},              // каждая: {status: ok|warn|missing|error, record?, records?, expected?,
                                            //           name?, found?, matches?, detail?}
  top_mailboxes: [{address, name, used_mb, quota_mb, percent, active}],   // до 10, по занятому месту
  recent_audit: [{ts, actor, action, object, details}]                   // последние 10 по объектам домена
}
```
`dns.mx.expected` — имя почтового хоста; `dns.spf.expected` и `dns.dmarc.expected` — рекомендуемая запись,
если своей нет; `dns.dkim.name` — имя TXT-записи, `matches` — совпадает ли ключ в DNS с ключом сервера.
Проверка DNS идёт при каждом запросе (до ~8 с при недоступном DNS), фронт показывает её отдельным блоком.

## Ящики

| Метод | Путь | Тело / параметры | Ответ |
|---|---|---|---|
| GET | `/mailboxes?domain=&q=` | фильтр по домену и подстроке | `[mailbox]` |
| POST | `/mailboxes` | `{address, name, auth, password?, ad_upn?, quota_mb?, active?}` | `mailbox` |
| GET | `/mailboxes/{address}` | — | `mailbox` |
| PUT | `/mailboxes/{address}` | `{name?, quota_mb?, active?, auth?, ad_upn?}` | `mailbox` |
| POST | `/mailboxes/{address}/password` | `{password}` | 204 (только `auth=local`) |
| DELETE | `/mailboxes/{address}` | — | 204 |

`mailbox = {address, domain, name, auth, ad_upn, quota_mb, used_mb, active, created_at}`
`auth` ∈ `local` (пароль в базе) | `ad` (пароль проверяет Dovecot в AD по `ad_upn`).

## Алиасы и пересылки

| Метод | Путь | Тело / параметры | Ответ |
|---|---|---|---|
| GET | `/aliases?domain=&q=` | — | `[alias]` |
| POST | `/aliases` | `{address, targets: [email], description?, active?}` | `alias` |
| GET | `/aliases/{address}` | — | `alias` |
| PUT | `/aliases/{address}` | `{targets?, description?, active?}` | `alias` |
| DELETE | `/aliases/{address}` | — | 204 |

`alias = {address, domain, targets, description, active, created_at}`.
Catch-all: `address = "@domain"`. Пересылка с ящика наружу — тот же объект с `address` = адрес ящика.

## Доменные алиасы

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| GET | `/domain-aliases` | — | `[{alias_domain, target_domain, active}]` |
| POST | `/domain-aliases` | `{alias_domain, target_domain}` | объект |
| DELETE | `/domain-aliases/{alias_domain}` | — | 204 |

## Рассылки (группы)

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| GET | `/lists?domain=` | — | `[list]` |
| POST | `/lists` | `{address, name, members: [email], ad_group?, active?}` | `list` |
| PUT | `/lists/{address}` | `{name?, members?, ad_group?, active?}` | `list` |
| DELETE | `/lists/{address}` | — | 204 |

`list = {address, domain, name, members, ad_group, active, synced_at}`; если задан `ad_group` (DN группы AD),
состав обновляется синхронизацией и вручную не правится.

## Синхронизация с AD

| Метод | Путь | Ответ |
|---|---|---|
| GET | `/ad/sync/preview` | `{create: [..], update: [..], disable: [..], lists: [..]}` |
| POST | `/ad/sync` | то же, что применено |

## Очередь Postfix (через агент на хосте)

| Метод | Путь | Ответ |
|---|---|---|
| GET | `/queue` | `[{id, sender, recipients, size, arrival, reason}]` |
| POST | `/queue/flush` | 204 |
| DELETE | `/queue/{id}` | 204 |

## Аудит и сводка

| Метод | Путь | Параметры | Ответ |
|---|---|---|---|
| GET | `/audit` | `limit, offset, actor?, object?` | `{items: [{ts, actor, action, object, details}], total}` |
| GET | `/stats` | — | `{domains, mailboxes, aliases, lists, queue, used_mb, rspamd}` |

`rspamd` (только суперадмину, иначе `null`; `null` и если Rspamd недоступен) = `{scanned, ham, spam, reject, add_header, greylist, no_action, learned, connections, uptime}` — счётчики антиспама и антивируса с момента запуска Rspamd; `uptime` в секундах.

## Спам-фильтр и антивирус (только суперадмин)

Всё хранит и применяет сам Rspamd (его контроллер), бэкенд — прокси с проверкой прав и аудитом.

| Метод | Путь | Тело / параметры | Ответ |
|---|---|---|---|
| GET | `/filter/overview` | — | `{stats, actions, antivirus}` |
| GET | `/filter/actions` | — | `actions` |
| PUT | `/filter/actions` | `{greylist, add_header, reject}` (возрастают) | `actions` |
| GET | `/filter/symbols?q=` | фильтр по имени/описанию | `[{name, score, description, group, frequency}]` |
| PUT | `/filter/symbols` | `[{name, score}]` | 204 |
| GET | `/filter/lists` | — | `[list]` |
| PUT | `/filter/lists/{id}` | `{entries: [..]}` | `list` |
| GET | `/filter/history?limit=&action=&q=` | `action` ∈ `no action, greylist, add header, reject, soft reject` | `[row]` |
| POST | `/filter/learn/{spam\|ham}` | тело — письмо целиком, `text/plain` | 204 |
| GET | `/filter/antivirus` | — | `antivirus` |
| POST | `/filter/antivirus/update` | — | 202 (перезапуск freshclam) |

`actions = {greylist, add_header, reject}` — пороги баллов: до greylist письмо проходит, от add_header
помечается спамом (уходит в Junk), от reject отклоняется на SMTP.
`list = {id, title, description, entries: [..], count, available}`; `id` ∈ `whitelist_from`, `blacklist_from`
(адрес или домен), `whitelist_ip`, `blacklist_ip` (адрес или CIDR). `available=false` — карта не найдена в Rspamd.
`row = {time (unix), ip, user, sender, recipients, subject, score, required_score, action, size,
symbols: [{name, score}], scan_time, message_id}` — новые сверху; `symbols` отсортированы по модулю балла.
`antivirus = {available, daemon_active, engine_version, db_version, db_date, signatures, virus_score, detail?}`;
`virus_score` — вес символа `CLAMAV`; сам по себе он не важен: модуль antivirus настроен на `action = reject`,
письмо с вирусом отклоняется независимо от баллов.

## Настройки домена

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| GET | `/domains/{name}/settings` | — | `domain_settings` |
| PUT | `/domains/{name}/settings` | `domain_settings` (суперадмин) | `domain_settings` |

`domain_settings = {transport, bcc_address, outbound_allowed}`: `transport` — `smtp:[host]:port` для relay на другой
сервер или `null` (локальная доставка); `bcc_address` — скрытая копия всех писем домена; `outbound_allowed=false` —
пользователи домена пишут только на адреса этого сервера.

## Настройки ящика (админ) и личный кабинет

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| GET | `/mailboxes/{address}/settings` | — | `mailbox_settings` |
| PUT | `/mailboxes/{address}/settings` | `{mode?, autoreply?, forward?, sieve_custom?, bcc_address?}` | `mailbox_settings` |
| POST | `/me/login` | `{address, password}` | `{token, me}`; 401 / 429 как у `/auth/login` |
| GET | `/me` | — | `me` |
| POST | `/me/password` | `{current_password, password}` (только auth=local; неверный текущий — 403, после 5 неудач — 429) | 204 |
| GET | `/me/settings` | — | `mailbox_settings` |
| PUT | `/me/settings` | `{autoreply?, forward?, sieve_custom?}` | `mailbox_settings` |

Токен кабинета — отдельного типа (`typ=user`), в админские эндпоинты не пускает, и наоборот.
`mailbox_settings = {address, mode, autoreply: {enabled, subject, body, date_from, date_to}, forward: {targets, keep_copy},
sieve_custom, bcc_address, sieve_synced_at, sieve_error}`; `mode` ∈ `normal` | `receive_only` (не может отправлять) |
`send_only` (не принимает) | `internal` (пишет только внутрь сервера). `sieve_custom` — пользовательские правила Sieve
(текст), проверяются на сервере при сохранении (422 с текстом ошибки). После сохранения автоответа/правил скрипт
заливается через ManageSieve; если не удалось — `sieve_error` заполнен, остальное сохранено.
`me = {address, name, domain, auth, quota_mb, used_mb, messages, mode}`.

## Настройки сервера (только суперадмин)

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| GET | `/server/smarthost` | — | `smarthost` |
| PUT | `/server/smarthost` | `{enabled, host, port, user, password?}` | `smarthost` |
| GET | `/server/tls-policies` | — | `[{domain, policy, params, comment, updated_at}]` |
| PUT | `/server/tls-policies/{domain}` | `{domain, policy, params, comment}` | объект |
| DELETE | `/server/tls-policies/{domain}` | — | 204 |
| GET | `/server/access-rules?kind=` | `kind` ∈ `client, sender, recipient` | `[rule]` |
| POST | `/server/access-rules` | `{kind, pattern, action, message, comment, active}` | `rule` |
| PUT | `/server/access-rules/{id}` | то же | `rule` |
| DELETE | `/server/access-rules/{id}` | — | 204 |
| GET | `/server/params` | — | `[param]` |
| PUT | `/server/params/{key}` | `{value}` | `param` |

`smarthost` — исходящая почта через внешний релей: `password` в ответе не отдаётся, есть `password_set`; в PUT `password`
опущен = не менять. `policy` ∈ `none, may, encrypt, dane, dane-only, verify, secure`, `params` — доп. параметры Postfix
(например `match=.example.com`). `rule.pattern`: для `client` — IP или префикс сети (`10.0.5`), для `sender`/`recipient` —
адрес или домен; `action` ∈ `OK, REJECT, DISCARD`. `param = {key, value, service, type (int|enum|re), label, group,
values?, min?, max?}` — глобальные параметры Postfix/Dovecot из белого списка; применяются сразу (reload).

## Состояние сервера (только суперадмин)

| Метод | Путь | Параметры | Ответ |
|---|---|---|---|
| GET | `/system/overview` | — | `overview` |
| GET | `/system/history` | `hours` (1..168, по умолчанию 24) | `{points: [sample]}` |

```
overview = {
  host: {hostname, uptime_s, load: [l1, l5, l15], cpu_count, cpu_percent,
         mem: {total, used, available, swap_total, swap_used},            // байты
         disks: [{mount, total, used, free}]},
  services: {postfix: "active"|"inactive"|"failed"|…, dovecot, rspamd, clamav-daemon, …},
  queue: {active, deferred, hold, incoming, total},
  sessions: {imap, users, by_proto: {imap: n, …}},
  mail: {delivered, sent_out, bounced, deferred, rejected, hours: 24},  // по логу Postfix
  cert: {subject, not_after, days_left},
  fail2ban: {<jail>: {banned, total}},
  db: {size_bytes, mailboxes, messages_total},                         // messages_total — из mailbox_usage
  redis: {used_memory, keys, uptime_s} | null,
  rspamd: RspamdStats | null,
  agent_ok: bool, detail?: str                                          // agent_ok=false — метрики хоста недоступны
}
sample = {ts, load1, cpu_percent, mem_used, mem_total, disk_used, disk_total, vmail_used, vmail_total,
          queue_active, queue_deferred, sessions_imap, delivered_1h, sent_out_1h, bounced_1h, deferred_1h,
          rejected_1h, rspamd_scanned, rspamd_spam}
```
Выборки пишет таймер раз в 5 минут (`cli system-sample`), хранятся 30 дней; `history` отдаёт точки по порядку времени.
