-- Run once as a superuser AFTER migrations. The application connects as novacloud_app, which cannot
-- rewrite history in audit_log (the trigger in migration 0001 is a second line of defence).
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'novacloud_app') THEN
    CREATE ROLE novacloud_app LOGIN PASSWORD 'change-me';
  END IF;
END $$;
GRANT USAGE ON SCHEMA public TO novacloud_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO novacloud_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO novacloud_app;
REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM novacloud_app;
