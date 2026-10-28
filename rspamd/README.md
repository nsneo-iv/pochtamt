# rspamd — антиспам, DKIM, ARC, DMARC

Все файлы кладутся в `/etc/rspamd/local.d/` (переопределяют значения по умолчанию, не заменяя их целиком).

| Файл | Что делает |
|---|---|
| `redis.conf` | адрес и пароль Redis — общий для bayes, DKIM-ключей, greylist |
| `dkim_signing.conf` | подпись DKIM; ключи берутся из Redis по домену заголовка From |
| `arc.conf` | ARC-подпись теми же ключами |
| `worker-proxy.inc` | milter для Postfix на 127.0.0.1:11332 |
| `worker-normal.inc` | сканер на 127.0.0.1:11333 |
| `worker-controller.inc` | веб-интерфейс и API на 127.0.0.1:11334, пароль хешем |
| `milter_headers.conf` | какие X-Spam-заголовки добавлять |
| `classifier-bayes.conf` | байес в Redis с автообучением |
| `actions.conf` | пороги greylist / add_header / reject |
| `dmarc.conf` | проверка DMARC, отчёты выключены |
| `ratelimit.conf` | лимит исходящих писем на аутентифицированного пользователя (взломанный ящик не станет рассыльщиком) |
| `options.inc` | свои сети (`LAN_NETS`), DNS-резолвер (локальный unbound с DNSSEC) |
| `antivirus.conf` | ClamAV по unix-сокету: вирус → reject на SMTP; части письма до 50 МБ |
| `multimap.conf` | белые/чёрные списки отправителей и IP из панели (карты в /var/lib/rspamd/maps) |
| `history_redis.conf` | история проверок в Redis — раздел «Фильтр» в панели |

Плейсхолдеры `@REDIS_PASSWORD@`, `@RSPAMD_PASSWORD_HASH@` и `@LAN_NETS_COMMA@` подставляет `install/render.py`
(хеш пароля контроллера считается `rspamadm pw` в `install.sh`).

## Антивирус

ClamAV (`clamav-daemon` + `clamav-freshclam`) ставится `install.sh`; Rspamd ходит к нему по сокету
`/run/clamav/clamd.ctl` (пользователь `_rspamd` в группе `clamav`). Вирус даёт символ `CLAMAV`,
модуль настроен на `action = reject`: письмо отбивается ещё на SMTP, отправителю уходит 5xx. Базы обновляет freshclam
раз в час. ClamAV держит ~1.2 ГБ RAM под сигнатуры — на VM должно быть не меньше 4 ГБ.

Проверка: отправить письмо с тестовой строкой EICAR во вложении, в логе Rspamd — `CLAMAV`,
в логе Postfix — `reject`.

## DKIM без файлов на хосте

Панель генерирует ключ (RSA 2048), сохраняет его в таблицу `dkim_keys` и кладёт в Redis:

```
HSET DKIM_PRIVATE_KEYS mail.example.com "<PEM-ключ целиком>"
HSET DKIM_SELECTORS    example.com mail
```

Rspamd при подписи берёт селектор и ключ из этих хешей. Если Redis пересоздан, `backend/cli.py dkim-sync`
заливает все ключи из базы заново. Текст DNS-записи панель показывает в карточке домена.

## Проверка

```bash
rspamadm configtest
rspamc stat
# отправить письмо через 587 и посмотреть DKIM-Signature в заголовках
```
