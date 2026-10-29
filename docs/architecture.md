# Архитектура

```
                 интернет                                        свои сети (LAN_NETS / VPN)
                    │                                                     │
            25  465  587  993  80(ACME)                     https://<ADMIN_HOSTNAME>/  (панель, /me, /rspamd/)
                    │                                                     │
   ┌────────────────▼──────────────────── почтовый хост ──────────────────▼──────────────────┐
   │                                                                                         │
   │  Postfix ──milter──▶ Rspamd ◀──ключи DKIM, байес── Redis ◀────────┐                     │
   │     │ LMTP            │ ClamAV (unix-сокет)                       │                     │
   │     ▼                 ▼                                           │     nginx           │
   │  Dovecot (IMAP 993, LMTP, ManageSieve 4190, квоты, Sieve)         │      ├─ /       фронт (Vue)      │
   │     │ passdb sql (+ passdb ldap ──▶ AD, если настроен)            │      ├─ /api ─▶ бэкенд (FastAPI) │
   │     │                                                             │      └─ /rspamd ─▶ контроллер   │
   │     ▼ SELECT из представлений (роли mail_postfix / mail_dovecot)  │                │                │
   │  PostgreSQL «mail» ◀──────── INSERT/UPDATE (роль mail_app) ───────┴────────────────┘                │
   │                                                                                    │                │
   │  агент 127.0.0.1:8025 (sudo-белый список: postqueue, postsuper, doveadm, …) ◀──────┘                │
   │  unbound 127.0.0.1 (DNSSEC → DANE), certbot, fail2ban, nftables, systemd-таймеры                    │
   │  [SOGo в Docker, сеть хоста, 127.0.0.1:20000] ──IMAP 143 / SMTP 587 / PostgreSQL──▶ (необязательно)   │
   └─────────────────────────────────────────────────────────────────────────────────────────────────────┘
          ▲
          │ IMAP/SMTP/ManageSieve как обычный клиент
   веб-почта (отдельный хост, Roundcube) — docs/webmail.md
```

## Компоненты

| Компонент | Роль | Откуда конфиг |
|---|---|---|
| PostgreSQL, база `mail` | единственный источник правды: домены, ящики, алиасы, рассылки, DKIM, админы, аудит, настройки сервера | `db/schema.sql`, `db/schema_settings.sql`, роли `db/roles.sql` |
| Postfix 3.10 | SMTP: приём на 25, отправка на 465/587 с SASL через Dovecot, карты — SQL-запросы к представлениям | `postfix/main.cf`, `master.cf`, `pgsql/*.cf` |
| Dovecot 2.4 | IMAP, LMTP-доставка, квоты, Sieve, ManageSieve, проверка паролей (SQL/LDAP) | `dovecot/dovecot.conf` |
| Rspamd + ClamAV | milter: антиспам, DKIM/ARC-подпись, DMARC, лимиты, антивирус | `rspamd/local.d/*` |
| Redis | ключи DKIM для Rspamd, байес, история проверок, счётчики неудачных входов | `install.sh` (requirepass) |
| Бэкенд (FastAPI, `mailapp`) | REST API `/api/v1`, CLI, таймеры (usage, AD-sync, выборка нагрузки) | `backend/`, `backend/.env` |
| Фронт (Vue 3 + PrimeVue) | панель администрирования и личный кабинет; статика за nginx | `frontend/` |
| Агент (`mailagent`) | очередь Postfix, квоты Dovecot, сессии IMAP, баны, параметры служб, состояние хоста | `agent/`, `install/sudoers-mail-agent` |
| nginx | TLS для панели, `allow` по сетям, `limit_req` на вход, заголовки безопасности, ACME на 80; сайт SOGo | `install/nginx/mail-admin.conf`, `install/nginx/sogo.conf` |
| SOGo (необязательно, Docker) | CalDAV/CardDAV, приглашения, общие календари, веб-почта, ActiveSync; своя база `sogo`; клиент Dovecot/Postfix на loopback | `sogo/` |
| unbound | DNSSEC-валидирующий резолвер для DANE и Rspamd; форвард внутренних зон AD | `install.sh` |
| nftables, fail2ban | фаервол и баны по логам Postfix/Dovecot/sshd | `install/nftables.conf`, `install/fail2ban/` |

## Границы доверия

| Компонент | Что может | Чего не может |
|---|---|---|
| Бэкенд (`mailapp`) | читать/писать таблицы, класть ключи DKIM в Redis, спрашивать агента, bind в AD, ManageSieve | читать файлы хоста, запускать команды, менять конфиги, писать в свой код |
| Агент (`mailagent`) | команды из sudoers (аргументы по регулярным выражениям) | что-либо ещё |
| Postfix, Dovecot | `SELECT` из своих представлений | видеть таблицы, хеши паролей чужих объектов, ключи DKIM |
| Веб-почта (отдельный хост) | IMAP/SMTP/ManageSieve как клиент | база, API, хост |
| SOGo (контейнер, роль `sogo`) | IMAP/SMTP как клиент, своя база `sogo`, чтение `v_sogo_users` (хеши локальных ящиков) | таблицы `mail`, API, хост (без capabilities, конфиг только чтение) |
| Фронт | только `/api` с JWT | — |

Подробно — [`security.md`](security.md).

## Потоки данных

- **Входящее письмо**: Postfix принимает на 25 (PTR, HELO, лимиты) → Rspamd (SPF, DKIM, DMARC, байес, ClamAV,
  списки из панели) → Postfix спрашивает базу: домен наш? алиас? ящик? транспорт? → LMTP в Dovecot → Sieve
  (глобальный Junk, затем пользовательский: автоответ, пересылка, правила) → Maildir `/var/vmail/<домен>/<ящик>`.
- **Исходящее**: клиент на 587/465 с TLS → SASL через Dovecot (пароль в базе или AD) → Postfix проверяет, что
  от этого адреса пользователю слать можно (`sender_login_maps`), режим ящика и правила доступа → Rspamd
  подписывает DKIM и ARC, считает лимит → доставка напрямую с DANE или через smarthost.
- **Изменение в панели**: фронт → `/api` → бэкенд пишет в таблицу + `audit_log` → Postfix/Dovecot видят при
  следующем запросе. Параметры хоста: бэкенд → агент → `apply_settings.py` (белый список) → `postconf -e` /
  `/etc/dovecot/panel.conf` + reload.
- **DKIM**: панель генерирует ключ → таблица `dkim_keys` → Redis (`DKIM_PRIVATE_KEYS`, `DKIM_SELECTORS`) → Rspamd.
- **AD** (если настроен): раз в час бэкенд заводит ящики для учёток с `mail` и отключает исчезнувшие; группы →
  рассылки. Пароль таких ящиков проверяет Dovecot bind'ом в AD по LDAPS.
- **Состояние**: агент собирает CPU/память/диски/очередь/сессии/сертификат; таймер пишет выборки в базу для
  графиков.

## Схема базы (основное)

`domains` → `mailboxes` (`auth = local|ad`, `mode`, `quota_mb`, `password` в формате Dovecot) → `mailbox_usage`;
`aliases` + `alias_targets` (включая catch-all `@domain`); `domain_aliases`; `lists` + `list_members`;
`dkim_keys`; `admins` + `admin_domains` (локальный `password_hash` или проверка в AD); `audit_log` (только
добавление); настройки сервера — `server_settings`, `transport_policies`, `tls_policies`, `access_rules`
(`db/schema_settings.sql`). Представления `v_postfix_*` и `v_dovecot_*` — единственное, что читают демоны.

## Чего нет и почему

- **Своего webmail** — рендер чужого HTML это главный источник XSS; Roundcube на отдельном хосте делает это лучше.
- **JMAP** — у Dovecot его нет. CalDAV/CardDAV, приглашения и ActiveSync даёт необязательный SOGo (`calendar.md`).
- **Docker для почтового ядра** — всё из пакетов Debian, обновления безопасности приходят через `apt`; в Docker
  только SOGo, и его образ тоже собирается из пакетов Debian.
- **Кластеризации** — один хост; отказоустойчивость — бэкап VM и быстрое восстановление (`operations.md`).
- **Автоконфигурации клиентов (autodiscover/autoconfig)** — пока нет, параметры в `install.md`.
