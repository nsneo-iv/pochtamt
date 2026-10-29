# install — развёртывание на сервере

| Файл | Что делает |
|---|---|
| `install.sh` | полная установка на чистый Debian 13 от root (идемпотентна): пакеты, пользователи, TLS, PostgreSQL, Redis, unbound, Postfix, Dovecot, ClamAV, Rspamd, бэкенд, агент, фронт, nginx, certbot, fail2ban, nftables |
| `deploy.sh` | с рабочего ПК: собрать фронт, залить репозиторий (с `.env`) на сервер по SSH и запустить `install.sh`; `--sync` — только залить |
| `fetch-cert.sh` | забрать готовый сертификат с другого хоста по SSH в `install/certs/` и залить на сервер с перечитыванием Postfix/Dovecot/nginx; `--local` — только скачать |
| `render.py` | подставить значения из `install/.env` в шаблоны → `install/out/` (в git не попадает); `--check` — только проверить заполненность |
| `.env.example` | все ключи с пояснениями (справочник — `docs/configuration.md`) |
| `nginx/mail-admin.conf` | сайт панели: статика фронта, `/api` → бэкенд, `/rspamd/` → Rspamd, `limit_req` на вход; только из `ADMIN_ALLOW_NETS`; на 80 — ACME и редирект |
| `mail-backend.service` | systemd: uvicorn от пользователя `mailapp` в песочнице |
| `mail-agent.service` | systemd: агент от пользователя `mailagent` |
| `mail-usage-sync.*`, `mail-ad-sync.*`, `mail-system-sample.*` | таймеры: занятое место раз в 10 минут, синхронизация с AD раз в час (только при AD), выборка нагрузки раз в 5 минут |
| `sudoers-mail-agent` | белый список команд агента (регулярные выражения sudo) |
| `fail2ban/mail.conf` | jail'ы Postfix, SASL, Dovecot; `LAN_NETS` не банятся |
| `nftables.conf` | файрвол: наружу 25/465/587/993 и 80; 443, 4190, 22, 10050 — из `LAN_NETS` (443 для всех при SOGo) |
| `nginx/sogo.conf` | сайт SOGo (при `SOGO_HOSTNAME`): `/SOGo`, статика, ActiveSync, `.well-known/caldav` |
| `sogo.service` | systemd: контейнер SOGo через `docker compose` (при `SOGO_HOSTNAME`) |
| `migrate/iredmail-export.sh` | на старом сервере iRedMail: выгрузка базы `vmail` в TSV (только чтение) |
| `migrate/place-maildirs.py` | на новом сервере: разложить принятые Maildir'ы по `/var/vmail/<домен>/<ящик>` (`docs/migration-iredmail.md`) |

Каталоги `install/out/` (собранные конфиги с паролями) и `install/certs/` (ключ сертификата, сертификат DC) в git
не попадают; на сервере весь `install/` принадлежит root с правами 0700.

## Порядок

Полное руководство — [`docs/install.md`](../docs/install.md). Коротко:

1. Сервер Debian 13 (2 vCPU, 4 ГБ, диск под `/var/vmail`), внешний адрес с PTR, порты 25/465/587/993/80 снаружи.
2. Заполнить `install/.env`, `backend/.env`, `agent/.env` по образцам.
3. `bash install/install.sh` на сервере (или `bash install/deploy.sh` с ПК). Повторные запуски безопасны.
4. Первый админ: `sudo -u mailapp backend/.venv/bin/python -m app.cli admin-add admin superadmin --password`
   (из `backend/`).
5. В панели: домен → DKIM → DNS-записи из карточки домена → ящики (или синхронизация с AD).
6. Веб-почта — отдельный хост ([`docs/webmail.md`](../docs/webmail.md)). Панель наружу не публиковать.

## Обновление

```bash
bash install/deploy.sh          # или на сервере: git pull && bash install/install.sh
```

Сертификат: certbot продлевает сам; при `fetch-cert.sh` — запускать после продления на исходном хосте.
Крупные обновления Dovecot (2.4.x → 2.5) — сначала на снапшоте: формат конфига у них меняется.
