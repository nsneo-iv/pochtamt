# backend — API панели

FastAPI + PostgreSQL (psycopg 3). Единственное, что бэкенд умеет менять, — таблицы базы `mail` и хеши DKIM
в Redis. На почтовый хост он не ходит; очередь и квоты даёт отдельный агент (`agent/`).

| Файл | Что делает |
|---|---|
| `app/main.py` | приложение FastAPI, подключает роутеры под `/api/v1` (Swagger/OpenAPI отключены) |
| `app/config.py` | настройки из `.env` (образец — `.env.example`) |
| `app/db.py` | пул соединений PostgreSQL |
| `app/security.py` | хеши паролей `{BLF-CRYPT}` для Dovecot, JWT сессий |
| `app/deps.py` | текущий админ, роли, доступ к доменам |
| `app/audit.py` | запись в `audit_log` |
| `app/models.py` | схемы запросов/ответов и нормализация адресов |
| `app/routers/*.py` | разделы API: auth, domains (+DKIM), mailboxes, aliases, domain_aliases, lists, ad, queue, audit, stats |
| `app/services/ad.py` | Active Directory (необязательно): вход через AD (bind), синхронизация ящиков и рассылок |
| `app/services/dkim.py` | генерация ключей, выкладка в Redis для Rspamd |
| `app/services/agent.py` | клиент агента на хосте |
| `app/services/usage.py` | занятое место ящиков → `mailbox_usage` |
| `app/services/throttle.py` | счётчики неудачных входов в Redis: 429 до обращения к AD (защита учёток от lockout) |
| `app/services/migrate_iredmail.py` | импорт доменов, ящиков, пересылок и ключей DKIM из выгрузки iRedMail (`cli import-iredmail`, `import-dkim`) |
| `app/cli.py` | служебные команды: init-db, admin-add, admin-password, dkim-sync, ad-sync, usage-sync, import-iredmail |
| `tests/` | pytest без внешних систем |

Контракт API — `docs/api.md`.

## Роли

- `superadmin` — всё.
- `domain_admin` — ящики, алиасы и рассылки только своих доменов (`admin_domains`); домены, доменные алиасы,
  очередь и синхронизация с AD недоступны.

Пароль админа — локальный хеш (`admins.password_hash`, bcrypt) или, если настроен AD, bind под его UPN;
роль — таблица `admins`. Первый админ заводится из консоли:

```bash
python -m app.cli admin-add admin superadmin --password        # локальный пароль (спросит)
python -m app.cli admin-add user@corp.local superadmin         # пароль проверяет AD
```

## Запуск для разработки

```bash
cd backend
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env                                # заполнить
python -m app.cli init-db
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
pytest
```

На сервере бэкенд ставится `install/install.sh` как systemd-служба `mail-backend` (`install/mail-backend.service`)
и публикуется nginx по пути `/api`.

## Регламентные задачи

- `usage-sync` — раз в 10 минут (cron/systemd timer, ставит `install.sh`): обновляет занятое место ящиков.
- `ad-sync --apply` — раз в час (только при настроенном AD): заводит ящики для новых учёток AD с атрибутом `mail`,
  отключает уволенных, обновляет состав рассылок, привязанных к группам.
- `dkim-sync` — вручную после пересоздания Redis.

## Удаление ящика

API удаляет только запись в базе: Dovecot и Postfix перестают видеть ящик сразу. Каталог `/var/vmail/<домен>/<ящик>`
остаётся на диске до ручной очистки — это сознательно, чтобы ошибочное удаление было обратимым.
