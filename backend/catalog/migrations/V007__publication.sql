-- Publication ledger. ADR 0015 item 5.
-- layout_template_id stays null. This batch has no writer for it.
-- status is the only CHECK. publication_asset is not created.
-- papers, paper_pages, confirmations, practice_item, and approvals stay as they are.

CREATE TABLE publication (
    publication_id text PRIMARY KEY,
    question_version_id text NOT NULL,
    answer_version_id text NOT NULL,
    layout_template_id text NULL,
    subject_id text NOT NULL,
    status text NOT NULL DEFAULT 'active',
    CONSTRAINT publication_status_known CHECK (status IN ('active', 'retired')),
    CONSTRAINT publication_binding_unique UNIQUE (question_version_id, answer_version_id, status)
);

-- One active row for each approval that has both sides approved and is not retired.
-- publication_id is deterministic so the row can be found again.
-- approvals.retired is boolean NOT NULL, so NOT retired is enough.
-- A retired approval is not copied. A later publish creates the new row.

INSERT INTO publication (
    publication_id,
    question_version_id,
    answer_version_id,
    subject_id,
    status
)
SELECT
    'pub-' || question_version_id || '-' || answer_version_id AS publication_id,
    question_version_id,
    answer_version_id,
    subject_id,
    'active'
FROM approvals
WHERE question_approved = true
  AND answer_approved = true
  AND NOT retired;
