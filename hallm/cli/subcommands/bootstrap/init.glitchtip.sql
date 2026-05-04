-- Glitchtip database, role, and grants.
--
-- Connects as the hallm admin (via PGUSER); creates a dedicated
-- glitchtip role and database, then re-connects into the new database
-- to land schema-level grants on the right target.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${GLITCHTIP_DB_USER}') THEN
        EXECUTE format(
            'CREATE ROLE %I WITH LOGIN PASSWORD %L',
            '${GLITCHTIP_DB_USER}',
            '${GLITCHTIP_DB_PASSWORD}'
        );
    END IF;
END
$$;

SELECT format('CREATE DATABASE %I OWNER %I', '${GLITCHTIP_DB_NAME}', '${GLITCHTIP_DB_USER}')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${GLITCHTIP_DB_NAME}')
\gexec

GRANT CREATE, CONNECT ON DATABASE "${GLITCHTIP_DB_NAME}" TO "${GLITCHTIP_DB_USER}";

\connect ${GLITCHTIP_DB_NAME}

GRANT ALL ON SCHEMA public TO "${GLITCHTIP_DB_USER}";
ALTER SCHEMA public OWNER TO "${GLITCHTIP_DB_USER}";
