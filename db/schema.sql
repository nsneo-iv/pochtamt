-- ============================================================================
--  Схема базы почтового сервера (PostgreSQL 15+).
--  Единственный источник правды: бэкенд пишет сюда, Postfix и Dovecot только читают
--  через представления v_postfix_* и v_dovecot_* под ролями mail_postfix / mail_dovecot (см. db/roles.sql).
--  Применяется: psql -U postgres -d mail -f db/schema.sql (идемпотентно).
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS citext;

-- ---------------------------------------------------------------- домены ----
CREATE TABLE IF NOT EXISTS domains (
    name            citext PRIMARY KEY,
    description     text        NOT NULL DEFAULT '',
    max_mailboxes   integer     NOT NULL DEFAULT 0,      -- 0 = без ограничения
    max_quota_mb    integer     NOT NULL DEFAULT 0,      -- потолок квоты одного ящика, 0 = без ограничения
    active          boolean     NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT domains_name_chk CHECK (name ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$')
);

-- доменные алиасы: всё, что пришло на user@alias_domain, доставляется user@target_domain
CREATE TABLE IF NOT EXISTS domain_aliases (
    alias_domain    citext PRIMARY KEY,
    target_domain   citext      NOT NULL REFERENCES domains(name) ON DELETE CASCADE,
    active          boolean     NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT domain_aliases_not_self CHECK (alias_domain <> target_domain)
);

-- ---------------------------------------------------------------- ящики ----
CREATE TABLE IF NOT EXISTS mailboxes (
    address         citext PRIMARY KEY,
    domain          citext      NOT NULL REFERENCES domains(name) ON DELETE RESTRICT,
    local_part      text        NOT NULL,
    name            text        NOT NULL DEFAULT '',
    auth            text        NOT NULL DEFAULT 'local' CHECK (auth IN ('local', 'ad')),
    ad_upn          text,                                 -- userPrincipalName в AD при auth = 'ad'
    password        text,                                 -- хеш в формате Dovecot ({BLF-CRYPT}$2b$...), только auth = 'local'
    quota_mb        integer     NOT NULL DEFAULT 1024,    -- 0 = без ограничения
    active          boolean     NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT mailboxes_address_chk CHECK (address = (local_part || '@' || domain)::citext),
    CONSTRAINT mailboxes_auth_chk CHECK (
        (auth = 'local' AND ad_upn IS NULL) OR (auth = 'ad' AND ad_upn IS NOT NULL)
    )
);
CREATE INDEX IF NOT EXISTS mailboxes_domain_idx ON mailboxes(domain);

-- занятое место: бэкенд получает его от агента на хосте (doveadm quota) и пишет сюда (cli usage-sync)
CREATE TABLE IF NOT EXISTS mailbox_usage (
    address         citext PRIMARY KEY REFERENCES mailboxes(address) ON DELETE CASCADE,
    bytes           bigint      NOT NULL DEFAULT 0,
    messages        integer     NOT NULL DEFAULT 0,
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- алиасы ----
-- address = '@domain' — catch-all; address = адрес ящика — пересылка (ящик сам в targets = с копией)
CREATE TABLE IF NOT EXISTS aliases (
    address         citext PRIMARY KEY,
    domain          citext      NOT NULL REFERENCES domains(name) ON DELETE CASCADE,
    description     text        NOT NULL DEFAULT '',
    active          boolean     NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS aliases_domain_idx ON aliases(domain);

CREATE TABLE IF NOT EXISTS alias_targets (
    alias           citext      NOT NULL REFERENCES aliases(address) ON DELETE CASCADE,
    target          citext      NOT NULL,
    PRIMARY KEY (alias, target)
);

-- ---------------------------------------------------------------- рассылки ----
CREATE TABLE IF NOT EXISTS lists (
    address         citext PRIMARY KEY,
    domain          citext      NOT NULL REFERENCES domains(name) ON DELETE CASCADE,
    name            text        NOT NULL DEFAULT '',
    ad_group        text,                                 -- DN группы AD; если задан, состав ведёт синхронизация
    active          boolean     NOT NULL DEFAULT true,
    synced_at       timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS list_members (
    list            citext      NOT NULL REFERENCES lists(address) ON DELETE CASCADE,
    member          citext      NOT NULL,
    PRIMARY KEY (list, member)
);

-- ---------------------------------------------------------------- DKIM ----
-- Rspamd читает ключ из Redis (dkim_signing: use_redis); база — хранилище, из которого бэкенд его туда кладёт
CREATE TABLE IF NOT EXISTS dkim_keys (
    domain          citext PRIMARY KEY REFERENCES domains(name) ON DELETE CASCADE,
    selector        text        NOT NULL DEFAULT 'mail',
    private_key     text        NOT NULL,                 -- PEM
    public_key      text        NOT NULL,                 -- base64 DER для TXT-записи
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- админы ----
CREATE TABLE IF NOT EXISTS admins (
    login           citext PRIMARY KEY,                   -- локальный логин (admin) или UPN в AD (user@corp.local)
    display_name    text        NOT NULL DEFAULT '',
    role            text        NOT NULL CHECK (role IN ('superadmin', 'domain_admin')),
    password_hash   text,                                 -- {BLF-CRYPT}: локальный пароль; NULL — пароль проверяет AD
    active          boolean     NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE admins ADD COLUMN IF NOT EXISTS password_hash text;   -- обновление с ранних версий схемы

CREATE TABLE IF NOT EXISTS admin_domains (
    login           citext      NOT NULL REFERENCES admins(login) ON DELETE CASCADE,
    domain          citext      NOT NULL REFERENCES domains(name) ON DELETE CASCADE,
    PRIMARY KEY (login, domain)
);

-- ---------------------------------------------------------------- аудит ----
CREATE TABLE IF NOT EXISTS audit_log (
    id              bigserial PRIMARY KEY,
    ts              timestamptz NOT NULL DEFAULT now(),
    actor           text        NOT NULL,                 -- логин админа или 'system'
    action          text        NOT NULL,                 -- domain.create, mailbox.password, ...
    object          text        NOT NULL,                 -- адрес/домен, к которому относится
    details         jsonb       NOT NULL DEFAULT '{}'::jsonb,
    ip              inet
);
CREATE INDEX IF NOT EXISTS audit_log_ts_idx ON audit_log(ts DESC);
CREATE INDEX IF NOT EXISTS audit_log_object_idx ON audit_log(object);

-- ---------------------------------------------------------------- служебное ----
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END $$ LANGUAGE plpgsql;

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['domains', 'mailboxes', 'aliases', 'lists'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS %I_touch ON %I', t, t);
        EXECUTE format('CREATE TRIGGER %I_touch BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION touch_updated_at()', t, t);
    END LOOP;
END $$;

-- ============================================================================
--  Представления для Postfix (pgsql-карты в postfix/pgsql/*.cf)
-- ============================================================================

-- virtual_mailbox_domains: домены, за которые принимаем почту (включая доменные алиасы)
CREATE OR REPLACE VIEW v_postfix_domains AS
    SELECT name::text AS domain FROM domains WHERE active
    UNION
    SELECT da.alias_domain::text FROM domain_aliases da JOIN domains d ON d.name = da.target_domain
     WHERE da.active AND d.active;

-- virtual_mailbox_maps: существующие ящики (значение — путь Maildir относительно virtual_mailbox_base)
CREATE OR REPLACE VIEW v_postfix_mailboxes AS
    SELECT m.address::text AS address, (m.domain || '/' || m.local_part || '/')::text AS maildir
      FROM mailboxes m JOIN domains d ON d.name = m.domain
     WHERE m.active AND d.active;

-- virtual_alias_maps: алиасы, catch-all и рассылки.
-- Postfix спрашивает сначала полный адрес, потом '@domain'; доменные алиасы — отдельная карта ниже.
CREATE OR REPLACE VIEW v_postfix_aliases AS
    SELECT a.address::text AS address, t.target::text AS target
      FROM aliases a JOIN alias_targets t ON t.alias = a.address
      JOIN domains d ON d.name = a.domain
     WHERE a.active AND d.active
    UNION ALL
    SELECT l.address::text, lm.member::text
      FROM lists l JOIN list_members lm ON lm.list = l.address
      JOIN domains d ON d.name = l.domain
     WHERE l.active AND d.active
    UNION ALL
    -- «ящик сам себе»: без этого catch-all ('@domain') перехватывал бы почту СУЩЕСТВУЮЩИХ ящиков (Postfix ищет алиасы
    -- раньше ящиков). Если у ящика есть своя пересылка/рассылка с тем же адресом — она сама решает, кому доставлять.
    SELECT m.address::text, m.address::text
      FROM mailboxes m JOIN domains d ON d.name = m.domain
     WHERE m.active AND d.active
       AND NOT EXISTS (SELECT 1 FROM aliases a WHERE a.address = m.address AND a.active)
       AND NOT EXISTS (SELECT 1 FROM lists l WHERE l.address = m.address AND l.active);

-- доменные алиасы: карта по домену; адрес собирает Postfix в result_format (postfix/pgsql/virtual_alias_domains.cf)
CREATE OR REPLACE VIEW v_postfix_alias_domains AS
    SELECT da.alias_domain::text AS alias_domain, da.target_domain::text AS target_domain
      FROM domain_aliases da JOIN domains d ON d.name = da.target_domain
     WHERE da.active AND d.active;

-- smtpd_sender_login_maps: кто имеет право отправлять от какого адреса (ящик — сам, алиас — его цели-ящики).
-- Catch-all ('@domain') сюда не попадает: Postfix ищет и по '@domain', и получатель catch-all смог бы слать от любого адреса.
CREATE OR REPLACE VIEW v_postfix_sender_login AS
    SELECT m.address::text AS sender, m.address::text AS login FROM mailboxes m WHERE m.active
    UNION
    SELECT a.address::text, t.target::text
      FROM aliases a JOIN alias_targets t ON t.alias = a.address JOIN mailboxes m ON m.address = t.target
     WHERE a.active AND m.active AND a.address::text NOT LIKE '@%';

-- ============================================================================
--  Представления для Dovecot (dovecot/dovecot-sql.conf.ext)
-- ============================================================================

-- прежнее представление только для local-ящиков заменено на v_dovecot_auth
DROP VIEW IF EXISTS v_dovecot_passwd;

-- passdb: все активные ящики с признаком способа проверки (local — хеш из базы; ad — решает passdb ldap).
-- Логин, которого здесь нет, не пускается ни локально, ни через AD.
CREATE OR REPLACE VIEW v_dovecot_auth AS
    SELECT m.address::text AS username, m.password, m.auth
      FROM mailboxes m JOIN domains d ON d.name = m.domain
     WHERE m.active AND d.active;

-- userdb: домашний каталог и квота для всех активных ящиков (и local, и ad)
CREATE OR REPLACE VIEW v_dovecot_users AS
    SELECT m.address::text AS username,
           m.domain::text  AS domain,
           m.local_part    AS local_part,
           CASE WHEN m.quota_mb > 0 THEN (m.quota_mb::bigint * 1024 * 1024) ELSE 0 END AS quota_bytes,
           m.auth
      FROM mailboxes m JOIN domains d ON d.name = m.domain
     WHERE m.active AND d.active;

-- ============================================================================
--  Сводка для панели
-- ============================================================================
CREATE OR REPLACE VIEW v_domain_stats AS
    SELECT d.name AS domain,
           (SELECT count(*) FROM mailboxes m WHERE m.domain = d.name)   AS mailboxes,
           (SELECT count(*) FROM aliases a WHERE a.domain = d.name)     AS aliases,
           (SELECT count(*) FROM lists l WHERE l.domain = d.name)       AS lists,
           COALESCE((SELECT sum(u.bytes) FROM mailbox_usage u JOIN mailboxes m ON m.address = u.address
                      WHERE m.domain = d.name), 0) AS used_bytes
      FROM domains d;
