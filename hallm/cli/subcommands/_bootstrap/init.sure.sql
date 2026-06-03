-- Sure database, role, and grants.
--
-- Connects as the hallm admin (via PGUSER); creates a dedicated
-- sure role and database, then re-connects into the new database
-- to land schema-level grants on the right target.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${SURE_DB_USER}') THEN
        EXECUTE format(
            'CREATE ROLE %I WITH LOGIN PASSWORD %L',
            '${SURE_DB_USER}',
            '${SURE_DB_PASSWORD}'
        );
    END IF;
END
$$;

SELECT format('CREATE DATABASE %I OWNER %I', '${SURE_DB_NAME}', '${SURE_DB_USER}')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${SURE_DB_NAME}')
\gexec

GRANT CREATE, CONNECT ON DATABASE "${SURE_DB_NAME}" TO "${SURE_DB_USER}";

\connect ${SURE_DB_NAME}

GRANT ALL ON SCHEMA public TO "${SURE_DB_USER}";
ALTER SCHEMA public OWNER TO "${SURE_DB_USER}";
