#!/usr/bin/env bash
# ============================================================================
#  Забрать готовый TLS-сертификат с другого хоста по SSH (например, с обратного прокси, где его выпускает ACME)
#  и положить на почтовый сервер. Альтернатива certbot на самом сервере (CERTBOT_EMAIL в install/.env).
#      bash install/fetch-cert.sh            # скачать в install/certs/ и залить на сервер, перечитать Postfix/Dovecot/nginx
#      bash install/fetch-cert.sh --local    # только скачать в install/certs/ (их подхватит install.sh через TLS_SRC_DIR)
#  Нужны в install/.env: CERT_HOST, CERT_USER, CERT_DIR, CERT_FULLCHAIN_FILE, CERT_KEY_FILE, SSH_KEY;
#  для заливки — VM_HOST, VM_USER, TLS_CERT, TLS_KEY. После продления сертификата на том хосте запустить снова
#  (или поставить в планировщик раз в месяц).
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."
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
: "${CERT_HOST:?}" "${CERT_USER:?}" "${CERT_DIR:?}" "${SSH_KEY:?}"
SSH_KEY=${SSH_KEY/#\~/$HOME}
OUT=install/certs
mkdir -p "$OUT"

echo "== скачиваю с $CERT_USER@$CERT_HOST:$CERT_DIR"
# в пути бывает '*' (каталоги wildcard-сертификатов) — экранируем, чтобы удалённый shell не раскрыл его как маску
RDIR=$(printf '%q' "$CERT_DIR")
scp -q -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "$CERT_USER@$CERT_HOST:$RDIR/${CERT_FULLCHAIN_FILE:-fullchain.pem}" "$OUT/fullchain.pem"
scp -q -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "$CERT_USER@$CERT_HOST:$RDIR/${CERT_KEY_FILE:-privkey.pem}" "$OUT/privkey.pem"
chmod 0600 "$OUT/privkey.pem"
openssl x509 -in "$OUT/fullchain.pem" -noout -subject -enddate | sed 's/^/   /'
# ключ и сертификат должны совпадать
[ "$(openssl x509 -in "$OUT/fullchain.pem" -noout -pubkey)" = "$(openssl pkey -in "$OUT/privkey.pem" -pubout)" ] \
    || { echo "ОШИБКА: ключ не подходит к сертификату"; exit 1; }

[ "${1:-}" = "--local" ] && { echo "готово: $OUT (на сервер попадёт при install.sh, TLS_SRC_DIR=$OUT)"; exit 0; }

: "${VM_HOST:?}" "${VM_USER:?}" "${TLS_CERT:?}" "${TLS_KEY:?}"
SSH="ssh -i $SSH_KEY -o StrictHostKeyChecking=accept-new $VM_USER@$VM_HOST"
echo "== заливаю на $VM_HOST: $TLS_CERT, $TLS_KEY"
scp -q -i "$SSH_KEY" "$OUT/fullchain.pem" "$OUT/privkey.pem" "$VM_USER@$VM_HOST:/tmp/"
$SSH "sudo install -d -m 0755 \"\$(dirname '$TLS_CERT')\" && sudo install -m 0644 -o root -g root /tmp/fullchain.pem '$TLS_CERT' \
    && sudo install -m 0640 -o root -g root /tmp/privkey.pem '$TLS_KEY' && rm -f /tmp/fullchain.pem /tmp/privkey.pem \
    && sudo systemctl reload postfix dovecot nginx && echo '   Postfix, Dovecot, nginx перечитали сертификат'"
