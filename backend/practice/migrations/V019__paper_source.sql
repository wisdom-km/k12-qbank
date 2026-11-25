-- R8 follow-up papers. Old rows stay NULL. No foreign key and no backfill.
-- The runner holds pg_advisory_xact_lock. This file does not.

ALTER TABLE papers ADD COLUMN source_paper_id text NULL;
