# Образ SOGo из пакетов Debian 13 (тот же выпуск, что и на хосте): sogod, ActiveSync, memcached.
# Собирается install.sh на самом почтовом хосте (docker compose build), контейнер работает в сети хоста
# и слушает только 127.0.0.1:20000; наружу его публикует nginx хоста (install/nginx/sogo.conf).
FROM debian:trixie-slim

# фиксированные uid/gid: файлы конфига и данных на хосте принадлежат 950:950
RUN groupadd -g 950 sogo && useradd -u 950 -g 950 -d /var/lib/sogo -s /usr/sbin/nologin sogo

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        sogo sogo-activesync memcached ca-certificates tzdata util-linux \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 0755 /usr/local/bin/entrypoint.sh

# /etc/sogo/sogo.conf и /var/lib/sogo монтируются с хоста; /srv/www — статика для nginx хоста
VOLUME ["/var/lib/sogo", "/srv/www"]
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
