-- Admin role + hallm application database, schemas, and grants.
--
-- Connects as the postgres superuser (PGUSER) and runs first by lex order;
-- every other bootstrap script assumes the hallm role exists.
--
-- Substituted via `envsubst` before psql sees the file.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${HALLM_DB_USER}') THEN
        EXECUTE format(
            'CREATE ROLE %I WITH LOGIN SUPERUSER PASSWORD %L',
            '${HALLM_DB_USER}',
            '${HALLM_DB_PASSWORD}'
        );
    END IF;
END
$$;

SELECT format('CREATE DATABASE %I OWNER %I', '${HALLM_DB_NAME}', '${HALLM_DB_USER}')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${HALLM_DB_NAME}')
\gexec

\connect ${HALLM_DB_NAME}

CREATE SCHEMA IF NOT EXISTS hallm;
CREATE SCHEMA IF NOT EXISTS library;

GRANT USAGE, CREATE ON SCHEMA hallm   TO "${HALLM_DB_USER}";
GRANT USAGE, CREATE ON SCHEMA library TO "${HALLM_DB_USER}";
GRANT ALL PRIVILEGES  ON SCHEMA hallm   TO "${HALLM_DB_USER}";
GRANT ALL PRIVILEGES  ON SCHEMA library TO "${HALLM_DB_USER}";
