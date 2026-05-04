-- Paperless database, role, and grants.
--
-- Connects as the hallm admin (via PGUSER); creates a dedicated
-- paperless role and database, then re-connects into the new database
-- to land schema-level grants on the right target.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${PAPERLESS_DB_USER}') THEN
        EXECUTE format(
            'CREATE ROLE %I WITH LOGIN PASSWORD %L',
            '${PAPERLESS_DB_USER}',
            '${PAPERLESS_DB_PASSWORD}'
        );
    END IF;
END
$$;

SELECT format('CREATE DATABASE %I OWNER %I', '${PAPERLESS_DB_NAME}', '${PAPERLESS_DB_USER}')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${PAPERLESS_DB_NAME}')
\gexec

GRANT CREATE, CONNECT ON DATABASE "${PAPERLESS_DB_NAME}" TO "${PAPERLESS_DB_USER}";

\connect ${PAPERLESS_DB_NAME}

GRANT ALL ON SCHEMA public TO "${PAPERLESS_DB_USER}";
ALTER SCHEMA public OWNER TO "${PAPERLESS_DB_USER}";
