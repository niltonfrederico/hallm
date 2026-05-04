-- Read-only role used by the signoz-extras OTEL collector to scrape
-- pg_stat_* views via the postgresql receiver.  Membership in pg_monitor
-- grants SELECT on system stats without exposing application data.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'signoz_monitor') THEN
        CREATE ROLE signoz_monitor WITH LOGIN PASSWORD '##POSTGRES_PASSWORD##';
    END IF;
END
$$;

GRANT pg_monitor TO signoz_monitor;
