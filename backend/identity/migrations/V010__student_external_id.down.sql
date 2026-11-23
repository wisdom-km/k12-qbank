-- Down drops external_id. Stored external_id values are discarded.
-- A null name is replaced with '' so NOT NULL can be restored.
-- The runner holds pg_advisory_xact_lock. This file does not.

UPDATE students SET name = '' WHERE name IS NULL;

ALTER TABLE students ALTER COLUMN name SET NOT NULL;

ALTER TABLE students DROP CONSTRAINT IF EXISTS students_external_id_key;

ALTER TABLE students DROP COLUMN IF EXISTS external_id;
