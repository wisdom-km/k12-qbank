-- Reverse V005. schema_migrations stays; the runner deletes the version row.
-- questions and answers stay. V004 owns those tables.

DROP TABLE IF EXISTS question_option;
DROP TABLE IF EXISTS question_asset;
DROP TABLE IF EXISTS sub_question;
DROP TABLE IF EXISTS answer_part;
DROP TABLE IF EXISTS answer_asset;

ALTER TABLE approvals DROP CONSTRAINT IF EXISTS approvals_type_structure_check;
ALTER TABLE approvals DROP COLUMN IF EXISTS structure;
ALTER TABLE approvals DROP COLUMN IF EXISTS type;
