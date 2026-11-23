-- Reverse V009. schema_migrations stays; the runner deletes the version row.
-- This does not delete retired rows. Two retired rows for one binding make
-- the restore fail on purpose.

DROP INDEX IF EXISTS publication_one_active;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM publication
        GROUP BY question_version_id, answer_version_id, status
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION 'publication_binding_unique cannot be restored: a binding has more than one row with the same status';
    END IF;
END
$$;

ALTER TABLE publication
    ADD CONSTRAINT publication_binding_unique
    UNIQUE (question_version_id, answer_version_id, status);
