# Настройка

Вся конфигурация делится на три слоя:

1. **`.env`-файлы** (при установке): имена хостов, сети, пароли, AD, TLS. Из них `install/render.py` собирает
   конфиги Postfix/Dovecot/Rspamd/nginx/systemd (`install/out/`, в git не попадает), а `install.sh` раскладывает
   их по `/etc`. Изменили `.env` — повторный `install.sh`.
2. **Панель** (во время работы): всё, что относится к почтовым объектам и части параметров сервера. Применяется
   сразу, без перезапусков (демоны читают базу при каждом запросе; параметры хоста применяет агент с reload).
3. **Шаблоны в репозитории** (`postfix/`, `dovecot/`, `rspamd/local.d/`): всё остальное. Правят шаблон, а не живой
   файл в `/etc`, иначе следующий `install.sh` затрёт изменения.

Файлы `.env` читаются построчно (значение после первого `=`, кавычки по краям снимаются); переменные окружения
с тем же именем имеют приоритет. Пароли генерируйте `openssl rand -hex 24`, секреты подписи — `openssl rand -hex 32`.

## `install/.env`

| Ключ | Что это |
|---|---|
| `MAIL_HOSTNAME` | Имя почтового хоста: HELO, сертификат, MX. A-запись → внешний IP, PTR → это имя |
| `ADMIN_HOSTNAME` | Имя сайта панели (`default_server` в nginx: панель откроется и по IP). Может совпадать с `MAIL_HOSTNAME` |
| `ADMIN_ALLOW_NETS` | Сети (через пробел), откуда пускать в панель, кабинет и `/rspamd/` — `allow` в nginx |
| `LAN_NETS` | «Свои» сети: SSH, 443, ManageSieve, порт агента мониторинга открыты только для них; fail2ban их не банит; Rspamd считает письма из них своими (без SPF/greylist, с DKIM-подписью) |
| `TLS_CERT`, `TLS_KEY` | Пути на хосте, куда ляжет сертификат и ключ (их читают Postfix, Dovecot, nginx, агент) |
| `TLS_SRC_DIR` | Каталог с готовыми `fullchain.pem` и `privkey.pem` (например, `install/certs` после `fetch-cert.sh`). Приоритет над certbot |
| `CERTBOT_EMAIL` | Если задан и `TLS_SRC_DIR` пуст — сертификат Let's Encrypt через `certbot --webroot` (порт 80 снаружи). Продление — `certbot.timer` с reload служб |
| `CERTBOT_DOMAINS` | Имена в сертификате через пробел; пусто — только `MAIL_HOSTNAME`. Добавляйте `ADMIN_HOSTNAME`, если он резолвится снаружи |
| `CERT_HOST`, `CERT_USER`, `CERT_DIR`, `CERT_FULLCHAIN_FILE`, `CERT_KEY_FILE` | Для `install/fetch-cert.sh`: откуда по SSH забрать готовый сертификат (например, с обратного прокси) |
| `DB_APP_PASSWORD` | Пароль роли `mail_app` (бэкенд, чтение/запись таблиц) |
| `DB_POSTFIX_PASSWORD` | Пароль роли `mail_postfix` (только `v_postfix_*`) |
| `DB_DOVECOT_PASSWORD` | Пароль роли `mail_dovecot` (только `v_dovecot_*`) |
| `REDIS_PASSWORD` | `requirepass` Redis (ключи DKIM, байес, история Rspamd, счётчики входа) |
| `RSPAMD_PASSWORD` | Пароль веб-интерфейса и API Rspamd; `RSPAMD_PASSWORD_HASH` считает и записывает `install.sh` |
| `AD_LDAP_URI` | Адрес контроллера домена (`ldaps://dc.corp.local:3269`). **Пусто — AD выключен** во всём проекте |
| `AD_BIND_USER`, `AD_BIND_PASSWORD`, `AD_BASE_DN` | Сервисная учётка и база поиска для Dovecot (те же — в `backend/.env`) |
| `AD_CA_CERT` | PEM открытой части сертификата DC или его CA; `install.sh` кладёт в доверенные ОС и проверяет LDAPS |
| `AD_DNS_ZONE`, `AD_FORWARD_DNS`, `AD_REVERSE_ZONES` | Внутренняя зона AD и её DNS: unbound форвардит их без DNSSEC |
| `CLAMAV_MIRRORS` | Зеркала баз ClamAV по порядку; подлинность баз проверяется подписью |
| `SIEVE_MASTER_PASSWORD` | Пароль master-пользователя Dovecot `panel` (бэкенд заливает Sieve-скрипты через ManageSieve, вход только с localhost) |
| `VM_HOST`, `VM_USER`, `SSH_KEY` | Для `deploy.sh`/`fetch-cert.sh` с рабочего ПК |

## `backend/.env`

| Ключ | Что это |
|---|---|
| `DB_DSN` | `postgresql://mail_app:<DB_APP_PASSWORD>@127.0.0.1:5432/mail` |
| `JWT_SECRET`, `JWT_TTL_MINUTES` | Секрет подписи сессий (32+ символов, обязателен) и их срок (120) |
| `AD_LDAP_URI`, `AD_BIND_USER`, `AD_BIND_PASSWORD`, `AD_BASE_DN` | Как в `install/.env`; пустой `AD_LDAP_URI` — вход только по локальным паролям, разделы AD скрыты |
| `AD_UPN_SUFFIX`, `AD_NETBIOS` | `user` → `user@<суффикс>`, `NETBIOS\user` принимается как тот же логин |
| `AD_TLS_VERIFY` | Проверять сертификат DC (`false` только на стенде) |
| `MAIL_HOSTNAME` | С ним сравнивается MX в проверке DNS на дашборде домена |
| `RSPAMD_URL`, `RSPAMD_PASSWORD` | Контроллер Rspamd для статистики, истории, порогов и списков |
| `REDIS_URL` | `redis://:<REDIS_PASSWORD>@127.0.0.1:6379/0` |
| `SIEVE_HOST`, `SIEVE_PORT`, `SIEVE_MASTER_USER`, `SIEVE_MASTER_PASSWORD` | ManageSieve для автоответов/пересылок/правил; хост должен совпадать с именем в сертификате |
| `AGENT_URL`, `AGENT_TOKEN` | Агент на хосте и общий с ним токен |
| `LISTEN_HOST`, `LISTEN_PORT`, `CORS_ORIGINS` | uvicorn за nginx; CORS не нужен, если фронт отдаёт тот же nginx |

## `agent/.env`

| Ключ | Что это |
|---|---|
| `AGENT_TOKEN` | Тот же токен, что в `backend/.env` |
| `AGENT_LISTEN` | `127.0.0.1:8025`; если бэкенд на другом хосте — адрес внутренней сети и правило в nftables |

## `frontend/.env` (при сборке)

| Ключ | Что это |
|---|---|
| `VITE_API_BASE` | Базовый адрес бэкенда; пусто — тот же origin |
| `VITE_APP_TITLE` | Название панели в шапке, на входе и в заголовке вкладки (по умолчанию «Почтамт») |
| `VITE_WEBMAIL_URL` | Ссылка на веб-почту в личном кабинете; пусто — нет ссылки |

## Что настраивается из панели

**Почтовые объекты** — домены (лимиты, активность), ящики (квота, режим, авторизация local/AD, пароль),
алиасы и пересылки (в том числе catch-all), доменные алиасы, рассылки (вручную или из группы AD), DKIM.

**Настройки ящика** (и в личном кабинете): автоответ с датами, пересылка с сохранением копии, BCC всей
входящей/исходящей, пользовательские правила Sieve (панель генерирует скрипт и заливает через ManageSieve).

**Настройки домена**: транспорт (доставка домена на другой хост), BCC домена, запрет внешней исходящей почты.

**Сервер**
- *Исходящая почта*: smarthost (хост, порт, логин, пароль; SASL только с TLS).
- *TLS к получателям*: политика по доменам (`may` / `encrypt` / `dane` / `secure`, …).
- *Доступ SMTP*: правила client (IP/префикс) / sender / recipient → OK / REJECT / DISCARD.
- *Параметры*: белый список с проверкой значений, применяются с `reload` службы через агента —

| Служба | Параметр | Допустимые значения |
|---|---|---|
| Postfix | `message_size_limit` | 1 МБ … 200 МБ |
| Postfix | `smtpd_client_connection_rate_limit`, `smtpd_client_message_rate_limit`, `smtpd_client_recipient_rate_limit` | 0 … 10 000 / 100 000 |
| Postfix | `anvil_rate_time_unit` | `60s` и т.п. |
| Postfix | `smtpd_banner` | `$myhostname` + короткий текст |
| Postfix | `smtpd_tls_protocols`, `smtpd_tls_mandatory_protocols` | `>=TLSv1.2`, `>=TLSv1.3` |
| Postfix | `smtp_tls_security_level` | `may`, `encrypt`, `dane` |
| Postfix | `mynetworks` | loopback и частные сети не шире /16 (v4) или /64 (v6) |
| Postfix | `maximal_queue_lifetime`, `bounce_queue_lifetime` | `5d`, `12h`, … |
| Postfix | `disable_vrfy_command`, `smtpd_helo_required` | `yes` / `no` |
| Dovecot | `mail_max_userip_connections` | 1 … 1000 |
| Dovecot | `auth_failure_delay` | `N secs` |
| Dovecot | `imap_idle_notify_interval` | `N mins` |
| Dovecot | `quota_exceeded_message` | текст до 200 символов из безопасного набора |
| Dovecot | `lmtp_rcpt_check_quota` | `yes` / `no` |

Список и проверки одинаковы в `backend/app/services/hostconf.py` и `agent/apply_settings.py`; sudoers разрешает
агенту только `apply_settings.py set <служба> <ключ> <значение>` с ограничениями по длине и символам.

**Фильтр** (Rspamd): пороги greylist / add_header / reject, белые и чёрные списки адресов и IP (карты в
`/var/lib/rspamd/maps`), веса символов, запрос обновления баз ClamAV.

## Что живёт в шаблонах

Порты и службы (`postfix/master.cf`, `dovecot/dovecot.conf`), ограничения smtpd и политика PTR
(`postfix/main.cf`), шифры TLS, квоты по умолчанию, лимиты Sieve, модули Rspamd (`rspamd/local.d/*`), jail'ы
fail2ban (`install/fail2ban/mail.conf`), правила nftables (`install/nftables.conf`), заголовки безопасности nginx
(`install/nginx/mail-admin.conf`), песочницы systemd (`install/*.service`). После правки — `python install/render.py
--check`, затем `install.sh` (или `deploy.sh`).
