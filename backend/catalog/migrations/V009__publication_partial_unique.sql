-- One active row per binding. Retired rows may repeat.
-- The runner holds pg_advisory_xact_lock. This file does not.
-- Existing rows already have at most one active row, so nothing is rewritten.

ALTER TABLE publication DROP CONSTRAINT IF EXISTS publication_binding_unique;

CREATE UNIQUE INDEX IF NOT EXISTS publication_one_active
    ON publication (question_version_id, answer_version_id)
    WHERE status = 'active';
