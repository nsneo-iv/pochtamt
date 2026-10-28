# postfix — MTA

| Файл | Что делает |
|---|---|
| `main.cf` | шаблон основного конфига: виртуальные домены из PostgreSQL, LMTP в Dovecot, SASL через Dovecot, TLS, Rspamd-milter, лимиты |
| `master.cf` | службы: 25 (приём), 587 и 465 (отправка только с TLS и авторизацией) |
| `pgsql/*.cf` | pgsql-карты: домены, ящики, алиасы, доменные алиасы, кто может слать от какого адреса |

Шаблоны содержат плейсхолдеры `@MAIL_HOSTNAME@`, `@TLS_CERT@`, `@TLS_KEY@`, `@DB_POSTFIX_PASSWORD@`;
их подставляет `install/render.py` из `install/.env`, результат ложится в `install/out/postfix/` и
копируется в `/etc/postfix/` скриптом `install/install.sh`.

## Как это работает

- Postfix не хранит ни одной карты в файлах — каждая доставка делает SELECT в представления `v_postfix_*`
  под ролью `mail_postfix` (только чтение).
- Порядок обработки входящего адреса: `virtual_alias_maps` (алиас → цели, catch-all, доменный алиас),
  затем `virtual_mailbox_maps` (есть ли ящик), затем доставка в Dovecot по LMTP.
- Отправка: `reject_authenticated_sender_login_mismatch` + `sender_login_maps` — пользователь может слать
  только от своего ящика и от алиасов, которые на него указывают.
- Rspamd подключён как milter на 127.0.0.1:11332, он же подписывает DKIM/ARC исходящие письма.
- `smtp_tls_security_level = dane` — для исходящих проверяется DANE при наличии DNSSEC-резолвера
  (в `install.sh` ставится unbound с DNSSEC); иначе работает как `may`.

## Проверка после установки

```bash
postfix check
postmap -q example.com pgsql:/etc/postfix/pgsql/virtual_mailbox_domains.cf
postmap -q user@example.com pgsql:/etc/postfix/pgsql/virtual_mailbox_maps.cf
postmap -q info@example.com pgsql:/etc/postfix/pgsql/virtual_alias_maps.cf
```
