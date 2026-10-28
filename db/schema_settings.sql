-- ============================================================================
--  Расширенные настройки сервера (применяется после schema.sql, так же идемпотентно):
--  маршрутизация и smarthost, TLS-политики, BCC, политики доступа SMTP, режимы ящиков,
--  автоответ. Postfix читает представления v_postfix_* под ролями mail_postfix / mail_dovecot.
--  Применяется: psql -U postgres -d mail -f db/schema_settings.sql
-- ============================================================================

-- глобальные параметры «ключ — значение» (smarthost и т.п.; секреты тоже здесь, доступ только mail_app)
CREATE TABLE IF NOT EXISTS settings (
    key             text PRIMARY KEY,
    value           text        NOT NULL DEFAULT '',
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- домен: транспорт, BCC, исходящая ----
CREATE TABLE IF NOT EXISTS domain_settings (
    domain          citext PRIMARY KEY REFERENCES domains(name) ON DELETE CASCADE,
    transport       text,                                 -- Postfix transport, напр. smtp:[relay.example.com]:25; NULL = локально
    bcc_address     citext,                               -- скрытая копия всех входящих и исходящих писем домена (журналирование)
    outbound_allowed boolean    NOT NULL DEFAULT true,    -- false: пользователи домена пишут только внутрь сервера
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- ящик: режим, автоответ, BCC ----
ALTER TABLE mailboxes ADD COLUMN IF NOT EXISTS mode text NOT NULL DEFAULT 'normal'
    CHECK (mode IN ('normal', 'receive_only', 'send_only', 'internal'));
-- normal — обычный; receive_only — не может отправлять; send_only — не принимает; internal — пишет только внутрь сервера

CREATE TABLE IF NOT EXISTS mailbox_settings (
    address         citext PRIMARY KEY REFERENCES mailboxes(address) ON DELETE CASCADE,
    autoreply_enabled boolean  NOT NULL DEFAULT false,
    autoreply_subject text     NOT NULL DEFAULT '',
    autoreply_body  text        NOT NULL DEFAULT '',
    autoreply_from  date,                                 -- NULL = без ограничения по датам
    autoreply_to    date,
    sieve_custom    text        NOT NULL DEFAULT '',      -- пользовательские правила Sieve (текст), включаются в скрипт панели
    bcc_address     citext,                               -- скрытая копия писем этого ящика
    sieve_synced_at timestamptz,                          -- когда скрипт последний раз залит через ManageSieve
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- TLS к доменам-получателям ----
CREATE TABLE IF NOT EXISTS tls_policies (
    domain          citext PRIMARY KEY,                   -- домен получателя (или nexthop smarthost в квадратных скобках)
    policy          text        NOT NULL CHECK (policy IN ('none', 'may', 'encrypt', 'dane', 'dane-only', 'verify', 'secure')),
    params          text        NOT NULL DEFAULT '',      -- дополнительно, напр. match=.example.com
    comment         text        NOT NULL DEFAULT '',
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- политики доступа SMTP ----
CREATE TABLE IF NOT EXISTS access_rules (
    id              serial PRIMARY KEY,
    kind            text        NOT NULL CHECK (kind IN ('client', 'sender', 'recipient')),
    pattern         text        NOT NULL,                 -- client: IP или префикс (10.0.5 / 10.0); sender/recipient: адрес или домен
    action          text        NOT NULL CHECK (action IN ('OK', 'REJECT', 'DISCARD')),
    message         text        NOT NULL DEFAULT '',      -- текст отказа (для REJECT)
    comment         text        NOT NULL DEFAULT '',
    active          boolean     NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (kind, pattern)
);

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['domain_settings', 'mailbox_settings', 'tls_policies', 'settings'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS %I_touch ON %I', t, t);
        EXECUTE format('CREATE TRIGGER %I_touch BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION touch_updated_at()', t, t);
    END LOOP;
END $$;

-- ============================================================================
--  Представления для Postfix
-- ============================================================================

-- transport_maps: транспорт по домену; '*' — smarthost для всего остального (settings smarthost_*)
CREATE OR REPLACE VIEW v_postfix_transport AS
    SELECT ds.domain::text AS domain, ds.transport
      FROM domain_settings ds JOIN domains d ON d.name = ds.domain
     WHERE ds.transport IS NOT NULL AND ds.transport <> '' AND d.active
    UNION ALL
    -- свои домены доставляем локально ЯВНО: иначе '*' (smarthost) перехватил бы и входящую почту на наши ящики
    SELECT v.domain::text, 'lmtp:unix:private/dovecot-lmtp'
      FROM v_postfix_domains v
     WHERE NOT EXISTS (SELECT 1 FROM domain_settings ds
                        WHERE ds.domain = v.domain AND ds.transport IS NOT NULL AND ds.transport <> '')
    UNION ALL
    SELECT '*', 'smtp:[' || h.value || ']:' || COALESCE(NULLIF(p.value, ''), '25')
      FROM settings h LEFT JOIN settings p ON p.key = 'smarthost_port'
     WHERE h.key = 'smarthost_host' AND h.value <> ''
       AND COALESCE((SELECT value FROM settings WHERE key = 'smarthost_enabled'), 'false') = 'true';

-- smtp_sasl_password_maps: логин:пароль для smarthost (Postfix ищет по nexthop '[host]:port', затем по host)
CREATE OR REPLACE VIEW v_postfix_sasl_password AS
    SELECT '[' || h.value || ']:' || COALESCE(NULLIF(p.value, ''), '25') AS nexthop,
           u.value || ':' || COALESCE(w.value, '') AS credentials
      FROM settings h
      LEFT JOIN settings p ON p.key = 'smarthost_port'
      LEFT JOIN settings u ON u.key = 'smarthost_user'
      LEFT JOIN settings w ON w.key = 'smarthost_password'
     WHERE h.key = 'smarthost_host' AND h.value <> '' AND COALESCE(u.value, '') <> '';

-- smtp_tls_policy_maps
CREATE OR REPLACE VIEW v_postfix_tls_policy AS
    SELECT domain::text AS domain, trim(policy || ' ' || params) AS policy FROM tls_policies;

-- recipient_bcc_maps / sender_bcc_maps: ключи — адрес ящика или '@domain'
CREATE OR REPLACE VIEW v_postfix_bcc AS
    SELECT ('@' || ds.domain)::text AS address, ds.bcc_address::text AS bcc
      FROM domain_settings ds JOIN domains d ON d.name = ds.domain
     WHERE ds.bcc_address IS NOT NULL AND d.active
    UNION ALL
    SELECT ms.address::text, ms.bcc_address::text
      FROM mailbox_settings ms JOIN mailboxes m ON m.address = ms.address
     WHERE ms.bcc_address IS NOT NULL AND m.active;

-- check_client_access: IP или префикс сети (Postfix сам спрашивает 1.2.3.4, 1.2.3, 1.2, 1)
CREATE OR REPLACE VIEW v_postfix_client_access AS
    SELECT pattern AS key, CASE WHEN action = 'REJECT' AND message <> '' THEN 'REJECT ' || message ELSE action END AS result
      FROM access_rules WHERE kind = 'client' AND active;

-- check_sender_access: правила + режимы ящиков (receive_only -> REJECT; internal или домен без исходящей -> класс internal_only)
CREATE OR REPLACE VIEW v_postfix_sender_access AS
    SELECT pattern AS key, CASE WHEN action = 'REJECT' AND message <> '' THEN 'REJECT ' || message ELSE action END AS result
      FROM access_rules WHERE kind = 'sender' AND active
    UNION ALL
    SELECT m.address::text, 'REJECT Mailbox is receive-only' FROM mailboxes m WHERE m.active AND m.mode = 'receive_only'
    UNION ALL
    SELECT m.address::text, 'internal_only' FROM mailboxes m WHERE m.active AND m.mode = 'internal'
    UNION ALL
    -- ключ домена без '@': access-карты Postfix ищут «user@domain», «domain» и «user@», но не «@domain»
    SELECT ds.domain::text, 'internal_only'
      FROM domain_settings ds JOIN domains d ON d.name = ds.domain WHERE NOT ds.outbound_allowed AND d.active;

-- check_recipient_access: правила + send_only -> REJECT
CREATE OR REPLACE VIEW v_postfix_recipient_access AS
    SELECT pattern AS key, CASE WHEN action = 'REJECT' AND message <> '' THEN 'REJECT ' || message ELSE action END AS result
      FROM access_rules WHERE kind = 'recipient' AND active
    UNION ALL
    SELECT m.address::text, 'REJECT Mailbox is send-only' FROM mailboxes m WHERE m.active AND m.mode = 'send_only';

-- класс internal_only: получатели в наших доменах — OK, остальное отклоняется (main.cf: smtpd_restriction_classes)
CREATE OR REPLACE VIEW v_postfix_recipient_internal AS
    SELECT domain::text AS key, 'OK'::text AS result FROM v_postfix_domains;

-- права на представления и таблицы выдаёт db/roles.sql (он применяется после схем, когда роли уже существуют)

-- ---------------------------------------------------------------- история нагрузки (раз в 5 минут, cli system-sample) ----
CREATE TABLE IF NOT EXISTS system_samples (
    ts              timestamptz PRIMARY KEY DEFAULT now(),
    load1           real        NOT NULL DEFAULT 0,
    cpu_percent     real        NOT NULL DEFAULT 0,
    mem_used        bigint      NOT NULL DEFAULT 0,
    mem_total       bigint      NOT NULL DEFAULT 0,
    disk_used       bigint      NOT NULL DEFAULT 0,      -- корневой раздел
    disk_total      bigint      NOT NULL DEFAULT 0,
    vmail_used      bigint      NOT NULL DEFAULT 0,      -- раздел /var/vmail (или тот же, что корень)
    vmail_total     bigint      NOT NULL DEFAULT 0,
    queue_active    integer     NOT NULL DEFAULT 0,
    queue_deferred  integer     NOT NULL DEFAULT 0,
    sessions_imap   integer     NOT NULL DEFAULT 0,
    delivered_1h    integer     NOT NULL DEFAULT 0,      -- за последний час по логу Postfix
    sent_out_1h     integer     NOT NULL DEFAULT 0,
    bounced_1h      integer     NOT NULL DEFAULT 0,
    deferred_1h     integer     NOT NULL DEFAULT 0,
    rejected_1h     integer     NOT NULL DEFAULT 0,
    rspamd_scanned  bigint      NOT NULL DEFAULT 0,      -- накопительный счётчик Rspamd
    rspamd_spam     bigint      NOT NULL DEFAULT 0
);
