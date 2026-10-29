# Установка

## Что понадобится

| | Минимум | Примечание |
|---|---|---|
| ОС | чистый Debian 13 (trixie), amd64 | облачный образ `debian-13-generic` подходит; скрипт ждёт, пока `unattended-upgrades` отпустит apt |
| CPU / ОЗУ | 2 vCPU / 4 ГБ | ClamAV держит ~1,2 ГБ сигнатур в памяти; с SOGo — 6 ГБ |
| Диск | 20 ГБ система + отдельный диск под `/var/vmail` | почта растёт; отдельный диск проще расширять и бэкапить |
| Сеть | внешний IPv4 с PTR-записью | без PTR крупные провайдеры отклоняют или складывают в спам |
| Порты снаружи | 25, 465, 587, 993 входящие; 25 исходящий; 80 для Let's Encrypt; 443, если включён SOGo | 4190 (ManageSieve), 443 (панель без SOGo), 22 (SSH) — только из своих сетей |
| DNS | A `mail.example.com` → внешний IP, PTR → `mail.example.com` | MX/SPF/DKIM/DMARC — после установки, панель покажет записи |

Всё ставится из пакетов Debian: Postfix 3.10, Dovecot 2.4, Rspamd 3.12, ClamAV 1.4, PostgreSQL 17, Redis 8,
unbound, nginx, Python 3.13. Node.js нужен только для сборки фронта (на сервере — если не собрали заранее).

## Два способа запуска

**На сервере** — клонировать репозиторий в `/opt/mail` и запустить `install/install.sh` от root.

**С рабочего ПК** (Linux, macOS, Windows с Git Bash) — заполнить `.env` локально и выполнить
`bash install/deploy.sh`: скрипт соберёт фронт (если есть `npm`), зальёт репозиторий вместе с `.env` по SSH
в `/opt/mail` и запустит `install.sh` через `sudo`. Нужны `VM_HOST`, `VM_USER` (пользователь с sudo без пароля,
как в cloud-init) и `SSH_KEY` в `install/.env`. Повторный `deploy.sh` — это обновление.

## Шаг 1. Три файла `.env`

```bash
cp install/.env.example install/.env
cp backend/.env.example backend/.env
cp agent/.env.example agent/.env
```

Минимум, что нужно заполнить (полный справочник — [`configuration.md`](configuration.md)):

`install/.env`
- `MAIL_HOSTNAME` — имя почтового хоста (совпадает с A и PTR), `ADMIN_HOSTNAME` — имя панели
  (может совпадать с `MAIL_HOSTNAME`; панель всё равно открыта только для `ADMIN_ALLOW_NETS`).
- `ADMIN_ALLOW_NETS`, `LAN_NETS` — ваши сети (офис, VPN). Из них доступны панель, SSH, ManageSieve; их не банит fail2ban.
- TLS: `CERTBOT_EMAIL` для Let's Encrypt (порт 80 должен быть доступен снаружи), либо `TLS_SRC_DIR` с готовыми
  `fullchain.pem` и `privkey.pem`, либо ничего — самоподписанный для стенда.
- Пароли `DB_APP_PASSWORD`, `DB_POSTFIX_PASSWORD`, `DB_DOVECOT_PASSWORD`, `REDIS_PASSWORD`, `RSPAMD_PASSWORD`,
  `SIEVE_MASTER_PASSWORD` — `openssl rand -hex 24` для каждого.
- Active Directory — оставить пустым, если его нет ([`active-directory.md`](active-directory.md), если есть).
- SOGo (календарь, контакты, ActiveSync) — оставить `SOGO_HOSTNAME` пустым или заполнить по [`calendar.md`](calendar.md).

`backend/.env`
- `DB_DSN` с паролем `mail_app` (тот же `DB_APP_PASSWORD`), `REDIS_URL` с `REDIS_PASSWORD`,
  `RSPAMD_PASSWORD`, `SIEVE_MASTER_PASSWORD`, `SIEVE_HOST` = `MAIL_HOSTNAME`, `MAIL_HOSTNAME`.
- `JWT_SECRET` — `openssl rand -hex 32` (бэкенд не стартует с пустым или коротким).
- `AGENT_TOKEN` — `openssl rand -hex 32`, тот же — в `agent/.env`.

`agent/.env`
- `AGENT_TOKEN` — как в `backend/.env`.

`frontend/.env` (необязательно, только при сборке): `VITE_APP_TITLE` — название панели, `VITE_WEBMAIL_URL` — ссылка
на веб-почту в личном кабинете.

## Шаг 2. Установка

```bash
bash install/install.sh            # на сервере, от root; или bash install/deploy.sh с ПК
```

Скрипт идемпотентен: повторный запуск обновляет конфиги, зависимости и перезапускает службы. Что он делает по порядку:
пакеты → пользователи `vmail`, `mailapp`, `mailagent` → `/etc/hosts` → TLS (копия/самоподписанный) → хеш пароля
Rspamd → рендер шаблонов в `install/out/` → PostgreSQL (схема, роли) → Redis → unbound (DNSSEC) и `systemd-resolved`
→ sshd (только ключи, без root) → проверка LDAPS (если AD) → Postfix → Dovecot → ClamAV (первая загрузка баз до
10 минут) → Rspamd → бэкенд (venv, systemd, таймеры) → агент (sudoers) → фронт → nginx → certbot (если задан) →
fail2ban → nftables.

Если шаг упал, скрипт останавливается с сообщением; после исправления `.env` его запускают заново.

## Шаг 3. Первый администратор

```bash
cd /opt/mail/backend
sudo -u mailapp .venv/bin/python -m app.cli admin-add admin superadmin --password     # спросит пароль (12+ символов)
```

С Active Directory администратора заводят доменной учёткой без пароля (его проверит AD):
`admin-add user@corp.local superadmin`. Администратор отдельного домена:
`admin-add login domain_admin --domains example.com [--password]`.

## Шаг 4. Домен и DNS

Открыть `https://<ADMIN_HOSTNAME>/` из разрешённой сети (с самоподписанным сертификатом браузер предупредит).

1. **Домены → Создать**: имя домена; при необходимости лимиты для доменных админов.
2. На дашборде домена **выпустить DKIM** (селектор по умолчанию `mail`).
3. Прописать в DNS записи, которые показывает блок «DNS» (там же кнопки копирования и проверка):

| Запись | Значение |
|---|---|
| `MX example.com` | `10 mail.example.com` |
| `TXT example.com` | `v=spf1 mx -all` (плюс `ip4:`/`include:` для других отправителей) |
| `TXT mail._domainkey.example.com` | из карточки домена (`v=DKIM1; k=rsa; p=...`) |
| `TXT _dmarc.example.com` | `v=DMARC1; p=quarantine; rua=mailto:postmaster@example.com` (начать можно с `p=none`) |
| PTR внешнего IP | `mail.example.com` (у провайдера/хостера) |

4. **Ящики → Создать**: адрес, имя, локальный пароль (или AD), квота.

Проверка снаружи: отправить письмо на новый ящик и с него, посмотреть заголовки `Authentication-Results`
у получателя (SPF/DKIM/DMARC = pass). Сервисы вроде mail-tester.com показывают итоговую оценку.

## Шаг 5. Клиенты

| Протокол | Хост | Порт | Безопасность | Логин |
|---|---|---|---|---|
| IMAP | `mail.example.com` | 993 | SSL/TLS | полный адрес ящика |
| SMTP (отправка) | `mail.example.com` | 587 (STARTTLS) или 465 (SSL/TLS) | обязательно TLS + авторизация | полный адрес ящика |
| ManageSieve | `mail.example.com` | 4190 | STARTTLS | полный адрес; только из `LAN_NETS` |

Обычный IMAP на 143 снаружи выключен намеренно. Личный кабинет пользователя — `https://<ADMIN_HOSTNAME>/me`
(из тех же сетей, что и панель). Веб-почта — [`webmail.md`](webmail.md); календарь, контакты и ActiveSync —
[`calendar.md`](calendar.md).

## Что проверить после установки

```bash
systemctl status postfix dovecot rspamd clamav-daemon redis-server postgresql unbound nginx mail-backend mail-agent
postfix check && doveconf -n >/dev/null && rspamadm configtest
doveadm auth test user@example.com            # вход в ящик
postmap -q example.com pgsql:/etc/postfix/pgsql/virtual_mailbox_domains.cf
curl -s https://127.0.0.1/api/v1/health -k    # {"status":"ok"}
dig +dnssec @127.0.0.1 example.com MX          # unbound отвечает, флаг ad при DNSSEC у домена
nft list ruleset | head -30 && fail2ban-client status
```

Панель → «Состояние» показывает службы, сертификат, очередь, нагрузку; «Фильтр → Сводка» — состояние антивируса
и баз.

## Стенд без внешнего адреса

Для проверки в локальной сети достаточно: `TLS_SRC_DIR` и `CERTBOT_EMAIL` пустые (самоподписанный сертификат),
`MAIL_HOSTNAME` любое имя, которое резолвится у клиентов (хотя бы через `hosts`), `LAN_NETS` — сеть стенда.
Почта между ящиками одного сервера ходит без внешнего DNS; наружу письма уйдут, но без PTR и SPF скорее всего
попадут в спам.
