# Документация Pochtamt

| Документ | О чём |
|---|---|
| [`install.md`](install.md) | Требования, DNS и сеть, установка на чистый Debian 13, первый администратор, первый домен, проверка |
| [`configuration.md`](configuration.md) | Все ключи `install/.env`, `backend/.env`, `agent/.env`, `frontend/.env`; что настраивается из панели |
| [`operations.md`](operations.md) | Обновление, сертификаты, бэкап и восстановление, журналы, таймеры, типовые неполадки |
| [`architecture.md`](architecture.md) | Компоненты, границы доверия, потоки данных, чего нет и почему |
| [`security.md`](security.md) | Модель угроз, что сделано, известные ограничения |
| [`api.md`](api.md) | Контракт REST API бэкенда (`/api/v1`) |
| [`active-directory.md`](active-directory.md) | Интеграция с AD: LDAPS, Global Catalog, вход админов, ящики `auth=ad`, синхронизация |
| [`calendar.md`](calendar.md) | SOGo в Docker: календарь, контакты, веб-почта, ActiveSync; клиенты, эксплуатация |
| [`webmail.md`](webmail.md) | Как подключить веб-почту (Roundcube) на отдельном хосте |
| [`migration-iredmail.md`](migration-iredmail.md) | Перенос с iRedMail: база, Maildir'ы, DKIM, переключение |

README папок (`backend/`, `frontend/`, `agent/`, `db/`, `postfix/`, `dovecot/`, `rspamd/`, `sogo/`, `install/`) описывают
файлы внутри и команды проверки.
