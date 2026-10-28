# Pochtamt — почтовый сервер с панелью управления

[English](README.en.md) · [Документация](docs/README.md) · [Установка](docs/install.md) · [Лицензия GPL-3.0](LICENSE)

Pochtamt («почтамт») — самодостаточный почтовый сервер для небольшой организации на одном хосте Debian 13:
Postfix + Dovecot + Rspamd + ClamAV с PostgreSQL в роли единого источника правды, REST-бэкенд на FastAPI
и панель администрирования на Vue 3. Без Docker, всё из пакетов Debian. Пользователи и пароли — локальные или
из Active Directory (необязательно).

Главный принцип: **панель не имеет доступа к хосту.** Бэкенд пишет только в базу и Redis; Postfix и Dovecot читают
из базы через представления под ролями «только чтение»; единственное окно на хост — маленький агент с белым
списком команд в sudoers. Компрометация панели не даёт шелл на почтовом сервере.

## Возможности

**Почта**
- Виртуальные домены, ящики, алиасы и пересылки, catch-all, доменные алиасы, рассылки.
- Режимы ящика: обычный, только приём, только отправка, только внутри своих доменов.
- Квоты (Dovecot quota), автоответ, пересылка с копией, скрытая копия (BCC), пользовательские правила Sieve.
- Отправка только от своих адресов (`sender_login_maps`), SASL через Dovecot, TLS ≥ 1.2, DANE для исходящих
  (unbound с DNSSEC на хосте), опциональный smarthost и TLS-политики по доменам получателей.
- Rspamd: SPF/DKIM/DMARC/ARC, байес, greylisting, лимиты отправки на пользователя; ClamAV — отказ на SMTP.
- DKIM-ключи генерирует панель и хранит в базе (рабочая копия в Redis), готовые DNS-записи — в карточке домена.

**Панель администрирования**
- Сводка: домены, ящики, очередь, занятое место, антиспам и антивирус.
- Дашборд домена: проверка DNS (MX, SPF, DKIM, DMARC) с ожидаемыми записями, DKIM, топ ящиков, последние действия.
- Очередь Postfix (просмотр, повтор, удаление), состояние хоста с графиками за 6 ч / 24 ч / 7 дней.
- Настройки сервера из панели по белому списку: smarthost, TLS-политики, правила доступа SMTP (client/sender/
  recipient), ограниченный набор параметров Postfix/Dovecot с проверкой значений.
- Спам-фильтр: пороги, белые/чёрные списки, история проверок, веса символов, обновление баз антивируса.
- Роли: суперадминистратор и администратор домена; журнал аудита всех изменений.
- Личный кабинет пользователя (`/me`): пароль, автоответ, пересылка, правила Sieve.

**Active Directory (по желанию)**
- Вход администраторов доменной учёткой, проверка паролей ящиков bind'ом в AD по LDAPS.
- Синхронизация: учётки с атрибутом `mail` → ящики, отключённые → отключённые ящики, группы → рассылки.

**Эксплуатация**
- Установка одним скриптом на чистый Debian 13 (идемпотентна), деплой с рабочего ПК по SSH.
- TLS: Let's Encrypt (certbot) на самом сервере, сертификат с другого хоста или самоподписанный для стенда.
- nftables, fail2ban, systemd-песочницы для бэкенда и агента, защита входа от перебора.
- Миграция с iRedMail: домены, ящики с хешами паролей, пересылки, Maildir'ы, ключи DKIM.

## Из чего состоит

| Папка | Что внутри |
|---|---|
| [`db/`](db/) | схема PostgreSQL: таблицы, представления для Postfix/Dovecot, роли |
| [`postfix/`](postfix/) | шаблоны `main.cf`, `master.cf`, pgsql-карты |
| [`dovecot/`](dovecot/) | конфиг Dovecot 2.4: SQL (+ LDAP для AD), квоты, LMTP, Sieve, ManageSieve |
| [`rspamd/`](rspamd/) | антиспам, DKIM/ARC с ключами в Redis, DMARC, ClamAV |
| [`backend/`](backend/) | FastAPI: домены, ящики, алиасы, рассылки, DKIM, настройки сервера, AD, аудит, CLI |
| [`frontend/`](frontend/) | панель администрирования и личный кабинет, Vue 3 + PrimeVue |
| [`agent/`](agent/) | агент на хосте: очередь Postfix, квоты, параметры служб через sudo-белый список |
| [`install/`](install/) | установка на Debian 13, systemd, nginx, fail2ban, nftables, certbot, деплой, миграция |
| [`docs/`](docs/) | документация: установка, настройка, эксплуатация, AD, безопасность, API, миграция |
| [`tools/`](tools/) | проверка секретов перед коммитом, выпуск сертификата LDAPS на контроллере домена |

Версии на Debian 13: Postfix 3.10, Dovecot 2.4, Rspamd 3.12, ClamAV 1.4, PostgreSQL 17, Redis 8, Python 3.13.
Архитектура и границы доверия — [`docs/architecture.md`](docs/architecture.md).

## Быстрый старт

Нужны: чистый Debian 13 (2 vCPU, 4 ГБ ОЗУ, диск под `/var/vmail`), внешний адрес с PTR, открытые снаружи
порты 25, 465, 587, 993 и 80 (для Let's Encrypt). Подробно — [`docs/install.md`](docs/install.md).

```bash
git clone https://github.com/nsneo-iv/pochtamt.git /opt/mail && cd /opt/mail
cp install/.env.example install/.env && cp backend/.env.example backend/.env && cp agent/.env.example agent/.env
# заполнить три .env (имена хостов, сети, пароли: openssl rand -hex 24; секреты: openssl rand -hex 32)
bash install/install.sh
cd backend && sudo -u mailapp .venv/bin/python -m app.cli admin-add admin superadmin --password
```

Дальше в панели `https://<ADMIN_HOSTNAME>/`: создать домен, выпустить DKIM, прописать DNS-записи из карточки
домена, завести ящики. С рабочего ПК вместо входа на сервер — `bash install/deploy.sh` (заливка по SSH и установка).

## Документация

- [Установка](docs/install.md) · [Настройка (все ключи `.env`)](docs/configuration.md) · [Эксплуатация](docs/operations.md)
- [Архитектура](docs/architecture.md) · [Безопасность](docs/security.md) · [Контракт API](docs/api.md)
- [Active Directory](docs/active-directory.md) · [Веб-почта](docs/webmail.md) · [Миграция с iRedMail](docs/migration-iredmail.md)
- [Как участвовать](CONTRIBUTING.md) · [История изменений](CHANGELOG.md) · [Сообщить об уязвимости](SECURITY.md)

Интерфейс панели и документация — на русском языке; код, API и конфигурация — на английском.

## Чего здесь нет

- Своего веб-клиента: рендер чужого HTML — главный источник уязвимостей, это делает Roundcube на отдельном
  хосте ([`docs/webmail.md`](docs/webmail.md)).
- CalDAV/CardDAV/JMAP — у Dovecot их нет; календарь при необходимости — отдельный сервис.
- Кластеризации и Docker: один хост, бэкап на уровне VM и `pg_dump`.

## Лицензия

GNU General Public License v3.0 или новее — см. [`LICENSE`](LICENSE). Copyright © 2026 Pochtamt contributors.
