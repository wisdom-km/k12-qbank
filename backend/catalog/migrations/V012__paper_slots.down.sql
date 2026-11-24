-- Reverse V012. schema_migrations stays; the runner deletes the version row.
-- Stored slots_per_page, page_no, slot_no, slot_span, and option_text values are discarded.

ALTER TABLE approvals DROP COLUMN IF EXISTS option_text;

ALTER TABLE practice_item DROP COLUMN IF EXISTS option_text;

ALTER TABLE practice_item DROP COLUMN IF EXISTS slot_span;

ALTER TABLE practice_item DROP COLUMN IF EXISTS slot_no;

ALTER TABLE practice_item DROP COLUMN IF EXISTS page_no;

ALTER TABLE papers DROP COLUMN IF EXISTS slots_per_page;
