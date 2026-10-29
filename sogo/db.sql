-- Роль и представление для SOGo (применяется install.sh только при заданном SOGO_HOSTNAME, идемпотентно).
-- Роль sogo владеет своей базой `sogo` (SOGo создаёт таблицы сам) и читает из базы `mail` одно
-- представление v_sogo_users: локальные ящики с хешами паролей в формате Dovecot ({BLF-CRYPT}$2b$...),
-- которые SOGo проверяет сам (userPasswordAlgorithm = blf-crypt). Ящики auth = ad сюда не попадают:
-- их SOGo проверяет в Active Directory через источник ldap.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sogo') THEN
        CREATE ROLE sogo LOGIN PASSWORD '@DB_SOGO_PASSWORD@';
    ELSE
        ALTER ROLE sogo WITH PASSWORD '@DB_SOGO_PASSWORD@';
    END IF;
END $$;

CREATE OR REPLACE VIEW v_sogo_users AS
SELECT m.address::text                                    AS c_uid,
       m.address::text                                    AS c_name,
       m.password                                         AS c_password,
       COALESCE(NULLIF(m.name, ''), m.address::text)      AS c_cn,
       m.address::text                                    AS mail,
       m.domain::text                                     AS domain
  FROM mailboxes m
  JOIN domains d ON d.name = m.domain
 WHERE m.active AND d.active AND m.auth = 'local';

GRANT CONNECT ON DATABASE mail TO sogo;
GRANT SELECT ON v_sogo_users TO sogo;
