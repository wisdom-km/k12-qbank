-- R5 intake photos. Existing files rows stay purpose page. No UPDATE.
-- The runner holds pg_advisory_xact_lock. This file does not.

ALTER TABLE files ADD CONSTRAINT files_purpose_known
    CHECK (purpose IN ('page', 'intake'));

ALTER TABLE papers ADD COLUMN issued_on date;

CREATE TABLE intake_page (
    intake_id text PRIMARY KEY,
    paper_id text NOT NULL REFERENCES papers (paper_id),
    page_no integer NOT NULL,
    file_id text NOT NULL REFERENCES files (file_id),
    uploaded_by text NOT NULL,
    uploaded_at timestamptz NOT NULL,
    located_by text NOT NULL,
    superseded_at timestamptz NULL,
    CONSTRAINT intake_page_page_no CHECK (page_no >= 1),
    CONSTRAINT intake_page_located_by CHECK (located_by IN ('qr', 'manual'))
);

CREATE UNIQUE INDEX intake_page_current
    ON intake_page (paper_id, page_no)
    WHERE superseded_at IS NULL;
