-- R8 down. Drops only the source column. Paper rows stay.

ALTER TABLE papers DROP COLUMN IF EXISTS source_paper_id;
