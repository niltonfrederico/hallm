-- Heimdall database, role, and grants.
--
-- Connects as the hallm admin (via PGUSER); creates a dedicated
-- heimdall role and database, then re-connects into the new database
-- to land schema-level grants on the right target.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${HEIMDALL_DB_USER}') THEN
        EXECUTE format(
            'CREATE ROLE %I WITH LOGIN PASSWORD %L',
            '${HEIMDALL_DB_USER}',
            '${HEIMDALL_DB_PASSWORD}'
        );
    END IF;
END
$$;

SELECT format('CREATE DATABASE %I OWNER %I', '${HEIMDALL_DB_NAME}', '${HEIMDALL_DB_USER}')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${HEIMDALL_DB_NAME}')
\gexec

GRANT CREATE, CONNECT ON DATABASE "${HEIMDALL_DB_NAME}" TO "${HEIMDALL_DB_USER}";

\connect ${HEIMDALL_DB_NAME}

GRANT ALL ON SCHEMA public TO "${HEIMDALL_DB_USER}";
ALTER SCHEMA public OWNER TO "${HEIMDALL_DB_USER}";
