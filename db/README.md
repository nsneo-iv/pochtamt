# db — схема PostgreSQL

| Файл | Что делает |
|---|---|
| `schema.sql` | таблицы, представления для Postfix/Dovecot, триггеры. Идемпотентен, применяется повторно при обновлении |
| `roles.sql` | роли `mail_app` (бэкенд) и `mail_postfix` / `mail_dovecot` (Postfix/Dovecot, только представления). Пароли подставляет `install/render.py` |

## Принцип

Демоны почты **никогда не читают таблицы напрямую** — только представления `v_postfix_*` и `v_dovecot_*`.
Это позволяет менять схему, не трогая конфиги Postfix и Dovecot, и держать роли `mail_postfix` и `mail_dovecot` без доступа
к таблицам с хешами паролей и ключами DKIM (ей видны только представления).

Изменения применяются сразу: Postfix и Dovecot делают запрос при каждой доставке и входе, перезапуски не нужны.

## Объекты

- `domains` — почтовые домены. `max_mailboxes`, `max_quota_mb` — лимиты для доменных админов.
- `domain_aliases` — домен-синоним: `user@alias` → `user@target`.
- `mailboxes` — ящики. `auth = local` (хеш в `password`, формат Dovecot `{BLF-CRYPT}`) или `auth = ad`
  (пароль проверяет Dovecot по LDAP в AD, `ad_upn` — UPN учётки).
- `mailbox_usage` — занятое место; бэкенд берёт его у агента на хосте (`doveadm quota get -A`) и пишет сюда.
- `aliases` + `alias_targets` — алиасы, пересылки и catch-all (`@domain`).
- `lists` + `list_members` — рассылки; при заданном `ad_group` состав ведёт синхронизация с AD.
- `dkim_keys` — ключи DKIM; рабочая копия для Rspamd лежит в Redis, бэкенд её туда кладёт.
- `admins`, `admin_domains` — кто и чем управляет в панели (локальный `password_hash` или проверка пароля в AD).
- `audit_log` — все изменения через API.

## Применение

```bash
sudo -u postgres createdb mail
sudo -u postgres psql -d mail -f db/schema.sql
sudo -u postgres psql -d mail < install/out/db/roles.sql     # после install/render.py
```
