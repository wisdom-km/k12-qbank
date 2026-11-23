-- Institution student number. One database is one institution.
-- The runner holds pg_advisory_xact_lock. This file does not.
-- Existing rows receive placeholder ids (synth-0001, ...). Those are not real student numbers.
-- Down drops external_id. Stored external_id values are discarded.

ALTER TABLE students ADD COLUMN external_id text;

UPDATE students AS student
SET external_id = numbered.external_id
FROM (
    SELECT student_id,
           'synth-' || lpad(row_number() OVER (ORDER BY created_at, student_id)::text, 4, '0') AS external_id
    FROM students
) AS numbered
WHERE student.student_id = numbered.student_id
  AND student.external_id IS NULL;

ALTER TABLE students ALTER COLUMN external_id SET NOT NULL;

ALTER TABLE students ADD CONSTRAINT students_external_id_key UNIQUE (external_id);

ALTER TABLE students ALTER COLUMN name DROP NOT NULL;
