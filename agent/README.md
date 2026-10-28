# agent — агент на почтовом хосте

Единственное место, где панель касается самого сервера. Чистый Python 3 без зависимостей.

| Файл | Что делает |
|---|---|
| `mail_agent.py` | HTTP-служба на 127.0.0.1:8025: очередь Postfix (список, flush, удаление письма), квоты Dovecot, ClamAV, параметры Postfix/Dovecot, состояние хоста (`/system`) |
| `apply_settings.py` | помощник с root-правами: глобальные параметры Postfix/Dovecot по белому списку (`get` / `set`) |
| `tests/test_parse.py` | разбор вывода `postqueue -j` и `doveadm quota` |

Устанавливается `install/install.sh`: пользователь `mailagent`, служба `mail-agent`, sudoers
`install/sudoers-mail-agent` ровно на шесть команд:

```
/usr/sbin/postqueue -j
/usr/sbin/postqueue -f
/usr/sbin/postsuper -d <ID>
/usr/bin/doveadm -f tab quota get -A
/usr/bin/systemctl restart clamav-freshclam
/opt/mail-agent/apply_settings.py get | set <служба> <ключ> <значение>
/usr/bin/doveadm -f tab who
/usr/bin/fail2ban-client status [<jail>]
/usr/bin/tail -c 20000000 /var/log/postfix.log
```

`apply_settings.py` — root-овый помощник и граница доверия для глобальных параметров: белый список ключей
и проверка значений зашиты в нём (копия реестра — `backend/app/services/hostconf.py`). Postfix — `postconf -e`
+ `postfix reload`; Dovecot — `/etc/dovecot/panel.conf` (включён в dovecot.conf через `!include_try`),
проверка `doveconf -n` с откатом и `doveadm reload`.

Версию баз ClamAV агент читает без sudo (`clamdscan --version`, `sigtool --info`): пользователь `mailagent`
состоит в группе `clamav` и видит сокет clamd.

Клиент передаёт только id письма, и тот проверяется регуляркой `^[A-Z0-9]{6,20}$`. Аутентификация —
общий токен `AGENT_TOKEN` (одинаковый в `agent/.env` и `backend/.env`), сравнение константное по времени.

Если бэкенд живёт на другом хосте, агент можно слушать на адресе внутренней сети (`AGENT_LISTEN=<ip>:8025`)
и открыть порт в nftables только для адреса бэкенда; по умолчанию — только localhost.
