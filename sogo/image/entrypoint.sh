#!/usr/bin/env bash
# Точка входа контейнера SOGo: memcached + sogod в foreground, статика для nginx хоста,
# служебные задачи SOGo (напоминания по почте раз в минуту, чистка сессий раз в час).
# Конфиг — /etc/sogo/sogo.conf (с хоста, только чтение), данные — /var/lib/sogo (с хоста).
set -euo pipefail

[ -f /etc/sogo/sogo.conf ] || { echo "нет /etc/sogo/sogo.conf" >&2; exit 1; }
install -d -o sogo -g sogo -m 0750 /var/lib/sogo /var/lib/sogo/GNUstep /var/spool/sogo /run/sogo
# статика веб-интерфейса — в каталог, который nginx хоста отдаёт как /SOGo.woa/WebServerResources/
rm -rf /srv/www/* && cp -a /usr/share/GNUstep/SOGo/WebServerResources/. /srv/www/ && chmod -R a+rX /srv/www

WORKERS=${SOGO_WORKERS:-5}
# memcached — только на loopback (контейнер в сети хоста)
memcached -u sogo -l 127.0.0.1 -p 11211 -m 64 &

as_sogo() { setpriv --reuid=sogo --regid=sogo --init-groups "$@"; }
# напоминания о событиях по почте и чистка просроченных сессий (вместо cron хоста)
( while true; do sleep 60; as_sogo /usr/sbin/sogo-ealarms-notify >/dev/null 2>&1 || true; done ) &
( while true; do sleep 3600; as_sogo /usr/sbin/sogo-tool expire-sessions 160 >/dev/null 2>&1 || true; done ) &

trap 'kill 0' TERM INT
# sogod слушает только localhost; лог — в stderr контейнера (journal службы sogo на хосте). -WOLogFile не задавать:
# после смены пользователя /dev/stdout (канал root) не открывается, и sogod молча завершается
exec setpriv --reuid=sogo --regid=sogo --init-groups /usr/sbin/sogod -WONoDetach YES \
    -WOPort 127.0.0.1:20000 -WOWorkersCount "$WORKERS" -WOPidFile /run/sogo/sogod.pid
