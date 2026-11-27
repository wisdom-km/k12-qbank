-- R10 intake archive. Old rows stay NULL. No foreign key and no backfill.
-- The runner holds pg_advisory_xact_lock. This file does not.

ALTER TABLE intake_page ADD COLUMN archived_at timestamptz NULL;
