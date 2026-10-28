-- ============================================================================
--  Роли базы. Пароли подставляет install/render.py из install/.env (плейсхолдеры @...@).
--    mail_app     — бэкенд: таблицы (журнал аудита — только добавление);
--    mail_postfix — Postfix: только представления v_postfix_*;
--    mail_dovecot — Dovecot: только представления v_dovecot_* (хеши паролей видит только он).
--  Раздельные роли: компрометация Postfix (процесс, обращённый в интернет) не даёт хешей паролей ящиков,
--  а компрометация Dovecot — пароля smarthost.
--  Применяется ПОСЛЕ schema.sql и schema_settings.sql (все GRANT — здесь, в одном месте).
-- ============================================================================
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mail_app') THEN
        CREATE ROLE mail_app LOGIN PASSWORD '@DB_APP_PASSWORD@';
    ELSE
        ALTER ROLE mail_app WITH PASSWORD '@DB_APP_PASSWORD@';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mail_postfix') THEN
        CREATE ROLE mail_postfix LOGIN PASSWORD '@DB_POSTFIX_PASSWORD@';
    ELSE
        ALTER ROLE mail_postfix WITH PASSWORD '@DB_POSTFIX_PASSWORD@';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mail_dovecot') THEN
        CREATE ROLE mail_dovecot LOGIN PASSWORD '@DB_DOVECOT_PASSWORD@';
    ELSE
        ALTER ROLE mail_dovecot WITH PASSWORD '@DB_DOVECOT_PASSWORD@';
    END IF;
    -- прежняя общая роль только для чтения (до разделения) больше не нужна
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mail_ro') THEN
        DROP OWNED BY mail_ro;
        DROP ROLE mail_ro;
    END IF;
END $$;

GRANT CONNECT ON DATABASE mail TO mail_app, mail_postfix, mail_dovecot;
GRANT USAGE ON SCHEMA public TO mail_app, mail_postfix, mail_dovecot;

-- бэкенд
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO mail_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO mail_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mail_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO mail_app;
-- журнал действий неизменяем: скомпрометированный бэкенд не может стереть следы
REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM mail_app;

-- Postfix: только представления (smarthost-пароль — v_postfix_sasl_password — доступен только ему)
GRANT SELECT ON v_postfix_domains, v_postfix_mailboxes, v_postfix_aliases, v_postfix_alias_domains,
                v_postfix_sender_login, v_postfix_transport, v_postfix_sasl_password, v_postfix_tls_policy,
                v_postfix_bcc, v_postfix_client_access, v_postfix_sender_access, v_postfix_recipient_access,
                v_postfix_recipient_internal TO mail_postfix;

-- Dovecot: пароли и пользователи
GRANT SELECT ON v_dovecot_auth, v_dovecot_users TO mail_dovecot;
