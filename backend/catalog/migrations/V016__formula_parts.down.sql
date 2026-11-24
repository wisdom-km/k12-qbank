-- Drop only the columns added for formula parts. Existing rows are not rewritten.

ALTER TABLE practice_item DROP COLUMN IF EXISTS formula_draw;

ALTER TABLE practice_item DROP COLUMN IF EXISTS option_parts;

ALTER TABLE practice_item DROP COLUMN IF EXISTS stem_parts;

ALTER TABLE approvals DROP COLUMN IF EXISTS option_parts;

ALTER TABLE approvals DROP COLUMN IF EXISTS stem_parts;
