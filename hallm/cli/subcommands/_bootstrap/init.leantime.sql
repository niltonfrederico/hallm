-- Leantime database, role, and grants.
--
-- Connects as the hallm admin (via PGUSER); creates a dedicated
-- leantime role and database, then re-connects into the new database
-- to land schema-level grants on the right target.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${LEANTIME_DB_USER}') THEN
        EXECUTE format(
            'CREATE ROLE %I WITH LOGIN PASSWORD %L',
            '${LEANTIME_DB_USER}',
            '${LEANTIME_DB_PASSWORD}'
        );
    END IF;
END
$$;

SELECT format('CREATE DATABASE %I OWNER %I', '${LEANTIME_DB_NAME}', '${LEANTIME_DB_USER}')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${LEANTIME_DB_NAME}')
\gexec

GRANT CREATE, CONNECT ON DATABASE "${LEANTIME_DB_NAME}" TO "${LEANTIME_DB_USER}";

\connect ${LEANTIME_DB_NAME}

GRANT ALL ON SCHEMA public TO "${LEANTIME_DB_USER}";
ALTER SCHEMA public OWNER TO "${LEANTIME_DB_USER}";
