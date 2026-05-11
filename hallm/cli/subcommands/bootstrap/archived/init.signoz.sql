-- Read-only role used by the signoz-extras OTEL collector to scrape
-- pg_stat_* views via the postgresql receiver. Membership in pg_monitor
-- grants SELECT on system stats without exposing application data.
--
-- No service database is created here — the role queries the cluster's
-- shared stat views directly.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${SIGNOZ_MONITOR_USER}') THEN
        EXECUTE format(
            'CREATE ROLE %I WITH LOGIN PASSWORD %L',
            '${SIGNOZ_MONITOR_USER}',
            '${SIGNOZ_MONITOR_PASSWORD}'
        );
    END IF;
END
$$;

GRANT pg_monitor TO "${SIGNOZ_MONITOR_USER}";
