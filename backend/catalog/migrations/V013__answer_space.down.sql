-- Drop the flow-layout table and the columns added for answer space.
-- Stored box rows and the answer_space values are discarded.

DROP TABLE IF EXISTS practice_item_box;

ALTER TABLE practice_item DROP COLUMN IF EXISTS placed_lines;

ALTER TABLE papers DROP CONSTRAINT IF EXISTS papers_layout_kind_value;

ALTER TABLE papers DROP COLUMN IF EXISTS layout_params;

ALTER TABLE papers DROP COLUMN IF EXISTS layout_kind;

ALTER TABLE approvals DROP CONSTRAINT IF EXISTS approvals_answer_space_value;

ALTER TABLE approvals DROP COLUMN IF EXISTS answer_space;
