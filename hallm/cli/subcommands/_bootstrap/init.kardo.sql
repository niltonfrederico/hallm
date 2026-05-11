-- Kardo database, role, and grants.
--
-- Connects as the hallm admin (via PGUSER); creates a dedicated
-- Kardo role and database, then re-connects into the new database
-- to land schema-level grants on the right target.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${KARDO_DB_USER}') THEN
        EXECUTE format(
            'CREATE ROLE %I WITH LOGIN PASSWORD %L',
            '${KARDO_DB_USER}',
            '${KARDO_DB_PASSWORD}'
        );
    END IF;
END
$$;

SELECT format('CREATE DATABASE %I OWNER %I', '${KARDO_DB_NAME}', '${KARDO_DB_USER}')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${KARDO_DB_NAME}')
\gexec

GRANT CREATE, CONNECT ON DATABASE "${KARDO_DB_NAME}" TO "${KARDO_DB_USER}";

\connect ${KARDO_DB_NAME}

GRANT ALL ON SCHEMA public TO "${KARDO_DB_USER}";
ALTER SCHEMA public OWNER TO "${KARDO_DB_USER}";
