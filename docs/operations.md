# Эксплуатация

## Обновление

```bash
# на сервере
cd /opt/mail && git pull && bash install/install.sh
# или с рабочего ПК
bash install/deploy.sh
```

`install.sh` обновляет пакеты проекта (не системные), конфиги из шаблонов, зависимости бэкенда, фронт, схему базы
(`db/schema.sql` идемпотентен, `ALTER … IF NOT EXISTS` для новых колонок) и перезапускает службы. Почта на время
перезапуска Postfix/Dovecot (секунды) буферизуется отправителями, клиенты переподключаются.

Системные обновления — обычный Debian: `apt update && apt upgrade`; `unattended-upgrades` для `security.debian.org`
включён в облачном образе по умолчанию. Крупные версии Dovecot (2.4 → 2.5) — сначала на снапшоте VM: формат
конфига у них меняется, шаблон `dovecot/dovecot.conf` может потребовать правок (`doveconf -n` покажет).

Перед изменениями CHANGELOG проекта стоит прочитать: миграции схемы и ключи `.env` описываются там.

## Сертификат TLS

| Способ | Продление |
|---|---|
| certbot (`CERTBOT_EMAIL`) | `certbot.timer` раз в 12 часов; deploy-hook перечитывает Postfix, Dovecot, nginx. Порт 80 должен оставаться открытым снаружи |
| с другого хоста (`fetch-cert.sh`) | после продления там — `bash install/fetch-cert.sh` с ПК (скачает, зальёт, перечитает службы); можно в планировщик раз в месяц |
| самоподписанный | год; повторный `install.sh` не перевыпускает, пока файл есть — удалите `TLS_CERT` и запустите снова |

Срок действия виден в панели («Состояние» → сертификат); агент читает его из `TLS_CERT`.

## Резервное копирование

Что нужно сохранять:

| Что | Где | Как |
|---|---|---|
| База `mail` (домены, ящики, хеши паролей, алиасы, DKIM-ключи, аудит, настройки) | PostgreSQL | `sudo -u postgres pg_dump -Fc mail > mail.dump` |
| Почта | `/var/vmail/<домен>/<ящик>/Maildir` | снапшот диска или `rsync -a` (`dovecot.index*` можно не копировать) |
| Секреты | `/opt/mail/install/.env`, `backend/.env`, `agent/.env`, `/etc/mail-agent.env`, `/etc/dovecot/master-users` | копия в защищённое место; без них восстановление = новые пароли ролей |
| Сертификат | `/etc/letsencrypt` или `TLS_CERT`/`TLS_KEY` | при certbot переизлучается заново, при переносе проще скопировать |
| Rspamd (байес, история) | Redis `/var/lib/redis/dump.rdb`, `/var/lib/rspamd/maps` | терять не страшно: DKIM-ключи восстанавливаются из базы (`cli dkim-sync`), байес переобучится |

Проще всего — снапшот/бэкап всей VM раз в сутки плюс `pg_dump` чаще (база маленькая).

**Восстановление на новый хост**: установить проект с теми же `.env` → `pg_restore -d mail mail.dump` (после
`install.sh`, который создал базу и роли; `--clean` при непустой базе) → вернуть `/var/vmail` (владелец `vmail:vmail`)
→ `python -m app.cli dkim-sync` → проверить `doveadm auth test`.

## Регламентные задачи (systemd timers)

| Таймер | Период | Что делает |
|---|---|---|
| `mail-usage-sync` | 10 мин | занятое место ящиков из `doveadm quota` через агента → `mailbox_usage` |
| `mail-system-sample` | 5 мин | выборка нагрузки хоста для графиков «Состояние» |
| `mail-ad-sync` | 1 ч | синхронизация с AD (включается только при заданном `AD_LDAP_URI`) |
| `certbot` | 12 ч | продление сертификата (при `CERTBOT_EMAIL`) |
| `clamav-freshclam` | служба | базы антивируса раз в час |

`systemctl list-timers 'mail-*'`, журнал: `journalctl -u mail-usage-sync`.

## CLI бэкенда

Запускать из `/opt/mail/backend` под `mailapp`: `sudo -u mailapp .venv/bin/python -m app.cli <команда>`.

| Команда | Что делает |
|---|---|
| `admin-add <логин> superadmin\|domain_admin [--domains a,b] [--password]` | завести/обновить админа; `--password` — локальный пароль (без AD обязателен) |
| `admin-password <логин>` | сменить локальный пароль админа |
| `admin-list` | список админов |
| `dkim-sync` | перезалить все ключи DKIM из базы в Redis (после пересоздания Redis) |
| `ad-sync [--apply]` | синхронизация с AD (без `--apply` — предпросмотр) |
| `usage-sync`, `system-sample` | то, что делают таймеры |
| `import-iredmail DIR [--apply]`, `import-dkim DIR --selector S [--apply]` | миграция, см. `migration-iredmail.md` |
| `init-db` | применить `db/schema.sql` (делает `install.sh`) |

## Журналы

| Что | Где |
|---|---|
| Postfix | `/var/log/postfix.log` (0640 root:adm), `journalctl -u postfix` |
| Dovecot | `/var/log/dovecot.log` (`auth_verbose = yes`, пароли не пишутся) |
| Rspamd | `/var/log/rspamd/rspamd.log`; история проверок — в панели «Фильтр → История» |
| Бэкенд, агент | `journalctl -u mail-backend`, `journalctl -u mail-agent` |
| nginx | `/var/log/nginx/access.log`, `error.log` |
| fail2ban | `fail2ban-client status postfix` / `postfix-sasl` / `dovecot` / `sshd`; панель «Состояние» показывает баны |
| Аудит изменений | панель «Аудит» (таблица `audit_log`, бэкенд может только добавлять записи) |

## Типовые неполадки

**Письмо не доходит снаружи.** `postmap -q example.com pgsql:/etc/postfix/pgsql/virtual_mailbox_domains.cf`
должен вернуть домен, `… virtual_mailbox_maps.cf` — ящик. В `/var/log/postfix.log` смотреть ответ при `RCPT TO`:
`450 … cannot find your reverse hostname` — у отправителя нет PTR (политика `reject_unknown_reverse_client_hostname`
в `postfix/main.cf`); `454 4.7.1` при `milter` — Rspamd недоступен (`systemctl status rspamd`), почта ждёт в очереди
отправителя (`milter_default_action = tempfail` — намеренно, чтобы не пропускать без проверки).

**Исходящее попадает в спам.** Проверить дашборд домена: MX, SPF, DKIM, DMARC должны быть зелёными; PTR у
хостера; `Authentication-Results` в письме у получателя. Заголовок `DKIM-Signature` отсутствует — ключ не в Redis
(`cli dkim-sync`) или домен в `From` не совпадает с доменом ключа.

**Вход в ящик не работает.** `doveadm auth test user@example.com`; для `auth=ad` — `docs/active-directory.md`.
После пяти неудач за 10 минут fail2ban банит IP на час (кроме `LAN_NETS`): `fail2ban-client unban <ip>`.

**Панель: 429 при входе.** Защита от перебора: 5 неудач по логину или 20 по IP за 15 минут. Счётчики в Redis
(`thr:admin:*`, `thr:me:*`) истекают сами; срочно — `redis-cli -a … DEL thr:admin:l:<логин>`.

**Очередь растёт.** Панель «Очередь» показывает причины отложенных писем; `postqueue -p` на хосте. Для исходящей
через smarthost — проверить логин/пароль и TLS в «Сервер → Исходящая почта».

**ClamAV не стартует / `CLAMAV_FAIL` в логе Rspamd.** Баз нет или `freshclam` не может скачать (403 от CDN):
другое зеркало в `CLAMAV_MIRRORS`, повторный `install.sh`; либо положить `main.cvd`, `daily.cvd`, `bytecode.cvd`
в `/var/lib/clamav` вручную. Пока антивирус недоступен, письма проходят без проверки на вирусы (fail-open модуля
antivirus) — это отражено в `security.md`.

**Шаблоны не собираются.** `python install/render.py --check` перечисляет незаполненные ключи `install/.env`.

**Dovecot не принимает конфиг после обновления пакета.** `doveconf -n` покажет строку; правка — в шаблоне
`dovecot/dovecot.conf`, затем `install.sh`.

## Удаление ящика

API удаляет только запись в базе — Postfix и Dovecot перестают видеть ящик сразу, каталог `/var/vmail/<домен>/<ящик>`
остаётся до ручной очистки (`rm -r` от root), чтобы ошибочное удаление было обратимым: создайте ящик заново с
тем же адресом — письма на месте.

## Мониторинг

Порт 10050 (Zabbix agent) открыт в nftables из `LAN_NETS`; сам агент мониторинга не ставится. Для внешних систем
полезны: `GET /api/v1/health` (локально), `systemctl is-active` служб, размер очереди (`postqueue -p | tail -1`),
срок сертификата, место в `/var/vmail`.
