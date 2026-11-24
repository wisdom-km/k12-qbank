-- R4b slot layout. Old rows were one item per page and are not reflowed.
-- The runner holds pg_advisory_xact_lock. This file does not.
-- Down drops the new columns. Stored slot values are discarded.

ALTER TABLE papers ADD COLUMN slots_per_page integer NOT NULL DEFAULT 1;

ALTER TABLE practice_item ADD COLUMN page_no integer NOT NULL DEFAULT 1;

ALTER TABLE practice_item ADD COLUMN slot_no integer NOT NULL DEFAULT 1;

ALTER TABLE practice_item ADD COLUMN slot_span integer NOT NULL DEFAULT 1;

ALTER TABLE practice_item ADD COLUMN option_text text NOT NULL DEFAULT '';

ALTER TABLE approvals ADD COLUMN option_text text NOT NULL DEFAULT '';
