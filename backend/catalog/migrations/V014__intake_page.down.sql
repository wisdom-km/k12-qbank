-- Drop the intake table, the purpose check, and the issue date.
-- Stored intake rows are discarded. Existing page files stay.

DROP TABLE IF EXISTS intake_page;

ALTER TABLE files DROP CONSTRAINT IF EXISTS files_purpose_known;

ALTER TABLE papers DROP COLUMN IF EXISTS issued_on;
