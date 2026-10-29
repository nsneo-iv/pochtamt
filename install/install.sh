#!/usr/bin/env bash
# ============================================================================
#  Установка Pochtamt на чистый Debian 13. Запускать от root на сервере:
#      git clone https://github.com/nsneo-iv/pochtamt.git /opt/mail   (или install/deploy.sh с рабочего ПК)
#      заполнить /opt/mail/install/.env, backend/.env, agent/.env (образцы — .env.example)
#      bash /opt/mail/install/install.sh
#  Идемпотентен: повторный запуск обновляет конфиги и перезапускает службы.
# ============================================================================
set -euo pipefail
REPO=${REPO:-/opt/mail}
cd "$REPO"

log() { echo -e "\n\033[1;32m== $*\033[0m"; }
die() { echo "ОШИБКА: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || die "запускать от root"
[ -f install/.env ] || die "нет install/.env"
[ -f backend/.env ] || die "нет backend/.env"
[ -f agent/.env ] || die "нет agent/.env"
# читаем .env построчно, не выполняя его как shell (в паролях бывают ; & $ и пробелы)
load_env() {
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in ''|'#'*) continue;; esac
        k=${line%%=*}; v=${line#*=}
        v=${v%\"}; v=${v#\"}; v=${v%\'}; v=${v#\'}
        export "$k=$v"
    done <"$1"
}
load_env install/.env
DOCKER_REGISTRY_MIRRORS_JSON=$(for m in ${DOCKER_REGISTRY_MIRRORS:-}; do printf '"%s", ' "$m"; done); DOCKER_REGISTRY_MIRRORS_JSON=${DOCKER_REGISTRY_MIRRORS_JSON%, }
if [ -n "${SOGO_HOSTNAME:-}" ]; then
    [ "$SOGO_HOSTNAME" != "$ADMIN_HOSTNAME" ] || die "SOGO_HOSTNAME должен отличаться от ADMIN_HOSTNAME (разные сайты nginx)"
    [ -n "${DB_SOGO_PASSWORD:-}" ] || die "задайте DB_SOGO_PASSWORD в install/.env"
fi

log "пакеты"
export DEBIAN_FRONTEND=noninteractive
# на первом старте cloud-образа apt занят unattended-upgrades — ждём
for i in $(seq 1 120); do fuser /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/lib/apt/lists/lock >/dev/null 2>&1 || break; sleep 5; done
debconf-set-selections <<<"postfix postfix/main_mailer_type select No configuration"
apt-get update -q
apt-get install -y -q postfix postfix-pgsql \
    dovecot-core dovecot-imapd dovecot-lmtpd dovecot-pgsql dovecot-ldap dovecot-sieve dovecot-managesieved \
    rspamd redis-server postgresql unbound clamav-daemon clamav-freshclam \
    nginx \
    python3 python3-venv python3-pip \
    fail2ban nftables ca-certificates curl git sudo openssl ldap-utils rsync

log "пользователи"
getent group vmail >/dev/null || groupadd -g 5000 vmail
id vmail >/dev/null 2>&1 || useradd -u 5000 -g vmail -d /var/vmail -s /usr/sbin/nologin -M vmail
install -d -o vmail -g vmail -m 0750 /var/vmail
id mailapp >/dev/null 2>&1 || useradd -r -d /opt/mail -s /usr/sbin/nologin mailapp
id mailagent >/dev/null 2>&1 || useradd -r -d /nonexistent -s /usr/sbin/nologin mailagent

log "/etc/hosts: имена сервера на себя"
sed -i "/ # mail-hostnames$/d" /etc/hosts
echo "127.0.1.1 ${MAIL_HOSTNAME} ${ADMIN_HOSTNAME} # mail-hostnames" >>/etc/hosts

log "TLS"
install -d -m 0755 /etc/ssl/mail          # каталог открыт: сертификат публичный, ключ 0640 root; агент читает срок действия
if [ -n "${TLS_SRC_DIR:-}" ]; then
    cp "$TLS_SRC_DIR/fullchain.pem" "$TLS_CERT"
    cp "$TLS_SRC_DIR/privkey.pem" "$TLS_KEY"
elif [ ! -f "$TLS_CERT" ]; then
    echo "TLS_SRC_DIR пуст — самоподписанный сертификат для стенда"
    openssl req -x509 -nodes -newkey rsa:2048 -days 365 -subj "/CN=${MAIL_HOSTNAME}" \
        -addext "subjectAltName=DNS:${MAIL_HOSTNAME},DNS:${ADMIN_HOSTNAME}${SOGO_HOSTNAME:+,DNS:$SOGO_HOSTNAME}" \
        -keyout "$TLS_KEY" -out "$TLS_CERT" 2>/dev/null
fi
chmod 0640 "$TLS_KEY"; chown root:root "$TLS_KEY" "$TLS_CERT"

log "Rspamd: хеш пароля"
if [ -z "${RSPAMD_PASSWORD_HASH:-}" ]; then
    [ -n "${RSPAMD_PASSWORD:-}" ] || die "задайте RSPAMD_PASSWORD в install/.env"
    RSPAMD_PASSWORD_HASH=$(rspamadm pw -p "$RSPAMD_PASSWORD")
    sed -i "s|^RSPAMD_PASSWORD_HASH=.*|RSPAMD_PASSWORD_HASH=${RSPAMD_PASSWORD_HASH}|" install/.env
    export RSPAMD_PASSWORD_HASH
fi

log "шаблоны -> install/out"
python3 install/render.py

log "PostgreSQL"
systemctl enable --now postgresql
sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='mail'" | grep -q 1 || sudo -u postgres createdb mail
sudo -u postgres psql -q -d mail -f db/schema.sql
sudo -u postgres psql -q -d mail -f db/schema_settings.sql
sudo -u postgres psql -q -d mail < install/out/db/roles.sql   # через stdin: каталог install закрыт для всех, кроме root

log "Redis"
sed -i "s|^# *requirepass .*|requirepass ${REDIS_PASSWORD}|; s|^requirepass .*|requirepass ${REDIS_PASSWORD}|" /etc/redis/redis.conf
grep -q "^requirepass" /etc/redis/redis.conf || echo "requirepass ${REDIS_PASSWORD}" >>/etc/redis/redis.conf
systemctl enable --now redis-server && systemctl restart redis-server

log "unbound (DNSSEC-резолвер для DANE и Rspamd; внутренние зоны AD — на контроллер домена)"
# внутренние зоны (AD_DNS_ZONE, AD_REVERSE_ZONES) без DNSSEC форвардятся на AD_FORWARD_DNS; без AD блок пустой
AD_ZONES_SERVER=""; AD_ZONES_FORWARD=""
if [ -n "${AD_DNS_ZONE:-}" ] && [ -n "${AD_FORWARD_DNS:-}" ]; then
    AD_ZONES_SERVER=$(printf '    domain-insecure: "%s"\n    private-domain: "%s"\n' "$AD_DNS_ZONE" "$AD_DNS_ZONE"
        for z in ${AD_REVERSE_ZONES:-}; do printf '    local-zone: "%s." nodefault\n    domain-insecure: "%s"\n' "$z" "$z"; done)
    AD_ZONES_FORWARD=$(for z in "$AD_DNS_ZONE" ${AD_REVERSE_ZONES:-}; do
        printf 'forward-zone:\n    name: "%s"\n    forward-addr: %s\n' "$z" "$AD_FORWARD_DNS"; done)
fi
cat >/etc/unbound/unbound.conf.d/mail.conf <<EOF
server:
    interface: 127.0.0.1
    access-control: 127.0.0.0/8 allow
    do-ip6: no
    harden-dnssec-stripped: yes
    prefetch: yes
${AD_ZONES_SERVER}
${AD_ZONES_FORWARD}
EOF
systemctl enable --now unbound && systemctl restart unbound
# systemd-resolved (cloud-образ) отправляем в unbound; сам он не валидирует — это делает unbound
install -d /etc/systemd/resolved.conf.d
cat >/etc/systemd/resolved.conf.d/mail.conf <<EOF
[Resolve]
DNS=127.0.0.1
Domains=~.
DNSSEC=no
EOF
systemctl restart systemd-resolved 2>/dev/null || true
# LLMNR/mDNS на почтовом сервере не нужны (порт 5355 слушает на всех интерфейсах)
cat >>/etc/systemd/resolved.conf.d/mail.conf <<EOF
LLMNR=no
MulticastDNS=no
EOF
systemctl restart systemd-resolved 2>/dev/null || true

# sshd: только ключи, без root и пробросов (файл drop-in, основной sshd_config не трогаем)
install -d /etc/ssh/sshd_config.d
cat >/etc/ssh/sshd_config.d/00-mail-hardening.conf <<EOF
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding no
MaxAuthTries 3
LoginGraceTime 30
EOF
if ! sshd -t; then
    rm -f /etc/ssh/sshd_config.d/00-mail-hardening.conf
    die "sshd не принял drop-in 00-mail-hardening.conf (файл убран, конфигурация прежняя)"
fi
systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || true
# Postfix (DANE) должен спрашивать unbound напрямую, а не stub 127.0.0.53 (он не отдаёт бит AD):
# /etc/resolv.conf -> список upstream-серверов resolved, первым там 127.0.0.1
ln -sf /run/systemd/resolve/resolv.conf /etc/resolv.conf

if [ -n "${AD_LDAP_URI:-}" ]; then
    log "Active Directory: ${AD_LDAP_URI}"
    AD_HOST=${AD_LDAP_URI#*://}; AD_HOST=${AD_HOST%%/*}; AD_HOST=${AD_HOST%%:*}
    getent hosts "$AD_HOST" >/dev/null || echo "ВНИМАНИЕ: $AD_HOST не резолвится (AD_DNS_ZONE / AD_FORWARD_DNS?)"
    if [[ "${AD_LDAP_URI}" == ldaps://* ]]; then
        AD_PORT=${AD_LDAP_URI##*:}; [[ "$AD_PORT" =~ ^[0-9]+$ ]] || AD_PORT=636
        ldaps_ok() { timeout 15 openssl s_client -connect "${AD_HOST}:${AD_PORT}" -verify_hostname "${AD_HOST}" </dev/null 2>&1 | grep -q "Verify return code: 0"; }
        if [ -n "${AD_CA_CERT:-}" ] && [ -f "$AD_CA_CERT" ]; then
            # сертификат DC (или его CA) закреплён файлом: никакого доверия «при первом обращении»
            openssl x509 -in "$AD_CA_CERT" -noout >/dev/null || die "$AD_CA_CERT не сертификат"
            cp "$AD_CA_CERT" /usr/local/share/ca-certificates/ad-dc.crt
            update-ca-certificates >/dev/null
        fi
        # без проверяемого LDAPS вход админов и ящиков auth=ad не работал бы молча — останавливаемся
        ldaps_ok || die "LDAPS ${AD_HOST}:${AD_PORT} не проверяется: положите сертификат DC/CA в ${AD_CA_CERT:-install/certs/ad-ca.pem} (tools/ad-ldaps-cert.ps1)"
        echo "LDAPS ${AD_HOST}:${AD_PORT}: сертификат проверяется"
    else
        echo "ВНИМАНИЕ: ${AD_LDAP_URI} без TLS — пароли пользователей идут на DC открытым текстом"
    fi
fi

log "Postfix"
install -d -m 0750 -o root -g postfix /etc/postfix/pgsql
cp install/out/postfix/main.cf install/out/postfix/master.cf /etc/postfix/
cp install/out/postfix/pgsql/*.cf /etc/postfix/pgsql/
chmod 0640 /etc/postfix/pgsql/*.cf; chown root:postfix /etc/postfix/pgsql/*.cf
postfix check
systemctl enable --now postfix && systemctl restart postfix

log "Dovecot"
[ -n "${SIEVE_MASTER_PASSWORD:-}" ] || die "задайте SIEVE_MASTER_PASSWORD в install/.env"
# allow_nets: вход «ящик*panel» принимается только с самого сервера (бэкенд -> ManageSieve), не из сети
echo "panel:$(doveadm pw -s BLF-CRYPT -p "$SIEVE_MASTER_PASSWORD")::::::allow_nets=127.0.0.1" >/etc/dovecot/master-users
chmod 0640 /etc/dovecot/master-users; chown root:dovecot /etc/dovecot/master-users
touch /etc/dovecot/panel.conf; chown root:dovecot /etc/dovecot/panel.conf; chmod 0644 /etc/dovecot/panel.conf
cp install/out/dovecot/dovecot.conf /etc/dovecot/dovecot.conf
chmod 0640 /etc/dovecot/dovecot.conf; chown root:dovecot /etc/dovecot/dovecot.conf
install -d /etc/dovecot/sieve/before.d
cp dovecot/sieve/before.d/*.sieve /etc/dovecot/sieve/before.d/
sievec /etc/dovecot/sieve/before.d/*.sieve || true
doveconf -n >/dev/null || die "doveconf: ошибка в конфиге (см. dovecot/README.md)"
systemctl enable --now dovecot && systemctl restart dovecot

log "ClamAV (антивирус для Rspamd)"
# clamd слушает unix-сокет; _rspamd читает его через группу clamav. Базы качает freshclam (первый раз — несколько минут)
sed -i "s|^LocalSocket .*|LocalSocket /run/clamav/clamd.ctl|; s|^LocalSocketGroup .*|LocalSocketGroup clamav|; s|^LocalSocketMode .*|LocalSocketMode 660|" /etc/clamav/clamd.conf
grep -q "^MaxFileSize" /etc/clamav/clamd.conf && sed -i "s|^MaxFileSize .*|MaxFileSize 50M|" /etc/clamav/clamd.conf || echo "MaxFileSize 50M" >>/etc/clamav/clamd.conf
grep -q "^MaxScanSize" /etc/clamav/clamd.conf && sed -i "s|^MaxScanSize .*|MaxScanSize 100M|" /etc/clamav/clamd.conf || echo "MaxScanSize 100M" >>/etc/clamav/clamd.conf
usermod -a -G clamav _rspamd
usermod -a -G clamav mailagent
# зеркала баз: официальный CDN блокирует регион, порядок — из CLAMAV_MIRRORS
sed -i "/^DatabaseMirror /d; /^# mail: mirrors$/d" /etc/clamav/freshclam.conf
{ echo "# mail: mirrors"; for m in ${CLAMAV_MIRRORS:-database.clamav.net}; do echo "DatabaseMirror $m"; done; } >>/etc/clamav/freshclam.conf
rm -f /var/lib/clamav/freshclam.dat        # сбросить cool-down после 403 от CDN
systemctl enable --now clamav-freshclam && systemctl restart clamav-freshclam
if [ ! -f /var/lib/clamav/main.cvd ] && [ ! -f /var/lib/clamav/main.cld ]; then
    echo "первая загрузка баз ClamAV (freshclam), ждём до 10 минут…"
    for i in $(seq 1 60); do { [ -f /var/lib/clamav/main.cvd ] || [ -f /var/lib/clamav/main.cld ]; } && break; sleep 10; done
fi
if [ -f /var/lib/clamav/main.cvd ] || [ -f /var/lib/clamav/main.cld ]; then
    systemctl enable --now clamav-daemon && systemctl restart clamav-daemon
else
    echo "ВНИМАНИЕ: баз ClamAV нет (database.clamav.net недоступен?) — clamd не запущен, Rspamd будет писать CLAMAV_FAIL;"
    echo "          положите main.cvd/daily.cvd/bytecode.cvd в /var/lib/clamav (chown clamav) и: systemctl restart clamav-daemon"
    systemctl enable clamav-daemon >/dev/null 2>&1 || true
fi

log "Rspamd"
# карты белых/чёрных списков: файлы принадлежат _rspamd, чтобы контроллер мог их сохранять из панели
install -d -o _rspamd -g _rspamd -m 0750 /var/lib/rspamd/maps
for m in whitelist_from blacklist_from whitelist_ip blacklist_ip; do
    [ -f /var/lib/rspamd/maps/$m.map ] || install -o _rspamd -g _rspamd -m 0640 /dev/null /var/lib/rspamd/maps/$m.map
done
cp install/out/rspamd/local.d/* /etc/rspamd/local.d/
chown root:_rspamd /etc/rspamd/local.d/*; chmod 0640 /etc/rspamd/local.d/*
rspamadm configtest >/dev/null || die "rspamadm configtest"
systemctl enable --now rspamd && systemctl restart rspamd

log "бэкенд"
# код и venv принадлежат root: скомпрометированный бэкенд (mailapp) не может переписать собственный код;
# ему доступен на чтение только свой .env
python3 -m venv backend/.venv
backend/.venv/bin/pip install -q -e backend
chown -R root:root "$REPO/backend"
chown root:mailapp backend/.env; chmod 0640 backend/.env
# секреты установки и агента нужны только root (агент получает копию в /etc/mail-agent.env)
chmod 0600 install/.env agent/.env; chown root:root install/.env agent/.env
# в install/out — пароли ролей БД, AD, Redis; в install/certs — ключ сертификата: каталог закрыт для всех, кроме root
chown -R root:root install; chmod 0700 install; chmod -R go-rwx install/out install/certs 2>/dev/null || true
cp install/out/install/mail-backend.service /etc/systemd/system/
cp install/out/install/mail-usage-sync.service install/out/install/mail-usage-sync.timer /etc/systemd/system/
cp install/out/install/mail-ad-sync.service install/out/install/mail-ad-sync.timer /etc/systemd/system/
cp install/out/install/mail-system-sample.service install/out/install/mail-system-sample.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now mail-backend mail-usage-sync.timer mail-system-sample.timer
if [ -n "${AD_LDAP_URI:-}" ]; then
    systemctl enable --now mail-ad-sync.timer
else
    systemctl disable --now mail-ad-sync.timer 2>/dev/null || true
fi
systemctl restart mail-backend

log "агент"
install -d -m 0755 /opt/mail-agent
cp agent/mail_agent.py /opt/mail-agent/
install -m 0755 -o root -g root agent/apply_settings.py /opt/mail-agent/apply_settings.py
install -m 0640 -o root -g mailagent agent/.env /etc/mail-agent.env
# сначала проверяем исходный файл: битый файл в /etc/sudoers.d ломает sudo для всех, включая администратора
visudo -cf install/out/install/sudoers-mail-agent >/dev/null || die "sudoers"
install -m 0440 install/out/install/sudoers-mail-agent /etc/sudoers.d/mail-agent
cp install/out/install/mail-agent.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now mail-agent && systemctl restart mail-agent

if [ -n "${SOGO_HOSTNAME:-}" ]; then
    log "SOGo в Docker: ${SOGO_HOSTNAME}"
    apt-get install -y -q docker.io docker-compose
    # Docker не должен трогать файрвол хоста (nftables): контейнер работает в сети хоста, NAT и мосты не нужны
    install -d /etc/docker
    DAEMON_JSON="{\"iptables\": false, \"ip6tables\": false, \"bridge\": \"none\", \"registry-mirrors\": [${DOCKER_REGISTRY_MIRRORS_JSON:-}]}"
    if [ "$(cat /etc/docker/daemon.json 2>/dev/null)" != "$DAEMON_JSON" ]; then
        echo "$DAEMON_JSON" >/etc/docker/daemon.json
        systemctl restart docker
    fi
    systemctl enable --now docker
    # роль, представление в базе mail и своя база sogo
    sudo -u postgres psql -q -d mail < install/out/sogo/db.sql
    sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='sogo'" | grep -q 1 || sudo -u postgres createdb -O sogo sogo
    # конфиг и данные: uid/gid 950 — пользователь sogo внутри контейнера
    install -d -m 0750 /etc/sogo
    install -m 0640 -o root -g 950 install/out/sogo/sogo.conf /etc/sogo/sogo.conf
    install -m 0644 install/out/sogo/docker-compose.yml /etc/sogo/docker-compose.yml
    rm -rf /etc/sogo/image && cp -r sogo/image /etc/sogo/image
    install -d -o 950 -g 950 -m 0750 /var/lib/sogo/data
    install -d -o 950 -g 950 -m 0755 /var/lib/sogo/www
    ( cd /etc/sogo && docker compose build --pull -q ) || die "сборка образа SOGo не удалась (доступ к Docker Hub и deb.debian.org?)"
    cp install/out/install/sogo.service /etc/systemd/system/
    systemctl daemon-reload && systemctl enable --now sogo && systemctl restart sogo
else
    systemctl disable --now sogo 2>/dev/null || true
    rm -f /etc/systemd/system/sogo.service
fi

log "фронтенд"
if [ -f frontend/dist/index.html ]; then
    echo "dist собран заранее (deploy.sh), сборка на сервере не нужна"
else
    apt-get install -y -q nodejs npm
    ( cd frontend && npm ci --silent && npm run build --silent )
fi

log "nginx"
rm -f /etc/nginx/sites-enabled/default
cp install/out/install/nginx/*.conf /etc/nginx/sites-available/
for f in install/out/install/nginx/*.conf; do ln -sf "/etc/nginx/sites-available/$(basename "$f")" /etc/nginx/sites-enabled/; done
install -d -m 0755 /var/www/acme
nginx -t && systemctl enable --now nginx && systemctl reload nginx

if [ -z "${TLS_SRC_DIR:-}" ] && [ -n "${CERTBOT_EMAIL:-}" ]; then
    log "TLS: Let's Encrypt (certbot, HTTP-01 через nginx на 80)"
    apt-get install -y -q certbot
    CERT_NAMES=${CERTBOT_DOMAINS:-"$MAIL_HOSTNAME${SOGO_HOSTNAME:+ $SOGO_HOSTNAME}"}
    DOMS=""; for d in $CERT_NAMES; do DOMS="$DOMS -d $d"; done
    FIRST=${CERT_NAMES%% *}
    # shellcheck disable=SC2086
    certbot certonly --webroot -w /var/www/acme $DOMS --cert-name "$FIRST" --non-interactive --agree-tos \
        -m "$CERTBOT_EMAIL" --keep-until-expiring --deploy-hook "systemctl reload postfix dovecot nginx" \
        || die "certbot не выпустил сертификат: порт 80 должен быть доступен снаружи, имена ${CERTBOT_DOMAINS:-$MAIL_HOSTNAME} — указывать на этот хост"
    ln -sf "/etc/letsencrypt/live/$FIRST/fullchain.pem" "$TLS_CERT"
    ln -sf "/etc/letsencrypt/live/$FIRST/privkey.pem" "$TLS_KEY"
    systemctl reload postfix dovecot nginx
    echo "сертификат Let's Encrypt: $FIRST, продление — таймер certbot.timer"
fi

log "fail2ban и nftables"
# jail'ы падают, если файла лога ещё нет — создаём пустые
touch /var/log/postfix.log /var/log/dovecot.log
# в логах адреса, IP и логины: читать может только root и группа adm
chown root:adm /var/log/postfix.log /var/log/dovecot.log; chmod 0640 /var/log/postfix.log /var/log/dovecot.log
cp install/out/install/fail2ban/*.conf /etc/fail2ban/jail.d/
systemctl enable --now fail2ban && systemctl restart fail2ban
cp install/out/install/nftables.conf /etc/nftables.conf
nft -c -f /etc/nftables.conf && systemctl enable --now nftables && systemctl restart nftables

log "готово"
cat <<EOF
Дальше:
  1. первый админ панели (выполнять из $REPO/backend):
       sudo -u mailapp $REPO/backend/.venv/bin/python -m app.cli admin-add admin superadmin --password
     с Active Directory вместо локального пароля: admin-add user@corp.local superadmin
  2. панель:   https://${ADMIN_HOSTNAME}/   (из сетей ${ADMIN_ALLOW_NETS})
     Rspamd:    https://${ADMIN_HOSTNAME}/rspamd/
  3. DNS: MX -> ${MAIL_HOSTNAME}, SPF, DKIM (из карточки домена в панели), DMARC, PTR.
  4. веб-почта (Roundcube и т.п.) — отдельный хост, ходит сюда по IMAP 993 / submission 587 / ManageSieve 4190 (docs/webmail.md)
${SOGO_HOSTNAME:+  5. SOGo (календарь, контакты, веб-почта, ActiveSync): https://${SOGO_HOSTNAME}/SOGo/ — вход адресом ящика и паролем}
EOF
