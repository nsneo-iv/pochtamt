# dovecot — IMAP, LMTP, Sieve

| Файл | Что делает |
|---|---|
| `dovecot.conf` | единый конфиг Dovecot 2.4: Maildir в `/var/vmail`, passdb SQL (+ LDAP, если настроен AD), userdb SQL, квоты, LMTP для Postfix, Sieve, ManageSieve |
| `sieve/before.d/10-spam.sieve` | глобальное правило: спам от Rspamd в папку Junk |

Плейсхолдеры `@TLS_CERT@`, `@TLS_KEY@`, `@DB_DOVECOT_PASSWORD@` и блок `@DOVECOT_PASSDB_LDAP@` (passdb ldap с
`AD_LDAP_URI`, `AD_BIND_USER`, `AD_BIND_PASSWORD`, `AD_BASE_DN`; без AD — комментарий) подставляет `install/render.py`.

## Как проходит вход

1. Пользователь входит адресом ящика (`user@example.com`) и паролем.
2. `passdb sql` читает `v_dovecot_auth` (все активные ящики): для `auth = local` проверяет хеш — неверный пароль
   это отказ, в AD не проваливаемся; для `auth = ad` отдаёт `noauthenticate` и решение остаётся за следующим passdb;
   ящика нет в базе — отказ (`result_failure = return-fail`).
3. `passdb ldap` (только для `auth = ad`) ищет в AD учётку, у которой `userPrincipalName` или `mail` равен
   введённому адресу, и делает bind её паролем. Отключённые учётки (`userAccountControl` бит 2) отсекаются фильтром.
4. `userdb sql` обязателен для обоих путей: если ящика нет в базе, входа нет даже при верном пароле AD.

`AD_LDAP_URI` должен указывать на Global Catalog (порт 3269 по LDAPS, 3268 без TLS): на 389/636 лес с дочерними доменами
возвращает referrals, и auth-процесс Dovecot на них зависает. Подробнее — `docs/active-directory.md`.

Важно: чтобы вход через AD работал, у учётки в AD должен быть атрибут `mail` = адрес ящика
(или UPN = адрес), а в панели ящик создан с `auth = ad`. Синхронизация с AD (`backend` → `/ad/sync`)
создаёт такие ящики сама.

## Квоты

Размер приходит из `v_dovecot_users.quota_bytes` как `quota_storage_size`; `0` — без ограничения.
Занятое место панель получает от агента (`doveadm quota get -A`), в самом Dovecot ничего писать не нужно.

## Проверка после установки

```bash
doveconf -n                                   # конфиг разбирается
doveadm auth test user@example.com            # спросит пароль; для auth=ad — пароль AD
doveadm user user@example.com                 # userdb: home и квота
doveadm quota get -u user@example.com
```

Если `doveconf` ругается на незнакомые параметры — это разница версий 2.4.x; смотреть
`https://doc.dovecot.org/2.4.0/core/summaries/settings.html` и править шаблон, а не живой файл.
