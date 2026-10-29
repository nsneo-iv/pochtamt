# sogo — календарь, контакты, веб-почта, ActiveSync (необязательно, в Docker)

SOGo даёт то, чего нет у Dovecot: CalDAV/CardDAV с приглашениями на встречи и занятостью коллег, общие
календари и адресные книги, собственную веб-почту и ActiveSync для Outlook и телефонов. Включается ключом
`SOGO_HOSTNAME` в `install/.env` (пусто — компонент не ставится). Руководство — `docs/calendar.md`.

Единственный компонент проекта в Docker: GNUstep-зависимости SOGo не попадают на хост, а образ собирается из
пакета `sogo` того же Debian 13 прямо на сервере. Контейнер работает в сети хоста, слушает только
`127.0.0.1:20000` и ходит к Dovecot (143 на loopback), Postfix (587) и PostgreSQL (5432) как локальный клиент.
Демон Docker ставится с выключенным управлением iptables, чтобы не трогать nftables хоста.

| Файл | Что делает |
|---|---|
| `image/Dockerfile` | образ из `debian:trixie-slim`: `sogo`, `sogo-activesync`, `memcached`; пользователь `sogo` 950:950 |
| `image/entrypoint.sh` | memcached на loopback, статика в `/srv/www` (для nginx хоста), напоминания и чистка сессий по таймеру, `sogod` в foreground |
| `docker-compose.yml` | шаблон: один сервис в `network_mode: host`, тома `/etc/sogo/sogo.conf`, `/var/lib/sogo/{data,www}`, `/etc/ssl/certs` (сертификат DC для LDAPS); без capabilities |
| `sogo.conf` | шаблон конфига SOGo: своя база `sogo`, источники пользователей (`@SOGO_USER_SOURCES@` собирает `render.py`), IMAP/SMTP localhost, ActiveSync, язык и часовой пояс |
| `db.sql` | роль `sogo`, представление `v_sogo_users` в базе `mail` (локальные ящики с хешами `{BLF-CRYPT}`), права |

На хосте: `/etc/sogo/` (конфиг 0640 root:950, compose, контекст сборки), `/var/lib/sogo/data` (GNUstep-профиль),
`/var/lib/sogo/www` (статика, отдаёт nginx), база PostgreSQL `sogo`; служба `sogo` (`install/sogo.service`),
сайт `install/nginx/sogo.conf`. Проверка: `systemctl status sogo`, `journalctl -u sogo`, `curl -I https://<SOGO_HOSTNAME>/SOGo/`.

Сознательные ограничения: автоответ, пересылка, фильтры и смена пароля в SOGo выключены — ими управляет панель
(личный кабинет `/me`) через Sieve, иначе два источника правды перезаписывали бы друг друга.
