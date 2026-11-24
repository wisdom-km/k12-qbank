-- R4e formula boundaries. New rows may store parts. Old rows stay NULL.
-- The runner holds pg_advisory_xact_lock. This file does not.

ALTER TABLE approvals ADD COLUMN stem_parts jsonb;

ALTER TABLE approvals ADD COLUMN option_parts jsonb;

ALTER TABLE practice_item ADD COLUMN stem_parts jsonb;

ALTER TABLE practice_item ADD COLUMN option_parts jsonb;

ALTER TABLE practice_item ADD COLUMN formula_draw jsonb;
