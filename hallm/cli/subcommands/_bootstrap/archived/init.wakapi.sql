-- Wakapi database, role, and grants.
--
-- Connects as the hallm admin (via PGUSER); creates a dedicated
-- Wakapi role and database, then re-connects into the new database
-- to land schema-level grants on the right target.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${WAKAPI_DB_USER}') THEN
        EXECUTE format(
            'CREATE ROLE %I WITH LOGIN PASSWORD %L',
            '${WAKAPI_DB_USER}',
            '${WAKAPI_DB_PASSWORD}'
        );
    END IF;
END
$$;

SELECT format('CREATE DATABASE %I OWNER %I', '${WAKAPI_DB_NAME}', '${WAKAPI_DB_USER}')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${WAKAPI_DB_NAME}')
\gexec

GRANT CREATE, CONNECT ON DATABASE "${WAKAPI_DB_NAME}" TO "${WAKAPI_DB_USER}";

\connect ${WAKAPI_DB_NAME}

GRANT ALL ON SCHEMA public TO "${WAKAPI_DB_USER}";
ALTER SCHEMA public OWNER TO "${WAKAPI_DB_USER}";
