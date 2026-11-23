-- Reverse V011. schema_migrations stays; the runner deletes the version row.
-- Stored qr_printed, printed_external_id, stem_text, and answer_text values are discarded.

ALTER TABLE practice_item DROP COLUMN IF EXISTS answer_text;

ALTER TABLE practice_item DROP COLUMN IF EXISTS stem_text;

ALTER TABLE papers DROP COLUMN IF EXISTS printed_external_id;

ALTER TABLE papers DROP COLUMN IF EXISTS qr_printed;
