-- Gitea database, role, and grants.
--
-- Connects as the hallm admin (via PGUSER); creates a dedicated
-- gitea role and database, then re-connects into the new database
-- to land schema-level grants on the right target.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${GITEA_DB_USER}') THEN
        EXECUTE format(
            'CREATE ROLE %I WITH LOGIN PASSWORD %L',
            '${GITEA_DB_USER}',
            '${GITEA_DB_PASSWORD}'
        );
    END IF;
END
$$;

SELECT format('CREATE DATABASE %I OWNER %I', '${GITEA_DB_NAME}', '${GITEA_DB_USER}')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${GITEA_DB_NAME}')
\gexec

GRANT CREATE, CONNECT ON DATABASE "${GITEA_DB_NAME}" TO "${GITEA_DB_USER}";

\connect ${GITEA_DB_NAME}

GRANT ALL ON SCHEMA public TO "${GITEA_DB_USER}";
ALTER SCHEMA public OWNER TO "${GITEA_DB_USER}";
