-- R4d answer space and flow layout.
-- Old approval rows keep answer_space NULL, which means the type default.
-- Old papers keep layout_kind slots and are not reflowed.
-- The runner holds pg_advisory_xact_lock. This file does not.

ALTER TABLE approvals ADD COLUMN answer_space text;

ALTER TABLE approvals ADD CONSTRAINT approvals_answer_space_value
    CHECK (answer_space IS NULL OR answer_space IN ('letter', 'blanks', 'small', 'medium', 'large', 'full'));

ALTER TABLE papers ADD COLUMN layout_kind text NOT NULL DEFAULT 'slots';

ALTER TABLE papers ADD CONSTRAINT papers_layout_kind_value
    CHECK (layout_kind IN ('slots', 'flow'));

ALTER TABLE papers ADD COLUMN layout_params text;

ALTER TABLE practice_item ADD COLUMN placed_lines text;

CREATE TABLE practice_item_box (
    paper_id text NOT NULL REFERENCES papers (paper_id) ON DELETE CASCADE,
    order_no integer NOT NULL,
    box_no integer NOT NULL,
    page_no integer NOT NULL,
    x double precision NOT NULL,
    y double precision NOT NULL,
    w double precision NOT NULL,
    h double precision NOT NULL,
    kind text NOT NULL,
    PRIMARY KEY (paper_id, order_no, box_no)
);
