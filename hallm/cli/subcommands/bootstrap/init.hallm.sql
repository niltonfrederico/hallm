-- Create schemas
CREATE SCHEMA IF NOT EXISTS hallm;
CREATE SCHEMA IF NOT EXISTS library;

-- Create users
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'hallm') THEN
        CREATE ROLE hallm WITH LOGIN PASSWORD '##POSTGRES_PASSWORD##';
    END IF;

    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'paperless') THEN
        CREATE ROLE paperless WITH LOGIN PASSWORD '##PAPERLESS_DB_PASSWORD##';
    END IF;

    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'glitchtip') THEN
        CREATE ROLE glitchtip WITH LOGIN PASSWORD '##GLITCHTIP_DB_PASSWORD##';
    END IF;
END
$$;

GRANT USAGE ON SCHEMA hallm TO hallm;
GRANT USAGE ON SCHEMA library TO hallm;
GRANT ALL PRIVILEGES ON SCHEMA hallm TO hallm;
GRANT ALL PRIVILEGES ON SCHEMA library TO hallm;
